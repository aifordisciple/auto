"use client";

import React, { useState, useEffect, useRef } from 'react';
import { X, FolderPlus, Loader2, Folder } from "lucide-react";
import { createFolder } from "@/lib/api";

interface CreateFolderModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  parentPath: string;
  onSuccess: () => void;
}

export function CreateFolderModal({ isOpen, onClose, projectId, parentPath, onSuccess }: CreateFolderModalProps) {
  const [folderName, setFolderName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 自动聚焦
  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  // 重置状态
  useEffect(() => {
    if (!isOpen) {
      setFolderName('');
      setError(null);
      setIsLoading(false);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!folderName.trim()) {
      setError('请输入文件夹名称');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      await createFolder(projectId, {
        parent_path: parentPath,
        folder_name: folderName.trim()
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || '创建失败，请重试');
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#1a1a1c] border border-neutral-700 rounded-xl w-full max-w-md shadow-2xl animate-in zoom-in-95 duration-200">

        {/* Header */}
        <div className="h-14 shrink-0 border-b border-neutral-800 px-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/20 border border-purple-500/30 rounded-lg text-purple-400">
              <FolderPlus size={18} />
            </div>
            <h3 className="text-white font-semibold text-sm tracking-wide">创建新文件夹</h3>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors disabled:opacity-50"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {/* 父目录显示 */}
          <div className="space-y-1.5">
            <label className="text-xs text-neutral-500 font-medium uppercase tracking-wider">父目录</label>
            <div className="flex items-center gap-2 px-3 py-2.5 bg-neutral-900 border border-neutral-800 rounded-lg text-sm text-neutral-400">
              <Folder size={14} className="text-purple-400 shrink-0" />
              <span className="font-mono truncate">{parentPath}</span>
            </div>
          </div>

          {/* 文件夹名称输入 */}
          <div className="space-y-1.5">
            <label className="text-xs text-neutral-500 font-medium uppercase tracking-wider">文件夹名称</label>
            <input
              ref={inputRef}
              type="text"
              value={folderName}
              onChange={(e) => setFolderName(e.target.value)}
              placeholder="输入文件夹名称..."
              disabled={isLoading}
              className="w-full bg-neutral-950 border border-neutral-700 rounded-lg px-3 py-2.5 text-sm text-neutral-200 outline-none focus:border-purple-500/50 transition-all placeholder:text-neutral-600 disabled:opacity-50"
            />
          </div>

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
              disabled={isLoading}
              className="px-4 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isLoading || !folderName.trim()}
              className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm font-medium rounded-lg transition-colors shadow-lg shadow-purple-900/20"
            >
              {isLoading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  创建中...
                </>
              ) : (
                <>
                  <FolderPlus size={16} />
                  创建
                </>
              )}
            </button>
          </div>
        </form>

      </div>
    </div>
  );
}