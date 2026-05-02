/**
 * ClaudeChatStage — Claude 模式主容器
 * 三栏布局: 左侧会话列表 | 中间对话时间线 | 右侧预览区 (Phase 3)
 */
'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useClaudeChat } from '@/hooks/useClaudeChat';
import { useClaudeStore, type ClaudeSession, type PlanData } from '@/store/useClaudeStore';
import { ThinkingBlock } from './ThinkingBlock';
import { PlanCard } from './PlanCard';
import { TaskCard } from './TaskCard';
import { ToolUseBlock } from './ToolUseBlock';
import { ClaudePreview } from './ClaudePreview';
import { fetchAPI } from '@/lib/api';

export function ClaudeChatStage() {
  const {
    activeSessionId,
    activeConversationId,
    sessions,
    setSessions,
    setActiveSession,
    addSession,
    removeSession,
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
  const [searchQuery, setSearchQuery] = useState('');
  const [pageState, setPageState] = useState<'loading' | 'empty' | 'error' | 'ready'>('loading');
  const [errorMessage, setErrorMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const refreshSessions = useCallback(async () => {
    try {
      setPageState('loading');
      const data = await fetchAPI('/api/claude/sessions');
      if (data && data.sessions && data.sessions.length > 0) {
        setSessions(data.sessions as ClaudeSession[]);
        setPageState('ready');
      } else {
        setPageState('empty');
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '连接失败');
      setPageState('error');
      console.error('Failed to refresh sessions:', err);
    }
  }, [setSessions]);

  useEffect(() => {
    refreshSessions();
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
      const session = await fetchAPI('/api/claude/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '新会话' }),
      });
      addSession(session as ClaudeSession);
      setActiveSession(session.id);
      setPageState('ready');
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm('确定要删除此会话吗？关联的对话和消息将被永久删除。')) return;
    try {
      await fetchAPI(`/api/claude/sessions/${sessionId}`, { method: 'DELETE' });
      removeSession(sessionId);
      if (activeSessionId === sessionId) {
        setActiveSession(sessions[0]?.id || '');
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  };

  const filteredSessions = sessions.filter((s) =>
    !searchQuery || s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  };

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;

    let sid = activeSessionId;
    let cid = activeConversationId;

    // 自动创建 session
    if (!sid) {
      try {
        const res = await fetchAPI('/api/claude/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: input.trim().slice(0, 30) }),
        });
        sid = res.id;
        addSession(res as ClaudeSession);
        setActiveSession(sid!);
      } catch (err) {
        console.error('Failed to create session:', err);
        return;
      }
    }

    // 自动创建 conversation
    if (!cid && sid) {
      try {
        const res = await fetchAPI(`/api/claude/sessions/${sid}/conversations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: input.trim().slice(0, 30) }),
        });
        cid = res.id;
      } catch (err) {
        console.error('Failed to create conversation:', err);
        return;
      }
    }

    sendMessage(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /** 确认分析方案 — 发送确认指令给 Claude Code */
  const handlePlanConfirm = useCallback(() => {
    sendMessage('确认执行方案，请开始执行。');
  }, [sendMessage]);

  const buildTextContent = (events: Array<{ type: string; content?: string }>) => {
    return events
      .filter((e) => e.type === 'text_delta')
      .map((e) => e.content || '')
      .join('');
  };

  /** 从事件列表中提取方案数据 */
  const extractPlan = (events: Array<{ type: string; content?: string; [key: string]: unknown }>): PlanData | null => {
    const planEvent = events.find((e) => e.type === 'plan');
    if (planEvent?.content) {
      try {
        return JSON.parse(planEvent.content) as PlanData;
      } catch {
        return null;
      }
    }
    return null;
  };

  /** 从事件列表中提取已提交的任务ID列表 */
  const extractTaskIds = (events: Array<{ type: string; task_id?: string; [key: string]: unknown }>): string[] => {
    return events
      .filter((e) => e.type === 'task_submitted' && e.task_id)
      .map((e) => e.task_id!);
  };

  return (
    <div className="flex h-full">
      {/* 左侧: 会话列表 */}
      <div className="w-56 border-r border-gray-700 p-3 flex flex-col">
        <button
          onClick={handleCreateSession}
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
            filteredSessions.map((s) => (
              <div
                key={s.id}
                className={`group flex items-center rounded ${
                  s.id === activeSessionId ? 'bg-gray-700' : 'hover:bg-gray-800'
                }`}
              >
                <button
                  onClick={() => setActiveSession(s.id)}
                  className="flex-1 text-left px-3 py-2 rounded text-sm truncate min-w-0"
                >
                  <div className={`truncate ${
                    s.id === activeSessionId ? 'text-white' : 'text-gray-400'
                  }`}>
                    {s.title}
                  </div>
                  {s.updatedAt && (
                    <div className="text-xs text-gray-600 mt-0.5">
                      {formatDate(s.updatedAt)}
                    </div>
                  )}
                </button>
                <button
                  onClick={(e) => handleDeleteSession(e, s.id)}
                  className="px-2 py-1 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all text-xs shrink-0"
                  title="删除会话"
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 中间: 对话时间线 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 加载态 */}
        {pageState === 'loading' && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3" />
              <div className="text-gray-400 text-sm">正在连接 Claude Agent...</div>
            </div>
          </div>
        )}
        {/* 空态 */}
        {pageState === 'empty' && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-gray-400 text-lg mb-3">开始你的分析之旅</div>
              <button
                onClick={handleCreateSession}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
              >
                创建新会话
              </button>
            </div>
          </div>
        )}
        {/* 错误态 */}
        {pageState === 'error' && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-red-400 text-sm mb-2">{errorMessage}</div>
              <button
                onClick={() => refreshSessions()}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-sm"
              >
                重试
              </button>
            </div>
          </div>
        )}
        {/* 就绪态: 消息列表 */}
        {pageState === 'ready' && (
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
                  {msg.events && extractPlan(msg.events) && (
                    <PlanCard
                      plan={extractPlan(msg.events)!}
                      onConfirm={handlePlanConfirm}
                      disabled={true}
                    />
                  )}
                  {msg.events?.map((event, i) => {
                    if (event.type === 'thinking') {
                      return <ThinkingBlock key={i} content={event.content || ''} />;
                    }
                    if (event.type === 'tool_use' || event.type === 'tool_result') {
                      return <ToolUseBlock key={i} event={event} />;
                    }
                    return null;
                  })}
                  {msg.events && msg.events.length > 0 && (
                    <div className="text-gray-200 whitespace-pre-wrap">
                      {buildTextContent(msg.events)}
                    </div>
                  )}
                  {msg.events && extractTaskIds(msg.events).map((tid) => (
                    <TaskCard key={tid} taskId={tid} />
                  ))}
                </div>
              )}
            </div>
          ))}

          {/* 流式渲染 */}
          {isStreaming && (
            <div className="mb-4">
              {extractPlan(streamEvents) && (
                <PlanCard
                  plan={extractPlan(streamEvents)!}
                  onConfirm={handlePlanConfirm}
                />
              )}
              {streamEvents.filter((e) => e.type === 'thinking').map((e, i) => (
                <ThinkingBlock key={`stream-thinking-${i}`} content={e.content || ''} />
              ))}
              {streamEvents.filter((e) => e.type === 'tool_use' || e.type === 'tool_result').map((e, i) => (
                <ToolUseBlock key={`stream-tool-${i}`} event={e} />
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
              {extractTaskIds(streamEvents).map((tid) => (
                <TaskCard key={tid} taskId={tid} />
              ))}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
        )}

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
      <div className="w-64 border-l border-gray-700">
        <ClaudePreview />
      </div>
    </div>
  );
}
