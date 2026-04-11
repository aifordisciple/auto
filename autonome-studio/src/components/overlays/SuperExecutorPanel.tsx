"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import {
  X,
  Play,
  Loader2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  FileCode,
  FolderOpen,
  Zap,
  RefreshCw,
  Download,
  Eye,
  Copy,
  ExternalLink,
  Bot
} from "lucide-react";

import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { BASE_URL } from "@/lib/api";

// ==========================================
// ✨ 类型定义
// ==========================================

interface CodeBlock {
  language: string;
  order: number;
  code_preview: string;
}

interface PathMapping {
  [fake: string]: string;
}

interface ExecutionResult {
  order: number;
  language: string;
  status: string;
  exit_code: number;
  retry_count: number;
  error?: string;
}

interface GeneratedFile {
  path: string;
  name: string;
  size: number;
  extension: string;
}

interface BattleReport {
  task_out_dir?: string;  // 任务输出目录路径
  success_count: number;
  failed_count: number;
  total_retries: number;
  path_mappings: PathMapping;
  generated_files: GeneratedFile[];
  execution_summary: ExecutionResult[];
}

type ExecutionStatus = "idle" | "parsing" | "resolving" | "executing" | "debugging" | "generating_report" | "completed" | "error" | "understanding";

// 自然语言模式的事件数据类型
interface NaturalLanguageResponse {
  message: string;
  tool_used?: string;
  result_preview?: string;
}

interface ToolCall {
  tool: string;
  parameters: Record<string, unknown>;
}

interface ToolResult {
  tool: string;
  result: string;
}

// ==========================================
// ✨ Claude 权限类型
// ==========================================

interface ClaudePermission {
  allowed: boolean;
  modes: string[];
  message: string;
}

// ==========================================
// ✨ 状态徽章组件
// ==========================================

function StatusBadge({ status }: { status: ExecutionStatus }) {
  const statusConfig: Record<ExecutionStatus, { color: string; icon: React.ReactNode; text: string }> = {
    idle: { color: "bg-neutral-700 text-neutral-400", icon: null, text: "等待输入" },
    parsing: { color: "bg-blue-500/20 text-blue-400", icon: <Loader2 size={14} className="animate-spin" />, text: "解析代码" },
    resolving: { color: "bg-purple-500/20 text-purple-400", icon: <Loader2 size={14} className="animate-spin" />, text: "解析路径" },
    executing: { color: "bg-orange-500/20 text-orange-400", icon: <Loader2 size={14} className="animate-spin" />, text: "执行中" },
    debugging: { color: "bg-yellow-500/20 text-yellow-400", icon: <RefreshCw size={14} className="animate-spin" />, text: "自动修复" },
    generating_report: { color: "bg-cyan-500/20 text-cyan-400", icon: <Loader2 size={14} className="animate-spin" />, text: "生成战报" },
    completed: { color: "bg-green-500/20 text-green-400", icon: <CheckCircle size={14} />, text: "执行完成" },
    error: { color: "bg-red-500/20 text-red-400", icon: <XCircle size={14} />, text: "执行失败" },
    understanding: { color: "bg-cyan-500/20 text-cyan-400", icon: <Loader2 size={14} className="animate-spin" />, text: "理解指令" }
  };

  const config = statusConfig[status];

  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${config.color}`}>
      {config.icon}
      <span>{config.text}</span>
    </div>
  );
}

// ==========================================
// ✨ 战报卡片组件
// ==========================================

function BattleReportView({ report }: { report: BattleReport | null }) {
  if (!report) return null;

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  const getFileIcon = (ext: string) => {
    const imageExts = [".png", ".jpg", ".jpeg", ".pdf", ".svg"];
    const dataExts = [".csv", ".tsv", ".xlsx", ".h5", ".h5ad"];
    if (imageExts.includes(ext)) return "🖼️";
    if (dataExts.includes(ext)) return "📊";
    return "📄";
  };

  // 判断文件是否可预览
  const isPreviewable = (ext: string) => {
    const previewableExts = [".png", ".jpg", ".jpeg", ".svg", ".pdf", ".txt", ".csv", ".tsv", ".json", ".md"];
    return previewableExts.includes(ext);
  };

  // 复制路径到剪贴板
  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      // 可以添加 toast 提示
    } catch (err) {
      console.error("复制失败:", err);
    }
  };

  // 下载文件
  const downloadFile = (filePath: string, fileName: string) => {
    // 构建 API URL（使用完整 URL）
    const token = localStorage.getItem("autonome_access_token");
    const downloadUrl = `${BASE_URL}/api/super-executor/files/download?path=${encodeURIComponent(filePath)}&token=${token}`;

    // 创建下载链接
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = fileName;
    link.target = "_blank";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // 预览文件
  const previewFile = (filePath: string) => {
    const token = localStorage.getItem("autonome_access_token");
    const previewUrl = `${BASE_URL}/api/super-executor/files/preview?path=${encodeURIComponent(filePath)}&token=${token}`;
    window.open(previewUrl, "_blank");
  };

  return (
    <div className="space-y-6">
      {/* 输出目录路径 */}
      {report.task_out_dir && (
        <div className="p-4 bg-neutral-900/50 border border-neutral-800 rounded-xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FolderOpen size={16} className="text-cyan-400" />
              <span className="text-sm text-neutral-400">输出目录:</span>
            </div>
            <button
              onClick={() => copyToClipboard(report.task_out_dir!)}
              className="flex items-center gap-1 px-2 py-1 text-xs text-neutral-400 hover:text-white hover:bg-neutral-700 rounded transition-colors"
              title="复制路径"
            >
              <Copy size={12} />
              复制
            </button>
          </div>
          <div className="mt-2 p-2 bg-neutral-800 rounded font-mono text-xs text-cyan-400 break-all">
            {report.task_out_dir}
          </div>
        </div>
      )}

      {/* 执行摘要 */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4 text-center">
          <div className="text-3xl font-bold text-green-400">{report.success_count}</div>
          <div className="text-sm text-green-300 mt-1">成功</div>
        </div>
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-center">
          <div className="text-3xl font-bold text-red-400">{report.failed_count}</div>
          <div className="text-sm text-red-300 mt-1">失败</div>
        </div>
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 text-center">
          <div className="text-3xl font-bold text-yellow-400">{report.total_retries}</div>
          <div className="text-sm text-yellow-300 mt-1">重试次数</div>
        </div>
      </div>

      {/* 路径映射表 */}
      {Object.keys(report.path_mappings).length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-neutral-300 mb-2 flex items-center gap-2">
            <FolderOpen size={14} />
            路径映射
          </h3>
          <div className="bg-neutral-900/50 border border-neutral-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-neutral-800/50">
                <tr>
                  <th className="px-3 py-2 text-left text-neutral-400">假路径</th>
                  <th className="px-3 py-2 text-left text-neutral-400">真实路径</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.path_mappings).map(([fake, real], idx) => (
                  <tr key={`path-${idx}-${fake.slice(0, 20)}`} className="border-t border-neutral-800">
                    <td className="px-3 py-2 text-neutral-400 font-mono text-xs truncate max-w-[200px]">{fake}</td>
                    <td className="px-3 py-2 text-green-400 font-mono text-xs truncate max-w-[250px]">{real}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 执行详情 */}
      {report.execution_summary && report.execution_summary.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-neutral-300 mb-2 flex items-center gap-2">
            <FileCode size={14} />
            执行详情
          </h3>
          <div className="space-y-2">
            {report.execution_summary.map((result, idx) => (
              <div
                key={idx}
                className={`p-3 rounded-lg border ${
                  result.exit_code === 0
                    ? "bg-green-500/5 border-green-500/20"
                    : "bg-red-500/5 border-red-500/20"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      result.language === "python" ? "bg-blue-500/20 text-blue-400" : "bg-purple-500/20 text-purple-400"
                    }`}>
                      {result.language.toUpperCase()}
                    </span>
                    <span className="text-neutral-300 text-sm">代码块 #{result.order + 1}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {result.retry_count > 0 && (
                      <span className="text-yellow-400 text-xs">重试 {result.retry_count} 次</span>
                    )}
                    {result.exit_code === 0 ? (
                      <CheckCircle size={16} className="text-green-400" />
                    ) : (
                      <XCircle size={16} className="text-red-400" />
                    )}
                  </div>
                </div>
                {result.error && (
                  <div className="mt-2 p-2 bg-red-900/20 rounded text-xs text-red-300 font-mono overflow-x-auto">
                    {result.error}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 生成文件 */}
      {report.generated_files && report.generated_files.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-neutral-300 mb-2 flex items-center gap-2">
            <Zap size={14} />
            生成文件 ({report.generated_files.length})
          </h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {report.generated_files.map((file, idx) => (
              <div
                key={idx}
                className="flex items-center gap-3 p-3 bg-neutral-800/50 rounded-lg border border-neutral-700 hover:border-neutral-600 transition-colors"
              >
                <span className="text-lg flex-shrink-0">{getFileIcon(file.extension)}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-neutral-200 truncate" title={file.name}>{file.name}</div>
                  <div className="text-xs text-neutral-500">{formatSize(file.size)}</div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  {/* 预览按钮 */}
                  {isPreviewable(file.extension) && (
                    <button
                      onClick={() => previewFile(file.path)}
                      className="p-1.5 text-neutral-400 hover:text-cyan-400 hover:bg-neutral-700 rounded transition-colors"
                      title="预览"
                    >
                      <Eye size={14} />
                    </button>
                  )}
                  {/* 下载按钮 */}
                  <button
                    onClick={() => downloadFile(file.path, file.name)}
                    className="p-1.5 text-neutral-400 hover:text-green-400 hover:bg-neutral-700 rounded transition-colors"
                    title="下载"
                  >
                    <Download size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ==========================================
// ✨ 主组件
// ==========================================

export function SuperExecutorPanel() {
  const { closeSuperExecutor, isSuperExecutorOpen } = useUIStore();
  const currentProjectId = useWorkspaceStore(state => state.currentProjectId);

  // Claude 权限状态
  const [claudePermission, setClaudePermission] = useState<ClaudePermission | null>(null);

  // 状态
  const [inputValue, setInputValue] = useState("");
  const [status, setStatus] = useState<ExecutionStatus>("idle");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [codeBlocks, setCodeBlocks] = useState<CodeBlock[]>([]);
  const [pathMappings, setPathMappings] = useState<PathMapping>({});
  const [battleReport, setBattleReport] = useState<BattleReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 自然语言模式状态
  const [inputMode, setInputMode] = useState<"code_blocks" | "natural_language" | null>(null);
  const [nlResponse, setNlResponse] = useState<NaturalLanguageResponse | null>(null);
  const [toolCall, setToolCall] = useState<ToolCall | null>(null);
  const [toolResult, setToolResult] = useState<ToolResult | null>(null);

  // SSE 相关
  const eventSourceRef = useRef<EventSource | null>(null);

  // 检查 Claude Code 权限
  useEffect(() => {
    const checkPermission = async () => {
      try {
        const token = localStorage.getItem("token");
        if (!token) return;

        const response = await fetch("/api/claude-executor/check-permission", {
          headers: {
            "Authorization": `Bearer ${token}`
          }
        });

        if (response.ok) {
          const data = await response.json();
          setClaudePermission(data);
        }
      } catch (e) {
        console.error("检查 Claude 权限失败:", e);
      }
    };

    if (isSuperExecutorOpen) {
      checkPermission();
    }
  }, [isSuperExecutorOpen]);

  // 清理 SSE 连接
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // 处理 SSE 事件
  const handleSSEEvent = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);

      switch (event.type || "message") {
        case "mode_detected":
          setInputMode(data.mode);
          break;

        case "status_update":
          setStatus(data.status as ExecutionStatus);
          break;

        case "code_extracted":
          setCodeBlocks(data.blocks || []);
          break;

        case "path_resolved":
          setPathMappings(data.mappings || {});
          if (data.unresolved && data.unresolved.length > 0) {
            console.warn("未解析的路径:", data.unresolved);
          }
          break;

        case "execution_progress":
          // 可以用来更新进度条
          break;

        case "debug_retry":
          setStatus("debugging");
          break;

        case "battle_report":
          setBattleReport(data);
          setStatus("completed");
          break;

        case "tool_call":
          setToolCall(data);
          break;

        case "tool_result":
          setToolResult(data);
          break;

        case "natural_language_response":
          setNlResponse(data);
          setStatus("completed");
          break;

        case "error":
          setError(data.error || "执行失败");
          setStatus("error");
          break;

        case "done":
          if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
          }
          break;

        case "heartbeat":
          // 心跳，忽略
          break;
      }
    } catch (e) {
      console.error("解析 SSE 事件失败:", e);
    }
  }, []);

  // 关闭面板时清理
  const handleClose = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setInputValue("");
    setStatus("idle");
    setTaskId(null);
    setCodeBlocks([]);
    setPathMappings({});
    setBattleReport(null);
    setError(null);
    // 重置自然语言模式状态
    setInputMode(null);
    setNlResponse(null);
    setToolCall(null);
    setToolResult(null);
    closeSuperExecutor();
  }, [closeSuperExecutor]);

  // 开始执行
  const handleExecute = useCallback(async () => {
    if (!inputValue.trim() || !currentProjectId) return;

    // ✨ 自动判断执行模式：根据用户权限决定使用 Claude Code 还是 V4 引擎
    // 优先级：宿主机 > 容器 > V4 引擎
    let useClaudeMode: 'host' | 'container' | null = null;

    if (claudePermission?.allowed && claudePermission.modes.length > 0) {
      if (claudePermission.modes.includes('host')) {
        useClaudeMode = 'host';
      } else if (claudePermission.modes.includes('container')) {
        useClaudeMode = 'container';
      }
    }

    // Claude Code 模式 - 打开终端
    if (useClaudeMode) {
      await handleClaudeExecute(useClaudeMode);
      return;
    }

    // V4 模式 - 原有逻辑
    setStatus("parsing");
    setError(null);
    setCodeBlocks([]);
    setPathMappings({});
    setBattleReport(null);
    // 重置自然语言模式状态
    setInputMode(null);
    setNlResponse(null);
    setToolCall(null);
    setToolResult(null);

    try {
      // 获取 token
      const token = localStorage.getItem("token");
      if (!token) {
        setError("未登录，请先登录");
        setStatus("error");
        return;
      }

      // 提交任务
      const response = await fetch("/api/super-executor/execute", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          project_id: currentProjectId,
          raw_input: inputValue
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "提交失败");
      }

      const result = await response.json();
      setTaskId(result.task_id);

      // 建立 SSE 连接
      const eventSource = new EventSource(
        `/api/super-executor/${result.task_id}/events/stream?token=${token}`
      );
      eventSourceRef.current = eventSource;

      eventSource.onmessage = handleSSEEvent;
      eventSource.onerror = (e) => {
        console.error("SSE 错误:", e);
        eventSource.close();
        eventSourceRef.current = null;
      };

    } catch (e: any) {
      setError(e.message || "执行失败");
      setStatus("error");
    }
  }, [inputValue, currentProjectId, handleSSEEvent, claudePermission]);

  // Claude Code 模式执行
  const handleClaudeExecute = useCallback(async (mode: 'host' | 'container') => {
    setStatus("parsing");
    setError(null);

    try {
      const token = localStorage.getItem("token");
      if (!token) {
        setError("未登录，请先登录");
        setStatus("error");
        return;
      }

      // 调用 Claude 执行器 API
      const response = await fetch("/api/claude-executor/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          project_id: currentProjectId,
          prompt: inputValue,
          mode: mode
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "启动失败");
      }

      const result = await response.json();

      // 打开终端
      const { openClaudeTerminal } = useUIStore.getState();
      if (openClaudeTerminal) {
        openClaudeTerminal(result.session_id);
      }

      // 关闭面板
      handleClose();

    } catch (e: any) {
      setError(e.message || "执行失败");
      setStatus("error");
    }
  }, [inputValue, currentProjectId, handleClose]);

  if (!isSuperExecutorOpen) return null;

  return (
    <>
      {/* 背景遮罩 */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={handleClose}
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm cursor-pointer"
      />

      {/* 面板主体 */}
      <motion.div
        initial={{ x: "100%", opacity: 0.5 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: "100%", opacity: 0.5 }}
        transition={{ type: "spring", damping: 25, stiffness: 200 }}
        className="fixed top-0 right-0 bottom-0 z-50 w-full md:w-[600px] bg-neutral-950 border-l border-neutral-800 shadow-2xl flex flex-col"
      >
        {/* 头部 */}
        <div className="h-16 border-b border-neutral-800 flex items-center justify-between px-4 md:px-6 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-500/10 rounded-lg">
              <Zap size={20} className="text-green-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">超级执行者</h2>
              <p className="text-xs text-neutral-500">执行代码块或自然语言指令，自动排错</p>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-md transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* 执行模式提示 */}
        {claudePermission?.allowed && claudePermission.modes.length > 0 && (
          <div className="px-4 md:px-6 py-2 bg-blue-500/5 border-b border-blue-500/10 shrink-0">
            <div className="flex items-center gap-2 text-xs">
              <Zap size={12} className="text-blue-400" />
              <span className="text-blue-300">
                执行模式: {claudePermission.modes.includes('host') ? 'Claude Code (宿主机)' : 'Claude Code (容器)'}
              </span>
            </div>
          </div>
        )}

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
          {/* 输入区 */}
          <div>
            <label className="block text-sm font-medium text-neutral-300 mb-2">
              粘贴外部 AI 输出
            </label>
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder='粘贴外部 AI 代码（```python 或 ```r），或输入自然语言指令（如"列出项目文件"、"预览 counts.csv"）...'
              className="w-full h-48 bg-neutral-900 border border-neutral-800 rounded-xl p-4 text-sm text-neutral-200 placeholder-neutral-600 resize-none focus:outline-none focus:ring-1 focus:ring-green-500/50 focus:border-green-500/50"
              disabled={status !== "idle" && status !== "completed" && status !== "error"}
            />
          </div>

          {/* 状态显示 */}
          {status !== "idle" && (
            <div className="flex items-center justify-between p-4 bg-neutral-900/50 border border-neutral-800 rounded-xl">
              <StatusBadge status={status} />
              {taskId && (
                <span className="text-xs text-neutral-500 font-mono">Task: {taskId.slice(0, 8)}</span>
              )}
            </div>
          )}

          {/* 代码块预览 */}
          {codeBlocks.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-neutral-300 mb-2">
                检测到 {codeBlocks.length} 个代码块
              </h3>
              <div className="space-y-2">
                {codeBlocks.map((block, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-neutral-900 border border-neutral-800 rounded-lg"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        block.language === "python" ? "bg-blue-500/20 text-blue-400" : "bg-purple-500/20 text-purple-400"
                      }`}>
                        {block.language.toUpperCase()}
                      </span>
                      <span className="text-xs text-neutral-500">代码块 #{block.order + 1}</span>
                    </div>
                    <pre className="text-xs text-neutral-400 font-mono overflow-x-auto">
                      {block.code_preview}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 自然语言模式结果 */}
          {inputMode === "natural_language" && (
            <div className="space-y-4">
              {/* 模式提示 */}
              <div className="p-3 bg-cyan-500/10 border border-cyan-500/20 rounded-lg">
                <div className="flex items-center gap-2 text-cyan-400">
                  <Zap size={16} />
                  <span className="text-sm">自然语言指令模式</span>
                </div>
              </div>

              {/* 工具调用信息 */}
              {toolCall && (
                <div className="p-3 bg-neutral-900 border border-neutral-800 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs text-neutral-500">调用工具:</span>
                    <span className="px-2 py-0.5 bg-green-500/20 text-green-400 rounded text-xs font-mono">
                      {toolCall.tool}
                    </span>
                  </div>
                  <pre className="text-xs text-neutral-400 font-mono overflow-x-auto">
                    {JSON.stringify(toolCall.parameters, null, 2)}
                  </pre>
                </div>
              )}

              {/* 工具执行结果 */}
              {toolResult && (
                <div className="p-3 bg-neutral-900 border border-neutral-800 rounded-lg">
                  <h4 className="text-sm font-medium text-neutral-300 mb-2">执行结果</h4>
                  <pre className="text-xs text-neutral-400 font-mono overflow-x-auto whitespace-pre-wrap max-h-96">
                    {toolResult.result}
                  </pre>
                </div>
              )}

              {/* LLM 响应 */}
              {nlResponse && (
                <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-xl">
                  <div className="flex items-center gap-2 text-green-400 mb-2">
                    <CheckCircle size={16} />
                    <span className="font-medium">{nlResponse.message}</span>
                  </div>
                  {nlResponse.tool_used && (
                    <p className="text-sm text-neutral-400">
                      使用工具: <span className="text-green-400 font-mono">{nlResponse.tool_used}</span>
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 错误显示 */}
          {error && (
            <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl">
              <div className="flex items-center gap-2 text-red-400">
                <AlertTriangle size={16} />
                <span className="font-medium">执行错误</span>
              </div>
              <p className="mt-2 text-sm text-red-300">{error}</p>
            </div>
          )}

          {/* 战报 */}
          {battleReport && <BattleReportView report={battleReport} />}
        </div>

        {/* 底部操作栏 */}
        <div className="h-16 border-t border-neutral-800 flex items-center justify-end gap-3 px-4 md:px-6 shrink-0">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors"
          >
            关闭
          </button>
          <button
            onClick={handleExecute}
            disabled={!inputValue.trim() || (status !== "idle" && status !== "completed" && status !== "error")}
            className="px-6 py-2 bg-green-600 hover:bg-green-700 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
          >
            {status !== "idle" && status !== "completed" && status !== "error" ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                执行中...
              </>
            ) : (
              <>
                <Play size={16} />
                开始执行
              </>
            )}
          </button>
        </div>
      </motion.div>
    </>
  );
}

export default SuperExecutorPanel;