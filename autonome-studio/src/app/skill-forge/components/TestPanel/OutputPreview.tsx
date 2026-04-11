/**
 * 测试输出预览组件
 *
 * 支持预览表格数据、图片、PDF、文本文件等
 * 支持文件下载
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { FileText, Image, Table, File, Download, Eye, Maximize2, X, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { BASE_URL } from '@/lib/api';

export interface OutputFile {
  name: string;
  path: string;
  type: 'table' | 'image' | 'text' | 'pdf' | 'other';
  size?: number;
  preview?: string; // 用于文本/表格预览内容
}

interface OutputPreviewProps {
  outputs: OutputFile[];
  baseDir?: string;
  onSelect?: (file: OutputFile) => void;
}

// 根据文件扩展名判断类型
const getFileType = (filename: string): OutputFile['type'] => {
  const ext = filename.toLowerCase().split('.').pop();

  if (['tsv', 'csv', 'xls', 'xlsx'].includes(ext || '')) return 'table';
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext || '')) return 'image';
  if (['pdf'].includes(ext || '')) return 'pdf';
  if (['txt', 'md', 'json', 'yaml', 'yml', 'log'].includes(ext || '')) return 'text';

  return 'other';
};

// 从后端类型映射到前端类型
const mapBackendType = (backendType: string, filename: string): OutputFile['type'] => {
  // 后端返回 'data' 类型对应前端的 'table'
  if (backendType === 'data') return 'table';
  // 后端返回 'image' 类型
  if (backendType === 'image') return 'image';
  // 后端返回 'text' 类型
  if (backendType === 'text') return 'text';
  // 后端返回 'script' 类型
  if (backendType === 'script') return 'text';
  // 后端返回 'pdf' 类型
  if (backendType === 'pdf') return 'pdf';
  // 其他情况根据文件名推断
  return getFileType(filename);
};

// 格式化文件大小
const formatSize = (bytes?: number): string => {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

// 获取文件图标
const FileIcon = ({ type }: { type: OutputFile['type'] }) => {
  switch (type) {
    case 'table':
      return <Table size={16} className="text-green-400" />;
    case 'image':
      return <Image size={16} className="text-purple-400" />;
    case 'text':
      return <FileText size={16} className="text-blue-400" />;
    case 'pdf':
      return <File size={16} className="text-red-400" />;
    default:
      return <File size={16} className="text-neutral-400" />;
  }
};

// 文件卡片组件
const FileCard = ({ file, onClick }: { file: OutputFile; onClick: () => void }) => (
  <button
    onClick={onClick}
    className="flex items-center gap-3 p-2 rounded-lg border border-neutral-700 hover:border-neutral-500 hover:bg-neutral-800/50 transition-all text-left group"
  >
    <div className="p-2 bg-neutral-800 rounded">
      <FileIcon type={file.type} />
    </div>
    <div className="flex-1 min-w-0">
      <div className="text-sm text-white truncate group-hover:text-blue-400 transition-colors">
        {file.name}
      </div>
      <div className="text-xs text-neutral-500">
        {formatSize(file.size)}
        {file.preview && <span className="ml-2 text-green-500">可预览</span>}
      </div>
    </div>
    <Eye size={14} className="text-neutral-600 group-hover:text-neutral-400 transition-colors" />
  </button>
);

// 图片预览模态框
const ImageModal = ({ file, onClose }: { file: OutputFile; onClose: () => void }) => (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0 }}
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
    onClick={onClose}
  >
    <motion.div
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      exit={{ scale: 0.9, opacity: 0 }}
      className="relative max-w-[90vw] max-h-[90vh]"
      onClick={e => e.stopPropagation()}
    >
      <button
        onClick={onClose}
        className="absolute -top-10 right-0 p-2 text-white hover:text-neutral-300"
      >
        <X size={24} />
      </button>
      {/* 图片展示 - 实际使用时需要根据 path 构建正确的 URL */}
      <img
        src={file.path}
        alt={file.name}
        className="max-w-full max-h-[85vh] object-contain rounded-lg"
      />
      <div className="text-center mt-2 text-sm text-neutral-400">
        {file.name}
      </div>
    </motion.div>
  </motion.div>
);

// 表格预览组件
const TablePreview = ({ data, maxRows = 20 }: { data: string; maxRows?: number }) => {
  // 解析 CSV/TSV
  const parseTable = (text: string) => {
    const lines = text.split('\n').filter(Boolean);
    const separator = text.includes('\t') ? '\t' : ',';
    return lines.slice(0, maxRows).map(line => line.split(separator));
  };

  const rows = parseTable(data);

  if (rows.length === 0) {
    return <div className="text-neutral-500 text-sm">无法解析表格数据</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="border-b border-neutral-700">
            {rows[0].map((cell, i) => (
              <th key={i} className="px-2 py-1 text-left text-neutral-400 font-medium whitespace-nowrap">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(1).map((row, i) => (
            <tr key={i} className="border-b border-neutral-800">
              {row.map((cell, j) => (
                <td key={j} className="px-2 py-1 text-neutral-300 whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length >= maxRows && (
        <div className="text-xs text-neutral-500 mt-2">
          仅显示前 {maxRows} 行...
        </div>
      )}
    </div>
  );
};

export function OutputPreview({ outputs, baseDir, onSelect }: OutputPreviewProps) {
  const [selectedFile, setSelectedFile] = useState<OutputFile | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileMimeType, setFileMimeType] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  // 清理 Blob URL
  useEffect(() => {
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [blobUrl]);

  // 规范化文件类型（处理后端返回的类型）
  const normalizedOutputs = outputs.map(file => ({
    ...file,
    type: mapBackendType(file.type, file.name)
  }));

  // 按类型分组
  const groupedOutputs = normalizedOutputs.reduce((acc, file) => {
    if (!acc[file.type]) acc[file.type] = [];
    acc[file.type].push(file);
    return acc;
  }, {} as Record<OutputFile['type'], OutputFile[]>);

  // Base64 转 Blob URL
  const base64ToBlobUrl = useCallback((base64: string, mimeType: string): string => {
    try {
      const byteCharacters = atob(base64);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: mimeType });
      const url = URL.createObjectURL(blob);
      console.log('[OutputPreview] base64ToBlobUrl 成功, blob大小:', blob.size, 'URL:', url);
      return url;
    } catch (e) {
      console.error('[OutputPreview] base64ToBlobUrl 失败:', e);
      throw e;
    }
  }, []);

  // 加载文件内容
  const loadFileContent = useCallback(async (file: OutputFile) => {
    // 文本和表格文件已有预览内容，不需要重新加载
    if ((file.type === 'text' || file.type === 'table') && file.preview) {
      return;
    }

    // 图片和PDF需要从后端加载
    if (file.type === 'image' || file.type === 'pdf') {
      setIsLoading(true);
      try {
        const token = localStorage.getItem('autonome_access_token');
        console.log('[OutputPreview] 加载文件:', file.path, '类型:', file.type);

        const response = await fetch(
          `${BASE_URL}/api/skills/forge/test_file?path=${encodeURIComponent(file.path)}`,
          {
            headers: token ? { 'Authorization': `Bearer ${token}` } : {}
          }
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('[OutputPreview] API响应:', {
          status: data.status,
          type: data.type,
          mime_type: data.mime_type,
          data_length: data.data?.length
        });

        if (data.status === 'success') {
          setFileContent(data.data);
          setFileMimeType(data.mime_type);

          // PDF 使用 Blob URL 以支持 iframe 预览
          if (file.type === 'pdf') {
            try {
              const url = base64ToBlobUrl(data.data, data.mime_type);
              console.log('[OutputPreview] 创建Blob URL成功:', url);
              setBlobUrl(url);
            } catch (e) {
              console.error('[OutputPreview] 创建Blob URL失败:', e);
            }
          }
        } else {
          console.error('[OutputPreview] API返回错误:', data);
        }
      } catch (error) {
        console.error('[OutputPreview] 加载文件失败:', error);
        setFileContent(null);
        setBlobUrl(null);
      } finally {
        setIsLoading(false);
      }
    }
  }, [base64ToBlobUrl]);

  // 下载文件
  const handleDownload = useCallback(async (file: OutputFile) => {
    try {
      const token = localStorage.getItem('autonome_access_token');
      const response = await fetch(
        `${BASE_URL}/api/skills/forge/test_file?path=${encodeURIComponent(file.path)}`,
        {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        }
      );

      if (!response.ok) {
        throw new Error('下载文件失败');
      }

      const data = await response.json();
      if (data.status === 'success') {
        // 创建 blob 并下载
        const byteCharacters = atob(data.data);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: data.mime_type });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('下载失败:', error);
    }
  }, []);

  const handleFileClick = (file: OutputFile) => {
    // 清理旧的 Blob URL
    if (blobUrl) {
      URL.revokeObjectURL(blobUrl);
      setBlobUrl(null);
    }
    setSelectedFile(file);
    setShowModal(true);
    setFileContent(null);
    setFileMimeType(null);
    onSelect?.(file);
    loadFileContent(file);
  };

  if (outputs.length === 0) {
    return (
      <div className="p-4 text-center text-neutral-600">
        <File size={24} className="mx-auto mb-2 opacity-50" />
        <p className="text-sm">暂无输出文件</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 输出文件列表 */}
      {(['image', 'table', 'text', 'pdf', 'other'] as OutputFile['type'][]).map(type => {
        const files = groupedOutputs[type];
        if (!files || files.length === 0) return null;

        return (
          <div key={type}>
            <div className="text-xs text-neutral-500 mb-2 flex items-center gap-1">
              <FileIcon type={type} />
              <span>
                {type === 'image' ? '图片文件' :
                 type === 'table' ? '表格文件' :
                 type === 'text' ? '文本文件' :
                 type === 'pdf' ? 'PDF 文件' : '其他文件'}
              </span>
              <span className="text-neutral-600">({files.length})</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {files.map(file => (
                <FileCard
                  key={file.path}
                  file={file}
                  onClick={() => handleFileClick(file)}
                />
              ))}
            </div>
          </div>
        );
      })}

      {/* 预览模态框 */}
      <AnimatePresence>
        {showModal && selectedFile && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
            onClick={() => setShowModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl w-full max-w-4xl max-h-[80vh] overflow-hidden"
              onClick={e => e.stopPropagation()}
            >
              {/* 标题栏 */}
              <div className="flex items-center justify-between p-4 border-b border-neutral-800">
                <div className="flex items-center gap-2">
                  <FileIcon type={selectedFile.type} />
                  <span className="text-white font-medium">{selectedFile.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => selectedFile && handleDownload(selectedFile)}
                    className="p-2 text-neutral-400 hover:text-white transition-colors"
                    title="下载"
                  >
                    <Download size={16} />
                  </button>
                  <button
                    onClick={() => setShowModal(false)}
                    className="p-2 text-neutral-400 hover:text-white transition-colors"
                  >
                    <X size={20} />
                  </button>
                </div>
              </div>

              {/* 内容区 */}
              <div className="p-4 overflow-auto max-h-[calc(80vh-60px)]">
                {selectedFile.type === 'image' && (
                  isLoading ? (
                    <div className="text-center py-8 text-neutral-500">
                      <Loader2 size={48} className="mx-auto mb-4 animate-spin" />
                      <p>加载中...</p>
                    </div>
                  ) : fileContent && fileMimeType ? (
                    <div className="text-center">
                      <img
                        src={`data:${fileMimeType};base64,${fileContent}`}
                        alt={selectedFile.name}
                        className="max-w-full max-h-[60vh] object-contain rounded-lg mx-auto"
                      />
                      <div className="text-xs text-neutral-500 mt-2">
                        {selectedFile.name} • {formatSize(selectedFile.size)}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-neutral-500">
                      <Image size={48} className="mx-auto mb-4 opacity-50" />
                      <p>图片加载失败</p>
                      <p className="text-sm mt-2 text-neutral-600">{selectedFile.path}</p>
                      <p className="text-xs mt-4 text-neutral-600">提示：可下载文件后本地查看</p>
                    </div>
                  )
                )}

                {selectedFile.type === 'table' && (
                  selectedFile.preview ? (
                    <TablePreview data={selectedFile.preview} />
                  ) : (
                    <div className="text-center py-8 text-neutral-500">
                      <Table size={48} className="mx-auto mb-4 opacity-50" />
                      <p>表格文件较大，暂无预览</p>
                      <p className="text-sm mt-2 text-neutral-600">{selectedFile.path}</p>
                    </div>
                  )
                )}

                {selectedFile.type === 'text' && (
                  selectedFile.preview ? (
                    <pre className="text-xs text-neutral-300 font-mono whitespace-pre-wrap bg-neutral-800 p-4 rounded-lg">
                      {selectedFile.preview}
                    </pre>
                  ) : (
                    <div className="text-center py-8 text-neutral-500">
                      <FileText size={48} className="mx-auto mb-4 opacity-50" />
                      <p>文本文件较大，暂无预览</p>
                      <p className="text-sm mt-2 text-neutral-600">{selectedFile.path}</p>
                    </div>
                  )
                )}

                {selectedFile.type === 'pdf' && (
                  isLoading ? (
                    <div className="text-center py-8 text-neutral-500">
                      <Loader2 size={48} className="mx-auto mb-4 animate-spin" />
                      <p>加载中...</p>
                    </div>
                  ) : blobUrl ? (
                    <div className="w-full">
                      <iframe
                        src={blobUrl}
                        className="w-full h-[60vh] rounded-lg border border-neutral-700"
                        title={selectedFile.name}
                      />
                      <div className="text-xs text-neutral-500 mt-2 text-center">
                        {selectedFile.name} • {formatSize(selectedFile.size)}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-neutral-500">
                      <File size={48} className="mx-auto mb-4 opacity-50" />
                      <p>PDF 加载失败</p>
                      <p className="text-sm mt-2 text-neutral-600">{selectedFile.path}</p>
                      <p className="text-xs mt-4 text-neutral-600">提示：可下载文件后本地查看</p>
                    </div>
                  )
                )}

                {selectedFile.type === 'other' && (
                  <div className="text-center py-8 text-neutral-500">
                    <File size={48} className="mx-auto mb-4 opacity-50" />
                    <p>无法预览此文件类型</p>
                    <p className="text-sm mt-2">{selectedFile.path}</p>
                    <p className="text-xs mt-4 text-neutral-600">提示：可下载文件后本地查看</p>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}