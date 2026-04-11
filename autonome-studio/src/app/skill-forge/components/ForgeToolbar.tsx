/**
 * Gemini 风格底部工具栏
 *
 * 设计参考：Gemini 消息输入框
 *
 * 特点：
 * - 圆角药丸形状的输入容器
 * - 左侧：Plus 按钮（附件上传）
 * - 中间：输入框（支持多行）
 * - 右侧：工具模式选择器 + 发送按钮
 * - 底部：快捷操作提示
 *
 * Tool 选择器选项：
 * | 模式 | 说明 |
 * |------|------|
 * | chat | 对话锻造（默认） |
 * | code_import | 代码导入 - AI 分析推断参数 |
 * | skill_import | SKILL 导入 - 上传压缩包解析 |
 */

'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Plus, Send, ChevronDown, MessageSquare, Code, FileArchive, Loader2, X, Paperclip, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useForgeStore, ToolMode, TOOL_MODE_CONFIG } from '@/store/useForgeStore';

// ==========================================
// 工具模式选择器组件
// ==========================================

interface ToolModeSelectorProps {
  value: ToolMode;
  onChange: (mode: ToolMode) => void;
  disabled?: boolean;
}

function ToolModeSelector({ value, onChange, disabled }: ToolModeSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  const modeIcons: Record<ToolMode, React.ReactNode> = {
    chat: <MessageSquare size={14} />,
    code_import: <Code size={14} />,
    skill_import: <FileArchive size={14} />
  };

  const currentConfig = TOOL_MODE_CONFIG[value];

  return (
    <div ref={dropdownRef} className="relative">
      {/* 主按钮 */}
      <button
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-neutral-700/50 disabled:opacity-50 text-neutral-300 text-sm rounded-full transition-colors"
      >
        {modeIcons[value]}
        <span className="font-medium">{currentConfig.label}</span>
        <ChevronDown size={14} className={`transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* 下拉菜单 */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="absolute bottom-full right-0 mb-2 w-56 bg-neutral-900 border border-neutral-700 rounded-2xl shadow-2xl overflow-hidden z-50"
          >
            <div className="p-2">
              {(Object.keys(TOOL_MODE_CONFIG) as ToolMode[]).map((mode) => {
                const config = TOOL_MODE_CONFIG[mode];
                const isSelected = mode === value;

                return (
                  <button
                    key={mode}
                    onClick={() => {
                      onChange(mode);
                      setIsOpen(false);
                    }}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors ${
                      isSelected
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'text-neutral-300 hover:bg-neutral-800'
                    }`}
                  >
                    <div className={`p-1.5 rounded-lg ${
                      isSelected ? 'bg-blue-500/30' : 'bg-neutral-800'
                    }`}>
                      {modeIcons[mode]}
                    </div>
                    <div className="text-left">
                      <div className="text-sm font-medium">{config.label}</div>
                      <div className="text-xs text-neutral-500">{config.description}</div>
                    </div>
                    {isSelected && (
                      <div className="ml-auto w-1.5 h-1.5 rounded-full bg-blue-400" />
                    )}
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ==========================================
// 附件预览标签
// ==========================================

interface AttachmentTagProps {
  filename: string;
  onRemove: () => void;
}

function AttachmentTag({ filename, onRemove }: AttachmentTagProps) {
  // 获取文件扩展名图标
  const getIcon = () => {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (['py'].includes(ext || '')) return <Code size={12} className="text-green-400" />;
    if (['r', 'R'].includes(ext || '')) return <Code size={12} className="text-blue-400" />;
    if (['zip', 'tar', 'gz', 'tgz'].includes(ext || '')) return <FileArchive size={12} className="text-orange-400" />;
    return <Paperclip size={12} />;
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className="flex items-center gap-1.5 px-3 py-1.5 bg-neutral-800 border border-neutral-700 text-neutral-300 text-sm rounded-full"
    >
      {getIcon()}
      <span className="max-w-[120px] truncate">{filename}</span>
      <button
        onClick={onRemove}
        className="ml-1 p-0.5 hover:bg-neutral-700 rounded-full transition-colors"
      >
        <X size={12} />
      </button>
    </motion.div>
  );
}

// ==========================================
// 主组件：ForgeToolbar (Gemini 风格)
// ==========================================

interface ForgeToolbarProps {
  onSendMessage: (message: string, attachments: File[]) => void;
  onOpenFileUploader: () => void;
  isTyping: boolean;
  attachments: File[];
  onRemoveAttachment: (index: number) => void;
}

export function ForgeToolbar({
  onSendMessage,
  onOpenFileUploader,
  isTyping,
  attachments,
  onRemoveAttachment
}: ForgeToolbarProps) {
  const { toolMode, setToolMode } = useForgeStore();
  const [inputValue, setInputValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 自动调整输入框高度（最小4行，最大8行）
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      // 设置最小高度约为4行（约80px）
      const minHeight = 80;
      const maxHeight = 160;
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${Math.max(minHeight, Math.min(scrollHeight, maxHeight))}px`;
    }
  }, [inputValue]);

  // 发送消息
  const handleSend = useCallback(() => {
    if (isTyping) return;
    if (!inputValue.trim() && attachments.length === 0) return;

    onSendMessage(inputValue, attachments);
    setInputValue('');
  }, [isTyping, inputValue, attachments, onSendMessage]);

  // 键盘事件处理
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="p-4 bg-neutral-900">
      {/* 主输入容器 - 药丸形状 */}
      <div
        className={`relative bg-neutral-800/80 border rounded-3xl transition-all duration-200 ${
          isFocused
            ? 'border-blue-500/50 shadow-[0_0_0_2px_rgba(59,130,246,0.1)]'
            : 'border-neutral-700 hover:border-neutral-600'
        }`}
      >
        {/* 附件预览区 */}
        {attachments.length > 0 && (
          <div className="flex gap-2 p-3 pb-0 flex-wrap">
            <AnimatePresence>
              {attachments.map((file, index) => (
                <AttachmentTag
                  key={index}
                  filename={file.name}
                  onRemove={() => onRemoveAttachment(index)}
                />
              ))}
            </AnimatePresence>
          </div>
        )}

        {/* 主输入行 */}
        <div className="flex items-end gap-1 p-2">
          {/* 左侧：Plus 按钮 */}
          <button
            onClick={onOpenFileUploader}
            disabled={isTyping}
            className="shrink-0 p-2.5 text-neutral-400 hover:text-white hover:bg-neutral-700/50 disabled:opacity-50 rounded-full transition-colors"
            title="添加附件"
          >
            <Plus size={20} strokeWidth={2} />
          </button>

          {/* 中间：输入框 */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={
                toolMode === 'chat'
                  ? '描述您的技能需求...'
                  : toolMode === 'code_import'
                  ? '粘贴代码，AI 将自动推断参数...'
                  : '上传技能包后点击发送...'
              }
              disabled={isTyping}
              rows={4}
              className="w-full bg-transparent px-2 py-2 text-white text-sm resize-none focus:outline-none disabled:opacity-50 placeholder:text-neutral-500"
              style={{ minHeight: '80px', maxHeight: '160px' }}
            />
          </div>

          {/* 右侧：工具选择器 + 发送按钮 */}
          <div className="flex items-center gap-1 shrink-0">
            <ToolModeSelector
              value={toolMode}
              onChange={setToolMode}
              disabled={isTyping}
            />

            <button
              onClick={handleSend}
              disabled={isTyping || (!inputValue.trim() && attachments.length === 0)}
              className={`p-2.5 rounded-full transition-all duration-200 ${
                (inputValue.trim() || attachments.length > 0) && !isTyping
                  ? 'bg-blue-500 hover:bg-blue-400 text-white shadow-lg shadow-blue-500/25'
                  : 'bg-neutral-700/50 text-neutral-500'
              }`}
            >
              {isTyping ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <Send size={18} />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* 底部提示 */}
      <div className="mt-2 flex items-center justify-center gap-4 text-xs text-neutral-500">
        <span className="flex items-center gap-1">
          <Sparkles size={12} className="text-blue-400" />
          AI 驱动的技能开发
        </span>
        <span>Enter 发送 · Shift+Enter 换行</span>
      </div>
    </div>
  );
}