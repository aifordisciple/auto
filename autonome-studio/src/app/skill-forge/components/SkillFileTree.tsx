/**
 * 技能文件树组件
 *
 * 显示技能包的文件结构，支持展开/折叠、选择文件、右键菜单等
 */

'use client';

import React, { useState } from 'react';
import {
  Folder,
  FolderOpen,
  File,
  FileCode,
  FileText,
  Braces,
  Table,
  ChevronRight,
  ChevronDown,
  Plus,
  FilePlus,
  FolderPlus,
  Trash2,
  Pencil
} from 'lucide-react';
import { useForgeStore, SkillFileNode, getFileLanguage } from '@/store/useForgeStore';

// ==========================================
// 文件图标组件
// ==========================================
function FileIcon({ name, className = '' }: { name: string; className?: string }) {
  const ext = name.split('.').pop()?.toLowerCase();

  const iconMap: Record<string, React.ReactNode> = {
    py: <FileCode size={16} className={`text-yellow-400 ${className}`} />,
    r: <FileCode size={16} className={`text-blue-400 ${className}`} />,
    R: <FileCode size={16} className={`text-blue-400 ${className}`} />,
    nf: <FileCode size={16} className={`text-green-400 ${className}`} />,
    md: <FileText size={16} className={`text-purple-400 ${className}`} />,
    json: <Braces size={16} className={`text-amber-400 ${className}`} />,
    yaml: <Braces size={16} className={`text-cyan-400 ${className}`} />,
    yml: <Braces size={16} className={`text-cyan-400 ${className}`} />,
    tsv: <Table size={16} className={`text-emerald-400 ${className}`} />,
    csv: <Table size={16} className={`text-orange-400 ${className}`} />,
    sh: <FileCode size={16} className={`text-lime-400 ${className}`} />,
  };

  return iconMap[ext || ''] || <File size={16} className={`text-neutral-400 ${className}`} />;
}

// ==========================================
// 右键菜单组件
// ==========================================
interface ContextMenuProps {
  x: number;
  y: number;
  node: SkillFileNode;
  onClose: () => void;
  onRename: () => void;
  onDelete: () => void;
  onNewFile: () => void;
  onNewFolder: () => void;
}

function ContextMenu({ x, y, node, onClose, onRename, onDelete, onNewFile, onNewFolder }: ContextMenuProps) {
  const isFolder = node.type === 'folder';

  return (
    <>
      {/* 遮罩层 */}
      <div className="fixed inset-0 z-40" onClick={onClose} />

      {/* 菜单 */}
      <div
        className="fixed z-50 bg-neutral-800 border border-neutral-700 rounded-lg shadow-xl py-1 min-w-[140px]"
        style={{ left: x, top: y }}
      >
        {isFolder && (
          <>
            <button
              onClick={() => { onNewFile(); onClose(); }}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-700"
            >
              <FilePlus size={14} /> 新建文件
            </button>
            <button
              onClick={() => { onNewFolder(); onClose(); }}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-700"
            >
              <FolderPlus size={14} /> 新建文件夹
            </button>
            <div className="border-t border-neutral-700 my-1" />
          </>
        )}
        <button
          onClick={() => { onRename(); onClose(); }}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-700"
        >
          <Pencil size={14} /> 重命名
        </button>
        <button
          onClick={() => { onDelete(); onClose(); }}
          className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-red-400 hover:bg-neutral-700"
        >
          <Trash2 size={14} /> 删除
        </button>
      </div>
    </>
  );
}

// ==========================================
// 文件树节点组件
// ==========================================
interface FileTreeNodeProps {
  node: SkillFileNode;
  depth: number;
}

function FileTreeNode({ node, depth }: FileTreeNodeProps) {
  const {
    activeFileId,
    expandedFolders,
    setActiveFile,
    toggleFolder,
    deleteFile,
    renameFile,
    addFile
  } = useForgeStore();

  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(node.name);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const [newFileName, setNewFileName] = useState('');
  const [isAddingFile, setIsAddingFile] = useState(false);
  const [isAddingFolder, setIsAddingFolder] = useState(false);

  const isFolder = node.type === 'folder';
  const isExpanded = expandedFolders.has(node.id);
  const isActive = activeFileId === node.id;

  // 处理点击
  const handleClick = () => {
    if (isFolder) {
      toggleFolder(node.id);
    } else {
      setActiveFile(node.id);
    }
  };

  // 右键菜单
  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  // 重命名完成
  const handleRenameSubmit = () => {
    if (editName.trim() && editName !== node.name) {
      renameFile(node.id, editName.trim());
    }
    setIsEditing(false);
  };

  // 新建文件/文件夹
  const handleAddFile = () => {
    setIsAddingFile(true);
    setNewFileName('');
  };

  const handleAddFolder = () => {
    setIsAddingFolder(true);
    setNewFileName('');
  };

  const handleNewFileSubmit = (type: 'file' | 'folder') => {
    if (newFileName.trim()) {
      addFile(node.id, newFileName.trim(), type);
    }
    setIsAddingFile(false);
    setIsAddingFolder(false);
    setNewFileName('');
  };

  return (
    <div className="select-none">
      {/* 节点行 */}
      <div
        className={`flex items-center gap-1 px-2 py-1 cursor-pointer transition-colors group
          ${isActive ? 'bg-blue-500/20 text-white' : 'text-neutral-400 hover:bg-neutral-800'}
        `}
        style={{ paddingLeft: `${8 + depth * 16}px` }}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      >
        {/* 展开/折叠图标 */}
        {isFolder ? (
          <span className="shrink-0 text-neutral-500">
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        ) : (
          <span className="shrink-0 w-3.5" />
        )}

        {/* 文件/文件夹图标 */}
        <span className="shrink-0">
          {isFolder ? (
            isExpanded ? (
              <FolderOpen size={16} className="text-amber-400" />
            ) : (
              <Folder size={16} className="text-amber-400" />
            )
          ) : (
            <FileIcon name={node.name} />
          )}
        </span>

        {/* 文件名 */}
        {isEditing ? (
          <input
            autoFocus
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={handleRenameSubmit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRenameSubmit();
              if (e.key === 'Escape') setIsEditing(false);
            }}
            className="flex-1 bg-neutral-700 px-1 text-sm text-white outline-none rounded"
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className="flex-1 truncate text-sm">{node.name}</span>
        )}

        {/* 修改标记 */}
        {node.isModified && (
          <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" title="已修改" />
        )}
      </div>

      {/* 子节点 */}
      {isFolder && isExpanded && (
        <div>
          {node.children && node.children.map(child => (
            <FileTreeNode key={child.id} node={child} depth={depth + 1} />
          ))}

          {/* 新建文件输入框 */}
          {isAddingFile && (
            <div
              className="flex items-center gap-1 px-2 py-1"
              style={{ paddingLeft: `${8 + (depth + 1) * 16}px` }}
            >
              <FileIcon name="new.py" />
              <input
                autoFocus
                value={newFileName}
                onChange={(e) => setNewFileName(e.target.value)}
                onBlur={() => setIsAddingFile(false)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleNewFileSubmit('file');
                  if (e.key === 'Escape') setIsAddingFile(false);
                }}
                placeholder="文件名..."
                className="flex-1 bg-neutral-700 px-1 text-sm text-white outline-none rounded"
              />
            </div>
          )}

          {/* 新建文件夹输入框 */}
          {isAddingFolder && (
            <div
              className="flex items-center gap-1 px-2 py-1"
              style={{ paddingLeft: `${8 + (depth + 1) * 16}px` }}
            >
              <Folder size={16} className="text-amber-400" />
              <input
                autoFocus
                value={newFileName}
                onChange={(e) => setNewFileName(e.target.value)}
                onBlur={() => setIsAddingFolder(false)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleNewFileSubmit('folder');
                  if (e.key === 'Escape') setIsAddingFolder(false);
                }}
                placeholder="文件夹名..."
                className="flex-1 bg-neutral-700 px-1 text-sm text-white outline-none rounded"
              />
            </div>
          )}
        </div>
      )}

      {/* 右键菜单 */}
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          node={node}
          onClose={() => setContextMenu(null)}
          onRename={() => setIsEditing(true)}
          onDelete={() => deleteFile(node.id)}
          onNewFile={handleAddFile}
          onNewFolder={handleAddFolder}
        />
      )}
    </div>
  );
}

// ==========================================
// 主组件：技能文件树
// ==========================================
export function SkillFileTree() {
  const {
    skillFiles,
    addFile,
    initSkillFiles,
    executorType,
    skillDraft
  } = useForgeStore();

  // 确保文件系统已初始化
  React.useEffect(() => {
    if (skillFiles.length === 0 && skillDraft.script_code) {
      initSkillFiles();
    }
  }, [executorType]);

  // 新建文件/文件夹（根目录）
  const [isAddingFile, setIsAddingFile] = useState(false);
  const [isAddingFolder, setIsAddingFolder] = useState(false);
  const [newName, setNewName] = useState('');

  const handleNewFileSubmit = (type: 'file' | 'folder') => {
    if (newName.trim()) {
      addFile('', newName.trim(), type);
    }
    setIsAddingFile(false);
    setIsAddingFolder(false);
    setNewName('');
  };

  return (
    <div className="h-full flex flex-col bg-neutral-900/50">
      {/* 工具栏 */}
      <div className="shrink-0 flex items-center justify-between px-3 py-2 border-b border-neutral-800">
        <span className="text-xs text-neutral-400 font-medium">文件浏览器</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsAddingFile(true)}
            className="p-1 hover:bg-neutral-700 rounded text-neutral-500 hover:text-white transition-colors"
            title="新建文件"
          >
            <FilePlus size={14} />
          </button>
          <button
            onClick={() => setIsAddingFolder(true)}
            className="p-1 hover:bg-neutral-700 rounded text-neutral-500 hover:text-white transition-colors"
            title="新建文件夹"
          >
            <FolderPlus size={14} />
          </button>
        </div>
      </div>

      {/* 文件树 */}
      <div className="flex-1 overflow-y-auto custom-scrollbar py-1">
        {skillFiles.map(node => (
          <FileTreeNode key={node.id} node={node} depth={0} />
        ))}

        {/* 根目录新建文件 */}
        {isAddingFile && (
          <div className="flex items-center gap-1 px-2 py-1" style={{ paddingLeft: '8px' }}>
            <FileIcon name="new.py" />
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onBlur={() => setIsAddingFile(false)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleNewFileSubmit('file');
                if (e.key === 'Escape') setIsAddingFile(false);
              }}
              placeholder="文件名..."
              className="flex-1 bg-neutral-700 px-1 text-sm text-white outline-none rounded"
            />
          </div>
        )}

        {/* 根目录新建文件夹 */}
        {isAddingFolder && (
          <div className="flex items-center gap-1 px-2 py-1" style={{ paddingLeft: '8px' }}>
            <Folder size={16} className="text-amber-400" />
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onBlur={() => setIsAddingFolder(false)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleNewFileSubmit('folder');
                if (e.key === 'Escape') setIsAddingFolder(false);
              }}
              placeholder="文件夹名..."
              className="flex-1 bg-neutral-700 px-1 text-sm text-white outline-none rounded"
            />
          </div>
        )}

        {/* 空状态 */}
        {skillFiles.length === 0 && !isAddingFile && !isAddingFolder && (
          <div className="flex flex-col items-center justify-center h-32 text-neutral-600">
            <Folder size={32} className="opacity-30 mb-2" />
            <p className="text-xs">空目录</p>
            <p className="text-xs text-neutral-700">点击上方按钮添加文件</p>
          </div>
        )}
      </div>
    </div>
  );
}