"use client";

import { memo, useState, useCallback, useRef, useEffect } from "react";
import { Folder, FileText, X, Loader2, Paperclip, Box, Code, Square, Wrench, FlaskConical, MessageSquare, Brain } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { useUIStore } from "@/store/useUIStore";
import { useChatStore } from "@/store/useChatStore";

// ==========================================
// ✨ ChatInputBox - 独立的输入组件（memo）
// 关键优化：inputValue 状态在组件内部管理
// 每次按键只触发本组件重渲染，不会导致父组件和消息列表重渲染
// ==========================================

interface ChatInputBoxProps {
  // ✨ 核心：onSend 接收消息文本和深度思考开关，由组件内部传递
  onSend: (messageText: string, enableThink?: boolean) => void;
  onStop: () => void;
  onPaste: (e: React.ClipboardEvent) => void;
  isTyping: boolean;
  // ✨ 父组件传入的状态控制
  isActionMenuOpen: boolean;
  setIsActionMenuOpen: (open: boolean) => void;
  isAttachmentPickerOpen: boolean;
  setIsAttachmentPickerOpen: (open: boolean) => void;
  isCodeImportOpen: boolean;
  setIsCodeImportOpen: (open: boolean) => void;
  // ✨ Tools 按钮回调：打开技能中心（基础分析模式）
  onOpenBasicAnalysis?: () => void;
}

// ==========================================
// ✨ 深度思考开关组件 - 持久化到 useChatStore
// ==========================================
const DeepThinkToggle = memo(function DeepThinkToggle() {
  const enableThink = useChatStore(state => state.enableThink);
  const setEnableThink = useChatStore(state => state.setEnableThink);

  return (
    <button
      onClick={() => setEnableThink(!enableThink)}
      className={`p-2 rounded-full transition-all ${
        enableThink
          ? 'text-violet-500 bg-violet-500/10'
          : 'text-neutral-500 hover:text-violet-500 hover:bg-violet-500/10'
      }`}
      title={enableThink ? '深度思考已开启' : '开启深度思考'}
    >
      <Brain size={18} />
    </button>
  );
});

const ChatInputBox = memo(function ChatInputBox({
  onSend,
  onStop,
  onPaste,
  isTyping,
  isActionMenuOpen,
  setIsActionMenuOpen,
  isAttachmentPickerOpen,
  setIsAttachmentPickerOpen,
  isCodeImportOpen,
  setIsCodeImportOpen,
  onOpenBasicAnalysis,
}: ChatInputBoxProps) {
  // ✨ 核心：inputValue 状态在组件内部管理
  // 每次按键只触发本组件重渲染，不会导致父组件重渲染
  const [inputValue, setInputValue] = useState("");

  // ✨ 本地状态：Tools 菜单开关
  const [isToolsMenuOpen, setIsToolsMenuOpen] = useState(false);

  // ✨ refs 用于点击外部检测
  const actionMenuRef = useRef<HTMLDivElement>(null);
  const toolsMenuRef = useRef<HTMLDivElement>(null);

  // ✨ 点击外部关闭菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      // 关闭加号菜单
      if (isActionMenuOpen && actionMenuRef.current && !actionMenuRef.current.contains(target)) {
        setIsActionMenuOpen(false);
      }
      // 关闭工具菜单
      if (isToolsMenuOpen && toolsMenuRef.current && !toolsMenuRef.current.contains(target)) {
        setIsToolsMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isActionMenuOpen, isToolsMenuOpen, setIsActionMenuOpen]);

  // ✨ 精确订阅：只订阅需要的 store 值
  const pendingChatSkill = useWorkspaceStore(state => state.pendingChatSkill);
  const clearPendingChatSkill = useWorkspaceStore(state => state.clearPendingChatSkill);
  const pendingChatAttachments = useWorkspaceStore(state => state.pendingChatAttachments);
  const removePendingChatAttachment = useWorkspaceStore(state => state.removePendingChatAttachment);
  const pastedAttachments = useWorkspaceStore(state => state.pastedAttachments);
  const removePastedAttachment = useWorkspaceStore(state => state.removePastedAttachment);
  const openSkillCenter = useUIStore(state => state.openSkillCenter);

  // ✨ 订阅 Claude Code 会话状态
  const claudeCodeSessionId = useWorkspaceStore(state => state.claudeCodeSessionId);
  const clearClaudeCodeSession = useWorkspaceStore(state => state.clearClaudeCodeSession);

  // ✨ 内部发送处理：获取当前输入值并清空
  // ✨ 防并发：isTyping 时禁止发送，用户必须等待 AI 回复完成
  const handleInternalSend = useCallback(() => {
    if (isTyping) return; // AI 正在回复，拒绝发送
    const hasUploading = pastedAttachments.some(att => att.isUploading);
    const canSend = (inputValue.trim() || pendingChatAttachments.length > 0 || pastedAttachments.length > 0);
    if (hasUploading || !canSend) return;

    // ✨ 传递深度思考开关状态（从 store 读取，持久化）
    onSend(inputValue, useChatStore.getState().enableThink);
    setInputValue(""); // 发送后清空
    // 发送后保持焦点，让用户可以继续输入
    document.getElementById("chat-input-box")?.focus();
  }, [inputValue, onSend, pendingChatAttachments.length, pastedAttachments, isTyping]);

  // ✨ 处理 Enter 键发送
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleInternalSend();
    }
  }, [handleInternalSend]);

  // ✨ 防并发：isTyping 时禁用发送，必须等待 AI 回复完成
  const hasUploading = pastedAttachments.some(att => att.isUploading);
  const canSend = !isTyping && !hasUploading && (inputValue.trim() || pendingChatAttachments.length > 0 || pastedAttachments.length > 0);

  return (
    <div className="w-full bg-white dark:bg-[#1e1e1f] border border-gray-200 dark:border-neutral-800/60 rounded-2xl p-2 focus-within:ring-1 focus-within:ring-blue-500/50 transition-all shadow-sm dark:shadow-xl flex flex-col">
      {/* ✨ 已选技能标签 - 紫色主题区分于文件附件（蓝色） */}
      {pendingChatSkill && (
        <div className="flex items-center gap-2 px-2 pt-1 pb-1 flex-wrap border-b border-gray-100 dark:border-neutral-800/50 mb-1">
          <div className="flex items-center gap-1 px-2 py-1 bg-purple-500/10 border border-purple-500/20 rounded-md text-xs text-purple-300">
            <Box size={10} className="shrink-0" />
            <span className="truncate">{pendingChatSkill.name}</span>
            <button
              onClick={clearPendingChatSkill}
              className="hover:text-white text-neutral-400 transition-colors shrink-0"
              title="移除技能"
            >
              <X size={10} />
            </button>
          </div>
        </div>
      )}

      {/* ✨ Claude Code 会话状态标签 - 青色主题，显示会话已连接 */}
      {claudeCodeSessionId && (
        <div className="flex items-center gap-2 px-2 pt-1 pb-1 flex-wrap border-b border-gray-100 dark:border-neutral-800/50 mb-1">
          <div className="flex items-center gap-1 px-2 py-1 bg-cyan-500/10 border border-cyan-500/20 rounded-md text-xs text-cyan-300">
            <MessageSquare size={10} className="shrink-0" />
            <span className="truncate">Claude Code 会话</span>
            <span className="text-cyan-400/60 font-mono text-[10px]">
              {claudeCodeSessionId.slice(0, 8)}...
            </span>
            <button
              onClick={clearClaudeCodeSession}
              className="hover:text-white text-neutral-400 transition-colors shrink-0 ml-1"
              title="开始新会话"
            >
              <X size={10} />
            </button>
          </div>
        </div>
      )}

      {/* 已附加的项目标签 - 显示在 textarea 上方 */}
      {pendingChatAttachments.length > 0 && (
        <div className="flex items-center gap-2 px-2 pt-1 pb-1 flex-wrap border-b border-gray-100 dark:border-neutral-800/50 mb-1">
          {pendingChatAttachments.map((path, idx) => {
            const isFolder = !path.includes('.') || path.split('/').pop()?.includes('.') === false;
            return (
              <div key={idx} className="flex items-center gap-1 px-2 py-1 bg-blue-500/10 border border-blue-500/20 rounded-md text-xs text-blue-300 max-w-[150px]">
                {isFolder ? <Folder size={10} className="text-purple-400 shrink-0" /> : <FileText size={10} className="shrink-0" />}
                <span className="truncate">{path.split('/').pop()}</span>
                <button
                  onClick={() => removePendingChatAttachment(path)}
                  className="hover:text-white text-neutral-400 transition-colors shrink-0"
                  title="移除"
                >
                  <X size={10} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* ✨ 粘贴的附件预览 - 图片缩略图 + 文件标签 */}
      {pastedAttachments.length > 0 && (
        <div className="flex items-center gap-2 px-2 pt-1 pb-1 flex-wrap border-b border-gray-100 dark:border-neutral-800/50 mb-1">
          {pastedAttachments.map((att) => (
            <div key={att.id} className={`relative rounded-md overflow-hidden border ${
              att.type === 'image'
                ? "w-16 h-16 border-green-500/20 bg-green-500/10"
                : "px-2 py-1 border-orange-500/20 bg-orange-500/10"
            }`}>
              {att.type === 'image' ? (
                <>
                  {/* 图片缩略图预览 */}
                  {att.localUrl && (
                    <img src={att.localUrl} alt="pasted" className="w-full h-full object-cover" />
                  )}
                  {/* 上传中 loading 遮罩 */}
                  {att.isUploading && (
                    <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                      <Loader2 size={16} className="animate-spin text-white" />
                    </div>
                  )}
                </>
              ) : (
                /* 文件标签 */
                <div className="flex items-center gap-1 text-xs text-orange-300">
                  <FileText size={12} />
                  <span className="truncate max-w-[80px]">{att.fileName}</span>
                  {att.isUploading && <Loader2 size={12} className="animate-spin ml-1" />}
                </div>
              )}
              {/* 删除按钮 */}
              <button
                onClick={() => {
                  if (att.localUrl) URL.revokeObjectURL(att.localUrl);
                  removePastedAttachment(att.id);
                }}
                className="absolute top-0 right-0 p-0.5 bg-red-500/80 rounded-bl-sm hover:bg-red-600"
                title="移除"
              >
                <X size={10} className="text-white" />
              </button>
            </div>
          ))}
        </div>
      )}

      <textarea
        id="chat-input-box"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onPaste={onPaste}
        onKeyDown={handleKeyDown}
        disabled={isTyping}
        placeholder={isTyping ? "AI 正在回复中，请等待..." : "Ask anything... (支持 Ctrl+V 粘贴图片或文件)"}
        className="w-full bg-transparent text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-neutral-500 resize-none outline-none max-h-48 min-h-[60px] p-3 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
      />

      {/* 底部操作栏：左侧附件按钮，右侧发送按钮 */}
      <div className="flex justify-between items-center px-2 pb-1 pt-1">
        {/* 左侧: 操作按钮 (Plus 图标) - 点击弹出选项菜单 */}
        <div className="relative" ref={actionMenuRef}>
          <button
            onClick={() => setIsActionMenuOpen(!isActionMenuOpen)}
            className={`p-2 md:p-2 rounded-full transition-all min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 flex items-center justify-center ${isActionMenuOpen ? 'text-blue-500 bg-blue-500/10' : 'text-neutral-500 hover:text-blue-500 hover:bg-blue-500/10'}`}
            title="添加内容"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: isActionMenuOpen ? 'rotate(45deg)' : 'rotate(0deg)', transition: 'transform 0.2s ease' }}>
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </button>

          {/* ✨ 选项菜单 - 类似 Gemini 风格 */}
          <AnimatePresence>
            {isActionMenuOpen && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.15 }}
                className="absolute bottom-full left-0 mb-2 w-56 bg-[#1a1a1c] border border-neutral-700 rounded-xl shadow-2xl overflow-hidden z-50"
              >
                {/* 添加附件选项 */}
                <button
                  onClick={() => {
                    setIsActionMenuOpen(false);
                    setIsAttachmentPickerOpen(true);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-neutral-800/60 transition-colors text-left"
                >
                  <div className="p-2 bg-blue-500/10 rounded-lg">
                    <Paperclip size={18} className="text-blue-400" />
                  </div>
                  <div>
                    <div className="text-sm text-neutral-200">添加附件</div>
                    <div className="text-xs text-neutral-500">上传文件或选择项目文件</div>
                  </div>
                </button>

                {/* 选择技能选项 */}
                <button
                  onClick={() => {
                    setIsActionMenuOpen(false);
                    openSkillCenter();
                  }}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-neutral-800/60 transition-colors text-left border-t border-neutral-800"
                >
                  <div className="p-2 bg-purple-500/10 rounded-lg">
                    <Box size={18} className="text-purple-400" />
                  </div>
                  <div>
                    <div className="text-sm text-neutral-200">选择技能</div>
                    <div className="text-xs text-neutral-500">附加技能到聊天，AI 将直接调用</div>
                  </div>
                </button>

                {/* 导入代码选项 */}
                <button
                  onClick={() => {
                    setIsActionMenuOpen(false);
                    setIsCodeImportOpen(true);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-neutral-800/60 transition-colors text-left border-t border-neutral-800"
                >
                  <div className="p-2 bg-green-500/10 rounded-lg">
                    <Code size={18} className="text-green-400" />
                  </div>
                  <div>
                    <div className="text-sm text-neutral-200">导入代码</div>
                    <div className="text-xs text-neutral-500">粘贴代码片段作为上下文</div>
                  </div>
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* ✨ Tools 按钮 - 只保留基础分析 */}
        <div className="relative" ref={toolsMenuRef}>
          <button
            onClick={() => setIsToolsMenuOpen(!isToolsMenuOpen)}
            className={`p-2 rounded-full transition-all ${isToolsMenuOpen ? 'text-blue-500 bg-blue-500/10' : 'text-neutral-500 hover:text-blue-500 hover:bg-blue-500/10'}`}
            title="基础分析"
          >
            <Wrench size={18} />
          </button>

          {/* ✨ Tools 选项菜单 - 只保留基础分析 */}
          <AnimatePresence>
            {isToolsMenuOpen && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.15 }}
                className="absolute bottom-full left-0 mb-2 w-64 bg-[#1a1a1c] border border-neutral-700 rounded-xl shadow-2xl overflow-hidden z-50"
              >
                {/* 基础分析选项 */}
                <button
                  onClick={() => {
                    setIsToolsMenuOpen(false);
                    // 调用回调函数打开技能中心（基础分析模式）
                    if (onOpenBasicAnalysis) {
                      onOpenBasicAnalysis();
                    } else {
                      openSkillCenter();
                    }
                  }}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-neutral-800/60 transition-colors text-left"
                >
                  <div className="p-2 bg-blue-500/10 rounded-lg">
                    <FlaskConical size={18} className="text-blue-400" />
                  </div>
                  <div>
                    <div className="text-sm text-neutral-200">基础分析</div>
                    <div className="text-xs text-neutral-500">打开技能中心，选择标准化分析流程</div>
                  </div>
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* 弹性空间，让 Tools 按钮和发送按钮分开 */}
        <div className="flex-1" />

        {/* 右侧: 深度思考开关 + 发送按钮 + 停止按钮 */}
        <div className="flex items-center gap-1">
          {/* ✨ 深度思考开关 - 发送按钮左侧，持久化状态 */}
          <DeepThinkToggle />
          {/* ✨ 停止按钮 - 流式输出时显示 */}
          {isTyping && (
            <button
              onClick={onStop}
              className="p-2 md:p-2 bg-red-500 hover:bg-red-600 text-white rounded-full transition-colors min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 flex items-center justify-center"
              title="停止生成"
            >
              <Square size={18} fill="currentColor" />
            </button>
          )}
          {/* 发送按钮 - AI 回复期间禁用（防并发） */}
          <button
            onClick={handleInternalSend}
            disabled={!canSend}
            className="p-2 md:p-2 bg-blue-600 hover:bg-blue-700 dark:bg-white dark:text-black dark:hover:bg-neutral-200 disabled:bg-gray-300 dark:disabled:bg-neutral-800 disabled:text-neutral-500 dark:disabled:text-neutral-500 text-white rounded-full transition-colors min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 flex items-center justify-center"
            title={isTyping ? "请等待 AI 回复完成" : "发送"}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          </button>
        </div>
      </div>
    </div>
  );
});

export { ChatInputBox };