/**
 * useChatSync — useChat 状态到 Zustand store 的单向同步桥接
 *
 * 将 Vercel AI SDK useChat 的 messages/isLoading/data 状态
 * 镜像到 Zustand useChatStore，保持现有组件无需感知 useChat 的存在。
 *
 * 数据流：useChat → useChatSync → useChatStore.mirrored*
 * 其他组件继续从 useChatStore 读取状态，不直接依赖 useChat。
 */
import { useEffect, useRef } from 'react';
import { useChatStore } from '@/store/useChatStore';
import type { Message as AiMessage } from 'ai';

/** AI SDK 的 data channel 中可能推送的事件类型 */
interface ChatDataEvent {
  type: string;
  [key: string]: unknown;
}

/** useChat 返回的子集，方便测试和组合 */
interface UseChatSyncOptions {
  messages: AiMessage[];
  isLoading: boolean;
  data?: ChatDataEvent[] | undefined;
}

export function useChatSync({ messages, isLoading, data }: UseChatSyncOptions) {
  const syncFromUseChat = useChatStore(state => state.syncFromUseChat);
  const setThinkingContent = useChatStore(state => state.setThinkingContent);
  const setIsThinking = useChatStore(state => state.setIsThinking);
  const setCurrentSessionId = useChatStore(state => state.setCurrentSessionId);

  const lastProcessedDataIndex = useRef(0);

  // 同步 messages 和 isLoading 到 store 的镜像字段
  useEffect(() => {
    syncFromUseChat(messages, isLoading);
  }, [messages, isLoading, syncFromUseChat]);

  // 处理 data channel 中的结构化事件
  useEffect(() => {
    if (!data || data.length === 0) return;

    for (let i = lastProcessedDataIndex.current; i < data.length; i++) {
      const event = data[i];
      if (!event) continue;

      switch (event.type) {
        case 'thinking':
          // 累积思考内容（后端逐 token 推送）
          {
            const thinkingContent = useChatStore.getState().thinkingContent;
            setThinkingContent(thinkingContent + (event.content as string));
            setIsThinking(true);
          }
          break;
        case 'session_info':
          setCurrentSessionId(event.session_id as string);
          break;
        case 'billing':
          useChatStore.getState().setLastBilling({
            cost: event.cost as number,
            balance: event.balance as number,
          });
          break;
        case 'ai_message_id':
          useChatStore.getState().updateMirroredMessageId(event.message_id as string);
          break;
        case 'ai_message_content':
          // 内容已通过 useChat.messages 自动同步，无需额外处理
          break;
        case 'queue_start':
        case 'queue_progress':
        case 'queue_complete':
        case 'queue_error':
        case 'queue_done':
          // 队列事件保留占位，后续 Task 接入队列 UI 时处理
          break;
      }
    }

    lastProcessedDataIndex.current = data.length;
  }, [data, setThinkingContent, setIsThinking, setCurrentSessionId]);

  // 流结束后关闭思考状态
  useEffect(() => {
    if (!isLoading) {
      setIsThinking(false);
    }
  }, [isLoading, setIsThinking]);
}
