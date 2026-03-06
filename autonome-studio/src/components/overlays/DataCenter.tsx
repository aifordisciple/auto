"use client";

import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { X, HardDrive, FolderOpen, FileText, Search } from "lucide-react";

export function DataCenter() {
  const { isDataCenterOpen, closeAllOverlays } = useUIStore();
  const { currentProjectId, projectFiles } = useWorkspaceStore();

  if (!isDataCenterOpen) return null;

  return (
    <div className="absolute inset-y-0 left-20 right-0 z-40 flex">
      {/* Blur backdrop */}
      <div 
        className="absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity" 
        onClick={closeAllOverlays}
      />
      
      {/* Slide-in panel */}
      <div className="relative w-[600px] h-full bg-neutral-900 border-r border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-left duration-300">
        
        {/* Header */}
        <div className="h-16 shrink-0 border-b border-neutral-800 px-6 flex items-center justify-between bg-neutral-900/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/20 rounded-lg text-purple-400">
              <HardDrive size={20} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-neutral-200">全景数据中心</h2>
              <p className="text-[10px] text-neutral-500">Workspace ID: {currentProjectId} • 物理沙箱层</p>
            </div>
          </div>
          <button 
            onClick={closeAllOverlays}
            className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Toolbar */}
        <div className="p-4 border-b border-neutral-800 flex gap-4">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
            <input 
              type="text" 
              placeholder="搜索文件名..." 
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-sm text-neutral-200 outline-none focus:border-purple-500 transition-colors"
            />
          </div>
        </div>

        {/* File List */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-1">
            {projectFiles.map(f => {
              const filePath = (f as any).path || f.filename;
              return (
                <div key={filePath} className="flex items-center gap-3 p-3 hover:bg-neutral-800 rounded-lg cursor-pointer group transition-colors border border-transparent hover:border-neutral-700">
                  {filePath.startsWith('raw_data') ? <FolderOpen size={16} className="text-purple-400" /> : <FileText size={16} className="text-green-400" />}
                  <span className="text-sm text-neutral-300 font-mono tracking-tight">{filePath}</span>
                </div>
              );
            })}
          </div>
        </div>
        
      </div>
    </div>
  );
}
