/**
 * ChatStage.tsx - 主聊天组件（重构版）
 *
 * 性能优化重构：
 * 1. 提取 hooks 到独立文件，减少主组件复杂度
 * 2. 使用精确的 Zustand 订阅，避免不必要的重渲染
 * 3. 组件拆分，提高代码可维护性
 *
 * 主要职责：
 * - 组合各种 hooks 和子组件
 * - 管理聊天 UI 布局
 * - 协调各功能模块
 */
"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { ArrowDown, X, Eye, Download, Loader2, Code } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

// ==========================================
// 状态管理导入
// ==========================================
import { useChatStore, ChatState, Message } from "@/store/useChatStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useUIStore } from "@/store/useUIStore";

// ==========================================
// 性能优化 Hooks（从本文件提取）
// ==========================================
import { useSmartScroll } from "@/hooks/useSmartScroll";
import { useImmediateStream } from "@/hooks/useImmediateStream";
import { useFilePreview } from "@/hooks/useFilePreview";
import { useMessageActions } from "@/hooks/useMessageActions";
import { usePasteUpload } from "@/hooks/usePasteUpload";
import { useChatEventListeners } from "@/hooks/useChatEventListeners";
import { useChatStream } from "@/hooks/useChatStream";

// ==========================================
// 子组件导入
// ==========================================
import { ChatInputBox } from "./ChatInputBox";
import { MemoizedMessageItem } from "./MemoizedMessageItem";
import { VirtualizedMessageList } from "./VirtualizedMessageList";
import {
  TablePreview,
  AttachmentPicker,
} from "./components";
import { BASE_URL, getToken } from "@/lib/api";

// ==========================================
// 主组件
// ==========================================
export function ChatStage() {
  // ==========================================
  // 状态订阅 - 使用精确订阅避免不必要的重渲染
  // ==========================================
  const currentProjectId = useWorkspaceStore(state => state.currentProjectId);
  const currentSessionId = useWorkspaceStore(state => state.currentSessionId);
  const setCurrentSessionId = useWorkspaceStore(state => state.setCurrentSessionId);
  const pendingChatAttachments = useWorkspaceStore(state => state.pendingChatAttachments);
  // ✨ 新增：引入更新附件状态的函数
  const setPendingChatAttachments = useWorkspaceStore(state => state.setPendingChatAttachments);

  const messages = useChatStore((state: ChatState) => state.messages);
  const setMessages = useChatStore((state: ChatState) => state.setMessages);
  const addMessage = useChatStore((state: ChatState) => state.addMessage);
  const isTyping = useChatStore((state: ChatState) => state.isTyping);
  const streamingContent = useChatStore((state: ChatState) => state.streamingContent);
  const setStreamingContent = useChatStore((state: ChatState) => state.setStreamingContent);
  const clearStreamingContent = useChatStore((state: ChatState) => state.clearStreamingContent);
  const commitStreamingContent = useChatStore((state: ChatState) => state.commitStreamingContent);
  const setStreamingMessageId = useChatStore((state: ChatState) => state.setStreamingMessageId);

  const openSkillCenter = useUIStore(state => state.openSkillCenter);
  const setSkillFilterMode = useUIStore(state => state.setSkillFilterMode);

  // ==========================================
  // Refs
  // ==========================================
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // ==========================================
  // 本地 UI 状态
  // ==========================================
  const [isActionMenuOpen, setIsActionMenuOpen] = useState(false);
  const [isAttachmentPickerOpen, setIsAttachmentPickerOpen] = useState(false);
  const [isCodeImportOpen, setIsCodeImportOpen] = useState(false);
  const [importedCode, setImportedCode] = useState("");

  // ==========================================
  // 智能滚动 Hook
  // ==========================================
  const { isAtBottom, isPaused, isAtBottomRef, isPausedRef, scrollToBottom, resumeAutoScroll } = useSmartScroll(scrollContainerRef, {
    bottomThreshold: 150,
    smoothScroll: true,
    scrollDuration: 100,
  });

  // ==========================================
  // 即时渲染流式输出 Hook
  // ==========================================
  const handleTypewriterUpdate = useCallback((content: string) => {
    setStreamingContent(content);
    // 使用 ref 读取最新值，避免闭包过期导致滚动失效
    if (isAtBottomRef.current && !isPausedRef.current) {
      requestAnimationFrame(() => scrollToBottom());
    }
  }, [setStreamingContent, isAtBottomRef, isPausedRef, scrollToBottom]);

  const { append: appendStream, reset: resetStream, getCurrentContent } = useImmediateStream({
    onContentUpdate: handleTypewriterUpdate,
    minUpdateInterval: 16,
  });

  // ==========================================
  // 文件预览 Hook
  // ==========================================
  const {
    previewData,
    previewType,
    previewContent,
    previewLanguage,
    isPreviewLoading,
    handlePreviewAsset,
    handleDownloadAsset,
    closePreview,
  } = useFilePreview();

  // ==========================================
  // 粘贴上传 Hook
  // ==========================================
  const {
    pastedAttachments,
    handlePaste,
    cleanupPastedAttachments,
  } = usePasteUpload();

  // ==========================================
  // 聊天流式消息 Hook
  // ==========================================
  const {
    handleSend,
    handleStop,
    abortControllerRef,
    isStreamingRef,
  } = useChatStream({
    getCurrentContent,
    appendStream,
    resetStream,
    clearStreamingContent,
    setStreamingMessageId,
    commitStreamingContent,
    scrollToBottom,
    isAtBottomRef,
    isPausedRef,
  });

  // ==========================================
  // 消息操作 Hook
  // ==========================================
  const {
    handleRetry,
    handleEditResend,
    handleInterpret,
    handleSendRef,
  } = useMessageActions({
    getCurrentContent,
    resetStream,
    clearStreamingContent,
    setStreamingMessageId,
    commitStreamingContent,
    appendStream,
    abortControllerRef,
    isStreamingRef,
    isInsufficientCreditsRef: useRef(false),
  });

  // 更新 handleSendRef 引用
  useEffect(() => {
    handleSendRef.current = handleSend;
  }, [handleSend, handleSendRef]);

  // ==========================================
  // 新消息到达时自动滚动到底部
  // 防止用户发送消息后聊天窗口不滚动
  // ==========================================
  useEffect(() => {
    if (messages.length > 0 && isAtBottomRef.current && !isPausedRef.current) {
      requestAnimationFrame(() => scrollToBottom());
    }
  }, [messages.length, scrollToBottom, isAtBottomRef, isPausedRef]);

  // ==========================================
  // 事件监听器 Hook
  // ==========================================
  useChatEventListeners({
    messagesEndRef,
  });

  // ==========================================
  // Fetch messages when session changes
  // ==========================================
  useEffect(() => {
    const fetchMessages = async () => {
      if (!currentSessionId) {
        setMessages([]);
        return;
      }

      if (isStreamingRef.current) {
        return;
      }

      const token = getToken();
      try {
        const res = await fetch(`${BASE_URL}/api/chat/sessions/${currentSessionId}/messages`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (data.data && data.data.length > 0) {
          const formattedMessages = data.data.map((msg: { role: string; content: string; id: number; attachments?: any }) => ({
            id: String(msg.id),
            role: msg.role as 'user' | 'assistant',
            content: msg.content,
            timestamp: Date.now(),
            attachments: msg.attachments
          }));
          setMessages(formattedMessages);
        } else {
          setMessages([]);
        }
      } catch (e) {
        console.error('Failed to fetch messages:', e);
        setMessages([]);
      }
    };
    fetchMessages();
  }, [currentSessionId, setMessages, isStreamingRef]);

  // ==========================================
  // 打开技能中心（基础分析模式）
  // ==========================================
  const handleOpenBasicAnalysis = useCallback(() => {
    setSkillFilterMode('basic');
    openSkillCenter();
  }, [setSkillFilterMode, openSkillCenter]);

  // ==========================================
  // 发送消息包装函数
  // ==========================================
  const handleSendWrapper = useCallback((messageText: string, contextFiles?: string[]) => {
    handleSend(messageText, contextFiles, undefined, pastedAttachments, cleanupPastedAttachments);
  }, [handleSend, pastedAttachments, cleanupPastedAttachments]);

  // ==========================================
  // 渲染
  // ==========================================
  const isChatEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full w-full bg-white dark:bg-[#131314]">

      {isChatEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center px-4 pb-20 animate-in fade-in duration-500">
          <h1 className="text-3xl md:text-4xl font-semibold text-gray-900 dark:text-neutral-200 mb-8 tracking-tight">
            What do you want to analyze?
          </h1>

          <div className="w-full max-w-3xl">
            <ChatInputBox
              onSend={handleSendWrapper}
              onStop={handleStop}
              onPaste={handlePaste}
              isTyping={isTyping}
              isActionMenuOpen={isActionMenuOpen}
              setIsActionMenuOpen={setIsActionMenuOpen}
              isAttachmentPickerOpen={isAttachmentPickerOpen}
              setIsAttachmentPickerOpen={setIsAttachmentPickerOpen}
              isCodeImportOpen={isCodeImportOpen}
              setIsCodeImportOpen={setIsCodeImportOpen}
              onOpenBasicAnalysis={handleOpenBasicAnalysis}
            />

          </div>
        </div>
      ) : (
        <>
          <div
            ref={scrollContainerRef}
            className="flex-1 overflow-y-auto px-2 md:px-4 pt-6 pb-4 smooth-scroll-container bg-white dark:bg-[#131314]"
          >
            <VirtualizedMessageList
              messages={messages}
              isTyping={isTyping}
              streamingContent={streamingContent}
              currentProjectId={currentProjectId ?? undefined}
              onPreviewAsset={handlePreviewAsset}
              onDownloadAsset={handleDownloadAsset}
              onInterpret={(files, code, userMsg) => handleInterpret(files, code, userMsg, handleSend)}
              onRetry={handleRetry}
              onEditResend={handleEditResend}
              scrollContainerRef={scrollContainerRef}
              messagesEndRef={messagesEndRef}

              // ✨ 核心修改：无缝衔接的占位思考动画
              footer={
                // 触发条件：正在请求中，且最后一条是"空 assistant 消息"，倒数第二条是"用户消息"
                // 这代表网络请求在路上，后端尚未返回有效内容，AI气泡已建立但内容为空
                isTyping && messages.length >= 2 &&
                messages[messages.length - 1].role === 'assistant' &&
                messages[messages.length - 1].content === '' &&
                messages[messages.length - 2].role === 'user' ? (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex flex-col group items-start max-w-4xl mx-auto w-full transition-all duration-300 mt-2"
                  >
                    <div className="flex items-start gap-0 md:gap-4 w-full">
                      {/* 统一的 AI 头像（与真实消息保持完全一致） */}
                      <div className="hidden md:flex w-8 h-8 rounded-full items-center justify-center shrink-0 overflow-hidden bg-[#1a1a1c] border border-neutral-700/60 shadow-sm">
                        <img src="/ai-avatar.png" alt="AI Avatar" className="w-full h-full object-cover scale-[1.15]" />
                      </div>

                      {/* 占位气泡 */}
                      <div className="flex-1 min-w-0 rounded-2xl px-3 md:px-5 py-3 md:py-4 bg-transparent">
                        <div className="flex items-center gap-2 text-violet-500 dark:text-violet-400 text-sm bg-violet-50 dark:bg-violet-500/10 px-3 py-2 rounded-lg border border-violet-100 dark:border-violet-500/20 w-fit">
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span className="font-medium tracking-wide">Processing...</span>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                ) : null
              }
            />

            <button
              onClick={() => {
                scrollToBottom();
                resumeAutoScroll();
              }}
              className={`scroll-to-bottom-btn ${!isAtBottom ? 'visible' : ''}`}
            >
              <ArrowDown size={16} />
              <span>滚动到底部</span>
            </button>

          </div>

          <div className="shrink-0 px-2 md:px-4 pt-2 pb-3 md:pb-3 bg-white dark:bg-[#131314] pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
            <div className="w-full md:max-w-4xl md:mx-auto">
              <ChatInputBox
                onSend={handleSendWrapper}
                onStop={handleStop}
                onPaste={handlePaste}
                isTyping={isTyping}
                isActionMenuOpen={isActionMenuOpen}
                setIsActionMenuOpen={setIsActionMenuOpen}
                isAttachmentPickerOpen={isAttachmentPickerOpen}
                setIsAttachmentPickerOpen={setIsAttachmentPickerOpen}
                isCodeImportOpen={isCodeImportOpen}
                setIsCodeImportOpen={setIsCodeImportOpen}
                onOpenBasicAnalysis={handleOpenBasicAnalysis}
              />
              <div className="text-center mt-2 text-[10px] text-gray-400 dark:text-neutral-500">
                Autonome Copilot can make mistakes. Check important info.
              </div>
            </div>
          </div>
        </>
      )}

      {/* 文件预览弹窗 */}
      {previewData && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 md:p-12 animate-in fade-in duration-200">
          <div className="bg-white dark:bg-[#1a1a1c] border border-gray-200 dark:border-[#2d2d30] rounded-2xl w-full max-w-5xl h-full flex flex-col shadow-2xl overflow-hidden relative animate-in zoom-in-95 duration-200">

            <div className="h-14 shrink-0 border-b border-gray-200 dark:border-[#2d2d30] px-6 flex items-center justify-between bg-gray-50 dark:bg-[#1e1e20]">
              <div className="flex items-center gap-3 overflow-hidden">
                <Eye size={18} className="text-emerald-500 dark:text-emerald-400 shrink-0"/>
                <h3 className="text-gray-900 dark:text-white font-medium text-sm tracking-wide truncate max-w-lg">{previewData.filename}</h3>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => handleDownloadAsset(previewData.url, previewData.filename)} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 dark:bg-blue-500/10 dark:hover:bg-blue-500/20 dark:text-blue-400 text-xs font-medium rounded-lg transition-colors border border-blue-200 dark:border-blue-500/20">
                  <Download size={14} /> 保存到本地
                </button>
                <div className="w-px h-4 bg-gray-300 dark:bg-neutral-800 mx-1"></div>
                <button onClick={closePreview} className="p-1.5 text-gray-500 hover:text-gray-900 hover:bg-gray-200 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-neutral-800 rounded-lg transition-colors">
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-auto p-6 flex items-start justify-center bg-gray-100 dark:bg-[#121212] relative">
              {isPreviewLoading ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-gray-500 dark:text-neutral-500">
                  <Loader2 size={32} className="animate-spin text-emerald-500" />
                  <span className="text-sm tracking-widest">安全加载中...</span>
                </div>
              ) : previewType === 'image' && previewContent ? (
                <img src={previewContent} alt="Preview" className="max-w-full max-h-full object-contain rounded shadow-md dark:drop-shadow-2xl" />
              ) : previewType === 'pdf' && previewContent ? (
                <iframe src={previewContent} className="w-full h-full rounded-xl border border-gray-200 dark:border-neutral-800 bg-white" title="PDF Preview" />
              ) : previewType === 'table' && previewContent ? (
                <div className="w-full h-full bg-[#1a1a1a] rounded-xl border border-neutral-800 overflow-hidden">
                  <TablePreview data={previewContent} />
                </div>
              ) : previewType === 'code' && previewContent ? (
                <div className="w-full h-full bg-[#1e1e1e] rounded-xl border border-neutral-800 overflow-hidden">
                  <SyntaxHighlighter
                    style={vscDarkPlus}
                    language={previewLanguage || 'text'}
                    PreTag="div"
                    customStyle={{
                      margin: 0,
                      padding: '1.25rem',
                      borderRadius: 0,
                      fontSize: '0.875rem',
                      backgroundColor: '#1e1e1e',
                      height: '100%',
                      overflow: 'auto',
                    }}
                    codeTagProps={{
                      style: {
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                      }
                    }}
                  >
                    {previewContent}
                  </SyntaxHighlighter>
                </div>
              ) : previewType === 'text' && previewContent ? (
                <div className="w-full h-full bg-white dark:bg-[#1e1e1e] rounded-xl border border-gray-200 dark:border-neutral-800 p-4 overflow-auto custom-scrollbar">
                  <pre className="text-[13px] leading-relaxed text-gray-800 dark:text-neutral-300 font-mono whitespace-pre-wrap">{previewContent}</pre>
                </div>
              ) : null}
            </div>

          </div>
        </div>
      )}

      {/* 附件选择器弹窗 */}
      <AttachmentPicker
        isOpen={isAttachmentPickerOpen}
        onClose={() => setIsAttachmentPickerOpen(false)}
        projectId={currentProjectId}
        onAddFiles={(paths) => {
          // 去重并合并新旧附件
          const newPaths = [...new Set([...pendingChatAttachments, ...paths])];
          // ✨ 修复：取消注释，真正触发状态更新
          setPendingChatAttachments(newPaths);
        }}
      />

      {/* 导入代码弹窗 */}
      <AnimatePresence>
        {isCodeImportOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center"
          >
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setIsCodeImportOpen(false)} />
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="relative w-[600px] max-h-[70vh] bg-[#1a1a1c] border border-neutral-700 rounded-xl shadow-2xl flex flex-col"
            >
              <div className="shrink-0 border-b border-neutral-800 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Code size={18} className="text-green-400" />
                  <h3 className="text-sm font-semibold text-neutral-200">导入代码</h3>
                </div>
                <button onClick={() => setIsCodeImportOpen(false)} className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg">
                  <X size={16} />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-4">
                <p className="text-xs text-neutral-500 mb-3">粘贴代码片段，将作为对话上下文发送给 AI 助手。</p>
                <textarea
                  value={importedCode}
                  onChange={(e) => setImportedCode(e.target.value)}
                  placeholder="在此粘贴代码..."
                  className="w-full h-64 bg-neutral-900 border border-neutral-800 rounded-lg p-3 text-sm text-neutral-300 font-mono resize-none outline-none focus:border-green-500/50 transition-colors placeholder:text-neutral-600"
                />
              </div>

              <div className="shrink-0 border-t border-neutral-800 px-4 py-3 flex justify-end gap-2">
                <button
                  onClick={() => setIsCodeImportOpen(false)}
                  className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={() => {
                    if (importedCode.trim()) {
                      const codeMessage = `请帮我分析以下代码：\n\`\`\`\n${importedCode}\n\`\`\`\n`;
                      handleSendWrapper(codeMessage);
                      setImportedCode("");
                      setIsCodeImportOpen(false);
                    }
                  }}
                  disabled={!importedCode.trim()}
                  className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
                >
                  <Code size={14} />
                  导入代码
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}