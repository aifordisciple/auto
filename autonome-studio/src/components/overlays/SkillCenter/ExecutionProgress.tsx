/**
 * ExecutionProgress 组件 - 技能执行进度显示
 *
 * P2 等待体验优化功能：
 * 1. 分段进度条 - 显示具体执行阶段
 * 2. 预期时间显示 - 预估剩余时间
 * 3. 即时反馈 - 操作后立即显示状态变化
 */

'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, CheckCircle, XCircle, Clock, Zap, Database, Cpu, FileOutput } from 'lucide-react';

// ==========================================
// 类型定义
// ==========================================

export type ExecutionPhase =
  | 'submitting'   // 提交中
  | 'initializing' // 初始化
  | 'loading'      // 加载数据
  | 'processing'   // 处理中
  | 'writing'      // 写入结果
  | 'finalizing'   // 收尾
  | 'success'      // 成功
  | 'failure';     // 失败

export interface ExecutionProgressProps {
  isExecuting: boolean;
  taskStatus: string | null;
  taskId?: string | null;
  logs?: string[];
  startTime?: number | null;
  estimatedDuration?: number; // 预估执行时间（秒）
  skillName?: string;
}

// ==========================================
// 阶段配置
// ==========================================

const PHASE_CONFIG: Record<ExecutionPhase, {
  label: string;
  icon: React.ReactNode;
  color: string;
  progress: number;
}> = {
  submitting: {
    label: '提交任务...',
    icon: <Zap size={14} />,
    color: 'text-yellow-400',
    progress: 5
  },
  initializing: {
    label: '初始化环境...',
    icon: <Loader2 size={14} className="animate-spin" />,
    color: 'text-blue-400',
    progress: 15
  },
  loading: {
    label: '加载数据...',
    icon: <Database size={14} />,
    color: 'text-cyan-400',
    progress: 30
  },
  processing: {
    label: '正在计算...',
    icon: <Cpu size={14} />,
    color: 'text-purple-400',
    progress: 60
  },
  writing: {
    label: '生成结果...',
    icon: <FileOutput size={14} />,
    color: 'text-orange-400',
    progress: 85
  },
  finalizing: {
    label: '清理资源...',
    icon: <Loader2 size={14} className="animate-spin" />,
    color: 'text-blue-400',
    progress: 95
  },
  success: {
    label: '执行完成',
    icon: <CheckCircle size={14} />,
    color: 'text-green-400',
    progress: 100
  },
  failure: {
    label: '执行失败',
    icon: <XCircle size={14} />,
    color: 'text-red-400',
    progress: 0
  }
};

// ==========================================
// 组件实现
// ==========================================

export function ExecutionProgress({
  isExecuting,
  taskStatus,
  taskId,
  logs = [],
  startTime,
  estimatedDuration,
  skillName
}: ExecutionProgressProps) {
  const [elapsedTime, setElapsedTime] = useState(0);
  const [currentPhase, setCurrentPhase] = useState<ExecutionPhase>('submitting');

  // 更新经过时间
  useEffect(() => {
    if (!startTime || !isExecuting) {
      setElapsedTime(0);
      return;
    }

    const interval = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [startTime, isExecuting]);

  // 根据日志推断当前阶段
  useEffect(() => {
    if (!isExecuting && taskStatus) {
      if (taskStatus === 'SUCCESS') {
        setCurrentPhase('success');
      } else if (taskStatus === 'FAILURE') {
        setCurrentPhase('failure');
      }
      return;
    }

    if (logs.length === 0) {
      setCurrentPhase('submitting');
      return;
    }

    // 分析最新日志推断阶段
    const recentLogs = logs.slice(-10).join(' ').toLowerCase();

    if (recentLogs.includes('loading') || recentLogs.includes('读取') || recentLogs.includes('加载')) {
      setCurrentPhase('loading');
    } else if (recentLogs.includes('processing') || recentLogs.includes('计算') || recentLogs.includes('分析')) {
      setCurrentPhase('processing');
    } else if (recentLogs.includes('writing') || recentLogs.includes('输出') || recentLogs.includes('保存') || recentLogs.includes('生成')) {
      setCurrentPhase('writing');
    } else if (recentLogs.includes('initializing') || recentLogs.includes('初始化')) {
      setCurrentPhase('initializing');
    } else if (recentLogs.includes('done') || recentLogs.includes('complete') || recentLogs.includes('完成')) {
      setCurrentPhase('finalizing');
    } else {
      // 默认处理中
      setCurrentPhase('processing');
    }
  }, [logs, isExecuting, taskStatus]);

  // 计算预估剩余时间
  const remainingTime = useMemo(() => {
    if (!estimatedDuration || !elapsedTime) return null;
    const remaining = Math.max(0, estimatedDuration - elapsedTime);
    return remaining;
  }, [estimatedDuration, elapsedTime]);

  // 格式化时间
  const formatTime = (seconds: number): string => {
    if (seconds < 60) return `${seconds}秒`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return secs > 0 ? `${mins}分${secs}秒` : `${mins}分钟`;
  };

  // 获取当前阶段配置
  const phaseConfig = PHASE_CONFIG[currentPhase];

  // 不显示条件
  if (!isExecuting && !taskStatus) {
    return null;
  }

  return (
    <div className="shrink-0 p-4 border-t border-neutral-800 bg-neutral-900/20">
      {/* 状态行 */}
      <div className="flex items-center gap-3">
        <span className={phaseConfig.color}>
          {phaseConfig.icon}
        </span>

        <span className="text-sm text-neutral-300">
          {phaseConfig.label}
        </span>

        {/* 经过时间 */}
        {isExecuting && elapsedTime > 0 && (
          <span className="text-xs text-neutral-500 flex items-center gap-1">
            <Clock size={12} />
            {formatTime(elapsedTime)}
          </span>
        )}

        {/* 任务ID */}
        {taskId && (
          <span className="text-xs text-neutral-500 font-mono ml-auto">
            Task: {taskId.slice(0, 8)}
          </span>
        )}
      </div>

      {/* 进度条 */}
      {isExecuting && (
        <div className="mt-3">
          <div className="h-1.5 bg-neutral-800 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${phaseConfig.progress}%` }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
              className="h-full bg-gradient-to-r from-blue-500 to-purple-500"
            />
          </div>

          {/* 进度详情 */}
          <div className="mt-1.5 flex justify-between items-center">
            <span className="text-[10px] text-neutral-500">
              {phaseConfig.progress}%
            </span>

            {/* 预估剩余时间 */}
            {remainingTime !== null && remainingTime > 0 && (
              <span className="text-[10px] text-neutral-500">
                预计还需 {formatTime(remainingTime)}
              </span>
            )}
          </div>
        </div>
      )}

      {/* 预估时间提示（首次执行） */}
      {isExecuting && estimatedDuration && elapsedTime < 5 && (
        <div className="mt-2 text-xs text-neutral-500 flex items-center gap-1">
          <Clock size={12} />
          预计执行时间: {formatTime(estimatedDuration)}
        </div>
      )}
    </div>
  );
}

// ==========================================
// 辅助函数：根据技能类型估算执行时间
// ==========================================

export function estimateExecutionTime(
  executorType: string,
  skillName?: string
): number {
  // 基于技能类型估算（秒）
  const baseEstimates: Record<string, number> = {
    'Python_env': 60,    // Python 脚本平均 1 分钟
    'R_env': 90,         // R 脚本平均 1.5 分钟
    'Logical_Blueprint': 180, // Nextflow 流程平均 3 分钟
    'Python_Package': 120,    // Python 包平均 2 分钟
  };

  // 技能名关键词调整
  let estimate = baseEstimates[executorType] || 60;

  if (skillName) {
    const nameLower = skillName.toLowerCase();

    // 快速操作
    if (nameLower.includes('qc') || nameLower.includes('质控')) {
      estimate = Math.min(estimate, 30);
    }
    // 耗时操作
    if (nameLower.includes('align') || nameLower.includes('比对')) {
      estimate *= 2;
    }
    if (nameLower.includes('annotation') || nameLower.includes('注释')) {
      estimate *= 1.5;
    }
  }

  return estimate;
}