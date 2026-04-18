/**
 * 依赖包管理编辑器组件
 *
 * 功能：
 * - 包搜索添加
 * - 版本指定
 * - 常用包推荐
 * - 批量导入
 */

'use client';

import { useState, useCallback, useMemo, KeyboardEvent } from 'react';
import { Package, Plus, X, Search, Upload } from 'lucide-react';

interface DependenciesEditorProps {
  value: string[];
  onChange: (deps: string[]) => void;
  executorType?: string;
  /** 内嵌模式：不显示标题栏，用于嵌入父级折叠面板 */
  showHeader?: boolean;
}

// 生信常用包
const BIO_PACKAGES = {
  Python: [
    { name: 'numpy', desc: '数值计算' },
    { name: 'pandas', desc: '数据处理' },
    { name: 'scipy', desc: '科学计算' },
    { name: 'scanpy', desc: '单细胞分析' },
    { name: 'anndata', desc: '注释数据结构' },
    { name: 'matplotlib', desc: '绘图' },
    { name: 'seaborn', desc: '统计可视化' },
    { name: 'biopython', desc: '生物信息学工具' },
    { name: 'pysam', desc: 'SAM/BAM 处理' },
    { name: 'htseq', desc: '测序数据分析' },
  ],
  R: [
    { name: 'Seurat', desc: '单细胞分析' },
    { name: 'DESeq2', desc: '差异表达分析' },
    { name: 'edgeR', desc: '差异表达分析' },
    { name: 'ggplot2', desc: '绘图' },
    { name: 'dplyr', desc: '数据处理' },
    { name: 'tidyr', desc: '数据整理' },
    { name: 'biostrings', desc: '生物序列处理' },
    { name: 'GenomicRanges', desc: '基因组范围操作' },
    { name: 'SingleCellExperiment', desc: '单细胞数据结构' },
    { name: 'monocle3', desc: '拟时序分析' },
  ]
};

// 包搜索模拟
const searchPackages = async (query: string, language: 'Python' | 'R'): Promise<string[]> => {
  // 模拟搜索结果
  const packages = BIO_PACKAGES[language] || [];
  return packages
    .filter(p => p.name.toLowerCase().includes(query.toLowerCase()))
    .map(p => p.name);
};

export function DependenciesEditor({ value, onChange, executorType, showHeader = true }: DependenciesEditorProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [searchResults, setSearchResults] = useState<string[]>([]);

  // 根据执行器类型确定语言
  const language = useMemo(() => {
    if (executorType === 'R_env') return 'R';
    return 'Python';
  }, [executorType]);

  // 获取推荐包
  const recommendedPackages = useMemo(() => {
    return BIO_PACKAGES[language] || [];
  }, [language]);

  // 处理搜索
  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query);
    if (query.length > 0) {
      const results = recommendedPackages
        .filter(p => p.name.toLowerCase().includes(query.toLowerCase()))
        .map(p => p.name);
      setSearchResults(results);
      setShowSearch(true);
    } else {
      setShowSearch(false);
      setSearchResults([]);
    }
  }, [recommendedPackages]);

  // 添加依赖
  const handleAddDependency = useCallback((dep: string) => {
    const normalizedDep = dep.trim();
    if (normalizedDep && !value.includes(normalizedDep)) {
      onChange([...value, normalizedDep]);
    }
    setSearchQuery('');
    setShowSearch(false);
  }, [value, onChange]);

  // 移除依赖
  const handleRemoveDependency = useCallback((dep: string) => {
    onChange(value.filter(d => d !== dep));
  }, [value, onChange]);

  // 处理回车添加
  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && searchQuery.trim()) {
      handleAddDependency(searchQuery);
    }
  }, [searchQuery, handleAddDependency]);

  // 批量导入
  const handleBulkImport = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = language === 'Python' ? '.txt' : '.txt';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;

      const text = await file.text();
      const lines = text.split('\n')
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('#'));

      const newDeps = [...new Set([...value, ...lines])];
      onChange(newDeps);
    };
    input.click();
  }, [value, onChange, language]);

  // 渲染内容区域（供内嵌模式和带标题栏模式共用）
  const renderContent = () => (
    <>
      {/* 搜索和添加 */}
      <div className="p-2 border-b border-neutral-800 relative">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => searchQuery && setShowSearch(true)}
            onBlur={() => setTimeout(() => setShowSearch(false), 200)}
            placeholder="搜索或输入包名..."
            className="w-full bg-neutral-800 border border-neutral-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder:text-neutral-500 focus:border-blue-500 focus:outline-none"
          />
          <button
            onClick={() => handleAddDependency(searchQuery)}
            disabled={!searchQuery.trim()}
            className="absolute right-1 top-1/2 -translate-y-1/2 p-1 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-700 disabled:text-neutral-500 rounded text-white transition-colors"
          >
            <Plus size={14} />
          </button>
        </div>

        {/* 搜索结果下拉 */}
        {showSearch && searchResults.length > 0 && (
          <div className="absolute left-2 right-2 mt-1 bg-neutral-800 border border-neutral-700 rounded-lg shadow-lg z-10 max-h-32 overflow-y-auto">
            {searchResults.map((pkg) => (
              <button
                key={pkg}
                onClick={() => handleAddDependency(pkg)}
                className="w-full text-left px-3 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700 flex items-center justify-between"
              >
                <span>{pkg}</span>
                <Plus size={12} className="text-neutral-500" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 当前依赖列表 */}
      {value.length > 0 && (
        <div className="p-2 border-b border-neutral-800">
          <div className="flex flex-wrap gap-1">
            {value.map((dep) => (
              <div
                key={dep}
                className="flex items-center gap-1 px-2 py-1 bg-neutral-800 rounded text-xs text-neutral-300 group"
              >
                <span className="font-mono">{dep}</span>
                <button
                  onClick={() => handleRemoveDependency(dep)}
                  className="text-neutral-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 常用包推荐 */}
      <div className="p-2">
        <p className="text-[10px] text-neutral-500 mb-1.5">常用 {language} 生信包:</p>
        <div className="flex flex-wrap gap-1">
          {recommendedPackages.slice(0, 6).map((pkg) => {
            const isAdded = value.includes(pkg.name);
            return (
              <button
                key={pkg.name}
                onClick={() => !isAdded && handleAddDependency(pkg.name)}
                disabled={isAdded}
                className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                  isAdded
                    ? 'bg-neutral-800 text-neutral-500 cursor-not-allowed'
                    : 'bg-neutral-800/50 text-neutral-400 hover:bg-neutral-700 hover:text-white'
                }`}
                title={pkg.desc}
              >
                {pkg.name}
                {isAdded && ' ✓'}
              </button>
            );
          })}
        </div>
      </div>
    </>
  );

  // 内嵌模式：不显示标题栏
  if (!showHeader) {
    return (
      <div className="border border-neutral-800 rounded-lg bg-neutral-900/50 overflow-hidden">
        {renderContent()}
      </div>
    );
  }

  // 带标题栏模式（默认）
  return (
    <div className="border border-neutral-800 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-neutral-900 border-b border-neutral-800">
        <div className="flex items-center gap-2">
          <Package size={14} className="text-emerald-500" />
          <span className="text-xs font-medium text-neutral-300">依赖包管理</span>
          <span className="text-[10px] text-neutral-500">({language})</span>
        </div>
        <button
          onClick={handleBulkImport}
          className="flex items-center gap-1 px-2 py-1 text-xs text-neutral-400 hover:text-white hover:bg-neutral-800 rounded transition-colors"
        >
          <Upload size={12} />
          导入
        </button>
      </div>

      {renderContent()}
    </div>
  );
}