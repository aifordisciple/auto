"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { X, Move, Loader2, Folder, FolderOpen, ChevronRight, ChevronDown, Lock, File, FileText } from "lucide-react";
import { moveFile, getFolderTree, FolderNode } from "@/lib/api";

interface MoveFileModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  sourcePath: string;
  sourceName: string;
  isFolder: boolean;
  onSuccess: () => void;
}

// 文件夹树节点组件
const FolderTreeNode = ({
  node,
  selectedPath,
  onSelect,
  expandedPaths,
  toggleExpand,
  level = 0
}: {
  node: FolderNode;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  expandedPaths: Set<string>;
  toggleExpand: (path: string) => void;
  level?: number;
}) => {
  const isExpanded = expandedPaths.has(node.path);
  const isSelected = selectedPath === node.path;
  const hasChildren = node.children && node.children.length > 0;

  return (
    <div className="flex flex-col">
      <div
        className={`flex items-center gap-2 px-2 py-1.5 hover:bg-neutral-800/80 rounded-lg cursor-pointer transition-all ${isSelected ? 'bg-purple-500/20 border border-purple-500/30' : 'border border-transparent'}`}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => node.writable && onSelect(node.path)}
      >
        {/* 展开/折叠箭头 */}
        {hasChildren ? (
          <span
            className="text-neutral-500 hover:text-neutral-300 transition-colors shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              toggleExpand(node.path);
            }}
          >
            {isExpanded ? <ChevronDown size={14} strokeWidth={2.5} /> : <ChevronRight size={14} strokeWidth={2.5} />}
          </span>
        ) : (
          <span className="w-3.5" />
        )}

        {/* 文件夹图标 */}
        {isExpanded ? (
          <FolderOpen size={15} className={`${node.writable ? 'text-purple-400' : 'text-neutral-600'} shrink-0`} />
        ) : (
          <Folder size={15} className={`${node.writable ? 'text-purple-400' : 'text-neutral-600'} shrink-0`} />
        )}

        {/* 名称 */}
        <span className={`text-sm truncate ${node.writable ? 'text-neutral-200' : 'text-neutral-500'}`}>
          {node.name}
        </span>

        {/* 只读标记 */}
        {!node.writable && (
          <span className="flex items-center gap-1 text-[9px] bg-neutral-800 text-neutral-500 px-1.5 py-0.5 rounded border border-neutral-700 uppercase tracking-wider shrink-0">
            <Lock size={9} /> 只读
          </span>
        )}
      </div>

      {/* 子节点 */}
      {isExpanded && hasChildren && (
        <div className="border-l border-neutral-800 ml-4">
          {node.children.map((child) => (
            <FolderTreeNode
              key={child.path}
              node={child}
              selectedPath={selectedPath}
              onSelect={onSelect}
              expandedPaths={expandedPaths}
              toggleExpand={toggleExpand}
              level={level + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export function MoveFileModal({ isOpen, onClose, projectId, sourcePath, sourceName, isFolder, onSuccess }: MoveFileModalProps) {
  const [folders, setFolders] = useState<FolderNode[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set(['raw_data', 'results']));
  const [isLoading, setIsLoading] = useState(false);
  const [isMoving, setIsMoving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 加载文件夹树
  const loadFolders = useCallback(async () => {
    if (!isOpen) return;
    setIsLoading(true);
    try {
      const result = await getFolderTree(projectId);
      if (result.status === 'success') {
        setFolders(result.data);
      }
    } catch (err: any) {
      setError(err.message || '加载文件夹失败');
    } finally {
      setIsLoading(false);
    }
  }, [isOpen, projectId]);

  useEffect(() => {
    loadFolders();
  }, [loadFolders]);

  // 重置状态
  useEffect(() => {
    if (!isOpen) {
      setSelectedPath(null);
      setError(null);
      setIsMoving(false);
    }
  }, [isOpen]);

  const toggleExpand = (path: string) => {
    setExpandedPaths(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleMove = async () => {
    if (!selectedPath) {
      setError('请选择目标目录');
      return;
    }

    // 不能移动到自身所在目录
    const parentOfSource = sourcePath.substring(0, sourcePath.lastIndexOf('/')) || '';
    if (selectedPath === parentOfSource) {
      setError('文件已在该目录中，无需移动');
      return;
    }

    setIsMoving(true);
    setError(null);

    try {
      await moveFile(projectId, {
        source_path: sourcePath,
        destination_path: selectedPath,
        overwrite: false
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || '移动失败，请重试');
    } finally {
      setIsMoving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#1a1a1c] border border-neutral-700 rounded-xl w-full max-w-lg shadow-2xl animate-in zoom-in-95 duration-200">

        {/* Header */}
        <div className="h-14 shrink-0 border-b border-neutral-800 px-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/20 border border-blue-500/30 rounded-lg text-blue-400">
              <Move size={18} />
            </div>
            <h3 className="text-white font-semibold text-sm tracking-wide">移动到...</h3>
          </div>
          <button
            onClick={onClose}
            disabled={isMoving}
            className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors disabled:opacity-50"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          {/* 源文件显示 */}
          <div className="space-y-1.5">
            <label className="text-xs text-neutral-500 font-medium uppercase tracking-wider">要移动的项目</label>
            <div className="flex items-center gap-2 px-3 py-2.5 bg-neutral-900 border border-neutral-800 rounded-lg text-sm text-neutral-400">
              {isFolder ? (
                <Folder size={14} className="text-purple-400 shrink-0" />
              ) : (
                <FileText size={14} className="text-blue-400 shrink-0" />
              )}
              <span className="font-mono truncate">{sourceName}</span>
              <span className="text-neutral-600 truncate text-xs">{sourcePath}</span>
            </div>
          </div>

          {/* 目标目录选择器 */}
          <div className="space-y-1.5">
            <label className="text-xs text-neutral-500 font-medium uppercase tracking-wider">选择目标目录</label>
            <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-2 max-h-64 overflow-y-auto custom-scrollbar">
              {isLoading ? (
                <div className="flex items-center justify-center py-8 text-neutral-500">
                  <Loader2 size={20} className="animate-spin mr-2" />
                  加载中...
                </div>
              ) : folders.length === 0 ? (
                <div className="text-center py-8 text-neutral-600 text-sm">
                  暂无可用目录
                </div>
              ) : (
                <div className="space-y-0.5">
                  {folders.map((folder) => (
                    <FolderTreeNode
                      key={folder.path}
                      node={folder}
                      selectedPath={selectedPath}
                      onSelect={setSelectedPath}
                      expandedPaths={expandedPaths}
                      toggleExpand={toggleExpand}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 选中的目标路径 */}
          {selectedPath && (
            <div className="flex items-center gap-2 px-3 py-2 bg-purple-500/10 border border-purple-500/20 rounded-lg text-sm text-purple-300">
              <span className="text-neutral-400">目标:</span>
              <span className="font-mono">{selectedPath}/{sourceName}</span>
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="px-3 py-2.5 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
              {error}
            </div>
          )}

          {/* 按钮组 */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isMoving}
              className="px-4 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors disabled:opacity-50"
            >
              取消
            </button>
            <button
              onClick={handleMove}
              disabled={isMoving || !selectedPath || isLoading}
              className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm font-medium rounded-lg transition-colors shadow-lg shadow-blue-900/20"
            >
              {isMoving ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  移动中...
                </>
              ) : (
                <>
                  <Move size={16} />
                  移动
                </>
              )}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}