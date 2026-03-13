"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Clock, CheckCircle, Loader2, XCircle, Edit3, Terminal, ChevronDown, ChevronUp, RefreshCw, Eye, ExternalLink, Copy, Check } from "lucide-react";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { useUIStore } from "@/store/useUIStore";
import { BASE_URL } from "@/lib/api";
import { fetchEventSource } from '@microsoft/fetch-event-source';

export interface StrategyCardData {
  title: string;
  description: string;
  tool_id: string;
  code?: string;
  parameters?: Record<string, unknown>;
  steps?: string[];
  estimated_time?: string;
  risk_level?: "low" | "medium" | "high";
}

interface StrategyCardProps {
  data: StrategyCardData;
  onExecute?: (taskId: string) => void;
  onCancel?: () => void;
}

// 日志弹窗组件
const LogModal = ({ taskId, isOpen, onClose }: { taskId: string; isOpen: boolean; onClose: () => void }) => {
  const [logs, setLogs] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const logEndRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    setLogs([]);
    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const fetchLogs = async () => {
      try {
        await fetchEventSource(`${BASE_URL}/api/tasks/${taskId}/logs/stream`, {
          method: 'GET',
          signal: controller.signal,
          onmessage(event) {
            if (event.event === 'log') {
              try {
                const data = JSON.parse(event.data);
                setLogs(prev => [...prev, data.text]);
              } catch (e) {
                // 忽略解析错误
              }
            } else if (event.event === 'done') {
              setIsLoading(false);
              controller.abort();
            }
          },
          onerror(err) {
            console.error('Log stream error:', err);
            setIsLoading(false);
          }
        });
      } catch (e) {
        setIsLoading(false);
      }
    };

    fetchLogs();

    return () => {
      controller.abort();
    };
  }, [taskId, isOpen]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          className="bg-white dark:bg-[#1a1a1c] border border-gray-200 dark:border-neutral-700 rounded-xl w-full max-w-3xl max-h-[80vh] flex flex-col shadow-2xl"
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900/50">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-green-500" />
              <span className="font-medium text-gray-900 dark:text-white">任务日志</span>
              <code className="text-xs bg-gray-200 dark:bg-neutral-800 px-2 py-0.5 rounded text-blue-600 dark:text-blue-400">{taskId.slice(0, 8)}</code>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
            >
              <XCircle className="w-5 h-5" />
            </button>
          </div>

          {/* Log Content */}
          <div className="flex-1 overflow-y-auto p-4 bg-gray-900 dark:bg-neutral-950 font-mono text-xs">
            {isLoading && logs.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-gray-500">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                加载日志中...
              </div>
            ) : logs.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-gray-500">
                暂无日志
              </div>
            ) : (
              <div className="space-y-0.5">
                {logs.map((log, i) => (
                  <div
                    key={i}
                    className={`py-0.5 px-1 hover:bg-white/5 rounded ${
                      log.includes('ERROR') || log.includes('❌') || log.includes('💥')
                        ? 'text-red-400'
                        : log.includes('WARNING') || log.includes('⚠️')
                        ? 'text-yellow-400'
                        : log.includes('✅') || log.includes('🎉') || log.includes('SUCCESS')
                        ? 'text-green-400'
                        : 'text-green-300/80'
                    }`}
                  >
                    {log}
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 border-t border-gray-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900/50">
            <div className="text-xs text-gray-500 dark:text-neutral-400">
              共 {logs.length} 条日志
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export function StrategyCard({ data, onExecute, onCancel }: StrategyCardProps) {
  const { currentProjectId, currentSessionId } = useWorkspaceStore();
  const { autoExecuteStrategy } = useUIStore();
  const [isExecuting, setIsExecuting] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const hasAutoExecuted = useRef(false); // 防止重复自动执行

  // 实时日志状态
  const [logs, setLogs] = useState<string[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  const [progressStatus, setProgressStatus] = useState<string | null>(null);
  const [retryAttempt, setRetryAttempt] = useState<number | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);
  const logAbortControllerRef = useRef<AbortController | null>(null);

  // ✨ 修复后的代码状态
  const [fixedCode, setFixedCode] = useState<string | null>(null);

  // 日志弹窗状态
  const [showLogModal, setShowLogModal] = useState(false);

  // 可编辑参数状态
  const [editableParams, setEditableParams] = useState<Record<string, unknown>>(data.parameters || {});
  const [isEditingParams, setIsEditingParams] = useState(false);

  // ✨ 可编辑代码状态
  const [editableCode, setEditableCode] = useState<string>(data.code || '');
  const [isEditingCode, setIsEditingCode] = useState(false);
  const [isCodeCopied, setIsCodeCopied] = useState(false);
  const codeEditorRef = useRef<HTMLTextAreaElement>(null);

  // 判断是否为 SKILL 类型（非 execute-python/execute-r）
  const isSkillType = data.tool_id !== 'execute-python' && data.tool_id !== 'execute-r';
  const hasCode = !isSkillType && (data.code || editableCode);

  // 复制代码到剪贴板（带降级方案）
  const handleCopyCode = async () => {
    const codeToCopy = isEditingCode ? editableCode : (data.code || editableCode);
    if (!codeToCopy) return;

    try {
      // 优先使用现代 Clipboard API
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(codeToCopy);
      } else {
        // 降级方案：使用 execCommand
        const textArea = document.createElement('textarea');
        textArea.value = codeToCopy;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        textArea.style.top = '0';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      setIsCodeCopied(true);
      setTimeout(() => setIsCodeCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  };

  // 获取语言类型
  const getCodeLanguage = () => {
    if (data.tool_id === 'execute-r') return 'r';
    return 'python';
  };

  // 任务完成后，滚动到对应的分析资产消息
  const scrollToResultMessage = (id: string) => {
    // 发送自定义事件，让 ChatStage 滚动到包含该任务结果的消息
    window.dispatchEvent(new CustomEvent('scroll-to-task-result', {
      detail: { taskId: id }
    }));
  };

  // 自动执行逻辑
  useEffect(() => {
    // 只有当自动执行开关打开、且还没有执行过、且没有缓存状态时才自动执行
    if (
      autoExecuteStrategy &&
      !hasAutoExecuted.current &&
      !taskId &&
      !taskStatus &&
      !isExecuting
    ) {
      hasAutoExecuted.current = true;
      // 稍微延迟一下，让用户看到卡片出现
      const timer = setTimeout(() => {
        handleExecute();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [autoExecuteStrategy, taskId, taskStatus, isExecuting]);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (logAbortControllerRef.current) {
        logAbortControllerRef.current.abort();
      }
    };
  }, []);

  // 自动滚动日志到底部
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // 连接日志流
  const connectLogStream = (id: string) => {
    setLogs([]); // 清空旧日志
    setShowLogs(true); // 自动展开日志窗口

    const controller = new AbortController();
    logAbortControllerRef.current = controller;

    const connect = async () => {
      try {
        await fetchEventSource(`${BASE_URL}/api/tasks/${id}/logs/stream`, {
          method: 'GET',
          signal: controller.signal,
          onmessage(event) {
            if (event.event === 'log') {
              try {
                const data = JSON.parse(event.data);
                const logText = data.text;

                // ✨ 检查是否是代码更新事件
                if (logText.startsWith('__CODE_UPDATE__:')) {
                  try {
                    const codeEventStr = logText.replace('__CODE_UPDATE__:', '');
                    const codeEvent = JSON.parse(codeEventStr);
                    if (codeEvent.type === 'code_update' && codeEvent.code) {
                      setFixedCode(codeEvent.code);
                      setLogs(prev => [...prev, `🔄 代码已由 AI 修复 (第 ${codeEvent.attempt} 次尝试)`]);
                    }
                  } catch (e) {
                    // 解析失败，当作普通日志处理
                    setLogs(prev => [...prev, logText]);
                  }
                } else {
                  // 普通日志
                  setLogs(prev => [...prev, logText]);
                }
              } catch (e) {
                // 忽略解析错误
              }
            } else if (event.event === 'done') {
              controller.abort();
            }
          },
          onerror(err) {
            console.error('Log stream error:', err);
          }
        });
      } catch (e) {
        // 忽略中止错误
      }
    };
    connect();
  };

  const connectWebSocket = (id: string) => {
    const token = localStorage.getItem('autonome_access_token');
    const wsUrl = `${BASE_URL.replace('http', 'ws')}/api/tasks/${id}/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected for task:', id);
      // 同时连接日志流
      connectLogStream(id);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        if (message.type === 'status') {
          setTaskStatus(message.status);
          setProgress(message.progress);
          // 捕获重试状态
          if (message.progress_status) {
            setProgressStatus(message.progress_status);
          }
          if (message.attempt) {
            setRetryAttempt(message.attempt);
          }

          if (message.status === 'SUCCESS' || message.status === 'FAILURE') {
            setIsExecuting(false);
            if (message.status === 'SUCCESS') {
              // 后端已将正确的消息存入数据库（包含实际生成的文件列表）
              // 只需触发刷新即可获取正确消息，添加短暂延迟确保后端写入完成
              setTimeout(() => {
                window.dispatchEvent(new CustomEvent('refresh-chat'));
              }, 500);
            }
            ws.close();
          }
        } else if (message.type === 'error') {
          setError(message.error);
          setIsExecuting(false);
          ws.close();
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      setError('WebSocket connection error');
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected for task:', id);
    };

    wsRef.current = ws;
  };

  const handleExecute = async () => {
    if (!data.tool_id) {
      setError("No tool selected");
      return;
    }

    setIsExecuting(true);
    setError(null);

    const safeSessionId = currentSessionId || 1;

    try {
      const token = localStorage.getItem('autonome_access_token');

      let payload: Record<string, unknown>;

      // Support both execute-python and execute-r
      // ✨ 使用编辑后的代码 (editableCode)，如果没有编辑则使用原始代码
      const codeToExecute = editableCode || data.code || '';
      if ((data.tool_id === 'execute-python' || data.tool_id === 'execute-r') && codeToExecute) {
        payload = {
          tool_id: data.tool_id,
          parameters: {
            code: codeToExecute,  // ✨ 使用可编辑的代码
            session_id: safeSessionId,
            project_id: currentProjectId
          },
          project_id: currentProjectId
        };
      } else {
        // ✨ SKILL 类型：使用用户编辑后的参数
        payload = {
          tool_id: data.tool_id,
          parameters: editableParams,  // 使用 editableParams 替代 data.parameters
          project_id: currentProjectId
        };
      }

      const response = await fetch(`${BASE_URL}/api/tasks/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(payload)
      });

      const result = await response.json();

      if (result.status === 'submitted') {
        setTaskId(result.task_id);
        onExecute?.(result.task_id);
        
        // Connect to WebSocket for real-time updates
        connectWebSocket(result.task_id);
      } else {
        setError(result.message || 'Failed to submit task');
        setIsExecuting(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setIsExecuting(false);
    }
  };

  const getStatusIcon = () => {
    if (isExecuting) return <Loader2 className="w-4 h-4 animate-spin text-blue-400" />;
    if (taskStatus === 'SUCCESS') return <CheckCircle className="w-4 h-4 text-green-400" />;
    if (taskStatus === 'FAILURE') return <XCircle className="w-4 h-4 text-red-400" />;
    return <Clock className="w-4 h-4 text-yellow-400" />;
  };

  const getRiskColor = (risk?: string) => {
    switch (risk) {
      case 'low': return 'bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/30';
      case 'medium': return 'bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/30';
      case 'high': return 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/30';
      default: return 'bg-gray-200 dark:bg-neutral-700/50 text-gray-600 dark:text-neutral-400 border-gray-300 dark:border-neutral-600';
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-gradient-to-br from-gray-50 to-gray-100 dark:from-neutral-900 dark:to-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-xl p-5 shadow-sm dark:shadow-xl my-4 max-w-2xl"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">{data.title}</h3>
          <div className="flex items-center gap-2">
            {data.estimated_time && (
              <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-neutral-400">
                <Clock className="w-3 h-3" />
                {data.estimated_time}
              </span>
            )}
            {data.risk_level && (
              <span className={`text-xs px-2 py-0.5 rounded-full border ${getRiskColor(data.risk_level)}`}>
                {data.risk_level.toUpperCase()} RISK
              </span>
            )}
          </div>
        </div>
        <div className="px-3 py-1.5 bg-blue-50 dark:bg-blue-600/20 border border-blue-200 dark:border-blue-500/30 rounded-lg">
          <span className="text-xs font-mono text-blue-700 dark:text-blue-400">{data.tool_id}</span>
        </div>
      </div>

      {/* Description */}
      <p className="text-sm text-gray-700 dark:text-neutral-300 mb-4">{data.description}</p>

      {/* Steps Preview */}
      {data.steps && data.steps.length > 0 && (
        <div className="bg-gray-100 dark:bg-neutral-950/50 rounded-lg p-3 mb-4">
          <p className="text-xs text-gray-500 dark:text-neutral-500 mb-2">执行步骤</p>
          <ul className="space-y-1">
            {data.steps.map((step, i) => (
              <li key={i} className="text-xs text-gray-600 dark:text-neutral-400 flex items-start gap-2">
                <span className="text-indigo-500 mt-0.5">•</span>
                {step}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ✨ 代码预览和编辑区域 - 带固定工具栏 */}
      {hasCode && (
        <div className="mb-4 rounded-lg overflow-hidden border border-gray-200 dark:border-neutral-700">
          {/* 固定工具栏 */}
          <div className="sticky top-0 z-10 flex items-center justify-between px-3 py-2 bg-gray-800 dark:bg-neutral-900 border-b border-gray-700 dark:border-neutral-700">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-gray-400">
                {getCodeLanguage() === 'r' ? 'R' : 'Python'}
              </span>
              <span className="text-xs text-gray-500">
                {editableCode.split('\n').length} 行
              </span>
            </div>
            <div className="flex items-center gap-1">
              {/* 复制按钮 */}
              <button
                onClick={handleCopyCode}
                className="flex items-center gap-1 px-2 py-1 text-xs text-gray-300 hover:text-white hover:bg-gray-700 rounded transition-colors"
                title="复制代码"
              >
                {isCodeCopied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-green-400" />
                    <span className="text-green-400">已复制</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">复制</span>
                  </>
                )}
              </button>
              {/* 编辑按钮 */}
              <button
                onClick={() => {
                  setIsEditingCode(!isEditingCode);
                  if (!isEditingCode) {
                    // 进入编辑模式时，聚焦到编辑器
                    setTimeout(() => codeEditorRef.current?.focus(), 100);
                  }
                }}
                className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
                  isEditingCode
                    ? 'text-blue-400 bg-blue-500/20 hover:bg-blue-500/30'
                    : 'text-gray-300 hover:text-white hover:bg-gray-700'
                }`}
                title={isEditingCode ? '完成编辑' : '编辑代码'}
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{isEditingCode ? '完成' : '编辑'}</span>
              </button>
            </div>
          </div>

          {/* 代码内容区域 */}
          <div className="relative bg-gray-900 dark:bg-neutral-950">
            {isEditingCode ? (
              // 编辑模式 - textarea
              <textarea
                ref={codeEditorRef}
                value={editableCode}
                onChange={(e) => setEditableCode(e.target.value)}
                className="w-full min-h-[200px] max-h-[400px] p-3 bg-transparent text-gray-300 font-mono text-xs leading-relaxed focus:outline-none resize-y"
                placeholder="在此编辑代码..."
                spellCheck={false}
              />
            ) : (
              // 只读模式 - pre
              <div className="max-h-[300px] overflow-auto">
                <pre className="p-3 text-xs leading-relaxed text-gray-300 font-mono whitespace-pre-wrap break-all">
                  {editableCode || data.code}
                </pre>
              </div>
            )}
          </div>

          {/* 编辑模式提示 */}
          {isEditingCode && (
            <div className="px-3 py-2 bg-amber-900/30 border-t border-amber-500/30">
              <p className="text-xs text-amber-300">
                💡 编辑代码后，点击"执行"按钮将运行修改后的代码
              </p>
            </div>
          )}
        </div>
      )}

      {/* Parameters Preview - ✨ 支持动态编辑 */}
      {data.parameters && Object.keys(data.parameters).length > 0 && (
        <div className="bg-gray-100 dark:bg-neutral-950/50 rounded-lg p-3 mb-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-gray-500 dark:text-neutral-500">Parameters</p>
            {isSkillType && (
              <button
                onClick={() => setIsEditingParams(!isEditingParams)}
                className="flex items-center gap-1 text-xs text-blue-500 hover:text-blue-400 transition-colors"
              >
                <Edit3 className="w-3 h-3" />
                {isEditingParams ? 'Done' : 'Edit'}
              </button>
            )}
          </div>

          {isEditingParams && isSkillType ? (
            // ✨ 动态参数编辑表单
            <div className="space-y-3">
              {Object.entries(editableParams).map(([key, value]) => {
                const isBool = typeof value === 'boolean' || value === 'true' || value === 'false';

                return (
                  <div key={key} className="flex items-center gap-3">
                    <label className="text-xs text-gray-600 dark:text-neutral-400 min-w-[120px]">
                      {key}
                    </label>
                    {isBool ? (
                      // 布尔值用下拉选择
                      <select
                        value={String(editableParams[key])}
                        onChange={(e) => setEditableParams({
                          ...editableParams,
                          [key]: e.target.value === 'true'
                        })}
                        className="flex-1 px-2 py-1 text-xs bg-gray-200 dark:bg-neutral-800 border border-gray-300 dark:border-neutral-600 rounded text-gray-700 dark:text-neutral-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    ) : (
                      // 其他类型用输入框
                      <input
                        type="text"
                        value={String(editableParams[key] ?? '')}
                        onChange={(e) => setEditableParams({
                          ...editableParams,
                          [key]: e.target.value
                        })}
                        className="flex-1 px-2 py-1 text-xs bg-gray-200 dark:bg-neutral-800 border border-gray-300 dark:border-neutral-600 rounded text-gray-700 dark:text-neutral-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            // 原有的参数展示
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.parameters).map(([key, value]) => (
                <span key={key} className="text-xs bg-gray-200 dark:bg-neutral-800 px-2 py-1 rounded text-gray-700 dark:text-neutral-300">
                  <span className="text-gray-500 dark:text-neutral-500">{key}:</span> {String(value)}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Status */}
      {(isExecuting || taskStatus) && (
        <div className="flex items-center gap-2 text-sm mb-2">
          {progressStatus === 'RETRY' ? (
            <RefreshCw className="w-4 h-4 text-yellow-500 animate-spin" />
          ) : (
            getStatusIcon()
          )}
          <span className="text-gray-700 dark:text-neutral-300">
            {progressStatus === 'RETRY' ? (
              `AI 修复中 (${retryAttempt || 1}/3)...`
            ) : isExecuting
              ? progress !== null
                ? `执行中... ${progress}%`
                : '启动中...'
              : `状态: ${taskStatus}`
            }
          </span>
          {progress !== null && progressStatus !== 'RETRY' && (
            <div className="flex-1 h-1.5 bg-gray-200 dark:bg-neutral-700 rounded-full overflow-hidden ml-2">
              <div
                className="h-full bg-blue-500 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>
      )}

      {/* 实时日志窗口 */}
      <AnimatePresence>
        {(isExecuting || logs.length > 0) && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-4 overflow-hidden"
          >
            <div
              className="bg-gray-900 dark:bg-neutral-950 border border-gray-700 dark:border-neutral-800 rounded-lg overflow-hidden"
            >
              {/* 日志头部 */}
              <div
                className="flex items-center justify-between px-3 py-2 bg-gray-800/50 dark:bg-neutral-900/50 cursor-pointer"
                onClick={() => setShowLogs(!showLogs)}
              >
                <div className="flex items-center gap-2">
                  <Terminal className="w-3.5 h-3.5 text-green-400" />
                  <span className="text-xs font-mono text-gray-300">执行日志</span>
                  {logs.length > 0 && (
                    <span className="text-[10px] text-gray-500">({logs.length} 行)</span>
                  )}
                </div>
                {showLogs ? (
                  <ChevronUp className="w-3.5 h-3.5 text-gray-500" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
                )}
              </div>

              {/* 日志内容 */}
              {showLogs && (
                <div className="max-h-48 overflow-y-auto p-2 font-mono text-[11px]">
                  {logs.length === 0 ? (
                    <div className="text-gray-500 text-center py-4">
                      <Loader2 className="w-4 h-4 animate-spin mx-auto mb-1" />
                      等待日志输出...
                    </div>
                  ) : (
                    logs.map((log, i) => (
                      <div
                        key={i}
                        className={`py-0.5 px-1 hover:bg-white/5 rounded ${
                          log.includes('ERROR') || log.includes('❌') || log.includes('💥')
                            ? 'text-red-400'
                            : log.includes('WARNING') || log.includes('⚠️')
                            ? 'text-yellow-400'
                            : log.includes('✅') || log.includes('🎉') || log.includes('SUCCESS')
                            ? 'text-green-400'
                            : 'text-green-300/80'
                        }`}
                      >
                        {log}
                      </div>
                    ))
                  )}
                  <div ref={logEndRef} />
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error */}
      {error && (
        <div className="bg-red-950/30 border border-red-500/30 rounded-lg p-3 mb-4">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        {!taskId ? (
          <>
            <button
              onClick={handleExecute}
              disabled={isExecuting}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              {isExecuting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Execute
            </button>
            {onCancel && (
              <button
                onClick={onCancel}
                className="px-4 py-2 bg-gray-200 dark:bg-neutral-700 hover:bg-gray-300 dark:hover:bg-neutral-600 text-gray-700 dark:text-white text-sm font-medium rounded-lg transition-colors"
              >
                Cancel
              </button>
            )}
          </>
        ) : (
          /* ✨ 任务完成状态行：状态徽章 + TaskID + 眼睛图标 */
          <div className="flex items-center gap-3 w-full">
            {/* 完成状态徽章 */}
            {taskStatus === 'SUCCESS' ? (
              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-green-100 dark:bg-green-900/30 border border-green-200 dark:border-green-500/30 rounded-lg">
                <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />
                <span className="text-sm font-medium text-green-700 dark:text-green-300">完成</span>
              </div>
            ) : taskStatus === 'FAILURE' ? (
              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-500/30 rounded-lg">
                <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
                <span className="text-sm font-medium text-red-700 dark:text-red-300">失败</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-lg">
                <Loader2 className="w-4 h-4 text-gray-500 animate-spin" />
                <span className="text-sm font-medium text-gray-600 dark:text-neutral-400">执行中</span>
              </div>
            )}

            {/* Task ID 组：ID + 跳转按钮 + 日志眼睛 */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => scrollToResultMessage(taskId)}
                className="group flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-neutral-800 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                title="点击跳转到分析结果"
              >
                <span className="text-xs text-gray-500 dark:text-neutral-500">Task</span>
                <code className="text-xs text-blue-600 dark:text-blue-400 font-mono font-medium">{taskId.slice(0, 8)}</code>
                <ExternalLink className="w-3 h-3 text-gray-400 group-hover:text-blue-500 transition-colors" />
              </button>
              {/* 眼睛图标 - 查看日志 */}
              <button
                onClick={() => setShowLogModal(true)}
                className="p-1.5 text-gray-400 hover:text-green-500 hover:bg-green-50 dark:hover:bg-green-900/20 rounded transition-colors"
                title="查看执行日志"
              >
                <Eye className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ✨ 修复后的代码预览 */}
      {taskId && fixedCode && (
        <div className="mt-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-500/30 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <RefreshCw className="w-4 h-4 text-amber-500" />
            <span className="text-xs font-medium text-amber-700 dark:text-amber-300">AI 修复后的代码</span>
          </div>
          <pre className="text-xs text-gray-700 dark:text-neutral-300 font-mono overflow-x-auto max-h-40 overflow-y-auto bg-gray-100 dark:bg-neutral-900/50 rounded p-2">
            {fixedCode}
          </pre>
        </div>
      )}

      {/* 日志弹窗 */}
      {taskId && (
        <LogModal
          taskId={taskId}
          isOpen={showLogModal}
          onClose={() => setShowLogModal(false)}
        />
      )}
    </motion.div>
  );
}

// Helper to parse strategy card from AI response
export function parseStrategyCard(content: string): StrategyCardData | null {
  if (!content) return null;

  try {
    let data = null;
    let jsonStr = "";

    // 🛡️ 终极防御：利用大括号深度匹配，完美抠出最准确的 JSON 对象，绝不会多包含任何 R 代码
    const extractJSON = (str: string) => {
      const start = str.indexOf('{');
      if (start === -1) return null;
      let depth = 0;
      for (let i = start; i < str.length; i++) {
        if (str[i] === '{') depth++;
        else if (str[i] === '}') {
          depth--;
          if (depth === 0) {
            return str.substring(start, i + 1);
          }
        }
      }
      return null;
    };

    // 1. 优先尝试从规范的代码块中提取
    const jsonMatch = content.match(/```(?:json_strategy|json)\s*\n([\s\S]*?)```/);
    if (jsonMatch) {
      jsonStr = jsonMatch[1];
    } else {
      // 2. 如果没有代码块，去全文寻找包含 "tool_id" 的最近的那个大括号包裹层
      const toolIdIndex = content.indexOf('"tool_id"');
      if (toolIdIndex !== -1) {
        const start = content.lastIndexOf('{', toolIdIndex);
        if (start !== -1) {
          jsonStr = extractJSON(content.substring(start)) || "";
        }
      }
    }

    // 清洗常见的 JSON 语法错误（如零宽空格、多余逗号）
    if (jsonStr) {
      jsonStr = jsonStr
        .replace(/\u00A0/g, ' ')
        .replace(/,\s*}/g, '}')
        .replace(/,\s*]/g, ']');
        
      try {
        data = JSON.parse(jsonStr);
      } catch (e) {
        console.error("JSON parse failed:", e, "\nRaw:", jsonStr.substring(0, 100));
      }
    }
    
    if (!data || !data.tool_id || !data.title) return null;

    // 强制统一工具 ID 命名规范
    if (data.tool_id === 'execute_r' || data.tool_id === 'R') {
      data.tool_id = 'execute-r';
    } else if (data.tool_id === 'execute_python' || data.tool_id === 'python') {
      data.tool_id = 'execute-python';
    }

    // 2. 提取需要执行的代码块
    let codeStr = "";
    const rMatch = content.match(/```(?:r|R)\s*\n([\s\S]*?)```/);
    const pyMatch = content.match(/```(?:python|Python)\s*\n([\s\S]*?)```/);
    
    if (rMatch) {
      codeStr = rMatch[1];
    } else if (pyMatch) {
      codeStr = pyMatch[1];
    }

    data.code = codeStr.trim();

    return data;
  } catch (e) {
    console.error("❌ 解析卡片失败:", e);
    return null;
  }
}
