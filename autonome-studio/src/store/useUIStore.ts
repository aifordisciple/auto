import { create } from 'zustand';

interface UIState {
  isTaskCenterOpen: boolean;
  isSettingsOpen: boolean;
  isProjectCenterOpen: boolean;
  isControlPanelOpen: boolean;
  isDataCenterOpen: boolean;

  toggleTaskCenter: () => void;
  toggleSettings: () => void;
  toggleProjectCenter: () => void;
  toggleControlPanel: () => void;
  toggleDataCenter: () => void;
  closeAllOverlays: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  isTaskCenterOpen: false,
  isSettingsOpen: false,
  isProjectCenterOpen: false,
  isControlPanelOpen: false,
  isDataCenterOpen: false,

  toggleTaskCenter: () => set((state) => ({ isTaskCenterOpen: !state.isTaskCenterOpen, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false })),
  toggleSettings: () => set((state) => ({ isSettingsOpen: !state.isSettingsOpen, isTaskCenterOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false })),
  toggleProjectCenter: () => set((state) => ({ isProjectCenterOpen: !state.isProjectCenterOpen, isTaskCenterOpen: false, isSettingsOpen: false, isDataCenterOpen: false, isControlPanelOpen: false })),
  toggleControlPanel: () => set((state) => ({ isControlPanelOpen: !state.isControlPanelOpen, isTaskCenterOpen: false, isSettingsOpen: false, isDataCenterOpen: false, isProjectCenterOpen: false })),
  toggleDataCenter: () => set((state) => ({ isDataCenterOpen: !state.isDataCenterOpen, isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isControlPanelOpen: false })),
  
  closeAllOverlays: () => set({ isTaskCenterOpen: false, isSettingsOpen: false, isProjectCenterOpen: false, isDataCenterOpen: false, isControlPanelOpen: false })
}));
