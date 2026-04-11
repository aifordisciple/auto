/**
 * ComparisonGroupEditor - 比较组编辑器组件
 *
 * 功能：
 * 1. 从分组列表选择 case_group 和 control_group
 * 2. 支持添加/删除比较组
 * 3. 实时验证（检查分组是否存在、比较组是否重复）
 * 4. 支持自动生成所有可能组合的快捷按钮
 *
 * 使用场景：
 * - RNA-seq 差异分析定义比较组
 * - 单细胞差异分析定义比较组
 */

'use client';

import React, { useState, useMemo, useCallback } from 'react';
import {
  Plus,
  Trash2,
  Sparkles,
  ChevronDown,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  X
} from "lucide-react";
import { toast } from 'sonner';

import {
  ComparisonGroup,
  ComparisonTableData,
  inferComparisonGroups,
  validateComparisonGroups
} from './utils';

// ==========================================
// 类型定义
// ==========================================

interface ComparisonGroupEditorProps {
  /** 可用的分组列表（从 Sample Sheet 提取） */
  availableGroups: string[];
  /** 比较组数据 */
  data: ComparisonTableData;
  /** 数据变更回调 */
  onChange: (data: ComparisonTableData) => void;
  /** 是否禁用 */
  disabled?: boolean;
}

// ==========================================
// 组件
// ==========================================

export function ComparisonGroupEditor({
  availableGroups,
  data,
  onChange,
  disabled = false
}: ComparisonGroupEditorProps) {
  // 状态
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
  const [newCaseGroup, setNewCaseGroup] = useState('');
  const [newControlGroup, setNewControlGroup] = useState('');

  // ==========================================
  // 验证
  // ==========================================

  const validation = useMemo(() => {
    return validateComparisonGroups(data.comparisons, availableGroups);
  }, [data.comparisons, availableGroups]);

  // ==========================================
  // 操作方法
  // ==========================================

  /**
   * 添加新的比较组
   */
  const handleAddComparison = useCallback(() => {
    if (!newCaseGroup.trim()) {
      toast.error('请选择实验组');
      return;
    }
    if (!newControlGroup.trim()) {
      toast.error('请选择对照组');
      return;
    }
    if (newCaseGroup === newControlGroup) {
      toast.error('实验组和对照组不能相同');
      return;
    }

    // 检查是否已存在相同组合
    const exists = data.comparisons.some(
      comp => comp.case_group === newCaseGroup && comp.control_group === newControlGroup
    );
    if (exists) {
      toast.warning('该比较组组合已存在');
      return;
    }

    const newComparison: ComparisonGroup = {
      case_group: newCaseGroup,
      control_group: newControlGroup,
      comparison_name: `${newCaseGroup}_vs_${newControlGroup}`
    };

    onChange({
      comparisons: [...data.comparisons, newComparison]
    });

    // 清空选择
    setNewCaseGroup('');
    setNewControlGroup('');

    toast.success('已添加比较组');
  }, [newCaseGroup, newControlGroup, data.comparisons, onChange]);

  /**
   * 删除选中的比较组
   */
  const handleDeleteSelected = useCallback(() => {
    if (selectedRows.size === 0) {
      toast.error('请先选择要删除的比较组');
      return;
    }

    const newComparisons = data.comparisons.filter(
      (_, idx) => !selectedRows.has(idx)
    );

    onChange({ comparisons: newComparisons });
    setSelectedRows(new Set());

    toast.success(`已删除 ${selectedRows.size} 个比较组`);
  }, [selectedRows, data.comparisons, onChange]);

  /**
   * 清空所有比较组
   */
  const handleClearAll = useCallback(() => {
    if (data.comparisons.length === 0) {
      return;
    }

    onChange({ comparisons: [] });
    setSelectedRows(new Set());

    toast.success('已清空所有比较组');
  }, [data.comparisons, onChange]);

  /**
   * 自动生成所有可能的比较组组合
   */
  const handleAutoGenerate = useCallback(() => {
    if (availableGroups.length < 2) {
      toast.error('分组数量不足（需要至少 2 个分组）');
      return;
    }

    const inferredComparisons = inferComparisonGroups(availableGroups);

    if (inferredComparisons.length === 0) {
      toast.error('无法生成比较组');
      return;
    }

    onChange({ comparisons: inferredComparisons });
    setSelectedRows(new Set());

    toast.success(`已自动生成 ${inferredComparisons.length} 个比较组`);
  }, [availableGroups, onChange]);

  /**
   * 切换行选择
   */
  const toggleRowSelection = (index: number) => {
    const newSelected = new Set(selectedRows);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelectedRows(newSelected);
  };

  /**
   * 全选/取消全选
   */
  const toggleSelectAll = () => {
    if (selectedRows.size === data.comparisons.length && data.comparisons.length > 0) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(data.comparisons.map((_, i) => i)));
    }
  };

  // ==========================================
  // 渲染
  // ==========================================

  return (
    <div className="h-full flex flex-col">
      {/* 工具栏 */}
      <div className="shrink-0 p-3 border-b border-neutral-800 flex items-center justify-between bg-neutral-900/30">
        {/* 左侧操作 */}
        <div className="flex items-center gap-2">
          {/* 添加新比较组 */}
          <div className="flex items-center gap-1">
            <select
              value={newCaseGroup}
              onChange={(e) => setNewCaseGroup(e.target.value)}
              disabled={disabled}
              className="w-28 px-2 py-1 text-sm bg-neutral-800 border border-neutral-700 rounded text-white disabled:opacity-50"
              title="选择实验组"
            >
              <option value="">实验组...</option>
              {availableGroups.map(g => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>

            <span className="text-sm text-neutral-500">vs</span>

            <select
              value={newControlGroup}
              onChange={(e) => setNewControlGroup(e.target.value)}
              disabled={disabled}
              className="w-28 px-2 py-1 text-sm bg-neutral-800 border border-neutral-700 rounded text-white disabled:opacity-50"
              title="选择对照组"
            >
              <option value="">对照组...</option>
              {availableGroups.map(g => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>

            <button
              onClick={handleAddComparison}
              disabled={disabled || !newCaseGroup || !newControlGroup}
              className="flex items-center gap-1 px-2 py-1 text-sm bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded transition-colors"
            >
              <Plus size={14} />
              添加
            </button>
          </div>

          <div className="w-px h-5 bg-neutral-700 mx-1" />

          {/* 快捷操作 */}
          <button
            onClick={handleAutoGenerate}
            disabled={disabled || availableGroups.length < 2}
            className="flex items-center gap-1 px-2 py-1 text-sm text-purple-400 hover:text-purple-300 hover:bg-purple-500/10 disabled:opacity-50 rounded transition-colors"
            title="自动生成所有可能的比较组组合"
          >
            <Sparkles size={14} />
            自动生成
          </button>

          <button
            onClick={handleDeleteSelected}
            disabled={disabled || selectedRows.size === 0}
            className="flex items-center gap-1 px-2 py-1 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 disabled:opacity-50 rounded transition-colors"
          >
            <Trash2 size={14} />
            删除 ({selectedRows.size})
          </button>

          <button
            onClick={handleClearAll}
            disabled={disabled || data.comparisons.length === 0}
            className="flex items-center gap-1 px-2 py-1 text-sm text-neutral-400 hover:text-neutral-300 hover:bg-neutral-800 disabled:opacity-50 rounded transition-colors"
            title="清空所有比较组"
          >
            <X size={14} />
            清空
          </button>
        </div>

        {/* 右侧状态 */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-neutral-500">
            可用分组: {availableGroups.length} 个
          </span>
          <span className="text-xs px-2 py-0.5 rounded bg-neutral-800 text-neutral-400">
            比较组: {data.comparisons.length} 个
          </span>
        </div>
      </div>

      {/* 验证错误提示 */}
      {validation.errors.length > 0 && (
        <div className="shrink-0 px-4 py-2 bg-red-500/10 border-b border-red-500/20 flex items-center gap-2">
          <AlertTriangle size={16} className="text-red-400" />
          <span className="text-sm text-red-300">
            {validation.errors[0]}
            {validation.errors.length > 1 && ` (还有 ${validation.errors.length - 1} 个错误)`}
          </span>
        </div>
      )}

      {/* 分组提示 */}
      {availableGroups.length < 2 && (
        <div className="shrink-0 px-4 py-2 bg-yellow-500/10 border-b border-yellow-500/20 flex items-center gap-2">
          <AlertTriangle size={16} className="text-yellow-400" />
          <span className="text-sm text-yellow-300">
            分组数量不足（需要至少 2 个分组才能定义比较组）
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
                  checked={selectedRows.size === data.comparisons.length && data.comparisons.length > 0}
                  onChange={toggleSelectAll}
                  disabled={disabled}
                  className="w-4 h-4 rounded border-neutral-600 bg-neutral-800 text-blue-500"
                />
              </th>

              {/* 数据列 */}
              <th className="text-left p-2 border-b border-neutral-700">
                <span className="text-sm font-medium text-orange-300">实验组 (Case)</span>
              </th>
              <th className="text-left p-2 border-b border-neutral-700">
                <span className="text-sm font-medium text-blue-300">对照组 (Control)</span>
              </th>
              <th className="text-left p-2 border-b border-neutral-700">
                <span className="text-sm font-medium text-neutral-300">比较组名称</span>
              </th>
            </tr>
          </thead>

          <tbody>
            {data.comparisons.map((comp, rowIndex) => {
              const hasError = !availableGroups.includes(comp.case_group) ||
                               !availableGroups.includes(comp.control_group);

              return (
                <tr
                  key={rowIndex}
                  className={`border-b border-neutral-800/50 ${
                    selectedRows.has(rowIndex) ? 'bg-blue-500/5' : 'hover:bg-neutral-800/30'
                  } ${hasError ? 'bg-red-500/5' : ''}`}
                >
                  {/* 选择框 */}
                  <td className="p-2 text-center">
                    <input
                      type="checkbox"
                      checked={selectedRows.has(rowIndex)}
                      onChange={() => toggleRowSelection(rowIndex)}
                      disabled={disabled}
                      className="w-4 h-4 rounded border-neutral-600 bg-neutral-800 text-blue-500"
                    />
                  </td>

                  {/* 实验组 */}
                  <td className="p-2">
                    <div className={`px-2 py-1 text-sm rounded ${
                      !availableGroups.includes(comp.case_group)
                        ? 'text-red-400 bg-red-500/10'
                        : 'text-orange-300 bg-orange-500/10'
                    }`}>
                      {comp.case_group}
                    </div>
                  </td>

                  {/* 对照组 */}
                  <td className="p-2">
                    <div className={`px-2 py-1 text-sm rounded ${
                      !availableGroups.includes(comp.control_group)
                        ? 'text-red-400 bg-red-500/10'
                        : 'text-blue-300 bg-blue-500/10'
                    }`}>
                      {comp.control_group}
                    </div>
                  </td>

                  {/* 比较组名称 */}
                  <td className="p-2">
                    <span className="text-sm text-neutral-300">
                      {comp.comparison_name}
                    </span>
                  </td>
                </tr>
              );
            })}

            {/* 空状态 */}
            {data.comparisons.length === 0 && (
              <tr>
                <td colSpan={4} className="p-8 text-center">
                  <div className="flex flex-col items-center gap-2 text-neutral-500">
                    <p className="text-sm">暂无比较组定义</p>
                    {availableGroups.length >= 2 ? (
                      <button
                        onClick={handleAutoGenerate}
                        disabled={disabled}
                        className="text-sm text-purple-400 hover:text-purple-300 disabled:opacity-50"
                      >
                        <Sparkles size={14} className="inline mr-1" />
                        自动生成所有组合
                      </button>
                    ) : (
                      <p className="text-xs text-yellow-400">
                        请先在 Sample Sheet 中定义分组
                      </p>
                    )}
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 底部状态栏 */}
      <div className="shrink-0 p-2 border-t border-neutral-800 flex items-center justify-between text-xs text-neutral-500">
        <span>共 {data.comparisons.length} 个比较组</span>
        {validation.valid ? (
          <span className="flex items-center gap-1 text-green-400">
            <CheckCircle size={12} />
            验证通过
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

export default ComparisonGroupEditor;