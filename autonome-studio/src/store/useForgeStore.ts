/**
 * 技能锻造状态管理 Store
 *
 * 管理锻造会话、消息、技能草稿等状态
 */

import { create } from 'zustand';

// 执行器类型
export type ExecutorType = 'Python_env' | 'R_env' | 'Logical_Blueprint' | 'Python_Package';

// 技能草稿结构
export interface SkillDraft {
  name: string;
  description: string;
  executor_type: ExecutorType;
  script_code: string;
  nextflow_code?: string;
  parameters_schema: Record<string, any>;
  expert_knowledge: string;
  dependencies: string[];
  category?: string;
  subcategory?: string;
  tags?: string[];
}

// 消息结构
export interface ForgeMessage {
  id: number;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  attachments: string[];
  created_at: string;
}

// 会话结构
export interface ForgeSession {
  id: string;
  user_id: number;
  title: string;
  status: 'drafting' | 'testing' | 'ready' | 'saved';
  skill_draft: SkillDraft;
  skill_id?: string;
  executor_type: ExecutorType;
  created_at: string;
  updated_at: string;
  messages: ForgeMessage[];
}

// 会话列表项
export interface ForgeSessionListItem {
  id: string;
  title: string;
  status: string;
  executor_type: string;
  created_at: string;
  updated_at: string;
  has_draft: boolean;
}

// 初始草稿状态
const initialDraft: SkillDraft = {
  name: '',
  description: '',
  executor_type: 'Python_env',
  script_code: '',
  nextflow_code: '',
  parameters_schema: {},
  expert_knowledge: '',
  dependencies: []
};

// Store 状态接口
interface ForgeState {
  // 会话信息
  sessionId: string | null;
  sessionTitle: string;
  sessionStatus: string;

  // 消息列表
  messages: ForgeMessage[];
  addMessage: (role: 'user' | 'assistant', content: string, attachments?: string[]) => void;
  appendLastMessage: (content: string) => void;
  setMessages: (messages: ForgeMessage[]) => void;
  clearMessages: () => void;

  // 技能草稿
  skillDraft: SkillDraft;
  updateSkillDraft: (updates: Partial<SkillDraft>) => void;
  setSkillDraft: (draft: SkillDraft) => void;

  // 附件
  attachments: string[];
  addAttachment: (path: string) => void;
  removeAttachment: (path: string) => void;
  clearAttachments: () => void;

  // 执行器类型
  executorType: ExecutorType;
  setExecutorType: (type: ExecutorType) => void;

  // 状态
  isTyping: boolean;
  setIsTyping: (status: boolean) => void;

  // 会话列表
  sessionList: ForgeSessionListItem[];
  setSessionList: (list: ForgeSessionListItem[]) => void;

  // 会话管理
  createSession: () => Promise<string>;
  loadSession: (sessionId: string) => Promise<void>;
  loadSessionList: () => Promise<void>;

  // 重置
  reset: () => void;
}

// 初始状态
const initialState = {
  sessionId: null,
  sessionTitle: '新技能锻造',
  sessionStatus: 'drafting',
  messages: [],
  skillDraft: initialDraft,
  attachments: [],
  executorType: 'Python_env' as ExecutorType,
  isTyping: false,
  sessionList: []
};

export const useForgeStore = create<ForgeState>((set, get) => ({
  ...initialState,

  // 消息操作
  addMessage: (role, content, attachments = []) => set(state => ({
    messages: [...state.messages, {
      id: Date.now(),
      session_id: state.sessionId || '',
      role,
      content,
      attachments,
      created_at: new Date().toISOString()
    }]
  })),

  appendLastMessage: (content) => set(state => {
    const messages = [...state.messages];
    if (messages.length > 0) {
      messages[messages.length - 1].content += content;
    }
    return { messages };
  }),

  setMessages: (messages) => set({ messages }),

  clearMessages: () => set({ messages: [], skillDraft: initialDraft }),

  // 技能草稿操作
  updateSkillDraft: (updates) => set(state => ({
    skillDraft: { ...state.skillDraft, ...updates }
  })),

  setSkillDraft: (draft) => set({ skillDraft: draft }),

  // 附件操作
  addAttachment: (path) => set(state => ({
    attachments: [...state.attachments, path]
  })),

  removeAttachment: (path) => set(state => ({
    attachments: state.attachments.filter(p => p !== path)
  })),

  clearAttachments: () => set({ attachments: [] }),

  // 执行器类型
  setExecutorType: (type) => set({ executorType: type }),

  // 状态
  setIsTyping: (status) => set({ isTyping: status }),

  // 会话列表
  setSessionList: (list) => set({ sessionList: list }),

  // 创建会话
  createSession: async () => {
    const { executorType } = get();

    try {
      const response = await fetch('/api/skills/forge/session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        },
        body: JSON.stringify({
          title: '新技能锻造',
          executor_type: executorType
        })
      });

      const data = await response.json();
      set({
        sessionId: data.session_id,
        sessionTitle: data.title,
        sessionStatus: 'drafting',
        messages: [],
        skillDraft: initialDraft
      });

      return data.session_id;
    } catch (error) {
      console.error('创建会话失败:', error);
      throw error;
    }
  },

  // 加载会话
  loadSession: async (sessionId) => {
    try {
      const response = await fetch(`/api/skills/forge/session/${sessionId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        }
      });

      const data = await response.json();

      set({
        sessionId: data.id,
        sessionTitle: data.title,
        sessionStatus: data.status,
        messages: data.messages || [],
        skillDraft: data.skill_draft || initialDraft,
        executorType: data.executor_type
      });
    } catch (error) {
      console.error('加载会话失败:', error);
      throw error;
    }
  },

  // 加载会话列表
  loadSessionList: async () => {
    try {
      const response = await fetch('/api/skills/forge/sessions', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        }
      });

      const data = await response.json();
      set({ sessionList: data.sessions || [] });
    } catch (error) {
      console.error('加载会话列表失败:', error);
    }
  },

  // 重置
  reset: () => set(initialState)
}));