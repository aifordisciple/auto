/**
 * 专家知识编辑器组件
 *
 * 功能：
 * - 结构化分区编辑（参数说明、使用建议、注意事项、示例数据）
 * - Markdown 实时预览
 * - AI 辅助生成
 */

'use client';

import React, { useState, useCallback } from 'react';
import { BookOpen, Sparkles, Eye, Edit3, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BASE_URL } from '@/lib/api';

interface ExpertKnowledgeEditorProps {
  value: string;
  onChange: (value: string) => void;
  code?: string;
  executorType?: string;
  /** 内嵌模式：不显示标题栏，用于嵌入父级折叠面板 */
  showHeader?: boolean;
}

// 专家知识模板
const KNOWLEDGE_TEMPLATES = {
  parameters: `## 参数说明

- **input_path**: 输入文件路径，支持 FASTQ/BAM/VCF 等格式
- **output_dir**: 输出目录，所有结果将保存在此目录
- **threads**: 线程数，默认为 4
- **quality_threshold**: 质量阈值，默认为 20`,

  usage: `## 使用建议

1. 在执行前，请确保输入文件格式正确
2. 建议先使用小规模数据测试
3. 输出目录需要有足够的存储空间
4. 对于大数据集，建议增加线程数`,

  notes: `## 注意事项

- 确保输入文件存在且可读
- 输出目录不存在时会自动创建
- 执行过程中请勿中断
- 如遇错误，请检查日志文件`,

  example: `## 示例数据

\`\`\`json
{
  "input_path": "/data/sample.fastq",
  "output_dir": "/results/sample",
  "threads": 8
}
\`\`\``
};

export function ExpertKnowledgeEditor({ value, onChange, code, executorType, showHeader = true }: ExpertKnowledgeEditorProps) {
  const [activeTab, setActiveTab] = useState<'edit' | 'preview'>('edit');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);

  // AI 生成专家知识
  const handleAiGenerate = useCallback(async () => {
    if (!code || isGenerating) return;

    setIsGenerating(true);
    try {
      const response = await fetch(`${BASE_URL}/api/ai/generate_expert_knowledge`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        },
        body: JSON.stringify({
          code,
          executor_type: executorType
        })
      });

      if (!response.ok) {
        throw new Error('AI 生成失败');
      }

      const data = await response.json();
      if (data.expert_knowledge) {
        onChange(data.expert_knowledge);
      }
    } catch (error) {
      console.error('AI 生成专家知识失败:', error);
      // 使用模板作为后备
      const template = `${KNOWLEDGE_TEMPLATES.parameters}\n\n${KNOWLEDGE_TEMPLATES.usage}`;
      onChange(template);
    } finally {
      setIsGenerating(false);
    }
  }, [code, executorType, isGenerating, onChange]);

  // 插入模板
  const handleInsertTemplate = (templateKey: keyof typeof KNOWLEDGE_TEMPLATES) => {
    const template = KNOWLEDGE_TEMPLATES[templateKey];
    onChange(value ? `${value}\n\n${template}` : template);
    setShowTemplates(false);
  };

  // 内嵌模式：不显示标题栏，只有内容区域
  if (!showHeader) {
    return (
      <div className="relative">
        {/* 工具栏 */}
        <div className="flex items-center gap-1 mb-2">
          <button
            onClick={() => setShowTemplates(!showTemplates)}
            className="px-2 py-1 text-xs text-neutral-400 hover:text-white hover:bg-neutral-800 rounded transition-colors"
          >
            模板
          </button>
          <button
            onClick={handleAiGenerate}
            disabled={isGenerating || !code}
            className="flex items-center gap-1 px-2 py-1 text-xs text-purple-400 hover:text-purple-300 hover:bg-purple-500/10 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGenerating ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                生成中...
              </>
            ) : (
              <>
                <Sparkles size={12} />
                AI 生成
              </>
            )}
          </button>
          <div className="w-px h-4 bg-neutral-700 mx-1" />
          <button
            onClick={() => setActiveTab('edit')}
            className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
              activeTab === 'edit' ? 'bg-blue-600 text-white' : 'text-neutral-400 hover:text-white'
            }`}
          >
            <Edit3 size={12} />
            编辑
          </button>
          <button
            onClick={() => setActiveTab('preview')}
            className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
              activeTab === 'preview' ? 'bg-purple-600 text-white' : 'text-neutral-400 hover:text-white'
            }`}
          >
            <Eye size={12} />
            预览
          </button>
        </div>

        {/* 模板选择下拉 */}
        {showTemplates && (
          <div className="absolute left-0 top-8 w-48 bg-neutral-800 border border-neutral-700 rounded-lg shadow-lg z-10">
            <div className="p-2 space-y-1">
              <button
                onClick={() => handleInsertTemplate('parameters')}
                className="w-full text-left px-2 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700 rounded"
              >
                📝 参数说明
              </button>
              <button
                onClick={() => handleInsertTemplate('usage')}
                className="w-full text-left px-2 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700 rounded"
              >
                💡 使用建议
              </button>
              <button
                onClick={() => handleInsertTemplate('notes')}
                className="w-full text-left px-2 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700 rounded"
              >
                ⚠️ 注意事项
              </button>
              <button
                onClick={() => handleInsertTemplate('example')}
                className="w-full text-left px-2 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700 rounded"
              >
                📊 示例数据
              </button>
            </div>
          </div>
        )}

        {/* 内容区域 */}
        {activeTab === 'edit' ? (
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="输入专家知识，支持 Markdown 格式...

示例：
## 参数说明
- input_path: 输入文件路径

## 使用建议
建议在执行前检查数据质量..."
            className="w-full h-32 px-3 py-2 bg-neutral-950 text-sm text-neutral-300 resize-none focus:outline-none placeholder:text-neutral-600 border border-neutral-800 rounded-lg"
          />
        ) : (
          <div className="h-32 overflow-y-auto p-3 bg-neutral-950 border border-neutral-800 rounded-lg custom-scrollbar">
            {value ? (
              <div className="prose prose-invert prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {value}
                </ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm text-neutral-600">暂无专家知识</p>
            )}
          </div>
        )}
      </div>
    );
  }

  // 带标题栏模式（默认）
  return (
    <div className="border border-neutral-800 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-neutral-900 border-b border-neutral-800">
        <div className="flex items-center gap-2">
          <BookOpen size={14} className="text-amber-500" />
          <span className="text-xs font-medium text-neutral-300">专家知识</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowTemplates(!showTemplates)}
            className="px-2 py-1 text-xs text-neutral-400 hover:text-white hover:bg-neutral-800 rounded transition-colors"
          >
            模板
          </button>
          <button
            onClick={handleAiGenerate}
            disabled={isGenerating || !code}
            className="flex items-center gap-1 px-2 py-1 text-xs text-purple-400 hover:text-purple-300 hover:bg-purple-500/10 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGenerating ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                生成中...
              </>
            ) : (
              <>
                <Sparkles size={12} />
                AI 生成
              </>
            )}
          </button>
          <div className="w-px h-4 bg-neutral-700 mx-1" />
          <button
            onClick={() => setActiveTab('edit')}
            className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
              activeTab === 'edit' ? 'bg-blue-600 text-white' : 'text-neutral-400 hover:text-white'
            }`}
          >
            <Edit3 size={12} />
            编辑
          </button>
          <button
            onClick={() => setActiveTab('preview')}
            className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
              activeTab === 'preview' ? 'bg-purple-600 text-white' : 'text-neutral-400 hover:text-white'
            }`}
          >
            <Eye size={12} />
            预览
          </button>
        </div>
      </div>

      {/* 模板选择下拉 */}
      {showTemplates && (
        <div className="absolute right-4 mt-1 w-48 bg-neutral-800 border border-neutral-700 rounded-lg shadow-lg z-10">
          <div className="p-2 space-y-1">
            <button
              onClick={() => handleInsertTemplate('parameters')}
              className="w-full text-left px-2 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700 rounded"
            >
              📝 参数说明
            </button>
            <button
              onClick={() => handleInsertTemplate('usage')}
              className="w-full text-left px-2 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700 rounded"
            >
              💡 使用建议
            </button>
            <button
              onClick={() => handleInsertTemplate('notes')}
              className="w-full text-left px-2 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700 rounded"
            >
              ⚠️ 注意事项
            </button>
            <button
              onClick={() => handleInsertTemplate('example')}
              className="w-full text-left px-2 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700 rounded"
            >
              📊 示例数据
            </button>
          </div>
        </div>
      )}

      {/* Content */}
      {activeTab === 'edit' ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="输入专家知识，支持 Markdown 格式...

示例：
## 参数说明
- input_path: 输入文件路径

## 使用建议
建议在执行前检查数据质量..."
          className="w-full h-32 px-3 py-2 bg-neutral-950 text-sm text-neutral-300 resize-none focus:outline-none placeholder:text-neutral-600"
        />
      ) : (
        <div className="h-32 overflow-y-auto p-3 bg-neutral-950 custom-scrollbar">
          {value ? (
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {value}
              </ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm text-neutral-600">暂无专家知识</p>
          )}
        </div>
      )}
    </div>
  );
}