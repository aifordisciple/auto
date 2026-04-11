"use client";

import React, { useState, useEffect } from 'react';
import { X, FileText, Folder, Loader2, AlertCircle } from 'lucide-react';
import { BASE_URL } from '@/lib/api';

interface RenameModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  sourcePath: string;
  sourceName: string;
  isFolder: boolean;
  onSuccess: () => void;
}

export function RenameModal({
  isOpen,
  onClose,
  projectId,
  sourcePath,
  sourceName,
  isFolder,
  onSuccess
}: RenameModalProps) {
  const [newName, setNewName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 初始化名称
  useEffect(() => {
    if (isOpen && sourceName) {
      setNewName(sourceName);
      setError(null);
    }
  }, [isOpen, sourceName]);

  // 处理重命名
  const handleSubmit = async () => {
    if (!newName.trim()) {
      setError('名称不能为空');
      return;
    }

    if (newName === sourceName) {
      setError('新名称与原名称相同');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const token = localStorage.getItem('autonome_access_token');
      const response = await fetch(`${BASE_URL}/api/projects/${projectId}/files/rename`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          source_path: sourcePath,
          new_name: newName.trim()
        })
      });

      const result = await response.json();

      if (response.ok && result.status === 'success') {
        onSuccess();
        onClose();
      } else {
        setError(result.detail || result.message || '重命名失败');
      }
    } catch (e) {
      setError('网络错误，请稍后重试');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 键盘事件
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isSubmitting) {
      handleSubmit();
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#1a1a1c] border border-neutral-700 rounded-xl w-full max-w-md shadow-2xl animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-800">
          <div className="flex items-center gap-3">
            {isFolder ? (
              <div className="p-2 bg-purple-500/10 rounded-lg">
                <Folder size={18} className="text-purple-400" />
              </div>
            ) : (
              <div className="p-2 bg-blue-500/10 rounded-lg">
                <FileText size={18} className="text-blue-400" />
              </div>
            )}
            <h3 className="text-base font-semibold text-neutral-200">
              重命名{isFolder ? '文件夹' : '文件'}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="px-5 py-4">
          <div className="mb-4">
            <label className="block text-sm text-neutral-400 mb-2">
              {isFolder ? '文件夹名称' : '文件名称'}
            </label>
            <input
              type="text"
              value={newName}
              onChange={(e) => {
                setNewName(e.target.value);
                setError(null);
              }}
              onKeyDown={handleKeyDown}
              placeholder="输入新名称..."
              className="w-full px-4 py-2.5 bg-neutral-900 border border-neutral-700 rounded-lg text-neutral-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 placeholder:text-neutral-600"
              autoFocus
            />
          </div>

          {/* 原名称提示 */}
          <div className="text-xs text-neutral-500 mb-4">
            原名称: <span className="font-mono text-neutral-400">{sourceName}</span>
          </div>

          {/* 错误提示 */}
          {error && (
            <div className="flex items-center gap-2 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg mb-4">
              <AlertCircle size={14} className="text-red-400 shrink-0" />
              <span className="text-sm text-red-400">{error}</span>
            </div>
          )}

          {/* 提示信息 */}
          <div className="text-xs text-neutral-500">
            <span className="text-yellow-500">⚠️</span> 重命名后，相关引用可能需要更新
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-neutral-800 bg-neutral-900/30 rounded-b-xl">
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm text-neutral-300 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || !newName.trim() || newName === sourceName}
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {isSubmitting ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                处理中...
              </>
            ) : (
              '确认重命名'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}