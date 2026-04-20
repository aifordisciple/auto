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
 *
 * ✨ 修复：兼容 Vercel AI SDK 的 annotations 和 parts 两种格式，
 * 鲁棒解析数据层级（兼容存在或不存在嵌套 .data 层级的情况），
 * 彻底修复思考框不显示和 session_id 丢失的问题。
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
 * 从 UIMessage 中提取纯文本内容
 *
 * ⚠️ 修复：Vercel AI SDK 的 user 消息往往只有 content 没有 parts，
 * 原代码仅从 parts 提取，导致 user 消息内容为空字符串，UI 不显示用户消息。
 * 修复策略：优先使用 content，仅在 parts 有文本时覆盖（parts 更完整）。
 */
function extractTextFromParts(msg: UIMessage): string {
  let content = msg.content || '';
  if (msg.parts && msg.parts.length > 0) {
    const textParts = msg.parts.filter((part): part is typeof part & { type: 'text' } => part.type === 'text');
    if (textParts.length > 0) {
      content = textParts.map(part => (part as { type: 'text'; text: string }).text).join('');
    }
  }
  return content;
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
      // 流刚开始：同步 typing 状态，同时清空上一轮的思考内容
      // ⚠️ 修复：不清空 thinkingContent 会导致思考框卡死或内容堆叠
      useChatStore.getState().syncLoadingState(true);
      useChatStore.getState().setThinkingContent('');
      useChatStore.getState().setIsThinking(false);
    } else if (!isLoading) {
      // 非流式状态（流结束或空闲）：提交完整消息到 Zustand
      // 这也覆盖了首次挂载和会话切换后的初始化同步
      const storeMessages = convertToStoreMessages(messages);
      syncFromUseChat(storeMessages, false);
    }
    // 流式期间（isLoading && wasLoading）：跳过，不触发任何 Zustand 写入
  }, [messages, isLoading, syncFromUseChat]);

  // ==========================================
  // ✨ 处理消息中的 data-* 自定义事件
  // 兼容 Vercel AI SDK 的 parts 和 annotations 两种格式
  // 鲁棒解析数据层级（兼容存在或不存在嵌套 .data 层级的情况）
  // ==========================================
  useEffect(() => {
    for (const msg of messages) {
      // ✨ 兼容 Vercel AI SDK: 事件可能在 parts 也可能在 annotations (v5 注解协议)
      let dataParts: any[] = [];

      if (msg.parts && msg.parts.length > 0) {
        const parts = msg.parts.filter((p: any) => p.type && p.type.startsWith('data-'));
        dataParts = [...dataParts, ...parts];
      }

      if (msg.annotations && msg.annotations.length > 0) {
        const annotations = msg.annotations.filter((a: any) => a && a.type && a.type.startsWith('data-'));
        dataParts = [...dataParts, ...annotations];
      }

      if (dataParts.length === 0) continue;

      const alreadyProcessed = processedDataPartsRef.current[msg.id] ?? 0;
      const newParts = dataParts.slice(alreadyProcessed);

      for (const part of newParts) {
        const eventName = part.type.slice(5); // "data-thinking" → "thinking"

        // ✨ 鲁棒解析：兼容存在或不存在嵌套 .data 层级的情况
        // Vercel AI SDK v5 中，data-* part 的数据可能在 part.data 中，
        // 也可能直接在 part 本身（作为 annotations 时）
        let event: Record<string, unknown>;
        if (part.data && typeof part.data === 'object') {
          event = part.data as Record<string, unknown>;
        } else {
          // 没有 .data 包装，直接使用 part 本身（去掉 type 字段）
          const { type, ...rest } = part;
          event = rest;
        }

        switch (eventName) {
          case 'thinking':
            // 累积思考内容（后端逐 token 推送）
            {
              const thinkingContent = useChatStore.getState().thinkingContent;
              // ✨ 兼容：思考内容可能在 content 或 text 字段
              const newContent = (event.content || event.text || '') as string;
              setThinkingContent(thinkingContent + newContent);
              setIsThinking(true);
            }
            break;
          case 'session_info':
            {
              const sessionId = event.session_id as string;
              if (sessionId) {
                setCurrentSessionId(sessionId);
                // ⚠️ 修复：无论 is_new 是什么，都强制同步给 workspace，
                // 防止 fetch 历史后 currentSessionId 不一致导致上下文丢失
                setWorkspaceSessionId(sessionId);
              }
            }
            break;
          case 'billing':
            if (event.cost !== undefined && event.balance !== undefined) {
              useChatStore.getState().setLastBilling({
                cost: Number(event.cost),
                balance: Number(event.balance),
              });
            }
            break;
          case 'ai_message_id':
            if (event.message_id) {
              useChatStore.getState().updateMirroredMessageId(event.message_id as string);
            }
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
