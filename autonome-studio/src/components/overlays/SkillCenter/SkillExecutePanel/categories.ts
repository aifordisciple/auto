/**
 * 系统内置分类定义
 *
 * 扩展版分类体系，支持多级子分类
 */
import type { Category } from './types';

/**
 * 系统内置分类列表
 */
export const BUILT_IN_CATEGORIES: Category[] = [
  { id: 'all', name: '全部', icon: '📦', description: '所有可用技能' },
  {
    id: 'quality_control',
    name: '质量控制',
    icon: '🔬',
    description: '数据质量评估与控制',
    subcategories: [
      { id: 'fastq_qc', name: 'FastQ质控', icon: '🧬', description: '原始测序数据质量检测' },
      { id: 'bam_qc', name: 'BAM质控', icon: '📊', description: '比对文件质量评估' },
      { id: 'vcf_qc', name: 'VCF质控', icon: '🧪', description: '变异检测结果质控' }
    ]
  },
  {
    id: 'alignment',
    name: '序列比对',
    icon: '🧬',
    description: '序列比对与映射',
    subcategories: [
      { id: 'dna_align', name: 'DNA比对', icon: '🔗', description: 'DNA序列比对' },
      { id: 'rna_align', name: 'RNA比对', icon: '🔗', description: 'RNA序列比对' }
    ]
  },
  {
    id: 'quantification',
    name: '定量分析',
    icon: '📊',
    description: '表达定量与计数',
    subcategories: [
      { id: 'rnaseq_quant', name: 'RNA-Seq定量', icon: '📈', description: '转录组表达定量' },
      { id: 'scrna_quant', name: '单细胞定量', icon: '🔬', description: '单细胞表达分析' }
    ]
  },
  {
    id: 'differential_analysis',
    name: '差异分析',
    icon: '📉',
    description: '差异表达与统计分析',
    subcategories: [
      { id: 'degs', name: '差异基因', icon: '🧬', description: '差异表达基因分析' },
      { id: 'pathway', name: '通路富集', icon: '🗺️', description: '功能通路富集分析' }
    ]
  },
  {
    id: 'visualization',
    name: '可视化',
    icon: '📈',
    description: '数据可视化与图表生成',
    subcategories: [
      { id: 'heatmap', name: '热图', icon: '🔥', description: '表达热图绑定' },
      { id: 'volcano', name: '火山图', icon: '🌋', description: '差异分析火山图' },
      { id: 'pca', name: 'PCA分析', icon: '📐', description: '主成分分析可视化' }
    ]
  },
  {
    id: 'pipeline',
    name: '流程编排',
    icon: '⚙️',
    description: '多步骤分析流程',
    subcategories: [
      { id: 'nextflow', name: 'Nextflow', icon: '🔄', description: 'Nextflow工作流' },
      { id: 'snakemake', name: 'Snakemake', icon: '🐍', description: 'Snakemake工作流' }
    ]
  }
];