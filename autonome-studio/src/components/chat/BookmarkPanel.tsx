"use client";

import { useState, useEffect } from "react";
import { Bookmark, X, ExternalLink, Trash2, Edit2, Loader2 } from "lucide-react";
import { BASE_URL } from "@/lib/api";
import { useChatStore } from "@/store/useChatStore";

interface BookmarkItem {
  bookmark_id: number;
  message_id: string;
  session_id: string;
  session_title: string;
  project_id: string;
  content: string;
  note: string | null;
  created_at: string;
}

interface BookmarkPanelProps {
  projectId: string;
  onSelectSession: (sessionId: string, title?: string) => void;
}

export function BookmarkPanel({ projectId, onSelectSession }: BookmarkPanelProps) {
  const { showBookmarkPanel, setShowBookmarkPanel } = useChatStore();
  const [bookmarks, setBookmarks] = useState<BookmarkItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editNote, setEditNote] = useState("");

  const fetchBookmarks = async () => {
    setIsLoading(true);
    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/bookmarks?project_id=${projectId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setBookmarks(data.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch bookmarks:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (showBookmarkPanel && projectId) {
      fetchBookmarks();
    }
  }, [showBookmarkPanel, projectId]);

  const handleDelete = async (bookmarkId: number, messageId: string) => {
    if (!confirm("确定要取消收藏吗？")) return;

    const token = localStorage.getItem('autonome_access_token');
    try {
      await fetch(`${BASE_URL}/api/chat/messages/${messageId}/bookmark`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      setBookmarks(prev => prev.filter(b => b.bookmark_id !== bookmarkId));
    } catch (e) {
      console.error('Failed to delete bookmark:', e);
    }
  };

  const handleUpdateNote = async (bookmarkId: number) => {
    const token = localStorage.getItem('autonome_access_token');
    try {
      await fetch(`${BASE_URL}/api/chat/bookmarks/${bookmarkId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ note: editNote })
      });
      setBookmarks(prev => prev.map(b =>
        b.bookmark_id === bookmarkId ? { ...b, note: editNote } : b
      ));
      setEditingId(null);
    } catch (e) {
      console.error('Failed to update note:', e);
    }
  };

  const handleNavigate = (sessionId: string, title: string) => {
    onSelectSession(sessionId, title);
    setShowBookmarkPanel(false);
  };

  if (!showBookmarkPanel) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30 dark:bg-black/50"
        onClick={() => setShowBookmarkPanel(false)}
      />

      {/* Panel */}
      <div className="absolute right-0 top-0 bottom-0 w-80 bg-white dark:bg-[#1a1a1a] border-l border-gray-200 dark:border-neutral-800 shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-neutral-800">
          <div className="flex items-center gap-2">
            <Bookmark size={16} className="text-blue-500" />
            <span className="text-sm font-medium text-gray-700 dark:text-neutral-200">收藏夹</span>
          </div>
          <button
            onClick={() => setShowBookmarkPanel(false)}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-neutral-300 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-3">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={24} className="text-blue-500 animate-spin" />
            </div>
          ) : bookmarks.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-gray-400 dark:text-neutral-500">
              <Bookmark size={32} className="mb-2 opacity-50" />
              <p className="text-sm">暂无收藏</p>
              <p className="text-xs mt-1">悬停在消息上点击收藏按钮</p>
            </div>
          ) : (
            <div className="space-y-2">
              {bookmarks.map(bookmark => (
                <div
                  key={bookmark.bookmark_id}
                  className="p-3 rounded-lg border border-gray-200 dark:border-neutral-700/50 bg-gray-50 dark:bg-neutral-800/30 group"
                >
                  {/* Session title and navigate */}
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-blue-500 truncate flex-1">
                      {bookmark.session_title}
                    </span>
                    <button
                      onClick={() => handleNavigate(bookmark.session_id, bookmark.session_title)}
                      className="p-1 text-gray-400 hover:text-blue-500 transition-colors opacity-0 group-hover:opacity-100"
                      title="跳转到对话"
                    >
                      <ExternalLink size={14} />
                    </button>
                  </div>

                  {/* Content preview */}
                  <p className="text-xs text-gray-600 dark:text-neutral-400 line-clamp-3 mb-2">
                    {bookmark.content}
                  </p>

                  {/* Note */}
                  {editingId === bookmark.bookmark_id ? (
                    <div className="flex items-center gap-2">
                      <input
                        autoFocus
                        value={editNote}
                        onChange={e => setEditNote(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') handleUpdateNote(bookmark.bookmark_id);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        placeholder="添加笔记..."
                        className="flex-1 text-xs px-2 py-1 bg-transparent border border-gray-300 dark:border-neutral-600 rounded text-gray-700 dark:text-neutral-300 outline-none focus:border-blue-500"
                      />
                      <button
                        onClick={() => handleUpdateNote(bookmark.bookmark_id)}
                        className="text-xs text-blue-500 hover:text-blue-600"
                      >
                        保存
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      {bookmark.note ? (
                        <p className="text-xs text-gray-500 dark:text-neutral-500 italic flex-1">
                          📝 {bookmark.note}
                        </p>
                      ) : (
                        <button
                          onClick={() => {
                            setEditingId(bookmark.bookmark_id);
                            setEditNote("");
                          }}
                          className="text-xs text-gray-400 hover:text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          + 添加笔记
                        </button>
                      )}
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => {
                            setEditingId(bookmark.bookmark_id);
                            setEditNote(bookmark.note || "");
                          }}
                          className="p-1 text-gray-400 hover:text-blue-500"
                          title="编辑笔记"
                        >
                          <Edit2 size={12} />
                        </button>
                        <button
                          onClick={() => handleDelete(bookmark.bookmark_id, bookmark.message_id)}
                          className="p-1 text-gray-400 hover:text-rose-500"
                          title="取消收藏"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Timestamp */}
                  <p className="text-[10px] text-gray-400 dark:text-neutral-600 mt-2">
                    {new Date(bookmark.created_at).toLocaleString('zh-CN')}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}