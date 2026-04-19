/**
 * SkillDraftCard - 技能草稿卡片组件
 *
 * 显示 AI 生成的技能草稿预览
 * 提供测试和发布按钮
 */
"use client";

import { memo, useState, useCallback } from 'react';
import {
  Wrench,
  Play,
  Upload,
  FileCode,
  CheckCircle,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// ==========================================
// 类型定义
// ==========================================

interface SkillDraftCardProps {
  /** 技能 ID */
  skillId: string;
  /** 技能名称 */
  name: string;
  /** 技能描述 */
  description?: string;
  /** 执行器类型 */
  executorType?: string;
  /** 草稿 SKILL.md 内容 */
  skillContent?: string;
  /** 测试回调 */
  onTest?: (skillId: string) => Promise<void>;
  /** 发布回调 */
  onPublish?: (skillId: string) => Promise<void>;
}

// ==========================================
// 主组件
// ==========================================

export const SkillDraftCard = memo(function SkillDraftCard({
  skillId,
  name,
  description,
  executorType,
  skillContent,
  onTest,
  onPublish,
}: SkillDraftCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);

  // 测试技能
  const handleTest = useCallback(async () => {
    if (!onTest) return;
    setIsTesting(true);
    setTestResult(null);
    try {
      await onTest(skillId);
      setTestResult('success');
    } catch {
      setTestResult('error');
    } finally {
      setIsTesting(false);
    }
  }, [onTest, skillId]);

  // 发布技能
  const handlePublish = useCallback(async () => {
    if (!onPublish) return;
    setIsPublishing(true);
    try {
      await onPublish(skillId);
    } finally {
      setIsPublishing(false);
    }
  }, [onPublish, skillId]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="w-full bg-[#1a1a1b] border border-neutral-700/60 rounded-xl overflow-hidden shadow-md"
    >
      {/* 卡片头部 */}
      <div className="flex items-center justify-between px-4 py-3 bg-neutral-800/50">
        <div className="flex items-center gap-3">
          <Wrench size={16} className="text-purple-400" />
          <span className="text-sm font-medium text-neutral-200">{name}</span>
          {executorType && (
            <span className="px-2 py-0.5 rounded-full bg-purple-900/30 text-[10px] text-purple-400 font-mono">
              {executorType}
            </span>
          )}
          {testResult === 'success' && (
            <CheckCircle size={14} className="text-emerald-400" />
          )}
          {testResult === 'error' && (
            <AlertCircle size={14} className="text-red-400" />
          )}
        </div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1 hover:bg-neutral-700/50 rounded transition-colors"
        >
          {isExpanded ? <ChevronDown size={14} className="text-neutral-500" /> : <ChevronRight size={14} className="text-neutral-500" />}
        </button>
      </div>

      {/* 描述 */}
      {description && (
        <div className="px-4 py-2 text-xs text-neutral-400 border-b border-neutral-800/50">
          {description}
        </div>
      )}

      {/* SKILL.md 内容预览 */}
      <AnimatePresence>
        {isExpanded && skillContent && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="p-3 border-t border-neutral-800/50">
              <div className="flex items-center gap-2 mb-2">
                <FileCode size={12} className="text-neutral-500" />
                <span className="text-[10px] text-neutral-500 font-mono">SKILL.md</span>
              </div>
              <pre className="text-xs text-neutral-300 font-mono bg-neutral-900/80 p-3 rounded-lg max-h-48 overflow-y-auto custom-scrollbar whitespace-pre-wrap break-words">
                {skillContent}
              </pre>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 操作按钮栏 */}
      <div className="flex items-center gap-2 px-4 py-2 border-t border-neutral-800/50 bg-neutral-900/30">
        {/* 测试按钮 */}
        {onTest && (
          <button
            onClick={handleTest}
            disabled={isTesting || isPublishing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600/80 hover:bg-emerald-600 disabled:bg-emerald-800/50 text-white text-xs rounded-lg transition-colors"
          >
            {isTesting ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Play size={12} />
            )}
            测试
          </button>
        )}

        {/* 发布按钮 */}
        {onPublish && (
          <button
            onClick={handlePublish}
            disabled={isPublishing || isTesting || testResult !== 'success'}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600/80 hover:bg-purple-600 disabled:bg-purple-800/50 disabled:text-neutral-500 text-white text-xs rounded-lg transition-colors"
          >
            {isPublishing ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Upload size={12} />
            )}
            发布
          </button>
        )}

        {/* 状态提示 */}
        {testResult === 'success' && (
          <span className="ml-auto text-[10px] text-emerald-400">测试通过，可以发布</span>
        )}
        {testResult === 'error' && (
          <span className="ml-auto text-[10px] text-red-400">测试失败，请检查</span>
        )}
      </div>
    </motion.div>
  );
});

SkillDraftCard.displayName = 'SkillDraftCard';

export default SkillDraftCard;
