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

// ✨ 商业级安全图片组件：带 Token 请求并转换成 Blob URL
const SecureImage = ({ src, alt, ...props }: { src?: string; alt?: string }) => {
  const [imgSrc, setImgSrc] = useState<string>('');
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    if (!src) return;

    // 如果不是后端的 API 图片（比如外部网络图片），直接显示
    if (!src.includes('/api/projects/')) {
      setImgSrc(src);
      return;
    }

    const fetchImage = async () => {
      try {
        const token = localStorage.getItem('autonome_access_token');
        const response = await fetch(src, {
          headers: {
            'Authorization': `Bearer ${token}` // 🛡️ 核心：带上用户的钥匙
          }
        });

        if (!response.ok) throw new Error('Unauthorized or not found');

        // 将返回的文件流转换为浏览器本地的对象 URL
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        setImgSrc(objectUrl);
      } catch (err) {
        console.error('Failed to load secure image:', err);
        setHasError(true);
      }
    };

    fetchImage();
  }, [src]);

  if (hasError) {
    return (
      <div className="flex items-center justify-center h-32 w-full bg-red-950/20 border border-red-900/50 rounded-lg text-red-500 text-xs">
        图片加载失败 (未授权或文件不存在)
      </div>
    );
  }

  if (!imgSrc) {
    return (
      <div className="flex items-center justify-center h-48 w-full bg-neutral-800/50 rounded-lg animate-pulse text-neutral-500 text-xs border border-neutral-700/50">
        正在安全解密并加载图表...
      </div>
    );
  }

  return (
    <img
      src={imgSrc}
      alt={alt || '数据可视化'}
      className="max-w-full h-auto rounded-lg shadow-lg border border-neutral-700 my-4"
      {...props}
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
                <code className="bg-neutral-800 text-blue-400 px-1.5 py-0.5 rounded text-[0.85em] font-mono" {...props}>
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
          // ✨ 用安全组件劫持所有 Markdown 里的图片
          img: ({ node, ...props }) => {
            return <SecureImage src={props.src} alt={props.alt} />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
