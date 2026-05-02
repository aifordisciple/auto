/**
 * ClaudePreview — Claude 模式右侧预览区
 *
 * 显示会话相关的文件、任务、输出结果。
 * 支持：
 * - 文件列表浏览 (workspace files)
 * - 图片预览 (PNG/JPG/SVG)
 * - CSV/TSV 表格预览
 * - HTML 报告 iframe 预览
 * - 任务状态概览
 */
'use client';

import { useEffect, useState, useCallback } from 'react';
import { fetchAPI } from '@/lib/api';

interface WorkspaceFile {
  name: string;
  path: string;
  size: number;
  type: 'image' | 'csv' | 'html' | 'text' | 'other';
  modified_at: string;
}

interface PreviewState {
  type: 'none' | 'image' | 'csv' | 'html';
  filePath?: string;
  data?: string;
}

export function ClaudePreview({ onClose }: { onClose?: () => void }) {
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<PreviewState>({ type: 'none' });
  const [csvData, setCsvData] = useState<string[][]>([]);

  const detectFileType = (name: string): WorkspaceFile['type'] => {
    const ext = name.split('.').pop()?.toLowerCase();
    if (['png', 'jpg', 'jpeg', 'svg', 'gif', 'webp'].includes(ext || '')) return 'image';
    if (['csv', 'tsv'].includes(ext || '')) return 'csv';
    if (['html', 'htm'].includes(ext || '')) return 'html';
    if (['txt', 'md', 'py', 'r', 'sh', 'json', 'yaml', 'yml', 'log'].includes(ext || '')) return 'text';
    return 'other';
  };

  const loadFiles = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchAPI('/api/claude/workspace/files');
      if (res.ok) {
        const data = await res.json();
        const typed = (data.files || []).map((f: WorkspaceFile) => ({
          ...f,
          type: detectFileType(f.name),
        }));
        setFiles(typed);
      }
    } catch {
      // 文件列表暂不可用
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFiles();
    const interval = setInterval(loadFiles, 10000);
    return () => clearInterval(interval);
  }, [loadFiles]);

  const handlePreviewImage = async (filePath: string) => {
    setPreview({ type: 'image', filePath });
  };

  const handlePreviewCsv = async (filePath: string) => {
    try {
      const res = await fetchAPI(`/api/claude/workspace/files/content?path=${encodeURIComponent(filePath)}`);
      if (res.ok) {
        const text = await res.text();
        const lines = text.trim().split('\n');
        const delimiter = filePath.endsWith('.tsv') ? '\t' : ',';
        const rows = lines.map((line: string) => line.split(delimiter));
        setCsvData(rows);
        setPreview({ type: 'csv', filePath });
      }
    } catch {
      // 预览失败
    }
  };

  const handlePreviewHtml = async (filePath: string) => {
    setPreview({ type: 'html', filePath });
  };

  const closePreview = () => {
    setPreview({ type: 'none' });
    setCsvData([]);
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const fileIcon = (type: WorkspaceFile['type']) => {
    switch (type) {
      case 'image': return '🖼';
      case 'csv': return '📊';
      case 'html': return '🌐';
      case 'text': return '📄';
      default: return '📁';
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 标题区 */}
      <div className="px-3 py-2 border-b border-gray-700 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-300">预览区</h3>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-xs px-1.5 py-0.5 rounded hover:bg-gray-700 transition-colors"
            title="隐藏预览面板"
          >
            ✕
          </button>
        )}
      </div>

      {/* 预览内容区 */}
      {preview.type !== 'none' ? (
        <div className="flex-1 flex flex-col">
          <div className="flex items-center justify-between px-3 py-1.5 bg-gray-800 border-b border-gray-700">
            <span className="text-xs text-gray-400 truncate">{preview.filePath}</span>
            <button
              onClick={closePreview}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              ✕ 关闭
            </button>
          </div>
          <div className="flex-1 overflow-auto">
            {preview.type === 'image' && (
              <div className="p-2">
                <img
                  src={`/api/claude/workspace/files/content?path=${encodeURIComponent(preview.filePath || '')}`}
                  alt={preview.filePath}
                  className="max-w-full rounded"
                />
              </div>
            )}
            {preview.type === 'csv' && csvData.length > 0 && (
              <div className="overflow-auto">
                <table className="text-xs border-collapse">
                  <thead>
                    <tr className="bg-gray-800">
                      {csvData[0]?.map((col, i) => (
                        <th key={i} className="px-2 py-1 text-left text-gray-400 border border-gray-700 whitespace-nowrap">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {csvData.slice(1, 100).map((row, ri) => (
                      <tr key={ri} className={ri % 2 === 0 ? 'bg-gray-850' : ''}>
                        {row.map((col, ci) => (
                          <td key={ci} className="px-2 py-0.5 text-gray-300 border border-gray-700/50 whitespace-nowrap max-w-[200px] truncate">
                            {col}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {csvData.length > 101 && (
                  <div className="text-xs text-gray-500 p-2">
                    仅显示前 100 行 (共 {csvData.length - 1} 行数据)
                  </div>
                )}
              </div>
            )}
            {preview.type === 'html' && (
              <iframe
                src={`/api/claude/workspace/files/content?path=${encodeURIComponent(preview.filePath || '')}`}
                className="w-full h-full border-0 bg-white"
                sandbox="allow-scripts"
              />
            )}
          </div>
        </div>
      ) : (
        /* 文件列表 */
        <div className="flex-1 overflow-y-auto">
          {loading && files.length === 0 ? (
            <div className="p-3 text-xs text-gray-500">加载文件列表...</div>
          ) : files.length === 0 ? (
            <div className="p-3 text-xs text-gray-500">
              暂无文件
              <div className="mt-1 text-gray-600">
                分析结果文件将显示在这里
              </div>
            </div>
          ) : (
            <div className="p-2 space-y-0.5">
              {files.map((file, i) => (
                <button
                  key={i}
                  onClick={() => {
                    if (file.type === 'image') handlePreviewImage(file.path);
                    else if (file.type === 'csv') handlePreviewCsv(file.path);
                    else if (file.type === 'html') handlePreviewHtml(file.path);
                  }}
                  className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-left hover:bg-gray-800 transition-colors ${
                    file.type !== 'text' && file.type !== 'other'
                      ? 'cursor-pointer'
                      : 'cursor-default'
                  }`}
                >
                  <span>{fileIcon(file.type)}</span>
                  <span className="text-gray-300 truncate flex-1">{file.name}</span>
                  <span className="text-gray-600 shrink-0">{formatSize(file.size)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 底部提示 */}
      <div className="px-3 py-2 border-t border-gray-700 text-xs text-gray-600">
        点击文件预览 | 结果自动刷新
      </div>
    </div>
  );
}
