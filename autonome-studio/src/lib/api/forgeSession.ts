// ==========================================
// 技能锻造会话 API
// ==========================================

import { fetchAPI, BASE_URL } from '../api';
import type { ExecutorType } from './skillForge';

export interface ForgeSessionCreateRequest {
  title?: string;
  executor_type?: ExecutorType;
}

export interface ForgeSessionResponse {
  session_id: string;
  title: string;
}

export interface SkillDraft {
  name: string;
  description: string;
  executor_type: string;
  script_code: string;
  nextflow_code?: string;
  parameters_schema: Record<string, any>;
  expert_knowledge: string;
  dependencies: string[];
}

export interface ForgeSessionDetail {
  id: string;
  user_id: number;
  title: string;
  status: string;
  skill_draft: SkillDraft;
  skill_id?: string;
  executor_type: string;
  created_at: string;
  updated_at: string;
  messages: ForgeMessageData[];
}

export interface ForgeMessageData {
  id: number;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  attachments: string[];
  created_at: string;
}

export interface ForgeChatRequest {
  session_id?: string;
  message: string;
  attachments?: string[];
  executor_type?: ExecutorType;
}

export interface SkillDraftUpdateRequest {
  name?: string;
  description?: string;
  executor_type?: string;
  script_code?: string;
  nextflow_code?: string;
  parameters_schema?: Record<string, any>;
  expert_knowledge?: string;
  dependencies?: string[];
}

export interface ForgeSessionListItem {
  id: string;
  title: string;
  status: string;
  executor_type: string;
  created_at: string;
  updated_at: string;
  has_draft: boolean;
}

export const forgeSessionApi = {
  /**
   * 创建锻造会话
   */
  createSession: async (request: ForgeSessionCreateRequest): Promise<ForgeSessionResponse> => {
    const response = await fetchAPI('/api/skills/forge/session', {
      method: 'POST',
      body: JSON.stringify(request),
    });
    return response;
  },

  /**
   * 获取用户的锻造会话列表
   */
  listSessions: async (limit: number = 20, offset: number = 0): Promise<{ sessions: ForgeSessionListItem[] }> => {
    const response = await fetchAPI(`/api/skills/forge/sessions?limit=${limit}&offset=${offset}`);
    return response;
  },

  /**
   * 获取会话详情
   */
  getSession: async (sessionId: string): Promise<ForgeSessionDetail> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}`);
    return response;
  },

  /**
   * 删除会话
   */
  deleteSession: async (sessionId: string): Promise<{ status: string; message: string }> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}`, {
      method: 'DELETE',
    });
    return response;
  },

  /**
   * 手动更新技能草稿
   */
  updateDraft: async (sessionId: string, draft: SkillDraftUpdateRequest): Promise<{ status: string; skill_draft: SkillDraft }> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}/draft`, {
      method: 'PUT',
      body: JSON.stringify(draft),
    });
    return response;
  },

  /**
   * 确认保存技能
   */
  commitSkill: async (sessionId: string): Promise<{ status: string; skill_id: string; name: string }> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}/commit`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 保存并提交审核
   */
  submitSkill: async (sessionId: string): Promise<{ status: string; skill_id: string; name: string }> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}/submit`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 流式对话锻造 (SSE)
   *
   * 使用方法:
   * const onMessage = (content: string) => { ... }
   * const onSkillUpdate = (draft: SkillDraft) => { ... }
   * const onError = (error: string) => { ... }
   * const onComplete = () => { ... }
   *
   * await forgeSessionApi.chatStream(sessionId, message, attachments, onMessage, onSkillUpdate, onError, onComplete, signal);
   */
  chatStream: async (
    sessionId: string,
    message: string,
    attachments: string[] = [],
    onMessage: (content: string) => void,
    onSkillUpdate: (draft: SkillDraft) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    signal?: AbortSignal
  ): Promise<void> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null;

    const response = await fetch(`${BASE_URL}/api/skills/forge/session/${sessionId}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
      },
      body: JSON.stringify({
        message,
        attachments,
        executor_type: 'Python_env'
      }),
      signal
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            const eventType = line.substring(7).trim();
            continue;
          }

          if (line.startsWith('data:')) {
            const data = line.substring(5).trim();
            try {
              const parsed = JSON.parse(data);

              if (parsed.type === 'text') {
                onMessage(parsed.content);
              } else if (parsed.type === 'draft') {
                onSkillUpdate(parsed.data);
              } else if (parsed.type === 'error') {
                onError?.(parsed.content);
              } else if (parsed.type === 'done') {
                onComplete?.();
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
};
