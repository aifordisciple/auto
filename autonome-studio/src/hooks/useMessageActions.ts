/**
 * useMessageActions - 消息操作 Hook
 *
 * Vercel AI SDK 重构后：
 * - 移除对 useChatStream / useImmediateStream 的依赖
 * - handleRetry / handleEditResend 简化，不再操作流式状态
 * - handleInterpret 保留但简化签名
 *
 * 核心职责：
 * - 消息重试：重新发送用户消息
 * - 消息编辑：修改用户消息后重新发送
 * - 深度解读：对代码/文件进行生物学解读
 */
import { useCallback, useRef } from 'react';
import { useChatStore, ChatState, Message } from '@/store/useChatStore';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { BASE_URL, getToken } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

interface UseMessageActionsOptions {
  // Vercel AI SDK 重构后不再需要流式相关的回调
}

// ==========================================
// Hook 实现
// ==========================================

export function useMessageActions(_options?: UseMessageActionsOptions) {
  // ==========================================
  // Store 订阅
  // ==========================================
  const messages = useChatStore((state: ChatState) => state.mirroredMessages);
  const setMessages = useChatStore((state: ChatState) => state.setMessages);
  const currentSessionId = useWorkspaceStore(state => state.currentSessionId);

  // handleSend 引用 — 由父组件通过 useEffect 更新
  const handleSendRef = useRef<(message: string, contextFiles?: string[]) => void>(() => {});

  // ==========================================
  // 消息重试：重新发送指定消息
  // ==========================================
  const handleRetry = useCallback(async (messageId: string) => {
    const message = messages.find(m => m.id === messageId);
    if (!message || message.role !== 'user') return;

    // 移除该消息之后的所有消息（包括 assistant 回复）
    const messageIndex = messages.findIndex(m => m.id === messageId);
    const trimmedMessages = messages.slice(0, messageIndex);
    setMessages(trimmedMessages);

    // 重新发送该消息
    handleSendRef.current(message.content);
  }, [messages, setMessages]);

  // ==========================================
  // 消息编辑重发：修改内容后重新发送
  // ==========================================
  const handleEditResend = useCallback(async (messageId: string, newContent: string, _attachments?: Message['attachments']) => {
    const message = messages.find(m => m.id === messageId);
    if (!message || message.role !== 'user') return;

    // 移除该消息之后的所有消息
    const messageIndex = messages.findIndex(m => m.id === messageId);
    const trimmedMessages = messages.slice(0, messageIndex);
    setMessages(trimmedMessages);

    // 发送编辑后的消息
    handleSendRef.current(newContent);
  }, [messages, setMessages]);

  // ==========================================
  // 深度解读：对代码/文件进行生物学解读
  // ==========================================
  const handleInterpret = useCallback(async (files: string[], code: string, _userMessage: string, handleSend: (msg: string) => void) => {
    if (!files.length && !code) return;

    // 构建解读请求消息
    const fileList = files.length > 0 ? `\n文件: ${files.join(', ')}` : '';
    const codeBlock = code ? `\n代码:\n\`\`\`\n${code}\n\`\`\`` : '';
    const interpretMessage = `请对以下内容进行深度生物学解读：${fileList}${codeBlock}`;

    // 使用传入的 handleSend 发送
    handleSend(interpretMessage);
  }, []);

  return {
    handleRetry,
    handleEditResend,
    handleInterpret,
    handleSendRef,
  };
}