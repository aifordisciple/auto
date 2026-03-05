"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { useUIStore } from "../store/useUIStore";
import { useKeyboardShortcut } from "../hooks/useKeyboardShortcut";

// ✨ 引入我们刚刚拆分好的业务组件
import { ControlPanel } from "./overlays/ControlPanel";
import { ProjectCenter } from "./overlays/ProjectCenter";
import { SettingsCenter } from "./overlays/SettingsCenter";
import { TaskCenter } from "./overlays/TaskCenter";
import { TopUpModal } from "./overlays/TopUpModal";

export function GlobalOverlay() {
  const { activeOverlay, closeOverlay } = useUIStore();

  // ✨ ESC 关闭弹窗 - 只有当有弹窗打开时才响应
  useKeyboardShortcut("Escape", () => {
    if (activeOverlay !== 'none') {
      closeOverlay();
    }
  });

  // 极其清爽的视图分发器
  const renderContent = () => {
    switch (activeOverlay) {
      case 'control': return <ControlPanel />;
      case 'projects': return <ProjectCenter />;
      case 'settings': return <SettingsCenter />;
      case 'tasks': return <TaskCenter />;
      default: return null;
    }
  };

  return (
    <>
      {/* TopUpModal - 独立居中的模态框 */}
      <TopUpModal 
        isOpen={activeOverlay === 'topup'} 
        onClose={() => useUIStore.getState().closeOverlay()} 
      />
      
      <AnimatePresence>
        {activeOverlay !== 'none' && activeOverlay !== 'topup' && (
          <>
            {/* 背景模糊遮罩 */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={closeOverlay}
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm cursor-pointer"
            />

            {/* 侧滑主面板外壳 */}
            <motion.div
              initial={{ x: "-100%", opacity: 0.5 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: "-100%", opacity: 0.5 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="fixed top-0 left-0 bottom-0 z-50 w-[85vw] max-w-6xl bg-neutral-950 border-r border-neutral-800 shadow-2xl flex flex-col"
            >
              {/* 全局统一的顶栏和关闭按钮 */}
              <div className="h-16 border-b border-neutral-800 flex items-center justify-between px-8 shrink-0">
                <h2 className="text-lg font-semibold text-white tracking-wide uppercase">
                  {activeOverlay}
                </h2>
                <button 
                  onClick={closeOverlay}
                  className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-md transition-colors"
                >
                  <X size={20} />
                </button>
              </div>

              {/* 动态挂载内部业务组件 */}
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
