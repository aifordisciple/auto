/**
 * ChatStage.tsx - 主聊天组件（Vercel AI SDK 重构版）
 *
 * 重构要点：
 * 1. 使用 Vercel AI SDK useChat hook 替代手动 SSE 流管理
 * 2. useChatSync 桥接将 useChat 状态同步到 Zustand store
 * 3. 移除 useImmediateStream / useChatStream / streamingContent 相关逻辑
 * 4. 消息列表直接读取 useChat.messages，isLoading 替代 isTyping
 *
 * 主要职责：
 * - 组合各种 hooks 和子组件
 * - 管理聊天 UI 布局
 * - 协调各功能模块
 */
"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { ArrowDown, X, Eye, Download, Loader2, Code } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';

// ==========================================
// 状态管理导入
// ==========================================
import { useChatStore, ChatState } from "@/store/useChatStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { useUIStore } from "@/store/useUIStore";

// ==========================================
// 性能优化 Hooks
// ==========================================
import { useSmartScroll } from "@/hooks/useSmartScroll";
import { useFilePreview } from "@/hooks/useFilePreview";
import { useMessageActions } from "@/hooks/useMessageActions";
import { usePasteUpload } from "@/hooks/usePasteUpload";
import { useChatEventListeners } from "@/hooks/useChatEventListeners";
import { useChatSync } from "@/hooks/useChatSync";

// ==========================================
// 子组件导入
// ==========================================
import { ChatInputBox } from "./ChatInputBox";
import { QueueIndicator } from "./QueueIndicator";
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
  const pendingChatAttachments = useWorkspaceStore(state => state.pendingChatAttachments);
  // 新增：引入更新附件状态的函数
  const setPendingChatAttachments = useWorkspaceStore(state => state.setPendingChatAttachments);

  // Store 状态 — 仍需 setMessages 用于历史加载
  const setMessages = useChatStore((state: ChatState) => state.setMessages);

  const openSkillCenter = useUIStore(state => state.openSkillCenter);
  const setSkillFilterMode = useUIStore(state => state.setSkillFilterMode);

  // ==========================================
  // Vercel AI SDK useChat hook
  // 核心流式通信由 useChat 管理，不再手动 SSE
  // ==========================================
  // useMemo 确保 transport 实例稳定，避免每次渲染重建导致 useChat 状态丢失
  // ⚠️ 关键：不将 currentSessionId / pendingChatAttachments 放入依赖数组！
  // 原因：headers/body 使用函数形式，每次请求时自动读取最新值。
  // 如果放入依赖，后端返回 session_info → currentSessionId 变化 → transport 重建
  // → useChat 内部状态丢失 → 消息被清空 → UI 重置为初始状态
  const chatTransport = useMemo(() => new DefaultChatTransport({
    api: '/api/chat',
    // 注入 JWT 认证头，BFF 代理从 header 中提取 token 转发给后端
    // 使用函数形式确保每次请求都获取最新 token
    headers: () => {
      const token = getToken();
      return token ? { Authorization: `Bearer ${token}` } : {};
    },
    // 通过 body 传递上下文信息给 BFF 代理（函数形式确保获取最新值）
    body: () => ({
      data: {
        projectId: useWorkspaceStore.getState().currentProjectId,
        sessionId: useWorkspaceStore.getState().currentSessionId,
        contextFiles: useWorkspaceStore.getState().pendingChatAttachments,
      },
    }),
  }), []);

  const {
    messages: aiMessages,
    status,
    stop,
    sendMessage,
    setMessages: setAiMessages,
    error: chatError,
  } = useChat({
    transport: chatTransport,
    onError: (error) => {
      console.error('[useChat] Stream error:', error);
    },
    onFinish: ({ finishReason }) => {
      console.log('[useChat] Stream finished:', finishReason);
    },
  });

  // v5 API: status 替代 isLoading
  // 'submitted' | 'streaming' 表示正在请求
  const isLoading = status === 'submitted' || status === 'streaming';

  // ==========================================
  // useChatSync 桥接：将 useChat 状态同步到 Zustand store
  // 供其他组件（如 SessionSidebar）读取会话 ID、计费等
  // ==========================================
  useChatSync({ messages: aiMessages, isLoading });

  // ==========================================
  // 直接从 useChat.messages 渲染（不经过 store 中转）
  // UIMessage.parts → 提取文本 → 转为 store Message 格式
  // 这样避免 mirroredMessages 同步延迟导致 UI 不更新
  // ==========================================
  const messages = useMemo(() => aiMessages.map(msg => ({
    id: msg.id,
    role: msg.role as 'user' | 'assistant' | 'system',
    content: (msg.parts ?? [])
      .filter((p): p is typeof p & { type: 'text' } => p.type === 'text')
      .map(p => (p as { type: 'text'; text: string }).text)
      .join(''),
    timestamp: Date.now(),
  })), [aiMessages]);
  const isTyping = isLoading;

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
  // 消息操作 Hook（简化版，不再依赖 stream refs）
  // ==========================================
  const {
    handleRetry,
    handleEditResend,
    handleInterpret,
  } = useMessageActions();

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
  // ⚠️ 关键保护：流式输出中不重新加载，避免清空正在接收的消息
  // ==========================================
  useEffect(() => {
    const fetchMessages = async () => {
      if (!currentSessionId) {
        setMessages([]);
        setAiMessages([]);
        return;
      }

      // 流式输出中不重新加载（这是"发送后重置"bug 的另一个原因）
      if (isLoading) return;

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
  }, [currentSessionId, setMessages, setAiMessages, isLoading]);

  // ==========================================
  // 打开技能中心（基础分析模式）
  // ==========================================
  const handleOpenBasicAnalysis = useCallback(() => {
    setSkillFilterMode('basic');
    openSkillCenter();
  }, [setSkillFilterMode, openSkillCenter]);

  // ==========================================
  // 发送消息包装函数 — 调用 useChat.append
  // ==========================================
  const handleSendWrapper = useCallback((messageText: string, _contextFiles?: string[]) => {
    // 清理粘贴附件
    cleanupPastedAttachments();

    // 调用 sendMessage 发送消息（v5 API）
    sendMessage({ text: messageText });

    // 自动滚动到底部
    if (isAtBottomRef.current && !isPausedRef.current) {
      requestAnimationFrame(() => scrollToBottom());
    }
  }, [sendMessage, cleanupPastedAttachments, isAtBottomRef, isPausedRef, scrollToBottom]);

  // ==========================================
  // 停止生成 — 调用 useChat.stop
  // ==========================================
  const handleStop = useCallback(() => {
    stop();
  }, [stop]);

  // ==========================================
  // 渲染
  // ==========================================
  // ⚠️ 不再用 isChatEmpty 切换视图！
  // 原因：sendMessage 是异步的，调用后 React 还没重渲染，isChatEmpty 仍为 true，
  // UI 卡在居中输入框视图。等 aiMessages 更新后才切换，导致首条消息无 processing 状态。
  // 修复：始终渲染消息列表，空列表时在列表上方显示欢迎语。
  const isChatEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full w-full bg-white dark:bg-[#131314]">

      {/* 空聊天时显示居中欢迎语 + 输入框 */}
      {isChatEmpty && !isLoading && (
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
      )}

      {/* 有消息或正在加载时，始终渲染消息列表 */}
      {(!isChatEmpty || isLoading) && (
        <>
          <div
            ref={scrollContainerRef}
            className="flex-1 overflow-y-auto px-2 md:px-4 pt-6 pb-4 smooth-scroll-container bg-white dark:bg-[#131314]"
          >
            <VirtualizedMessageList
              messages={messages}
              isTyping={isTyping}
              currentProjectId={currentProjectId ?? undefined}
              onPreviewAsset={handlePreviewAsset}
              onDownloadAsset={handleDownloadAsset}
              onInterpret={(files, code, userMsg) => handleInterpret(files, code, userMsg, handleSendWrapper)}
              onRetry={handleRetry}
              onEditResend={handleEditResend}
              scrollContainerRef={scrollContainerRef}
              messagesEndRef={messagesEndRef}
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
            {/* ✨ 消息队列指示器（输入框上方） */}
            <QueueIndicator />
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