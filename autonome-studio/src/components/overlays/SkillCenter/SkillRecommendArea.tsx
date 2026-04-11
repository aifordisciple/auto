/**
 * 技能推荐区域 - 展示热门、最新、个性化推荐技能
 *
 * 位于技能中心顶部，横向滚动展示推荐技能卡片
 */

'use client';

import React, { useState, useEffect } from 'react';
import { Box, Star, TrendingUp, Sparkles, Clock, ChevronRight, Loader2 } from "lucide-react";
import { fetchAPI } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================

interface TrendingSkill {
  skill_id: string;
  name: string;
  description: string | null;
  executor_type: string;
  usage_count: number;
  avg_rating: number;
  trend: string; // "rising" | "stable" | "hot"
}

interface RecentSkill {
  skill_id: string;
  name: string;
  description: string | null;
  executor_type: string;
  avg_rating: number;
  created_at: string;
  is_new: boolean;
}

interface RecommendedSkill {
  skill_id: string;
  name: string;
  description: string | null;
  executor_type: string;
  category: string | null;
  match_score: number;
  match_reason: string;
  avg_rating: number;
  usage_count: number;
}

interface SkillRecommendAreaProps {
  onSkillSelect?: (skillId: string) => void;
  onViewAll?: (category: 'trending' | 'recent' | 'personalized') => void;
}

// ==========================================
// 子组件：技能卡片
// ==========================================

interface SkillCardProps {
  skill: TrendingSkill | RecentSkill | RecommendedSkill;
  onClick?: () => void;
  badge?: React.ReactNode;
  meta?: React.ReactNode;
}

function SkillCard({ skill, onClick, badge, meta }: SkillCardProps) {
  return (
    <button
      onClick={onClick}
      className="flex-shrink-0 w-[200px] p-3 rounded-lg bg-neutral-800/50 border border-neutral-700 hover:border-blue-500/30 hover:bg-neutral-800 transition-all text-left group"
    >
      <div className="flex items-start gap-2 mb-2">
        <Box size={16} className="shrink-0 mt-0.5 text-neutral-500 group-hover:text-blue-400 transition-colors" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-neutral-200 truncate group-hover:text-blue-300 transition-colors">
            {skill.name}
          </p>
          <p className="text-[10px] text-neutral-500 font-mono truncate">{skill.skill_id}</p>
        </div>
      </div>

      {badge && <div className="mb-2">{badge}</div>}

      {skill.description && (
        <p className="text-xs text-neutral-500 line-clamp-2 mb-2">{skill.description}</p>
      )}

      <div className="flex items-center gap-2 text-xs text-neutral-400">
        <div className="flex items-center gap-0.5">
          <Star size={10} className="text-yellow-400 fill-yellow-400" />
          <span>{skill.avg_rating.toFixed(1)}</span>
        </div>
        {meta}
        <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-neutral-700/50 text-neutral-500">
          {skill.executor_type}
        </span>
      </div>
    </button>
  );
}

// ==========================================
// 子组件：趋势徽章
// ==========================================

function TrendBadge({ trend }: { trend: string }) {
  const config: Record<string, { label: string; className: string }> = {
    hot: { label: '🔥 热门', className: 'bg-orange-500/10 text-orange-400 border-orange-500/20' },
    rising: { label: '📈 上升', className: 'bg-green-500/10 text-green-400 border-green-500/20' },
    stable: { label: '稳定', className: 'bg-neutral-700/50 text-neutral-400 border-neutral-600' },
  };

  const { label, className } = config[trend] || config.stable;

  return (
    <span className={`text-[9px] px-1.5 py-0.5 rounded border ${className}`}>
      {label}
    </span>
  );
}

// ==========================================
// 子组件：NEW 徽章
// ==========================================

function NewBadge({ isNew }: { isNew: boolean }) {
  if (!isNew) return null;

  return (
    <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
      ✨ NEW
    </span>
  );
}

// ==========================================
// 主组件
// ==========================================

export function SkillRecommendArea({ onSkillSelect, onViewAll }: SkillRecommendAreaProps) {
  const [trendingSkills, setTrendingSkills] = useState<TrendingSkill[]>([]);
  const [recentSkills, setRecentSkills] = useState<RecentSkill[]>([]);
  const [personalizedSkills, setPersonalizedSkills] = useState<RecommendedSkill[]>([]);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 加载推荐数据
  useEffect(() => {
    loadRecommendations();
  }, []);

  const loadRecommendations = async () => {
    setIsLoading(true);
    setError(null);

    try {
      // 并行加载三种推荐
      const [trending, recent, personalized] = await Promise.all([
        fetchAPI('/api/skills/market/trending?limit=5').catch(() => []),
        fetchAPI('/api/skills/market/recent?limit=5').catch(() => []),
        fetchAPI('/api/skills/market/personalized?limit=5').catch(() => [])
      ]);

      setTrendingSkills(Array.isArray(trending) ? trending : []);
      setRecentSkills(Array.isArray(recent) ? recent : []);
      setPersonalizedSkills(Array.isArray(personalized) ? personalized : []);
    } catch (e) {
      console.error('Failed to load recommendations:', e);
      setError('加载推荐失败');
    } finally {
      setIsLoading(false);
    }
  };

  // 渲染加载状态
  if (isLoading) {
    return (
      <div className="p-4 border-b border-neutral-800">
        <div className="flex items-center justify-center h-24 text-neutral-500">
          <Loader2 size={24} className="animate-spin" />
          <span className="ml-2 text-sm">加载推荐...</span>
        </div>
      </div>
    );
  }

  // 渲染错误状态
  if (error) {
    return (
      <div className="p-4 border-b border-neutral-800">
        <div className="flex items-center justify-center h-16 text-neutral-500">
          <span className="text-sm">{error}</span>
          <button
            onClick={loadRecommendations}
            className="ml-2 text-blue-400 hover:text-blue-300 text-sm"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  // 如果没有任何推荐数据，不显示
  if (trendingSkills.length === 0 && recentSkills.length === 0 && personalizedSkills.length === 0) {
    return null;
  }

  return (
    <div className="border-b border-neutral-800 bg-neutral-900/30">
      {/* 热门技能 */}
      {trendingSkills.length > 0 && (
        <div className="p-4 border-b border-neutral-800/50">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} className="text-orange-400" />
              <h3 className="text-sm font-medium text-neutral-300">🔥 热门技能</h3>
            </div>
            {onViewAll && (
              <button
                onClick={() => onViewAll('trending')}
                className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                查看全部
                <ChevronRight size={12} />
              </button>
            )}
          </div>
          <div className="flex gap-2 overflow-x-auto pb-2 custom-scrollbar">
            {trendingSkills.map((skill) => (
              <SkillCard
                key={skill.skill_id}
                skill={skill}
                onClick={() => onSkillSelect?.(skill.skill_id)}
                badge={<TrendBadge trend={skill.trend} />}
                meta={
                  <span className="text-neutral-500">{skill.usage_count} 次使用</span>
                }
              />
            ))}
          </div>
        </div>
      )}

      {/* 最新上线 */}
      {recentSkills.length > 0 && (
        <div className="p-4 border-b border-neutral-800/50">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Clock size={14} className="text-blue-400" />
              <h3 className="text-sm font-medium text-neutral-300">✨ 新上线</h3>
            </div>
            {onViewAll && (
              <button
                onClick={() => onViewAll('recent')}
                className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                查看全部
                <ChevronRight size={12} />
              </button>
            )}
          </div>
          <div className="flex gap-2 overflow-x-auto pb-2 custom-scrollbar">
            {recentSkills.map((skill) => (
              <SkillCard
                key={skill.skill_id}
                skill={skill}
                onClick={() => onSkillSelect?.(skill.skill_id)}
                badge={<NewBadge isNew={skill.is_new} />}
                meta={
                  <span className="text-neutral-500">
                    {new Date(skill.created_at).toLocaleDateString()}
                  </span>
                }
              />
            ))}
          </div>
        </div>
      )}

      {/* 个性化推荐 */}
      {personalizedSkills.length > 0 && (
        <div className="p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles size={14} className="text-purple-400" />
              <h3 className="text-sm font-medium text-neutral-300">💡 为你推荐</h3>
            </div>
            {onViewAll && (
              <button
                onClick={() => onViewAll('personalized')}
                className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                查看全部
                <ChevronRight size={12} />
              </button>
            )}
          </div>
          <div className="flex gap-2 overflow-x-auto pb-2 custom-scrollbar">
            {personalizedSkills.map((skill) => (
              <SkillCard
                key={skill.skill_id}
                skill={skill}
                onClick={() => onSkillSelect?.(skill.skill_id)}
                meta={
                  <span className="text-neutral-500 truncate max-w-[100px]" title={skill.match_reason}>
                    {skill.match_reason}
                  </span>
                }
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}