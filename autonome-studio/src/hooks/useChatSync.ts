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
 * 自定义数据事件通过消息 parts 中 type="data-*" 的项传递。
 */
import { useEffect, useRef } from 'react';
import { useChatStore } from '@/store/useChatStore';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
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
 * 从 UIMessage.parts 中提取 data-* 自定义事件
 * v5 协议要求自定义数据事件的 type 以 "data-" 开头
 * 返回 [{eventName, data}, ...] 例如 [{eventName: "thinking", data: {content: "..."}}]
 */
function extractDataEvents(msg: UIMessage): { eventName: string; data: unknown }[] {
  if (!msg.parts) return [];
  return msg.parts
    .filter((part): part is typeof part & { type: string } => part.type.startsWith('data-'))
    .map(part => ({
      eventName: part.type.slice(5), // "data-thinking" → "thinking"
      data: (part as { type: string; data: unknown }).data,
    }));
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
    timestamp: Date.now(),
  }));
}

export function useChatSync({ messages, isLoading }: UseChatSyncOptions) {
  const syncFromUseChat = useChatStore(state => state.syncFromUseChat);
  const setThinkingContent = useChatStore(state => state.setThinkingContent);
  const setIsThinking = useChatStore(state => state.setIsThinking);
  const setCurrentSessionId = useChatStore(state => state.setCurrentSessionId);
  // ⚠️ 同时同步 session_id 到 workspaceStore，确保 SessionSidebar 刷新
  const setWorkspaceSessionId = useWorkspaceStore(state => state.setCurrentSessionId);

  // 跟踪每个消息已处理的 data-* parts 数量
  // key: message.id, value: 已处理的 data parts 数量
  const processedDataPartsRef = useRef<Record<string, number>>({});
  // 跟踪上一次 isLoading 状态，避免流式期间重复触发 syncLoadingState
  const prevIsLoadingRef = useRef(false);

  // ==========================================
  // 分离高频渲染状态与低频业务状态
  //
  // 流式输出期间（isLoading=true），aiMessages 每秒变化十几次，
  // 如果全量同步到 Zustand mirroredMessages，会触发所有订阅组件无效重渲染。
  //
  // 优化策略：
  // - 流式开始时：仅同步 isLoading=true，不同步消息内容
  // - 流式期间：messages 变化不触发任何 Zustand 写入（跳过）
  // - 流结束后：一次性将完整消息提交到 mirroredMessages
  // - data-* 事件始终同步（低频，不影响性能）
  // ==========================================
  useEffect(() => {
    const wasLoading = prevIsLoadingRef.current;
    prevIsLoadingRef.current = isLoading;

    if (isLoading && !wasLoading) {
      // 流刚开始：仅同步 typing 状态，保持 mirroredMessages 不变
      useChatStore.getState().syncLoadingState(true);
    } else if (!isLoading) {
      // 非流式状态（流结束或空闲）：提交完整消息到 Zustand
      // 这也覆盖了首次挂载和会话切换后的初始化同步
      const storeMessages = convertToStoreMessages(messages);
      syncFromUseChat(storeMessages, false);
    }
    // 流式期间（isLoading && wasLoading）：跳过，不触发任何 Zustand 写入
  }, [messages, isLoading, syncFromUseChat]);

  // 处理消息 parts 中的 data-* 事件（v5 自定义数据事件）
  // ⚠️ 关键：data-* parts 是增量添加到现有 assistant 消息中的，
  // 所以需要跟踪每个消息已处理的 parts 数量，只处理新增的
  useEffect(() => {
    for (const msg of messages) {
      if (!msg.parts) continue;

      const dataParts = msg.parts.filter(
        (part): part is typeof part & { type: string } => part.type.startsWith('data-')
      );

      const alreadyProcessed = processedDataPartsRef.current[msg.id] ?? 0;
      const newParts = dataParts.slice(alreadyProcessed);

      for (const part of newParts) {
        const eventName = part.type.slice(5); // "data-thinking" → "thinking"
        const eventData = (part as { type: string; data: unknown }).data;
        if (!eventData || typeof eventData !== 'object') continue;
        const event = eventData as Record<string, unknown>;

        switch (eventName) {
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
            // ⚠️ 同步到 workspaceStore，确保 SessionSidebar 和 ChatStage 的 currentSessionId 一致
            // 只有新会话（is_new=true）时才更新，避免切换历史会话时覆盖
            if (event.is_new) {
              setWorkspaceSessionId(event.session_id as string);
            }
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

      // 更新已处理的 parts 计数
      processedDataPartsRef.current[msg.id] = dataParts.length;
    }

    // 清理已删除消息的跟踪记录
    const currentIds = new Set(messages.map(m => m.id));
    for (const id of Object.keys(processedDataPartsRef.current)) {
      if (!currentIds.has(id)) {
        delete processedDataPartsRef.current[id];
      }
    }
  }, [messages, setThinkingContent, setIsThinking, setCurrentSessionId, setWorkspaceSessionId]);

  // 流结束后关闭思考状态
  useEffect(() => {
    if (!isLoading) {
      setIsThinking(false);
    }
  }, [isLoading, setIsThinking]);
}
