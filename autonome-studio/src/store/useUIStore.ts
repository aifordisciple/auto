import { create } from 'zustand';

// 定义所有可能的大屏视图枚举
export type OverlayView = 'none' | 'projects' | 'tasks' | 'settings' | 'control' | 'topup';

interface UIState {
  activeOverlay: OverlayView;
  setActiveOverlay: (view: OverlayView) => void;
  closeOverlay: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeOverlay: 'none',
  setActiveOverlay: (view) => set({ activeOverlay: view }),
  closeOverlay: () => set({ activeOverlay: 'none' }),
}));
