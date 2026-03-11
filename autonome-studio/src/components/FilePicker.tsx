"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { X, Folder, FolderOpen, FileText, ChevronRight, ChevronDown, Loader2, Check } from "lucide-react";
import { BASE_URL } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================
interface FileNode {
  name: string;
  path: string;
  type: 'folder' | 'file';
  children?: Record<string, FileNode>;
}

interface FilePickerProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  value: string;
  onChange: (path: string) => void;
  type: 'file' | 'directory';
  accept?: string;  // 文件类型过滤
  title?: string;
}

// ==========================================
// 组件：FilePicker 文件/目录选择器
// ==========================================
export function FilePicker({
  isOpen,
  onClose,
  projectId,
  value,
  onChange,
  type,
  accept,
  title = '选择路径'
}: FilePickerProps) {
  const [files, setFiles] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [selectedPath, setSelectedPath] = useState<string>(value || '');

  // 加载文件列表
  useEffect(() => {
    if (isOpen && projectId) {
      fetchFiles();
    }
  }, [isOpen, projectId]);

  const fetchFiles = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${BASE_URL}/api/projects/${projectId}/files`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      const data = await res.json();
      if (data.data) {
        setFiles(data.data);
      } else if (data.files) {
        setFiles(data.files);
      }
    } catch (e) {
      console.error('Failed to fetch files:', e);
    } finally {
      setIsLoading(false);
    }
  };

  // 构建文件树
  const fileTree = useMemo(() => {
    const root: Record<string, FileNode> = {};

    // 第一遍：创建所有目录节点
    files.forEach(item => {
      const itemPath = item.path || item.filename;
      const itemType = item.type || 'file';

      if (itemType === 'folder') {
        const parts = itemPath.split('/');
        let currentLevel = root;

        parts.forEach((part: string, idx: number) => {
          if (!currentLevel[part]) {
            currentLevel[part] = {
              name: part,
              path: parts.slice(0, idx + 1).join('/'),
              type: 'folder',
              children: {}
            };
          }
          currentLevel = currentLevel[part].children!;
        });
      }
    });

    // 第二遍：添加文件节点
    files.forEach(file => {
      const filePath = file.path || file.filename;
      const fileType = file.type || 'file';

      if (fileType === 'file') {
        const parts = filePath.split('/');
        let currentLevel = root;

        parts.forEach((part: string, idx: number) => {
          if (!currentLevel[part]) {
            currentLevel[part] = {
              name: part,
              path: parts.slice(0, idx + 1).join('/'),
              type: idx === parts.length - 1 ? 'file' : 'folder',
              children: idx === parts.length - 1 ? undefined : {}
            };
          } else if (idx === parts.length - 1) {
            currentLevel[part].type = 'file';
          }
          if (currentLevel[part].children) {
            currentLevel = currentLevel[part].children!;
          }
        });
      }
    });

    return root;
  }, [files]);

  const toggleExpand = (path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleSelect = (path: string, nodeType: 'folder' | 'file') => {
    // 根据类型限制选择
    if (type === 'directory' && nodeType === 'file') {
      return; // 目录选择模式下不能选择文件
    }
    if (type === 'file' && nodeType === 'folder') {
      return; // 文件选择模式下不能选择目录
    }
    setSelectedPath(path);
  };

  const handleConfirm = () => {
    onChange(selectedPath);
    onClose();
  };

  // 树节点渲染
  const TreeNode = ({ node, depth = 0 }: { node: FileNode; depth?: number }) => {
    const isFolder = node.type === 'folder';
    const isExpanded = expandedFolders.has(node.path);
    const isSelected = selectedPath === node.path;
    const canSelect = (type === 'directory' && isFolder) || (type === 'file' && !isFolder);

    return (
      <div className="flex flex-col">
        <div
          className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-all ${
            isSelected
              ? 'bg-blue-500/20 border border-blue-500/40'
              : canSelect
                ? 'hover:bg-neutral-800/80 border border-transparent'
                : 'opacity-60 border border-transparent'
          }`}
          style={{ paddingLeft: `${8 + depth * 16}px` }}
          onClick={() => canSelect && handleSelect(node.path, node.type)}
        >
          {isFolder ? (
            <span
              className="text-neutral-500 hover:text-neutral-300 transition-colors shrink-0"
              onClick={(e) => { e.stopPropagation(); toggleExpand(node.path); }}
            >
              {isExpanded ? <ChevronDown size={14} strokeWidth={2.5} /> : <ChevronRight size={14} strokeWidth={2.5} />}
            </span>
          ) : (
            <span className="w-[14px] shrink-0" />
          )}

          {isFolder ? (
            isExpanded ? (
              <FolderOpen size={16} className="text-purple-400 shrink-0" />
            ) : (
              <Folder size={16} className="text-purple-400 shrink-0" />
            )
          ) : (
            <FileText size={16} className="text-neutral-400 shrink-0" />
          )}

          <span className={`text-sm truncate ${isFolder ? 'text-neutral-200 font-medium' : 'text-neutral-400'}`}>
            {node.name}
          </span>

          {isSelected && (
            <Check size={14} className="text-blue-400 ml-auto shrink-0" />
          )}
        </div>

        {isFolder && isExpanded && node.children && (
          <div className="flex flex-col">
            {Object.values(node.children).map((child) => (
              <TreeNode key={child.path} node={child} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    );
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-[480px] max-h-[70vh] bg-[#1a1a1c] border border-neutral-700 rounded-xl shadow-2xl flex flex-col animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="shrink-0 border-b border-neutral-800 px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {type === 'directory' ? (
              <Folder size={18} className="text-purple-400" />
            ) : (
              <FileText size={18} className="text-blue-400" />
            )}
            <h3 className="text-sm font-semibold text-neutral-200">{title}</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-3 custom-scrollbar">
          {isLoading ? (
            <div className="flex items-center justify-center h-32 text-neutral-500">
              <Loader2 size={24} className="animate-spin" />
            </div>
          ) : Object.keys(fileTree).length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-neutral-600 gap-2">
              <Folder size={32} className="opacity-20" />
              <p className="text-sm">项目目录为空</p>
            </div>
          ) : (
            <div className="space-y-0.5">
              {Object.values(fileTree).map((node) => (
                <TreeNode key={node.path} node={node} />
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-neutral-800 px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex-1 text-xs text-neutral-500 font-mono truncate">
            {selectedPath || '未选择'}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleConfirm}
              disabled={!selectedPath}
              className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white font-medium rounded-lg transition-colors"
            >
              确认选择
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================
// 导出：触发按钮组件
// ==========================================
interface FilePickerButtonProps {
  projectId: string;
  value: string;
  onChange: (path: string) => void;
  type: 'file' | 'directory';
  placeholder?: string;
  accept?: string;
}

export function FilePickerButton({
  projectId,
  value,
  onChange,
  type,
  placeholder = '点击选择路径',
  accept
}: FilePickerButtonProps) {
  const [isPickerOpen, setIsPickerOpen] = useState(false);

  const handleClick = () => {
    if (!projectId) {
      alert('请先选择一个项目');
      return;
    }
    setIsPickerOpen(true);
  };

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        className={`w-full flex items-center gap-2 px-3 py-2 text-sm border rounded-lg text-left transition-colors ${
          projectId
            ? 'bg-neutral-800 border-neutral-700 hover:border-neutral-600'
            : 'bg-neutral-900 border-neutral-800 text-neutral-500 cursor-not-allowed'
        }`}
      >
        {type === 'directory' ? (
          <Folder size={14} className={value ? 'text-purple-400' : 'text-neutral-500'} />
        ) : (
          <FileText size={14} className={value ? 'text-blue-400' : 'text-neutral-500'} />
        )}
        <span className={value ? 'text-neutral-200' : 'text-neutral-500'}>
          {!projectId ? '请先选择项目' : value || placeholder}
        </span>
      </button>

      {projectId && (
        <FilePicker
          isOpen={isPickerOpen}
          onClose={() => setIsPickerOpen(false)}
          projectId={projectId}
          value={value}
          onChange={onChange}
          type={type}
          accept={accept}
          title={type === 'directory' ? '选择目录' : '选择文件'}
        />
      )}
    </>
  );
}