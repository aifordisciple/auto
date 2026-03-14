/**
 * 单个参数编辑项
 */

'use client';

import React, { useState } from 'react';
import { GripVertical, Trash2, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react';
import { ParameterDefinition, ParameterType, validateParameterName } from './types';
import { TypeSelector } from './TypeSelector';

interface ParameterItemProps {
  parameter: ParameterDefinition;
  index: number;
  onChange: (index: number, param: ParameterDefinition) => void;
  onDelete: (index: number) => void;
  onMoveUp?: (index: number) => void;
  onMoveDown?: (index: number) => void;
  isFirst: boolean;
  isLast: boolean;
}

export function ParameterItem({
  parameter,
  index,
  onChange,
  onDelete,
  onMoveUp,
  onMoveDown,
  isFirst,
  isLast
}: ParameterItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  const handleChange = (field: keyof ParameterDefinition, value: any) => {
    if (field === 'name') {
      const validation = validateParameterName(value);
      setNameError(validation.valid ? null : validation.error || null);
    }
    onChange(index, { ...parameter, [field]: value });
  };

  const handleTypeChange = (type: ParameterType) => {
    const newParam: ParameterDefinition = {
      ...parameter,
      type,
      // 重置类型特定字段
      enumValues: type === 'enum' ? ['option1'] : undefined,
      defaultValue: undefined,
    };
    onChange(index, newParam);
  };

  const renderDefaultValueInput = () => {
    const { type, defaultValue, enumValues } = parameter;

    if (type === 'boolean') {
      return (
        <select
          value={defaultValue === true ? 'true' : defaultValue === false ? 'false' : ''}
          onChange={(e) => handleChange('defaultValue', e.target.value === 'true' ? true : e.target.value === 'false' ? false : undefined)}
          className="w-full bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
        >
          <option value="">无默认值</option>
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      );
    }

    if (type === 'enum') {
      return (
        <div className="space-y-2">
          <select
            value={defaultValue as string || ''}
            onChange={(e) => handleChange('defaultValue', e.target.value || undefined)}
            className="w-full bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
          >
            <option value="">无默认值</option>
            {(enumValues || []).map(opt => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
          <div className="text-xs text-neutral-500">
            枚举选项 (逗号分隔):
            <input
              type="text"
              value={(enumValues || []).join(', ')}
              onChange={(e) => handleChange('enumValues', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
              placeholder="option1, option2, option3"
              className="w-full mt-1 bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>
      );
    }

    if (type === 'number' || type === 'integer') {
      return (
        <div className="space-y-2">
          <input
            type="number"
            value={defaultValue as number || ''}
            onChange={(e) => handleChange('defaultValue', e.target.value ? parseFloat(e.target.value) : undefined)}
            placeholder="默认值"
            className="w-full bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
          />
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-xs text-neutral-500">最小值</label>
              <input
                type="number"
                value={parameter.min || ''}
                onChange={(e) => handleChange('min', e.target.value ? parseFloat(e.target.value) : undefined)}
                className="w-full bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-neutral-500">最大值</label>
              <input
                type="number"
                value={parameter.max || ''}
                onChange={(e) => handleChange('max', e.target.value ? parseFloat(e.target.value) : undefined)}
                className="w-full bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>
        </div>
      );
    }

    if (type === 'array') {
      return (
        <div className="text-xs text-neutral-500">
          默认值 (逗号分隔):
          <input
            type="text"
            value={Array.isArray(defaultValue) ? (defaultValue as string[]).join(', ') : ''}
            onChange={(e) => handleChange('defaultValue', e.target.value ? e.target.value.split(',').map(s => s.trim()) : undefined)}
            placeholder="item1, item2"
            className="w-full mt-1 bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
          />
        </div>
      );
    }

    // string, FilePath, DirectoryPath
    return (
      <input
        type="text"
        value={defaultValue as string || ''}
        onChange={(e) => handleChange('defaultValue', e.target.value || undefined)}
        placeholder="默认值"
        className="w-full bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
      />
    );
  };

  return (
    <div className="border border-neutral-700 rounded-lg bg-neutral-800/50 mb-2 overflow-hidden">
      {/* 主行 */}
      <div className="flex items-center gap-2 p-2">
        {/* 拖拽手柄 */}
        <div className="text-neutral-500 cursor-grab">
          <GripVertical size={16} />
        </div>

        {/* 参数名 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1">
            <input
              type="text"
              value={parameter.name}
              onChange={(e) => handleChange('name', e.target.value)}
              placeholder="参数名"
              className={`flex-1 bg-neutral-900 border rounded-md px-2 py-1 text-sm text-white focus:outline-none ${
                nameError ? 'border-red-500' : 'border-neutral-700 focus:border-blue-500'
              }`}
            />
            {nameError && (
              <span className="text-red-400" title={nameError}>
                <AlertCircle size={14} />
              </span>
            )}
          </div>
        </div>

        {/* 类型选择 */}
        <div className="w-32">
          <TypeSelector value={parameter.type} onChange={handleTypeChange} />
        </div>

        {/* 必填复选框 */}
        <label className="flex items-center gap-1 text-xs text-neutral-400 cursor-pointer">
          <input
            type="checkbox"
            checked={parameter.required}
            onChange={(e) => handleChange('required', e.target.checked)}
            className="rounded border-neutral-600 bg-neutral-800"
          />
          必填
        </label>

        {/* 展开/收起 */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1 text-neutral-400 hover:text-white transition-colors"
        >
          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>

        {/* 删除按钮 */}
        <button
          onClick={() => onDelete(index)}
          className="p-1 text-neutral-400 hover:text-red-400 transition-colors"
        >
          <Trash2 size={16} />
        </button>

        {/* 上下移动 */}
        <div className="flex flex-col">
          <button
            onClick={() => onMoveUp?.(index)}
            disabled={isFirst}
            className="p-0.5 text-neutral-400 hover:text-white disabled:text-neutral-600 disabled:cursor-not-allowed"
          >
            <ChevronUp size={12} />
          </button>
          <button
            onClick={() => onMoveDown?.(index)}
            disabled={isLast}
            className="p-0.5 text-neutral-400 hover:text-white disabled:text-neutral-600 disabled:cursor-not-allowed"
          >
            <ChevronDown size={12} />
          </button>
        </div>
      </div>

      {/* 展开的详细信息 */}
      {isExpanded && (
        <div className="px-2 pb-2 pt-0 space-y-3 border-t border-neutral-700">
          {/* 描述 */}
          <div>
            <label className="text-xs text-neutral-500 mb-1 block">描述</label>
            <input
              type="text"
              value={parameter.description}
              onChange={(e) => handleChange('description', e.target.value)}
              placeholder="参数描述..."
              className="w-full bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* 默认值（根据类型显示不同输入） */}
          <div>
            <label className="text-xs text-neutral-500 mb-1 block">默认值</label>
            {renderDefaultValueInput()}
          </div>

          {/* 字符串正则（仅 string 类型） */}
          {parameter.type === 'string' && (
            <div>
              <label className="text-xs text-neutral-500 mb-1 block">正则验证</label>
              <input
                type="text"
                value={parameter.pattern || ''}
                onChange={(e) => handleChange('pattern', e.target.value || undefined)}
                placeholder="正则表达式 (可选)"
                className="w-full bg-neutral-800 border border-neutral-700 rounded-md px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}