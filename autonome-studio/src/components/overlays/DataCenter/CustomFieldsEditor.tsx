"use client";

/**
 * CustomFieldsEditor - 自定义字段编辑器
 *
 * 功能说明：
 * - 提供键值对形式的自定义字段编辑功能
 * - 支持添加、编辑、删除字段
 * - 支持多种字段值类型（文本、路径、数字）
 *
 * 使用场景：
 * - 基因组资产编辑表单
 * - 分析数据库编辑表单
 */

import React, { useState } from 'react';
import { Plus, Trash2, Edit3, Check, X, FileText, Hash, Type } from 'lucide-react';

// ==========================================
// 类型定义
// ==========================================

export type FieldType = 'text' | 'path' | 'number';

export interface CustomField {
  key: string;
  value: string;
  type: FieldType;
}

interface CustomFieldsEditorProps {
  fields: Record<string, any>;
  onChange: (fields: Record<string, any>) => void;
  disabled?: boolean;
  maxFields?: number;
}

// ==========================================
// 辅助函数
// ==========================================

const detectFieldType = (value: any): FieldType => {
  if (typeof value === 'number') return 'number';
  if (typeof value === 'string' && (value.startsWith('/') || value.includes('://'))) return 'path';
  return 'text';
};

const fieldsToRecord = (fields: CustomField[]): Record<string, any> => {
  const record: Record<string, any> = {};
  fields.forEach(f => {
    record[f.key] = f.type === 'number' ? parseFloat(f.value) || 0 : f.value;
  });
  return record;
};

const recordToFields = (record: Record<string, any>): CustomField[] => {
  return Object.entries(record || {}).map(([key, value]) => ({
    key,
    value: String(value),
    type: detectFieldType(value)
  }));
};

// ==========================================
// 主组件
// ==========================================

export function CustomFieldsEditor({
  fields,
  onChange,
  disabled = false,
  maxFields = 20
}: CustomFieldsEditorProps) {
  const [localFields, setLocalFields] = useState<CustomField[]>(recordToFields(fields));
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [newType, setNewType] = useState<FieldType>('text');
  const [isAdding, setIsAdding] = useState(false);

  // 更新外部状态
  const emitChange = (updatedFields: CustomField[]) => {
    setLocalFields(updatedFields);
    onChange(fieldsToRecord(updatedFields));
  };

  // 添加字段
  const handleAdd = () => {
    if (!newKey.trim()) return;
    if (localFields.some(f => f.key === newKey.trim())) {
      alert('字段名已存在');
      return;
    }
    if (localFields.length >= maxFields) {
      alert(`最多添加 ${maxFields} 个自定义字段`);
      return;
    }

    const updatedFields = [
      ...localFields,
      { key: newKey.trim(), value: newValue, type: newType }
    ];
    emitChange(updatedFields);

    setNewKey('');
    setNewValue('');
    setNewType('text');
    setIsAdding(false);
  };

  // 删除字段
  const handleDelete = (index: number) => {
    const updatedFields = localFields.filter((_, i) => i !== index);
    emitChange(updatedFields);
  };

  // 更新字段
  const handleUpdate = (index: number, field: Partial<CustomField>) => {
    const updatedFields = localFields.map((f, i) =>
      i === index ? { ...f, ...field } : f
    );
    emitChange(updatedFields);
  };

  // 开始编辑
  const startEdit = (index: number) => {
    setEditingIndex(index);
  };

  // 完成编辑
  const finishEdit = () => {
    setEditingIndex(null);
  };

  // 取消添加
  const cancelAdd = () => {
    setIsAdding(false);
    setNewKey('');
    setNewValue('');
    setNewType('text');
  };

  if (disabled && localFields.length === 0) {
    return (
      <div className="text-neutral-500 text-sm py-4 text-center">
        无自定义字段
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* 字段列表 */}
      {localFields.map((field, index) => (
        <div
          key={field.key}
          className="flex items-center gap-2 bg-neutral-800/50 rounded-lg p-2 group"
        >
          {/* 类型图标 */}
          <div className="shrink-0 w-6 h-6 flex items-center justify-center text-neutral-500">
            {field.type === 'path' && <FileText size={14} />}
            {field.type === 'number' && <Hash size={14} />}
            {field.type === 'text' && <Type size={14} />}
          </div>

          {/* 字段名 */}
          {editingIndex === index ? (
            <input
              type="text"
              value={field.key}
              onChange={(e) => handleUpdate(index, { key: e.target.value })}
              className="flex-1 bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-sm text-white outline-none focus:border-purple-500"
            />
          ) : (
            <span className="flex-1 text-sm text-purple-400 font-mono truncate">
              {field.key}
            </span>
          )}

          {/* 字段值 */}
          {editingIndex === index ? (
            <input
              type={field.type === 'number' ? 'number' : 'text'}
              value={field.value}
              onChange={(e) => handleUpdate(index, { value: e.target.value })}
              className="flex-1 bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-sm text-white outline-none focus:border-purple-500"
            />
          ) : (
            <span className="flex-1 text-sm text-neutral-300 truncate">
              {field.value}
            </span>
          )}

          {/* 操作按钮 */}
          {!disabled && (
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              {editingIndex === index ? (
                <button
                  onClick={finishEdit}
                  className="p-1 text-green-400 hover:bg-green-500/20 rounded"
                >
                  <Check size={14} />
                </button>
              ) : (
                <button
                  onClick={() => startEdit(index)}
                  className="p-1 text-neutral-400 hover:text-white hover:bg-neutral-700 rounded"
                >
                  <Edit3 size={14} />
                </button>
              )}
              <button
                onClick={() => handleDelete(index)}
                className="p-1 text-red-400 hover:bg-red-500/20 rounded"
              >
                <Trash2 size={14} />
              </button>
            </div>
          )}
        </div>
      ))}

      {/* 添加新字段 */}
      {!disabled && !isAdding && localFields.length < maxFields && (
        <button
          onClick={() => setIsAdding(true)}
          className="w-full flex items-center justify-center gap-2 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800/50 rounded-lg border border-dashed border-neutral-700 transition-colors"
        >
          <Plus size={14} />
          添加自定义字段
        </button>
      )}

      {/* 添加表单 */}
      {!disabled && isAdding && (
        <div className="bg-neutral-800/50 rounded-lg p-3 space-y-2">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="字段名"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              className="flex-1 bg-neutral-900 border border-neutral-700 rounded px-2 py-1.5 text-sm text-white outline-none focus:border-purple-500 placeholder:text-neutral-500"
            />
            <select
              value={newType}
              onChange={(e) => setNewType(e.target.value as FieldType)}
              className="bg-neutral-900 border border-neutral-700 rounded px-2 py-1.5 text-sm text-white outline-none focus:border-purple-500"
            >
              <option value="text">文本</option>
              <option value="path">路径</option>
              <option value="number">数字</option>
            </select>
          </div>
          <input
            type={newType === 'number' ? 'number' : 'text'}
            placeholder="字段值"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            className="w-full bg-neutral-900 border border-neutral-700 rounded px-2 py-1.5 text-sm text-white outline-none focus:border-purple-500 placeholder:text-neutral-500"
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={cancelAdd}
              className="px-3 py-1 text-sm text-neutral-400 hover:text-white transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleAdd}
              disabled={!newKey.trim()}
              className="px-3 py-1 text-sm bg-purple-600 hover:bg-purple-500 text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              添加
            </button>
          </div>
        </div>
      )}

      {/* 空状态提示 */}
      {localFields.length === 0 && disabled && (
        <div className="text-neutral-500 text-sm py-2 text-center">
          无自定义字段
        </div>
      )}
    </div>
  );
}