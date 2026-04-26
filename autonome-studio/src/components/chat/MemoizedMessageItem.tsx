"use client";

import { memo, useState, useMemo } from "react";
import { User, FileText, Image as ImageIcon, Box, Copy, Check, Sparkles, Eye, Download, ChevronDown, ChevronRight, RefreshCw, Edit3, X, Send, CheckCircle, CheckCircle2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import type { Message, MessageAttachments } from "@/store/useChatStore";
import { useChatStore } from "@/store/useChatStore";
import { MarkdownBlock } from "../MarkdownBlock";
import { StreamingMarkdown } from "./StreamingMarkdown";
import { ParameterProbingCard, type ParameterProbingCardProps } from "./ParameterProbingCard";
import { AdhocAnalysisCard } from "./components/AdhocAnalysisCard";
import { IntentTag } from "./IntentTag";
import { BASE_URL, getToken } from "@/lib/api";
import { filterThinkingContent } from "@/lib/contentFilter";
import { buildAssetTreeFromFiles, AssetTreeNode } from "@/components/chat/shared/AssetTree";

// ==========================================
// ✨ 辅助函数：复制到剪贴板
// ==========================================
const copyToClipboard = async (text: string) => {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
  } else {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-9999px";
    textArea.style.top = "0";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
    } catch (err) {
      console.error('Fallback copy failed', err);
    }
    document.body.removeChild(textArea);
  }
};

// ==========================================
// ✨ 辅助函数：格式化时间戳为 HH:mm 格式
// ==========================================
const formatTime = (timestamp: number): string => {
  const date = new Date(timestamp);
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  return `${hours}:${minutes}`;
};

// ==========================================
// ✨ 任务元数据卡片组件 - 显示任务 ID 和名称
// ==========================================
const TaskMetaCard = ({ taskId, taskName }: { taskId: string; taskName?: string }) => (
  <motion.div
    initial={{ opacity: 0, y: 4 }}
    animate={{ opacity: 1, y: 0 }}
    className="flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-500/30 rounded-lg mb-2"
  >
    <CheckCircle className="w-4 h-4 text-blue-500" />
    <span className="text-xs text-blue-600 dark:text-blue-400">
      Task: <code className="font-mono bg-blue-100 dark:bg-blue-800/50 px-1 rounded">{taskName || taskId.slice(0, 8)}</code>
    </span>
  </motion.div>
);

// ==========================================
// ✨ 提取任务元数据的辅助函数
// ==========================================
const parseTaskMeta = (content: string): { taskId: string; taskName: string } | null => {
  const taskIdMatch = content.match(/<!-- TASK_ID: ([a-f0-9-]+) -->/);
  const taskNameMatch = content.match(/<!-- TASK_NAME: ([^\s]+) -->/);

  if (taskIdMatch || taskNameMatch) {
    return {
      taskId: taskIdMatch ? taskIdMatch[1] : '',
      taskName: taskNameMatch ? taskNameMatch[1] : ''
    };
  }
  return null;
};

// ==========================================
// ✨ 资产树卡片组件 - 带AI专家解读按钮
// ==========================================
interface AssetTreeCardProps {
  files: { projectId: string; path: string; name: string; ext: string }[];
  onPreview: (url: string, filename: string) => void;
  onDownload: (url: string, filename: string) => void;
  onInterpret: () => void;
  currentProjectId?: string;
}

const AssetTreeCard = memo(function AssetTreeCard({ files, onPreview, onDownload, onInterpret, currentProjectId }: AssetTreeCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const apiBase = BASE_URL.replace(/\/$/, '');

  // 构建树状结构（使用共享的 buildAssetTreeFromFiles）
  const tree = useMemo(() => {
    return buildAssetTreeFromFiles(
      files,
      (file) => `${apiBase}/api/projects/${file.projectId || currentProjectId}/files/${file.path}/view`
    );
  }, [files, apiBase, currentProjectId]);

  return (
    <div className="bg-[#1a1a1b] border border-neutral-700/60 rounded-xl overflow-hidden shadow-md w-full mt-3">
      {/* 卡片头部 */}
      <div
        className="flex items-center justify-between px-4 py-3 bg-neutral-800/50 cursor-pointer hover:bg-neutral-800/80 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-neutral-200">生成产物资产 (Assets)</span>
          <span className="px-2 py-0.5 rounded-full bg-blue-900/30 text-[10px] text-blue-400 font-mono">
            {files.length} 个文件
          </span>
        </div>
        {isExpanded ? <ChevronDown size={16} className="text-neutral-400" /> : <ChevronRight size={16} className="text-neutral-400" />}
      </div>

      {/* 文件列表 */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="flex flex-col gap-1 p-2 border-t border-neutral-800/50 max-h-64 overflow-y-auto"
          >
            {Object.values(tree.children).map((node) => (
              <AssetTreeNode key={node.name} node={node} level={0} onPreview={onPreview} onDownload={onDownload} variant="dark-only" />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ✨ AI 专家解读按钮 */}
      <div className="p-3 border-t border-neutral-800/50 bg-[#1e1e1f]/80">
        <button
          onClick={onInterpret}
          className="w-full py-2.5 rounded-lg bg-gradient-to-r from-blue-900/20 to-indigo-900/20 hover:from-blue-600/20 hover:to-indigo-600/20 border border-blue-500/20 hover:border-blue-400/50 text-blue-300 hover:text-blue-200 text-sm font-medium flex items-center justify-center gap-2 transition-all group shadow-[0_0_15px_rgba(59,130,246,0.1)] hover:shadow-[0_0_20px_rgba(59,130,246,0.2)]"
        >
          <Sparkles size={16} className="text-blue-400 group-hover:animate-pulse" />
          <span>✨ 深度解读分析结果</span>
        </button>
      </div>
    </div>
  );
});

// ==========================================
// ✨ MemoizedMessageItem - 记忆化消息组件
// 只有消息内容变化时才重渲染，避免输入框状态变化导致的重渲染
// ==========================================

interface MemoizedMessageItemProps {
  msg: Message;
  index: number;
  isLast: boolean;
  isTyping: boolean;
  currentProjectId?: string;
  // 回调函数
  onPreviewAsset: (url: string, filename: string) => void;
  onDownloadAsset: (url: string, filename: string) => void;
  onInterpret: (files: string[], code: string, userMessage: string) => void;
  // 新增：重试和编辑回调
  onRetry?: (messageId: string) => void;
  onEditResend?: (messageId: string, newContent: string, attachments?: MessageAttachments) => void;
  /**
   * ✨ Active Probing：提交工具调用结果
   * 来自 Vercel AI SDK useChat 的 addToolResult，
   * 供 ParameterProbingCard 将用户填写的参数回传给 LLM
   * 使用宽松类型避免与 SDK 内部泛型不兼容
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  addToolResult: any;
}

const MemoizedMessageItem = memo(function MemoizedMessageItem({
  msg,
  index,
  isLast,
  isTyping,
  currentProjectId,
  onPreviewAsset,
  onDownloadAsset,
  onInterpret,
  onRetry,
  onEditResend,
  addToolResult,
}: MemoizedMessageItemProps) {
  // ✨ 复制按钮状态
  const [copied, setCopied] = useState(false);

  // ✨ 编辑状态
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');

  // ✨ 思考过程状态：从 store 读取，传递给 StreamingMarkdown
  const thinkingContent = useChatStore((state) => state.thinkingContent);
  const isThinking = useChatStore((state) => state.isThinking);

  // 流式消息优化：useChat 自动追加内容到 msg.content，无需 streamingContent
  const displayContent = msg.content;

  // 是否正在流式输出（流式时隐藏操作按钮）
  const isStreaming = isLast && isTyping && msg.role === 'assistant';

  // ✨ 复制处理函数
  const handleCopy = async () => {
    await copyToClipboard(displayContent || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // ✨ 文件资产检测：从消息内容中提取文件路径
  const fileAssets = useMemo(() => {
    if (msg.role !== 'assistant' || !displayContent) return [];

    // ✨ 修复：匹配新路径 /workspace/project_xxx/results/...
    const filePatterns = [
      /\/workspace\/project_([a-zA-Z0-9_-]+)\/(results\/[a-zA-Z0-9_-]+\/[^\s'"]+\.([a-zA-Z0-9]+))/gi,
      // 兼容旧路径（如果有遗留消息）
      /\/app\/uploads\/project_([a-zA-Z0-9_-]+)\/(results\/[a-zA-Z0-9_-]+\/[^\s'"]+\.([a-zA-Z0-9]+))/gi,
    ];

    const files: { projectId: string; path: string; name: string; ext: string }[] = [];

    for (const pattern of filePatterns) {
      const matches = Array.from(displayContent.matchAll(pattern));
      for (const match of matches) {
        if (match.length >= 4) {
          const projectId = match[1];
          const path = match[2];
          const ext = match[3].toLowerCase();

          if (path && !files.find(f => f.path === path)) {
            files.push({
              projectId,
              path,
              name: path.split('/').pop() || path,
              ext
            });
          }
        }
      }
    }

    return files;
  }, [msg.role, displayContent]);

  // ✨ 提取隐藏元数据（用于 AI 专家解读）
  const interpretMeta = useMemo(() => {
    if (!displayContent) return { code: '', userMessage: '' };

    let extractedCode = '';
    let extractedUserMessage = '';
    const metaMatch = displayContent.match(/<!-- DEEP_INTERPRET_META\n([\s\S]*?)DEEP_INTERPRET_META -->/);
    if (metaMatch) {
      const metaData = metaMatch[1];
      const userMsgMatch = metaData.match(/USER_MESSAGE: (.*)/);
      const codeMatch = metaData.match(/CODE_START\n([\s\S]*?)\nCODE_END/);
      if (userMsgMatch) extractedUserMessage = userMsgMatch[1].trim();
      if (codeMatch) extractedCode = codeMatch[1].trim();
    }

    return { code: extractedCode, userMessage: extractedUserMessage };
  }, [displayContent]);

  // ✨ 终极清理函数：防漏、防幻觉、防乱码的系统指令过滤器
  const cleanedContent = useMemo(() => {
    if (!displayContent) return '';
    let cleaned = filterThinkingContent(displayContent);

    const removePatterns: RegExp[] = [
      // 1. 后端内部文件路径及其他噪音
      /\/workspace\/project_[a-zA-Z0-9_-]+\/results\/[^\s'"]+\.[a-zA-Z0-9]+/gi,
      /\/app\/uploads\/project_[a-zA-Z0-9_-]+\/results\/[^\s'"]+\.[a-zA-Z0-9]+/gi,
      /\[.*?\]\(\)/g,
      /^[-*+]\s*$/gm,
      // ✨ 增强：使用更宽泛的匹配，涵盖所有可能的 DEEP_INTERPRET_META 注释块
      /<!-- DEEP_INTERPRET_META[\s\S]*?DEEP_INTERPRET_META -->/gi,
      /<!-- DEEP_SEARCH_META[\s\S]*?DEEP_SEARCH_META -->/gi,
      /<!-- TASK_ID: [a-f0-9-]+ -->\n?/g,
      /<!-- TASK_NAME: [^\s]+ -->\n?/g,
      /^[\s\n]+$/gm,
    ];

    for (const pattern of removePatterns) {
      cleaned = cleaned.replace(pattern, '');
    }

    return cleaned.trim();
  }, [displayContent]);

  // ✨ 提取任务元数据（用于 TaskMetaCard 渲染）
  const taskMeta = useMemo(() => {
    if (!displayContent || msg.role !== 'assistant') return null;
    return parseTaskMeta(displayContent);
  }, [displayContent, msg.role]);

  // ✨ AI 专家解读处理函数
  const handleInterpret = () => {
    const filePaths = fileAssets.map(f => f.path);
    onInterpret(filePaths, interpretMeta.code, interpretMeta.userMessage);
  };

  // 隐藏空的 assistant 消息（但在流式生成中或思考中保留，以显示思考框）
  if (msg.role === 'assistant' && !displayContent && !(isLast && isTyping) && !isThinking) {
    return null;
  }

  return (
    <motion.div
      data-message-id={msg.id}
      // ✨ 流式消息优化：流式消息不使用入场动画，避免跳动
      initial={isLast && isTyping && msg.role === 'assistant' ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: isLast && isTyping && msg.role === 'assistant' ? 0 : 0.2 }}
      className={`flex flex-col group ${msg.role === 'user' ? 'items-end' : 'items-start'} max-w-4xl mx-auto w-full transition-all duration-300`}
    >
      {/* ✨ 移动端优化：隐藏头像节省空间，gap-0 消除间距，消息内容占满全宽 */}
      <div className={`flex items-start gap-0 md:gap-4 w-full ${msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''}`}>
        {/* ✨ 移动端隐藏头像（hidden md:flex），桌面端保持显示 */}
        <div className={`hidden md:flex w-8 h-8 rounded-full items-center justify-center shrink-0 overflow-hidden ${
          msg.role === 'user'
            ? 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
            : 'bg-[#1a1a1c] border border-neutral-700/60 shadow-sm'
        }`}>
          {msg.role === 'user' ? (
            <User size={18} />
          ) : (
            <img
              src="/ai-avatar.png"
              alt="AI Avatar"
              className="w-full h-full object-cover scale-[1.15]"
            />
          )}
        </div>
        {/* ✨ 移动端减少 padding（px-3 py-3），桌面端保持原样（px-5 py-4） */}
        {/* ✨ 用户消息：温和的蓝灰色背景 + 柔和文字色，保护眼睛 */}
        <div className={`flex-1 min-w-0 rounded-2xl px-3 md:px-5 py-3 md:py-4 ${
          msg.role === 'user'
            ? 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200'
            : 'bg-transparent'
        }`}>
          {msg.role === 'user' ? (
            <div>
              {/* ✨ 编辑模式：显示文本框和操作按钮 */}
              {isEditing ? (
                <div className="space-y-3">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="w-full min-h-[80px] p-3 rounded-lg bg-slate-200 dark:bg-slate-700 border border-slate-300 dark:border-slate-600 text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-400 resize-y focus:outline-none focus:ring-2 focus:ring-blue-400/50 text-[0.9375rem] leading-relaxed"
                    placeholder="编辑消息内容..."
                    autoFocus
                  />
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        if (onEditResend && editContent.trim()) {
                          onEditResend(msg.id, editContent.trim(), msg.attachments);
                          setIsEditing(false);
                        }
                      }}
                      disabled={!editContent.trim()}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:bg-neutral-700 disabled:text-neutral-500 text-white text-sm font-medium transition-colors"
                    >
                      <Send size={14} />
                      <span>重新发送</span>
                    </button>
                    <button
                      onClick={() => setIsEditing(false)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-700 hover:bg-neutral-600 text-neutral-300 text-sm transition-colors"
                    >
                      <X size={14} />
                      <span>取消</span>
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {/* 用户消息文本 */}
                  <div className="whitespace-pre-wrap break-words text-[0.9375rem] leading-relaxed">{msg.content}</div>

                  {/* ✨ 附件标记 - 在消息文本下方显示 */}
                  {msg.attachments && (
                    <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-slate-300/50 dark:border-slate-600/50">
                      {/* 技能标记 - 紫色 */}
                      {msg.attachments.skill && (
                        <div className="flex items-center gap-1 px-2 py-0.5 bg-purple-100 dark:bg-purple-900/40 border border-purple-300 dark:border-purple-700/50 rounded text-xs text-purple-700 dark:text-purple-300">
                          <Box size={10} />
                          <span>{msg.attachments.skill.name}</span>
                        </div>
                      )}

                      {/* 文件标记 - 蓝色 */}
                      {msg.attachments.files?.map((path, idx) => (
                        <div key={idx} className="flex items-center gap-1 px-2 py-0.5 bg-blue-100 dark:bg-blue-900/40 border border-blue-300 dark:border-blue-700/50 rounded text-xs text-blue-700 dark:text-blue-300">
                          <FileText size={10} />
                          <span className="truncate max-w-[120px]">{path.split('/').pop()}</span>
                        </div>
                      ))}

                      {/* 图片标记 - 显示缩略图 */}
                      {msg.attachments.images?.map((path, idx) => {
                        // 构建图片预览 URL
                        // path 可能是绝对路径（如 /workspace/project_xxx/raw_data/.pasted/image.png）
                        // 或相对路径（如 raw_data/.pasted/image.png）
                        // /view 端点需要相对路径，所以提取 project_xxx/ 之后的部分
                        const projectId = currentProjectId || '';
                        let relativePath = path;
                        const projectPrefix = `project_${projectId}/`;
                        const prefixIdx = path.indexOf(projectPrefix);
                        if (prefixIdx !== -1) {
                          relativePath = path.substring(prefixIdx + projectPrefix.length);
                        }
                        const token = getToken();
                        const previewUrl = `${BASE_URL}/api/projects/${projectId}/files/${relativePath}/view${token ? `?token=${token}` : ''}`;
                        return (
                          <div key={idx} className="mt-1">
                            <img
                              src={previewUrl}
                              alt={path.split('/').pop() || '图片'}
                              className="max-w-[200px] max-h-[150px] rounded-lg border border-slate-300/50 dark:border-slate-600/50 object-cover cursor-pointer hover:opacity-80 transition-opacity"
                              onClick={() => window.open(previewUrl, '_blank')}
                              onError={(e) => {
                                // 图片加载失败时显示文件名标签
                                const target = e.target as HTMLImageElement;
                                target.style.display = 'none';
                                const fallback = document.createElement('div');
                                fallback.className = 'flex items-center gap-1 px-2 py-0.5 bg-emerald-100 dark:bg-emerald-900/40 border border-emerald-300 dark:border-emerald-700/50 rounded text-xs text-emerald-700 dark:text-emerald-300';
                                fallback.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> ${path.split('/').pop()}`;
                                target.parentNode?.appendChild(fallback);
                              }}
                            />
                          </div>
                        );
                      })}

                      {/* 粘贴文件标记 - 橙色 */}
                      {msg.attachments.pastedFiles?.map((path, idx) => (
                        <div key={idx} className="flex items-center gap-1 px-2 py-0.5 bg-orange-100 dark:bg-orange-900/40 border border-orange-300 dark:border-orange-700/50 rounded text-xs text-orange-700 dark:text-orange-300">
                          <FileText size={10} />
                          <span className="truncate max-w-[120px]">{path.split('/').pop()}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-4 w-full">
              {/* ✨ 意图识别标签：AI 消息左上角显示意图类型文字（低调纯文字） */}
              {msg.intentLabel && (
                <div className="flex items-center gap-1.5 -mb-2">
                  <IntentTag intentType={msg.intentLabel} />
                </div>
              )}
              {/* ✨ 任务元数据卡片：显示任务 ID 和名称 */}
              {taskMeta && (
                <TaskMetaCard taskId={taskMeta.taskId} taskName={taskMeta.taskName} />
              )}
              {/* ✨ 流式消息丝滑渲染：使用 StreamingMarkdown 组件 */}
              {(() => {
                // ✨ 流式输出中：使用 StreamingMarkdown（处理未闭合结构 + DOM Diff）
                // 即使 displayContent 为空也要渲染，因为 StreamingMarkdown 需要显示思考框
                if (isLast && isTyping) {
                  return (
                    <StreamingMarkdown
                      content={cleanedContent}
                      isStreaming={true}
                      thinkingContent={thinkingContent}
                      isThinking={isThinking}
                    />
                  );
                }

                if (!displayContent) return null;

                // ✨ 已完成的 AI 消息：如果消息上有 thinkingContent，也要传递给 StreamingMarkdown
                // 这样思考卡片在流结束后仍然保留，用户可以随时展开查看
                if (msg.role === 'assistant' && msg.thinkingContent) {
                  return (
                    <StreamingMarkdown
                      content={cleanedContent}
                      isStreaming={false}
                      thinkingContent={msg.thinkingContent}
                      isThinking={false}
                    />
                  );
                }

                // ✨ 文件资产树渲染：检测到文件时显示资产树卡片
                if (fileAssets.length > 0) {
                  return (
                    <>
                      {/* 清理后的文本内容 */}
                      {cleanedContent && <MarkdownBlock content={cleanedContent} projectId={currentProjectId} />}
                      {/* 文件资产树卡片 + AI 专家解读按钮 */}
                      <AssetTreeCard
                        files={fileAssets}
                        onPreview={onPreviewAsset}
                        onDownload={onDownloadAsset}
                        onInterpret={handleInterpret}
                        currentProjectId={currentProjectId}
                      />
                    </>
                  );
                }

                // 简化版：返回普通 Markdown 渲染
                return <MarkdownBlock content={displayContent} projectId={currentProjectId} />;
              })()}

              {/* ✨ Active Probing：渲染工具调用（ParameterProbingCard 参数探查表单）
                  Vercel AI SDK v5 中，工具调用以 parts 形式存储在 UIMessage 上。
                  当后端 L2 层检测到参数缺失时，通过 ToolCall 发送 JSON Schema，
                  前端使用 ParameterProbingCard 动态渲染表单，用户补全后参数合并回 TaskNode。 */}
              {msg.toolInvocationParts && msg.toolInvocationParts.length > 0 && (
                <div className="space-y-3">
                  {msg.toolInvocationParts.map((part) => {
                    // 提取工具名称：Vercel AI SDK v5 中 type 为 "tool-xxx" 或 "dynamic-tool"
                    const toolName = part.type === 'dynamic-tool'
                      ? (part as { toolName: string }).toolName
                      : part.type.replace('tool-', '');
                    const toolCallId = part.toolCallId || '';
                    const toolState = part.state || '';
                    const toolInput = part.input as Record<string, unknown> | undefined;

                    // ✨ render_adhoc_card 工具：渲染 AdhocAnalysisCard 即席分析策略卡片
                    if (toolName === 'render_adhoc_card' && toolState !== 'output-available' && toolState !== 'output-error') {
                      const strategy = (toolInput?.strategy || '') as string;
                      const code = (toolInput?.code || '') as string;
                      const code_language = (toolInput?.code_language || 'python') as 'python' | 'r';
                      const parameter_schema = (toolInput?.parameter_schema || {}) as {
                        type: string;
                        properties: Record<string, unknown>;
                        required?: string[];
                      };
                      const input_mapping = (toolInput?.input_mapping || {}) as Record<string, string>;

                      return (
                        <AdhocAnalysisCard
                          key={toolCallId}
                          strategy={strategy}
                          code={code}
                          code_language={code_language}
                          parameter_schema={parameter_schema as any}
                          input_mapping={input_mapping}
                          addToolResult={addToolResult}
                          toolCallId={toolCallId}
                        />
                      );
                    }

                    // ✨ request_parameters 工具：渲染 ParameterProbingCard 参数探查表单
                    if (toolName === 'request_parameters' && toolState !== 'output-available' && toolState !== 'output-error') {
                      // 从 input 中提取 schema 和 message
                      const schema = (toolInput?.schema || {}) as ParameterProbingCardProps['schema'];
                      const message = (toolInput?.message || '') as string;

                      return (
                        <ParameterProbingCard
                          key={toolCallId}
                          message={message}
                          schema={schema}
                          onSubmit={(values) => {
                            // 将用户填写的参数通过 addToolResult 回传给 LLM
                            addToolResult({
                              tool: toolName,
                              toolCallId,
                              output: values,
                            });
                          }}
                        />
                      );
                    }

                    // ✨ 工具调用已完成（output-available）：显示绿色勾号"参数已补全"
                    if (toolState === 'output-available') {
                      return (
                        <div
                          key={toolCallId}
                          className="flex items-center gap-1.5 text-xs text-emerald-500"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>参数已补全</span>
                        </div>
                      );
                    }

                    // ✨ 工具调用出错（output-error）：显示错误提示
                    if (toolState === 'output-error') {
                      return (
                        <div
                          key={toolCallId}
                          className="flex items-center gap-1.5 text-xs text-red-400"
                        >
                          <X className="w-3.5 h-3.5" />
                          <span>参数提交失败</span>
                        </div>
                      );
                    }

                    // 其他工具调用状态不渲染（如 input-streaming）
                    return null;
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ✨ 消息操作按钮和时间（流式时隐藏），和消息内容区域对齐 */}
      {!isStreaming && (
        <div className={`flex items-start gap-0 md:gap-4 w-full ${msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''}`}>
          {/* ✨ 头像占位（保持和消息行一致的布局） */}
          <div className="hidden md:flex w-8 shrink-0" />

          {/* ✨ 操作区域：flex-1 和消息内容宽度一致，内部用 justify-between */}
          <div className="flex-1 min-w-0 flex items-center justify-between">
            {/* ✨ 左侧：操作按钮 */}
            <div className="flex items-center gap-1">
              {/* ✨ 用户消息：编辑按钮 */}
              {msg.role === 'user' && onEditResend && (
                <button
                  onClick={() => {
                    setEditContent(msg.content);
                    setIsEditing(true);
                  }}
                  className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-gray-400 dark:text-neutral-500 hover:text-gray-600 dark:hover:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-800/50 transition-all opacity-100 md:opacity-0 md:group-hover:opacity-100"
                  title="编辑并重新发送"
                >
                  <Edit3 className="w-3 h-3" />
                  <span>编辑</span>
                </button>
              )}

              {/* ✨ AI 消息：重试按钮 */}
              {msg.role === 'assistant' && onRetry && displayContent?.trim() && (
                <button
                  onClick={() => onRetry(msg.id)}
                  className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-gray-400 dark:text-neutral-500 hover:text-gray-600 dark:hover:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-800/50 transition-all opacity-100 md:opacity-0 md:group-hover:opacity-100"
                  title="重新生成回复"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>重试</span>
                </button>
              )}

              {/* 复制按钮 */}
              {displayContent?.trim() && (
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-gray-400 dark:text-neutral-500 hover:text-gray-600 dark:hover:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-800/50 transition-all opacity-100 md:opacity-0 md:group-hover:opacity-100"
                  title="复制消息"
                >
                  {copied ? (
                    <>
                      <Check className="w-3 h-3 text-green-500" />
                      <span className="text-green-500">已复制</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      <span>复制</span>
                    </>
                  )}
                </button>
              )}
            </div>

            {/* ✨ 右侧：时间显示（消息下方最右边） */}
            <span
              className="text-xs text-gray-400 dark:text-neutral-500 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity shrink-0"
              suppressHydrationWarning
            >
              {formatTime(msg.timestamp)}
            </span>
          </div>
        </div>
      )}
    </motion.div>
  );
});

export { MemoizedMessageItem };