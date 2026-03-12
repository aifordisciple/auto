"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { useUIStore } from "../store/useUIStore";
import { useKeyboardShortcut } from "../hooks/useKeyboardShortcut";
import { useEffect } from "react";

import { ControlPanel } from "./overlays/ControlPanel";
import { ProjectCenter } from "./overlays/ProjectCenter";
import { SettingsCenter } from "./overlays/SettingsCenter";
import { TaskCenter } from "./overlays/TaskCenter";
import { TopUpModal } from "./overlays/TopUpModal";
import { DataCenter } from "./overlays/DataCenter";
import { SkillCenter } from "./overlays/SkillCenter";
import { ShortcutManager } from "./ShortcutManager";

export function GlobalOverlay() {
  const { isTaskCenterOpen, isSettingsOpen, isProjectCenterOpen, isControlPanelOpen, isDataCenterOpen, closeAllOverlays, theme } = useUIStore();

  // ✨ 主题切换引擎：监听 theme 变化并同步到 HTML 根节点
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [theme]);

  // ✨ 初始化主题（在组件挂载时执行一次）
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, []);

  useKeyboardShortcut("Escape", () => {
    closeAllOverlays();
  });

  const renderContent = () => {
    if (isProjectCenterOpen) return <ProjectCenter />;
    if (isSettingsOpen) return <SettingsCenter />;
    if (isTaskCenterOpen) return <TaskCenter />;
    if (isControlPanelOpen) return <ControlPanel />;
    return null;
  };

  const getTitle = () => {
    if (isProjectCenterOpen) return 'Projects';
    if (isSettingsOpen) return 'Settings';
    if (isTaskCenterOpen) return 'Tasks';
    if (isControlPanelOpen) return 'Control Panel';
    return '';
  };

  const anyOverlayOpen = isTaskCenterOpen || isSettingsOpen || isProjectCenterOpen || isControlPanelOpen;

  return (
    <>
      {/* ✨ 挂载隐形快捷键引擎，只要页面打开它就在后台安静地运行 */}
      <ShortcutManager />

      <ControlPanel />
      <DataCenter />
      <SkillCenter />
      <TopUpModal />
      
      <AnimatePresence>
        {anyOverlayOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={closeAllOverlays}
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm cursor-pointer"
            />

            <motion.div
              initial={{ x: "100%", opacity: 0.5 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: "100%", opacity: 0.5 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed top-0 right-0 bottom-0 z-50 w-[85vw] max-w-6xl bg-neutral-950 border-l border-neutral-800 shadow-2xl flex flex-col"
            >
              <div className="h-16 border-b border-neutral-800 flex items-center justify-between px-8 shrink-0">
                <h2 className="text-lg font-semibold text-white tracking-wide uppercase">
                  {getTitle()}
                </h2>
                <button 
                  onClick={closeAllOverlays}
                  className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-md transition-colors"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="flex-1 overflow-hidden">
                {renderContent()}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
