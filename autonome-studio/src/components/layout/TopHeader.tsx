"use client";

import { useEffect } from "react";
import { Menu, ChevronRight, Share2, Zap, Play, Pause } from "lucide-react";
import { useAuthStore } from "../../store/useAuthStore";
import { useUIStore } from "../../store/useUIStore";

interface TopHeaderProps {
  projectName?: string;
  isLeftOpen?: boolean;
  onToggleLeft?: () => void;
  onShare?: () => void;
}

export function TopHeader({
  projectName = "Default Workspace",
  isLeftOpen = true,
  onToggleLeft,
  onShare
}: TopHeaderProps) {
  const { user, fetchProfile } = useAuthStore();
  const { toggleProjectCenter, autoExecuteStrategy, toggleAutoExecute } = useUIStore();

  // 定时轮询刷新用户信息（包括算力余额）
  useEffect(() => {
    fetchProfile();
    const interval = setInterval(() => {
      fetchProfile();
    }, 15000); // 每15秒刷新一次
    return () => clearInterval(interval);
  }, [fetchProfile]);

  return (
    <header className="h-14 shrink-0 flex items-center justify-between px-4 bg-transparent text-sm z-20">

      {/* 左侧：左侧边栏控制与面包屑导航 */}
      <div className="flex items-center gap-2">
        <button
          onClick={onToggleLeft}
          className={`p-2 rounded-md transition-colors ${
            !isLeftOpen ? 'text-white dark:text-white bg-gray-200 dark:bg-neutral-800' : 'text-gray-600 dark:text-neutral-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800'
          }`}
          title={isLeftOpen ? "Hide left sidebar" : "Show left sidebar"}
        >
          <Menu size={18} />
        </button>

        <div className="hidden md:flex items-center text-gray-500 dark:text-neutral-400">
          <span
            className="hover:text-gray-700 dark:hover:text-white cursor-pointer transition-colors"
            onClick={toggleProjectCenter}
          >
            Projects
          </span>
          <ChevronRight size={16} className="mx-1 opacity-50" />
          <span className="text-gray-900 dark:text-white font-medium">{projectName}</span>
        </div>
      </div>

      {/* 右侧：状态展示 */}
      <div className="flex items-center gap-3">
        {/* ✨ 自动执行开关 - 在 credits 左边 */}
        <button
          onClick={toggleAutoExecute}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-all ${
            autoExecuteStrategy
              ? 'bg-green-100 dark:bg-green-900/30 border border-green-200 dark:border-green-500/30 text-green-700 dark:text-green-400'
              : 'bg-gray-100 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-800 text-gray-600 dark:text-neutral-400'
          }`}
          title={autoExecuteStrategy ? "Auto-execute is ON: Strategies will run automatically" : "Auto-execute is OFF: Click to enable automatic execution"}
        >
          {autoExecuteStrategy ? (
            <>
              <Play size={14} className="fill-current" />
              <span>Auto</span>
            </>
          ) : (
            <>
              <Pause size={14} />
              <span>Manual</span>
            </>
          )}
        </button>

        {user && (
          <div className="hidden md:flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-800 rounded-full text-xs text-gray-600 dark:text-neutral-300">
            <Zap size={14} className="text-yellow-500 fill-yellow-500" />
            <span>{user.credits_balance.toFixed(1)} Credits</span>
          </div>
        )}

        <div className="flex items-center gap-1 border-l border-gray-200 dark:border-neutral-800 pl-3 ml-1">
          <button
            onClick={onShare}
            className="flex items-center gap-2 px-3 py-1.5 text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md transition-colors"
          >
            <Share2 size={16} /> <span className="hidden sm:inline">Get code</span>
          </button>
        </div>
      </div>
    </header>
  );
}
