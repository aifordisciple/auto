"use client";

/**
 * DatabaseFormModal - 数据库编辑表单弹窗
 *
 * 功能说明：
 * - 创建和编辑分析数据库
 * - 支持多种数据库类型
 * - 支持自定义字段编辑
 */

import React, { useState, useEffect } from 'react';
import { X, Save, Loader2, Database } from 'lucide-react';
import { CustomFieldsEditor } from './CustomFieldsEditor';
import { Button } from '@/components/ui/Button';
import { databaseApi, AnalysisDatabase } from '@/lib/api';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { HybridPathInput } from '@/components/HybridPathInput';

// ==========================================
// 类型定义
// ==========================================

interface DatabaseFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  editDatabase?: AnalysisDatabase | null;
}

// 数据库类型配置
const DB_TYPES = [
  { value: 'annotation', label: '注释数据库', description: 'GO、KEGG、InterPro 等' },
  { value: 'pathway', label: '信号通路', description: 'Reactome、WikiPathways 等' },
  { value: 'protein', label: '蛋白质数据库', description: 'UniProt、PDB 等' },
  { value: 'variant', label: '变异数据库', description: 'dbSNP、ClinVar 等' },
  { value: 'regulation', label: '调控数据库', description: 'ENCODE、TFbind 等' },
  { value: 'metabolism', label: '代谢数据库', description: 'KEGG Compound、HMDB 等' },
  { value: 'custom', label: '自定义数据库', description: '用户上传的自定义数据库' }
];

// 必填字段
const REQUIRED_FIELDS = ['db_id', 'name', 'db_type', 'path'];

// ==========================================
// 主组件
// ==========================================

export function DatabaseFormModal({ isOpen, onClose, onSuccess, editDatabase }: DatabaseFormModalProps) {
  // 获取当前项目 ID（用于 HybridPathInput 的文件选择功能）
  const { currentProjectId } = useWorkspaceStore();

  const [formData, setFormData] = useState<Record<string, any>>({
    db_id: '',
    name: '',
    description: '',
    db_type: 'annotation',
    species: '',
    version: '',
    path: '',
    file_format: '',
    size_bytes: null,
    is_active: true,
    source_url: '',
    license: '',
    tags: [],
    custom_fields: {},
    visibility: 'private'
  });
  const [tagInput, setTagInput] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // 初始化表单数据
  useEffect(() => {
    if (editDatabase) {
      setFormData({
        ...editDatabase,
        custom_fields: editDatabase.custom_fields || {},
        tags: editDatabase.tags || []
      });
    } else {
      setFormData({
        db_id: '',
        name: '',
        description: '',
        db_type: 'annotation',
        species: '',
        version: '',
        path: '',
        file_format: '',
        size_bytes: null,
        is_active: true,
        source_url: '',
        license: '',
        tags: [],
        custom_fields: {},
        visibility: 'private'
      });
    }
    setErrors({});
  }, [editDatabase, isOpen]);

  // 更新字段值
  const updateField = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  // 添加标签
  const addTag = () => {
    const tag = tagInput.trim();
    if (tag && !formData.tags.includes(tag)) {
      updateField('tags', [...formData.tags, tag]);
    }
    setTagInput('');
  };

  // 删除标签
  const removeTag = (tag: string) => {
    updateField('tags', formData.tags.filter((t: string) => t !== tag));
  };

  // 表单验证
  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};
    REQUIRED_FIELDS.forEach(field => {
      if (!formData[field] || (typeof formData[field] === 'string' && !formData[field].trim())) {
        const labels: Record<string, string> = {
          db_id: '数据库 ID',
          name: '名称',
          db_type: '类型',
          path: '路径'
        };
        newErrors[field] = `${labels[field] || field} 是必填项`;
      }
    });
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // 提交表单
  const handleSubmit = async () => {
    if (!validateForm()) return;

    setIsSaving(true);
    try {
      if (editDatabase) {
        await databaseApi.updateDatabase(editDatabase.db_id, formData);
      } else {
        await databaseApi.createDatabase(formData);
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      alert('保存失败: ' + err.message);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#1a1a1c] border border-neutral-800 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="shrink-0 h-14 border-b border-neutral-800 px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-blue-500/20 border border-blue-500/30 rounded-lg text-blue-400">
              <Database size={16} />
            </div>
            <h3 className="text-white font-medium">
              {editDatabase ? `编辑数据库: ${editDatabase.db_id}` : '创建新数据库'}
            </h3>
          </div>
          <Button variant="icon" onClick={onClose}>
            <X size={18} />
          </Button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* 基本信息 */}
          <div className="space-y-4">
            <h4 className="text-sm font-medium text-neutral-300 border-b border-neutral-800 pb-2">
              基本信息
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 数据库 ID */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400 flex items-center gap-1">
                  数据库 ID <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formData.db_id}
                  onChange={(e) => updateField('db_id', e.target.value)}
                  disabled={!!editDatabase}
                  className={`w-full bg-neutral-900 border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500 font-mono ${
                    errors.db_id ? 'border-red-500' : 'border-neutral-700'
                  } ${editDatabase ? 'opacity-50 cursor-not-allowed' : ''}`}
                  placeholder="go_basic"
                />
                {errors.db_id && <p className="text-xs text-red-400">{errors.db_id}</p>}
              </div>

              {/* 名称 */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400 flex items-center gap-1">
                  名称 <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => updateField('name', e.target.value)}
                  className={`w-full bg-neutral-900 border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500 ${
                    errors.name ? 'border-red-500' : 'border-neutral-700'
                  }`}
                  placeholder="GO Basic Ontology"
                />
                {errors.name && <p className="text-xs text-red-400">{errors.name}</p>}
              </div>

              {/* 类型 */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400 flex items-center gap-1">
                  类型 <span className="text-red-400">*</span>
                </label>
                <select
                  value={formData.db_type}
                  onChange={(e) => updateField('db_type', e.target.value)}
                  className={`w-full bg-neutral-900 border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500 ${
                    errors.db_type ? 'border-red-500' : 'border-neutral-700'
                  }`}
                >
                  {DB_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>

              {/* 物种 */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">物种</label>
                <input
                  type="text"
                  value={formData.species || ''}
                  onChange={(e) => updateField('species', e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500"
                  placeholder="human / mouse / all"
                />
              </div>

              {/* 版本 */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">版本</label>
                <input
                  type="text"
                  value={formData.version || ''}
                  onChange={(e) => updateField('version', e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500"
                  placeholder="2024-01"
                />
              </div>

              {/* 文件格式 */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">文件格式</label>
                <select
                  value={formData.file_format || ''}
                  onChange={(e) => updateField('file_format', e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500"
                >
                  <option value="">选择格式</option>
                  <option value="tsv">TSV</option>
                  <option value="csv">CSV</option>
                  <option value="json">JSON</option>
                  <option value="rds">RDS (R)</option>
                  <option value="fasta">FASTA</option>
                  <option value="gff">GFF</option>
                  <option value="gtf">GTF</option>
                  <option value="directory">目录</option>
                </select>
              </div>
            </div>

            {/* 描述 */}
            <div className="space-y-1">
              <label className="text-xs text-neutral-400">描述（支持 Markdown）</label>
              <textarea
                value={formData.description || ''}
                onChange={(e) => updateField('description', e.target.value)}
                rows={3}
                className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500 resize-none"
                placeholder="数据库描述信息..."
              />
            </div>
          </div>

          {/* 存储信息 */}
          <div className="space-y-4">
            <h4 className="text-sm font-medium text-neutral-300 border-b border-neutral-800 pb-2">
              存储信息
            </h4>
            <div className="space-y-4">
              {/* 路径 */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400 flex items-center gap-1">
                  路径 <span className="text-red-400">*</span>
                </label>
                <HybridPathInput
                  projectId={currentProjectId || ''}
                  value={formData.path}
                  onChange={(path) => updateField('path', path)}
                  type={formData.file_format === 'directory' ? 'directory' : 'file'}
                  placeholder="/path/to/database 或点击选择"
                  error={errors.path}
                  disabled={!currentProjectId}
                />
                {!currentProjectId && (
                  <p className="text-xs text-neutral-500">请先选择项目以使用文件选择功能，或直接手动输入路径</p>
                )}
                {errors.path && <p className="text-xs text-red-400">{errors.path}</p>}
              </div>

              {/* 来源 URL */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">来源 URL</label>
                <input
                  type="text"
                  value={formData.source_url || ''}
                  onChange={(e) => updateField('source_url', e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500"
                  placeholder="https://..."
                />
              </div>

              {/* 许可证 */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">许可证</label>
                <input
                  type="text"
                  value={formData.license || ''}
                  onChange={(e) => updateField('license', e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500"
                  placeholder="MIT / CC-BY / ..."
                />
              </div>
            </div>
          </div>

          {/* 标签 */}
          <div className="space-y-4">
            <h4 className="text-sm font-medium text-neutral-300 border-b border-neutral-800 pb-2">
              标签
            </h4>
            <div className="flex flex-wrap gap-2">
              {formData.tags.map((tag: string) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-purple-500/10 text-purple-400 border border-purple-500/30 rounded-full text-xs"
                >
                  {tag}
                  <button
                    onClick={() => removeTag(tag)}
                    className="hover:text-white"
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
                className="flex-1 bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500"
                placeholder="输入标签后按 Enter 添加"
              />
              <button
                onClick={addTag}
                className="px-3 py-2 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-sm rounded-lg transition-colors"
              >
                添加
              </button>
            </div>
          </div>

          {/* 自定义字段 */}
          <div className="space-y-4">
            <h4 className="text-sm font-medium text-neutral-300 border-b border-neutral-800 pb-2">
              自定义字段
            </h4>
            <CustomFieldsEditor
              fields={formData.custom_fields || {}}
              onChange={(fields) => updateField('custom_fields', fields)}
            />
          </div>

          {/* 权限设置 */}
          <div className="space-y-4">
            <h4 className="text-sm font-medium text-neutral-300 border-b border-neutral-800 pb-2">
              权限设置
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">可见性</label>
                <select
                  value={formData.visibility}
                  onChange={(e) => updateField('visibility', e.target.value)}
                  className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500"
                >
                  <option value="private">私有（仅自己可见）</option>
                  <option value="team">团队（团队成员可见）</option>
                  <option value="public">公开（所有用户可见）</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">状态</label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => updateField('is_active', e.target.checked)}
                    className="w-4 h-4 rounded border-neutral-700 bg-neutral-900 text-purple-500 focus:ring-purple-500"
                  />
                  <span className="text-sm text-neutral-300">启用此数据库</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-neutral-800 px-6 py-4 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
          >
            {isSaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            {isSaving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}