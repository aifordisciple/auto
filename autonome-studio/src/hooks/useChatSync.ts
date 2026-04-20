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
 * ✨ 修复：
 * - 兼容 Vercel AI SDK 的 annotations 和 parts 两种格式
 * - 放宽事件过滤：兼容 data- 前缀和无前缀的标准标注（thinking, session_info 等）
 * - 鲁棒解析数据层级（兼容存在或不存在嵌套 .data 层级）
 * - 处理 intent 意图事件，避免知识类问题"没有回复"
 */
import { useEffect, useRef } from 'react';
import { useChatStore } from '@/store/useChatStore';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { useUIStore } from '@/store/useUIStore';
import { useAuthStore } from '@/store/useAuthStore';
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
 * 修复策略：优先从 parts 提取（更完整），安全回退到 content。
 */
function extractTextFromParts(msg: UIMessage): string {
  if (msg.parts && msg.parts.length > 0) {
    const textParts = msg.parts.filter((part): part is typeof part & { type: 'text' } => part.type === 'text');
    if (textParts.length > 0) {
      return textParts.map(part => (part as { type: 'text'; text: string }).text).join('');
    }
  }
  // ✨ 安全回退：parts 无文本时使用 content（user 消息通常只有 content）
  return msg.content || '';
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

/**
 * ✨ 判断是否为有效的自定义事件类型
 * 兼容 Vercel AI SDK v5 的 data- 前缀格式和无前缀的标准标注
 */
const KNOWN_EVENT_NAMES = new Set([
  'thinking', 'session_info', 'billing', 'ai_message_id', 'ai_message_content',
  'intent', 'action',
  'queue_start', 'queue_progress', 'queue_complete', 'queue_error', 'queue_done',
]);

function isValidEventType(type: string): boolean {
  if (!type) return false;
  if (type.startsWith('data-')) return true;
  return KNOWN_EVENT_NAMES.has(type);
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
      useChatStore.getState().syncLoadingState(true);
      useChatStore.getState().setThinkingContent('');
      // ✨ 修复：流开始时立即设置 isThinking=true
      // 这样即使模型不输出 <think> 标签（如 Ollama），也会显示"思考中..."框
      // 当第一个文本内容到达或流结束时，isThinking 会被设为 false
      useChatStore.getState().setIsThinking(true);
    } else if (!isLoading && wasLoading) {
      // ✨ 流刚结束：提交完整消息到 Zustand
      // 同时将全局 thinkingContent 保存到最后一条 assistant 消息上
      // 必须在 syncFromUseChat 之前保存，否则 thinkingContent 会被覆盖掉
      const storeMessages = convertToStoreMessages(messages);
      const currentThinking = useChatStore.getState().thinkingContent;
      if (currentThinking) {
        // 找到最后一条 assistant 消息，附上 thinkingContent
        const lastAssistantIdx = storeMessages.map(m => m.role).lastIndexOf('assistant');
        if (lastAssistantIdx !== -1) {
          storeMessages[lastAssistantIdx] = {
            ...storeMessages[lastAssistantIdx],
            thinkingContent: currentThinking,
          };
        }
      }
      syncFromUseChat(storeMessages, false);
    } else if (!isLoading) {
      // 空闲状态：提交完整消息到 Zustand（保留已有 thinkingContent）
      const storeMessages = convertToStoreMessages(messages);
      syncFromUseChat(storeMessages, false);
    }

    // ✨ 流式期间：检测到助手消息有实际文本内容时，关闭思考状态
    // 这样"思考中..."框会在 AI 开始输出文本后自动消失
    if (isLoading && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.role === 'assistant') {
        const textContent = extractTextFromParts(lastMsg);
        if (textContent.length > 0) {
          useChatStore.getState().setIsThinking(false);
        }
      }
    }
  }, [messages, isLoading, syncFromUseChat]);

  // ==========================================
  // ✨ 处理消息中的自定义事件
  // 兼容 Vercel AI SDK 的 parts 和 annotations 两种格式
  // 放宽过滤条件：兼容 data- 前缀和无前缀的标准标注
  // 鲁棒解析数据层级（兼容存在或不存在嵌套 .data 层级）
  // ==========================================
  useEffect(() => {
    for (const msg of messages) {
      // ✨ 兼容 Vercel AI SDK: 事件可能在 parts 也可能在 annotations (v5 注解协议)
      let dataParts: any[] = [];

      if (msg.parts && msg.parts.length > 0) {
        const parts = msg.parts.filter((p: any) => isValidEventType(p.type));
        dataParts = [...dataParts, ...parts];
      }

      if (msg.annotations && msg.annotations.length > 0) {
        const annotations = msg.annotations.filter((a: any) => a && isValidEventType(a.type));
        dataParts = [...dataParts, ...annotations];
      }

      if (dataParts.length === 0) continue;

      const alreadyProcessed = processedDataPartsRef.current[msg.id] ?? 0;
      const newParts = dataParts.slice(alreadyProcessed);

      for (const part of newParts) {
        // ✨ 抹平命名差异：data-thinking → thinking, thinking → thinking
        let eventName = part.type;
        if (eventName.startsWith('data-')) eventName = eventName.slice(5);

        // ✨ 鲁棒解析：兼容存在或不存在嵌套 .data 层级的情况
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
                setWorkspaceSessionId(sessionId);
              }
            }
            break;
          case 'billing':
            if (event.cost !== undefined && event.balance !== undefined) {
              const newBalance = Number(event.balance);
              useChatStore.getState().setLastBilling({
                cost: Number(event.cost),
                balance: newBalance,
              });
              // ⚠️ 修复：同步更新 authStore 的 credits_balance，
              // 否则 TopHeader/Sidebar 余额不会实时刷新
              useAuthStore.getState().setCreditsBalance(newBalance);
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
          case 'intent':
            // ✨ 处理意图识别结果事件
            // 当意图为知识类/技能分发时，可触发技能中心打开
            {
              const intent = event.intent as string;
              if (intent === 'knowledge' || intent === 'basic_analysis') {
                useUIStore.getState().setSkillFilterMode('basic');
                // 不自动打开技能中心，仅在用户明确请求时打开
              }
            }
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
