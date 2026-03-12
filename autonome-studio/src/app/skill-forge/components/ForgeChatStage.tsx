"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Bot, User, Sparkles, Paperclip, Send, X, Loader2, Hammer } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchEventSource } from '@microsoft/fetch-event-source';

import { useForgeStore } from '@/store/useForgeStore';
import { MarkdownBlock } from '@/components/MarkdownBlock';
import { BASE_URL } from '@/lib/api';

// 附件选择器组件（简化版）
const AttachmentPicker = ({
  isOpen,
  onClose,
  onAddFiles,
  projectId
}: {
  isOpen: boolean;
  onClose: () => void;
  onAddFiles: (paths: string[]) => void;
  projectId: string | null;
}) => {
  const [files, setFiles] = useState<any[]>([]);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (isOpen && projectId) {
      const token = localStorage.getItem('autonome_access_token');
      fetch(`${BASE_URL}/api/projects/${projectId}/files`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      })
        .then(res => res.json())
        .then(data => setFiles(data.data || []))
        .catch(() => setFiles([]));
    }
  }, [isOpen, projectId]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-neutral-900 rounded-xl p-4 w-[400px] max-h-[500px] overflow-hidden">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-white font-medium">选择附件</h3>
          <button onClick={onClose} className="text-neutral-400 hover:text-white">
            <X size={18} />
          </button>
        </div>
        <div className="max-h-[350px] overflow-y-auto space-y-1">
          {files.map((file: any) => {
            const path = file.path || file.filename;
            const isSelected = selectedPaths.has(path);
            return (
              <div
                key={path}
                onClick={() => {
                  setSelectedPaths(prev => {
                    const next = new Set(prev);
                    isSelected ? next.delete(path) : next.add(path);
                    return next;
                  });
                }}
                className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors ${
                  isSelected ? 'bg-blue-500/20 text-blue-400' : 'hover:bg-neutral-800 text-neutral-300'
                }`}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => {}}
                  className="w-4 h-4 rounded"
                />
                <span className="text-sm truncate">{path.split('/').pop()}</span>
              </div>
            );
          })}
        </div>
        <div className="flex justify-end gap-2 mt-3 pt-3 border-t border-neutral-800">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-neutral-400 hover:text-white">
            取消
          </button>
          <button
            onClick={() => {
              onAddFiles(Array.from(selectedPaths));
              setSelectedPaths(new Set());
              onClose();
            }}
            className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-lg"
          >
            添加 ({selectedPaths.size})
          </button>
        </div>
      </div>
    </div>
  );
};

export function ForgeChatStage() {
  const {
    sessionId,
    messages,
    addMessage,
    appendLastMessage,
    attachments,
    addAttachment,
    removeAttachment,
    clearAttachments,
    skillDraft,
    setSkillDraft,
    isTyping,
    setIsTyping,
    executorType,
    createSession
  } = useForgeStore();

  const [inputValue, setInputValue] = useState('');
  const [isAttachmentPickerOpen, setIsAttachmentPickerOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isStreamingRef = useRef(false);

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 确保有会话
  useEffect(() => {
    if (!sessionId) {
      createSession();
    }
  }, [sessionId, createSession]);

  const handleSend = async () => {
    if (!inputValue.trim() && attachments.length === 0) return;
    if (!sessionId) return;

    // 添加用户消息
    addMessage('user', inputValue, attachments);
    setInputValue('');
    setIsTyping(true);
    isStreamingRef.current = true;

    const currentAttachments = [...attachments];
    clearAttachments();

    // 添加空的助手消息（用于流式追加）
    addMessage('assistant', '');

    try {
      const token = localStorage.getItem('autonome_access_token');

      await fetchEventSource(`${BASE_URL}/api/skills/forge/session/${sessionId}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          message: inputValue,
          attachments: currentAttachments,
          executor_type: executorType
        }),
        openWhenHidden: true,
        onmessage(event) {
          if (event.event === 'message') {
            try {
              const data = JSON.parse(event.data);
              if (data.type === 'text') {
                appendLastMessage(data.content);
              }
            } catch {}
          } else if (event.event === 'skill_update') {
            try {
              const data = JSON.parse(event.data);
              if (data.type === 'draft') {
                setSkillDraft({ ...skillDraft, ...data.data });
              }
            } catch {}
          } else if (event.event === 'done') {
            isStreamingRef.current = false;
            setIsTyping(false);
          } else if (event.event === 'error') {
            try {
              const data = JSON.parse(event.data);
              appendLastMessage(`\n\n❌ 错误: ${data.content}`);
            } catch {}
            isStreamingRef.current = false;
            setIsTyping(false);
          }
        },
        onclose() {
          isStreamingRef.current = false;
          setIsTyping(false);
        },
        onerror(err) {
          console.error('Forge chat error:', err);
          isStreamingRef.current = false;
          setIsTyping(false);
          throw err;
        }
      });
    } catch (error) {
      console.error('Forge chat error:', error);
      setIsTyping(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* 欢迎消息 */}
      {messages.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center py-8 text-neutral-500">
            <Hammer size={32} className="mx-auto mb-3 text-blue-500" />
            <p className="font-medium text-neutral-300">技能锻造工坊</p>
            <p className="text-sm mt-2">描述您的需求，AI 将帮您锻造标准化技能</p>
            <div className="mt-4 text-xs text-neutral-600 space-y-1">
              <p>示例："帮我写一个用 scanpy 过滤单细胞数据的脚本"</p>
              <p>"写一个 FastQC + MultiQC 质控工作流"</p>
            </div>
          </div>
        </div>
      )}

      {/* 消息列表 */}
      {messages.length > 0 && (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <AnimatePresence>
            {messages.map((msg, idx) => (
              <motion.div
                key={msg.id || idx}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center shrink-0">
                    <Bot size={16} className="text-blue-400" />
                  </div>
                )}
                <div className={`max-w-[85%] ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-neutral-800 text-neutral-200'
                } rounded-2xl px-4 py-3`}>
                  {msg.role === 'assistant' ? (
                    <MarkdownBlock content={msg.content} />
                  ) : (
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  )}
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {msg.attachments.map((att, i) => (
                        <span key={i} className="text-xs bg-black/20 px-2 py-0.5 rounded flex items-center gap-1">
                          <Paperclip size={10} />
                          {att.split('/').pop()}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                    <User size={16} className="text-emerald-400" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {isTyping && messages[messages.length - 1]?.role !== 'assistant' && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center">
                <Loader2 size={16} className="text-blue-400 animate-spin" />
              </div>
              <div className="bg-neutral-800 rounded-2xl px-4 py-3">
                <Sparkles size={16} className="text-blue-400 animate-pulse" />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      )}

      {/* 输入区 */}
      <div className="border-t border-neutral-800 p-4">
        {attachments.length > 0 && (
          <div className="flex gap-2 mb-2 flex-wrap">
            {attachments.map((att, idx) => (
              <span key={idx} className="text-xs bg-blue-500/20 text-blue-300 px-2 py-1 rounded flex items-center gap-1">
                <Paperclip size={10} />
                {att.split('/').pop()}
                <button onClick={() => removeAttachment(att)} className="hover:text-white ml-1">
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => setIsAttachmentPickerOpen(true)}
            className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
            title="添加附件"
          >
            <Paperclip size={18} />
          </button>
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="描述您的技能需求..."
            className="flex-1 bg-neutral-800 border border-neutral-700 rounded-xl px-4 py-2 text-sm text-white resize-none focus:border-blue-500 focus:outline-none"
            rows={2}
          />
          <button
            onClick={handleSend}
            disabled={isTyping || (!inputValue.trim() && attachments.length === 0)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-xl transition-colors"
          >
            <Send size={18} />
          </button>
        </div>
      </div>

      {/* 附件选择器 */}
      <AttachmentPicker
        isOpen={isAttachmentPickerOpen}
        onClose={() => setIsAttachmentPickerOpen(false)}
        onAddFiles={(paths) => paths.forEach(addAttachment)}
        projectId={null}
      />
    </div>
  );
}