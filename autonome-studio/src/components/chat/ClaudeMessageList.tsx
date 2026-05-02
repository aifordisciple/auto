/**
 * ClaudeMessageList — 对话消息时间线 + 流式渲染
 * 纯展示组件：接收 messages/streamEvents，渲染消息气泡和事件块
 */
'use client';

import { useRef, useEffect } from 'react';
import { ThinkingBlock } from './ThinkingBlock';
import { PlanCard } from './PlanCard';
import { TaskCard } from './TaskCard';
import { ToolUseBlock } from './ToolUseBlock';
import type { ClaudeMessage, PlanData } from '@/types/claude';

interface ClaudeMessageListProps {
  messages: ClaudeMessage[];
  streamEvents: Array<{ type: string; [key: string]: unknown }>;
  isStreaming: boolean;
  onPlanConfirm: () => void;
}

function buildTextContent(events: Array<{ type: string; content?: string }>): string {
  return events
    .filter((e) => e.type === 'text_delta')
    .map((e) => e.content || '')
    .join('');
}

function extractPlan(events: Array<{ type: string; title?: string; steps?: Array<{ title: string; description: string }>; codeSnapshot?: string; estimatedCost?: string; [key: string]: unknown }>): PlanData | null {
  const e = events.find((ev) => ev.type === 'plan');
  if (!e) return null;
  return {
    title: String(e.title || ''),
    steps: (e.steps as PlanData['steps']) || [],
    codeSnapshot: String(e.codeSnapshot || ''),
    estimatedCost: String(e.estimatedCost || ''),
  };
}

function extractTaskIds(events: Array<{ type: string; task_id?: string; [key: string]: unknown }>): string[] {
  return events
    .filter((e) => e.type === 'task_submitted' && e.task_id)
    .map((e) => e.task_id!);
}

export function ClaudeMessageList({
  messages,
  streamEvents,
  isStreaming,
  onPlanConfirm,
}: ClaudeMessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamEvents]);

  return (
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
                  onConfirm={onPlanConfirm}
                  disabled={true}
                />
              )}
              {msg.events?.map((event, i) => {
                if (event.type === 'thinking') {
                  return <ThinkingBlock key={i} content={(event.content as string) || ''} />;
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
            <PlanCard plan={extractPlan(streamEvents)!} onConfirm={onPlanConfirm} />
          )}
          {streamEvents.filter((e) => e.type === 'thinking').map((e, i) => (
            <ThinkingBlock key={`stream-thinking-${i}`} content={(e.content as string) || ''} />
          ))}
          {streamEvents.filter((e) => e.type === 'tool_use' || e.type === 'tool_result').map((e, i) => (
            <ToolUseBlock key={`stream-tool-${i}`} event={e} />
          ))}
          <div className="text-gray-200 whitespace-pre-wrap">
            {streamEvents
              .filter((e) => e.type === 'text_delta')
              .map((e) => (e.content as string) || '')
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
  );
}
