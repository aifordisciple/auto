"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Button 变体类型定义
 * - primary: 主要操作（action blue 胶囊形）
 * - secondary: 次要操作（中性深色背景）
 * - destructive: 危险操作（danger red）
 * - ghost: 幽灵按钮（透明，hover 显示背景）
 * - icon: 仅图标按钮（透明，小尺寸 hover 效果）
 * - purple: 紫色语义操作（data 领域）
 * - green: 绿色语义操作（success 领域）
 */
type ButtonVariant = "primary" | "secondary" | "destructive" | "ghost" | "icon" | "purple" | "green";

/**
 * Button 尺寸类型定义
 * - sm: 紧凑（tag pills, 行内操作）
 * - md: 默认（大部分按钮）
 * - lg: 大尺寸（表单提交, CTA）
 */
type ButtonSize = "sm" | "md" | "lg";

/**
 * Button 组件 Props
 * 扩展原生 button 属性，增加 variant / size / isLoading
 */
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  children: React.ReactNode;
}

// ==========================================
// 变体样式映射
// ==========================================

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-action hover:bg-action/90 text-action-foreground disabled:bg-neutral-800 disabled:text-neutral-500",
  secondary:
    "bg-neutral-800 hover:bg-neutral-700 text-neutral-200 disabled:bg-neutral-800 disabled:text-neutral-500",
  destructive:
    "bg-danger hover:bg-danger/90 text-danger-foreground disabled:bg-neutral-800 disabled:text-neutral-500",
  ghost:
    "text-neutral-400 hover:text-white hover:bg-neutral-800/50 disabled:text-neutral-600 disabled:hover:bg-transparent",
  icon:
    "text-neutral-400 hover:text-white hover:bg-neutral-800 disabled:text-neutral-600 disabled:hover:bg-transparent",
  purple:
    "bg-data hover:bg-data/90 text-data-foreground disabled:bg-neutral-800 disabled:text-neutral-500",
  green:
    "bg-success hover:bg-success/90 text-success-foreground disabled:bg-neutral-800 disabled:text-neutral-500",
};

// ==========================================
// 尺寸样式映射
// ==========================================

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-2 py-1 text-xs rounded-md gap-1",
  md: "px-4 py-2 text-sm rounded-lg gap-2",
  lg: "px-6 py-2.5 text-sm rounded-lg gap-2",
};

// ==========================================
// 变体对应的圆角样式
// ==========================================

const variantRadius: Partial<Record<ButtonVariant, string>> = {
  primary: "rounded-full",
  ghost: "rounded-lg",
  icon: "rounded-md",
};

// ==========================================
// Button 组件
// ==========================================

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", isLoading = false, className, children, disabled, ...props }, ref) => {
    const variantClass = variantClasses[variant];
    const sizeClass = sizeClasses[size];
    const radiusClass = variantRadius[variant] ?? "";

    return (
      <button
        ref={ref}
        className={cn(
          // 基础样式
          "inline-flex items-center justify-center font-medium transition-colors",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          // 变体 + 尺寸 + 圆角
          variantClass,
          sizeClass,
          radiusClass,
          // 调用方扩展
          className,
        )}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
        {children}
      </button>
    );
  },
);

Button.displayName = "Button";

export { Button };
export type { ButtonProps, ButtonVariant, ButtonSize };
