/**
 * 消息队列 API
 *
 * 提供消息队列的 CRUD 操作：
 * - 添加消息到队列
 * - 获取队列状态
 * - 编辑/删除队列项
 * - 调整顺序/清空队列
 * - 恢复中断的队列
 */

import { fetchAPI, BASE_URL, getToken } from '../api';

// ==========================================
// 类型定义
// ==========================================

/** 队列项状态 */
export type QueueItemStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';

/** 队列项 */
export interface ChatQueueItem {
  id: string;
  session_id: string;
  project_id: string;
  status: QueueItemStatus;
  message: string;
  attachments?: Record<string, unknown>;
  position: number;
  result_message_id?: string;
  error?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

// ==========================================
// API 调用
// ==========================================

export const chatQueueApi = {
  /**
   * 提交消息到队列
   */
  async add(request: {
    session_id: string;
    project_id: string;
    message: string;
    attachments?: Record<string, unknown>;
  }): Promise<ChatQueueItem> {
    return fetchAPI('/chat/queue', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  /**
   * 获取队列状态
   */
  async getStatus(sessionId: string): Promise<ChatQueueItem[]> {
    return fetchAPI(`/chat/queue/${sessionId}`);
  },

  /**
   * 编辑队列项（仅 pending 状态可编辑）
   */
  async update(itemId: string, updates: {
    message?: string;
    attachments?: Record<string, unknown>;
  }): Promise<ChatQueueItem> {
    return fetchAPI(`/chat/queue/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
  },

  /**
   * 删除队列项
   */
  async delete(itemId: string): Promise<{ success: boolean }> {
    return fetchAPI(`/chat/queue/${itemId}`, {
      method: 'DELETE',
    });
  },

  /**
   * 清空会话的所有 pending 队列项
   */
  async clear(sessionId: string): Promise<{ cleared: number }> {
    return fetchAPI(`/chat/queue/session/${sessionId}`, {
      method: 'DELETE',
    });
  },

  /**
   * 调整队列中消息的顺序
   */
  async reorder(sessionId: string, itemIds: string[]): Promise<ChatQueueItem[]> {
    return fetchAPI('/chat/queue/reorder', {
      method: 'PATCH',
      body: JSON.stringify({
        session_id: sessionId,
        item_ids: itemIds,
      }),
    });
  },

  /**
   * 恢复中断的队列（SSE 重连后调用）
   */
  async recover(sessionId: string): Promise<{ success: boolean }> {
    return fetchAPI(`/chat/queue/${sessionId}/recover`, {
      method: 'POST',
    });
  },

  /**
   * 获取队列 SSE 流的 URL
   */
  getQueueStreamUrl(): string {
    return `${BASE_URL}/api/chat/stream/queue`;
  },
};
