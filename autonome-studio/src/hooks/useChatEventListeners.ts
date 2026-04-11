/**
 * useChatEventListeners Hook - 聊天事件监听器管理
 *
 * 功能：
 * 1. 统一管理所有全局事件监听器
 * 2. 自动清理，防止内存泄漏
 * 3. 支持自定义事件类型
 *
 * 从 ChatStage.tsx 提取，减少主组件复杂度
 */
import { useEffect, useCallback } from 'react';
import { useChatStore, ChatState } from '@/store/useChatStore';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { BASE_URL } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

export interface ChatEventListenersConfig {
  /** 滚动到底部的 ref */
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
}

// ==========================================
// Hook 实现
// ==========================================

export function useChatEventListeners(config: ChatEventListenersConfig) {
  const { messagesEndRef } = config;

  // Store 状态
  const currentSessionId = useWorkspaceStore(state => state.currentSessionId);
  const setMessages = useChatStore((state: ChatState) => state.setMessages);
  const addMessage = useChatStore((state: ChatState) => state.addMessage);
  const messages = useChatStore((state: ChatState) => state.messages);

  /**
   * 刷新聊天消息
   */
  const refreshChatMessages = useCallback(async () => {
    if (!currentSessionId) return;
    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/sessions/${currentSessionId}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.data && data.data.length > 0) {
        const formattedMessages = data.data.map((msg: { role: string; content: string; id: number; attachments?: any }) => ({
          id: String(msg.id),
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
          timestamp: Date.now(),
          attachments: msg.attachments
        }));
        setMessages(formattedMessages);
      }
    } catch (e) {
      console.error('Failed to refresh messages:', e);
    }
  }, [currentSessionId, setMessages]);

  /**
   * 监听刷新聊天事件
   */
  useEffect(() => {
    window.addEventListener('refresh-chat', refreshChatMessages);
    return () => window.removeEventListener('refresh-chat', refreshChatMessages);
  }, [refreshChatMessages]);

  /**
   * 监听任务结果追加事件
   */
  useEffect(() => {
    const handleAppendResultMessage = (event: any) => {
      const newMsg = event.detail;
      if (newMsg && newMsg.content) {
        addMessage(newMsg.role, newMsg.content);
        // 自动滚动到底部看卡片
        setTimeout(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }, 100);
      }
    };

    window.addEventListener('append-result-message', handleAppendResultMessage);
    return () => window.removeEventListener('append-result-message', handleAppendResultMessage);
  }, [addMessage, messagesEndRef]);

  /**
   * 监听滚动到任务结果消息的事件
   */
  useEffect(() => {
    const handleScrollToTaskResult = (event: CustomEvent) => {
      const { taskName, taskId } = event.detail;
      if (!taskName && !taskId) return;

      const searchPattern = taskName ? `results/${taskName}` : `results/task_${taskId}`;
      const messageIndex = messages.findIndex((msg: any) =>
        msg.role === 'assistant' && msg.content.includes(searchPattern)
      );

      if (messageIndex !== -1) {
        const messageElements = document.querySelectorAll('[data-message-id]');
        if (messageElements[messageIndex]) {
          messageElements[messageIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
          // 添加高亮效果
          messageElements[messageIndex].classList.add('ring-2', 'ring-blue-500', 'ring-opacity-50');
          setTimeout(() => {
            messageElements[messageIndex].classList.remove('ring-2', 'ring-blue-500', 'ring-opacity-50');
          }, 2000);
        }
      }
    };

    window.addEventListener('scroll-to-task-result', handleScrollToTaskResult as EventListener);
    return () => window.removeEventListener('scroll-to-task-result', handleScrollToTaskResult as EventListener);
  }, [messages]);

  /**
   * 监听全局快捷键发来的聚焦信号
   */
  useEffect(() => {
    const handleFocusInput = () => {
      const inputEl = document.getElementById("chat-input-box");
      if (inputEl) {
        inputEl.focus();
      }
    };

    window.addEventListener('shortcut-focus-input', handleFocusInput);
    return () => window.removeEventListener('shortcut-focus-input', handleFocusInput);
  }, []);

  return {
    refreshChatMessages,
  };
}

/**
 * useGlobalEvent Hook - 通用全局事件监听器
 * 用于简化单个事件监听器的绑定
 */
export function useGlobalEvent(
  eventName: string,
  handler: (event: Event) => void,
  deps: any[] = []
) {
  useEffect(() => {
    window.addEventListener(eventName, handler);
    return () => window.removeEventListener(eventName, handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventName, ...deps]);
}

export default useChatEventListeners;