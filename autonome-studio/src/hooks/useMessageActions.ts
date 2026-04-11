/**
 * useMessageActions Hook - 消息操作管理
 *
 * 功能：
 * 1. 重试 AI 回复
 * 2. 编辑并重新发送用户消息
 * 3. 深度解读分析结果
 *
 * 从 ChatStage.tsx 提取，减少主组件复杂度
 */
import { useCallback, useRef } from 'react';
import { useChatStore, ChatState, Message } from '@/store/useChatStore';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { useAuthStore } from '@/store/useAuthStore';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { BASE_URL } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

export interface MessageActionsConfig {
  /** 获取当前流式内容的函数 */
  getCurrentContent: () => string;
  /** 重置流式状态 */
  resetStream: () => void;
  /** 清除流式内容 */
  clearStreamingContent: () => void;
  /** 设置流式消息 ID */
  setStreamingMessageId: (id: string) => void;
  /** 提交流式内容 */
  commitStreamingContent: (content: string) => void;
  /** 追加流式内容 */
  appendStream: (chunk: string) => void;
  /** 中断控制器引用 */
  abortControllerRef: React.MutableRefObject<AbortController | null>;
  /** 流式状态引用 */
  isStreamingRef: React.MutableRefObject<boolean>;
  /** 余额不足引用 */
  isInsufficientCreditsRef: React.MutableRefObject<boolean>;
}

// ==========================================
// Hook 实现
// ==========================================

export function useMessageActions(config: MessageActionsConfig) {
  const {
    getCurrentContent,
    resetStream,
    clearStreamingContent,
    setStreamingMessageId,
    commitStreamingContent,
    appendStream,
    abortControllerRef,
    isStreamingRef,
    isInsufficientCreditsRef,
  } = config;

  // Store 状态
  const messages = useChatStore((state: ChatState) => state.messages);
  const addMessage = useChatStore((state: ChatState) => state.addMessage);
  const appendLastMessage = useChatStore((state: ChatState) => state.appendLastMessage);
  const deleteMessagesAfter = useChatStore((state: ChatState) => state.deleteMessagesAfter);
  const setIsTyping = useChatStore((state: ChatState) => state.setIsTyping);
  const updateLastMessageId = useChatStore((state: ChatState) => state.updateLastMessageId);

  const currentProjectId = useWorkspaceStore(state => state.currentProjectId);
  const currentSessionId = useWorkspaceStore(state => state.currentSessionId);

  const { updateCredits } = useAuthStore();

  // handleSend 引用（解决循环依赖）
  const handleSendRef = useRef<(messageText: string, contextFiles?: string[], attachments?: any) => void>(undefined);

  /**
   * 重试 AI 回复
   * 找到该 AI 消息之前的用户消息，删除该 AI 消息及其之后的所有消息，然后重新发送
   */
  const handleRetry = useCallback((aiMessageId: string) => {
    // 找到该 AI 消息的索引
    const aiMessageIndex = messages.findIndex((msg: Message) => msg.id === aiMessageId);
    if (aiMessageIndex === -1) return;

    // 找到该 AI 消息之前的最后一条用户消息
    let userMessageIndex = -1;
    for (let i = aiMessageIndex - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        userMessageIndex = i;
        break;
      }
    }

    if (userMessageIndex === -1) return;

    const userMessage = messages[userMessageIndex];

    // 删除该 AI 消息及其之后的所有消息
    deleteMessagesAfter(aiMessageId);

    // 重新发送用户消息（通过 ref 调用）
    setTimeout(() => {
      handleSendRef.current?.(userMessage.content, userMessage.attachments?.files || [], userMessage.attachments);
    }, 100);
  }, [messages, deleteMessagesAfter]);

  /**
   * 编辑并重新发送用户消息
   * 删除该消息及其之后的所有消息，然后发送新的用户消息
   */
  const handleEditResend = useCallback((messageId: string, newContent: string, attachments?: any) => {
    // 删除该消息及其之后的所有消息
    deleteMessagesAfter(messageId);

    // 发送新的用户消息（通过 ref 调用）
    setTimeout(() => {
      handleSendRef.current?.(newContent, attachments?.files || [], attachments);
    }, 100);
  }, [deleteMessagesAfter]);

  /**
   * 深度解读函数 - 调用专用解读 API
   */
  const handleInterpret = useCallback(async (files: string[] = [], code: string = '', userMessage: string = '', handleSend: any) => {
    if (!files.length || !code) {
      // 降级：如果没有代码或文件，使用普通聊天
      const interpretPrompt = "\n\n请对以上分析结果进行深度解读，包括：1) 主要发现和结论；2) 图表数据的生物学意义；3) 可能的临床或研究应用价值。";
      await handleSend(interpretPrompt, files);
      return;
    }

    // 添加用户消息提示
    addMessage('user', '🧬 深度解读分析结果');

    // 初始化流式状态
    const newMessageId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setStreamingMessageId(newMessageId);
    clearStreamingContent();
    resetStream();

    addMessage('assistant', '');
    setIsTyping(true);
    isStreamingRef.current = true;

    // 创建中断控制器
    abortControllerRef.current = new AbortController();

    try {
      const token = localStorage.getItem('autonome_access_token');

      await fetchEventSource(`${BASE_URL}/api/chat/interpret`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          project_id: currentProjectId,
          session_id: currentSessionId,
          user_message: userMessage || '分析任务',
          code: code,
          files: files
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
            throw new Error(`Server responded with ${res.status}`);
          }
        },
        onmessage(event) {
          if (event.event === 'message') {
            const data = JSON.parse(event.data);
            appendStream(data.content);
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
            commitStreamingContent(data.content);
            clearStreamingContent();
            isStreamingRef.current = false;
            setIsTyping(false);
          } else if (event.event === 'done') {
            if (isStreamingRef.current) {
              const finalContent = getCurrentContent();
              commitStreamingContent(finalContent);
              clearStreamingContent();
              isStreamingRef.current = false;
              setIsTyping(false);
            }
          }
        },
        onclose() {
          const finalContent = getCurrentContent();
          commitStreamingContent(finalContent);
          clearStreamingContent();
          isStreamingRef.current = false;
          setIsTyping(false);
        },
        onerror(err) {
          isStreamingRef.current = false;
          setIsTyping(false);
          if (isInsufficientCreditsRef.current) {
            throw new Error('Insufficient credits - stop retry');
          }
          console.error("Interpret Error:", err);
          appendLastMessage("\n\n**[系统错误]** 深度解读服务异常，请稍后重试。");
          throw err;
        }
      });
    } catch (error) {
      isStreamingRef.current = false;
      setIsTyping(false);
      if (isInsufficientCreditsRef.current) {
        return;
      }
      console.error('[Interpret] Error:', error);
      appendLastMessage("\n\n**[系统错误]** 深度解读请求失败。");
    }
  }, [
    addMessage,
    appendLastMessage,
    appendStream,
    clearStreamingContent,
    commitStreamingContent,
    currentProjectId,
    currentSessionId,
    getCurrentContent,
    resetStream,
    setIsTyping,
    setStreamingMessageId,
    updateCredits,
    updateLastMessageId,
    abortControllerRef,
    isInsufficientCreditsRef,
    isStreamingRef,
  ]);

  return {
    handleRetry,
    handleEditResend,
    handleInterpret,
    handleSendRef,
  };
}

export default useMessageActions;