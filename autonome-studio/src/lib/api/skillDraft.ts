// ==========================================
// 技能草稿 API（自动转化功能）
// ==========================================

import { fetchAPI } from '../api';

export interface PendingSkillDraft {
  id: number;
  user_id: number;
  session_id: string;
  project_id: string | null;
  trigger_source: string;
  trigger_score: number;
  trigger_reason: string;
  raw_material: string;
  code_blocks: Array<{ language: string; code: string }>;
  strategies: Array<Record<string, any>>;
  draft_name: string;
  draft_description: string;
  executor_type: string;
  parameters_schema: Record<string, any>;
  expert_knowledge: string;
  script_code: string;
  dependencies: string[];
  status: string;
  created_at: string;
  updated_at: string;
  published_skill_id: string | null;
}

export interface DraftStats {
  total: number;
  pending: number;
  reviewed: number;
  published: number;
  dismissed: number;
  failed: number;
}

export const skillDraftApi = {
  /**
   * 获取用户的技能草稿列表
   */
  getDrafts: async (params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<PendingSkillDraft[]> => {
    const queryParams = new URLSearchParams();
    if (params?.status) queryParams.set('status', params.status);
    if (params?.limit) queryParams.set('limit', params.limit.toString());
    if (params?.offset) queryParams.set('offset', params.offset.toString());

    const query = queryParams.toString();
    const response = await fetchAPI(`/api/skills/drafts${query ? `?${query}` : ''}`);
    return response;
  },

  /**
   * 获取草稿统计信息
   */
  getDraftStats: async (): Promise<DraftStats> => {
    const response = await fetchAPI('/api/skills/drafts/stats');
    return response;
  },

  /**
   * 获取单个草稿详情
   */
  getDraft: async (draftId: number): Promise<PendingSkillDraft> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}`);
    return response;
  },

  /**
   * 更新草稿内容
   */
  updateDraft: async (draftId: number, updates: Partial<PendingSkillDraft>): Promise<PendingSkillDraft> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
    return response;
  },

  /**
   * 发布草稿为正式技能
   */
  publishDraft: async (draftId: number, params?: {
    skill_name?: string;
    category?: string;
    tags?: string[];
  }): Promise<{ skill_id: string; name: string; status: string; message: string }> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}/publish`, {
      method: 'POST',
      body: JSON.stringify(params || {}),
    });
    return response;
  },

  /**
   * 忽略草稿
   */
  dismissDraft: async (draftId: number): Promise<{ status: string; message: string }> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}/dismiss`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 标记草稿为已查看
   */
  markReviewed: async (draftId: number): Promise<{ status: string; message: string }> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}/review`, {
      method: 'POST',
    });
    return response;
  }
};
