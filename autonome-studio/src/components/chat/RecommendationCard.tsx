"use client";

import { memo, useState } from "react";
import { motion } from "framer-motion";
import {
  Lightbulb,
  Code,
  Zap,
  ArrowRight,
  CheckCircle,
  Sparkles,
  Loader2
} from "lucide-react";

// ==========================================
// ✨ 推荐选择卡片数据类型定义
// ==========================================

export interface SkillOption {
  type: "skill";
  skill_id: string;
  name: string;
  description: string;
  match_score: number;
}

export interface LiveCodingOption {
  type: "live_coding";
  name: string;
  description: string;
}

export interface DirectOption {
  type: "direct";
  name: string;
  description: string;
}

export type RecommendationOption = SkillOption | LiveCodingOption | DirectOption;

export interface RecommendationCardData {
  message_id: string;
  title?: string;
  options: RecommendationOption[];
}

// ==========================================
// ✨ 推荐卡片组件
// ==========================================

interface RecommendationCardProps {
  data: RecommendationCardData;
  onSelect: (option: RecommendationOption) => void;
  onCancel?: () => void;
}

/**
 * 推荐选择卡片组件
 *
 * 功能：
 * 1. 展示技能推荐列表（带匹配分数）
 * 2. 展示 Live Coding 选项
 * 3. 展示直接分析选项
 * 4. 用户选择后触发回调
 */
const RecommendationCard = memo(function RecommendationCard({
  data,
  onSelect,
  onCancel
}: RecommendationCardProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSelect = async (option: RecommendationOption, index: number) => {
    if (isLoading) return;

    setSelectedIndex(index);
    setIsLoading(true);

    try {
      onSelect(option);
    } finally {
      setIsLoading(false);
      setSelectedIndex(null);
    }
  };

  const getIcon = (type: string) => {
    switch (type) {
      case "skill":
        return <Lightbulb size={18} />;
      case "live_coding":
        return <Code size={18} />;
      case "direct":
        return <Zap size={18} />;
      default:
        return <ArrowRight size={18} />;
    }
  };

  const getIconBgColor = (type: string) => {
    switch (type) {
      case "skill":
        return "bg-blue-500/20 text-blue-400";
      case "live_coding":
        return "bg-green-500/20 text-green-400";
      case "direct":
        return "bg-purple-500/20 text-purple-400";
      default:
        return "bg-neutral-500/20 text-neutral-400";
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="bg-gradient-to-br from-neutral-900 to-neutral-800 border border-neutral-700/50 rounded-xl p-4 shadow-xl my-4"
    >
      {/* 标题 */}
      <div className="flex items-center gap-2 mb-4">
        <Sparkles size={18} className="text-blue-400" />
        <h3 className="text-base font-semibold text-white">
          {data.title || "请选择执行方式"}
        </h3>
      </div>

      {/* 选项列表 */}
      <div className="space-y-2">
        {data.options.map((option, index) => {
          const isSkill = option.type === "skill";
          const isSelected = selectedIndex === index;

          return (
            <motion.button
              key={
                isSkill
                  ? (option as SkillOption).skill_id
                  : `${option.type}-${index}`
              }
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
              onClick={() => handleSelect(option, index)}
              disabled={isLoading}
              className={`w-full text-left p-3 rounded-lg border transition-all ${
                isSelected
                  ? "border-blue-500 bg-blue-500/10"
                  : "border-neutral-700/50 bg-neutral-800/50 hover:border-blue-500/50 hover:bg-neutral-800"
              } ${isLoading && !isSelected ? "opacity-50" : ""}`}
            >
              <div className="flex items-start gap-3">
                {/* 图标 */}
                <div className={`p-2 rounded-lg ${getIconBgColor(option.type)}`}>
                  {getIcon(option.type)}
                </div>

                {/* 内容 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium text-white text-sm">
                      {option.name}
                    </h4>
                    {isSelected && (
                      <CheckCircle size={14} className="text-blue-400" />
                    )}
                    {isLoading && isSelected && (
                      <Loader2 size={14} className="text-blue-400 animate-spin" />
                    )}
                  </div>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    {option.description}
                  </p>

                  {/* 技能匹配分数 */}
                  {isSkill && (option as SkillOption).match_score > 0 && (
                    <div className="flex items-center gap-2 mt-2">
                      <div className="flex-1 h-1 bg-neutral-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all"
                          style={{
                            width: `${Math.min(100, (option as SkillOption).match_score * 100)}%`
                          }}
                        />
                      </div>
                      <span className="text-[10px] text-neutral-500 w-10 text-right">
                        {((option as SkillOption).match_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}
                </div>

                {/* 箭头 */}
                <ArrowRight
                  size={16}
                  className={`text-neutral-500 transition-transform ${
                    isSelected ? "translate-x-1 text-blue-400" : ""
                  }`}
                />
              </div>
            </motion.button>
          );
        })}
      </div>

      {/* 取消按钮 */}
      {onCancel && (
        <button
          onClick={onCancel}
          className="w-full mt-3 py-2 text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
        >
          取消
        </button>
      )}
    </motion.div>
  );
});

// ==========================================
// ✨ 解析函数
// ==========================================

/**
 * 解析推荐卡片数据
 */
export function parseRecommendationCard(data: any): RecommendationCardData | null {
  if (!data) return null;

  try {
    return {
      message_id: data.message_id || "",
      title: data.title,
      options: data.options || []
    };
  } catch {
    return null;
  }
}

export { RecommendationCard };
