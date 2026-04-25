import { create } from 'zustand';
import { fetchAPI } from '@/lib/api';

export interface Task {
  task_id: string;
  name: string;
  tool_id: string;
  project_id: string;
  status: string;
  progress: number | null;
  progress_status?: string;  // ✨ 新增：用于区分 RETRY 状态
  attempt?: number;          // ✨ 新增：重试次数
  max_retries?: number;      // ✨ 新增：最大重试次数
  result: any;
  created_at: number;
}

interface TaskState {
  // 看板数据
  tasks: Task[];
  activeTaskId: string | null;
  logs: string[];
  isLoading: boolean;
  
  // Actions
  fetchTasks: () => Promise<void>;
  setActiveTaskId: (id: string | null) => void;
  appendLog: (log: string) => void;
  clearLogs: () => void;
  setLoading: (loading: boolean) => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: [],
  activeTaskId: null,
  logs: [],
  isLoading: false,
  
  fetchTasks: async () => {
    set({ isLoading: true });
    try {
      const data = await fetchAPI('/api/tasks/list');
      set({ tasks: data.tasks || [] });
    } catch (e) {
      console.error('Failed to fetch tasks:', e);
    } finally {
      set({ isLoading: false });
    }
  },
  
  setActiveTaskId: (id) => set({ activeTaskId: id, logs: [] }),
  appendLog: (log) => set((state) => ({ logs: [...state.logs, log] })),
  clearLogs: () => set({ logs: [] }),
  setLoading: (loading) => set({ isLoading: loading }),
}));
