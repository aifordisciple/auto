/**
 * Claude Code Agent 模式 — 统一类型定义
 *
 * 所有 Claude 模式相关组件、store、hooks 共享的类型集中在此文件，
 * 避免分散在 useClaudeStore.ts、各组件中重复定义。
 */

// ==========================================
// 事件类型
// ==========================================

/** Claude Code SSE 事件 */
export interface ClaudeEvent {
  [key: string]: unknown;
  type: string;
  timestamp: number;
  content?: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_use_id?: string;
  status?: string;
  message?: string;
  input_tokens?: number;
  output_tokens?: number;
}

// ==========================================
// 会话与对话
// ==========================================

export interface ClaudeSession {
  id: string;
  title: string;
  status: 'active' | 'archived' | 'closed';
  createdAt: string;
  updatedAt: string;
}

export interface ClaudeConversation {
  id: string;
  sessionId: string;
  title: string;
  createdAt: string;
}

// ==========================================
// 消息
// ==========================================

export interface ClaudeMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  events?: ClaudeEvent[];
  plan?: PlanData | null;
  codeSnapshot?: string;
  usage?: { input_tokens: number; output_tokens: number } | null;
  createdAt: string;
}

// ==========================================
// 方案与任务
// ==========================================

export interface PlanStep {
  title: string;
  description: string;
}

export interface PlanData {
  title: string;
  steps: PlanStep[];
  codeSnapshot: string;
  estimatedCost: string;
}
