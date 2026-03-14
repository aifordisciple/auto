"use client";

import React, { useState, useMemo, useCallback } from 'react';
import { Code, Save, Send, Check, AlertTriangle, Eye, FileText, Sparkles } from 'lucide-react';
import Editor from '@monaco-editor/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { useForgeStore, ExecutorType } from '@/store/useForgeStore';
import { forgeSessionApi } from '@/lib/api';
import { ParameterSchemaEditor, JsonSchema } from './ParameterSchemaEditor';
import { TestPanel } from './TestPanel';

// 执行器类型配置
const EXECUTOR_TYPES = [
  { value: 'Python_env', label: 'Python 脚本', description: '使用 argparse 参数化', language: 'python' },
  { value: 'R_env', label: 'R 脚本', description: '使用 commandArgs 参数化', language: 'r' },
  { value: 'Logical_Blueprint', label: 'Nextflow 工作流', description: 'DSL2 并行工作流', language: 'groovy' },
] as const;

// 获取 Monaco 语言
const getMonacoLanguage = (executorType: ExecutorType): string => {
  const config = EXECUTOR_TYPES.find(t => t.value === executorType);
  return config?.language || 'python';
};

// 生成 SKILL.md 内容
const generateSkillMd = (
  name: string,
  description: string,
  executorType: ExecutorType,
  parametersSchema: JsonSchema | Record<string, any>,
  expertKnowledge: string
): string => {
  const skillId = name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') || 'unnamed_skill';

  // 生成参数表格
  const generateParameterTable = (): string => {
    const props = parametersSchema?.properties || {};
    const required = new Set(parametersSchema?.required || []);

    if (Object.keys(props).length === 0) {
      return '| 暂无参数定义 | | | | |';
    }

    const rows = Object.entries(props).map(([key, prop]: [string, any]) => {
      const isRequired = required.has(key) ? '是' : '否';
      const type = prop.format === 'file-path' ? 'FilePath' :
                   prop.format === 'directory-path' ? 'DirectoryPath' :
                   prop.enum ? `enum(${prop.enum.join('|')})` :
                   prop.type || 'string';
      const defaultVal = prop.default !== undefined ? String(prop.default) : '-';
      const desc = prop.description || '-';
      return `| ${key} | ${type} | ${isRequired} | ${defaultVal} | ${desc} |`;
    });

    return `| 参数键名 | 数据类型 | 必填 | 默认值 | 描述 |
|---|---|---|---|---|
${rows.join('\n')}`;
  };

  return `---
skill_id: "${skillId}"
name: "${name || '未命名技能'}"
version: "1.0.0"
executor_type: "${executorType}"
category: "自定义"
subcategory: ""
tags: []
---

## 1. 技能意图

${description || '暂无描述'}

## 2. 参数定义

${generateParameterTable()}

## 3. 专家知识

${expertKnowledge || '暂无专家知识'}

## 4. 使用示例

\`\`\`json_strategy
{
  "title": "执行 ${name || '技能'}",
  "description": "${description || '执行自定义分析'}",
  "tool_id": "${skillId}",
  "parameters": {}
}
\`\`\`
`;
};

export function SkillDraftEditor() {
  const {
    sessionId,
    skillDraft,
    updateSkillDraft,
    executorType,
    setExecutorType
  } = useForgeStore();

  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [saveMessage, setSaveMessage] = useState('');
  const [activeTab, setActiveTab] = useState<'code' | 'preview'>('code');
  const [editorTheme, setEditorTheme] = useState<'vs-dark' | 'light'>('vs-dark');
  const [isInferring, setIsInferring] = useState(false);

  // 获取当前代码
  const currentCode = executorType === 'Logical_Blueprint'
    ? (skillDraft.nextflow_code || '')
    : skillDraft.script_code;

  // 生成 SKILL.md 预览内容
  const skillMdContent = useMemo(() => {
    return generateSkillMd(
      skillDraft.name,
      skillDraft.description,
      executorType,
      skillDraft.parameters_schema,
      skillDraft.expert_knowledge
    );
  }, [skillDraft.name, skillDraft.description, executorType, skillDraft.parameters_schema, skillDraft.expert_knowledge]);

  // Monaco Editor 配置
  const editorOptions = useMemo(() => ({
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
  }), []);

  // 代码变更处理
  const handleCodeChange = useCallback((value: string | undefined) => {
    if (value === undefined) return;
    if (executorType === 'Logical_Blueprint') {
      updateSkillDraft({ nextflow_code: value });
    } else {
      updateSkillDraft({ script_code: value });
    }
  }, [executorType, updateSkillDraft]);

  // AI 参数推断
  const handleInferParameters = async () => {
    if (!currentCode || isInferring) return;

    setIsInferring(true);
    try {
      const BASE_URL = typeof window !== 'undefined'
        ? `http://${window.location.hostname}:8000`
        : 'http://localhost:8000';

      const response = await fetch(`${BASE_URL}/api/skills/infer_parameters`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`
        },
        body: JSON.stringify({
          code: currentCode,
          executor_type: executorType
        })
      });

      if (!response.ok) {
        throw new Error('参数推断失败');
      }

      const data = await response.json();
      if (data.parameters_schema) {
        updateSkillDraft({ parameters_schema: data.parameters_schema });
      }
    } catch (error: any) {
      console.error('AI 参数推断失败:', error);
    } finally {
      setIsInferring(false);
    }
  };

  // 保存为私有
  const handleSaveOnly = async () => {
    if (!sessionId || !skillDraft.script_code) return;

    setIsSaving(true);
    setSaveStatus('idle');
    setSaveMessage('');

    try {
      // 先更新草稿
      await forgeSessionApi.updateDraft(sessionId, {
        name: skillDraft.name,
        description: skillDraft.description,
        script_code: skillDraft.script_code,
        parameters_schema: skillDraft.parameters_schema
      });

      // 提交保存
      const result = await forgeSessionApi.commitSkill(sessionId);
      setSaveStatus('success');
      setSaveMessage(`技能已保存！ID: ${result.skill_id}`);
    } catch (error: any) {
      setSaveStatus('error');
      setSaveMessage(error.message || '保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  // 保存并提交审核
  const handleSubmit = async () => {
    if (!sessionId || !skillDraft.script_code) return;

    setIsSaving(true);
    setSaveStatus('idle');
    setSaveMessage('');

    try {
      const result = await forgeSessionApi.submitSkill(sessionId);
      setSaveStatus('success');
      setSaveMessage(`技能已提交审核！ID: ${result.skill_id}`);
    } catch (error: any) {
      setSaveStatus('error');
      setSaveMessage(error.message || '提交失败');
    } finally {
      setIsSaving(false);
    }
  };

  // 测试完成回调
  const handleTestComplete = (result: any) => {
    if (result.success) {
      // 可以在这里添加成功后的处理
    }
  };

  // 代码更新回调（AI 自动修复）
  const handleCodeUpdate = (newCode: string) => {
    updateSkillDraft({ script_code: newCode });
  };

  const hasCode = Boolean(skillDraft.script_code);

  return (
    <div className="flex-1 flex flex-col overflow-hidden relative">
      {/* 基本信息编辑 */}
      <div className="p-4 border-b border-neutral-800 bg-neutral-900/30">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-neutral-500 mb-1 block">技能名称</label>
            <input
              type="text"
              value={skillDraft.name}
              onChange={(e) => updateSkillDraft({ name: e.target.value })}
              placeholder="输入技能名称..."
              className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="text-xs text-neutral-500 mb-1 block">执行器类型</label>
            <select
              value={executorType}
              onChange={(e) => setExecutorType(e.target.value as ExecutorType)}
              className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
            >
              {EXECUTOR_TYPES.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-3">
          <label className="text-xs text-neutral-500 mb-1 block">技能描述</label>
          <input
            type="text"
            value={skillDraft.description}
            onChange={(e) => updateSkillDraft({ description: e.target.value })}
            placeholder="一句话描述技能功能..."
            className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
          />
        </div>
      </div>

      {/* 代码编辑器 + 预览区 */}
      <div className="flex-1 flex flex-col overflow-hidden min-h-0">
        {/* 标签栏 */}
        <div className="h-10 bg-neutral-900 flex items-center justify-between px-4 border-b border-neutral-800">
          <div className="flex items-center gap-2">
            <Code size={14} className="text-yellow-500" />
            <span className="text-xs text-neutral-400">
              {executorType === 'Logical_Blueprint' ? 'process.nf' : 'main.py / main.R'}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setActiveTab('code')}
              className={`flex items-center gap-1 px-3 py-1 text-xs rounded-md transition-colors ${
                activeTab === 'code'
                  ? 'bg-blue-600 text-white'
                  : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
              }`}
            >
              <FileText size={14} />
              代码
            </button>
            <button
              onClick={() => setActiveTab('preview')}
              className={`flex items-center gap-1 px-3 py-1 text-xs rounded-md transition-colors ${
                activeTab === 'preview'
                  ? 'bg-purple-600 text-white'
                  : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
              }`}
            >
              <Eye size={14} />
              SKILL.md 预览
            </button>
          </div>
        </div>

        {/* 内容区域 */}
        {activeTab === 'code' ? (
          <div className="flex-1 min-h-0">
            <Editor
              height="100%"
              language={getMonacoLanguage(executorType)}
              value={currentCode}
              onChange={handleCodeChange}
              theme={editorTheme}
              options={editorOptions}
              loading={
                <div className="flex items-center justify-center h-full text-neutral-500">
                  <div className="animate-spin mr-2">
                    <Code size={20} />
                  </div>
                  加载编辑器...
                </div>
              }
            />
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-auto p-4 bg-neutral-900/50">
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // 自定义代码块渲染
                  code({ className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const isInline = !match;
                    if (isInline) {
                      return (
                        <code className="bg-neutral-700 px-1.5 py-0.5 rounded text-sm text-emerald-400" {...props}>
                          {children}
                        </code>
                      );
                    }
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  },
                  // 表格样式
                  table({ children }) {
                    return (
                      <div className="overflow-x-auto my-4">
                        <table className="min-w-full border-collapse border border-neutral-700 text-sm">
                          {children}
                        </table>
                      </div>
                    );
                  },
                  th({ children }) {
                    return (
                      <th className="border border-neutral-700 bg-neutral-800 px-3 py-2 text-left text-neutral-300 font-medium">
                        {children}
                      </th>
                    );
                  },
                  td({ children }) {
                    return (
                      <td className="border border-neutral-700 px-3 py-2 text-neutral-400">
                        {children}
                      </td>
                    );
                  },
                  // 标题样式
                  h2({ children }) {
                    return (
                      <h2 className="text-lg font-semibold text-white mt-6 mb-3 pb-2 border-b border-neutral-700">
                        {children}
                      </h2>
                    );
                  },
                  // 段落样式
                  p({ children }) {
                    return <p className="text-neutral-300 leading-relaxed my-2">{children}</p>;
                  },
                }}
              >
                {skillMdContent}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </div>

      {/* 参数 Schema 编辑器 */}
      <div className="border-t border-neutral-800">
        <ParameterSchemaEditor
          value={skillDraft.parameters_schema || {}}
          onChange={(schema: JsonSchema) => updateSkillDraft({ parameters_schema: schema })}
          onAiInfer={handleInferParameters}
          isInfering={isInferring}
          showJsonPreview={true}
          defaultExpanded={Object.keys(skillDraft.parameters_schema?.properties || {}).length > 0}
        />
      </div>

      {/* 增强版测试面板 */}
      <div className="border-t border-neutral-800">
        <TestPanel
          scriptCode={executorType === 'Logical_Blueprint' ? (skillDraft.nextflow_code || '') : skillDraft.script_code}
          parametersSchema={skillDraft.parameters_schema}
          executorType={executorType}
          onTestComplete={handleTestComplete}
          onCodeUpdate={handleCodeUpdate}
          disabled={!hasCode}
        />
      </div>

      {/* 底部操作按钮 */}
      <div className="p-3 border-t border-neutral-800 flex gap-2">
        <button
          onClick={handleSaveOnly}
          disabled={isSaving || !hasCode}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-neutral-700 hover:bg-neutral-600 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
        >
          <Save size={16} />
          保存为私有
        </button>
        <button
          onClick={handleSubmit}
          disabled={isSaving || !hasCode}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
        >
          <Send size={16} />
          保存并提交审核
        </button>
      </div>

      {/* 状态提示 */}
      {saveStatus === 'success' && (
        <div className="absolute top-2 right-2 bg-emerald-500/20 text-emerald-400 px-3 py-1 rounded-lg text-xs flex items-center gap-1 z-10">
          <Check size={14} /> {saveMessage}
        </div>
      )}
      {saveStatus === 'error' && (
        <div className="absolute top-2 right-2 bg-red-500/20 text-red-400 px-3 py-1 rounded-lg text-xs flex items-center gap-1 z-10">
          <AlertTriangle size={14} /> {saveMessage}
        </div>
      )}
    </div>
  );
}