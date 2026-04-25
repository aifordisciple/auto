import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { fetchAPI } from '@/lib/api';

// Define tool parameter JSON Schema structure
export type ParamType = 'number' | 'boolean' | 'select' | 'string';

export interface ToolParameter {
  type: ParamType;
  label: string;
  default?: any;
  options?: string[]; // For select
  min?: number;      // For number (slider)
  max?: number;
  step?: number;    // For number slider step
}

export interface ToolSchema {
  id: string;
  name: string;
  description: string;
  parameters: Record<string, ToolParameter>;
}

// Real file interface from database
export interface RealFile {
  id: string;
  filename: string;
  file_path: string;
  file_size: number;
  file_type: string;
  project_id: string;
  uploaded_at: string;
}

// ==========================================
// ✨ 技能附件接口 - 用于聊天中预选技能
// ==========================================
export interface PendingSkill {
  skill_id: string;
  name: string;
  executor_type: string;
}

// ==========================================
// ✨ 粘贴附件接口 - 用于 Ctrl+V 粘贴上传
// ==========================================
export interface PastedAttachment {
  id: string;              // 唯一标识
  type: 'image' | 'file';  // 类型区分：图片或文件
  localUrl?: string;       // 图片本地预览 URL (blob:xxx)
  fileName: string;        // 文件名
  fileSize: number;        // 文件大小
  serverPath: string;      // 服务器存储路径
  isUploading: boolean;    // 上传状态
}

interface WorkspaceState {
  // Project context
  currentProjectId: string | null;
  setCurrentProjectId: (id: string | null) => void;

  // Current chat session
  currentSessionId: string | null;
  currentSessionTitle: string | null;
  setCurrentSessionId: (id: string | null, title?: string | null) => void;

  // Data Center: mounted files for AI context
  projectFiles: RealFile[];
  setProjectFiles: (files: RealFile[]) => void;
  addProjectFile: (file: RealFile) => void;
  fetchProjectFiles: (projectId?: string) => Promise<void>;

  mountedFiles: string[];
  toggleMountFile: (file: string) => void;

  // Dynamic Toolbox: active tool and parameters
  activeTool: ToolSchema | null;
  toolParams: Record<string, any>;
  setActiveTool: (tool: ToolSchema | null) => void;
  updateToolParam: (key: string, value: any) => void;

  // Pending chat attachments (from DataCenter batch selection)
  pendingChatAttachments: string[];
  setPendingChatAttachments: (paths: string[]) => void;
  addPendingChatAttachment: (path: string) => void;
  removePendingChatAttachment: (path: string) => void;
  clearPendingChatAttachments: () => void;

  // ✨ 技能附件状态 - 用户预选的技能
  pendingChatSkill: PendingSkill | null;
  setPendingChatSkill: (skill: PendingSkill | null) => void;
  clearPendingChatSkill: () => void;

  // ✨ 粘贴附件状态 - Ctrl+V 粘贴的图片/文件
  pastedAttachments: PastedAttachment[];
  addPastedAttachment: (attachment: PastedAttachment) => void;
  removePastedAttachment: (id: string) => void;
  updatePastedAttachment: (id: string, updates: Partial<PastedAttachment>) => void;
  clearPastedAttachments: () => void;

  // ✨ 任务模式状态 - 用于 Tools 按钮选择
  // 'complex' = 强制复杂任务流程，输出 json_blueprint
  // 'super_executor' = 超级执行者模式，外部 AI 代码自动执行
  // 'basic' = 基础分析流程，跳转技能中心
  // 'interactive' = NL2Vis 交互式可视化模式，输出 json_interactive_plot
  // null = 正常模式，由 Agent 自动判断
  taskMode: 'complex' | 'super_executor' | 'basic' | 'interactive' | null;
  setTaskMode: (mode: 'complex' | 'super_executor' | 'basic' | 'interactive' | null) => void;
  clearTaskMode: () => void;

  // ✨ Claude Code 会话状态
  claudeCodeSessionId: string | null;  // 当前 Claude Code 的会话 ID
  setClaudeCodeSessionId: (id: string | null) => void;
  clearClaudeCodeSession: () => void;  // 清除会话，下次启动新会话
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      // ✨ Default to null (no project selected)
      currentProjectId: null,
      setCurrentProjectId: (id) => {
        // 同步更新 localStorage，确保 page.tsx 可以读取
        if (id) {
          localStorage.setItem('autonome_current_project_id', id);
        } else {
          localStorage.removeItem('autonome_current_project_id');
        }
        set({ currentProjectId: id });
      },

      // Current session ID and title
      // ✨ 每次打开页面时清空，不自动加载历史会话
      currentSessionId: null,
      currentSessionTitle: null,
      setCurrentSessionId: (id, title = null) => set({
        currentSessionId: id,
        currentSessionTitle: title
      }),

      projectFiles: [],
      setProjectFiles: (files) => set({ projectFiles: files }),
      addProjectFile: (file) => set((state) => ({
        projectFiles: [...state.projectFiles, file]
      })),
      fetchProjectFiles: async (projectId?: string) => {
        let pid = projectId;
        if (!pid) {
          const stored = localStorage.getItem('autonome_current_project_id');
          pid = stored || undefined;
        }
        if (!pid) return;
        try {
          const data = await fetchAPI(`/projects/${pid}/files`);
          if (data.status === 'success') {
            set({ projectFiles: data.data });
          }
        } catch (e) {
          console.error('Failed to fetch project files:', e);
        }
      },

      mountedFiles: [],
      toggleMountFile: (file) => 
        set((state) => ({
          mountedFiles: state.mountedFiles.includes(file)
            ? state.mountedFiles.filter(f => f !== file)
            : [...state.mountedFiles, file]
        })),
        
      activeTool: null,
      toolParams: {},
      
      // When AI activates a tool, auto-initialize default parameters
      setActiveTool: (tool) => {
        if (!tool) {
          set({ activeTool: null, toolParams: {} });
          return;
        }
        const initialParams: Record<string, any> = {};
        Object.entries(tool.parameters).forEach(([key, param]) => {
          initialParams[key] = param.default;
        });
        set({ activeTool: tool, toolParams: initialParams });
      },
      
      updateToolParam: (key, value) =>
        set((state) => ({
          toolParams: { ...state.toolParams, [key]: value }
        })),

      // Pending chat attachments (from DataCenter batch selection)
      pendingChatAttachments: [],
      setPendingChatAttachments: (paths) => set({ pendingChatAttachments: paths }),
      addPendingChatAttachment: (path) => set((state) => ({
        pendingChatAttachments: [...state.pendingChatAttachments, path]
      })),
      removePendingChatAttachment: (path) => set((state) => ({
        pendingChatAttachments: state.pendingChatAttachments.filter(p => p !== path)
      })),
      clearPendingChatAttachments: () => set({ pendingChatAttachments: [] }),

      // ✨ 技能附件状态实现
      pendingChatSkill: null,
      setPendingChatSkill: (skill) => set({ pendingChatSkill: skill }),
      clearPendingChatSkill: () => set({ pendingChatSkill: null }),

      // ✨ 粘贴附件状态实现
      pastedAttachments: [],
      addPastedAttachment: (attachment) => set((state) => ({
        pastedAttachments: [...state.pastedAttachments, attachment]
      })),
      removePastedAttachment: (id) => set((state) => ({
        pastedAttachments: state.pastedAttachments.filter(a => a.id !== id)
      })),
      updatePastedAttachment: (id, updates) => set((state) => ({
        pastedAttachments: state.pastedAttachments.map(a =>
          a.id === id ? { ...a, ...updates } : a
        )
      })),
      clearPastedAttachments: () => set({ pastedAttachments: [] }),

      // ✨ 任务模式状态实现
      taskMode: null,
      setTaskMode: (mode) => set({ taskMode: mode }),
      clearTaskMode: () => set({ taskMode: null }),

      // ✨ Claude Code 会话状态实现
      claudeCodeSessionId: null,
      setClaudeCodeSessionId: (id) => set({ claudeCodeSessionId: id }),
      clearClaudeCodeSession: () => set({ claudeCodeSessionId: null }),
    }),
    {
      name: 'autonome-workspace-storage',
      // ✨ 只持久化 currentProjectId，不持久化 currentSessionId
      // 这样每次打开页面都是新对话，用户点击历史消息时再加载
      partialize: (state) => ({
        currentProjectId: state.currentProjectId,
      }),
    }
  )
);
