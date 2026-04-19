/**
 * useChatQueue - 消息队列管理 Hook
 *
 * 功能：
 * 1. 管理消息队列的增删改查操作
 * 2. 通过 BFF 代理路由与后端队列 API 交互
 * 3. 同步队列状态到 Zustand store
 *
 * 使用场景：
 * - AI 正在回复时，新消息自动入队
 * - 用户可以管理队列中的待处理消息
 */
import { useState, useCallback } from 'react';
import { useChatStore } from '@/store/useChatStore';
import type { ChatQueueItem } from '@/store/useChatStore';

// ==========================================
// 类型定义
// ==========================================

interface UseChatQueueOptions {
  sessionId: string | null;
  projectId: string | null;
  /** 当前是否有流式请求正在进行 */
  isLoading: boolean;
}

// ==========================================
// Hook 实现
// ==========================================

export function useChatQueue({ sessionId, projectId, isLoading }: UseChatQueueOptions) {
  // 从 store 读取队列状态
  const queueItems = useChatStore(state => state.queueItems);
  const isQueueActive = useChatStore(state => state.isQueueActive);
  const addQueueItem = useChatStore(state => state.addQueueItem);
  const removeQueueItem = useChatStore(state => state.removeQueueItem);
  const clearQueueItems = useChatStore(state => state.clearQueueItems);

  // 队列流式输出状态
  const [isQueueStreaming, setIsQueueStreaming] = useState(false);

  // ==========================================
  // 添加消息到队列
  // ==========================================
  const addToQueue = useCallback(async (message: string, contextFiles?: string[]) => {
    if (!sessionId || !projectId) return;
    try {
      const res = await fetch('/api/chat/queue-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'add',
          sessionId,
          projectId,
          message,
          context_files: contextFiles,
        }),
      });
      const data = await res.json();
      if (data.data) {
        addQueueItem({
          id: String(data.data.id),
          session_id: sessionId,
          project_id: projectId,
          status: 'pending',
          message,
          position: queueItems.length + 1,
          created_at: new Date().toISOString(),
        } as ChatQueueItem);
      }
    } catch (e) {
      console.error('Failed to add to queue:', e);
    }
  }, [sessionId, projectId, addQueueItem, queueItems.length]);

  // ==========================================
  // 从队列中移除消息
  // ==========================================
  const removeFromQueue = useCallback(async (itemId: string) => {
    try {
      await fetch('/api/chat/queue-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'delete',
          sessionId,
          itemId,
        }),
      });
      removeQueueItem(itemId);
    } catch (e) {
      console.error('Failed to remove from queue:', e);
    }
  }, [sessionId, removeQueueItem]);

  // ==========================================
  // 清空队列
  // ==========================================
  const clearQueue = useCallback(async () => {
    try {
      await fetch('/api/chat/queue-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'clear',
          sessionId,
        }),
      });
      clearQueueItems();
    } catch (e) {
      console.error('Failed to clear queue:', e);
    }
  }, [sessionId, clearQueueItems]);

  // ==========================================
  // 重排队列顺序
  // ==========================================
  const reorderQueue = useCallback(async (itemIds: string[]) => {
    try {
      await fetch('/api/chat/queue-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'reorder',
          sessionId,
          itemIds,
        }),
      });
    } catch (e) {
      console.error('Failed to reorder queue:', e);
    }
  }, [sessionId]);

  return {
    queueItems,
    isQueueActive,
    isQueueStreaming,
    addToQueue,
    removeFromQueue,
    clearQueue,
    reorderQueue,
  };
}
