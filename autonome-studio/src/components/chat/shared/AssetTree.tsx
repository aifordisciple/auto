/**
 * 共享资产树组件
 *
 * 从 MarkdownBlock.tsx / MemoizedMessageItem.tsx / ExecutionResultCard.tsx 提取的
 * 通用资产树构建和渲染逻辑。
 *
 * 导出:
 *   - AssetNodeType   节点类型定义
 *   - buildAssetTree  从文件路径列表构建树结构
 *   - getFileIcon     根据文件名返回图标
 *   - AssetTreeNode   递归渲染树节点
 */
"use client";

import React, { useState } from "react";
import {
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  FileText,
  Eye,
  Download,
  Image as ImageIcon,
  Table2,
  FileImage,
  FileSpreadsheet,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ==========================================
// 类型定义
// ==========================================

/** 资产树节点数据结构 */
export interface AssetNodeType {
  name: string;
  type: "file" | "folder";
  url?: string | null;
  ext?: string | null;
  children: Record<string, AssetNodeType>;
}

/** buildAssetTree 的输入项 */
export interface AssetTreeInputItem {
  /** 显示标题或路径（用 / 分隔表示层级） */
  title: string;
  /** 文件访问 URL */
  url: string;
}

/** AssetTreeNode 组件 Props */
export interface AssetTreeNodeProps {
  /** 当前节点数据 */
  node: AssetNodeType;
  /** 缩进层级，0 表示顶层 */
  level: number;
  /** 预览回调 */
  onPreview: (url: string, name: string) => void;
  /** 下载回调 */
  onDownload: (url: string, name: string) => void;
  /** 额外的根 className */
  className?: string;
  /** 主题变体：light-dark 适配亮色模式，dark-only 纯暗色 */
  variant?: "light-dark" | "dark-only";
}

// ==========================================
// 文件图标获取函数
// ==========================================

/**
 * 根据文件扩展名返回对应的 Lucide 图标
 */
export const getFileIcon = (filename: string, variant: "light-dark" | "dark-only" = "light-dark") => {
  const lower = filename.toLowerCase();

  if (lower.endsWith(".tsv") || lower.endsWith(".csv") || lower.endsWith(".txt") || lower.endsWith(".log")) {
    return <Table2 size={15} className={variant === "dark-only" ? "text-blue-400 shrink-0" : "text-blue-500 dark:text-blue-400 shrink-0"} />;
  }
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".pdf") || lower.endsWith(".svg")) {
    return <ImageIcon size={15} className={variant === "dark-only" ? "text-pink-400 shrink-0" : "text-pink-500 dark:text-pink-400 shrink-0"} />;
  }

  return <FileText size={15} className={variant === "dark-only" ? "text-neutral-400 shrink-0" : "text-gray-500 dark:text-neutral-400 shrink-0"} />;
};

/**
 * 根据文件扩展名返回分类图标（用于纯暗色主题的简化图标）
 * 区分图片类 / 数据类 / 其他
 */
export const getFileTypeIcon = (ext: string | null | undefined) => {
  const isImage = ext && ["png", "jpg", "jpeg", "gif", "svg"].includes(ext);
  const isData = ext && ["csv", "tsv", "txt", "h5ad", "xlsx"].includes(ext);

  if (isImage) return <FileImage size={14} className="text-blue-400" />;
  if (isData) return <FileSpreadsheet size={14} className="text-emerald-400" />;
  return <FileText size={14} className="text-neutral-400" />;
};

// ==========================================
// 资产树构建函数
// ==========================================

/**
 * 从平铺的链接列表构建树状结构
 *
 * @param links  文件链接列表，title 用 / 分隔表示目录层级
 * @param rootName 根节点名称，默认 "Analysis Results"
 * @returns 根节点（包含 children）
 */
export function buildAssetTree(
  links: AssetTreeInputItem[],
  rootName: string = "Analysis Results"
): AssetNodeType {
  const root: AssetNodeType = { type: "folder", name: rootName, children: {} };

  links.forEach((link) => {
    // 尝试从 URL 中提取合理的相对路径
    let pathStr = link.title;
    if (link.url.includes("/files/")) {
      pathStr = link.url.split("/files/")[1] || link.title;
    }

    const parts = pathStr.split("/").filter((p) => p);
    let current = root;

    parts.forEach((part, idx) => {
      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          type: idx === parts.length - 1 ? "file" : "folder",
          children: {},
          url: idx === parts.length - 1 ? link.url : null,
        };
      }
      current = current.children[part];
    });
  });

  return root;
}

/**
 * 从文件对象列表构建树状结构（用于 MemoizedMessageItem 场景）
 * 每个文件对象包含 projectId / path / name / ext
 *
 * @param files  文件对象列表
 * @param urlBuilder  根据 file 构建完整访问 URL 的函数
 * @param rootName 根节点名称，默认 "Analysis Results"
 * @returns 根节点（包含 children）
 */
export function buildAssetTreeFromFiles<T extends { path: string; ext: string }>(
  files: T[],
  urlBuilder: (file: T) => string,
  rootName: string = "Analysis Results"
): AssetNodeType {
  const root: AssetNodeType = { type: "folder", name: rootName, children: {} };

  files.forEach((file) => {
    const parts = file.path.split("/").filter((p) => p);
    let current = root;

    parts.forEach((part, idx) => {
      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          type: idx === parts.length - 1 ? "file" : "folder",
          children: {},
          url: idx === parts.length - 1 ? urlBuilder(file) : null,
          ext: idx === parts.length - 1 ? file.ext : null,
        };
      }
      current = current.children[part];
    });
  });

  return root;
}

// ==========================================
// 资产树节点渲染组件
// ==========================================

/**
 * AssetTreeNode - 递归渲染资产树的节点
 *
 * 支持两种视觉变体：
 *   - "light-dark"（默认）：适配亮色/暗色模式切换，用于 MarkdownBlock 和 ExecutionResultCard
 *   - "dark-only"：纯暗色主题，用于 MemoizedMessageItem 的暗色卡片
 */
export const AssetTreeNode: React.FC<AssetTreeNodeProps> = ({
  node,
  level,
  onPreview,
  onDownload,
  className,
  variant = "light-dark",
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const isFolder = node.type === "folder";

  // 根据变体选择样式
  const isDarkOnly = variant === "dark-only";

  // 行样式
  const rowClassName = cn(
    "flex items-center gap-2 py-1.5 px-2 rounded-md cursor-pointer group transition-colors",
    isDarkOnly
      ? "hover:bg-neutral-800/60"
      : "hover:bg-gray-100 dark:hover:bg-[#2d2d30]/80",
    className
  );

  // 缩进样式
  const indentStyle =
    level > 0
      ? isDarkOnly
        ? { marginLeft: `${level * 16}px` }
        : { marginLeft: `${level * 16}px`, borderLeft: "1px solid", borderLeftColor: level > 1 ? "transparent" : undefined, paddingLeft: "12px" }
      : {};

  // 文件名样式
  const nameClassName = cn(
    "text-[13px] truncate flex-1 tracking-wide",
    isFolder
      ? "font-medium " + (isDarkOnly ? "text-gray-200" : "text-gray-800 dark:text-gray-200")
      : isDarkOnly
        ? "text-gray-400 group-hover:text-gray-100"
        : "text-gray-600 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-gray-100"
  );

  // 按钮样式
  const btnClassName = cn(
    "p-1 rounded border shrink-0",
    isDarkOnly
      ? "text-neutral-400 bg-neutral-800 border-neutral-700"
      : "text-gray-400 bg-white dark:bg-[#1e1e20] shadow-sm border-gray-200 dark:border-gray-700"
  );

  return (
    <div className="flex flex-col">
      <div
        className={rowClassName}
        style={indentStyle}
        onClick={() =>
          isFolder ? setIsExpanded(!isExpanded) : onPreview(node.url || "", node.name)
        }
      >
        {/* 图标区域 */}
        {isFolder ? (
          <div className={cn("flex items-center gap-1 shrink-0", isDarkOnly ? "text-blue-400" : "text-gray-400 dark:text-gray-500")}>
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {isExpanded ? (
              <FolderOpen size={15} className="text-blue-400" />
            ) : (
              <Folder size={15} className="text-blue-400" />
            )}
          </div>
        ) : (
          <div className="ml-5 shrink-0">
            {node.ext ? getFileTypeIcon(node.ext) : getFileIcon(node.name, variant)}
          </div>
        )}

        {/* 文件名 */}
        <span className={nameClassName}>{node.name}</span>

        {/* 文件操作悬浮按钮 */}
        {!isFolder && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onPreview(node.url || "", node.name);
              }}
              className={cn(btnClassName, "hover:text-emerald-500 dark:hover:text-emerald-400")}
              title="安全预览"
            >
              <Eye size={13} />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDownload(node.url || "", node.name);
              }}
              className={cn(btnClassName, "hover:text-blue-500 dark:hover:text-blue-400")}
              title="下载"
            >
              <Download size={13} />
            </button>
          </div>
        )}
      </div>

      {/* 递归子节点 */}
      {isFolder && isExpanded && (
        <div className="flex flex-col mt-0.5">
          {Object.values(node.children).map((child) => (
            <AssetTreeNode
              key={child.name}
              node={child}
              level={level + 1}
              onPreview={onPreview}
              onDownload={onDownload}
              variant={variant}
            />
          ))}
        </div>
      )}
    </div>
  );
};
