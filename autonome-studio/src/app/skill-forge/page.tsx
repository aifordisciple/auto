"use client";

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';

import { TopHeader } from '@/components/layout/TopHeader';
import { useForgeStore } from '@/store/useForgeStore';
import { ForgeSidebar } from './components/ForgeSidebar';
import { ForgeChatStage } from './components/ForgeChatStage';
import { SkillDraftEditor } from './components/SkillDraftEditor';

export default function SkillForgePage() {
  const router = useRouter();
  const { sessionId, createSession, loadSessionList } = useForgeStore();

  // 初始化
  useEffect(() => {
    loadSessionList();
    if (!sessionId) {
      createSession();
    }
  }, []);

  return (
    <main className="h-screen w-full bg-white dark:bg-[#131314] flex overflow-hidden font-sans transition-colors">
      {/* 左侧边栏 */}
      <ForgeSidebar />

      {/* 主工作区 */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        <TopHeader />

        {/* 顶部工具栏 */}
        <div className="h-12 bg-gray-100 dark:bg-[#1e1e1f] border-b border-gray-200 dark:border-neutral-800 flex items-center justify-between px-4 shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={() => router.push('/')}
              className="flex items-center gap-2 text-gray-600 dark:text-white font-bold tracking-wider hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
            >
              <ArrowLeft size={18} />
              <span className="text-blue-500">🧬</span> AUTONOME
            </button>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-neutral-400">
            <span>技能锻造工厂</span>
            <span className="text-blue-500">AI 驱动</span>
          </div>
        </div>

        {/* 双栏布局 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 左栏：AI对话区 */}
          <div className="w-1/2 flex flex-col border-r border-gray-200 dark:border-neutral-800 bg-gray-50/50 dark:bg-[#1e1e1f]/50">
            <ForgeChatStage />
          </div>

          {/* 右栏：技能编辑/预览区 */}
          <div className="w-1/2 flex flex-col bg-white dark:bg-[#1e1e1f] relative">
            <SkillDraftEditor />
          </div>
        </div>
      </div>
    </main>
  );
}