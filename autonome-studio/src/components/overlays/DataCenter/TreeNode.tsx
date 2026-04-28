/**
 * TreeNode 组件
 *
 * 递归渲染单个节点，支持批量模式
 */
'use client';

import React from 'react';
import { ChevronDown, ChevronRight, FolderOpen, Folder, Eye, Download, Trash2, Lock, FolderPlus, Move, Pencil } from "lucide-react";
import { getFileIcon, formatBytes, formatDateTime } from './utils';

/**
 * 文件节点数据结构
 */
export interface FileNode {
  name: string;
  path: string;
  type: 'folder' | 'file';
  children?: Record<string, FileNode>;
  fileData?: {
    size?: number;
    file_size?: number;
    modified_at?: string | number;
    mtime?: string | number;
  };
}

/**
 * TreeNode 组件 Props
 */
export interface TreeNodeProps {
  /** 当前节点 */
  node: FileNode;
  /** 已展开的文件夹路径集合 */
  expandedFolders: Set<string>;
  /** 切换展开状态 */
  toggleExpand: (path: string) => void;
  /** 删除回调 */
  onDelete: (path: string) => void;
  /** 下载回调 */
  onDownload: (path: string) => void;
  /** 预览回调 */
  onPreview: (path: string) => void;
  /** 是否批量模式 */
  isBatchMode: boolean;
  /** 已选中的路径集合 */
  selectedPaths: Set<string>;
  /** 切换选中状态 */
  toggleSelection: (path: string) => void;
  /** 右键菜单处理 */
  onContextMenu: (e: React.MouseEvent | { preventDefault: () => void; stopPropagation: () => void }, node: FileNode & { _action?: string }) => void;
  /** 高亮目标路径（数据中心联动） */
  highlightedPath?: string | null;
  /** 高亮节点 ref（用于 scrollIntoView） */
  highlightedNodeRef?: React.RefObject<HTMLDivElement | null>;
}

/**
 * TreeNode 组件 - 递归渲染单个节点
 */
export const TreeNode: React.FC<TreeNodeProps> = ({
  node,
  expandedFolders,
  toggleExpand,
  onDelete,
  onDownload,
  onPreview,
  isBatchMode,
  selectedPaths,
  toggleSelection,
  onContextMenu,
  highlightedPath,
  highlightedNodeRef,
}) => {
  const isFolder = node.type === 'folder';
  const isExpanded = expandedFolders.has(node.path);
  const isProtectedRoot = isFolder && (node.path === 'raw_data' || node.path === 'results' || node.path === 'references');
  const isReadOnly = node.path.startsWith('references');
  const isHighlighted = highlightedPath && node.path === highlightedPath;

  // ✨ 是否允许被批量选中
  const isSelectable = !isProtectedRoot && !isReadOnly;

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onContextMenu(e, node);
  };

  return (
    <div className="flex flex-col">
      <div
        ref={isHighlighted ? highlightedNodeRef : undefined}
        className={`flex items-center gap-2 px-2 py-1.5 hover:bg-neutral-800/80 rounded-lg cursor-pointer group transition-all ${!isFolder ? 'ml-6' : ''} ${selectedPaths?.has(node.path) ? 'bg-red-500/10 border border-red-500/20' : 'border border-transparent'} ${isHighlighted ? 'ring-2 ring-indigo-400 bg-indigo-50/10 dark:bg-indigo-500/10 animate-pulse' : ''}`}
        onClick={() => {
          if (isBatchMode && isSelectable) {
            toggleSelection(node.path);
          } else {
            if (isFolder) toggleExpand(node.path);
            else onPreview(node.path);
          }
        }}
        onContextMenu={handleContextMenu}
      >
        {/* ✨ 批量模式：复选框 */}
        {isBatchMode && isSelectable && (
          <div className="shrink-0 mr-1 flex items-center" onClick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              checked={selectedPaths.has(node.path)}
              onChange={() => toggleSelection(node.path)}
              className="w-3.5 h-3.5 rounded border-gray-600 bg-neutral-900 text-red-500 focus:ring-red-500/20 cursor-pointer"
            />
          </div>
        )}

        {isFolder && (
          <span className="text-neutral-500 group-hover:text-neutral-300 transition-colors shrink-0">
            {isExpanded ? <ChevronDown size={15} strokeWidth={2.5} /> : <ChevronRight size={15} strokeWidth={2.5} />}
          </span>
        )}

        {isFolder ? (
          isExpanded ? <FolderOpen size={16} className={`${isReadOnly ? 'text-emerald-500' : 'text-purple-400'} shrink-0`} /> : <Folder size={16} className={`${isReadOnly ? 'text-emerald-500' : 'text-purple-400'} shrink-0`} />
        ) : (
          getFileIcon(node.name)
        )}

        <span className={`text-sm tracking-wide truncate ${isFolder ? 'text-neutral-200 font-semibold' : 'text-neutral-400 group-hover:text-neutral-200'} ${isBatchMode && !isSelectable ? 'opacity-50' : ''}`}>
          {node.name}
        </span>

        {isFolder && isReadOnly && node.path === 'references' && (
          <span className="flex items-center gap-1 text-[9px] bg-emerald-500/10 text-emerald-500 px-1.5 py-0.5 rounded border border-emerald-500/20 uppercase tracking-wider shrink-0">
            <Lock size={10} /> 只读共享
          </span>
        )}

        {/* 正常模式下的悬浮操作栏 - 移动端常驻显示 */}
        {!isBatchMode && (
          <div className="ml-auto flex items-center opacity-100 md:opacity-0 group-hover:opacity-100 transition-opacity gap-1 z-10 shrink-0">
            {!isFolder && (
              <>
                <button onClick={(e) => { e.stopPropagation(); onPreview(node.path); }} className="p-2 md:p-1.5 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 text-neutral-500 hover:text-emerald-400 hover:bg-emerald-500/10 rounded-md transition-all" title="安全预览">
                  <Eye size={16} className="md:w-3.5 md:h-3.5" />
                </button>
                <button onClick={(e) => { e.stopPropagation(); onDownload(node.path); }} className="p-2 md:p-1.5 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 text-neutral-500 hover:text-blue-400 hover:bg-blue-500/10 rounded-md transition-all" title="直接下载">
                  <Download size={16} className="md:w-3.5 md:h-3.5" />
                </button>
              </>
            )}
            {/* 新增：新建文件夹按钮（仅文件夹显示） */}
            {isFolder && !isReadOnly && (
              <button onClick={(e) => { e.stopPropagation(); onContextMenu({ preventDefault: () => {}, stopPropagation: () => {} }, { ...node, _action: 'create_folder' }); }} className="p-2 md:p-1.5 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 text-neutral-500 hover:text-purple-400 hover:bg-purple-500/10 rounded-md transition-all" title="新建文件夹">
                <FolderPlus size={16} className="md:w-3.5 md:h-3.5" />
              </button>
            )}
            {/* 新增：移动按钮 */}
            {!isProtectedRoot && !isReadOnly && (
              <button onClick={(e) => { e.stopPropagation(); onContextMenu({ preventDefault: () => {}, stopPropagation: () => {} }, { ...node, _action: 'move' }); }} className="p-2 md:p-1.5 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 text-neutral-500 hover:text-blue-400 hover:bg-blue-500/10 rounded-md transition-all" title="移动到...">
                <Move size={16} className="md:w-3.5 md:h-3.5" />
              </button>
            )}
            {/* 新增：重命名按钮 */}
            {!isProtectedRoot && !isReadOnly && (
              <button onClick={(e) => { e.stopPropagation(); onContextMenu({ preventDefault: () => {}, stopPropagation: () => {} }, { ...node, _action: 'rename' }); }} className="p-2 md:p-1.5 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 text-neutral-500 hover:text-yellow-400 hover:bg-yellow-500/10 rounded-md transition-all" title="重命名">
                <Pencil size={16} className="md:w-3.5 md:h-3.5" />
              </button>
            )}
            {!isProtectedRoot && !isFolder && !isReadOnly && (
              <button onClick={(e) => { e.stopPropagation(); onDelete(node.path); }} className="p-2 md:p-1.5 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 text-neutral-500 hover:text-red-400 hover:bg-red-500/10 rounded-md transition-all" title="彻底删除">
                <Trash2 size={16} className="md:w-3.5 md:h-3.5" />
              </button>
            )}
          </div>
        )}

        {/* 文件大小和时间 */}
        {!isFolder && (node.fileData?.size !== undefined || node.fileData?.file_size !== undefined) && (
          <div className="flex items-center gap-2 ml-auto shrink-0 group-hover:hidden">
            <span className="text-[10px] text-neutral-600 font-mono bg-neutral-900 px-1.5 py-0.5 rounded border border-neutral-800">
              {formatBytes(node.fileData?.size ?? node.fileData?.file_size)}
            </span>
            {/* 修改时间 */}
            {(node.fileData?.modified_at || node.fileData?.mtime) && (
              <span className="text-[10px] text-neutral-600 font-mono bg-neutral-900/50 px-1.5 py-0.5 rounded">
                {formatDateTime(node.fileData?.modified_at || node.fileData?.mtime)}
              </span>
            )}
          </div>
        )}
      </div>

      {isFolder && isExpanded && (
        <div className="ml-4 border-l border-neutral-800 pl-2 mt-1 mb-2 flex flex-col gap-0.5">
          {Object.values(node.children || {}).map((child: FileNode) => (
            <TreeNode
              key={child.path}
              node={child}
              expandedFolders={expandedFolders}
              toggleExpand={toggleExpand}
              onDelete={onDelete}
              onDownload={onDownload}
              onPreview={onPreview}
              isBatchMode={isBatchMode}
              selectedPaths={selectedPaths}
              toggleSelection={toggleSelection}
              onContextMenu={onContextMenu}
              highlightedPath={highlightedPath}
              highlightedNodeRef={highlightedNodeRef}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default TreeNode;