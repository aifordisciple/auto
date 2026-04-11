"use client";

import { MessageSquare, Folder, Database, Box } from "lucide-react";
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";

/**
 * MobileNav - 移动端底部导航栏
 *
 * 设计原则：
 * - 固定在屏幕底部，仅移动端显示 (md:hidden)
 * - 4 个核心入口：聊天、项目、数据、技能
 * - 使用 safe-area-bottom 适配 iOS 刘海屏
 * - 高对比度图标，触摸友好（44px 最小触摸目标）
 *
 * 行为说明：
 * - 点击导航项时关闭其他打开的面板，避免层级冲突
 * - 当前激活项高亮显示
 */
export function MobileNav() {
  const {
    isProjectCenterOpen,
    isDataCenterOpen,
    isSkillCenterOpen,
    toggleProjectCenter,
    toggleDataCenter,
    toggleSkillCenter,
    closeAllOverlays,
  } = useUIStore();

  const { currentSessionId } = useWorkspaceStore();

  // ✨ 导航项配置
  const navItems = [
    {
      id: "chat",
      label: "聊天",
      icon: MessageSquare,
      // 聊天页面始终存在，点击时关闭所有覆盖层回到聊天
      isActive: !isProjectCenterOpen && !isDataCenterOpen && !isSkillCenterOpen,
      onClick: () => closeAllOverlays(),
    },
    {
      id: "project",
      label: "项目",
      icon: Folder,
      isActive: isProjectCenterOpen,
      onClick: () => toggleProjectCenter(),
    },
    {
      id: "data",
      label: "数据",
      icon: Database,
      isActive: isDataCenterOpen,
      onClick: () => toggleDataCenter(),
    },
    {
      id: "skill",
      label: "技能",
      icon: Box,
      isActive: isSkillCenterOpen,
      onClick: () => toggleSkillCenter(),
    },
  ];

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 md:hidden
        bg-neutral-900/95 backdrop-blur-lg border-t border-neutral-800
        safe-area-bottom"
    >
      <div className="flex items-center justify-around h-14 px-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={item.onClick}
              className={`
                flex flex-col items-center justify-center
                w-16 h-14 rounded-lg transition-all duration-200
                ${item.isActive
                  ? "text-blue-400"
                  : "text-neutral-500 hover:text-neutral-300"
                }
              `}
              aria-label={item.label}
              aria-current={item.isActive ? "page" : undefined}
            >
              <Icon
                size={22}
                strokeWidth={item.isActive ? 2.5 : 2}
                className={item.isActive ? "text-blue-400" : ""}
              />
              <span
                className={`
                  text-[10px] mt-0.5 font-medium
                  ${item.isActive ? "text-blue-400" : "text-neutral-500"}
                `}
              >
                {item.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}