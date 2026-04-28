/**
 * useUserProfileStore - 用户画像与自适应体验状态管理
 *
 * 核心理念：自动检测用户熟练度（新手 vs 专家），动态调整 UI 呈现方式。
 *
 * 检测策略（自动积累证据）：
 * - 用户编辑过即席分析代码 → 专家倾向 +1
 * - 用户使用过技能中心 → 专家倾向 +1
 * - 用户查看过原始日志 → 专家倾向 +1
 * - 用户手动切换到专家/新手模式 → 直接锁定
 *
 * 模式影响：
 * | 特性 | 新手模式 | 专家模式 |
 * |------|---------|---------|
 * | 代码可见性 | 默认隐藏 | 默认展示 |
 * | 参数描述 | 自然语言 | 技术参数名 |
 * | 日志详细度 | 进度+关键步骤 | 完整原始日志 |
 * | 代码编辑器 | 不可编辑 | Monaco 语法高亮 |
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// ==========================================
// 类型定义
// ==========================================

/** 用户熟练度模式 */
export type ProficiencyMode = 'beginner' | 'expert';

/** 证据信号 */
interface ProfileSignals {
  /** 是否编辑过即席分析代码 */
  hasEditedCode: boolean;
  /** 是否使用过技能中心 */
  hasUsedSkillCenter: boolean;
  /** 是否查看过原始/完整日志 */
  hasViewedRawLogs: boolean;
  /** 用户是否手动锁定模式 */
  modeLocked: boolean;
}

interface UserProfileState {
  // === 模式状态 ===
  /** 当前模式（如果 modeLocked 为 true，此值不会自动切换） */
  mode: ProficiencyMode;
  /** 用户手动锁定的模式（null 表示自动检测） */
  lockedMode: ProficiencyMode | null;

  // === 行为信号 ===
  signals: ProfileSignals;

  // === 自适应偏好 ===
  /** 代码区默认是否展开 */
  codeExpandedByDefault: boolean;
  /** 日志默认 Tab */
  defaultLogTab: 'progress' | 'analysis' | 'all';

  // === Actions ===
  /** 记录代码编辑行为 → 专家倾向 */
  recordCodeEdit: () => void;
  /** 记录技能中心使用 → 专家倾向 */
  recordSkillCenterUse: () => void;
  /** 记录原始日志查看 → 专家倾向 */
  recordRawLogView: () => void;
  /** 手动切换到指定模式（锁定） */
  setMode: (mode: ProficiencyMode) => void;
  /** 解锁模式，恢复自动检测 */
  unlockMode: () => void;
  /** 重置所有信号 */
  resetProfile: () => void;
}

// ==========================================
// 信号阈值：达到此数量即切换为专家模式
// ==========================================
const EXPERT_THRESHOLD = 2;

function computeMode(signals: ProfileSignals, lockedMode: ProficiencyMode | null): ProficiencyMode {
  if (lockedMode) return lockedMode;

  const score =
    (signals.hasEditedCode ? 1 : 0) +
    (signals.hasUsedSkillCenter ? 1 : 0) +
    (signals.hasViewedRawLogs ? 1 : 0);

  return score >= EXPERT_THRESHOLD ? 'expert' : 'beginner';
}

function computeAdaptivePreferences(mode: ProficiencyMode) {
  return {
    codeExpandedByDefault: mode === 'expert',
    defaultLogTab: (mode === 'expert' ? 'all' : 'progress') as 'progress' | 'all' | 'analysis',
  };
}

// ==========================================
// 默认初始状态
// ==========================================
const DEFAULT_SIGNALS: ProfileSignals = {
  hasEditedCode: false,
  hasUsedSkillCenter: false,
  hasViewedRawLogs: false,
  modeLocked: false,
};

// ==========================================
// Store 创建
// ==========================================
export const useUserProfileStore = create<UserProfileState>()(
  persist(
    (set, get) => ({
      mode: 'beginner',
      lockedMode: null,
      signals: { ...DEFAULT_SIGNALS },
      ...computeAdaptivePreferences('beginner'),

      recordCodeEdit: () => {
        const { signals, lockedMode } = get();
        if (signals.hasEditedCode) return; // 已记录，避免重复
        const newSignals = { ...signals, hasEditedCode: true };
        const mode = computeMode(newSignals, lockedMode);
        set({
          signals: newSignals,
          mode,
          ...computeAdaptivePreferences(mode),
        });
      },

      recordSkillCenterUse: () => {
        const { signals, lockedMode } = get();
        if (signals.hasUsedSkillCenter) return;
        const newSignals = { ...signals, hasUsedSkillCenter: true };
        const mode = computeMode(newSignals, lockedMode);
        set({
          signals: newSignals,
          mode,
          ...computeAdaptivePreferences(mode),
        });
      },

      recordRawLogView: () => {
        const { signals, lockedMode } = get();
        if (signals.hasViewedRawLogs) return;
        const newSignals = { ...signals, hasViewedRawLogs: true };
        const mode = computeMode(newSignals, lockedMode);
        set({
          signals: newSignals,
          mode,
          ...computeAdaptivePreferences(mode),
        });
      },

      setMode: (mode: ProficiencyMode) => {
        set({
          mode,
          lockedMode: mode,
          signals: { ...get().signals, modeLocked: true },
          ...computeAdaptivePreferences(mode),
        });
      },

      unlockMode: () => {
        const { signals } = get();
        const newSignals = { ...signals, modeLocked: false };
        const mode = computeMode(newSignals, null);
        set({
          mode,
          lockedMode: null,
          signals: newSignals,
          ...computeAdaptivePreferences(mode),
        });
      },

      resetProfile: () => {
        set({
          mode: 'beginner',
          lockedMode: null,
          signals: { ...DEFAULT_SIGNALS },
          ...computeAdaptivePreferences('beginner'),
        });
      },
    }),
    {
      name: 'autonome-user-profile',
      partialize: (state) => ({
        mode: state.mode,
        lockedMode: state.lockedMode,
        signals: state.signals,
      }),
    }
  )
);
