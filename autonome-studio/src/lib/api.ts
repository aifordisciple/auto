const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const url = `${BASE_URL}/api${endpoint}`;
  
  const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null;
  
  const headers: any = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  if (options.headers) {
    Object.assign(headers, options.headers);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401) {
      console.error("Authentication required");
      if (typeof window !== 'undefined') window.location.href = "/login";
    }
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.message || `API request failed: ${response.status}`);
  }

  return response.json();
}

export { BASE_URL };
