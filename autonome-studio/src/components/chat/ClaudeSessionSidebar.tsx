/**
 * ClaudeSessionSidebar — 会话侧栏 + 对话管理
 *
 * 展示 session 列表，选中 session 时展开其下 conversations。
 * 支持创建/切换/删除 session 和 conversation。
 */
'use client';

import { useState, useEffect } from 'react';
import type { ClaudeSession, ClaudeConversation } from '@/types/claude';
import { fetchAPI } from '@/lib/api';

interface ClaudeSessionSidebarProps {
  sessions: ClaudeSession[];
  activeSessionId: string | null;
  activeConversationId: string | null;
  onSelectSession: (id: string) => void;
  onSelectConversation: (id: string) => void;
  onCreateSession: () => void;
  onCreateConversation: (sessionId: string) => void;
  onDeleteSession: (id: string) => void;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

export function ClaudeSessionSidebar({
  sessions,
  activeSessionId,
  activeConversationId,
  onSelectSession,
  onSelectConversation,
  onCreateSession,
  onCreateConversation,
  onDeleteSession,
}: ClaudeSessionSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [conversationsMap, setConversationsMap] = useState<Record<string, ClaudeConversation[]>>({});

  // 当选中的 session 改变时，加载其 conversations
  useEffect(() => {
    if (!activeSessionId) return;
    fetchAPI(`/api/claude/sessions/${activeSessionId}`)
      .then((res) => {
        if (res?.data?.conversations) {
          setConversationsMap((prev) => ({
            ...prev,
            [activeSessionId]: res.data.conversations,
          }));
        }
      })
      .catch(() => {});
  }, [activeSessionId]);

  const filteredSessions = sessions.filter((s) =>
    !searchQuery || s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="w-56 border-r border-gray-700 p-3 flex flex-col">
      <button
        onClick={onCreateSession}
        className="w-full px-3 py-2 mb-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
      >
        + 新建会话
      </button>
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="搜索会话..."
        className="w-full mb-2 px-2 py-1.5 bg-gray-800 text-gray-300 text-xs rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <div className="flex-1 overflow-y-auto space-y-1">
        {filteredSessions.length === 0 ? (
          <div className="text-xs text-gray-500 text-center py-4">
            {searchQuery ? '无匹配会话' : '暂无会话'}
          </div>
        ) : (
          filteredSessions.map((s) => {
            const isActive = s.id === activeSessionId;
            const conversations = conversationsMap[s.id] || [];
            return (
              <div key={s.id}>
                {/* Session 条目 */}
                <div
                  className={`group flex items-center rounded ${
                    isActive ? 'bg-gray-700' : 'hover:bg-gray-800'
                  }`}
                >
                  <button
                    onClick={() => onSelectSession(s.id)}
                    className="flex-1 text-left px-3 py-2 rounded text-sm truncate min-w-0"
                  >
                    <div
                      className={`truncate ${
                        isActive ? 'text-white' : 'text-gray-400'
                      }`}
                    >
                      {isActive ? '▼' : '▶'} {s.title}
                    </div>
                    {s.updatedAt && (
                      <div className="text-xs text-gray-600 mt-0.5">
                        {formatDate(s.updatedAt)}
                      </div>
                    )}
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(s.id);
                    }}
                    className="px-2 py-1 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all text-xs shrink-0"
                    title="删除会话"
                  >
                    ✕
                  </button>
                </div>

                {/* Conversations 列表（展开时显示） */}
                {isActive && (
                  <div className="ml-3 space-y-0.5">
                    {conversations.map((conv) => (
                      <button
                        key={conv.id}
                        onClick={() => onSelectConversation(conv.id)}
                        className={`w-full text-left px-3 py-1.5 rounded text-xs ${
                          conv.id === activeConversationId
                            ? 'bg-blue-600/30 text-blue-300'
                            : 'text-gray-400 hover:bg-gray-800'
                        }`}
                      >
                        {conv.title}
                      </button>
                    ))}
                    <button
                      onClick={() => onCreateConversation(s.id)}
                      className="w-full text-left px-3 py-1.5 rounded text-xs text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                    >
                      + 新对话
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
