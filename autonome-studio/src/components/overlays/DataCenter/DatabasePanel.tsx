"use client";

/**
 * DatabasePanel - 分析数据库管理面板
 *
 * 功能说明：
 * - 显示和管理分析数据库资产
 * - 支持搜索、筛选、分页
 * - 提供创建、编辑、删除、共享功能
 *
 * 数据库类型：
 * - annotation: 注释数据库
 * - pathway: 信号通路
 * - protein: 蛋白质数据库
 * - variant: 变异数据库
 * - regulation: 调控数据库
 * - metabolism: 代谢数据库
 * - custom: 自定义数据库
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Database, Search, Plus, RefreshCw, MoreVertical,
  Edit3, Trash2, CheckCircle, XCircle, Loader2, TrendingUp
} from 'lucide-react';
import { databaseApi, AnalysisDatabase } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

interface DatabasePanelProps {
  onCreateNew: () => void;
  onEdit: (database: AnalysisDatabase) => void;
  onViewDetail: (database: AnalysisDatabase) => void;
}

// 数据库类型配置
const DB_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  annotation: { label: '注释', color: 'bg-blue-500/10 text-blue-400 border-blue-500/30' },
  pathway: { label: '通路', color: 'bg-green-500/10 text-green-400 border-green-500/30' },
  protein: { label: '蛋白质', color: 'bg-purple-500/10 text-purple-400 border-purple-500/30' },
  variant: { label: '变异', color: 'bg-red-500/10 text-red-400 border-red-500/30' },
  regulation: { label: '调控', color: 'bg-orange-500/10 text-orange-400 border-orange-500/30' },
  metabolism: { label: '代谢', color: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30' },
  custom: { label: '自定义', color: 'bg-neutral-500/10 text-neutral-400 border-neutral-500/30' }
};

// ==========================================
// 辅助组件
// ==========================================

// 状态徽章
const StatusBadge = ({ isActive }: { isActive: boolean }) => (
  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${
    isActive
      ? 'bg-green-500/10 text-green-400 border border-green-500/30'
      : 'bg-red-500/10 text-red-400 border border-red-500/30'
  }`}>
    {isActive ? <CheckCircle size={10} /> : <XCircle size={10} />}
    {isActive ? '启用' : '禁用'}
  </span>
);

// 类型徽章
const TypeBadge = ({ type }: { type: string }) => {
  const config = DB_TYPE_CONFIG[type] || DB_TYPE_CONFIG.custom;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${config.color}`}>
      {config.label}
    </span>
  );
};

// 可见性徽章
const VisibilityBadge = ({ visibility }: { visibility: string }) => {
  const colors: Record<string, string> = {
    public: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    team: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
    private: 'bg-neutral-500/10 text-neutral-400 border-neutral-500/30'
  };
  const labels: Record<string, string> = {
    public: '公开',
    team: '团队',
    private: '私有'
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${colors[visibility] || colors.private}`}>
      {labels[visibility] || visibility}
    </span>
  );
};

// ==========================================
// 主组件
// ==========================================

export function DatabasePanel({ onCreateNew, onEdit, onViewDetail }: DatabasePanelProps) {
  // 状态
  const [databases, setDatabases] = useState<AnalysisDatabase[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [typeList, setTypeList] = useState<{ type: string; name: string; count: number }[]>([]);
  const [showDropdown, setShowDropdown] = useState<number | null>(null);

  // 获取数据库列表
  const fetchDatabases = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await databaseApi.listDatabases(typeFilter || undefined, searchQuery || undefined);
      setDatabases(data);
    } catch (err: any) {
      setError(err.message || '获取数据库列表失败');
    } finally {
      setIsLoading(false);
    }
  }, [typeFilter, searchQuery]);

  // 获取类型列表
  const fetchTypeList = useCallback(async () => {
    try {
      const data = await databaseApi.listTypes();
      setTypeList(data.data || []);
    } catch (err) {
      console.error('获取类型列表失败:', err);
    }
  }, []);

  // 初始化加载
  useEffect(() => {
    fetchDatabases();
    fetchTypeList();
  }, [fetchDatabases, fetchTypeList]);

  // 切换数据库状态
  const handleToggleActive = async (dbId: string) => {
    try {
      await databaseApi.toggleActive(dbId);
      fetchDatabases();
    } catch (err: any) {
      alert('切换状态失败: ' + err.message);
    }
    setShowDropdown(null);
  };

  // 删除数据库
  const handleDelete = async (dbId: string) => {
    if (!confirm(`确定要删除数据库 "${dbId}" 吗？此操作不可撤销。`)) return;
    try {
      await databaseApi.deleteDatabase(dbId);
      fetchDatabases();
    } catch (err: any) {
      alert('删除失败: ' + err.message);
    }
    setShowDropdown(null);
  };

  // 格式化使用次数
  const formatUsageCount = (count: number) => {
    if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
    return count.toString();
  };

  // 渲染加载状态
  if (isLoading && databases.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={24} className="animate-spin text-purple-400" />
      </div>
    );
  }

  // 渲染错误状态
  if (error && databases.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-neutral-500 gap-3">
        <XCircle size={40} className="text-red-400" />
        <p className="text-sm">{error}</p>
        <button
          onClick={fetchDatabases}
          className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg"
        >
          重试
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* 工具栏 */}
      <div className="shrink-0 p-4 border-b border-neutral-800 flex flex-wrap items-center gap-3">
        {/* 搜索框 */}
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
          <input
            type="text"
            placeholder="搜索数据库..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-neutral-900 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-sm text-neutral-300 outline-none focus:border-purple-500/50 transition-all"
          />
        </div>

        {/* 类型筛选 */}
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-300 outline-none focus:border-purple-500/50"
        >
          <option value="">全部类型</option>
          {typeList.map(t => (
            <option key={t.type} value={t.type}>{t.name} ({t.count})</option>
          ))}
        </select>

        {/* 操作按钮 */}
        <div className="flex items-center gap-2">
          <button
            onClick={onCreateNew}
            className="flex items-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg transition-colors"
          >
            <Plus size={14} />
            新建
          </button>
          <button
            onClick={fetchDatabases}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-2 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>
      </div>

      {/* 表格 */}
      <div className="flex-1 overflow-auto">
        {databases.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-neutral-500 gap-3">
            <Database size={40} className="opacity-20" />
            <p className="text-sm">暂无数据库数据</p>
            <button
              onClick={onCreateNew}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg"
            >
              创建第一个数据库
            </button>
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-neutral-900 border-b border-neutral-800">
              <tr className="text-left text-xs text-neutral-400">
                <th className="px-4 py-3 font-medium">数据库 ID</th>
                <th className="px-4 py-3 font-medium">名称</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">物种</th>
                <th className="px-4 py-3 font-medium">路径</th>
                <th className="px-4 py-3 font-medium">使用次数</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {databases.map((db) => (
                <tr
                  key={db.db_id}
                  className="border-b border-neutral-800/50 hover:bg-neutral-800/30 transition-colors cursor-pointer"
                  onClick={() => onViewDetail(db)}
                >
                  <td className="px-4 py-3">
                    <span className="text-sm font-mono text-purple-400">{db.db_id}</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-300 truncate max-w-[150px]">
                    {db.name}
                  </td>
                  <td className="px-4 py-3">
                    <TypeBadge type={db.db_type} />
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-400">
                    {db.species || '-'}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-400 font-mono truncate max-w-[150px]">
                    {db.path}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-1 text-xs text-neutral-300">
                      <TrendingUp size={12} className="text-green-400" />
                      {formatUsageCount(db.usage_count)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge isActive={db.is_active} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="relative inline-block">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowDropdown(showDropdown === db.id ? null : db.id);
                        }}
                        className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-700 rounded transition-colors"
                      >
                        <MoreVertical size={14} />
                      </button>
                      {showDropdown === db.id && (
                        <div className="absolute right-0 top-full mt-1 bg-neutral-800 border border-neutral-700 rounded-lg shadow-xl py-1 min-w-[120px] z-50">
                          <button
                            onClick={(e) => { e.stopPropagation(); onEdit(db); setShowDropdown(null); }}
                            className="w-full text-left px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-700 flex items-center gap-2"
                          >
                            <Edit3 size={14} /> 编辑
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleToggleActive(db.db_id); }}
                            className="w-full text-left px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-700 flex items-center gap-2"
                          >
                            {db.is_active ? <XCircle size={14} /> : <CheckCircle size={14} />}
                            {db.is_active ? '禁用' : '启用'}
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDelete(db.db_id); }}
                            className="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 flex items-center gap-2"
                          >
                            <Trash2 size={14} /> 删除
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}