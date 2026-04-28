"use client";

import React, { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { X, HardDrive, FolderOpen, Folder, FileText, Search, ChevronRight, ChevronDown, Table2, Image as ImageIcon, Trash2, Download, RefreshCw, UploadCloud, Loader2, Lock, Eye, ListChecks, FolderPlus, Move, FolderInput, Pencil, MessageSquarePlus, Dna, Database, Save, Edit3 } from "lucide-react";
import { fetchAPI, BASE_URL, getToken } from "@/lib/api";
import { CreateFolderModal } from "./CreateFolderModal";
import { MoveFileModal } from "./MoveFileModal";
import { UploadManager } from "./UploadManager";
import { RenameModal } from "./RenameModal";
import { GenomePanel, DatabasePanel, GenomeFormModal, DatabaseFormModal, GenomeDetailDrawer, DatabaseDetailDrawer, ImportGenomeModal, TABS, TreeNode, AdhocHistory, formatBytes, formatDateTime } from "./DataCenter/index";
import { GenomeAsset, AnalysisDatabase } from '@/lib/api';

// ✨ 文件预览增强组件导入
import { TablePreview } from "@/components/chat/components/TablePreview";
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeRaw from 'rehype-raw';

// ✨ 动态导入 Monaco Editor，禁用 SSR
const MonacoEditor = dynamic(() => import('@monaco-editor/react').then(mod => mod.default), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full text-neutral-500 bg-neutral-900">
      <div className="animate-pulse">加载编辑器...</div>
    </div>
  )
});

// ✨ 导入类型
import type { TabType, FileNode } from "./DataCenter/index";

export function DataCenter() {
  const { isDataCenterOpen, closeAllOverlays, dataCenterHighlightPath, setDataCenterHighlightPath } = useUIStore();
  const { currentProjectId, projectFiles, fetchProjectFiles, setPendingChatAttachments } = useWorkspaceStore();

  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['raw_data', 'results', 'references']));
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  // 高亮节点 ref，用于即席分析结果联动 — 打开时自动滚动到输出目录
  const highlightedNodeRef = useRef<HTMLDivElement>(null);
  // 本地高亮路径状态：消费 store 中的 dataCenterHighlightPath 后保持在此处
  const [localHighlightPath, setLocalHighlightPath] = useState<string | null>(null);

  // 即席分析结果联动：当 DataCenter 打开且有高亮路径时，自动展开父级目录并滚动到目标
  useEffect(() => {
    if (isDataCenterOpen && dataCenterHighlightPath) {
      const targetPath = dataCenterHighlightPath;
      // 先设置本地高亮路径（用于渲染高亮样式）
      setLocalHighlightPath(targetPath);
      // 延迟执行以确保文件树已渲染
      const timer = setTimeout(() => {
        // 将高亮路径的各级父目录加入展开集合
        const parts = targetPath.split('/').filter(Boolean);
        const parents: string[] = [];
        for (let i = 0; i < parts.length; i++) {
          parents.push(parts.slice(0, i + 1).join('/'));
        }
        setExpandedFolders(prev => {
          const next = new Set(prev);
          parents.forEach(p => next.add(p));
          return next;
        });
        // 滚动到高亮节点
        if (highlightedNodeRef.current) {
          highlightedNodeRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        // 清除 store 中的高亮路径（单次消费）
        setDataCenterHighlightPath(null);
        // 3 秒后清除本地高亮样式
        setTimeout(() => setLocalHighlightPath(null), 3000);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [isDataCenterOpen, dataCenterHighlightPath, setDataCenterHighlightPath]);

  // ✨ Tab 状态
  const [activeTab, setActiveTab] = useState<TabType>('files');

  // ✨ 基因组/数据库相关状态
  const [genomeFormOpen, setGenomeFormOpen] = useState(false);
  const [genomeImportOpen, setGenomeImportOpen] = useState(false);
  const [databaseFormOpen, setDatabaseFormOpen] = useState(false);
  const [editingGenome, setEditingGenome] = useState<GenomeAsset | null>(null);
  const [editingDatabase, setEditingDatabase] = useState<AnalysisDatabase | null>(null);
  const [viewingGenome, setViewingGenome] = useState<GenomeAsset | null>(null);
  const [viewingDatabase, setViewingDatabase] = useState<AnalysisDatabase | null>(null);

  // ✨ 上传目标路径
  const [uploadTargetPath, setUploadTargetPath] = useState<string>('raw_data');
  const [showUploadTargetSelector, setShowUploadTargetSelector] = useState(false);

  // ✨ 上传管理器状态
  const [uploadManagerState, setUploadManagerState] = useState<{
    isOpen: boolean;
    files: File[];
  }>({ isOpen: false, files: [] });

  // ✨ 数据中心打开时自动获取文件
  useEffect(() => {
    if (isDataCenterOpen && currentProjectId) {
      fetchProjectFiles(currentProjectId);
    }
  }, [isDataCenterOpen, currentProjectId, fetchProjectFiles]);

  // ✨ 批量模式状态
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());

  // ✨ 右键菜单状态
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    node: any;
  } | null>(null);

  // ✨ 模态框状态
  const [createFolderModal, setCreateFolderModal] = useState<{
    isOpen: boolean;
    parentPath: string;
  }>({ isOpen: false, parentPath: '' });

  const [moveFileModal, setMoveFileModal] = useState<{
    isOpen: boolean;
    sourcePath: string;
    sourceName: string;
    isFolder: boolean;
  }>({ isOpen: false, sourcePath: '', sourceName: '', isFolder: false });

  // ✨ 重命名模态框状态
  const [renameModal, setRenameModal] = useState<{
    isOpen: boolean;
    sourcePath: string;
    sourceName: string;
    isFolder: boolean;
  }>({ isOpen: false, sourcePath: '', sourceName: '', isFolder: false });

  // ✨ 处理右键菜单
  const handleContextMenu = useCallback((e: React.MouseEvent | { preventDefault: () => void; stopPropagation: () => void }, node: any) => {
    // 如果是通过按钮触发的假事件，直接处理
    if ('_action' in node) {
      const action = node._action;
      const actualNode = { ...node };
      delete actualNode._action;

      if (action === 'create_folder') {
        setCreateFolderModal({ isOpen: true, parentPath: actualNode.path });
      } else if (action === 'move') {
        setMoveFileModal({
          isOpen: true,
          sourcePath: actualNode.path,
          sourceName: actualNode.name,
          isFolder: actualNode.type === 'folder'
        });
      } else if (action === 'rename') {
        setRenameModal({
          isOpen: true,
          sourcePath: actualNode.path,
          sourceName: actualNode.name,
          isFolder: actualNode.type === 'folder'
        });
      }
      return;
    }

    // 真实的右键菜单事件
    const mouseEvent = e as React.MouseEvent;
    setContextMenu({
      x: mouseEvent.clientX || 0,
      y: mouseEvent.clientY || 0,
      node: node
    });
  }, []);

  // ✨ 关闭右键菜单
  const closeContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  // ✨ 点击外部关闭右键菜单
  React.useEffect(() => {
    const handleClick = () => closeContextMenu();
    window.addEventListener('click', handleClick);
    return () => window.removeEventListener('click', handleClick);
  }, [closeContextMenu]);

  // ✨ 切换文件选中状态
  const toggleSelection = (path: string) => {
    setSelectedPaths(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  // ✨ 核心逻辑：执行批量删除
  const handleBatchDelete = async () => {
    if (selectedPaths.size === 0) return;
    if (!window.confirm(`⚠️ 高危操作确认\n\n您确定要彻底删除选中的 ${selectedPaths.size} 个项目吗？\n如果包含文件夹，将递归清空其内部所有内容！此操作不可逆。`)) return;

    setIsSyncing(true); // 借用同步状态显示 Loading
    try {
      // 并发发送多条删除请求
      const promises = Array.from(selectedPaths).map(path =>
        fetchAPI(`/api/projects/${currentProjectId}/files/${path}`, { method: 'DELETE' })
      );

      await Promise.all(promises);

      // 清理状态并刷新
      setSelectedPaths(new Set());
      setIsBatchMode(false);
      if (currentProjectId) {
        await fetchProjectFiles(currentProjectId);
      }
    } catch (e) {
      alert("❌ 批量删除执行中断，部分文件可能删除失败。");
    } finally {
      setIsSyncing(false);
    }
  };

  // ✨ 批量添加到聊天：发送给 AI（支持文件和文件夹）
  const handleBatchAddToChat = () => {
    if (selectedPaths.size === 0) return;

    // 直接使用选中的路径（文件和文件夹都支持）
    const selectedPathsArray = Array.from(selectedPaths);

    if (selectedPathsArray.length === 0) {
      alert("请选择文件或文件夹");
      return;
    }

    setPendingChatAttachments(selectedPathsArray);
    closeAllOverlays();

    // 聚焦聊天输入框
    setTimeout(() => {
      document.getElementById("chat-input-box")?.focus();
    }, 100);
  };

  // ✨ 预览弹窗状态 - 扩展类型支持表格/Markdown/代码高亮
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<'image' | 'text' | 'pdf' | 'html' | 'table' | 'markdown' | 'code' | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  // ✨ 新增：代码语言和 Markdown 渲染模式
  const [previewLanguage, setPreviewLanguage] = useState<string>('text');
  const [mdViewMode, setMdViewMode] = useState<'render' | 'source'>('render');
  // ✨ 新增：编辑模式
  const [editMode, setEditMode] = useState<'preview' | 'edit'>('preview');
  const [editContent, setEditContent] = useState<string>('');
  const [isSaving, setIsSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

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
      const token = getToken();
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

  // ✨ 根据文件扩展名判断预览类型和语言
  const getPreviewTypeInfo = (filePath: string): { type: 'table' | 'markdown' | 'code' | 'text'; language?: string } => {
    const ext = filePath.split('.').pop()?.toLowerCase() || '';

    // TSV/CSV -> 表格预览
    if (['tsv', 'csv'].includes(ext)) {
      return { type: 'table' };
    }

    // Markdown -> MD预览（支持切换）
    if (['md', 'markdown'].includes(ext)) {
      return { type: 'markdown' };
    }

    // 代码文件 -> 语法高亮
    const codeLanguageMap: Record<string, string> = {
      'py': 'python',
      'r': 'r',
      'js': 'javascript',
      'ts': 'typescript',
      'tsx': 'tsx',
      'jsx': 'jsx',
      'json': 'json',
      'yaml': 'yaml',
      'yml': 'yaml',
      'sh': 'bash',
      'bash': 'bash',
      'zsh': 'bash',
      'sql': 'sql',
      'html': 'html',
      'css': 'css',
      'scss': 'scss',
      'java': 'java',
      'c': 'c',
      'cpp': 'cpp',
      'h': 'c',
      'hpp': 'cpp',
      'go': 'go',
      'rs': 'rust',
      'swift': 'swift',
      'kt': 'kotlin',
      'scala': 'scala',
      'rb': 'ruby',
      'php': 'php',
      'lua': 'lua',
      'pl': 'perl',
      'pm': 'perl',
      'nf': 'groovy',  // Nextflow 使用 Groovy 语法
      'config': 'ini',
      'ini': 'ini',
      'toml': 'toml',
      'xml': 'xml',
      'log': 'text',
      'txt': 'text',
    };

    if (codeLanguageMap[ext]) {
      return { type: 'code', language: codeLanguageMap[ext] };
    }

    // 默认文本
    return { type: 'text' };
  };

  // ✨ 核心逻辑：安全拉取文件并在内存中渲染（增强版）
  const handlePreviewNode = async (filePath: string) => {
    if (!currentProjectId) return;
    const ext = filePath.split('.').pop()?.toLowerCase() || '';
    const isImage = ['png', 'jpg', 'jpeg', 'svg', 'gif'].includes(ext);
    const isPdf = ext === 'pdf';
    const isHtml = ['html', 'htm'].includes(ext);

    // ✨ 使用新的类型判断函数
    const typeInfo = getPreviewTypeInfo(filePath);
    const isTextLike = ['table', 'markdown', 'code', 'text'].includes(typeInfo.type);

    if (!isImage && !isPdf && !isHtml && !isTextLike) {
      alert("💡 当前文件格式暂不支持内存预览，请点击右侧【下载】按钮直接下载。");
      return;
    }

    setPreviewPath(filePath);
    setIsPreviewLoading(true);
    setPreviewContent(null);
    // ✨ 设置语言和 MD 模式
    setPreviewLanguage(typeInfo.language || 'text');
    if (typeInfo.type === 'markdown') {
      setMdViewMode('render');
    }

    try {
      const token = getToken();
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
      } else if (isHtml) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setPreviewContent(url);
        setPreviewType('html');
      } else {
        // ✨ 所有文本类型（包括 table/markdown/code）
        const text = await res.text();
        const MAX_LENGTH = 100000;
        setPreviewContent(text.length > MAX_LENGTH ? text.substring(0, MAX_LENGTH) + '\n\n... [⚠️ 数据表过大，内存预览已截断，请下载查看完整全貌]' : text);
        setPreviewType(typeInfo.type);
      }
    } catch (e) {
      alert("❌ 预览加载失败，可能是网络问题或权限不足。");
      setPreviewPath(null);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const closePreview = () => {
    // 检查是否有未保存的更改
    if (hasUnsavedChanges && editMode === 'edit') {
      if (!window.confirm("有未保存的更改，确定要关闭吗？")) {
        return;
      }
    }
    if ((previewType === 'image' || previewType === 'pdf' || previewType === 'html') && previewContent) {
      URL.revokeObjectURL(previewContent);
    }
    setPreviewPath(null);
    setPreviewContent(null);
    // ✨ 重置编辑模式状态
    setEditMode('preview');
    setEditContent('');
    setHasUnsavedChanges(false);
  };

  // ✨ 保存文件内容
  const handleSaveFile = async () => {
    if (!currentProjectId || !previewPath) return;

    setIsSaving(true);
    try {
      await fetchAPI(`/api/projects/${currentProjectId}/files/${previewPath}/content`, {
        method: 'PUT',
        body: JSON.stringify({ content: editContent })
      });

      // 更新预览内容
      setPreviewContent(editContent);
      setHasUnsavedChanges(false);
      alert('✅ 文件保存成功');
    } catch (e: any) {
      alert(`❌ 保存失败: ${e.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  // ✨ 切换到编辑模式
  const enterEditMode = () => {
    if (previewContent) {
      setEditContent(previewContent);
      setEditMode('edit');
      setHasUnsavedChanges(false);
    }
  };

  // ✨ 退出编辑模式
  const exitEditMode = () => {
    if (hasUnsavedChanges) {
      if (!window.confirm("有未保存的更改，确定要放弃吗？")) {
        return;
      }
    }
    setEditMode('preview');
    setHasUnsavedChanges(false);
  };

  const handleSync = async () => {
    if (!currentProjectId) return;
    setIsSyncing(true);
    await fetchProjectFiles(currentProjectId);
    setTimeout(() => setIsSyncing(false), 600);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // 打开上传管理器
    setUploadManagerState({
      isOpen: true,
      files: Array.from(files)
    });

    // 清空input以便可以再次选择相同文件
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleUploadComplete = () => {
    setUploadManagerState({ isOpen: false, files: [] });
    handleSync();
  };

  // ✨ 获取可上传的文件夹列表（raw_data 和 results 下的所有文件夹）
  const uploadableFolders = useMemo(() => {
    const folders: { path: string; name: string; depth: number }[] = [
      { path: 'raw_data', name: 'raw_data', depth: 0 },
      { path: 'results', name: 'results', depth: 0 }
    ];

    projectFiles.forEach(item => {
      const itemPath = (item as any).path;
      const itemType = (item as any).type;

      // 只添加 raw_data 和 results 下的文件夹
      if (itemType === 'folder' &&
          (itemPath.startsWith('raw_data/') || itemPath.startsWith('results/'))) {
        const parts = itemPath.split('/');
        folders.push({
          path: itemPath,
          name: parts[parts.length - 1],
          depth: parts.length - 1
        });
      }
    });

    return folders;
  }, [projectFiles]);

  // ✨ 执行右键菜单操作
  const handleContextMenuAction = useCallback((action: string) => {
    if (!contextMenu?.node) return;

    const node = contextMenu.node;

    switch (action) {
      case 'create_folder':
        setCreateFolderModal({ isOpen: true, parentPath: node.path });
        break;
      case 'move':
        setMoveFileModal({
          isOpen: true,
          sourcePath: node.path,
          sourceName: node.name,
          isFolder: node.type === 'folder'
        });
        break;
      case 'rename':
        setRenameModal({
          isOpen: true,
          sourcePath: node.path,
          sourceName: node.name,
          isFolder: node.type === 'folder'
        });
        break;
      case 'delete':
        handleDeleteNode(node.path);
        break;
      case 'preview':
        handlePreviewNode(node.path);
        break;
      case 'download':
        handleDownloadNode(node.path);
        break;
    }

    closeContextMenu();
  }, [contextMenu, closeContextMenu]);

  const fileTree = useMemo(() => {
    const root: any = {};

    // 第一遍：创建所有目录节点（包括空目录）
    projectFiles.forEach(item => {
      const itemPath = (item as any).path || (item as any).filename;
      const itemType = (item as any).type || 'file';

      if (itemType === 'folder') {
        const parts = itemPath.split('/');
        let currentLevel = root;

        parts.forEach((part: string, idx: number) => {
          if (!currentLevel[part]) {
            currentLevel[part] = {
              name: part,
              path: parts.slice(0, idx + 1).join('/'),
              type: 'folder',
              children: {},
              fileData: null
            };
          }
          currentLevel = currentLevel[part].children;
        });
      }
    });

    // 第二遍：添加文件节点
    projectFiles.forEach(file => {
      const filePath = (file as any).path || file.filename;
      const fileType = (file as any).type || 'file';

      if (fileType === 'file') {
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
          } else if (idx === parts.length - 1) {
            // 更新已存在的节点信息（文件）
            currentLevel[part].fileData = file;
          }
          currentLevel = currentLevel[part].children;
        });
      }
    });

    return root;
  }, [projectFiles]);

  // ✨ 计算文件夹数量（用于显示提示）
  const folderCount = useMemo(() => {
    let count = 0;
    const findNodeByPath = (nodes: any, targetPath: string): any => {
      for (const key of Object.keys(nodes)) {
        const node = nodes[key];
        if (node.path === targetPath) return node;
        if (node.children) {
          const found = findNodeByPath(node.children, targetPath);
          if (found) return found;
        }
      }
      return null;
    };
    selectedPaths.forEach(path => {
      const node = findNodeByPath(fileTree, path);
      if (node && node.type === 'folder') count++;
    });
    return count;
  }, [selectedPaths, fileTree]);

  if (!isDataCenterOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={closeAllOverlays} />

      <div className="relative w-[900px] max-md:w-full max-md:fixed max-md:inset-0 h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">

        {/* ✨ 头部高度响应式 - 移动端紧凑 */}
        <div className="h-14 md:h-16 shrink-0 border-b border-neutral-800 px-3 md:px-6 flex items-center justify-between bg-neutral-900/40">
          <div className="flex items-center gap-2 md:gap-4 flex-1 min-w-0">
            <div className="flex items-center gap-2 md:gap-3 shrink-0">
              <div className="p-1.5 md:p-2 bg-purple-500/20 border border-purple-500/30 rounded-lg text-purple-400 shadow-[0_0_15px_rgba(168,85,247,0.15)]">
                <HardDrive size={16} strokeWidth={2.5} className="md:w-[18px] md:h-[18px]" />
              </div>
              <div className="hidden sm:block">
                <h2 className="text-sm font-bold text-neutral-200 tracking-wide">全景数据中心</h2>
                <p className="text-[10px] text-neutral-500 font-mono mt-0.5">项目数据 · 基因组 · 数据库</p>
              </div>
            </div>

            {/* ✨ Tab 切换 */}
            <div className="flex items-center bg-neutral-800/50 rounded-lg p-1 ml-1 md:ml-4 overflow-x-auto flex-1 md:flex-none">
              {TABS.map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1 md:gap-2 px-2 md:px-4 py-1.5 rounded-md text-xs font-medium transition-all ${
                      isActive
                        ? tab.color + ' shadow-md'
                        : 'text-neutral-400 hover:text-white'
                    }`}
                  >
                    {tab.icon}
                    <span className="hidden sm:inline">{tab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <button onClick={closeAllOverlays} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors shrink-0 ml-2">
            <X size={18} />
          </button>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {/* ✨ 项目数据 Tab */}
          {activeTab === 'files' && (
            <>
              {/* ✨ 工具栏 - 移动端 flex-wrap 自动换行，确保触摸友好 */}
              <div className="shrink-0 p-3 md:p-4 border-b border-neutral-800 flex flex-col md:flex-row items-stretch md:items-center gap-2 md:gap-3 bg-neutral-900/20">
                <div className="flex-1 relative">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                  <input
                    type="text"
                    placeholder="在项目中搜索文件..."
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-sm text-neutral-300 outline-none focus:border-purple-500/50 transition-all placeholder:text-neutral-600"
                  />
                </div>

                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  {/* ✨ 批量管理开关 */}
                  <button
                    onClick={() => { setIsBatchMode(!isBatchMode); setSelectedPaths(new Set()); }}
                    className={`flex items-center gap-1.5 px-3 py-2 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 text-sm rounded-lg border transition-all whitespace-nowrap ${isBatchMode ? 'bg-red-500/10 text-red-400 border-red-500/30' : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-200 border-neutral-700'}`}
                  >
                    <ListChecks size={16} />
                    <span className="hidden md:inline">{isBatchMode ? '退出批量' : '批量管理'}</span>
                    <span className="md:hidden">{isBatchMode ? '退出' : '批量'}</span>
                  </button>

                  {/* ✨ 上传目标选择器 */}
                  <div className="relative">
                    <button
                      onClick={() => setShowUploadTargetSelector(!showUploadTargetSelector)}
                      disabled={isSyncing || isBatchMode}
                      className="flex items-center gap-1.5 px-3 py-2 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm rounded-lg border border-neutral-700 transition-all disabled:opacity-50"
                    >
                      <Folder size={14} className="text-purple-400" />
                      <span className="max-w-[80px] md:max-w-[120px] truncate">{uploadTargetPath.split('/').pop()}</span>
                      <ChevronDown size={12} />
                    </button>

                    {showUploadTargetSelector && (
                      <div className="absolute top-full left-0 mt-1 bg-[#1a1a1c] border border-neutral-700 rounded-lg shadow-2xl py-1 min-w-[200px] max-h-64 overflow-y-auto z-50">
                        {uploadableFolders.map(folder => (
                          <button
                            key={folder.path}
                            onClick={() => {
                              setUploadTargetPath(folder.path);
                              setShowUploadTargetSelector(false);
                            }}
                            className={`w-full text-left px-3 py-2 text-sm hover:bg-neutral-800 transition-colors flex items-center gap-2 ${uploadTargetPath === folder.path ? 'text-purple-400 bg-purple-500/10' : 'text-neutral-300'}`}
                            style={{ paddingLeft: `${12 + folder.depth * 12}px` }}
                          >
                            <Folder size={14} className="shrink-0" />
                            <span className="truncate">{folder.name}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <input type="file" multiple ref={fileInputRef} onChange={handleFileSelect} className="hidden" />
                  <button onClick={() => fileInputRef.current?.click()} disabled={isSyncing || isBatchMode} className="flex items-center gap-1.5 px-3 py-2 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm rounded-lg border border-neutral-700 transition-all disabled:opacity-50">
                    <UploadCloud size={16} className="text-purple-400" />
                    <span className="hidden sm:inline">上传</span>
                  </button>
                  <button onClick={handleSync} disabled={isSyncing || isBatchMode} className="flex items-center gap-1.5 px-3 py-2 min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg shadow-lg shadow-purple-500/20 transition-all disabled:opacity-50 group">
                    <RefreshCw size={16} className={isSyncing ? "animate-spin" : "group-hover:rotate-180 transition-transform duration-500"} />
                    <span className="hidden sm:inline">物理同步</span>
                    <span className="sm:hidden">同步</span>
                  </button>
                </div>
              </div>

              {/* ✨ 内容区域 - 移动端紧凑 padding */}
              <div className="flex-1 overflow-y-auto p-3 md:p-4 custom-scrollbar">
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
                        isBatchMode={isBatchMode} selectedPaths={selectedPaths} toggleSelection={toggleSelection}
                        onContextMenu={handleContextMenu}
                        highlightedPath={localHighlightPath}
                        highlightedNodeRef={highlightedNodeRef}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* ✨ 批量操作执行栏 - 移动端垂直布局 */}
              {isBatchMode && (
                <div className="shrink-0 p-3 md:p-4 border-t border-neutral-800 bg-neutral-900/80 backdrop-blur-sm flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                  {/* 选择统计 */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm text-neutral-400">已选择 <strong className="text-red-400">{selectedPaths.size}</strong> 项</span>
                    {/* 显示文件夹数量提示 */}
                    {folderCount > 0 && (
                      <span className="text-xs text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded border border-blue-500/20">
                        含 {folderCount} 个文件夹
                      </span>
                    )}
                  </div>
                  {/* 操作按钮 - 移动端全宽 */}
                  <div className="flex items-center gap-2">
                    {/* 新增: 发送给 AI 按钮 */}
                    <button
                      onClick={handleBatchAddToChat}
                      disabled={selectedPaths.size === 0}
                      className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3 py-2 min-h-[44px] bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                      <MessageSquarePlus size={14} />
                      发送给 AI
                    </button>
                    {/* 现有: 删除按钮 */}
                    <button
                      onClick={handleBatchDelete}
                      disabled={selectedPaths.size === 0 || isSyncing}
                      className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3 py-2 min-h-[44px] bg-red-600/20 hover:bg-red-600/30 text-red-400 text-sm font-medium rounded-lg transition-colors"
                    >
                      {isSyncing ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                      删除
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* ✨ 参考基因组 Tab */}
          {activeTab === 'genomes' && (
            <GenomePanel
              onCreateNew={() => { setEditingGenome(null); setGenomeFormOpen(true); }}
              onEdit={(genome) => { setEditingGenome(genome); setGenomeFormOpen(true); }}
              onViewDetail={(genome) => setViewingGenome(genome)}
              onOpenImport={() => setGenomeImportOpen(true)}
            />
          )}

          {/* ✨ 分析数据库 Tab */}
          {activeTab === 'databases' && (
            <DatabasePanel
              onCreateNew={() => { setEditingDatabase(null); setDatabaseFormOpen(true); }}
              onEdit={(db) => { setEditingDatabase(db); setDatabaseFormOpen(true); }}
              onViewDetail={(db) => setViewingDatabase(db)}
            />
          )}

          {/* ✨ 即席分析历史 Tab */}
          {activeTab === 'history' && (
            <AdhocHistory
              projectId={currentProjectId || ''}
              onNavigateToOutput={(outputDir) => {
                // 构建完整路径：results/{outputDir}
                const fullPath = `results/${outputDir}`;
                setDataCenterHighlightPath(fullPath);
                // 切换到文件 Tab 以显示高亮
                setActiveTab('files');
              }}
            />
          )}
        </div>
      </div>

      {/* 绝美沉浸式文件预览弹窗 */}
      {previewPath && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 md:p-12 animate-in fade-in duration-200">
          <div className="bg-[#1a1a1c] border border-neutral-800 rounded-2xl w-full max-w-5xl h-full flex flex-col shadow-2xl overflow-hidden relative animate-in zoom-in-95 duration-200">

            {/* Header - 增加预览/编辑模式切换 */}
            <div className="h-14 shrink-0 border-b border-neutral-800 px-6 flex items-center justify-between bg-neutral-900">
              <div className="flex items-center gap-3">
                {editMode === 'edit' ? (
                  <Edit3 size={18} className="text-amber-400"/>
                ) : (
                  <Eye size={18} className="text-emerald-400"/>
                )}
                <h3 className="text-white font-medium text-sm tracking-wide truncate max-w-lg">
                  {previewPath}
                  {hasUnsavedChanges && <span className="text-amber-400 ml-2">●</span>}
                </h3>
              </div>
              <div className="flex items-center gap-2">
                {/* ✨ 文本类文件：预览/编辑模式切换 */}
                {['text', 'markdown', 'code', 'table'].includes(previewType || '') && (
                  <div className="flex items-center gap-1 bg-neutral-800 rounded-lg p-1">
                    <button
                      onClick={() => editMode === 'edit' ? exitEditMode() : null}
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                        editMode === 'preview'
                          ? 'bg-emerald-500 text-white shadow-md'
                          : 'text-neutral-400 hover:text-white'
                      }`}
                      disabled={editMode === 'preview'}
                    >
                      <Eye size={12} />
                      预览
                    </button>
                    <button
                      onClick={() => editMode === 'preview' ? enterEditMode() : null}
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                        editMode === 'edit'
                          ? 'bg-amber-500 text-white shadow-md'
                          : 'text-neutral-400 hover:text-white'
                      }`}
                      disabled={editMode === 'edit'}
                    >
                      <Edit3 size={12} />
                      编辑
                    </button>
                  </div>
                )}

                {/* ✨ Markdown 渲染/源码切换（仅在预览模式下显示） */}
                {previewType === 'markdown' && editMode === 'preview' && (
                  <div className="flex items-center gap-1 bg-neutral-800 rounded-lg p-1">
                    <button
                      onClick={() => setMdViewMode('render')}
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                        mdViewMode === 'render'
                          ? 'bg-purple-500 text-white shadow-md'
                          : 'text-neutral-400 hover:text-white'
                      }`}
                    >
                      <Eye size={12} />
                      渲染
                    </button>
                    <button
                      onClick={() => setMdViewMode('source')}
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                        mdViewMode === 'source'
                          ? 'bg-purple-500 text-white shadow-md'
                          : 'text-neutral-400 hover:text-white'
                      }`}
                    >
                      <FileText size={12} />
                      源码
                    </button>
                  </div>
                )}

                {/* ✨ 编辑模式：保存按钮 */}
                {editMode === 'edit' && (
                  <button
                    onClick={handleSaveFile}
                    disabled={isSaving || !hasUnsavedChanges}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors border ${
                      hasUnsavedChanges
                        ? 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 border-amber-500/30'
                        : 'bg-neutral-800 text-neutral-500 border-neutral-700 cursor-not-allowed'
                    }`}
                  >
                    {isSaving ? (
                      <>
                        <Loader2 size={14} className="animate-spin" />
                        保存中...
                      </>
                    ) : (
                      <>
                        <Save size={14} />
                        保存
                      </>
                    )}
                  </button>
                )}

                <button onClick={() => handleDownloadNode(previewPath)} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 text-xs font-medium rounded-lg transition-colors border border-blue-500/20">
                  <Download size={14} /> 下载
                </button>
                <div className="w-px h-4 bg-neutral-800 mx-1"></div>
                <button onClick={closePreview} className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors">
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Content Area - 增强渲染逻辑 */}
            <div className="flex-1 overflow-auto p-6 flex items-start justify-center bg-[#121212] relative">
              {isPreviewLoading ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-neutral-500">
                  <Loader2 size={32} className="animate-spin text-emerald-500" />
                  <span className="text-sm tracking-widest">安全加载中...</span>
                </div>
              // ✨ 编辑模式：Monaco 编辑器
              ) : editMode === 'edit' && editContent !== null ? (
                <div className="w-full h-full bg-[#1e1e1e] rounded-xl border border-neutral-800 overflow-hidden">
                  <MonacoEditor
                    height="100%"
                    language={
                      previewType === 'markdown' ? 'markdown' :
                      previewType === 'code' ? previewLanguage :
                      previewType === 'table' ? 'csv' : 'plaintext'
                    }
                    value={editContent}
                    onChange={(value) => {
                      setEditContent(value || '');
                      if (value !== previewContent) {
                        setHasUnsavedChanges(true);
                      } else {
                        setHasUnsavedChanges(false);
                      }
                    }}
                    theme="vs-dark"
                    options={{
                      minimap: { enabled: false },
                      fontSize: 13,
                      lineNumbers: 'on',
                      wordWrap: 'on',
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                      tabSize: 2,
                      readOnly: false,
                    }}
                  />
                </div>
              ) : previewType === 'image' && previewContent ? (
                <img src={previewContent} alt="Preview" className="max-w-full max-h-full object-contain rounded drop-shadow-2xl" />
              ) : previewType === 'pdf' && previewContent ? (
                <iframe src={previewContent} className="w-full h-full rounded-xl border border-neutral-800 bg-white" title="PDF Preview" />
              ) : previewType === 'html' && previewContent ? (
                <iframe src={previewContent} className="w-full h-full rounded-xl border border-neutral-800 bg-white" title="HTML Preview" sandbox="allow-scripts allow-same-origin" />
              // ✨ 新增：表格预览 (TSV/CSV)
              ) : previewType === 'table' && previewContent ? (
                <div className="w-full h-full bg-[#1e1e1e] rounded-xl border border-neutral-800 overflow-hidden">
                  <TablePreview data={previewContent} maxRows={100} />
                </div>
              // ✨ 新增：Markdown预览 (支持切换)
              ) : previewType === 'markdown' && previewContent ? (
                mdViewMode === 'render' ? (
                  <div className="w-full h-full bg-[#1e1e1e] rounded-xl border border-neutral-800 p-6 overflow-auto custom-scrollbar">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkBreaks]}
                      rehypePlugins={[rehypeRaw]}
                      components={{
                        // 代码块渲染
                        code({ className, children, ...props }) {
                          const match = /language-(\w+)/.exec(className || '');
                          if (!match) {
                            return (
                              <code className="bg-neutral-800 text-blue-400 px-1.5 py-0.5 rounded text-[0.875em] font-mono">
                                {children}
                              </code>
                            );
                          }
                          return (
                            <SyntaxHighlighter
                              style={vscDarkPlus}
                              language={match[1]}
                              PreTag="div"
                              customStyle={{
                                margin: 0,
                                padding: '1rem',
                                borderRadius: '0.5rem',
                                fontSize: '0.875rem',
                                backgroundColor: '#1e1e1e',
                              }}
                            >
                              {String(children).replace(/\n$/, '')}
                            </SyntaxHighlighter>
                          );
                        },
                        // 表格样式
                        table({ children }) {
                          return (
                            <div className="overflow-x-auto my-4">
                              <table className="min-w-full border-collapse">{children}</table>
                            </div>
                          );
                        },
                        th({ children }) {
                          return <th className="border border-neutral-700 px-3 py-2 bg-neutral-800 text-neutral-300">{children}</th>;
                        },
                        td({ children }) {
                          return <td className="border border-neutral-700 px-3 py-2 text-neutral-400">{children}</td>;
                        },
                      }}
                    >
                      {previewContent}
                    </ReactMarkdown>
                  </div>
                ) : (
                  // MD源码模式
                  <div className="w-full h-full bg-[#1e1e1e] rounded-xl border border-neutral-800 p-4 overflow-auto custom-scrollbar">
                    <pre className="text-[13px] leading-relaxed text-neutral-300 font-mono whitespace-pre-wrap">
                      {previewContent}
                    </pre>
                  </div>
                )
              // ✨ 新增：代码预览 (语法高亮)
              ) : previewType === 'code' && previewContent ? (
                <div className="w-full h-full bg-[#1e1e1e] rounded-xl border border-neutral-800 overflow-hidden">
                  <SyntaxHighlighter
                    style={vscDarkPlus}
                    language={previewLanguage || 'text'}
                    PreTag="div"
                    customStyle={{
                      margin: 0,
                      padding: '1.25rem',
                      borderRadius: 0,
                      fontSize: '0.875rem',
                      backgroundColor: '#1e1e1e',
                      height: '100%',
                      overflow: 'auto',
                    }}
                    codeTagProps={{
                      style: {
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                      }
                    }}
                  >
                    {previewContent}
                  </SyntaxHighlighter>
                </div>
              // 原有文本预览（作为 fallback）
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

      {/* ✨ 右键菜单 */}
      {contextMenu && (
        <div
          className="fixed z-[150] bg-[#1a1a1c] border border-neutral-700 rounded-lg shadow-2xl py-1 min-w-[160px] animate-in fade-in-0 zoom-in-95 duration-150"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          {(() => {
            const node = contextMenu.node;
            const isFolder = node.type === 'folder';
            const isProtectedRoot = isFolder && (node.path === 'raw_data' || node.path === 'results' || node.path === 'references');
            const isReadOnly = node.path.startsWith('references');
            const canCreateFolder = isFolder && !isReadOnly;
            const canMove = !isProtectedRoot && !isReadOnly;
            const canDelete = !isProtectedRoot && !isFolder && !isReadOnly;

            return (
              <>
                {/* 文件操作 */}
                {!isFolder && (
                  <>
                    <button
                      onClick={() => handleContextMenuAction('preview')}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-800 hover:text-white transition-colors"
                    >
                      <Eye size={14} className="text-emerald-400" />
                      预览
                    </button>
                    <button
                      onClick={() => handleContextMenuAction('download')}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-800 hover:text-white transition-colors"
                    >
                      <Download size={14} className="text-blue-400" />
                      下载
                    </button>
                    <div className="h-px bg-neutral-800 my-1" />
                  </>
                )}

                {/* 新建文件夹 */}
                {canCreateFolder && (
                  <button
                    onClick={() => handleContextMenuAction('create_folder')}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-800 hover:text-white transition-colors"
                  >
                    <FolderPlus size={14} className="text-purple-400" />
                    新建文件夹
                  </button>
                )}

                {/* 移动 */}
                {canMove && (
                  <button
                    onClick={() => handleContextMenuAction('move')}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-800 hover:text-white transition-colors"
                  >
                    <FolderInput size={14} className="text-blue-400" />
                    移动到...
                  </button>
                )}

                {/* 重命名 */}
                {canMove && (
                  <button
                    onClick={() => handleContextMenuAction('rename')}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-800 hover:text-white transition-colors"
                  >
                    <Pencil size={14} className="text-yellow-400" />
                    重命名
                  </button>
                )}

                {/* 删除 */}
                {canDelete && (
                  <>
                    <div className="h-px bg-neutral-800 my-1" />
                    <button
                      onClick={() => handleContextMenuAction('delete')}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 transition-colors"
                    >
                      <Trash2 size={14} />
                      删除
                    </button>
                  </>
                )}

                {/* 只读提示 */}
                {isReadOnly && (
                  <div className="px-3 py-2 text-xs text-neutral-500 flex items-center gap-2">
                    <Lock size={12} />
                    只读目录，禁止操作
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}

      {/* ✨ 创建文件夹模态框 */}
      <CreateFolderModal
        isOpen={createFolderModal.isOpen}
        onClose={() => setCreateFolderModal({ isOpen: false, parentPath: '' })}
        projectId={currentProjectId || ''}
        parentPath={createFolderModal.parentPath}
        onSuccess={() => currentProjectId && fetchProjectFiles(currentProjectId)}
      />

      {/* ✨ 移动文件模态框 */}
      <MoveFileModal
        isOpen={moveFileModal.isOpen}
        onClose={() => setMoveFileModal({ isOpen: false, sourcePath: '', sourceName: '', isFolder: false })}
        projectId={currentProjectId || ''}
        sourcePath={moveFileModal.sourcePath}
        sourceName={moveFileModal.sourceName}
        isFolder={moveFileModal.isFolder}
        onSuccess={() => currentProjectId && fetchProjectFiles(currentProjectId)}
      />

      {/* ✨ 重命名模态框 */}
      <RenameModal
        isOpen={renameModal.isOpen}
        onClose={() => setRenameModal({ isOpen: false, sourcePath: '', sourceName: '', isFolder: false })}
        projectId={currentProjectId || ''}
        sourcePath={renameModal.sourcePath}
        sourceName={renameModal.sourceName}
        isFolder={renameModal.isFolder}
        onSuccess={() => currentProjectId && fetchProjectFiles(currentProjectId)}
      />

      {/* ✨ 上传管理器 */}
      <UploadManager
        isOpen={uploadManagerState.isOpen}
        onClose={() => setUploadManagerState({ isOpen: false, files: [] })}
        projectId={currentProjectId || ''}
        targetPath={uploadTargetPath}
        files={uploadManagerState.files}
        onComplete={handleUploadComplete}
      />

      {/* ✨ 基因组表单弹窗 */}
      <GenomeFormModal
        isOpen={genomeFormOpen}
        onClose={() => { setGenomeFormOpen(false); setEditingGenome(null); }}
        onSuccess={() => {}}
        editGenome={editingGenome}
      />

      {/* ✨ 数据库表单弹窗 */}
      <DatabaseFormModal
        isOpen={databaseFormOpen}
        onClose={() => { setDatabaseFormOpen(false); setEditingDatabase(null); }}
        onSuccess={() => {}}
        editDatabase={editingDatabase}
      />

      {/* ✨ 基因组详情抽屉 */}
      <GenomeDetailDrawer
        genome={viewingGenome}
        isOpen={!!viewingGenome}
        onClose={() => setViewingGenome(null)}
        onEdit={(genome) => { setViewingGenome(null); setEditingGenome(genome); setGenomeFormOpen(true); }}
        onDelete={(genomeid) => { setViewingGenome(null); }}
        onRefresh={() => {}}
      />

      {/* ✨ 数据库详情抽屉 */}
      <DatabaseDetailDrawer
        database={viewingDatabase}
        isOpen={!!viewingDatabase}
        onClose={() => setViewingDatabase(null)}
        onEdit={(db) => { setViewingDatabase(null); setEditingDatabase(db); setDatabaseFormOpen(true); }}
        onDelete={(dbId) => { setViewingDatabase(null); }}
      />

      {/* ✨ 基因组导入弹窗 */}
      <ImportGenomeModal
        isOpen={genomeImportOpen}
        onClose={() => setGenomeImportOpen(false)}
        onSuccess={() => {}}
      />

    </div>
  );
}
