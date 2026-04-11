/**
 * 附件选择器组件
 *
 * 支持项目文件选择和本地文件上传
 * 包含树形文件选择界面
 */
"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import {
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  FileText,
  X,
  Loader2,
  Paperclip,
  Upload,
  CloudUpload,
  Check,
} from "lucide-react";
import { BASE_URL } from "@/lib/api";

// ==========================================
// 附件树节点接口定义
// ==========================================
interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children: Record<string, FileNode>;
  fileData: any;
}

// ==========================================
// 附件树节点组件
// ==========================================
interface AttachmentTreeNodeProps {
  node: FileNode;
  selectedPaths: Set<string>;
  setSelectedPaths: React.Dispatch<React.SetStateAction<Set<string>>>;
  expandedFolders: Set<string>;
  setExpandedFolders: React.Dispatch<React.SetStateAction<Set<string>>>;
}

const AttachmentTreeNode: React.FC<AttachmentTreeNodeProps> = ({
  node,
  selectedPaths,
  setSelectedPaths,
  expandedFolders,
  setExpandedFolders,
}) => {
  const isFolder = node.type === 'folder';
  const isExpanded = expandedFolders.has(node.path);
  const isSelected = selectedPaths.has(node.path);

  return (
    <div className="flex flex-col">
      <div
        className="flex items-center gap-2 px-2 py-1.5 hover:bg-neutral-800/60 rounded cursor-pointer group transition-colors"
        onClick={() => {
          // ✨ 修复：点击整行即可切换选中状态，大幅提升体验
          setSelectedPaths((prev: Set<string>) => {
            const next = new Set(prev);
            isSelected ? next.delete(node.path) : next.add(node.path);
            return next;
          });
        }}
      >
        {/* 复选框 */}
        <input
          type="checkbox"
          checked={isSelected}
          onChange={(e) => {
            // ✨ 复选框单独处理
            setSelectedPaths((prev: Set<string>) => {
              const next = new Set(prev);
              e.target.checked ? next.add(node.path) : next.delete(node.path);
              return next;
            });
          }}
          onClick={(e) => e.stopPropagation()} // 防止冒泡触发外层 div 的 onClick
          className="w-4 h-4 rounded border-neutral-600 bg-neutral-800 text-blue-500 focus:ring-blue-500/20 cursor-pointer"
        />

        {/* ✨ 修复：文件夹展开图标拆分为独立点击区域，防止和选中功能冲突 */}
        {isFolder && (
          <div
            className="p-0.5 hover:bg-neutral-700/80 rounded transition-colors"
            onClick={(e) => {
              e.stopPropagation(); // 仅触发展开/折叠，不选中
              setExpandedFolders(prev => {
                const next = new Set(prev);
                next.has(node.path) ? next.delete(node.path) : next.add(node.path);
                return next;
              });
            }}
          >
            {isExpanded ? <ChevronDown size={16} className="text-neutral-400 hover:text-white" /> : <ChevronRight size={16} className="text-neutral-400 hover:text-white" />}
          </div>
        )}

        {/* 图标 */}
        {isFolder ? (
          <Folder size={16} className="text-purple-400 shrink-0" />
        ) : (
          <FileText size={16} className="text-neutral-400 shrink-0" />
        )}

        {/* 名称 */}
        <span className="text-sm text-neutral-300 truncate flex-1 select-none">{node.name}</span>

        {/* 文件夹标签 */}
        {isFolder && (
          <span className="text-[10px] text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded shrink-0 select-none">文件夹</span>
        )}
      </div>

      {/* 子节点 */}
      {isFolder && isExpanded && node.children && Object.keys(node.children).length > 0 && (
        <div className="ml-6 border-l border-neutral-800 pl-2 mt-0.5 mb-1">
          {Object.values(node.children).map((child: FileNode) => (
            <AttachmentTreeNode
              key={child.path}
              node={child}
              selectedPaths={selectedPaths}
              setSelectedPaths={setSelectedPaths}
              expandedFolders={expandedFolders}
              setExpandedFolders={setExpandedFolders}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// ==========================================
// 附件选择器弹窗组件
// ==========================================
interface AttachmentPickerProps {
  isOpen: boolean;
  onClose: () => void;
  onAddFiles: (paths: string[]) => void;
  projectId: string | null;
}

export const AttachmentPicker: React.FC<AttachmentPickerProps> = ({
  isOpen,
  onClose,
  onAddFiles,
  projectId,
}) => {
  const [activeTab, setActiveTab] = useState<'project' | 'local'>('project');
  const [files, setFiles] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['raw_data', 'results']));

  const [localFiles, setLocalFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ [key: string]: number }>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 加载项目文件
  useEffect(() => {
    if (isOpen && projectId && activeTab === 'project') {
      setIsLoading(true);
      const token = localStorage.getItem('autonome_access_token');
      fetch(`${BASE_URL}/api/projects/${projectId}/files`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      })
        .then(res => res.json())
        .then(data => {
          // ✨ 增强对不同结构 API 的兼容性
          if (Array.isArray(data)) setFiles(data);
          else if (data?.data && Array.isArray(data.data)) setFiles(data.data);
          else if (data?.files && Array.isArray(data.files)) setFiles(data.files);
          else setFiles([]);
        })
        .catch(err => {
          console.error('Failed to load project files:', err);
          setFiles([]);
        })
        .finally(() => setIsLoading(false));
    }
  }, [isOpen, projectId, activeTab]);

  // 构建文件树
  const fileTree = useMemo(() => {
    if (!Array.isArray(files)) return {};

    const root: Record<string, FileNode> = {};
    files.forEach(file => {
      // ✨ 增强属性后备判断
      const filePath = (file as any).path || (file as any).filename || (file as any).name || '';
      if (!filePath) return;

      const fileType = (file as any).type || 'file';

      const parts = filePath.split('/').filter(Boolean);
      let current = root;
      parts.forEach((part: string, idx: number) => {
        if (!current[part]) {
          current[part] = {
            name: part,
            path: parts.slice(0, idx + 1).join('/'),
            type: idx === parts.length - 1 && fileType === 'file' ? 'file' : 'folder',
            children: {},
            fileData: idx === parts.length - 1 ? file : null
          };
        }
        current = current[part].children;
      });
    });
    return root;
  }, [files]);

  // 处理本地文件选择
  const handleLocalFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (selectedFiles) {
      setLocalFiles(prev => [...prev, ...Array.from(selectedFiles)]);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeLocalFile = (index: number) => {
    setLocalFiles(prev => prev.filter((_, i) => i !== index));
  };

  // 上传本地文件到项目
  const uploadLocalFiles = async () => {
    if (!projectId || localFiles.length === 0) return;

    setIsUploading(true);
    const token = localStorage.getItem('autonome_access_token');
    const uploadedPaths: string[] = [];

    try {
      for (const file of localFiles) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('target_path', 'raw_data');

        setUploadProgress(prev => ({ ...prev, [file.name]: 0 }));

        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${BASE_URL}/api/projects/${projectId}/files/upload`);

        if (token) {
          xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        }

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            setUploadProgress(prev => ({ ...prev, [file.name]: percent }));
          }
        };

        const response = await new Promise<any>((resolve, reject) => {
          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve(JSON.parse(xhr.responseText));
            } else {
              reject(new Error(`Upload failed: ${xhr.status}`));
            }
          };
          xhr.onerror = () => reject(new Error('Upload failed'));
          xhr.send(formData);
        });

        // ✨ 增强上传结果路径提取健壮性
        const path = response?.data?.path || response?.path || response?.url || response?.file_path;
        if (path) {
          uploadedPaths.push(path);
        }
      }

      if (uploadedPaths.length > 0) {
        onAddFiles(uploadedPaths);
      }

      setLocalFiles([]);
      setUploadProgress({});
      onClose();

    } catch (error) {
      console.error('Upload error:', error);
      alert('部分文件上传失败，请重试');
    } finally {
      setIsUploading(false);
    }
  };

  const handleConfirm = () => {
    onAddFiles(Array.from(selectedPaths));
    setSelectedPaths(new Set());
    onClose();
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-[550px] max-h-[70vh] bg-[#1a1a1c] border border-neutral-700 rounded-xl shadow-2xl flex flex-col">
        {/* Header */}
        <div className="shrink-0 border-b border-neutral-800 px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Paperclip size={18} className="text-blue-400" />
            <h3 className="text-sm font-semibold text-neutral-200">添加附件</h3>
          </div>
          <button onClick={onClose} className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg">
            <X size={16} />
          </button>
        </div>

        {/* Tab */}
        <div className="shrink-0 border-b border-neutral-800 px-4 pt-3">
          <div className="flex gap-1">
            <button
              onClick={() => setActiveTab('project')}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-lg border-b-2 transition-all ${
                activeTab === 'project'
                  ? 'text-blue-400 border-blue-400 bg-blue-500/10'
                  : 'text-neutral-400 border-transparent hover:text-neutral-200'
              }`}
            >
              <Folder size={14} />
              项目文件
            </button>
            <button
              onClick={() => setActiveTab('local')}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-lg border-b-2 transition-all ${
                activeTab === 'local'
                  ? 'text-blue-400 border-blue-400 bg-blue-500/10'
                  : 'text-neutral-400 border-transparent hover:text-neutral-200'
              }`}
            >
              <Upload size={14} />
              上传本地文件
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-3">
          {activeTab === 'project' ? (
            isLoading ? (
              <div className="flex items-center justify-center py-8 text-neutral-500">
                <Loader2 size={20} className="animate-spin mr-2" />
                加载中...
              </div>
            ) : Object.keys(fileTree).length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-neutral-500">
                <FolderOpen size={32} className="opacity-50 mb-2" />
                <span className="text-sm">项目目录为空</span>
              </div>
            ) : (
              Object.values(fileTree).map((node: FileNode) => (
                <AttachmentTreeNode
                  key={node.path}
                  node={node}
                  selectedPaths={selectedPaths}
                  setSelectedPaths={setSelectedPaths}
                  expandedFolders={expandedFolders}
                  setExpandedFolders={setExpandedFolders}
                />
              ))
            )
          ) : (
            <div className="flex flex-col gap-3">
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-neutral-700 rounded-xl p-6 flex flex-col items-center justify-center cursor-pointer hover:border-blue-500/50 hover:bg-blue-500/5 transition-all"
              >
                <CloudUpload size={32} className="text-neutral-500 mb-2" />
                <span className="text-sm text-neutral-400">点击选择文件或拖拽到此处</span>
                <span className="text-xs text-neutral-600 mt-1">支持所有文件类型，将上传到 raw_data 目录</span>
                <input type="file" multiple ref={fileInputRef} onChange={handleLocalFileSelect} className="hidden" />
              </div>

              {localFiles.length > 0 && (
                <div className="flex flex-col gap-2">
                  <span className="text-xs text-neutral-500 px-1">已选择 {localFiles.length} 个文件</span>
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    {localFiles.map((file, index) => (
                      <div key={index} className="flex items-center gap-2 px-3 py-2 bg-neutral-800/50 rounded-lg border border-neutral-700">
                        <FileText size={14} className="text-neutral-400 shrink-0" />
                        <span className="text-sm text-neutral-300 truncate flex-1">{file.name}</span>
                        <span className="text-xs text-neutral-500">{formatFileSize(file.size)}</span>
                        {uploadProgress[file.name] !== undefined && uploadProgress[file.name] < 100 && (
                          <div className="w-16 h-1.5 bg-neutral-700 rounded-full overflow-hidden">
                            <div className="h-full bg-blue-500 transition-all" style={{ width: `${uploadProgress[file.name]}%` }} />
                          </div>
                        )}
                        {uploadProgress[file.name] === 100 && (
                          <Check size={14} className="text-green-400" />
                        )}
                        {!isUploading && (
                          <button onClick={(e) => { e.stopPropagation(); removeLocalFile(index); }} className="p-1 text-neutral-500 hover:text-red-400 transition-colors">
                            <X size={12} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-neutral-800 px-4 py-3 flex items-center justify-between">
          <span className="text-xs text-neutral-500">
            {activeTab === 'project'
              ? `已选择 ${selectedPaths.size} 项（支持文件和文件夹）`
              : `已选择 ${localFiles.length} 个本地文件`
            }
          </span>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors">
              取消
            </button>
            {activeTab === 'project' ? (
              <button
                onClick={handleConfirm}
                disabled={selectedPaths.size === 0}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
              >
                添加
              </button>
            ) : (
              <button
                onClick={uploadLocalFiles}
                disabled={localFiles.length === 0 || isUploading}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
              >
                {isUploading ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    上传中...
                  </>
                ) : (
                  <>
                    <Upload size={14} />
                    上传并添加
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AttachmentPicker;