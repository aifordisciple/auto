const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const url = `${BASE_URL}${endpoint}`;
  
  // ✨ 从本地存储获取 token (这里假设你登录后把 token 存为 'autonome_access_token')
  const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null;
  
  const defaultHeaders: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}), // ✨ 动态植入 Token
  };

  const response = await fetch(url, {
    ...options,
    headers: { ...defaultHeaders, ...options.headers },
  });

  if (!response.ok) {
    if (response.status === 401) {
      // Token 过期或未登录，可以在这里触发全局事件跳回登录页
      console.error("Authentication required");
      if (typeof window !== 'undefined') window.location.href = "/login"; // 强制跳转登录
    }
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `API request failed: ${response.status}`);
  }

  return response.json();
}

// 导出 BASE_URL 供 SSE 和文件上传表单使用（因为它们往往不能直接使用普通的 fetch）
export { BASE_URL };
