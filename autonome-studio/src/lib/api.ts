// 🛡️ 智能动态获取后端的 IP 地址
// 如果在浏览器环境，自动获取当前访问的 IP (如 113.44.66.210)，拼接上后端 8000 端口
// 如果在服务端渲染环境，则默认兜底为 localhost
export const BASE_URL = typeof window !== 'undefined'
  ? `http://${window.location.hostname}:8000`
  : 'http://localhost:8000';

// ==========================================
// API 缓存工具导入
// ==========================================
import { cachedFetch, invalidateCache } from './apiCache';

/**
 * 获取存储在本地的 JWT token
 */
export function getToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('autonome_access_token');
  }
  return null;
}

export async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const token = getToken();
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
  skill_md?: string;
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
  nextflow_code: string | null;
  dependencies: string[];
  status: string;
  reject_reason: string | null;
  owner_id: number;
  // 分类信息
  category: string | null;
  category_name: string | null;
  subcategory: string | null;
  subcategory_name: string | null;
  tags: string[];
  // ✨ 基础分析标记
  is_basic_analysis: boolean;
  created_at: string;
  updated_at: string;
}

export const skillForgeApi = {
  /**
   * 获取当前用户可用的所有技能（已包含权限过滤）
   * 🚀 使用缓存优化，缓存 5 分钟
   */
  listSkills: async (options?: { forceRefresh?: boolean }): Promise<SkillAsset[]> => {
    return cachedFetch<SkillAsset[]>(
      'skills:list',
      () => fetchAPI('/api/skills/'),
      undefined,
      options
    );
  },

  /**
   * 使技能列表缓存失效
   */
  invalidateSkillsCache: () => {
    invalidateCache('skills:list');
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
    onFileItem?: (file: { name: string; path: string; size: number; type: string }) => void,
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
    const timeoutMs = 600000; // 10分钟总超时
    const inactivityTimeoutMs = 180000; // 3分钟无活动超时（适应LLM生成测试数据）

    const timeoutId = setTimeout(() => {
      controller.abort();
      onLog('⏱️ 测试超时（10分钟），已自动取消');
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
          onLog('⏱️ 响应超时（3分钟无活动），已自动取消');
        }
      }, 10000);

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
                } else if (event.type === 'file_tree' && event.message) {
                  onLog(event.message);
                } else if (event.type === 'file_item' && onFileItem && event.data) {
                  onFileItem(event.data);
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
    // 后端返回 { status: "success", source: "database/filesystem", data: { ... } }
    // 需要提取 data 字段
    return response.data || response;
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
// 技能草稿 API（自动转化功能）
// ==========================================

export interface PendingSkillDraft {
  id: number;
  user_id: number;
  session_id: string;
  project_id: string | null;
  trigger_source: string;
  trigger_score: number;
  trigger_reason: string;
  raw_material: string;
  code_blocks: Array<{ language: string; code: string }>;
  strategies: Array<Record<string, any>>;
  draft_name: string;
  draft_description: string;
  executor_type: string;
  parameters_schema: Record<string, any>;
  expert_knowledge: string;
  script_code: string;
  dependencies: string[];
  status: string;
  created_at: string;
  updated_at: string;
  published_skill_id: string | null;
}

export interface DraftStats {
  total: number;
  pending: number;
  reviewed: number;
  published: number;
  dismissed: number;
  failed: number;
}

export const skillDraftApi = {
  /**
   * 获取用户的技能草稿列表
   */
  getDrafts: async (params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<PendingSkillDraft[]> => {
    const queryParams = new URLSearchParams();
    if (params?.status) queryParams.set('status', params.status);
    if (params?.limit) queryParams.set('limit', params.limit.toString());
    if (params?.offset) queryParams.set('offset', params.offset.toString());

    const query = queryParams.toString();
    const response = await fetchAPI(`/api/skills/drafts${query ? `?${query}` : ''}`);
    return response;
  },

  /**
   * 获取草稿统计信息
   */
  getDraftStats: async (): Promise<DraftStats> => {
    const response = await fetchAPI('/api/skills/drafts/stats');
    return response;
  },

  /**
   * 获取单个草稿详情
   */
  getDraft: async (draftId: number): Promise<PendingSkillDraft> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}`);
    return response;
  },

  /**
   * 更新草稿内容
   */
  updateDraft: async (draftId: number, updates: Partial<PendingSkillDraft>): Promise<PendingSkillDraft> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
    return response;
  },

  /**
   * 发布草稿为正式技能
   */
  publishDraft: async (draftId: number, params?: {
    skill_name?: string;
    category?: string;
    tags?: string[];
  }): Promise<{ skill_id: string; name: string; status: string; message: string }> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}/publish`, {
      method: 'POST',
      body: JSON.stringify(params || {}),
    });
    return response;
  },

  /**
   * 忽略草稿
   */
  dismissDraft: async (draftId: number): Promise<{ status: string; message: string }> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}/dismiss`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 标记草稿为已查看
   */
  markReviewed: async (draftId: number): Promise<{ status: string; message: string }> => {
    const response = await fetchAPI(`/api/skills/drafts/${draftId}/review`, {
      method: 'POST',
    });
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
  nextflow_code?: string | null;
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
  submitSkill: async (sessionId: string): Promise<{ status: string; skill_id: string; name: string }> => {
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


// ==========================================
// 参考基因组管理 API (Genome API)
// ==========================================

export interface GenomeAsset {
  id: number;
  genomeid: string;
  species: string;
  version: string;
  species_code: string | null;
  url: string | null;
  date: string | null;
  genome: string;
  chrlen: string | null;
  gff: string | null;
  gffdb: string | null;
  gtf: string | null;
  geneanno: string | null;
  genelen: string | null;
  genome_info: string | null;
  bowtie2_index: string | null;
  bowtie1_index: string | null;
  bwa_index: string | null;
  star_index: string | null;
  hisat2_index: string | null;
  novoalign_index: string | null;
  minimap2_index: string | null;
  minimap2_juncbed: string | null;
  rsem_index: string | null;
  noncode_index: string | null;
  ref10x: string | null;
  sc_star: string | null;
  sc_gtf: string | null;
  godes: string | null;
  kg: string | null;
  known_lncRNA: string | null;
  bsgenome: string | null;
  geneid_or_symbol: string;
  is_active: boolean;
  description: string | null;
  custom_fields: Record<string, any>;
  owner_id: number;
  visibility: string;
  shared_with: number[];
  created_at: string;
  updated_at: string;
}

export const genomeApi = {
  /**
   * 获取基因组列表
   * 🚀 使用缓存优化，缓存 10 分钟
   */
  listGenomes: async (species?: string, search?: string, options?: { forceRefresh?: boolean }): Promise<GenomeAsset[]> => {
    const params: Record<string, string> = {};
    if (species) params.species = species;
    if (search) params.search = search;

    return cachedFetch<GenomeAsset[]>(
      'genomes:list',
      () => {
        const query = Object.keys(params).length > 0
          ? `?${new URLSearchParams(params).toString()}`
          : '';
        return fetchAPI(`/api/genomes/${query}`);
      },
      Object.keys(params).length > 0 ? params : undefined,
      options
    );
  },

  /**
   * 使基因组列表缓存失效
   */
  invalidateGenomesCache: () => {
    invalidateCache('genomes:list');
  },

  /**
   * 获取物种列表
   */
  listSpecies: async (): Promise<{ status: string; data: { species: string; count: number }[] }> => {
    return fetchAPI('/api/genomes/species/list');
  },

  /**
   * 获取单个基因组详情
   */
  getGenome: async (genomeid: string): Promise<GenomeAsset> => {
    return fetchAPI(`/api/genomes/${genomeid}`);
  },

  /**
   * 获取基因组配置（besaltpipe 兼容格式）
   */
  getGenomeConfig: async (genomeid: string): Promise<Record<string, any>> => {
    return fetchAPI(`/api/genomes/${genomeid}/config`);
  },

  /**
   * 创建基因组
   */
  createGenome: async (data: Partial<GenomeAsset>): Promise<GenomeAsset> => {
    return fetchAPI('/api/genomes/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * 更新基因组
   */
  updateGenome: async (genomeid: string, data: Partial<GenomeAsset>): Promise<GenomeAsset> => {
    return fetchAPI(`/api/genomes/${genomeid}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /**
   * 删除基因组
   */
  deleteGenome: async (genomeid: string): Promise<{ status: string; message: string }> => {
    return fetchAPI(`/api/genomes/${genomeid}`, {
      method: 'DELETE',
    });
  },

  /**
   * 切换基因组启用/禁用状态
   */
  toggleActive: async (genomeid: string): Promise<{ status: string; is_active: boolean }> => {
    return fetchAPI(`/api/genomes/${genomeid}/toggle-active`, {
      method: 'POST',
    });
  },

  /**
   * 共享基因组
   */
  shareGenome: async (genomeid: string, userIds: number[]): Promise<{ status: string; shared_with: number[] }> => {
    return fetchAPI(`/api/genomes/${genomeid}/share`, {
      method: 'POST',
      body: JSON.stringify({ user_ids: userIds }),
    });
  },

  /**
   * 验证基因组路径
   */
  validatePaths: async (genomeid: string): Promise<{
    status: string;
    total_paths: number;
    existing_paths: number;
    missing_paths: number;
    results: Record<string, any>;
  }> => {
    return fetchAPI(`/api/genomes/${genomeid}/validate`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  /**
   * 导出 TSV
   */
  exportTsv: async (species?: string): Promise<Blob> => {
    const params = species ? `?species=${species}` : '';
    const response = await fetch(`${BASE_URL}/api/genomes/export/tsv${params}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`,
      },
    });
    return response.blob();
  },

  /**
   * 导入 TSV/CSV 文件
   */
  importTsv: async (formData: FormData): Promise<{
    status: string;
    imported_count: number;
    skipped_count: number;
    error_count: number;
    imported: string[];
    skipped: { genomeid: string; reason: string }[];
    errors: string[];
  }> => {
    const response = await fetch(`${BASE_URL}/api/genomes/import-tsv`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`,
      },
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || '导入失败');
    }
    return response.json();
  },
};


// ==========================================
// 分析数据库管理 API (Database API)
// ==========================================

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
   * 🚀 使用缓存优化，缓存 10 分钟
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

// ==========================================
// 错误诊断 API
// ==========================================

export interface DiagnoseRequest {
  error_log: string;
  exit_code: number;
  language: string;
  context?: Record<string, unknown>;
}

export interface FixSuggestion {
  action: string;
  description: string;
  auto_fixable: boolean;
  fix_command?: string;
  fix_code?: string;
  manual_steps: string[];
}

export interface ErrorDiagnosis {
  error_type: string;
  severity: string;
  title: string;
  message: string;
  original_error: string;
  line_number?: number;
  module_name?: string;
  file_path?: string;
  suggestions: FixSuggestion[];
  context: Record<string, unknown>;
}

export interface DiagnoseResponse {
  status: string;
  diagnosis: ErrorDiagnosis;
}

export interface FixResponse {
  success: boolean;
  message: string;
  action: string;
  details?: Record<string, unknown>;
}

export const errorDiagnosticApi = {
  /**
   * 诊断执行错误
   */
  diagnose: async (request: DiagnoseRequest): Promise<DiagnoseResponse> => {
    return fetchAPI('/api/error/diagnose', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  /**
   * 一键修复错误
   */
  fix: async (
    errorType: string,
    moduleName?: string,
    filePath?: string,
    language: string = 'python'
  ): Promise<FixResponse> => {
    return fetchAPI('/api/error/fix', {
      method: 'POST',
      body: JSON.stringify({
        error_type: errorType,
        module_name: moduleName,
        file_path: filePath,
        language,
      }),
    });
  },

  /**
   * 获取常见错误列表
   */
  getCommonErrors: async (): Promise<{
    status: string;
    errors: Array<{
      type: string;
      title: string;
      description: string;
      solution: string;
      auto_fixable: boolean;
    }>;
  }> => {
    return fetchAPI('/api/error/common-errors');
  },
};

// ==========================================
// 执行参数状态管理（本地存储）
// ==========================================

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


// ==========================================
// 首页收藏技能管理（本地存储）
// ==========================================

const PINNED_SKILLS_KEY = 'autonome_pinned_skills';

export interface PinnedSkill {
  skill_id: string;
  name: string;
  description?: string;
  executor_type: string;
  pinned_at: number;
}

export const pinnedSkillsApi = {
  /**
   * 获取所有收藏的技能
   */
  getPinnedSkills: (): PinnedSkill[] => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(PINNED_SKILLS_KEY);
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
   * 添加收藏技能
   */
  pinSkill: (skill: PinnedSkill): void => {
    if (typeof window !== 'undefined') {
      const skills = pinnedSkillsApi.getPinnedSkills();
      // 检查是否已收藏
      if (!skills.find(s => s.skill_id === skill.skill_id)) {
        skills.unshift({ ...skill, pinned_at: Date.now() });
        // 只保留最近 10 个
        const trimmed = skills.slice(0, 10);
        localStorage.setItem(PINNED_SKILLS_KEY, JSON.stringify(trimmed));
      }
    }
  },

  /**
   * 取消收藏
   */
  unpinSkill: (skillId: string): void => {
    if (typeof window !== 'undefined') {
      const skills = pinnedSkillsApi.getPinnedSkills();
      const filtered = skills.filter(s => s.skill_id !== skillId);
      localStorage.setItem(PINNED_SKILLS_KEY, JSON.stringify(filtered));
    }
  },

  /**
   * 检查是否已收藏
   */
  isPinned: (skillId: string): boolean => {
    const skills = pinnedSkillsApi.getPinnedSkills();
    return skills.some(s => s.skill_id === skillId);
  },
};


// ==========================================
// 技能快速执行 API
// ==========================================

export interface QuickMatchRequest {
  user_query: string;
  context?: Record<string, unknown>;
}

export interface QuickMatchResponse {
  intent_type: string;
  confidence: number;
  matched_skills: Array<{
    skill_id: string;
    name: string;
    description?: string;
    executor_type: string;
    match_score: number;
    match_reason: string;
  }>;
  parameters_suggestion: Record<string, unknown>;
  match_source: string;
  match_mode: string;  // fast | precise | auto
  reason: string;
}

/**
 * 匹配模式类型
 * - fast: 快速模式，仅规则+向量匹配，<200ms
 * - precise: 精准模式，完整三阶段匹配（含LLM），~1-2s
 * - auto: 自动模式，根据置信度决定是否使用LLM（默认）
 */
export type MatchMode = 'fast' | 'precise' | 'auto';

export const quickExecuteApi = {
  /**
   * 快速匹配技能 - 根据用户输入推荐最合适的技能
   * @param query 用户查询
   * @param context 上下文信息
   * @param mode 匹配模式：fast(快速) | precise(精准) | auto(自动，默认)
   */
  matchSkills: async (
    query: string,
    context?: Record<string, unknown>,
    mode: MatchMode = 'auto'
  ): Promise<QuickMatchResponse> => {
    return fetchAPI('/api/skill-recommend/match', {
      method: 'POST',
      body: JSON.stringify({
        user_query: query,
        context,
        mode,
      }),
    });
  },

  /**
   * 意图识别 - 分析用户输入意图
   */
  detectIntent: async (query: string, sessionId?: string): Promise<{
    intent_type: string;
    confidence: number;
    matched_skills: Array<{
      skill_id: string;
      name: string;
      description?: string;
      executor_type: string;
      match_score: number;
      match_reason: string;
    }>;
    should_inject: boolean;
  }> => {
    return fetchAPI('/api/skill-recommend/intent', {
      method: 'POST',
      body: JSON.stringify({
        user_query: query,
        session_id: sessionId,
      }),
    });
  },
};


// ==========================================
// 推荐反馈 API
// ==========================================

export type FeedbackEventType = 'recommend' | 'click' | 'execute' | 'success' | 'failure' | 'dismiss';

export interface RecordBehaviorRequest {
  session_id: string;
  event_type: FeedbackEventType;
  skill_id: string;
  query?: string;
  match_source?: string;
  confidence?: number;
  execution_time?: number;
}

export const feedbackApi = {
  /**
   * 记录用户行为埋点
   *
   * 事件类型：
   * - recommend: 技能被推荐
   * - click: 用户点击技能
   * - execute: 技能被执行
   * - success: 执行成功
   * - failure: 执行失败
   * - dismiss: 用户忽略推荐
   */
  recordBehavior: async (request: RecordBehaviorRequest): Promise<{ success: boolean; message: string }> => {
    return fetchAPI('/api/skill-recommend/feedback/record', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  /**
   * 获取反馈统计（管理员）
   */
  getStats: async (): Promise<{
    aggregation_time: string;
    total_skills: number;
    total_recommendations: number;
    total_clicks: number;
    total_executions: number;
    total_successes: number;
    overall_click_rate: number;
    overall_success_rate: number;
    top_performing_skills: Array<{
      skill_id: string;
      dynamic_score: number;
      click_rate: number;
      success_rate: number;
    }>;
  }> => {
    return fetchAPI('/api/skill-recommend/feedback/stats');
  },
};
