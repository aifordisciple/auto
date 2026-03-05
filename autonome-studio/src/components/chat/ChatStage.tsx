"use client";

import { useState, useRef, useEffect } from "react";
import { Bot, User, Sparkles } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { fetchEventSource } from '@microsoft/fetch-event-source';

import { useChatStore } from "@/store/useChatStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { useAuthStore } from "@/store/useAuthStore";
import { MarkdownBlock } from "../MarkdownBlock";
import { StrategyCard, parseStrategyCard } from "./StrategyCard";
import { BASE_URL } from "@/lib/api";

export function ChatStage() {
  const { currentProjectId, mountedFiles, setActiveTool, updateToolParam, currentSessionId, setCurrentSessionId } = useWorkspaceStore();
  const { messages, addMessage, setMessages, appendLastMessage, isTyping, setIsTyping } = useChatStore();
  const { updateCredits } = useAuthStore();

  const [inputValue, setInputValue] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Fetch messages when session changes
  useEffect(() => {
    const fetchMessages = async () => {
      if (!currentSessionId) {
        setMessages([]);
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

  const handleSend = async (messageText?: string) => {
    const currentInput = messageText || inputValue;
    if (!currentInput?.trim()) return;
    
    if (!messageText) {
      setInputValue("");
    }
    
    addMessage('user', currentInput);
    addMessage('assistant', ''); 
    setIsTyping(true);

    try {
      const token = localStorage.getItem('autonome_access_token');
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
              fetch(`${BASE_URL}/api/chat/sessions/${data.session_id}/auto-name`, {
                method: "POST",
                headers: { 'Authorization': `Bearer ${token}` }
              }).then(() => {
                window.dispatchEvent(new Event('refresh-sessions'));
              });
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
            setIsTyping(false);
          }
        },
        onerror(err) {
          console.error("Connection Error:", err);
          appendLastMessage("\n\n**[系统错误]** 连接后端大脑失败，请检查 FastAPI 服务是否启动。");
          throw err; 
        }
      });
    } catch (error) {
      setIsTyping(false);
    }
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#131314]">
      {/* 消息滚动区 */}
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
                className={`flex items-start gap-3 max-w-4xl mx-auto w-full ${msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''}`}
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === 'user' 
                    ? 'bg-neutral-800 text-neutral-300' 
                    : 'bg-blue-900/40 text-blue-400'
                }`}>
                  {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
                </div>
                <div className={`flex-1 rounded-xl p-4 ${
                  msg.role === 'user' 
                    ? 'bg-neutral-800/50 text-neutral-200' 
                    : 'bg-neutral-900/60 text-neutral-300'
                }`}>
                  {msg.role === 'user' ? (
                    <div className="whitespace-pre-wrap text-sm">{msg.content}</div>
                  ) : strategyCard ? (
                    <StrategyCard data={strategyCard} />
                  ) : (
                    <MarkdownBlock content={msg.content} />
                  )}
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
              
              <div className="flex items-center gap-3 bg-[#1e1e1f] border border-neutral-800/60 rounded-2xl rounded-tl-sm px-5 py-3.5 shadow-lg relative overflow-hidden">
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

      {/* 底部输入区 */}
      <div className="shrink-0 px-4 pt-2 pb-3 bg-[#131314]">
        <div className="max-w-4xl mx-auto">
          <div className="bg-[#1e1e1f] border border-neutral-800/60 rounded-3xl p-2 focus-within:ring-1 focus-within:ring-blue-500/50 transition-all shadow-lg flex flex-col">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask anything or generate an analysis script..."
              className="w-full bg-transparent text-white placeholder-neutral-500 resize-none outline-none max-h-48 min-h-[60px] p-3 text-sm"
            />
            
            <div className="flex justify-between items-center px-2 pb-1">
              <div className="flex gap-2"></div>
              <button 
                onClick={() => handleSend()}
                disabled={isTyping || !inputValue.trim()}
                className="p-2 bg-white text-black hover:bg-neutral-200 disabled:bg-neutral-800 disabled:text-neutral-500 rounded-full transition-colors"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
              </button>
            </div>
          </div>

          <div className="text-center mt-2 text-[10px] text-neutral-500">
            Autonome Copilot can make mistakes. Check important info.
          </div>
        </div>
      </div>
    </div>
  );
}
