/**
 * useChatStream Hook - 聊天流式消息处理
 *
 * 功能：
 * 1. 管理聊天消息的发送和流式接收
 * 2. 处理 SSE (Server-Sent Events) 流式输出
 * 3. 支持中断流式输出
 * 4. ✨ 支持消息队列：AI 忙碌时消息入队，通过队列 SSE 接收回复
 *
 * 从 ChatStage.tsx 提取，减少主组件复杂度
 */
import React, { useCallback, useRef } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useChatStore, ChatState, ChatQueueItem, QueueItemStatus } from '@/store/useChatStore';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { useAuthStore } from '@/store/useAuthStore';
import { BASE_URL, chatQueueApi } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

export interface ChatStreamConfig {
  /** 获取当前流式内容 */
  getCurrentContent: () => string;
  /** 追加流式内容到即时渲染 hook（保持 useImmediateStream refs 同步） */
  appendStream: (chunk: string) => void;
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
  /** 是否在底部的 ref（避免 SSE onmessage 闭包过期） */
  isAtBottomRef: React.RefObject<boolean>;
  /** 是否暂停自动滚动的 ref（避免 SSE onmessage 闭包过期） */
  isPausedRef: React.RefObject<boolean>;
}

// ==========================================
// Hook 实现
// ==========================================

export function useChatStream(config: ChatStreamConfig) {
  const {
    getCurrentContent,
    appendStream,
    resetStream,
    clearStreamingContent,
    setStreamingMessageId,
    commitStreamingContent,
    scrollToBottom,
    isAtBottomRef,
    isPausedRef,
  } = config;

  // ✨ 思考内容状态
  const thinkingContent = useChatStore((state: ChatState) => state.thinkingContent);
  const setThinkingContent = useChatStore((state: ChatState) => state.setThinkingContent);
  const isThinking = useChatStore((state: ChatState) => state.isThinking);
  const setIsThinking = useChatStore((state: ChatState) => state.setIsThinking);

  // Store 状态 - 使用精确订阅避免不必要的重渲染
  const addMessage = useChatStore((state: ChatState) => state.addMessage);
  const appendLastMessage = useChatStore((state: ChatState) => state.appendLastMessage);
  const setIsTyping = useChatStore((state: ChatState) => state.setIsTyping);
  const updateLastMessageId = useChatStore((state: ChatState) => state.updateLastMessageId);
  // ✨ 队列状态
  const addQueueItem = useChatStore((state: ChatState) => state.addQueueItem);
  const updateQueueItemStatus = useChatStore((state: ChatState) => state.updateQueueItemStatus);
  const removeQueueItem = useChatStore((state: ChatState) => state.removeQueueItem);
  const isQueueActive = useChatStore((state: ChatState) => state.isQueueActive);
  const setIsQueueActive = useChatStore((state: ChatState) => state.setIsQueueActive);
  const updateMessageQueueStatus = useChatStore((state: ChatState) => state.updateMessageQueueStatus);

  const currentProjectId = useWorkspaceStore(state => state.currentProjectId);
  const currentSessionId = useWorkspaceStore(state => state.currentSessionId);
  const setCurrentSessionId = useWorkspaceStore(state => state.setCurrentSessionId);
  const pendingChatAttachments = useWorkspaceStore(state => state.pendingChatAttachments);
  const clearPendingChatAttachments = useWorkspaceStore(state => state.clearPendingChatAttachments);
  const pendingChatSkill = useWorkspaceStore(state => state.pendingChatSkill);
  const clearPendingChatSkill = useWorkspaceStore(state => state.clearPendingChatSkill);

  const { updateCredits } = useAuthStore();

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
   *
   * ✨ 队列模式：如果 AI 正在回复（isStreamingRef.current === true），
   * 消息进入后端队列，通过队列 SSE 接收回复。
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

    // ✨ 队列模式：AI 正在回复时，消息入队
    if (isStreamingRef.current && currentSessionId) {
      try {
        const queueItem = await chatQueueApi.add({
          session_id: currentSessionId,
          project_id: currentProjectId,
          message: currentInput,
          attachments: messageAttachments,
        });
        // 前端立即显示用户消息 + "排队中" 标签
        addMessage('user', currentInput, messageAttachments, queueItem.id);
        addQueueItem(queueItem as ChatQueueItem);
        return;
      } catch (error: any) {
        console.error('[Chat] Queue add failed:', error);
        // 队列添加失败，回退到直接发送（中断当前流）
        // 不做任何事，让用户重试
        appendLastMessage(`\n\n**[队列错误]** ${error.message || '消息入队失败'}`);
        return;
      }
    }

    // ✨ 直接发送模式：AI 空闲时走现有逻辑
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

    // 任务模式已简化为 normal，不再发送 task_mode
    const taskModeToSend = null;

    // 重置余额不足标志
    isInsufficientCreditsRef.current = false;

    // 创建中断控制器
    abortControllerRef.current = new AbortController();

    try {
      const token = localStorage.getItem('autonome_access_token');

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
          } else if (event.event === 'thinking') {
            // ✨ 思考过程事件：累积到 thinkingContent，前端在可折叠思考框中展示
            const data = JSON.parse(event.data);
            setThinkingContent(thinkingContent + data.content);
            if (!isThinking) setIsThinking(true);
            if (isAtBottomRef.current && !isPausedRef.current) {
              requestAnimationFrame(() => scrollToBottom());
            }
          } else if (event.event === 'message') {
            const data = JSON.parse(event.data);
            // 通过 appendStream 写入 useImmediateStream，由其 flushRender 机制
            // 自动将完整累积内容传递给 Zustand store
            appendStream(data.content);
            // 使用 ref 读取最新值，避免闭包过期导致滚动失效
            if (isAtBottomRef.current && !isPausedRef.current) {
              requestAnimationFrame(() => scrollToBottom());
            }
          } else if (event.event === 'billing') {
            const data = JSON.parse(event.data);
            updateCredits(data.balance);
          } else if (event.event === 'ai_message_id') {
            const data = JSON.parse(event.data);
            updateLastMessageId(data.message_id);
          } else if (event.event === 'ai_message_content') {
            const data = JSON.parse(event.data);
            // ✨ 使用 ref 防止重复提交
            if (!hasCommittedRef.current && data.content) {
              commitStreamingContent(data.content);
              hasCommittedRef.current = true;
            }
            clearStreamingContent();
            isStreamingRef.current = false;
            setIsTyping(false);
            // ✨ 思考结束，清除思考状态
            setIsThinking(false);
            setThinkingContent('');
          } else if (event.event === 'done') {
            // 使用 ref 防止重复提交
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
            // ✨ 队列模式：done 后检查是否还有队列项需要处理
            // 如果有，启动队列 SSE 连接
            _checkAndStartQueueStream();
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
    addMessage,
    appendLastMessage,
    setIsTyping,
    updateLastMessageId,
    setCurrentSessionId,
    clearPendingChatAttachments,
    clearPendingChatSkill,
    updateCredits,
    appendStream,
    getCurrentContent,
    resetStream,
    clearStreamingContent,
    setStreamingMessageId,
    commitStreamingContent,
    scrollToBottom,
    isAtBottomRef,
    isPausedRef,
    addQueueItem,
    updateQueueItemStatus,
    removeQueueItem,
    isQueueActive,
    setIsQueueActive,
    updateMessageQueueStatus,
  ]);

  // ==========================================
  // ✨ 队列 SSE 流处理
  // ==========================================

  /**
   * 检查是否有队列项需要处理，如果有则启动队列 SSE 连接
   */
  const _checkAndStartQueueStream = useCallback(() => {
    const { queueItems, isQueueActive } = useChatStore.getState();
    if (!isQueueActive || queueItems.length === 0) return;

    // 启动队列 SSE 连接
    _startQueueStream();
  }, []);

  /**
   * 启动队列 SSE 连接，接收 Celery worker 处理队列项时的流式回复
   */
  const _startQueueStream = useCallback(async () => {
    const { queueItems } = useChatStore.getState();
    if (queueItems.length === 0) return;

    const sessionId = queueItems[0].session_id;
    const projectId = queueItems[0].project_id;
    const token = localStorage.getItem('autonome_access_token');

    // 初始化流式状态
    const newMessageId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setStreamingMessageId(newMessageId);
    clearStreamingContent();
    resetStream();
    addMessage('assistant', '');
    setIsTyping(true);
    isStreamingRef.current = true;
    hasCommittedRef.current = false;

    const queueAbortController = new AbortController();

    try {
      await fetchEventSource(`${BASE_URL}/api/chat/stream/queue`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          session_id: sessionId,
          project_id: projectId,
        }),
        signal: queueAbortController.signal,
        openWhenHidden: true,
        onopen: async (res) => {
          if (!res.ok) {
            throw new Error(`Queue stream error: ${res.status}`);
          }
        },
        onmessage(event) {
          if (event.event === 'queue_start') {
            // 标识开始处理哪个队列项
            const data = JSON.parse(event.data);
            updateQueueItemStatus(data.queue_item_id, 'processing' as QueueItemStatus);
          } else if (event.event === 'queue_progress') {
            // 队列进度通知（可用于 UI 显示）
            const data = JSON.parse(event.data);
          } else if (event.event === 'thinking') {
            // ✨ 思考过程事件：累积到 thinkingContent，前端在可折叠思考框中展示
            const data = JSON.parse(event.data);
            setThinkingContent(thinkingContent + data.content);
            if (!isThinking) setIsThinking(true);
            if (isAtBottomRef.current && !isPausedRef.current) {
              requestAnimationFrame(() => scrollToBottom());
            }
          } else if (event.event === 'message') {
            // 流式内容
            const data = JSON.parse(event.data);
            appendStream(data.content);
            if (isAtBottomRef.current && !isPausedRef.current) {
              requestAnimationFrame(() => scrollToBottom());
            }
          } else if (event.event === 'billing') {
            const data = JSON.parse(event.data);
            updateCredits(data.balance);
          } else if (event.event === 'ai_message_id') {
            const data = JSON.parse(event.data);
            updateLastMessageId(data.message_id);
          } else if (event.event === 'ai_message_content') {
            const data = JSON.parse(event.data);
            if (!hasCommittedRef.current && data.content) {
              commitStreamingContent(data.content);
              hasCommittedRef.current = true;
            }
            // ✨ 思考结束，清除思考状态
            setIsThinking(false);
            setThinkingContent('');
          } else if (event.event === 'queue_complete') {
            // 队列项处理完成
            const data = JSON.parse(event.data);
            removeQueueItem(data.queue_item_id);
            // 重置流式状态，准备下一个队列项
            hasCommittedRef.current = false;
          } else if (event.event === 'queue_error') {
            // 队列项处理失败
            const data = JSON.parse(event.data);
            updateQueueItemStatus(data.queue_item_id, 'failed' as QueueItemStatus, data.error);
            removeQueueItem(data.queue_item_id);
          } else if (event.event === 'queue_done') {
            // 全部队列项处理完毕
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
            setIsQueueActive(false);
          } else if (event.event === 'done') {
            // SSE 连接关闭
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
          }
        },
        onclose() {
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
          console.error('[Queue Stream] Error:', err);
          throw err;
        },
      });
    } catch (error) {
      isStreamingRef.current = false;
      setIsTyping(false);
      console.error('[Queue Stream] Failed:', error);
    }
  }, [
    addMessage,
    appendStream,
    clearStreamingContent,
    commitStreamingContent,
    getCurrentContent,
    isAtBottomRef,
    isPausedRef,
    removeQueueItem,
    resetStream,
    scrollToBottom,
    setIsQueueActive,
    setIsTyping,
    setStreamingMessageId,
    updateCredits,
    updateLastMessageId,
    updateQueueItemStatus,
    // ✨ 思考过程状态
    thinkingContent,
    setThinkingContent,
    isThinking,
    setIsThinking,
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