/**
 * ClaudeChatStage — Claude 模式主容器（编排器 ~80 行）
 * 三栏布局: 左侧会话侧栏 | 中间消息时间线 | 右侧预览区
 *
 * 子组件: ClaudeSessionSidebar / ClaudeMessageList / ClaudeInputArea / ClaudePreview
 */
'use client';

import { useEffect, useState, useCallback } from 'react';
import { useClaudeChat } from '@/hooks/useClaudeChat';
import { useClaudeStore } from '@/store/useClaudeStore';
import type { ClaudeSession } from '@/types/claude';
import { ClaudeSessionSidebar } from './ClaudeSessionSidebar';
import { ClaudeMessageList } from './ClaudeMessageList';
import { ClaudeInputArea } from './ClaudeInputArea';
import { ClaudePreview } from './ClaudePreview';
import { fetchAPI } from '@/lib/api';

export function ClaudeChatStage() {
  const {
    activeSessionId,
    activeConversationId,
    sessions,
    setSessions,
    setActiveSession,
    setActiveConversation,
    addSession,
    removeSession,
  } = useClaudeStore();

  const { messages, isStreaming, streamEvents, sendMessage, cancelStream, loadMessages } =
    useClaudeChat();

  const [pageState, setPageState] = useState<'loading' | 'empty' | 'error' | 'ready'>('loading');
  const [errorMessage, setErrorMessage] = useState('');

  const refreshSessions = useCallback(async () => {
    try {
      setPageState('loading');
      const data = await fetchAPI('/api/claude/sessions');
      if (data?.sessions?.length > 0) {
        setSessions(data.sessions as ClaudeSession[]);
        setPageState('ready');
      } else {
        setPageState('empty');
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : '连接失败');
      setPageState('error');
    }
  }, [setSessions]);

  useEffect(() => { refreshSessions(); }, []);
  useEffect(() => {
    if (activeSessionId && activeConversationId) {
      loadMessages(activeSessionId, activeConversationId);
    }
  }, [activeSessionId, activeConversationId, loadMessages]);

  const handleCreateSession = async () => {
    try {
      const res = await fetchAPI('/api/claude/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '新会话' }),
      });
      addSession(res.data as ClaudeSession);
      setActiveSession(res.data.id);
      setPageState('ready');
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (!confirm('确定要删除此会话吗？')) return;
    await fetchAPI(`/api/claude/sessions/${sessionId}`, { method: 'DELETE' });
    removeSession(sessionId);
    if (activeSessionId === sessionId) {
      setActiveSession(sessions[0]?.id || '');
    }
  };

  const handleCreateConversation = async (sessionId: string) => {
    const res = await fetchAPI(`/api/claude/sessions/${sessionId}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: `对话 ${new Date().toLocaleTimeString()}` }),
    });
    if (res?.data?.id) {
      setActiveConversation(res.data.id);
    }
  };

  const handleSend = async (content: string) => {
    let sid = activeSessionId;
    let cid = activeConversationId;

    if (!sid) {
      const res = await fetchAPI('/api/claude/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: content.slice(0, 30) }),
      });
      sid = res.data.id;
      addSession(res.data as ClaudeSession);
      setActiveSession(sid!);
    }

    if (!cid && sid) {
      const res = await fetchAPI(`/api/claude/sessions/${sid}/conversations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: content.slice(0, 30) }),
      });
      cid = res.data.id;
    }

    sendMessage(content);
  };

  const handlePlanConfirm = useCallback(() => {
    sendMessage('确认执行方案，请开始执行。');
  }, [sendMessage]);

  return (
    <div className="flex h-full">
      <ClaudeSessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        activeConversationId={activeConversationId}
        onSelectSession={setActiveSession}
        onSelectConversation={setActiveConversation}
        onCreateSession={handleCreateSession}
        onCreateConversation={handleCreateConversation}
        onDeleteSession={handleDeleteSession}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {pageState === 'loading' && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3" />
              <div className="text-gray-400 text-sm">正在连接 Claude Agent...</div>
            </div>
          </div>
        )}

        {pageState === 'error' && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-red-400 text-sm mb-2">{errorMessage}</div>
              <button onClick={refreshSessions} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-sm">
                重试
              </button>
            </div>
          </div>
        )}

        {pageState === 'empty' && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-gray-400 text-lg mb-3">开始你的分析之旅</div>
              <button onClick={handleCreateSession} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm">
                创建新会话
              </button>
            </div>
          </div>
        )}

        {pageState === 'ready' && (
          <ClaudeMessageList
            messages={messages}
            streamEvents={streamEvents}
            isStreaming={isStreaming}
            onPlanConfirm={handlePlanConfirm}
          />
        )}

        <ClaudeInputArea isStreaming={isStreaming} onSend={handleSend} onCancel={cancelStream} />
      </div>

      <div className="w-64 border-l border-gray-700">
        <ClaudePreview />
      </div>
    </div>
  );
}
