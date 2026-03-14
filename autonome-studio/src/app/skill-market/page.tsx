"use client";

/**
 * 技能市场页面 - 技能浏览、搜索、评分、收藏
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Search, Star, Heart, Filter, ChevronLeft, ChevronRight, Loader2, Code, GitBranch, BarChart3, ArrowLeft } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useRouter } from 'next/navigation';

import { SkillCard } from './components/SkillCard';
import { SkillDetailDrawer } from './components/SkillDetailDrawer';
import { CategoryNav } from './components/CategoryNav';

// 类型定义
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

interface PaginatedResponse {
  skills: SkillSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface Category {
  id: string;
  name: string;
  icon: string;
}

// 执行器类型图标
const EXECUTOR_ICONS: Record<string, React.ReactNode> = {
  'Python_env': <Code size={14} className="text-blue-400" />,
  'R_env': <Code size={14} className="text-green-400" />,
  'Logical_Blueprint': <GitBranch size={14} className="text-purple-400" />,
};

export default function SkillMarketPage() {
  const router = useRouter();

  // 状态
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<'popularity' | 'rating' | 'recent'>('popularity');

  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const [categories, setCategories] = useState<Category[]>([]);

  // 获取分类列表
  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const BASE_URL = typeof window !== 'undefined'
          ? `http://${window.location.hostname}:8000`
          : 'http://localhost:8000';

        const response = await fetch(`${BASE_URL}/api/skills/market/categories`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
          }
        });
        const data = await response.json();
        setCategories(data.categories || []);
      } catch (error) {
        console.error('获取分类失败:', error);
      }
    };
    fetchCategories();
  }, []);

  // 获取技能列表
  const fetchSkills = useCallback(async () => {
    setIsLoading(true);
    try {
      const BASE_URL = typeof window !== 'undefined'
        ? `http://${window.location.hostname}:8000`
        : 'http://localhost:8000';

      const params = new URLSearchParams();
      params.set('page', page.toString());
      params.set('page_size', pageSize.toString());
      params.set('sort_by', sortBy);
      if (searchQuery) params.set('search', searchQuery);
      if (selectedCategory) params.set('category', selectedCategory);

      const response = await fetch(`${BASE_URL}/api/skills/market/skills?${params}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        }
      });

      const data: PaginatedResponse = await response.json();
      setSkills(data.skills || []);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (error) {
      console.error('获取技能列表失败:', error);
    } finally {
      setIsLoading(false);
    }
  }, [page, pageSize, sortBy, searchQuery, selectedCategory]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  // 搜索防抖
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      fetchSkills();
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // 分类切换
  useEffect(() => {
    setPage(1);
    fetchSkills();
  }, [selectedCategory, sortBy]);

  // 收藏切换
  const handleFavoriteToggle = async (skillId: string) => {
    try {
      const BASE_URL = typeof window !== 'undefined'
        ? `http://${window.location.hostname}:8000`
        : 'http://localhost:8000';

      const response = await fetch(`${BASE_URL}/api/skills/market/skills/${skillId}/favorite`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        }
      });

      const data = await response.json();

      // 更新本地状态
      setSkills(prev => prev.map(skill =>
        skill.skill_id === skillId
          ? { ...skill, is_favorited: data.is_favorited }
          : skill
      ));
    } catch (error) {
      console.error('收藏操作失败:', error);
    }
  };

  // 点击技能卡片
  const handleSkillClick = (skillId: string) => {
    setSelectedSkillId(skillId);
    setIsDrawerOpen(true);
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-white">
      {/* 顶部导航栏 */}
      <header className="sticky top-0 z-50 bg-neutral-900/95 backdrop-blur-sm border-b border-neutral-800">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            {/* 返回按钮 + 标题 */}
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/')}
                className="p-2 hover:bg-neutral-800 rounded-lg transition-colors"
              >
                <ArrowLeft size={20} className="text-neutral-400" />
              </button>
              <div>
                <h1 className="text-xl font-semibold text-white">技能市场</h1>
                <p className="text-xs text-neutral-500">发现和使用高质量的生信分析技能</p>
              </div>
            </div>

            {/* 搜索栏 */}
            <div className="flex-1 max-w-xl mx-8">
              <div className="relative">
                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="搜索技能名称、描述..."
                  className="w-full bg-neutral-800 border border-neutral-700 rounded-lg pl-10 pr-4 py-2 text-sm text-white placeholder-neutral-500 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>

            {/* 排序选择 */}
            <div className="flex items-center gap-2">
              <Filter size={16} className="text-neutral-500" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
              >
                <option value="popularity">按热度排序</option>
                <option value="rating">按评分排序</option>
                <option value="recent">按时间排序</option>
              </select>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex gap-6">
          {/* 左侧分类导航 */}
          <aside className="w-48 flex-shrink-0">
            <CategoryNav
              categories={categories}
              selectedCategory={selectedCategory}
              onSelectCategory={setSelectedCategory}
            />
          </aside>

          {/* 主内容区 */}
          <main className="flex-1">
            {/* 统计信息 */}
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-neutral-400">
                共找到 <span className="text-white font-medium">{total}</span> 个技能
              </p>
            </div>

            {/* 加载状态 */}
            {isLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 size={32} className="animate-spin text-blue-500" />
              </div>
            ) : skills.length === 0 ? (
              /* 空状态 */
              <div className="text-center py-20">
                <BarChart3 size={48} className="mx-auto text-neutral-600 mb-4" />
                <p className="text-neutral-400">暂无技能</p>
                <p className="text-sm text-neutral-500 mt-1">尝试调整搜索条件或分类</p>
              </div>
            ) : (
              <>
                {/* 技能网格 */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  <AnimatePresence>
                    {skills.map((skill, index) => (
                      <motion.div
                        key={skill.skill_id}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        transition={{ delay: index * 0.05 }}
                      >
                        <SkillCard
                          skill={skill}
                          onFavoriteToggle={handleFavoriteToggle}
                          onClick={() => handleSkillClick(skill.skill_id)}
                        />
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>

                {/* 分页 */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-center gap-2 mt-8">
                    <button
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className="p-2 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-900 disabled:text-neutral-600 rounded-lg transition-colors"
                    >
                      <ChevronLeft size={18} />
                    </button>

                    <div className="flex items-center gap-1">
                      {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                        let pageNum;
                        if (totalPages <= 5) {
                          pageNum = i + 1;
                        } else if (page <= 3) {
                          pageNum = i + 1;
                        } else if (page >= totalPages - 2) {
                          pageNum = totalPages - 4 + i;
                        } else {
                          pageNum = page - 2 + i;
                        }

                        return (
                          <button
                            key={pageNum}
                            onClick={() => setPage(pageNum)}
                            className={`w-8 h-8 rounded-lg text-sm transition-colors ${
                              page === pageNum
                                ? 'bg-blue-600 text-white'
                                : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-300'
                            }`}
                          >
                            {pageNum}
                          </button>
                        );
                      })}
                    </div>

                    <button
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                      disabled={page === totalPages}
                      className="p-2 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-900 disabled:text-neutral-600 rounded-lg transition-colors"
                    >
                      <ChevronRight size={18} />
                    </button>
                  </div>
                )}
              </>
            )}
          </main>
        </div>
      </div>

      {/* 技能详情抽屉 */}
      <SkillDetailDrawer
        skillId={selectedSkillId}
        isOpen={isDrawerOpen}
        onClose={() => {
          setIsDrawerOpen(false);
          setSelectedSkillId(null);
        }}
        onFavoriteToggle={handleFavoriteToggle}
      />
    </div>
  );
}