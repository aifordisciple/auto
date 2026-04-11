"use client";

import { memo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  Play,
  Zap,
  FileCode,
  FolderOpen,
  Search,
  FileText,
  AlertTriangle,
  Clock,
} from "lucide-react";

// ==========================================
// 类型定义
// ==========================================

export type StepStatus = "pending" | "running" | "success" | "failed" | "skipped";

export interface ExecutionStepData {
  step_id: string;
  name: string;
  description: string;
  step_type: "code_execution" | "data_probe" | "file_operation" | "skill_call";
  tool_id: string;
  parameters: Record<string, unknown>;
  code?: string;
  language?: "python" | "r";
  depends_on: string[];
  status: StepStatus;
  output?: string;
  error?: string;
  execution_time?: number;
  retry_count?: number;
}

export interface ExecutionPlanData {
  plan_id: string;
  user_intent: string;
  risk_level: "low" | "medium" | "high";
  estimated_time?: string;
  steps: ExecutionStepData[];
  notes?: string[];
}

export interface ExecutionResultData {
  plan_id: string;
  success: boolean;
  total_steps: number;
  completed_steps: number;
  failed_steps: number;
  execution_time: number;
  output_dir: string;
  generated_files: Array<{
    path: string;
    name: string;
    size: number;
    extension: string;
  }>;
  step_summaries: Array<{
    step_id: string;
    name: string;
    status: string;
    execution_time: number;
    error?: string;
  }>;
}

// ==========================================
// 步骤图标
// ==========================================

function getStepIcon(stepType: string) {
  switch (stepType) {
    case "code_execution":
      return <FileCode size={14} className="text-blue-400" />;
    case "data_probe":
      return <Search size={14} className="text-emerald-400" />;
    case "file_operation":
      return <FolderOpen size={14} className="text-amber-400" />;
    case "skill_call":
      return <Zap size={14} className="text-purple-400" />;
    default:
      return <FileText size={14} className="text-neutral-400" />;
  }
}

function getStatusIcon(status: StepStatus) {
  switch (status) {
    case "running":
      return <Loader2 size={14} className="animate-spin text-blue-400" />;
    case "success":
      return <CheckCircle size={14} className="text-green-400" />;
    case "failed":
      return <XCircle size={14} className="text-red-400" />;
    case "skipped":
      return <span className="text-neutral-500 text-xs">跳过</span>;
    default:
      return <Clock size={14} className="text-neutral-500" />;
  }
}

// ==========================================
// 执行计划预览组件
// ==========================================

interface ExecutionPlanPreviewProps {
  plan: ExecutionPlanData;
  onConfirm?: () => void;
  onCancel?: () => void;
  isConfirming?: boolean;
}

export const ExecutionPlanPreview = memo(function ExecutionPlanPreview({
  plan,
  onConfirm,
  onCancel,
  isConfirming = false,
}: ExecutionPlanPreviewProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) {
        next.delete(stepId);
      } else {
        next.add(stepId);
      }
      return next;
    });
  };

  const riskColors = {
    low: "bg-green-500/10 border-green-500/20 text-green-400",
    medium: "bg-yellow-500/10 border-yellow-500/20 text-yellow-400",
    high: "bg-red-500/10 border-red-500/20 text-red-400",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-gradient-to-br from-cyan-50/50 to-blue-50/50 dark:from-cyan-950/30 dark:to-blue-950/30 border border-cyan-200 dark:border-cyan-800/50 rounded-xl p-5 shadow-lg my-4 max-w-4xl"
    >
      {/* 标题 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-cyan-100 dark:bg-cyan-900/50 rounded-lg">
            <Zap className="w-5 h-5 text-cyan-600 dark:text-cyan-400" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              执行计划
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {plan.user_intent}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-1 rounded-full text-xs font-medium border ${riskColors[plan.risk_level]}`}
          >
            {plan.risk_level === "high"
              ? "⚠️ 高风险"
              : plan.risk_level === "medium"
              ? "⚡ 中风险"
              : "✓ 低风险"}
          </span>
          {plan.estimated_time && (
            <span className="text-xs text-neutral-500">
              预计 {plan.estimated_time}
            </span>
          )}
        </div>
      </div>

      {/* 步骤列表 */}
      <div className="space-y-2 mb-4">
        {plan.steps.map((step, index) => (
          <div
            key={step.step_id}
            className="bg-white/50 dark:bg-black/20 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden"
          >
            <button
              onClick={() => toggleStep(step.step_id)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-xs text-neutral-500 font-mono">
                  #{index + 1}
                </span>
                {getStepIcon(step.step_type)}
                <span className="text-sm font-medium text-neutral-800 dark:text-neutral-200">
                  {step.name}
                </span>
                {step.depends_on.length > 0 && (
                  <span className="text-xs text-neutral-500">
                    ← {step.depends_on.map((d) => d.replace("step_", "#")).join(", ")}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs px-2 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500">
                  {step.tool_id}
                </span>
                {expandedSteps.has(step.step_id) ? (
                  <ChevronDown size={14} className="text-neutral-400" />
                ) : (
                  <ChevronRight size={14} className="text-neutral-400" />
                )}
              </div>
            </button>

            <AnimatePresence>
              {expandedSteps.has(step.step_id) && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="border-t border-neutral-200 dark:border-neutral-700"
                >
                  <div className="p-3 text-xs">
                    <p className="text-neutral-500 mb-2">{step.description}</p>
                    {step.code && (
                      <pre className="bg-neutral-900 rounded p-2 text-neutral-300 font-mono overflow-x-auto max-h-32">
                        {step.code.slice(0, 500)}
                        {step.code.length > 500 && "..."}
                      </pre>
                    )}
                    {Object.keys(step.parameters).length > 0 && (
                      <div className="mt-2">
                        <span className="text-neutral-500">参数: </span>
                        <code className="text-cyan-600 dark:text-cyan-400">
                          {JSON.stringify(step.parameters)}
                        </code>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>

      {/* 提示信息 */}
      {plan.notes && plan.notes.length > 0 && (
        <div className="mb-4 p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
          <div className="flex items-start gap-2">
            <AlertTriangle size={14} className="text-amber-400 mt-0.5" />
            <div className="text-xs text-amber-300">
              {plan.notes.map((note, i) => (
                <p key={i}>• {note}</p>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 操作按钮 */}
      {onConfirm && (
        <div className="flex items-center justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isConfirming}
            className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={isConfirming}
            className="px-6 py-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
          >
            {isConfirming ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                确认中...
              </>
            ) : (
              <>
                <Play size={16} />
                确认执行
              </>
            )}
          </button>
        </div>
      )}
    </motion.div>
  );
});

// ==========================================
// 执行进度组件
// ==========================================

interface ExecutionProgressProps {
  steps: ExecutionStepData[];
  currentStepId?: string;
}

export const ExecutionProgress = memo(function ExecutionProgress({
  steps,
  currentStepId,
}: ExecutionProgressProps) {
  return (
    <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Loader2 size={16} className="animate-spin text-cyan-400" />
        <span className="text-sm font-medium text-neutral-300">执行进度</span>
      </div>
      <div className="space-y-2">
        {steps.map((step) => (
          <div
            key={step.step_id}
            className={`flex items-center gap-3 p-2 rounded-lg ${
              step.status === "running"
                ? "bg-blue-500/10 border border-blue-500/20"
                : step.status === "success"
                ? "bg-green-500/5"
                : step.status === "failed"
                ? "bg-red-500/5"
                : "bg-transparent"
            }`}
          >
            {getStatusIcon(step.status)}
            {getStepIcon(step.step_type)}
            <span className="text-sm text-neutral-300 flex-1">{step.name}</span>
            {step.execution_time && step.execution_time > 0 && (
              <span className="text-xs text-neutral-500">
                {step.execution_time.toFixed(1)}s
              </span>
            )}
            {step.retry_count && step.retry_count > 0 && (
              <span className="text-xs text-yellow-400">
                重试 {step.retry_count}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
});

// ==========================================
// 执行结果组件
// ==========================================

interface ExecutionResultViewProps {
  result: ExecutionResultData;
}

export const ExecutionResultView = memo(function ExecutionResultView({
  result,
}: ExecutionResultViewProps) {
  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(1)}秒`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}分${secs}秒`;
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-xl p-5 shadow-lg my-4 max-w-4xl ${
        result.success
          ? "bg-gradient-to-br from-green-50/50 to-emerald-50/50 dark:from-green-950/30 dark:to-emerald-950/30 border border-green-200 dark:border-green-800/50"
          : "bg-gradient-to-br from-red-50/50 to-orange-50/50 dark:from-red-950/30 dark:to-orange-950/30 border border-red-200 dark:border-red-800/50"
      }`}
    >
      {/* 标题 */}
      <div className="flex items-center gap-3 mb-4">
        {result.success ? (
          <CheckCircle className="w-6 h-6 text-green-500" />
        ) : (
          <XCircle className="w-6 h-6 text-red-500" />
        )}
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            {result.success ? "执行完成" : "执行失败"}
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            完成 {result.completed_steps}/{result.total_steps} 步骤 · 耗时{" "}
            {formatTime(result.execution_time)}
          </p>
        </div>
      </div>

      {/* 输出目录 */}
      {result.output_dir && (
        <div className="mb-4 p-3 bg-neutral-900/50 rounded-lg">
          <div className="flex items-center gap-2 text-xs">
            <FolderOpen size={12} className="text-cyan-400" />
            <span className="text-neutral-400">输出目录:</span>
            <code className="text-cyan-400 font-mono">{result.output_dir}</code>
          </div>
        </div>
      )}

      {/* 生成的文件 */}
      {result.generated_files && result.generated_files.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-neutral-300 mb-2 flex items-center gap-2">
            <Zap size={14} />
            生成文件 ({result.generated_files.length})
          </h4>
          <div className="grid grid-cols-2 gap-2 max-h-32 overflow-y-auto">
            {result.generated_files.map((file, i) => (
              <div
                key={i}
                className="flex items-center gap-2 p-2 bg-neutral-800/50 rounded border border-neutral-700"
              >
                <FileText size={12} className="text-neutral-400" />
                <span className="text-xs text-neutral-300 truncate flex-1">
                  {file.name}
                </span>
                <span className="text-xs text-neutral-500">
                  {formatSize(file.size)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 错误信息 */}
      {result.step_summaries.some((s) => s.error) && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
          <h4 className="text-sm font-medium text-red-400 mb-2">错误详情</h4>
          <div className="space-y-1">
            {result.step_summaries
              .filter((s) => s.error)
              .map((s) => (
                <div key={s.step_id} className="text-xs text-red-300">
                  <span className="font-medium">{s.name}:</span> {s.error}
                </div>
              ))}
          </div>
        </div>
      )}
    </motion.div>
  );
});

export default ExecutionPlanPreview;