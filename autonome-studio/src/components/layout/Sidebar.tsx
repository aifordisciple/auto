"use client";

import { useState, useRef, useEffect } from "react";
import { LayoutDashboard, Settings, Zap, LogOut, ShieldAlert, Activity, FolderGit2, ListTodo, ChevronUp, Sparkles, CreditCard, HardDrive } from "lucide-react";
import { useUIStore } from "../../store/useUIStore";
import { useAuthStore } from "../../store/useAuthStore";
import { useWorkspaceStore } from "../../store/useWorkspaceStore";
import { SessionSidebar } from "./SessionSidebar";

export function Sidebar() {
  const { toggleControlPanel, toggleProjectCenter, toggleDataCenter, toggleTaskCenter, toggleSettings, isProjectCenterOpen, isDataCenterOpen } = useUIStore();
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
    localStorage.removeItem('autonome_access_token');
    localStorage.removeItem('autonome_current_project_id');
    logout();
    window.location.href = '/login';
  }

  return (
    <div className="flex flex-col h-full w-full">
      {/* Logo */}
      <div 
        className="h-14 shrink-0 flex items-center px-4 border-b border-neutral-800 cursor-pointer"
        onClick={() => window.location.href = '/'}
      >
        <div className="flex items-center gap-2 text-white font-bold tracking-wider">
          <span className="text-blue-500">🧬</span> AUTONOME
        </div>
      </div>

      {/* Navigation */}
      <div className="p-3 space-y-1 text-sm text-neutral-400 mt-2">
        {/* Dashboard */}
        <div 
          onClick={() => window.location.href = '/dashboard'} 
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <LayoutDashboard size={18} /> <span>Projects Dashboard</span>
        </div>

        {/* Control Panel */}
        <div 
          onClick={() => toggleControlPanel()}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <Activity size={18} /> <span>控制面板</span>
        </div>
        
        {/* Task Center */}
        <div 
          onClick={() => toggleTaskCenter()}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <ListTodo size={18} /> <span>任务中心</span>
        </div>
        
        {/* Projects */}
        <div 
          onClick={() => toggleProjectCenter()}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <FolderGit2 size={18} /> <span>项目中心</span>
        </div>

        {/* Data Center */}
        <div 
          onClick={toggleDataCenter}
          className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors ${isDataCenterOpen ? 'bg-purple-600 text-white' : 'hover:bg-neutral-800/50 hover:text-white'}`}
        >
          <HardDrive size={18} /> <span>数据中心</span>
        </div>
      </div>

      {/* Session Management - under Project Center */}
      <div className="flex-1 overflow-hidden flex flex-col border-t border-neutral-800 mt-2">
        {currentProjectId ? (
          <SessionSidebar 
            projectId={currentProjectId}
            currentSessionId={currentSessionId}
            onSelectSession={setCurrentSessionId}
          />
        ) : (
          <div className="px-4 py-4 text-center text-xs text-neutral-500">
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
          <div className="absolute bottom-full left-3 right-3 mb-2 bg-[#1e1e1f] border border-neutral-800/80 rounded-xl shadow-2xl overflow-hidden animate-in fade-in slide-in-from-bottom-1 duration-200 z-50">
            {/* 账号显示区 */}
            <div className="px-3 py-2.5 border-b border-neutral-800 bg-neutral-900/50">
              <p className="text-[11px] font-medium text-neutral-400 truncate">
                {user?.email || 'user@autonome.ai'}
              </p>
            </div>
            
            {/* 菜单操作区 */}
            <div className="p-1">
              <button 
                onClick={() => { toggleSettings(); setIsUserMenuOpen(false); }}
                className="w-full flex items-center gap-2.5 px-2 py-1.5 text-[13px] text-neutral-300 hover:text-white hover:bg-neutral-800/60 rounded-lg transition-colors"
              >
                <Settings size={14} className="text-neutral-400" /> 
                设置中心
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
              
              <button 
                onClick={() => { toggleSettings(); setIsUserMenuOpen(false); }}
                className="w-full flex items-center gap-2.5 px-2 py-1.5 text-[13px] text-neutral-300 hover:text-white hover:bg-neutral-800/60 rounded-lg transition-colors"
              >
                <CreditCard size={14} className="text-neutral-400" /> 
                算力充值
              </button>
              
              <div className="h-px bg-neutral-800/60 my-1 mx-2" />
              
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
              ? 'bg-neutral-800/80 border-neutral-700 shadow-inner' 
              : 'bg-transparent border-transparent hover:bg-neutral-800/40 hover:border-neutral-800/60'
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
              <span className="text-[13px] font-medium text-neutral-200 truncate leading-none mt-0.5">
                {user?.full_name || user?.email?.split('@')[0] || 'Autonome User'}
              </span>
              <span className="text-[10px] text-neutral-500 flex items-center gap-1 font-mono leading-none mt-1.5">
                <Sparkles size={9} className="text-indigo-400/80" />
                {user?.credits_balance?.toFixed(1) || '0.0'}
              </span>
            </div>
          </div>
          
          <ChevronUp 
            size={14} 
            className={`text-neutral-500 transition-transform duration-200 shrink-0 ${isUserMenuOpen ? 'rotate-180 text-neutral-300' : ''}`} 
          />
        </button>
      </div>
    </div>
  );
}
