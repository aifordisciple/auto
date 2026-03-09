// 🛡️ 智能动态获取后端的 IP 地址
// 如果在浏览器环境，自动获取当前访问的 IP (如 113.44.66.210)，拼接上后端 8000 端口
// 如果在服务端渲染环境，则默认兜底为 localhost
export const BASE_URL = typeof window !== 'undefined'
  ? `http://${window.location.hostname}:8000`
  : 'http://localhost:8000';

export async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null;
  const headers: any = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  // 🛡️ 防弹级 FormData 检测 (兼容各种复杂的 SSR / 浏览器环境)
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  if (!isFormData && options.body) {
    headers['Content-Type'] = 'application/json';
  }

  if (options.headers) {
    Object.assign(headers, options.headers);
  }

  // 🛡️ 防弹级 URL 拼接：终极方案
  const cleanBase = BASE_URL.replace(/\/$/, '');
  let cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

  // 核心修复：如果 endpoint 已经以 /api 开头，我们就不再重复添加 /api
  // 否则，我们在前面加上 /api
  const url = cleanEndpoint.startsWith('/api')
    ? `${cleanBase}${cleanEndpoint}`
    : `${cleanBase}/api${cleanEndpoint}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      if (response.status === 401 && typeof window !== 'undefined') {
        localStorage.removeItem('autonome_access_token');
        window.location.href = '/login';
      }
      const errorData = await response.json().catch(() => ({}));
      // ✨ 更清晰的报错信息
      throw new Error(errorData.detail || errorData.message || `后端拒绝了请求 (状态码: ${response.status})`);
    }

    return await response.json();
  } catch (error: any) {
    // 🛡️ 专门捕获 Network Error / CORS 错误
    if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
      console.error("🌐 网络或 CORS 跨域错误。尝试访问的 URL:", url);
      throw new Error(`网络连接失败，请检查后端 ${cleanBase} 是否运行正常，或者 URL 是否正确。`);
    }
    throw error;
  }
}

// ==========================================
// 文件夹管理 API
// ==========================================

export interface CreateFolderRequest {
  parent_path: string;
  folder_name: string;
}

export interface MoveFileRequest {
  source_path: string;
  destination_path: string;
  overwrite?: boolean;
}

export interface FolderNode {
  name: string;
  path: string;
  writable: boolean;
  children: FolderNode[];
}

/**
 * 创建新文件夹
 */
export async function createFolder(projectId: string, request: CreateFolderRequest) {
  return fetchAPI(`/api/projects/${projectId}/folders`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * 移动文件或文件夹
 */
export async function moveFile(projectId: string, request: MoveFileRequest) {
  return fetchAPI(`/api/projects/${projectId}/files/move`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * 获取文件夹树（用于目标选择器）
 */
export async function getFolderTree(projectId: string): Promise<{ status: string; data: FolderNode[] }> {
  return fetchAPI(`/api/projects/${projectId}/folders`);
}
