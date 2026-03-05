import { create } from 'zustand';

export type Role = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: number;
}

interface ChatState {
  messages: Message[];
  setMessages: (messages: Message[]) => void;
  addMessage: (role: Role, content: string) => void;
  // 新增：用于流式拼接最后一个气泡的内容
  appendLastMessage: (contentChunk: string) => void;
  // 清空消息
  clearMessages: () => void;
  isTyping: boolean;
  setIsTyping: (status: boolean) => void;
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
  appendLastMessage: (contentChunk) =>
    set((state) => {
      const newMessages = [...state.messages];
      if (newMessages.length > 0) {
        newMessages[newMessages.length - 1].content += contentChunk;
      }
      return { messages: newMessages };
    }),
  // 清空消息（保留初始欢迎语）
  clearMessages: () => set({ messages: [initialMessage] }),
  isTyping: false,
  setIsTyping: (status: boolean) => set({ isTyping: status }),
}));
