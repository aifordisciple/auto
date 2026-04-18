/**
 * 新手引导组件
 *
 * P1 新手友好化：
 * - 首次访问显示功能卡片
 * - 渐进式披露：先展示核心功能
 * - 智能示例：可点击的示例输入
 */

'use client';

import { useState, useEffect, ReactNode } from 'react';
import { X, Sparkles, Database, BarChart3, Dna } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// 使用相对路径导入以避免测试环境路径别名问题
import { cn } from '../../lib/utils';

// ==========================================
// 类型定义
// ==========================================

export interface OnboardingStep {
  title: string;
  description: string;
  example: string;
  icon?: ReactNode;
}

interface OnboardingGuideProps {
  steps?: OnboardingStep[];
  onExampleClick?: (example: string) => void;
  onDismiss?: () => void;
  className?: string;
}

// ==========================================
// 默认引导步骤
// ==========================================

const DEFAULT_STEPS: OnboardingStep[] = [
  {
    title: '数据质控',
    description: '检查测序数据质量，发现异常样本',
    example: '分析我的测序数据质量',
    icon: <Database className="w-5 h-5" />,
  },
  {
    title: '基因表达分析',
    description: '比较不同组间的基因表达差异',
    example: '找出两组样本的差异基因',
    icon: <Dna className="w-5 h-5" />,
  },
  {
    title: '可视化绘图',
    description: '生成论文级图表',
    example: '绘制火山图展示差异基因',
    icon: <BarChart3 className="w-5 h-5" />,
  },
];

// 本地存储键名
const STORAGE_KEY = 'autonome_has_seen_onboarding';

// ==========================================
// 主组件
// ==========================================

export function OnboardingGuide({
  steps = DEFAULT_STEPS,
  onExampleClick,
  onDismiss,
  className,
}: OnboardingGuideProps) {
  // 是否显示引导
  const [isVisible, setIsVisible] = useState(false);

  // 检查是否已经看过引导
  useEffect(() => {
    const hasSeenOnboarding = localStorage.getItem(STORAGE_KEY);
    if (!hasSeenOnboarding) {
      setIsVisible(true);
    }
  }, []);

  // 处理关闭
  const handleDismiss = () => {
    setIsVisible(false);
    localStorage.setItem(STORAGE_KEY, 'true');
    onDismiss?.();
  };

  // 处理示例点击
  const handleExampleClick = (example: string) => {
    onExampleClick?.(example);
  };

  // 不显示时返回 null
  if (!isVisible) {
    return null;
  }

  // 空步骤时不渲染
  if (steps.length === 0) {
    return null;
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className={cn('w-full', className)}
      >
        {/* 引导卡片容器 */}
        <div className="bg-gradient-to-br from-blue-500/5 to-purple-500/5 border border-blue-500/20 rounded-2xl p-6 relative">
          {/* 关闭按钮 */}
          <button
            onClick={handleDismiss}
            className="absolute top-3 right-3 p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
            aria-label="关闭引导"
          >
            <X size={18} />
          </button>

          {/* 标题 */}
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-semibold text-neutral-200">
              快速开始
            </h2>
          </div>

          {/* 描述 */}
          <p className="text-sm text-neutral-400 mb-5">
            选择一个常用分析任务，或直接输入您的需求
          </p>

          {/* 引导步骤卡片 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {steps.map((step, index) => (
              <motion.div
                key={step.title}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
              >
                <button
                  onClick={() => handleExampleClick(step.example)}
                  className="w-full text-left p-4 bg-neutral-900/50 hover:bg-neutral-800/50 border border-neutral-800 hover:border-blue-500/30 rounded-xl transition-all group"
                >
                  {/* 图标和标题 */}
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-blue-400 group-hover:text-blue-300 transition-colors">
                      {step.icon || <Sparkles className="w-5 h-5" />}
                    </span>
                    <span className="font-medium text-neutral-200 group-hover:text-white transition-colors">
                      {step.title}
                    </span>
                  </div>

                  {/* 描述 */}
                  <p className="text-xs text-neutral-500 mb-3">
                    {step.description}
                  </p>

                  {/* 示例提示 */}
                  <div className="flex items-center gap-2 text-xs text-blue-400/70 group-hover:text-blue-300">
                    <span className="truncate">{step.example}</span>
                    <span className="text-neutral-600">→</span>
                  </div>
                </button>
              </motion.div>
            ))}
          </div>

          {/* 跳过按钮 */}
          <div className="mt-4 text-center">
            <button
              onClick={handleDismiss}
              className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
              aria-label="跳过引导"
            >
              跳过引导，直接开始
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

// ==========================================
// Hook: 重置引导状态
// ==========================================

export function useResetOnboarding() {
  return () => {
    localStorage.removeItem(STORAGE_KEY);
  };
}

// ==========================================
// Hook: 检查是否显示引导
// ==========================================

export function useShouldShowOnboarding() {
  const [shouldShow, setShouldShow] = useState(false);

  useEffect(() => {
    const hasSeenOnboarding = localStorage.getItem(STORAGE_KEY);
    setShouldShow(!hasSeenOnboarding);
  }, []);

  return shouldShow;
}

export default OnboardingGuide;