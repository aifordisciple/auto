/**
 * DataPreviewCard - 数据预览卡片组件
 *
 * 显示数据文件的列信息和统计摘要
 * 用于 AI 回复中嵌入的数据探针结果
 */
"use client";

import { memo, useMemo } from 'react';
import {
  Table,
  FileSpreadsheet,
  Rows3,
  Columns3,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useState } from 'react';

// ==========================================
// 类型定义
// ==========================================

interface DataColumn {
  name: string;
  type: string;
  sample?: string;
}

interface DataPreviewCardProps {
  /** 数据源文件名 */
  filename: string;
  /** 列信息 */
  columns: DataColumn[];
  /** 行数 */
  rowCount: number;
  /** 文件格式（csv, tsv, h5ad 等） */
  format?: string;
}

// ==========================================
// 列类型到颜色的映射
// ==========================================

const TYPE_COLOR_MAP: Record<string, string> = {
  int: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  float: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  numeric: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  string: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  categorical: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  bool: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
  datetime: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
};

const DEFAULT_TYPE_COLOR = 'bg-neutral-500/10 text-neutral-400 border-neutral-500/20';

// ==========================================
// 主组件
// ==========================================

export const DataPreviewCard = memo(function DataPreviewCard({
  filename,
  columns,
  rowCount,
  format,
}: DataPreviewCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  // 按类型分组列
  const columnsByType = useMemo(() => {
    const groups: Record<string, string[]> = {};
    for (const col of columns) {
      const type = col.type || 'unknown';
      if (!groups[type]) groups[type] = [];
      groups[type].push(col.name);
    }
    return groups;
  }, [columns]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="w-full bg-[#1a1a1b] border border-neutral-700/60 rounded-xl overflow-hidden shadow-md"
    >
      {/* 卡片头部 */}
      <div className="flex items-center justify-between px-4 py-3 bg-neutral-800/50">
        <div className="flex items-center gap-3">
          <FileSpreadsheet size={16} className="text-emerald-400" />
          <span className="text-sm font-medium text-neutral-200">{filename}</span>
          {format && (
            <span className="px-2 py-0.5 rounded-full bg-emerald-900/30 text-[10px] text-emerald-400 font-mono uppercase">
              {format}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-neutral-500">
          <span className="flex items-center gap-1">
            <Rows3 size={12} />
            {rowCount.toLocaleString()} rows
          </span>
          <span className="flex items-center gap-1">
            <Columns3 size={12} />
            {columns.length} cols
          </span>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 hover:bg-neutral-700/50 rounded transition-colors"
          >
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>
      </div>

      {/* 列信息列表 */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="p-3 space-y-3 max-h-64 overflow-y-auto custom-scrollbar">
              {/* 按类型分组显示列标签 */}
              {Object.entries(columnsByType).map(([type, cols]) => (
                <div key={type} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${TYPE_COLOR_MAP[type] || DEFAULT_TYPE_COLOR}`}>
                      {type}
                    </span>
                    <span className="text-[10px] text-neutral-600">{cols.length} columns</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {cols.map((colName) => (
                      <span
                        key={colName}
                        className="px-2 py-0.5 bg-neutral-800/60 text-[11px] text-neutral-300 rounded border border-neutral-700/40 font-mono"
                      >
                        {colName}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

DataPreviewCard.displayName = 'DataPreviewCard';

export default DataPreviewCard;
