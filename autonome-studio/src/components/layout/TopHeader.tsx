"use client";

import { useEffect } from "react";
import { Menu, ChevronRight, Share2, Settings, Zap, PanelRightClose, PanelLeftClose } from "lucide-react";
import { useAuthStore } from "../../store/useAuthStore";
import { useUIStore } from "../../store/useUIStore";

interface TopHeaderProps {
  projectName?: string;
  isLeftOpen?: boolean;
  isRightOpen?: boolean;
  onToggleLeft?: () => void;
  onToggleRight?: () => void;
  onShare?: () => void;
}

export function TopHeader({ 
  projectName = "Default Workspace", 
  isLeftOpen = true,
  isRightOpen = true,
  onToggleLeft,
  onToggleRight,
  onShare 
}: TopHeaderProps) {
  const { user, fetchProfile } = useAuthStore();
  const { toggleProjectCenter } = useUIStore();

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
            !isLeftOpen ? 'text-white bg-neutral-800' : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
          }`}
          title={isLeftOpen ? "Hide left sidebar" : "Show left sidebar"}
        >
          <Menu size={18} />
        </button>
        
        <div className="hidden md:flex items-center text-neutral-400">
          <span
            className="hover:text-white cursor-pointer transition-colors"
            onClick={toggleProjectCenter}
          >
            Projects
          </span>
          <ChevronRight size={16} className="mx-1 opacity-50" />
          <span className="text-white font-medium">{projectName}</span>
        </div>
      </div>

      {/* 右侧：状态展示与右侧边栏控制 */}
      <div className="flex items-center gap-3">
        {user && (
          <div className="hidden md:flex items-center gap-1.5 px-3 py-1.5 bg-neutral-900 border border-neutral-800 rounded-full text-xs text-neutral-300">
            <Zap size={14} className="text-yellow-500 fill-yellow-500" />
            <span>{user.credits_balance.toFixed(1)} Credits</span>
          </div>
        )}

        <div className="flex items-center gap-1 border-l border-neutral-800 pl-3 ml-1">
          <button 
            onClick={onShare}
            className="flex items-center gap-2 px-3 py-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-md transition-colors"
          >
            <Share2 size={16} /> <span className="hidden sm:inline">Get code</span>
          </button>
          
          <button 
            onClick={onToggleRight}
            className={`p-2 rounded-md transition-colors ${
              isRightOpen ? 'text-white bg-neutral-800' : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
            }`}
            title={isRightOpen ? "Hide right sidebar" : "Show right sidebar"}
          >
            <Settings size={18} />
          </button>
        </div>
      </div>
    </header>
  );
}
