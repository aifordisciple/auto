import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Shortcut {
  id: string;
  name: string;
  description: string;
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  alt?: boolean;
}

interface ShortcutState {
  shortcuts: Record<string, Shortcut>;
  updateShortcut: (id: string, newShortcut: Partial<Shortcut>) => void;
  resetToDefault: () => void;
}

// 默认系统快捷键预设
const defaultShortcuts: Record<string, Shortcut> = {
  'new_chat': { id: 'new_chat', name: '新建对话', description: '快速开启一段全新的 AI 分析对话', key: 'n', meta: true },
  'toggle_project_center': { id: 'toggle_project_center', name: '切换项目中心', description: '打开或关闭工作区选择面板', key: 'p', meta: true },
  'toggle_data_center': { id: 'toggle_data_center', name: '切换数据中心', description: '打开或关闭右侧项目数据面板', key: 'd', meta: true },
  'toggle_task_center': { id: 'toggle_task_center', name: '切换任务中心', description: '查看后台超算节点的任务队列', key: 't', meta: true },
  'toggle_settings': { id: 'toggle_settings', name: '打开设置', description: '打开全局设置中心', key: ',', meta: true },
  'focus_input': { id: 'focus_input', name: '聚焦输入框', description: '快速将光标定位到聊天输入框', key: '/', ctrl: false },
};

export const useShortcutStore = create<ShortcutState>()(
  persist(
    (set) => ({
      shortcuts: defaultShortcuts,
      updateShortcut: (id, newShortcut) => set((state) => ({
        shortcuts: {
          ...state.shortcuts,
          [id]: { ...state.shortcuts[id], ...newShortcut }
        }
      })),
      resetToDefault: () => set({ shortcuts: defaultShortcuts }),
    }),
    {
      name: 'autonome-shortcuts-storage', // 持久化到 localStorage
    }
  )
);
