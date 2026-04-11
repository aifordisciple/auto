"use client";

/**
 * HybridPathInput - 混合路径输入组件
 *
 * 功能说明：
 * - 支持手动输入路径字符串
 * - 支持通过 FilePicker 选择文件/目录
 * - 两种模式无缝切换，用户可自由选择
 *
 * 使用场景：
 * - 基因组表单中的路径字段
 * - 需要路径输入但希望提供文件选择便利的场景
 */

import React, { useState } from 'react';
import { FolderOpen, FileText } from 'lucide-react';
import { FilePicker } from './FilePicker';

// ==========================================
// 类型定义
// ==========================================

interface HybridPathInputProps {
  /** 项目 ID，用于 FilePicker 加载项目文件 */
  projectId: string;
  /** 当前路径值 */
  value: string;
  /** 路径变更回调 */
  onChange: (path: string) => void;
  /** 选择类型：文件或目录 */
  type: 'file' | 'directory';
  /** placeholder 文本 */
  placeholder?: string;
  /** 文件类型过滤（如 '.fa,.fasta'） */
  accept?: string;
  /** 禁用状态 */
  disabled?: boolean;
  /** 错误信息 */
  error?: string;
}

// ==========================================
// 主组件
// ==========================================

export function HybridPathInput({
  projectId,
  value,
  onChange,
  type,
  placeholder = '/path/to/file 或点击选择',
  accept,
  disabled = false,
  error
}: HybridPathInputProps) {
  // FilePicker 弹窗状态
  const [isPickerOpen, setIsPickerOpen] = useState(false);

  // 打开文件选择器
  const handleOpenPicker = () => {
    if (!projectId) {
      // 无项目时给出提示
      return;
    }
    setIsPickerOpen(true);
  };

  // 文件选择确认
  const handlePickerChange = (path: string) => {
    onChange(path);
    setIsPickerOpen(false);
  };

  // 文本输入变更
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value);
  };

  // 样式定义 - 保持与 GenomeFormModal 一致
  const inputClassName = `flex-1 bg-neutral-900 border rounded-lg px-3 py-2
    text-sm text-white outline-none focus:border-purple-500 font-mono text-xs
    ${error ? 'border-red-500' : 'border-neutral-700'}
    ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`;

  const buttonClassName = `shrink-0 px-2 py-2 bg-neutral-800 border
    border-neutral-700 rounded-lg hover:bg-neutral-700 hover:border-neutral-600
    transition-colors flex items-center justify-center
    ${!projectId || disabled ? 'opacity-50 cursor-not-allowed' : ''}`;

  return (
    <div className="flex gap-2 items-start">
      {/* 文本输入框 - 可手动输入路径 */}
      <input
        type="text"
        value={value}
        onChange={handleInputChange}
        disabled={disabled}
        className={inputClassName}
        placeholder={placeholder}
      />

      {/* 文件选择按钮 - 点击打开 FilePicker */}
      <button
        type="button"
        onClick={handleOpenPicker}
        disabled={!projectId || disabled}
        className={buttonClassName}
        title={!projectId ? '请先选择项目' : type === 'directory' ? '选择目录' : '选择文件'}
      >
        {type === 'directory' ? (
          <FolderOpen size={16} className={!projectId ? 'text-neutral-500' : 'text-purple-400'} />
        ) : (
          <FileText size={16} className={!projectId ? 'text-neutral-500' : 'text-blue-400'} />
        )}
      </button>

      {/* FilePicker 弹窗 */}
      {projectId && isPickerOpen && (
        <FilePicker
          isOpen={isPickerOpen}
          onClose={() => setIsPickerOpen(false)}
          projectId={projectId}
          value={value}
          onChange={handlePickerChange}
          type={type}
          accept={accept}
          title={type === 'directory' ? '选择目录' : '选择文件'}
        />
      )}
    </div>
  );
}