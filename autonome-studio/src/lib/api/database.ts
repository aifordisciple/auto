// ==========================================
// 分析数据库管理 API (Database API)
// ==========================================

import { fetchAPI } from '../api';
import { cachedFetch, invalidateCache } from '../apiCache';

export interface AnalysisDatabase {
  id: number;
  db_id: string;
  name: string;
  description: string | null;
  db_type: string;
  species: string | null;
  version: string | null;
  path: string;
  file_format: string | null;
  size_bytes: number | null;
  is_active: boolean;
  usage_count: number;
  last_used_at: string | null;
  source_url: string | null;
  license: string | null;
  tags: string[];
  custom_fields: Record<string, any>;
  owner_id: number;
  visibility: string;
  shared_with: number[];
  created_at: string;
  updated_at: string;
}

export const databaseApi = {
  /**
   * 获取数据库列表
   * 使用缓存优化，缓存 10 分钟
   */
  listDatabases: async (dbType?: string, search?: string, options?: { forceRefresh?: boolean }): Promise<AnalysisDatabase[]> => {
    const params: Record<string, string> = {};
    if (dbType) params.db_type = dbType;
    if (search) params.search = search;

    return cachedFetch<AnalysisDatabase[]>(
      'databases:list',
      () => {
        const query = Object.keys(params).length > 0
          ? `?${new URLSearchParams(params).toString()}`
          : '';
        return fetchAPI(`/api/databases/${query}`);
      },
      Object.keys(params).length > 0 ? params : undefined,
      options
    );
  },

  /**
   * 使数据库列表缓存失效
   */
  invalidateDatabasesCache: () => {
    invalidateCache('databases:list');
  },

  /**
   * 获取数据库类型列表
   */
  listTypes: async (): Promise<{
    status: string;
    data: { type: string; name: string; description: string; count: number }[];
  }> => {
    return fetchAPI('/api/databases/types/list');
  },

  /**
   * 获取物种列表
   */
  listSpecies: async (): Promise<{ status: string; data: { species: string; count: number }[] }> => {
    return fetchAPI('/api/databases/species/list');
  },

  /**
   * 获取单个数据库详情
   */
  getDatabase: async (dbId: string): Promise<AnalysisDatabase> => {
    return fetchAPI(`/api/databases/${dbId}`);
  },

  /**
   * 创建数据库
   */
  createDatabase: async (data: Partial<AnalysisDatabase>): Promise<AnalysisDatabase> => {
    return fetchAPI('/api/databases/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * 更新数据库
   */
  updateDatabase: async (dbId: string, data: Partial<AnalysisDatabase>): Promise<AnalysisDatabase> => {
    return fetchAPI(`/api/databases/${dbId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /**
   * 删除数据库
   */
  deleteDatabase: async (dbId: string): Promise<{ status: string; message: string }> => {
    return fetchAPI(`/api/databases/${dbId}`, {
      method: 'DELETE',
    });
  },

  /**
   * 切换数据库启用/禁用状态
   */
  toggleActive: async (dbId: string): Promise<{ status: string; is_active: boolean }> => {
    return fetchAPI(`/api/databases/${dbId}/toggle-active`, {
      method: 'POST',
    });
  },

  /**
   * 共享数据库
   */
  shareDatabase: async (dbId: string, userIds: number[]): Promise<{ status: string; shared_with: number[] }> => {
    return fetchAPI(`/api/databases/${dbId}/share`, {
      method: 'POST',
      body: JSON.stringify({ user_ids: userIds }),
    });
  },

  /**
   * 增加使用次数
   */
  incrementUsage: async (dbId: string, increment: number = 1): Promise<{ status: string; usage_count: number }> => {
    return fetchAPI(`/api/databases/${dbId}/increment-usage`, {
      method: 'POST',
      body: JSON.stringify({ increment }),
    });
  },

  /**
   * 验证数据库路径
   */
  validatePath: async (dbId: string): Promise<{
    status: string;
    path: string;
    exists: boolean;
    is_directory: boolean;
  }> => {
    return fetchAPI(`/api/databases/${dbId}/validate`);
  },
};
