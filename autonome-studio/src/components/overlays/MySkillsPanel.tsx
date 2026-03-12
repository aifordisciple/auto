"use client";

import React, { useState, useEffect } from 'react';
import { skillForgeApi, SkillAsset } from '@/lib/api';
import {
  Box, Sparkles, Search, Trash2, Edit, Send, Eye, Clock,
  Loader2, X, FileCode, AlertCircle, CheckCircle, Hourglass, XCircle
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// 状态配置
const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  DRAFT: { label: '草稿', color: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300', icon: <Edit size={12} /> },
  PRIVATE: { label: '私有', color: 'bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400', icon: <Eye size={12} /> },
  PENDING_REVIEW: { label: '待审核', color: 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/50 dark:text-yellow-400', icon: <Hourglass size={12} /> },
  PUBLISHED: { label: '已发布', color: 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-400', icon: <CheckCircle size={12} /> },
  REJECTED: { label: '已驳回', color: 'bg-red-100 text-red-600 dark:bg-red-900/50 dark:text-red-400', icon: <XCircle size={12} /> },
};

// 状态过滤选项
const STATUS_FILTERS = [
  { value: 'all', label: '全部' },
  { value: 'DRAFT', label: '草稿' },
  { value: 'PRIVATE', label: '私有' },
  { value: 'PENDING_REVIEW', label: '待审核' },
  { value: 'PUBLISHED', label: '已发布' },
  { value: 'REJECTED', label: '已驳回' },
];

interface MySkillsPanelProps {
  onEditSkill: (skill: SkillAsset) => void;
}

export function MySkillsPanel({ onEditSkill }: MySkillsPanelProps) {
  const [skills, setSkills] = useState<SkillAsset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // 加载我的技能
  useEffect(() => {
    loadMySkills();
  }, [statusFilter]);

  const loadMySkills = async () => {
    setIsLoading(true);
    try {
      const data = await skillForgeApi.listMySkills(
        statusFilter !== 'all' ? statusFilter : undefined
      );
      setSkills(data || []);
    } catch (e) {
      console.error('Failed to load my skills:', e);
    } finally {
      setIsLoading(false);
    }
  };

  // 过滤技能
  const filteredSkills = skills.filter(skill => {
    if (!searchQuery) return true;
    return (
      skill.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      skill.skill_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (skill.description?.toLowerCase() || '').includes(searchQuery.toLowerCase())
    );
  });

  // 删除技能
  const handleDelete = async (skillId: string, skillName: string) => {
    if (!confirm(`确定要删除技能「${skillName}」吗？此操作不可撤销。`)) {
      return;
    }

    setDeletingId(skillId);
    try {
      await skillForgeApi.deleteSkill(skillId);
      setSkills(prev => prev.filter(s => s.skill_id !== skillId));
    } catch (e: any) {
      alert(`删除失败: ${e.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  // 提交审核
  const handleSubmitReview = async (skillId: string) => {
    if (!confirm('确定要提交审核吗？提交后将无法修改，等待管理员审核。')) {
      return;
    }

    try {
      await skillForgeApi.submitForReview(skillId);
      loadMySkills();
    } catch (e: any) {
      alert(`提交审核失败: ${e.message}`);
    }
  };

  // 格式化日期
  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // 获取执行器类型名称
  const getExecutorName = (type: string) => {
    switch (type) {
      case 'Python_env':
        return 'Python';
      case 'R_env':
        return 'R';
      case 'Logical_Blueprint':
        return 'Blueprint';
      case 'Python_Package':
        return 'Package';
      default:
        return type;
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 顶部工具栏 */}
      <div className="p-4 border-b border-gray-200 dark:border-neutral-800 space-y-3 shrink-0">
        {/* 搜索栏 */}
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-neutral-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="搜索我的技能..."
            className="w-full pl-9 pr-4 py-2 bg-white dark:bg-neutral-800 border border-gray-300 dark:border-neutral-700 rounded-lg text-sm text-gray-700 dark:text-neutral-300 focus:border-blue-500 focus:outline-none"
          />
        </div>

        {/* 状态过滤 */}
        <div className="flex flex-wrap gap-2">
          {STATUS_FILTERS.map(filter => {
            const count = filter.value === 'all'
              ? skills.length
              : skills.filter(s => s.status === filter.value).length;

            return (
              <button
                key={filter.value}
                onClick={() => setStatusFilter(filter.value)}
                className={`px-3 py-1 text-xs rounded-full transition-colors ${
                  statusFilter === filter.value
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 dark:bg-neutral-800 text-gray-600 dark:text-neutral-400 hover:bg-gray-200 dark:hover:bg-neutral-700'
                }`}
              >
                {filter.label}
                <span className="ml-1 opacity-70">({count})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 技能列表 */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex items-center justify-center h-32 text-gray-400 dark:text-neutral-500">
            <Loader2 size={24} className="animate-spin" />
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-gray-400 dark:text-neutral-500">
            <Box size={32} className="mb-2 opacity-50" />
            <span className="text-sm">
              {searchQuery ? '未找到匹配的技能' : '暂无技能，去创建一个吧！'}
            </span>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredSkills.map(skill => {
              const statusConfig = STATUS_CONFIG[skill.status] || STATUS_CONFIG.DRAFT;

              return (
                <motion.div
                  key={skill.skill_id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-white dark:bg-neutral-800/50 border border-gray-200 dark:border-neutral-700 rounded-lg p-4 hover:border-blue-300 dark:hover:border-blue-600 transition-all"
                >
                  {/* 标题行 */}
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <FileCode size={14} className="text-blue-400 shrink-0" />
                        <h3 className="font-medium text-gray-900 dark:text-white text-sm truncate">
                          {skill.name}
                        </h3>
                        <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${statusConfig.color}`}>
                          {statusConfig.icon}
                          {statusConfig.label}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 dark:text-neutral-500 font-mono">
                        {skill.skill_id}
                      </p>
                    </div>
                  </div>

                  {/* 描述 */}
                  <p className="text-xs text-gray-500 dark:text-neutral-400 line-clamp-2 mb-3">
                    {skill.description || '暂无描述'}
                  </p>

                  {/* 元信息 */}
                  <div className="flex items-center gap-4 text-[10px] text-gray-400 dark:text-neutral-500 mb-3">
                    <span className="flex items-center gap-1">
                      <Box size={10} />
                      {getExecutorName(skill.executor_type)}
                    </span>
                    <span>v{skill.version}</span>
                    <span className="flex items-center gap-1">
                      <Clock size={10} />
                      {formatDate(skill.updated_at)}
                    </span>
                  </div>

                  {/* 驳回原因 */}
                  {skill.status === 'REJECTED' && skill.reject_reason && (
                    <div className="mb-3 p-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded text-xs text-red-600 dark:text-red-400">
                      <div className="flex items-center gap-1 font-medium mb-1">
                        <AlertCircle size={12} />
                        驳回原因
                      </div>
                      {skill.reject_reason}
                    </div>
                  )}

                  {/* 操作按钮 */}
                  <div className="flex items-center gap-2 pt-2 border-t border-gray-100 dark:border-neutral-700">
                    {skill.status === 'DRAFT' && (
                      <>
                        <button
                          onClick={() => onEditSkill(skill)}
                          className="flex items-center gap-1 px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white text-xs rounded transition-colors"
                        >
                          <Edit size={12} />
                          编辑
                        </button>
                        <button
                          onClick={() => handleSubmitReview(skill.skill_id)}
                          className="flex items-center gap-1 px-3 py-1 bg-emerald-500 hover:bg-emerald-600 text-white text-xs rounded transition-colors"
                        >
                          <Send size={12} />
                          提交审核
                        </button>
                      </>
                    )}
                    {skill.status === 'PRIVATE' && (
                      <button
                        onClick={() => handleSubmitReview(skill.skill_id)}
                        className="flex items-center gap-1 px-3 py-1 bg-emerald-500 hover:bg-emerald-600 text-white text-xs rounded transition-colors"
                      >
                        <Send size={12} />
                        提交审核
                      </button>
                    )}
                    {skill.status === 'REJECTED' && (
                      <button
                        onClick={() => onEditSkill(skill)}
                        className="flex items-center gap-1 px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white text-xs rounded transition-colors"
                      >
                        <Edit size={12} />
                        修改并重新提交
                      </button>
                    )}
                    <div className="flex-1" />
                    {skill.status !== 'PUBLISHED' && skill.status !== 'PENDING_REVIEW' && (
                      <button
                        onClick={() => handleDelete(skill.skill_id, skill.name)}
                        disabled={deletingId === skill.skill_id}
                        className="flex items-center gap-1 px-3 py-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 text-xs rounded transition-colors disabled:opacity-50"
                      >
                        {deletingId === skill.skill_id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Trash2 size={12} />
                        )}
                        删除
                      </button>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}