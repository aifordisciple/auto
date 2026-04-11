/**
 * 技能编辑器主区域
 *
 * 显示标签栏和 Monaco 编辑器
 */

'use client';

import React from 'react';
import { FileCode, X, ChevronLeft, ChevronRight } from 'lucide-react';
import dynamic from 'next/dynamic';
import { useForgeStore, findNodeInTree } from '@/store/useForgeStore';

// 动态导入 Monaco Editor，禁用 SSR
const Editor = dynamic(() => import('@monaco-editor/react').then(mod => mod.default), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full text-neutral-500 bg-neutral-900">
      <div className="animate-pulse">加载编辑器...</div>
    </div>
  )
});

// ==========================================
// 标签组件
// ==========================================
interface EditorTabProps {
  id: string;
  name: string;
  language: string;
  isModified: boolean;
  isActive: boolean;
  onSelect: () => void;
  onClose: () => void;
}

function EditorTab({ name, isModified, isActive, onSelect, onClose }: EditorTabProps) {
  return (
    <div
      className={`group flex items-center gap-2 px-3 py-1.5 border-r border-neutral-700 cursor-pointer transition-colors min-w-[100px] max-w-[180px]
        ${isActive ? 'bg-neutral-800 text-white' : 'bg-neutral-900 text-neutral-400 hover:bg-neutral-800/50'}
      `}
      onClick={onSelect}
    >
      <span className="flex-1 truncate text-xs">{name}</span>
      {isModified && (
        <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" title="已修改" />
      )}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-neutral-700 rounded transition-opacity"
      >
        <X size={12} />
      </button>
    </div>
  );
}

// ==========================================
// 主组件
// ==========================================
export function SkillEditorMain() {
  const {
    openTabs,
    activeFileId,
    skillFiles,
    setActiveFile,
    closeTab,
    updateFileContent
  } = useForgeStore();

  // 获取当前活动文件
  const activeFile = activeFileId ? findNodeInTree(skillFiles, activeFileId) : null;

  // 编辑器配置
  const editorOptions = {
    minimap: { enabled: false },
    fontSize: 14,
    lineNumbers: 'on' as const,
    roundedSelection: true,
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 2,
    wordWrap: 'on' as const,
    folding: true,
    foldingHighlight: true,
    showFoldingControls: 'mouseover' as const,
    bracketPairColorization: { enabled: true },
    renderLineHighlight: 'line' as const,
    cursorBlinking: 'smooth' as const,
    smoothScrolling: true,
    padding: { top: 16, bottom: 16 },
  };

  // 内容变化处理
  const handleContentChange = (value: string | undefined) => {
    if (value !== undefined && activeFileId) {
      updateFileContent(activeFileId, value);
    }
  };

  return (
    <div className="h-full flex flex-col bg-neutral-900">
      {/* 标签栏 */}
      {openTabs.length > 0 && (
        <div className="shrink-0 flex items-center h-9 bg-neutral-800/50 border-b border-neutral-800 overflow-x-auto custom-scrollbar">
          {/* 左侧指示 */}
          <div className="shrink-0 px-2 text-neutral-600">
            <ChevronLeft size={14} />
          </div>

          {/* 标签 */}
          <div className="flex-1 flex items-center min-w-0">
            {openTabs.map(tab => (
              <EditorTab
                key={tab.id}
                id={tab.id}
                name={tab.name}
                language={tab.language}
                isModified={tab.isModified}
                isActive={tab.id === activeFileId}
                onSelect={() => setActiveFile(tab.id)}
                onClose={() => closeTab(tab.id)}
              />
            ))}
          </div>

          {/* 右侧指示 */}
          <div className="shrink-0 px-2 text-neutral-600">
            <ChevronRight size={14} />
          </div>
        </div>
      )}

      {/* 编辑器区域 */}
      <div className="flex-1 min-h-0">
        {activeFile && activeFile.type === 'file' ? (
          <Editor
            height="100%"
            language={activeFile.language || 'plaintext'}
            value={activeFile.content || ''}
            onChange={handleContentChange}
            theme="vs-dark"
            options={editorOptions}
            loading={
              <div className="flex items-center justify-center h-full text-neutral-500">
                <div className="animate-spin mr-2">
                  <FileCode size={20} />
                </div>
                加载编辑器...
              </div>
            }
          />
        ) : (
          // 空状态
          <div className="h-full flex items-center justify-center text-neutral-500">
            <div className="text-center">
              <FileCode size={48} className="mx-auto mb-4 opacity-30" />
              <p className="text-sm">选择文件开始编辑</p>
              <p className="text-xs text-neutral-600 mt-2">在左侧文件树中点击文件</p>
            </div>
          </div>
        )}
      </div>

      {/* 状态栏 */}
      {activeFile && (
        <div className="shrink-0 h-6 bg-neutral-800/50 border-t border-neutral-800 flex items-center px-3 text-xs text-neutral-500">
          <span className="mr-4">{activeFile.path}</span>
          <span className="mr-4">{activeFile.language}</span>
          {activeFile.isModified && (
            <span className="text-amber-500">已修改</span>
          )}
        </div>
      )}
    </div>
  );
}