/**
 * ClaudeInputArea — 消息输入区域
 * 仅负责输入框 + 发送/取消按钮，无业务逻辑依赖
 */
'use client';

import { useState } from 'react';

interface ClaudeInputAreaProps {
  isStreaming: boolean;
  onSend: (content: string) => void;
  onCancel: () => void;
}

export function ClaudeInputArea({ isStreaming, onSend, onCancel }: ClaudeInputAreaProps) {
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    onSend(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
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
          onClick={isStreaming ? onCancel : handleSend}
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
  );
}
