/**
 * useChatSync — useChat 状态到 Zustand store 的单向同步桥接
 *
 * 将 Vercel AI SDK useChat 的 messages/status 状态
 * 镜像到 Zustand useChatStore，保持现有组件无需感知 useChat 的存在。
 *
 * 数据流：useChat → useChatSync → useChatStore.mirrored*
 * 其他组件继续从 useChatStore 读取状态，不直接依赖 useChat。
 *
 * v5 适配：UIMessage 使用 parts[] 而非 content 字符串，
 * 此处将 UIMessage 转换为 store 的 Message 格式（含 content: string）。
 * data channel 事件通过消息 parts 中的 data 类型传递。
 */
import { useEffect, useRef } from 'react';
import { useChatStore } from '@/store/useChatStore';
import type { Message } from '@/store/useChatStore';
import type { UIMessage } from '@ai-sdk/react';

/** useChat 返回的子集，方便测试和组合 */
interface UseChatSyncOptions {
  messages: UIMessage[];
  isLoading: boolean;
}

/**
 * 从 UIMessage.parts 中提取纯文本内容
 * v5 中 UIMessage 没有 content 字段，文本在 parts 中 type='text' 的项里
 */
function extractTextFromParts(msg: UIMessage): string {
  if (!msg.parts) return '';
  return msg.parts
    .filter((part): part is typeof part & { type: 'text' } => part.type === 'text')
    .map(part => (part as { type: 'text'; text: string }).text)
    .join('');
}

/**
 * 从 UIMessage.parts 中提取 data channel 事件
 * v5 中自定义数据通过 parts 中 type='data' 的项传递
 */
function extractDataEvents(msg: UIMessage): unknown[] {
  if (!msg.parts) return [];
  return msg.parts
    .filter(part => part.type === 'data')
    .map(part => (part as { type: 'data'; data: unknown }).data);
}

/**
 * 将 UIMessage[] 转换为 store 的 Message[] 格式
 * 保持下游组件（MemoizedMessageItem、VirtualizedMessageList）无需改动
 */
function convertToStoreMessages(aiMessages: UIMessage[]): Message[] {
  return aiMessages.map(msg => ({
    id: msg.id,
    role: msg.role as 'user' | 'assistant' | 'system',
    content: extractTextFromParts(msg),
    timestamp: msg.createdAt ? new Date(msg.createdAt).getTime() : Date.now(),
  }));
}

export function useChatSync({ messages, isLoading }: UseChatSyncOptions) {
  const syncFromUseChat = useChatStore(state => state.syncFromUseChat);
  const setThinkingContent = useChatStore(state => state.setThinkingContent);
  const setIsThinking = useChatStore(state => state.setIsThinking);
  const setCurrentSessionId = useChatStore(state => state.setCurrentSessionId);

  // 跟踪已处理的消息数量，避免重复处理 data 事件
  const lastProcessedMessageCount = useRef(0);

  // 同步 messages 和 isLoading 到 store 的镜像字段
  // 转换 UIMessage[] → Message[]，保持下游组件兼容
  useEffect(() => {
    const storeMessages = convertToStoreMessages(messages);
    syncFromUseChat(storeMessages, isLoading);
  }, [messages, isLoading, syncFromUseChat]);

  // 处理消息 parts 中的 data 事件（v5 替代 data channel）
  useEffect(() => {
    // 只处理新增的消息
    for (let i = lastProcessedMessageCount.current; i < messages.length; i++) {
      const msg = messages[i];
      if (!msg) continue;

      const dataEvents = extractDataEvents(msg);
      for (const eventData of dataEvents) {
        if (!eventData || typeof eventData !== 'object') continue;
        const event = eventData as Record<string, unknown>;

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
    }

    lastProcessedMessageCount.current = messages.length;
  }, [messages, setThinkingContent, setIsThinking, setCurrentSessionId]);

  // 流结束后关闭思考状态
  useEffect(() => {
    if (!isLoading) {
      setIsThinking(false);
    }
  }, [isLoading, setIsThinking]);
}
