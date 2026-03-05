"use client";

import { useState, useEffect } from "react";
import { Plus, MessageSquare, Trash2, Edit2, Check, X } from "lucide-react";
import { BASE_URL } from "@/lib/api";

interface Session {
  id: number;
  title: string;
  created_at: string;
}

interface SessionSidebarProps {
  projectId: number;
  currentSessionId: number | null;
  onSelectSession: (id: number | null) => void;
}

export function SessionSidebar({ projectId, currentSessionId, onSelectSession }: SessionSidebarProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const fetchSessions = async () => {
    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/projects/${projectId}/sessions`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSessions(data.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch sessions:', e);
    }
  };

  useEffect(() => {
    if (projectId) {
      fetchSessions();
    }
  }, [projectId]);

  useEffect(() => {
    const handleRefresh = () => fetchSessions();
    window.addEventListener('refresh-sessions', handleRefresh);
    return () => window.removeEventListener('refresh-sessions', handleRefresh);
  }, []);

  const handleNewChat = () => {
    onSelectSession(null);
  };

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (!confirm("确定要删除这个对话吗？")) return;
    
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
    const token = localStorage.getItem('autonome_access_token');
    try {
      await fetch(`${BASE_URL}/api/chat/sessions/${id}`, {
        method: "PUT",
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ title: editTitle })
      });
      setEditingId(null);
      fetchSessions();
    } catch (e) {
      console.error('Failed to rename session:', e);
    }
  };

  const handleAutoName = async (sessionId: number) => {
    const token = localStorage.getItem('autonome_access_token');
    try {
      await fetch(`${BASE_URL}/api/chat/sessions/${sessionId}/auto-name`, {
        method: "POST",
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchSessions();
      window.dispatchEvent(new Event('refresh-sessions'));
    } catch (e) {
      console.error('Failed to auto-name session:', e);
    }
  };

  return (
    <div className="flex flex-col h-full w-full">
      <div className="p-3">
        <button 
          onClick={handleNewChat}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors font-medium text-sm"
        >
          <Plus size={16} /> 新建对话
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        <p className="px-3 py-2 text-xs font-semibold text-neutral-500 uppercase tracking-wider">
          Active Workspace
        </p>
        
        {sessions.map((session) => {
          const isActive = currentSessionId === session.id;
          
          return (
            <div 
              key={session.id}
              onClick={() => onSelectSession(session.id)}
              className={`group flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                isActive ? 'bg-[#1e1e1f] text-white shadow-sm' : 'hover:bg-neutral-800/50 text-neutral-400 hover:text-neutral-200'
              }`}
            >
              {editingId === session.id ? (
                <div className="flex items-center gap-2 w-full" onClick={e => e.stopPropagation()}>
                  <input 
                    autoFocus
                    value={editTitle}
                    onChange={e => setEditTitle(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleRename(session.id)}
                    className="flex-1 bg-neutral-900 border border-indigo-500 text-sm px-2 py-1 rounded text-white outline-none"
                  />
                  <Check size={14} className="text-emerald-500 cursor-pointer" onClick={() => handleRename(session.id)} />
                  <X size={14} className="text-neutral-500 cursor-pointer" onClick={() => setEditingId(null)} />
                </div>
              ) : (
                <>
                  <div className="flex items-center gap-3 truncate w-[80%]">
                    <MessageSquare size={16} className={isActive ? "text-indigo-400 shrink-0" : "text-neutral-500 shrink-0"} />
                    <span className="text-sm truncate font-medium">{session.title}</span>
                  </div>
                  
                  <div className={`flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity ${isActive ? 'opacity-100' : ''}`}>
                    <Edit2 size={14} className="text-neutral-500 hover:text-white" onClick={(e) => {
                      e.stopPropagation();
                      setEditTitle(session.title);
                      setEditingId(session.id);
                    }}/>
                    <Trash2 size={14} className="text-neutral-500 hover:text-rose-400" onClick={(e) => handleDelete(e, session.id)} />
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export { handleAutoName };
