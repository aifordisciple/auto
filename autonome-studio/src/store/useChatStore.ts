import { create } from 'zustand';

export type Role = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: number;
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

interface ChatState {
  messages: Message[];
  setMessages: (messages: Message[]) => void;
  addMessage: (role: Role, content: string) => void;
  // 新增：用于流式拼接最后一个气泡的内容
  appendLastMessage: (contentChunk: string) => void;
  // 新增：更新指定消息的内容
  updateMessage: (messageId: string, content: string) => void;
  // 清空消息
  clearMessages: () => void;
  isTyping: boolean;
  setIsTyping: (status: boolean) => void;

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

export const useChatStore = create<ChatState>((set) => ({
  messages: [initialMessage],
  setMessages: (messages: Message[]) => set({ messages }),
  addMessage: (role, content) =>
    set((state) => ({
      messages: [
        ...state.messages,
        { id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`, role, content, timestamp: Date.now() },
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
  // 清空消息（保留初始欢迎语）
  clearMessages: () => set({ messages: [initialMessage] }),
  isTyping: false,
  setIsTyping: (status: boolean) => set({ isTyping: status }),

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