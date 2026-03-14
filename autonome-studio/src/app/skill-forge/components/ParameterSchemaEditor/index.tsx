/**
 * 参数 Schema 可视化编辑器
 *
 * 将 JSON Schema 编辑转化为可视化表单操作
 */

'use client';

import React, { useState, useEffect } from 'react';
import { Plus, Sparkles, FileJson, Code, ChevronDown, ChevronUp } from 'lucide-react';
import { ParameterItem } from './ParameterItem';
import {
  ParameterDefinition,
  JsonSchema,
  parametersToJsonSchema,
  jsonSchemaToParameters,
  validateParameterName,
  ParameterType
} from './types';

interface ParameterSchemaEditorProps {
  // 当前 schema
  value: JsonSchema | Record<string, any>;
  // 变更回调
  onChange: (schema: JsonSchema) => void;
  // AI 推断回调（可选）
  onAiInfer?: () => void;
  // 是否正在推断
  isInfering?: boolean;
  // 显示 JSON 预览
  showJsonPreview?: boolean;
  // 初始展开状态
  defaultExpanded?: boolean;
  // 禁用状态
  disabled?: boolean;
}

// 生成唯一参数名
const generateUniqueName = (existingNames: Set<string>): string => {
  let index = 1;
  while (existingNames.has(`param_${index}`)) {
    index++;
  }
  return `param_${index}`;
};

export function ParameterSchemaEditor({
  value,
  onChange,
  onAiInfer,
  isInfering = false,
  showJsonPreview = true,
  defaultExpanded = true,
  disabled = false
}: ParameterSchemaEditorProps) {
  const [parameters, setParameters] = useState<ParameterDefinition[]>([]);
  const [showJson, setShowJson] = useState(false);
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  // 从 schema 同步到本地参数列表
  useEffect(() => {
    if (value && Object.keys(value.properties || {}).length > 0) {
      const parsed = jsonSchemaToParameters(value as JsonSchema);
      setParameters(parsed);
    }
  }, []); // 只在初始化时解析

  // 参数变更处理
  const handleParameterChange = (index: number, param: ParameterDefinition) => {
    const newParams = [...parameters];
    newParams[index] = param;
    setParameters(newParams);
    emitChange(newParams);
  };

  // 添加新参数
  const handleAddParameter = () => {
    const existingNames = new Set(parameters.map(p => p.name));
    const newParam: ParameterDefinition = {
      name: generateUniqueName(existingNames),
      type: 'string',
      description: '',
      required: true,
    };
    const newParams = [...parameters, newParam];
    setParameters(newParams);
    emitChange(newParams);
  };

  // 删除参数
  const handleDeleteParameter = (index: number) => {
    const newParams = parameters.filter((_, i) => i !== index);
    setParameters(newParams);
    emitChange(newParams);
  };

  // 移动参数顺序
  const handleMoveUp = (index: number) => {
    if (index === 0) return;
    const newParams = [...parameters];
    [newParams[index - 1], newParams[index]] = [newParams[index], newParams[index - 1]];
    setParameters(newParams);
    emitChange(newParams);
  };

  const handleMoveDown = (index: number) => {
    if (index === parameters.length - 1) return;
    const newParams = [...parameters];
    [newParams[index], newParams[index + 1]] = [newParams[index + 1], newParams[index]];
    setParameters(newParams);
    emitChange(newParams);
  };

  // 输出变更
  const emitChange = (params: ParameterDefinition[]) => {
    const schema = parametersToJsonSchema(params);
    onChange(schema);
  };

  // 验证所有参数
  const hasErrors = parameters.some(p => {
    const result = validateParameterName(p.name);
    return !result.valid;
  });

  // 检查重名
  const nameSet = new Set<string>();
  const hasDuplicates = parameters.some(p => {
    if (nameSet.has(p.name)) return true;
    nameSet.add(p.name);
    return false;
  });

  return (
    <div className="border border-neutral-800 rounded-lg bg-neutral-900/50 overflow-hidden">
      {/* 标题栏 */}
      <div
        className="flex items-center justify-between p-3 bg-neutral-800/50 cursor-pointer hover:bg-neutral-800/70 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <FileJson size={16} className="text-blue-400" />
          <span className="text-sm font-medium text-white">参数定义</span>
          <span className="text-xs text-neutral-500">
            ({parameters.length} 个参数)
          </span>
          {hasErrors && (
            <span className="text-xs text-red-400 flex items-center gap-1">
              <span className="w-2 h-2 bg-red-400 rounded-full"></span>
              有错误
            </span>
          )}
          {hasDuplicates && (
            <span className="text-xs text-yellow-400">存在重名</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isExpanded ? <ChevronUp size={16} className="text-neutral-400" /> : <ChevronDown size={16} className="text-neutral-400" />}
        </div>
      </div>

      {/* 展开内容 */}
      {isExpanded && (
        <div className="p-3">
          {/* 工具栏 */}
          <div className="flex items-center gap-2 mb-3">
            <button
              onClick={handleAddParameter}
              disabled={disabled}
              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-700 disabled:text-neutral-500 text-white rounded-md transition-colors"
            >
              <Plus size={14} />
              添加参数
            </button>

            {onAiInfer && (
              <button
                onClick={onAiInfer}
                disabled={disabled || isInfering}
                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-purple-600 hover:bg-purple-500 disabled:bg-neutral-700 disabled:text-neutral-500 text-white rounded-md transition-colors"
              >
                <Sparkles size={14} />
                {isInfering ? '推断中...' : 'AI 推断参数'}
              </button>
            )}

            {showJsonPreview && (
              <button
                onClick={() => setShowJson(!showJson)}
                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-neutral-700 hover:bg-neutral-600 text-white rounded-md transition-colors ml-auto"
              >
                <Code size={14} />
                {showJson ? '隐藏 JSON' : '显示 JSON'}
              </button>
            )}
          </div>

          {/* 参数列表 */}
          {parameters.length > 0 ? (
            <div className="space-y-0">
              {parameters.map((param, index) => (
                <ParameterItem
                  key={`${param.name}-${index}`}
                  parameter={param}
                  index={index}
                  onChange={handleParameterChange}
                  onDelete={handleDeleteParameter}
                  onMoveUp={handleMoveUp}
                  onMoveDown={handleMoveDown}
                  isFirst={index === 0}
                  isLast={index === parameters.length - 1}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-neutral-500 text-sm">
              <FileJson size={32} className="mx-auto mb-2 opacity-50" />
              <p>暂无参数定义</p>
              <p className="text-xs mt-1">点击"添加参数"或使用"AI 推断参数"</p>
            </div>
          )}

          {/* JSON 预览 */}
          {showJson && showJsonPreview && parameters.length > 0 && (
            <div className="mt-3 p-2 bg-neutral-800/50 rounded-md border border-neutral-700">
              <label className="text-xs text-neutral-500 mb-1 block">JSON Schema 预览</label>
              <pre className="text-xs text-emerald-400 font-mono whitespace-pre-wrap max-h-48 overflow-auto">
                {JSON.stringify(parametersToJsonSchema(parameters), null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// 导出类型和工具函数
export * from './types';
export { TypeSelector } from './TypeSelector';
export { ParameterItem } from './ParameterItem';