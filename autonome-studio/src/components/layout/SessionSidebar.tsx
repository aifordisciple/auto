"use client";

import { useState, useEffect, useMemo } from "react";
import { SquarePen, Trash2, Edit2, MessageSquare, Search, X, Tag, Plus, Bookmark, Loader2 } from "lucide-react";
import { BASE_URL } from "@/lib/api";
import { useChatStore } from "@/store/useChatStore";

interface Session {
  id: string;
  title: string;
  created_at: string;
}

interface SessionSidebarProps {
  projectId: string;
  currentSessionId: string | null;
  onSelectSession: (id: string | null, title?: string | null) => void;
}

export function SessionSidebar({ projectId, currentSessionId, onSelectSession }: SessionSidebarProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  // 从 store 获取搜索和标签状态
  const {
    searchQuery, setSearchQuery, searchResults, setSearchResults, isSearching, setIsSearching,
    tags, setTags, selectedTagId, setSelectedTagId, showBookmarkPanel, setShowBookmarkPanel
  } = useChatStore();

  // 获取会话列表
  const fetchSessions = async () => {
    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/projects/${projectId}/sessions`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        const sessionList = data.data || [];
        setSessions(sessionList);

        if (!currentSessionId && sessionList.length > 0) {
          onSelectSession(sessionList[0].id, sessionList[0].title);
        }
      }
    } catch (e) {
      console.error('Failed to fetch sessions:', e);
    }
  };

  // 获取标签列表
  const fetchTags = async () => {
    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/tags`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setTags(data.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch tags:', e);
    }
  };

  // 搜索对话
  const handleSearch = async (query: string) => {
    setSearchQuery(query);
    if (!query || query.length < 2) {
      setSearchResults([]);
      return;
    }

    setIsSearching(true);
    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ query, project_id: projectId })
      });
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.results || []);
      }
    } catch (e) {
      console.error('Search failed:', e);
    } finally {
      setIsSearching(false);
    }
  };

  // 按标签筛选会话
  const fetchSessionsByTag = async (tagId: number) => {
    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/projects/${projectId}/sessions/tagged/${tagId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSessions(data.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch tagged sessions:', e);
    }
  };

  useEffect(() => {
    if (projectId) {
      fetchSessions();
      fetchTags();
    }
  }, [projectId]);

  useEffect(() => {
    const handleRefresh = () => fetchSessions();
    window.addEventListener('refresh-sessions', handleRefresh);
    return () => window.removeEventListener('refresh-sessions', handleRefresh);
  }, [projectId]);

  // Time-based grouping
  const groupedSessions = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const sevenDaysAgo = new Date(today);
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const groups: Record<string, Session[]> = {
      "Today": [],
      "Previous 7 Days": [],
      "Older": []
    };

    sessions.forEach(session => {
      const date = new Date(session.created_at + (session.created_at.endsWith('Z') ? '' : 'Z'));
      if (date >= today) {
        groups["Today"].push(session);
      } else if (date >= sevenDaysAgo) {
        groups["Previous 7 Days"].push(session);
      } else {
        groups["Older"].push(session);
      }
    });

    return groups;
  }, [sessions]);

  const handleNewChat = () => onSelectSession(null);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this chat?")) return;

    const token = localStorage.getItem('autonome_access_token');
    try {
      await fetch(`${BASE_URL}/api/chat/sessions/${id}`, {
        method: "DELETE",
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchSessions();
      if (currentSessionId === id) handleNewChat();
    } catch (e) {
      console.error('Failed to delete session:', e);
    }
  };

  const handleRename = async (id: string) => {
    if (!editTitle.trim()) {
      setEditingId(null);
      return;
    }
    const token = localStorage.getItem('autonome_access_token');
    try {
      await fetch(`${BASE_URL}/api/chat/sessions/${id}`, {
        method: "PUT",
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ title: editTitle.trim() })
      });
      setEditingId(null);
      fetchSessions();
    } catch (e) {
      console.error('Failed to rename session:', e);
    }
  };

  const handleTagClick = (tagId: number | null) => {
    setSelectedTagId(tagId);
    if (tagId === null) {
      fetchSessions();
    } else {
      fetchSessionsByTag(tagId);
    }
  };

  const renderSessionItem = (session: Session) => {
    const isActive = currentSessionId === session.id;

    return (
      <div
        key={session.id}
        onClick={() => onSelectSession(session.id, session.title)}
        className={`group relative flex items-center justify-between px-2 py-1.5 mx-2 rounded-md cursor-pointer transition-all duration-200 ${
          isActive
            ? 'bg-gray-200 dark:bg-neutral-800/40 text-gray-800 dark:text-neutral-200'
            : 'text-gray-500 dark:text-neutral-400 hover:bg-gray-100 dark:hover:bg-neutral-800/20 hover:text-gray-700 dark:hover:text-neutral-300'
        }`}
      >
        {isActive && (
          <div className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-blue-500 dark:bg-neutral-400 rounded-r-full" />
        )}

        {editingId === session.id ? (
          <div className="flex items-center gap-2 w-full pl-1" onClick={e => e.stopPropagation()}>
            <input
              autoFocus
              value={editTitle}
              onChange={e => setEditTitle(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleRename(session.id);
                if (e.key === 'Escape') setEditingId(null);
              }}
              onBlur={() => setEditingId(null)}
              className="flex-1 bg-transparent border-b border-gray-300 dark:border-neutral-600 text-[13px] px-0.5 py-0.5 text-gray-800 dark:text-neutral-200 outline-none focus:border-blue-500 dark:focus:border-neutral-400 transition-colors"
            />
          </div>
        ) : (
          <>
            <div className="flex-1 truncate pl-1 text-[13px] leading-relaxed">
              {session.title}
            </div>

            <div className={`flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity ${isActive ? 'bg-gray-200 dark:bg-neutral-800/40' : 'bg-gray-50 dark:bg-[#121212] group-hover:bg-gray-100 dark:group-hover:bg-neutral-800/20'} pl-2`}>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setEditTitle(session.title);
                  setEditingId(session.id);
                }}
                className="p-1 text-gray-400 dark:text-neutral-500 hover:text-gray-600 dark:hover:text-neutral-300 transition-colors"
              >
                <Edit2 size={13} strokeWidth={1.5} />
              </button>
              <button
                onClick={(e) => handleDelete(e, session.id)}
                className="p-1 text-gray-400 dark:text-neutral-500 hover:text-rose-500 dark:hover:text-rose-400/80 transition-colors"
              >
                <Trash2 size={13} strokeWidth={1.5} />
              </button>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full w-full bg-transparent">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 group">
        <span className="text-sm font-medium text-gray-700 dark:text-neutral-300">Chats</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowBookmarkPanel(!showBookmarkPanel)}
            title="收藏夹"
            className={`p-1.5 rounded-md transition-all ${showBookmarkPanel ? 'text-blue-500 bg-blue-500/10' : 'text-gray-400 dark:text-neutral-500 hover:text-gray-600 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-800/50'}`}
          >
            <Bookmark size={15} strokeWidth={1.5} />
          </button>
          <button
            onClick={handleNewChat}
            title="New Chat (⌘N)"
            className="p-1.5 text-gray-400 dark:text-neutral-500 hover:text-gray-600 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-800/50 rounded-md transition-all flex items-center gap-1"
          >
            <SquarePen size={15} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {/* 搜索框 */}
      <div className="px-3 mb-2">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-neutral-500" />
          <input
            type="text"
            placeholder="搜索对话..."
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full pl-8 pr-8 py-1.5 text-[13px] bg-gray-100 dark:bg-neutral-800/60 border border-gray-200 dark:border-neutral-700/50 rounded-md text-gray-800 dark:text-neutral-200 placeholder-gray-400 dark:placeholder-neutral-500 outline-none focus:border-blue-500 dark:focus:border-neutral-600 transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => {
                setSearchQuery('');
                setSearchResults([]);
                fetchSessions();
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-neutral-300"
            >
              <X size={14} />
            </button>
          )}
          {isSearching && (
            <Loader2 size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-blue-500 animate-spin" />
          )}
        </div>
      </div>

      {/* 标签筛选 */}
      {tags.length > 0 && (
        <div className="px-3 mb-2">
          <div className="flex items-center gap-1 flex-wrap">
            <button
              onClick={() => handleTagClick(null)}
              className={`px-2 py-0.5 text-[11px] rounded-full transition-all ${
                selectedTagId === null
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-100 dark:bg-neutral-800 text-gray-600 dark:text-neutral-400 hover:bg-gray-200 dark:hover:bg-neutral-700'
              }`}
            >
              全部
            </button>
            {tags.map(tag => (
              <button
                key={tag.id}
                onClick={() => handleTagClick(tag.id)}
                className={`px-2 py-0.5 text-[11px] rounded-full transition-all flex items-center gap-1 ${
                  selectedTagId === tag.id
                    ? 'text-white'
                    : 'text-gray-600 dark:text-neutral-400 hover:bg-gray-200 dark:hover:bg-neutral-700'
                }`}
                style={{
                  backgroundColor: selectedTagId === tag.id ? tag.color : undefined
                }}
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: tag.color }}
                />
                {tag.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 搜索结果 */}
      {searchQuery && searchResults.length > 0 && (
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          <div className="text-[11px] text-gray-400 dark:text-neutral-500 px-2 py-1">
            找到 {searchResults.length} 个相关对话
          </div>
          {searchResults.map(result => (
            <div
              key={result.session_id}
              onClick={() => {
                onSelectSession(result.session_id, result.session_title);
                setSearchQuery('');
                setSearchResults([]);
              }}
              className="px-2 py-2 mb-1 rounded-md cursor-pointer hover:bg-gray-100 dark:hover:bg-neutral-800/40 border border-gray-200 dark:border-neutral-700/50"
            >
              <div className="text-[13px] font-medium text-gray-700 dark:text-neutral-300 truncate">
                {result.session_title}
              </div>
              {result.matched_messages.slice(0, 2).map((msg, idx) => (
                <div key={idx} className="text-[11px] text-gray-500 dark:text-neutral-400 mt-1 line-clamp-2">
                  {msg.highlight}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* 会话列表 */}
      {(!searchQuery || searchResults.length === 0) && (
        <div className="flex-1 overflow-y-auto pb-4 scroll-smooth">
          {Object.entries(groupedSessions).map(([groupName, groupSessions]) => {
            if (groupSessions.length === 0) return null;

            return (
              <div key={groupName} className="mb-4">
                <div className="px-4 py-1.5 text-[11px] font-semibold text-gray-400 dark:text-neutral-500 uppercase tracking-wider sticky top-0 bg-white dark:bg-[#121212]/95 backdrop-blur-sm z-10">
                  {groupName}
                </div>

                <div className="space-y-0.5 mt-1">
                  {groupSessions.map(renderSessionItem)}
                </div>
              </div>
            );
          })}

          {sessions.length === 0 && (
            <div className="px-4 py-10 flex flex-col items-center justify-center text-center gap-3">
              <div className="w-10 h-10 rounded-full bg-gray-100 dark:bg-neutral-800/50 flex items-center justify-center text-gray-400 dark:text-neutral-500 mb-1">
                <MessageSquare size={18} strokeWidth={1.5} />
              </div>
              <p className="text-[13px] text-gray-400 dark:text-neutral-500">暂无历史对话</p>
              <button
                onClick={handleNewChat}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-200 dark:bg-neutral-800 hover:bg-gray-300 dark:hover:bg-neutral-700 text-gray-700 dark:text-neutral-300 hover:text-gray-900 dark:hover:text-white text-[12px] rounded-md transition-all shadow-sm border border-gray-300 dark:border-neutral-700/50 hover:border-gray-400 dark:hover:border-neutral-600"
              >
                <SquarePen size={13} strokeWidth={1.5} />
                开启新对话
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}