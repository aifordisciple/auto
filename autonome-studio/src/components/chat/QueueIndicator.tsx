/**
 * QueueIndicator - 消息队列指示器
 *
 * 在聊天区域底部（输入框上方）显示队列状态：
 * - 队列中消息数量
 * - 展开/折叠队列项列表
 * - 清空队列按钮
 * - 各队列项的编辑/删除操作
 */
"use client";

import { useState, useCallback } from 'react';
import { ListOrdered, Trash2, ChevronDown, ChevronUp, Edit3, X, GripVertical, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useChatStore, ChatState, ChatQueueItem, QueueItemStatus } from '@/store/useChatStore';
import { chatQueueApi } from '@/lib/api';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';

export function QueueIndicator() {
  // ✨ 所有 Hooks 必须在任何条件返回之前调用（React Rules of Hooks）
  const queueItems = useChatStore((state: ChatState) => state.queueItems);
  const isQueueActive = useChatStore((state: ChatState) => state.isQueueActive);
  const removeQueueItem = useChatStore((state: ChatState) => state.removeQueueItem);
  const setQueueItems = useChatStore((state: ChatState) => state.setQueueItems);
  const updateQueueItemStatus = useChatStore((state: ChatState) => state.updateQueueItemStatus);

  const [isExpanded, setIsExpanded] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');

  const currentSessionId = useWorkspaceStore(state => state.currentSessionId);

  // 删除队列项
  const handleDelete = useCallback(async (itemId: string) => {
    try {
      await chatQueueApi.delete(itemId);
      removeQueueItem(itemId);
    } catch (error) {
      console.error('删除队列项失败:', error);
    }
  }, [removeQueueItem]);

  // 清空队列
  const handleClear = useCallback(async () => {
    if (!currentSessionId) return;
    try {
      await chatQueueApi.clear(currentSessionId);
      setQueueItems([]);
    } catch (error) {
      console.error('清空队列失败:', error);
    }
  }, [currentSessionId, setQueueItems]);

  // 编辑队列项
  const handleEdit = useCallback(async (itemId: string) => {
    if (!editText.trim()) {
      setEditingId(null);
      return;
    }
    try {
      await chatQueueApi.update(itemId, { message: editText });
      updateQueueItemStatus(itemId, 'pending' as QueueItemStatus);
      setEditingId(null);
    } catch (error) {
      console.error('编辑队列项失败:', error);
    }
  }, [editText, updateQueueItemStatus]);

  // 开始编辑
  const startEdit = useCallback((item: ChatQueueItem) => {
    setEditingId(item.id);
    setEditText(item.message);
  }, []);

  // ✨ early return 必须在所有 Hooks 之后
  if (queueItems.length === 0 && !isQueueActive) return null;

  const pendingCount = queueItems.filter(item => item.status === 'pending').length;
  const processingCount = queueItems.filter(item => item.status === 'processing').length;

  return (
    <div className="w-full md:max-w-4xl md:mx-auto px-2 md:px-4">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-neutral-900/80 dark:bg-neutral-800/90 border border-neutral-700/50 rounded-xl overflow-hidden backdrop-blur-sm"
      >
        {/* 头部：队列概览 */}
        <div
          className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-neutral-800/50 transition-colors"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center gap-2">
            <ListOrdered size={14} className="text-blue-400" />
            <span className="text-xs text-neutral-300 font-medium">
              队列中: {pendingCount}条待处理
              {processingCount > 0 && ` · ${processingCount}条处理中`}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleClear();
              }}
              className="flex items-center gap-1 px-2 py-0.5 text-[10px] text-neutral-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
            >
              <Trash2 size={10} />
              清空
            </button>
            {isExpanded ? <ChevronUp size={14} className="text-neutral-500" /> : <ChevronDown size={14} className="text-neutral-500" />}
          </div>
        </div>

        {/* 展开的队列项列表 */}
        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="border-t border-neutral-700/50 px-3 py-2 space-y-1.5 max-h-60 overflow-y-auto custom-scrollbar">
                {queueItems.map((item, index) => (
                  <div
                    key={item.id}
                    className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-neutral-700/30 transition-colors group"
                  >
                    {/* 拖拽手柄 */}
                    <GripVertical size={12} className="text-neutral-600 cursor-grab shrink-0" />

                    {/* 位置编号 */}
                    <span className="text-[10px] text-neutral-500 w-4 shrink-0 text-right">{index + 1}</span>

                    {/* 状态指示器 */}
                    <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      item.status === 'pending' ? 'bg-neutral-500' :
                      item.status === 'processing' ? 'bg-blue-400 animate-pulse' :
                      item.status === 'failed' ? 'bg-red-400' :
                      'bg-green-400'
                    }`} />

                    {/* 消息内容 */}
                    {editingId === item.id ? (
                      <div className="flex-1 flex items-center gap-1">
                        <input
                          type="text"
                          value={editText}
                          onChange={(e) => setEditText(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleEdit(item.id);
                            if (e.key === 'Escape') setEditingId(null);
                          }}
                          className="flex-1 bg-neutral-800 border border-neutral-600 rounded px-2 py-0.5 text-xs text-neutral-200 outline-none focus:border-blue-500/50"
                          autoFocus
                        />
                        <button
                          onClick={() => handleEdit(item.id)}
                          className="text-[10px] text-blue-400 hover:text-blue-300"
                        >
                          保存
                        </button>
                      </div>
                    ) : (
                      <span className="flex-1 text-xs text-neutral-300 truncate">
                        {item.message}
                      </span>
                    )}

                    {/* 状态标签 */}
                    <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
                      item.status === 'pending' ? 'text-neutral-400 bg-neutral-700/50' :
                      item.status === 'processing' ? 'text-blue-400 bg-blue-500/10' :
                      item.status === 'failed' ? 'text-red-400 bg-red-500/10' :
                      'text-green-400 bg-green-500/10'
                    }`}>
                      {item.status === 'pending' ? '排队中' :
                       item.status === 'processing' ? '处理中' :
                       item.status === 'failed' ? '失败' : '完成'}
                    </span>

                    {/* 操作按钮（仅 pending 状态可操作） */}
                    {item.status === 'pending' && editingId !== item.id && (
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => startEdit(item)}
                          className="p-0.5 text-neutral-500 hover:text-blue-400 transition-colors"
                        >
                          <Edit3 size={11} />
                        </button>
                        <button
                          onClick={() => handleDelete(item.id)}
                          className="p-0.5 text-neutral-500 hover:text-red-400 transition-colors"
                        >
                          <X size={11} />
                        </button>
                      </div>
                    )}

                    {/* 失败项显示重试提示 */}
                    {item.status === 'failed' && item.error && (
                      <div className="flex items-center gap-1 text-[10px] text-red-400" title={item.error}>
                        <AlertCircle size={10} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
