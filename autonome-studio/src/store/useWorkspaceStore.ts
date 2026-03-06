import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://113.44.66.210:8000';

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
  id: number;
  filename: string;
  file_path: string;
  file_size: number;
  file_type: string;
  project_id: number;
  uploaded_at: string;
}

interface WorkspaceState {
  // Project context
  currentProjectId: number;
  setCurrentProjectId: (id: number) => void;
  
  // Current chat session
  currentSessionId: number | null;
  currentSessionTitle: string | null;
  setCurrentSessionId: (id: number | null, title?: string | null) => void;
  
  // Data Center: mounted files for AI context
  projectFiles: RealFile[];
  setProjectFiles: (files: RealFile[]) => void;
  addProjectFile: (file: RealFile) => void;
  fetchProjectFiles: (projectId: number) => Promise<void>;
  
  mountedFiles: string[];
  toggleMountFile: (file: string) => void;
  
  // Dynamic Toolbox: active tool and parameters
  activeTool: ToolSchema | null;
  toolParams: Record<string, any>;
  setActiveTool: (tool: ToolSchema | null) => void;
  updateToolParam: (key: string, value: any) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      // Default to project ID 1 (demo project)
      currentProjectId: 1,
      setCurrentProjectId: (id) => set({ currentProjectId: id }),

      // Current session ID and title
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
      fetchProjectFiles: async (projectId: number) => {
        const token = localStorage.getItem('autonome_access_token');
        try {
          const res = await fetch(`${BASE_URL}/api/projects/${projectId}/files`, {
            headers: { 'Authorization': `Bearer ${token}` }
          });
          const data = await res.json();
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
    }),
    {
      name: 'autonome-workspace-storage',
      partialize: (state) => ({ 
        currentProjectId: state.currentProjectId,
        currentSessionId: state.currentSessionId,
        currentSessionTitle: state.currentSessionTitle
      }),
    }
  )
);
