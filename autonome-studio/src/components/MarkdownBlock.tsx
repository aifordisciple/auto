"use client";

import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';
import { BASE_URL } from '@/lib/api';

interface MarkdownBlockProps {
  content: string;
}

// ✨ 商业级安全图片组件：精准报错与内存回收
const SecureImage = ({ src, alt, ...props }: any) => {
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
      <div className="flex flex-col items-center justify-center h-32 w-full bg-neutral-900 border border-neutral-700/50 rounded-lg text-neutral-400 text-sm my-4 gap-2">
        <span className="font-medium text-neutral-300">🖼️ 图片加载中断</span>
        <span className="text-xs text-red-400">{errorMsg}</span>
        <code className="text-[10px] text-neutral-600 px-4 text-center break-all">{src}</code>
      </div>
    );
  }

  // 加载中骨架屏
  if (!imgSrc) {
    return (
      <div className="flex items-center justify-center h-48 w-full bg-neutral-800/50 rounded-lg animate-pulse text-neutral-500 text-xs border border-neutral-700/50 my-4">
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
      className="max-w-full h-auto rounded-lg shadow-lg border border-neutral-700 my-4 bg-white"
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
  return (
    <div className="prose prose-invert prose-sm max-w-none prose-pre:p-0 prose-pre:bg-transparent">
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
                <code className="bg-neutral-800 text-blue-400 px-1.5 py-0.5 rounded text-[0.85em] font-mono">
                  {children}
                </code>
              );
            }

            return (
              <div className="relative group my-4">
                <button
                  onClick={handleCopy}
                  className="absolute right-3 top-3 p-2 rounded-lg bg-neutral-800/80 border border-neutral-700 text-neutral-400 opacity-0 group-hover:opacity-100 transition-all z-20 hover:text-white hover:bg-neutral-700 shadow-lg"
                  title="复制代码"
                >
                  {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                </button>
                <SyntaxHighlighter
                  style={vscDarkPlus}
                  language={match[1]}
                  PreTag="div"
                  customStyle={{
                    margin: 0,
                    padding: '1.25rem',
                    borderRadius: '0.75rem',
                    fontSize: '0.875rem',
                    backgroundColor: '#1e1e1e',
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
          // ✨ 终极暴力净化：只提取字符串类型的 src 和 alt，其他一概不理
          img: (props: any) => {
            // 1. 安全地提取 src
            const src = typeof props.src === 'string' ? props.src : undefined;

            // 2. 安全地提取 alt (如果没有，给个默认值)
            let alt = '数据可视化图表';
            if (typeof props.alt === 'string' && props.alt.trim() !== '') {
                alt = props.alt;
            }

            // 3. 如果连 src 都没有，直接返回 null，什么都不渲染
            if (!src) return null;

            // 4. 绝对干净地调用 SecureImage，不传递任何多余的 props
            return <SecureImage src={src} alt={alt} />;
          },
          // ✨ 防止 p 标签包裹 div/span 导致 hydration 错误
          p: ({ children }) => <>{children}</>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
