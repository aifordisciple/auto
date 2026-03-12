"use client";

import React, { useState, useEffect } from 'react';
import { templateApi, SkillTemplate, SkillAsset } from '@/lib/api';
import {
  Box, Sparkles, Search, ChevronRight, FileCode, GitBranch, Code,
  Loader2, X, Play, BookOpen, Tag, TrendingUp
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// 模板分类定义
const TEMPLATE_CATEGORIES = [
  { id: 'all', name: '全部模板', icon: <Box size={16} /> },
  { id: 'quality_control', name: '质量控制', icon: <FileCode size={16} /> },
  { id: 'pipeline', name: '流程编排', icon: <GitBranch size={16} /> },
  { id: 'visualization', name: '可视化', icon: <Code size={16} /> },
  { id: 'general', name: '通用', icon: <Code size={16} /> },
];

interface TemplateLibraryProps {
  onSelectTemplate: (template: SkillTemplate) => void;
}

export function TemplateLibrary({ onSelectTemplate }: TemplateLibraryProps) {
  const [templates, setTemplates] = useState<SkillTemplate[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');

  // 加载模板列表
  useEffect(() => {
    loadTemplates();
    loadCategories();
  }, []);

  const loadTemplates = async () => {
    setIsLoading(true);
    try {
      const data = await templateApi.listTemplates();
      setTemplates(data || []);
    } catch (e) {
      console.error('Failed to load templates:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const loadCategories = async () => {
    try {
      const result = await templateApi.getCategories();
      if (result.status === 'success') {
        setCategories(result.data || []);
      }
    } catch (e) {
      console.error('Failed to load categories:', e);
    }
  };

  // 过滤模板
  const filteredTemplates = templates.filter(template => {
    const matchesSearch = !searchQuery ||
      template.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (template.description?.toLowerCase() || '').includes(searchQuery.toLowerCase()) ||
      template.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesCategory = selectedCategory === 'all' || template.category === selectedCategory;

    return matchesSearch && matchesCategory;
  });

  // 获取模板类型图标
  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'Python_env':
        return <Code size={14} className="text-blue-400" />;
      case 'R_env':
        return <Code size={14} className="text-green-400" />;
      case 'Logical_Blueprint':
        return <GitBranch size={14} className="text-purple-400" />;
      case 'Nextflow':
        return <GitBranch size={14} className="text-orange-400" />;
      default:
        return <FileCode size={14} className="text-gray-400" />;
    }
  };

  // 获取模板类型名称
  const getTypeName = (type: string) => {
    switch (type) {
      case 'Python_env':
        return 'Python';
      case 'R_env':
        return 'R';
      case 'Logical_Blueprint':
        return 'Blueprint';
      case 'Nextflow':
        return 'Nextflow';
      default:
        return type;
    }
  };

  return (
    <div className="flex h-full">
      {/* 左侧分类导航 */}
      <div className="w-44 shrink-0 border-r border-gray-200 dark:border-[#2d2d30] bg-gray-50 dark:bg-[#1e1e20] flex flex-col">
        <div className="p-3 border-b border-gray-200 dark:border-neutral-800">
          <span className="text-xs text-gray-500 dark:text-neutral-500 font-medium uppercase tracking-wider">
            分类
          </span>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          {TEMPLATE_CATEGORIES.map(category => {
            const count = category.id === 'all'
              ? templates.length
              : templates.filter(t => t.category === category.id).length;

            return (
              <button
                key={category.id}
                onClick={() => setSelectedCategory(category.id)}
                className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm transition-colors ${
                  selectedCategory === category.id
                    ? 'bg-blue-50 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 border-r-2 border-blue-500'
                    : 'text-gray-600 dark:text-neutral-400 hover:bg-gray-100 dark:hover:bg-neutral-800'
                }`}
              >
                {category.icon}
                <span className="flex-1 truncate">{category.name}</span>
                <span className="text-xs text-gray-400 dark:text-neutral-500">{count}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 右侧模板列表 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 搜索栏 */}
        <div className="p-3 border-b border-gray-200 dark:border-neutral-800 shrink-0">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-neutral-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="搜索模板..."
              className="w-full pl-9 pr-4 py-2 bg-white dark:bg-neutral-800 border border-gray-300 dark:border-neutral-700 rounded-lg text-sm text-gray-700 dark:text-neutral-300 focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>

        {/* 模板列表 */}
        <div className="flex-1 overflow-y-auto p-3">
          {isLoading ? (
            <div className="flex items-center justify-center h-32 text-gray-400 dark:text-neutral-500">
              <Loader2 size={24} className="animate-spin" />
            </div>
          ) : filteredTemplates.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-gray-400 dark:text-neutral-500">
              <Box size={32} className="mb-2 opacity-50" />
              <span className="text-sm">暂无模板</span>
            </div>
          ) : (
            <div className="grid gap-3">
              {filteredTemplates.map(template => (
                <motion.div
                  key={template.template_id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-white dark:bg-neutral-800/50 border border-gray-200 dark:border-neutral-700 rounded-lg p-3 hover:border-blue-300 dark:hover:border-blue-600 cursor-pointer transition-all group"
                  onClick={() => onSelectTemplate(template)}
                >
                  {/* 标题行 */}
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {getTypeIcon(template.template_type)}
                      <h3 className="font-medium text-gray-900 dark:text-white text-sm">
                        {template.name}
                      </h3>
                    </div>
                    <div className="flex items-center gap-2">
                      {template.is_official && (
                        <span className="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-500/30 text-blue-600 dark:text-blue-400 text-[10px] rounded font-medium">
                          官方
                        </span>
                      )}
                      <span className="text-[10px] text-gray-400 dark:text-neutral-500 bg-gray-100 dark:bg-neutral-700 px-1.5 py-0.5 rounded">
                        {getTypeName(template.template_type)}
                      </span>
                    </div>
                  </div>

                  {/* 描述 */}
                  <p className="text-xs text-gray-500 dark:text-neutral-400 line-clamp-2 mb-2">
                    {template.description || '暂无描述'}
                  </p>

                  {/* 底部信息 */}
                  <div className="flex items-center justify-between">
                    {/* 标签 */}
                    <div className="flex items-center gap-1 flex-wrap">
                      {template.tags.slice(0, 3).map(tag => (
                        <span
                          key={tag}
                          className="px-1.5 py-0.5 bg-gray-100 dark:bg-neutral-700 text-gray-500 dark:text-neutral-400 text-[10px] rounded"
                        >
                          {tag}
                        </span>
                      ))}
                      {template.tags.length > 3 && (
                        <span className="text-[10px] text-gray-400 dark:text-neutral-500">
                          +{template.tags.length - 3}
                        </span>
                      )}
                    </div>

                    {/* 使用次数 */}
                    <div className="flex items-center gap-1 text-[10px] text-gray-400 dark:text-neutral-500">
                      <TrendingUp size={12} />
                      <span>{template.usage_count || 0} 次使用</span>
                    </div>
                  </div>

                  {/* 悬浮操作提示 - pointer-events-none 防止阻挡点击 */}
                  <div className="absolute inset-0 bg-blue-500/5 dark:bg-blue-500/10 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center pointer-events-none">
                    <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400 text-sm font-medium pointer-events-none">
                      点击实例化
                      <ChevronRight size={16} />
                    </span>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}