/**
 * 消息操作按钮组件
 *
 * 提供复制、收藏等操作功能
 */
"use client";

import React, { useState, useEffect } from "react";
import { Copy, Check, Bookmark } from "lucide-react";
import { BASE_URL } from "@/lib/api";

/**
 * 复制文本到剪贴板
 */
export const copyToClipboard = async (text: string) => {
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

interface MessageActionButtonsProps {
  /** 消息内容 */
  content: string;
  /** 消息 ID */
  messageId?: string;
  /** 会话 ID */
  sessionId?: string;
}

/**
 * 消息操作按钮组件
 */
export const MessageActionButtons: React.FC<MessageActionButtonsProps> = ({
  content,
  messageId,
  sessionId,
}) => {
  const [copied, setCopied] = useState(false);
  const [isBookmarked, setIsBookmarked] = useState(false);

  // Check if message is bookmarked
  useEffect(() => {
    const checkBookmark = async () => {
      if (!messageId || !sessionId) return;
      const token = localStorage.getItem('autonome_access_token');
      try {
        const res = await fetch(`${BASE_URL}/api/chat/bookmarks`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          const found = (data.data || []).some((b: any) => b.message_id === messageId);
          setIsBookmarked(found);
        }
      } catch (e) {
        // Ignore errors
      }
    };
    checkBookmark();
  }, [messageId, sessionId]);

  const handleCopy = async () => {
    await copyToClipboard(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleBookmark = async () => {
    if (!messageId) return;

    const token = localStorage.getItem('autonome_access_token');
    try {
      if (isBookmarked) {
        // Remove bookmark
        await fetch(`${BASE_URL}/api/chat/messages/${messageId}/bookmark`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${token}` }
        });
        setIsBookmarked(false);
      } else {
        // Add bookmark
        await fetch(`${BASE_URL}/api/chat/messages/${messageId}/bookmark`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({})
        });
        setIsBookmarked(true);
      }
    } catch (e) {
      console.error('Bookmark action failed:', e);
    }
  };

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={handleCopy}
        className="flex items-center gap-1.5 p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-neutral-800 text-gray-500 dark:text-neutral-500 hover:text-gray-700 dark:hover:text-neutral-300 transition-all border border-transparent hover:border-gray-200 dark:hover:border-neutral-700"
        title="复制全文"
      >
        {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
        <span className="text-xs">{copied ? '已复制' : '复制'}</span>
      </button>
      {messageId && (
        <button
          onClick={handleBookmark}
          className={`flex items-center gap-1.5 p-1.5 rounded-md transition-all border border-transparent ${
            isBookmarked
              ? 'bg-yellow-50 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/30'
              : 'hover:bg-gray-100 dark:hover:bg-neutral-800 text-gray-500 dark:text-neutral-500 hover:text-gray-700 dark:hover:text-neutral-300 hover:border-gray-200 dark:hover:border-neutral-700'
          }`}
          title={isBookmarked ? '取消收藏' : '收藏'}
        >
          <Bookmark size={14} className={isBookmarked ? 'fill-current' : ''} />
          <span className="text-xs">{isBookmarked ? '已收藏' : '收藏'}</span>
        </button>
      )}
    </div>
  );
};

export default MessageActionButtons;