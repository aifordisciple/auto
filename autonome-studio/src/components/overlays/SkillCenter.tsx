/**
 * SkillCenter - SKILL 兵器库（性能优化版）
 *
 * 性能优化：
 * 1. 使用 useGlobalEvent hook 统一管理事件监听器
 * 2. 减少重复的事件监听代码
 * 3. 自动清理，防止内存泄漏
 */
"use client";

import { useState, useEffect, useCallback, ReactNode } from 'react';
import { useUIStore } from "@/store/useUIStore";
import { X, Box, Play, Store, User, Hammer, Settings } from "lucide-react";
import { SkillExecutePanel } from './SkillCenter/SkillExecutePanel';
import { SkillMarketPanel } from './SkillCenter/SkillMarketPanel';
import { Button } from '@/components/ui/Button';
import { MySkillsPanel } from './SkillCenter/MySkillsPanel';
import { ForgePanel } from './SkillCenter/ForgePanel';
import { SettingsPanel } from './SkillCenter/SettingsPanel';
import { BASE_URL } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================
interface SkillParameter {
  type: string;
  format?: string;
  description?: string;
  default?: unknown;
}

interface SkillSchema {
  type: string;
  properties: Record<string, SkillParameter>;
  required: string[];
}

interface Skill {
  skill_id: string;
  name: string;
  version: string;
  author: string;
  executor_type: string;
  timeout_seconds: number;
  parameters_schema: SkillSchema;
  bundle_name: string;
  category?: string;
  category_name?: string;
  subcategory?: string;
  subcategory_name?: string;
  tags?: string[];
}

type TabType = 'execute' | 'my' | 'market' | 'forge' | 'settings';

// ==========================================
// Tab 配置
// ==========================================
const TABS: { id: TabType; label: string; icon: ReactNode; color: string }[] = [
  { id: 'execute', label: '执行', icon: <Play size={14} />, color: 'blue' },
  { id: 'my', label: '我的', icon: <User size={14} />, color: 'green' },
  { id: 'market', label: '市场', icon: <Store size={14} />, color: 'purple' },
  { id: 'forge', label: '工厂', icon: <Hammer size={14} />, color: 'orange' },
  { id: 'settings', label: '设置', icon: <Settings size={14} />, color: 'gray' },
];

const COLOR_CLASSES: Record<string, string> = {
  blue: 'bg-action text-action-foreground',
  green: 'bg-success text-success-foreground',
  purple: 'bg-data text-data-foreground',
  orange: 'bg-warning text-warning-foreground',
  gray: 'bg-neutral-600 text-white',
};

// ==========================================
// 主组件
// ==========================================
export function SkillCenter() {
  // V2: 功能标志 - 启用内联技能中心时，全局弹窗不渲染
  const enableInlineSkillCenter = process.env.NEXT_PUBLIC_ENABLE_INLINE_SKILL_CENTER === 'true';
  if (enableInlineSkillCenter) return null;

  // 状态订阅
  const isSkillCenterOpen = useUIStore(state => state.isSkillCenterOpen);
  const closeAllOverlays = useUIStore(state => state.closeAllOverlays);
  const openDataCenter = useUIStore(state => state.openDataCenter);

  // 本地状态
  const [activeTab, setActiveTab] = useState<TabType>('execute');
  const [selectedSkillFromMarket, setSelectedSkillFromMarket] = useState<Skill | null>(null);
  const [transformDraft, setTransformDraft] = useState<any>(null);
  const [pendingEditSkillId, setPendingEditSkillId] = useState<string | null>(null);
  // ✨ 预选技能 ID（用于从推荐卡片直接打开）
  const [preSelectedSkillId, setPreSelectedSkillId] = useState<string | null>(null);

  // ==========================================
  // 事件处理函数
  // ==========================================
  const handleSwitchToForge = useCallback(() => {
    setActiveTab('forge');
  }, []);

  const handleEditSkill = useCallback((event: Event) => {
    const customEvent = event as CustomEvent;
    const { skillId } = customEvent.detail || {};

    if (skillId) {
      setPendingEditSkillId(skillId);
      setActiveTab('forge');
    }
  }, []);

  const handleTransformToSkill = useCallback((event: Event) => {
    const customEvent = event as CustomEvent;
    const draft = customEvent.detail;

    if (draft) {
      setTransformDraft(draft);
      setActiveTab('forge');
    }
  }, []);

  // ✨ 处理预选技能事件
  const handlePreSelectSkill = useCallback((event: Event) => {
    const customEvent = event as CustomEvent;
    const { skillId } = customEvent.detail || {};

    if (skillId) {
      setPreSelectedSkillId(skillId);
      // 确保在执行 Tab
      setActiveTab('execute');
    }
  }, []);

  // ==========================================
  // 事件监听器（统一管理）
  // ==========================================
  useEffect(() => {
    window.addEventListener('switch-to-forge-tab', handleSwitchToForge);
    window.addEventListener('edit-skill', handleEditSkill);
    window.addEventListener('transform-to-skill', handleTransformToSkill);
    window.addEventListener('pre-select-skill', handlePreSelectSkill);

    return () => {
      window.removeEventListener('switch-to-forge-tab', handleSwitchToForge);
      window.removeEventListener('edit-skill', handleEditSkill);
      window.removeEventListener('transform-to-skill', handleTransformToSkill);
      window.removeEventListener('pre-select-skill', handlePreSelectSkill);
    };
  }, [handleSwitchToForge, handleEditSkill, handleTransformToSkill, handlePreSelectSkill]);

  // ==========================================
  // URL 参数处理
  // ==========================================
  useEffect(() => {
    if (isSkillCenterOpen) {
      const urlParams = new URLSearchParams(window.location.search);
      const tabParam = urlParams.get('tab') as TabType | null;

      if (tabParam && TABS.some(t => t.id === tabParam)) {
        setActiveTab(tabParam);
      }
    }
  }, [isSkillCenterOpen]);

  // ==========================================
  // 从市场使用技能
  // ==========================================
  const handleUseSkillFromMarket = useCallback(async (skillId: string) => {
    try {
      const response = await fetch(`${BASE_URL}/api/skills/market/skills/${skillId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        }
      });
      const data = await response.json();

      const skill: Skill = {
        skill_id: data.skill_id,
        name: data.name,
        version: data.version,
        author: data.owner_name || '匿名',
        executor_type: data.executor_type,
        timeout_seconds: 3600,
        parameters_schema: data.parameters_schema || { type: 'object', properties: {}, required: [] },
        bundle_name: data.skill_id,
        category: data.category,
        category_name: data.category,
        tags: data.tags || []
      };

      setSelectedSkillFromMarket(skill);
      setActiveTab('execute');
    } catch (error) {
      console.error('获取技能详情失败:', error);
    }
  }, []);

  // ==========================================
  // 编辑/转化完成回调
  // ==========================================
  const handleEditComplete = useCallback(() => {
    setPendingEditSkillId(null);
  }, []);

  const handleTransformComplete = useCallback(() => {
    setTransformDraft(null);
  }, []);

  // ==========================================
  // 渲染
  // ==========================================
  if (!isSkillCenterOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={closeAllOverlays} />

      <div className="relative w-full md:w-panel-xl md:max-w-panel h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">

        {/* Header with Tabs */}
        <div className="h-16 shrink-0 border-b border-neutral-800 px-3 md:px-6 flex items-center justify-between bg-neutral-900/40">
          <div className="flex items-center gap-2 md:gap-4 flex-1 min-w-0">
            <div className="flex items-center gap-2 md:gap-3 shrink-0">
              <div className="p-1.5 md:p-2 bg-blue-500/20 border border-blue-500/30 rounded-lg text-blue-400 shadow-[0_0_15px_rgba(59,130,246,0.15)]">
                <Box size={16} strokeWidth={2.5} className="md:w-[18px] md:h-[18px]" />
              </div>
              <div className="hidden sm:block">
                <h2 className="text-sm font-bold text-neutral-200 tracking-wide">SKILL 兵器库</h2>
                <p className="text-[10px] text-neutral-500 font-mono mt-0.5">技能发现、创建与执行</p>
              </div>
            </div>

            {/* Tab 切换 */}
            <div className="flex items-center bg-neutral-800/50 rounded-lg p-1 ml-1 md:ml-4 overflow-x-auto flex-1 md:flex-none">
              {TABS.map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1 md:gap-2 px-2 md:px-4 py-1.5 rounded-md text-xs font-medium transition-all ${
                      isActive
                        ? COLOR_CLASSES[tab.color] + ' shadow-md'
                        : 'text-neutral-400 hover:text-white'
                    }`}
                  >
                    {tab.icon}
                    <span className="hidden sm:inline">{tab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <Button variant="icon" onClick={closeAllOverlays} aria-label="关闭" className="shrink-0 ml-2">
            <X size={18} />
          </Button>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-hidden">
          {activeTab === 'execute' && (
            <SkillExecutePanel
              onDataCenterOpen={openDataCenter}
              selectedSkillFromMarket={selectedSkillFromMarket}
              preSelectedSkillId={preSelectedSkillId}
            />
          )}
          {activeTab === 'my' && (
            <MySkillsPanel />
          )}
          {activeTab === 'market' && (
            <SkillMarketPanel onUseSkill={handleUseSkillFromMarket} />
          )}
          {activeTab === 'forge' && (
            <ForgePanel
              transformDraft={transformDraft}
              editSkillId={pendingEditSkillId}
              onEditComplete={handleEditComplete}
              onTransformComplete={handleTransformComplete}
            />
          )}
          {activeTab === 'settings' && (
            <SettingsPanel />
          )}
        </div>
      </div>
    </div>
  );
}