/**
 * Claude 模式 Zustand Store
 *
 * 管理 Claude 会话状态: sessions, conversations, messages, streaming
 */

import { create } from 'zustand';

export interface ClaudeEvent {
  [key: string]: unknown;
  type: string;
  timestamp: number;
  content?: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_use_id?: string;
  status?: string;
  message?: string;
  input_tokens?: number;
  output_tokens?: number;
}

export interface ClaudeMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  events?: ClaudeEvent[];
  plan?: PlanData | null;
  codeSnapshot?: string;
  usage?: { input_tokens: number; output_tokens: number } | null;
  createdAt: string;
}

export interface PlanData {
  title: string;
  steps: Array<{ title: string; description: string }>;
  codeSnapshot: string;
  estimatedCost: string;
}

export interface ClaudeSession {
  id: string;
  title: string;
  status: 'active' | 'archived' | 'closed';
  createdAt: string;
  updatedAt: string;
}

export interface ClaudeConversation {
  id: string;
  sessionId: string;
  title: string;
  createdAt: string;
}

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
