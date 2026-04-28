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
  // ✨ 签名扩展：第二个参数支持 options.preAttachments（编辑重发场景传递原始附件）
  const handleSendRef = useRef<(message: string, options?: { preAttachments?: Message['attachments'] }) => void>(() => {});

  // ==========================================
  // 消息重试：重新发送指定消息
  // ✨ 修复：支持点击 assistant 消息的重试按钮
  // 如果点击的是 assistant 消息，找到它前面的 user 消息重新发送
  // ==========================================
  const handleRetry = useCallback(async (messageId: string) => {
    const message = messages.find(m => m.id === messageId);
    if (!message) return;

    let userMessage: Message | undefined;
    let trimIndex: number;

    if (message.role === 'user') {
      // 点击的是 user 消息：直接重试
      userMessage = message;
      trimIndex = messages.findIndex(m => m.id === messageId);
    } else if (message.role === 'assistant') {
      // ✨ 点击的是 assistant 消息：找到它前面的 user 消息
      const assistantIndex = messages.findIndex(m => m.id === messageId);
      // 从 assistant 消息往前找最近的 user 消息
      for (let i = assistantIndex - 1; i >= 0; i--) {
        if (messages[i].role === 'user') {
          userMessage = messages[i];
          break;
        }
      }
      if (!userMessage) return;
      // 截断到 user 消息之前（不含 user 消息本身，因为重新发送会重新创建）
      trimIndex = messages.findIndex(m => m.id === userMessage!.id);
    } else {
      return;
    }

    // 移除该 user 消息及之后的所有消息
    const trimmedMessages = messages.slice(0, trimIndex);
    setMessages(trimmedMessages);

    // 重新发送该 user 消息
    handleSendRef.current(userMessage.content);
  }, [messages, setMessages]);

  // ==========================================
  // 消息编辑重发：修改内容后重新发送
  // ✨ 修复：传递原始消息的 attachments（图片/文件/技能标记），
  // 避免编辑重发时丢失附件信息
  // ==========================================
  const handleEditResend = useCallback(async (messageId: string, newContent: string, attachments?: Message['attachments']) => {
    const message = messages.find(m => m.id === messageId);
    if (!message || message.role !== 'user') return;

    // 移除该消息之后的所有消息
    const messageIndex = messages.findIndex(m => m.id === messageId);
    const trimmedMessages = messages.slice(0, messageIndex);
    setMessages(trimmedMessages);

    // ✨ 发送编辑后的消息，同时传递原始附件（图片/文件/技能标记）
    handleSendRef.current(newContent, { preAttachments: attachments });
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