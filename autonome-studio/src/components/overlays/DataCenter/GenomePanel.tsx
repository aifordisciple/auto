"use client";

/**
 * GenomePanel - 参考基因组管理面板
 *
 * 功能说明：
 * - 显示和管理参考基因组资产
 * - 支持搜索、筛选、分页
 * - 提供创建、编辑、删除、共享功能
 * - 支持 TSV 批量导入（管理员）
 *
 * 权限逻辑：
 * - 管理员可创建公开基因组
 * - 普通用户只能创建私有基因组
 * - 用户可查看公开基因组和自己创建的基因组
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dna, Search, Plus, RefreshCw, Upload, Download, MoreVertical,
  Edit3, Trash2, Share2, CheckCircle, XCircle, FolderCheck, Loader2
} from 'lucide-react';
import { genomeApi, GenomeAsset } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

interface GenomePanelProps {
  onCreateNew: () => void;
  onEdit: (genome: GenomeAsset) => void;
  onViewDetail: (genome: GenomeAsset) => void;
  onOpenImport: () => void;
}

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

export function GenomePanel({ onCreateNew, onEdit, onViewDetail, onOpenImport }: GenomePanelProps) {
  // 状态
  const [genomes, setGenomes] = useState<GenomeAsset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [speciesFilter, setSpeciesFilter] = useState('');
  const [speciesList, setSpeciesList] = useState<{ species: string; count: number }[]>([]);
  const [showDropdown, setShowDropdown] = useState<number | null>(null);

  // 获取基因组列表
  const fetchGenomes = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await genomeApi.listGenomes(speciesFilter || undefined, searchQuery || undefined);
      setGenomes(data);
    } catch (err: any) {
      setError(err.message || '获取基因组列表失败');
    } finally {
      setIsLoading(false);
    }
  }, [speciesFilter, searchQuery]);

  // 获取物种列表
  const fetchSpeciesList = useCallback(async () => {
    try {
      const data = await genomeApi.listSpecies();
      setSpeciesList(data.data || []);
    } catch (err) {
      console.error('获取物种列表失败:', err);
    }
  }, []);

  // 初始化加载
  useEffect(() => {
    fetchGenomes();
    fetchSpeciesList();
  }, [fetchGenomes, fetchSpeciesList]);

  // 切换基因组状态
  const handleToggleActive = async (genomeid: string) => {
    try {
      await genomeApi.toggleActive(genomeid);
      fetchGenomes();
    } catch (err: any) {
      alert('切换状态失败: ' + err.message);
    }
    setShowDropdown(null);
  };

  // 删除基因组
  const handleDelete = async (genomeid: string) => {
    if (!confirm(`确定要删除基因组 "${genomeid}" 吗？此操作不可撤销。`)) return;
    try {
      await genomeApi.deleteGenome(genomeid);
      fetchGenomes();
    } catch (err: any) {
      alert('删除失败: ' + err.message);
    }
    setShowDropdown(null);
  };

  // 验证路径
  const handleValidate = async (genomeid: string) => {
    try {
      const result = await genomeApi.validatePaths(genomeid);
      const missing = result.total_paths - result.existing_paths;
      if (missing === 0) {
        alert('所有路径验证通过！');
      } else {
        alert(`验证完成：${result.existing_paths}/${result.total_paths} 个路径存在，${missing} 个路径缺失`);
      }
    } catch (err: any) {
      alert('验证失败: ' + err.message);
    }
    setShowDropdown(null);
  };

  // 导出 TSV
  const handleExport = async () => {
    try {
      const blob = await genomeApi.exportTsv(speciesFilter || undefined);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `genome_db_${new Date().toISOString().split('T')[0]}.tsv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert('导出失败: ' + err.message);
    }
  };

  // 渲染加载状态
  if (isLoading && genomes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={24} className="animate-spin text-purple-400" />
      </div>
    );
  }

  // 渲染错误状态
  if (error && genomes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-neutral-500 gap-3">
        <XCircle size={40} className="text-red-400" />
        <p className="text-sm">{error}</p>
        <button
          onClick={fetchGenomes}
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
            placeholder="搜索基因组..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-neutral-900 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-sm text-neutral-300 outline-none focus:border-purple-500/50 transition-all"
          />
        </div>

        {/* 物种筛选 */}
        <select
          value={speciesFilter}
          onChange={(e) => setSpeciesFilter(e.target.value)}
          className="bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-sm text-neutral-300 outline-none focus:border-purple-500/50"
        >
          <option value="">全部物种</option>
          {speciesList.map(s => (
            <option key={s.species} value={s.species}>{s.species} ({s.count})</option>
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
            onClick={onOpenImport}
            className="flex items-center gap-1.5 px-3 py-2 bg-green-600 hover:bg-green-500 text-white text-sm rounded-lg transition-colors"
          >
            <Upload size={14} />
            导入
          </button>
          <button
            onClick={fetchGenomes}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-2 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            刷新
          </button>
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 px-3 py-2 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm rounded-lg transition-colors"
          >
            <Download size={14} />
            导出
          </button>
        </div>
      </div>

      {/* 表格 */}
      <div className="flex-1 overflow-auto">
        {genomes.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-neutral-500 gap-3">
            <Dna size={40} className="opacity-20" />
            <p className="text-sm">暂无基因组数据</p>
            <button
              onClick={onCreateNew}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg"
            >
              创建第一个基因组
            </button>
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-neutral-900 border-b border-neutral-800">
              <tr className="text-left text-xs text-neutral-400">
                <th className="px-4 py-3 font-medium">Genome ID</th>
                <th className="px-4 py-3 font-medium">物种</th>
                <th className="px-4 py-3 font-medium">版本</th>
                <th className="px-4 py-3 font-medium">基因组路径</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">可见性</th>
                <th className="px-4 py-3 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {genomes.map((genome) => (
                <tr
                  key={genome.genomeid}
                  className="border-b border-neutral-800/50 hover:bg-neutral-800/30 transition-colors cursor-pointer"
                  onClick={() => onViewDetail(genome)}
                >
                  <td className="px-4 py-3">
                    <span className="text-sm font-mono text-purple-400">{genome.genomeid}</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-300">{genome.species}</td>
                  <td className="px-4 py-3 text-sm text-neutral-300">{genome.version}</td>
                  <td className="px-4 py-3 text-sm text-neutral-400 font-mono truncate max-w-[200px]">
                    {genome.genome}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge isActive={genome.is_active} />
                  </td>
                  <td className="px-4 py-3">
                    <VisibilityBadge visibility={genome.visibility} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="relative inline-block">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setShowDropdown(showDropdown === genome.id ? null : genome.id);
                        }}
                        className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-700 rounded transition-colors"
                      >
                        <MoreVertical size={14} />
                      </button>
                      {showDropdown === genome.id && (
                        <div className="absolute right-0 top-full mt-1 bg-neutral-800 border border-neutral-700 rounded-lg shadow-xl py-1 min-w-[120px] z-50">
                          <button
                            onClick={(e) => { e.stopPropagation(); onEdit(genome); setShowDropdown(null); }}
                            className="w-full text-left px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-700 flex items-center gap-2"
                          >
                            <Edit3 size={14} /> 编辑
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleValidate(genome.genomeid); }}
                            className="w-full text-left px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-700 flex items-center gap-2"
                          >
                            <FolderCheck size={14} /> 验证路径
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleToggleActive(genome.genomeid); }}
                            className="w-full text-left px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-700 flex items-center gap-2"
                          >
                            {genome.is_active ? <XCircle size={14} /> : <CheckCircle size={14} />}
                            {genome.is_active ? '禁用' : '启用'}
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDelete(genome.genomeid); }}
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