"use client";

import { useState, ReactNode } from 'react';
import { useUIStore } from "@/store/useUIStore";
import { useAuthStore } from "@/store/useAuthStore";
import { X, User, Shield, Keyboard, Wallet, Bot, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ProfilePanel } from './ProfilePanel';
import { SecurityPanel } from './SecurityPanel';
import { ShortcutsPanel } from './ShortcutsPanel';
import { WalletPanel } from './WalletPanel';
import { AIModelPanel } from './AIModelPanel';
import { RbacPanel } from './RbacPanel';

// Tab 类型定义
type TabType = 'profile' | 'security' | 'ai-model' | 'wallet' | 'shortcuts' | 'rbac';

// ==========================================
// 主组件：用户中心（统一入口）
// ==========================================
export function UserCenter() {
  const { isUserCenterOpen, closeAllOverlays } = useUIStore();
  const { user } = useAuthStore();

  // Tab 状态
  const [activeTab, setActiveTab] = useState<TabType>('profile');

  if (!isUserCenterOpen) return null;

  // Tab 配置（管理员额外显示 RBAC Tab）
  const tabs: { id: TabType; label: string; icon: ReactNode; color: string }[] = [
    { id: 'profile', label: '个人资料', icon: <User size={14} />, color: 'blue' },
    { id: 'security', label: '安全设置', icon: <Shield size={14} />, color: 'red' },
    { id: 'ai-model', label: 'AI 模型', icon: <Bot size={14} />, color: 'purple' },
    { id: 'wallet', label: '钱包', icon: <Wallet size={14} />, color: 'amber' },
    { id: 'shortcuts', label: '快捷键', icon: <Keyboard size={14} />, color: 'green' },
    ...(user?.is_superuser ? [{ id: 'rbac' as TabType, label: 'RBAC', icon: <ShieldCheck size={14} />, color: 'orange' }] : []),
  ];

  // 获取 Tab 样式
  const getTabStyle = (tab: typeof tabs[0], isActive: boolean) => {
    if (!isActive) return 'text-neutral-400 hover:text-white hover:bg-neutral-800';

    const colorMap: Record<string, string> = {
      blue: 'bg-action/20 text-action border border-action/30',
      red: 'bg-danger/20 text-danger border border-danger/30',
      purple: 'bg-data/20 text-data border border-data/30',
      amber: 'bg-warning/20 text-warning border border-warning/30',
      green: 'bg-success/20 text-success border border-success/30',
      orange: 'bg-warning/20 text-warning border border-warning/30',
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
      <div className="relative w-full md:w-panel-xl md:max-w-panel h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">

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
          <Button variant="icon" onClick={closeAllOverlays} aria-label="关闭">
            <X size={20} />
          </Button>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-hidden">
          {activeTab === 'profile' && <ProfilePanel />}
          {activeTab === 'security' && <SecurityPanel />}
          {activeTab === 'ai-model' && <AIModelPanel />}
          {activeTab === 'wallet' && <WalletPanel />}
          {activeTab === 'shortcuts' && <ShortcutsPanel />}
          {activeTab === 'rbac' && <RbacPanel />}
        </div>
      </div>
    </div>
  );
}