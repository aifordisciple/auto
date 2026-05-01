/**
 * ToolUseBlock — Claude Code 工具调用展示组件
 *
 * 在对话中可视化展示 Claude Code 的工具调用过程:
 * - tool_use: 工具调用开始 (带旋转指示器)
 * - tool_result: 工具调用结果 (可展开)
 */
'use client';

import { useState } from 'react';

interface ToolUseBlockProps {
  event: {
    type: string;
    tool_name?: string;
    tool_input?: Record<string, unknown>;
    tool_use_id?: string;
    status?: string;
    content?: string;
  };
}

const TOOL_LABELS: Record<string, { icon: string; label: string }> = {
  skill_search: { icon: '🔍', label: '检索技能' },
  execute_sandbox: { icon: '▶', label: '执行命令' },
  submit_heavy_task: { icon: '📤', label: '提交重型任务' },
  read_file: { icon: '📖', label: '读取文件' },
  write_file: { icon: '✏', label: '写入文件' },
  list_files: { icon: '📂', label: '列出文件' },
};

export function ToolUseBlock({ event }: ToolUseBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const toolInfo = TOOL_LABELS[event.tool_name || ''] || { icon: '🔧', label: event.tool_name || '工具调用' };

  if (event.type === 'tool_use') {
    return (
      <div className="border border-green-500/30 rounded-lg mb-2 overflow-hidden">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 w-full px-3 py-2 bg-green-500/10 hover:bg-green-500/20 text-left text-sm"
        >
          <span className="text-xs">{toolInfo.icon}</span>
          <span className="text-green-400 font-medium">{toolInfo.label}</span>
          <span className="ml-auto text-xs text-green-500/70">{expanded ? '▼' : '▶'}</span>
        </button>
        {expanded && event.tool_input && (
          <div className="px-3 py-2 bg-green-500/5 text-xs text-green-300/70 font-mono max-h-40 overflow-y-auto">
            <pre className="whitespace-pre-wrap">
              {JSON.stringify(event.tool_input, null, 2)}
            </pre>
          </div>
        )}
      </div>
    );
  }

  if (event.type === 'tool_result') {
    const isSuccess = event.status === 'success';
    return (
      <div className={`border rounded-lg mb-2 overflow-hidden ${
        isSuccess ? 'border-green-500/20' : 'border-red-500/30'
      }`}>
        <div className={`flex items-center gap-2 px-3 py-1.5 ${
          isSuccess ? 'bg-green-500/5' : 'bg-red-500/10'
        }`}>
          <span className="text-xs">{expanded ? '▼' : '▶'}</span>
          <span className={`text-xs ${isSuccess ? 'text-green-400' : 'text-red-400'}`}>
            {isSuccess ? '✓' : '✗'} 结果
          </span>
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-auto text-xs text-gray-500 hover:text-gray-300"
          >
            {expanded ? '收起' : '展开'}
          </button>
        </div>
        {expanded && event.content && (
          <div className="px-3 py-2 text-xs text-gray-400 max-h-40 overflow-y-auto">
            <pre className="whitespace-pre-wrap font-mono">{event.content}</pre>
          </div>
        )}
      </div>
    );
  }

  return null;
}
