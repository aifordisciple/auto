"use client";

import { memo, useState } from "react";
import { motion } from "framer-motion";
import {
  CheckCircle,
  XCircle,
  Zap,
  FolderOpen,
  FileCode,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  FileText,
  FileImage,
  FileSpreadsheet,
  Download,
  Eye,
  Copy,
  Loader2,
  X,
} from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { BASE_URL } from "../../lib/api";

// ==========================================
// 类型定义
// ==========================================

export interface ExecutionResult {
  order: number;
  language: string;
  status: string;
  exit_code: number;
  retry_count: number;
  error?: string;
}

export interface GeneratedFile {
  path: string;
  name: string;
  size: number;
  extension: string;
}

// V3 新增字段
export interface BattleReportDataV3 {
  success: boolean;
  execution_time: number;
  exit_code: number;
  user_intent: string;           // 用户意图描述
  path_mappings: Record<string, string>;
  generated_files: GeneratedFile[];
  stdout_preview?: string;        // 执行日志预览
  error_message?: string;         // 错误信息
  output_dir: string;
  retry_count: number;
}

export interface BattleReportData {
  task_out_dir?: string;  // 任务输出目录路径
  success_count: number;
  failed_count: number;
  total_retries: number;
  path_mappings: Record<string, string>;
  generated_files: GeneratedFile[];
  execution_summary: ExecutionResult[];
  // V3 扩展字段
  success?: boolean;
  execution_time?: number;
  user_intent?: string;
  stdout_preview?: string;
  error_message?: string;
  output_dir?: string;
  retry_count?: number;
}

interface BattleReportCardProps {
  data: BattleReportData;
  messageId?: string;
}

// ==========================================
// 辅助函数
// ==========================================

/**
 * 格式化文件大小
 */
const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

/**
 * 获取文件图标
 */
const getFileIcon = (ext: string) => {
  const imageExts = [".png", ".jpg", ".jpeg", ".pdf", ".svg", ".gif"];
  const dataExts = [".csv", ".tsv", ".xlsx", ".h5", ".h5ad"];
  const codeExts = [".py", ".r", ".R", ".sh", ".yaml", ".yml", ".toml"];
  const docExts = [".md", ".txt", ".json", ".log"];

  if (imageExts.includes(ext.toLowerCase())) {
    return <FileImage size={14} className="text-blue-400" />;
  }
  if (dataExts.includes(ext.toLowerCase())) {
    return <FileSpreadsheet size={14} className="text-emerald-400" />;
  }
  if (codeExts.includes(ext.toLowerCase())) {
    // Python: 蓝色, R: 紫色, Shell: 绿色, 其他: 橙色
    const lowerExt = ext.toLowerCase();
    if (lowerExt === ".py") {
      return <FileCode size={14} className="text-yellow-400" />;  // Python 黄色
    }
    if (lowerExt === ".r") {
      return <FileCode size={14} className="text-purple-400" />;  // R 紫色
    }
    if (lowerExt === ".sh") {
      return <FileCode size={14} className="text-green-400" />;  // Shell 绿色
    }
    return <FileCode size={14} className="text-orange-400" />;
  }
  if (docExts.includes(ext.toLowerCase())) {
    return <FileText size={14} className="text-cyan-400" />;
  }
  return <FileText size={14} className="text-neutral-400" />;
};

/**
 * 判断文件是否可预览
 * 支持：图片、PDF、文本文件、代码文件、Markdown
 */
const isPreviewable = (ext: string): boolean => {
  const previewableExts = [
    // 图片
    ".png", ".jpg", ".jpeg", ".svg", ".gif",
    // 文档
    ".pdf",
    // 文本/数据
    ".txt", ".csv", ".tsv", ".json", ".md",
    // 代码文件
    ".py", ".r", ".R", ".sh", ".yaml", ".yml", ".toml",
    // 日志
    ".log"
  ];
  return previewableExts.includes(ext.toLowerCase());
};

/**
 * 复制文本到剪贴板
 */
const copyToClipboard = async (text: string): Promise<void> => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    console.error("复制失败:", err);
  }
};

/**
 * 根据文件扩展名获取语法高亮语言
 */
const getLanguageFromExt = (ext: string): string => {
  const langMap: Record<string, string> = {
    // Python
    ".py": "python",
    // R
    ".r": "r",
    ".R": "r",
    // Shell
    ".sh": "bash",
    ".bash": "bash",
    // 配置文件
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    // 标记语言
    ".md": "markdown",
    ".markdown": "markdown",
    // Web
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".html": "html",
    ".css": "css",
    // 其他
    ".sql": "sql",
    ".xml": "xml",
    ".log": "text",
    ".txt": "text",
    ".csv": "csv",
    ".tsv": "csv",
  };
  return langMap[ext.toLowerCase()] || "text";
};

/**
 * 解析 json_battle_report 代码块
 *
 * @param content 消息内容
 * @returns BattleReportData 或 null
 */
export function parseBattleReport(content: string): BattleReportData | null {
  if (!content) return null;

  try {
    // 从 json_battle_report 代码块中提取
    const reportMatch = content.match(/```json_battle_report\s*\n([\s\S]*?)```/);
    if (reportMatch) {
      const data = JSON.parse(reportMatch[1]);
      // 验证必要字段
      if (
        typeof data.success_count === "number" &&
        typeof data.failed_count === "number" &&
        Array.isArray(data.execution_summary)
      ) {
        return data as BattleReportData;
      }
    }

    return null;
  } catch (e) {
    console.error("Failed to parse battle report:", e);
    return null;
  }
}

// ==========================================
// 战报卡片组件
// ==========================================

export const BattleReportCard = memo(function BattleReportCard({ data, messageId }: BattleReportCardProps) {
  // 展开/折叠状态
  const [isExpanded, setIsExpanded] = useState(true);
  const [showPathMappings, setShowPathMappings] = useState(true);
  const [showExecutionDetails, setShowExecutionDetails] = useState(true);
  const [showGeneratedFiles, setShowGeneratedFiles] = useState(true);
  const [showExecutionLog, setShowExecutionLog] = useState(false);  // V3: 执行日志折叠

  // 预览弹窗状态（参考 RightPanel.tsx 实现）
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<'image' | 'text' | 'pdf' | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  // 判断是否为 V3 格式（包含 success 字段）
  const isV3 = data.success !== undefined;

  // 统计信息（兼容 V1 和 V3）
  const totalBlocks = data.execution_summary?.length || (isV3 ? 1 : 0);
  const hasPathMappings = data.path_mappings && Object.keys(data.path_mappings).length > 0;
  const hasGeneratedFiles = data.generated_files && data.generated_files.length > 0;

  // V3 专用数据
  const userIntent = data.user_intent || "执行用户指令";
  const executionTime = data.execution_time || 0;
  const stdoutPreview = data.stdout_preview || "";
  const errorMessage = data.error_message || "";
  const retryCount = data.retry_count ?? data.total_retries ?? 0;

  // 计算成功/失败状态
  const isSuccess = isV3 ? data.success : (data.failed_count === 0 && data.success_count > 0);

  // ==========================================
  // 文件预览函数（使用弹窗，参考 RightPanel.tsx）
  // ==========================================
  const handlePreviewFile = async (filePath: string) => {
    const ext = filePath.split('.').pop()?.toLowerCase() || '';
    const isImage = ['png', 'jpg', 'jpeg', 'svg', 'gif'].includes(ext);
    const isText = ['txt', 'csv', 'tsv', 'md', 'py', 'r', 'json', 'sh', 'log', 'yaml', 'yml'].includes(ext);
    const isPdf = ext === 'pdf';

    if (!isImage && !isText && !isPdf) {
      alert("💡 当前文件格式暂不支持预览，请点击下载按钮保存到本地查看。");
      return;
    }

    setPreviewPath(filePath);
    setIsPreviewLoading(true);
    setPreviewContent(null);

    try {
      const token = localStorage.getItem('autonome_access_token') || localStorage.getItem('token');
      const res = await fetch(`${BASE_URL}/api/super-executor/files/preview?path=${encodeURIComponent(filePath)}&token=${token}`);

      if (!res.ok) throw new Error("获取文件失败");

      if (isImage) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setPreviewContent(url);
        setPreviewType('image');
      } else if (isPdf) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setPreviewContent(url);
        setPreviewType('pdf');
      } else {
        const text = await res.text();
        const MAX_LENGTH = 100000;
        setPreviewContent(text.length > MAX_LENGTH ? text.substring(0, MAX_LENGTH) + '\n\n... [文件过大，已截断]' : text);
        setPreviewType('text');
      }
    } catch (e) {
      console.error("预览加载失败:", e);
      alert("❌ 预览加载失败，请检查文件是否存在");
      setPreviewPath(null);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const closePreview = () => {
    if ((previewType === 'image' || previewType === 'pdf') && previewContent) {
      URL.revokeObjectURL(previewContent);
    }
    setPreviewPath(null);
    setPreviewContent(null);
  };

  // ==========================================
  // 文件下载函数（使用 fetch，避免打开新页面）
  // ==========================================
  const handleDownloadFile = async (filePath: string, fileName: string) => {
    try {
      const token = localStorage.getItem('autonome_access_token') || localStorage.getItem('token');
      const res = await fetch(`${BASE_URL}/api/super-executor/files/download?path=${encodeURIComponent(filePath)}&token=${token}`);

      if (!res.ok) throw new Error("获取文件失败");

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("下载失败:", e);
      alert("❌ 下载失败，请检查文件是否存在");
    }
  };

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className={`bg-gradient-to-br ${
          isSuccess
            ? "from-green-50/50 to-emerald-50/50 dark:from-green-950/30 dark:to-emerald-950/30 border-green-200 dark:border-green-800/50"
            : "from-red-50/50 to-orange-50/50 dark:from-red-950/30 dark:to-orange-950/30 border-red-200 dark:border-red-800/50"
        } border rounded-xl p-5 shadow-lg my-4 max-w-4xl`}
      >
        {/* 标题栏 */}
        <div
          className="flex items-center justify-between mb-4 cursor-pointer hover:bg-green-100/30 dark:hover:bg-green-900/20 rounded-lg p-2 -m-2 transition-colors"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${isSuccess ? "bg-green-100 dark:bg-green-900/50" : "bg-red-100 dark:bg-red-900/50"}`}>
              <Zap className={`w-5 h-5 ${isSuccess ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`} />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                执行战报 {isV3 && <span className="text-xs text-blue-500 dark:text-blue-400 ml-2">V3</span>}
              </h3>
              {/* V3: 显示用户意图 */}
              {isV3 && (
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {userIntent}
                </p>
              )}
              {!isV3 && (
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  超级执行者执行结果
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* 成功/失败徽章 */}
            <div className="flex items-center gap-2">
              {isV3 ? (
                <>
                  {isSuccess ? (
                    <span className="flex items-center gap-1 px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded-full">
                      <CheckCircle size={12} />
                      执行成功
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-xs rounded-full">
                      <XCircle size={12} />
                      执行失败
                    </span>
                  )}
                </>
              ) : (
                <>
                  {data.success_count > 0 && (
                    <span className="flex items-center gap-1 px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded-full">
                      <CheckCircle size={12} />
                      {data.success_count} 成功
                    </span>
                  )}
                  {data.failed_count > 0 && (
                    <span className="flex items-center gap-1 px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-xs rounded-full">
                      <XCircle size={12} />
                      {data.failed_count} 失败
                    </span>
                  )}
                </>
              )}
            </div>
            {isExpanded ? (
              <ChevronDown className="w-5 h-5 text-gray-500" />
            ) : (
              <ChevronRight className="w-5 h-5 text-gray-500" />
            )}
          </div>
        </div>

        {/* 展开内容 */}
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="space-y-4"
          >
            {/* 输出目录路径 */}
            {(data.task_out_dir || data.output_dir) && (
              <div className="p-4 bg-neutral-900/50 border border-neutral-800 rounded-xl">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FolderOpen size={16} className="text-cyan-400" />
                    <span className="text-sm text-neutral-400">输出目录:</span>
                  </div>
                  <button
                    onClick={() => copyToClipboard(data.task_out_dir || data.output_dir || "")}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-neutral-400 hover:text-white hover:bg-neutral-700 rounded transition-colors"
                    title="复制路径"
                  >
                    <Copy size={12} />
                    复制
                  </button>
                </div>
                <div className="mt-2 p-2 bg-neutral-800 rounded font-mono text-xs text-cyan-400 break-all">
                  {data.task_out_dir || data.output_dir}
                </div>
              </div>
            )}

            {/* 执行摘要统计 */}
            {isV3 ? (
              // V3 格式：显示执行时间、状态、重试次数
              <div className="grid grid-cols-3 gap-4">
                <div className={`rounded-xl p-4 text-center ${isSuccess ? "bg-green-500/10 border border-green-500/20" : "bg-red-500/10 border border-red-500/20"}`}>
                  <div className={`text-3xl font-bold ${isSuccess ? "text-green-400" : "text-red-400"}`}>
                    {isSuccess ? "✓" : "✗"}
                  </div>
                  <div className={`text-sm mt-1 ${isSuccess ? "text-green-300" : "text-red-300"}`}>
                    {isSuccess ? "执行成功" : "执行失败"}
                  </div>
                </div>
                <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-4 text-center">
                  <div className="text-3xl font-bold text-blue-400">{executionTime.toFixed(1)}s</div>
                  <div className="text-sm text-blue-300 mt-1">执行时间</div>
                </div>
                <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 text-center">
                  <div className="text-3xl font-bold text-yellow-400">{retryCount}</div>
                  <div className="text-sm text-yellow-300 mt-1">重试次数</div>
                </div>
              </div>
            ) : (
              // V1 格式：显示成功/失败/重试
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4 text-center">
                  <div className="text-3xl font-bold text-green-400">{data.success_count}</div>
                  <div className="text-sm text-green-300 mt-1">成功</div>
                </div>
                <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-center">
                  <div className="text-3xl font-bold text-red-400">{data.failed_count}</div>
                  <div className="text-sm text-red-300 mt-1">失败</div>
                </div>
                <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 text-center">
                  <div className="text-3xl font-bold text-yellow-400">{data.total_retries}</div>
                  <div className="text-sm text-yellow-300 mt-1">重试次数</div>
                </div>
              </div>
            )}

            {/* V3: 错误信息展示 */}
            {isV3 && errorMessage && (
              <div className="bg-red-900/20 border border-red-800/50 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <XCircle size={16} className="text-red-400" />
                  <span className="text-sm font-medium text-red-400">错误信息</span>
                </div>
                <div className="p-2 bg-neutral-900 rounded text-xs text-red-300 font-mono overflow-x-auto whitespace-pre-wrap">
                  {errorMessage}
                </div>
              </div>
            )}

            {/* V3: 执行日志折叠面板 */}
            {isV3 && stdoutPreview && (
              <div className="bg-white/50 dark:bg-black/20 rounded-lg overflow-hidden">
                <button
                  onClick={() => setShowExecutionLog(!showExecutionLog)}
                  className="w-full flex items-center justify-between px-4 py-3 bg-neutral-100/50 dark:bg-neutral-800/50 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
                    <FileText size={16} className="text-blue-500" />
                    执行日志
                  </div>
                  {showExecutionLog ? (
                    <ChevronDown size={16} className="text-neutral-400" />
                  ) : (
                    <ChevronRight size={16} className="text-neutral-400" />
                  )}
                </button>
                {showExecutionLog && (
                  <div className="border-t border-neutral-200 dark:border-neutral-700 p-3">
                    <div className="p-3 bg-neutral-900 rounded text-xs text-neutral-300 font-mono overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
                      {stdoutPreview}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 路径映射表 */}
            {hasPathMappings && (
              <div className="bg-white/50 dark:bg-black/20 rounded-lg overflow-hidden">
                <button
                  onClick={() => setShowPathMappings(!showPathMappings)}
                  className="w-full flex items-center justify-between px-4 py-3 bg-neutral-100/50 dark:bg-neutral-800/50 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
                    <FolderOpen size={16} className="text-green-500" />
                    路径映射 ({Object.keys(data.path_mappings).length})
                  </div>
                  {showPathMappings ? (
                    <ChevronDown size={16} className="text-neutral-400" />
                  ) : (
                    <ChevronRight size={16} className="text-neutral-400" />
                  )}
                </button>
                {showPathMappings && (
                  <div className="border-t border-neutral-200 dark:border-neutral-700">
                    <table className="w-full text-sm">
                      <thead className="bg-neutral-50 dark:bg-neutral-900/50">
                        <tr>
                          <th className="px-3 py-2 text-left text-neutral-500 dark:text-neutral-400 text-xs">
                            假路径
                          </th>
                          <th className="px-3 py-2 text-left text-neutral-500 dark:text-neutral-400 text-xs">
                            真实路径
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(data.path_mappings).map(([fake, real], idx) => (
                          <tr key={`path-${idx}`} className="border-t border-neutral-100 dark:border-neutral-800">
                            <td className="px-3 py-2 text-neutral-400 dark:text-neutral-500 font-mono text-xs truncate max-w-[200px]">
                              {fake}
                            </td>
                            <td className="px-3 py-2 text-green-600 dark:text-green-400 font-mono text-xs truncate max-w-[250px]">
                              {real}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* 执行详情 */}
            {data.execution_summary && data.execution_summary.length > 0 && (
              <div className="bg-white/50 dark:bg-black/20 rounded-lg overflow-hidden">
                <button
                  onClick={() => setShowExecutionDetails(!showExecutionDetails)}
                  className="w-full flex items-center justify-between px-4 py-3 bg-neutral-100/50 dark:bg-neutral-800/50 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
                    <FileCode size={16} className="text-blue-500" />
                    执行详情 ({data.execution_summary.length} 个代码块)
                  </div>
                  {showExecutionDetails ? (
                    <ChevronDown size={16} className="text-neutral-400" />
                  ) : (
                    <ChevronRight size={16} className="text-neutral-400" />
                  )}
                </button>
                {showExecutionDetails && (
                  <div className="p-3 space-y-2 border-t border-neutral-200 dark:border-neutral-700">
                    {data.execution_summary.map((result, idx) => (
                      <div
                        key={idx}
                        className={`p-3 rounded-lg border ${
                          result.exit_code === 0
                            ? "bg-green-500/5 border-green-500/20"
                            : "bg-red-500/5 border-red-500/20"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span
                              className={`px-2 py-0.5 rounded text-xs ${
                                result.language === "python"
                                  ? "bg-blue-500/20 text-blue-400"
                                  : "bg-purple-500/20 text-purple-400"
                              }`}
                            >
                              {result.language.toUpperCase()}
                            </span>
                            <span className="text-neutral-300 text-sm">代码块 #{result.order + 1}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            {result.retry_count > 0 && (
                              <span className="flex items-center gap-1 text-yellow-400 text-xs">
                                <RefreshCw size={10} />
                                重试 {result.retry_count} 次
                              </span>
                            )}
                            {result.exit_code === 0 ? (
                              <CheckCircle size={16} className="text-green-400" />
                            ) : (
                              <XCircle size={16} className="text-red-400" />
                            )}
                          </div>
                        </div>
                        {result.error && (
                          <div className="mt-2 p-2 bg-red-900/20 rounded text-xs text-red-300 font-mono overflow-x-auto">
                            {result.error}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 生成文件 */}
            {hasGeneratedFiles && (
              <div className="bg-white/50 dark:bg-black/20 rounded-lg overflow-hidden">
                <button
                  onClick={() => setShowGeneratedFiles(!showGeneratedFiles)}
                  className="w-full flex items-center justify-between px-4 py-3 bg-neutral-100/50 dark:bg-neutral-800/50 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
                    <Zap size={16} className="text-amber-500" />
                    生成文件 ({data.generated_files.length})
                  </div>
                  {showGeneratedFiles ? (
                    <ChevronDown size={16} className="text-neutral-400" />
                  ) : (
                    <ChevronRight size={16} className="text-neutral-400" />
                  )}
                </button>
                {showGeneratedFiles && (
                  <div className="p-3 space-y-2 max-h-64 overflow-y-auto border-t border-neutral-200 dark:border-neutral-700">
                    {data.generated_files.map((file, idx) => (
                      <div
                        key={idx}
                        className="flex items-center gap-3 p-3 bg-neutral-100/50 dark:bg-neutral-800/50 rounded-lg border border-neutral-200 dark:border-neutral-700 hover:border-neutral-400 dark:hover:border-neutral-600 transition-colors"
                      >
                        {getFileIcon(file.extension)}
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-neutral-200 truncate" title={file.name}>{file.name}</div>
                          <div className="text-xs text-neutral-500">{formatSize(file.size)}</div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {/* 预览按钮 */}
                          {isPreviewable(file.extension) && (
                            <button
                              onClick={() => handlePreviewFile(file.path)}
                              className="p-1.5 text-neutral-400 hover:text-cyan-400 hover:bg-neutral-700 rounded transition-colors"
                              title="预览"
                            >
                              <Eye size={14} />
                            </button>
                          )}
                          {/* 下载按钮 */}
                          <button
                            onClick={() => handleDownloadFile(file.path, file.name)}
                            className="p-1.5 text-neutral-400 hover:text-green-400 hover:bg-neutral-700 rounded transition-colors"
                            title="下载"
                          >
                            <Download size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}
      </motion.div>

      {/* 预览弹窗（参考 RightPanel.tsx 实现）*/}
      {previewPath && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 md:p-12 animate-in fade-in duration-200">
          <div className="bg-white dark:bg-[#1a1a1c] border border-gray-200 dark:border-neutral-800 rounded-2xl w-full max-w-5xl h-full flex flex-col shadow-2xl overflow-hidden relative animate-in zoom-in-95 duration-200">

            <div className="h-14 shrink-0 border-b border-gray-200 dark:border-neutral-800 px-6 flex items-center justify-between bg-gray-50 dark:bg-neutral-900">
              <div className="flex items-center gap-3">
                <Eye size={18} className="text-emerald-500 dark:text-emerald-400"/>
                <h3 className="text-gray-900 dark:text-white font-medium text-sm tracking-wide truncate max-w-lg">{previewPath.split('/').pop()}</h3>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleDownloadFile(previewPath, previewPath.split('/').pop() || 'download')}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 dark:bg-blue-500/10 hover:bg-blue-100 dark:hover:bg-blue-500/20 text-blue-600 dark:text-blue-400 text-xs font-medium rounded-lg transition-colors border border-blue-200 dark:border-blue-500/20"
                >
                  <Download size={14} /> 保存到本地
                </button>
                <div className="w-px h-4 bg-gray-200 dark:bg-neutral-800 mx-1"></div>
                <button
                  onClick={closePreview}
                  className="p-1.5 text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-auto p-6 flex items-start justify-center bg-gray-100 dark:bg-[#121212] relative">
              {isPreviewLoading ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-gray-400 dark:text-neutral-500">
                  <Loader2 size={32} className="animate-spin text-emerald-500" />
                  <span className="text-sm tracking-widest">安全加载中...</span>
                </div>
              ) : previewType === 'image' && previewContent ? (
                <img src={previewContent} alt="Preview" className="max-w-full max-h-full object-contain rounded drop-shadow-2xl" />
              ) : previewType === 'pdf' && previewContent ? (
                <iframe src={previewContent} className="w-full h-full rounded-xl border border-gray-200 dark:border-neutral-800 bg-white" title="PDF Preview" />
              ) : previewType === 'text' && previewContent ? (
                <div className="w-full h-full bg-white dark:bg-[#1e1e1e] rounded-xl border border-gray-200 dark:border-neutral-800 overflow-hidden flex flex-col">
                  {/* 语法高亮代码预览 */}
                  <SyntaxHighlighter
                    language={getLanguageFromExt('.' + (previewPath?.split('.').pop() || 'txt'))}
                    style={oneDark}
                    customStyle={{
                      margin: 0,
                      padding: '16px',
                      background: 'transparent',
                      fontSize: '13px',
                      lineHeight: '1.6',
                      height: '100%',
                      overflow: 'auto',
                    }}
                    showLineNumbers={true}
                    lineNumberStyle={{
                      minWidth: '3em',
                      paddingRight: '1em',
                      color: '#6b7280',
                      textAlign: 'right',
                    }}
                  >
                    {previewContent}
                  </SyntaxHighlighter>
                </div>
              ) : null}
            </div>

          </div>
        </div>
      )}
    </>
  );
});

export default BattleReportCard;