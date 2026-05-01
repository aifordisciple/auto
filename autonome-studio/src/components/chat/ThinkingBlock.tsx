/**
 * ThinkingBlock — 可折叠的 Claude Code 思考过程展示
 */
'use client';

import { useState } from 'react';

interface ThinkingBlockProps {
  content: string;
}

export function ThinkingBlock({ content }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);

  if (!content) return null;

  return (
    <div className="border border-amber-500/30 rounded-lg mb-2 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 bg-amber-500/10 hover:bg-amber-500/20 text-left text-sm text-amber-400"
      >
        <span className="text-xs">{expanded ? '▼' : '▶'}</span>
        <span>思考过程</span>
      </button>
      {expanded && (
        <div className="px-3 py-2 bg-amber-500/5 text-sm text-amber-300/80 whitespace-pre-wrap max-h-60 overflow-y-auto">
          {content}
        </div>
      )}
    </div>
  );
}
