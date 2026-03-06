"use client";

import React, { useState, useMemo } from 'react';
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { X, HardDrive, FolderOpen, Folder, FileText, Search, ChevronRight, ChevronDown, Table2, Image as ImageIcon } from "lucide-react";

const getFileIcon = (filename: string) => {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tsv') || lower.endsWith('.csv') || lower.endsWith('.txt')) {
    return <Table2 size={16} className="text-blue-400" />;
  }
  if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.pdf')) {
    return <ImageIcon size={16} className="text-pink-400" />;
  }
  return <FileText size={16} className="text-neutral-400" />;
};

const TreeNode = ({ node, expandedFolders, toggleExpand }: any) => {
  const isFolder = node.type === 'folder';
  const isExpanded = expandedFolders.has(node.path);

  return (
    <div className="flex flex-col">
      <div
        className={`flex items-center gap-2 px-2 py-1.5 hover:bg-neutral-800 rounded-lg cursor-pointer group transition-colors ${!isFolder ? 'ml-6' : ''}`}
        onClick={() => isFolder ? toggleExpand(node.path) : null}
      >
        {isFolder && (
          <span className="text-neutral-500 group-hover:text-neutral-300 transition-colors">
            {isExpanded ? <ChevronDown size={15} strokeWidth={2.5} /> : <ChevronRight size={15} strokeWidth={2.5} />}
          </span>
        )}
        
        {isFolder ? (
          isExpanded ? <FolderOpen size={16} className="text-purple-400" /> : <Folder size={16} className="text-purple-400" />
        ) : (
          getFileIcon(node.name)
        )}
        
        <span className={`text-sm tracking-wide ${isFolder ? 'text-neutral-200 font-semibold' : 'text-neutral-400 group-hover:text-neutral-200'}`}>
          {node.name}
        </span>

        {!isFolder && node.fileData?.file_size && (
          <span className="ml-auto text-[10px] text-neutral-600 font-mono bg-neutral-900 px-1.5 py-0.5 rounded border border-neutral-800">
            {(node.fileData.file_size / 1024).toFixed(1)} KB
          </span>
        )}
      </div>

      {isFolder && isExpanded && (
        <div className="ml-4 border-l border-neutral-800 pl-2 mt-1 mb-2 flex flex-col gap-0.5">
          {Object.values(node.children).map((child: any) => (
            <TreeNode key={child.path} node={child} expandedFolders={expandedFolders} toggleExpand={toggleExpand} />
          ))}
        </div>
      )}
    </div>
  );
};

export function DataCenter() {
  const { isDataCenterOpen, closeAllOverlays } = useUIStore();
  const { currentProjectId, projectFiles } = useWorkspaceStore();
  
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['raw_data', 'results']));

  const toggleExpand = (path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
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
    <div className="absolute inset-y-0 left-20 right-0 z-40 flex">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={closeAllOverlays} />
      
      <div className="relative w-[600px] h-full bg-[#121212] border-r border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-left duration-300">
        
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

        <div className="p-4 border-b border-neutral-800 flex gap-4 bg-neutral-900/20">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
            <input 
              type="text" 
              placeholder="在项目中搜索文件..." 
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-sm text-neutral-300 outline-none focus:border-purple-500/50 focus:bg-neutral-900 transition-all placeholder:text-neutral-600"
            />
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
                />
              ))}
            </div>
          )}
        </div>
        
      </div>
    </div>
  );
}
