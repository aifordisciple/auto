import { create, StoreApi, UseBoundStore } from 'zustand';

export type Role = 'user' | 'assistant' | 'system';

/**
 * ✨ 消息附件类型定义
 * 用于记录用户发送消息时附带的内容，在消息气泡下方显示标记
 */
export interface MessageAttachments {
  /** 从数据中心选择的文件路径（蓝色标签） */
  files?: string[];
  /** Ctrl+V 粘贴的图片路径（绿色标签） */
  images?: string[];
  /** Ctrl+V 粘贴的文件路径（橙色标签） */
  pastedFiles?: string[];
  /** 预选技能（紫色标签） */
  skill?: {
    skill_id: string;
    name: string;
  };
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: number;
  /** ✨ 消息附件信息 */
  attachments?: MessageAttachments;
  /** ✨ 队列状态标签（排队中的用户消息显示状态） */
  queueStatus?: 'pending' | 'processing' | 'completed' | 'failed';
  /** ✨ 关联的队列项 ID */
  queueItemId?: string;
}

export interface Bookmark {
  bookmark_id: number;
  message_id: string;
  session_id: string;
  session_title: string;
  project_id: string;
  content: string;
  note: string | null;
  created_at: string;
}

export interface SessionTag {
  id: number;
  name: string;
  color: string;
}

export interface SearchResult {
  session_id: string;
  session_title: string;
  matched_messages: {
    message_id: string;
    content: string;
    role: string;
    created_at: string;
    highlight: string;
  }[];
}

// ==========================================
// ✨ 消息队列类型定义
// ==========================================

export type QueueItemStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';

export interface ChatQueueItem {
  id: string;
  session_id: string;
  project_id: string;
  status: QueueItemStatus;
  message: string;
  attachments?: Record<string, unknown>;
  position: number;
  result_message_id?: string;
  error?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface ChatState {
  // ==========================================
  // 会话消息（从后端 API 获取，用于历史加载）
  // ==========================================
  messages: Message[];
  setMessages: (messages: Message[]) => void;
  /** 清空消息（保留初始欢迎语） */
  clearMessages: () => void;

  // ==========================================
  // useChat 镜像状态（由 useChatSync 同步，供现有组件读取）
  // ==========================================
  /** useChat 的 messages 镜像（AI SDK Message 格式） */
  mirroredMessages: Message[];
  /** useChat 的 isLoading 镜像 */
  mirroredIsTyping: boolean;
  /** 同步 useChat 状态到镜像字段（由 useChatSync 调用） */
  syncFromUseChat: (messages: Message[], isLoading: boolean) => void;
  /** 仅同步 isLoading 到镜像字段，流式期间不替换消息（性能优化） */
  syncLoadingState: (isLoading: boolean) => void;
  /** 更新镜像中最后一条 assistant 消息的 ID（后端真实 ID 同步） */
  updateMirroredMessageId: (newId: string) => void;
  /** 当前会话 ID（从 data channel session_info 事件获取） */
  currentSessionId: string | null;
  /** 设置当前会话 ID */
  setCurrentSessionId: (id: string | null) => void;

  // ==========================================
  // 计费状态
  // ==========================================
  /** 最近一次计费信息 */
  lastBilling: { cost: number; balance: number } | null;
  /** 设置计费信息 */
  setLastBilling: (billing: { cost: number; balance: number } | null) => void;

  // ==========================================
  // ✨ 分页与懒加载状态
  // ==========================================
  /** 是否有更多历史消息可加载 */
  hasMoreMessages: boolean;
  /** 是否正在加载更多消息 */
  isLoadingMore: boolean;
  /** 设置是否有更多消息 */
  setHasMoreMessages: (hasMore: boolean) => void;
  /** 设置是否正在加载 */
  setIsLoadingMore: (loading: boolean) => void;
  /** 在消息列表头部添加历史消息（懒加载） */
  prependMessages: (messages: Message[]) => void;

  // ==========================================
  // ✨ 思考过程状态
  // ==========================================
  /** AI 思考过程的累积内容 */
  thinkingContent: string;
  /** AI 是否正在思考 */
  isThinking: boolean;
  /** 设置思考内容 */
  setThinkingContent: (content: string) => void;
  /** 设置是否正在思考 */
  setIsThinking: (thinking: boolean) => void;

  // ==========================================
  // ✨ 消息队列状态
  // ==========================================
  /** 当前会话的队列项 */
  queueItems: ChatQueueItem[];
  /** 队列是否正在处理 */
  isQueueActive: boolean;
  /** 设置队列项 */
  setQueueItems: (items: ChatQueueItem[]) => void;
  /** 添加队列项 */
  addQueueItem: (item: ChatQueueItem) => void;
  /** 更新队列项状态 */
  updateQueueItemStatus: (itemId: string, status: QueueItemStatus, error?: string) => void;
  /** 移除队列项 */
  removeQueueItem: (itemId: string) => void;
  /** 清空队列 */
  clearQueueItems: () => void;
  /** 设置队列活跃状态 */
  setIsQueueActive: (active: boolean) => void;
  /** 更新消息的队列状态标签 */
  updateMessageQueueStatus: (messageId: string, status: 'pending' | 'processing' | 'completed' | 'failed') => void;

  // V3: 第一性原理消息类别

  // 搜索相关状态
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  searchResults: SearchResult[];
  setSearchResults: (results: SearchResult[]) => void;
  isSearching: boolean;
  setIsSearching: (status: boolean) => void;

  // 收藏相关状态
  bookmarks: Bookmark[];
  setBookmarks: (bookmarks: Bookmark[]) => void;
  showBookmarkPanel: boolean;
  setShowBookmarkPanel: (show: boolean) => void;

  // 标签相关状态
  tags: SessionTag[];
  setTags: (tags: SessionTag[]) => void;
  selectedTagId: number | null;
  setSelectedTagId: (tagId: number | null) => void;
}

// 预设一条初始欢迎语
const initialMessage: Message = {
  id: 'init-1',
  role: 'assistant',
  content: '您好，我是 Autonome Copilot。已为您加载当前项目的上下文环境，请问今天我们需要进行什么生信分析？\n\n您可以尝试问我：\n- 帮我写一个提取 Fastq 统计信息的 Python 脚本\n- 运行一次标准的 RNA-Seq 质控流程',
  timestamp: Date.now(),
};

/** 镜像消息的初始欢迎语（与 initialMessage 格式一致） */
const initialMirroredMessage: Message = {
  id: 'init-1',
  role: 'assistant',
  content: initialMessage.content,
  timestamp: Date.now(),
};

export const useChatStore: UseBoundStore<StoreApi<ChatState>> = create<ChatState>((set) => ({
  // ==========================================
  // 会话消息（后端 API 获取的历史消息）
  // ==========================================
  messages: [initialMessage],
  setMessages: (messages: Message[]) => set({ messages }),
  // 清空消息（保留初始欢迎语）
  clearMessages: () => set({ messages: [initialMessage] }),

  // ==========================================
  // useChat 镜像状态实现
  // ==========================================
  mirroredMessages: [initialMirroredMessage],
  mirroredIsTyping: false,
  // 同步 useChat 的 messages 和 isLoading 到镜像字段
  syncFromUseChat: (messages: Message[], isLoading: boolean) =>
    set({ mirroredMessages: messages, mirroredIsTyping: isLoading }),
  // 仅同步 isLoading，流式期间不替换 mirroredMessages（避免高频 text-delta 触发无效重渲染）
  syncLoadingState: (isLoading: boolean) =>
    set({ mirroredIsTyping: isLoading }),
  // 更新镜像中最后一条 assistant 消息的 ID（后端真实 ID 同步）
  // 解决问题：前端使用临时 ID，后端使用 msg_{uuid} 格式
  // 当用户点击执行策略卡片时，前端需要真实 ID 来调用 PATCH API 持久化 TASK_ID
  updateMirroredMessageId: (newId: string) =>
    set((state) => {
      const newMessages = [...state.mirroredMessages];
      const lastAssistantIndex = newMessages.map(m => m.role).lastIndexOf('assistant');
      if (lastAssistantIndex !== -1) {
        newMessages[lastAssistantIndex] = { ...newMessages[lastAssistantIndex], id: newId };
      }
      return { mirroredMessages: newMessages };
    }),
  currentSessionId: null,
  setCurrentSessionId: (id: string | null) => set({ currentSessionId: id }),

  // ==========================================
  // 计费状态实现
  // ==========================================
  lastBilling: null,
  setLastBilling: (billing: { cost: number; balance: number } | null) => set({ lastBilling: billing }),

  // ==========================================
  // ✨ 分页与懒加载状态实现
  // ==========================================
  hasMoreMessages: false,
  isLoadingMore: false,
  setHasMoreMessages: (hasMore: boolean) => set({ hasMoreMessages: hasMore }),
  setIsLoadingMore: (loading: boolean) => set({ isLoadingMore: loading }),
  prependMessages: (newMessages: Message[]) =>
    set((state) => ({
      messages: [...newMessages, ...state.messages],
    })),

  // ==========================================
  // ✨ 思考过程状态实现
  // ==========================================
  thinkingContent: '',
  isThinking: false,
  setThinkingContent: (content: string) => set({ thinkingContent: content }),
  setIsThinking: (thinking: boolean) => set({ isThinking: thinking }),

  // ==========================================
  // ✨ 消息队列状态实现
  // ==========================================
  queueItems: [],
  isQueueActive: false,
  setQueueItems: (items: ChatQueueItem[]) => set({ queueItems: items }),
  addQueueItem: (item: ChatQueueItem) =>
    set((state) => ({
      queueItems: [...state.queueItems, item],
      isQueueActive: true,
    })),
  updateQueueItemStatus: (itemId: string, status: QueueItemStatus, error?: string) =>
    set((state) => ({
      queueItems: state.queueItems.map(item =>
        item.id === itemId ? { ...item, status, error: error ?? item.error } : item
      ),
    })),
  removeQueueItem: (itemId: string) =>
    set((state) => ({
      queueItems: state.queueItems.filter(item => item.id !== itemId),
      isQueueActive: state.queueItems.filter(item => item.id !== itemId).length > 0,
    })),
  clearQueueItems: () => set({ queueItems: [], isQueueActive: false }),
  setIsQueueActive: (active: boolean) => set({ isQueueActive: active }),
  updateMessageQueueStatus: (messageId: string, status: 'pending' | 'processing' | 'completed' | 'failed') =>
    set((state) => ({
      messages: state.messages.map(msg =>
        msg.id === messageId ? { ...msg, queueStatus: status } : msg
      ),
    })),

  // 搜索相关
  searchQuery: '',
  setSearchQuery: (query: string) => set({ searchQuery: query }),
  searchResults: [],
  setSearchResults: (results: SearchResult[]) => set({ searchResults: results }),
  isSearching: false,
  setIsSearching: (status: boolean) => set({ isSearching: status }),

  // 收藏相关
  bookmarks: [],
  setBookmarks: (bookmarks: Bookmark[]) => set({ bookmarks }),
  showBookmarkPanel: false,
  setShowBookmarkPanel: (show: boolean) => set({ showBookmarkPanel: show }),

  // 标签相关
  tags: [],
  setTags: (tags: SessionTag[]) => set({ tags }),
  selectedTagId: null,
  setSelectedTagId: (tagId: number | null) => set({ selectedTagId: tagId }),
}));
