/**
 * 执行结果卡片组件
 *
 * 显示分析任务生成的资产文件列表
 * 支持文件预览和下载
 */
"use client";

import React, { useState, useMemo } from "react";
import {
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  FileText,
  Eye,
  Download,
  Table2,
  Image as ImageIcon,
  FileImage,
  FileSpreadsheet,
  Sparkles,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { MarkdownBlock } from "@/components/MarkdownBlock";
import { BASE_URL } from "@/lib/api";

// ==========================================
// 文件图标获取函数
// ==========================================
export const getFileIcon = (filename: string) => {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tsv') || lower.endsWith('.csv') || lower.endsWith('.txt') || lower.endsWith('.log')) {
    return <Table2 size={15} className="text-blue-500 dark:text-blue-400 shrink-0" />;
  }
  if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.pdf') || lower.endsWith('.svg')) {
    return <ImageIcon size={15} className="text-pink-500 dark:text-pink-400 shrink-0" />;
  }
  return <FileText size={15} className="text-gray-500 dark:text-neutral-400 shrink-0" />;
};

// ==========================================
// 资产树节点组件
// ==========================================
interface AssetTreeNodeProps {
  node: {
    name: string;
    type: 'file' | 'folder';
    url?: string | null;
    children: Record<string, any>;
  };
  level: number;
  onPreview: (url: string, name: string) => void;
  onDownload: (url: string, name: string) => void;
}

const AssetTreeNode: React.FC<AssetTreeNodeProps> = ({
  node,
  level,
  onPreview,
  onDownload,
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const isFolder = node.type === 'folder';

  return (
    <div className="flex flex-col">
      <div
        className={`flex items-center gap-2 py-1.5 px-2 hover:bg-gray-100 dark:hover:bg-[#2d2d30]/80 rounded-md cursor-pointer group transition-colors`}
        style={level > 0 ? { marginLeft: `${level * 16}px`, borderLeft: '1px solid', borderLeftColor: level > 1 ? 'transparent' : undefined, paddingLeft: '12px' } : {}}
        onClick={() => isFolder ? setIsExpanded(!isExpanded) : onPreview(node.url || '', node.name)}
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
             <button onClick={(e) => { e.stopPropagation(); onPreview(node.url || '', node.name); }} className="p-1 text-gray-400 hover:text-emerald-500 bg-white dark:bg-[#1e1e20] shadow-sm rounded border border-gray-200 dark:border-gray-700" title="安全预览"><Eye size={13} /></button>
             <button onClick={(e) => { e.stopPropagation(); onDownload(node.url || '', node.name); }} className="p-1 text-gray-400 hover:text-blue-500 bg-white dark:bg-[#1e1e20] shadow-sm rounded border border-gray-200 dark:border-gray-700" title="下载"><Download size={13} /></button>
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

// ==========================================
// 执行结果卡片组件
// ==========================================
interface ExecutionResultCardProps {
  /** 消息内容 */
  content: string;
  /** 深度解读回调 */
  onInterpret: (files: string[], code: string, userMessage: string) => void;
}

/**
 * ExecutionResultCard - 生成资产树状卡片组件
 * 解析消息内容中的文件路径，显示为树状资产列表
 */
export function ExecutionResultCard({ content, onInterpret }: ExecutionResultCardProps) {
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

// ==========================================
// 资产树卡片组件（升级版）
// ==========================================
interface AssetTreeCardProps {
  /** 文件链接列表 */
  links: { url: string; title: string }[];
  /** 预览回调 */
  onPreview: (url: string, name: string) => void;
  /** 下载回调 */
  onDownload: (url: string, name: string) => void;
  /** 深度解读回调（可选） */
  onInterpret?: () => void;
}

/**
 * AssetTreeCard - 升级版树状卡片，带有解读按钮
 */
export const AssetTreeCard: React.FC<AssetTreeCardProps> = ({
  links,
  onPreview,
  onDownload,
  onInterpret,
}) => {
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

export default ExecutionResultCard;