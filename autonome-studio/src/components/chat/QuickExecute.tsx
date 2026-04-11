/**
 * QuickExecute 组件 - 首页快捷入口
 *
 * 功能：
 * 1. 收藏的技能快速访问
 * 2. 技能中心、执行历史快捷入口
 *
 * 注：输入框已移至底部的 ChatInputBox，避免重复
 */

'use client';

import React, { useState, useEffect } from 'react';
import { Sparkles, Star, Clock, Pin, X } from 'lucide-react';
import { pinnedSkillsApi, PinnedSkill } from '@/lib/api';
import { useUIStore } from '@/store/useUIStore';
import { toast } from 'sonner';

// ==========================================
// 类型定义
// ==========================================

interface QuickExecuteProps {
  onExecuteSkill: (skillId: string, skillName: string) => void;
  onSendMessage: (message: string) => void;
}

// ==========================================
// 组件实现
// ==========================================

export function QuickExecute({ onExecuteSkill }: QuickExecuteProps) {
  // 获取收藏的技能 - 使用 state 以支持实时更新
  const [pinnedSkills, setPinnedSkills] = useState<PinnedSkill[]>([]);

  // 打开技能中心
  const openSkillCenter = useUIStore(state => state.openSkillCenter);

  // 初始化和刷新收藏列表
  useEffect(() => {
    setPinnedSkills(pinnedSkillsApi.getPinnedSkills());
  }, []);

  // 取消收藏
  const handleUnpin = (skillId: string, skillName: string, e: React.MouseEvent) => {
    e.stopPropagation(); // 阻止触发执行技能
    pinnedSkillsApi.unpinSkill(skillId);
    setPinnedSkills(pinnedSkillsApi.getPinnedSkills()); // 刷新列表
    toast.success(`「${skillName}」已取消收藏`);
  };

  // 没有收藏技能时，只显示快捷入口
  if (pinnedSkills.length === 0) {
    return (
      <div className="w-full max-w-3xl mx-auto mt-6">
        <div className="flex flex-wrap items-center justify-center gap-2">
          <button
            onClick={() => openSkillCenter()}
            className="flex items-center gap-1.5 px-4 py-2 text-sm text-gray-600 dark:text-neutral-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
          >
            <Star size={14} />
            收藏技能
          </button>
          <span className="text-gray-300 dark:text-neutral-700">|</span>
          <button
            onClick={() => {
              openSkillCenter();
              setTimeout(() => {
                window.dispatchEvent(new CustomEvent('skill-center-tab', { detail: 'history' }));
              }, 100);
            }}
            className="flex items-center gap-1.5 px-4 py-2 text-sm text-gray-600 dark:text-neutral-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
          >
            <Clock size={14} />
            执行历史
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl mx-auto mt-6">
      {/* 收藏的技能 */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-3 px-1">
          <Pin size={14} className="text-yellow-500" />
          <span className="text-xs font-medium text-gray-500 dark:text-neutral-400">快捷技能</span>
        </div>

        <div className="flex flex-wrap gap-2">
          {pinnedSkills.map((skill: PinnedSkill) => (
            <button
              key={skill.skill_id}
              onClick={() => onExecuteSkill(skill.skill_id, skill.name)}
              className="group flex items-center gap-2 px-3 py-2 bg-white dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg hover:border-blue-500 dark:hover:border-blue-500 text-sm text-gray-700 dark:text-neutral-200 transition-colors relative"
            >
              <Sparkles size={14} className="text-blue-500" />
              <span>{skill.name}</span>
              {/* 取消收藏按钮 - hover 时显示 */}
              <span
                onClick={(e) => handleUnpin(skill.skill_id, skill.name, e)}
                className="ml-1 p-0.5 rounded hover:bg-neutral-200 dark:hover:bg-neutral-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity"
                title="取消收藏"
              >
                <X size={12} />
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* 快捷入口 */}
      <div className="flex flex-wrap items-center justify-center gap-2">
        <button
          onClick={() => openSkillCenter()}
          className="flex items-center gap-1.5 px-4 py-2 text-sm text-gray-600 dark:text-neutral-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
        >
          <Star size={14} />
          收藏技能
        </button>
        <span className="text-gray-300 dark:text-neutral-700">|</span>
        <button
          onClick={() => {
            openSkillCenter();
            setTimeout(() => {
              window.dispatchEvent(new CustomEvent('skill-center-tab', { detail: 'history' }));
            }, 100);
          }}
          className="flex items-center gap-1.5 px-4 py-2 text-sm text-gray-600 dark:text-neutral-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
        >
          <Clock size={14} />
          执行历史
        </button>
      </div>
    </div>
  );
}