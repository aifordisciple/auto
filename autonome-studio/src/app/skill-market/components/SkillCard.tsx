/**
 * 技能卡片组件
 */

'use client';

import React from 'react';
import { Star, Heart, Code, GitBranch, Users } from 'lucide-react';

interface SkillSummary {
  skill_id: string;
  name: string;
  description: string | null;
  executor_type: string;
  category: string | null;
  tags: string[];
  avg_rating: number;
  rating_count: number;
  usage_count: number;
  owner_name: string | null;
  is_favorited: boolean;
  created_at: string;
}

interface SkillCardProps {
  skill: SkillSummary;
  onFavoriteToggle: (skillId: string) => void;
  onClick: () => void;
}

// 执行器类型颜色
const EXECUTOR_COLORS: Record<string, string> = {
  'Python_env': 'bg-blue-500/20 text-blue-400',
  'R_env': 'bg-green-500/20 text-green-400',
  'Logical_Blueprint': 'bg-purple-500/20 text-purple-400',
};

const EXECUTOR_LABELS: Record<string, string> = {
  'Python_env': 'Python',
  'R_env': 'R',
  'Logical_Blueprint': 'Nextflow',
};

export function SkillCard({ skill, onFavoriteToggle, onClick }: SkillCardProps) {
  const handleFavoriteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onFavoriteToggle(skill.skill_id);
  };

  return (
    <div
      onClick={onClick}
      className="group bg-neutral-900 border border-neutral-800 rounded-xl p-4 hover:border-neutral-700 hover:bg-neutral-900/80 transition-all cursor-pointer"
    >
      {/* 顶部：评分 + 收藏 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1">
          <Star size={14} className="text-yellow-500 fill-yellow-500" />
          <span className="text-sm font-medium text-white">{skill.avg_rating.toFixed(1)}</span>
          <span className="text-xs text-neutral-500">({skill.rating_count})</span>
        </div>
        <button
          onClick={handleFavoriteClick}
          className="p-1.5 rounded-lg hover:bg-neutral-800 transition-colors"
        >
          <Heart
            size={16}
            className={skill.is_favorited ? 'text-red-500 fill-red-500' : 'text-neutral-500'}
          />
        </button>
      </div>

      {/* 标题 + 执行器类型 */}
      <div className="flex items-start gap-2 mb-2">
        <div className={`px-2 py-0.5 rounded text-xs font-medium ${EXECUTOR_COLORS[skill.executor_type] || 'bg-neutral-700 text-neutral-300'}`}>
          {EXECUTOR_LABELS[skill.executor_type] || skill.executor_type}
        </div>
      </div>

      <h3 className="text-base font-semibold text-white mb-2 line-clamp-1 group-hover:text-blue-400 transition-colors">
        {skill.name}
      </h3>

      {/* 描述 */}
      <p className="text-sm text-neutral-400 line-clamp-2 mb-3">
        {skill.description || '暂无描述'}
      </p>

      {/* 分类标签 */}
      {skill.category && (
        <div className="mb-3">
          <span className="text-xs bg-neutral-800 text-neutral-300 px-2 py-0.5 rounded">
            {skill.category}
          </span>
        </div>
      )}

      {/* 底部：作者 + 使用量 */}
      <div className="flex items-center justify-between text-xs text-neutral-500 pt-2 border-t border-neutral-800">
        <div className="flex items-center gap-1">
          <Users size={12} />
          <span>{skill.owner_name || '匿名'}</span>
        </div>
        <div className="flex items-center gap-1">
          <Code size={12} />
          <span>{skill.usage_count.toLocaleString()} 次使用</span>
        </div>
      </div>
    </div>
  );
}