"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import { Bot, User, Sparkles, Copy, Check, Folder, FolderOpen, ChevronRight, ChevronDown, Eye, Download, FileText, Image as ImageIcon, Table2, X, Loader2, FileImage, FileSpreadsheet, Paperclip } from "lucide-react";
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
        className="flex items-center gap-1.5 p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-neutral-800 text-gray-500 dark:text-neutral-500 hover:text-gray-700 dark:hover:text-neutral-300 transition-all border border-transparent hover:border-gray-200 dark:hover:border-neutral-700"
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

// ==========================================
// ✨ 树状资产卡片组件集合
// ==========================================

const getFileIcon = (filename: string) => {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tsv') || lower.endsWith('.csv') || lower.endsWith('.txt') || lower.endsWith('.log')) {
    return <Table2 size={15} className="text-blue-500 dark:text-blue-400 shrink-0" />;
  }
  if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.pdf') || lower.endsWith('.svg')) {
    return <ImageIcon size={15} className="text-pink-500 dark:text-pink-400 shrink-0" />;
  }
  return <FileText size={15} className="text-gray-500 dark:text-neutral-400 shrink-0" />;
};

const AssetTreeNode = ({ node, level, onPreview, onDownload }: { node: any, level: number, onPreview: any, onDownload: any }) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const isFolder = node.type === 'folder';

  return (
    <div className="flex flex-col">
      <div
        className={`flex items-center gap-2 py-1.5 px-2 hover:bg-gray-100 dark:hover:bg-[#2d2d30]/80 rounded-md cursor-pointer group transition-colors`}
        style={level > 0 ? { marginLeft: `${level * 16}px`, borderLeft: '1px solid', borderLeftColor: level > 1 ? 'transparent' : undefined, paddingLeft: '12px' } : {}}
        onClick={() => isFolder ? setIsExpanded(!isExpanded) : onPreview(node.url, node.name)}
      >
        {isFolder ? (
          <div className="flex items-center gap-1 text-gray-500 dark:text-gray-400 shrink-0">
            {isExpanded ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
            {isExpanded ? <FolderOpen size={15} className="text-blue-500 dark:text-blue-400"/> : <Folder size={15} className="text-blue-500 dark:text-blue-400"/>}
          </div>
        ) : (
          <div className="ml-5 shrink-0">{getFileIcon(node.name)}</div>
        )}

        <span className={`text-[13px] truncate flex-1 tracking-wide ${isFolder ? 'font-medium text-gray-800 dark:text-gray-200' : 'text-gray-600 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-gray-100'}`}>
          {node.name}
        </span>

        {!isFolder && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
             <button onClick={(e) => { e.stopPropagation(); onPreview(node.url, node.name); }} className="p-1 text-gray-400 hover:text-emerald-500 bg-white dark:bg-[#1e1e20] shadow-sm rounded border border-gray-200 dark:border-gray-700" title="安全预览"><Eye size={13} /></button>
             <button onClick={(e) => { e.stopPropagation(); onDownload(node.url, node.name); }} className="p-1 text-gray-400 hover:text-blue-500 bg-white dark:bg-[#1e1e20] shadow-sm rounded border border-gray-200 dark:border-gray-700" title="下载"><Download size={13} /></button>
          </div>
        )}
      </div>

      {isFolder && isExpanded && (
        <div className="flex flex-col mt-0.5">
          {Object.values(node.children).map((child: any) => (
            <AssetTreeNode key={child.name} node={child} level={level + 1} onPreview={onPreview} onDownload={onDownload} />
          ))}
        </div>
      )}
    </div>
  );
};

// ✨ ExecutionResultCard - 生成资产树状卡片组件
function ExecutionResultCard({ content, onInterpret }: { content: string, onInterpret: (files: string[], code: string, userMessage: string) => void }) {
  const [isExpanded, setIsExpanded] = useState(true);

  // 解析并提取所有后台物理路径
  const fileRegex = /\/app\/uploads\/project_[a-zA-Z0-9_-]+\/([^\s'"]+\.([a-zA-Z0-9]+))/gi;
  const files: { projectId: string, path: string, name: string, ext: string }[] = [];

  const matches = Array.from(content.matchAll(fileRegex));
  for (const match of matches) {
    // 去重
    if (!files.find(f => f.path === match[1])) {
      files.push({
        projectId: match[0].match(/project_[a-zA-Z0-9_-]+/)?.[0]?.replace('project_', '') || '',
        path: match[1],
        name: match[1].split('/').pop() || match[1],
        ext: match[2].toLowerCase()
      });
    }
  }

  // ✨ 从消息内容中提取隐藏的元数据（用户消息和代码）
  let extractedCode = '';
  let extractedUserMessage = '';
  const metaMatch = content.match(/<!-- DEEP_INTERPRET_META\n([\s\S]*?)DEEP_INTERPRET_META -->/);
  if (metaMatch) {
    const metaData = metaMatch[1];
    const userMsgMatch = metaData.match(/USER_MESSAGE: (.*)/);
    const codeMatch = metaData.match(/CODE_START\n([\s\S]*?)\nCODE_END/);
    if (userMsgMatch) extractedUserMessage = userMsgMatch[1].trim();
    if (codeMatch) extractedCode = codeMatch[1].trim();
  }

  // 吃干抹净：将路径及多余的 Markdown 标记从原文本中彻底剔除
  let cleanContent = content.replace(fileRegex, '');
  cleanContent = cleanContent.replace(/\[.*?\]\(\)/g, ''); // 清理空的 markdown 链接
  cleanContent = cleanContent.replace(/^[-*+]\s*$/gm, ''); // 清理只剩下无序列表符号的空行
  cleanContent = cleanContent.replace(/^[\s\n]+$/g, ''); // 清理多余空行
  // 清理隐藏的元数据
  cleanContent = cleanContent.replace(/<!-- DEEP_INTERPRET_META[\s\S]*?DEEP_INTERPRET_META -->\n?/g, '');
  cleanContent = cleanContent.trim();

  // 如果没有检测到文件，降级为普通渲染
  if (files.length === 0) return <MarkdownBlock content={cleanContent} />;

  const apiBase = BASE_URL.replace(/\/$/, '');

  return (
    <div className="flex flex-col gap-3 w-full mt-2">
      {cleanContent && <MarkdownBlock content={cleanContent} />}

      <div className="bg-[#1a1a1b] dark:bg-[#1a1a1b] border border-neutral-700/60 dark:border-neutral-800 rounded-xl overflow-hidden shadow-md w-full">
        {/* 卡片头部：折叠控制 */}
        <div
          className="flex items-center justify-between px-4 py-3 bg-neutral-800/50 dark:bg-neutral-800/50 cursor-pointer hover:bg-neutral-800/80 dark:hover:bg-neutral-700/50 transition-colors"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-neutral-200 dark:text-neutral-200">生成产物资产 (Assets)</span>
            <span className="px-2 py-0.5 rounded-full bg-blue-900/30 dark:bg-blue-900/30 text-[10px] text-blue-400 font-mono">
              {files.length} 个文件
            </span>
          </div>
          {isExpanded ? <ChevronDown size={16} className="text-neutral-400" /> : <ChevronRight size={16} className="text-neutral-400" />}
        </div>

        {/* 卡片内容：文件列表 */}
        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="flex flex-col gap-1 p-2 border-t border-neutral-800/50 dark:border-neutral-800"
            >
              {files.map((file, idx) => {
                const isImage = ['png', 'jpg', 'jpeg', 'gif', 'svg'].includes(file.ext);
                const isData = ['csv', 'tsv', 'txt', 'h5ad', 'xlsx'].includes(file.ext);
                const fileUrl = `${apiBase}/api/projects/${file.projectId}/files/${file.path}/view`;

                return (
                  <div key={idx} className="group flex items-center justify-between p-2.5 rounded-lg hover:bg-neutral-800/60 dark:hover:bg-neutral-700/50 transition-colors">
                    <div className="flex items-center gap-3 overflow-hidden">
                      <div className={`p-1.5 rounded-md ${isImage ? 'bg-blue-900/20 text-blue-400' : isData ? 'bg-emerald-900/20 text-emerald-400' : 'bg-neutral-800 text-neutral-400'}`}>
                        {isImage ? <FileImage size={14} /> : isData ? <FileSpreadsheet size={14} /> : <FileText size={14} />}
                      </div>
                      <span className="text-sm text-neutral-300 dark:text-neutral-300 font-mono truncate">{file.name}</span>
                    </div>
                    <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <a
                        href={fileUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="p-1.5 rounded-md bg-neutral-700/50 hover:bg-blue-500/20 text-neutral-400 hover:text-blue-400 transition-colors"
                        title={isImage ? "预览图片" : "下载数据"}
                      >
                        {isImage ? <Eye size={14} /> : <Download size={14} />}
                      </a>
                    </div>
                  </div>
                );
              })}
            </motion.div>
          )}
        </AnimatePresence>

        {/* 卡片底部：闪烁的专家召唤按钮 */}
        <div className="p-3 border-t border-neutral-800/50 dark:border-neutral-800 bg-[#1e1e1f] dark:bg-[#1e1e1f]/80">
          <button
            onClick={() => {
              // 提取文件相对路径传递给 AI
              const relativePaths = files.map(f => f.path);
              onInterpret(relativePaths, extractedCode, extractedUserMessage);
            }}
            className="w-full py-2.5 rounded-lg bg-gradient-to-r from-blue-900/20 to-indigo-900/20 hover:from-blue-600/20 hover:to-indigo-600/20 border border-blue-500/20 hover:border-blue-400/50 text-blue-300 hover:text-blue-200 text-sm font-medium flex items-center justify-center gap-2 transition-all group shadow-[0_0_15px_rgba(59,130,246,0.1)] hover:shadow-[0_0_20px_rgba(59,130,246,0.2)]"
          >
            <Sparkles size={16} className="text-blue-400 group-hover:animate-pulse" />
            <span>✨ 深度解读分析结果</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// ✨ 升级版树状卡片，带有解读按钮
const AssetTreeCard = ({ links, onPreview, onDownload, onInterpret }: { links: {url: string, title: string}[], onPreview: any, onDownload: any, onInterpret?: () => void }) => {
  // 提取任务 ID（从第一个文件的路径中）
  const taskId = useMemo(() => {
    if (links.length === 0) return null;
    const match = links[0].title.match(/task_([a-zA-Z0-9]+)/);
    return match ? match[1] : null;
  }, [links]);

  const tree = useMemo(() => {
    const root: any = { type: 'folder', name: 'Analysis Results', children: {} };
    links.forEach(link => {
      const parts = link.title.split('/');
      let current = root;
      parts.forEach((part, idx) => {
        if (!current.children[part]) {
          current.children[part] = {
            name: part,
            type: idx === parts.length - 1 ? 'file' : 'folder',
            children: {},
            url: idx === parts.length - 1 ? link.url : null
          };
        }
        current = current.children[part];
      });
    });
    return root;
  }, [links]);

  return (
    <div className="w-full max-w-xl mt-3 bg-white dark:bg-[#1e1e20] border border-gray-200 dark:border-[#2d2d30] rounded-xl shadow-sm dark:shadow-none overflow-hidden flex flex-col">
      <div className="px-4 py-2.5 bg-gray-50 dark:bg-[#252528] border-b border-gray-200 dark:border-[#2d2d30] flex items-center gap-2 shrink-0">
        <FolderOpen size={16} className="text-purple-500" />
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
          生成的分析资产 (Output Assets)
          {taskId && (
            <span className="ml-2 text-xs font-mono text-purple-600 dark:text-purple-400 bg-purple-100 dark:bg-purple-900/30 px-1.5 py-0.5 rounded">
              Task: {taskId}
            </span>
          )}
        </span>
        <span className="text-xs bg-gray-200 dark:bg-black/30 text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded-full ml-auto">{links.length} files</span>
      </div>
      <div className="p-2 max-h-64 overflow-y-auto custom-scrollbar">
        {Object.values(tree.children).map((node: any) => (
          <AssetTreeNode key={node.name} node={node} level={0} onPreview={onPreview} onDownload={onDownload} />
        ))}
      </div>
      {/* ✨ 新增：深度解读动作栏 */}
      {onInterpret && (
        <div className="p-3 bg-gray-50 dark:bg-[#252528]/50 border-t border-gray-200 dark:border-[#2d2d30] flex justify-end">
          <button
            onClick={onInterpret}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg shadow-md transition-all group"
          >
            <Sparkles size={16} className="text-blue-200 group-hover:text-white group-hover:animate-pulse" />
            深度解读分析结果
          </button>
        </div>
      )}
    </div>
  );
};

export function ChatStage() {
  const { currentProjectId, setActiveTool, updateToolParam, currentSessionId, setCurrentSessionId, pendingChatAttachments, clearPendingChatAttachments } = useWorkspaceStore();
  const { messages, addMessage, setMessages, appendLastMessage, isTyping, setIsTyping } = useChatStore();
  const { updateCredits } = useAuthStore();

  const [inputValue, setInputValue] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isStreamingRef = useRef(false);

  // ✨ 聊天区文件预览状态引擎
  const [previewData, setPreviewData] = useState<{url: string, filename: string} | null>(null);
  const [previewType, setPreviewType] = useState<'image' | 'text' | 'pdf' | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const handleDownloadAsset = async (url: string, filename: string) => {
    try {
      const token = localStorage.getItem('autonome_access_token');
      const fetchUrl = url.startsWith('http') ? url : `${BASE_URL}${url}`;
      const res = await fetch(fetchUrl, { headers: { 'Authorization': `Bearer ${token}` } });
      if (!res.ok) throw new Error("获取文件失败");
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl; a.download = filename;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(objUrl);
    } catch (e) {
      alert("❌ 下载失败，可能是网络问题或无权限。");
    }
  };

  const handlePreviewAsset = async (url: string, filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    const isImage = ['png', 'jpg', 'jpeg', 'svg', 'gif'].includes(ext);
    const isText = ['txt', 'csv', 'tsv', 'md', 'py', 'r', 'json', 'sh', 'log', 'yaml'].includes(ext);
    const isPdf = ext === 'pdf';

    if (!isImage && !isText && !isPdf) {
      alert("💡 当前格式暂不支持内存预览，请点击右侧【下载】按钮获取。");
      return;
    }

    setPreviewData({ url, filename });
    setIsPreviewLoading(true); setPreviewContent(null);

    try {
      const token = localStorage.getItem('autonome_access_token');
      const fetchUrl = url.startsWith('http') ? url : `${BASE_URL}${url}`;
      const res = await fetch(fetchUrl, { headers: { 'Authorization': `Bearer ${token}` } });
      if (!res.ok) throw new Error("获取失败");

      if (isImage || isPdf) {
        setPreviewContent(URL.createObjectURL(await res.blob()));
        setPreviewType(isImage ? 'image' : 'pdf');
      } else {
        const text = await res.text();
        setPreviewContent(text.length > 100000 ? text.substring(0, 100000) + '\n\n... [⚠️ 数据表过大，内存预览已截断]' : text);
        setPreviewType('text');
      }
    } catch (e) {
      alert("❌ 预览加载失败。"); setPreviewData(null);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const closePreview = () => {
    if ((previewType === 'image' || previewType === 'pdf') && previewContent) URL.revokeObjectURL(previewContent);
    setPreviewData(null); setPreviewContent(null);
  };

  // ✨ 深度解读函数 - 调用专用解读 API
  const handleInterpret = async (files: string[] = [], code: string = '', userMessage: string = '') => {
    if (!files.length || !code) {
      // 降级：如果没有代码或文件，使用普通聊天
      const interpretPrompt = "\n\n请对以上分析结果进行深度解读，包括：1) 主要发现和结论；2) 图表数据的生物学意义；3) 可能的临床或研究应用价值。";
      await handleSend(interpretPrompt, files);
      return;
    }

    // 添加用户消息提示
    addMessage('user', '🧬 深度解读分析结果');
    addMessage('assistant', '');
    setIsTyping(true);
    isStreamingRef.current = true;

    try {
      const token = localStorage.getItem('autonome_access_token');

      await fetchEventSource(`${BASE_URL}/api/chat/interpret`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          project_id: currentProjectId,
          session_id: currentSessionId,
          user_message: userMessage || '分析任务',
          code: code,
          files: files
        }),
        openWhenHidden: true,
        onopen: async (res) => {
          if (!res.ok || res.status !== 200) {
            throw new Error(`Server responded with ${res.status}`);
          }
        },
        onmessage(event) {
          if (event.event === 'message') {
            const data = JSON.parse(event.data);
            appendLastMessage(data.content);
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
          console.error("Interpret Error:", err);
          appendLastMessage("\n\n**[系统错误]** 深度解读服务异常，请稍后重试。");
          throw err;
        }
      });
    } catch (error) {
      isStreamingRef.current = false;
      setIsTyping(false);
      console.error('[Interpret] Error:', error);
      appendLastMessage("\n\n**[系统错误]** 深度解读请求失败。");
    }
  };

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

  // ✨ 监听任务结果追加事件
  useEffect(() => {
    const handleAppendResultMessage = (event: any) => {
      const newMsg = event.detail;
      if (newMsg && newMsg.content) {
        // 使用 addMessage 来追加消息
        addMessage(newMsg.role, newMsg.content);

        // 自动滚动到底部看卡片
        setTimeout(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }, 100);
      }
    };

    window.addEventListener('append-result-message', handleAppendResultMessage);
    return () => window.removeEventListener('append-result-message', handleAppendResultMessage);
  }, [addMessage]);

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

  const handleSend = async (messageText?: string, contextFiles?: string[]) => {
    const currentInput = messageText || inputValue;
    // 允许空消息但有附件时发送
    if (!currentInput?.trim() && pendingChatAttachments.length === 0) return;

    if (!messageText) {
      setInputValue("");
    }

    // 合并附件
    const filesToSend = contextFiles || pendingChatAttachments;

    addMessage('user', currentInput);
    addMessage('assistant', '');
    setIsTyping(true);

    // ✨ 开启流式护盾
    isStreamingRef.current = true;

    // 发送后清除附件
    if (pendingChatAttachments.length > 0) {
      clearPendingChatAttachments();
    }

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
          context_files: filesToSend,  // 使用附件
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
        {/* 左侧: 附件显示 */}
        {pendingChatAttachments.length > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 border border-blue-500/30 rounded-lg">
            <Paperclip size={14} className="text-blue-400" />
            <span className="text-xs text-blue-300">{pendingChatAttachments.length} 个文件已附加</span>
            <button
              onClick={clearPendingChatAttachments}
              className="ml-1 hover:text-white text-neutral-400 transition-colors"
              title="清除附件"
            >
              <X size={12} />
            </button>
          </div>
        )}
        {/* 右侧: 发送按钮 */}
        <button
          onClick={() => handleSend()}
          disabled={isTyping || (!inputValue.trim() && pendingChatAttachments.length === 0)}
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
          <div className="flex-1 overflow-y-auto px-4 pt-6 pb-4 scroll-smooth bg-white dark:bg-[#131314]">
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

                            {/* ✨ 使用 AssetTreeCard 渲染资产文件 */}
                            {msg.content && (() => {
                              // ✨ 检测是否是策略消息，如果是则不提取文件（策略阶段的路径是假的）
                              const isStrategyMsg = msg.content.includes('```json_strategy');

                              // 如果是策略消息，不提取文件路径，只渲染文本
                              if (isStrategyMsg) {
                                let cleanText = msg.content.replace(/```json_strategy[\s\S]*?(```|$)/g, '').trim();
                                return <MarkdownBlock content={cleanText} />;
                              }

                              // ✨ 提取文件路径 - 只匹配真实结果路径（必须包含 results/task_）
                              // 排除策略消息中的示例路径
                              const filePatterns = [
                                // 真实结果路径格式: /app/uploads/project_xxx/results/task_xxx/xxx.png
                                /\/app\/uploads\/project_([a-zA-Z0-9_-]+)\/(results\/task_[a-zA-Z0-9_-]+\/[^\s'"]+\.([a-zA-Z0-9]+))/gi,
                              ];

                              const files: { projectId: string, path: string, name: string, ext: string }[] = [];

                              for (const pattern of filePatterns) {
                                const matches = Array.from(msg.content.matchAll(pattern));
                                for (const match of matches) {
                                  let projectId = '';
                                  let path = '';
                                  let ext = '';

                                  if (match.length === 4) {
                                    // 格式1: 有 project ID
                                    projectId = match[1];
                                    path = match[2];
                                    ext = match[3].toLowerCase();
                                  } else if (match.length === 3) {
                                    // 格式2/3: 无 project ID 或 results 路径
                                    path = match[1];
                                    ext = match[2].toLowerCase();
                                  }

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

                              // ✨ 使用 AssetTreeCard 树状卡片渲染
                              if (files.length > 0) {
                                const links = files.map(file => ({
                                  // 如果没有解析到 projectId，使用当前会话的 projectId
                                  url: `${BASE_URL}/api/projects/${file.projectId || currentProjectId}/files/${file.path}/view`,
                                  title: file.path
                                }));
                                // 提取文件相对路径用于深度解读
                                const filePaths = files.map(f => f.path);

                                // ✨ 从消息内容中提取隐藏的元数据（用户消息和代码）
                                let extractedCode = '';
                                let extractedUserMessage = '';
                                const metaMatch = msg.content.match(/<!-- DEEP_INTERPRET_META\n([\s\S]*?)DEEP_INTERPRET_META -->/);
                                if (metaMatch) {
                                  const metaData = metaMatch[1];
                                  const userMsgMatch = metaData.match(/USER_MESSAGE: (.*)/);
                                  const codeMatch = metaData.match(/CODE_START\n([\s\S]*?)\nCODE_END/);
                                  if (userMsgMatch) extractedUserMessage = userMsgMatch[1].trim();
                                  if (codeMatch) extractedCode = codeMatch[1].trim();
                                }

                                return (
                                  <AssetTreeCard
                                    links={links}
                                    onPreview={handlePreviewAsset}
                                    onDownload={handleDownloadAsset}
                                    onInterpret={() => handleInterpret(filePaths, extractedCode, extractedUserMessage)}
                                  />
                                );
                              } else {
                                // 无文件时降级为普通渲染，清理隐藏元数据
                                const cleanedContent = msg.content.replace(/<!-- DEEP_INTERPRET_META[\s\S]*?DEEP_INTERPRET_META -->\n?/g, '');
                                return <MarkdownBlock content={cleanedContent} />;
                              }
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
                  <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-500/30 flex items-center justify-center shrink-0 mt-1 relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/10 to-purple-500/10 animate-pulse"></div>
                    <Sparkles size={16} className="text-blue-600 dark:text-blue-400" />
                  </div>
                  
                  <div className="flex items-center gap-3 bg-white dark:bg-[#1e1e1f] border border-gray-200 dark:border-neutral-800/60 rounded-2xl rounded-tl-sm px-5 py-3.5 shadow-sm dark:shadow-lg relative overflow-hidden">
                    <span className="text-sm font-medium bg-clip-text text-transparent bg-gradient-to-r from-blue-600 dark:from-blue-400 via-purple-600 dark:via-purple-400 to-blue-600 dark:to-blue-400 animate-pulse">
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

      {/* ✨ 绝美沉浸式文件预览弹窗 */}
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
              ) : previewType === 'text' && previewContent ? (
                <div className="w-full h-full bg-white dark:bg-[#1e1e1e] rounded-xl border border-gray-200 dark:border-neutral-800 p-4 overflow-auto custom-scrollbar">
                  <pre className="text-[13px] leading-relaxed text-gray-800 dark:text-neutral-300 font-mono whitespace-pre-wrap">{previewContent}</pre>
                </div>
              ) : null}
            </div>

          </div>
        </div>
      )}

    </div>
  );
}
