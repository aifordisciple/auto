// ==========================================
// 推荐反馈 API
// ==========================================

import { fetchAPI } from '../api';

export type FeedbackEventType = 'recommend' | 'click' | 'execute' | 'success' | 'failure' | 'dismiss';

export interface RecordBehaviorRequest {
  session_id: string;
  event_type: FeedbackEventType;
  skill_id: string;
  query?: string;
  match_source?: string;
  confidence?: number;
  execution_time?: number;
}

export const feedbackApi = {
  /**
   * 记录用户行为埋点
   *
   * 事件类型：
   * - recommend: 技能被推荐
   * - click: 用户点击技能
   * - execute: 技能被执行
   * - success: 执行成功
   * - failure: 执行失败
   * - dismiss: 用户忽略推荐
   */
  recordBehavior: async (request: RecordBehaviorRequest): Promise<{ success: boolean; message: string }> => {
    return fetchAPI('/api/skill-recommend/feedback/record', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  /**
   * 获取反馈统计（管理员）
   */
  getStats: async (): Promise<{
    aggregation_time: string;
    total_skills: number;
    total_recommendations: number;
    total_clicks: number;
    total_executions: number;
    total_successes: number;
    overall_click_rate: number;
    overall_success_rate: number;
    top_performing_skills: Array<{
      skill_id: string;
      dynamic_score: number;
      click_rate: number;
      success_rate: number;
    }>;
  }> => {
    return fetchAPI('/api/skill-recommend/feedback/stats');
  },
};
