"use client";

import { useState } from "react";
import { LayoutDashboard, Code2, Settings, Zap, LogOut, ShieldAlert, Activity, FolderGit2, ListTodo } from "lucide-react";
import { useUIStore } from "../../store/useUIStore";
import { useAuthStore } from "../../store/useAuthStore";

export function Sidebar() {
  const { setActiveOverlay } = useUIStore();
  const { user, logout } = useAuthStore();

  const handleLogout = () => {
    localStorage.removeItem('autonome_access_token');
    localStorage.removeItem('autonome_current_project_id');
    logout();
    window.location.href = '/login';
  }

  return (
    <>
      {/* Logo */}
      <div 
        className="h-14 shrink-0 flex items-center px-4 border-b border-neutral-800 cursor-pointer"
        onClick={() => window.location.href = '/'}
      >
        <div className="flex items-center gap-2 text-white font-bold tracking-wider">
          <span className="text-blue-500">🧬</span> AUTONOME
        </div>
      </div>

      {/* User info & Credits */}
      {user && (
        <div className="p-4 border-b border-neutral-800 bg-neutral-900/50">
          <div className="text-xs text-neutral-500 mb-1 truncate">{user.email}</div>
          <div className="flex items-center justify-between mt-2">
             <div className="flex items-center gap-1 text-yellow-400 font-mono text-sm bg-yellow-400/10 px-2 py-1 rounded border border-yellow-400/20">
               <Zap size={14} className="fill-yellow-400" /> {user.credits_balance.toFixed(1)}
             </div>
             <span className="text-[10px] text-neutral-500 uppercase">Credits</span>
          </div>
        </div>
      )}
      
      {/* Navigation */}
      <div className="flex-1 p-3 space-y-1 text-sm text-neutral-400 mt-2">
        {/* Dashboard */}
        <div 
          onClick={() => window.location.href = '/dashboard'} 
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <LayoutDashboard size={18} /> <span>Projects Dashboard</span>
        </div>
        
        {/* Workspace */}
        <div 
          onClick={() => window.location.href = '/'} 
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <Code2 size={18} /> <span>Active Workspace</span>
        </div>

        {/* Divider */}
        <div className="h-px bg-neutral-800 my-3"></div>

        {/* Control Panel */}
        <div 
          onClick={() => setActiveOverlay('control')}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <Activity size={18} /> <span>控制面板</span>
        </div>
        
        {/* Task Center */}
        <div 
          onClick={() => setActiveOverlay('tasks')}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <ListTodo size={18} /> <span>任务中心</span>
        </div>
        
        {/* Projects */}
        <div 
          onClick={() => setActiveOverlay('projects')}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <FolderGit2 size={18} /> <span>项目中心</span>
        </div>
      </div>
      
      {/* Bottom section */}
      <div className="p-3 border-t border-neutral-800 text-sm text-neutral-400 shrink-0 space-y-1">
        {/* Admin */}
        {user?.is_superuser && (
          <div 
            onClick={() => window.location.href = '/admin'} 
            className="flex items-center gap-3 p-2.5 bg-yellow-900/20 text-yellow-500 hover:bg-yellow-900/40 rounded-lg cursor-pointer transition-colors"
          >
            <ShieldAlert size={18} /> <span className="font-bold">管理员控制台</span>
          </div>
        )}
        
        <div 
          onClick={() => setActiveOverlay('settings')}
          className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-neutral-800/50 hover:text-white"
        >
          <Settings size={18} /> <span>设置</span>
        </div>
        <div onClick={handleLogout} className="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors hover:bg-red-950 hover:text-red-400">
          <LogOut size={18} /> <span>安全登出</span>
        </div>
      </div>
    </>
  );
}
