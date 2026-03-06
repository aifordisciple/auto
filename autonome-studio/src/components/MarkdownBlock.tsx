"use client";

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';

interface MarkdownBlockProps {
  content: string;
}

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
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
