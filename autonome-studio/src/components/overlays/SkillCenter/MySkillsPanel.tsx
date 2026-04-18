/**
 * 我的技能面板 - 展示用户创建、收藏的技能和执行历史
 *
 * 功能：
 * - 我创建的：显示用户创建的技能，支持编辑、分享、删除
 * - 我的收藏：显示用户收藏的技能
 * - 执行历史：显示技能执行记录，支持重新执行
 *
 * 编辑功能：点击编辑按钮会触发 edit-skill 事件，ForgePanel 监听后加载技能详情
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useAuthStore } from "@/store/useAuthStore";
import { Box, Star, Clock, ChevronRight, Loader2, Trash2, Edit, Share2, Eye, RefreshCw, Hammer, FileEdit, Play, RotateCcw, Pin } from "lucide-react";
import { BASE_URL, pinnedSkillsApi } from "@/lib/api";
import { toast } from 'sonner';

// ==========================================
// 类型定义
// ==========================================
interface Skill {
  skill_id: string;
  name: string;
  description?: string;
  version?: string;
  executor_type: string;
  status: string;
  avg_rating?: number;
  usage_count?: number;
  created_at: string;
  updated_at?: string;  // 最后更新时间
}

interface ExecutionHistory {
  id: number;
  skill_id: string;
  skill_name: string;
  status: string;
  parameters: Record<string, unknown>;  // ✨ 新增：执行参数
  execution_time?: number;
  created_at: string;
  output_dir?: string;
}

// 子Tab类型
type SubTab = 'created' | 'favorites' | 'history';

export function MySkillsPanel() {
  const { user } = useAuthStore();
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('created');
  const [createdSkills, setCreatedSkills] = useState<Skill[]>([]);
  const [favoriteSkills, setFavoriteSkills] = useState<Skill[]>([]);
  const [executionHistory, setExecutionHistory] = useState<ExecutionHistory[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // 加载数据
  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('autonome_access_token');

      // 并行加载所有数据
      const [createdRes, favoritesRes, historyRes] = await Promise.all([
        fetch(`${BASE_URL}/api/skills/market/my/created`, {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        }),
        fetch(`${BASE_URL}/api/skills/market/my/favorites`, {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        }),
        fetch(`${BASE_URL}/api/skills/market/my/history`, {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        })
      ]);

      if (createdRes.ok) {
        const data = await createdRes.json();
        // 后端直接返回 List[SkillSummary]，不是 { skills: [...] }
        setCreatedSkills(Array.isArray(data) ? data : (data.skills || []));
      }
      if (favoritesRes.ok) {
        const data = await favoritesRes.json();
        setFavoriteSkills(Array.isArray(data) ? data : (data.favorites || []));
      }
      if (historyRes.ok) {
        const data = await historyRes.json();
        setExecutionHistory(Array.isArray(data) ? data : (data.history || []));
      }
    } catch (e) {
      console.error('加载数据失败:', e);
      toast.error('加载技能数据失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 初始加载
  useEffect(() => {
    loadData();
  }, [loadData]);

  // 监听技能保存成功事件
  useEffect(() => {
    const handleSkillSaved = () => {
      loadData();
    };

    window.addEventListener('skill-saved', handleSkillSaved);
    return () => window.removeEventListener('skill-saved', handleSkillSaved);
  }, [loadData]);

  // 取消收藏
  const handleUnfavorite = async (skillId: string) => {
    try {
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${BASE_URL}/api/skills/market/skills/${skillId}/favorite`, {
        method: 'DELETE',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });

      if (res.ok) {
        setFavoriteSkills(prev => prev.filter(s => s.skill_id !== skillId));
        toast.success('已取消收藏');
      }
    } catch (e) {
      toast.error('操作失败');
    }
  };

  // ==========================================
  // 编辑技能 - 跳转到技能工厂
  // ==========================================
  const handleEditSkill = (skillId: string) => {
    // 发送事件通知 SkillCenter 加载技能并切换到工厂 Tab
    // SkillCenter 会捕获此事件，设置 pendingEditSkillId 并切换 Tab
    // ForgePanel 挂载后会检测 editSkillId prop 并加载技能数据
    window.dispatchEvent(new CustomEvent('edit-skill', {
      detail: { skillId }
    }));

    toast.success('正在加载技能到编辑器...');
  };

  // 删除技能（已发布的会下架）
  const handleDeleteSkill = async (skillId: string, skillStatus: string) => {
    const confirmMessage = skillStatus === 'PUBLISHED'
      ? '确定要下架这个已发布的技能吗？下架后将不再对其他用户可见。'
      : '确定要删除这个技能吗？此操作不可撤销。';

    if (!confirm(confirmMessage)) return;

    try {
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${BASE_URL}/api/skills/${skillId}`, {
        method: 'DELETE',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });

      if (res.ok) {
        const result = await res.json();
        if (result.action === 'deprecated') {
          // 已发布技能下架，更新状态显示
          setCreatedSkills(prev => prev.map(s =>
            s.skill_id === skillId ? { ...s, status: 'DEPRECATED' } : s
          ));
          toast.success('技能已下架');
        } else {
          // 其他状态直接删除
          setCreatedSkills(prev => prev.filter(s => s.skill_id !== skillId));
          toast.success('技能已删除');
        }
      } else {
        const error = await res.json();
        toast.error(error.detail || '操作失败');
      }
    } catch (e) {
      toast.error('操作失败');
    }
  };

  // ==========================================
  // 重新执行技能 - 使用历史参数一键执行
  // ==========================================
  const handleReExecute = (record: ExecutionHistory) => {
    // 发送事件通知 SkillCenter 打开执行面板并预填充参数
    window.dispatchEvent(new CustomEvent('re-execute-skill', {
      detail: {
        skillId: record.skill_id,
        skillName: record.skill_name,
        parameters: record.parameters,
      }
    }));

    toast.success(`正在加载「${record.skill_name}」执行参数...`);
  };

  // ==========================================
  // 收藏技能到首页 - 快捷访问
  // ==========================================
  const handlePinSkill = (skill: Skill) => {
    pinnedSkillsApi.pinSkill({
      skill_id: skill.skill_id,
      name: skill.name,
      description: skill.description,
      executor_type: skill.executor_type,
      pinned_at: Date.now(),
    });
    toast.success(`「${skill.name}」已收藏到首页`);
  };

  // 状态颜色映射
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'PUBLISHED': return 'text-green-400 bg-green-400/10 border-green-400/20';
      case 'DRAFT': return 'text-amber-400 bg-amber-400/10 border-amber-400/20';
      case 'PRIVATE': return 'text-blue-400 bg-blue-400/10 border-blue-400/20';
      case 'PENDING_REVIEW': return 'text-purple-400 bg-purple-400/10 border-purple-400/20';
      case 'REJECTED': return 'text-red-400 bg-red-400/10 border-red-400/20';
      case 'DEPRECATED': return 'text-neutral-400 bg-neutral-400/10 border-neutral-400/20';
      case 'SUCCESS': return 'text-green-400';
      case 'FAILURE': return 'text-red-400';
      default: return 'text-neutral-400 bg-neutral-400/10 border-neutral-400/20';
    }
  };

  // 状态显示文本映射
  const getStatusText = (status: string) => {
    switch (status) {
      case 'PUBLISHED': return '已发布';
      case 'DRAFT': return '草稿';
      case 'PRIVATE': return '私有';
      case 'PENDING_REVIEW': return '待审核';
      case 'REJECTED': return '已驳回';
      case 'DEPRECATED': return '已下架';
      default: return status;
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 子Tab导航 */}
      <div className="border-b border-neutral-800 px-4 py-3 flex items-center gap-2 bg-neutral-900/20">
        <button
          onClick={() => setActiveSubTab('created')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeSubTab === 'created'
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
              : 'text-neutral-400 hover:text-neutral-300 hover:bg-neutral-800/50'
          }`}
        >
          <Edit size={16} />
          我创建的
          <span className="text-xs px-1.5 py-0.5 rounded bg-neutral-700/50">
            {createdSkills.length}
          </span>
        </button>
        <button
          onClick={() => setActiveSubTab('favorites')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeSubTab === 'favorites'
              ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
              : 'text-neutral-400 hover:text-neutral-300 hover:bg-neutral-800/50'
          }`}
        >
          <Star size={16} />
          我的收藏
          <span className="text-xs px-1.5 py-0.5 rounded bg-neutral-700/50">
            {favoriteSkills.length}
          </span>
        </button>
        <button
          onClick={() => setActiveSubTab('history')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeSubTab === 'history'
              ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
              : 'text-neutral-400 hover:text-neutral-300 hover:bg-neutral-800/50'
          }`}
        >
          <Clock size={16} />
          执行历史
          <span className="text-xs px-1.5 py-0.5 rounded bg-neutral-700/50">
            {executionHistory.length}
          </span>
        </button>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 size={24} className="animate-spin text-neutral-500" />
          </div>
        ) : (
          <>
            {/* 我创建的技能 */}
            {activeSubTab === 'created' && (
              <div className="space-y-2">
                {createdSkills.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-48 text-neutral-600 gap-3">
                    <Box size={40} className="opacity-30" />
                    <p className="text-sm">还没有创建任何技能</p>
                    <p className="text-xs text-neutral-500">前往技能工厂创建你的第一个技能</p>
                  </div>
                ) : (
                  createdSkills.map((skill) => (
                    <div
                      key={skill.skill_id}
                      className="p-4 bg-neutral-900/50 border border-neutral-800 rounded-lg hover:border-neutral-700 transition-colors group"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-medium text-neutral-200">{skill.name}</h4>
                            {/* 状态标签 */}
                            <span className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded border ${getStatusColor(skill.status)}`}>
                              {skill.status === 'DRAFT' && <FileEdit size={10} />}
                              {getStatusText(skill.status)}
                            </span>
                          </div>
                          <p className="text-xs text-neutral-500 mt-1 line-clamp-2">
                            {skill.description || '暂无描述'}
                          </p>
                          {/* 技能元信息：ID、版本、执行器类型 */}
                          <div className="flex items-center gap-4 mt-2 text-xs text-neutral-500">
                            <span className="font-mono">{skill.skill_id}</span>
                            <span>v{skill.version}</span>
                            <span>{skill.executor_type}</span>
                          </div>
                          {/* 时间信息：创建时间、更新时间 */}
                          <div className="flex items-center gap-4 mt-1.5 text-xs text-neutral-600">
                            <span className="flex items-center gap-1">
                              <Clock size={10} />
                              创建: {new Date(skill.created_at).toLocaleString()}
                            </span>
                            {skill.updated_at && (
                              <span className="flex items-center gap-1">
                                <RefreshCw size={10} />
                                更新: {new Date(skill.updated_at).toLocaleString()}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => handleEditSkill(skill.skill_id)}
                            className="p-1.5 hover:bg-neutral-700 rounded text-neutral-500 hover:text-blue-400 transition-colors"
                            title="编辑"
                          >
                            <Edit size={14} />
                          </button>
                          <button
                            className="p-1.5 hover:bg-neutral-700 rounded text-neutral-500 hover:text-green-400 transition-colors"
                            title="分享"
                          >
                            <Share2 size={14} />
                          </button>
                          <button
                            onClick={() => handleDeleteSkill(skill.skill_id, skill.status)}
                            className="p-1.5 hover:bg-neutral-700 rounded text-neutral-500 hover:text-red-400 transition-colors"
                            title={skill.status === 'PUBLISHED' ? '下架' : '删除'}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* 我的收藏 */}
            {activeSubTab === 'favorites' && (
              <div className="space-y-2">
                {favoriteSkills.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-48 text-neutral-600 gap-3">
                    <Star size={40} className="opacity-30" />
                    <p className="text-sm">还没有收藏任何技能</p>
                    <p className="text-xs text-neutral-500">在技能市场中发现并收藏感兴趣的技能</p>
                  </div>
                ) : (
                  favoriteSkills.map((skill) => (
                    <div
                      key={skill.skill_id}
                      className="p-4 bg-neutral-900/50 border border-neutral-800 rounded-lg hover:border-neutral-700 transition-colors group"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h4 className="text-sm font-medium text-neutral-200">{skill.name}</h4>
                          <p className="text-xs text-neutral-500 mt-1 line-clamp-2">
                            {skill.description || '暂无描述'}
                          </p>
                          <div className="flex items-center gap-4 mt-2 text-xs text-neutral-500">
                            <span className="font-mono">{skill.skill_id}</span>
                            <span>{skill.executor_type}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          {/* ✨ 收藏到首页按钮 */}
                          <button
                            onClick={() => handlePinSkill(skill)}
                            className="p-1.5 hover:bg-neutral-700 rounded text-neutral-500 hover:text-blue-400 transition-colors"
                            title="收藏到首页"
                          >
                            <Pin size={14} />
                          </button>
                          <button
                            onClick={() => handleUnfavorite(skill.skill_id)}
                            className="p-1.5 hover:bg-neutral-700 rounded text-yellow-400 transition-colors"
                            title="取消收藏"
                          >
                            <Star size={14} fill="currentColor" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* 执行历史 */}
            {activeSubTab === 'history' && (
              <div className="space-y-2">
                {executionHistory.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-48 text-neutral-600 gap-3">
                    <Clock size={40} className="opacity-30" />
                    <p className="text-sm">还没有执行记录</p>
                    <p className="text-xs text-neutral-500">执行技能后这里会显示历史记录</p>
                  </div>
                ) : (
                  executionHistory.map((record) => (
                    <div
                      key={record.id}
                      className="p-4 bg-neutral-900/50 border border-neutral-800 rounded-lg hover:border-neutral-700 transition-colors group"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-medium text-neutral-200">{record.skill_name}</h4>
                            <span className={`text-xs ${getStatusColor(record.status)}`}>
                              {record.status === 'SUCCESS' ? '成功' : record.status === 'FAILURE' ? '失败' : record.status}
                            </span>
                          </div>
                          <div className="flex items-center gap-4 mt-2 text-xs text-neutral-500">
                            <span>{new Date(record.created_at).toLocaleString()}</span>
                            {record.execution_time && (
                              <span>{record.execution_time.toFixed(1)}s</span>
                            )}
                          </div>
                          {record.output_dir && (
                            <p className="text-xs text-neutral-500 mt-1 font-mono truncate">
                              {record.output_dir}
                            </p>
                          )}
                        </div>
                        {/* ✨ 操作按钮组 */}
                        <div className="flex items-center gap-2">
                          {/* 重新执行按钮 */}
                          <button
                            onClick={() => handleReExecute(record)}
                            className="flex items-center gap-1 px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 text-xs font-medium rounded-lg transition-colors border border-blue-500/20"
                            title="使用相同参数重新执行"
                          >
                            <RotateCcw size={12} />
                            <span className="hidden sm:inline">重新执行</span>
                          </button>
                          <ChevronRight size={14} className="text-neutral-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}