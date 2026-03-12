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
   * 从压缩包创建技能
   * 支持 .zip, .tar.gz, .tgz 格式
   */
  craftFromBundle: async (params: {
    file: File;
    executorType?: ExecutorType;
    skillNameHint?: string;
    generateFullBundle?: boolean;
    category?: string;
    tags?: string[];
  }): Promise<{
    data: CraftResponse;
    bundle_path?: string;
    files_created?: string[];
    parsed_files?: Array<{
      path: string;
      type: string;
      language: string | null;
      size: number;
      preview: string;
    }>;
    file_stats?: Record<string, number>;
    raw_material_length?: number;
  }> => {
    const formData = new FormData();
    formData.append('file', params.file);
    formData.append('executor_type', params.executorType || 'Logical_Blueprint');
    formData.append('generate_full_bundle', String(params.generateFullBundle !== false));
    if (params.skillNameHint) {
      formData.append('skill_name_hint', params.skillNameHint);
    }
    if (params.category) {
      formData.append('category', params.category);
    }
    formData.append('tags', JSON.stringify(params.tags || []));

    const response = await fetchAPI('/api/skills/craft_from_bundle', {
      method: 'POST',
      body: formData,
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
    executorType?: string;
  }): Promise<any> => {
    const response = await fetchAPI('/api/skills/test_draft', {
      method: 'POST',
      body: JSON.stringify({
        script_code: params.scriptCode,
        test_instruction: params.testInstruction || '',
        parameters_schema: params.parametersSchema,
        auto_generate_data: params.autoGenerateData !== false,
        max_test_rounds: params.maxTestRounds || 3,
        executor_type: params.executorType || 'Python_env'
      }),
    });
    return response.data;
  },

  /**
   * 测试草稿技能（SSE 流式日志版本）
   * 实时返回测试进度，支持前端实时显示
   * 支持超时取消机制
   */
  testDraftSkillStream: async (
    params: {
      scriptCode: string;
      testInstruction?: string;
      parametersSchema?: Record<string, any>;
      autoGenerateData?: boolean;
      maxTestRounds?: number;
      executorType?: string;
    },
    onLog: (message: string) => void,
    onStatus?: (status: string) => void,
    onResult?: (result: any) => void,
    signal?: AbortSignal // 可选的外部取消信号
  ): Promise<void> => {
    const token = localStorage.getItem('autonome_access_token');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    // 创建 AbortController 用于超时控制
    const controller = new AbortController();
    const timeoutMs = 300000; // 5分钟总超时
    const inactivityTimeoutMs = 60000; // 60秒无活动超时

    const timeoutId = setTimeout(() => {
      controller.abort();
      onLog('⏱️ 测试超时（5分钟），已自动取消');
    }, timeoutMs);

    // 合并外部信号
    if (signal) {
      signal.addEventListener('abort', () => {
        controller.abort();
        onLog('⚠️ 测试已取消');
      });
    }

    try {
      const response = await fetch(`${BASE_URL}/api/skills/test_draft_stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          script_code: params.scriptCode,
          test_instruction: params.testInstruction || '',
          parameters_schema: params.parametersSchema,
          auto_generate_data: params.autoGenerateData !== false,
          max_test_rounds: params.maxTestRounds || 3,
          executor_type: params.executorType || 'Python_env'
        }),
        signal: controller.signal,
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
      let lastActivity = Date.now();

      // 无活动超时检测
      const inactivityCheck = setInterval(() => {
        if (Date.now() - lastActivity > inactivityTimeoutMs) {
          controller.abort();
          onLog('⏱️ 响应超时（60秒无活动），已自动取消');
        }
      }, 5000);

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          lastActivity = Date.now(); // 更新活动时间

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const event = JSON.parse(line.slice(6));

                // 心跳事件不触发回调
                if (event.type === 'heartbeat') continue;

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
        clearInterval(inactivityCheck);
        reader.releaseLock();
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        onLog('⚠️ 测试已取消');
      } else {
        throw error;
      }
    } finally {
      clearTimeout(timeoutId);
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
  },

  /**
   * 获取我的技能列表
   */
  listMySkills: async (status?: string): Promise<SkillAsset[]> => {
    const params = status ? `?status=${status}` : '';
    const response = await fetchAPI(`/api/skills/my${params}`);
    return response;
  },

  /**
   * 获取技能版本历史
   */
  getVersions: async (skillId: string): Promise<{ status: string; total: number; data: any[] }> => {
    const response = await fetchAPI(`/api/skills/${skillId}/versions`);
    return response;
  },

  /**
   * 创建新版本
   */
  createVersion: async (skillId: string, version: string, changeLog?: string): Promise<any> => {
    const params = new URLSearchParams({ version });
    if (changeLog) params.append('change_log', changeLog);
    const response = await fetchAPI(`/api/skills/${skillId}/versions?${params.toString()}`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 回滚到指定版本
   */
  rollbackVersion: async (skillId: string, versionId: number): Promise<any> => {
    const response = await fetchAPI(`/api/skills/${skillId}/rollback/${versionId}`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 获取技能使用统计
   */
  getStats: async (skillId: string): Promise<any> => {
    const response = await fetchAPI(`/api/skills/${skillId}/stats`);
    return response;
  },

  /**
   * 获取技能执行历史
   */
  getExecutionHistory: async (skillId: string, limit: number = 20): Promise<any> => {
    const response = await fetchAPI(`/api/skills/${skillId}/history?limit=${limit}`);
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


// ==========================================
// SKILL Templates 模板 API
// ==========================================

export interface SkillTemplate {
  id: number;
  template_id: string;
  name: string;
  description: string | null;
  template_type: 'Logical_Blueprint' | 'Python_env' | 'R_env' | 'Nextflow';
  script_template: string | null;
  parameters_schema: Record<string, any>;
  expert_knowledge: string | null;
  category: string;
  category_name: string;
  subcategory: string | null;
  subcategory_name: string | null;
  tags: string[];
  source_skill_id: string | null;
  is_official: boolean;
  usage_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface InstantiateRequest {
  skill_name?: string;
  customizations?: Record<string, any>;
}

export interface InstantiateResult {
  skill_id: string;
  name: string;
  description: string;
  executor_type: string;
  script_code: string | null;
  parameters_schema: Record<string, any>;
  expert_knowledge: string | null;
  dependencies: string[];
}

export const templateApi = {
  /**
   * 获取所有模板
   */
  listTemplates: async (): Promise<SkillTemplate[]> => {
    const response = await fetchAPI('/api/templates/');
    return response;
  },

  /**
   * 获取单个模板详情
   */
  getTemplate: async (templateId: string): Promise<{ status: string; data: SkillTemplate }> => {
    const response = await fetchAPI(`/api/templates/${templateId}`);
    return response;
  },

  /**
   * 从模板实例化技能
   */
  instantiateTemplate: async (templateId: string, request: InstantiateRequest): Promise<InstantiateResult> => {
    const response = await fetchAPI(`/api/templates/${templateId}/instantiate`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
    return response;
  },

  /**
   * 从现有技能提取模板
   */
  extractTemplate: async (skillId: string, templateName: string, templateId?: string, saveToDb: boolean = false): Promise<any> => {
    const params = new URLSearchParams({
      skill_id: skillId,
      template_name: templateName,
      save_to_db: String(saveToDb)
    });
    if (templateId) {
      params.append('template_id', templateId);
    }
    const response = await fetchAPI(`/api/templates/extract?${params.toString()}`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 获取模板分类统计
   */
  getCategories: async (): Promise<{ status: string; data: any[] }> => {
    const response = await fetchAPI('/api/templates/categories/list');
    return response;
  }
};


// ==========================================
// 技能锻造会话 API
// ==========================================

export interface ForgeSessionCreateRequest {
  title?: string;
  executor_type?: ExecutorType;
}

export interface ForgeSessionResponse {
  session_id: string;
  title: string;
}

export interface ForgeSessionDetail {
  id: string;
  user_id: number;
  title: string;
  status: string;
  skill_draft: SkillDraft;
  skill_id?: string;
  executor_type: string;
  created_at: string;
  updated_at: string;
  messages: ForgeMessageData[];
}

export interface ForgeMessageData {
  id: number;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  attachments: string[];
  created_at: string;
}

export interface ForgeChatRequest {
  session_id?: string;
  message: string;
  attachments?: string[];
  executor_type?: ExecutorType;
}

export interface SkillDraftUpdateRequest {
  name?: string;
  description?: string;
  executor_type?: string;
  script_code?: string;
  nextflow_code?: string;
  parameters_schema?: Record<string, any>;
  expert_knowledge?: string;
  dependencies?: string[];
}

export interface ForgeSessionListItem {
  id: string;
  title: string;
  status: string;
  executor_type: string;
  created_at: string;
  updated_at: string;
  has_draft: boolean;
}

export const forgeSessionApi = {
  /**
   * 创建锻造会话
   */
  createSession: async (request: ForgeSessionCreateRequest): Promise<ForgeSessionResponse> => {
    const response = await fetchAPI('/api/skills/forge/session', {
      method: 'POST',
      body: JSON.stringify(request),
    });
    return response;
  },

  /**
   * 获取用户的锻造会话列表
   */
  listSessions: async (limit: number = 20, offset: number = 0): Promise<{ sessions: ForgeSessionListItem[] }> => {
    const response = await fetchAPI(`/api/skills/forge/sessions?limit=${limit}&offset=${offset}`);
    return response;
  },

  /**
   * 获取会话详情
   */
  getSession: async (sessionId: string): Promise<ForgeSessionDetail> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}`);
    return response;
  },

  /**
   * 删除会话
   */
  deleteSession: async (sessionId: string): Promise<{ status: string; message: string }> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}`, {
      method: 'DELETE',
    });
    return response;
  },

  /**
   * 手动更新技能草稿
   */
  updateDraft: async (sessionId: string, draft: SkillDraftUpdateRequest): Promise<{ status: string; skill_draft: SkillDraft }> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}/draft`, {
      method: 'PUT',
      body: JSON.stringify(draft),
    });
    return response;
  },

  /**
   * 确认保存技能
   */
  commitSkill: async (sessionId: string): Promise<{ status: string; skill_id: string; name: string }> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}/commit`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 保存并提交审核
   */
  submitSkill: async (sessionId: string): Promise<{ status: string; skill_id: string; name: string; status: string }> => {
    const response = await fetchAPI(`/api/skills/forge/session/${sessionId}/submit`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 流式对话锻造 (SSE)
   *
   * 使用方法:
   * const onMessage = (content: string) => { ... }
   * const onSkillUpdate = (draft: SkillDraft) => { ... }
   * const onError = (error: string) => { ... }
   * const onComplete = () => { ... }
   *
   * await forgeSessionApi.chatStream(sessionId, message, attachments, onMessage, onSkillUpdate, onError, onComplete, signal);
   */
  chatStream: async (
    sessionId: string,
    message: string,
    attachments: string[] = [],
    onMessage: (content: string) => void,
    onSkillUpdate: (draft: SkillDraft) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    signal?: AbortSignal
  ): Promise<void> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('autonome_access_token') : null;

    const response = await fetch(`${BASE_URL}/api/skills/forge/session/${sessionId}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
      },
      body: JSON.stringify({
        message,
        attachments,
        executor_type: 'Python_env'
      }),
      signal
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
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
          if (line.startsWith('event:')) {
            const eventType = line.substring(7).trim();
            continue;
          }

          if (line.startsWith('data:')) {
            const data = line.substring(5).trim();
            try {
              const parsed = JSON.parse(data);

              if (parsed.type === 'text') {
                onMessage(parsed.content);
              } else if (parsed.type === 'draft') {
                onSkillUpdate(parsed.data);
              } else if (parsed.type === 'error') {
                onError?.(parsed.content);
              } else if (parsed.type === 'done') {
                onComplete?.();
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
  }
};

// 补充类型定义
interface SkillDraft {
  name: string;
  description: string;
  executor_type: string;
  script_code: string;
  nextflow_code?: string;
  parameters_schema: Record<string, any>;
  expert_knowledge: string;
  dependencies: string[];
}
