"use client";

import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Hammer } from 'lucide-react';
import { useUIStore } from '@/store/useUIStore';
import { useForgeStore } from '@/store/useForgeStore';
import { ForgeChatStage } from '@/app/skill-forge/components/ForgeChatStage';
import { SkillDraftEditor } from '@/app/skill-forge/components/SkillDraftEditor';

export function ForgeOverlay() {
  const { isSkillForgeOpen, closeAllOverlays } = useUIStore();
  const { sessionId, createSession, loadSessionList, reset } = useForgeStore();

  // 初始化锻造会话
  useEffect(() => {
    if (isSkillForgeOpen) {
      loadSessionList();
      if (!sessionId) {
        createSession();
      }
    }
  }, [isSkillForgeOpen]);

  // 关闭时重置状态
  const handleClose = () => {
    closeAllOverlays();
  };

  return (
    <AnimatePresence>
      {isSkillForgeOpen && (
        <>
          {/* 背景遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={handleClose}
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm cursor-pointer"
          />

          {/* 全屏悬浮窗 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            className="fixed inset-4 z-50 bg-white dark:bg-[#131314] rounded-2xl shadow-2xl border border-gray-200 dark:border-neutral-800 flex flex-col overflow-hidden"
          >
            {/* 顶部标题栏 */}
            <div className="h-14 border-b border-gray-200 dark:border-neutral-800 flex items-center justify-between px-6 shrink-0 bg-gray-50 dark:bg-[#1e1e1f]">
              <div className="flex items-center gap-3">
                <Hammer className="text-blue-500" size={20} />
                <h2 className="font-semibold text-gray-900 dark:text-white">技能锻造工厂</h2>
                <span className="text-xs text-blue-500 bg-blue-500/10 px-2 py-0.5 rounded-full">AI 驱动</span>
              </div>
              <button
                onClick={handleClose}
                className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            {/* 主内容区 - 双栏布局 */}
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
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}