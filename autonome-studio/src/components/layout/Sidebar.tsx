"use client";

import { useState, useRef, useEffect } from "react";
import { LogOut, ShieldAlert, Activity, FolderGit2, ListTodo, ChevronUp, Sparkles, HardDrive, Sun, Moon, Box, Terminal, UserCircle, BookOpen } from "lucide-react";
import dynamic from "next/dynamic";
import { useUIStore } from "../../store/useUIStore";
import { useAuthStore } from "../../store/useAuthStore";
import { useWorkspaceStore } from "../../store/useWorkspaceStore";
import { removeToken } from "@/lib/api";

// ✨ 延迟加载会话管理组件
const SessionSidebar = dynamic(() => import("./SessionSidebar").then(m => m.SessionSidebar), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex flex-col px-2 py-3 gap-2">
      <div className="animate-pulse h-8 w-20 bg-gray-200 dark:bg-gray-700 rounded" />
      <div className="animate-pulse h-10 bg-gray-100 dark:bg-gray-800 rounded" />
      <div className="animate-pulse h-10 bg-gray-100 dark:bg-gray-800 rounded" />
      <div className="animate-pulse h-10 bg-gray-100 dark:bg-gray-800 rounded" />
    </div>
  ),
});

const BookmarkPanel = dynamic(() => import("../chat/BookmarkPanel").then(m => m.BookmarkPanel), {
  ssr: false,
  loading: () => null,
});

export function Sidebar() {
  const { toggleControlPanel, toggleProjectCenter, toggleDataCenter, toggleTaskCenter, toggleSkillCenter, toggleTerminal, toggleLearningCenter, openUserCenter, isProjectCenterOpen, isDataCenterOpen, isSkillCenterOpen, isLearningCenterOpen, theme, toggleTheme } = useUIStore();
  const { user, logout } = useAuthStore();
  const { currentProjectId, currentSessionId, setCurrentSessionId } = useWorkspaceStore();

  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = () => {
    removeToken();
    localStorage.removeItem('autonome_current_project_id');
    logout();
    window.location.href = '/login';
  }

  return (
    <div className="flex flex-col h-full w-full">
      {/* Logo */}
      <div
        className="h-14 shrink-0 flex items-center px-4 border-b border-gray-200 dark:border-neutral-800 cursor-pointer"
        onClick={() => window.location.href = '/'}
      >
        <div className="flex items-center gap-2 text-gray-900 dark:text-white font-bold tracking-wider">
          <span className="text-blue-500">🧬</span> AUTONOME
        </div>
      </div>

      {/* Navigation */}
      <div className="p-3 space-y-1 text-sm text-gray-500 dark:text-neutral-400 mt-2">
        {/* Control Panel */}
        <div
          onClick={() => toggleControlPanel()}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-gray-100 dark:hover:bg-neutral-800/50 hover:text-gray-900 dark:hover:text-white"
        >
          <Activity size={18} /> <span>控制面板</span>
        </div>

        {/* Projects */}
        <div
          onClick={() => toggleProjectCenter()}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-gray-100 dark:hover:bg-neutral-800/50 hover:text-gray-900 dark:hover:text-white"
        >
          <FolderGit2 size={18} /> <span>项目中心</span>
        </div>

        {/* Task Center */}
        <div
          onClick={() => toggleTaskCenter()}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-gray-100 dark:hover:bg-neutral-800/50 hover:text-gray-900 dark:hover:text-white"
        >
          <ListTodo size={18} /> <span>任务中心</span>
        </div>

        {/* Data Center */}
        <div
          onClick={toggleDataCenter}
          className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors ${isDataCenterOpen ? 'bg-purple-600 text-white' : 'hover:bg-gray-100 dark:hover:bg-neutral-800/50 hover:text-gray-900 dark:hover:text-white'}`}
        >
          <HardDrive size={18} /> <span>数据中心</span>
        </div>

        {/* ✨ Skill Center - 技能兵器库 */}
        <div
          onClick={toggleSkillCenter}
          className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors ${isSkillCenterOpen ? 'bg-blue-600 text-white' : 'hover:bg-gray-100 dark:hover:bg-neutral-800/50 hover:text-gray-900 dark:hover:text-white'}`}
        >
          <Box size={18} /> <span>技能中心</span>
        </div>

        {/* ✨ Learning Center - 学习中心 */}
        <div
          onClick={toggleLearningCenter}
          className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors ${isLearningCenterOpen ? 'bg-emerald-600 text-white' : 'hover:bg-gray-100 dark:hover:bg-neutral-800/50 hover:text-gray-900 dark:hover:text-white'}`}
        >
          <BookOpen size={18} /> <span>学习中心</span>
        </div>

        {/* ✨ Web Terminal - 终端 */}
        <div
          onClick={toggleTerminal}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-gray-100 dark:hover:bg-neutral-800/50 hover:text-gray-900 dark:hover:text-white"
        >
          <Terminal size={18} /> <span>终端</span>
        </div>
      </div>

      {/* Session Management - under Project Center */}
      <div className="flex-1 overflow-hidden flex flex-col border-t border-gray-200 dark:border-neutral-800 mt-2">
        {currentProjectId ? (
          <SessionSidebar
            projectId={currentProjectId}
            currentSessionId={currentSessionId}
            onSelectSession={setCurrentSessionId}
          />
        ) : (
          <div className="px-4 py-4 text-center text-xs text-gray-400 dark:text-neutral-500">
            请先选择项目
          </div>
        )}
      </div>
      
      {/* ========================================== */}
      {/* ⬇️ 最底部：极简悬浮胶囊 (Capsule Footer) */}
      {/* ========================================== */}
      <div className="relative p-3 mt-auto shrink-0" ref={menuRef}>
        
        {/* ✨ 弹出菜单 (Popover Menu) */}
        {isUserMenuOpen && (
          <div className="absolute bottom-full left-3 right-3 mb-2 bg-white dark:bg-[#1e1e1f] border border-gray-200 dark:border-neutral-800/80 rounded-xl shadow-2xl overflow-hidden animate-in fade-in slide-in-from-bottom-1 duration-200 z-50">
            {/* 账号显示区 */}
            <div className="px-3 py-2.5 border-b border-gray-100 dark:border-neutral-800 bg-gray-50 dark:bg-neutral-900/50">
              <p className="text-[11px] font-medium text-gray-500 dark:text-neutral-400 truncate">
                {user?.email || 'user@autonome.ai'}
              </p>
            </div>

            {/* 菜单操作区 */}
            <div className="p-1">
              {/* ✨ 用户中心 - 主入口（替代原设置中心） */}
              <button
                onClick={() => { openUserCenter(); setIsUserMenuOpen(false); }}
                className="w-full flex items-center gap-2.5 px-2 py-1.5 text-[13px] text-gray-700 dark:text-neutral-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800/60 rounded-lg transition-colors"
              >
                <UserCircle size={14} className="text-blue-400" />
                用户中心
              </button>

              {/* ✨ 切换主题按钮 */}
              <button
                onClick={() => { toggleTheme(); setIsUserMenuOpen(false); }}
                className="w-full flex items-center justify-between px-2 py-1.5 text-[13px] text-gray-700 dark:text-neutral-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800/60 rounded-lg transition-colors"
              >
                <div className="flex items-center gap-2.5">
                  {theme === 'dark' ? <Moon size={14} className="text-purple-400" /> : <Sun size={14} className="text-amber-400" />}
                  <span>主题模式</span>
                </div>
                <span className="text-[10px] font-mono text-gray-400 dark:text-neutral-500 bg-gray-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded">
                  {theme === 'dark' ? 'Dark' : 'Light'}
                </span>
              </button>

              {user?.is_superuser && (
                <button
                  onClick={() => { window.location.href = '/admin'; setIsUserMenuOpen(false); }}
                  className="w-full flex items-center gap-2.5 px-2 py-1.5 text-[13px] text-yellow-500 hover:text-yellow-400 hover:bg-yellow-500/10 rounded-lg transition-colors"
                >
                  <ShieldAlert size={14} />
                  管理员控制台
                </button>
              )}

              <div className="h-px bg-gray-100 dark:bg-neutral-800/60 my-1 mx-2" />

              <button
                onClick={() => { handleLogout(); setIsUserMenuOpen(false); }}
                className="w-full flex items-center gap-2.5 px-2 py-1.5 text-[13px] text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 rounded-lg transition-colors"
              >
                <LogOut size={14} />
                退出登录
              </button>
            </div>
          </div>
        )}

        {/* ✨ 底部胶囊按钮 (Capsule Button) */}
        <button
          onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
          className={`w-full flex items-center justify-between p-1 pl-1.5 pr-3 rounded-full border transition-all duration-200 ${
            isUserMenuOpen
              ? 'bg-gray-100 dark:bg-neutral-800/80 border-gray-200 dark:border-neutral-700 shadow-inner'
              : 'bg-transparent border-transparent hover:bg-gray-100 dark:hover:bg-neutral-800/40 hover:border-gray-200 dark:hover:border-neutral-800/60'
          }`}
        >
          <div className="flex items-center gap-2 truncate">
            {/* ✨ 无图片渐变头像：高级感拉满 */}
            <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-indigo-500/80 to-purple-500/80 flex items-center justify-center shrink-0 shadow-sm border border-white/5">
              <span className="text-[11px] font-bold text-white leading-none mt-0.5">
                {user?.email?.charAt(0).toUpperCase() || 'A'}
              </span>
            </div>

            {/* 文字信息：极其紧凑的行高 */}
            <div className="flex flex-col items-start truncate pb-0.5">
              <span className="text-[13px] font-medium text-gray-700 dark:text-neutral-200 truncate leading-none mt-0.5">
                {user?.full_name || user?.email?.split('@')[0] || 'Autonome User'}
              </span>
              <span className="text-[10px] text-gray-400 dark:text-neutral-500 flex items-center gap-1 font-mono leading-none mt-1.5">
                <Sparkles size={9} className="text-indigo-400/80" />
                {user?.credits_balance?.toFixed(1) || '0.0'}
              </span>
            </div>
          </div>

          <ChevronUp
            size={14}
            className={`text-gray-400 dark:text-neutral-500 transition-transform duration-200 shrink-0 ${isUserMenuOpen ? 'rotate-180 text-gray-600 dark:text-neutral-300' : ''}`}
          />
        </button>
      </div>

      {/* Bookmark Panel - 收藏夹面板 */}
      {currentProjectId && (
        <BookmarkPanel
          projectId={currentProjectId}
          onSelectSession={setCurrentSessionId}
        />
      )}
    </div>
  );
}
