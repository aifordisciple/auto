"use client";

/**
 * LearningCenter - 学习中心 Overlay
 *
 * UI 风格与 SkillCenter 保持一致：
 * - 全屏右侧滑出面板
 * - 深色主题 bg-[#121212]
 * - 发光图标徽章
 * - 药丸状 Tab 栏
 *
 * Tab 切换视图：
 * - Library (文献库): 文献卡片网格 + 上传
 * - Knowledge (知识库): 全文搜索 + 知识块列表
 * - Notes (笔记): 笔记时间线
 * - Settings (设置): 标签管理
 */

import { useState, useEffect, useCallback } from "react";
import {
  BookOpen, Library, Brain, StickyNote, Settings2,
  X, UploadCloud, Search, Loader2, FileText, Trash2, ExternalLink, Code, Tag
} from "lucide-react";
import { useUIStore } from "@/store/useUIStore";
import { useLearningStore } from "@/store/useLearningStore";

// ==========================================
// Tab 配置（与 SkillCenter 风格一致）
// ==========================================

type TabType = "library" | "knowledge" | "notes" | "settings";

const TABS: { id: TabType; label: string; icon: React.ReactNode; color: string }[] = [
  { id: "library", label: "文献库", icon: <Library size={14} />, color: "emerald" },
  { id: "knowledge", label: "知识库", icon: <Brain size={14} />, color: "blue" },
  { id: "notes", label: "笔记", icon: <StickyNote size={14} />, color: "purple" },
  { id: "settings", label: "设置", icon: <Settings2 size={14} />, color: "gray" },
];

/** Tab 激活态颜色映射 */
const COLOR_CLASSES: Record<string, string> = {
  emerald: "bg-emerald-600 text-white",
  blue: "bg-blue-600 text-white",
  purple: "bg-purple-600 text-white",
  gray: "bg-neutral-600 text-white",
};

// ==========================================
// 主组件
// ==========================================

export function LearningCenter() {
  const { isLearningCenterOpen, closeAllOverlays } = useUIStore();
  const { stopAllPolling } = useLearningStore();
  const [activeTab, setActiveTab] = useState<TabType>("library");

  // 📚 组件卸载时清理轮询定时器
  useEffect(() => {
    return () => {
      stopAllPolling();
    };
  }, [stopAllPolling]);

  if (!isLearningCenterOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* 背景遮罩 */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={closeAllOverlays} />

      {/* 主面板 - 与 SkillCenter 一致的深色风格 */}
      <div className="relative w-full h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">

        {/* Header with Tabs - 与 SkillCenter 一致 */}
        <div className="h-16 shrink-0 border-b border-neutral-800 px-3 md:px-6 flex items-center justify-between bg-neutral-900/40">
          <div className="flex items-center gap-2 md:gap-4 flex-1 min-w-0">
            {/* 图标徽章 - 发光效果 */}
            <div className="flex items-center gap-2 md:gap-3 shrink-0">
              <div className="p-1.5 md:p-2 bg-emerald-500/20 border border-emerald-500/30 rounded-lg text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.15)]">
                <BookOpen size={16} strokeWidth={2.5} className="md:w-[18px] md:h-[18px]" />
              </div>
              <div className="hidden sm:block">
                <h2 className="text-sm font-bold text-neutral-200 tracking-wide">学习中心</h2>
                <p className="text-[10px] text-neutral-500 font-mono mt-0.5">文献管理、知识检索与锻造</p>
              </div>
            </div>

            {/* Tab 切换 - 药丸状与 SkillCenter 一致 */}
            <div className="flex items-center bg-neutral-800/50 rounded-lg p-1 ml-1 md:ml-4 overflow-x-auto flex-1 md:flex-none">
              {TABS.map((tab) => {
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1 md:gap-2 px-2 md:px-4 py-1.5 rounded-md text-xs font-medium transition-all ${
                      isActive
                        ? COLOR_CLASSES[tab.color] + ' shadow-md'
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

          {/* 关闭按钮 */}
          <button onClick={closeAllOverlays} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors shrink-0 ml-2">
            <X size={18} />
          </button>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-hidden">
          {activeTab === "library" && <LibraryPanel />}
          {activeTab === "knowledge" && <KnowledgePanel />}
          {activeTab === "notes" && <NotesPanel />}
          {activeTab === "settings" && <SettingsPanel />}
        </div>
      </div>
    </div>
  );
}

// ==========================================
// Library Panel (文献库)
// ==========================================

function LibraryPanel() {
  const {
    literatures, isLoading, isUploading, filters,
    fetchLiteratures, uploadPDF, deleteLiterature, selectLiterature, setFilters,
  } = useLearningStore();
  const [searchInput, setSearchInput] = useState(filters.search);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => { fetchLiteratures(); }, []);

  const handleSearch = () => {
    setFilters({ search: searchInput });
  };

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter(f => f.type === "application/pdf");
    if (files.length > 0) await uploadPDF(files);
  }, [uploadPDF]);

  const handleFileSelect = useCallback(async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.accept = ".pdf";
    input.onchange = async () => {
      if (input.files && input.files.length > 0) {
        await uploadPDF(Array.from(input.files));
      }
    };
    input.click();
  }, [uploadPDF]);

  const handleSelect = async (id: number) => {
    setSelectedId(id);
    await selectLiterature(id);
  };

  return (
    <div className="flex h-full">
      {/* 左侧：文献列表 */}
      <div className="w-2/3 border-r border-neutral-800 flex flex-col">
        {/* 搜索栏 + 上传 */}
        <div className="p-4 border-b border-neutral-800 flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-500" />
            <input
              type="text"
              placeholder="搜索文献标题、作者、DOI..."
              className="w-full pl-10 pr-4 py-2 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-500 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
            />
          </div>
          <button
            onClick={handleFileSelect}
            disabled={isUploading}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 text-white text-sm font-medium rounded-md transition-colors"
          >
            {isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <UploadCloud className="w-4 h-4" />}
            上传 PDF
          </button>
        </div>

        {/* 拖拽区域 + 文献卡片网格 */}
        <div
          className="flex-1 overflow-y-auto p-4"
          onDragOver={e => e.preventDefault()}
          onDrop={handleDrop}
        >
          {isLoading ? (
            <div className="flex justify-center items-center h-full text-neutral-500">
              <Loader2 className="w-6 h-6 animate-spin" />
            </div>
          ) : literatures.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-neutral-500 gap-3">
              <BookOpen className="w-12 h-12" />
              <p className="text-sm">暂无文献，拖拽 PDF 到此处或点击上传</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {literatures.map(lit => (
                <div
                  key={lit.id}
                  onClick={() => handleSelect(lit.id)}
                  className={`p-3 rounded-lg border cursor-pointer transition-all hover:shadow-md hover:shadow-emerald-500/5 ${
                    selectedId === lit.id
                      ? "border-emerald-500/50 bg-emerald-500/5"
                      : "border-neutral-800 bg-neutral-900/50 hover:border-neutral-700"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-medium text-neutral-200 line-clamp-2">{lit.title}</h3>
                    <StatusBadge status={lit.status} parseError={lit.parse_error} />
                  </div>
                  {/* 📚 错误状态显示错误原因 */}
                  {lit.status === 'error' && lit.parse_error && (
                    <p className="text-xs text-red-400 mt-1 line-clamp-1">{lit.parse_error}</p>
                  )}
                  {lit.authors && <p className="text-xs text-neutral-500 mt-1 line-clamp-1">{lit.authors}</p>}
                  <div className="flex items-center gap-2 mt-2 text-xs text-neutral-500">
                    {lit.journal && <span>{lit.journal}</span>}
                    {lit.year && <span>{lit.year}</span>}
                  </div>
                  {lit.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {lit.tags.slice(0, 3).map(tag => (
                        <span key={tag} className="px-1.5 py-0.5 bg-neutral-800 text-neutral-400 text-xs rounded">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 右侧：文献详情 */}
      <div className="w-1/3 flex flex-col">
        <LiteratureDetailPanel
          onClose={() => setSelectedId(null)}
        />
      </div>
    </div>
  );
}

// ==========================================
// 状态徽章
// ==========================================

function StatusBadge({ status, parseError }: { status: string; parseError?: string }) {
  const config: Record<string, { label: string; className: string; icon?: React.ReactNode }> = {
    uploading: {
      label: "上传中",
      className: "bg-yellow-900/30 text-yellow-400",
      icon: <Loader2 className="w-3 h-3 animate-spin" />,
    },
    parsing: {
      label: "解析中",
      className: "bg-blue-900/30 text-blue-400",
      icon: <Loader2 className="w-3 h-3 animate-spin" />,
    },
    ready: {
      label: "就绪",
      className: "bg-emerald-900/30 text-emerald-400",
    },
    error: {
      label: "错误",
      className: "bg-red-900/30 text-red-400",
    },
  };
  const c = config[status] || config.error;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded font-medium ${c.className}`}>
      {c.icon}
      {c.label}
    </span>
  );
}

// ==========================================
// 文献详情面板
// ==========================================

function LiteratureDetailPanel({ onClose }: { onClose: () => void }) {
  const { selectedLiterature, chunks, deleteLiterature, forgeToChat } = useLearningStore();

  if (!selectedLiterature) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-neutral-500 gap-2">
        <FileText className="w-10 h-10" />
        <p className="text-sm">点击文献查看详情</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="p-4 border-b border-neutral-800">
        <h3 className="text-sm font-semibold text-neutral-200 line-clamp-2">{selectedLiterature.title}</h3>
        {selectedLiterature.authors && <p className="text-xs text-neutral-500 mt-1">{selectedLiterature.authors}</p>}
        <div className="flex items-center gap-3 mt-2 text-xs text-neutral-500">
          {selectedLiterature.journal && <span>{selectedLiterature.journal}</span>}
          {selectedLiterature.year && <span>{selectedLiterature.year}</span>}
          {selectedLiterature.doi && (
            <a href={`https://doi.org/${selectedLiterature.doi}`} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-blue-400 hover:text-blue-300 hover:underline">
              DOI <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      </div>

      {/* 摘要 */}
      {selectedLiterature.abstract && (
        <div className="p-4 border-b border-neutral-800">
          <h4 className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-2">摘要</h4>
          <p className="text-xs text-neutral-400 line-clamp-6">{selectedLiterature.abstract}</p>
        </div>
      )}

      {/* 知识块列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <h4 className="text-xs font-semibold text-neutral-500 uppercase tracking-wider">知识块 ({chunks.length})</h4>
        {chunks.map(chunk => (
          <div key={chunk.id} className="p-3 rounded-md border border-neutral-800 bg-neutral-900/50">
            <div className="flex items-center gap-2 mb-1">
              <span className={`px-1.5 py-0.5 text-xs rounded font-medium ${
                chunk.chunk_type === "figure" ? "bg-purple-900/30 text-purple-400" :
                chunk.chunk_type === "table" ? "bg-orange-900/30 text-orange-400" :
                "bg-neutral-800 text-neutral-400"
              }`}>
                {chunk.chunk_type}
              </span>
              <span className="text-xs text-neutral-500">P{chunk.page_number}</span>
              {chunk.section_title && <span className="text-xs text-neutral-400 truncate">{chunk.section_title}</span>}
            </div>
            <p className="text-xs text-neutral-400 line-clamp-4">{chunk.content}</p>
            {chunk.figure_caption && (
              <p className="text-xs text-neutral-500 mt-1 italic line-clamp-2">{chunk.figure_caption}</p>
            )}
          </div>
        ))}
      </div>

      {/* 操作栏 */}
      <div className="p-4 border-t border-neutral-800 space-y-2">
        <button
          onClick={() => forgeToChat(selectedLiterature.id)}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-md transition-colors"
        >
          <Code className="w-4 h-4" />
          一键锻造 → 发送到 Chat
        </button>
        <button
          onClick={() => { deleteLiterature(selectedLiterature.id); onClose(); }}
          className="w-full flex items-center justify-center gap-2 py-2 px-4 text-red-400 hover:bg-red-900/20 text-sm font-medium rounded-md transition-colors"
        >
          <Trash2 className="w-4 h-4" />
          删除文献
        </button>
      </div>
    </div>
  );
}

// ==========================================
// Knowledge Panel (知识库)
// ==========================================

function KnowledgePanel() {
  const { searchResults, searchQuery, isSearching, searchKnowledge } = useLearningStore();
  const [input, setInput] = useState("");

  const handleSearch = () => {
    if (input.trim()) searchKnowledge(input.trim());
  };

  return (
    <div className="flex flex-col h-full p-6">
      {/* 搜索栏 */}
      <div className="flex items-center gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
          <input
            type="text"
            placeholder="输入分析目的或图形特征（如：单细胞拟时序分析轨迹图...）"
            className="w-full pl-12 pr-4 py-3 rounded-lg border border-neutral-700 bg-neutral-900 shadow-sm text-sm text-neutral-200 placeholder:text-neutral-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSearch()}
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={isSearching || !input.trim()}
          className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium rounded-lg transition-colors"
        >
          深度检索
        </button>
      </div>

      {/* 搜索结果 */}
      {isSearching ? (
        <div className="flex justify-center items-center h-40 text-neutral-500">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : searchResults.length > 0 ? (
        <div className="flex-1 overflow-y-auto space-y-4">
          <p className="text-sm text-neutral-500">找到 {searchResults.length} 个匹配知识块</p>
          {searchResults.map((result, idx) => (
            <div key={idx} className="p-4 rounded-lg border border-neutral-800 bg-neutral-900/50">
              <div className="flex items-center gap-2 mb-2">
                <span className={`px-1.5 py-0.5 text-xs rounded font-medium ${
                  result.match_type === "semantic" ? "bg-emerald-900/30 text-emerald-400" : "bg-blue-900/30 text-blue-400"
                }`}>
                  {result.match_type === "semantic" ? "语义匹配" : "关键词匹配"}
                </span>
                <span className="text-xs text-neutral-500">P{result.page_number}</span>
              </div>
              {result.source_title && (
                <p className="text-xs font-medium text-neutral-400 mb-1">
                  来源: {result.source_title}
                </p>
              )}
              <p className="text-sm text-neutral-300 line-clamp-6">{result.content}</p>
            </div>
          ))}
        </div>
      ) : searchQuery ? (
        <div className="text-center text-neutral-500 mt-10">未找到匹配的知识块</div>
      ) : (
        <div className="flex flex-col items-center justify-center h-40 text-neutral-500 gap-2">
          <Brain className="w-10 h-10" />
          <p className="text-sm">输入关键词或自然语言进行检索</p>
        </div>
      )}
    </div>
  );
}

// ==========================================
// Notes Panel (笔记)
// ==========================================

function NotesPanel() {
  const { notes, selectedLiterature } = useLearningStore();

  return (
    <div className="flex flex-col h-full p-6">
      {!selectedLiterature ? (
        <div className="flex flex-col items-center justify-center h-full text-neutral-500 gap-2">
          <StickyNote className="w-10 h-10" />
          <p className="text-sm">请先选择一篇文献查看笔记</p>
        </div>
      ) : notes.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full text-neutral-500 gap-2">
          <StickyNote className="w-10 h-10" />
          <p className="text-sm">暂无笔记</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-3">
          {notes.map(note => (
            <div key={note.id} className="p-3 rounded-md border border-neutral-800 bg-neutral-900/50">
              <p className="text-sm text-neutral-300">{note.content}</p>
              <p className="text-xs text-neutral-500 mt-2">{new Date(note.created_at).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ==========================================
// Settings Panel (设置)
// ==========================================

function SettingsPanel() {
  const { tags, fetchTags, createTag, deleteTag } = useLearningStore();
  const [newTagName, setNewTagName] = useState("");

  useEffect(() => { fetchTags(); }, []);

  const handleCreate = async () => {
    if (newTagName.trim()) {
      await createTag(newTagName.trim());
      setNewTagName("");
    }
  };

  return (
    <div className="flex flex-col h-full p-6">
      <h3 className="text-sm font-semibold text-neutral-200 mb-4">标签管理</h3>

      {/* 新建标签 */}
      <div className="flex items-center gap-2 mb-6">
        <input
          type="text"
          placeholder="新标签名称"
          className="flex-1 px-3 py-2 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-500"
          value={newTagName}
          onChange={e => setNewTagName(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleCreate()}
        />
        <button
          onClick={handleCreate}
          disabled={!newTagName.trim()}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 text-white text-sm rounded-md transition-colors"
        >
          添加
        </button>
      </div>

      {/* 标签列表 */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {tags.map(tag => (
          <div key={tag.id} className="flex items-center justify-between p-3 rounded-md border border-neutral-800">
            <div className="flex items-center gap-2">
              <Tag className="w-4 h-4 text-neutral-500" />
              <span className="text-sm text-neutral-300">{tag.name}</span>
            </div>
            <button
              onClick={() => deleteTag(tag.id)}
              className="p-1 hover:bg-red-900/20 rounded transition-colors"
            >
              <Trash2 className="w-4 h-4 text-red-400" />
            </button>
          </div>
        ))}
        {tags.length === 0 && (
          <p className="text-sm text-neutral-500 text-center mt-10">暂无标签</p>
        )}
      </div>
    </div>
  );
}

export default LearningCenter;
