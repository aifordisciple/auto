"use client";

/**
 * ETA 预估徽章组件
 *
 * 显示工作流的预计完成时间
 */

import { Clock, Loader2, CheckCircle } from "lucide-react";

// ==========================================
// 类型定义
// ==========================================

interface ETABadgeProps {
  etaSeconds: number | null;
  confidence?: number; // 0-1
  isCompleted?: boolean;
  size?: "sm" | "md";
}

// ==========================================
// 组件
// ==========================================

export function ETABadge({
  etaSeconds,
  confidence = 0.5,
  isCompleted = false,
  size = "md",
}: ETABadgeProps) {
  // 格式化时间
  const formatETA = (seconds: number): string => {
    if (seconds < 60) {
      return `${Math.round(seconds)}秒`;
    }
    if (seconds < 3600) {
      const minutes = Math.round(seconds / 60);
      return `${minutes}分钟`;
    }
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.round((seconds % 3600) / 60);
    return minutes > 0 ? `${hours}小时${minutes}分` : `${hours}小时`;
  };

  // 已完成
  if (isCompleted) {
    return (
      <div
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 ${
          size === "sm" ? "text-xs" : "text-sm"
        }`}
      >
        <CheckCircle className="w-3.5 h-3.5" />
        <span>已完成</span>
      </div>
    );
  }

  // 无法估算
  if (etaSeconds === null || etaSeconds === undefined) {
    return (
      <div
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-neutral-500/10 text-neutral-400 ${
          size === "sm" ? "text-xs" : "text-sm"
        }`}
      >
        <Clock className="w-3.5 h-3.5" />
        <span>计算中...</span>
      </div>
    );
  }

  // 即将完成
  if (etaSeconds < 60) {
    return (
      <div
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 ${
          size === "sm" ? "text-xs" : "text-sm"
        }`}
      >
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        <span>即将完成</span>
      </div>
    );
  }

  // 根据置信度选择颜色
  const getColorClass = () => {
    if (confidence >= 0.7) {
      return "bg-blue-500/10 text-blue-400";
    } else if (confidence >= 0.4) {
      return "bg-amber-500/10 text-amber-400";
    } else {
      return "bg-neutral-500/10 text-neutral-400";
    }
  };

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full ${getColorClass()} ${
        size === "sm" ? "text-xs" : "text-sm"
      }`}
    >
      <Clock className="w-3.5 h-3.5" />
      <span>约 {formatETA(etaSeconds)}</span>
      {confidence < 0.5 && <span className="opacity-50">?</span>}
    </div>
  );
}