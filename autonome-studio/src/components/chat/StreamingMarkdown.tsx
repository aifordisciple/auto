/**
 * StreamingMarkdown - 流式 Markdown 增量渲染组件
 *
 * 核心原理：
 * 1. 使用 StreamMarkdownProcessor 进行增量 DOM 更新
 * 2. 流式时持续解析完整 Markdown，但只更新变化的 DOM 节点
 * 3. 避免全局 innerHTML 替换，消除闪烁和跳动
 */
import React, { useRef, useEffect, useMemo, memo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks'; // 兼容大模型（如 Kimi）的单换行输出习惯
// ✨ 移除 rehypeRaw：允许原始 HTML 标签会导致 <think> 等标签被渲染，引发浏览器错误
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus, vs } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check, Loader2 } from 'lucide-react';
import { useUIStore } from '@/store/useUIStore';

// ==========================================
// 辅助函数
// ==========================================

const copyToClipboard = async (text: string) => {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
  } else {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
  }
};

/**
 * ✨ 解析并过滤思考过程（支持未闭合标签）
 * 核心问题：流式传输时 <think> 标签可能未闭合，导致内容被渲染到页面上闪烁
 * 解决方案：检测未闭合的 <think> 标签，截断其后续内容，并标记为"思考中"状态
 */
function parseAndFilterThinking(content: string): { cleanContent: string; isThinking: boolean } {
  if (!content) return { cleanContent: '', isThinking: false };

  let cleanContent = content;
  let isThinking = false;

  // 1. 移除所有已闭合的 <think>...</think> 块
  cleanContent = cleanContent.replace(/<think>[\s\S]*?<\/think>/gi, '');

  // 2. 检测是否存在未闭合的 <think> 标签
  const openThinkIndex = cleanContent.toLowerCase().indexOf('<think>');
  if (openThinkIndex !== -1) {
    isThinking = true;
    // 截断未闭合的 think 及后面的所有内容，防止闪烁
    cleanContent = cleanContent.substring(0, openThinkIndex);
  }

  return { cleanContent, isThinking };
}

/**
 * 预处理流式 Markdown - 处理未闭合的结构
 * 对于未闭合的代码块，自动补全闭合标记
 */
function preprocessStreamingMarkdown(content: string): { processed: string; isThinking: boolean } {
  if (!content) return { processed: '', isThinking: false };

  // ✨ 首先处理 think 标签，检测是否处于思考中状态
  const { cleanContent, isThinking } = parseAndFilterThinking(content);

  // 计算代码块数量
  const codeBlockMatches = cleanContent.match(/```[\w]*/g) || [];
  const openCodeBlocks = codeBlockMatches.length % 2;

  let processed = cleanContent;

  // 如果有未闭合的代码块，添加临时闭合
  if (openCodeBlocks > 0) {
    processed += '\n```';
  }

  return { processed, isThinking };
}

// ==========================================
// 代码块组件（带复制按钮）
// ==========================================

interface CodeBlockProps {
  language: string;
  children: string;
  isDark: boolean;
}

const CodeBlock = memo(({ language, children, isDark }: CodeBlockProps) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    await copyToClipboard(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group my-4">
      <button
        onClick={handleCopy}
        className="absolute right-3 top-3 p-2 rounded-lg bg-gray-100 dark:bg-neutral-800/80 border border-gray-200 dark:border-neutral-700 text-gray-600 dark:text-neutral-400 opacity-0 group-hover:opacity-100 transition-all z-20 hover:text-gray-900 dark:hover:text-white"
        title="复制代码"
      >
        {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
      </button>
      <SyntaxHighlighter
        style={isDark ? vscDarkPlus : vs}
        language={language}
        PreTag="div"
        customStyle={{
          margin: 0,
          padding: '1.25rem',
          borderRadius: '0.75rem',
          fontSize: '0.875rem',
          backgroundColor: isDark ? '#1e1e1e' : '#f6f8fa',
        }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
});

CodeBlock.displayName = 'CodeBlock';

// ==========================================
// 流式 Markdown 渲染组件
// ==========================================

interface StreamingMarkdownProps {
  content: string;
  isStreaming?: boolean;
}

/**
 * 流式 Markdown 渲染器
 *
 * 流式时：
 * - 预处理未闭合的 Markdown 结构
 * - 正常渲染，React 的虚拟 DOM 会处理增量更新
 *
 * 关键优化点：
 * - React 本身有虚拟 DOM Diff 机制
 * - 我们只需要确保每次传递的内容是完整的、处理过的 Markdown
 */
export const StreamingMarkdown = memo(({ content, isStreaming = false }: StreamingMarkdownProps) => {
  const theme = useUIStore((state) => state.theme);
  const isDark = theme !== 'light';

  // 预处理内容
  const { processedContent, isCurrentlyThinking } = useMemo(() => {
    if (!content) return { processedContent: '', isCurrentlyThinking: false };
    // 流式时处理未闭合的结构
    if (isStreaming) {
      return preprocessStreamingMarkdown(content);
    }
    // 非流式也做一次完整的 think 过滤
    const { cleanContent, isThinking } = parseAndFilterThinking(content);
    return { processedContent: cleanContent, isCurrentlyThinking: isThinking };
  }, [content, isStreaming]);

  // Markdown 渲染组件配置
  const components = useMemo(() => ({
    code({ className, children, ...props }: any) {
      const match = /language-(\w+)/.exec(className || '');
      const language = match ? match[1] : '';

      // 内联代码
      if (!match) {
        return (
          <code className="bg-gray-200 dark:bg-neutral-800 text-blue-600 dark:text-blue-400 px-1.5 py-0.5 rounded text-[0.875em] font-mono">
            {children}
          </code>
        );
      }

      // ✨ 特殊处理：json_interactive_plot 及其变体
      // 这些代码块应该被 InteractivePlotCard 组件处理
      const interactivePlotLanguages = [
        'json_interactive_plot',
        'on_interactive_plot',
        'interactive_plot',
      ];

      if (interactivePlotLanguages.includes(language) ||
          language.includes('interactive_plot')) {
        // 流式渲染阶段显示加载状态
        return (
          <div className="relative group my-4">
            <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl p-4">
              <div className="flex items-center gap-2 text-violet-400 text-xs mb-2">
                <span className="animate-pulse">🎨</span>
                <span>正在生成交互式图表配置...</span>
              </div>
              <SyntaxHighlighter
                style={isDark ? vscDarkPlus : vs}
                language="json"
                PreTag="div"
                customStyle={{
                  margin: 0,
                  padding: '1rem',
                  borderRadius: '0.5rem',
                  fontSize: '0.75rem',
                  backgroundColor: isDark ? '#1e1e1e' : '#f6f8fa',
                }}
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            </div>
          </div>
        );
      }

      // 代码块
      return (
        <CodeBlock language={language} isDark={isDark}>
          {String(children).replace(/\n$/, '')}
        </CodeBlock>
      );
    },

    // 表格样式
    table({ children }: any) {
      return (
        <div className="chat-table-wrapper">
          <table className="w-full border-collapse">{children}</table>
        </div>
      );
    },

    // 链接样式
    a({ href, children }: any) {
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline break-all">
          {children}
        </a>
      );
    },

    // ✨ 列表样式 - 修复列表渲染问题
    ul({ children }: any) {
      return (
        <ul className="list-disc list-outside ml-6 my-2 space-y-1">
          {children}
        </ul>
      );
    },

    ol({ children }: any) {
      return (
        <ol className="list-decimal list-outside ml-6 my-2 space-y-1">
          {children}
        </ol>
      );
    },

    li({ children }: any) {
      return (
        <li className="leading-relaxed">
          {children}
        </li>
      );
    },

    // ✨ 段落样式 - 确保正确换行
    p({ children }: any) {
      return (
        <p className="mb-3 last:mb-0">
          {children}
        </p>
      );
    },

    // ✨ 额外的 HTML 标签处理 - 过滤任何残留的 think 标签
    // 这是一个额外的安全层，防止 think 标签被渲染到页面上
    // 包括未闭合的情况（当 think 内容被截断后，剩余部分可能包含 < 符号）
    html({ children }: any) {
      // 如果是字符串类型，直接过滤掉 think 标签内容
      if (typeof children === 'string') {
        // 过滤已闭合的 think 标签
        const filtered = children.replace(/<think>[\s\S]*?<\/think>/gi, '');
        // 额外安全层：过滤可能残留的未闭合 think 标签片段
        const finalFiltered = filtered.replace(/<think>[\s\S]*$/gi, '');
        if (finalFiltered !== children) {
          return <>{finalFiltered}</>;
        }
        // 没有 think 标签但包含 HTML，直接渲染为普通文本（避免 dangerouslySetInnerHTML）
        return <>{children}</>;
      }
      return <>{children}</>;
    },
  }), [isDark]);

  if (!content) return null;

  // 流式消息使用淡入效果类
  const containerClass = isStreaming
    ? "chat-message-content streaming-message-content"
    : "chat-message-content";

  return (
    <div className={containerClass}>
      {/* ✨ 优雅的深度思考状态展示 (仅在正在 thinking 时出现) */}
      {isCurrentlyThinking && (
        <div className="flex items-center gap-2 text-violet-500 dark:text-violet-400 text-sm mb-4 bg-violet-50 dark:bg-violet-500/10 px-3 py-2 rounded-lg border border-violet-100 dark:border-violet-500/20 w-fit">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="font-medium tracking-wide">深度思考中...</span>
        </div>
      )}

      {/* 渲染正常的 Markdown 内容 */}
      {processedContent && (
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkBreaks]}
          components={components}
        >
          {processedContent}
        </ReactMarkdown>
      )}

      {/* ✨ 流式时显示光标，且正在思考时不显示 */}
      {isStreaming && !isCurrentlyThinking && (
        <span className="streaming-cursor">
          <span className="cursor-block" />
        </span>
      )}
    </div>
  );
});

StreamingMarkdown.displayName = 'StreamingMarkdown';

export default StreamingMarkdown;