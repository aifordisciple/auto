/**
 * 技能详情抽屉 - 展示技能的完整信息
 * 包括：基本信息、参数说明、专家知识、用户评价、执行历史
 */

'use client';

import React, { useState, useEffect } from 'react';
import {
  X, Star, Heart, Play, Clock, User, ChevronRight,
  Box, Terminal, BookOpen, MessageSquare, History,
  Loader2, CheckCircle, XCircle, AlertCircle
} from "lucide-react";
import { fetchAPI, BASE_URL } from "@/lib/api";
import { toast } from 'sonner';

// ==========================================
// 类型定义
// ==========================================

interface ReviewItem {
  id: number;
  user_name: string | null;
  rating: number;
  comment: string | null;
  created_at: string;
}

interface ExecutionHistoryItem {
  id: number;
  project_id: string;
  status: string;
  parameters: Record<string, unknown>;
  execution_time: number | null;
  created_at: string;
}

interface SkillDetailFull {
  skill_id: string;
  name: string;
  description: string | null;
  version: string;
  executor_type: string;
  parameters_schema: {
    type: string;
    properties: Record<string, {
      type: string;
      format?: string;
      description?: string;
      default?: unknown;
    }>;
    required: string[];
  };
  expert_knowledge: string | null;
  dependencies: string[];
  avg_rating: number;
  rating_count: number;
  usage_count: number;
  favorite_count: number;
  owner_id: number;
  owner_name: string | null;
  is_favorited: boolean;
  user_rating: number | null;
  reviews: ReviewItem[];
  recent_executions: ExecutionHistoryItem[];
  created_at: string;
  updated_at: string;
}

interface SkillDetailDrawerProps {
  skillId: string;
  onClose: () => void;
  onUse?: (skillId: string) => void;
}

// ==========================================
// 子组件：星级评分显示
// ==========================================

function StarRating({ rating, size = 16 }: { rating: number; size?: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          size={size}
          className={`${i <= Math.round(rating) ? 'text-yellow-400 fill-yellow-400' : 'text-neutral-600'}`}
        />
      ))}
    </div>
  );
}

// ==========================================
// 子组件：参数类型图标
// ==========================================

function ParamTypeIcon({ type, format }: { type: string; format?: string }) {
  const iconMap: Record<string, string> = {
    'string': '📝',
    'integer': '🔢',
    'number': '🔢',
    'boolean': '✓',
    'array': '📋',
    'object': '📦',
  };

  const formatMap: Record<string, string> = {
    'filepath': '📄',
    'directorypath': '📁',
    'date': '📅',
    'date-time': '🕐',
  };

  const icon = format ? (formatMap[format.toLowerCase()] || iconMap[type.toLowerCase()] || '•') : iconMap[type.toLowerCase()] || '•';

  return <span className="text-xs">{icon}</span>;
}

// ==========================================
// 主组件
// ==========================================

export function SkillDetailDrawer({ skillId, onClose, onUse }: SkillDetailDrawerProps) {
  const [skill, setSkill] = useState<SkillDetailFull | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'params' | 'knowledge' | 'reviews' | 'history'>('params');
  const [isFavoriting, setIsFavoriting] = useState(false);
  const [userRating, setUserRating] = useState<number | null>(null);
  const [isRating, setIsRating] = useState(false);

  // 加载技能详情
  useEffect(() => {
    fetchSkillDetail();
  }, [skillId]);

  const fetchSkillDetail = async () => {
    setIsLoading(true);
    try {
      const data = await fetchAPI(`/api/skills/market/skills/${skillId}/full`);
      setSkill(data);
      setUserRating(data.user_rating);
    } catch (e) {
      const msg = e instanceof Error ? e.message : '未知错误';
      console.error('Failed to fetch skill detail:', e);
      toast.error(`加载技能详情失败: ${msg}`);
    } finally {
      setIsLoading(false);
    }
  };

  // 切换收藏
  const handleToggleFavorite = async () => {
    if (!skill || isFavoriting) return;
    setIsFavoriting(true);
    try {
      const data = await fetchAPI(`/api/skills/market/skills/${skillId}/favorite`, {
        method: 'POST'
      });
      setSkill({ ...skill, is_favorited: data.is_favorited, favorite_count: data.favorite_count });
      toast.success(data.is_favorited ? '已添加到收藏' : '已取消收藏');
    } catch (e) {
      toast.error('操作失败');
    } finally {
      setIsFavoriting(false);
    }
  };

  // 提交评分
  const handleRate = async (rating: number) => {
    if (!skill || isRating) return;
    setIsRating(true);
    try {
      const data = await fetchAPI(`/api/skills/market/skills/${skillId}/rate`, {
        method: 'POST',
        body: JSON.stringify({ rating })
      });
      setUserRating(rating);
      setSkill({
        ...skill,
        avg_rating: data.avg_rating,
        rating_count: data.rating_count
      });
      toast.success('评分成功');
    } catch (e) {
      toast.error('评分失败');
    } finally {
      setIsRating(false);
    }
  };

  // 渲染加载状态
  if (isLoading) {
    return (
      <div className="fixed inset-y-0 right-0 w-full md:w-[600px] max-w-full bg-neutral-900 border-l border-neutral-800 shadow-2xl z-50 flex items-center justify-center">
        <Loader2 size={32} className="animate-spin text-neutral-500" />
      </div>
    );
  }

  // 渲染错误状态
  if (!skill) {
    return (
      <div className="fixed inset-y-0 right-0 w-full md:w-[600px] max-w-full bg-neutral-900 border-l border-neutral-800 shadow-2xl z-50 flex flex-col items-center justify-center gap-4">
        <AlertCircle size={48} className="text-red-400 opacity-50" />
        <p className="text-neutral-400">技能不存在或无权访问</p>
        <button
          onClick={onClose}
          className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded-lg text-sm text-neutral-300"
        >
          关闭
        </button>
      </div>
    );
  }

  return (
    <div className="fixed inset-y-0 right-0 w-full md:w-[600px] max-w-full bg-neutral-900 border-l border-neutral-800 shadow-2xl z-50 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-neutral-800 bg-neutral-900/80 backdrop-blur-sm">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-semibold text-neutral-100 truncate">{skill.name}</h2>
            <p className="text-xs text-neutral-500 font-mono mt-1">{skill.skill_id}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-neutral-800 rounded-lg text-neutral-400 hover:text-neutral-200 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Stats Row */}
        <div className="flex items-center gap-4 mt-3">
          <div className="flex items-center gap-1.5">
            <StarRating rating={skill.avg_rating} size={14} />
            <span className="text-sm text-neutral-300">{skill.avg_rating.toFixed(1)}</span>
            <span className="text-xs text-neutral-500">({skill.rating_count})</span>
          </div>
          <div className="flex items-center gap-1.5 text-neutral-400">
            <Clock size={14} />
            <span className="text-xs">{skill.usage_count} 次使用</span>
          </div>
          <div className="flex items-center gap-1.5 text-neutral-400">
            <Heart size={14} />
            <span className="text-xs">{skill.favorite_count} 收藏</span>
          </div>
        </div>

        {/* Tags */}
        <div className="flex items-center gap-2 mt-3 flex-wrap">
          <span className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
            {skill.executor_type}
          </span>
          <span className="text-xs px-2 py-1 rounded bg-neutral-800 text-neutral-400">
            v{skill.version}
          </span>
          <span className="text-xs px-2 py-1 rounded bg-neutral-800 text-neutral-400">
            by {skill.owner_name || '未知'}
          </span>
        </div>

        {/* Description */}
        {skill.description && (
          <p className="text-sm text-neutral-400 mt-3 leading-relaxed">{skill.description}</p>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 mt-4">
          {onUse && (
            <button
              onClick={() => onUse(skillId)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Play size={16} />
              使用技能
            </button>
          )}
          <button
            onClick={handleToggleFavorite}
            disabled={isFavoriting}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              skill.is_favorited
                ? 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20'
                : 'bg-neutral-800 text-neutral-300 hover:bg-neutral-700'
            }`}
          >
            <Heart size={16} className={skill.is_favorited ? 'fill-red-400' : ''} />
            {skill.is_favorited ? '已收藏' : '收藏'}
          </button>

          {/* User Rating */}
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-neutral-500">我的评分:</span>
            <div className="flex items-center gap-0.5">
              {[1, 2, 3, 4, 5].map((i) => (
                <button
                  key={i}
                  onClick={() => handleRate(i)}
                  disabled={isRating}
                  className="p-0.5 hover:scale-110 transition-transform"
                >
                  <Star
                    size={16}
                    className={`${
                      userRating && i <= userRating
                        ? 'text-yellow-400 fill-yellow-400'
                        : 'text-neutral-600 hover:text-yellow-400'
                    }`}
                  />
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 p-2 border-b border-neutral-800 bg-neutral-900/50">
        {[
          { id: 'params', label: '参数说明', icon: Box },
          { id: 'knowledge', label: '专家知识', icon: BookOpen },
          { id: 'reviews', label: `评价 (${skill.reviews.length})`, icon: MessageSquare },
          { id: 'history', label: '执行历史', icon: History },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                : 'text-neutral-400 hover:text-neutral-300 hover:bg-neutral-800/50'
            }`}
          >
            <tab.icon size={14} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {/* 参数说明 Tab */}
        {activeTab === 'params' && (
          <div className="space-y-4">
            {skill.parameters_schema?.properties &&
            Object.keys(skill.parameters_schema.properties).length > 0 ? (
              Object.entries(skill.parameters_schema.properties).map(([key, prop]) => {
                const isRequired = skill.parameters_schema.required?.includes(key);
                return (
                  <div key={key} className="p-3 rounded-lg bg-neutral-800/50 border border-neutral-700">
                    <div className="flex items-center gap-2 mb-2">
                      <ParamTypeIcon type={prop.type} format={prop.format} />
                      <span className="text-sm font-mono text-neutral-200">{key}</span>
                      {isRequired && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
                          必填
                        </span>
                      )}
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-700 text-neutral-400 ml-auto">
                        {prop.type}{prop.format ? ` (${prop.format})` : ''}
                      </span>
                    </div>
                    {prop.description && (
                      <p className="text-xs text-neutral-400 leading-relaxed">{prop.description}</p>
                    )}
                    {prop.default !== undefined && (
                      <div className="mt-2 text-xs text-neutral-500">
                        默认值: <code className="px-1.5 py-0.5 rounded bg-neutral-900 text-neutral-300">{JSON.stringify(prop.default)}</code>
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="text-center text-neutral-500 py-8">
                该技能无需配置参数
              </div>
            )}

            {/* Dependencies */}
            {skill.dependencies && skill.dependencies.length > 0 && (
              <div className="mt-6">
                <h4 className="text-sm font-medium text-neutral-300 mb-3">依赖包</h4>
                <div className="flex flex-wrap gap-2">
                  {skill.dependencies.map((dep, i) => (
                    <span key={i} className="text-xs px-2 py-1 rounded bg-neutral-800 text-neutral-400 font-mono">
                      {dep}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 专家知识 Tab */}
        {activeTab === 'knowledge' && (
          <div>
            {skill.expert_knowledge ? (
              <div className="prose prose-invert prose-sm max-w-none">
                <div
                  className="text-sm text-neutral-300 leading-relaxed whitespace-pre-wrap"
                  dangerouslySetInnerHTML={{
                    __html: skill.expert_knowledge
                      .replace(/\n/g, '<br/>')
                      .replace(/#{1,6}\s*(.+)/g, '<strong class="text-neutral-200">$1</strong>')
                      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                      .replace(/`(.+?)`/g, '<code class="px-1 py-0.5 rounded bg-neutral-800 text-neutral-300">$1</code>')
                  }}
                />
              </div>
            ) : (
              <div className="text-center text-neutral-500 py-8">
                暂无专家知识
              </div>
            )}
          </div>
        )}

        {/* 评价 Tab */}
        {activeTab === 'reviews' && (
          <div className="space-y-3">
            {skill.reviews.length > 0 ? (
              skill.reviews.map((review) => (
                <div key={review.id} className="p-3 rounded-lg bg-neutral-800/50 border border-neutral-700">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-6 h-6 rounded-full bg-neutral-700 flex items-center justify-center">
                      <User size={12} className="text-neutral-400" />
                    </div>
                    <span className="text-sm text-neutral-300">{review.user_name || '匿名用户'}</span>
                    <StarRating rating={review.rating} size={12} />
                    <span className="text-xs text-neutral-500 ml-auto">
                      {new Date(review.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  {review.comment && (
                    <p className="text-xs text-neutral-400 leading-relaxed">{review.comment}</p>
                  )}
                </div>
              ))
            ) : (
              <div className="text-center text-neutral-500 py-8">
                暂无评价
              </div>
            )}
          </div>
        )}

        {/* 执行历史 Tab */}
        {activeTab === 'history' && (
          <div className="space-y-2">
            {skill.recent_executions.length > 0 ? (
              skill.recent_executions.map((execution) => (
                <div key={execution.id} className="p-3 rounded-lg bg-neutral-800/50 border border-neutral-700">
                  <div className="flex items-center gap-2 mb-2">
                    {execution.status === 'SUCCESS' && <CheckCircle size={14} className="text-green-400" />}
                    {execution.status === 'FAILURE' && <XCircle size={14} className="text-red-400" />}
                    {execution.status === 'PENDING' && <Loader2 size={14} className="text-blue-400 animate-spin" />}
                    {!['SUCCESS', 'FAILURE', 'PENDING'].includes(execution.status) && (
                      <Terminal size={14} className="text-neutral-400" />
                    )}
                    <span className="text-sm text-neutral-300">{execution.status}</span>
                    {execution.execution_time && (
                      <span className="text-xs text-neutral-500">
                        {execution.execution_time.toFixed(1)}s
                      </span>
                    )}
                    <span className="text-xs text-neutral-500 ml-auto">
                      {new Date(execution.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="text-xs text-neutral-500 font-mono truncate">
                    Project: {execution.project_id}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center text-neutral-500 py-8">
                暂无执行记录
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-neutral-800 bg-neutral-900/50">
        <div className="flex items-center justify-between text-xs text-neutral-500">
          <span>创建于 {new Date(skill.created_at).toLocaleDateString()}</span>
          <span>更新于 {new Date(skill.updated_at).toLocaleDateString()}</span>
        </div>
      </div>
    </div>
  );
}