/**
 * 技能锻造状态管理 Store
 *
 * 管理锻造会话、消息、技能草稿等状态
 */

import { create } from 'zustand';

// 执行器类型
export type ExecutorType = 'Python_env' | 'R_env' | 'Logical_Blueprint' | 'Python_Package';

// ==========================================
// Gemini 风格工具模式
// ==========================================

/** 工具模式类型定义 */
export type ToolMode = 'chat' | 'code_import' | 'skill_import';

/** 工具模式配置 */
export const TOOL_MODE_CONFIG: Record<ToolMode, { label: string; description: string; icon: string }> = {
  chat: {
    label: '对话锻造',
    description: '通过 AI 对话描述需求',
    icon: 'MessageSquare'
  },
  code_import: {
    label: '代码导入',
    description: '粘贴代码，AI 推断参数',
    icon: 'Code'
  },
  skill_import: {
    label: '技能包导入',
    description: '上传 .zip 技能包',
    icon: 'FileArchive'
  }
};

// 技能草稿结构
export interface SkillDraft {
  name: string;
  description: string;
  executor_type: ExecutorType;
  script_code: string;
  nextflow_code?: string;
  parameters_schema: Record<string, any>;
  expert_knowledge: string;
  dependencies: string[];
  category?: string;
  subcategory?: string;
  tags?: string[];
}

// 消息结构
export interface ForgeMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  attachments: string[];
  created_at: string;
}

// 会话结构
export interface ForgeSession {
  id: string;
  user_id: number;
  title: string;
  status: 'drafting' | 'testing' | 'ready' | 'saved';
  skill_draft: SkillDraft;
  skill_id?: string;
  executor_type: ExecutorType;
  created_at: string;
  updated_at: string;
  messages: ForgeMessage[];
}

// 会话列表项
export interface ForgeSessionListItem {
  id: string;
  title: string;
  status: string;
  executor_type: string;
  created_at: string;
  updated_at: string;
  has_draft: boolean;
}

// ==========================================
// 文件系统类型定义
// ==========================================

/** 文件节点 */
export interface SkillFileNode {
  id: string;                    // 文件路径作为 ID
  name: string;                  // 文件/文件夹名称
  type: 'file' | 'folder';       // 类型
  path: string;                  // 相对路径（相对于技能根目录）
  content?: string;              // 文件内容（仅文件类型）
  language?: string;             // Monaco 编辑器语言
  children?: SkillFileNode[];    // 子节点（仅文件夹类型）
  isModified?: boolean;          // 是否已修改
  isNew?: boolean;               // 是否新建文件
}

/** 打开的文件标签页 */
export interface OpenFileTab {
  id: string;                    // 文件路径
  name: string;                  // 文件名
  language: string;              // 语法
  isModified: boolean;           // 是否已修改
}

// ==========================================
// 文件系统工具函数
// ==========================================

/** 根据文件扩展名获取 Monaco 语言 */
export function getFileLanguage(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const languageMap: Record<string, string> = {
    py: 'python',
    r: 'r',
    R: 'r',
    nf: 'groovy',     // Nextflow 基于 Groovy
    md: 'markdown',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    sh: 'shell',
    ts: 'typescript',
    js: 'javascript',
    tsv: 'plaintext',
    csv: 'plaintext',
  };
  return languageMap[ext] || 'plaintext';
}

/** 从 SkillDraft 初始化虚拟文件系统 */
function initVirtualFileSystem(draft: SkillDraft, executorType: ExecutorType): SkillFileNode[] {
  const nodes: SkillFileNode[] = [];

  // ==========================================
  // 生成 SKILL.md 内容
  // ==========================================
  const skillMdContent = generateSkillMdContent(draft, executorType);

  // 0. SKILL.md 文件（根目录）
  nodes.push({
    id: 'SKILL.md',
    name: 'SKILL.md',
    type: 'file',
    path: 'SKILL.md',
    content: skillMdContent,
    language: 'markdown'
  });

  // 1. scripts 目录（包含主脚本文件）
  if (executorType !== 'Logical_Blueprint') {
    const mainScriptFile = executorType === 'Python_env' ? {
      id: 'scripts/main.py',
      name: 'main.py',
      type: 'file' as const,  // 显式指定类型字面量
      path: 'scripts/main.py',
      content: draft.script_code || '# Python 技能脚本\n',
      language: 'python'
    } : executorType === 'R_env' ? {
      id: 'scripts/main.R',
      name: 'main.R',
      type: 'file' as const,  // 显式指定类型字面量
      path: 'scripts/main.R',
      content: draft.script_code || '# R 技能脚本\n',
      language: 'r'
    } : null;

    nodes.push({
      id: 'scripts',
      name: 'scripts',
      type: 'folder',
      path: 'scripts',
      children: mainScriptFile ? [mainScriptFile] : []
    });
  }

  // 2. main.nf 文件（Nextflow 工作流，根目录）
  if (executorType === 'Logical_Blueprint') {
    nodes.push({
      id: 'main.nf',
      name: 'main.nf',
      type: 'file',
      path: 'main.nf',
      content: draft.nextflow_code || '// Nextflow 工作流\n',
      language: 'groovy'
    });
  }

  return nodes;
}

/**
 * 生成 SKILL.md 内容
 *
 * 按照标准 SKILL 规范生成 YAML 头部 + Markdown 内容
 */
function generateSkillMdContent(draft: SkillDraft, executorType: ExecutorType): string {
  // 生成参数表格
  const paramsTable = generateParamsTable(draft.parameters_schema);

  // 生成 YAML 头部
  const yamlHeader = `---
# ==========================================
# 核心系统元数据 (Core System Metadata)
# ------------------------------------------
# 以下区域为 YAML 格式，供后端系统路由和调度引擎直接读取
# ==========================================

skill_id: "${draft.name ? draft.name.toLowerCase().replace(/\s+/g, '_') : 'unnamed_skill'}"
name: "${draft.name || '未命名技能'}"
version: "1.0.0"
author: "Skill Forge"
executor_type: "${executorType}"
entry_point: "${executorType === 'Logical_Blueprint' ? 'main.nf' : 'scripts/main.' + (executorType === 'R_env' ? 'R' : 'py')}"
timeout_seconds: 3600
# 分类信息
category: "${draft.category || 'general'}"
category_name: "通用"
subcategory: "${draft.subcategory || ''}"
subcategory_name: ""
tags: [${(draft.tags || []).map(t => `"${t}"`).join(', ')}]
---`;

  // 生成完整内容
  return `${yamlHeader}

## 1. 技能意图与功能边界 (Intent & Scope)

*面向 AI 的核心描述，帮助其判断在何种场景下应该召唤此工具。*

${draft.description || '暂无描述'}

## 2. 动态参数定义规范 (Parameters Schema)

*系统底层的解析器将扫描此表格并转换为严格的 JSON Schema，并在前端渲染动态配置卡片。*

${paramsTable}

## 3. 操作指令与专家级知识库 (Operational Directives & Expert Knowledge)

*这里包含了系统赋予大模型的"锦囊妙计"，塑造其资深生信架构师的专业表现。*

${draft.expert_knowledge || '暂无专家指导'}

## 4. 依赖环境 (Dependencies)

${(draft.dependencies || []).length > 0 ? draft.dependencies.map(d => `- ${d}`).join('\n') : '暂无依赖'}
`;
}

/**
 * 生成参数表格
 */
function generateParamsTable(parametersSchema: Record<string, any>): string {
  if (!parametersSchema || !parametersSchema.properties) {
    return '暂无参数定义';
  }

  const props = parametersSchema.properties;
  const required = new Set(parametersSchema.required || []);

  // 表头
  let table = `| 参数键名 (Key) | 数据类型 (Type) | 必填 (Required) | 默认值 (Default) | 详细描述说明 (Detailed Description) |
|---|---|---|---|---|
`;

  // 遍历每个参数
  for (const [name, prop] of Object.entries(props)) {
    const paramProp = prop as { default?: any; description?: string };
    const type = getParamTypeDisplay(prop);
    const isRequired = required.has(name) ? '是 (Yes)' : '否 (No)';
    const defaultValue = paramProp.default !== undefined ? String(paramProp.default) : '';
    const description = paramProp.description || '';

    table += `| \`${name}\` | ${type} | ${isRequired} | ${defaultValue} | ${description} |
`;
  }

  return table;
}

/**
 * 获取参数类型显示文本
 */
function getParamTypeDisplay(prop: any): string {
  const format = (prop.format || '').toLowerCase().replace(/-/g, '');

  if (format === 'filepath') return 'FilePath';
  if (format === 'directorypath') return 'DirectoryPath';

  if (prop.enum) return 'Enum';
  if (prop.type === 'array') return 'Array';
  if (prop.type === 'boolean') return 'Boolean';
  if (prop.type === 'number') return 'Number';
  if (prop.type === 'integer') return 'Integer';

  return 'String';
}

/** 在文件树中查找节点 */
export function findNodeInTree(nodes: SkillFileNode[], targetId: string): SkillFileNode | null {
  for (const node of nodes) {
    if (node.id === targetId) return node;
    if (node.children) {
      const found = findNodeInTree(node.children, targetId);
      if (found) return found;
    }
  }
  return null;
}

/** 更新文件树中节点的内容 */
function updateNodeInTree(nodes: SkillFileNode[], targetId: string, updates: Partial<SkillFileNode>): SkillFileNode[] {
  return nodes.map(node => {
    if (node.id === targetId) {
      return { ...node, ...updates };
    }
    if (node.children) {
      return { ...node, children: updateNodeInTree(node.children, targetId, updates) };
    }
    return node;
  });
}

/** 清除所有修改标记 */
function clearModifiedFlags(nodes: SkillFileNode[]): SkillFileNode[] {
  return nodes.map(node => ({
    ...node,
    isModified: false,
    children: node.children ? clearModifiedFlags(node.children) : undefined
  }));
}

// 初始草稿状态
const initialDraft: SkillDraft = {
  name: '',
  description: '',
  executor_type: 'Python_env',
  script_code: '',
  nextflow_code: '',
  parameters_schema: {},
  expert_knowledge: '',
  dependencies: []
};

// Store 状态接口
interface ForgeState {
  // 会话信息
  sessionId: string | null;
  sessionTitle: string;
  sessionStatus: string;
  skillId: string | null;  // 已保存技能的 ID（如果有）
  skillVersion: string;     // 当前版本号

  // 消息列表
  messages: ForgeMessage[];
  addMessage: (role: 'user' | 'assistant', content: string, attachments?: string[]) => void;
  appendLastMessage: (content: string) => void;
  setMessages: (messages: ForgeMessage[]) => void;
  clearMessages: () => void;

  // 技能草稿
  skillDraft: SkillDraft;
  updateSkillDraft: (updates: Partial<SkillDraft>) => void;
  setSkillDraft: (draft: SkillDraft) => void;

  // 附件
  attachments: string[];
  addAttachment: (path: string) => void;
  removeAttachment: (path: string) => void;
  clearAttachments: () => void;

  // 执行器类型
  executorType: ExecutorType;
  // 执行器类型（同时会重新初始化文件系统）
  // 可选参数 draft：传入草稿数据用于初始化文件系统，解决编辑技能时的时序问题
  setExecutorType: (type: ExecutorType, draft?: SkillDraft) => void;

  // ==========================================
  // Gemini 风格工具模式
  // ==========================================
  toolMode: ToolMode;
  setToolMode: (mode: ToolMode) => void;

  // 状态
  isTyping: boolean;
  setIsTyping: (status: boolean) => void;

  // 会话列表
  sessionList: ForgeSessionListItem[];
  setSessionList: (list: ForgeSessionListItem[]) => void;
  refreshSessionList: () => Promise<void>;

  // 会话管理
  createSession: () => Promise<string>;
  loadSession: (sessionId: string) => Promise<void>;
  loadSessionList: () => Promise<void>;

  // 技能 ID 和版本管理
  setSkillId: (skillId: string | null) => void;
  setSkillVersion: (version: string) => void;

  // ==========================================
  // 文件系统状态
  // ==========================================
  skillFiles: SkillFileNode[];
  activeFileId: string | null;
  openTabs: OpenFileTab[];
  expandedFolders: Set<string>;

  // 文件系统方法
  initSkillFiles: () => void;
  setActiveFile: (fileId: string | null) => void;
  updateFileContent: (fileId: string, content: string) => void;
  toggleFolder: (folderId: string) => void;
  closeTab: (fileId: string) => void;
  closeAllTabs: () => void;
  addFile: (parentPath: string, name: string, type: 'file' | 'folder') => void;
  deleteFile: (fileId: string) => void;
  renameFile: (fileId: string, newName: string) => void;

  // 重置
  reset: () => void;
}

// 初始状态
const initialState = {
  sessionId: null,
  sessionTitle: '新技能锻造',
  sessionStatus: 'drafting',
  skillId: null,
  skillVersion: '1.0.0',
  messages: [],
  skillDraft: initialDraft,
  attachments: [],
  executorType: 'Python_env' as ExecutorType,
  isTyping: false,
  sessionList: [],
  // Gemini 风格工具模式
  toolMode: 'chat' as ToolMode,
  // 文件系统
  skillFiles: [] as SkillFileNode[],
  activeFileId: null as string | null,
  openTabs: [] as OpenFileTab[],
  expandedFolders: new Set<string>(['scripts'])
};

// 生成唯一消息ID
const generateMessageId = () => {
  return `forge_msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
};

export const useForgeStore = create<ForgeState>((set, get) => ({
  ...initialState,

  // 消息操作
  addMessage: (role, content, attachments = []) => set(state => ({
    messages: [...state.messages, {
      id: generateMessageId(),
      session_id: state.sessionId || '',
      role,
      content,
      attachments,
      created_at: new Date().toISOString()
    }]
  })),

  appendLastMessage: (content) => set(state => {
    const messages = [...state.messages];
    if (messages.length > 0) {
      messages[messages.length - 1].content += content;
    }
    return { messages };
  }),

  setMessages: (messages) => set({ messages }),

  clearMessages: () => set({ messages: [], skillDraft: initialDraft }),

  // 技能草稿操作
  updateSkillDraft: (updates) => set(state => {
    const newState: any = {
      skillDraft: { ...state.skillDraft, ...updates }
    };
    // 如果更新了 executor_type，同步更新 executorType 状态
    if (updates.executor_type) {
      newState.executorType = updates.executor_type as ExecutorType;
    }
    return newState;
  }),

  setSkillDraft: (draft) => set(state => {
    // 更新 SKILL.md 文件内容
    const skillMdContent = generateSkillMdContent(draft, draft.executor_type as ExecutorType);
    const updatedFiles = updateNodeInTree(state.skillFiles, 'SKILL.md', {
      content: skillMdContent
    });

    return {
      skillDraft: draft,
      // 同步执行器类型状态，确保 UI 一致性
      executorType: draft.executor_type as ExecutorType,
      // 更新文件树中的 SKILL.md
      skillFiles: updatedFiles.length > 0 ? updatedFiles : state.skillFiles
    };
  }),

  // 附件操作
  addAttachment: (path) => set(state => ({
    attachments: [...state.attachments, path]
  })),

  removeAttachment: (path) => set(state => ({
    attachments: state.attachments.filter(p => p !== path)
  })),

  clearAttachments: () => set({ attachments: [] }),

  // 执行器类型（同时重新初始化文件系统）
  // 可选参数 draft：传入草稿数据用于初始化文件系统，解决编辑技能时的时序问题
  // 当传入 draft 时，使用传入的数据初始化文件系统；否则使用当前状态的 skillDraft
  setExecutorType: (type, draft) => {
    // 优先使用传入的 draft，否则使用当前状态的 skillDraft
    const currentDraft = draft || get().skillDraft;

    // 更新执行器类型
    set({ executorType: type });

    // 更新 skillDraft（使用传入的 draft 或合并当前状态）
    const newDraft = draft || { ...currentDraft, executor_type: type };
    set({ skillDraft: newDraft });

    // 使用正确的草稿数据初始化文件系统（关键修复：传入 newDraft 而非 get().skillDraft）
    const nodes = initVirtualFileSystem(newDraft, type);
    set({
      skillFiles: nodes,
      activeFileId: null,
      openTabs: [],
      expandedFolders: new Set(['scripts'])
    });
  },

  // ==========================================
  // Gemini 风格工具模式
  // ==========================================
  setToolMode: (mode) => set({ toolMode: mode }),

  // 状态
  setIsTyping: (status) => set({ isTyping: status }),

  // 会话列表
  setSessionList: (list) => set({ sessionList: list }),

  // 刷新会话列表（用于保存/提交后）
  refreshSessionList: async () => {
    const BASE_URL = typeof window !== 'undefined'
      ? `http://${window.location.hostname}:8000`
      : 'http://localhost:8000';

    try {
      const response = await fetch(`${BASE_URL}/api/skills/forge/sessions`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        }
      });

      const data = await response.json();
      set({ sessionList: data.sessions || [] });
    } catch (error) {
      console.error('刷新会话列表失败:', error);
    }
  },

  // 创建会话
  createSession: async () => {
    const { executorType } = get();
    const BASE_URL = typeof window !== 'undefined'
      ? `http://${window.location.hostname}:8000`
      : 'http://localhost:8000';

    try {
      const response = await fetch(`${BASE_URL}/api/skills/forge/session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        },
        body: JSON.stringify({
          title: '新技能锻造',
          executor_type: executorType
        })
      });

      const data = await response.json();
      set({
        sessionId: data.session_id,
        sessionTitle: data.title,
        sessionStatus: 'drafting',
        messages: [],
        skillDraft: initialDraft
      });

      return data.session_id;
    } catch (error) {
      console.error('创建会话失败:', error);
      throw error;
    }
  },

  // 加载会话
  loadSession: async (sessionId) => {
    const BASE_URL = typeof window !== 'undefined'
      ? `http://${window.location.hostname}:8000`
      : 'http://localhost:8000';

    try {
      const response = await fetch(`${BASE_URL}/api/skills/forge/session/${sessionId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        }
      });

      const data = await response.json();
      const draft = data.skill_draft || initialDraft;
      const execType = data.executor_type || draft.executor_type || 'Python_env';

      console.log('[loadSession] 加载的草稿数据:', {
        id: data.id,
        name: draft.name,
        executor_type: draft.executor_type,
        script_code_length: draft.script_code?.length || 0,
        has_code: !!draft.script_code
      });

      // 先更新基本状态
      set({
        sessionId: data.id,
        sessionTitle: data.title,
        sessionStatus: data.status,
        messages: data.messages || [],
        skillDraft: draft,
        executorType: execType as ExecutorType,
        skillId: data.skill_id || null
      });

      // 然后根据加载的草稿初始化文件系统
      console.log('[loadSession] 初始化文件系统，executorType:', execType, 'script_code preview:', draft.script_code?.substring(0, 100));
      const nodes = initVirtualFileSystem(draft, execType as ExecutorType);
      console.log('[loadSession] 生成的文件节点:', nodes.map(n => ({ id: n.id, name: n.name, hasContent: !!n.content, children: n.children?.map(c => c.id) })));

      set({
        skillFiles: nodes,
        activeFileId: null,
        openTabs: [],
        expandedFolders: new Set(['scripts'])
      });

      console.log('[loadSession] 会话加载完成，文件系统已初始化');
    } catch (error) {
      console.error('加载会话失败:', error);
      throw error;
    }
  },

  // 加载会话列表
  loadSessionList: async () => {
    const BASE_URL = typeof window !== 'undefined'
      ? `http://${window.location.hostname}:8000`
      : 'http://localhost:8000';

    try {
      const response = await fetch(`${BASE_URL}/api/skills/forge/sessions`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        }
      });

      const data = await response.json();
      set({ sessionList: data.sessions || [] });
    } catch (error) {
      console.error('加载会话列表失败:', error);
    }
  },

  // 设置技能 ID
  setSkillId: (skillId) => set({ skillId }),

  // 设置技能版本
  setSkillVersion: (skillVersion) => set({ skillVersion }),

  // ==========================================
  // 文件系统方法实现
  // ==========================================

  // 初始化文件系统
  initSkillFiles: () => set(state => {
    const nodes = initVirtualFileSystem(state.skillDraft, state.executorType);
    return {
      skillFiles: nodes,
      activeFileId: null,
      openTabs: [],
      expandedFolders: new Set(['scripts'])
    };
  }),

  // 设置活动文件
  setActiveFile: (fileId) => set(state => {
    if (!fileId) {
      return { activeFileId: null };
    }

    const file = findNodeInTree(state.skillFiles, fileId);
    if (!file || file.type === 'folder') {
      return state;
    }

    // 添加到打开的标签页
    const existingTab = state.openTabs.find(t => t.id === fileId);
    const newTabs = existingTab
      ? state.openTabs
      : [...state.openTabs, {
          id: file.id,
          name: file.name,
          language: file.language || getFileLanguage(file.name),
          isModified: file.isModified || false
        }];

    return {
      activeFileId: fileId,
      openTabs: newTabs
    };
  }),

  // 更新文件内容
  updateFileContent: (fileId, content) => set(state => {
    // 更新文件树
    const newFiles = updateNodeInTree(state.skillFiles, fileId, {
      content,
      isModified: true
    });

    // 同步更新到 SkillDraft（保持向后兼容）
    const updates: Partial<SkillDraft> = {};
    if (fileId === 'scripts/main.py' || fileId === 'scripts/main.R') {
      updates.script_code = content;
    } else if (fileId === 'main.nf') {
      updates.nextflow_code = content;
    }

    return {
      skillFiles: newFiles,
      openTabs: state.openTabs.map(t =>
        t.id === fileId ? { ...t, isModified: true } : t
      ),
      skillDraft: Object.keys(updates).length > 0
        ? { ...state.skillDraft, ...updates }
        : state.skillDraft
    };
  }),

  // 切换文件夹展开状态
  toggleFolder: (folderId) => set(state => {
    const newExpanded = new Set(state.expandedFolders);
    if (newExpanded.has(folderId)) {
      newExpanded.delete(folderId);
    } else {
      newExpanded.add(folderId);
    }
    return { expandedFolders: newExpanded };
  }),

  // 关闭标签页
  closeTab: (fileId) => set(state => {
    const newTabs = state.openTabs.filter(t => t.id !== fileId);
    let newActiveId = state.activeFileId;

    // 如果关闭的是当前活动标签，切换到相邻标签
    if (state.activeFileId === fileId && newTabs.length > 0) {
      const closedIndex = state.openTabs.findIndex(t => t.id === fileId);
      newActiveId = newTabs[Math.min(closedIndex, newTabs.length - 1)].id;
    } else if (newTabs.length === 0) {
      newActiveId = null;
    }

    return {
      openTabs: newTabs,
      activeFileId: newActiveId
    };
  }),

  // 关闭所有标签页
  closeAllTabs: () => set({
    openTabs: [],
    activeFileId: null
  }),

  // 添加新文件
  addFile: (parentPath, name, type) => set(state => {
    const newId = parentPath ? `${parentPath}/${name}` : name;
    const newNode: SkillFileNode = {
      id: newId,
      name,
      type,
      path: newId,
      content: type === 'file' ? '' : undefined,
      language: type === 'file' ? getFileLanguage(name) : undefined,
      children: type === 'folder' ? [] : undefined,
      isNew: true,
      isModified: false
    };

    const addToTree = (nodes: SkillFileNode[]): SkillFileNode[] => {
      if (!parentPath) {
        return [...nodes, newNode];
      }

      return nodes.map(node => {
        if (node.id === parentPath && node.type === 'folder') {
          return { ...node, children: [...(node.children || []), newNode] };
        }
        if (node.children) {
          return { ...node, children: addToTree(node.children) };
        }
        return node;
      });
    };

    return { skillFiles: addToTree(state.skillFiles) };
  }),

  // 删除文件
  deleteFile: (fileId) => set(state => {
    const removeFromTree = (nodes: SkillFileNode[]): SkillFileNode[] => {
      return nodes
        .filter(node => node.id !== fileId)
        .map(node => {
          if (node.children) {
            return { ...node, children: removeFromTree(node.children) };
          }
          return node;
        });
    };

    return {
      skillFiles: removeFromTree(state.skillFiles),
      openTabs: state.openTabs.filter(t => t.id !== fileId),
      activeFileId: state.activeFileId === fileId ? null : state.activeFileId
    };
  }),

  // 重命名文件
  renameFile: (fileId, newName) => set(state => {
    const renameInTree = (nodes: SkillFileNode[]): SkillFileNode[] => {
      return nodes.map(node => {
        if (node.id === fileId) {
          const newId = node.path.split('/').slice(0, -1).concat(newName).join('/');
          return {
            ...node,
            id: newId,
            name: newName,
            path: newId,
            language: node.type === 'file' ? getFileLanguage(newName) : undefined
          };
        }
        if (node.children) {
          return { ...node, children: renameInTree(node.children) };
        }
        return node;
      });
    };

    return {
      skillFiles: renameInTree(state.skillFiles),
      openTabs: state.openTabs.map(t =>
        t.id === fileId ? { ...t, name: newName, language: getFileLanguage(newName) } : t
      )
    };
  }),

  // 重置（保留会话列表）
  reset: () => set({
    sessionId: null,
    sessionTitle: '新技能锻造',
    sessionStatus: 'drafting',
    skillId: null,
    skillVersion: '1.0.0',
    messages: [],
    skillDraft: initialDraft,
    attachments: [],
    executorType: 'Python_env' as ExecutorType,
    isTyping: false,
    // Gemini 风格工具模式
    toolMode: 'chat' as ToolMode,
    // 文件系统状态
    skillFiles: [],
    activeFileId: null,
    openTabs: [],
    expandedFolders: new Set(['scripts'])
    // 注意：不重置 sessionList，保留历史记录
  })
}));