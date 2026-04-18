// ==========================================
// 技能快速执行 API
// ==========================================

import { fetchAPI } from '../api';

export interface QuickMatchRequest {
  user_query: string;
  context?: Record<string, unknown>;
}

export interface QuickMatchResponse {
  intent_type: string;
  confidence: number;
  matched_skills: Array<{
    skill_id: string;
    name: string;
    description?: string;
    executor_type: string;
    match_score: number;
    match_reason: string;
  }>;
  parameters_suggestion: Record<string, unknown>;
  match_source: string;
  match_mode: string;  // fast | precise | auto
  reason: string;
}

/**
 * 匹配模式类型
 * - fast: 快速模式，仅规则+向量匹配，<200ms
 * - precise: 精准模式，完整三阶段匹配（含LLM），~1-2s
 * - auto: 自动模式，根据置信度决定是否使用LLM（默认）
 */
export type MatchMode = 'fast' | 'precise' | 'auto';

export const quickExecuteApi = {
  /**
   * 快速匹配技能 - 根据用户输入推荐最合适的技能
   * @param query 用户查询
   * @param context 上下文信息
   * @param mode 匹配模式：fast(快速) | precise(精准) | auto(自动，默认)
   */
  matchSkills: async (
    query: string,
    context?: Record<string, unknown>,
    mode: MatchMode = 'auto'
  ): Promise<QuickMatchResponse> => {
    return fetchAPI('/api/skill-recommend/match', {
      method: 'POST',
      body: JSON.stringify({
        user_query: query,
        context,
        mode,
      }),
    });
  },

  /**
   * 意图识别 - 分析用户输入意图
   */
  detectIntent: async (query: string, sessionId?: string): Promise<{
    intent_type: string;
    confidence: number;
    matched_skills: Array<{
      skill_id: string;
      name: string;
      description?: string;
      executor_type: string;
      match_score: number;
      match_reason: string;
    }>;
    should_inject: boolean;
  }> => {
    return fetchAPI('/api/skill-recommend/intent', {
      method: 'POST',
      body: JSON.stringify({
        user_query: query,
        session_id: sessionId,
      }),
    });
  },
};
