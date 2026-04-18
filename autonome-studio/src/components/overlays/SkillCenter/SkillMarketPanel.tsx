/**
 * 技能市场面板 - 整合到技能中心的市场功能
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { Search, Star, Heart, Filter, ChevronLeft, ChevronRight, Loader2, Code, BarChart3, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { BASE_URL } from '@/lib/api';
import { useIsMobile } from '@/hooks/useIsMobile';
import { useDebounce } from '@/hooks/usePerformance';
import { cn } from '@/lib/utils';

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

interface SkillMarketPanelProps {
  onUseSkill: (skillId: string) => void;
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

export function SkillMarketPanel({ onUseSkill }: SkillMarketPanelProps) {
  // 状态
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  const [searchQuery, setSearchQuery] = useState('');
  // 🚀 性能优化：使用统一的防抖 Hook，避免重复实现
  const debouncedSearchQuery = useDebounce(searchQuery, 300);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<'popularity' | 'rating' | 'recent'>('popularity');

  const [categories, setCategories] = useState<Category[]>([]);

  // 移动端分类抽屉状态
  const isMobile = useIsMobile();
  const [showCategoryDrawer, setShowCategoryDrawer] = useState(false);

  // 获取分类列表
  useEffect(() => {
    const fetchCategories = async () => {
      try {
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
      const params = new URLSearchParams();
      params.set('page', page.toString());
      params.set('page_size', pageSize.toString());
      params.set('sort_by', sortBy);
      // 🚀 使用防抖后的搜索词，减少不必要的 API 调用
      if (debouncedSearchQuery) params.set('search', debouncedSearchQuery);
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
  }, [page, pageSize, sortBy, debouncedSearchQuery, selectedCategory]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  // 🚀 防抖搜索触发：当防抖值变化时重置页码并触发搜索
  useEffect(() => {
    setPage(1);
    fetchSkills();
  }, [debouncedSearchQuery]);

  // 分类切换
  useEffect(() => {
    setPage(1);
    fetchSkills();
  }, [selectedCategory, sortBy]);

  // 收藏切换
  const handleFavoriteToggle = async (skillId: string) => {
    try {
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

  return (
    <div className="flex-1 flex overflow-hidden">
      {isMobile ? (
        // ============================================================
        // 移动端: 分类抽屉 + 单列技能网格
        // ============================================================
        <>
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* 顶部搜索栏 */}
            <div className="shrink-0 p-3 border-b border-neutral-800 flex items-center gap-2">
              {/* 分类筛选按钮 */}
              <button
                onClick={() => setShowCategoryDrawer(true)}
                className="flex items-center gap-2 px-3 py-2.5 bg-neutral-800 rounded-xl min-h-[44px]"
              >
                <Filter size={18} />
                <span className="text-sm">筛选</span>
                {selectedCategory && (
                  <span className="w-2 h-2 rounded-full bg-blue-500" />
                )}
              </button>
              {/* 搜索输入 */}
              <div className="relative flex-1">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="搜索技能..."
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-neutral-300 outline-none focus:border-blue-500/50 transition-all placeholder:text-neutral-600 min-h-[44px]"
                />
              </div>
            </div>

            {/* 统计信息 + 排序 */}
            <div className="shrink-0 px-4 py-2 border-b border-neutral-800 flex items-center justify-between">
              <p className="text-xs text-neutral-400">
                共 <span className="text-white font-medium">{total}</span> 个技能
              </p>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                className="bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
              >
                <option value="popularity">按热度</option>
                <option value="rating">按评分</option>
                <option value="recent">按时间</option>
              </select>
            </div>

            {/* 技能网格 - 单列布局 */}
            <div className="flex-1 overflow-y-auto p-3 custom-scrollbar">
              {isLoading ? (
                <div className="flex items-center justify-center h-32 text-neutral-500">
                  <Loader2 size={28} className="animate-spin" />
                </div>
              ) : skills.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-32 text-neutral-600 gap-3">
                  <BarChart3 size={40} className="opacity-20" />
                  <p className="text-sm">暂无技能</p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 gap-3">
                    <AnimatePresence>
                      {skills.map((skill, index) => (
                        <motion.div
                          key={skill.skill_id}
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -20 }}
                          transition={{ delay: index * 0.03 }}
                        >
                          <SkillCardCompact
                            skill={skill}
                            onFavoriteToggle={handleFavoriteToggle}
                            onUseSkill={onUseSkill}
                          />
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>

                  {/* 分页 */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-2 mt-4">
                      <button
                        onClick={() => setPage(p => Math.max(1, p - 1))}
                        disabled={page === 1}
                        className="p-2 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-900 disabled:text-neutral-600 rounded-lg transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
                      >
                        <ChevronLeft size={20} />
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
                              className={cn(
                                "w-9 h-9 rounded-lg text-xs transition-colors min-h-[44px] min-w-[44px]",
                                page === pageNum
                                  ? "bg-blue-600 text-white"
                                  : "bg-neutral-800 hover:bg-neutral-700 text-neutral-300"
                              )}
                            >
                              {pageNum}
                            </button>
                          );
                        })}
                      </div>

                      <button
                        onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                        disabled={page === totalPages}
                        className="p-2 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-900 disabled:text-neutral-600 rounded-lg transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
                      >
                        <ChevronRight size={20} />
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* 分类抽屉 - 移动端弹出 */}
          {showCategoryDrawer && (
            <div className="fixed inset-0 z-50 flex">
              {/* 背景遮罩 */}
              <div
                className="absolute inset-0 bg-black/60"
                onClick={() => setShowCategoryDrawer(false)}
              />
              {/* 抽屉内容 */}
              <div className="absolute left-0 top-0 bottom-0 w-[280px] max-w-[80vw] bg-neutral-900 border-r border-neutral-800 flex flex-col">
                {/* 头部 */}
                <div className="p-4 border-b border-neutral-800 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-neutral-200">分类筛选</h3>
                  <button
                    onClick={() => setShowCategoryDrawer(false)}
                    className="p-2 hover:bg-neutral-800 rounded-lg text-neutral-400 min-h-[44px] min-w-[44px] flex items-center justify-center"
                  >
                    <X size={20} />
                  </button>
                </div>
                {/* 分类列表 */}
                <div className="flex-1 overflow-y-auto p-3 custom-scrollbar">
                  <button
                    onClick={() => {
                      setSelectedCategory(null);
                      setShowCategoryDrawer(false);
                    }}
                    className={cn(
                      "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition-all min-h-[48px]",
                      selectedCategory === null
                        ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                        : "hover:bg-neutral-800 text-neutral-400"
                    )}
                  >
                    <span className="text-lg">📦</span>
                    <span className="flex-1 text-left">全部技能</span>
                  </button>

                  <div className="mt-2 space-y-1">
                    {categories.map((category) => (
                      <button
                        key={category.id}
                        onClick={() => {
                          setSelectedCategory(category.id);
                          setShowCategoryDrawer(false);
                        }}
                        className={cn(
                          "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition-all min-h-[48px]",
                          selectedCategory === category.id
                            ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                            : "hover:bg-neutral-800 text-neutral-400"
                        )}
                      >
                        <span className="text-lg">{category.icon}</span>
                        <span className="flex-1 text-left">{category.name}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        // ============================================================
        // 桌面端: 保持现有双栏布局
        // ============================================================
        <>
          {/* Left Panel: 分类导航 (180px) */}
          <div className="w-[180px] border-r border-neutral-800 flex flex-col bg-neutral-900/20">
            <div className="p-3 border-b border-neutral-800">
              <h3 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider">分类筛选</h3>
            </div>
            <div className="flex-1 overflow-y-auto p-2 custom-scrollbar">
              <button
                onClick={() => setSelectedCategory(null)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors ${
                  selectedCategory === null
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                    : 'hover:bg-neutral-800 text-neutral-400'
                }`}
              >
                <span>📦</span>
                <span>全部技能</span>
              </button>

              {categories.map((category) => (
                <button
                  key={category.id}
                  onClick={() => setSelectedCategory(category.id)}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors ${
                    selectedCategory === category.id
                      ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                      : 'hover:bg-neutral-800 text-neutral-400'
                  }`}
                >
                  <span className="text-sm">{category.icon}</span>
                  <span>{category.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Right Panel: 技能列表 */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* 搜索和排序 */}
            <div className="p-3 border-b border-neutral-800 flex items-center gap-3">
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="搜索技能..."
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-sm text-neutral-300 outline-none focus:border-blue-500/50 transition-all placeholder:text-neutral-600"
                />
              </div>
              <div className="flex items-center gap-2">
                <Filter size={14} className="text-neutral-500" />
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                  className="bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
                >
                  <option value="popularity">按热度</option>
                  <option value="rating">按评分</option>
                  <option value="recent">按时间</option>
                </select>
              </div>
            </div>

            {/* 统计信息 */}
            <div className="px-4 py-2 border-b border-neutral-800">
              <p className="text-xs text-neutral-400">
                共找到 <span className="text-white font-medium">{total}</span> 个技能
              </p>
            </div>

            {/* 技能网格 */}
            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
              {isLoading ? (
                <div className="flex items-center justify-center h-32 text-neutral-500">
                  <Loader2 size={24} className="animate-spin" />
                </div>
              ) : skills.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-32 text-neutral-600 gap-2">
                  <BarChart3 size={32} className="opacity-20" />
                  <p className="text-sm">暂无技能</p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                    <AnimatePresence>
                      {skills.map((skill, index) => (
                        <motion.div
                          key={skill.skill_id}
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -20 }}
                          transition={{ delay: index * 0.03 }}
                        >
                          <SkillCardCompact
                            skill={skill}
                            onFavoriteToggle={handleFavoriteToggle}
                            onUseSkill={onUseSkill}
                          />
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>

                  {/* 分页 */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-2 mt-4">
                      <button
                        onClick={() => setPage(p => Math.max(1, p - 1))}
                        disabled={page === 1}
                        className="p-1.5 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-900 disabled:text-neutral-600 rounded-lg transition-colors"
                      >
                        <ChevronLeft size={16} />
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
                              className={`w-7 h-7 rounded-lg text-xs transition-colors ${
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
                        className="p-1.5 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-900 disabled:text-neutral-600 rounded-lg transition-colors"
                      >
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// 紧凑版技能卡片
interface SkillCardCompactProps {
  skill: SkillSummary;
  onFavoriteToggle: (skillId: string) => void;
  onUseSkill: (skillId: string) => void;
}

function SkillCardCompact({ skill, onFavoriteToggle, onUseSkill }: SkillCardCompactProps) {
  return (
    <div className="group bg-neutral-900/50 border border-neutral-800 rounded-lg p-3 hover:border-neutral-700 hover:bg-neutral-900/80 transition-all">
      {/* 顶部：评分 + 收藏 */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1">
          <Star size={12} className="text-yellow-500 fill-yellow-500" />
          <span className="text-xs font-medium text-white">{skill.avg_rating.toFixed(1)}</span>
          <span className="text-[10px] text-neutral-500">({skill.rating_count})</span>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onFavoriteToggle(skill.skill_id);
          }}
          className="p-1 rounded hover:bg-neutral-800 transition-colors"
        >
          <Heart
            size={14}
            className={skill.is_favorited ? 'text-red-500 fill-red-500' : 'text-neutral-500'}
          />
        </button>
      </div>

      {/* 执行器类型标签 */}
      <div className="mb-2">
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${EXECUTOR_COLORS[skill.executor_type] || 'bg-neutral-700 text-neutral-300'}`}>
          {EXECUTOR_LABELS[skill.executor_type] || skill.executor_type}
        </span>
      </div>

      {/* 标题 */}
      <h3 className="text-sm font-semibold text-white mb-1 line-clamp-1 group-hover:text-blue-400 transition-colors">
        {skill.name}
      </h3>

      {/* 描述 */}
      <p className="text-xs text-neutral-400 line-clamp-2 mb-2">
        {skill.description || '暂无描述'}
      </p>

      {/* 底部：使用量 */}
      <div className="flex items-center justify-between text-[10px] text-neutral-500 pt-2 border-t border-neutral-800">
        <div className="flex items-center gap-1">
          <Code size={10} />
          <span>{skill.usage_count.toLocaleString()} 次使用</span>
        </div>
        <button
          onClick={() => onUseSkill(skill.skill_id)}
          className="px-2 py-1 bg-blue-600/20 text-blue-400 rounded hover:bg-blue-600/30 transition-colors"
        >
          使用
        </button>
      </div>
    </div>
  );
}