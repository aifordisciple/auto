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
  /**
   * 跨平台修饰键：Mac 上映射为 ⌘Cmd，Windows/Linux 上映射为 Ctrl
   * 优先级高于单独的 meta/ctrl 字段，设置后 meta/ctrl 会被忽略
   */
  metaOrCtrl?: boolean;
}

interface ShortcutState {
  shortcuts: Record<string, Shortcut>;
  updateShortcut: (id: string, newShortcut: Partial<Shortcut>) => void;
  resetToDefault: () => void;
}

// 默认系统快捷键预设
// 设计原则：使用 metaOrCtrl 确保 Mac(⌘) 和 Windows(Ctrl) 都能舒适使用
const defaultShortcuts: Record<string, Shortcut> = {
  'new_chat': { id: 'new_chat', name: '新建对话', description: '快速开启一段全新的 AI 分析对话', key: 'n', metaOrCtrl: true },
  'toggle_project_center': { id: 'toggle_project_center', name: '切换项目中心', description: '打开或关闭工作区选择面板', key: 'p', metaOrCtrl: true },
  'toggle_data_center': { id: 'toggle_data_center', name: '切换数据中心', description: '打开或关闭右侧项目数据面板', key: 'd', metaOrCtrl: true },
  'toggle_task_center': { id: 'toggle_task_center', name: '切换任务中心', description: '查看后台超算节点的任务队列', key: 't', metaOrCtrl: true },
  'toggle_settings': { id: 'toggle_settings', name: '打开设置', description: '打开全局设置中心', key: ',', metaOrCtrl: true },
  'focus_input': { id: 'focus_input', name: '聚焦输入框', description: '快速将光标定位到聊天输入框', key: '/' },
  'toggle_left_sidebar': { id: 'toggle_left_sidebar', name: '切换左侧栏', description: '展开或收起左侧导航面板', key: 'b', metaOrCtrl: true },
  'toggle_right_sidebar': { id: 'toggle_right_sidebar', name: '切换右侧栏', description: '展开或收起右侧数据面板', key: 'j', metaOrCtrl: true },
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
      name: 'autonome-shortcuts-storage',
      // ✨ 合并策略：将默认快捷键与已保存的合并，确保新添加的快捷键也能显示
      // 同时自动升级旧格式（meta/ctrl）为跨平台 metaOrCtrl 格式
      merge: (persisted, current) => {
        const persistedShortcuts = (persisted as any)?.shortcuts || {};

        // 旧格式升级：将仅有 meta:true 或 ctrl:true 的快捷键自动转为 metaOrCtrl:true
        const upgradedShortcuts: Record<string, Shortcut> = {};
        for (const [id, sc] of Object.entries(persistedShortcuts) as [string, Shortcut][]) {
          // 如果已有 metaOrCtrl 字段，保持不变
          if (sc.metaOrCtrl) {
            upgradedShortcuts[id] = sc;
            continue;
          }
          // 旧格式 meta:true → metaOrCtrl:true（Mac 用户之前录制的 ⌘ 快捷键）
          // 旧格式 ctrl:true → metaOrCtrl:true（Windows 用户之前录制的 Ctrl 快捷键）
          if (sc.meta || sc.ctrl) {
            const { meta, ctrl, ...rest } = sc;
            upgradedShortcuts[id] = { ...rest, metaOrCtrl: true };
          } else {
            upgradedShortcuts[id] = sc;
          }
        }

        return {
          ...current,
          shortcuts: {
            ...defaultShortcuts,       // 先放默认值（确保新快捷键存在）
            ...upgradedShortcuts,      // 再用升级后的用户保存值覆盖
          }
        };
      },
    }
  )
);
