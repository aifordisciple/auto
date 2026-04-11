/**
 * 待发布草稿列表组件
 *
 * 显示自动生成的技能草稿，支持：
 * - 查看草稿详情
 * - 编辑草稿
 * - 一键发布
 * - 忽略草稿
 */

'use client';

import React, { useEffect, useState } from 'react';
import { skillDraftApi, PendingSkillDraft, DraftStats } from '@/lib/api';
import { toast } from 'sonner';
import {
  Sparkles,
  FileCode,
  Clock,
  Check,
  X,
  ChevronRight,
  ChevronDown,
  Trash2,
  Loader2
} from 'lucide-react';

interface PendingDraftsListProps {
  onSelectDraft?: (draft: PendingSkillDraft) => void;
}

export function PendingDraftsList({ onSelectDraft }: PendingDraftsListProps) {
  const [drafts, setDrafts] = useState<PendingSkillDraft[]>([]);
  const [stats, setStats] = useState<DraftStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(true);
  const [publishingId, setPublishingId] = useState<number | null>(null);

  // 加载草稿列表
  const loadDrafts = async () => {
    try {
      const [draftsData, statsData] = await Promise.all([
        skillDraftApi.getDrafts({ status: 'PENDING', limit: 10 }),
        skillDraftApi.getDraftStats()
      ]);
      setDrafts(draftsData);
      setStats(statsData);
    } catch (error) {
      console.error('加载草稿失败:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDrafts();
    // 每30秒刷新一次
    const interval = setInterval(loadDrafts, 30000);
    return () => clearInterval(interval);
  }, []);

  // 发布草稿
  const handlePublish = async (draftId: number, skillName?: string) => {
    setPublishingId(draftId);
    try {
      const result = await skillDraftApi.publishDraft(draftId, { skill_name: skillName });
      toast.success(`技能 "${result.name}" 已创建`);
      loadDrafts();
    } catch (error: any) {
      toast.error(error.message || '发布失败');
    } finally {
      setPublishingId(null);
    }
  };

  // 忽略草稿
  const handleDismiss = async (draftId: number) => {
    try {
      await skillDraftApi.dismissDraft(draftId);
      toast.success('草稿已忽略');
      loadDrafts();
    } catch (error: any) {
      toast.error(error.message || '操作失败');
    }
  };

  // 标记为已查看
  const handleMarkReviewed = async (draftId: number) => {
    try {
      await skillDraftApi.markReviewed(draftId);
    } catch (error) {
      // 静默处理
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4 text-neutral-500">
        <Loader2 className="w-4 h-4 animate-spin mr-2" />
        加载中...
      </div>
    );
  }

  if (!stats || stats.pending === 0) {
    return null; // 没有待处理草稿时不显示
  }

  return (
    <div className="border-b border-neutral-800 bg-neutral-900/50">
      {/* 头部 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-neutral-800/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-medium text-neutral-200">
            自动生成的技能草稿
          </span>
          <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded-full">
            {stats.pending} 待处理
          </span>
        </div>
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-neutral-500" />
        ) : (
          <ChevronRight className="w-4 h-4 text-neutral-500" />
        )}
      </button>

      {/* 草稿列表 */}
      {expanded && (
        <div className="px-4 pb-3 space-y-2">
          {drafts.map((draft) => (
            <div
              key={draft.id}
              className="group bg-neutral-800/50 rounded-lg p-3 border border-neutral-700/50 hover:border-neutral-600 transition-colors"
              onClick={() => handleMarkReviewed(draft.id)}
            >
              {/* 草稿信息 */}
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1 min-w-0">
                  <h4 className="text-sm font-medium text-neutral-200 truncate">
                    {draft.draft_name || '未命名技能'}
                  </h4>
                  <p className="text-xs text-neutral-500 truncate mt-0.5">
                    {draft.draft_description || '暂无描述'}
                  </p>
                </div>
                <div className="flex items-center gap-1 text-xs text-neutral-500">
                  <Clock className="w-3 h-3" />
                  {new Date(draft.created_at).toLocaleDateString()}
                </div>
              </div>

              {/* 触发信息 */}
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded">
                  {draft.trigger_source === 'code_complexity' && '代码复杂度'}
                  {draft.trigger_source === 'execution_time' && '执行时长'}
                  {draft.trigger_source === 'output_file' && '输出文件'}
                  {draft.trigger_source === 'success_signal' && '成功信号'}
                </span>
                <span className="text-xs text-neutral-500">
                  {draft.executor_type === 'Python_env' && 'Python'}
                  {draft.executor_type === 'R_env' && 'R'}
                  {draft.executor_type === 'Logical_Blueprint' && 'Nextflow'}
                </span>
              </div>

              {/* 操作按钮 */}
              <div className="flex items-center gap-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handlePublish(draft.id, draft.draft_name);
                  }}
                  disabled={publishingId === draft.id}
                  className="flex items-center gap-1 px-3 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs rounded transition-colors"
                >
                  {publishingId === draft.id ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Check className="w-3 h-3" />
                  )}
                  发布
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectDraft?.(draft);
                  }}
                  className="flex items-center gap-1 px-3 py-1 bg-neutral-700 hover:bg-neutral-600 text-neutral-200 text-xs rounded transition-colors"
                >
                  <FileCode className="w-3 h-3" />
                  查看
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDismiss(draft.id);
                  }}
                  className="flex items-center gap-1 px-2 py-1 text-neutral-500 hover:text-red-400 text-xs transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}

          {/* 加载更多 */}
          {drafts.length >= 10 && (
            <button className="w-full text-center text-xs text-neutral-500 hover:text-neutral-400 py-2">
              查看更多...
            </button>
          )}
        </div>
      )}
    </div>
  );
}