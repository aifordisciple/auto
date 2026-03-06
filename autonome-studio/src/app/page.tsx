"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "../components/layout/Sidebar";
import { SessionSidebar } from "../components/layout/SessionSidebar";
import { TopHeader } from "../components/layout/TopHeader";
import { ChatStage } from "../components/chat/ChatStage";
import { RightPanel } from "../components/RightPanel";
import { GlobalOverlay } from "../components/GlobalOverlay";
import { useAuthStore } from "../store/useAuthStore";
import { useWorkspaceStore } from "../store/useWorkspaceStore";
import { Panel, Group, Separator } from "react-resizable-panels";
import { useKeyboardShortcut } from "../hooks/useKeyboardShortcut";

export default function AutonomeStudio() {
  const { token, user } = useAuthStore();
  const { currentProjectId, setCurrentProjectId, currentSessionId, setCurrentSessionId } = useWorkspaceStore();
  const [mounted, setMounted] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  
  // 左右侧边栏开关状态
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(true);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(true);

  // 键盘快捷键
  useKeyboardShortcut({ key: "b", ctrl: true }, () => setIsLeftSidebarOpen(p => !p));
  useKeyboardShortcut({ key: "b", meta: true }, () => setIsLeftSidebarOpen(p => !p));
  useKeyboardShortcut({ key: "j", ctrl: true }, () => setIsRightSidebarOpen(p => !p));
  useKeyboardShortcut({ key: "j", meta: true }, () => setIsRightSidebarOpen(p => !p));
  useKeyboardShortcut({ key: "Escape", shift: true }, () => window.location.href = '/dashboard');

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const localToken = localStorage.getItem('autonome_access_token');
    if (!localToken) {
      window.location.href = '/login';
      return;
    }
    
    const currentId = localStorage.getItem('autonome_current_project_id');
    if (!currentId) {
      window.location.href = '/dashboard';
    } else {
      setProjectId(currentId);
      setCurrentProjectId(parseInt(currentId));
    }
  }, []);

  const handleSelectSession = (id: number | null, title?: string | null) => {
    setCurrentSessionId(id, title);
  };

  if (!projectId) {
    return <div className="h-screen bg-[#131314]" />;
  }

  return (
    <main className="h-screen w-full bg-neutral-950 flex overflow-hidden font-sans">
      <GlobalOverlay />
      
      {/* 左侧边栏 - 根据 isLeftSidebarOpen 条件渲染 */}
      {isLeftSidebarOpen && (
        <div className="w-56 shrink-0 border-r border-neutral-800 bg-neutral-950 flex flex-col z-20 hidden md:flex">
          <Sidebar />
        </div>
      )}

      {/* 主工作区 */}
      <div className="flex-1 flex overflow-hidden">
        <Group orientation="horizontal">
          
          {/* 中栏：聊天主舞台 */}
          <Panel defaultSize={isRightSidebarOpen ? 80 : 100} minSize={40} className="flex flex-col bg-[#131314]">
            
            {/* 顶栏 */}
            <TopHeader 
              projectName={`Workspace Project #${projectId}`} 
              isLeftOpen={isLeftSidebarOpen}
              isRightOpen={isRightSidebarOpen}
              onToggleLeft={() => setIsLeftSidebarOpen(!isLeftSidebarOpen)}
              onToggleRight={() => setIsRightSidebarOpen(!isRightSidebarOpen)}
              onShare={() => {}} 
            />
            
            {/* 聊天主容器 */}
            <div className="flex-1 overflow-hidden w-full relative">
              <ChatStage />
            </div>
            
          </Panel>
          
          {/* 右侧边栏与分隔条 - 根据 isRightSidebarOpen 条件渲染 */}
          {isRightSidebarOpen && (
            <>
              <Separator className="w-1 bg-neutral-800/50 hover:bg-blue-500/50 transition-colors cursor-col-resize" />
              
              <Panel defaultSize={20} minSize={15} className="bg-neutral-950 border-l border-neutral-800 flex flex-col">
                <RightPanel />
              </Panel>
            </>
          )}
          
        </Group>
      </div>
    </main>
  );
}
