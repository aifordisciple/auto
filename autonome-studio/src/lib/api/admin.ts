// ==========================================
// Admin 管理员专区 API
// ==========================================

import { fetchAPI } from '../api';
import type { SkillAsset } from './skillForge';

export const adminApi = {
  /**
   * 获取待审核的 SKILL 列表
   */
  getPendingSkills: async (): Promise<SkillAsset[]> => {
    const response = await fetchAPI('/api/admin/skills/pending');
    return response;
  },

  /**
   * 提交审核决策
   */
  reviewSkill: async (skillId: string, action: 'APPROVE' | 'REJECT', rejectReason: string = ""): Promise<any> => {
    const response = await fetchAPI(`/api/admin/skills/${skillId}/review`, {
      method: 'POST',
      body: JSON.stringify({ action, reject_reason: rejectReason }),
    });
    return response;
  }
};
