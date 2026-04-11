/**
 * @autonome/shared-types
 * 共享 TypeScript 类型定义
 */

// API 响应类型
export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  detail?: string;
  message?: string;
}

// 用户类型
export interface User {
  id: number;
  email: string;
  full_name?: string;
  credits_balance: number;
  is_superuser: boolean;
}

// 项目类型
export interface Project {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  owner_id: number;
  status: 'active' | 'archived' | 'deleted';
}

// 技能类型
export interface Skill {
  skill_id: string;
  name: string;
  version: string;
  executor_type: 'Python_env' | 'R_env' | 'Logical_Blueprint' | 'Python_Package';
  category: string;
  category_name: string;
  subcategory?: string;
  subcategory_name?: string;
  tags: string[];
  visibility: 'private' | 'team' | 'public';
  description?: string;
}

// 聊天消息类型
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
}

// 任务类型
export interface Task {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress?: number;
  result?: unknown;
  error?: string;
  created_at: string;
  updated_at: string;
}

// 文件节点类型
export interface FolderNode {
  name: string;
  path: string;
  writable: boolean;
  children: FolderNode[];
}

// 平台类型
export type PlatformType = 'web' | 'desktop';