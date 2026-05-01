/**
 * ClaudeChatStage — Claude 模式主容器
 * 三栏布局: 左侧会话列表 | 中间对话时间线 | 右侧预览区 (Phase 3)
 */
'use client';

import { useEffect, useState, useRef } from 'react';
import { useClaudeChat } from '@/hooks/useClaudeChat';
import { useClaudeStore, type ClaudeSession } from '@/store/useClaudeStore';
import { ThinkingBlock } from './ThinkingBlock';
import { fetchAPI } from '@/lib/api';

export function ClaudeChatStage() {
  const {
    activeSessionId,
    activeConversationId,
    sessions,
    setSessions,
    setActiveSession,
    addSession,
  } = useClaudeStore();

  const {
    messages,
    isStreaming,
    streamEvents,
    sendMessage,
    cancelStream,
    loadMessages,
  } = useClaudeChat();

  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchAPI('/api/claude/sessions')
      .then((res) => res.json())
      .then((data) => {
        if (data.sessions) {
          setSessions(data.sessions as ClaudeSession[]);
          if (data.sessions.length > 0 && !activeSessionId) {
            const convId = activeConversationId || '';
            setActiveSession(data.sessions[0].id);
          }
        }
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (activeSessionId && activeConversationId) {
      loadMessages(activeSessionId, activeConversationId);
    }
  }, [activeSessionId, activeConversationId, loadMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamEvents]);

  const handleCreateSession = async () => {
    try {
      const res = await fetchAPI('/api/claude/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '新会话' }),
      });
      const session = await res.json();
      addSession(session as ClaudeSession);
      setActiveSession(session.id);
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  };

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    sendMessage(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const buildTextContent = (events: Array<{ type: string; content?: string }>) => {
    return events
      .filter((e) => e.type === 'text_delta')
      .map((e) => e.content || '')
      .join('');
  };

  return (
    <div className="flex h-full">
      {/* 左侧: 会话列表 */}
      <div className="w-56 border-r border-gray-700 p-3 flex flex-col">
        <button
          onClick={handleCreateSession}
          className="w-full px-3 py-2 mb-3 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
        >
          + 新建会话
        </button>
        <div className="flex-1 overflow-y-auto space-y-1">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSession(s.id)}
              className={`w-full text-left px-3 py-2 rounded text-sm truncate ${
                s.id === activeSessionId
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-400 hover:bg-gray-800'
              }`}
            >
              {s.title}
            </button>
          ))}
        </div>
      </div>

      {/* 中间: 对话时间线 */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto p-4">
          {messages.map((msg) => (
            <div key={msg.id} className="mb-4">
              {msg.role === 'user' ? (
                <div className="flex justify-end">
                  <div className="bg-blue-600 text-white px-4 py-2 rounded-lg max-w-[80%]">
                    {msg.content}
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  {msg.events?.map((event, i) => {
                    if (event.type === 'thinking') {
                      return <ThinkingBlock key={i} content={event.content || ''} />;
                    }
                    return null;
                  })}
                  {msg.events && msg.events.length > 0 && (
                    <div className="text-gray-200 whitespace-pre-wrap">
                      {buildTextContent(msg.events)}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* 流式渲染 */}
          {isStreaming && (
            <div className="mb-4">
              {streamEvents.filter((e) => e.type === 'thinking').map((e, i) => (
                <ThinkingBlock key={`stream-thinking-${i}`} content={e.content || ''} />
              ))}
              <div className="text-gray-200 whitespace-pre-wrap">
                {streamEvents
                  .filter((e) => e.type === 'text_delta')
                  .map((e) => e.content || '')
                  .join('')}
                {streamEvents.some((e) => e.type === 'status' && e.status === 'thinking') && (
                  <span className="inline-block w-2 h-4 bg-blue-400 animate-pulse ml-1" />
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="border-t border-gray-700 p-3">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息... (Enter 发送)"
              rows={2}
              className="flex-1 bg-gray-800 text-gray-200 rounded px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <button
              onClick={isStreaming ? cancelStream : handleSend}
              className={`px-4 py-2 rounded text-sm ${
                isStreaming
                  ? 'bg-red-600 hover:bg-red-700 text-white'
                  : 'bg-blue-600 hover:bg-blue-700 text-white'
              }`}
            >
              {isStreaming ? '停止' : '发送'}
            </button>
          </div>
        </div>
      </div>

      {/* 右侧: 预览区 */}
      <div className="w-64 border-l border-gray-700 p-3 text-gray-500 text-sm">
        预览区 (开发中)
      </div>
    </div>
  );
}
