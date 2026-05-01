/**
 * PlanCard — Claude Code 生成的分析方案展示组件
 *
 * 显示 Claude Code 制定的分析方案，包含步骤列表和用户确认按钮。
 * 用户确认后触发 onConfirm 回调发送确认指令。
 */
'use client';

import { useState } from 'react';
import type { PlanData } from '@/store/useClaudeStore';

interface PlanCardProps {
  plan: PlanData;
  onConfirm: () => void;
  disabled?: boolean;
}

export function PlanCard({ plan, onConfirm, disabled }: PlanCardProps) {
  const [confirmed, setConfirmed] = useState(false);

  const handleConfirm = () => {
    setConfirmed(true);
    onConfirm();
  };

  return (
    <div className="border border-blue-500/30 rounded-lg mb-3 overflow-hidden">
      {/* 方案标题栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-blue-500/10 border-b border-blue-500/20">
        <div className="flex items-center gap-2">
          <span className="text-blue-400 text-sm">📋</span>
          <span className="text-blue-300 font-medium text-sm">{plan.title}</span>
        </div>
        {plan.estimatedCost && (
          <span className="text-xs text-blue-400/60">
            预计耗时: {plan.estimatedCost}
          </span>
        )}
      </div>

      {/* 步骤列表 */}
      <div className="px-4 py-3 space-y-2">
        {plan.steps.map((step, i) => (
          <div key={i} className="flex gap-3 text-sm">
            <span className="text-blue-400 font-mono text-xs mt-0.5 shrink-0">
              {i + 1}.
            </span>
            <div>
              <div className="text-gray-200 font-medium">{step.title}</div>
              {step.description && (
                <div className="text-gray-400 text-xs mt-0.5">{step.description}</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 代码预览 (如果有) */}
      {plan.codeSnapshot && (
        <div className="mx-4 mb-3 rounded bg-gray-900 border border-gray-700 overflow-hidden">
          <div className="px-3 py-1.5 bg-gray-800 text-xs text-gray-500">
            代码预览
          </div>
          <pre className="px-3 py-2 text-xs text-gray-300 overflow-x-auto max-h-40">
            {plan.codeSnapshot}
          </pre>
        </div>
      )}

      {/* 确认按钮 */}
      <div className="px-4 py-3 bg-blue-500/5 border-t border-blue-500/20 flex items-center gap-3">
        <button
          onClick={handleConfirm}
          disabled={confirmed || disabled}
          className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
            confirmed
              ? 'bg-green-600 text-white cursor-default'
              : 'bg-blue-600 hover:bg-blue-700 text-white'
          }`}
        >
          {confirmed ? '已确认' : '确认执行方案'}
        </button>
        {!confirmed && (
          <span className="text-xs text-gray-500">
            确认后 Claude 将开始执行分析任务
          </span>
        )}
      </div>
    </div>
  );
}
