"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X, Maximize2, Minimize2, Bot, CheckCircle, XCircle, AlertCircle,
  FileText, Code2, Terminal, Wrench, Loader2, ChevronDown, ChevronRight
} from "lucide-react";
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { getToken } from "@/lib/api";

const log = {
  info: (msg: string) => console.log(`%c[ClaudeTerminal] ${msg}`, "color: #3B82F6"),
  error: (msg: string, ...args: unknown[]) => console.error(`[ClaudeTerminal] ${msg}`, ...args),
};

// ==========================================
// 类型定义
// ==========================================

type TabType = 'logs' | 'terminal';

interface WSMessage {
  type: "status" | "output" | "battle_report" | "error";
  status?: string;
  message?: string;
  content?: string;
  data?: unknown;
  exit_code?: number;
  execution_time?: number;
  timestamp?: string;
}

// 结构化事件类型
interface SessionInfo {
  type: "session_info";
  model: string;
  tools: string[];
  cwd: string;
  permission_mode?: string;
  session_id?: string;
}

interface ToolCall {
  type: "tool_call";
  name: string;
  input: Record<string, unknown>;
  call_id?: string;
  input_preview?: string;
  status?: 'pending' | 'success' | 'error';
  output_preview?: string;
}

interface ToolResult {
  type: "tool_result";
  call_id: string;
  status: 'success' | 'error';
  output_preview?: string;
}

interface ThinkingEvent {
  type: "thinking";
  content: string;
}

interface ResultEvent {
  type: "result";
  content?: string;
  cost_usd?: number;
  duration_ms?: number;
  is_error?: boolean;
}

type StructuredEvent = SessionInfo | ToolCall | ToolResult | ThinkingEvent | ResultEvent;

interface BattleReport {
  success: boolean;
  files_created: string[];
  files_modified: string[];
  commands_executed: string[];
  errors: string[];
  summary: string;
  output_preview: string;
}

// ==========================================
// 工具调用卡片组件
// ==========================================

function ToolCallCard({ call }: { call: ToolCall }) {
  const [expanded, setExpanded] = useState(false);

  const getToolIcon = (name: string) => {
    switch (name) {
      case 'Read': return <FileText size={14} className="text-blue-400" />;
      case 'Write': return <FileText size={14} className="text-green-400" />;
      case 'Edit': return <Code2 size={14} className="text-yellow-400" />;
      case 'Bash': return <Terminal size={14} className="text-purple-400" />;
      default: return <Wrench size={14} className="text-neutral-400" />;
    }
  };

  const statusIcon = call.status === 'pending' ? (
    <Loader2 size={12} className="animate-spin text-blue-400" />
  ) : call.status === 'success' ? (
    <CheckCircle size={12} className="text-green-400" />
  ) : call.status === 'error' ? (
    <XCircle size={12} className="text-red-400" />
  ) : null;

  return (
    <div className="bg-neutral-900/50 border border-neutral-800 rounded-lg overflow-hidden">
      <div
        className="flex items-center justify-between p-2 cursor-pointer hover:bg-neutral-800/50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          {getToolIcon(call.name)}
          <span className="text-sm text-neutral-300">{call.name}</span>
          {call.input_preview && (
            <span className="text-xs text-neutral-500 truncate max-w-[200px]">{call.input_preview}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {statusIcon}
          {expanded ? <ChevronDown size={14} className="text-neutral-500" /> : <ChevronRight size={14} className="text-neutral-500" />}
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            className="border-t border-neutral-800"
          >
            <div className="p-2 space-y-2 text-xs">
              {/* 输入参数 */}
              <div>
                <span className="text-neutral-500">输入:</span>
                <pre className="mt-1 p-2 bg-neutral-800/50 rounded text-neutral-400 overflow-x-auto">
                  {JSON.stringify(call.input, null, 2)}
                </pre>
              </div>
              {/* 输出预览 */}
              {call.output_preview && (
                <div>
                  <span className="text-neutral-500">输出:</span>
                  <pre className="mt-1 p-2 bg-neutral-800/50 rounded text-neutral-400 overflow-x-auto whitespace-pre-wrap">
                    {call.output_preview}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ==========================================
// 思考过程面板
// ==========================================

function ThinkingPanel({ logs }: { logs: string[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  // 自动滚动
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  if (logs.length === 0) return null;

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium text-neutral-400 flex items-center gap-2">
        <span>💭</span>
        <span>思考过程</span>
      </h4>
      <div
        ref={containerRef}
        className="max-h-48 overflow-y-auto space-y-2 p-2 bg-neutral-900/30 rounded-lg border border-neutral-800/50"
      >
        {logs.map((log, idx) => (
          <div key={idx} className="flex gap-2 text-sm">
            <span className="text-purple-400 shrink-0">›</span>
            <span className="text-neutral-300 break-words">{log}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==========================================
// 主组件
// ==========================================

export function ClaudeTerminal() {
  const { isClaudeTerminalOpen, closeClaudeTerminal, claudeSessionId, isTerminalFullscreen, toggleTerminalFullscreen } = useUIStore();
  const currentProjectId = useWorkspaceStore(state => state.currentProjectId);

  // Refs
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<any>(null);
  const fitAddonRef = useRef<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const isInitializedRef = useRef(false);

  // Tab 状态
  const [activeTab, setActiveTab] = useState<TabType>('logs');

  // 基础状态
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [executionStatus, setExecutionStatus] = useState<string>("idle");
  const [battleReport, setBattleReport] = useState<BattleReport | null>(null);

  // 结构化日志状态
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [toolCalls, setToolCalls] = useState<Map<string, ToolCall>>(new Map());
  const [thinkingLogs, setThinkingLogs] = useState<string[]>([]);
  const [toolCallOrder, setToolCallOrder] = useState<string[]>([]);

  // 处理结构化事件
  const handleStructuredEvent = useCallback((event: StructuredEvent) => {
    log.info(`收到结构化事件: ${event.type}`);

    switch (event.type) {
      case "session_info":
        setSessionInfo(event);
        break;

      case "tool_call":
        const call = event as ToolCall;
        call.status = 'pending';
        setToolCalls(prev => new Map(prev).set(call.call_id || `call_${Date.now()}`, call));
        setToolCallOrder(prev => [...prev, call.call_id || `call_${Date.now()}`]);
        break;

      case "tool_result":
        const result = event as ToolResult;
        setToolCalls(prev => {
          const newMap = new Map(prev);
          const existingCall = newMap.get(result.call_id);
          if (existingCall) {
            newMap.set(result.call_id, {
              ...existingCall,
              status: result.status,
              output_preview: result.output_preview
            });
          }
          return newMap;
        });
        break;

      case "thinking":
        setThinkingLogs(prev => [...prev, event.content]);
        break;

      case "result":
        // 最终结果
        break;
    }
  }, []);

  // 初始化终端并连接
  useEffect(() => {
    if (!isClaudeTerminalOpen || !claudeSessionId) return;

    const initAndConnect = async () => {
      if (isInitializedRef.current) return;
      isInitializedRef.current = true;

      try {
        // 动态导入 xterm
        const [{ Terminal: XTerm }, { FitAddon }] = await Promise.all([
          import("@xterm/xterm"),
          import("@xterm/addon-fit")
        ]);

        // 注入 CSS
        if (typeof document !== 'undefined' && !document.getElementById('xterm-css')) {
          const link = document.createElement('link');
          link.id = 'xterm-css';
          link.rel = 'stylesheet';
          link.href = 'https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css';
          document.head.appendChild(link);
        }

        // 创建终端
        const xterm = new XTerm({
          theme: {
            background: "#0a0a0a",
            foreground: "#e5e5e5",
            cursor: "#3B82F6",
            cursorAccent: "#0a0a0a",
            selectionBackground: "rgba(59, 130, 246, 0.3)",
          },
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
          fontSize: 14,
          cursorBlink: true,
          scrollback: 10000,
        });

        const fitAddon = new FitAddon();
        xterm.loadAddon(fitAddon);

        if (terminalRef.current) {
          xterm.open(terminalRef.current);
        }

        xtermRef.current = xterm;
        fitAddonRef.current = fitAddon;

        setTimeout(() => fitAddon.fit(), 100);
        log.info("终端已初始化");

        // 连接 WebSocket
        await connectWebSocket();

      } catch (error) {
        log.error("初始化失败:", error);
        setConnectionError("初始化失败");
      }
    };

    const connectWebSocket = async () => {
      if (!claudeSessionId) {
        setConnectionError("会话 ID 无效");
        return;
      }

      const token = getToken();
      if (!token) {
        setConnectionError("请先登录");
        return;
      }

      // 从 URL 参数获取 prompt（需要从 SuperExecutorPanel 传递）
      const urlParams = new URLSearchParams(window.location.search);
      const prompt = urlParams.get('claude_prompt') || "执行任务";

      // 构建 WebSocket URL
      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      let wsHost: string;
      if (process.env.NEXT_PUBLIC_API_URL) {
        wsHost = process.env.NEXT_PUBLIC_API_URL.replace(/^https?:\/\//, "");
      } else {
        wsHost = `${window.location.hostname}:8000`;
      }

      const wsUrl = `${wsProtocol}//${wsHost}/api/claude-executor/ws/${claudeSessionId}?token=${encodeURIComponent(token)}&prompt=${encodeURIComponent(prompt)}`;
      log.info(`WebSocket URL: ${wsProtocol}//${wsHost}/api/claude-executor/ws/...`);

      try {
        const ws = new WebSocket(wsUrl);
        ws.binaryType = "arraybuffer";
        wsRef.current = ws;

        ws.onopen = () => {
          log.info("✅ WebSocket onopen 触发");
          setIsConnected(true);
          setConnectionError(null);
          xtermRef.current?.write("\x1b[32m✅ 已连接到 Claude Code 执行器\x1b[0m\r\n");
        };

        ws.onmessage = (event) => {
          // 尝试解析消息
          if (typeof event.data === 'string') {
            // 检查是否是结构化事件
            if (event.data.startsWith('__STRUCTURED_EVENT__:')) {
              try {
                const eventJson = event.data.substring('__STRUCTURED_EVENT__:'.length);
                const structuredEvent: StructuredEvent = JSON.parse(eventJson);
                handleStructuredEvent(structuredEvent);
                return;
              } catch (e) {
                log.error("解析结构化事件失败:", e);
              }
            }

            // 尝试解析为 WSMessage
            try {
              const data: WSMessage = JSON.parse(event.data);
              handleMessage(data);
              return;
            } catch (e) {
              // 非结构化消息，直接输出到终端
            }

            // 原始文本输出到终端
            xtermRef.current?.write(event.data);
          } else if (event.data instanceof ArrayBuffer) {
            xtermRef.current?.write(new Uint8Array(event.data));
          }
        };

        ws.onerror = (e) => {
          log.error("WebSocket onerror", e);
          setConnectionError("连接错误");
          xtermRef.current?.write("\x1b[31m❌ 连接错误\x1b[0m\r\n");
        };

        ws.onclose = (event) => {
          log.info(`WebSocket onclose: code=${event.code}, reason=${event.reason}`);
          setIsConnected(false);
          xtermRef.current?.write(`\r\n\x1b[33m连接已关闭: ${event.reason || '完成'}\x1b[0m\r\n`);
        };

      } catch (e) {
        log.error("创建 WebSocket 失败", e);
        setConnectionError("创建连接失败");
      }
    };

    initAndConnect();

    // 清理函数
    return () => {
      log.info("清理终端");
      if (wsRef.current) {
        wsRef.current.close(1000, "关闭");
        wsRef.current = null;
      }
      if (xtermRef.current) {
        xtermRef.current.dispose();
        xtermRef.current = null;
      }
      isInitializedRef.current = false;
      setIsConnected(false);
    };
  }, [isClaudeTerminalOpen, claudeSessionId, handleStructuredEvent]);

  // 处理 WebSocket 消息
  const handleMessage = (data: WSMessage) => {
    switch (data.type) {
      case "status":
        setExecutionStatus(data.status || "unknown");
        xtermRef.current?.write(`\r\n\x1b[36m[${data.status}] ${data.message || ''}\x1b[0m\r\n`);
        break;

      case "output":
        if (data.content) {
          xtermRef.current?.write(data.content);
        } else if (data.data) {
          // JSON 格式的输出数据
          xtermRef.current?.write(JSON.stringify(data.data, null, 2));
        }
        break;

      case "battle_report":
        if (data.data) {
          setBattleReport(data.data as BattleReport);
          xtermRef.current?.write("\r\n\x1b[32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m\r\n");
          xtermRef.current?.write("\x1b[32m✅ 执行完成 - 战报已生成\x1b[0m\r\n");
          xtermRef.current?.write("\x1b[32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m\r\n");
        }
        break;

      case "error":
        xtermRef.current?.write(`\r\n\x1b[31m❌ 错误: ${data.message}\x1b[0m\r\n`);
        break;
    }
  };

  // 窗口大小变化
  useEffect(() => {
    if (!isClaudeTerminalOpen) return;

    const handleResize = () => {
      fitAddonRef.current?.fit();
    };

    window.addEventListener("resize", handleResize);
    setTimeout(handleResize, 100);

    return () => window.removeEventListener("resize", handleResize);
  }, [isClaudeTerminalOpen]);

  if (!isClaudeTerminalOpen) return null;

  // 获取按顺序排列的工具调用列表
  const orderedToolCalls = toolCallOrder
    .map(id => toolCalls.get(id))
    .filter((call): call is ToolCall => call !== undefined);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: "100%", opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: "100%", opacity: 0 }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className={`fixed z-50 bg-neutral-950 border-neutral-800 shadow-2xl flex flex-col ${
          isTerminalFullscreen ? "inset-0 border-0" : "bottom-0 left-0 right-0 h-[60vh] border-t"
        }`}
      >
        {/* 标题栏 */}
        <div className="h-10 border-b border-neutral-800 flex items-center justify-between px-4 shrink-0 bg-neutral-900">
          <div className="flex items-center gap-4">
            {/* Tab 按钮 */}
            <div className="flex items-center gap-1 bg-neutral-800/50 rounded-lg p-0.5">
              <button
                onClick={() => setActiveTab('logs')}
                className={`px-3 py-1 text-sm rounded-md transition-colors ${
                  activeTab === 'logs'
                    ? 'bg-neutral-700 text-white'
                    : 'text-neutral-400 hover:text-white'
                }`}
              >
                日志
              </button>
              <button
                onClick={() => setActiveTab('terminal')}
                className={`px-3 py-1 text-sm rounded-md transition-colors ${
                  activeTab === 'terminal'
                    ? 'bg-neutral-700 text-white'
                    : 'text-neutral-400 hover:text-white'
                }`}
              >
                终端
              </button>
            </div>

            <div className="flex items-center gap-2">
              <Bot size={16} className="text-blue-500" />
              <span className="text-sm text-neutral-300 font-medium">Claude Code</span>
              {sessionInfo && (
                <span className="text-xs text-neutral-500">• {sessionInfo.model}</span>
              )}
              <div className="flex items-center gap-1.5 ml-2">
                <div className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
                <span className="text-xs text-neutral-500">{isConnected ? "已连接" : "未连接"}</span>
              </div>
              {executionStatus !== "idle" && (
                <span className={`text-xs px-2 py-0.5 rounded ${
                  executionStatus === "completed" ? "bg-green-500/20 text-green-400" :
                  executionStatus === "error" ? "bg-red-500/20 text-red-400" :
                  "bg-blue-500/20 text-blue-400"
                }`}>
                  {executionStatus}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={toggleTerminalFullscreen} className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded">
              {isTerminalFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button onClick={closeClaudeTerminal} className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded">
              <X size={16} />
            </button>
          </div>
        </div>

        {/* 内容区域 */}
        <div className="flex-1 overflow-hidden relative">
          {connectionError && !isConnected && (
            <div className="absolute inset-0 flex items-center justify-center bg-neutral-950/80 z-10">
              <div className="flex items-center gap-2 text-red-400">
                <AlertCircle size={20} />
                <p>{connectionError}</p>
              </div>
            </div>
          )}

          {/* 日志 Tab */}
          {activeTab === 'logs' && (
            <div className="h-full overflow-y-auto p-4 space-y-4">
              {/* 会话信息卡片 */}
              {sessionInfo && (
                <div className="p-3 bg-neutral-900/50 border border-neutral-800 rounded-lg">
                  <div className="flex items-center gap-3">
                    <Bot size={20} className="text-blue-400" />
                    <div>
                      <div className="text-sm text-neutral-300 font-medium">{sessionInfo.model}</div>
                      <div className="text-xs text-neutral-500">
                        工具: {sessionInfo.tools?.slice(0, 4).join(', ')}{sessionInfo.tools && sessionInfo.tools.length > 4 ? '...' : ''}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* 思考过程 */}
              {thinkingLogs.length > 0 && (
                <ThinkingPanel logs={thinkingLogs} />
              )}

              {/* 工具调用时间线 */}
              {orderedToolCalls.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-medium text-neutral-400 flex items-center gap-2">
                    <Wrench size={14} />
                    <span>工具调用 ({orderedToolCalls.length})</span>
                  </h4>
                  <div className="space-y-2">
                    {orderedToolCalls.map((call, idx) => (
                      <ToolCallCard key={call.call_id || idx} call={call} />
                    ))}
                  </div>
                </div>
              )}

              {/* 空状态 */}
              {orderedToolCalls.length === 0 && thinkingLogs.length === 0 && (
                <div className="flex flex-col items-center justify-center h-48 text-neutral-500">
                  <Bot size={32} className="mb-2 opacity-50" />
                  <p className="text-sm">等待 Claude 开始执行...</p>
                </div>
              )}
            </div>
          )}

          {/* 终端 Tab */}
          {activeTab === 'terminal' && (
            <div ref={terminalRef} className="w-full h-full p-2" style={{ backgroundColor: "#0a0a0a" }} />
          )}
        </div>

        {/* 战报摘要 */}
        {battleReport && (
          <div className="h-auto max-h-32 border-t border-neutral-800 p-3 bg-neutral-900/50 overflow-y-auto">
            <div className="flex items-center gap-4 text-xs">
              {battleReport.success ? (
                <div className="flex items-center gap-1 text-green-400">
                  <CheckCircle size={14} />
                  <span>执行成功</span>
                </div>
              ) : (
                <div className="flex items-center gap-1 text-red-400">
                  <XCircle size={14} />
                  <span>执行失败</span>
                </div>
              )}
              {battleReport.files_created.length > 0 && (
                <span className="text-neutral-400">创建文件: {battleReport.files_created.length}</span>
              )}
              {battleReport.files_modified.length > 0 && (
                <span className="text-neutral-400">修改文件: {battleReport.files_modified.length}</span>
              )}
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

export default ClaudeTerminal;