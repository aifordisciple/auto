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
// Discriminant Union 事件类型 — 按 type 窄化，消除 as 强制转换
// ==========================================

export interface ClaudeThinkingEvent {
  type: 'thinking';
  content: string;
  timestamp: number;
}

export interface ClaudeTextDeltaEvent {
  type: 'text_delta';
  content: string;
  timestamp: number;
}

export interface ClaudePlanEventType {
  type: 'plan';
  title: string;
  steps: PlanStep[];
  codeSnapshot: string;
  estimatedCost: string;
  timestamp: number;
}

export interface ClaudeToolUseEventType {
  type: 'tool_use';
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_use_id: string;
  timestamp: number;
}

export interface ClaudeToolResultEventType {
  type: 'tool_result';
  tool_name: string;
  tool_use_id: string;
  status: string;
  output: string;
  timestamp: number;
}

export interface ClaudeStatusEventType {
  type: 'status';
  status: string;
  message: string;
  timestamp: number;
}

export interface ClaudeErrorEventType {
  type: 'error';
  message: string;
  code?: string;
  timestamp: number;
}

export interface ClaudeUsageEventType {
  type: 'usage';
  input_tokens: number;
  output_tokens: number;
  timestamp: number;
}

export interface ClaudeTaskSubmittedEventType {
  type: 'task_submitted';
  task_id: string;
  celery_queue?: string;
  skill_id?: string;
  timestamp: number;
}

export interface ClaudeTaskStatusEventType {
  type: 'task_status';
  task_id: string;
  status: string;
  progress?: string;
  timestamp: number;
}

/** 按 type 字段 discriminant 的完整事件联合类型 */
export type ClaudeStreamEvent =
  | ClaudeThinkingEvent
  | ClaudeTextDeltaEvent
  | ClaudePlanEventType
  | ClaudeToolUseEventType
  | ClaudeToolResultEventType
  | ClaudeStatusEventType
  | ClaudeErrorEventType
  | ClaudeUsageEventType
  | ClaudeTaskSubmittedEventType
  | ClaudeTaskStatusEventType;

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
