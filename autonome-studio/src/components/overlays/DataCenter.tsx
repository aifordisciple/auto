"use client";

import React, { useState, useMemo, useRef } from 'react';
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { X, HardDrive, FolderOpen, Folder, FileText, Search, ChevronRight, ChevronDown, Table2, Image as ImageIcon, Trash2, Download, RefreshCw, UploadCloud, Loader2 } from "lucide-react";
import { fetchAPI, BASE_URL } from "@/lib/api";

const getFileIcon = (filename: string) => {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tsv') || lower.endsWith('.csv') || lower.endsWith('.txt')) {
    return <Table2 size={16} className="text-blue-400 shrink-0" />;
  }
  if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.pdf')) {
    return <ImageIcon size={16} className="text-pink-400 shrink-0" />;
  }
  return <FileText size={16} className="text-neutral-400 shrink-0" />;
};

const TreeNode = ({ node, expandedFolders, toggleExpand, onDelete, onDownload }: any) => {
  const isFolder = node.type === 'folder';
  const isExpanded = expandedFolders.has(node.path);
  const isProtectedRoot = isFolder && (node.path === 'raw_data' || node.path === 'results');

  return (
    <div className="flex flex-col">
      <div
        className={`flex items-center gap-2 px-2 py-1.5 hover:bg-neutral-800/80 rounded-lg cursor-pointer group transition-all ${!isFolder ? 'ml-6' : ''}`}
        onClick={() => isFolder ? toggleExpand(node.path) : null}
      >
        {isFolder && (
          <span className="text-neutral-500 group-hover:text-neutral-300 transition-colors shrink-0">
            {isExpanded ? <ChevronDown size={15} strokeWidth={2.5} /> : <ChevronRight size={15} strokeWidth={2.5} />}
          </span>
        )}
        
        {isFolder ? (
          isExpanded ? <FolderOpen size={16} className="text-purple-400 shrink-0" /> : <Folder size={16} className="text-purple-400 shrink-0" />
        ) : (
          getFileIcon(node.name)
        )}
        
        <span className={`text-sm tracking-wide truncate ${isFolder ? 'text-neutral-200 font-semibold' : 'text-neutral-400 group-hover:text-neutral-200'}`}>
          {node.name}
        </span>

        <div className="ml-auto flex items-center opacity-0 group-hover:opacity-100 transition-opacity gap-1 z-10 shrink-0">
          {!isFolder && (
            <button
              onClick={(e) => { e.stopPropagation(); onDownload(node.path); }}
              className="p-1.5 text-neutral-500 hover:text-blue-400 hover:bg-blue-500/10 rounded-md transition-all"
              title="下载文件 / 浏览器新标签页预览"
            >
              <Download size={14} />
            </button>
          )}

          {!isProtectedRoot && !isFolder && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(node.path); }}
              className="p-1.5 text-neutral-500 hover:text-red-400 hover:bg-red-500/10 rounded-md transition-all"
              title="彻底删除"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>

        {!isFolder && node.fileData?.file_size && (
          <span className="text-[10px] text-neutral-600 font-mono bg-neutral-900 px-1.5 py-0.5 rounded border border-neutral-800 group-hover:hidden shrink-0 ml-auto">
            {(node.fileData.file_size / 1024).toFixed(1)} KB
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
            />
          ))}
        </div>
      )}
    </div>
  );
};

export function DataCenter() {
  const { isDataCenterOpen, closeAllOverlays } = useUIStore();
  const { currentProjectId, projectFiles, fetchProjectFiles } = useWorkspaceStore();
  
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['raw_data', 'results']));

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const toggleExpand = (path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
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
      const token = localStorage.getItem('autonome_access_token');
      const uploadPromises = Array.from(files).map(async (file) => {
        const formData = new FormData();
        formData.append("file", file);
        return fetch(`/api/projects/${currentProjectId}/files`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: formData
        });
      });
      await Promise.all(uploadPromises);
      await handleSync();
    } catch (error) {
      console.error("Upload failed", error);
      alert("❌ 上传失败，请检查网络状态或文件大小限制。");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDeleteNode = async (filePath: string) => {
    if (!window.confirm(`⚠️ 危险操作\n\n确定要从物理磁盘彻底删除 \n${filePath} 吗？\n此操作不可逆！`)) return;
    
    try {
      const token = localStorage.getItem('autonome_access_token');
      await fetch(`${BASE_URL}/api/projects/${currentProjectId}/files/${filePath}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (currentProjectId) {
        fetchProjectFiles(currentProjectId);
      }
    } catch (e) {
      console.error("Failed to delete file:", e);
      alert("❌ 删除失败，可能文件正被系统占用或无权限。");
    }
  };

  const handleDownloadNode = (filePath: string) => {
    const token = localStorage.getItem('autonome_access_token');
    const downloadUrl = `${BASE_URL}/api/projects/${currentProjectId}/files/${filePath}/view?token=${token}`;
    window.open(downloadUrl, '_blank');
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
              <p className="text-[10px] text-neutral-500 font-mono mt-0.5">Project_{currentProjectId} • 物理层直连</p>
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
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-sm text-neutral-300 outline-none focus:border-purple-500/50 focus:bg-neutral-900 transition-all placeholder:text-neutral-600"
            />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <input 
              type="file" 
              multiple 
              ref={fileInputRef} 
              onChange={handleFileUpload} 
              className="hidden" 
            />
            
            <button 
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading || isSyncing}
              className="flex items-center gap-1.5 px-3 py-2 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm rounded-lg border border-neutral-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isUploading ? <Loader2 size={16} className="animate-spin text-purple-400" /> : <UploadCloud size={16} className="text-purple-400" />}
              <span>{isUploading ? '上传中...' : '上传'}</span>
            </button>

            <button 
              onClick={handleSync}
              disabled={isSyncing || isUploading}
              className="flex items-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg shadow-lg shadow-purple-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed group"
              title="从服务器底层重新扫描硬盘文件"
            >
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
                  key={node.path} 
                  node={node} 
                  expandedFolders={expandedFolders} 
                  toggleExpand={toggleExpand}
                  onDelete={handleDeleteNode}
                  onDownload={handleDownloadNode}
                />
              ))}
            </div>
          )}
        </div>
        
      </div>
    </div>
  );
}
