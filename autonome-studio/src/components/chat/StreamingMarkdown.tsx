/**
 * StreamingMarkdown - 流式 Markdown 增量渲染组件
 *
 * 核心原理：
 * 1. 使用 ReactMarkdown 渲染 Markdown 内容
 * 2. 流式时持续解析完整 Markdown，但只更新变化的 DOM 节点
 * 3. 避免全局 innerHTML 替换，消除闪烁和跳动
 *
 * Vercel AI SDK 重构后：
 * - useChat 自动追加内容到 msg.content，无需手动管理流式内容
 * - isStreaming 简化为布尔标志，不再需要动画光标
 * - 保留思考框、未闭合结构处理、交互式图表占位符
 * - 保留性能优化（纯文本路径无代码块时）
 */
import { useRef, useEffect, useMemo, memo, useCallback, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks'; // 兼容大模型（如 Kimi）的单换行输出习惯
import remarkMath from 'remark-math'; // ✨ 数学公式解析：将 $...$ / $$...$$ 转为 AST 节点
import rehypeKatex from 'rehype-katex'; // ✨ KaTeX 渲染：将数学 AST 节点转为精美排版 HTML
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
  // ✨ 如果内容为空，可能是刚建立连接尚未来得及发送任何内容，
  //   这种情况应该显示"思考中..."状态
  if (!content) return { cleanContent: '', isThinking: true };

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
 * ✨ 新增：对于未闭合的 $ / $$ 数学公式，自动补全闭合标记，防止 KaTeX 渲染闪烁
 */
function preprocessStreamingMarkdown(content: string): { processedContent: string; isCurrentlyThinking: boolean } {
  // ✨ 空内容时处于思考等待状态，直到收到第一个有效字符
  if (!content) return { processedContent: '', isCurrentlyThinking: true };

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

  // ✨ 处理未闭合的数学公式（防止 KaTeX 渲染闪烁）
  // 先处理独立公式块 $$，再处理行内公式 $
  // 注意：必须在代码块闭合之后处理，避免代码块内的 $ 被误判
  if (openCodeBlocks === 0) {
    processed = closeUnclosedMath(processed);
  }

  return { processedContent: processed, isCurrentlyThinking: isThinking };
}

/**
 * ✨ 闭合未闭合的数学公式标记
 *
 * 流式传输时，AI 可能正在输出 $alpha = 0.05$ 但 $ 还未闭合，
 * 此时 remark-math 会将未闭合的 $ 当作普通文本，导致闪烁。
 * 解决方案：检测未闭合的 $ / $$，临时追加闭合标记。
 *
 * 处理顺序：先处理 $$（独立公式块），再处理 $（行内公式）
 * 避免将 $$ 误判为两个 $
 */
function closeUnclosedMath(text: string): string {
  // 跳过代码块内的内容（代码块内的 $ 不是数学公式）
  // 简单策略：按 ``` 分割，只处理非代码块部分
  const segments = text.split(/(```[\s\S]*?```)/g);
  const result = segments.map((segment, index) => {
    // 奇数索引是代码块内容，跳过
    if (index % 2 === 1) return segment;

    // 处理非代码块部分
    let processed = segment;

    // 1. 处理未闭合的 $$（独立公式块）
    // 统计 $$ 的数量（排除转义的 \$\$）
    const displayMathMatches = processed.match(/(?<!\\)\$\$/g);
    const displayMathCount = displayMathMatches ? displayMathMatches.length : 0;
    if (displayMathCount % 2 !== 0) {
      // 奇数个 $$，说明有未闭合的独立公式块
      processed += '$$';
    }

    // 2. 处理未闭合的 $（行内公式）
    // 移除已匹配的 $$ 后，统计剩余的 $ 数量
    // 先将已闭合的 $$...$$ 替换为占位符，避免干扰 $ 的计数
    const withoutDisplayMath = processed.replace(/(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$/g, '');
    const inlineMathMatches = withoutDisplayMath.match(/(?<!\\)\$/g);
    const inlineMathCount = inlineMathMatches ? inlineMathMatches.length : 0;
    if (inlineMathCount % 2 !== 0) {
      // 奇数个 $，说明有未闭合的行内公式
      processed += '$';
    }

    return processed;
  });

  return result.join('');
}

// ==========================================
// 代码块组件（带复制按钮）
// ✨ 流式期间使用纯 <pre> 渲染（避免 Prism 高亮导致浏览器卡死）
// ✨ 流结束后使用 Prism 语法高亮
// ==========================================

interface CodeBlockProps {
  language: string;
  children: string;
  isDark: boolean;
  /** ✨ 是否正在流式输出（流式时跳过 Prism 高亮，避免卡顿） */
  isStreaming?: boolean;
}

const CodeBlock = memo(({ language, children, isDark, isStreaming }: CodeBlockProps) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await copyToClipboard(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // ✨ 流式期间：使用纯 <pre> 渲染，避免 Prism 高亮导致浏览器卡死
  // Prism 对长代码块的高亮是 CPU 密集型操作，每个 token 到达时重新高亮会冻结主线程
  if (isStreaming) {
    return (
      <div className="relative group my-4">
        <div className="flex items-center justify-between px-4 py-2 bg-[#1e1e1e] dark:bg-[#1e1e1e] rounded-t-xl border-b border-neutral-700/50">
          <span className="text-xs text-neutral-400 font-mono">{language}</span>
          <button
            onClick={handleCopy}
            className="p-1.5 rounded-md text-neutral-400 hover:text-white hover:bg-neutral-700/50 transition-all"
            title="复制代码"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
        <pre className="!m-0 !p-4 !rounded-b-xl !bg-[#1e1e1e] !text-[0.875rem] overflow-x-auto custom-scrollbar">
          <code className={`language-${language} font-mono text-neutral-200`}>
            {children}
          </code>
        </pre>
      </div>
    );
  }

  // ✨ 流结束后：使用 Prism 语法高亮（一次性渲染，不会卡顿）
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
  /** ✨ 思考过程内容（从 thinking SSE 事件累积） */
  thinkingContent?: string;
  /** ✨ 是否正在思考 */
  isThinking?: boolean;
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
export const StreamingMarkdown = memo(({ content, isStreaming = false, thinkingContent = '', isThinking: isThinkingProp = false }: StreamingMarkdownProps) => {
  const theme = useUIStore((state) => state.theme);
  const isDark = theme !== 'light';

  // ✨ 思考框折叠状态
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(true);

  // ✨ 当思考开始时自动展开，思考结束后延迟折叠
  useEffect(() => {
    if (isThinkingProp) {
      setIsThinkingExpanded(true);
    } else if (thinkingContent && !isThinkingProp) {
      const timer = setTimeout(() => setIsThinkingExpanded(false), 800);
      return () => clearTimeout(timer);
    }
  }, [isThinkingProp, thinkingContent]);

  // ✨ 截断思考内容预览（折叠时显示前100字符）
  const thinkingPreview = useMemo(() => {
    if (!thinkingContent) return '';
    return thinkingContent.length > 100
      ? thinkingContent.slice(0, 100) + '...'
      : thinkingContent;
  }, [thinkingContent]);

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
        <CodeBlock language={language} isDark={isDark} isStreaming={isStreaming}>
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
  }), [isDark, isStreaming]);

  // ✨ 关键修复：允许空内容渲染，只要是流式状态或者正在思考
  if (!content && !isStreaming && !isCurrentlyThinking && !isThinkingProp) return null;

  // 流式消息使用淡入效果类
  const containerClass = isStreaming
    ? "chat-message-content streaming-message-content"
    : "chat-message-content";

  // ✨ 思考框显示条件：isThinkingProp（store 状态）或 isCurrentlyThinking（内容检测）或有 thinkingContent
  const showThinkingBox = isThinkingProp || isCurrentlyThinking || !!thinkingContent;

  return (
    <div className={containerClass}>
      {/* ✨ 可折叠的思考过程展示 */}
      {showThinkingBox && (
        <div className="mb-4">
          <button
            onClick={() => setIsThinkingExpanded(!isThinkingExpanded)}
            className="flex items-center gap-2 text-violet-500 dark:text-violet-400 text-sm bg-violet-50 dark:bg-violet-500/10 px-3 py-2 rounded-lg border border-violet-100 dark:border-violet-500/20 w-full hover:bg-violet-100 dark:hover:bg-violet-500/15 transition-colors"
          >
            {isThinkingProp || isCurrentlyThinking ? (
              <Loader2 className="w-4 h-4 animate-spin shrink-0" />
            ) : (
              <span className="text-violet-500 shrink-0">✦</span>
            )}
            <span className="font-medium tracking-wide">
              {isThinkingProp || isCurrentlyThinking ? '深度思考中...' : `思考过程 (${thinkingContent.length}字)`}
            </span>
            <span className="ml-auto text-violet-400/60 text-xs">
              {isThinkingExpanded ? '收起' : '展开'}
            </span>
          </button>
          {isThinkingExpanded && thinkingContent && (
            <div className="mt-2 p-3 bg-violet-50/50 dark:bg-violet-500/5 border border-violet-100/50 dark:border-violet-500/10 rounded-lg text-xs text-violet-700 dark:text-violet-300 max-h-60 overflow-y-auto custom-scrollbar whitespace-pre-wrap break-words leading-relaxed">
              {thinkingContent}
            </div>
          )}
        </div>
      )}

      {/* 渲染正常的 Markdown 内容 */}
      {processedContent && (
        isStreaming ? (
          // 流式时使用轻量级渲染，避免 ReactMarkdown 每次重解析导致卡顿
          // ✨ 检测是否包含代码块或数学公式，如果有则使用 ReactMarkdown（需要语法高亮或 KaTeX 渲染）
          // 否则直接渲染纯文本（快得多）
          (processedContent.includes('```') || processedContent.includes('$')) ? (
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={components}
            >
              {processedContent}
            </ReactMarkdown>
          ) : (
            <div className="whitespace-pre-wrap break-words text-[0.9375rem] leading-relaxed">
              {processedContent}
            </div>
          )
        ) : (
          // 非流式时使用完整 Markdown 渲染
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]}
            rehypePlugins={[rehypeKatex]}
            components={components}
          >
            {processedContent}
          </ReactMarkdown>
        )
      )}
    </div>
  );
});

StreamingMarkdown.displayName = 'StreamingMarkdown';

export default StreamingMarkdown;