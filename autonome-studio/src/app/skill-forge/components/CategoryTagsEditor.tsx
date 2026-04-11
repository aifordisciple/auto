/**
 * 分类与标签编辑器组件
 *
 * 功能：
 * - 分类下拉选择
 * - 子分类联动
 * - 标签输入与自动补全
 */

'use client';

import React, { useState, useCallback, useMemo } from 'react';
import { Tag, ChevronRight, X, Plus } from 'lucide-react';

interface CategoryTagsEditorProps {
  category?: string;
  subcategory?: string;
  tags?: string[];
  onChange: (data: { category?: string; subcategory?: string; tags?: string[] }) => void;
  /** 内嵌模式：不显示标题栏，用于嵌入父级折叠面板 */
  showHeader?: boolean;
}

// 分类定义（与 SkillCenter 一致）
const CATEGORIES = [
  { id: 'quality_control', name: '质量控制', subcategories: [
    { id: 'fastq_qc', name: 'FastQ质控' },
    { id: 'bam_qc', name: 'BAM质控' },
    { id: 'vcf_qc', name: 'VCF质控' }
  ]},
  { id: 'alignment', name: '序列比对', subcategories: [
    { id: 'dna_align', name: 'DNA比对' },
    { id: 'rna_align', name: 'RNA比对' }
  ]},
  { id: 'quantification', name: '定量分析', subcategories: [
    { id: 'rnaseq_quant', name: 'RNA-Seq定量' },
    { id: 'scrna_quant', name: '单细胞定量' }
  ]},
  { id: 'differential_analysis', name: '差异分析', subcategories: [
    { id: 'degs', name: '差异基因' },
    { id: 'pathway', name: '通路富集' }
  ]},
  { id: 'visualization', name: '可视化', subcategories: [
    { id: 'heatmap', name: '热图' },
    { id: 'volcano', name: '火山图' },
    { id: 'pca', name: 'PCA分析' }
  ]},
  { id: 'pipeline', name: '流程编排', subcategories: [
    { id: 'nextflow', name: 'Nextflow' },
    { id: 'snakemake', name: 'Snakemake' }
  ]},
  { id: 'single_cell', name: '单细胞分析', subcategories: [
    { id: 'scrna_preprocessing', name: '预处理' },
    { id: 'scrna_clustering', name: '聚类分析' },
    { id: 'scrna_annotation', name: '细胞注释' }
  ]},
  { id: 'other', name: '其他', subcategories: [] }
];

// 常用标签建议
const SUGGESTED_TAGS = [
  'RNA-seq', 'scRNA-seq', 'ChIP-seq', 'ATAC-seq', 'BS-seq',
  '差异分析', '质量控制', '可视化', '比对', '定量',
  '单细胞', '空间转录组', '蛋白质组', '代谢组',
  'Python', 'R', 'Nextflow', 'Snakemake'
];

export function CategoryTagsEditor({ category, subcategory, tags = [], onChange, showHeader = true }: CategoryTagsEditorProps) {
  const [newTag, setNewTag] = useState('');
  const [showTagSuggestions, setShowTagSuggestions] = useState(false);

  // 获取当前分类的子分类列表
  const currentSubcategories = useMemo(() => {
    const cat = CATEGORIES.find(c => c.id === category);
    return cat?.subcategories || [];
  }, [category]);

  // 处理分类变更
  const handleCategoryChange = useCallback((newCategory: string) => {
    onChange({
      category: newCategory,
      subcategory: undefined // 重置子分类
    });
  }, [onChange]);

  // 处理子分类变更
  const handleSubcategoryChange = useCallback((newSubcategory: string) => {
    onChange({ subcategory: newSubcategory });
  }, [onChange]);

  // 添加标签
  const handleAddTag = useCallback((tag: string) => {
    const normalizedTag = tag.trim();
    if (normalizedTag && !tags.includes(normalizedTag)) {
      onChange({ tags: [...tags, normalizedTag] });
    }
    setNewTag('');
    setShowTagSuggestions(false);
  }, [tags, onChange]);

  // 移除标签
  const handleRemoveTag = useCallback((tag: string) => {
    onChange({ tags: tags.filter(t => t !== tag) });
  }, [tags, onChange]);

  // 过滤标签建议
  const filteredSuggestions = useMemo(() => {
    if (!newTag) return SUGGESTED_TAGS.slice(0, 8);
    return SUGGESTED_TAGS.filter(t =>
      t.toLowerCase().includes(newTag.toLowerCase()) &&
      !tags.includes(t)
    ).slice(0, 8);
  }, [newTag, tags]);

  // 渲染内容区域
  const renderContent = () => (
    <div className="p-3 space-y-3">
      {/* 分类选择 */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] text-neutral-500 mb-1 block">分类</label>
          <select
            value={category || ''}
            onChange={(e) => handleCategoryChange(e.target.value)}
            className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
          >
            <option value="">选择分类...</option>
            {CATEGORIES.map((cat) => (
              <option key={cat.id} value={cat.id}>{cat.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-[10px] text-neutral-500 mb-1 block">子分类</label>
          <select
            value={subcategory || ''}
            onChange={(e) => handleSubcategoryChange(e.target.value)}
            disabled={!category || currentSubcategories.length === 0}
            className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option value="">选择子分类...</option>
            {currentSubcategories.map((sub) => (
              <option key={sub.id} value={sub.id}>{sub.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* 当前分类显示 */}
      {category && (
        <div className="flex items-center gap-1 text-xs text-neutral-400">
          <span>当前:</span>
          <span className="text-neutral-300">
            {CATEGORIES.find(c => c.id === category)?.name || category}
          </span>
          {subcategory && (
            <>
              <ChevronRight size={10} />
              <span className="text-neutral-300">
                {currentSubcategories.find(s => s.id === subcategory)?.name || subcategory}
              </span>
            </>
          )}
        </div>
      )}

      {/* 标签输入 */}
      <div>
        <label className="text-[10px] text-neutral-500 mb-1 block">标签</label>
        <div className="relative">
          <div className="flex items-center gap-1">
            <input
              type="text"
              value={newTag}
              onChange={(e) => {
                setNewTag(e.target.value);
                setShowTagSuggestions(true);
              }}
              onFocus={() => setShowTagSuggestions(true)}
              onBlur={() => setTimeout(() => setShowTagSuggestions(false), 200)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddTag(newTag);
                }
              }}
              placeholder="输入标签..."
              className="flex-1 bg-neutral-800 border border-neutral-700 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder:text-neutral-500 focus:border-blue-500 focus:outline-none"
            />
            <button
              onClick={() => handleAddTag(newTag)}
              disabled={!newTag.trim()}
              className="p-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-neutral-700 disabled:text-neutral-500 rounded-lg text-white transition-colors"
            >
              <Plus size={14} />
            </button>
          </div>

          {/* 标签建议下拉 */}
          {showTagSuggestions && filteredSuggestions.length > 0 && (
            <div className="absolute left-0 right-0 mt-1 bg-neutral-800 border border-neutral-700 rounded-lg shadow-lg z-10 max-h-24 overflow-y-auto">
              {filteredSuggestions.map((tag) => (
                <button
                  key={tag}
                  onClick={() => handleAddTag(tag)}
                  className="w-full text-left px-2.5 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700"
                >
                  {tag}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 已添加的标签 */}
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {tags.map((tag) => (
              <div
                key={tag}
                className="flex items-center gap-1 px-2 py-0.5 bg-neutral-800 rounded text-xs text-neutral-300 group"
              >
                <span>{tag}</span>
                <button
                  onClick={() => handleRemoveTag(tag)}
                  className="text-neutral-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
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
      <div className="flex items-center gap-2 px-3 py-2 bg-neutral-900 border-b border-neutral-800">
        <Tag size={14} className="text-cyan-500" />
        <span className="text-xs font-medium text-neutral-300">分类与标签</span>
      </div>

      {renderContent()}
    </div>
  );
}