/**
 * 设置面板 - 分类管理、标签管理、审核队列（管理员）
 */

'use client';

import { useState, useEffect } from 'react';
import { useAuthStore } from "@/store/useAuthStore";
import { Settings, Tag, FolderTree, CheckCircle, XCircle, Clock, Loader2, ChevronRight } from "lucide-react";
import { BASE_URL } from "@/lib/api";
import { toast } from 'sonner';

// ==========================================
// 类型定义
// ==========================================
interface Category {
  id: string;
  name: string;
  icon: string;
  description?: string;
  skill_count: number;
}

interface TagItem {
  id: string;
  name: string;
  color: string;
  usage_count: number;
}

interface PendingSkill {
  skill_id: string;
  name: string;
  description?: string;
  owner_name: string;
  executor_type: string;
  created_at: string;
}

// 子Tab类型
type SubTab = 'categories' | 'tags' | 'review';

export function SettingsPanel() {
  const { user } = useAuthStore();
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('categories');
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<TagItem[]>([]);
  const [pendingSkills, setPendingSkills] = useState<PendingSkill[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const isAdmin = user?.is_superuser || false;

  // 加载数据
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('autonome_access_token');
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      // 加载分类
      const catRes = await fetch(`${BASE_URL}/api/skills/categories`, { headers });
      if (catRes.ok) {
        const data = await catRes.json();
        setCategories(data.categories || []);
      }

      // 加载标签
      const tagRes = await fetch(`${BASE_URL}/api/skills/tags`, { headers });
      if (tagRes.ok) {
        const data = await tagRes.json();
        setTags(data.tags || []);
      }

      // 管理员加载审核队列
      if (isAdmin) {
        const reviewRes = await fetch(`${BASE_URL}/api/skills/admin/pending`, { headers });
        if (reviewRes.ok) {
          const data = await reviewRes.json();
          setPendingSkills(data.skills || []);
        }
      }
    } catch (e) {
      console.error('加载数据失败:', e);
    } finally {
      setIsLoading(false);
    }
  };

  // 审核通过
  const handleApprove = async (skillId: string) => {
    try {
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${BASE_URL}/api/skills/admin/${skillId}/approve`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });

      if (res.ok) {
        setPendingSkills(prev => prev.filter(s => s.skill_id !== skillId));
        toast.success('技能已通过审核');
      }
    } catch (e) {
      toast.error('操作失败');
    }
  };

  // 审核拒绝
  const handleReject = async (skillId: string, reason: string) => {
    try {
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${BASE_URL}/api/skills/admin/${skillId}/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ reason })
      });

      if (res.ok) {
        setPendingSkills(prev => prev.filter(s => s.skill_id !== skillId));
        toast.success('已拒绝该技能');
      }
    } catch (e) {
      toast.error('操作失败');
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 子Tab导航 */}
      <div className="border-b border-neutral-800 px-4 py-3 flex items-center gap-2 bg-neutral-900/20">
        <button
          onClick={() => setActiveSubTab('categories')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeSubTab === 'categories'
              ? 'bg-action/20 text-action border border-action/30'
              : 'text-neutral-400 hover:text-neutral-300 hover:bg-neutral-800/50'
          }`}
        >
          <FolderTree size={16} />
          分类管理
        </button>
        <button
          onClick={() => setActiveSubTab('tags')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeSubTab === 'tags'
              ? 'bg-data/20 text-data border border-data/30'
              : 'text-neutral-400 hover:text-neutral-300 hover:bg-neutral-800/50'
          }`}
        >
          <Tag size={16} />
          标签管理
        </button>
        {isAdmin && (
          <button
            onClick={() => setActiveSubTab('review')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeSubTab === 'review'
                ? 'bg-warning/20 text-warning border border-warning/30'
                : 'text-neutral-400 hover:text-neutral-300 hover:bg-neutral-800/50'
            }`}
          >
            <Clock size={16} />
            审核队列
            <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-400">
              {pendingSkills.length}
            </span>
          </button>
        )}
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 size={24} className="animate-spin text-neutral-500" />
          </div>
        ) : (
          <>
            {/* 分类管理 */}
            {activeSubTab === 'categories' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-medium text-neutral-300">技能分类</h3>
                  <button className="text-xs px-3 py-1.5 bg-action hover:bg-action/90 text-white rounded-lg transition-colors">
                    + 新增分类
                  </button>
                </div>
                {categories.map((category) => (
                  <div
                    key={category.id}
                    className="p-4 bg-neutral-900/50 border border-neutral-800 rounded-lg hover:border-neutral-700 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-xl">{category.icon}</span>
                        <div>
                          <h4 className="text-sm font-medium text-neutral-200">{category.name}</h4>
                          {category.description && (
                            <p className="text-xs text-neutral-500 mt-0.5">{category.description}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-neutral-500">
                          {category.skill_count} 个技能
                        </span>
                        <ChevronRight size={14} className="text-neutral-500" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* 标签管理 */}
            {activeSubTab === 'tags' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-medium text-neutral-300">技能标签</h3>
                  <button className="text-xs px-3 py-1.5 bg-data hover:bg-data/90 text-white rounded-lg transition-colors">
                    + 新增标签
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {tags.map((tag) => (
                    <div
                      key={tag.id}
                      className="flex items-center gap-2 px-3 py-1.5 bg-neutral-900/50 border border-neutral-800 rounded-full hover:border-neutral-700 transition-colors group"
                    >
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: tag.color }}
                      />
                      <span className="text-sm text-neutral-300">{tag.name}</span>
                      <span className="text-xs text-neutral-500">({tag.usage_count})</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 审核队列 */}
            {activeSubTab === 'review' && isAdmin && (
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-neutral-300 mb-4">
                  待审核技能 ({pendingSkills.length})
                </h3>
                {pendingSkills.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-48 text-neutral-600 gap-3">
                    <CheckCircle size={40} className="opacity-30" />
                    <p className="text-sm">暂无待审核的技能</p>
                  </div>
                ) : (
                  pendingSkills.map((skill) => (
                    <div
                      key={skill.skill_id}
                      className="p-4 bg-neutral-900/50 border border-neutral-800 rounded-lg"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h4 className="text-sm font-medium text-neutral-200">{skill.name}</h4>
                          <p className="text-xs text-neutral-500 mt-1 line-clamp-2">
                            {skill.description || '暂无描述'}
                          </p>
                          <div className="flex items-center gap-4 mt-2 text-xs text-neutral-500">
                            <span>提交者: {skill.owner_name}</span>
                            <span>{skill.executor_type}</span>
                            <span>{new Date(skill.created_at).toLocaleDateString()}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-4">
                          <button
                            onClick={() => handleApprove(skill.skill_id)}
                            className="flex items-center gap-1 px-3 py-1.5 bg-success hover:bg-success/90 text-success-foreground text-xs rounded-lg transition-colors"
                          >
                            <CheckCircle size={14} />
                            通过
                          </button>
                          <button
                            onClick={() => {
                              const reason = prompt('请输入拒绝原因:');
                              if (reason) handleReject(skill.skill_id, reason);
                            }}
                            className="flex items-center gap-1 px-3 py-1.5 bg-danger hover:bg-danger/90 text-danger-foreground text-xs rounded-lg transition-colors"
                          >
                            <XCircle size={14} />
                            拒绝
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* 非管理员提示 */}
            {activeSubTab === 'review' && !isAdmin && (
              <div className="flex flex-col items-center justify-center h-48 text-neutral-600 gap-3">
                <Settings size={40} className="opacity-30" />
                <p className="text-sm">需要管理员权限才能访问审核队列</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}