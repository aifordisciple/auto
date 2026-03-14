"use client";

import React, { useEffect, useState } from 'react';
import { Hammer, Plus, MessageSquare, Box, ChevronRight, Trash2, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

import { useForgeStore, ForgeSessionListItem } from '@/store/useForgeStore';
import { forgeSessionApi } from '@/lib/api';
import { CreateEntryDialog } from './CreateEntryDialog';

export function ForgeSidebar() {
  const {
    sessionId,
    sessionList,
    setSessionList,
    loadSession,
    createSession,
    reset
  } = useForgeStore();

  const [isLoading, setIsLoading] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  // 加载会话列表
  useEffect(() => {
    loadSessionList();
  }, []);

  const loadSessionList = async () => {
    try {
      const result = await forgeSessionApi.listSessions();
      setSessionList(result.sessions || []);
    } catch (error) {
      console.error('加载会话列表失败:', error);
    }
  };

  // 创建新会话
  const handleNewSession = async () => {
    setIsLoading(true);
    try {
      reset();
      await createSession();
      await loadSessionList();
    } catch (error) {
      console.error('创建会话失败:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 加载会话
  const handleLoadSession = async (id: string) => {
    setIsLoading(true);
    try {
      await loadSession(id);
    } catch (error) {
      console.error('加载会话失败:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 删除会话
  const handleDeleteSession = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm('确定要删除这个会话吗？')) return;

    try {
      await forgeSessionApi.deleteSession(id);
      setSessionList(sessionList.filter(s => s.id !== id));
      if (sessionId === id) {
        reset();
        createSession();
      }
    } catch (error) {
      console.error('删除会话失败:', error);
    }
  };

  // 格式化时间
  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) {
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } else if (days === 1) {
      return '昨天';
    } else if (days < 7) {
      return `${days} 天前`;
    } else {
      return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    }
  };

  return (
    <div className="w-60 shrink-0 border-r border-neutral-800 bg-neutral-900 flex flex-col">
      {/* 标题 */}
      <div className="p-4 border-b border-neutral-800">
        <div className="flex items-center gap-2 text-white font-semibold">
          <Hammer size={18} className="text-blue-500" />
          <span>技能锻造工厂</span>
        </div>
        <p className="text-xs text-neutral-500 mt-1">AI 驱动的技能开发</p>
      </div>

      {/* 新建按钮 */}
      <div className="p-3">
        <button
          onClick={() => setShowCreateDialog(true)}
          disabled={isLoading}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white text-sm rounded-lg transition-colors"
        >
          <Plus size={16} />
          新建技能
        </button>
      </div>

      {/* 创建入口对话框 */}
      <CreateEntryDialog
        isOpen={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onSuccess={() => {
          loadSessionList();
        }}
      />

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto">
        <div className="px-3 py-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
          >
            <ChevronRight
              size={14}
              className={`transform transition-transform ${expanded ? 'rotate-90' : ''}`}
            />
            对话历史 ({sessionList.length})
          </button>
        </div>

        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="space-y-1 px-2"
            >
              {sessionList.map((session) => (
                <div
                  key={session.id}
                  onClick={() => handleLoadSession(session.id)}
                  className={`group flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors ${
                    sessionId === session.id
                      ? 'bg-blue-500/20 text-blue-400'
                      : 'hover:bg-neutral-800 text-neutral-300'
                  }`}
                >
                  <MessageSquare size={14} className="shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm truncate">{session.title}</p>
                    <p className="text-xs text-neutral-500">{formatTime(session.updated_at)}</p>
                  </div>
                  {session.has_draft && (
                    <Box size={12} className="text-emerald-500 shrink-0" />
                  )}
                  <button
                    onClick={(e) => handleDeleteSession(e, session.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-neutral-700 rounded transition-all"
                  >
                    <Trash2 size={12} className="text-neutral-500 hover:text-red-400" />
                  </button>
                </div>
              ))}

              {sessionList.length === 0 && (
                <div className="text-center py-4 text-xs text-neutral-600">
                  暂无历史会话
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* 底部说明 */}
      <div className="p-3 border-t border-neutral-800 text-xs text-neutral-600">
        <p>💡 对话、代码、模板、文件包</p>
        <p className="mt-1">多种方式创建技能</p>
      </div>
    </div>
  );
}