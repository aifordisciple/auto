"use client";

import { useState, useEffect } from "react";
import { Tag, Plus, X, Check, Loader2 } from "lucide-react";
import { BASE_URL } from "@/lib/api";

interface SessionTag {
  id: number;
  name: string;
  color: string;
}

interface SessionTagManagerProps {
  sessionId: string;
  onClose?: () => void;
}

export function SessionTagManager({ sessionId, onClose }: SessionTagManagerProps) {
  const [allTags, setAllTags] = useState<SessionTag[]>([]);
  const [sessionTags, setSessionTags] = useState<SessionTag[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showNewTag, setShowNewTag] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState("#3B82F6");

  const PRESET_COLORS = [
    "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
    "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1"
  ];

  const fetchAllTags = async () => {
    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/tags`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setAllTags(data.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch tags:', e);
    }
  };

  const fetchSessionTags = async () => {
    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/sessions/${sessionId}/tags`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSessionTags(data.tags || []);
      }
    } catch (e) {
      console.error('Failed to fetch session tags:', e);
    }
  };

  useEffect(() => {
    fetchAllTags();
    fetchSessionTags();
  }, [sessionId]);

  const isTagAssigned = (tagId: number) => {
    return sessionTags.some(t => t.id === tagId);
  };

  const handleToggleTag = async (tagId: number) => {
    setIsLoading(true);
    const token = localStorage.getItem('autonome_access_token');

    try {
      if (isTagAssigned(tagId)) {
        // Remove tag
        await fetch(`${BASE_URL}/api/chat/sessions/${sessionId}/tags/${tagId}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${token}` }
        });
        setSessionTags(prev => prev.filter(t => t.id !== tagId));
      } else {
        // Add tag
        await fetch(`${BASE_URL}/api/chat/sessions/${sessionId}/tags/${tagId}`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const tag = allTags.find(t => t.id === tagId);
        if (tag) {
          setSessionTags(prev => [...prev, tag]);
        }
      }
    } catch (e) {
      console.error('Failed to toggle tag:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateTag = async () => {
    if (!newTagName.trim()) return;

    const token = localStorage.getItem('autonome_access_token');
    try {
      const res = await fetch(`${BASE_URL}/api/chat/tags`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ name: newTagName.trim(), color: newTagColor })
      });
      if (res.ok) {
        const data = await res.json();
        setAllTags(prev => [...prev, data.tag]);
        // Auto-assign new tag to this session
        if (data.tag) {
          await fetch(`${BASE_URL}/api/chat/sessions/${sessionId}/tags/${data.tag.id}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
          });
          setSessionTags(prev => [...prev, data.tag]);
        }
        setNewTagName("");
        setShowNewTag(false);
      }
    } catch (e) {
      console.error('Failed to create tag:', e);
    }
  };

  return (
    <div className="p-3 bg-white dark:bg-[#1a1a1a] rounded-lg border border-gray-200 dark:border-neutral-700 shadow-lg min-w-64">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Tag size={14} className="text-blue-500" />
          <span className="text-sm font-medium text-gray-700 dark:text-neutral-200">管理标签</span>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-neutral-300">
            <X size={14} />
          </button>
        )}
      </div>

      {/* Assigned tags */}
      {sessionTags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {sessionTags.map(tag => (
            <span
              key={tag.id}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full text-white"
              style={{ backgroundColor: tag.color }}
            >
              {tag.name}
              <button
                onClick={() => handleToggleTag(tag.id)}
                className="hover:bg-white/20 rounded-full p-0.5"
              >
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* All tags */}
      <div className="space-y-1 max-h-48 overflow-y-auto">
        {allTags.map(tag => (
          <button
            key={tag.id}
            onClick={() => handleToggleTag(tag.id)}
            disabled={isLoading}
            className={`w-full flex items-center justify-between px-2 py-1.5 rounded-md transition-all ${
              isTagAssigned(tag.id)
                ? 'bg-blue-50 dark:bg-blue-500/10'
                : 'hover:bg-gray-100 dark:hover:bg-neutral-800'
            }`}
          >
            <div className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: tag.color }}
              />
              <span className="text-xs text-gray-700 dark:text-neutral-300">{tag.name}</span>
            </div>
            {isTagAssigned(tag.id) && (
              <Check size={14} className="text-blue-500" />
            )}
          </button>
        ))}

        {allTags.length === 0 && !showNewTag && (
          <p className="text-xs text-gray-400 dark:text-neutral-500 text-center py-2">
            暂无标签，点击下方创建
          </p>
        )}
      </div>

      {/* New tag form */}
      {showNewTag ? (
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-neutral-700 space-y-2">
          <input
            autoFocus
            value={newTagName}
            onChange={e => setNewTagName(e.target.value)}
            placeholder="输入标签名称..."
            className="w-full text-xs px-2 py-1.5 bg-transparent border border-gray-300 dark:border-neutral-600 rounded text-gray-700 dark:text-neutral-300 outline-none focus:border-blue-500"
            onKeyDown={e => {
              if (e.key === 'Enter') handleCreateTag();
              if (e.key === 'Escape') {
                setShowNewTag(false);
                setNewTagName("");
              }
            }}
          />

          {/* Color picker */}
          <div className="flex items-center gap-1 flex-wrap">
            {PRESET_COLORS.map(color => (
              <button
                key={color}
                onClick={() => setNewTagColor(color)}
                className={`w-5 h-5 rounded-full transition-transform ${newTagColor === color ? 'scale-110 ring-2 ring-offset-1 ring-gray-400' : ''}`}
                style={{ backgroundColor: color }}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCreateTag}
              disabled={!newTagName.trim()}
              className="flex-1 text-xs py-1.5 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-300 disabled:dark:bg-neutral-700 text-white rounded transition-colors"
            >
              创建并添加
            </button>
            <button
              onClick={() => {
                setShowNewTag(false);
                setNewTagName("");
              }}
              className="text-xs py-1.5 px-3 text-gray-500 hover:text-gray-700 dark:text-neutral-400 dark:hover:text-neutral-300"
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowNewTag(true)}
          className="w-full mt-3 flex items-center justify-center gap-1 text-xs text-blue-500 hover:text-blue-600 py-1.5 border border-dashed border-gray-300 dark:border-neutral-600 rounded-md hover:border-blue-500 transition-colors"
        >
          <Plus size={12} />
          创建新标签
        </button>
      )}
    </div>
  );
}