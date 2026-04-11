/**
 * useChatStream Hook - 聊天流式消息处理
 *
 * 功能：
 * 1. 管理聊天消息的发送和流式接收
 * 2. 处理 SSE (Server-Sent Events) 流式输出
 * 3. 支持中断流式输出
 * 4. 处理超级执行者 V2 事件
 *
 * 从 ChatStage.tsx 提取，减少主组件复杂度
 */
import { useCallback, useRef } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useChatStore, ChatState } from '@/store/useChatStore';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { useAuthStore } from '@/store/useAuthStore';
import { useUIStore } from '@/store/useUIStore';
import { BASE_URL } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

export interface ExecutionPlanData {
  plan_id: string;
  goal: string;
  steps: ExecutionStepData[];
  estimated_time?: number;
}

export interface ExecutionStepData {
  step_id: string;
  name: string;
  description?: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  execution_time?: number;
  output?: string;
  error?: string;
  retry_count?: number;
}

export interface ExecutionResultData {
  success: boolean;
  total_time: number;
  steps_completed: number;
  steps_failed: number;
  summary?: string;
}

export interface BlueprintState {
  blueprint_id: string;
  project_goal: string;
  total_tasks: number;
}

export interface ChatStreamConfig {
  /** 流式内容更新回调 */
  onContentUpdate: (content: string) => void;
  /** 获取当前流式内容 */
  getCurrentContent: () => string;
  /** 重置流式状态 */
  resetStream: () => void;
  /** 清除流式内容 */
  clearStreamingContent: () => void;
  /** 设置流式消息 ID */
  setStreamingMessageId: (id: string) => void;
  /** 提交流式内容 */
  commitStreamingContent: (content: string) => void;
  /** 滚动到底部 */
  scrollToBottom: () => void;
  /** 是否在底部 */
  isAtBottom: boolean;
  /** 是否暂停自动滚动 */
  isPaused: boolean;
}

// ==========================================
// Hook 实现
// ==========================================

export function useChatStream(config: ChatStreamConfig) {
  const {
    onContentUpdate,
    getCurrentContent,
    resetStream,
    clearStreamingContent,
    setStreamingMessageId,
    commitStreamingContent,
    scrollToBottom,
    isAtBottom,
    isPaused,
  } = config;

  // Store 状态 - 使用精确订阅避免不必要的重渲染
  const addMessage = useChatStore((state: ChatState) => state.addMessage);
  const appendLastMessage = useChatStore((state: ChatState) => state.appendLastMessage);
  const setIsTyping = useChatStore((state: ChatState) => state.setIsTyping);
  const updateLastMessageId = useChatStore((state: ChatState) => state.updateLastMessageId);

  const currentProjectId = useWorkspaceStore(state => state.currentProjectId);
  const currentSessionId = useWorkspaceStore(state => state.currentSessionId);
  const setCurrentSessionId = useWorkspaceStore(state => state.setCurrentSessionId);
  const pendingChatAttachments = useWorkspaceStore(state => state.pendingChatAttachments);
  const clearPendingChatAttachments = useWorkspaceStore(state => state.clearPendingChatAttachments);
  const pendingChatSkill = useWorkspaceStore(state => state.pendingChatSkill);
  const clearPendingChatSkill = useWorkspaceStore(state => state.clearPendingChatSkill);
  const setActiveTool = useWorkspaceStore(state => state.setActiveTool);
  const updateToolParam = useWorkspaceStore(state => state.updateToolParam);
  const setClaudeCodeSessionId = useWorkspaceStore(state => state.setClaudeCodeSessionId);

  const { updateCredits } = useAuthStore();
  const globalTaskMode = useUIStore(state => state.globalTaskMode);

  // Refs
  const abortControllerRef = useRef<AbortController | null>(null);
  const isStreamingRef = useRef(false);
  const isInsufficientCreditsRef = useRef(false);
  const hasCommittedRef = useRef(false);

  /**
   * 中断流式输出
   */
  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    const finalContent = getCurrentContent();
    if (finalContent) {
      commitStreamingContent(finalContent);
    }
    clearStreamingContent();
    isStreamingRef.current = false;
    setIsTyping(false);
  }, [getCurrentContent, commitStreamingContent, clearStreamingContent, setIsTyping]);

  /**
   * 发送聊天消息
   */
  const handleSend = useCallback(async (
    messageText: string,
    contextFiles?: string[],
    attachments?: any,
    pastedAttachments?: any[],
    cleanupPastedAttachments?: () => void
  ) => {
    // 安全检查：必须有有效的项目 ID
    if (!currentProjectId) {
      console.error('[Chat] Cannot send message: no project selected');
      addMessage('assistant', '⚠️ 请先选择项目后再发送消息。');
      return;
    }

    const currentInput = messageText;

    // 检查是否有正在上传的粘贴附件
    if (pastedAttachments?.some(att => att.isUploading)) {
      return;
    }

    // 允许空消息但有附件时发送
    if (!currentInput?.trim() && pendingChatAttachments.length === 0 && !pastedAttachments?.length) return;

    // 合并附件
    const pastedFilePaths = pastedAttachments
      ?.filter(att => att.type === 'file' && att.serverPath)
      .map(att => att.serverPath) || [];
    const filesToSend = [...(contextFiles || pendingChatAttachments), ...pastedFilePaths];

    // 收集粘贴的图片路径
    const imagePaths = pastedAttachments
      ?.filter(att => att.type === 'image' && att.serverPath)
      .map(att => att.serverPath) || [];

    // 构建附件信息
    const messageAttachments = {
      files: (contextFiles || pendingChatAttachments).length > 0 ? (contextFiles || pendingChatAttachments) : undefined,
      images: imagePaths.length > 0 ? imagePaths : undefined,
      pastedFiles: pastedFilePaths.length > 0 ? pastedFilePaths : undefined,
      skill: pendingChatSkill ? { skill_id: pendingChatSkill.skill_id, name: pendingChatSkill.name } : undefined,
    };

    // 添加用户消息
    addMessage('user', currentInput, messageAttachments);

    // 初始化流式状态
    const newMessageId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setStreamingMessageId(newMessageId);
    clearStreamingContent();
    resetStream();

    addMessage('assistant', '');
    setIsTyping(true);
    isStreamingRef.current = true;
    hasCommittedRef.current = false;

    // 发送后清除附件
    if (pendingChatAttachments.length > 0) {
      clearPendingChatAttachments();
    }

    // 清除粘贴附件
    if (cleanupPastedAttachments) {
      cleanupPastedAttachments();
    }

    // 清除技能附件
    const skillIdToSend = pendingChatSkill?.skill_id || null;
    if (pendingChatSkill) {
      clearPendingChatSkill();
    }

    // 使用全局任务模式
    const taskModeToSend = globalTaskMode === 'normal' ? null : globalTaskMode;

    // 重置余额不足标志
    isInsufficientCreditsRef.current = false;

    // 创建中断控制器
    abortControllerRef.current = new AbortController();

    try {
      const token = localStorage.getItem('autonome_access_token');
      console.log('[Chat] Sending message:', { project_id: currentProjectId, session_id: currentSessionId });

      await fetchEventSource(`${BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          project_id: currentProjectId,
          message: currentInput,
          context_files: filesToSend,
          session_id: currentSessionId,
          skill_id: skillIdToSend,
          images: imagePaths,
          task_mode: taskModeToSend
        }),
        signal: abortControllerRef.current.signal,
        openWhenHidden: true,
        onopen: async (res) => {
          if (!res.ok) {
            if (res.status === 402) {
              if (!isInsufficientCreditsRef.current) {
                isInsufficientCreditsRef.current = true;
                appendLastMessage("\n\n**[余额不足]** 您的算力余额不足，请充值后继续使用。");
              }
              isStreamingRef.current = false;
              setIsTyping(false);
              throw new Error('Insufficient credits');
            }
            if (res.status === 422) {
              try {
                const errorData = await res.json();
                console.error('[Chat] Validation error:', errorData);
                const detail = errorData?.detail || '请求参数验证失败';
                appendLastMessage(`\n\n**[参数错误]** ${JSON.stringify(detail)}`);
              } catch {
                appendLastMessage("\n\n**[参数错误]** 请求参数验证失败，请检查输入。");
              }
              isStreamingRef.current = false;
              setIsTyping(false);
              throw new Error('Validation error');
            }
            throw new Error(`Server responded with ${res.status}`);
          }
        },
        onmessage(event) {
          if (event.event === 'session_info') {
            const data = JSON.parse(event.data);
            if (data.is_new) {
              setCurrentSessionId(data.session_id);
              window.dispatchEvent(new Event('refresh-sessions'));
              fetch(`${BASE_URL}/api/chat/sessions/${data.session_id}/auto-name`, {
                method: "POST",
                headers: { 'Authorization': `Bearer ${token}` }
              }).catch(e => console.error("自动命名失败", e));
            }
          } else if (event.event === 'intent_detected') {
            // ✨ 意图检测结果事件
            const data = JSON.parse(event.data);
            console.log('[Chat] 意图检测:', data.intent_type, data.reason);
            // 发送自定义事件供其他组件监听
            window.dispatchEvent(new CustomEvent('intent-detected', { detail: data }));
          } else if (event.event === 'recommendation_card') {
            // ✨ 推荐选择卡片事件
            const data = JSON.parse(event.data);
            console.log('[Chat] 推荐卡片:', data.options?.length, '个选项');
            // 发送自定义事件供其他组件监听
            window.dispatchEvent(new CustomEvent('recommendation-card', { detail: data }));
          } else if (event.event === 'message') {
            const data = JSON.parse(event.data);
            onContentUpdate(data.content);
            // 只有在底部附近且用户没有暂停时才自动滚动
            if (isAtBottom && !isPaused) {
              requestAnimationFrame(() => scrollToBottom());
            }
          } else if (event.event === 'tool') {
            const data = JSON.parse(event.data);
            setActiveTool(data.tool);
            if (data.tool.id === 'rnaseq-qc') {
              setTimeout(() => updateToolParam('qual_threshold', 30), 300);
            }
          } else if (event.event === 'billing') {
            const data = JSON.parse(event.data);
            updateCredits(data.balance);
          } else if (event.event === 'ai_message_id') {
            const data = JSON.parse(event.data);
            console.log('[Chat] Received AI message ID:', data.message_id);
            updateLastMessageId(data.message_id);
          } else if (event.event === 'ai_message_content') {
            const data = JSON.parse(event.data);
            console.log('[Chat] Received fixed AI message content, length:', data.content?.length);
            // ✨ 使用 ref 防止重复提交
            if (!hasCommittedRef.current && data.content) {
              commitStreamingContent(data.content);
              hasCommittedRef.current = true;
            }
            clearStreamingContent();
            isStreamingRef.current = false;
            setIsTyping(false);
          } else if (event.event === 'done') {
            // ✨ 使用 ref 防止重复提交
            if (!hasCommittedRef.current) {
              const finalContent = getCurrentContent();
              if (finalContent) {
                commitStreamingContent(finalContent);
                hasCommittedRef.current = true;
              }
            }
            clearStreamingContent();
            isStreamingRef.current = false;
            setIsTyping(false);
            // 保存 Claude Code 会话 ID
            try {
              const data = JSON.parse(event.data);
              if (data.session_id) {
                console.log('[Chat] Claude Code session ID:', data.session_id);
                setClaudeCodeSessionId(data.session_id);
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        },
        onclose() {
          // ✨ onclose 只做最小化清理，使用 ref 防止重复提交
          if (!hasCommittedRef.current && isStreamingRef.current) {
            const finalContent = getCurrentContent();
            if (finalContent) {
              commitStreamingContent(finalContent);
              hasCommittedRef.current = true;
            }
          }
          clearStreamingContent();
          isStreamingRef.current = false;
          setIsTyping(false);
        },
        onerror(err) {
          hasCommittedRef.current = false;
          isStreamingRef.current = false;
          setIsTyping(false);
          if (isInsufficientCreditsRef.current) {
            throw new Error('Insufficient credits - stop retry');
          }
          console.error("Connection Error:", err);
          appendLastMessage("\n\n**[系统错误]** 连接后端大脑失败，请检查 FastAPI 服务是否启动。");
          throw err;
        }
      });
    } catch (error) {
      isStreamingRef.current = false;
      setIsTyping(false);
      if (isInsufficientCreditsRef.current) {
        return;
      }
      console.error('[Chat] Send error:', error);
      appendLastMessage("\n\n**[系统错误]** 发送消息失败，请检查控制台。");
    }
  }, [
    currentProjectId,
    currentSessionId,
    pendingChatAttachments,
    pendingChatSkill,
    globalTaskMode,
    addMessage,
    appendLastMessage,
    setIsTyping,
    updateLastMessageId,
    setCurrentSessionId,
    clearPendingChatAttachments,
    clearPendingChatSkill,
    setActiveTool,
    updateToolParam,
    setClaudeCodeSessionId,
    updateCredits,
    onContentUpdate,
    getCurrentContent,
    resetStream,
    clearStreamingContent,
    setStreamingMessageId,
    commitStreamingContent,
    scrollToBottom,
    isAtBottom,
    isPaused,
  ]);

  return {
    handleSend,
    handleStop,
    abortControllerRef,
    isStreamingRef,
    isInsufficientCreditsRef,
  };
}

export default useChatStream;