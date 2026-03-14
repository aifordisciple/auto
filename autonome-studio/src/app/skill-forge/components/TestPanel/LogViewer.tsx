/**
 * 实时日志查看器
 *
 * 支持 SSE 流式日志显示，带自动滚动和语法高亮
 */

'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Terminal, Check, AlertTriangle, Info, Loader2 } from 'lucide-react';

export interface LogEntry {
  id: string;
  timestamp: Date;
  level: 'info' | 'success' | 'warning' | 'error' | 'system';
  message: string;
}

interface LogViewerProps {
  logs: LogEntry[];
  isStreaming?: boolean;
  maxHeight?: string;
  autoScroll?: boolean;
}

// 日志级别样式
const levelStyles = {
  info: 'text-neutral-300',
  success: 'text-emerald-400',
  warning: 'text-yellow-400',
  error: 'text-red-400',
  system: 'text-blue-400'
};

// 日志级别图标
const levelIcons = {
  info: <Info size={12} />,
  success: <Check size={12} />,
  warning: <AlertTriangle size={12} />,
  error: <AlertTriangle size={12} />,
  system: <Terminal size={12} />
};

// 格式化时间
const formatTime = (date: Date): string => {
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

// 解析日志消息，识别特殊模式
const parseMessage = (message: string): { text: string; isCode?: boolean; highlight?: string } => {
  // 检测是否是代码行
  if (/^(import|from|def |class |function |if |for |while |return)/.test(message.trim())) {
    return { text: message, isCode: true };
  }

  // 检测错误信息
  if (/error|Error|ERROR|exception|Exception|EXCEPTION/.test(message)) {
    return { text: message, highlight: 'error' };
  }

  // 检测警告信息
  if (/warning|Warning|WARN/.test(message)) {
    return { text: message, highlight: 'warning' };
  }

  // 检测成功信息
  if (/success|Success|SUCCESS|完成|通过/.test(message)) {
    return { text: message, highlight: 'success' };
  }

  return { text: message };
};

export function LogViewer({ logs, isStreaming = false, maxHeight = '300px', autoScroll = true }: LogViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll && shouldAutoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll, shouldAutoScroll]);

  // 检测用户是否手动滚动
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    setShouldAutoScroll(isAtBottom);
  };

  return (
    <div className="bg-black rounded-lg border border-neutral-800 overflow-hidden">
      {/* 标题栏 */}
      <div className="flex items-center justify-between px-3 py-2 bg-neutral-900 border-b border-neutral-800">
        <div className="flex items-center gap-2 text-sm text-neutral-400">
          <Terminal size={14} />
          <span>执行日志</span>
          {logs.length > 0 && (
            <span className="text-xs text-neutral-600">({logs.length} 条)</span>
          )}
        </div>
        {isStreaming && (
          <div className="flex items-center gap-1 text-xs text-blue-400">
            <Loader2 size={12} className="animate-spin" />
            <span>执行中...</span>
          </div>
        )}
      </div>

      {/* 日志内容 */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="overflow-y-auto font-mono text-xs"
        style={{ maxHeight }}
      >
        {logs.length === 0 ? (
          <div className="p-4 text-neutral-600 text-center">
            <Terminal size={20} className="mx-auto mb-2 opacity-50" />
            <p>等待执行...</p>
          </div>
        ) : (
          <div className="p-2 space-y-0.5">
            {logs.map((log) => {
              const parsed = parseMessage(log.message);
              return (
                <div
                  key={log.id}
                  className={`flex gap-2 py-0.5 ${
                    parsed.isCode ? 'text-cyan-400' : levelStyles[log.level]
                  }`}
                >
                  <span className="text-neutral-600 shrink-0">
                    [{formatTime(log.timestamp)}]
                  </span>
                  <span className="shrink-0 mt-0.5">
                    {levelIcons[log.level]}
                  </span>
                  <span
                    className={`break-all ${
                      parsed.highlight === 'error' ? 'text-red-400' :
                      parsed.highlight === 'warning' ? 'text-yellow-400' :
                      parsed.highlight === 'success' ? 'text-emerald-400' : ''
                    }`}
                  >
                    {parsed.text}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 滚动到底部提示 */}
      {!shouldAutoScroll && logs.length > 10 && (
        <button
          onClick={() => {
            if (containerRef.current) {
              containerRef.current.scrollTop = containerRef.current.scrollHeight;
              setShouldAutoScroll(true);
            }
          }}
          className="absolute bottom-2 right-2 px-2 py-1 bg-neutral-800 text-neutral-400 text-xs rounded hover:bg-neutral-700 transition-colors"
        >
          滚动到底部
        </button>
      )}
    </div>
  );
}

// 工具函数：创建日志条目
export function createLogEntry(level: LogEntry['level'], message: string): LogEntry {
  return {
    id: `log_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    timestamp: new Date(),
    level,
    message
  };
}