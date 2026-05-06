"use client";

import { useState, useRef, useEffect } from "react";
import { Menu, ChevronRight, Zap, Download, ChevronDown, Share2, MessageSquare } from "lucide-react";
import { useAuthStore } from "../../store/useAuthStore";
import { useUIStore } from "../../store/useUIStore";
import { Button } from "@/components/ui/Button";

interface TopHeaderProps {
  projectName?: string;
  isLeftOpen?: boolean;
  onToggleLeft?: () => void;
  onExportMarkdown?: () => void;  // 导出对话回调
  chatMode?: 'normal' | 'claude';
  onModeChange?: (mode: 'normal' | 'claude') => void;
}

export function TopHeader({
  projectName = "Default Workspace",
  isLeftOpen = true,
  onToggleLeft,
  onExportMarkdown,
  chatMode = 'normal',
  onModeChange,
}: TopHeaderProps) {
  const { user, fetchProfile } = useAuthStore();
  const { toggleProjectCenter, toggleMobileMenu } = useUIStore();

  // ✨ 下拉菜单状态管理
  const [isToolsMenuOpen, setIsToolsMenuOpen] = useState(false);
  const [isModeMenuOpen, setIsModeMenuOpen] = useState(false);
  const toolsMenuRef = useRef<HTMLDivElement>(null);
  const modeMenuRef = useRef<HTMLDivElement>(null);

  // ✨ 定时轮询刷新用户信息（包括算力余额）
  useEffect(() => {
    fetchProfile();
    const interval = setInterval(() => {
      fetchProfile();
    }, 15000); // 每15秒刷新一次
    return () => clearInterval(interval);
  }, [fetchProfile]);

  // ✨ 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (toolsMenuRef.current && !toolsMenuRef.current.contains(event.target as Node)) {
        setIsToolsMenuOpen(false);
      }
      if (modeMenuRef.current && !modeMenuRef.current.contains(event.target as Node)) {
        setIsModeMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="h-14 shrink-0 flex items-center justify-between px-3 md:px-4 bg-transparent text-sm z-20">

      {/* 左侧：左侧边栏控制与面包屑导航 */}
      <div className="flex items-center gap-2">
        {/* ✨ 移动端汉堡菜单 - 仅移动端显示 */}
        <Button
          variant="icon"
          onClick={toggleMobileMenu}
          className="md:hidden min-h-[44px] min-w-[44px]"
          title="打开菜单"
        >
          <Menu size={20} />
        </Button>

        {/* ✨ 桌面端侧边栏切换按钮 */}
        <Button
          variant="icon"
          onClick={onToggleLeft}
          className={`hidden md:flex p-2 ${!isLeftOpen ? 'text-white dark:text-white bg-gray-200 dark:bg-neutral-800' : ''}`}
          title={isLeftOpen ? "Hide left sidebar" : "Show left sidebar"}
        >
          <Menu size={18} />
        </Button>

        {/* ✨ 移动端项目名显示 */}
        <span
          className="md:hidden text-sm font-medium text-gray-900 dark:text-white truncate max-w-[140px] cursor-pointer"
          onClick={toggleProjectCenter}
        >
          {projectName}
        </span>

        {/* ✨ 桌面端面包屑导航 */}
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
        {/* 模式切换下拉菜单 */}
        <div className="relative" ref={modeMenuRef}>
          <button
            onClick={() => setIsModeMenuOpen(!isModeMenuOpen)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs bg-gray-100 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-800 text-gray-600 dark:text-neutral-400 hover:bg-gray-200 dark:hover:bg-neutral-800 transition-colors"
          >
            <MessageSquare size={14} className={chatMode === 'claude' ? 'text-action' : ''} />
            <span className="hidden sm:inline">{chatMode === 'claude' ? 'Claude 模式' : '常规模式'}</span>
            <ChevronDown size={12} className={`transition-transform ${isModeMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {isModeMenuOpen && (
            <div className="absolute right-0 top-full mt-2 bg-white dark:bg-[#1e1e1f] border border-gray-200 dark:border-neutral-800/80 rounded-xl shadow-2xl overflow-hidden z-50 min-w-[160px]">
              <button
                onClick={() => { onModeChange('normal'); setIsModeMenuOpen(false); }}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-[13px] transition-colors ${
                  chatMode === 'normal'
                    ? 'text-action dark:text-action bg-action/10'
                    : 'text-gray-700 dark:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-800/60'
                }`}
              >
                <MessageSquare size={16} />
                <span>常规模式</span>
              </button>
              <button
                onClick={() => { onModeChange('claude'); setIsModeMenuOpen(false); }}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-[13px] transition-colors ${
                  chatMode === 'claude'
                    ? 'text-action dark:text-action bg-action/10'
                    : 'text-gray-700 dark:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-800/60'
                }`}
              >
                <MessageSquare size={16} className="text-action" />
                <span>Claude 模式</span>
              </button>
            </div>
          )}
        </div>

        {/* ✨ 积分余额 - 响应式显示 */}
        {user && (
          <div className="flex items-center gap-1.5 px-2 md:px-3 py-1.5 bg-gray-100 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-800 rounded-full text-xs text-gray-600 dark:text-neutral-300">
            <Zap size={14} className="text-warning fill-warning shrink-0" />
            {/* ✨ 移动端仅显示数字 */}
            <span className="md:hidden font-medium">{user.credits_balance.toFixed(0)}</span>
            {/* ✨ 桌面端显示完整文本 */}
            <span className="hidden md:inline">{user.credits_balance.toFixed(1)} Credits</span>
          </div>
        )}

        {/* ✨ 分享下拉菜单 */}
        <div className="relative flex items-center gap-1 border-l border-gray-200 dark:border-neutral-800 pl-3 ml-1" ref={toolsMenuRef}>
          {/* ✨ 分享图标按钮 */}
          <button
            onClick={() => setIsToolsMenuOpen(!isToolsMenuOpen)}
            className="flex items-center gap-2 px-3 py-1.5 text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md transition-colors"
            title="分享菜单"
          >
            <Share2 size={16} />
            <ChevronDown size={14} className={`transition-transform ${isToolsMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {/* ✨ 下拉菜单内容 */}
          {isToolsMenuOpen && (
            <div className="absolute right-0 top-full mt-2 bg-white dark:bg-[#1e1e1f] border border-gray-200 dark:border-neutral-800/80 rounded-xl shadow-2xl overflow-hidden z-50 min-w-[160px]">
              {/* ✨ 导出对话选项 */}
              <button
                onClick={() => {
                  setIsToolsMenuOpen(false);
                  onExportMarkdown?.();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 text-[13px] text-gray-700 dark:text-neutral-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800/60 transition-colors"
              >
                <Download size={16} className="shrink-0" />
                <span>导出对话</span>
              </button>

              {/* ✨ 后续可扩展其他分享功能 */}
              {/* <button className="w-full flex items-center gap-2.5 px-3 py-2.5 text-[13px] ...">
                <AnotherIcon size={16} />
                <span>其他分享</span>
              </button> */}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
