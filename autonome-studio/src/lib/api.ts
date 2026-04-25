/**
 * API 客户端模块
 *
 * 设计日期: 2026-03-22
 * 更新日期: 2026-04-21（阶段2：Cookie 模式 + 401 无感刷新）
 *
 * 功能：
 * - 统一 fetchAPI 封装，自动注入认证信息
 * - Cookie 模式：credentials: 'include' 自动携带 Cookie
 * - 401 拦截器：自动 Refresh Token 刷新，对调用方透明
 * - 并发刷新锁：防止多个 401 同时触发多个 refresh 请求
 * - SSE/WebSocket 场景：仍支持手动 Token 注入
 */

import { useAuthStore } from '@/store/useAuthStore';

// ==========================================
// 配置
// ==========================================

// BASE_URL: 后端服务器地址（不含 /api 前缀）
// 智能动态获取：浏览器环境取当前 hostname + :8000，SSR 环境兜底 localhost
export const BASE_URL = process.env.NEXT_PUBLIC_API_URL
  || (typeof window !== 'undefined' ? `http://${window.location.hostname}:8000` : 'http://localhost:8000');

// API_BASE_URL: 含 /api 前缀的完整 API 基地址
const API_BASE_URL = `${BASE_URL.replace(/\/$/, '')}/api`;

/**
 * 规范化 API 端点路径
 *
 * 根本原因：API_BASE_URL 已包含 /api 前缀，
 * 但部分调用方传入 '/api/xxx'（旧代码），部分传入 '/xxx'（新代码）。
 * 此函数统一剥离多余的 /api 前缀，避免产生 /api/api/xxx 的双重前缀问题。
 */
function normalizeEndpoint(endpoint: string): string {
  // 剥离开头的 /api 前缀（API_BASE_URL 已包含）
  if (endpoint.startsWith('/api/')) {
    return endpoint.slice(4); // '/api/projects' → '/projects'
  }
  if (endpoint.startsWith('/api')) {
    return endpoint.slice(4); // '/api' → ''
  }
  return endpoint;
}

// ==========================================
// 并发刷新锁
// ==========================================

let isRefreshing = false;
let refreshPromise: Promise<boolean> | null = null;

/**
 * 执行 Refresh Token 刷新（带并发锁）
 *
 * 多个请求同时收到 401 时，只触发一次 refresh，
 * 其他请求等待同一个 Promise 结果
 */
async function refreshAccessToken(): Promise<boolean> {
  // 如果已经在刷新中，复用同一个 Promise
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include', // 自动携带 refresh_token Cookie
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        // Refresh 失败，直接清除本地状态（不调后端 logout，避免死循环）
        const { clearAll } = useAuthStore.getState();
        clearAll();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
        return false;
      }

      const data = await response.json();
      // 新的 AT 已通过 Cookie 设置，无需手动管理
      // 但 SSE 等场景需要手动 Token，存储到 store
      if (data.access_token) {
        const { setToken } = useAuthStore.getState();
        setToken(data.access_token);
      }

      return true;
    } catch {
      // 网络错误等，直接清除本地状态（不调后端 logout，避免死循环）
      const { clearAll } = useAuthStore.getState();
      clearAll();
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
      return false;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// ==========================================
// 核心 fetchAPI 函数
// ==========================================

// ==========================================
// 401 安全端点：这些端点的 401 不应触发刷新
// 避免刷新失败→logout→401→刷新 的死循环
// ==========================================

const AUTH_ENDPOINTS_SKIP_REFRESH = ['/auth/logout', '/auth/refresh'];

function shouldSkipRefresh(endpoint: string): boolean {
  const normalized = normalizeEndpoint(endpoint);
  return AUTH_ENDPOINTS_SKIP_REFRESH.some(ep => normalized === ep);
}

export async function fetchAPI(
  endpoint: string,
  options: RequestInit & { skipRefresh?: boolean } = {}
): Promise<any> {
  const { skipRefresh, ...fetchOptionsBase } = options;
  const url = `${API_BASE_URL}${normalizeEndpoint(endpoint)}`;

  // 构建请求头
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(fetchOptionsBase.headers as Record<string, string> || {}),
  };

  // 对于 SSE/WebSocket 等需要手动注入 Token 的场景
  // 从 store 读取 token（仅当 Cookie 模式不可用时）
  const { token } = useAuthStore.getState();
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // 构建请求选项
  const fetchOptions: RequestInit = {
    ...fetchOptionsBase,
    headers,
    // Cookie 模式：自动携带 httpOnly Cookie
    credentials: 'include',
  };

  // 发送请求
  let response = await fetch(url, fetchOptions);

  // ==========================================
  // 401 拦截器：自动刷新 Token
  // 跳过条件：显式 skipRefresh 或认证端点（logout/refresh）
  // ==========================================
  const shouldRefresh = !skipRefresh && !shouldSkipRefresh(endpoint);
  if (response.status === 401 && shouldRefresh) {
    // 尝试刷新 Token
    const refreshed = await refreshAccessToken();

    if (refreshed) {
      // 刷新成功，重试原请求
      // 更新 Authorization header（如果使用手动 Token 模式）
      const { token: newToken } = useAuthStore.getState();
      if (newToken) {
        headers['Authorization'] = `Bearer ${newToken}`;
      }

      response = await fetch(url, {
        ...fetchOptions,
        headers,
      });

      // 重试后仍然 401，说明真的没权限
      if (response.status === 401) {
        const { clearAll } = useAuthStore.getState();
        clearAll();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
        throw new Error('认证失败，请重新登录');
      }
    } else {
      throw new Error('认证已过期，请重新登录');
    }
  }

  // ==========================================
  // 响应处理
  // ==========================================

  if (!response.ok) {
    // 尝试解析错误信息
    let errorDetail = `请求失败 (${response.status})`;
    try {
      const errorData = await response.json();
      errorDetail = errorData.detail || errorData.message || errorDetail;
    } catch {
      // JSON 解析失败，使用默认错误信息
    }
    throw new Error(errorDetail);
  }

  // 204 No Content
  if (response.status === 204) {
    return null;
  }

  return response.json();
}

// ==========================================
// Token 工具（向后兼容）
// ==========================================

/**
 * 获取当前 Token（供 SSE/WebSocket 等场景使用）
 * Cookie 模式下，普通请求无需手动管理 Token
 */
export function getToken(): string | null {
  const { token } = useAuthStore.getState();
  return token;
}

/**
 * 移除 Token（向后兼容，Cookie 模式下调用 logout 端点）
 */
export function removeToken(): void {
  const { setToken } = useAuthStore.getState();
  setToken(null);
}

// ==========================================
// SSE 流式请求（用于聊天等场景）
// ==========================================

export function createSSEUrl(endpoint: string): string {
  /**
   * 构建 SSE 连接 URL
   *
   * SSE 无法自定义 header，Token 通过 query parameter 传递
   * 后端需支持 ?token=xxx 参数验证
   */
  const { token } = useAuthStore.getState();
  const url = `${API_BASE_URL}${normalizeEndpoint(endpoint)}`;
  if (token) {
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}token=${encodeURIComponent(token)}`;
  }
  return url;
}

// ==========================================
// 文件上传
// ==========================================

export async function uploadFile(
  endpoint: string,
  file: File,
  additionalData?: Record<string, string>
): Promise<any> {
  /**
   * 文件上传（multipart/form-data）
   * 包含 401 拦截器：与 fetchAPI 一致的静默刷新逻辑
   */
  const formData = new FormData();
  formData.append('file', file);

  if (additionalData) {
    for (const [key, value] of Object.entries(additionalData)) {
      formData.append(key, value);
    }
  }

  const { token } = useAuthStore.getState();
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = `${API_BASE_URL}${normalizeEndpoint(endpoint)}`;
  const fetchOptions: RequestInit = {
    method: 'POST',
    headers,
    body: formData,
    credentials: 'include',
  };

  let response = await fetch(url, fetchOptions);

  // ==========================================
  // 401 拦截器：与 fetchAPI 一致的静默刷新
  // ==========================================
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();

    if (refreshed) {
      // 刷新成功，重试上传请求
      const { token: newToken } = useAuthStore.getState();
      if (newToken) {
        headers['Authorization'] = `Bearer ${newToken}`;
      }
      response = await fetch(url, {
        ...fetchOptions,
        headers,
      });

      // 重试后仍然 401，说明真的没权限
      if (response.status === 401) {
        const { clearAll } = useAuthStore.getState();
        clearAll();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
        throw new Error('认证失败，请重新登录');
      }
    } else {
      throw new Error('认证已过期，请重新登录');
    }
  }

  if (!response.ok) {
    let errorDetail = `上传失败 (${response.status})`;
    try {
      const errorData = await response.json();
      errorDetail = errorData.detail || errorData.message || errorDetail;
    } catch {}
    throw new Error(errorDetail);
  }

  return response.json();
}

// ==========================================
// 从领域模块重新导出所有 API
// 确保现有 import { ... } from '@/lib/api' 继续工作
// ==========================================

export {
  createFolder,
  moveFile,
  getFolderTree,
  type CreateFolderRequest,
  type MoveFileRequest,
  type FolderNode,
} from './api/folder';

export {
  skillForgeApi,
  type ExecutorType,
  type CraftRequest,
  type CraftResponse,
  type BundleResponse,
  type SkillAsset,
} from './api/skillForge';

export {
  skillDraftApi,
  type PendingSkillDraft,
  type DraftStats,
} from './api/skillDraft';

export { adminApi } from './api/admin';

export {
  templateApi,
  type SkillTemplate,
  type InstantiateRequest,
  type InstantiateResult,
} from './api/template';

export {
  forgeSessionApi,
  type ForgeSessionCreateRequest,
  type ForgeSessionResponse,
  type ForgeSessionDetail,
  type ForgeMessageData,
  type ForgeChatRequest,
  type SkillDraftUpdateRequest,
  type ForgeSessionListItem,
  type SkillDraft,
} from './api/forgeSession';

export {
  genomeApi,
  type GenomeAsset,
} from './api/genome';

export {
  databaseApi,
  type AnalysisDatabase,
} from './api/database';

export {
  errorDiagnosticApi,
  type DiagnoseRequest,
  type FixSuggestion,
  type ErrorDiagnosis,
  type DiagnoseResponse,
  type FixResponse,
} from './api/errorDiagnostic';

export {
  executionStateApi,
  type ExecutionParams,
} from './api/executionState';

export {
  pinnedSkillsApi,
  type PinnedSkill,
} from './api/pinnedSkills';

export {
  quickExecuteApi,
  type QuickMatchRequest,
  type QuickMatchResponse,
  type MatchMode,
} from './api/quickExecute';

export {
  feedbackApi,
  type FeedbackEventType,
  type RecordBehaviorRequest,
} from './api/feedback';

export {
  chatQueueApi,
  type ChatQueueItem,
  type QueueItemStatus,
} from './api/chatQueue';

export {
  rbacApi,
  type RoleOut,
  type PermissionOut,
  type AuditLogOut,
  type UserRolesOut,
} from './api/rbac';
