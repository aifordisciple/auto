"use client";

import { useState, useEffect, useMemo } from "react";
import { SquarePen, Trash2, Edit2, MessageSquare } from "lucide-react";
import { BASE_URL } from "@/lib/api";

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

  useEffect(() => {
    if (projectId) fetchSessions();
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

  const handleDelete = async (e: React.MouseEvent, id: number) => {
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

  const handleRename = async (id: number) => {
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

  const renderSessionItem = (session: Session) => {
    const isActive = currentSessionId === session.id;

    return (
      <div 
        key={session.id}
        onClick={() => onSelectSession(session.id, session.title)}
        className={`group relative flex items-center justify-between px-2 py-1.5 mx-2 rounded-md cursor-pointer transition-all duration-200 ${
          isActive 
            ? 'bg-neutral-800/40 text-neutral-200' 
            : 'text-neutral-400 hover:bg-neutral-800/20 hover:text-neutral-300'
        }`}
      >
        {isActive && (
          <div className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-neutral-400 rounded-r-full" />
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
              className="flex-1 bg-transparent border-b border-neutral-600 text-[13px] px-0.5 py-0.5 text-neutral-200 outline-none focus:border-neutral-400 transition-colors"
            />
          </div>
        ) : (
          <>
            <div className="flex-1 truncate pl-1 text-[13px] leading-relaxed">
              {session.title}
            </div>
            
            <div className={`flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity ${isActive ? 'bg-neutral-800/40' : 'bg-[#121212] group-hover:bg-neutral-800/20'} pl-2`}>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  setEditTitle(session.title);
                  setEditingId(session.id);
                }}
                className="p-1 text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                <Edit2 size={13} strokeWidth={1.5} />
              </button>
              <button 
                onClick={(e) => handleDelete(e, session.id)}
                className="p-1 text-neutral-500 hover:text-rose-400/80 transition-colors"
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
        <span className="text-sm font-medium text-neutral-300">Chats</span>
        <button 
          onClick={handleNewChat}
          title="New Chat (⌘N)"
          className="p-1.5 text-neutral-500 hover:text-neutral-200 hover:bg-neutral-800/50 rounded-md transition-all flex items-center gap-1"
        >
          <SquarePen size={15} strokeWidth={1.5} />
        </button>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto pb-4 scroll-smooth">
        {Object.entries(groupedSessions).map(([groupName, groupSessions]) => {
          if (groupSessions.length === 0) return null;
          
          return (
            <div key={groupName} className="mb-4">
              <div className="px-4 py-1.5 text-[11px] font-semibold text-neutral-500 uppercase tracking-wider sticky top-0 bg-[#121212]/95 backdrop-blur-sm z-10">
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
            <div className="w-10 h-10 rounded-full bg-neutral-800/50 flex items-center justify-center text-neutral-500 mb-1">
              <MessageSquare size={18} strokeWidth={1.5} />
            </div>
            <p className="text-[13px] text-neutral-500">暂无历史对话</p>
            <button 
              onClick={handleNewChat}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 hover:text-white text-[12px] rounded-md transition-all shadow-sm border border-neutral-700/50 hover:border-neutral-600"
            >
              <SquarePen size={13} strokeWidth={1.5} />
              开启新对话
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
