/**
 * API 缓存工具
 *
 * 功能：
 * 1. 内存缓存高频 API 响应
 * 2. 支持 TTL 自动过期
 * 3. 支持缓存失效和刷新
 * 4. 支持请求去重（防止重复请求）
 *
 * 使用场景：
 * - 技能列表（缓存 5 分钟）
 * - 基因组/数据库列表（缓存 10 分钟）
 * - 用户偏好（缓存 30 分钟）
 */

// ==========================================
// 类型定义
// ==========================================

interface CacheEntry<T> {
  data: T;
  expiresAt: number;
  timestamp: number;
}

interface CacheConfig {
  ttl: number; // 缓存时间（毫秒）
  staleWhileRevalidate?: boolean; // 是否允许过期数据后台刷新
}

// ==========================================
// 默认缓存配置
// ==========================================

export const DEFAULT_CACHE_CONFIGS: Record<string, CacheConfig> = {
  // 技能列表 - 5 分钟
  'skills:list': { ttl: 5 * 60 * 1000 },
  // 技能详情 - 10 分钟
  'skills:detail': { ttl: 10 * 60 * 1000 },
  // 基因组列表 - 10 分钟
  'genomes:list': { ttl: 10 * 60 * 1000 },
  // 数据库列表 - 10 分钟
  'databases:list': { ttl: 10 * 60 * 1000 },
  // 用户偏好 - 30 分钟
  'user:preferences': { ttl: 30 * 60 * 1000 },
  // 推荐结果 - 3 分钟
  'recommend:result': { ttl: 3 * 60 * 1000 },
  // 默认缓存 - 5 分钟
  'default': { ttl: 5 * 60 * 1000 },
};

// ==========================================
// 缓存存储
// ==========================================

class APICache {
  private cache: Map<string, CacheEntry<unknown>> = new Map();
  private pendingRequests: Map<string, Promise<unknown>> = new Map();
  private configs: Record<string, CacheConfig>;

  constructor(configs: Record<string, CacheConfig> = DEFAULT_CACHE_CONFIGS) {
    this.configs = configs;
  }

  /**
   * 生成缓存键
   */
  private generateKey(type: string, params?: Record<string, unknown>): string {
    if (!params) return type;
    const sortedParams = Object.keys(params)
      .sort()
      .map((key) => `${key}=${JSON.stringify(params[key])}`)
      .join('&');
    return `${type}?${sortedParams}`;
  }

  /**
   * 获取缓存配置
   */
  private getConfig(type: string): CacheConfig {
    return this.configs[type] || this.configs['default'];
  }

  /**
   * 检查缓存是否有效
   */
  private isValid<T>(entry: CacheEntry<T> | undefined): boolean {
    if (!entry) return false;
    return Date.now() < entry.expiresAt;
  }

  /**
   * 获取缓存
   */
  get<T>(type: string, params?: Record<string, unknown>): T | null {
    const key = this.generateKey(type, params);
    const entry = this.cache.get(key) as CacheEntry<T> | undefined;

    if (entry && this.isValid(entry)) {
      return entry.data;
    }

    return null;
  }

  /**
   * 设置缓存
   */
  set<T>(type: string, data: T, params?: Record<string, unknown>, customTTL?: number): void {
    const key = this.generateKey(type, params);
    const config = this.getConfig(type);
    const ttl = customTTL || config.ttl;

    this.cache.set(key, {
      data,
      expiresAt: Date.now() + ttl,
      timestamp: Date.now(),
    });
  }

  /**
   * 删除缓存
   */
  delete(type: string, params?: Record<string, unknown>): boolean {
    const key = this.generateKey(type, params);
    return this.cache.delete(key);
  }

  /**
   * 按类型批量删除缓存
   */
  deleteByType(type: string): number {
    let deleted = 0;
    for (const key of this.cache.keys()) {
      if (key.startsWith(type)) {
        this.cache.delete(key);
        deleted++;
      }
    }
    console.log(`[APICache] 🗑️ 批量删除: ${type}, 共 ${deleted} 项`);
    return deleted;
  }

  /**
   * 清空所有缓存
   */
  clear(): void {
    this.cache.clear();
    console.log('[APICache] 🧹 缓存已清空');
  }

  /**
   * 获取缓存的请求（请求去重）
   * 如果相同的请求正在进行中，返回现有的 Promise
   */
  getPendingRequest<T>(type: string, params?: Record<string, unknown>): Promise<T> | null {
    const key = this.generateKey(type, params);
    return (this.pendingRequests.get(key) as Promise<T>) || null;
  }

  /**
   * 设置进行中的请求
   */
  setPendingRequest<T>(type: string, promise: Promise<T>, params?: Record<string, unknown>): void {
    const key = this.generateKey(type, params);
    this.pendingRequests.set(key, promise);

    // 请求完成后自动清理
    promise
      .finally(() => {
        this.pendingRequests.delete(key);
      })
      .catch(() => {
        // 忽略错误，已经处理
      });
  }

  /**
   * 带缓存的 API 调用
   * 自动处理缓存命中、请求去重、缓存更新
   */
  async fetchWithCache<T>(
    type: string,
    fetcher: () => Promise<T>,
    params?: Record<string, unknown>,
    options?: {
      forceRefresh?: boolean;
      customTTL?: number;
    }
  ): Promise<T> {
    const { forceRefresh = false, customTTL } = options || {};

    // 1. 检查缓存（如果非强制刷新）
    if (!forceRefresh) {
      const cached = this.get<T>(type, params);
      if (cached !== null) {
        return cached;
      }
    }

    // 2. 检查是否有进行中的相同请求（请求去重）
    const pendingRequest = this.getPendingRequest<T>(type, params);
    if (pendingRequest) {
      console.log(`[APICache] ⏳ 等待进行中的请求: ${type}`);
      return pendingRequest;
    }

    // 3. 发起请求
    const requestPromise = fetcher();
    this.setPendingRequest(type, requestPromise, params);

    try {
      const data = await requestPromise;
      // 4. 缓存结果
      this.set(type, data, params, customTTL);
      return data;
    } catch (error) {
      console.error(`[APICache] ❌ 请求失败: ${type}`, error);
      throw error;
    }
  }

  /**
   * 获取缓存统计信息
   */
  getStats(): {
    size: number;
    pendingRequests: number;
    entries: Array<{ key: string; age: number; ttl: number }>;
  } {
    const entries = Array.from(this.cache.entries()).map(([key, entry]) => ({
      key,
      age: Date.now() - entry.timestamp,
      ttl: entry.expiresAt - Date.now(),
    }));

    return {
      size: this.cache.size,
      pendingRequests: this.pendingRequests.size,
      entries,
    };
  }
}

// ==========================================
// 全局单例
// ==========================================

let globalCache: APICache | null = null;

export function getAPICache(): APICache {
  if (!globalCache) {
    globalCache = new APICache();
  }
  return globalCache;
}

// ==========================================
// 便捷函数
// ==========================================

/**
 * 带缓存的 API 调用
 */
export async function cachedFetch<T>(
  type: string,
  fetcher: () => Promise<T>,
  params?: Record<string, unknown>,
  options?: { forceRefresh?: boolean; customTTL?: number }
): Promise<T> {
  return getAPICache().fetchWithCache(type, fetcher, params, options);
}

/**
 * 使缓存失效
 */
export function invalidateCache(type: string, params?: Record<string, unknown>): void {
  if (params) {
    getAPICache().delete(type, params);
  } else {
    getAPICache().deleteByType(type);
  }
}

/**
 * 清空所有缓存
 */
export function clearAllCache(): void {
  getAPICache().clear();
}

// ==========================================
// React Hooks（可选，用于 React 组件）
// ==========================================

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * React Hook: 带缓存的 API 调用
 */
export function useCachedQuery<T>(
  type: string,
  fetcher: () => Promise<T>,
  options?: {
    enabled?: boolean;
    forceRefresh?: boolean;
    customTTL?: number;
  }
): {
  data: T | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
} {
  const { enabled = true, forceRefresh = false, customTTL } = options || {};
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const mountedRef = useRef(true);

  const fetchData = useCallback(async () => {
    if (!enabled) return;

    setIsLoading(true);
    setError(null);

    try {
      const result = await getAPICache().fetchWithCache<T>(
        type,
        fetcher,
        undefined,
        { forceRefresh, customTTL }
      );
      if (mountedRef.current) {
        setData(result);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err : new Error(String(err)));
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [type, enabled, forceRefresh, customTTL]);

  useEffect(() => {
    mountedRef.current = true;
    fetchData();

    return () => {
      mountedRef.current = false;
    };
  }, [fetchData]);

  return {
    data,
    isLoading,
    error,
    refetch: () => fetchData(),
  };
}