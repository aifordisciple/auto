/**
 * SampleTableEditor - 样本表格编辑器
 *
 * 功能：
 * 1. 可视化编辑 Sample Sheet 表格（类 Excel 体验）
 * 2. 支持添加/删除行
 * 3. 支持导入/导出 TSV
 * 4. 实时验证数据有效性
 */

'use client';

import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Plus,
  Trash2,
  Download,
  Upload,
  ChevronLeft,
  Save,
  Loader2,
  AlertTriangle,
  CheckCircle,
  FileText
} from "lucide-react";
import { toast } from 'sonner';

// ==========================================
// 类型定义
// ==========================================

export interface ColumnConfig {
  key: string;
  label: string;
  required: boolean;
  editable: boolean;
  options?: string[];
  description?: string;
}

export interface TableData {
  columns: ColumnConfig[];
  rows: Record<string, string>[];
}

interface SampleTableEditorProps {
  data: TableData;
  columnConfig: ColumnConfig[];
  onChange: (data: TableData) => void;
  onSave: () => void;
  onBack: () => void;
  isLoading: boolean;
  /** 自定义文件名 */
  filename: string;
  /** 文件名变更回调 */
  onFilenameChange: (name: string) => void;
}

// ==========================================
// 文件名验证函数
// ==========================================

/**
 * 验证文件名格式
 * 规则：
 * - 必须以 .tsv 结尾
 * - 基础名长度 3-100 字符
 * - 只允许字母、数字、下划线、横线和点
 *
 * @param name 文件名
 * @returns 验证结果 { valid, error }
 */
const validateFilename = (name: string): { valid: boolean; error?: string } => {
  if (!name.trim()) {
    return { valid: false, error: '文件名不能为空' };
  }
  if (!name.endsWith('.tsv')) {
    return { valid: false, error: '文件名必须以 .tsv 结尾' };
  }
  const baseName = name.slice(0, -4);
  if (baseName.length < 3) {
    return { valid: false, error: '文件名长度至少 3 个字符' };
  }
  if (baseName.length > 100) {
    return { valid: false, error: '文件名长度不能超过 100 字符' };
  }
  // 只允许字母、数字、下划线、横线和点
  if (!/^[a-zA-Z0-9_\-\.]+$/.test(baseName)) {
    return { valid: false, error: '文件名只能包含字母、数字、下划线、横线和点' };
  }
  return { valid: true };
};

// ==========================================
// 组件
// ==========================================

export function SampleTableEditor({
  data,
  columnConfig,
  onChange,
  onSave,
  onBack,
  isLoading,
  filename,
  onFilenameChange
}: SampleTableEditorProps) {
  // 状态
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
  const [editingCell, setEditingCell] = useState<{ row: number; col: string } | null>(null);
  const [cellValue, setCellValue] = useState('');
  const [filenameError, setFilenameError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 使用 columnConfig 作为列定义
  const columns = useMemo(() => columnConfig, [columnConfig]);

  // 当列配置变化时，更新表格数据
  useEffect(() => {
    if (columns.length > 0 && data.rows.length > 0) {
      // 确保所有行都有所有列
      const updatedRows = data.rows.map(row => {
        const newRow = { ...row };
        columns.forEach(col => {
          if (!(col.key in newRow)) {
            newRow[col.key] = '';
          }
        });
        return newRow;
      });
      if (JSON.stringify(updatedRows) !== JSON.stringify(data.rows)) {
        onChange({ columns, rows: updatedRows });
      }
    }
  }, [columns]);

  // 验证数据
  const validation = useMemo(() => {
    const errors: { row: number; col: string; message: string }[] = [];

    data.rows.forEach((row, rowIndex) => {
      columns.forEach(col => {
        if (col.required && !row[col.key]?.trim()) {
          errors.push({
            row: rowIndex,
            col: col.key,
            message: `${col.label} 是必填项`
          });
        }
      });
    });

    // 检查样本名重复
    const sampleNames = data.rows.map(r => r.sample_name || r.name).filter(Boolean);
    const duplicates = sampleNames.filter((name, idx) => sampleNames.indexOf(name) !== idx);
    if (duplicates.length > 0) {
      errors.push({
        row: -1,
        col: 'sample_name',
        message: `样本名重复: ${[...new Set(duplicates)].join(', ')}`
      });
    }

    return {
      valid: errors.length === 0,
      errors
    };
  }, [data, columns]);

  // 添加行
  const handleAddRow = () => {
    const newRow: Record<string, string> = {};
    columns.forEach(col => {
      newRow[col.key] = '';
    });
    onChange({ ...data, rows: [...data.rows, newRow] });
  };

  // 删除选中行
  const handleDeleteRows = () => {
    if (selectedRows.size === 0) {
      toast.error('请先选择要删除的行');
      return;
    }

    const newRows = data.rows.filter((_, idx) => !selectedRows.has(idx));
    onChange({ ...data, rows: newRows });
    setSelectedRows(new Set());
    toast.success(`已删除 ${selectedRows.size} 行`);
  };

  // 切换行选择
  const toggleRowSelection = (index: number) => {
    const newSelected = new Set(selectedRows);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelectedRows(newSelected);
  };

  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedRows.size === data.rows.length) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(data.rows.map((_, i) => i)));
    }
  };

  // 开始编辑单元格
  const startEditing = (row: number, col: string, value: string) => {
    setEditingCell({ row, col });
    setCellValue(value);
    setTimeout(() => inputRef.current?.select(), 0);
  };

  // 完成编辑
  const finishEditing = () => {
    if (editingCell) {
      const newRows = [...data.rows];
      newRows[editingCell.row] = {
        ...newRows[editingCell.row],
        [editingCell.col]: cellValue
      };
      onChange({ ...data, rows: newRows });
      setEditingCell(null);
    }
  };

  // 取消编辑
  const cancelEditing = () => {
    setEditingCell(null);
  };

  // 导出 TSV
  const handleExportTsv = () => {
    const header = columns.map(c => c.key).join('\t');
    const rows = data.rows.map(row =>
      columns.map(col => row[col.key] || '').join('\t')
    );
    const tsv = [header, ...rows].join('\n');

    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    // 使用自定义文件名，如果验证失败则使用默认格式
    const exportFilename = filename.trim() || `sample_sheet_${Date.now()}.tsv`;
    a.download = exportFilename;
    a.click();
    URL.revokeObjectURL(url);

    toast.success('已导出 TSV 文件');
  };

  /**
   * 处理文件名变更
   * 实时验证文件名格式，显示错误提示
   */
  const handleFilenameChange = (name: string) => {
    onFilenameChange(name);
    // 实时验证
    const result = validateFilename(name);
    setFilenameError(result.valid ? null : result.error || null);
  };

  // 渲染单元格
  const renderCell = (row: Record<string, string>, rowIndex: number, col: ColumnConfig) => {
    const isEditing = editingCell?.row === rowIndex && editingCell?.col === col.key;
    const value = row[col.key] || '';
    const hasError = !col.required || !value.trim()
      ? validation.errors.find(e => e.row === rowIndex && e.col === col.key)
      : null;

    if (isEditing) {
      if (col.options) {
        return (
          <select
            ref={inputRef as any}
            value={cellValue}
            onChange={(e) => setCellValue(e.target.value)}
            onBlur={finishEditing}
            autoFocus
            className="w-full bg-neutral-700 border border-blue-500 rounded px-2 py-1 text-sm text-white outline-none"
          >
            <option value="">请选择...</option>
            {col.options.map(opt => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        );
      }

      return (
        <input
          ref={inputRef}
          type="text"
          value={cellValue}
          onChange={(e) => setCellValue(e.target.value)}
          onBlur={finishEditing}
          onKeyDown={(e) => {
            if (e.key === 'Enter') finishEditing();
            if (e.key === 'Escape') cancelEditing();
          }}
          autoFocus
          className="w-full bg-neutral-700 border border-blue-500 rounded px-2 py-1 text-sm text-white outline-none"
        />
      );
    }

    return (
      <div
        onClick={() => col.editable && startEditing(rowIndex, col.key, value)}
        className={`min-h-[24px] px-2 py-1 text-sm rounded cursor-text ${
          col.editable ? 'hover:bg-neutral-700' : 'bg-neutral-800/50 text-neutral-500'
        } ${hasError ? 'bg-red-500/10 border border-red-500/30' : ''}`}
        title={col.editable ? '点击编辑' : '不可编辑'}
      >
        {value || <span className="text-neutral-600 italic">点击填写</span>}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col">
      {/* 工具栏 */}
      <div className="shrink-0 p-3 pb-8 border-b border-neutral-800 flex items-center justify-between bg-neutral-900/30">
        <div className="flex items-center gap-2">
          <button
            onClick={onBack}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
          >
            <ChevronLeft size={16} />
            返回
          </button>

          <div className="w-px h-5 bg-neutral-700 mx-1" />

          {/* 文件名输入框 */}
          <div className="flex items-center gap-2">
            <FileText size={14} className="text-neutral-500" />
            <div className="relative">
              <input
                type="text"
                value={filename}
                onChange={(e) => handleFilenameChange(e.target.value)}
                placeholder="samples_20260320.tsv"
                className={`w-52 px-2 py-1 text-sm bg-neutral-800 border rounded text-white placeholder-neutral-600 focus:outline-none ${
                  filenameError
                    ? 'border-red-500 focus:border-red-400'
                    : 'border-neutral-700 focus:border-blue-500'
                }`}
                title={filenameError || '自定义文件名'}
              />
              {filenameError && (
                <span className="absolute -bottom-5 left-0 text-xs text-red-400 whitespace-nowrap">
                  {filenameError}
                </span>
              )}
            </div>
          </div>

          <div className="w-px h-5 bg-neutral-700 mx-1" />

          <button
            onClick={handleAddRow}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-neutral-300 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
          >
            <Plus size={16} />
            添加行
          </button>

          <button
            onClick={handleDeleteRows}
            disabled={selectedRows.size === 0}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-neutral-400 hover:text-red-400 hover:bg-red-500/10 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            <Trash2 size={16} />
            删除 ({selectedRows.size})
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleExportTsv}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
          >
            <Download size={16} />
            导出 TSV
          </button>

          <button
            onClick={onSave}
            disabled={isLoading || !validation.valid || !!filenameError}
            className="flex items-center gap-1 px-4 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-lg transition-colors"
          >
            {isLoading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                保存中...
              </>
            ) : (
              <>
                <Save size={16} />
                保存 Sample Sheet
              </>
            )}
          </button>
        </div>
      </div>

      {/* 验证错误提示 */}
      {validation.errors.length > 0 && (
        <div className="shrink-0 px-4 py-2 bg-red-500/10 border-b border-red-500/20 flex items-center gap-2">
          <AlertTriangle size={16} className="text-red-400" />
          <span className="text-sm text-red-300">
            {validation.errors[0].message}
            {validation.errors.length > 1 && ` (还有 ${validation.errors.length - 1} 个错误)`}
          </span>
        </div>
      )}

      {/* 表格 */}
      <div className="flex-1 overflow-auto custom-scrollbar">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-[#141416]">
            <tr className="border-b border-neutral-700">
              {/* 选择列 */}
              <th className="w-10 p-2 text-center">
                <input
                  type="checkbox"
                  checked={selectedRows.size === data.rows.length && data.rows.length > 0}
                  onChange={toggleSelectAll}
                  className="w-4 h-4 rounded border-neutral-600 bg-neutral-800 text-blue-500"
                />
              </th>

              {/* 数据列 */}
              {columns.map(col => (
                <th key={col.key} className="text-left p-2 border-b border-neutral-700">
                  <div className="flex items-center gap-1">
                    <span className="text-sm font-medium text-neutral-300">{col.label}</span>
                    {col.required && (
                      <span className="text-red-400 text-xs">*</span>
                    )}
                  </div>
                  {col.description && (
                    <p className="text-xs text-neutral-500 mt-0.5">{col.description}</p>
                  )}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {data.rows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className={`border-b border-neutral-800/50 ${
                  selectedRows.has(rowIndex) ? 'bg-blue-500/5' : 'hover:bg-neutral-800/30'
                }`}
              >
                {/* 选择框 */}
                <td className="p-2 text-center">
                  <input
                    type="checkbox"
                    checked={selectedRows.has(rowIndex)}
                    onChange={() => toggleRowSelection(rowIndex)}
                    className="w-4 h-4 rounded border-neutral-600 bg-neutral-800 text-blue-500"
                  />
                </td>

                {/* 数据单元格 */}
                {columns.map(col => (
                  <td key={col.key} className="p-0 border-b border-neutral-800/30">
                    {renderCell(row, rowIndex, col)}
                  </td>
                ))}
              </tr>
            ))}

            {/* 空状态 */}
            {data.rows.length === 0 && (
              <tr>
                <td colSpan={columns.length + 1} className="p-8 text-center">
                  <div className="flex flex-col items-center gap-2 text-neutral-500">
                    <p className="text-sm">暂无数据</p>
                    <button
                      onClick={handleAddRow}
                      className="text-sm text-blue-400 hover:text-blue-300"
                    >
                      + 添加第一行
                    </button>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 底部状态栏 */}
      <div className="shrink-0 p-2 border-t border-neutral-800 flex items-center justify-between text-xs text-neutral-500">
        <span>共 {data.rows.length} 行</span>
        {validation.valid ? (
          <span className="flex items-center gap-1 text-green-400">
            <CheckCircle size={12} />
            数据验证通过
          </span>
        ) : (
          <span className="flex items-center gap-1 text-red-400">
            <AlertTriangle size={12} />
            {validation.errors.length} 个错误需要修复
          </span>
        )}
      </div>
    </div>
  );
}

export default SampleTableEditor;