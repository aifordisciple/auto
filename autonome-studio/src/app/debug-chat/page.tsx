/**
 * 临时调试页面：测试 useChat + DefaultChatTransport 是否能解析 UIMessage Stream
 * 访问 /debug-chat 查看
 */
"use client";

import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';
import { useMemo } from 'react';

export default function DebugChat() {
  const transport = useMemo(() => new DefaultChatTransport({
    api: '/api/chat',
    headers: () => {
      const token = typeof window !== 'undefined'
        ? localStorage.getItem('autonome_access_token') : null;
      const result: Record<string, string> = {};
      if (token) result['Authorization'] = `Bearer ${token}`;
      return result;
    },
    body: () => ({
      data: {
        projectId: 'proj_09224daaedc4',
        sessionId: null,
        contextFiles: [],
      },
    }),
  }), []);

  const { messages, status, sendMessage, error } = useChat({ transport });

  return (
    <div style={{ padding: 20, fontFamily: 'monospace', fontSize: 14 }}>
      <h2>Debug Chat - useChat + DefaultChatTransport</h2>
      <p>Status: <b>{status}</b></p>
      {error && <p style={{ color: 'red' }}>Error: {error.message}</p>}
      <p>Messages count: <b>{messages.length}</b></p>

      <button
        onClick={() => sendMessage({ text: '你好' })}
        disabled={status !== 'ready'}
        style={{ padding: '8px 16px', cursor: 'pointer' }}
      >
        Send "你好"
      </button>

      <hr />
      <h3>Raw messages:</h3>
      <pre style={{ background: '#1a1a1a', color: '#0f0', padding: 10, overflow: 'auto', maxHeight: 400 }}>
        {JSON.stringify(messages, null, 2)}
      </pre>
    </div>
  );
}
