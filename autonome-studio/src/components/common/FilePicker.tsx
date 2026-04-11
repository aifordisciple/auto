/**
 * 文件选择器组件
 *
 * 提供统一的文件选择界面：
 * - 桌面端：直接打开本地文件选择对话框
 * - Web 端：通过数据中心选择文件
 */

import React, { useState, useCallback } from 'react';
import { clsx } from 'clsx';
import {
  isTauri,
  openFilePicker,
  FileFilters,
  type FileInfo,
  type FileFilter,
  type DialogOptions,
} from '@/adapter';

// cn helper
const cn = (...args: any[]) => clsx(args);

// ============================================
// 类型定义
// ============================================

export interface SelectedFile {
  /** 文件名 */
  name: string;
  /** 文件路径 */
  path: string;
  /** 文件大小 */
  size?: number;
}

export interface FilePickerProps {
  /** 选择的文件变化回调 */
  onChange?: (files: SelectedFile[]) => void;
  /** 初始选中的文件 */
  value?: SelectedFile[];
  /** 文件过滤器 */
  filters?: FileFilter[];
  /** 是否多选 */
  multiple?: boolean;
  /** 占位文本 */
  placeholder?: string;
  /** 是否禁用 */
  disabled?: boolean;
  /** 最大选择数量 */
  maxFiles?: number;
  /** 最大文件大小（字节） */
  maxSize?: number;
  /** 自定义类名 */
  className?: string;
  /** 打开数据中心的回调（Web 端使用） */
  onOpenDataCenter?: () => void;
}

// ============================================
// 组件实现
// ============================================

export function FilePicker({
  onChange,
  value = [],
  filters = [FileFilters.ALL],
  multiple = false,
  placeholder = '选择文件...',
  disabled = false,
  maxFiles = 10,
  maxSize,
  className,
  onOpenDataCenter,
}: FilePickerProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 处理选择文件
  const handleSelect = useCallback(async () => {
    if (disabled || isLoading) return;

    setIsLoading(true);
    setError(null);

    try {
      if (isTauri()) {
        // 桌面端：打开本地文件选择对话框
        const paths = await openFilePicker({
          filters,
          multiple,
        });

        if (paths.length > 0) {
          // 转换为统一格式
          const files: SelectedFile[] = paths.map((path) => {
            const name = path.split('/').pop() || path.split('\\').pop() || path;
            return { name, path };
          });

          // 检查最大数量
          if (multiple && files.length > maxFiles) {
            setError(`最多只能选择 ${maxFiles} 个文件`);
            return;
          }

          onChange?.(multiple ? [...value, ...files] : files);
        }
      } else {
        // Web 端：打开数据中心
        if (onOpenDataCenter) {
          onOpenDataCenter();
        } else {
          setError('请在数据中心选择文件');
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '选择文件失败');
    } finally {
      setIsLoading(false);
    }
  }, [disabled, isLoading, filters, multiple, maxFiles, value, onChange, onOpenDataCenter]);

  // 移除文件
  const handleRemove = useCallback(
    (index: number) => {
      const newFiles = [...value];
      newFiles.splice(index, 1);
      onChange?.(newFiles);
    },
    [value, onChange]
  );

  // 清空所有文件
  const handleClear = useCallback(() => {
    onChange?.([]);
  }, [onChange]);

  // 格式化文件大小
  const formatSize = (bytes?: number): string => {
    if (!bytes) return '';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    return `${size.toFixed(1)} ${units[unitIndex]}`;
  };

  return (
    <div className={cn('space-y-2', className)}>
      {/* 选择按钮 */}
      <button
        type="button"
        onClick={handleSelect}
        disabled={disabled || isLoading}
        className={cn(
          'w-full px-4 py-2 rounded-lg border border-gray-600',
          'bg-gray-800 hover:bg-gray-700 transition-colors',
          'text-sm text-gray-300',
          'flex items-center justify-center gap-2',
          disabled && 'opacity-50 cursor-not-allowed'
        )}
      >
        {isLoading ? (
          <>
            <svg
              className="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <span>处理中...</span>
          </>
        ) : (
          <>
            <svg
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <span>{isTauri() ? '选择本地文件' : '从数据中心选择'}</span>
          </>
        )}
      </button>

      {/* 错误提示 */}
      {error && (
        <p className="text-sm text-red-400 px-2">{error}</p>
      )}

      {/* 已选文件列表 */}
      {value.length > 0 && (
        <div className="space-y-1">
          <div className="flex items-center justify-between px-2">
            <span className="text-xs text-gray-500">
              已选择 {value.length} 个文件
            </span>
            {value.length > 0 && (
              <button
                type="button"
                onClick={handleClear}
                className="text-xs text-red-400 hover:text-red-300"
              >
                清空
              </button>
            )}
          </div>

          <ul className="space-y-1">
            {value.map((file, index) => (
              <li
                key={`${file.path}-${index}`}
                className="flex items-center justify-between px-3 py-2 bg-gray-800/50 rounded-lg"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {/* 文件图标 */}
                  <svg
                    className="h-4 w-4 flex-shrink-0 text-blue-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>

                  {/* 文件名 */}
                  <span className="text-sm text-gray-300 truncate">
                    {file.name}
                  </span>

                  {/* 文件大小 */}
                  {file.size && (
                    <span className="text-xs text-gray-500 flex-shrink-0">
                      ({formatSize(file.size)})
                    </span>
                  )}
                </div>

                {/* 删除按钮 */}
                <button
                  type="button"
                  onClick={() => handleRemove(index)}
                  className="flex-shrink-0 p-1 hover:bg-gray-700 rounded"
                >
                  <svg
                    className="h-4 w-4 text-gray-500 hover:text-red-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 空状态 */}
      {value.length === 0 && !isLoading && (
        <p className="text-sm text-gray-500 text-center py-4">
          {placeholder}
        </p>
      )}
    </div>
  );
}

// ============================================
// 便捷组件
// ============================================

/**
 * 数据文件选择器
 *
 * 预设了常用数据文件格式的过滤器
 */
export function DataFilePicker(props: Omit<FilePickerProps, 'filters'>) {
  return (
    <FilePicker
      {...props}
      filters={[FileFilters.DATA_FILES, FileFilters.FASTQ, FileFilters.BAM, FileFilters.ALL]}
    />
  );
}

/**
 * 图片文件选择器
 */
export function ImageFilePicker(props: Omit<FilePickerProps, 'filters'>) {
  return <FilePicker {...props} filters={[FileFilters.IMAGES, FileFilters.ALL]} />;
}

export default FilePicker;