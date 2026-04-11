/**
 * SkillSheetInput - Sample Sheet 输入组件
 *
 * 用于 SkillExecutePanel 中 sample-table 类型参数的输入。
 * 支持两种模式：
 * 1. 选择已有的 Sample Sheet 文件
 * 2. 打开生成器创建新的 Sample Sheet
 */

'use client';

import React, { useState, useEffect } from 'react';
import {
  FileText,
  Plus,
  Table,
  ChevronDown,
  Loader2,
  FolderOpen
} from "lucide-react";
import { toast } from 'sonner';
import { BASE_URL, fetchAPI } from "@/lib/api";
import { SampleSheetGenerator } from './index';

// ==========================================
// 类型定义
// ==========================================

interface SavedSheet {
  filename: string;
  path: string;
  size_bytes: number;
  created_at: number;
  modified_at: number;
}

interface SkillSheetInputProps {
  projectId: string;
  skillId: string;
  value: string;
  onChange: (path: string) => void;
  skillType: 'fastqc' | 'singlecell' | 'generic';
}

// ==========================================
// 组件
// ==========================================

export function SkillSheetInput({
  projectId,
  skillId,
  value,
  onChange,
  skillType
}: SkillSheetInputProps) {
  // 状态
  const [savedSheets, setSavedSheets] = useState<SavedSheet[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [showGenerator, setShowGenerator] = useState(false);

  // 加载已保存的 Sample Sheets
  useEffect(() => {
    loadSavedSheets();
  }, [projectId]);

  const loadSavedSheets = async () => {
    if (!projectId) return;

    setIsLoading(true);
    try {
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${BASE_URL}/api/projects/${projectId}/sample-sheets`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      const data = await res.json();

      if (data.status === 'success') {
        setSavedSheets(data.sheets || []);
      }
    } catch (e) {
      console.error('Failed to load saved sheets:', e);
    } finally {
      setIsLoading(false);
    }
  };

  // 选择已保存的文件
  const handleSelectSaved = (sheet: SavedSheet) => {
    onChange(sheet.path);
    setShowDropdown(false);
  };

  // 处理生成器确认
  const handleGeneratorConfirm = (path: string) => {
    onChange(path);
    setShowGenerator(false);
    loadSavedSheets(); // 刷新列表
  };

  // 获取文件名显示
  const displayValue = value
    ? value.split('/').pop() || value
    : '点击选择或创建 Sample Sheet';

  return (
    <div className="relative">
      {/* 主按钮 */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setShowDropdown(!showDropdown)}
          className="flex-1 flex items-center gap-2 px-3 py-2 text-sm border border-neutral-700 rounded-lg bg-neutral-800 hover:border-neutral-600 transition-colors text-left"
        >
          <Table size={14} className={value ? 'text-green-400' : 'text-neutral-500'} />
          <span className={`flex-1 truncate ${value ? 'text-neutral-200' : 'text-neutral-500'}`}>
            {displayValue}
          </span>
          <ChevronDown size={14} className={`text-neutral-500 transition-transform ${showDropdown ? 'rotate-180' : ''}`} />
        </button>

        {/* 创建新按钮 */}
        <button
          type="button"
          onClick={() => setShowGenerator(true)}
          className="flex items-center gap-1 px-3 py-2 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
          title="创建新的 Sample Sheet"
        >
          <Plus size={14} />
          创建
        </button>
      </div>

      {/* 下拉列表 */}
      {showDropdown && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-neutral-800 border border-neutral-700 rounded-lg shadow-xl z-50 max-h-[200px] overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-4 text-neutral-500">
              <Loader2 size={16} className="animate-spin" />
            </div>
          ) : savedSheets.length === 0 ? (
            <div className="py-4 text-center text-neutral-500 text-sm">
              <FolderOpen size={24} className="mx-auto mb-2 opacity-50" />
              暂无已保存的 Sample Sheet
            </div>
          ) : (
            <div className="py-1">
              {savedSheets.map((sheet) => (
                <button
                  key={sheet.path}
                  type="button"
                  onClick={() => handleSelectSaved(sheet)}
                  className={`w-full text-left px-3 py-2 hover:bg-neutral-700 transition-colors flex items-center gap-2 ${
                    value === sheet.path ? 'bg-blue-500/10 text-blue-300' : 'text-neutral-300'
                  }`}
                >
                  <FileText size={14} className="text-neutral-500" />
                  <span className="flex-1 truncate text-sm">{sheet.filename}</span>
                  <span className="text-xs text-neutral-500">
                    {new Date(sheet.modified_at).toLocaleDateString()}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 点击外部关闭下拉 */}
      {showDropdown && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setShowDropdown(false)}
        />
      )}

      {/* Sample Sheet 生成器弹窗 */}
      {showGenerator && (
        <SampleSheetGenerator
          isOpen={showGenerator}
          onClose={() => setShowGenerator(false)}
          projectId={projectId}
          skillId={skillId}
          skillType={skillType}
          onConfirm={handleGeneratorConfirm}
        />
      )}
    </div>
  );
}

export default SkillSheetInput;