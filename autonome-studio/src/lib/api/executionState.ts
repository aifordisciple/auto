// ==========================================
// 执行参数状态管理（本地存储）
// ==========================================

import type { ErrorDiagnosis } from './errorDiagnostic';

const EXECUTION_PARAMS_KEY = 'autonome_execution_params';

export interface ExecutionParams {
  skillId: string;
  skillName: string;
  parameters: Record<string, unknown>;
  timestamp: number;
  status: 'success' | 'failed' | 'pending';
  errorMessage?: string;
  errorDiagnosis?: ErrorDiagnosis;
}

export const executionStateApi = {
  /**
   * 保存执行参数（失败时保留）
   */
  saveParams: (params: ExecutionParams): void => {
    if (typeof window !== 'undefined') {
      const allParams = executionStateApi.getAllParams();
      allParams.unshift(params);
      // 只保留最近 10 条
      const trimmed = allParams.slice(0, 10);
      localStorage.setItem(EXECUTION_PARAMS_KEY, JSON.stringify(trimmed));
    }
  },

  /**
   * 获取所有保存的参数
   */
  getAllParams: (): ExecutionParams[] => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(EXECUTION_PARAMS_KEY);
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
   * 获取最近失败的参数
   */
  getRecentFailed: (): ExecutionParams | null => {
    const allParams = executionStateApi.getAllParams();
    return allParams.find(p => p.status === 'failed') || null;
  },

  /**
   * 标记参数为成功
   */
  markSuccess: (skillId: string): void => {
    if (typeof window !== 'undefined') {
      const allParams = executionStateApi.getAllParams();
      const updated = allParams.map(p =>
        p.skillId === skillId ? { ...p, status: 'success' as const } : p
      );
      localStorage.setItem(EXECUTION_PARAMS_KEY, JSON.stringify(updated));
    }
  },

  /**
   * 删除特定参数
   */
  removeParams: (skillId: string): void => {
    if (typeof window !== 'undefined') {
      const allParams = executionStateApi.getAllParams();
      const filtered = allParams.filter(p => p.skillId !== skillId);
      localStorage.setItem(EXECUTION_PARAMS_KEY, JSON.stringify(filtered));
    }
  },

  /**
   * 清除所有参数
   */
  clearAll: (): void => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(EXECUTION_PARAMS_KEY);
    }
  },
};
