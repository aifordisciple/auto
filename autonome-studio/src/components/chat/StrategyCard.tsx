"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Clock, CheckCircle, Loader2, XCircle, Edit3, Terminal, ChevronDown, ChevronUp, RefreshCw, Eye, ExternalLink, Copy, Check, FolderInput, Hammer, Sparkles } from "lucide-react";
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { useUIStore } from "@/store/useUIStore";
import { useChatStore } from "@/store/useChatStore";
import { BASE_URL } from "@/lib/api";
import { fetchEventSource } from '@microsoft/fetch-event-source';

// ✨ 从拆分模块导入类型和组件
import { LogModal } from './StrategyCard/LogModal';
import type { StrategyCardData, StrategyCardProps } from './StrategyCard/types';
import type { InteractivePlotData } from './InteractivePlotCard/types';
import { parseStrategyCard } from './StrategyCard/parseUtils';

// ✨ 保持向后兼容：重新导出类型和解析函数
export type { StrategyCardData, StrategyCardProps } from './StrategyCard/types';
export { parseStrategyCard } from './StrategyCard/parseUtils';

export function StrategyCard({ data, messageId, messageContent, onExecute, onCancel }: StrategyCardProps) {
  const { currentProjectId, currentSessionId } = useWorkspaceStore();
  const { autoExecuteStrategy, openSkillCenter } = useUIStore();
  const { updateMessage } = useChatStore();

  // ✨ 调试日志：检查 task_mode 和 visualization_config
  useEffect(() => {
    console.log('[StrategyCard] data:', {
      tool_id: data.tool_id,
      task_mode: data.task_mode,
      has_visualization_config: !!data.visualization_config,
      visualization_config: data.visualization_config,
    });
  }, [data]);

  // ✨ 使用 ref 存储 data，确保在 WebSocket 回调中获取最新值
  const dataRef = useRef(data);
  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  // ✨ 防止重复追加图表消息的标志
  const hasAppendedVisualization = useRef(false);

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

  // ✨ 任务输出目录名称（用户可自定义）
  const generateDefaultTaskName = () => {
    const timestamp = Date.now().toString(36).slice(-4); // 使用时间戳后4位
    const random = Math.random().toString(36).slice(-4); // 随机4位
    return `task_${timestamp}${random}`;
  };
  const [taskName, setTaskName] = useState<string>(generateDefaultTaskName());

  // ✨ 保存实际使用的任务名称（用于跳转）
  const [executedTaskName, setExecutedTaskName] = useState<string | null>(null);
  const executedTaskNameRef = useRef<string | null>(null); // ✨ 用于 WebSocket 回调中获取最新值

  // ✨ 同步 executedTaskName 到 ref
  useEffect(() => {
    executedTaskNameRef.current = executedTaskName;
  }, [executedTaskName]);

  // ✨ 追加交互式图表消息的函数
  const appendVisualizationMessage = (
    visualizationConfig: NonNullable<StrategyCardData['visualization_config']>,
    taskNameUsed: string | null
  ) => {
    // ✨ 防止重复追加
    if (hasAppendedVisualization.current) {
      console.log('[StrategyCard] 已追加过图表消息，跳过');
      return;
    }
    hasAppendedVisualization.current = true;

    const { addMessage } = useChatStore.getState();

    // 构建 data_source 完整路径
    const dataSource = taskNameUsed
      ? `results/${taskNameUsed}/${visualizationConfig.data_source}`
      : visualizationConfig.data_source;

    // 构建 InteractivePlotData
    const plotData: InteractivePlotData = {
      ...visualizationConfig,
      data_source: dataSource,
    };

    // 构建消息内容
    const messageContent = `数据处理已完成！生成交互式图表：\n\n\`\`\`json_interactive_plot\n${JSON.stringify(plotData, null, 2)}\n\`\`\``;

    // 追加消息
    addMessage('assistant', messageContent);
    console.log('[StrategyCard] 已追加交互式图表消息');
  };

  // 判断是否为 SKILL 类型（非 execute-python/execute-r）
  const isSkillType = data.tool_id !== 'execute-python' && data.tool_id !== 'execute-r';
  const hasCode = !isSkillType && (data.code || editableCode);

  // ✨ 将编辑后的代码持久化到消息内容
  // 当用户编辑代码后，更新数据库中的消息，以便刷新页面后仍能保持修改
  const persistCodeChange = async (newCode: string) => {
    if (!messageId || !messageContent) return;

    // 构建新的消息内容：替换代码块
    let updatedContent = messageContent;

    // 匹配并替换 Python 代码块
    const pyMatch = messageContent.match(/```(?:python|Python)\s*\n[\s\S]*?```/);
    if (pyMatch) {
      updatedContent = messageContent.replace(
        /```(?:python|Python)\s*\n[\s\S]*?```/,
        `\`\`\`python\n${newCode}\n\`\`\``
      );
    }

    // 匹配并替换 R 代码块
    const rMatch = messageContent.match(/```(?:r|R)\s*\n[\s\S]*?```/);
    if (rMatch) {
      updatedContent = messageContent.replace(
        /```(?:r|R)\s*\n[\s\S]*?```/,
        `\`\`\`r\n${newCode}\n\`\`\``
      );
    }

    // 更新本地 store
    updateMessage(messageId, updatedContent);

    // 调用后端 API 持久化
    try {
      const token = localStorage.getItem('autonome_access_token');
      await fetch(`${BASE_URL}/api/chat/messages/${messageId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ content: updatedContent })
      });
    } catch (error) {
      console.error('持久化代码失败:', error);
    }
  };

  // ✨ 重置状态，允许用户重新执行分析
  const handleRerun = () => {
    setTaskId(null);
    setTaskStatus(null);
    setProgress(null);
    setError(null);
    setLogs([]);
    setRetryAttempt(null);
    setFixedCode(null);
    setExecutedTaskName(null);
    setIsExecuting(false);
  };

  // ✨ 固化为 SKILL：通过 CustomEvent 发送草稿数据到技能工厂
  const handleTransformToSkill = () => {
    const draft = {
      name: data.title || '未命名技能',
      description: data.description || '',
      script_code: editableCode || data.code || '',
      parameters_schema: data.parameters || {},
      executor_type: data.tool_id === 'execute-r' ? 'R_env' : 'Python_env'
    };

    // 发送自定义事件，让 SkillCenter 接收草稿数据
    window.dispatchEvent(new CustomEvent('transform-to-skill', { detail: draft }));
    openSkillCenter();
  };

  // ✨ 从消息内容中提取已存储的 taskId
  const getStoredTaskId = (): string | null => {
    if (!messageContent) return null;
    const match = messageContent.match(/<!-- TASK_ID: ([a-f0-9-]+) -->/);
    return match ? match[1] : null;
  };

  // ✨ 从消息内容中提取已存储的任务名称
  const getStoredTaskName = (): string | null => {
    if (!messageContent) return null;
    const match = messageContent.match(/<!-- TASK_NAME: ([^\s]+) -->/);
    return match ? match[1] : null;
  };

  // ✨ 组件挂载时恢复任务状态
  useEffect(() => {
    const storedTaskId = getStoredTaskId();
    const storedTaskName = getStoredTaskName();

    if (storedTaskId && !taskId) {
      setTaskId(storedTaskId);
      // ✨ 恢复任务名称
      if (storedTaskName) {
        setExecutedTaskName(storedTaskName);
        setTaskName(storedTaskName);  // 同步更新输入框显示
      }

      // 查询任务状态
      const fetchTaskStatus = async () => {
        try {
          const response = await fetch(`${BASE_URL}/api/tasks/${storedTaskId}/status`);
          const result = await response.json();
          if (result.status) {
            setTaskStatus(result.status);
            setProgress(result.progress || null);

            // ✨ 恢复重试状态
            if (result.attempt && result.attempt > 1) {
              setRetryAttempt(result.attempt);
              // 只有在有重试时才设置 fixedCode
              if (result.final_code && result.status === 'SUCCESS') {
                setEditableCode(result.final_code);
                setFixedCode(result.final_code);
              }
            }

            // 如果任务还在执行中，连接 WebSocket
            if (result.status === 'PENDING' || result.status === 'STARTED' || result.status === 'RETRY') {
              setIsExecuting(true);
              connectWebSocket(storedTaskId);
            }
            // ✨ 如果任务已完成但前端没收到通知，触发刷新
            if (result.status === 'SUCCESS' || result.status === 'FAILURE') {
              // ✨ 交互式可视化模式：追加图表消息，不触发 refresh-chat
              if (dataRef.current.task_mode === 'interactive_visualization' && dataRef.current.visualization_config) {
                console.log('[StrategyCard:init] 检测到交互式可视化模式，追加图表消息');
                appendVisualizationMessage(dataRef.current.visualization_config, executedTaskNameRef.current);
              } else {
                // 非交互式模式：触发刷新
                setTimeout(() => {
                  window.dispatchEvent(new CustomEvent('refresh-chat'));
                }, 500);
              }
            }
          }
        } catch (e) {
          console.error('Failed to fetch task status:', e);
        }
      };
      fetchTaskStatus();
    }
  }, []);

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
    // ✨ 使用实际的任务名称跳转，而不是 Celery task ID
    const targetName = executedTaskName || id;
    // 发送自定义事件，让 ChatStage 滚动到包含该任务结果的消息
    window.dispatchEvent(new CustomEvent('scroll-to-task-result', {
      detail: { taskName: targetName, taskId: id }
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

    // ✨ 添加 WebSocket 超时检测：如果 30 秒内没有收到消息，回退到轮询
    // 从 5 秒延长到 30 秒，减少网络延迟导致的竞态条件
    const wsTimeout = setTimeout(() => {
      console.log('WebSocket timeout, falling back to polling...');
      if (ws.readyState !== WebSocket.CLOSED) {
        ws.close();
      }
      // 回退到轮询状态
      pollTaskStatus(id);
    }, 30000);

    ws.onopen = () => {
      console.log('WebSocket connected for task:', id);
      // 同时连接日志流
      connectLogStream(id);
    };

    ws.onmessage = (event) => {
      // ✨ 收到消息，清除超时检测
      clearTimeout(wsTimeout);

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

          // ✨ 如果收到最终执行代码且有重试，更新代码显示
          if (message.final_code && message.status === 'SUCCESS' && retryAttempt && retryAttempt > 1) {
            setEditableCode(message.final_code);
            setFixedCode(message.final_code);
          }

          if (message.status === 'SUCCESS' || message.status === 'FAILURE') {
            setIsExecuting(false);
            if (message.status === 'SUCCESS') {
              // ✨ 如果是交互式可视化模式，自动追加图表消息（不触发 refresh-chat）
              if (dataRef.current.task_mode === 'interactive_visualization' && dataRef.current.visualization_config) {
                console.log('[StrategyCard] 检测到交互式可视化模式，追加图表消息');
                console.log('[StrategyCard] visualization_config:', dataRef.current.visualization_config);
                console.log('[StrategyCard] taskNameUsed:', executedTaskNameRef.current);
                // 追加图表消息
                appendVisualizationMessage(dataRef.current.visualization_config, executedTaskNameRef.current);
                // ✨ 交互式模式下不触发 refresh-chat，避免覆盖追加的消息
              } else {
                // 非交互式模式：后端已将正确的消息存入数据库，触发刷新获取
                setTimeout(() => {
                  window.dispatchEvent(new CustomEvent('refresh-chat'));
                }, 500);
              }
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
      // ✨ WebSocket 出错，清除超时并回退到轮询
      clearTimeout(wsTimeout);
      pollTaskStatus(id);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected for task:', id);
      clearTimeout(wsTimeout);

      // ✨ 修复：WebSocket 关闭时检查任务状态
      // 直接查询后端状态，而不是依赖闭包中的 taskStatus（可能不是最新值）
      fetch(`${BASE_URL}/api/tasks/${id}/status`)
        .then(res => res.json())
        .then(data => {
          console.log('Task status on ws close:', data.status);
          if (data.status !== 'SUCCESS' && data.status !== 'FAILURE') {
            // 任务还没完成，回退到轮询
            console.log('Task not completed, falling back to polling...');
            pollTaskStatus(id);
          } else {
            // 任务已完成，更新状态
            setTaskStatus(data.status);
            setIsExecuting(false);

            // ✨ 交互式可视化模式：追加图表消息，不触发 refresh-chat
            if (data.status === 'SUCCESS' &&
                dataRef.current.task_mode === 'interactive_visualization' &&
                dataRef.current.visualization_config) {
              console.log('[StrategyCard:ws.onclose] 检测到交互式可视化模式，追加图表消息');
              appendVisualizationMessage(dataRef.current.visualization_config, executedTaskNameRef.current);
            } else if (data.status === 'SUCCESS') {
              // 非交互式模式：触发刷新
              setTimeout(() => {
                window.dispatchEvent(new CustomEvent('refresh-chat'));
              }, 500);
            }
          }
        })
        .catch(err => {
          console.error('Failed to check task status on ws close:', err);
          // 出错时回退到轮询
          pollTaskStatus(id);
        });
    };

    wsRef.current = ws;
  };

  // ✨ 新增：轮询任务状态（作为 WebSocket 的回退方案）
  const pollTaskStatus = async (id: string) => {
    console.log('Polling task status for:', id);
    let attempts = 0;
    const maxAttempts = 30; // 最多轮询 30 次（60秒）

    const poll = async () => {
      try {
        const response = await fetch(`${BASE_URL}/api/tasks/${id}/status`);
        const data = await response.json();

        console.log('Task status poll result:', data.status);
        setTaskStatus(data.status);
        setProgress(data.progress);

        if (data.progress_status) {
          setProgressStatus(data.progress_status);
        }
        if (data.attempt) {
          setRetryAttempt(data.attempt);
        }

        if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
          setIsExecuting(false);
          if (data.status === 'SUCCESS') {
            // ✨ 交互式可视化模式：追加图表消息，不触发 refresh-chat
            if (dataRef.current.task_mode === 'interactive_visualization' && dataRef.current.visualization_config) {
              console.log('[StrategyCard:poll] 检测到交互式可视化模式，追加图表消息');
              appendVisualizationMessage(dataRef.current.visualization_config, executedTaskNameRef.current);
            } else {
              // 非交互式模式：触发刷新
              setTimeout(() => {
                window.dispatchEvent(new CustomEvent('refresh-chat'));
              }, 500);
            }
          }
          return; // 停止轮询
        }

        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 2000); // 2秒后再轮询
        } else {
          // ✨ 修复：超时后不停止，改为慢速轮询（每 10 秒一次）
          // 确保长时间运行的任务最终能正确更新状态
          console.log('Max fast polling attempts reached, switching to slow polling (10s interval)...');
          setTimeout(poll, 10000);  // 继续轮询，直到任务完成
        }
      } catch (e) {
        console.error('Failed to poll task status:', e);
        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 2000);
        }
      }
    };

    poll();
  };

  const handleExecute = async () => {
    if (!data.tool_id) {
      setError("No tool selected");
      return;
    }

    setIsExecuting(true);
    setError(null);
    hasAppendedVisualization.current = false; // ✨ 重置追加标志

    const safeSessionId = currentSessionId || 1;

    // ✨ 清理任务名称：移除非法字符，确保是有效的目录名
    const sanitizedTaskName = taskName.trim().replace(/[^\w\-_]/g, '_') || generateDefaultTaskName();

    try {
      const token = localStorage.getItem('autonome_access_token');

      let payload: Record<string, unknown>;

      // Support both execute-python and execute-r
      // ✨ 使用编辑后的代码 (editableCode)，如果没有编辑则使用原始代码
      const codeToExecute = editableCode || data.code || '';
      if ((data.tool_id === 'execute-python' || data.tool_id === 'execute-r') && codeToExecute) {
        // ✨ 修复：Live_Coding 模式也需要传递 parameters，用于 argparse 参数注入
        // 过滤掉系统保留参数，只保留用户参数
        const userParams = { ...data.parameters };
        delete userParams.task_name;
        delete userParams.session_id;
        delete userParams.project_id;
        delete userParams.code;

        payload = {
          tool_id: data.tool_id,
          parameters: {
            code: codeToExecute,  // ✨ 使用可编辑的代码
            session_id: safeSessionId,
            project_id: currentProjectId,
            task_name: sanitizedTaskName,  // ✨ 用户自定义的任务目录名
            task_summary: data.task_summary,  // ✨ 新增：AI 生成的任务概述
            // ✨ 新增：传递用户参数，用于 argparse 参数注入
            ...(Object.keys(userParams).length > 0 ? { user_params: userParams } : {})
          },
          project_id: currentProjectId
        };
      } else {
        // ✨ SKILL 类型：使用用户编辑后的参数
        payload = {
          tool_id: data.tool_id,
          parameters: {
            ...editableParams,  // 使用 editableParams 替代 data.parameters
            task_name: sanitizedTaskName,  // ✨ 用户自定义的任务目录名
            session_id: safeSessionId,  // ✨ 修复：传递 session_id 用于消息发送
            task_summary: data.task_summary  // ✨ 新增：AI 生成的任务概述
          },
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
        setExecutedTaskName(sanitizedTaskName);  // ✨ 保存实际使用的任务名称
        onExecute?.(result.task_id);

        // ✨ 修复：立即更新策略卡片消息，追加 TASK_ID 和 TASK_NAME 标记，确保刷新页面后状态可恢复
        // 原因：策略卡片消息和任务结果消息是两条独立的消息，策略卡片消息本身不包含 TASK_ID
        // 解决：在用户点击执行获取 task_id 后，立即更新策略卡片消息内容
        if (messageId && messageContent) {
          // 检查是否已包含 TASK_ID 标记，避免重复追加
          if (!messageContent.includes('<!-- TASK_ID:')) {
            // ✨ 同时保存 TASK_ID 和 TASK_NAME，确保刷新后可以恢复完整状态
            const updatedContent = messageContent +
              `\n<!-- TASK_ID: ${result.task_id} -->` +
              `\n<!-- TASK_NAME: ${sanitizedTaskName} -->`;
            // 更新本地状态
            updateMessage(messageId, updatedContent);
            // 异步调用后端 API 持久化更新（不阻塞执行流程）
            fetch(`${BASE_URL}/api/chat/messages/${messageId}`, {
              method: 'PATCH',
              headers: {
                'Content-Type': 'application/json',
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
              },
              body: JSON.stringify({ content: updatedContent })
            }).catch(err => console.error('更新消息失败:', err));
          }
        }

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
      className="bg-gradient-to-br from-gray-50 to-gray-100 dark:from-neutral-900 dark:to-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-xl p-5 shadow-sm dark:shadow-xl my-4 w-full"
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
      {/* ✨ 增加 whitespace-pre-wrap 和 leading-relaxed 让换行生效且排版更好 */}
      <p className="text-sm text-gray-700 dark:text-neutral-300 mb-4 whitespace-pre-wrap leading-relaxed">
        {data.description}
      </p>

      {/* Steps Preview */}
      {data.steps && data.steps.length > 0 && (
        <div className="bg-gray-100 dark:bg-neutral-950/50 rounded-lg p-3 mb-4">
          <p className="text-xs text-gray-500 dark:text-neutral-500 mb-2">执行步骤</p>
          <ul className="space-y-1">
            {data.steps.map((step, i) => (
              <li key={i} className="text-xs text-gray-600 dark:text-neutral-400 flex items-start gap-2">
                <span className="text-indigo-500 mt-0.5">•</span>
                {/* ✨ 把 step 包裹起来并加上 whitespace-pre-wrap */}
                <span className="whitespace-pre-wrap leading-relaxed">{step}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ✨ 代码缺失警告 - Live_Coding 模式但未提取到代码 */}
      {!isSkillType && !hasCode && (
        <div className="mb-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-500/30 rounded-lg">
          <div className="flex items-start gap-2">
            <span className="text-yellow-500 text-sm">⚠️</span>
            <div>
              <p className="text-sm font-medium text-yellow-700 dark:text-yellow-300">
                未检测到可执行代码
              </p>
              <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                可能是 AI 输出格式不规范导致代码提取失败。请尝试重新发送消息。
              </p>
            </div>
          </div>
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
                  if (isEditingCode) {
                    // ✨ 完成编辑时，持久化代码修改
                    if (editableCode !== data.code) {
                      persistCodeChange(editableCode);
                    }
                  } else {
                    // 进入编辑模式时，聚焦到编辑器
                    setTimeout(() => codeEditorRef.current?.focus(), 100);
                  }
                  setIsEditingCode(!isEditingCode);
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

          {/* 代码内容区域 - ✨ 带语法高亮 */}
          <div className="relative bg-gray-900 dark:bg-neutral-950">
            {isEditingCode ? (
              // 编辑模式 - textarea
              <textarea
                ref={codeEditorRef}
                value={editableCode}
                onChange={(e) => setEditableCode(e.target.value)}
                onKeyDown={(e) => {
                  // ✨ Ctrl+Enter 或 Cmd+Enter 完成编辑并持久化
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    if (editableCode !== data.code) {
                      persistCodeChange(editableCode);
                    }
                    setIsEditingCode(false);
                  }
                }}
                className="w-full min-h-[200px] max-h-[400px] p-3 bg-transparent text-gray-300 font-mono text-xs leading-relaxed focus:outline-none resize-y"
                placeholder="在此编辑代码... (Ctrl+Enter 保存)"
                spellCheck={false}
              />
            ) : (
              // 只读模式 - ✨ 使用 SyntaxHighlighter 实现代码高亮
              <div className="max-h-[300px] overflow-auto">
                <SyntaxHighlighter
                  language={getCodeLanguage()}
                  style={oneDark}
                  customStyle={{
                    margin: 0,
                    padding: '12px',
                    fontSize: '11px',
                    lineHeight: '1.5',
                    background: 'transparent',
                    maxHeight: '300px',
                  }}
                  showLineNumbers={true}
                  lineNumberStyle={{
                    minWidth: '2.5em',
                    paddingRight: '1em',
                    color: '#6b7280',
                    textAlign: 'right',
                  }}
                  wrapLines={true}
                  wrapLongLines={true}
                >
                  {editableCode || data.code || ''}
                </SyntaxHighlighter>
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
                const isAIInferred = data.ai_inferred_params?.includes(key);

                return (
                  <div key={key} className="flex items-center gap-3">
                    <label className={`text-xs min-w-[120px] flex items-center gap-1 ${isAIInferred ? 'text-blue-500 dark:text-blue-400' : 'text-gray-600 dark:text-neutral-400'}`}>
                      {isAIInferred && <Sparkles className="w-3 h-3" />}
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
                        className={`flex-1 px-2 py-1 text-xs border rounded focus:outline-none focus:ring-1 focus:ring-blue-500 ${
                          isAIInferred
                            ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700 text-gray-700 dark:text-neutral-300'
                            : 'bg-gray-200 dark:bg-neutral-800 border-gray-300 dark:border-neutral-600'
                        }`}
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
                        className={`flex-1 px-2 py-1 text-xs border rounded focus:outline-none focus:ring-1 focus:ring-blue-500 ${
                          isAIInferred
                            ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700 text-gray-700 dark:text-neutral-300'
                            : 'bg-gray-200 dark:bg-neutral-800 border-gray-300 dark:border-neutral-600 text-gray-700 dark:text-neutral-300'
                        }`}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            // 原有的参数展示
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.parameters).map(([key, value]) => {
                const isAIInferred = data.ai_inferred_params?.includes(key);
                return (
                  <span
                    key={key}
                    className={`text-xs px-2 py-1 rounded ${
                      isAIInferred
                        ? 'bg-blue-100 dark:bg-blue-900/30 border border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300'
                        : 'bg-gray-200 dark:bg-neutral-800 text-gray-700 dark:text-neutral-300'
                    }`}
                  >
                    {isAIInferred && <Sparkles className="inline w-3 h-3 mr-1" />}
                    <span className={isAIInferred ? 'text-blue-500 dark:text-blue-400' : 'text-gray-500 dark:text-neutral-500'}>{key}:</span> {String(value)}
                  </span>
                );
              })}
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
          {/* ✨ 增加 whitespace-pre-wrap */}
          <p className="text-sm text-red-400 whitespace-pre-wrap">{error}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 flex-wrap">
        {!taskId ? (
          <>
            {/* ✨ 任务名称输入框 */}
            <div className="flex items-center gap-2">
              <FolderInput className="w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={taskName}
                onChange={(e) => setTaskName(e.target.value)}
                placeholder="任务名称"
                className="w-40 px-3 py-2 text-sm bg-gray-100 dark:bg-neutral-800 border border-gray-300 dark:border-neutral-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={isExecuting}
              />
            </div>
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

            {/* Task ID 组：任务名称 + 跳转按钮 + 日志眼睛 */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => scrollToResultMessage(taskId)}
                className="group flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-neutral-800 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                title="点击跳转到分析结果"
              >
                <span className="text-xs text-gray-500 dark:text-neutral-500">Task</span>
                <code className="text-xs text-blue-600 dark:text-blue-400 font-mono font-medium">
                  {executedTaskName || taskId.slice(0, 8)}
                </code>
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

            {/* ✨ 操作按钮组 */}
            {/* 再次分析按钮 - 成功或失败后都可以使用 */}
            {taskId && (taskStatus === 'SUCCESS' || taskStatus === 'FAILURE') && (
              <button
                onClick={handleRerun}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-100 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-500/30 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
                title="重置状态，允许修改参数或代码后重新执行"
              >
                <RefreshCw className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                <span className="text-sm font-medium text-blue-700 dark:text-blue-300">再次分析</span>
              </button>
            )}

            {/* 固化为SKILL按钮 - 仅成功且非SKILL类型时显示 */}
            {taskId && taskStatus === 'SUCCESS' && !isSkillType && (
              <button
                onClick={handleTransformToSkill}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-100 dark:bg-orange-900/30 border border-orange-200 dark:border-orange-500/30 rounded-lg hover:bg-orange-200 dark:hover:bg-orange-900/50 transition-colors"
                title="将此代码固化为可复用的 SKILL"
              >
                <Hammer className="w-4 h-4 text-orange-600 dark:text-orange-400" />
                <span className="text-sm font-medium text-orange-700 dark:text-orange-300">固化为SKILL</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* ✨ 修复后的代码预览 - 只在有重试时显示 */}
      {taskId && fixedCode && retryAttempt && retryAttempt > 1 && (
        <div className="mt-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-500/30 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <RefreshCw className="w-4 h-4 text-amber-500" />
            <span className="text-xs font-medium text-amber-700 dark:text-amber-300">AI 修复后的代码 (第 {retryAttempt} 次尝试)</span>
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
