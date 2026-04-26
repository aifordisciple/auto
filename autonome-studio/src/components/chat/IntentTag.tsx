/**
 * IntentTag — AI 消息意图识别文字标签（低调版）
 *
 * 在 AI 回复消息左上角显示意图类型的极简文字标记。
 * 使用语义分组配色：分析(靛蓝)、执行(翠绿)、交互(琥珀)、异常(玫红)。
 * 纯文字样式，无背景色块，非常低调。
 *
 * 数据来源：后端 SSE intent 事件 → useChatSync 捕获 → Message.intentLabel
 */
"use client";

import { memo } from "react";

// ==========================================
// ✨ 意图配置映射表
// intentType → { label(精简短名), group(语义分组), textColor(文字色) }
// ==========================================
const INTENT_CONFIG: Record<string, {
  label: string;
  group: string;
  textColor: string;
}> = {
  // --- 分析类（靛蓝） ---
  INTENT_DATA_PROBE: {
    label: "探查",
    group: "analysis",
    textColor: "text-indigo-400/70",
  },
  INTENT_VISUAL_PERCEPTION_AND_TWEAK: {
    label: "可视化",
    group: "analysis",
    textColor: "text-indigo-400/70",
  },
  INTENT_ADHOC_INTERACTIVE_ANALYSIS: {
    label: "即席",
    group: "analysis",
    textColor: "text-indigo-400/70",
  },
  INTENT_LITERATURE_MINING: {
    label: "文献",
    group: "analysis",
    textColor: "text-indigo-400/70",
  },
  // --- 执行类（翠绿） ---
  INTENT_EXPLICIT_EXEC: {
    label: "执行",
    group: "execution",
    textColor: "text-emerald-400/70",
  },
  INTENT_SKILL_FORGE: {
    label: "锻造",
    group: "execution",
    textColor: "text-emerald-400/70",
  },
  INTENT_WORKFLOW_ORCHESTRATE: {
    label: "工作流",
    group: "execution",
    textColor: "text-emerald-400/70",
  },
  INTENT_VERSION_CONTROL: {
    label: "版本",
    group: "execution",
    textColor: "text-emerald-400/70",
  },
  // --- 交互类（琥珀） ---
  INTENT_GENERAL_CHAT: {
    label: "问答",
    group: "interaction",
    textColor: "text-amber-400/70",
  },
  INTENT_COLLABORATION: {
    label: "协作",
    group: "interaction",
    textColor: "text-amber-400/70",
  },
  INTENT_SYSTEM_MACRO: {
    label: "指令",
    group: "interaction",
    textColor: "text-amber-400/70",
  },
  // --- 异常类（玫红） ---
  INTENT_DIAGNOSTIC_RECOVERY: {
    label: "诊断",
    group: "exception",
    textColor: "text-rose-400/70",
  },
  INTENT_SYSTEM_ASSET_OPS: {
    label: "运维",
    group: "exception",
    textColor: "text-rose-400/70",
  },
};

// ✨ 未知意图的兜底样式
const FALLBACK_TEXT_COLOR = "text-slate-400/70";

// ==========================================
// ✨ 辅助函数：根据 intentType 获取配置
// ==========================================
export function getIntentConfig(intentType: string): {
  label: string;
  group: string;
  textColor: string;
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
    textColor: FALLBACK_TEXT_COLOR,
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
      className={`${config.textColor} text-[10px] font-normal`}
    >
      {config.label}
    </span>
  );
});

export { IntentTag };