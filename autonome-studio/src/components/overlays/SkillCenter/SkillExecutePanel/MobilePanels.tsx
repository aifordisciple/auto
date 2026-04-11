/**
 * 移动端子组件集合
 *
 * 包含三个移动端专用面板组件：
 * 1. MobileCategoryPanel - 分类选择面板 (Step 1)
 * 2. MobileSkillListPanel - 技能列表面板 (Step 2)
 * 3. MobileParamConfigPanel - 参数配置面板 (Step 3)
 *
 * 设计原则：触摸友好的大按钮布局，每个按钮最小高度 48px
 */
'use client';

import React from 'react';
import {
  Search,
  Play,
  Loader2,
  CheckCircle,
  XCircle,
  ChevronRight,
  ChevronDown,
  Terminal,
  Box,
  Info,
  MessageSquarePlus
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Skill, SkillParameter, Category } from './types';

// ==========================================
// 移动端子组件：分类选择面板
// Step 1: 用户选择技能分类
// 触摸友好的大按钮布局，每个分类按钮最小高度 56px
// ==========================================

interface MobileCategoryPanelProps {
  categories: Category[];
  categoryCounts: Record<string, number>;
  selectedCategory: string;
  expandedCategories: Set<string>;
  toggleCategoryExpand: (id: string) => void;
  onSelect: (categoryId: string) => void;
}

export function MobileCategoryPanel({
  categories,
  categoryCounts,
  selectedCategory,
  expandedCategories,
  toggleCategoryExpand,
  onSelect
}: MobileCategoryPanelProps) {
  return (
    <div className="flex-1 overflow-y-auto p-3 custom-scrollbar">
      <h3 className="text-sm font-medium text-neutral-400 mb-3">选择分类</h3>
      <div className="space-y-2">
        {categories.map((category) => {
          const isExpanded = expandedCategories.has(category.id);
          const hasSubcategories = category.subcategories && category.subcategories.length > 0;
          const count = categoryCounts[category.id] || 0;

          return (
            <div key={category.id}>
              {/* 主分类按钮 */}
              <button
                onClick={() => {
                  if (hasSubcategories) {
                    toggleCategoryExpand(category.id);
                  } else {
                    onSelect(category.id);
                  }
                }}
                className={cn(
                  "w-full flex items-center gap-3 p-4 rounded-xl border transition-all min-h-[56px]",
                  selectedCategory === category.id && !hasSubcategories
                    ? "bg-blue-500/10 border-blue-500/30 text-blue-300"
                    : "bg-neutral-900/50 border-neutral-800 hover:border-blue-500/30 text-neutral-200"
                )}
              >
                <span className="text-xl">{category.icon}</span>
                <span className="flex-1 text-left font-medium">{category.name}</span>
                <span className="text-xs px-2 py-1 rounded bg-neutral-800 text-neutral-400">
                  {count}
                </span>
                {hasSubcategories && (
                  <ChevronDown
                    size={18}
                    className={cn(
                      "text-neutral-500 transition-transform",
                      isExpanded && "rotate-180"
                    )}
                  />
                )}
                {!hasSubcategories && (
                  <ChevronRight size={18} className="text-neutral-500" />
                )}
              </button>

              {/* 子分类列表 */}
              {hasSubcategories && isExpanded && (
                <div className="mt-2 ml-4 space-y-1.5">
                  {category.subcategories!.map((sub) => {
                    const subCount = categoryCounts[sub.id] || 0;
                    return (
                      <button
                        key={sub.id}
                        onClick={() => onSelect(sub.id)}
                        className={cn(
                          "w-full flex items-center gap-3 p-3 rounded-xl border transition-all min-h-[52px]",
                          selectedCategory === sub.id
                            ? "bg-blue-500/10 border-blue-500/30 text-blue-300"
                            : "bg-neutral-900/30 border-neutral-800 hover:border-blue-500/30 text-neutral-300"
                        )}
                      >
                        <span className="text-lg">{sub.icon || '•'}</span>
                        <span className="flex-1 text-left text-sm">{sub.name}</span>
                        <span className="text-xs px-2 py-1 rounded bg-neutral-800 text-neutral-500">
                          {subCount}
                        </span>
                        <ChevronRight size={16} className="text-neutral-500" />
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ==========================================
// 移动端子组件：技能列表面板
// Step 2: 用户选择具体技能
// 包含搜索功能和技能卡片列表
// ==========================================

interface MobileSkillListPanelProps {
  skills: Skill[];
  isLoading: boolean;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  selectedSkill: Skill | null;
  onSelect: (skill: Skill) => void;
  onViewDetail: (skillId: string) => void;
}

export function MobileSkillListPanel({
  skills,
  isLoading,
  searchQuery,
  setSearchQuery,
  selectedSkill,
  onSelect,
  onViewDetail
}: MobileSkillListPanelProps) {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 搜索栏 - 固定顶部 */}
      <div className="shrink-0 p-3 border-b border-neutral-800">
        <div className="relative">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索技能..."
            className="w-full bg-neutral-950 border border-neutral-800 rounded-xl pl-11 pr-4 py-3 text-sm text-neutral-300 outline-none focus:border-blue-500/50 transition-all min-h-[48px] placeholder:text-neutral-600"
          />
        </div>
      </div>

      {/* 技能列表 - 可滚动 */}
      <div className="flex-1 overflow-y-auto p-3 custom-scrollbar">
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 size={28} className="animate-spin text-neutral-500" />
          </div>
        ) : skills.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-neutral-600 gap-3">
            <Box size={40} className="opacity-20" />
            <p className="text-sm">暂无匹配的技能</p>
          </div>
        ) : (
          <div className="space-y-2">
            {skills.map((skill) => (
              <div
                key={skill.skill_id}
                onClick={() => onSelect(skill)}
                className={cn(
                  "w-full flex items-center gap-3 p-4 rounded-xl border transition-all text-left min-h-[72px] cursor-pointer",
                  selectedSkill?.skill_id === skill.skill_id
                    ? "bg-blue-500/10 border-blue-500/30"
                    : "bg-neutral-900/50 border-neutral-800 hover:border-blue-500/30"
                )}
              >
                <Box size={22} className="shrink-0 text-neutral-500" />
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-neutral-200 truncate">{skill.name}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <p className="text-xs text-neutral-500 font-mono truncate">{skill.skill_id}</p>
                    {skill.category_name && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400">
                        {skill.category_name}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onViewDetail(skill.skill_id);
                  }}
                  className="p-2.5 hover:bg-neutral-800 rounded-lg text-neutral-500 min-h-[44px] min-w-[44px] flex items-center justify-center"
                  title="查看详情"
                >
                  <Info size={18} />
                </button>
                <ChevronRight size={18} className="text-neutral-500" />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ==========================================
// 移动端子组件：参数配置面板
// Step 3: 用户配置参数并执行技能
// 包含技能信息、参数表单、执行按钮
// ==========================================

interface MobileParamConfigPanelProps {
  skill: Skill;
  paramValues: Record<string, unknown>;
  setParamValues: (values: Record<string, unknown>) => void;
  isExecuting: boolean;
  taskStatus: string | null;
  taskId: string | null;
  logs: string[];
  currentProjectId: string | null;
  onExecute: () => void;
  onViewDetail: () => void;
  onAttachToChat: () => void;
  renderParamInput: (key: string, prop: SkillParameter) => React.ReactNode;
  terminalEndRef: React.RefObject<HTMLDivElement | null>;
}

export function MobileParamConfigPanel({
  skill,
  paramValues,
  setParamValues,
  isExecuting,
  taskStatus,
  taskId,
  logs,
  currentProjectId,
  onExecute,
  onViewDetail,
  onAttachToChat,
  renderParamInput,
  terminalEndRef
}: MobileParamConfigPanelProps) {
  const schema = skill.parameters_schema;
  const parameterOrder = schema?.['x-parameter-order'];
  let entries: [string, SkillParameter][] = [];

  if (schema?.properties) {
    if (parameterOrder && Array.isArray(parameterOrder)) {
      entries = parameterOrder
        .filter(name => schema.properties[name])
        .map(name => [name, schema.properties[name]]);
    } else {
      entries = Object.entries(schema.properties);
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* 技能信息头部 - 固定 */}
      <div className="shrink-0 p-4 border-b border-neutral-800 bg-neutral-900/20">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-neutral-200">{skill.name}</h3>
          <button
            onClick={onViewDetail}
            className="p-2.5 hover:bg-neutral-800 rounded-lg text-neutral-500 min-h-[44px] min-w-[44px] flex items-center justify-center"
          >
            <Info size={20} />
          </button>
        </div>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <span className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
            {skill.executor_type}
          </span>
          <span className="text-xs text-neutral-500">v{skill.version}</span>
          {skill.category_name && (
            <span className="text-xs text-neutral-500">• {skill.category_name}</span>
          )}
        </div>
      </div>

      {/* 参数表单 - 可滚动 */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        <h4 className="text-sm font-medium text-neutral-400 mb-4">参数配置</h4>
        {schema?.properties && Object.keys(schema.properties).length > 0 ? (
          <div className="space-y-4">
            {entries.map(([key, prop]) => {
              const isRequired = schema.required?.includes(key);
              return (
                <div key={key}>
                  <label className="flex items-center gap-2 text-sm text-neutral-300 mb-2">
                    <span className="font-mono">{key}</span>
                    {isRequired && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
                        必填
                      </span>
                    )}
                  </label>
                  {prop.description && (
                    <p className="text-xs text-neutral-500 mb-2">{prop.description}</p>
                  )}
                  {renderParamInput(key, prop)}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center text-neutral-500 py-8">
            此技能无需配置参数
          </div>
        )}
      </div>

      {/* 执行状态 */}
      {(isExecuting || taskStatus) && (
        <div className="shrink-0 p-4 border-t border-neutral-800 bg-neutral-900/20">
          <div className="flex items-center gap-2">
            {taskStatus === 'SUCCESS' && <CheckCircle size={18} className="text-green-400" />}
            {taskStatus === 'FAILURE' && <XCircle size={18} className="text-red-400" />}
            {(taskStatus === 'PENDING' || taskStatus === 'STARTED' || isExecuting) && (
              <Loader2 size={18} className="text-blue-400 animate-spin" />
            )}
            <span className="text-sm text-neutral-300">
              {taskStatus === 'SUCCESS' && '执行完成'}
              {taskStatus === 'FAILURE' && '执行失败'}
              {(taskStatus === 'PENDING' || taskStatus === 'STARTED') && '执行中...'}
              {!taskStatus && isExecuting && '提交中...'}
            </span>
            {taskId && (
              <span className="text-xs text-neutral-500 font-mono ml-auto">
                Task: {taskId.slice(0, 8)}
              </span>
            )}
          </div>
        </div>
      )}

      {/* 实时日志 */}
      {taskId && (
        <div className="shrink-0 border-t border-neutral-800 max-h-[180px]">
          <div className="p-3 border-b border-neutral-800 flex items-center gap-2 bg-neutral-900/30">
            <Terminal size={14} className="text-green-400" />
            <span className="text-xs font-medium text-neutral-400">执行日志</span>
            <span className="text-[10px] text-neutral-500 ml-auto font-mono">{logs.length} 行</span>
          </div>
          <div className="h-32 overflow-y-auto p-3 bg-neutral-950 font-mono text-xs text-green-400/90 custom-scrollbar">
            {logs.length === 0 ? (
              <div className="flex items-center justify-center h-full text-neutral-600 gap-2">
                <Loader2 size={14} className="animate-spin" />
                <span>等待日志输出...</span>
              </div>
            ) : (
              <div className="space-y-0.5">
                {logs.map((log, i) => (
                  <div key={i} className="hover:bg-white/5 px-1 py-0.5 rounded whitespace-pre-wrap">
                    {log}
                  </div>
                ))}
                <span className="animate-pulse inline-block w-2 h-3 bg-green-500 ml-1 align-middle"></span>
                <div ref={terminalEndRef} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* 执行按钮 - 固定底部 */}
      <div className="shrink-0 p-4 border-t border-neutral-800 bg-neutral-900/80 space-y-3">
        {/* 附加到聊天 */}
        <button
          onClick={onAttachToChat}
          className="w-full flex items-center justify-center gap-2 py-3 bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 text-purple-300 font-medium rounded-xl transition-all min-h-[52px]"
        >
          <MessageSquarePlus size={18} />
          附加到聊天
        </button>

        {/* 执行按钮 */}
        <button
          onClick={onExecute}
          disabled={isExecuting || !currentProjectId}
          className="w-full flex items-center justify-center gap-2 py-4 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white font-medium rounded-xl transition-all min-h-[56px]"
        >
          {isExecuting ? (
            <>
              <Loader2 size={20} className="animate-spin" />
              执行中...
            </>
          ) : (
            <>
              <Play size={20} />
              执行技能
            </>
          )}
        </button>
      </div>
    </div>
  );
}