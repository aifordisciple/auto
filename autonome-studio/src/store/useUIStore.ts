/**
 * useUIStore - UI 状态管理（性能优化版）
 *
 * 性能优化：
 * 1. 使用单一 activeOverlay 状态替代多个布尔值
 * 2. 减少 toggle 操作时的状态更新次数
 * 3. 使用 Immer 进行不可变更新
 * 4. 精确的状态订阅，避免不必要的重渲染
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { produce } from 'immer';

// ==========================================
// 类型定义
// ==========================================

type OverlayType =
  | 'taskCenter'
  | 'settings'
  | 'projectCenter'
  | 'controlPanel'
  | 'dataCenter'
  | 'skillCenter'
  | 'skillForge'
  | 'packageManager'
  | 'terminal'
  | 'userCenter'
  | 'chatSearch'
  | 'learningCenter'
  | null;

interface UIState {
  // ==========================================
  // 面板状态（使用单一状态替代多个布尔值）
  // ==========================================
  activeOverlay: OverlayType;

  // 兼容旧代码的布尔值（从 activeOverlay 派生）
  isTaskCenterOpen: boolean;
  isSettingsOpen: boolean;
  isProjectCenterOpen: boolean;
  isControlPanelOpen: boolean;
  isDataCenterOpen: boolean;
  isSkillCenterOpen: boolean;
  isSkillForgeOpen: boolean;
  isPackageManagerOpen: boolean;
  isTerminalOpen: boolean;
  isUserCenterOpen: boolean;
  isChatSearchOpen: boolean;
  isLearningCenterOpen: boolean;

  // ==========================================
  // 终端特殊状态
  // ==========================================
  isTerminalFullscreen: boolean;

  // ==========================================
  // 移动端菜单状态
  // ==========================================
  isMobileMenuOpen: boolean;

  // ==========================================
  // 自动执行策略开关
  // ==========================================
  autoExecuteStrategy: boolean;

  // ==========================================
  // 主题相关状态
  // ==========================================
  theme: 'light' | 'dark';

  // ==========================================
  // 技能过滤模式
  // ==========================================
  skillFilterMode: 'all' | 'basic';

  // ==========================================
  // 全局任务模式
  // ==========================================
  globalTaskMode: 'normal';

  // ==========================================
  // V2: 内联展开状态（替代全局弹窗）
  // ==========================================
  inlineExpansions: Record<string, boolean>;

  // ==========================================
  // 即席分析结果 → 数据中心联动
  // ==========================================
  /** 即席分析输出目录高亮路径（用于执行完成后引导用户到数据中心查看文件） */
  dataCenterHighlightPath: string | null;
  setDataCenterHighlightPath: (path: string | null) => void;

  // ==========================================
  // 操作方法
  // ==========================================
  // 移动端菜单
  toggleMobileMenu: () => void;
  closeMobileMenu: () => void;

  // 自动执行
  toggleAutoExecute: () => void;
  setAutoExecute: (value: boolean) => void;

  // 主题
  toggleTheme: () => void;
  setTheme: (theme: 'light' | 'dark') => void;

  // 技能过滤
  setSkillFilterMode: (mode: 'all' | 'basic') => void;

  // 面板切换（统一处理）
  toggleOverlay: (type: OverlayType) => void;
  openOverlay: (type: OverlayType) => void;
  closeOverlay: () => void;

  // 兼容旧 API 的方法
  toggleTaskCenter: () => void;
  toggleSettings: () => void;
  toggleProjectCenter: () => void;
  toggleControlPanel: () => void;
  toggleDataCenter: () => void;
  toggleSkillCenter: () => void;
  toggleSkillForge: () => void;
  togglePackageManager: () => void;
  toggleTerminal: () => void;
  toggleTerminalFullscreen: () => void;
  toggleUserCenter: () => void;
  openSkillCenter: () => void;
  closeSkillCenter: () => void;
  openDataCenter: () => void;
  openSkillForge: () => void;
  openPackageManager: () => void;
  openTerminal: () => void;
  closeTerminal: () => void;
  openUserCenter: () => void;
  openChatSearch: () => void;
  closeChatSearch: () => void;
  toggleLearningCenter: () => void;
  openLearningCenter: () => void;
  closeAllOverlays: () => void;

  // V2: 内联展开操作
  toggleInlineExpansion: (id: string) => void;
  setInlineExpansion: (id: string, expanded: boolean) => void;
  isInlineExpanded: (id: string) => boolean;
}

// ==========================================
// 辅助函数：根据 activeOverlay 计算布尔值
// ==========================================
const getOverlayFlags = (activeOverlay: OverlayType) => ({
  isTaskCenterOpen: activeOverlay === 'taskCenter',
  isSettingsOpen: activeOverlay === 'settings',
  isProjectCenterOpen: activeOverlay === 'projectCenter',
  isControlPanelOpen: activeOverlay === 'controlPanel',
  isDataCenterOpen: activeOverlay === 'dataCenter',
  isSkillCenterOpen: activeOverlay === 'skillCenter',
  isSkillForgeOpen: activeOverlay === 'skillForge',
  isPackageManagerOpen: activeOverlay === 'packageManager',
  isTerminalOpen: activeOverlay === 'terminal',
  isUserCenterOpen: activeOverlay === 'userCenter',
  isChatSearchOpen: activeOverlay === 'chatSearch',
  isLearningCenterOpen: activeOverlay === 'learningCenter',
});

// ==========================================
// Store 实现
// ==========================================
export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      // 初始状态
      activeOverlay: null,
      ...getOverlayFlags(null),

      isTerminalFullscreen: false,
      isMobileMenuOpen: false,
      autoExecuteStrategy: false,
      theme: 'dark',
      skillFilterMode: 'all',
      globalTaskMode: 'normal',
      inlineExpansions: {},
      dataCenterHighlightPath: null,
      setDataCenterHighlightPath: (path) => set({ dataCenterHighlightPath: path }),

      // ==========================================
      // 移动端菜单
      // ==========================================
      toggleMobileMenu: () => set(produce((state) => {
        state.isMobileMenuOpen = !state.isMobileMenuOpen;
      })),
      closeMobileMenu: () => set({ isMobileMenuOpen: false }),

      // ==========================================
      // 自动执行
      // ==========================================
      toggleAutoExecute: () => set(produce((state) => {
        state.autoExecuteStrategy = !state.autoExecuteStrategy;
      })),
      setAutoExecute: (value) => set({ autoExecuteStrategy: value }),

      // ==========================================
      // 主题
      // ==========================================
      toggleTheme: () => set(produce((state) => {
        state.theme = state.theme === 'light' ? 'dark' : 'light';
      })),
      setTheme: (theme) => set({ theme }),

      // ==========================================
      // 技能过滤
      // ==========================================
      setSkillFilterMode: (mode) => set({ skillFilterMode: mode }),

      // ==========================================
      // 统一面板操作（核心优化）
      // ==========================================
      toggleOverlay: (type) => set(produce((state) => {
        // 如果点击的是当前已打开的面板，则关闭
        if (state.activeOverlay === type) {
          state.activeOverlay = null;
        } else {
          state.activeOverlay = type;
        }
        // 更新布尔值
        Object.assign(state, getOverlayFlags(state.activeOverlay));
        // 关闭全屏终端
        if (type !== 'terminal') {
          state.isTerminalFullscreen = false;
        }
      })),

      openOverlay: (type) => set(produce((state) => {
        state.activeOverlay = type;
        Object.assign(state, getOverlayFlags(type));
      })),

      closeOverlay: () => set(produce((state) => {
        state.activeOverlay = null;
        Object.assign(state, getOverlayFlags(null));
      })),

      // ==========================================
      // 兼容旧 API 的方法
      // ==========================================
      toggleTaskCenter: () => get().toggleOverlay('taskCenter'),
      toggleSettings: () => get().toggleOverlay('settings'),
      toggleProjectCenter: () => get().toggleOverlay('projectCenter'),
      toggleControlPanel: () => get().toggleOverlay('controlPanel'),
      toggleDataCenter: () => get().toggleOverlay('dataCenter'),
      toggleSkillCenter: () => get().toggleOverlay('skillCenter'),
      toggleSkillForge: () => get().toggleOverlay('skillForge'),
      togglePackageManager: () => get().toggleOverlay('packageManager'),
      toggleTerminal: () => get().toggleOverlay('terminal'),
      toggleTerminalFullscreen: () => set(produce((state) => {
        state.isTerminalFullscreen = !state.isTerminalFullscreen;
      })),
      toggleUserCenter: () => get().toggleOverlay('userCenter'),

      openSkillCenter: () => get().openOverlay('skillCenter'),
      closeSkillCenter: () => get().closeOverlay(),
      openDataCenter: () => get().openOverlay('dataCenter'),
      openSkillForge: () => get().openOverlay('skillForge'),
      openPackageManager: () => get().openOverlay('packageManager'),
      openTerminal: () => get().openOverlay('terminal'),
      closeTerminal: () => set({ activeOverlay: null, isTerminalFullscreen: false, ...getOverlayFlags(null) }),
      openUserCenter: () => get().openOverlay('userCenter'),

      openChatSearch: () => get().openOverlay('chatSearch'),
      closeChatSearch: () => get().closeOverlay(),

      toggleLearningCenter: () => get().toggleOverlay('learningCenter'),
      openLearningCenter: () => get().openOverlay('learningCenter'),

      closeAllOverlays: () => set(produce((state) => {
        state.activeOverlay = null;
        state.isTerminalFullscreen = false;
        Object.assign(state, getOverlayFlags(null));
      })),

      // V2: 内联展开操作
      toggleInlineExpansion: (id) => set(produce((state) => {
        state.inlineExpansions = {
          ...state.inlineExpansions,
          [id]: !state.inlineExpansions[id],
        };
      })),
      setInlineExpansion: (id, expanded) => set(produce((state) => {
        state.inlineExpansions = {
          ...state.inlineExpansions,
          [id]: expanded,
        };
      })),
      isInlineExpanded: (id) => get().inlineExpansions[id] ?? false,
    }),
    {
      name: 'autonome-ui-storage',
      partialize: (state) => ({
        theme: state.theme,
        autoExecuteStrategy: state.autoExecuteStrategy,
        globalTaskMode: state.globalTaskMode
      })
    }
  )
);

// ==========================================
// 性能优化：精确订阅选择器
// ==========================================

/**
 * 订阅当前活动的面板
 * 用于组件判断自己是否应该显示
 */
export const useActiveOverlay = () => useUIStore((state) => state.activeOverlay);

/**
 * 订阅主题状态
 */
export const useTheme = () => useUIStore((state) => ({
  theme: state.theme,
  toggleTheme: state.toggleTheme,
  setTheme: state.setTheme,
}));

/**
 * 订阅全局任务模式
 */
export const useGlobalTaskMode = () => useUIStore((state) => ({
  globalTaskMode: state.globalTaskMode,
}));