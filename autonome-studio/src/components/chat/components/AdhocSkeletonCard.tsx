'use client'

import { useEffect, useState } from 'react';
import { Check, Loader2, FileText, Code, Settings, Sparkles, ShieldCheck } from 'lucide-react';

/**
 * AdhocSkeletonCard — 即席分析策略生成进度卡片。
 *
 * 当后端流式生成策略包时，通过 adhoc_status 事件推送阶段变更，
 * 前端消费这些事件实现 5 阶段渐进式进度指示，替代原来的脉冲骨架屏。
 *
 * 5 个阶段：
 * 1. understanding — 理解需求
 * 2. planning — 设计策略
 * 3. coding — 生成代码
 * 4. params — 构建参数
 * 5. validating — 校验策略包
 */

interface StageInfo {
  stage: string;
  message: string;
  timestamp: number;
}

interface AdhocSkeletonCardProps {
  /** 从 adhoc_status parts 中提取的阶段事件列表 */
  stages?: StageInfo[];
}

const STAGE_CONFIG: Record<string, { icon: typeof Sparkles; label: string }> = {
  understanding: { icon: Sparkles, label: '理解需求' },
  planning: { icon: FileText, label: '设计策略' },
  coding: { icon: Code, label: '生成代码' },
  params: { icon: Settings, label: '构建参数' },
  validating: { icon: ShieldCheck, label: '校验策略' },
};

const STAGE_ORDER = ['understanding', 'planning', 'coding', 'params', 'validating'];

export function AdhocSkeletonCard({ stages = [] }: AdhocSkeletonCardProps) {
  // 当前活跃阶段（最新的已完成或进行中）
  const currentStage = stages.length > 0 ? stages[stages.length - 1].stage : 'understanding';
  const currentStageIdx = STAGE_ORDER.indexOf(currentStage);

  // 阶段完成的动画延迟
  const [animatedStages, setAnimatedStages] = useState<Set<string>>(new Set());

  useEffect(() => {
    // 当前阶段之前的阶段标记为完成
    const completed = new Set<string>();
    for (let i = 0; i < currentStageIdx; i++) {
      completed.add(STAGE_ORDER[i]);
    }
    setAnimatedStages(completed);
  }, [currentStage, currentStageIdx]);

  return (
    <div className="my-3 rounded-xl border border-indigo-500/30 bg-white dark:bg-[#1a1a1c] shadow-sm overflow-hidden">
      {/* 标题区 — 显示当前阶段信息 */}
      <div className="bg-indigo-50/30 dark:bg-indigo-900/10 p-4 border-b border-indigo-100/50 dark:border-indigo-500/10">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            {/* 脉冲环 */}
            <div className="absolute inset-0 rounded-full border-2 border-indigo-400 animate-ping opacity-30" />
          </div>
          <div>
            <div className="text-sm font-semibold text-indigo-700 dark:text-indigo-300">
              ⚡ 即席分析策略生成中
            </div>
            <div className="text-xs text-gray-500 dark:text-zinc-400 mt-0.5">
              {stages.length > 0 ? stages[stages.length - 1].message : '正在理解您的分析需求...'}
            </div>
          </div>
        </div>
      </div>

      {/* 5 阶段进度指示器 */}
      <div className="p-4">
        <div className="flex items-center gap-2">
          {STAGE_ORDER.map((stage, idx) => {
            const config = STAGE_CONFIG[stage];
            const Icon = config.icon;
            const isCompleted = idx < currentStageIdx;
            const isCurrent = idx === currentStageIdx;
            const isPending = idx > currentStageIdx;

            return (
              <div key={stage} className="flex-1 flex flex-col items-center">
                {/* 连接线 + 图标 */}
                <div className="flex items-center w-full">
                  {/* 左侧连接线 */}
                  {idx > 0 && (
                    <div
                      className={`flex-1 h-0.5 ${
                        isCompleted || isCurrent
                          ? 'bg-indigo-400'
                          : 'bg-gray-200 dark:bg-zinc-700'
                      }`}
                    />
                  )}
                  {/* 阶段图标 */}
                  <div
                    className={`relative w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                      isCompleted
                        ? 'bg-indigo-500 text-white'
                        : isCurrent
                        ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400 ring-2 ring-indigo-400'
                        : 'bg-gray-100 dark:bg-zinc-800 text-gray-400 dark:text-zinc-500'
                    }`}
                  >
                    {isCompleted ? (
                      <Check className="w-4 h-4" />
                    ) : isCurrent ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Icon className="w-4 h-4" />
                    )}
                  </div>
                  {/* 右侧连接线 */}
                  {idx < STAGE_ORDER.length - 1 && (
                    <div
                      className={`flex-1 h-0.5 ${
                        isCompleted
                          ? 'bg-indigo-400'
                          : 'bg-gray-200 dark:bg-zinc-700'
                      }`}
                    />
                  )}
                </div>
                {/* 阶段标签 */}
                <span
                  className={`text-[10px] mt-1.5 text-center leading-tight ${
                    isCurrent
                      ? 'text-indigo-600 dark:text-indigo-400 font-medium'
                      : isCompleted
                      ? 'text-indigo-500 dark:text-indigo-400'
                      : 'text-gray-400 dark:text-zinc-500'
                  }`}
                >
                  {config.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 策略/代码/参数内容预览区 — 默认折叠占位 */}
      <div className="px-4 pb-4 space-y-2">
        {/* 策略预览 */}
        <div className="rounded-md bg-gray-50 dark:bg-[#1e1e20] p-3">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-xs text-gray-500">策略描述</span>
            {currentStageIdx >= 1 && (
              <span className="text-[10px] text-green-500 flex items-center gap-0.5">
                <Check className="w-3 h-3" /> 已完成
              </span>
            )}
          </div>
          {currentStageIdx >= 1 ? (
            <div className="text-xs text-gray-600 dark:text-zinc-300 animate-in fade-in duration-300">
              策略已生成，正在构建代码...
            </div>
          ) : (
            <div className="h-3 w-3/4 bg-gray-200 dark:bg-zinc-700 rounded animate-pulse" />
          )}
        </div>

        {/* 代码预览 */}
        <div className="rounded-md bg-gray-50 dark:bg-[#1e1e20] p-3">
          <div className="flex items-center gap-2 mb-2">
            <Code className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-xs text-gray-500">分析代码</span>
            {(currentStageIdx >= 2 || currentStageIdx === 1) && currentStageIdx < 2 && (
              <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
            )}
            {currentStageIdx >= 2 && (
              <span className="text-[10px] text-green-500 flex items-center gap-0.5">
                <Check className="w-3 h-3" /> 已完成
              </span>
            )}
          </div>
          {currentStageIdx >= 2 ? (
            <div className="text-xs text-gray-600 dark:text-zinc-300 animate-in fade-in duration-300">
              代码已生成，正在构建参数表单...
            </div>
          ) : (
            <div className="h-3 w-1/2 bg-gray-200 dark:bg-zinc-700 rounded animate-pulse" />
          )}
        </div>

        {/* 参数预览 */}
        <div className="rounded-md bg-gray-50 dark:bg-[#1e1e20] p-3">
          <div className="flex items-center gap-2 mb-2">
            <Settings className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-xs text-gray-500">参数表单</span>
            {currentStageIdx >= 3 && (
              <span className="text-[10px] text-green-500 flex items-center gap-0.5">
                <Check className="w-3 h-3" /> 已完成
              </span>
            )}
            {currentStageIdx === 3 && (
              <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
            )}
          </div>
          {currentStageIdx >= 3 ? (
            <div className="text-xs text-gray-600 dark:text-zinc-300 animate-in fade-in duration-300">
              参数已构建，正在校验...
            </div>
          ) : (
            <div className="h-3 w-2/3 bg-gray-200 dark:bg-zinc-700 rounded animate-pulse" />
          )}
        </div>
      </div>

      {/* 操作区骨架 — 等待策略包完成 */}
      <div className="p-4 bg-gray-50/50 dark:bg-[#1e1e20] border-t border-gray-200/50 dark:border-zinc-800 flex justify-between">
        <div className="h-9 w-28 bg-gray-200 dark:bg-zinc-700/30 rounded-md" />
        <div className="h-9 w-24 bg-indigo-100 dark:bg-indigo-800/20 rounded-md flex items-center justify-center gap-1">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-500" />
          <span className="text-xs text-indigo-500">等待策略包...</span>
        </div>
      </div>
    </div>
  );
}
