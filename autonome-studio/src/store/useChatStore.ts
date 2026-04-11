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

export interface ChatState {
  messages: Message[];
  setMessages: (messages: Message[]) => void;
  addMessage: (role: Role, content: string, attachments?: MessageAttachments) => void;
  // 新增：用于流式拼接最后一个气泡的内容
  appendLastMessage: (contentChunk: string) => void;
  // 新增：更新指定消息的内容
  updateMessage: (messageId: string, content: string) => void;
  // ✨ 新增：更新最后一条消息的 ID（用于流式结束后同步后端真实消息 ID）
  updateLastMessageId: (newId: string) => void;
  // 新增：删除指定消息及其之后的所有消息（用于重试和编辑）
  deleteMessagesAfter: (messageId: string) => void;
  // 清空消息
  clearMessages: () => void;
  isTyping: boolean;
  setIsTyping: (status: boolean) => void;

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
  // ✨ 流式消息优化状态
  // ==========================================
  /** 当前正在流式传输的消息 ID */
  streamingMessageId: string | null;
  /** 流式消息的累积内容（用于快速渲染） */
  streamingContent: string;
  /** 流式内容版本号（用于防止竞态条件） */
  streamingContentVersion: number;
  /** 已提交内容版本号（用于防止旧内容覆盖新内容） */
  committedContentVersion: number;
  /** 设置流式消息 ID */
  setStreamingMessageId: (id: string | null) => void;
  /** 追加流式内容（直接更新，不经过消息列表） */
  appendStreamingContent: (chunk: string) => void;
  /** 设置流式内容（完整替换） */
  setStreamingContent: (content: string) => void;
  /** 提交流式内容到消息列表 */
  commitStreamingContent: (explicitContent?: string) => void;
  /** 清空流式状态 */
  clearStreamingContent: () => void;
  /** 获取当前流式内容（用于同步读取） */
  getCurrentStreamingContent: () => string;

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

export const useChatStore: UseBoundStore<StoreApi<ChatState>> = create<ChatState>((set) => ({
  messages: [initialMessage],
  setMessages: (messages: Message[]) => set({ messages }),
  // ✨ 扩展 addMessage 支持附件参数
  addMessage: (role, content, attachments) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          role,
          content,
          timestamp: Date.now(),
          attachments,  // ✨ 保存附件信息
        },
      ],
    })),
  // 新增实现：找到最后一条消息，把新传来的字符拼接到末尾
  appendLastMessage: (contentChunk: string) =>
    set((state) => {
      const newMessages = [...state.messages];
      if (newMessages.length > 0) {
        newMessages[newMessages.length - 1].content += contentChunk;
      }
      return { messages: newMessages };
    }),
  // 新增实现：更新指定消息的内容
  updateMessage: (messageId: string, content: string) =>
    set((state) => ({
      messages: state.messages.map(msg =>
        msg.id === messageId ? { ...msg, content } : msg
      ),
    })),
  // ✨ 新增：更新最后一条消息的 ID（用于流式结束后同步后端真实消息 ID）
  // 解决问题：前端使用临时 ID（如 1712345678900-abc），后端使用 msg_{uuid} 格式
  // 当用户点击执行策略卡片时，前端需要真实 ID 来调用 PATCH API 持久化 TASK_ID
  updateLastMessageId: (newId: string) =>
    set((state) => {
      const newMessages = [...state.messages];
      if (newMessages.length > 0) {
        // 找到最后一条 assistant 消息并更新其 ID
        const lastAssistantIndex = newMessages.map(m => m.role).lastIndexOf('assistant');
        if (lastAssistantIndex !== -1) {
          newMessages[lastAssistantIndex] = {
            ...newMessages[lastAssistantIndex],
            id: newId,
          };
        }
      }
      return { messages: newMessages };
    }),
  // ✨ 新增：删除指定消息及其之后的所有消息（用于重试和编辑重新发送）
  deleteMessagesAfter: (messageId: string) =>
    set((state) => {
      const messageIndex = state.messages.findIndex(msg => msg.id === messageId);
      if (messageIndex === -1) return state;
      // 保留该消息之前的所有消息
      return {
        messages: state.messages.slice(0, messageIndex),
        // 清空流式状态
        streamingMessageId: null,
        streamingContent: '',
        isTyping: false,
      };
    }),
  // 清空消息（保留初始欢迎语）
  clearMessages: () => set({ messages: [initialMessage] }),
  isTyping: false,
  setIsTyping: (status: boolean) => set({ isTyping: status }),

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
  // ✨ 流式消息优化状态实现
  // ==========================================
  streamingMessageId: null,
  streamingContent: '',
  streamingContentVersion: 0,
  committedContentVersion: 0,
  setStreamingMessageId: (id: string | null) => set({ streamingMessageId: id }),
  appendStreamingContent: (chunk: string) =>
    set((state) => ({
      streamingContent: state.streamingContent + chunk,
      streamingContentVersion: state.streamingContentVersion + 1,
    })),
  setStreamingContent: (content: string) =>
    set((state) => ({
      streamingContent: content,
      streamingContentVersion: state.streamingContentVersion + 1,
    })),
  // ✨ 修复：commitStreamingContent 接受可选的 content 参数
  // 如果传入 content，直接使用它而不是从 state 读取（解决异步问题）
  // 🔧 增强：添加版本号检查，防止旧内容覆盖新内容
  commitStreamingContent: (explicitContent?: string) =>
    set((state) => {
      // 🔧 版本号检查：如果传入内容但版本号已过期，跳过更新
      // 注意：只有传入 explicitContent 时才检查版本号，因为这是后端发送的修复内容
      if (explicitContent !== undefined) {
        // 后端发送的修复内容优先级最高，直接使用
        const newMessages = [...state.messages];
        if (newMessages.length > 0) {
          const lastAssistantIndex = newMessages.map(m => m.role).lastIndexOf('assistant');
          if (lastAssistantIndex !== -1) {
            newMessages[lastAssistantIndex] = {
              ...newMessages[lastAssistantIndex],
              content: explicitContent,
            };
          }
        }
        return {
          messages: newMessages,
          streamingMessageId: null,
          streamingContent: '',
          committedContentVersion: state.streamingContentVersion + 1,
        };
      }

      // 使用 state 中的流式内容
      const contentToCommit = state.streamingContent;
      const newMessages = [...state.messages];
      if (newMessages.length > 0 && contentToCommit) {
        const lastAssistantIndex = newMessages.map(m => m.role).lastIndexOf('assistant');
        if (lastAssistantIndex !== -1) {
          newMessages[lastAssistantIndex] = {
            ...newMessages[lastAssistantIndex],
            content: contentToCommit,
          };
        }
      }
      return {
        messages: newMessages,
        streamingMessageId: null,
        streamingContent: '',
        committedContentVersion: state.streamingContentVersion + 1,
      };
    }),
  clearStreamingContent: () => set({ streamingMessageId: null, streamingContent: '' }),
  getCurrentStreamingContent: () => {
    const state = useChatStore.getState();
    return state.streamingContent;
  },

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