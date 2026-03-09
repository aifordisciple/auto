"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "../components/layout/Sidebar";
import { SessionSidebar } from "../components/layout/SessionSidebar";
import { TopHeader } from "../components/layout/TopHeader";
import { ChatStage } from "../components/chat/ChatStage";
import { GlobalOverlay } from "../components/GlobalOverlay";
import { useAuthStore } from "../store/useAuthStore";
import { useWorkspaceStore } from "../store/useWorkspaceStore";
import { useUIStore } from "../store/useUIStore";

export default function AutonomeStudio() {
  const { token, user } = useAuthStore();
  const { currentProjectId, setCurrentProjectId, currentSessionId, setCurrentSessionId } = useWorkspaceStore();
  const { toggleProjectCenter } = useUIStore();
  const [mounted, setMounted] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState<string>("加载中...");

  // 左侧边栏开关状态
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(true);

  // 监听侧栏切换事件（由 ShortcutManager 分发）
  useEffect(() => {
    const handleToggleLeft = () => setIsLeftSidebarOpen(p => !p);

    window.addEventListener('shortcut-toggle-left-sidebar', handleToggleLeft);

    return () => {
      window.removeEventListener('shortcut-toggle-left-sidebar', handleToggleLeft);
    };
  }, []);

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
      // 没有选中的项目，自动打开项目中心让用户选择
      toggleProjectCenter();
    } else {
      setProjectId(currentId);
      setCurrentProjectId(currentId);

      // ✨ 获取真实项目名称
      const localToken = localStorage.getItem('autonome_access_token');
      fetch(`http://113.44.66.210:8000/api/projects/${currentId}`, {
        headers: { 'Authorization': `Bearer ${localToken}` }
      })
        .then(res => res.json())
        .then(data => {
          if (data.status === 'success' && data.data) {
            setProjectName(data.data.name);
          } else {
            const shortId = currentId.split('_')[1]?.substring(0, 6) || currentId;
            setProjectName(`Project ${shortId}`);
          }
        })
        .catch(() => {
          const shortId = currentId.split('_')[1]?.substring(0, 6) || currentId;
          setProjectName(`Project ${shortId}`);
        });
    }
  }, []);

  const handleSelectSession = (id: string | null, title?: string | null) => {
    setCurrentSessionId(id, title);
  };

  // ✨ 当项目切换时更新顶部名称
  useEffect(() => {
    if (!currentProjectId) {
      setProjectName("请在项目中心选择工作区");
      return;
    }

    const fetchProjectName = async () => {
      const localToken = localStorage.getItem('autonome_access_token');
      try {
        const res = await fetch(`http://113.44.66.210:8000/api/projects/${currentProjectId}`, {
          headers: { 'Authorization': `Bearer ${localToken}` }
        });
        const data = await res.json();
        if (data.status === 'success' && data.data) {
          setProjectName(data.data.name);
        } else {
          const shortId = currentProjectId.split('_')[1]?.substring(0, 6) || currentProjectId;
          setProjectName(`Project ${shortId}`);
        }
      } catch {
        const shortId = currentProjectId.split('_')[1]?.substring(0, 6) || currentProjectId;
        setProjectName(`Project ${shortId}`);
      }
    };

    fetchProjectName();
  }, [currentProjectId]);

  // 当没有项目时，仍然渲染布局，项目中心会通过 GlobalOverlay 显示
  // if (!projectId) {
  //   return <div className="h-screen bg-[#131314]" />;
  // }

  return (
    <main className="h-screen w-full bg-white dark:bg-[#131314] flex overflow-hidden font-sans transition-colors">
      <GlobalOverlay />

      {/* 左侧边栏 - 根据 isLeftSidebarOpen 条件渲染 */}
      {isLeftSidebarOpen && (
        <div className="w-56 shrink-0 border-r border-gray-200 dark:border-[#2d2d30] bg-gray-50 dark:bg-[#1e1e20] flex flex-col z-20 hidden md:flex">
          <Sidebar />
        </div>
      )}

      {/* 主工作区 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 顶栏 */}
        <TopHeader
          projectName={projectName}
          isLeftOpen={isLeftSidebarOpen}
          onToggleLeft={() => setIsLeftSidebarOpen(!isLeftSidebarOpen)}
          onShare={() => {}}
        />

        {/* 聊天主容器 */}
        <div className="flex-1 overflow-hidden w-full relative">
          <ChatStage />
        </div>
      </div>
    </main>
  );
}
