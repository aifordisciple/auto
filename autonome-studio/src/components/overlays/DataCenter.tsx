"use client";

import React, { useState, useMemo, useRef } from 'react';
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { X, HardDrive, FolderOpen, Folder, FileText, Search, ChevronRight, ChevronDown, Table2, Image as ImageIcon, Trash2, Download, RefreshCw, UploadCloud, Loader2, Lock, Eye } from "lucide-react";
import { fetchAPI, BASE_URL } from "@/lib/api";

// ==========================================
// 辅助函数：根据文件名分配图标
// ==========================================
const getFileIcon = (filename: string) => {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tsv') || lower.endsWith('.csv') || lower.endsWith('.txt') || lower.endsWith('.log')) {
    return <Table2 size={16} className="text-blue-400 shrink-0" />;
  }
  if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.pdf') || lower.endsWith('.svg')) {
    return <ImageIcon size={16} className="text-pink-400 shrink-0" />;
  }
  return <FileText size={16} className="text-neutral-400 shrink-0" />;
};

// ==========================================
// 辅助函数：智能转换文件大小
// ==========================================
const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

// ==========================================
// 组件 1：递归渲染单个节点
// ==========================================
const TreeNode = ({ node, expandedFolders, toggleExpand, onDelete, onDownload, onPreview }: any) => {
  const isFolder = node.type === 'folder';
  const isExpanded = expandedFolders.has(node.path);
  const isProtectedRoot = isFolder && (node.path === 'raw_data' || node.path === 'results' || node.path === 'references');
  const isReadOnly = node.path.startsWith('references');

  return (
    <div className="flex flex-col">
      <div
        className={`flex items-center gap-2 px-2 py-1.5 hover:bg-neutral-800/80 rounded-lg cursor-pointer group transition-all ${!isFolder ? 'ml-6' : ''}`}
        onClick={() => {
          if (isFolder) toggleExpand(node.path);
          else onPreview(node.path);
        }}
      >
        {isFolder && (
          <span className="text-neutral-500 group-hover:text-neutral-300 transition-colors shrink-0">
            {isExpanded ? <ChevronDown size={15} strokeWidth={2.5} /> : <ChevronRight size={15} strokeWidth={2.5} />}
          </span>
        )}

        {isFolder ? (
          isExpanded ? <FolderOpen size={16} className={`${isReadOnly ? 'text-emerald-500' : 'text-purple-400'} shrink-0`} /> : <Folder size={16} className={`${isReadOnly ? 'text-emerald-500' : 'text-purple-400'} shrink-0`} />
        ) : (
          getFileIcon(node.name)
        )}

        <span className={`text-sm tracking-wide truncate ${isFolder ? 'text-neutral-200 font-semibold' : 'text-neutral-400 group-hover:text-neutral-200'}`}>
          {node.name}
        </span>

        {isFolder && isReadOnly && node.path === 'references' && (
          <span className="flex items-center gap-1 text-[9px] bg-emerald-500/10 text-emerald-500 px-1.5 py-0.5 rounded border border-emerald-500/20 uppercase tracking-wider shrink-0">
            <Lock size={10} /> 只读共享
          </span>
        )}

        {/* 操作栏 */}
        <div className="ml-auto flex items-center opacity-0 group-hover:opacity-100 transition-opacity gap-1 z-10 shrink-0">
          {!isFolder && (
            <>
              {/* 新增：预览按钮 */}
              <button
                onClick={(e) => { e.stopPropagation(); onPreview(node.path); }}
                className="p-1.5 text-neutral-500 hover:text-emerald-400 hover:bg-emerald-500/10 rounded-md transition-all"
                title="安全预览"
              >
                <Eye size={14} />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onDownload(node.path); }}
                className="p-1.5 text-neutral-500 hover:text-blue-400 hover:bg-blue-500/10 rounded-md transition-all"
                title="直接下载"
              >
                <Download size={14} />
              </button>
            </>
          )}
          {!isProtectedRoot && !isFolder && !isReadOnly && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(node.path); }}
              className="p-1.5 text-neutral-500 hover:text-red-400 hover:bg-red-500/10 rounded-md transition-all"
              title="彻底删除"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>

        {!isFolder && node.fileData?.file_size !== undefined && (
          <span className="text-[10px] text-neutral-600 font-mono bg-neutral-900 px-1.5 py-0.5 rounded border border-neutral-800 group-hover:hidden shrink-0 ml-auto">
            {formatBytes(node.fileData.file_size)}
          </span>
        )}
      </div>

      {isFolder && isExpanded && (
        <div className="ml-4 border-l border-neutral-800 pl-2 mt-1 mb-2 flex flex-col gap-0.5">
          {Object.values(node.children).map((child: any) => (
            <TreeNode
              key={child.path}
              node={child}
              expandedFolders={expandedFolders}
              toggleExpand={toggleExpand}
              onDelete={onDelete}
              onDownload={onDownload}
              onPreview={onPreview}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// ==========================================
// 主组件：全景数据中心
// ==========================================
export function DataCenter() {
  const { isDataCenterOpen, closeAllOverlays } = useUIStore();
  const { currentProjectId, projectFiles, fetchProjectFiles } = useWorkspaceStore();

  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['raw_data', 'results', 'references']));
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  // 预览弹窗状态
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<'image' | 'text' | 'pdf' | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  const toggleExpand = (path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleDeleteNode = async (filePath: string) => {
    if (!window.confirm(`⚠️ 危险操作\n\n确定要从物理磁盘彻底删除 \n${filePath} 吗？\n此操作不可逆！`)) return;
    try {
      await fetchAPI(`/api/projects/${currentProjectId}/files/${filePath}`, { method: 'DELETE' });
      if (currentProjectId) fetchProjectFiles(currentProjectId);
    } catch (e) {
      alert("❌ 删除失败，可能文件正被系统占用或无权限。");
    }
  };

  // 基于内存 Blob 流的安全下载，完美携带 Token
  const handleDownloadNode = async (filePath: string) => {
    if (!currentProjectId) return;
    try {
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${BASE_URL}/api/projects/${currentProjectId}/files/${filePath}/view`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!res.ok) throw new Error("获取文件失败");

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = url;
      a.download = filePath.split('/').pop() || 'download';
      document.body.appendChild(a);
      a.click();

      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert("❌ 下载失败，可能是网络问题或无权限访问该文件。");
    }
  };

  // 核心逻辑：安全拉取文件并在内存中渲染
  const handlePreviewNode = async (filePath: string) => {
    if (!currentProjectId) return;
    const ext = filePath.split('.').pop()?.toLowerCase() || '';
    const isImage = ['png', 'jpg', 'jpeg', 'svg', 'gif'].includes(ext);
    const isText = ['txt', 'csv', 'tsv', 'md', 'py', 'r', 'json', 'sh', 'log', 'yaml', 'yml'].includes(ext);
    const isPdf = ext === 'pdf';

    if (!isImage && !isText && !isPdf) {
      alert("💡 当前文件格式暂不支持内存预览，请点击右侧【下载】按钮直接下载。");
      return;
    }

    setPreviewPath(filePath);
    setIsPreviewLoading(true);
    setPreviewContent(null);

    try {
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${BASE_URL}/api/projects/${currentProjectId}/files/${filePath}/view`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

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
        setPreviewContent(text.length > MAX_LENGTH ? text.substring(0, MAX_LENGTH) + '\n\n... [⚠️ 数据表过大，内存预览已截断，请下载查看完整全貌]' : text);
        setPreviewType('text');
      }
    } catch (e) {
      alert("❌ 预览加载失败，可能是网络问题或权限不足。");
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

  const handleSync = async () => {
    if (!currentProjectId) return;
    setIsSyncing(true);
    await fetchProjectFiles(currentProjectId);
    setTimeout(() => setIsSyncing(false), 600);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0 || !currentProjectId) return;

    setIsUploading(true);
    try {
      const uploadPromises = Array.from(files).map(async (file) => {
        const formData = new FormData();
        formData.append("file", file);
        return fetchAPI(`/api/projects/${currentProjectId}/files`, {
          method: 'POST',
          body: formData
        });
      });
      await Promise.all(uploadPromises);
      await handleSync();
    } catch (error: any) {
      alert(`❌ 数据中心上传失败: ${error.message}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const fileTree = useMemo(() => {
    const root: any = {};
    projectFiles.forEach(file => {
      const filePath = (file as any).path || file.filename;
      const parts = filePath.split('/');
      let currentLevel = root;

      parts.forEach((part: string, idx: number) => {
        if (!currentLevel[part]) {
          currentLevel[part] = {
            name: part,
            path: parts.slice(0, idx + 1).join('/'),
            type: idx === parts.length - 1 ? 'file' : 'folder',
            children: {},
            fileData: idx === parts.length - 1 ? file : null
          };
        }
        currentLevel = currentLevel[part].children;
      });
    });
    return root;
  }, [projectFiles]);

  if (!isDataCenterOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={closeAllOverlays} />

      <div className="relative w-[600px] h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">

        <div className="h-16 shrink-0 border-b border-neutral-800 px-6 flex items-center justify-between bg-neutral-900/40">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/20 border border-purple-500/30 rounded-lg text-purple-400 shadow-[0_0_15px_rgba(168,85,247,0.15)]">
              <HardDrive size={18} strokeWidth={2.5} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-neutral-200 tracking-wide">全景数据中心</h2>
              <p className="text-[10px] text-neutral-500 font-mono mt-0.5">Project_{currentProjectId?.split('_')[1]?.substring(0,6) || currentProjectId} • 物理层直连</p>
            </div>
          </div>
          <button onClick={closeAllOverlays} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="p-4 border-b border-neutral-800 flex items-center gap-3 bg-neutral-900/20">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
            <input
              type="text"
              placeholder="在项目中搜索文件..."
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-sm text-neutral-300 outline-none focus:border-purple-500/50 transition-all placeholder:text-neutral-600"
            />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <input type="file" multiple ref={fileInputRef} onChange={handleFileUpload} className="hidden" />
            <button onClick={() => fileInputRef.current?.click()} disabled={isUploading || isSyncing} className="flex items-center gap-1.5 px-3 py-2 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm rounded-lg border border-neutral-700 transition-all">
              {isUploading ? <Loader2 size={16} className="animate-spin text-purple-400" /> : <UploadCloud size={16} className="text-purple-400" />}
              <span>上传</span>
            </button>
            <button onClick={handleSync} disabled={isSyncing || isUploading} className="flex items-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg shadow-lg shadow-purple-500/20 transition-all group">
              <RefreshCw size={16} className={isSyncing ? "animate-spin" : "group-hover:rotate-180 transition-transform duration-500"} />
              <span>物理同步</span>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
          {Object.keys(fileTree).length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-neutral-600 gap-3">
              <FolderOpen size={40} className="opacity-20" />
              <p className="text-sm">项目目录为空</p>
            </div>
          ) : (
            <div className="space-y-1">
              {Object.values(fileTree).map((node: any) => (
                <TreeNode
                  key={node.path} node={node} expandedFolders={expandedFolders}
                  toggleExpand={toggleExpand} onDelete={handleDeleteNode} onDownload={handleDownloadNode}
                  onPreview={handlePreviewNode}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 绝美沉浸式文件预览弹窗 */}
      {previewPath && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 md:p-12 animate-in fade-in duration-200">
          <div className="bg-[#1a1a1c] border border-neutral-800 rounded-2xl w-full max-w-5xl h-full flex flex-col shadow-2xl overflow-hidden relative animate-in zoom-in-95 duration-200">

            {/* Header */}
            <div className="h-14 shrink-0 border-b border-neutral-800 px-6 flex items-center justify-between bg-neutral-900">
              <div className="flex items-center gap-3">
                <Eye size={18} className="text-emerald-400"/>
                <h3 className="text-white font-medium text-sm tracking-wide truncate max-w-lg">{previewPath}</h3>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => handleDownloadNode(previewPath)} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 text-xs font-medium rounded-lg transition-colors border border-blue-500/20">
                  <Download size={14} /> 保存到本地
                </button>
                <div className="w-px h-4 bg-neutral-800 mx-1"></div>
                <button onClick={closePreview} className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors">
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-auto p-6 flex items-start justify-center bg-[#121212] relative">
              {isPreviewLoading ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-neutral-500">
                  <Loader2 size={32} className="animate-spin text-emerald-500" />
                  <span className="text-sm tracking-widest">安全加载中...</span>
                </div>
              ) : previewType === 'image' && previewContent ? (
                <img src={previewContent} alt="Preview" className="max-w-full max-h-full object-contain rounded drop-shadow-2xl" />
              ) : previewType === 'pdf' && previewContent ? (
                <iframe src={previewContent} className="w-full h-full rounded-xl border border-neutral-800 bg-white" title="PDF Preview" />
              ) : previewType === 'text' && previewContent ? (
                <div className="w-full h-full bg-[#1e1e1e] rounded-xl border border-neutral-800 p-4 overflow-auto custom-scrollbar">
                  <pre className="text-[13px] leading-relaxed text-neutral-300 font-mono whitespace-pre-wrap">
                    {previewContent}
                  </pre>
                </div>
              ) : null}
            </div>

          </div>
        </div>
      )}

    </div>
  );
}
