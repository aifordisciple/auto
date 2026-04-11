'use client';

import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import dynamic from 'next/dynamic';
import { Code, Save, Send, Check, AlertTriangle, Settings2, BookOpen, Package, Tag, FlaskConical, History, FileEdit } from 'lucide-react';
import { Panel, Group, Separator } from 'react-resizable-panels';

import { useForgeStore, ExecutorType } from '@/store/useForgeStore';
import { forgeSessionApi, skillForgeApi } from '@/lib/api';
import { ParameterSchemaEditor, JsonSchema } from './ParameterSchemaEditor';
import { TestPanel } from './TestPanel';
import { ExpertKnowledgeEditor } from './ExpertKnowledgeEditor';
import { DependenciesEditor } from './DependenciesEditor';
import { CategoryTagsEditor } from './CategoryTagsEditor';
import { VersionHistoryPanel } from './VersionHistoryPanel';
import { SkillFileTree } from './SkillFileTree';
import { SkillEditorMain } from './SkillEditorMain';

// Simple console log wrapper
const log = {
  info: (...args: any[]) => console.log('[SkillDraftEditor]', ...args),
  warn: (...args: any[]) => console.warn('[SkillDraftEditor]', ...args),
  error: (...args: any[]) => console.error('[SkillDraftEditor]', ...args),
};

// 执行器类型配置
const EXECUTOR_TYPES = [
  { value: 'Python_env', label: 'Python 脚本', description: '使用 argparse 参数化', language: 'python' },
  { value: 'R_env', label: 'R 脚本', description: '使用 commandArgs 参数化', language: 'r' },
  { value: 'Logical_Blueprint', label: 'Nextflow 工作流', description: 'DSL2 并行工作流', language: 'groovy' },
] as const;

// 编辑器 Tab 类型
type EditorTabType = 'editor' | 'config' | 'metadata' | 'test';

// 编辑器 Tab 配置
const EDITOR_TABS: { id: EditorTabType; label: string; icon: React.ReactNode; color: string }[] = [
  { id: 'editor', label: '编辑', icon: <Code size={14} />, color: 'blue' },
  { id: 'config', label: '配置', icon: <Settings2 size={14} />, color: 'green' },
  { id: 'metadata', label: '元数据', icon: <BookOpen size={14} />, color: 'purple' },
  { id: 'test', label: '测试', icon: <FlaskConical size={14} />, color: 'orange' },
];

export function SkillDraftEditor() {
  const {
    sessionId,
    skillDraft,
    updateSkillDraft,
    executorType,
    setExecutorType,
    refreshSessionList,
    skillId,
    setSkillId,
    skillVersion,
    setSkillVersion,
    skillFiles,
    initSkillFiles
  } = useForgeStore();

  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [saveMessage, setSaveMessage] = useState('');
  const [isInferring, setIsInferring] = useState(false);
  const hasUnsavedChanges = useRef(false);
  const autoSaveTimerRef = useRef<NodeJS.Timeout | null>(null);

  // ==========================================
  // Tab 状态管理
  // ==========================================
  const [activeEditorTab, setActiveEditorTab] = useState<EditorTabType>('editor');

  // ==========================================
  // 文件系统初始化说明
  // ==========================================
  // 注意：文件系统的初始化由 ForgePanel 和 useForgeStore.loadSession 负责
  // 这里不再自动初始化，避免覆盖从会话加载或编辑技能时设置的数据
  //
  // 之前的实现：
  // useEffect(() => {
  //   if (skillFiles.length === 0) {
  //     initSkillFiles();  // ❌ 这会在编辑技能时覆盖正确设置的数据
  //   }
  // }, []);
  //
  // 问题：当从"我的"标签页编辑技能时，这个 useEffect 可能在 ForgePanel 的
  // setExecutorType 完成之前执行，导致用空的 skillDraft 初始化文件系统

  // ==========================================
  // 自动保存功能
  // ==========================================

  // 标记草稿有未保存的更改
  const markUnsaved = useCallback(() => {
    hasUnsavedChanges.current = true;
  }, []);

  // 自动保存函数
  const autoSaveDraft = useCallback(async () => {
    if (!sessionId || !hasUnsavedChanges.current) return;

    try {
      await forgeSessionApi.updateDraft(sessionId, {
        name: skillDraft.name,
        description: skillDraft.description,
        executor_type: skillDraft.executor_type,
        script_code: skillDraft.script_code,
        nextflow_code: skillDraft.nextflow_code,
        parameters_schema: skillDraft.parameters_schema,
        expert_knowledge: skillDraft.expert_knowledge,
        dependencies: skillDraft.dependencies
      });
      hasUnsavedChanges.current = false;
      log.info('[AutoSave] 草稿已自动保存');
    } catch (error) {
      console.error('[AutoSave] 自动保存失败:', error);
    }
  }, [sessionId, skillDraft]);

  // 监听草稿变化，触发自动保存（防抖 5 秒）
  useEffect(() => {
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }

    autoSaveTimerRef.current = setTimeout(() => {
      if (hasUnsavedChanges.current) {
        autoSaveDraft();
      }
    }, 5000);

    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
      }
    };
  }, [skillDraft, autoSaveDraft]);

  // 页面离开时自动保存
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges.current) {
        // 触发自动保存
        autoSaveDraft();
        // 显示确认对话框
        e.preventDefault();
        e.returnValue = '您有未保存的更改，确定要离开吗？';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      // 组件卸载时保存
      if (hasUnsavedChanges.current) {
        autoSaveDraft();
      }
    };
  }, [autoSaveDraft]);

  // 监听草稿更新，标记未保存
  useEffect(() => {
    markUnsaved();
  }, [skillDraft, markUnsaved]);

  // 计算参数数量
  const paramCount = useMemo(() => {
    const props = skillDraft.parameters_schema?.properties || {};
    return Object.keys(props).length;
  }, [skillDraft.parameters_schema]);

  // 获取当前代码（用于 AI 参数推断）
  const currentCode = executorType === 'Logical_Blueprint'
    ? (skillDraft.nextflow_code || '')
    : skillDraft.script_code;

  // AI 参数推断
  const handleInferParameters = async () => {
    if (!currentCode || isInferring) return;

    setIsInferring(true);
    try {
      const BASE_URL = typeof window !== 'undefined'
        ? `http://${window.location.hostname}:8000`
        : 'http://localhost:8000';

      const response = await fetch(`${BASE_URL}/api/skills/forge/infer_parameters`, {
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

      if (!response.ok) throw new Error('参数推断失败');

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

  // 保存草稿
  const handleSaveDraft = async () => {
    const hasValidCode = executorType === 'Logical_Blueprint'
      ? Boolean(skillDraft.nextflow_code)
      : Boolean(skillDraft.script_code);

    if (!sessionId || !hasValidCode) return;

    setIsSaving(true);
    setSaveStatus('idle');
    setSaveMessage('');

    try {
      await forgeSessionApi.updateDraft(sessionId, {
        name: skillDraft.name,
        description: skillDraft.description,
        executor_type: skillDraft.executor_type,
        script_code: skillDraft.script_code,
        nextflow_code: skillDraft.nextflow_code,
        parameters_schema: skillDraft.parameters_schema,
        expert_knowledge: skillDraft.expert_knowledge,
        dependencies: skillDraft.dependencies
      });

      const result = await forgeSessionApi.commitSkill(sessionId);

      // 更新本地 skillId 状态，确保后续保存时更新而非创建新记录
      setSkillId(result.skill_id);
      hasUnsavedChanges.current = false;

      setSaveStatus('success');
      setSaveMessage(`草稿已保存！ID: ${result.skill_id}`);

      // 发送事件通知其他组件刷新
      window.dispatchEvent(new CustomEvent('skill-saved', {
        detail: { skill_id: result.skill_id, name: result.name, is_draft: true }
      }));

      // 刷新会话列表
      refreshSessionList();
    } catch (error: any) {
      setSaveStatus('error');
      setSaveMessage(error.message || '保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  // 保存并提交审核
  const handleSubmit = async () => {
    const hasValidCode = executorType === 'Logical_Blueprint'
      ? Boolean(skillDraft.nextflow_code)
      : Boolean(skillDraft.script_code);

    if (!sessionId || !hasValidCode) return;

    setIsSaving(true);
    setSaveStatus('idle');
    setSaveMessage('');

    try {
      await forgeSessionApi.updateDraft(sessionId, {
        name: skillDraft.name,
        description: skillDraft.description,
        executor_type: skillDraft.executor_type,
        script_code: skillDraft.script_code,
        nextflow_code: skillDraft.nextflow_code,
        parameters_schema: skillDraft.parameters_schema,
        expert_knowledge: skillDraft.expert_knowledge,
        dependencies: skillDraft.dependencies
      });

      const result = await forgeSessionApi.submitSkill(sessionId);

      // ✨ 更新本地 skillId 状态，确保后续保存时更新而非创建新记录
      setSkillId(result.skill_id);

      setSaveStatus('success');
      setSaveMessage(`技能已提交审核！ID: ${result.skill_id}`);

      // ✨ 发送事件通知其他组件刷新
      window.dispatchEvent(new CustomEvent('skill-saved', {
        detail: { skill_id: result.skill_id, name: result.name }
      }));

      // ✨ 刷新会话列表
      refreshSessionList();
    } catch (error: any) {
      setSaveStatus('error');
      setSaveMessage(error.message || '提交失败');
    } finally {
      setIsSaving(false);
    }
  };

  // ==========================================
  // 保存更新（编辑已有技能时使用）
  // ==========================================
  const handleSaveUpdate = async () => {
    if (!skillId) return;

    const hasValidCode = executorType === 'Logical_Blueprint'
      ? Boolean(skillDraft.nextflow_code)
      : Boolean(skillDraft.script_code);

    if (!hasValidCode) return;

    setIsSaving(true);
    setSaveStatus('idle');
    setSaveMessage('');

    try {
      // 直接更新已有技能
      const result = await skillForgeApi.updateSkill(skillId, {
        name: skillDraft.name,
        description: skillDraft.description,
        executor_type: skillDraft.executor_type,
        script_code: skillDraft.script_code,
        nextflow_code: skillDraft.nextflow_code,
        parameters_schema: skillDraft.parameters_schema,
        expert_knowledge: skillDraft.expert_knowledge,
        dependencies: skillDraft.dependencies,
        category: skillDraft.category,
        subcategory: skillDraft.subcategory,
        tags: skillDraft.tags,
      });

      hasUnsavedChanges.current = false;

      setSaveStatus('success');
      setSaveMessage(`技能已更新！`);

      // 发送事件通知其他组件刷新
      window.dispatchEvent(new CustomEvent('skill-saved', {
        detail: { skill_id: skillId, name: skillDraft.name, is_update: true }
      }));

      // 刷新会话列表
      refreshSessionList();
    } catch (error: any) {
      setSaveStatus('error');
      setSaveMessage(error.message || '更新失败');
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

  const hasCode = executorType === 'Logical_Blueprint'
    ? Boolean(skillDraft.nextflow_code)
    : Boolean(skillDraft.script_code);

  // Tab 颜色映射
  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-600 text-white',
    green: 'bg-green-600 text-white',
    purple: 'bg-purple-600 text-white',
    orange: 'bg-orange-600 text-white',
    gray: 'bg-neutral-600 text-white',
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 h-full overflow-hidden">
      {/* ========== Tab 切换栏 ========== */}
      <div className="shrink-0 border-b border-neutral-800 px-3 py-2 bg-neutral-900/40">
        <div className="flex items-center bg-neutral-800/50 rounded-lg p-1">
          {EDITOR_TABS.map((tab) => {
            const isActive = activeEditorTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveEditorTab(tab.id)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  isActive
                    ? colorClasses[tab.color] + ' shadow-md'
                    : 'text-neutral-400 hover:text-white'
                }`}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ========== Tab 内容区域 ========== */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {/* 编辑 Tab - 代码编辑器 */}
        {activeEditorTab === 'editor' && (
          <div className="h-full">
            <Group orientation="horizontal" className="h-full">
              {/* 左侧：文件树 */}
              <Panel defaultSize="25%" minSize="20%" maxSize="40%">
                <SkillFileTree />
              </Panel>

              {/* 分隔条 */}
              <Separator className="w-1 bg-neutral-700 hover:bg-blue-500 transition-colors cursor-col-resize" />

              {/* 右侧：编辑器 */}
              <Panel defaultSize="75%">
                <SkillEditorMain />
              </Panel>
            </Group>
          </div>
        )}

        {/* 配置 Tab - 基本信息 + 参数定义 */}
        {activeEditorTab === 'config' && (
          <div className="h-full overflow-y-auto custom-scrollbar p-3 flex flex-col gap-4">
            {/* 基本信息 */}
            <div className="bg-neutral-800/50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3 text-neutral-300">
                <Settings2 size={14} />
                <span className="text-sm font-medium">基本信息</span>
              </div>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
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
                <div>
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
            </div>

            {/* 参数定义 */}
            <div className="bg-neutral-800/50 rounded-lg p-4 flex-1">
              <div className="flex items-center gap-2 mb-3 text-neutral-300">
                <Settings2 size={14} />
                <span className="text-sm font-medium">参数定义</span>
                {paramCount > 0 && (
                  <span className="ml-2 px-2 py-0.5 bg-green-600/20 text-green-400 rounded text-xs">
                    {paramCount} 个参数
                  </span>
                )}
              </div>
              <ParameterSchemaEditor
                value={skillDraft.parameters_schema || {}}
                onChange={(schema: JsonSchema) => updateSkillDraft({ parameters_schema: schema })}
                onAiInfer={handleInferParameters}
                isInfering={isInferring}
                showJsonPreview={true}
                defaultExpanded={true}
                showHeader={false}
                maxHeight="none"
              />
            </div>
          </div>
        )}

        {/* 元数据 Tab - 专家知识 + 依赖管理 + 分类与标签 */}
        {activeEditorTab === 'metadata' && (
          <div className="h-full overflow-y-auto custom-scrollbar p-3 flex flex-col gap-4">
            {/* 专家知识 */}
            <div className="bg-neutral-800/50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3 text-neutral-300">
                <BookOpen size={14} />
                <span className="text-sm font-medium">专家知识</span>
              </div>
              <ExpertKnowledgeEditor
                value={skillDraft.expert_knowledge || ''}
                onChange={(value) => updateSkillDraft({ expert_knowledge: value })}
                code={currentCode}
                executorType={executorType}
                showHeader={false}
              />
            </div>

            {/* 依赖管理 */}
            <div className="bg-neutral-800/50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3 text-neutral-300">
                <Package size={14} />
                <span className="text-sm font-medium">依赖管理</span>
                {(skillDraft.dependencies?.length || 0) > 0 && (
                  <span className="ml-2 px-2 py-0.5 bg-blue-600/20 text-blue-400 rounded text-xs">
                    {skillDraft.dependencies?.length} 个依赖
                  </span>
                )}
              </div>
              <DependenciesEditor
                value={skillDraft.dependencies || []}
                onChange={(deps) => updateSkillDraft({ dependencies: deps })}
                executorType={executorType}
                showHeader={false}
              />
            </div>

            {/* 分类与标签 */}
            <div className="bg-neutral-800/50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3 text-neutral-300">
                <Tag size={14} />
                <span className="text-sm font-medium">分类与标签</span>
              </div>
              <CategoryTagsEditor
                category={skillDraft.category}
                subcategory={skillDraft.subcategory}
                tags={skillDraft.tags || []}
                onChange={(data) => updateSkillDraft(data)}
                showHeader={false}
              />
            </div>
          </div>
        )}

        {/* 测试 Tab - 测试运行 + 版本历史 */}
        {activeEditorTab === 'test' && (
          <div className="h-full overflow-y-auto custom-scrollbar p-3 flex flex-col gap-4">
            {/* 测试面板 */}
            <div className="bg-neutral-800/50 rounded-lg p-4 flex-1">
              <div className="flex items-center gap-2 mb-3 text-neutral-300">
                <FlaskConical size={14} />
                <span className="text-sm font-medium">测试运行</span>
                {hasCode && (
                  <span className="ml-2 px-2 py-0.5 bg-green-600/20 text-green-400 rounded text-xs">
                    代码就绪
                  </span>
                )}
              </div>
              <TestPanel
                scriptCode={executorType === 'Logical_Blueprint' ? (skillDraft.nextflow_code || '') : skillDraft.script_code}
                parametersSchema={skillDraft.parameters_schema}
                executorType={executorType}
                onTestComplete={handleTestComplete}
                onCodeUpdate={handleCodeUpdate}
                disabled={!hasCode}
                showHeader={false}
              />
            </div>

            {/* 版本历史 */}
            {skillId && (
              <div className="bg-neutral-800/50 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3 text-neutral-300">
                  <History size={14} />
                  <span className="text-sm font-medium">版本历史</span>
                </div>
                <VersionHistoryPanel
                  skillId={skillId}
                  skillName={skillDraft.name || '未命名技能'}
                  currentVersion={skillVersion}
                  isOwner={true}
                  onRollback={() => {
                    if (sessionId) {
                      forgeSessionApi.getSession(sessionId).then((data: any) => {
                        if (data.skill_draft) {
                          updateSkillDraft(data.skill_draft);
                        }
                      });
                    }
                  }}
                  onVersionCreated={() => {
                    setSkillVersion('1.0.0');
                  }}
                />
              </div>
            )}
          </div>
        )}
      </div>

      {/* ========== 底部操作按钮 ========== */}
      <div className="shrink-0 bg-neutral-900/90 backdrop-blur-sm p-3 border-t border-neutral-800 flex gap-2">
        {/* 编辑模式：显示"保存更新"按钮 */}
        {skillId ? (
          <>
            <button
              onClick={handleSaveUpdate}
              disabled={isSaving || !hasCode}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
            >
              <Save size={16} />
              保存更新
            </button>
            <button
              onClick={handleSubmit}
              disabled={isSaving || !hasCode}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
            >
              <Send size={16} />
              提交审核
            </button>
          </>
        ) : (
          <>
            {/* 新建模式：显示"保存草稿"和"提交审核"按钮 */}
            <button
              onClick={handleSaveDraft}
              disabled={isSaving || !hasCode}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-neutral-700 hover:bg-neutral-600 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
            >
              <FileEdit size={16} />
              保存草稿
            </button>
            <button
              onClick={handleSubmit}
              disabled={isSaving || !hasCode}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm rounded-lg transition-colors"
            >
              <Send size={16} />
              提交审核
            </button>
          </>
        )}
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