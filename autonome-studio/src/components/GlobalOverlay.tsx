"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import dynamic from "next/dynamic";
import { useUIStore } from "../store/useUIStore";
import { useKeyboardShortcut } from "../hooks/useKeyboardShortcut";
import { useEffect } from "react";

import { ShortcutManager } from "./ShortcutManager";

// ✨ 大型面板 - 带 loading fallback
const DataCenter = dynamic(() => import("./overlays/DataCenter").then(m => m.DataCenter), {
  ssr: false,
  loading: () => (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-neutral-900 rounded-xl p-8 flex flex-col items-center gap-4">
        <div className="animate-spin w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full" />
        <span className="text-neutral-400">加载数据中心...</span>
      </div>
    </div>
  ),
});

const SuperExecutorPanel = dynamic(() => import("./overlays/SuperExecutorPanel").then(m => m.SuperExecutorPanel), {
  ssr: false,
  loading: () => (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-neutral-900 rounded-xl p-8 flex flex-col items-center gap-4">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
        <span className="text-neutral-400">加载超级执行器...</span>
      </div>
    </div>
  ),
});

const ClaudeTerminal = dynamic(() => import("./overlays/ClaudeTerminal").then(m => m.ClaudeTerminal), {
  ssr: false,
  loading: () => (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-neutral-900 rounded-xl p-8 flex flex-col items-center gap-4">
        <div className="animate-spin w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full" />
        <span className="text-neutral-400">加载 Claude 终端...</span>
      </div>
    </div>
  ),
});

// ✨ 中型面板 - 简单 loading
const ControlPanel = dynamic(() => import("./overlays/ControlPanel").then(m => m.ControlPanel), { ssr: false });
const ProjectCenter = dynamic(() => import("./overlays/ProjectCenter").then(m => m.ProjectCenter), { ssr: false });
const SettingsCenter = dynamic(() => import("./overlays/SettingsCenter").then(m => m.SettingsCenter), { ssr: false });
const TaskCenter = dynamic(() => import("./overlays/TaskCenter").then(m => m.TaskCenter), { ssr: false });
const TopUpModal = dynamic(() => import("./overlays/TopUpModal").then(m => m.TopUpModal), { ssr: false });
const SkillCenter = dynamic(() => import("./overlays/SkillCenter").then(m => m.SkillCenter), { ssr: false });
const ForgeOverlay = dynamic(() => import("./overlays/ForgeOverlay").then(m => m.ForgeOverlay), { ssr: false });
const PackageManager = dynamic(() => import("./overlays/PackageManager").then(m => m.PackageManager), { ssr: false });
const WebTerminal = dynamic(() => import("./overlays/WebTerminal").then(m => m.WebTerminal), { ssr: false });
const UserCenter = dynamic(() => import("./overlays/UserCenter").then(m => m.UserCenter), { ssr: false });

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
    return null;
  };

  const getTitle = () => {
    if (isProjectCenterOpen) return 'Projects';
    if (isSettingsOpen) return 'Settings';
    if (isTaskCenterOpen) return 'Tasks';
    return '';
  };

  const anyOverlayOpen = isTaskCenterOpen || isSettingsOpen || isProjectCenterOpen;

  return (
    <>
      {/* ✨ 挂载隐形快捷键引擎，只要页面打开它就在后台安静地运行 */}
      <ShortcutManager />

      <ControlPanel />
      <DataCenter />
      <SkillCenter />
      <ForgeOverlay />
      <TopUpModal />
      <PackageManager />
      <SuperExecutorPanel />
      <WebTerminal />
      <ClaudeTerminal />
      <UserCenter />
      
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

            {/* ✨ 移动端全屏，桌面端侧边滑出 */}
            <motion.div
              initial={{ x: "100%", opacity: 0.5 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: "100%", opacity: 0.5 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed top-0 right-0 bottom-0 z-50 w-full md:w-[85vw] md:max-w-6xl bg-neutral-950 md:border-l border-neutral-800 shadow-2xl flex flex-col"
            >
              <div className="h-16 border-b border-neutral-800 flex items-center justify-between px-4 md:px-8 shrink-0">
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
