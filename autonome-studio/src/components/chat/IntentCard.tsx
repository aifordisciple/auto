"use client";

import { memo } from "react";
import { motion } from "framer-motion";
import {
  Lightbulb,
  Zap,
  Code,
  HelpCircle,
  Target,
  Wrench,
  ArrowRight,
  CheckCircle2,
  Sparkles
} from "lucide-react";

// ==========================================
// ✨ 意图识别数据类型定义
// ==========================================

export interface IntentCardData {
  intent_type: "explicit_skill" | "implicit_skill" | "live_coding" | "general_question";
  matched_skills?: Array<{
    skill_id: string;
    match_score: number;
    match_reason: string;
  }>;
  recommended_action?: "direct_execute" | "confirm_with_user" | "show_options";
  parameters_suggestion?: Record<string, unknown>;
  confidence?: number;
}

interface IntentCardProps {
  data: IntentCardData;
}

// ==========================================
// ✨ 意图类型配置
// ==========================================

const INTENT_CONFIG = {
  explicit_skill: {
    icon: Target,
    label: "明确技能调用",
    description: "检测到明确的技能调用意图",
    color: "emerald",
    bgColor: "bg-emerald-900/20",
    borderColor: "border-emerald-500/30",
    textColor: "text-emerald-400",
    iconBg: "bg-emerald-500/20"
  },
  implicit_skill: {
    icon: Lightbulb,
    label: "隐式技能推荐",
    description: "检测到可能匹配的技能需求",
    color: "amber",
    bgColor: "bg-amber-900/20",
    borderColor: "border-amber-500/30",
    textColor: "text-amber-400",
    iconBg: "bg-amber-500/20"
  },
  live_coding: {
    icon: Code,
    label: "实时编码",
    description: "将生成自定义代码实现",
    color: "blue",
    bgColor: "bg-blue-900/20",
    borderColor: "border-blue-500/30",
    textColor: "text-blue-400",
    iconBg: "bg-blue-500/20"
  },
  general_question: {
    icon: HelpCircle,
    label: "知识问答",
    description: "检测到知识问答型需求",
    color: "purple",
    bgColor: "bg-purple-900/20",
    borderColor: "border-purple-500/30",
    textColor: "text-purple-400",
    iconBg: "bg-purple-500/20"
  }
};

// ==========================================
// ✨ 意图卡片组件
// ==========================================

const IntentCard = memo(function IntentCard({ data }: IntentCardProps) {
  const config = INTENT_CONFIG[data.intent_type] || INTENT_CONFIG.live_coding;
  const IconComponent = config.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`${config.bgColor} border ${config.borderColor} rounded-lg p-3 mb-3`}
    >
      {/* 头部：意图类型标签 */}
      <div className="flex items-center gap-2 mb-2">
        <div className={`${config.iconBg} p-1.5 rounded-md`}>
          <IconComponent size={14} className={config.textColor} />
        </div>
        <span className={`text-sm font-medium ${config.textColor}`}>
          {config.label}
        </span>
        {data.confidence !== undefined && (
          <span className="text-xs text-neutral-500 ml-auto">
            置信度 {(data.confidence * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {/* 描述文本 */}
      <p className="text-xs text-neutral-400 mb-2">{config.description}</p>

      {/* 匹配的技能列表 */}
      {data.matched_skills && data.matched_skills.length > 0 && (
        <div className="space-y-1.5 mt-2 pt-2 border-t border-neutral-700/50">
          <div className="flex items-center gap-1 text-xs text-neutral-500">
            <Wrench size={10} />
            <span>推荐技能</span>
          </div>
          {data.matched_skills.map((skill, index) => (
            <div
              key={skill.skill_id}
              className="flex items-center gap-2 py-1.5 px-2 bg-neutral-800/50 rounded-md"
            >
              <div className="flex items-center gap-1.5 flex-1 min-w-0">
                <Sparkles size={12} className="text-blue-400 shrink-0" />
                <span className="text-xs text-neutral-300 font-mono truncate">
                  {skill.skill_id}
                </span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <div className="w-12 h-1.5 bg-neutral-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full"
                    style={{ width: `${Math.min(100, skill.match_score * 100)}%` }}
                  />
                </div>
                <span className="text-[10px] text-neutral-500 w-8 text-right">
                  {(skill.match_score * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 推荐操作 */}
      {data.recommended_action && (
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-neutral-700/50">
          <ArrowRight size={10} className="text-neutral-500" />
          <span className="text-xs text-neutral-400">
            {data.recommended_action === "direct_execute" && "将直接执行"}
            {data.recommended_action === "confirm_with_user" && "等待确认后执行"}
            {data.recommended_action === "show_options" && "将展示多个选项"}
          </span>
        </div>
      )}
    </motion.div>
  );
});

// ==========================================
// ✨ 解析函数：从消息内容中提取意图识别 JSON
// ==========================================

export function parseIntentCard(content: string): IntentCardData | null {
  if (!content) return null;

  try {
    // 匹配 ```json_intent ... ``` 块
    const jsonIntentMatch = content.match(/```json_intent\s*([\s\S]*?)```/);
    if (!jsonIntentMatch) return null;

    const jsonStr = jsonIntentMatch[1].trim();

    // 尝试解析 JSON
    const data = JSON.parse(jsonStr);

    // 验证必需字段
    if (!data.intent_type) return null;

    return {
      intent_type: data.intent_type,
      matched_skills: data.matched_skills || [],
      recommended_action: data.recommended_action,
      parameters_suggestion: data.parameters_suggestion,
      confidence: data.confidence
    };
  } catch (e) {
    // JSON 解析失败，返回 null
    return null;
  }
}

export { IntentCard };