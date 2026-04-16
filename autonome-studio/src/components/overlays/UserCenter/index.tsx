"use client";

import React, { useState } from 'react';
import { useUIStore } from "@/store/useUIStore";
import { X, User, Shield, Keyboard, Wallet } from "lucide-react";
import { ProfilePanel } from './ProfilePanel';
import { SecurityPanel } from './SecurityPanel';
import { ShortcutsPanel } from './ShortcutsPanel';
import { WalletPanel } from './WalletPanel';

// Tab 类型定义
type TabType = 'profile' | 'security' | 'shortcuts' | 'wallet';

// ==========================================
// 主组件：用户中心（统一入口）
// ==========================================
export function UserCenter() {
  const { isUserCenterOpen, closeAllOverlays } = useUIStore();

  // Tab 状态
  const [activeTab, setActiveTab] = useState<TabType>('profile');

  if (!isUserCenterOpen) return null;

  // Tab 配置
  const tabs: { id: TabType; label: string; icon: React.ReactNode; color: string }[] = [
    { id: 'profile', label: '个人资料', icon: <User size={14} />, color: 'blue' },
    { id: 'security', label: '安全设置', icon: <Shield size={14} />, color: 'red' },
    { id: 'wallet', label: '钱包', icon: <Wallet size={14} />, color: 'amber' },
    { id: 'shortcuts', label: '快捷键', icon: <Keyboard size={14} />, color: 'green' },
  ];

  // 获取 Tab 样式
  const getTabStyle = (tab: typeof tabs[0], isActive: boolean) => {
    if (!isActive) return 'text-neutral-400 hover:text-white hover:bg-neutral-800';

    const colorMap: Record<string, string> = {
      blue: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
      red: 'bg-red-500/20 text-red-400 border border-red-500/30',
      purple: 'bg-purple-500/20 text-purple-400 border border-purple-500/30',
      amber: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
      green: 'bg-green-500/20 text-green-400 border border-green-500/30',
    };
    return colorMap[tab.color] || colorMap.blue;
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity"
        onClick={closeAllOverlays}
      />

      {/* 主面板 */}
      <div className="relative w-full h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">

        {/* Header with Tabs */}
        <div className="h-14 shrink-0 border-b border-neutral-800 px-3 md:px-6 flex items-center justify-between bg-neutral-900/40">
          {/* Tab 导航 */}
          <div className="flex items-center gap-1 overflow-x-auto">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3 md:px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${getTabStyle(tab, activeTab === tab.id)}`}
              >
                {tab.icon}
                <span className="hidden md:inline">{tab.label}</span>
              </button>
            ))}
          </div>

          {/* 关闭按钮 */}
          <button
            onClick={closeAllOverlays}
            className="p-2 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-hidden">
          {activeTab === 'profile' && <ProfilePanel />}
          {activeTab === 'security' && <SecurityPanel />}
          {activeTab === 'wallet' && <WalletPanel />}
          {activeTab === 'shortcuts' && <ShortcutsPanel />}
        </div>
      </div>
    </div>
  );
}