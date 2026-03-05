import { create } from 'zustand';

export interface Task {
  task_id: string;
  name: string;
  tool_id: string;
  project_id: string;
  status: string;
  progress: number | null;
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
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/tasks/list`, {
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      const data = await res.json();
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
