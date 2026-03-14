"use client";

import React, { useState } from 'react';
import { Code, Save, Send, Check, AlertTriangle } from 'lucide-react';

import { useForgeStore } from '@/store/useForgeStore';
import { forgeSessionApi } from '@/lib/api';
import { ParameterSchemaEditor, JsonSchema } from './ParameterSchemaEditor';
import { TestPanel } from './TestPanel';

// 执行器类型配置
const EXECUTOR_TYPES = [
  { value: 'Python_env', label: 'Python 脚本', description: '使用 argparse 参数化' },
  { value: 'R_env', label: 'R 脚本', description: '使用 commandArgs 参数化' },
  { value: 'Logical_Blueprint', label: 'Nextflow 工作流', description: 'DSL2 并行工作流' },
] as const;

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
              onChange={(e) => setExecutorType(e.target.value as any)}
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

      {/* 代码编辑器 */}
      <div className="flex-1 flex flex-col overflow-hidden min-h-0">
        <div className="h-10 bg-neutral-900 flex items-center px-4 border-b border-neutral-800">
          <div className="flex items-center gap-2">
            <Code size={14} className="text-yellow-500" />
            <span className="text-xs text-neutral-400">
              {executorType === 'Logical_Blueprint' ? 'process.nf' : 'main.py / main.R'}
            </span>
          </div>
        </div>

        <textarea
          value={executorType === 'Logical_Blueprint' ? (skillDraft.nextflow_code || '') : skillDraft.script_code}
          onChange={(e) => updateSkillDraft(
            executorType === 'Logical_Blueprint'
              ? { nextflow_code: e.target.value }
              : { script_code: e.target.value }
          )}
          placeholder="AI 生成的代码将显示在这里..."
          className="flex-1 min-h-0 bg-neutral-900 text-green-400 font-mono text-sm p-4 focus:outline-none resize-none leading-relaxed"
          spellCheck={false}
        />
      </div>

      {/* 参数 Schema 编辑器 */}
      <div className="border-t border-neutral-800">
        <ParameterSchemaEditor
          value={skillDraft.parameters_schema || {}}
          onChange={(schema: JsonSchema) => updateSkillDraft({ parameters_schema: schema })}
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