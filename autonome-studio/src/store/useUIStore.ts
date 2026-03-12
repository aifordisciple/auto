import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UIState {
  isTaskCenterOpen: boolean;
  isSettingsOpen: boolean;
  isProjectCenterOpen: boolean;
  isControlPanelOpen: boolean;
  isDataCenterOpen: boolean;
  isSkillCenterOpen: boolean;
  isSkillForgeOpen: boolean;

  // ✨ 自动执行策略开关
  autoExecuteStrategy: boolean;
  toggleAutoExecute: () => void;
  setAutoExecute: (value: boolean) => void;

  // ✨ 新增主题相关的状态
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  setTheme: (theme: 'light' | 'dark') => void;

  toggleTaskCenter: () => void;
  toggleSettings: () => void;
  toggleProjectCenter: () => void;
  toggleControlPanel: () => void;
  toggleDataCenter: () => void;
  toggleSkillCenter: () => void;
  toggleSkillForge: () => void;
  openSkillCenter: () => void;
  closeSkillCenter: () => void;
  openDataCenter: () => void;
  openSkillForge: () => void;
  closeAllOverlays: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      isTaskCenterOpen: false,
      isSettingsOpen: false,
      isProjectCenterOpen: false,
      isControlPanelOpen: false,
      isDataCenterOpen: false,
      isSkillCenterOpen: false,
      isSkillForgeOpen: false,

      // ✨ 自动执行策略默认关闭
      autoExecuteStrategy: false,
      toggleAutoExecute: () => set((state) => ({ autoExecuteStrategy: !state.autoExecuteStrategy })),
      setAutoExecute: (value) => set({ autoExecuteStrategy: value }),

      // ✨ 新增：默认设置为暗黑模式
      theme: 'dark',
      toggleTheme: () => set((state) => ({ theme: state.theme === 'light' ? 'dark' : 'light' })),
      setTheme: (theme) => set({ theme }),

      toggleTaskCenter: () => set((state) => ({ isTaskCenterOpen: !state.isTaskCenterOpen, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false, isSkillForgeOpen: false })),
      toggleSettings: () => set((state) => ({ isSettingsOpen: !state.isSettingsOpen, isTaskCenterOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false, isSkillForgeOpen: false })),
      toggleProjectCenter: () => set((state) => ({ isProjectCenterOpen: !state.isProjectCenterOpen, isTaskCenterOpen: false, isSettingsOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false, isSkillForgeOpen: false })),
      toggleControlPanel: () => set((state) => ({ isControlPanelOpen: !state.isControlPanelOpen, isTaskCenterOpen: false, isSettingsOpen: false, isDataCenterOpen: false, isProjectCenterOpen: false, isSkillCenterOpen: false, isSkillForgeOpen: false })),
      toggleDataCenter: () => set((state) => ({ isDataCenterOpen: !state.isDataCenterOpen, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false, isSkillForgeOpen: false })),
      toggleSkillCenter: () => set((state) => ({ isSkillCenterOpen: !state.isSkillCenterOpen, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillForgeOpen: false })),
      toggleSkillForge: () => set((state) => ({ isSkillForgeOpen: !state.isSkillForgeOpen, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false })),
      openSkillCenter: () => set({ isSkillCenterOpen: true, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillForgeOpen: false }),
      closeSkillCenter: () => set({ isSkillCenterOpen: false }),
      openDataCenter: () => set({ isDataCenterOpen: true, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillForgeOpen: false }),
      openSkillForge: () => set({ isSkillForgeOpen: true, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillForgeOpen: false }),

      closeAllOverlays: () => set({ isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false, isSkillForgeOpen: false })
    }),
    {
      name: 'autonome-ui-storage', // 开启持久化
      // ✨ 确保 theme 和 autoExecuteStrategy 字段被存入 LocalStorage
      partialize: (state) => ({ theme: state.theme, autoExecuteStrategy: state.autoExecuteStrategy })
    }
  )
);