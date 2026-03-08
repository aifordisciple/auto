"use client";

import { useState, useRef, useEffect } from "react";
import { Bot, User, Sparkles, Copy, Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { fetchEventSource } from '@microsoft/fetch-event-source';

import { useChatStore } from "@/store/useChatStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { useAuthStore } from "@/store/useAuthStore";
import { MarkdownBlock } from "../MarkdownBlock";
import { StrategyCard, parseStrategyCard } from "./StrategyCard";
import { BASE_URL } from "@/lib/api";

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

function MessageActionButtons({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await copyToClipboard(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-1">
      <button 
        onClick={handleCopy}
        className="flex items-center gap-1.5 p-1.5 rounded-md hover:bg-neutral-800 text-neutral-500 hover:text-neutral-300 transition-all border border-transparent hover:border-neutral-700"
        title="复制全文"
      >
        {copied ? (
          <><Check className="w-3.5 h-3.5 text-green-500" /><span className="text-[10px]">已复制</span></>
        ) : (
          <><Copy className="w-3.5 h-3.5" /><span className="text-[10px]">复制</span></>
        )}
      </button>
    </div>
  );
}

export function ChatStage() {
  const { currentProjectId, mountedFiles, setActiveTool, updateToolParam, currentSessionId, setCurrentSessionId } = useWorkspaceStore();
  const { messages, addMessage, setMessages, appendLastMessage, isTyping, setIsTyping } = useChatStore();
  const { updateCredits } = useAuthStore();

  const [inputValue, setInputValue] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isStreamingRef = useRef(false);

  // Fetch messages when session changes
  useEffect(() => {
    const fetchMessages = async () => {
      if (!currentSessionId) {
        setMessages([]);
        return;
      }
      
      if (isStreamingRef.current) {
        return;
      }
      
      const token = localStorage.getItem('autonome_access_token');
      try {
        const res = await fetch(`${BASE_URL}/api/chat/sessions/${currentSessionId}/messages`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (data.data && data.data.length > 0) {
          const formattedMessages = data.data.map((msg: { role: string; content: string; id: number }) => ({
            id: String(msg.id),
            role: msg.role as 'user' | 'assistant',
            content: msg.content,
            timestamp: Date.now()
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
  }, [currentSessionId, setMessages]);

  useEffect(() => {
    const handleRefreshChat = () => {
      if (!currentSessionId) return;
      const token = localStorage.getItem('autonome_access_token');
      fetch(`${BASE_URL}/api/chat/sessions/${currentSessionId}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
        .then(res => res.json())
        .then(data => {
          if (data.data && data.data.length > 0) {
            const formattedMessages = data.data.map((msg: { role: string; content: string; id: number }) => ({
              id: String(msg.id),
              role: msg.role as 'user' | 'assistant',
              content: msg.content,
              timestamp: Date.now()
            }));
            setMessages(formattedMessages);
          }
        })
        .catch(console.error);
    };
    
    window.addEventListener('refresh-chat', handleRefreshChat);
    return () => window.removeEventListener('refresh-chat', handleRefreshChat);
  }, [setMessages, currentSessionId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  useEffect(() => { scrollToBottom(); }, [messages, isTyping]);

  // ✨ 监听全局快捷键发来的聚焦信号
  useEffect(() => {
    const handleFocusInput = () => {
      const inputEl = document.getElementById("chat-input-box");
      if (inputEl) {
        inputEl.focus();
      }
    };

    window.addEventListener('shortcut-focus-input', handleFocusInput);
    return () => window.removeEventListener('shortcut-focus-input', handleFocusInput);
  }, []);

  const handleSend = async (messageText?: string) => {
    const currentInput = messageText || inputValue;
    if (!currentInput?.trim()) return;
    
    if (!messageText) {
      setInputValue("");
    }
    
    addMessage('user', currentInput);
    addMessage('assistant', ''); 
    setIsTyping(true);
    
    // ✨ 开启流式护盾
    isStreamingRef.current = true;

    try {
      const token = localStorage.getItem('autonome_access_token');
      console.log('[Chat] Sending message:', { project_id: currentProjectId, session_id: currentSessionId });
      
      await fetchEventSource(`${BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          project_id: currentProjectId,
          message: currentInput,
          context_files: mountedFiles,
          session_id: currentSessionId
        }),
        openWhenHidden: true,
        onopen: async (res) => {
          if (!res.ok || res.status !== 200) {
            throw new Error(`Server responded with ${res.status}`);
          }
        },
        onmessage(event) {
          if (event.event === 'session_info') {
            const data = JSON.parse(event.data);
            if (data.is_new) {
              setCurrentSessionId(data.session_id);
              window.dispatchEvent(new Event('refresh-sessions'));
              fetch(`${BASE_URL}/api/chat/sessions/${data.session_id}/auto-name`, {
                method: "POST",
                headers: { 'Authorization': `Bearer ${token}` }
              }).catch(e => console.error("自动命名失败", e));
            }
          } else if (event.event === 'message') {
            const data = JSON.parse(event.data);
            appendLastMessage(data.content);
          } else if (event.event === 'tool') {
            const data = JSON.parse(event.data);
            setActiveTool(data.tool);
            if (data.tool.id === 'rnaseq-qc') {
              setTimeout(() => updateToolParam('qual_threshold', 30), 300);
            }
          } else if (event.event === 'billing') {
            const data = JSON.parse(event.data);
            updateCredits(data.balance);
          } else if (event.event === 'done') {
            isStreamingRef.current = false;
            setIsTyping(false);
          }
        },
        onclose() {
          isStreamingRef.current = false;
          setIsTyping(false);
        },
        onerror(err) {
          isStreamingRef.current = false;
          setIsTyping(false);
          console.error("Connection Error:", err);
          appendLastMessage("\n\n**[系统错误]** 连接后端大脑失败，请检查 FastAPI 服务是否启动。");
          throw err; 
        }
      });
    } catch (error) {
      isStreamingRef.current = false;
      setIsTyping(false);
      console.error('[Chat] Send error:', error);
      appendLastMessage("\n\n**[系统错误]** 发送消息失败，请检查控制台。");
    }
  };

  const isChatEmpty = messages.length === 0;

  const renderInputBox = () => (
    <div className="w-full bg-white dark:bg-[#1e1e1f] border border-gray-200 dark:border-neutral-800/60 rounded-2xl p-2 focus-within:ring-1 focus-within:ring-blue-500/50 transition-all shadow-sm dark:shadow-xl flex flex-col">
      <textarea
        id="chat-input-box"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        placeholder="Ask anything or generate an analysis script..."
        className="w-full bg-transparent text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-neutral-500 resize-none outline-none max-h-48 min-h-[60px] p-3 text-sm"
      />
      <div className="flex justify-between items-center px-2 pb-1">
        <div className="flex gap-2"></div>
        <button
          onClick={() => handleSend()}
          disabled={isTyping || !inputValue.trim()}
          className="p-2 bg-blue-600 hover:bg-blue-700 dark:bg-white dark:text-black dark:hover:bg-neutral-200 disabled:bg-gray-300 dark:disabled:bg-neutral-800 disabled:text-neutral-500 dark:disabled:text-neutral-500 text-white rounded-full transition-colors"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full w-full bg-white dark:bg-[#131314]">

      {isChatEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center px-4 pb-20 animate-in fade-in duration-500">
          <h1 className="text-3xl md:text-4xl font-semibold text-gray-900 dark:text-neutral-200 mb-8 tracking-tight">
            What do you want to analyze?
          </h1>

          <div className="w-full max-w-3xl">
            {renderInputBox()}

            <div className="flex flex-wrap items-center justify-center gap-2 mt-6">
              <button
                onClick={() => setInputValue('读取单细胞数据并绘制 UMAP')}
                className="text-xs px-4 py-2 rounded-full border border-gray-200 dark:border-neutral-800/80 text-gray-600 dark:text-neutral-400 hover:text-gray-900 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-800 transition-colors"
              >
                单细胞 UMAP 降维
              </button>
              <button
                onClick={() => setInputValue('读取表达矩阵并绘制火山图')}
                className="text-xs px-4 py-2 rounded-full border border-gray-200 dark:border-neutral-800/80 text-gray-600 dark:text-neutral-400 hover:text-gray-900 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-800 transition-colors"
              >
                差异基因火山图
              </button>
              <button
                onClick={() => setInputValue('对数据进行 QC 质控分析')}
                className="text-xs px-4 py-2 rounded-full border border-gray-200 dark:border-neutral-800/80 text-gray-600 dark:text-neutral-400 hover:text-gray-900 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-800 transition-colors"
              >
                数据 QC 质控
              </button>
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className="flex-1 overflow-y-auto px-4 pt-6 pb-4 scroll-smooth">
            <div className="max-w-4xl mx-auto space-y-6"> 
              <AnimatePresence>
                {messages.map((msg) => {
                  if (msg.role === 'assistant' && (!msg.content || msg.content.trim() === '')) {
                    return null;
                  }
                  
                  const strategyCard = msg.role === 'assistant' ? parseStrategyCard(msg.content) : null;
                  
                  return (
                  <motion.div 
                    key={msg.id} 
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2 }}
                    className={`flex flex-col group ${msg.role === 'user' ? 'items-end' : 'items-start'} max-w-4xl mx-auto w-full`}
                  >
                    <div className={`flex items-start gap-3 w-full ${msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''}`}>
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                        msg.role === 'user'
                          ? 'bg-gray-200 dark:bg-neutral-800 text-gray-700 dark:text-neutral-300'
                          : 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'
                      }`}>
                        {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
                      </div>
                      <div className={`flex-1 rounded-xl p-4 ${
                        msg.role === 'user'
                          ? 'bg-blue-50 dark:bg-neutral-800/50 text-gray-800 dark:text-neutral-200'
                          : 'bg-gray-100 dark:bg-neutral-900/60 text-gray-700 dark:text-neutral-300'
                      }`}>
                        {msg.role === 'user' ? (
                          <div className="whitespace-pre-wrap text-sm">{msg.content}</div>
                        ) : (
                          <div className="flex flex-col gap-4 w-full">

                            {/* ✨ 调整顺序 1：先渲染文本、代码、以及执行完成后的结果 */}
                            {msg.content && (() => {
                              let cleanText = msg.content.replace(/```json_strategy[\s\S]*?(```|$)/g, '').trim();

                              // 🌟 魔法拦截器：自动将后台物理路径升级为前端可见的图片和链接
                              const apiBase = BASE_URL.replace(/\/$/, '');

                              // 使用正则将内容按代码块进行分割，保护代码块内部的路径不被替换
                              const parts = cleanText.split(/(```[\s\S]*?```)/g);

                              cleanText = parts.map(part => {
                                // 如果是包裹在 ``` 里的代码块，直接跳过，防止破坏 AI 写的代码
                                if (part.startsWith('```')) return part;

                                let text = part;

                                // 1. 匹配图片格式 (png, jpg, svg等)，自动转成 Markdown 图片显示
                                text = text.replace(
                                  /\/app\/uploads\/project_(\d+)\/([^\s'"]+\.(png|jpg|jpeg|gif|svg))/gi,
                                  (match, pId, filePath) => {
                                    return `\n\n![分析图表](${apiBase}/api/projects/${pId}/files/${filePath}/view)\n\n`;
                                  }
                                );

                                // 2. 匹配数据文档格式 (tsv, csv, txt等)，自动转成可点击的下载/预览链接
                                text = text.replace(
                                  /\/app\/uploads\/project_(\d+)\/([^\s'"]+\.(csv|tsv|txt|h5ad|pdf|xlsx))/gi,
                                  (match, pId, filePath) => {
                                    const fileName = filePath.split('/').pop();
                                    return `[📥 下载/查看 ${fileName}](${apiBase}/api/projects/${pId}/files/${filePath}/view)`;
                                  }
                                );

                                return text;
                              }).join('');

                              return cleanText ? <MarkdownBlock content={cleanText} /> : null;
                            })()}

                            {/* ✨ 调整顺序 2：把策略卡片放到最后面，作为用户的下一步行动入口 */}
                            {strategyCard && <StrategyCard data={strategyCard} />}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className={`flex items-center gap-2 mt-1 px-1 opacity-0 group-hover:opacity-100 transition-opacity ${msg.role === 'user' ? 'mr-11' : 'ml-11'}`}>
                      <MessageActionButtons content={msg.content} />
                    </div>
                  </motion.div>
                )})}
              </AnimatePresence>
              
              {isTyping && 
               messages.length > 0 && 
               messages[messages.length - 1].role === 'assistant' && 
               !messages[messages.length - 1].content && (
                <motion.div 
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-start gap-4"
                >
                  <div className="w-8 h-8 rounded-lg bg-blue-900/20 border border-blue-500/30 flex items-center justify-center shrink-0 mt-1 relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/10 to-purple-500/10 animate-pulse"></div>
                    <Sparkles size={16} className="text-blue-400" />
                  </div>
                  
                  <div className="flex items-center gap-3 bg-white dark:bg-[#1e1e1f] border border-gray-200 dark:border-neutral-800/60 rounded-2xl rounded-tl-sm px-5 py-3.5 shadow-sm dark:shadow-lg relative overflow-hidden">
                    <span className="text-sm font-medium bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-purple-400 to-blue-400 animate-pulse">
                      Autonome is processing
                    </span>
                    
                    <div className="flex gap-1.5 items-center mt-1">
                      <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.3s]"></div>
                      <div className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-bounce [animation-delay:-0.15s]"></div>
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-bounce"></div>
                    </div>
                  </div>
                </motion.div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="shrink-0 px-4 pt-2 pb-3 bg-white dark:bg-[#131314]">
            <div className="max-w-4xl mx-auto">
              {renderInputBox()}
              <div className="text-center mt-2 text-[10px] text-gray-400 dark:text-neutral-500">
                Autonome Copilot can make mistakes. Check important info.
              </div>
            </div>
          </div>
        </>
      )}

    </div>
  );
}
