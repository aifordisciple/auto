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
import { toast } from 'sonner';

// ==========================================
// 状态管理导入
// ==========================================
import { useChatStore, ChatState, MessageAttachments } from "@/store/useChatStore";
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
import { DAGProgressView } from "./DAGProgressView";
import { fetchAPI, getToken } from "@/lib/api";

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
  // ✨ 待发送的图片/文件路径缓冲区
  // 解决时序问题：sendMessage 是异步的，body() 在 fetch 发起时才读取，
  // 但 cleanupPastedAttachments() 可能在 body() 读取前就清空了 store。
  // 使用 ref 缓冲：handleSendWrapper 提取路径存入 ref → body() 从 ref 读取 → 发送后清空 ref
  const pendingImagesRef = useRef<string[]>([]);
  const pendingFilesRef = useRef<string[]>([]);
  // ✨ 待关联到用户消息的 attachments（发送后通过 useChatSync 关联）
  const pendingAttachmentsRef = useRef<MessageAttachments | null>(null);

  // ==========================================
  // useMemo 确保 transport 实例稳定，避免每次渲染重建导致 useChat 状态丢失
  // ⚠️ 关键：不将 currentSessionId / pendingChatAttachments 放入依赖数组！
  // 原因：headers/body 使用函数形式，每次请求时自动读取最新值。
  // 如果放入依赖，后端返回 session_info → currentSessionId 变化 → transport 重建
  // → useChat 内部状态丢失 → 消息被清空 → UI 重置为初始状态
  const chatTransport = useMemo(() => new DefaultChatTransport({
    api: '/api/chat',
    // Cookie 模式：浏览器自动携带 httpOnly Cookie 到 Next.js BFF 代理
    credentials: 'include',
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
        // ✨ 深度思考开关：从 chatStore 读取（持久化状态）
        enableThink: useChatStore.getState().enableThink,
        // ✨ 粘贴上传的图片和文件路径（从 ref 缓冲区读取，确保时序正确）
        images: pendingImagesRef.current,
        pastedFiles: pendingFilesRef.current,
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
    // ✨ Active Probing：提交工具调用结果（如用户填写的参数）回传给 LLM
    addToolResult,
  } = useChat({
    transport: chatTransport,
    // ✨ Active Probing：启用多步工具调用流程
    // 当用户通过 addToolResult 提交参数后，SDK 需要继续对话循环，
    // 让后端处理工具结果并恢复 LangGraph 状态机
    maxSteps: 5,
    onError: (error) => {
      console.error('[useChat] Stream error:', error);
      // 根据错误类型提供用户友好提示
      const msg = error.message || '';
      if (msg.includes('402') || msg.toLowerCase().includes('insufficient') || msg.includes('余额')) {
        toast.error('余额不足，请充值后继续使用');
        useUIStore.getState().openOverlay('userCenter');
      } else {
        toast.error('对话出错，请稍后重试');
      }
    },
    onFinish: () => {
      // 流结束处理（如需可在此添加逻辑）
    },
  });

  // v5 API: status 替代 isLoading
  // 'submitted' | 'streaming' 表示正在请求
  const isLoading = status === 'submitted' || status === 'streaming';

  // ==========================================
  // useChatSync 桥接：将 useChat 状态同步到 Zustand store
  // 供其他组件（如 SessionSidebar）读取会话 ID、计费等
  // ==========================================
  useChatSync({ messages: aiMessages, isLoading, pendingAttachmentsRef });

  // ==========================================
  // 直接从 useChat.messages 渲染（不经过 store 中转）
  // UIMessage.parts → 提取文本 → 转为 store Message 格式
  // 这样避免 mirroredMessages 同步延迟导致 UI 不更新
  //
  // ⚠️ 修复：user 消息往往只有 content 没有 parts，
  // 必须兼容 content 字段，否则用户消息显示为空
  //
  // ✨ 修复：合并 mirroredMessages 上的 thinkingContent
  // thinkingContent 在流结束时由 useChatSync 保存到 mirroredMessages，
  // aiMessages (useChat) 本身没有这个字段，需要从 mirroredMessages 合并
  // ==========================================
  const mirroredMessages = useChatStore(state => state.mirroredMessages);
  const dagProgress = useChatStore(state => state.dagProgress);
  // ✨ 意图标签：读取暂存的意图标签（intent 事件先于 assistant 消息到达）
  const pendingIntentLabel = useChatStore(state => state.pendingIntentLabel);

  const messages = useMemo(() => {
    // 构建 thinkingContent、attachments 和 intentLabel 索引：key=message.id
    const thinkingMap = new Map<string, string>();
    const attachmentsMap = new Map<string, MessageAttachments>();
    const intentLabelMap = new Map<string, string>();
    for (const msg of mirroredMessages) {
      if (msg.thinkingContent) {
        thinkingMap.set(msg.id, msg.thinkingContent);
      }
      if (msg.attachments) {
        attachmentsMap.set(msg.id, msg.attachments);
      }
      if (msg.intentLabel) {
        intentLabelMap.set(msg.id, msg.intentLabel);
      }
    }

    // ✨ 流式期间：pendingAttachmentsRef 中的 attachments 还没同步到 mirroredMessages，
    // 需要直接关联到最后一条用户消息
    const pendingAttachments = pendingAttachmentsRef.current;

    // ✨ 意图标签：流式期间 pendingIntentLabel 还没回填到 mirroredMessages，
    // 需要直接关联到最后一条 assistant 消息
    const currentPendingIntentLabel = pendingIntentLabel;
    // ✨ 找到 aiMessages 中最后一条 assistant 消息的索引（用于 pendingIntentLabel 回填）
    let lastAssistantIdx = -1;
    for (let i = aiMessages.length - 1; i >= 0; i--) {
      if (aiMessages[i].role === 'assistant') {
        lastAssistantIdx = i;
        break;
      }
    }
    // ✨ 判断最后一条 assistant 消息是否是"新消息"（不在旧的 mirroredMessages 中）
    // intent 事件在 assistant 消息创建之前到达，此时 pendingIntentLabel 不应回填到旧消息上
    const mirroredIds = new Set(mirroredMessages.map(m => m.id));
    const lastAssistantIsNew = lastAssistantIdx !== -1
      && !mirroredIds.has(aiMessages[lastAssistantIdx].id);

    return aiMessages.map((msg, idx) => {
      let content = msg.content || '';
      if (msg.parts && msg.parts.length > 0) {
        const textParts = msg.parts.filter((p): p is typeof p & { type: 'text' } => p.type === 'text');
        if (textParts.length > 0) {
          content = textParts.map(p => (p as { type: 'text'; text: string }).text).join('');
        }
      }

      // ✨ 判断是否为最后一条用户消息（用于关联 pendingAttachments）
      const isLastUserMsg = msg.role === 'user' && idx === aiMessages.length - 1;

      // ✨ Active Probing：提取 toolInvocation 类型的 parts
      // Vercel AI SDK v5 中工具调用以 parts 形式存储，type 为 "tool-xxx" 或 "dynamic-tool"
      // 这里提取所有与工具调用相关的 parts，供 MemoizedMessageItem 渲染 ParameterProbingCard
      const toolInvocationParts = msg.parts?.filter(
        (p): p is typeof p & { type: string; toolCallId?: string; toolName?: string } =>
          (p.type.startsWith('tool-') || p.type === 'dynamic-tool')
      ) || [];

      // ✨ 意图标签：优先从 mirroredMessages 合并
      // 流式期间：只有当最后一条 assistant 是新消息时，才回填 pendingIntentLabel
      // 避免把当前轮的 intentLabel 错误地显示到上一轮的 assistant 消息上
      const resolvedIntentLabel = intentLabelMap.get(msg.id)
        || (idx === lastAssistantIdx && lastAssistantIsNew && currentPendingIntentLabel ? currentPendingIntentLabel : undefined);

      return {
        id: msg.id,
        role: msg.role as 'user' | 'assistant' | 'system',
        content,
        timestamp: Date.now(),
        // ✨ 合并 mirroredMessages 上的 thinkingContent、attachments 和 intentLabel
        thinkingContent: thinkingMap.get(msg.id),
        attachments: attachmentsMap.get(msg.id)
          || (isLastUserMsg && pendingAttachments ? pendingAttachments : undefined),
        // ✨ Active Probing：工具调用 parts，用于渲染参数探查表单
        toolInvocationParts: toolInvocationParts.length > 0 ? toolInvocationParts : undefined,
        // ✨ 意图识别标签：从 mirroredMessages 合并，流式期间使用 pendingIntentLabel
        intentLabel: resolvedIntentLabel,
      };
    });
  }, [aiMessages, mirroredMessages, pendingIntentLabel]);
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
    handleSendRef,
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
  //
  // ⚠️ 关键设计决策：此 effect 仅在 currentSessionId 变化时触发，
  // 用于加载历史会话的消息。对于同一会话内的后续消息，
  // useChat 的 aiMessages 会自然累积，无需重新拉取。
  //
  // ⚠️ 核心修复：使用 isLoadingRef 为历史拉取加锁
  // 当新消息发送导致新 Session ID 产生时，当前一定正在流式响应，
  // 此时绝对不能去服务端拉历史，否则空历史会清空掉用户的消息和正在打字的屏幕。
  //
  // ⚠️ 流式完成后不重新拉取：流式完成后 currentSessionId 不变，
  // effect 不会重新触发。aiMessages 由 useChat 自然维护，包含完整历史。
  // 如果流式完成后重新拉取并 setAiMessages，会替换 SDK 内部状态，
  // 可能导致消息 ID 冲突、重复消息、或丢失正在流式输出的内容。
  // ==========================================
  const isLoadingRef = useRef(isLoading);
  useEffect(() => {
    isLoadingRef.current = isLoading;
  }, [isLoading]);

  // 跟踪上一次拉取历史的 sessionId，避免重复拉取
  const lastFetchedSessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    const fetchMessages = async () => {
      if (!currentSessionId) {
        // 只有在非流式状态时才清空屏幕
        if (!isLoadingRef.current) {
          setMessages([]);
          setAiMessages([]);
          lastFetchedSessionIdRef.current = null;
        }
        return;
      }

      // 如果已经为当前 session 拉取过历史，跳过
      // 这防止流式完成后 currentSessionId 不变但 effect 因其他原因重新触发时重复拉取
      if (lastFetchedSessionIdRef.current === currentSessionId) return;

      // 核心修复：如果是新发起的对话刚拿到了服务端返回的 ID，当前一定正在流式响应！
      // 此时绝对不能去服务端拉历史，否则空历史会直接清空掉用户的消息和正在打字的屏幕。
      if (isLoadingRef.current) return;

      try {
        const data = await fetchAPI(`/api/chat/sessions/${currentSessionId}/messages`);
        if (data.data && data.data.length > 0) {
          const formattedMessages = data.data.map((msg: { role: string; content: string; id: number; attachments?: any }) => ({
            id: String(msg.id),
            role: msg.role as 'user' | 'assistant',
            content: msg.content,
            timestamp: Date.now(),
            attachments: msg.attachments
          }));

          // 同步给 Zustand store（供 SessionSidebar 等读取）
          setMessages(formattedMessages);

          // 同步给 Vercel AI SDK 的 aiMessages
          // 构造完整的 UIMessage 格式，包含 parts 字段（text part 从 content 重建），
          // 避免 Vercel AI SDK 因缺少 parts 导致内部状态不一致
          // ✨ Active Probing：如果历史消息包含 tool_calls，重建 tool invocation parts
          setAiMessages(formattedMessages.map((m: { id: string; role: string; content: string; tool_calls?: any }) => {
            const parts = m.content ? [{ type: 'text' as const, text: m.content }] : [];
            // ✨ 从后端 tool_calls 数据重建工具调用 parts（用于 Active Probing 历史回显）
            // 后端 AIMessage 的 tool_calls 字段包含工具调用信息，
            // 重建为 Vercel AI SDK v5 的 tool invocation parts 格式
            if (m.tool_calls && Array.isArray(m.tool_calls)) {
              for (const tc of m.tool_calls) {
                parts.push({
                  type: `tool-${tc.name}`,
                  toolCallId: tc.id || `call_${m.id}`,
                  toolName: tc.name,
                  state: 'output-available', // 历史消息的工具调用已完成
                  input: tc.args || {},
                  output: { status: 'completed' },
                });
              }
            }
            return {
              id: m.id,
              role: m.role,
              content: m.content,
              parts,
            };
          }));

          // 标记已拉取，避免重复
          lastFetchedSessionIdRef.current = currentSessionId;
        } else {
          setMessages([]);
        }
      } catch (e) {
        console.error('Failed to fetch messages:', e);
        setMessages([]);
      }
    };
    fetchMessages();
  }, [currentSessionId, setMessages, setAiMessages]);

  // ==========================================
  // 打开技能中心（基础分析模式）
  // ==========================================
  const handleOpenBasicAnalysis = useCallback(() => {
    setSkillFilterMode('basic');
    openSkillCenter();
  }, [setSkillFilterMode, openSkillCenter]);

  // ==========================================
  // 发送消息包装函数 — 调用 useChat.append
  // ✨ 扩展：接收 enableThink 参数，写入 transport body
  // ==========================================
  const handleSendWrapper = useCallback((messageText: string, _enableThink?: boolean) => {
    // ✨ 修复图片传递时序问题：
    // 1. 先从 store 提取图片/文件路径，存入 ref 缓冲区
    // 2. 然后调用 sendMessage（body() 会从 ref 读取）
    // 3. 最后清理粘贴附件和 ref
    const { pastedAttachments, pendingChatAttachments: contextFiles } = useWorkspaceStore.getState();
    const imagePaths = pastedAttachments
      .filter(att => att.type === 'image' && att.serverPath && !att.isUploading)
      .map(att => att.serverPath);
    const filePaths = pastedAttachments
      .filter(att => att.type === 'file' && att.serverPath && !att.isUploading)
      .map(att => att.serverPath);

    pendingImagesRef.current = imagePaths;
    pendingFilesRef.current = filePaths;

    // ✨ 设置待关联的 attachments（发送后 useChatSync 会将其附加到最新用户消息）
    // 包含粘贴附件（图片/文件）和项目文件附件（contextFiles → files 字段，蓝色标签）
    if (imagePaths.length > 0 || filePaths.length > 0 || contextFiles.length > 0) {
      const attachments: MessageAttachments = {};
      if (imagePaths.length > 0) attachments.images = imagePaths;
      if (filePaths.length > 0) attachments.pastedFiles = filePaths;
      if (contextFiles.length > 0) attachments.files = contextFiles;
      pendingAttachmentsRef.current = attachments;
    } else {
      pendingAttachmentsRef.current = null;
    }

    // 调用 sendMessage 发送消息（v5 API）
    sendMessage({ text: messageText });

    // 发送后清理粘贴附件、项目文件附件和 ref 缓冲区
    cleanupPastedAttachments();
    // ✨ 清空项目文件附件（避免附件标签残留在输入框上方）
    useWorkspaceStore.getState().clearPendingChatAttachments();
    // 延迟清空 ref，确保 body() 已经读取
    setTimeout(() => {
      pendingImagesRef.current = [];
      pendingFilesRef.current = [];
    }, 100);

    // 自动滚动到底部
    if (isAtBottomRef.current && !isPausedRef.current) {
      requestAnimationFrame(() => scrollToBottom());
    }
  }, [sendMessage, cleanupPastedAttachments, isAtBottomRef, isPausedRef, scrollToBottom]);

  // ✨ 将 handleSendWrapper 连接到 useMessageActions 的 handleSendRef
  // 这样 handleRetry / handleEditResend 可以通过 ref 调用发送
  useEffect(() => {
    handleSendRef.current = handleSendWrapper;
  }, [handleSendWrapper, handleSendRef]);

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
            {/* ✨ DAG 进度可视化：当有 DAG 任务进度时渲染 */}
            {dagProgress && dagProgress.length > 1 && (
              <div className="px-2 md:px-4">
                <DAGProgressView nodes={dagProgress} />
              </div>
            )}
            <VirtualizedMessageList
              messages={messages}
              isTyping={isTyping}
              currentProjectId={currentProjectId ?? undefined}
              onPreviewAsset={handlePreviewAsset}
              onDownloadAsset={handleDownloadAsset}
              onInterpret={(files, code, userMsg) => handleInterpret(files, code, userMsg, handleSendWrapper)}
              onRetry={handleRetry}
              onEditResend={handleEditResend}
              // ✨ Active Probing：传递 addToolResult 供 ParameterProbingCard 提交参数
              addToolResult={addToolResult}
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