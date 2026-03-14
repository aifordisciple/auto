"use client";

import React, { useState, useEffect } from 'react';
import { templateApi, SkillTemplate, InstantiateRequest, CraftResponse } from '@/lib/api';
import {
  X, Box, Code, GitBranch, FileCode, Play, Loader2, CheckCircle, AlertTriangle,
  BookOpen, Tag, TrendingUp, FileJson, Sparkles
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface TemplateDetailModalProps {
  template: SkillTemplate;
  onClose: () => void;
  onInstantiate: (skillData: CraftResponse) => void;
}

export function TemplateDetailModal({ template, onClose, onInstantiate }: TemplateDetailModalProps) {
  const [activeTab, setActiveTab] = useState<'params' | 'code' | 'knowledge'>('params');
  const [skillName, setSkillName] = useState('');
  const [isInstantiating, setIsInstantiating] = useState(false);

  // 获取模板类型图标
  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'Python_env':
        return <Code size={16} className="text-blue-400" />;
      case 'R_env':
        return <Code size={16} className="text-green-400" />;
      case 'Logical_Blueprint':
        return <GitBranch size={16} className="text-purple-400" />;
      case 'Nextflow':
        return <GitBranch size={16} className="text-orange-400" />;
      default:
        return <FileCode size={16} className="text-gray-400" />;
    }
  };

  // 获取模板类型名称
  const getTypeName = (type: string) => {
    switch (type) {
      case 'Python_env':
        return 'Python 脚本';
      case 'R_env':
        return 'R 脚本';
      case 'Logical_Blueprint':
        return 'Blueprint 流程';
      case 'Nextflow':
        return 'Nextflow 工作流';
      default:
        return type;
    }
  };

  // 实例化模板
  const handleInstantiate = async () => {
    setIsInstantiating(true);
    try {
      const request: InstantiateRequest = {
        skill_name: skillName || `${template.name}_${Date.now().toString(36)}`,
      };

      const result = await templateApi.instantiateTemplate(template.template_id, request);

      // 转换为 CraftResponse 格式
      const skillData: CraftResponse = {
        name: result.name,
        description: template.description || '',
        executor_type: result.executor_type as any,
        parameters_schema: result.parameters_schema,
        expert_knowledge: result.expert_knowledge || '',
        script_code: result.script_code ?? undefined,
        dependencies: result.dependencies,
        validation_passed: true,
      };

      onInstantiate(skillData);
      onClose();
    } catch (e: any) {
      alert(`实例化失败: ${e.message}`);
    } finally {
      setIsInstantiating(false);
    }
  };

  // 渲染参数 Schema
  const renderParametersSchema = () => {
    const schema = template.parameters_schema;
    if (!schema?.properties) {
      return (
        <div className="text-center py-8 text-gray-400 dark:text-neutral-500">
          <FileJson size={32} className="mx-auto mb-2 opacity-50" />
          <p className="text-sm">暂无参数定义</p>
        </div>
      );
    }

    const properties = schema.properties;
    const required = schema.required || [];

    return (
      <div className="space-y-2">
        <div className="grid grid-cols-12 gap-2 text-xs font-medium text-gray-500 dark:text-neutral-500 border-b border-gray-200 dark:border-neutral-700 pb-2 mb-3">
          <div className="col-span-3">参数名</div>
          <div className="col-span-2">类型</div>
          <div className="col-span-1">必填</div>
          <div className="col-span-6">描述</div>
        </div>
        {Object.entries(properties).map(([key, prop]: [string, any]) => (
          <div key={key} className="grid grid-cols-12 gap-2 text-xs py-2 border-b border-gray-100 dark:border-neutral-800">
            <div className="col-span-3 font-mono text-blue-600 dark:text-blue-400">{key}</div>
            <div className="col-span-2 text-gray-600 dark:text-neutral-400">
              {prop.format || prop.type}
            </div>
            <div className="col-span-1">
              {required.includes(key) ? (
                <span className="text-red-500">*</span>
              ) : (
                <span className="text-gray-400">-</span>
              )}
            </div>
            <div className="col-span-6 text-gray-500 dark:text-neutral-500">
              {prop.description || '-'}
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center cursor-pointer"
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          onClick={e => e.stopPropagation()}
          className="bg-white dark:bg-[#1e1e20] rounded-xl shadow-2xl w-[800px] max-h-[85vh] flex flex-col overflow-hidden cursor-default"
        >
          {/* 头部 */}
          <div className="flex items-start justify-between p-4 border-b border-gray-200 dark:border-neutral-800">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                {getTypeIcon(template.template_type)}
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {template.name}
                </h2>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-neutral-500">
                <span>{getTypeName(template.template_type)}</span>
                <span>·</span>
                <span>{template.category_name}</span>
                {template.is_official && (
                  <>
                    <span>·</span>
                    <span className="text-blue-500">官方模板</span>
                  </>
                )}
                <span>·</span>
                <span className="flex items-center gap-1">
                  <TrendingUp size={12} />
                  {template.usage_count || 0} 次使用
                </span>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
            >
              <X size={18} />
            </button>
          </div>

          {/* 描述 */}
          <div className="px-4 py-3 bg-gray-50 dark:bg-neutral-800/50 border-b border-gray-200 dark:border-neutral-800">
            <p className="text-sm text-gray-600 dark:text-neutral-300">
              {template.description || '暂无描述'}
            </p>
            {/* 标签 */}
            <div className="flex items-center gap-2 mt-2">
              <Tag size={12} className="text-gray-400" />
              <div className="flex flex-wrap gap-1">
                {template.tags.map(tag => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 bg-gray-100 dark:bg-neutral-700 text-gray-500 dark:text-neutral-400 text-xs rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Tab 切换 */}
          <div className="flex border-b border-gray-200 dark:border-neutral-800">
            {[
              { id: 'params', label: '参数配置', icon: <FileJson size={14} /> },
              { id: 'code', label: '代码预览', icon: <Code size={14} /> },
              { id: 'knowledge', label: '专家知识', icon: <BookOpen size={14} /> },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-gray-500 dark:text-neutral-500 hover:text-gray-700 dark:hover:text-neutral-300'
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          {/* 内容区 */}
          <div className="flex-1 overflow-y-auto p-4">
            {activeTab === 'params' && renderParametersSchema()}
            {activeTab === 'code' && (
              <pre className="bg-gray-900 dark:bg-[#0d0d0e] rounded-lg p-4 text-sm text-gray-300 font-mono overflow-x-auto">
                <code>{template.script_template || '// 暂无代码模板'}</code>
              </pre>
            )}
            {activeTab === 'knowledge' && (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                {template.expert_knowledge ? (
                  <div className="whitespace-pre-wrap text-sm text-gray-600 dark:text-neutral-300">
                    {template.expert_knowledge}
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-400 dark:text-neutral-500">
                    <BookOpen size={32} className="mx-auto mb-2 opacity-50" />
                    <p className="text-sm">暂无专家知识</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 底部操作栏 */}
          <div className="p-4 border-t border-gray-200 dark:border-neutral-800 bg-gray-50 dark:bg-[#1e1e20]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-neutral-500">技能名称:</span>
                <input
                  type="text"
                  value={skillName}
                  onChange={e => setSkillName(e.target.value)}
                  placeholder={`${template.name}_实例`}
                  className="px-3 py-1.5 bg-white dark:bg-neutral-800 border border-gray-300 dark:border-neutral-700 rounded-lg text-sm text-gray-700 dark:text-neutral-300 focus:border-blue-500 focus:outline-none w-48"
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={onClose}
                  className="px-4 py-2 text-gray-600 dark:text-neutral-400 hover:text-gray-800 dark:hover:text-neutral-200 text-sm transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleInstantiate}
                  disabled={isInstantiating}
                  className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-400 text-white text-sm rounded-lg font-medium transition-colors"
                >
                  {isInstantiating ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      实例化中...
                    </>
                  ) : (
                    <>
                      <Sparkles size={16} />
                      实例化并测试
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}