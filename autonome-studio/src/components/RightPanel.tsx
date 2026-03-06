"use client";

import { useWorkspaceStore } from "../store/useWorkspaceStore";
import { useTaskStore } from "../store/useTaskStore";
import { useState, useRef, useEffect } from "react";
import { Check, Play, Settings2, Database, UploadCloud, Loader2, Trash2 } from "lucide-react";
import { fetchAPI, BASE_URL } from "../lib/api";

export function RightPanel() {
  const { 
    currentProjectId,
    projectFiles, setProjectFiles, addProjectFile,
    mountedFiles, toggleMountFile, 
    activeTool, toolParams, updateToolParam 
  } = useWorkspaceStore();
  
  const { setActiveTaskId } = useTaskStore();
  
  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ✨ 统一的文件列表拉取函数
  const fetchProjectFiles = () => {
    if (!currentProjectId) return;
    setIsLoadingFiles(true);
    const token = localStorage.getItem('autonome_access_token');
    fetch(`${BASE_URL}/api/projects/${currentProjectId}/files`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setProjectFiles(data.data || []);
        }
      })
      .catch(err => console.error("Failed to load files:", err))
      .finally(() => setIsLoadingFiles(false));
  };

  // 页面加载时自动拉取文件列表
  useEffect(() => {
    fetchProjectFiles();
  }, [currentProjectId]);

  // Handle file upload
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const token = localStorage.getItem('autonome_access_token');
      const response = await fetch(`${BASE_URL}/api/projects/${currentProjectId}/files`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      });
      const data = await response.json();
      
      if (data.status === 'success') {
        // ✨ 上传成功后刷新整个列表，确保同步
        fetchProjectFiles();
      }
    } catch (error) {
      console.error("Upload failed:", error);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // Handle file deletion
  const handleDeleteFile = async (fileId: number) => {
    if (!confirm("确定要彻底删除这个文件吗？")) return;
    
    try {
      const token = localStorage.getItem('autonome_access_token');
      const response = await fetch(`${BASE_URL}/api/projects/${currentProjectId}/files/${fileId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        // 删除成功后刷新列表
        fetchProjectFiles();
      }
    } catch (error) {
      console.error("Delete failed:", error);
    }
  };

  // Handle task execution
  const handleExecuteTask = async () => {
    if (!activeTool) return;
    
    setIsExecuting(true);
    try {
      const data = await fetchAPI('/api/tasks/submit', {
        method: 'POST',
        body: JSON.stringify({
          tool_id: activeTool.id,
          project_id: currentProjectId,
          parameters: toolParams
        })
      });
      
      if (data.status === 'success' && data.data?.task_id) {
        setActiveTaskId(data.data.task_id);
      }
    } catch (error) {
      console.error("Task execution failed:", error);
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="h-full flex flex-col w-full bg-neutral-900">
      {/* ================= 上半部：DATA CENTER ================= */}
      <div className="flex-1 border-b border-neutral-800 flex flex-col min-h-0">
        <div className="h-10 shrink-0 flex items-center justify-between px-4 bg-neutral-900 border-b border-neutral-800 text-xs font-semibold text-neutral-500 tracking-wider">
          <div className="flex items-center gap-2">
            <Database size={14} /> 
            DATA CENTER
            {isLoadingFiles && <Loader2 size={12} className="animate-spin ml-1" />}
          </div>
          
          {/* Upload button */}
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileUpload} 
            className="hidden" 
          />
          <button 
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="flex items-center gap-1 text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-50"
          >
            {isUploading ? <Loader2 size={14} className="animate-spin" /> : <UploadCloud size={14} />}
            <span>{isUploading ? '上传中...' : '上传数据'}</span>
          </button>
        </div>
        
        <div className="p-4 flex-1 overflow-y-auto">
          <p className="mb-3 text-xs text-neutral-500 font-medium">可用物料 (点击 [+] 挂载给 AI)</p>
          
          {projectFiles.length === 0 && !isLoadingFiles ? (
            <div className="text-center text-neutral-600 text-xs py-10 border border-dashed border-neutral-700 rounded-lg">
              当前沙箱空空如也<br/>点击右上角上传 FASTQ/CSV
            </div>
          ) : (
            <ul className="space-y-2">
              {projectFiles.map(fileObj => {
                // ✨ 兼容新后端的 relative_path 字段，如果没有则回退到 filename
                const filePath = (fileObj as any).path || fileObj.filename; 
                // 获取不带文件夹的纯文件名
                const baseName = filePath.split('/').pop();
                // 获取所在的文件夹名称
                const folder = filePath.includes('/') ? filePath.split('/')[0] : '';
                
                const isMounted = mountedFiles.includes(filePath);
                const sizeMB = (fileObj.file_size / (1024 * 1024)).toFixed(2);
                
                return (
                  <li 
                    key={fileObj.id || filePath}
                    className={`group relative flex items-center justify-between p-2.5 rounded-lg border text-sm transition-all duration-300 cursor-pointer overflow-hidden ${
                      isMounted 
                        ? "bg-blue-900/10 border-blue-500/40 text-blue-100 shadow-[0_0_15px_rgba(59,130,246,0.15)] transform scale-[1.02]" 
                        : "bg-neutral-900 border-neutral-800 text-neutral-400 hover:bg-neutral-800/80 hover:border-neutral-600 hover:text-neutral-200"
                    }`}
                    onClick={() => toggleMountFile(filePath)}
                  >
                    {/* 左侧的霓虹指示条 */}
                    <div className={`absolute left-0 top-0 bottom-0 w-1 transition-all duration-300 ${
                      isMounted ? "bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.8)]" : "bg-neutral-600 opacity-0 group-hover:opacity-100"
                    }`}></div>

                    <div className="flex items-center gap-3 pl-2 overflow-hidden z-10 relative">
                      <button className={`w-4 h-4 rounded-sm flex items-center justify-center shrink-0 border transition-all duration-300 ${
                        isMounted ? "bg-blue-500 border-blue-400 text-white shadow-lg" : "border-neutral-600 bg-neutral-950 group-hover:border-neutral-400"
                      }`}>
                        {isMounted && <Check size={12} strokeWidth={4} />}
                      </button>
                      <span className="truncate font-medium tracking-wide flex items-center gap-1.5" title={filePath}>
                        {/* ✨ 美化显示：如果在特定目录下，加一个小标签 */}
                        {folder === 'raw_data' && <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded">RAW</span>}
                        {folder === 'results' && <span className="text-[10px] px-1.5 py-0.5 bg-green-500/20 text-green-400 rounded">OUT</span>}
                        {baseName}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-neutral-500 shrink-0 z-10 relative bg-neutral-950 px-2 py-1 rounded-md border border-neutral-800 group-hover:border-neutral-600">{sizeMB} MB</span>
                      {/* Delete button - only visible on hover */}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteFile(fileObj.id); }}
                        className="opacity-0 group-hover:opacity-100 p-1.5 text-neutral-500 hover:text-red-400 hover:bg-red-500/10 rounded transition-all"
                        title="删除文件"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {/* ================= 下半部：DYNAMIC TOOLBOX ================= */}
      <div className="h-[55%] flex flex-col bg-transparent">
        <div className="h-10 shrink-0 flex items-center px-4 border-t border-neutral-800/60 text-xs font-semibold text-neutral-500 tracking-wider gap-2">
          <Settings2 size={14} /> DYNAMIC TOOLBOX
        </div>
        
        <div className="p-5 flex-1 overflow-y-auto">
          {!activeTool ? (
            <div className="h-full flex flex-col items-center justify-center text-neutral-600 text-sm text-center">
              <Settings2 size={32} className="mb-3 opacity-20" />
              等待 AI 决策或用户手动<br/>调起分析工具...
            </div>
          ) : (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="mb-4">
                <h3 className="text-white font-medium flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                  {activeTool.name}
                </h3>
                <p className="text-xs text-neutral-500 mt-1">{activeTool.description}</p>
              </div>

              {/* Dynamic form rendering based on Schema */}
              <div className="space-y-5">
                {Object.entries(activeTool.parameters).map(([key, param]) => (
                  <div key={key} className="space-y-2">
                    <label className="text-xs text-neutral-400 font-medium flex justify-between">
                      <span>{param.label}</span>
                      {param.type === 'number' && <span className="text-blue-400">{toolParams[key]}</span>}
                    </label>
                    
                    {/* Number slider */}
                    {param.type === 'number' && (
                      <input 
                        type="range" 
                        min={param.min} 
                        max={param.max}
                        step={param.step || 1}
                        value={toolParams[key]}
                        onChange={(e) => updateToolParam(key, Number(e.target.value))}
                        className="w-full accent-blue-500 h-1 bg-neutral-800 rounded-lg appearance-none cursor-pointer"
                      />
                    )}

                    {/* Boolean toggle */}
                    {param.type === 'boolean' && (
                      <button 
                        onClick={() => updateToolParam(key, !toolParams[key])}
                        className={`w-11 h-6 rounded-full relative transition-colors ${toolParams[key] ? 'bg-blue-600' : 'bg-neutral-700'}`}
                      >
                        <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${toolParams[key] ? 'left-6' : 'left-1'}`} />
                      </button>
                    )}

                    {/* Select dropdown */}
                    {param.type === 'select' && param.options && (
                      <select 
                        value={toolParams[key]}
                        onChange={(e) => updateToolParam(key, e.target.value)}
                        className="w-full bg-neutral-900 border border-neutral-700 text-white text-sm rounded focus:ring-blue-500 focus:border-blue-500 block p-2 outline-none"
                      >
                        {param.options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                      </select>
                    )}
                  </div>
                ))}
              </div>

              {/* ✨ 核按钮：多层发光效果 */}
              <div className="mt-6 relative group">
                {/* 底层光晕 */}
                <div className="absolute -inset-0.5 bg-gradient-to-r from-blue-500 to-purple-600 rounded-lg blur opacity-30 group-hover:opacity-100 transition duration-500 group-hover:duration-200 animate-pulse"></div>
                
                <button 
                  onClick={handleExecuteTask}
                  disabled={isExecuting}
                  className="relative w-full flex items-center justify-center gap-2 bg-neutral-950 hover:bg-black disabled:bg-neutral-900 disabled:text-neutral-500 text-blue-400 font-bold p-3 rounded-lg text-sm transition-all border border-blue-500/30 hover:border-blue-400 overflow-hidden"
                >
                  {/* 扫光动画 */}
                  <div className="absolute inset-0 -translate-x-full group-hover:animate-shimmer bg-gradient-to-r from-transparent via-blue-500/10 to-transparent"></div>
                  
                  {isExecuting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} fill="currentColor" />}
                  <span className="tracking-widest">{isExecuting ? '执行中...' : 'EXECUTE TASK'}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
