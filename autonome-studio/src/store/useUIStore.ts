import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UIState {
  isTaskCenterOpen: boolean;
  isSettingsOpen: boolean;
  isProjectCenterOpen: boolean;
  isControlPanelOpen: boolean;
  isDataCenterOpen: boolean;
  isSkillCenterOpen: boolean;

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
  openSkillCenter: () => void;
  closeSkillCenter: () => void;
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

      // ✨ 新增：默认设置为暗黑模式
      theme: 'dark',
      toggleTheme: () => set((state) => ({ theme: state.theme === 'light' ? 'dark' : 'light' })),
      setTheme: (theme) => set({ theme }),

      toggleTaskCenter: () => set((state) => ({ isTaskCenterOpen: !state.isTaskCenterOpen, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false })),
      toggleSettings: () => set((state) => ({ isSettingsOpen: !state.isSettingsOpen, isTaskCenterOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false })),
      toggleProjectCenter: () => set((state) => ({ isProjectCenterOpen: !state.isProjectCenterOpen, isTaskCenterOpen: false, isSettingsOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false })),
      toggleControlPanel: () => set((state) => ({ isControlPanelOpen: !state.isControlPanelOpen, isTaskCenterOpen: false, isSettingsOpen: false, isDataCenterOpen: false, isProjectCenterOpen: false, isSkillCenterOpen: false })),
      toggleDataCenter: () => set((state) => ({ isDataCenterOpen: !state.isDataCenterOpen, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false })),
      toggleSkillCenter: () => set((state) => ({ isSkillCenterOpen: !state.isSkillCenterOpen, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false })),
      openSkillCenter: () => set({ isSkillCenterOpen: true, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false }),
      closeSkillCenter: () => set({ isSkillCenterOpen: false }),

      closeAllOverlays: () => set({ isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false, isSkillCenterOpen: false })
    }),
    {
      name: 'autonome-ui-storage', // 开启持久化
      // ✨ 确保 theme 字段被存入 LocalStorage
      partialize: (state) => ({ theme: state.theme })
    }
  )
);
