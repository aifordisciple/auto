"use client";

/**
 * DatabaseDetailDrawer - 数据库详情抽屉
 *
 * 功能说明：
 * - 右侧滑出抽屉显示数据库详细信息
 * - 显示所有字段和自定义字段
 * - 提供快捷操作按钮
 */

import React from 'react';
import {
  X, Database, Edit3, Trash2, CheckCircle, XCircle,
  Copy, TrendingUp, Calendar
} from 'lucide-react';
import { AnalysisDatabase } from '@/lib/api';
import { Button } from '@/components/ui/Button';

// ==========================================
// 类型定义
// ==========================================

interface DatabaseDetailDrawerProps {
  database: AnalysisDatabase | null;
  isOpen: boolean;
  onClose: () => void;
  onEdit: (database: AnalysisDatabase) => void;
  onDelete: (dbId: string) => void;
}

// 数据库类型配置
const DB_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  annotation: { label: '注释数据库', color: 'bg-blue-500/10 text-blue-400 border-blue-500/30' },
  pathway: { label: '信号通路', color: 'bg-green-500/10 text-green-400 border-green-500/30' },
  protein: { label: '蛋白质数据库', color: 'bg-purple-500/10 text-purple-400 border-purple-500/30' },
  variant: { label: '变异数据库', color: 'bg-red-500/10 text-red-400 border-red-500/30' },
  regulation: { label: '调控数据库', color: 'bg-orange-500/10 text-orange-400 border-orange-500/30' },
  metabolism: { label: '代谢数据库', color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30' },
  custom: { label: '自定义数据库', color: 'bg-neutral-500/10 text-neutral-400 border-neutral-500/30' }
};

// ==========================================
// 辅助组件
// ==========================================

const FieldRow = ({ label, value, isPath = false }: { label: string; value: any; isPath?: boolean }) => {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  const copyToClipboard = () => {
    navigator.clipboard.writeText(String(value));
  };

  return (
    <div className="flex items-start gap-2 py-2">
      <span className="text-xs text-neutral-500 w-24 shrink-0">{label}</span>
      <div className="flex-1 flex items-center gap-2 min-w-0">
        <span className={`text-sm text-neutral-300 break-all ${isPath ? 'font-mono text-xs' : ''}`}>
          {String(value)}
        </span>
        {isPath && (
          <button
            onClick={copyToClipboard}
            className="shrink-0 p-1 text-neutral-500 hover:text-white transition-colors"
            title="复制路径"
          >
            <Copy size={12} />
          </button>
        )}
      </div>
    </div>
  );
};

// ==========================================
// 主组件
// ==========================================

export function DatabaseDetailDrawer({
  database,
  isOpen,
  onClose,
  onEdit,
  onDelete
}: DatabaseDetailDrawerProps) {
  if (!isOpen || !database) return null;

  const typeConfig = DB_TYPE_CONFIG[database.db_type] || DB_TYPE_CONFIG.custom;

  // 格式化大小
  const formatSize = (bytes: number | null) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  };

  return (
    <div className="fixed inset-0 z-[150] flex justify-end">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 抽屉内容 */}
      <div className="relative w-[500px] max-w-full h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">
        {/* Header */}
        <div className="shrink-0 h-14 border-b border-neutral-800 px-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-blue-500/20 border border-blue-500/30 rounded-lg text-blue-400">
              <Database size={16} />
            </div>
            <div>
              <h3 className="text-sm font-medium text-white">{database.name}</h3>
              <p className="text-xs text-neutral-500 font-mono">{database.db_id}</p>
            </div>
          </div>
          <Button
            variant="icon"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>

        {/* 操作栏 */}
        <div className="shrink-0 px-4 py-3 border-b border-neutral-800 flex items-center gap-2">
          <button
            onClick={() => onEdit(database)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs rounded-lg transition-colors"
          >
            <Edit3 size={12} /> 编辑
          </button>
          <button
            onClick={() => onDelete(database.db_id)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs rounded-lg transition-colors"
          >
            <Trash2 size={12} /> 删除
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {/* 状态信息 */}
          <div className="flex items-center gap-4 p-3 bg-neutral-800/30 rounded-lg">
            <div className="flex items-center gap-2">
              <span className="text-xs text-neutral-500">状态:</span>
              {database.is_active ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-500/10 text-green-400 border border-green-500/30">
                  <CheckCircle size={10} /> 启用
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-red-500/10 text-red-400 border border-red-500/30">
                  <XCircle size={10} /> 禁用
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-neutral-500">类型:</span>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${typeConfig.color}`}>
                {typeConfig.label}
              </span>
            </div>
          </div>

          {/* 描述 */}
          {database.description && (
            <div className="p-3 bg-neutral-800/30 rounded-lg">
              <p className="text-sm text-neutral-300 whitespace-pre-wrap">{database.description}</p>
            </div>
          )}

          {/* 基本信息 */}
          <div className="space-y-1">
            <h4 className="text-xs font-medium text-neutral-400 border-b border-neutral-800 pb-2">
              基本信息
            </h4>
            <div className="divide-y divide-neutral-800/50">
              <FieldRow label="物种" value={database.species} />
              <FieldRow label="版本" value={database.version} />
              <FieldRow label="文件格式" value={database.file_format} />
              <FieldRow label="大小" value={formatSize(database.size_bytes)} />
            </div>
          </div>

          {/* 存储信息 */}
          <div className="space-y-1">
            <h4 className="text-xs font-medium text-neutral-400 border-b border-neutral-800 pb-2">
              存储信息
            </h4>
            <div className="divide-y divide-neutral-800/50">
              <FieldRow label="路径" value={database.path} isPath />
              <FieldRow label="来源 URL" value={database.source_url} />
              <FieldRow label="许可证" value={database.license} />
            </div>
          </div>

          {/* 使用统计 */}
          <div className="space-y-1">
            <h4 className="text-xs font-medium text-neutral-400 border-b border-neutral-800 pb-2">
              使用统计
            </h4>
            <div className="p-3 bg-neutral-800/30 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp size={16} className="text-green-400" />
                <span className="text-sm text-neutral-300">使用次数</span>
              </div>
              <span className="text-lg font-bold text-green-400">{database.usage_count}</span>
            </div>
            {database.last_used_at && (
              <div className="flex items-center gap-2 text-xs text-neutral-500 mt-2">
                <Calendar size={12} />
                最后使用: {new Date(database.last_used_at).toLocaleString()}
              </div>
            )}
          </div>

          {/* 标签 */}
          {database.tags && database.tags.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-medium text-neutral-400">标签</h4>
              <div className="flex flex-wrap gap-2">
                {database.tags.map(tag => (
                  <span
                    key={tag}
                    className="inline-flex items-center px-2 py-1 bg-purple-500/10 text-purple-400 border border-purple-500/30 rounded-full text-xs"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 自定义字段 */}
          {database.custom_fields && Object.keys(database.custom_fields).length > 0 && (
            <div className="space-y-1">
              <h4 className="text-xs font-medium text-neutral-400 border-b border-neutral-800 pb-2">
                自定义字段
              </h4>
              <div className="divide-y divide-neutral-800/50">
                {Object.entries(database.custom_fields).map(([key, value]) => (
                  <FieldRow
                    key={key}
                    label={key}
                    value={value}
                  />
                ))}
              </div>
            </div>
          )}

          {/* 时间信息 */}
          <div className="space-y-1 text-xs text-neutral-500">
            <p>创建时间: {new Date(database.created_at).toLocaleString()}</p>
            <p>更新时间: {new Date(database.updated_at).toLocaleString()}</p>
          </div>
        </div>
      </div>
    </div>
  );
}