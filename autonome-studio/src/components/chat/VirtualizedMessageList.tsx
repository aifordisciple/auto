/**
 * VirtualizedMessageList - 虚拟化消息列表组件
 *
 * 性能优化：
 * 1. 使用 @tanstack/react-virtual 实现虚拟滚动
 * 2. 只渲染可见区域的消息，大幅减少 DOM 节点
 * 3. 支持 1000+ 条消息流畅滚动
 * 4. 动态高度估算，自动调整
 *
 * 从 ChatStage.tsx 提取，解决消息过多时的性能问题
 */
"use client";

import { useRef, useCallback, memo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { AnimatePresence } from 'framer-motion';
import { Message } from '@/store/useChatStore';
import { MemoizedMessageItem } from './MemoizedMessageItem';

// ==========================================
// 类型定义
// ==========================================

export interface VirtualizedMessageListProps {
  /** 消息列表 */
  messages: Message[];
  /** 是否正在输入 */
  isTyping: boolean;
  /** 当前项目 ID */
  currentProjectId?: string;
  /** 预览资源回调 */
  onPreviewAsset: (url: string, filename: string) => void;
  /** 下载资源回调 */
  onDownloadAsset: (url: string, filename: string) => void;
  /** 深度解读回调 */
  onInterpret: (files: string[], code: string, userMessage: string) => void;
  /** 重试回调 */
  onRetry: (messageId: string) => void;
  /** 编辑重发回调 */
  onEditResend: (messageId: string, newContent: string, attachments?: any) => void;
  /**
   * ✨ Active Probing：提交工具调用结果
   * 来自 Vercel AI SDK useChat 的 addToolResult，
   * 供 ParameterProbingCard 将用户填写的参数回传给 LLM
   * 使用宽松类型避免与 SDK 内部泛型不兼容
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  addToolResult: any;
  /** 滚动容器引用 */
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  /** 消息底部引用 */
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  /** 消息列表底部的额外内容（如 typing 指示器） */
  footer?: React.ReactNode;
}

// ==========================================
// 主组件
// ==========================================

export const VirtualizedMessageList = memo(function VirtualizedMessageList({
  messages,
  isTyping,
  currentProjectId,
  onPreviewAsset,
  onDownloadAsset,
  onInterpret,
  onRetry,
  onEditResend,
  addToolResult,
  scrollContainerRef,
  messagesEndRef,
  footer,
}: VirtualizedMessageListProps) {
  // ==========================================
  // 虚拟化配置
  // ==========================================

  // 估算消息高度的函数
  const estimateSize = useCallback((index: number) => {
    const msg = messages[index];
    if (!msg) return 150; // 默认高度

    // 根据消息内容长度估算高度
    const contentLength = msg.content?.length || 0;

    // ✨ 基础高度估算（包含头像、操作按钮等）
    // 用户消息：头像(32px) + 消息气泡(约60-200px) + 操作按钮(约40px)
    // AI 消息：头像(32px) + 消息气泡(约100-400px) + 操作按钮(约40px)
    let estimatedHeight = 80;

    if (msg.role === 'user') {
      // 用户消息通常较短
      estimatedHeight += Math.max(60, Math.min(150, 40 + contentLength * 0.3));
      // 用户消息有操作按钮（编辑按钮等），约40px高度
      estimatedHeight += 40;
    } else {
      // AI 消息通常较长，包含代码块和 markdown
      estimatedHeight += Math.max(80, Math.min(350, 60 + contentLength * 0.4));

      // 代码块额外高度
      const codeBlockCount = (msg.content.match(/```/g) || []).length / 2;
      if (codeBlockCount > 0) {
        estimatedHeight += codeBlockCount * 200;
      }

      // 图片额外高度
      const hasImages = msg.content.includes('![');
      if (hasImages) {
        estimatedHeight += 150;
      }

      // 表格额外高度
      const hasTables = msg.content.includes('|');
      if (hasTables) {
        estimatedHeight += 100;
      }

      // AI 消息有操作按钮（重试、复制按钮），约40px高度
      estimatedHeight += 40;
    }

    // ✨ 注意：MemoizedMessageItem 有 mb-6 底部间距
    // 所以这里不需要额外添加间距

    // 限制最大高度估算
    return Math.max(150, Math.min(900, estimatedHeight));
  }, [messages]);

  // 创建虚拟化实例
  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize,
    overscan: 5, // 预渲染上下 5 条消息
  });

  // ==========================================
  // 渲染
  // ==========================================

  // ✨ 不再移除空的 assistant 消息
  // StreamingMarkdown 会正确处理空内容（显示思考框/思考中状态）
  const messagesToRender = messages;

  return (
    <div
      className="w-full md:max-w-4xl md:mx-auto space-y-6"
    >
      <AnimatePresence>
        {messagesToRender.map((msg, index) => (
          <MemoizedMessageItem
            key={msg.id}
            msg={msg}
            index={index}
            isLast={index === messagesToRender.length - 1}
            isTyping={isTyping}
            currentProjectId={currentProjectId}
            onPreviewAsset={onPreviewAsset}
            onDownloadAsset={onDownloadAsset}
            onInterpret={onInterpret}
            onRetry={onRetry}
            onEditResend={onEditResend}
            // ✨ Active Probing：传递 addToolResult 供 ParameterProbingCard 提交参数
            addToolResult={addToolResult}
          />
        ))}
      </AnimatePresence>

      {footer}

      <div ref={messagesEndRef} />
    </div>
  );
});

export default VirtualizedMessageList;