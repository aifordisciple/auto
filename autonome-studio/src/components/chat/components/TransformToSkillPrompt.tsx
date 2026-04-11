/**
 * 技能转化提示组件
 *
 * 在分析成功后提示用户将分析流程转化为可复用技能
 */
"use client";

import React, { useState } from "react";
import { Sparkles, Box, Loader2 } from "lucide-react";
import { motion } from "framer-motion";

interface TransformToSkillPromptProps {
  /** 会话 ID */
  sessionId: string;
  /** 关闭回调 */
  onClose: () => void;
  /** 转化回调 */
  onTransform: (skillName: string) => void;
}

/**
 * TransformToSkillPrompt - 技能转化提示组件
 * 显示分析成功后提示用户保存为技能的弹窗
 */
export const TransformToSkillPrompt: React.FC<TransformToSkillPromptProps> = ({
  sessionId,
  onClose,
  onTransform,
}) => {
  const [skillName, setSkillName] = useState("");
  const [isTransforming, setIsTransforming] = useState(false);

  const handleTransform = async () => {
    setIsTransforming(true);
    try {
      await onTransform(skillName);
    } finally {
      setIsTransforming(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4 mb-4 max-w-4xl mx-auto"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-emerald-500/20 rounded-lg">
          <Sparkles size={20} className="text-emerald-400" />
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-emerald-300 mb-1">
            🎉 分析成功！是否保存为可复用技能？
          </h4>
          <p className="text-xs text-emerald-400/80 mb-3">
            将此分析流程转化为标准技能，方便后续一键复用或分享给团队。
          </p>
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="技能名称（可选）"
              value={skillName}
              onChange={(e) => setSkillName(e.target.value)}
              className="flex-1 max-w-xs px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-sm text-emerald-200 placeholder:text-emerald-400/50 outline-none focus:border-emerald-400/50"
            />
            <button
              onClick={handleTransform}
              disabled={isTransforming}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-emerald-500 hover:bg-emerald-400 disabled:bg-emerald-500/50 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {isTransforming ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  转化中...
                </>
              ) : (
                <>
                  <Box size={14} />
                  保存为技能
                </>
              )}
            </button>
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-emerald-400 hover:text-emerald-300 text-sm transition-colors"
            >
              稍后再说
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default TransformToSkillPrompt;