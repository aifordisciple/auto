"use client";

/**
 * GenomeFormModal - 基因组编辑表单弹窗
 *
 * 功能说明：
 * - 创建和编辑基因组资产
 * - 分组显示所有字段
 * - 支持自定义字段编辑
 * - 表单验证
 */

import React, { useState, useEffect } from 'react';
import { X, Save, Loader2, Dna } from 'lucide-react';
import { CustomFieldsEditor } from './CustomFieldsEditor';
import { genomeApi, GenomeAsset } from '@/lib/api';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { HybridPathInput } from '@/components/HybridPathInput';

// ==========================================
// 类型定义
// ==========================================

interface GenomeFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  editGenome?: GenomeAsset | null;
}

// 字段分组配置
const FIELD_GROUPS = [
  {
    title: '基本信息',
    fields: ['genomeid', 'species', 'version', 'species_code', 'url', 'date', 'description']
  },
  {
    title: '核心文件路径',
    fields: ['genome', 'chrlen', 'gff', 'gffdb', 'gtf', 'geneanno', 'genelen', 'genome_info']
  },
  {
    title: '比对工具索引',
    fields: ['bowtie2_index', 'bowtie1_index', 'bwa_index', 'star_index', 'hisat2_index', 'novoalign_index', 'minimap2_index', 'minimap2_juncbed', 'rsem_index', 'noncode_index']
  },
  {
    title: '单细胞相关',
    fields: ['ref10x', 'sc_star', 'sc_gtf']
  },
  {
    title: '注释相关',
    fields: ['godes', 'kg', 'known_lncRNA', 'bsgenome', 'geneid_or_symbol']
  }
];

// 字段标签映射
const FIELD_LABELS: Record<string, string> = {
  genomeid: 'Genome ID',
  species: '物种',
  version: '版本',
  species_code: '物种缩写',
  url: '来源 URL',
  date: '创建日期',
  description: '描述',
  genome: '参考基因组 FASTA',
  chrlen: '染色体长度文件',
  gff: 'GFF 注释文件',
  gffdb: 'GFF 数据库文件',
  gtf: 'GTF 注释文件',
  geneanno: '基因注释文件',
  genelen: '基因长度文件',
  genome_info: '基因组信息文件',
  bowtie2_index: 'Bowtie2 索引',
  bowtie1_index: 'Bowtie1 索引',
  bwa_index: 'BWA 索引',
  star_index: 'STAR 索引',
  hisat2_index: 'HISAT2 索引',
  novoalign_index: 'Novoalign 索引',
  minimap2_index: 'Minimap2 索引',
  minimap2_juncbed: 'Minimap2 剪接位点 BED',
  rsem_index: 'RSEM 索引',
  noncode_index: '非编码 RNA 索引',
  ref10x: '10x 参考基因组',
  sc_star: '单细胞 STAR 索引',
  sc_gtf: '单细胞 GTF',
  godes: 'GO 注释文件',
  kg: 'KEGG 物种代码',
  known_lncRNA: '已知 lncRNA 文件',
  bsgenome: 'BSgenome 包名',
  geneid_or_symbol: '基因 ID 类型',
  visibility: '可见性'
};

// 必填字段
const REQUIRED_FIELDS = ['genomeid', 'species', 'version', 'genome'];

// ==========================================
// 主组件
// ==========================================

export function GenomeFormModal({ isOpen, onClose, onSuccess, editGenome }: GenomeFormModalProps) {
  // 获取当前项目 ID（用于 HybridPathInput 的文件选择功能）
  const { currentProjectId } = useWorkspaceStore();

  const [formData, setFormData] = useState<Record<string, any>>({
    genomeid: '',
    species: '',
    version: '',
    species_code: '',
    url: '',
    date: '',
    genome: '',
    chrlen: '',
    gff: '',
    gffdb: '',
    gtf: '',
    geneanno: '',
    genelen: '',
    genome_info: '',
    bowtie2_index: '',
    bowtie1_index: '',
    bwa_index: '',
    star_index: '',
    hisat2_index: '',
    novoalign_index: '',
    minimap2_index: '',
    minimap2_juncbed: '',
    rsem_index: '',
    noncode_index: '',
    ref10x: '',
    sc_star: '',
    sc_gtf: '',
    godes: '',
    kg: '',
    known_lncRNA: '',
    bsgenome: '',
    geneid_or_symbol: 'symbol',
    is_active: true,
    description: '',
    custom_fields: {},
    visibility: 'private'
  });
  const [isSaving, setIsSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // 初始化表单数据
  useEffect(() => {
    if (editGenome) {
      setFormData({
        ...editGenome,
        custom_fields: editGenome.custom_fields || {}
      });
    } else {
      // 重置为默认值
      setFormData({
        genomeid: '',
        species: '',
        version: '',
        species_code: '',
        url: '',
        date: '',
        genome: '',
        chrlen: '',
        gff: '',
        gffdb: '',
        gtf: '',
        geneanno: '',
        genelen: '',
        genome_info: '',
        bowtie2_index: '',
        bowtie1_index: '',
        bwa_index: '',
        star_index: '',
        hisat2_index: '',
        novoalign_index: '',
        minimap2_index: '',
        minimap2_juncbed: '',
        rsem_index: '',
        noncode_index: '',
        ref10x: '',
        sc_star: '',
        sc_gtf: '',
        godes: '',
        kg: '',
        known_lncRNA: '',
        bsgenome: '',
        geneid_or_symbol: 'symbol',
        is_active: true,
        description: '',
        custom_fields: {},
        visibility: 'private'
      });
    }
    setErrors({});
  }, [editGenome, isOpen]);

  // 更新字段值
  const updateField = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // 清除该字段的错误
    if (errors[field]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  // 表单验证
  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};
    REQUIRED_FIELDS.forEach(field => {
      if (!formData[field] || !formData[field].trim()) {
        newErrors[field] = `${FIELD_LABELS[field] || field} 是必填项`;
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
      if (editGenome) {
        // 更新
        await genomeApi.updateGenome(editGenome.genomeid, formData);
      } else {
        // 创建
        await genomeApi.createGenome(formData);
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

  // 渲染字段输入框
  const renderField = (field: string) => {
    const label = FIELD_LABELS[field] || field;
    const isRequired = REQUIRED_FIELDS.includes(field);
    const error = errors[field];

    // 特殊字段处理
    if (field === 'geneid_or_symbol') {
      return (
        <div key={field} className="space-y-1">
          <label className="text-xs text-neutral-400 flex items-center gap-1">
            {label}
            {isRequired && <span className="text-red-400">*</span>}
          </label>
          <select
            value={formData[field] || 'symbol'}
            onChange={(e) => updateField(field, e.target.value)}
            className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500"
          >
            <option value="symbol">Symbol</option>
            <option value="ensg">Ensembl ID</option>
          </select>
        </div>
      );
    }

    if (field === 'visibility') {
      return (
        <div key={field} className="space-y-1">
          <label className="text-xs text-neutral-400">{label}</label>
          <select
            value={formData[field] || 'private'}
            onChange={(e) => updateField(field, e.target.value)}
            className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500"
          >
            <option value="private">私有（仅自己可见）</option>
            <option value="team">团队（团队成员可见）</option>
            <option value="public">公开（所有用户可见）</option>
          </select>
        </div>
      );
    }

    if (field === 'description') {
      return (
        <div key={field} className="space-y-1">
          <label className="text-xs text-neutral-400">{label}</label>
          <textarea
            value={formData[field] || ''}
            onChange={(e) => updateField(field, e.target.value)}
            rows={3}
            className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500 resize-none"
            placeholder="输入描述信息..."
          />
        </div>
      );
    }

    // 判断是否为路径字段
    const isPath = field.includes('_index') || field.includes('path') || ['genome', 'chrlen', 'gff', 'gffdb', 'gtf', 'geneanno', 'genelen', 'genome_info', 'ref10x', 'sc_star', 'sc_gtf', 'godes', 'known_lncRNA'].includes(field);

    // 路径字段：使用 HybridPathInput（支持手动输入 + 文件选择）
    if (isPath) {
      // 根据字段判断选择类型：_index 字段是目录，其他是文件
      const pathType = field.includes('_index') ? 'directory' : 'file';

      return (
        <div key={field} className="space-y-1">
          <label className="text-xs text-neutral-400 flex items-center gap-1">
            {label}
            {isRequired && <span className="text-red-400">*</span>}
          </label>
          <HybridPathInput
            projectId={currentProjectId || ''}
            value={formData[field] || ''}
            onChange={(path) => updateField(field, path)}
            type={pathType}
            placeholder={pathType === 'directory' ? '/path/to/directory 或点击选择' : '/path/to/file 或点击选择'}
            error={error}
            disabled={!currentProjectId}
          />
          {!currentProjectId && (
            <p className="text-xs text-neutral-500">请先选择项目以使用文件选择功能，或直接手动输入路径</p>
          )}
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
      );
    }

    // 默认文本输入框（非路径字段）
    return (
      <div key={field} className="space-y-1">
        <label className="text-xs text-neutral-400 flex items-center gap-1">
          {label}
          {isRequired && <span className="text-red-400">*</span>}
        </label>
        <input
          type="text"
          value={formData[field] || ''}
          onChange={(e) => updateField(field, e.target.value)}
          className={`w-full bg-neutral-900 border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-purple-500 ${
            error ? 'border-red-500' : 'border-neutral-700'
          }`}
          placeholder=""
        />
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#1a1a1c] border border-neutral-800 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="shrink-0 h-14 border-b border-neutral-800 px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-purple-500/20 border border-purple-500/30 rounded-lg text-purple-400">
              <Dna size={16} />
            </div>
            <h3 className="text-white font-medium">
              {editGenome ? `编辑基因组: ${editGenome.genomeid}` : '创建新基因组'}
            </h3>
          </div>
          <button onClick={onClose} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* 字段分组 */}
          {FIELD_GROUPS.map(group => (
            <div key={group.title} className="space-y-3">
              <h4 className="text-sm font-medium text-neutral-300 border-b border-neutral-800 pb-2">
                {group.title}
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {group.fields.map(field => renderField(field))}
              </div>
            </div>
          ))}

          {/* 自定义字段 */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-neutral-300 border-b border-neutral-800 pb-2">
              自定义字段
            </h4>
            <CustomFieldsEditor
              fields={formData.custom_fields || {}}
              onChange={(fields) => updateField('custom_fields', fields)}
            />
          </div>

          {/* 权限设置 */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-neutral-300 border-b border-neutral-800 pb-2">
              权限设置
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {renderField('visibility')}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">状态</label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => updateField('is_active', e.target.checked)}
                    className="w-4 h-4 rounded border-neutral-700 bg-neutral-900 text-purple-500 focus:ring-purple-500"
                  />
                  <span className="text-sm text-neutral-300">启用此基因组</span>
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