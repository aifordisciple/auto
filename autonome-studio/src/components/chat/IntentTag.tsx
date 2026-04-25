/**
 * IntentTag — AI 消息意图识别胶囊标签
 *
 * 在 AI 回复消息左上角（头像右侧）显示意图类型的精简短名。
 * 使用语义分组配色：分析(靛蓝)、执行(翠绿)、交互(琥珀)、异常(玫红)。
 *
 * 数据来源：后端 SSE intent 事件 → useChatSync 捕获 → Message.intentLabel
 */
"use client";

import { memo } from "react";

// ==========================================
// ✨ 意图配置映射表
// intentType → { label(精简短名), group(语义分组), gradient(渐变色), shadow(投影色) }
// ==========================================
const INTENT_CONFIG: Record<string, {
  label: string;
  group: string;
  gradient: string;
  shadow: string;
}> = {
  // --- 分析类（靛蓝） ---
  INTENT_DATA_PROBE: {
    label: "探查",
    group: "analysis",
    gradient: "linear-gradient(135deg, #6366f1, #818cf8)",
    shadow: "0 1px 3px rgba(99,102,241,0.3)",
  },
  INTENT_VISUAL_PERCEPTION_AND_TWEAK: {
    label: "可视化",
    group: "analysis",
    gradient: "linear-gradient(135deg, #6366f1, #818cf8)",
    shadow: "0 1px 3px rgba(99,102,241,0.3)",
  },
  INTENT_ADHOC_INTERACTIVE_ANALYSIS: {
    label: "即席",
    group: "analysis",
    gradient: "linear-gradient(135deg, #6366f1, #818cf8)",
    shadow: "0 1px 3px rgba(99,102,241,0.3)",
  },
  INTENT_LITERATURE_MINING: {
    label: "文献",
    group: "analysis",
    gradient: "linear-gradient(135deg, #6366f1, #818cf8)",
    shadow: "0 1px 3px rgba(99,102,241,0.3)",
  },
  // --- 执行类（翠绿） ---
  INTENT_EXPLICIT_EXEC: {
    label: "执行",
    group: "execution",
    gradient: "linear-gradient(135deg, #10b981, #34d399)",
    shadow: "0 1px 3px rgba(16,185,129,0.3)",
  },
  INTENT_SKILL_FORGE: {
    label: "锻造",
    group: "execution",
    gradient: "linear-gradient(135deg, #10b981, #34d399)",
    shadow: "0 1px 3px rgba(16,185,129,0.3)",
  },
  INTENT_WORKFLOW_ORCHESTRATE: {
    label: "工作流",
    group: "execution",
    gradient: "linear-gradient(135deg, #10b981, #34d399)",
    shadow: "0 1px 3px rgba(16,185,129,0.3)",
  },
  INTENT_VERSION_CONTROL: {
    label: "版本",
    group: "execution",
    gradient: "linear-gradient(135deg, #10b981, #34d399)",
    shadow: "0 1px 3px rgba(16,185,129,0.3)",
  },
  // --- 交互类（琥珀） ---
  INTENT_GENERAL_CHAT: {
    label: "问答",
    group: "interaction",
    gradient: "linear-gradient(135deg, #f59e0b, #fbbf24)",
    shadow: "0 1px 3px rgba(245,158,11,0.3)",
  },
  INTENT_COLLABORATION: {
    label: "协作",
    group: "interaction",
    gradient: "linear-gradient(135deg, #f59e0b, #fbbf24)",
    shadow: "0 1px 3px rgba(245,158,11,0.3)",
  },
  INTENT_SYSTEM_MACRO: {
    label: "指令",
    group: "interaction",
    gradient: "linear-gradient(135deg, #f59e0b, #fbbf24)",
    shadow: "0 1px 3px rgba(245,158,11,0.3)",
  },
  // --- 异常类（玫红） ---
  INTENT_DIAGNOSTIC_RECOVERY: {
    label: "诊断",
    group: "exception",
    gradient: "linear-gradient(135deg, #ef4444, #f87171)",
    shadow: "0 1px 3px rgba(239,68,68,0.3)",
  },
  INTENT_SYSTEM_ASSET_OPS: {
    label: "运维",
    group: "exception",
    gradient: "linear-gradient(135deg, #ef4444, #f87171)",
    shadow: "0 1px 3px rgba(239,68,68,0.3)",
  },
};

// ✨ 未知意图的兜底样式（灰色胶囊 + 原始字符串）
const FALLBACK_STYLE = {
  gradient: "linear-gradient(135deg, #64748b, #94a3b8)",
  shadow: "0 1px 3px rgba(100,116,139,0.3)",
};

// ==========================================
// ✨ 辅助函数：根据 intentType 获取配置
// ==========================================
export function getIntentConfig(intentType: string): {
  label: string;
  group: string;
  gradient: string;
  shadow: string;
} {
  const config = INTENT_CONFIG[intentType];
  if (config) {
    return config;
  }
  // 兜底：显示原始 intent 字符串（去掉 INTENT_ 前缀）
  const shortLabel = intentType
    .replace("INTENT_", "")
    .replace("_", " ")
    .toLowerCase();
  return {
    label: shortLabel,
    group: "unknown",
    ...FALLBACK_STYLE,
  };
}

// ==========================================
// ✨ IntentTag 组件
// ==========================================
interface IntentTagProps {
  /** 后端意图类型字符串，如 INTENT_DATA_PROBE */
  intentType: string;
}

const IntentTag = memo(function IntentTag({ intentType }: IntentTagProps) {
  const config = getIntentConfig(intentType);

  return (
    <span
      style={{
        background: config.gradient,
        boxShadow: config.shadow,
      }}
      className="text-white text-[11px] px-2.5 py-0.5 rounded-xl font-medium tracking-wide inline-flex items-center"
    >
      {config.label}
    </span>
  );
});

export { IntentTag };