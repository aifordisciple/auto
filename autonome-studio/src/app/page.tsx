/**
 * Autonome Studio 主页面（性能优化版）
 *
 * 性能优化：
 * 1. 合并多个 useEffect，减少不必要的副作用
 * 2. 项目名称使用 sessionStorage 缓存
 * 3. 使用 BASE_URL 替代硬编码 IP
 * 4. Overlay 面板懒加载
 * 5. ChatStage 懒加载（骨架屏）
 */
"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { Sidebar } from "../components/layout/Sidebar";
import { TopHeader } from "../components/layout/TopHeader";
import { useAuthStore } from "../store/useAuthStore";
import { useWorkspaceStore } from "../store/useWorkspaceStore";
import { useUIStore } from "../store/useUIStore";
import { useChatStore, Message } from "../store/useChatStore";
import { BASE_URL } from "@/lib/api";

// ✨ ChatStage 懒加载 - 带骨架屏 fallback
const ChatStage = dynamic(() => import("../components/chat/ChatStage").then(m => m.ChatStage), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex flex-col">
      {/* 骨架消息列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-neutral-300 dark:bg-neutral-700 animate-pulse" />
            <div className="flex-1 space-y-2">
              <div className="h-4 bg-neutral-300 dark:bg-neutral-700 rounded w-3/4 animate-pulse" />
              <div className="h-4 bg-neutral-200 dark:bg-neutral-800 rounded w-1/2 animate-pulse" />
            </div>
          </div>
        ))}
      </div>
      {/* 骨架输入框 */}
      <div className="p-4 border-t border-neutral-200 dark:border-neutral-800">
        <div className="h-12 bg-neutral-200 dark:bg-neutral-800 rounded-xl animate-pulse" />
      </div>
    </div>
  ),
});

// ✨ 延迟加载 overlay 和移动端组件（减少首屏 JS bundle）
const GlobalOverlay = dynamic(() => import("../components/GlobalOverlay").then(m => m.GlobalOverlay), {
  ssr: false,
  loading: () => null,
});

const MobileNav = dynamic(() => import("../components/mobile/MobileNav").then(m => m.MobileNav), {
  ssr: false,
  loading: () => <div className="md:hidden h-16" />,
});

const MobileSidebarSheet = dynamic(() => import("../components/mobile/MobileSidebarSheet").then(m => m.MobileSidebarSheet), {
  ssr: false,
  loading: () => null,
});

// 全局快捷键系统导入
import { useKeyboardShortcuts, GLOBAL_SHORTCUTS } from "@/lib/KeyboardShortcuts";

// ==========================================
// 项目名称缓存工具
// ==========================================
const PROJECT_NAME_CACHE_KEY = 'autonome_project_name_cache';
const CACHE_EXPIRY_MS = 60 * 60 * 1000; // 1 小时

interface ProjectNameCache {
  [projectId: string]: {
    name: string;
    timestamp: number;
  };
}

function getCachedProjectName(projectId: string): string | null {
  try {
    const cacheStr = sessionStorage.getItem(PROJECT_NAME_CACHE_KEY);
    if (!cacheStr) return null;

    const cache: ProjectNameCache = JSON.parse(cacheStr);
    const entry = cache[projectId];

    if (!entry) return null;

    // 检查是否过期
    if (Date.now() - entry.timestamp > CACHE_EXPIRY_MS) {
      return null;
    }

    return entry.name;
  } catch {
    return null;
  }
}

function setCachedProjectName(projectId: string, name: string): void {
  try {
    const cacheStr = sessionStorage.getItem(PROJECT_NAME_CACHE_KEY);
    const cache: ProjectNameCache = cacheStr ? JSON.parse(cacheStr) : {};

    cache[projectId] = {
      name,
      timestamp: Date.now(),
    };

    sessionStorage.setItem(PROJECT_NAME_CACHE_KEY, JSON.stringify(cache));
  } catch {
    // 忽略存储错误
  }
}

// ==========================================
// SearchParams 处理组件
// ==========================================
function SearchParamsHandler() {
  const searchParams = useSearchParams();
  const openSkillCenter = useUIStore(state => state.openSkillCenter);

  useEffect(() => {
    const openParam = searchParams.get('open');

    if (openParam === 'skill-center') {
      openSkillCenter();
    }
  }, [searchParams, openSkillCenter]);

  return <></>;
}

// ==========================================
// 性能计时
// ==========================================
const PERF = {
  start: performance.now(),
  mark: (name: string) => {
    const elapsed = (performance.now() - PERF.start).toFixed(1);
    console.log(`[PERF] ${name}: ${elapsed}ms`);
  }
};

// ==========================================
// 主组件
// ==========================================
export default function AutonomeStudio() {
  // ✨ 记录组件挂载时间
  useEffect(() => {
    PERF.mark("Component mounted");
  }, []);

  // 状态订阅 - 使用精确订阅
  const token = useAuthStore(state => state.token);
  const currentProjectId = useWorkspaceStore(state => state.currentProjectId);
  const currentSessionId = useWorkspaceStore(state => state.currentSessionId);
  const setCurrentSessionId = useWorkspaceStore(state => state.setCurrentSessionId);
  const toggleProjectCenter = useUIStore(state => state.toggleProjectCenter);
  const openSkillCenter = useUIStore(state => state.openSkillCenter);
  const messages = useChatStore(state => state.messages);

  // 本地状态
  const [mounted, setMounted] = useState(false);
  const [projectName, setProjectName] = useState<string>("加载中...");
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(true);

  // ==========================================
  // 全局快捷键处理
  // ==========================================
  const shortcutHandlers = {
    'focus-search': useCallback(() => {
      const inputEl = document.getElementById("chat-input-box");
      if (inputEl) inputEl.focus();
    }, []),
    'open-command-palette': openSkillCenter,
    'open-skill-center': openSkillCenter,
    'execute-task': useCallback(() => {
      const sendButton = document.querySelector('[data-send-button]') as HTMLButtonElement;
      if (sendButton) sendButton.click();
    }, []),
    'close-modal': useCallback(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    }, []),
    'new-chat': useCallback(() => {
      console.log('[Shortcut] New chat');
    }, []),
    'open-history': useCallback(() => {
      console.log('[Shortcut] Open history');
    }, []),
    'show-shortcuts-help': useCallback(() => {
      console.log('[Shortcut] Show shortcuts help');
    }, []),
  };

  useKeyboardShortcuts(GLOBAL_SHORTCUTS, shortcutHandlers);

  // ==========================================
  // 导出对话到 Markdown
  // ==========================================
  const exportToMarkdown = useCallback(() => {
    if (messages.length === 0) {
      alert('当前没有对话内容可导出');
      return;
    }

    const formatTime = (timestamp: number): string => {
      const date = new Date(timestamp);
      const hours = date.getHours().toString().padStart(2, '0');
      const minutes = date.getMinutes().toString().padStart(2, '0');
      return `${hours}:${minutes}`;
    };

    const today = new Date();
    const dateStr = `${today.getFullYear()}-${(today.getMonth() + 1).toString().padStart(2, '0')}-${today.getDate().toString().padStart(2, '0')}`;

    let markdown = `# 对话记录 - ${dateStr}\n\n`;
    markdown += `> 导出时间: ${formatTime(Date.now())}\n\n`;
    markdown += `---\n\n`;

    messages.forEach((msg: Message) => {
      const role = msg.role === 'user' ? '用户' : 'AI';
      const time = formatTime(msg.timestamp);
      markdown += `## ${role} (${time})\n\n`;
      markdown += `${msg.content}\n\n`;
      markdown += `---\n\n`;
    });

    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `conversation-${dateStr}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [messages]);

  // ==========================================
  // 获取项目名称（带缓存）
  // ==========================================
  const fetchProjectName = useCallback(async (projectId: string) => {
    // 先检查缓存
    const cachedName = getCachedProjectName(projectId);
    if (cachedName) {
      setProjectName(cachedName);
      return;
    }

    const localToken = localStorage.getItem('autonome_access_token');
    if (!localToken) return;

    try {
      const res = await fetch(`${BASE_URL}/api/projects/${projectId}`, {
        headers: { 'Authorization': `Bearer ${localToken}` }
      });
      const data = await res.json();

      if (data.status === 'success' && data.data) {
        const name = data.data.name;
        setProjectName(name);
        setCachedProjectName(projectId, name);
      } else {
        const shortId = projectId.split('_')[1]?.substring(0, 6) || projectId;
        setProjectName(`Project ${shortId}`);
      }
    } catch {
      const shortId = projectId.split('_')[1]?.substring(0, 6) || projectId;
      setProjectName(`Project ${shortId}`);
    }
  }, []);

  // ==========================================
  // 合并的初始化 useEffect
  // ==========================================
  useEffect(() => {
    PERF.mark("useEffect start");

    setMounted(true);

    const localToken = localStorage.getItem('autonome_access_token');
    PERF.mark("Token checked");
    if (!localToken) {
      window.location.href = '/login';
      return;
    }

    // 如果有项目 ID，获取项目名称
    if (currentProjectId) {
      fetchProjectName(currentProjectId);
    } else {
      setProjectName("请在项目中心选择工作区");
      // 没有选中的项目，自动打开项目中心
      toggleProjectCenter();
    }
    PERF.mark("Init complete - UI interactive");
  }, [currentProjectId, fetchProjectName, toggleProjectCenter]);

  // ==========================================
  // 项目切换时更新名称
  // ==========================================
  useEffect(() => {
    if (currentProjectId) {
      fetchProjectName(currentProjectId);
    } else {
      setProjectName("请在项目中心选择工作区");
    }
  }, [currentProjectId, fetchProjectName]);

  // ==========================================
  // 侧栏切换事件监听
  // ==========================================
  useEffect(() => {
    const handleToggleLeft = () => setIsLeftSidebarOpen(p => !p);
    window.addEventListener('shortcut-toggle-left-sidebar', handleToggleLeft);
    return () => window.removeEventListener('shortcut-toggle-left-sidebar', handleToggleLeft);
  }, []);

  // ==========================================
  // 会话选择处理
  // ==========================================
  const handleSelectSession = useCallback((id: string | null, title?: string | null) => {
    setCurrentSessionId(id, title);
  }, [setCurrentSessionId]);

  // ==========================================
  // 渲染
  // ==========================================
  return (
    <main className="h-screen w-full bg-white dark:bg-[#131314] flex overflow-hidden font-sans transition-colors">
      <Suspense fallback={null}>
        <SearchParamsHandler />
      </Suspense>
      <GlobalOverlay />

      {/* 移动端侧边栏抽屉 */}
      <MobileSidebarSheet />

      {/* 左侧边栏 */}
      {isLeftSidebarOpen && (
        <div className="w-56 shrink-0 border-r border-gray-200 dark:border-[#2d2d30] bg-gray-50 dark:bg-[#1e1e20] flex flex-col z-20 hidden md:flex">
          <Sidebar />
        </div>
      )}

      {/* 主工作区 */}
      <div className="flex-1 flex flex-col overflow-hidden pb-16 md:pb-0">
        <TopHeader
          projectName={projectName}
          isLeftOpen={isLeftSidebarOpen}
          onToggleLeft={() => setIsLeftSidebarOpen(!isLeftSidebarOpen)}
          onExportMarkdown={exportToMarkdown}
        />

        {/* 聊天主容器 */}
        <div className="flex-1 overflow-hidden w-full relative">
          <ChatStage />
        </div>
      </div>

      {/* 移动端底部导航栏 */}
      <MobileNav />
    </main>
  );
}