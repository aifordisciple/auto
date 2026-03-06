"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { useUIStore } from "../store/useUIStore";
import { useKeyboardShortcut } from "../hooks/useKeyboardShortcut";

import { ControlPanel } from "./overlays/ControlPanel";
import { ProjectCenter } from "./overlays/ProjectCenter";
import { SettingsCenter } from "./overlays/SettingsCenter";
import { TaskCenter } from "./overlays/TaskCenter";
import { TopUpModal } from "./overlays/TopUpModal";
import { DataCenter } from "./overlays/DataCenter";

export function GlobalOverlay() {
  const { isTaskCenterOpen, isSettingsOpen, isProjectCenterOpen, closeAllOverlays } = useUIStore();

  useKeyboardShortcut("Escape", () => {
    closeAllOverlays();
  });

  const anyOverlayOpen = isTaskCenterOpen || isSettingsOpen || isProjectCenterOpen;

  const renderContent = () => {
    if (isProjectCenterOpen) return <ProjectCenter />;
    if (isSettingsOpen) return <SettingsCenter />;
    if (isTaskCenterOpen) return <TaskCenter />;
    return null;
  };

  return (
    <>
      <TopUpModal />
      <DataCenter />
      
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
                  {isProjectCenterOpen ? 'Projects' : isSettingsOpen ? 'Settings' : 'Tasks'}
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
