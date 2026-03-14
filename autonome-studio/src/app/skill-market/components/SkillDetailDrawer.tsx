/**
 * 技能详情抽屉组件
 */

'use client';

import React, { useState, useEffect } from 'react';
import { X, Star, Heart, Copy, Play, Code, GitBranch, Clock, Users, Loader2, Check } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface SkillDetail {
  skill_id: string;
  name: string;
  description: string | null;
  version: string;
  executor_type: string;
  parameters_schema: Record<string, any>;
  expert_knowledge: string | null;
  dependencies: string[];
  avg_rating: number;
  rating_count: number;
  usage_count: number;
  owner_id: number;
  owner_name: string | null;
  is_favorited: boolean;
  user_rating: number | null;
  created_at: string;
  updated_at: string;
}

interface SkillDetailDrawerProps {
  skillId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onFavoriteToggle: (skillId: string) => void;
}

const EXECUTOR_COLORS: Record<string, string> = {
  'Python_env': 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  'R_env': 'bg-green-500/20 text-green-400 border-green-500/30',
  'Logical_Blueprint': 'bg-purple-500/20 text-purple-400 border-purple-500/30',
};

const EXECUTOR_LABELS: Record<string, string> = {
  'Python_env': 'Python 脚本',
  'R_env': 'R 脚本',
  'Logical_Blueprint': 'Nextflow 工作流',
};

export function SkillDetailDrawer({ skillId, isOpen, onClose, onFavoriteToggle }: SkillDetailDrawerProps) {
  const [skill, setSkill] = useState<SkillDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [userRating, setUserRating] = useState<number | null>(null);
  const [ratingComment, setRatingComment] = useState('');
  const [isSubmittingRating, setIsSubmittingRating] = useState(false);
  const [copied, setCopied] = useState(false);

  // 加载技能详情
  useEffect(() => {
    if (skillId && isOpen) {
      loadSkillDetail(skillId);
    }
  }, [skillId, isOpen]);

  const loadSkillDetail = async (id: string) => {
    setIsLoading(true);
    try {
      const BASE_URL = typeof window !== 'undefined'
        ? `http://${window.location.hostname}:8000`
        : 'http://localhost:8000';

      const response = await fetch(`${BASE_URL}/api/skills/market/skills/${id}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        }
      });

      const data = await response.json();
      setSkill(data);
      setUserRating(data.user_rating);
    } catch (error) {
      console.error('加载技能详情失败:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 提交评分
  const handleSubmitRating = async () => {
    if (!skill || !userRating) return;

    setIsSubmittingRating(true);
    try {
      const BASE_URL = typeof window !== 'undefined'
        ? `http://${window.location.hostname}:8000`
        : 'http://localhost:8000';

      const response = await fetch(`${BASE_URL}/api/skills/market/skills/${skill.skill_id}/rate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        },
        body: JSON.stringify({
          rating: userRating,
          comment: ratingComment || undefined
        })
      });

      const data = await response.json();

      // 更新本地状态
      if (skill) {
        setSkill({
          ...skill,
          avg_rating: data.avg_rating,
          rating_count: data.rating_count
        });
      }
    } catch (error) {
      console.error('提交评分失败:', error);
    } finally {
      setIsSubmittingRating(false);
    }
  };

  // 复制 skill_id
  const handleCopySkillId = () => {
    if (skill) {
      navigator.clipboard.writeText(skill.skill_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // 渲染参数表格
  const renderParametersTable = () => {
    if (!skill?.parameters_schema?.properties) return null;

    const props = skill.parameters_schema.properties;
    const required = new Set(skill.parameters_schema.required || []);

    return (
      <div className="mt-4">
        <h4 className="text-sm font-medium text-neutral-300 mb-2">参数定义</h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-700">
                <th className="text-left py-2 px-3 text-neutral-400 font-medium">参数名</th>
                <th className="text-left py-2 px-3 text-neutral-400 font-medium">类型</th>
                <th className="text-left py-2 px-3 text-neutral-400 font-medium">必填</th>
                <th className="text-left py-2 px-3 text-neutral-400 font-medium">默认值</th>
                <th className="text-left py-2 px-3 text-neutral-400 font-medium">描述</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(props).map(([key, prop]: [string, any]) => (
                <tr key={key} className="border-b border-neutral-800">
                  <td className="py-2 px-3 text-blue-400 font-mono text-xs">{key}</td>
                  <td className="py-2 px-3 text-neutral-300">{prop.type || 'string'}</td>
                  <td className="py-2 px-3">
                    {required.has(key) ? (
                      <span className="text-red-400">是</span>
                    ) : (
                      <span className="text-neutral-500">否</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-neutral-400 font-mono text-xs">
                    {prop.default !== undefined ? String(prop.default) : '-'}
                  </td>
                  <td className="py-2 px-3 text-neutral-400">{prop.description || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* 背景遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
          />

          {/* 抽屉 */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="fixed right-0 top-0 h-full w-full max-w-2xl bg-neutral-900 border-l border-neutral-800 z-50 overflow-y-auto"
          >
            {isLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 size={32} className="animate-spin text-blue-500" />
              </div>
            ) : skill ? (
              <div className="p-6">
                {/* 关闭按钮 */}
                <button
                  onClick={onClose}
                  className="absolute top-4 right-4 p-2 hover:bg-neutral-800 rounded-lg transition-colors"
                >
                  <X size={20} className="text-neutral-400" />
                </button>

                {/* 头部 */}
                <div className="mb-6">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${EXECUTOR_COLORS[skill.executor_type] || 'bg-neutral-700 text-neutral-300'}`}>
                      {EXECUTOR_LABELS[skill.executor_type] || skill.executor_type}
                    </span>
                    <span className="text-xs text-neutral-500">v{skill.version}</span>
                  </div>
                  <h2 className="text-2xl font-bold text-white mb-2">{skill.name}</h2>
                  <p className="text-neutral-400">{skill.description || '暂无描述'}</p>
                </div>

                {/* 统计信息 */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="bg-neutral-800/50 rounded-lg p-4 text-center">
                    <div className="flex items-center justify-center gap-1 mb-1">
                      <Star size={16} className="text-yellow-500 fill-yellow-500" />
                      <span className="text-xl font-bold text-white">{skill.avg_rating.toFixed(1)}</span>
                    </div>
                    <p className="text-xs text-neutral-500">{skill.rating_count} 条评价</p>
                  </div>
                  <div className="bg-neutral-800/50 rounded-lg p-4 text-center">
                    <div className="flex items-center justify-center gap-1 mb-1">
                      <Code size={16} className="text-blue-400" />
                      <span className="text-xl font-bold text-white">{skill.usage_count.toLocaleString()}</span>
                    </div>
                    <p className="text-xs text-neutral-500">次使用</p>
                  </div>
                  <div className="bg-neutral-800/50 rounded-lg p-4 text-center">
                    <div className="flex items-center justify-center gap-1 mb-1">
                      <Users size={16} className="text-green-400" />
                      <span className="text-sm font-medium text-white truncate">{skill.owner_name || '匿名'}</span>
                    </div>
                    <p className="text-xs text-neutral-500">创建者</p>
                  </div>
                </div>

                {/* 操作按钮 */}
                <div className="flex gap-2 mb-6">
                  <button
                    onClick={() => onFavoriteToggle(skill.skill_id)}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                      skill.is_favorited
                        ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                        : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-300 border border-neutral-700'
                    }`}
                  >
                    <Heart size={16} className={skill.is_favorited ? 'fill-red-400' : ''} />
                    {skill.is_favorited ? '已收藏' : '收藏'}
                  </button>
                  <button
                    onClick={handleCopySkillId}
                    className="flex items-center gap-2 px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded-lg text-neutral-300 border border-neutral-700 transition-colors"
                  >
                    {copied ? <Check size={16} className="text-green-400" /> : <Copy size={16} />}
                    {copied ? '已复制' : '复制 ID'}
                  </button>
                </div>

                {/* 参数定义 */}
                {renderParametersTable()}

                {/* 专家知识 */}
                {skill.expert_knowledge && (
                  <div className="mt-6">
                    <h4 className="text-sm font-medium text-neutral-300 mb-2">专家知识</h4>
                    <div className="bg-neutral-800/50 rounded-lg p-4 text-sm text-neutral-400 whitespace-pre-wrap">
                      {skill.expert_knowledge}
                    </div>
                  </div>
                )}

                {/* 依赖 */}
                {skill.dependencies && skill.dependencies.length > 0 && (
                  <div className="mt-6">
                    <h4 className="text-sm font-medium text-neutral-300 mb-2">依赖包</h4>
                    <div className="flex flex-wrap gap-2">
                      {skill.dependencies.map((dep, i) => (
                        <span key={i} className="px-2 py-1 bg-neutral-800 rounded text-xs text-neutral-400">
                          {dep}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* 评分区域 */}
                <div className="mt-8 border-t border-neutral-800 pt-6">
                  <h4 className="text-sm font-medium text-neutral-300 mb-4">我的评分</h4>
                  <div className="flex items-center gap-2 mb-4">
                    {[1, 2, 3, 4, 5].map((star) => (
                      <button
                        key={star}
                        onClick={() => setUserRating(star)}
                        className="p-1"
                      >
                        <Star
                          size={24}
                          className={`${userRating && star <= userRating ? 'text-yellow-500 fill-yellow-500' : 'text-neutral-600'}`}
                        />
                      </button>
                    ))}
                    <span className="ml-2 text-sm text-neutral-400">
                      {userRating ? `${userRating} 星` : '点击评分'}
                    </span>
                  </div>

                  <textarea
                    value={ratingComment}
                    onChange={(e) => setRatingComment(e.target.value)}
                    placeholder="写下你的评价（可选）..."
                    className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white placeholder-neutral-500 focus:border-blue-500 focus:outline-none resize-none"
                    rows={3}
                  />

                  <button
                    onClick={handleSubmitRating}
                    disabled={!userRating || isSubmittingRating}
                    className="mt-3 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
                  >
                    {isSubmittingRating ? '提交中...' : '提交评分'}
                  </button>
                </div>

                {/* 时间信息 */}
                <div className="mt-8 flex items-center gap-4 text-xs text-neutral-500">
                  <div className="flex items-center gap-1">
                    <Clock size={12} />
                    <span>创建于 {new Date(skill.created_at).toLocaleDateString()}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Clock size={12} />
                    <span>更新于 {new Date(skill.updated_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>
            ) : null}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}