/**
 * useClaudeChat — Claude 模式 SSE 通信 Hook
 */

import { useCallback, useRef } from 'react';
import { useClaudeStore } from '@/store/useClaudeStore';
import type { ClaudeEvent } from '@/types/claude';
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

      const MAX_RETRIES = 5;
      const BASE_DELAY = 1000;
      const assistantEvents: ClaudeEvent[] = [];

      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
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

          // SSE 流正常结束，跳出重连循环
          break;
        } catch (err: unknown) {
          if (err instanceof Error && err.name === 'AbortError') {
            return;
          }

          if (attempt < MAX_RETRIES) {
            const delay = BASE_DELAY * Math.pow(2, attempt);
            console.warn(`Claude SSE 中断，${delay / 1000}s 后重连 (${attempt + 1}/${MAX_RETRIES})`);
            appendStreamContent({
              type: 'status',
              status: 'reconnecting',
              message: `连接中断，${delay / 1000}s 后重连 (${attempt + 1}/${MAX_RETRIES})`,
              timestamp: Date.now(),
            });
            await new Promise((r) => setTimeout(r, delay));
          } else {
            console.error('Claude chat error after max retries:', err);
            appendStreamContent({
              type: 'error',
              message: '连接失败，已达最大重试次数。请检查网络后重试。',
              timestamp: Date.now(),
            });
            break;
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
      setStreaming(false);
      abortControllerRef.current = null;
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
