/**
 * useClaudeChat — Claude 模式 SSE 通信 Hook
 */

import { useCallback, useRef } from 'react';
import { useClaudeStore, type ClaudeEvent } from '@/store/useClaudeStore';
import { fetchAPI } from '@/lib/api';

export function useClaudeChat() {
  const {
    activeSessionId,
    activeConversationId,
    isStreaming,
    streamEvents,
    addMessage,
    appendStreamContent,
    setStreaming,
    resetStream,
    messages,
    setMessages,
  } = useClaudeStore();

  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!activeSessionId || !activeConversationId) return;
      if (isStreaming) return;

      const userMsg = {
        id: `temp-${Date.now()}`,
        role: 'user' as const,
        content,
        createdAt: new Date().toISOString(),
      };
      addMessage(userMsg);

      resetStream();
      setStreaming(true);

      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      try {
        const response = await fetchAPI(
          `/api/claude/sessions/${activeSessionId}/conversations/${activeConversationId}/messages`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
            signal: abortController.signal,
          }
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';
        const assistantEvents: ClaudeEvent[] = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          let currentEvent = '';
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                if (currentEvent !== 'end' && currentEvent !== 'session_info') {
                  appendStreamContent(parsed);
                  assistantEvents.push(parsed);
                }
              } catch {
                // 跳过非 JSON 数据
              }
            }
          }
        }

        const assistantMsg = {
          id: `msg-${Date.now()}`,
          role: 'assistant' as const,
          content: '',
          events: assistantEvents,
          createdAt: new Date().toISOString(),
        };
        addMessage(assistantMsg);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') {
          return;
        }
        console.error('Claude chat error:', err);
      } finally {
        setStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [
      activeSessionId,
      activeConversationId,
      isStreaming,
      addMessage,
      appendStreamContent,
      setStreaming,
      resetStream,
    ]
  );

  const cancelStream = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const loadMessages = useCallback(
    async (sessionId: string, conversationId: string) => {
      try {
        const res = await fetchAPI(
          `/api/claude/sessions/${sessionId}/conversations/${conversationId}/messages`
        );
        if (res.ok) {
          const data = await res.json();
          setMessages(data.messages || []);
        }
      } catch (err) {
        console.error('Failed to load messages:', err);
      }
    },
    [setMessages]
  );

  return {
    messages,
    isStreaming,
    streamEvents,
    sendMessage,
    cancelStream,
    loadMessages,
  };
}
