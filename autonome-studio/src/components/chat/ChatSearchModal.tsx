"use client";

import { useState, useEffect, useRef } from "react";
import { Search, X, Loader2, MessageSquare } from "lucide-react";
import { BASE_URL, getToken } from "@/lib/api";
import { useUIStore } from "@/store/useUIStore";
import { SearchResult } from "@/store/useChatStore";
import { useDebounce } from "@/hooks/usePerformance";

interface ChatSearchModalProps {
  projectId: string;
  onSelectSession: (id: string | null, title?: string | null) => void;
}

/**
 * ✨ 对话搜索弹窗组件
 *
 * 功能说明：
 * - 点击搜索图标弹出居中搜索窗口
 * - 输入关键词实时搜索对话历史
 * - 显示搜索结果列表，点击跳转到对应对话
 * - 支持 ESC 键关闭、点击背景关闭
 * - 优雅的进入/退出动画效果
 *
 * 设计参考：类似 Gemini 的搜索交互方式
 */
export function ChatSearchModal({ projectId, onSelectSession }: ChatSearchModalProps) {
  // 搜索状态
  const [query, setQuery] = useState("");
  // 🚀 性能优化：使用统一的防抖 Hook
  const debouncedQuery = useDebounce(query, 300);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  // 弹窗状态
  const { isChatSearchOpen, closeChatSearch } = useUIStore();

  // 输入框引用（用于自动聚焦）
  const inputRef = useRef<HTMLInputElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  // ✨ 弹窗打开时自动聚焦输入框
  useEffect(() => {
    if (isChatSearchOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isChatSearchOpen]);

  // ✨ ESC 键关闭弹窗
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isChatSearchOpen) {
        closeChatSearch();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isChatSearchOpen, closeChatSearch]);

  // ✨ 执行搜索（使用防抖值触发）
  useEffect(() => {
    if (!debouncedQuery || debouncedQuery.length < 2) {
      setResults([]);
      return;
    }

    // 🚀 防抖已由 useDebounce Hook 处理，直接执行搜索
    performSearch(debouncedQuery);
  }, [debouncedQuery, projectId]);

  // 搜索 API 调用
  const performSearch = async (searchQuery: string) => {
    setIsSearching(true);
    const token = getToken();
    try {
      const res = await fetch(`${BASE_URL}/api/chat/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ query: searchQuery, project_id: projectId })
      });
      if (res.ok) {
        const data = await res.json();
        setResults(data.results || []);
      }
    } catch (e) {
      console.error('Search failed:', e);
    } finally {
      setIsSearching(false);
    }
  };

  // 点击搜索结果，跳转到对应对话
  const handleSelectResult = (result: SearchResult) => {
    onSelectSession(result.session_id, result.session_title);
    closeChatSearch();
    setQuery("");
    setResults([]);
  };

  // 点击背景关闭
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === modalRef.current) {
      closeChatSearch();
    }
  };

  // 弹窗关闭时清空状态
  const handleClose = () => {
    closeChatSearch();
    setQuery("");
    setResults([]);
  };

  if (!isChatSearchOpen) return null;

  return (
    <div
      ref={modalRef}
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/40 backdrop-blur-sm animate-in fade-in duration-200"
    >
      <div className="w-full max-w-lg mx-4 bg-white dark:bg-neutral-900 rounded-xl shadow-2xl border border-gray-200 dark:border-neutral-700/50 animate-in slide-in-from-top-4 duration-300">
        {/* 搜索头部 */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 dark:border-neutral-800">
          <Search size={18} className="text-gray-400 dark:text-neutral-500" />
          <input
            ref={inputRef}
            type="text"
            placeholder="搜索对话历史..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 bg-transparent text-[15px] text-gray-800 dark:text-neutral-200 placeholder-gray-400 dark:placeholder-neutral-500 outline-none"
          />
          {isSearching && (
            <Loader2 size={16} className="text-blue-500 animate-spin" />
          )}
          <button
            onClick={handleClose}
            className="p-1.5 text-gray-400 dark:text-neutral-500 hover:text-gray-600 dark:hover:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* 搜索结果列表 */}
        <div className="max-h-[400px] overflow-y-auto">
          {/* 无搜索词提示 */}
          {query.length < 2 && (
            <div className="px-4 py-8 text-center">
              <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gray-100 dark:bg-neutral-800/50 flex items-center justify-center text-gray-400 dark:text-neutral-500">
                <MessageSquare size={20} strokeWidth={1.5} />
              </div>
              <p className="text-sm text-gray-500 dark:text-neutral-400">
                输入关键词搜索对话历史
              </p>
            </div>
          )}

          {/* 正在搜索 */}
          {query.length >= 2 && isSearching && results.length === 0 && (
            <div className="px-4 py-6 text-center">
              <Loader2 size={20} className="mx-auto text-blue-500 animate-spin mb-2" />
              <p className="text-sm text-gray-500 dark:text-neutral-400">正在搜索...</p>
            </div>
          )}

          {/* 无结果 */}
          {query.length >= 2 && !isSearching && results.length === 0 && (
            <div className="px-4 py-6 text-center">
              <p className="text-sm text-gray-500 dark:text-neutral-400">
                未找到相关对话
              </p>
            </div>
          )}

          {/* 搜索结果 */}
          {results.length > 0 && (
            <div className="px-2 py-2">
              <div className="px-2 py-1.5 text-[11px] text-gray-400 dark:text-neutral-500">
                找到 {results.length} 个相关对话
              </div>
              {results.map((result) => (
                <div
                  key={result.session_id}
                  onClick={() => handleSelectResult(result)}
                  className="group px-3 py-2.5 mb-1 rounded-lg cursor-pointer hover:bg-gray-100 dark:hover:bg-neutral-800/50 transition-colors"
                >
                  {/* 对话标题 */}
                  <div className="text-[14px] font-medium text-gray-700 dark:text-neutral-300 truncate mb-1">
                    {result.session_title}
                  </div>
                  {/* 匹配的消息内容预览 */}
                  {result.matched_messages.slice(0, 2).map((msg, idx) => (
                    <div
                      key={idx}
                      className="text-[12px] text-gray-500 dark:text-neutral-400 line-clamp-2 leading-relaxed"
                    >
                      {/* ✨ 高亮显示匹配文本 */}
                      {msg.highlight.split('\n').map((line, lineIdx) => (
                        <span key={lineIdx}>
                          {lineIdx > 0 && <br />}
                          {line.split(/(<em>|<\/em>)/).map((part, partIdx) => {
                            if (part === '<em>') return null;
                            if (part === '</em>') return null;
                            // 检查是否是高亮文本（紧跟在 <em> 之后）
                            const isHighlight = line.split(/(<em>|<\/em>)/)[partIdx - 1] === '<em>';
                            return isHighlight ? (
                              <span key={partIdx} className="bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 font-medium rounded px-0.5">
                                {part}
                              </span>
                            ) : (
                              <span key={partIdx}>{part}</span>
                            );
                          })}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 底部提示 */}
        <div className="px-4 py-2 border-t border-gray-100 dark:border-neutral-800 text-[11px] text-gray-400 dark:text-neutral-500">
          按 <kbd className="px-1.5 py-0.5 bg-gray-100 dark:bg-neutral-800 rounded text-[10px]">ESC</kbd> 关闭
        </div>
      </div>
    </div>
  );
}