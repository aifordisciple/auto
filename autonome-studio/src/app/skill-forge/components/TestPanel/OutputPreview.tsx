/**
 * 测试输出预览组件
 *
 * 支持预览表格数据、图片、文本文件等
 */

'use client';

import React, { useState, useEffect } from 'react';
import { FileText, Image, Table, File, Download, Eye, Maximize2, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

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

  // 按类型分组
  const groupedOutputs = outputs.reduce((acc, file) => {
    if (!acc[file.type]) acc[file.type] = [];
    acc[file.type].push(file);
    return acc;
  }, {} as Record<OutputFile['type'], OutputFile[]>);

  const handleFileClick = (file: OutputFile) => {
    setSelectedFile(file);
    setShowModal(true);
    onSelect?.(file);
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
                  <div className="flex justify-center">
                    <img
                      src={selectedFile.path}
                      alt={selectedFile.name}
                      className="max-w-full max-h-[60vh] object-contain"
                    />
                  </div>
                )}

                {selectedFile.type === 'table' && selectedFile.preview && (
                  <TablePreview data={selectedFile.preview} />
                )}

                {selectedFile.type === 'text' && selectedFile.preview && (
                  <pre className="text-xs text-neutral-300 font-mono whitespace-pre-wrap bg-neutral-800 p-4 rounded-lg">
                    {selectedFile.preview}
                  </pre>
                )}

                {(selectedFile.type === 'pdf' || selectedFile.type === 'other') && (
                  <div className="text-center py-8 text-neutral-500">
                    <File size={48} className="mx-auto mb-4 opacity-50" />
                    <p>无法预览此文件类型</p>
                    <p className="text-sm mt-2">{selectedFile.path}</p>
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