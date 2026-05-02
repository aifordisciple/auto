/**
 * Claude 模式 Zustand Store
 *
 * 管理 Claude 会话状态: sessions, conversations, messages, streaming
 * 类型定义统一在 @/types/claude.ts
 */

import { create } from 'zustand';
import type {
  ClaudeEvent,
  ClaudeMessage,
  ClaudeSession,
  ClaudeConversation,
} from '@/types/claude';

// 重新导出供外部引用（向后兼容旧导入路径）
export type {
  ClaudeEvent,
  ClaudeMessage,
  ClaudeSession,
  ClaudeConversation,
  PlanData,
  PlanStep,
} from '@/types/claude';

interface ClaudeStore {
  sessions: ClaudeSession[];
  activeSessionId: string | null;
  conversations: ClaudeConversation[];
  activeConversationId: string | null;
  messages: ClaudeMessage[];
  isStreaming: boolean;
  streamEvents: ClaudeEvent[];

  setSessions: (sessions: ClaudeSession[]) => void;
  setActiveSession: (id: string) => void;
  addSession: (session: ClaudeSession) => void;
  removeSession: (id: string) => void;

  setConversations: (conversations: ClaudeConversation[]) => void;
  setActiveConversation: (id: string) => void;

  setMessages: (messages: ClaudeMessage[]) => void;
  addMessage: (message: ClaudeMessage) => void;
  appendStreamContent: (event: ClaudeEvent) => void;
  setStreaming: (streaming: boolean) => void;
  resetStream: () => void;
}

export const useClaudeStore = create<ClaudeStore>((set) => ({
  sessions: [],
  activeSessionId: null,
  conversations: [],
  activeConversationId: null,
  messages: [],
  isStreaming: false,
  streamEvents: [],

  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (id) => set({ activeSessionId: id }),
  addSession: (session) =>
    set((s) => ({ sessions: [...s.sessions, session] })),
  removeSession: (id) =>
    set((s) => ({
      sessions: s.sessions.filter((ses) => ses.id !== id),
    })),

  setConversations: (conversations) => set({ conversations }),
  setActiveConversation: (id) => set({ activeConversationId: id }),

  setMessages: (messages) => set({ messages }),
  addMessage: (message) =>
    set((s) => ({ messages: [...s.messages, message] })),
  appendStreamContent: (event) =>
    set((s) => ({ streamEvents: [...s.streamEvents, event] })),
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  resetStream: () => set({ streamEvents: [], isStreaming: false }),
}));
