import { create } from 'zustand';

interface UIState {
  isTaskCenterOpen: boolean;
  isSettingsOpen: boolean;
  isProjectCenterOpen: boolean;
  isDataCenterOpen: boolean;
  setActiveOverlay: (view: string) => void;
  toggleTaskCenter: () => void;
  toggleSettings: () => void;
  toggleProjectCenter: () => void;
  toggleDataCenter: () => void;
  closeAllOverlays: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  isTaskCenterOpen: false,
  isSettingsOpen: false,
  isProjectCenterOpen: false,
  isDataCenterOpen: false,

  setActiveOverlay: () => {},

  toggleTaskCenter: () => set((state) => ({ 
    isTaskCenterOpen: !state.isTaskCenterOpen, 
    isSettingsOpen: false, 
    isProjectCenterOpen: false, 
    isDataCenterOpen: false 
  })),
  
  toggleSettings: () => set((state) => ({ 
    isSettingsOpen: !state.isSettingsOpen, 
    isTaskCenterOpen: false, 
    isProjectCenterOpen: false, 
    isDataCenterOpen: false 
  })),
  
  toggleProjectCenter: () => set((state) => ({ 
    isProjectCenterOpen: !state.isProjectCenterOpen, 
    isTaskCenterOpen: false, 
    isSettingsOpen: false, 
    isDataCenterOpen: false 
  })),
  
  toggleDataCenter: () => set((state) => ({ 
    isDataCenterOpen: !state.isDataCenterOpen, 
    isTaskCenterOpen: false, 
    isSettingsOpen: false, 
    isProjectCenterOpen: false 
  })),
  
  closeAllOverlays: () => set({ 
    isTaskCenterOpen: false, 
    isSettingsOpen: false, 
    isProjectCenterOpen: false, 
    isDataCenterOpen: false 
  })
}));
