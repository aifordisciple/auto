"use client";

/**
 * GenomeDetailDrawer - 基因组详情抽屉
 *
 * 功能说明：
 * - 右侧滑出抽屉显示基因组详细信息
 * - 分组展示所有字段
 * - 显示自定义字段
 * - 提供快捷操作按钮
 */

import React from 'react';
import {
  X, Dna, Edit3, Trash2, Share2, CheckCircle, XCircle,
  ExternalLink, Copy, FolderCheck
} from 'lucide-react';
import { GenomeAsset, genomeApi } from '@/lib/api';
import { Button } from '@/components/ui/Button';

// ==========================================
// 类型定义
// ==========================================

interface GenomeDetailDrawerProps {
  genome: GenomeAsset | null;
  isOpen: boolean;
  onClose: () => void;
  onEdit: (genome: GenomeAsset) => void;
  onDelete: (genomeid: string) => void;
  onRefresh: () => void;
}

// 字段分组配置
const FIELD_GROUPS = [
  {
    title: '基本信息',
    fields: ['genomeid', 'species', 'version', 'species_code', 'url', 'date']
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
  geneid_or_symbol: '基因 ID 类型'
};

// ==========================================
// 辅助组件
// ==========================================

// 字段显示行
const FieldRow = ({ label, value, isPath = false }: { label: string; value: any; isPath?: boolean }) => {
  if (value === null || value === undefined || value === '') {
    return null;
  }

  const copyToClipboard = () => {
    navigator.clipboard.writeText(String(value));
  };

  return (
    <div className="flex items-start gap-2 py-2">
      <span className="text-xs text-neutral-500 w-28 shrink-0">{label}</span>
      <div className="flex-1 flex items-center gap-2 min-w-0">
        <span className={`text-sm text-neutral-300 break-all ${isPath ? 'font-mono text-xs' : ''}`}>
          {String(value)}
        </span>
        {isPath && (
          <button
            onClick={copyToClipboard}
            className="shrink-0 p-1 text-neutral-500 hover:text-white transition-colors"
            title="复制路径"
          >
            <Copy size={12} />
          </button>
        )}
      </div>
    </div>
  );
};

// ==========================================
// 主组件
// ==========================================

export function GenomeDetailDrawer({
  genome,
  isOpen,
  onClose,
  onEdit,
  onDelete,
  onRefresh
}: GenomeDetailDrawerProps) {
  if (!isOpen || !genome) return null;

  // 判断是否为路径字段
  const isPathField = (field: string) => {
    return field.includes('_index') ||
      ['genome', 'chrlen', 'gff', 'gffdb', 'gtf', 'geneanno', 'genelen', 'genome_info',
        'ref10x', 'sc_star', 'sc_gtf', 'godes', 'known_lncRNA', 'minimap2_juncbed'].includes(field);
  };

  // 复制基因组 ID
  const copyGenomeId = () => {
    navigator.clipboard.writeText(genome.genomeid);
  };

  // 验证路径
  const handleValidate = async () => {
    try {
      const result = await genomeApi.validatePaths(genome.genomeid);
      const missing = result.total_paths - result.existing_paths;
      if (missing === 0) {
        alert('✅ 所有路径验证通过！');
      } else {
        alert(`⚠️ 验证完成：${result.existing_paths}/${result.total_paths} 个路径存在，${missing} 个路径缺失`);
      }
    } catch (err: any) {
      alert('验证失败: ' + err.message);
    }
  };

  return (
    <div className="fixed inset-0 z-[150] flex justify-end">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 抽屉内容 */}
      <div className="relative w-[500px] max-w-full h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">
        {/* Header */}
        <div className="shrink-0 h-14 border-b border-neutral-800 px-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-purple-500/20 border border-purple-500/30 rounded-lg text-purple-400">
              <Dna size={16} />
            </div>
            <div>
              <h3 className="text-sm font-medium text-white">{genome.genomeid}</h3>
              <p className="text-xs text-neutral-500">{genome.species} · {genome.version}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={copyGenomeId}
              className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
              title="复制 ID"
            >
              <Copy size={16} />
            </button>
            <Button
              variant="icon"
              onClick={onClose}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* 操作栏 */}
        <div className="shrink-0 px-4 py-3 border-b border-neutral-800 flex items-center gap-2">
          <button
            onClick={() => onEdit(genome)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs rounded-lg transition-colors"
          >
            <Edit3 size={12} /> 编辑
          </button>
          <button
            onClick={handleValidate}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs rounded-lg transition-colors"
          >
            <FolderCheck size={12} /> 验证路径
          </button>
          <button
            onClick={() => onDelete(genome.genomeid)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs rounded-lg transition-colors"
          >
            <Trash2 size={12} /> 删除
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {/* 状态信息 */}
          <div className="flex items-center gap-4 p-3 bg-neutral-800/30 rounded-lg">
            <div className="flex items-center gap-2">
              <span className="text-xs text-neutral-500">状态:</span>
              {genome.is_active ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-500/10 text-green-400 border border-green-500/30">
                  <CheckCircle size={10} /> 启用
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-red-500/10 text-red-400 border border-red-500/30">
                  <XCircle size={10} /> 禁用
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-neutral-500">可见性:</span>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${
                genome.visibility === 'public'
                  ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                  : genome.visibility === 'team'
                    ? 'bg-orange-500/10 text-orange-400 border-orange-500/30'
                    : 'bg-neutral-500/10 text-neutral-400 border-neutral-500/30'
              }`}>
                {genome.visibility === 'public' ? '公开' : genome.visibility === 'team' ? '团队' : '私有'}
              </span>
            </div>
          </div>

          {/* 描述 */}
          {genome.description && (
            <div className="p-3 bg-neutral-800/30 rounded-lg">
              <p className="text-sm text-neutral-300 whitespace-pre-wrap">{genome.description}</p>
            </div>
          )}

          {/* 字段分组 */}
          {FIELD_GROUPS.map(group => {
            const fields = group.fields.filter(f => genome[f as keyof GenomeAsset]);
            if (fields.length === 0) return null;

            return (
              <div key={group.title} className="space-y-1">
                <h4 className="text-xs font-medium text-neutral-400 border-b border-neutral-800 pb-2">
                  {group.title}
                </h4>
                <div className="divide-y divide-neutral-800/50">
                  {fields.map(field => (
                    <FieldRow
                      key={field}
                      label={FIELD_LABELS[field] || field}
                      value={genome[field as keyof GenomeAsset]}
                      isPath={isPathField(field)}
                    />
                  ))}
                </div>
              </div>
            );
          })}

          {/* 自定义字段 */}
          {genome.custom_fields && Object.keys(genome.custom_fields).length > 0 && (
            <div className="space-y-1">
              <h4 className="text-xs font-medium text-neutral-400 border-b border-neutral-800 pb-2">
                自定义字段
              </h4>
              <div className="divide-y divide-neutral-800/50">
                {Object.entries(genome.custom_fields).map(([key, value]) => (
                  <FieldRow
                    key={key}
                    label={key}
                    value={value}
                  />
                ))}
              </div>
            </div>
          )}

          {/* 时间信息 */}
          <div className="space-y-1 text-xs text-neutral-500">
            <p>创建时间: {new Date(genome.created_at).toLocaleString()}</p>
            <p>更新时间: {new Date(genome.updated_at).toLocaleString()}</p>
          </div>
        </div>
      </div>
    </div>
  );
}