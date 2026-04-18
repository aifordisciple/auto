// ==========================================
// 首页收藏技能管理（本地存储）
// ==========================================

const PINNED_SKILLS_KEY = 'autonome_pinned_skills';

export interface PinnedSkill {
  skill_id: string;
  name: string;
  description?: string;
  executor_type: string;
  pinned_at: number;
}

export const pinnedSkillsApi = {
  /**
   * 获取所有收藏的技能
   */
  getPinnedSkills: (): PinnedSkill[] => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(PINNED_SKILLS_KEY);
      if (stored) {
        try {
          return JSON.parse(stored);
        } catch {
          return [];
        }
      }
    }
    return [];
  },

  /**
   * 添加收藏技能
   */
  pinSkill: (skill: PinnedSkill): void => {
    if (typeof window !== 'undefined') {
      const skills = pinnedSkillsApi.getPinnedSkills();
      // 检查是否已收藏
      if (!skills.find(s => s.skill_id === skill.skill_id)) {
        skills.unshift({ ...skill, pinned_at: Date.now() });
        // 只保留最近 10 个
        const trimmed = skills.slice(0, 10);
        localStorage.setItem(PINNED_SKILLS_KEY, JSON.stringify(trimmed));
      }
    }
  },

  /**
   * 取消收藏
   */
  unpinSkill: (skillId: string): void => {
    if (typeof window !== 'undefined') {
      const skills = pinnedSkillsApi.getPinnedSkills();
      const filtered = skills.filter(s => s.skill_id !== skillId);
      localStorage.setItem(PINNED_SKILLS_KEY, JSON.stringify(filtered));
    }
  },

  /**
   * 检查是否已收藏
   */
  isPinned: (skillId: string): boolean => {
    const skills = pinnedSkillsApi.getPinnedSkills();
    return skills.some(s => s.skill_id === skillId);
  },
};
