"use client";

import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus, vs } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check, Eye, Download, FileText, Image as ImageIcon, Table2, X, Loader2 } from 'lucide-react';
import { BASE_URL } from '@/lib/api';
import { useUIStore } from '@/store/useUIStore';

interface MarkdownBlockProps {
  content: string;
}

// 🎨 根据扩展名匹配漂亮的图标
const getFileIcon = (filename: string) => {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tsv') || lower.endsWith('.csv') || lower.endsWith('.txt') || lower.endsWith('.log')) {
    return <Table2 size={16} className="text-blue-500 dark:text-blue-400 shrink-0" />;
  }
  if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.jpeg') || lower.endsWith('.pdf') || lower.endsWith('.svg')) {
    return <ImageIcon size={16} className="text-pink-500 dark:text-pink-400 shrink-0" />;
  }
  return <FileText size={16} className="text-gray-500 dark:text-neutral-400 shrink-0" />;
};

// ✨ 商业级安全图片组件：精准报错与内存回收
const SecureImage = ({ src, alt, onPreview, onDownload, ...props }: any) => {
  const [imgSrc, setImgSrc] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!src) return;

    if (!src.includes('/api/projects/')) {
      setImgSrc(src);
      return;
    }

    const controller = new AbortController();

    const fetchImage = async () => {
      try {
        const token = localStorage.getItem('autonome_access_token');
        if (!token) {
          setErrorMsg('未授权 (本地无访问令牌)');
          return;
        }

        // ✨ 核心修复：强制拼接后端的 8000 端口地址，防止发给 3001
        let fetchUrl = src;
        if (src.startsWith('/api/')) {
          const apiBase = BASE_URL.replace(/\/$/, '');
          fetchUrl = `${apiBase}${src}`;
        }

        const response = await fetch(fetchUrl, {
          headers: {
            'Authorization': `Bearer ${token}`
          },
          signal: controller.signal
        });

        if (!response.ok) {
          // 🔍 精准定位报错原因，彻底粉碎 AI 幻觉障眼法
          if (response.status === 404) {
            setErrorMsg('文件不存在 (AI 代码未实际生成此图片)');
          } else if (response.status === 401) {
            setErrorMsg('访问被拒绝 (Token 失效或越权访问)');
          } else {
            setErrorMsg(`加载失败 (HTTP ${response.status})`);
          }
          return;
        }

        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        setImgSrc(objectUrl);

      } catch (err: any) {
        if (err.name !== 'AbortError') {
          console.error('Failed to load secure image:', err);
          setErrorMsg('网络拦截或跨域错误');
        }
      }
    };

    fetchImage();

    return () => {
      controller.abort();
    };
  }, [src]);

  // 如果出错，优雅地展示具体的错误原因
  if (errorMsg) {
    return (
      <div className="flex flex-col items-center justify-center h-32 w-full bg-gray-100 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700/50 rounded-lg text-gray-500 dark:text-neutral-400 text-sm my-4 gap-2">
        <span className="font-medium text-gray-700 dark:text-neutral-300">🖼️ 图片加载中断</span>
        <span className="text-xs text-red-500 dark:text-red-400">{errorMsg}</span>
        <code className="text-[10px] text-gray-400 dark:text-neutral-600 px-4 text-center break-all">{src}</code>
      </div>
    );
  }

  // 加载中骨架屏
  if (!imgSrc) {
    return (
      <div className="flex items-center justify-center h-48 w-full bg-gray-100 dark:bg-neutral-800/50 rounded-lg animate-pulse text-gray-400 dark:text-neutral-500 text-xs border border-gray-200 dark:border-neutral-700/50 my-4">
        正在安全解密并加载图表...
      </div>
    );
  }

  // 成功渲染
  return (
    // ✨ 拿掉 {...props}，防止 React 将未知属性渲染成奇怪的 DOM 节点或文字
    <img
      src={imgSrc}
      alt={alt || '数据可视化'}
      className="max-w-full h-auto rounded-lg shadow-lg border border-gray-200 dark:border-neutral-700 my-4 bg-white"
    />
  );
};

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

export function MarkdownBlock({ content }: { content: string }) {
  const theme = useUIStore((state) => state.theme);
  const isDark = theme !== 'light';

  // ✨ 聊天区文件预览状态
  const [previewData, setPreviewData] = useState<{url: string, filename: string} | null>(null);
  const [previewType, setPreviewType] = useState<'image' | 'text' | 'pdf' | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  // ✨ 基于流的安全下载
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

  // ✨ 基于流的内存级零信任预览
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

      if (isImage) {
        setPreviewContent(URL.createObjectURL(await res.blob())); setPreviewType('image');
      } else if (isPdf) {
        setPreviewContent(URL.createObjectURL(await res.blob())); setPreviewType('pdf');
      } else {
        const text = await res.text();
        const MAX_LENGTH = 100000;
        setPreviewContent(text.length > MAX_LENGTH ? text.substring(0, MAX_LENGTH) + '\n\n... [⚠️ 数据表过大，内存预览已截断，请下载查看完整全貌]' : text);
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

  // 🎨 资产卡片组件
  const FileAssetCard = ({ url, filename }: { url: string; filename: string }) => {
    return (
      <div className="flex items-center justify-between p-3 my-1.5 bg-white dark:bg-[#1e1e20] border border-gray-200 dark:border-[#2d2d30] rounded-xl shadow-sm hover:shadow-md dark:shadow-none transition-all group w-full max-w-sm">
        <div
          className="flex items-center gap-3 overflow-hidden flex-1 cursor-pointer"
          onClick={() => handlePreviewAsset(url, filename)}
        >
          <div className="p-2 bg-blue-50 dark:bg-blue-500/10 rounded-lg shrink-0">
            {getFileIcon(filename)}
          </div>
          <div className="truncate pr-2">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-200 truncate">{filename}</p>
            <p className="text-[10px] text-gray-500 dark:text-gray-500 font-mono mt-0.5">点击安全预览</p>
          </div>
        </div>

        {/* 悬浮操作栏 */}
        <div className="flex items-center gap-1.5 shrink-0 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
          <button onClick={(e) => { e.stopPropagation(); handlePreviewAsset(url, filename); }} className="p-1.5 text-gray-500 hover:text-emerald-600 dark:hover:text-emerald-400 bg-gray-50 hover:bg-emerald-50 dark:bg-[#2d2d30] dark:hover:bg-emerald-500/10 rounded-md transition-colors" title="安全预览">
            <Eye size={14} />
          </button>
          <button onClick={(e) => { e.stopPropagation(); handleDownloadAsset(url, filename); }} className="p-1.5 text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 bg-gray-50 hover:bg-blue-50 dark:bg-[#2d2d30] dark:hover:bg-blue-500/10 rounded-md transition-colors" title="保存到本地">
            <Download size={14} />
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className={`prose prose-sm max-w-none prose-pre:p-0 prose-pre:bg-transparent ${isDark ? 'prose-invert' : ''}`}>
      <ReactMarkdown
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const [copied, setCopied] = useState(false);

            const handleCopy = async () => {
              const codeString = String(children).replace(/\n$/, '');
              await copyToClipboard(codeString);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            };

            if (!match) {
              return (
                <code className="bg-gray-200 dark:bg-neutral-800 text-blue-600 dark:text-blue-400 px-1.5 py-0.5 rounded text-[0.85em] font-mono">
                  {children}
                </code>
              );
            }

            return (
              <div className="relative group my-4">
                <button
                  onClick={handleCopy}
                  className="absolute right-3 top-3 p-2 rounded-lg bg-gray-100 dark:bg-neutral-800/80 border border-gray-200 dark:border-neutral-700 text-gray-600 dark:text-neutral-400 opacity-0 group-hover:opacity-100 transition-all z-20 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-neutral-700 shadow-lg"
                  title="复制代码"
                >
                  {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                </button>
                <SyntaxHighlighter
                  style={isDark ? vscDarkPlus : vs}
                  language={match[1]}
                  PreTag="div"
                  customStyle={{
                    margin: 0,
                    padding: '1.25rem',
                    borderRadius: '0.75rem',
                    fontSize: '0.875rem',
                    backgroundColor: isDark ? '#1e1e1e' : '#f6f8fa',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                    overflowWrap: 'anywhere'
                  }}
                  codeTagProps={{
                    style: { 
                      whiteSpace: 'pre-wrap', 
                      wordBreak: 'break-all' 
                    }
                  }}
                >
                  {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
              </div>
            );
          },
          // ✨ 拦截：所有的图片，不再直接满屏显示，而是转换为优雅的卡片
          img: (props: any) => {
            const src = typeof props.src === 'string' ? props.src : undefined;
            let alt = '数据可视化图表';
            if (typeof props.alt === 'string' && props.alt.trim() !== '') {
                alt = props.alt;
            }
            if (!src) return null;

            const filename = alt || src.split('/').pop() || 'image.png';
            return <FileAssetCard url={src} filename={filename} />;
          },

          // ✨ 拦截：只要是包含系统内部 API 的文件链接，强制转为卡片
          a: ({ href, children, ...props }) => {
            if (!href) return <a {...props} className="text-blue-500 hover:underline">{children}</a>;

            if (href.includes('/api/projects/') && href.includes('/files/')) {
              const filename = typeof children === 'string' ? children : href.split('/').pop() || 'output_file';
              return <FileAssetCard url={href} filename={filename} />;
            }
            // 普通的外部网页链接正常渲染
            return <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline break-all">{children}</a>;
          },
          // ✨ 防止 p 标签包裹 div/span 导致 hydration 错误
          p: ({ children }) => <>{children}</>,
        }}
      >
        {content}
      </ReactMarkdown>

      {/* ✨ 绝美沉浸式文件预览弹窗 */}
      {previewData && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 md:p-12 animate-in fade-in duration-200">
          <div className="bg-white dark:bg-[#1a1a1c] border border-gray-200 dark:border-[#2d2d30] rounded-2xl w-full max-w-5xl h-full flex flex-col shadow-2xl overflow-hidden relative animate-in zoom-in-95 duration-200">

            {/* 弹窗 Header */}
            <div className="h-14 shrink-0 border-b border-gray-200 dark:border-[#2d2d30] px-6 flex items-center justify-between bg-gray-50 dark:bg-[#1e1e20]">
              <div className="flex items-center gap-3">
                <Eye size={18} className="text-emerald-500 dark:text-emerald-400"/>
                <h3 className="text-gray-900 dark:text-white font-medium text-sm tracking-wide truncate max-w-lg">{previewData.filename}</h3>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => handleDownloadAsset(previewData.url, previewData.filename)} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-600 dark:bg-blue-500/10 dark:hover:bg-blue-500/20 dark:text-blue-400 text-xs font-medium rounded-lg transition-colors border border-blue-200 dark:border-blue-500/20">
                  <Download size={14} /> 保存到本地
                </button>
                <div className="w-px h-4 bg-gray-300 dark:bg-neutral-800 mx-1"></div>
                <button onClick={closePreview} className="p-1.5 text-gray-500 hover:text-gray-900 hover:bg-gray-200 dark:text-neutral-400 dark:hover:text-white dark:hover:bg-neutral-800 rounded-lg transition-colors">
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* 弹窗内容渲染区 */}
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
