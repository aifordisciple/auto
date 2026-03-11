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


// ==========================================
// SKILL Forge 技能工厂 API
// ==========================================

export type ExecutorType = 'Python_env' | 'R_env' | 'Logical_Blueprint' | 'Python_Package';

export interface CraftRequest {
  raw_material: string;
  executor_type?: ExecutorType;
  generate_full_bundle?: boolean;
  skill_name_hint?: string;
  category?: string;
  subcategory?: string;
  tags?: string[];
}

export interface CraftResponse {
  name: string;
  description: string;
  executor_type: ExecutorType;
  parameters_schema: Record<string, any>;
  expert_knowledge: string;
  script_code?: string;
  nextflow_code?: string;
  dependencies: string[];
  validation_warning?: string;
  validation_passed?: boolean;
}

export interface BundleResponse {
  status: string;
  skill_id: string;
  name: string;
  bundle_path: string;
  files_created: string[];
  executor_type: ExecutorType;
  message: string;
}

export interface SkillAsset {
  id: number;
  skill_id: string;
  name: string;
  description: string | null;
  version: string;
  executor_type: string;
  parameters_schema: Record<string, any>;
  expert_knowledge: string | null;
  script_code: string | null;
  dependencies: string[];
  status: string;
  reject_reason: string | null;
  owner_id: number;
  created_at: string;
  updated_at: string;
}

export const skillForgeApi = {
  /**
   * 获取当前用户可用的所有技能（已包含权限过滤）
   */
  listSkills: async (): Promise<SkillAsset[]> => {
    const response = await fetchAPI('/api/skills/');
    return response;
  },

  /**
   * 将非结构化素材发送给大脑进行锻造
   */
  craftFromMaterial: async (request: CraftRequest): Promise<{
    data: CraftResponse;
    bundle_path?: string;
    files_created?: string[];
  }> => {
    const response = await fetchAPI('/api/skills/craft_from_material', {
      method: 'POST',
      body: JSON.stringify({
        raw_material: request.raw_material,
        executor_type: request.executor_type || 'Python_env',
        generate_full_bundle: request.generate_full_bundle || false,
        skill_name_hint: request.skill_name_hint,
        category: request.category,
        subcategory: request.subcategory,
        tags: request.tags || []
      }),
    });
    return response;
  },

  /**
   * 直接创建完整文件系统技能包
   */
  createSkillBundle: async (request: CraftRequest): Promise<BundleResponse> => {
    const response = await fetchAPI('/api/skills/bundle', {
      method: 'POST',
      body: JSON.stringify({
        raw_material: request.raw_material,
        executor_type: request.executor_type || 'Python_env',
        skill_name_hint: request.skill_name_hint,
        category: request.category,
        subcategory: request.subcategory,
        tags: request.tags || []
      }),
    });
    return response;
  },

  /**
   * 将生成的代码提交到沙箱进行自动化测试
   */
  /**
   * 测试草稿技能（增强版）
   * 支持自动生成测试数据、多场景测试、自动修复
   */
  testDraftSkill: async (params: {
    scriptCode: string;
    testInstruction?: string;
    parametersSchema?: Record<string, any>;
    autoGenerateData?: boolean;
    maxTestRounds?: number;
  }): Promise<any> => {
    const response = await fetchAPI('/api/skills/test_draft', {
      method: 'POST',
      body: JSON.stringify({
        script_code: params.scriptCode,
        test_instruction: params.testInstruction || '',
        parameters_schema: params.parametersSchema,
        auto_generate_data: params.autoGenerateData !== false,
        max_test_rounds: params.maxTestRounds || 3
      }),
    });
    return response.data;
  },

  /**
   * 测试草稿技能（SSE 流式日志版本）
   * 实时返回测试进度，支持前端实时显示
   */
  testDraftSkillStream: async (
    params: {
      scriptCode: string;
      testInstruction?: string;
      parametersSchema?: Record<string, any>;
      autoGenerateData?: boolean;
      maxTestRounds?: number;
    },
    onLog: (message: string) => void,
    onStatus?: (status: string) => void,
    onResult?: (result: any) => void
  ): Promise<void> => {
    const token = localStorage.getItem('autonome_access_token');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${BASE_URL}/api/skills/test_draft_stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        script_code: params.scriptCode,
        test_instruction: params.testInstruction || '',
        parameters_schema: params.parametersSchema,
        auto_generate_data: params.autoGenerateData !== false,
        max_test_rounds: params.maxTestRounds || 3
      }),
    });

    if (!response.ok) {
      throw new Error(`测试请求失败: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('无法获取响应流');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));

              if (event.type === 'log' && event.message) {
                onLog(event.message);
              } else if (event.type === 'status' && onStatus) {
                onStatus(event.message);
              } else if (event.type === 'result' && onResult) {
                onResult(event.data);
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  /**
   * 保存为私有技能 (入库)
   */
  savePrivateSkill: async (skillData: Partial<SkillAsset>): Promise<SkillAsset> => {
    const response = await fetchAPI('/api/skills/', {
      method: 'POST',
      body: JSON.stringify(skillData),
    });
    return response;
  },

  /**
   * 获取单个技能详情
   */
  getSkill: async (skillId: string): Promise<any> => {
    const response = await fetchAPI(`/api/skills/${skillId}`);
    return response;
  },

  /**
   * 更新技能
   */
  updateSkill: async (skillId: string, skillData: Partial<SkillAsset>): Promise<SkillAsset> => {
    const response = await fetchAPI(`/api/skills/${skillId}`, {
      method: 'PUT',
      body: JSON.stringify(skillData),
    });
    return response;
  },

  /**
   * 删除技能
   */
  deleteSkill: async (skillId: string): Promise<any> => {
    const response = await fetchAPI(`/api/skills/${skillId}`, {
      method: 'DELETE',
    });
    return response;
  },

  /**
   * 提交给管理员审核
   */
  submitForReview: async (skillId: string): Promise<any> => {
    const response = await fetchAPI(`/api/skills/${skillId}/submit_review`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 获取技能目录（包含文件系统和数据库）
   */
  getCatalog: async (): Promise<any> => {
    const response = await fetchAPI('/api/skills/catalog');
    return response;
  }
};


// ==========================================
// Admin 管理员专区 API
// ==========================================

export const adminApi = {
  /**
   * 获取待审核的 SKILL 列表
   */
  getPendingSkills: async (): Promise<SkillAsset[]> => {
    const response = await fetchAPI('/api/admin/skills/pending');
    return response;
  },

  /**
   * 提交审核决策
   */
  reviewSkill: async (skillId: string, action: 'APPROVE' | 'REJECT', rejectReason: string = ""): Promise<any> => {
    const response = await fetchAPI(`/api/admin/skills/${skillId}/review`, {
      method: 'POST',
      body: JSON.stringify({ action, reject_reason: rejectReason }),
    });
    return response;
  }
};
