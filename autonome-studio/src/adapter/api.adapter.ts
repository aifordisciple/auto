/**
 * API 适配器模块
 *
 * 提供统一的 API 调用接口，自动适配 Web 和桌面端
 */

import { Platform, getTauriInvoke } from './platform';

/**
 * API 请求选项
 */
export interface ApiRequestOptions extends RequestInit {
  /** 是否跳过认证 */
  skipAuth?: boolean;
  /** 请求超时时间（毫秒） */
  timeout?: number;
}

/**
 * API 响应错误
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * 获取存储在本地的 JWT token
 */
export function getToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('autonome_access_token');
  }
  return null;
}

/**
 * 设置 JWT token
 */
export function setToken(token: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('autonome_access_token', token);
  }
}

/**
 * 移除 JWT token
 */
export function removeToken(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('autonome_access_token');
  }
}

/**
 * 获取后端 API 基础 URL
 */
export function getBaseUrl(): string {
  if (Platform.isDesktop) {
    // 桌面端：从配置或环境变量获取
    // 默认连接云端后端
    return process.env.NEXT_PUBLIC_API_URL || 'https://api.autonome.io';
  }

  // Web 端：使用当前页面的 hostname
  if (typeof window !== 'undefined') {
    return `http://${window.location.hostname}:8000`;
  }

  return 'http://localhost:8000';
}

/**
 * 统一 API 请求函数
 *
 * 自动适配 Web 和桌面端：
 * - Web 端：使用 fetch
 * - 桌面端：使用 Tauri HTTP 客户端
 */
export async function fetchAPI<T = unknown>(
  endpoint: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const { skipAuth = false, timeout = 30000, ...fetchOptions } = options;
  const token = getToken();
  const baseUrl = getBaseUrl();

  // 构建请求头
  const headers: Record<string, string> = {};

  if (!skipAuth && token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // 检测是否是 FormData
  const isFormData =
    typeof FormData !== 'undefined' && fetchOptions.body instanceof FormData;
  if (!isFormData && fetchOptions.body) {
    headers['Content-Type'] = 'application/json';
  }

  // 合并请求头
  if (fetchOptions.headers) {
    Object.assign(headers, fetchOptions.headers as Record<string, string>);
  }

  // 构建 URL
  const cleanBase = baseUrl.replace(/\/$/, '');
  let cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const url = cleanEndpoint.startsWith('/api')
    ? `${cleanBase}${cleanEndpoint}`
    : `${cleanBase}/api${cleanEndpoint}`;

  // 桌面端使用 Tauri HTTP 客户端
  if (Platform.isDesktop) {
    const invoke = getTauriInvoke();
    if (invoke) {
      try {
        return await invoke<T>('fetch_api', {
          endpoint: url,
          options: {
            method: fetchOptions.method || 'GET',
            headers,
            body: fetchOptions.body,
            timeout,
          },
        });
      } catch (error) {
        throw new ApiError(
          error instanceof Error ? error.message : 'Request failed',
          500
        );
      }
    }
  }

  // Web 端使用 fetch
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const response = await fetch(url, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      // 处理 401 未授权
      if (response.status === 401 && typeof window !== 'undefined') {
        removeToken();
        window.location.href = '/login';
      }

      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || errorData.message || `请求失败 (${response.status})`,
        response.status,
        errorData
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) throw error;

    // 网络错误
    if (error instanceof Error && error.name === 'AbortError') {
      throw new ApiError('请求超时', 408);
    }

    throw new ApiError(
      error instanceof Error ? error.message : '网络请求失败',
      0
    );
  }
}

/**
 * API 客户端对象
 */
export const api = {
  fetch: fetchAPI,
  get: <T = unknown>(endpoint: string, options?: ApiRequestOptions) =>
    fetchAPI<T>(endpoint, { ...options, method: 'GET' }),
  post: <T = unknown>(endpoint: string, body?: unknown, options?: ApiRequestOptions) =>
    fetchAPI<T>(endpoint, {
      ...options,
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),
  put: <T = unknown>(endpoint: string, body?: unknown, options?: ApiRequestOptions) =>
    fetchAPI<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: <T = unknown>(endpoint: string, body?: unknown, options?: ApiRequestOptions) =>
    fetchAPI<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),
  delete: <T = unknown>(endpoint: string, options?: ApiRequestOptions) =>
    fetchAPI<T>(endpoint, { ...options, method: 'DELETE' }),
};

// 重新导出原有的 BASE_URL（向后兼容）
export const BASE_URL = typeof window !== 'undefined'
  ? `http://${window.location.hostname}:8000`
  : 'http://localhost:8000';