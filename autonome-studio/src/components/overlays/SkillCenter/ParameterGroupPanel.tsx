/**
 * 参数分组面板组件
 *
 * P4 参数表单智能分组：
 * - 将参数按逻辑分组显示（输入数据、分析参数、输出设置、高级选项）
 * - 支持折叠/展开
 * - 必填参数标记
 * - 默认值显示
 */

'use client';

import React, { useState, useMemo } from 'react';
import { ChevronDown, ChevronRight, Database, Sliders, Download, Settings, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { groupParameters, ParameterGroup, ParameterInfo, hasRequiredParams, countRequiredParams } from './parameterGrouper';

// ==========================================
// 类型定义
// ==========================================

// 参数属性类型
interface ParameterProperty {
  type?: string;
  description?: string;
  default?: unknown;
  enum?: (string | number)[];
  minimum?: number;
  maximum?: number;
  format?: string;
}

// 使用更宽松的 schema 类型以兼容 SkillSchema
interface LooseJSONSchema {
  type?: string;
  properties?: Record<string, ParameterProperty>;
  required?: string[];
  'x-parameter-order'?: string[];
}

interface ParameterGroupPanelProps {
  schema: LooseJSONSchema;
  paramValues: Record<string, unknown>;
  onParamChange: (key: string, value: unknown) => void;
  renderParamInput: (key: string, prop: ParameterProperty) => React.ReactNode;
  className?: string;
}

// ==========================================
// 分组图标映射
// ==========================================

const GROUP_ICONS: Record<string, React.ReactNode> = {
  输入数据: <Database size={14} />,
  分析参数: <Sliders size={14} />,
  输出设置: <Download size={14} />,
  高级选项: <Settings size={14} />,
};

// ==========================================
// 主组件
// ==========================================

export function ParameterGroupPanel({
  schema,
  paramValues,
  onParamChange,
  renderParamInput,
  className,
}: ParameterGroupPanelProps) {
  // 分组状态
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set(['高级选项']) // 默认折叠高级选项
  );

  // 计算分组
  const groups = useMemo(() => {
    return groupParameters(schema);
  }, [schema]);

  // 切换分组折叠状态
  const toggleGroup = (groupName: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupName)) {
        next.delete(groupName);
      } else {
        next.add(groupName);
      }
      return next;
    });
  };

  // 空状态
  if (groups.length === 0) {
    return (
      <div className={cn('text-sm text-neutral-500', className)}>
        该 SKILL 无需配置参数
      </div>
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      {groups.map((group) => (
        <ParameterGroupSection
          key={group.name}
          group={group}
          isCollapsed={collapsedGroups.has(group.name)}
          onToggle={() => toggleGroup(group.name)}
          paramValues={paramValues}
          renderParamInput={renderParamInput}
        />
      ))}
    </div>
  );
}

// ==========================================
// 分组渲染组件
// ==========================================

interface ParameterGroupSectionProps {
  group: ParameterGroup;
  isCollapsed: boolean;
  onToggle: () => void;
  paramValues: Record<string, unknown>;
  renderParamInput: (key: string, prop: ParameterProperty) => React.ReactNode;
}

function ParameterGroupSection({
  group,
  isCollapsed,
  onToggle,
  paramValues,
  renderParamInput,
}: ParameterGroupSectionProps) {
  const requiredCount = countRequiredParams(group);
  const hasRequired = hasRequiredParams(group);

  // 计算已填写的必填参数数量
  const filledRequiredCount = group.parameters.filter(
    (p) => p.required && paramValues[p.key] !== undefined && paramValues[p.key] !== ''
  ).length;

  // 是否所有必填参数都已填写
  const allRequiredFilled = !hasRequired || filledRequiredCount === requiredCount;

  return (
    <div className="border border-neutral-800 rounded-lg overflow-hidden">
      {/* 分组标题 */}
      <button
        onClick={onToggle}
        className={cn(
          'w-full flex items-center justify-between px-4 py-3 transition-colors',
          isCollapsed
            ? 'bg-neutral-900/50 hover:bg-neutral-800/50'
            : 'bg-neutral-800/30 hover:bg-neutral-800/50'
        )}
      >
        <div className="flex items-center gap-3">
          {/* 分组图标 */}
          <span className="text-neutral-400">
            {GROUP_ICONS[group.name] || <Settings size={14} />}
          </span>

          {/* 分组名称 */}
          <span className="text-sm font-medium text-neutral-200">{group.name}</span>

          {/* 必填参数计数 */}
          {hasRequired && (
            <span
              className={cn(
                'text-xs px-2 py-0.5 rounded-full',
                allRequiredFilled
                  ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                  : 'bg-orange-500/10 text-orange-400 border border-orange-500/20'
              )}
            >
              {filledRequiredCount}/{requiredCount} 必填
            </span>
          )}

          {/* 参数总数 */}
          <span className="text-xs text-neutral-500">
            {group.parameters.length} 个参数
          </span>
        </div>

        {/* 折叠指示器 */}
        <span className="text-neutral-500">
          {isCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
        </span>
      </button>

      {/* 参数列表 */}
      {!isCollapsed && (
        <div className="p-4 space-y-4 bg-neutral-900/30">
          {group.parameters.map((param) => (
            <ParameterField
              key={param.key}
              param={param}
              renderParamInput={renderParamInput}
            />
          ))}
        </div>
      )}

      {/* 折叠状态的提示 */}
      {isCollapsed && hasRequired && !allRequiredFilled && (
        <div className="px-4 py-2 bg-orange-500/5 border-t border-neutral-800 flex items-center gap-2">
          <AlertCircle size={12} className="text-orange-400" />
          <span className="text-xs text-orange-300">
            还有 {requiredCount - filledRequiredCount} 个必填参数未填写
          </span>
        </div>
      )}
    </div>
  );
}

// ==========================================
// 单个参数字段组件
// ==========================================

interface ParameterFieldProps {
  param: ParameterInfo;
  renderParamInput: (key: string, prop: ParameterProperty) => React.ReactNode;
}

function ParameterField({ param, renderParamInput }: ParameterFieldProps) {
  // 构建 prop 对象用于 renderParamInput
  const prop: ParameterProperty = {
    type: param.type,
    format: param.format,
    description: param.description,
    default: param.defaultValue,
    enum: param.enum,
    minimum: param.minimum,
    maximum: param.maximum,
  };

  return (
    <div>
      {/* 参数标签 */}
      <label className="flex items-center gap-2 text-sm text-neutral-300 mb-1.5">
        <span className="font-mono">{param.key}</span>
        {param.required && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
            必填
          </span>
        )}
        {param.defaultValue !== undefined && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
            默认: {String(param.defaultValue)}
          </span>
        )}
      </label>

      {/* 参数描述 */}
      {param.description && (
        <p className="text-xs text-neutral-500 mb-1.5">{param.description}</p>
      )}

      {/* 参数输入控件 */}
      {renderParamInput(param.key, prop)}
    </div>
  );
}

// ==========================================
// 导出
// ==========================================

export default ParameterGroupPanel;