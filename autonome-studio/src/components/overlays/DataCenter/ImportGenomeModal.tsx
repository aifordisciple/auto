"use client";

/**
 * ImportGenomeModal - 基因组导入弹窗
 *
 * 功能说明：
 * - 支持 TSV/CSV/Excel 文件导入
 * - 预览导入数据
 * - 字段映射
 * - 批量导入
 */

import React, { useState, useCallback } from 'react';
import {
  X, Upload, FileSpreadsheet, CheckCircle, AlertCircle,
  Loader2, Table, Eye, Download
} from 'lucide-react';
import { genomeApi } from '@/lib/api';
import { Button } from '@/components/ui/Button';

// ==========================================
// 类型定义
// ==========================================

interface ImportGenomeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface PreviewRow {
  genomeid: string;
  species: string;
  version: string;
  genome: string;
  [key: string]: string;
}

// 字段列表
const REQUIRED_FIELDS = ['genomeid', 'species', 'version', 'genome'];
const ALL_FIELDS = [
  'genomeid', 'species', 'version', 'species_code', 'url', 'date',
  'genome', 'chrlen', 'gff', 'gffdb', 'gtf', 'geneanno', 'genelen', 'genome_info',
  'bowtie2_index', 'bowtie1_index', 'bwa_index', 'star_index', 'hisat2_index',
  'novoalign_index', 'minimap2_index', 'minimap2_juncbed', 'rsem_index', 'noncode_index',
  'ref10x', 'sc_star', 'sc_gtf', 'godes', 'kg', 'known_lncRNA', 'bsgenome', 'geneid_or_symbol'
];

// ==========================================
// 辅助函数
// ==========================================

const parseCSV = (text: string, delimiter: string = '\t'): string[][] => {
  const lines = text.split('\n');
  return lines
    .filter(line => line.trim() && !line.startsWith('#'))
    .map(line => line.split(delimiter));
};

const parseTSV = (text: string): string[][] => parseCSV(text, '\t');

const parseCommaCSV = (text: string): string[][] => parseCSV(text, ',');

// ==========================================
// 主组件
// ==========================================

export function ImportGenomeModal({ isOpen, onClose, onSuccess }: ImportGenomeModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [previewData, setPreviewData] = useState<PreviewRow[]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    imported: number;
    skipped: number;
    errors: string[];
  } | null>(null);

  // 处理文件选择
  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    setFile(selectedFile);
    setError(null);
    setResult(null);
    setIsPreviewLoading(true);

    try {
      const text = await selectedFile.text();
      let rows: string[][];

      // 根据文件扩展名选择解析方式
      if (selectedFile.name.endsWith('.csv')) {
        rows = parseCommaCSV(text);
      } else {
        // 默认使用 TSV 格式
        rows = parseTSV(text);
      }

      if (rows.length < 2) {
        throw new Error('文件至少需要包含标题行和一行数据');
      }

      // 第一行是标题
      const headerRow = rows[0];
      const dataRows = rows.slice(1);

      setHeaders(headerRow);

      // 转换为预览数据
      const preview: PreviewRow[] = dataRows.slice(0, 10).map(row => {
        const obj: PreviewRow = {
          genomeid: '',
          species: '',
          version: '',
          genome: '',
        };
        headerRow.forEach((h, i) => {
          obj[h] = row[i] || '';
        });
        return obj;
      });

      setPreviewData(preview);
    } catch (err: any) {
      setError(err.message || '解析文件失败');
      setPreviewData([]);
      setHeaders([]);
    } finally {
      setIsPreviewLoading(false);
    }
  }, []);

  // 执行导入
  const handleImport = async () => {
    if (!file) return;

    setIsUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await genomeApi.importTsv(formData);
      setResult({
        imported: response.imported_count || 0,
        skipped: response.skipped?.length || 0,
        errors: response.errors || [],
      });

      if (response.imported_count > 0) {
        onSuccess();
      }
    } catch (err: any) {
      setError(err.message || '导入失败');
    } finally {
      setIsUploading(false);
    }
  };

  // 关闭并重置
  const handleClose = () => {
    setFile(null);
    setPreviewData([]);
    setHeaders([]);
    setError(null);
    setResult(null);
    onClose();
  };

  // 下载模板
  const downloadTemplate = () => {
    const templateHeaders = ALL_FIELDS.join('\t');
    const exampleRow = [
      'human_gencode_v47',
      'human',
      'v47',
      'hsa',
      '--',
      '20240101',
      '/opt/data1/public/genome/human/genome/GRCh38.fa',
      '/opt/data1/public/genome/human/genome/GRCh38.chrlen.xls',
      '/opt/data1/public/genome/human/annotation/gencode_v47/annotation.gff3',
      '',
      '/opt/data1/public/genome/human/annotation/gencode_v47/annotation.gtf',
      '/opt/data1/public/genome/human/annotation/gencode_v47/anno.txt',
      '',
      '',
      '/opt/data1/public/genome/human/genome/index/bowtie2/GRCh38',
      '',
      '/opt/data1/public/genome/human/genome/index/bwa/GRCh38.fa',
      '/opt/data1/public/genome/human/genome/index/STAR',
      '/opt/data1/public/genome/human/genome/index/hisat2/GRCh38',
      '',
      '',
      '',
      '',
      '',
      '/opt/data1/public/genome/human/genome/index/ref10x/GRCh38',
      '',
      '',
      '/opt/data1/public/genome/human/annotation/gencode_v47/godes.txt',
      'hsa',
      'symbol',
      '',
      '',
      '',
    ].join('\t');

    const content = `# 基因组配置模板\n# 第一行为标题，请勿删除或修改\n${templateHeaders}\n${exampleRow}`;

    const blob = new Blob([content], { type: 'text/tab-separated-values' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'genome_template.tsv';
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#1a1a1c] border border-neutral-800 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="shrink-0 h-14 border-b border-neutral-800 px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-1.5 bg-green-500/20 border border-green-500/30 rounded-lg text-green-400">
              <Upload size={16} />
            </div>
            <h3 className="text-white font-medium">导入基因组配置</h3>
          </div>
          <Button variant="icon" onClick={handleClose}>
            <X size={18} />
          </Button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* 说明 */}
          <div className="p-4 bg-neutral-800/30 rounded-lg space-y-2">
            <h4 className="text-sm font-medium text-neutral-200">导入说明</h4>
            <ul className="text-xs text-neutral-400 space-y-1 list-disc list-inside">
              <li>支持 <strong>TSV</strong>（推荐）、<strong>CSV</strong> 格式文件</li>
              <li>文件第一行必须为标题行，包含字段名</li>
              <li>必填字段：<code className="bg-neutral-700 px-1 rounded">genomeid</code>、<code className="bg-neutral-700 px-1 rounded">species</code>、<code className="bg-neutral-700 px-1 rounded">version</code>、<code className="bg-neutral-700 px-1 rounded">genome</code></li>
              <li>已存在的 genomeid 将被跳过</li>
              <li>路径必须是 Docker 容器内可访问的绝对路径</li>
            </ul>
            <button
              onClick={downloadTemplate}
              className="flex items-center gap-2 text-xs text-purple-400 hover:text-purple-300 transition-colors mt-2"
            >
              <Download size={12} /> 下载模板文件
            </button>
          </div>

          {/* 文件选择 */}
          <div className="space-y-2">
            <label className="text-sm text-neutral-300">选择文件</label>
            <div className="relative">
              <input
                type="file"
                accept=".tsv,.csv,.xls,.xlsx"
                onChange={handleFileSelect}
                className="hidden"
                id="genome-import-file"
              />
              <label
                htmlFor="genome-import-file"
                className="flex items-center justify-center gap-3 p-8 border-2 border-dashed border-neutral-700 rounded-xl cursor-pointer hover:border-purple-500/50 transition-colors"
              >
                <div className="text-center">
                  <FileSpreadsheet size={32} className="mx-auto text-neutral-500 mb-2" />
                  {file ? (
                    <div>
                      <p className="text-sm text-neutral-300">{file.name}</p>
                      <p className="text-xs text-neutral-500">{(file.size / 1024).toFixed(1)} KB</p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-sm text-neutral-400">点击选择或拖拽文件</p>
                      <p className="text-xs text-neutral-600 mt-1">支持 .tsv, .csv 格式</p>
                    </div>
                  )}
                </div>
              </label>
            </div>
          </div>

          {/* 预览加载 */}
          {isPreviewLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={24} className="animate-spin text-purple-400" />
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-start gap-3">
              <AlertCircle size={18} className="text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-red-400">{error}</p>
              </div>
            </div>
          )}

          {/* 导入结果 */}
          {result && (
            <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg space-y-2">
              <div className="flex items-center gap-2">
                <CheckCircle size={18} className="text-green-400" />
                <span className="text-sm text-green-400 font-medium">导入完成</span>
              </div>
              <div className="text-sm text-neutral-300 space-y-1">
                <p>✅ 成功导入: <strong className="text-green-400">{result.imported}</strong> 个基因组</p>
                {result.skipped > 0 && (
                  <p>⏭️ 跳过: <strong className="text-yellow-400">{result.skipped}</strong> 个（已存在）</p>
                )}
                {result.errors.length > 0 && (
                  <div className="mt-2">
                    <p className="text-red-400">❌ 错误:</p>
                    <ul className="text-xs text-red-300 list-disc list-inside mt-1">
                      {result.errors.slice(0, 5).map((err, i) => (
                        <li key={i}>{err}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 数据预览 */}
          {previewData.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Eye size={14} className="text-neutral-400" />
                <span className="text-sm text-neutral-300">数据预览（前 10 行）</span>
              </div>
              <div className="overflow-x-auto rounded-lg border border-neutral-800">
                <table className="w-full text-xs">
                  <thead className="bg-neutral-800">
                    <tr>
                      {headers.map((h, i) => (
                        <th
                          key={i}
                          className={`px-3 py-2 text-left font-medium ${
                            REQUIRED_FIELDS.includes(h) ? 'text-purple-400' : 'text-neutral-400'
                          }`}
                        >
                          {h}
                          {REQUIRED_FIELDS.includes(h) && <span className="text-red-400 ml-1">*</span>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewData.map((row, i) => (
                      <tr key={i} className="border-t border-neutral-800 hover:bg-neutral-800/50">
                        {headers.map((h, j) => (
                          <td
                            key={j}
                            className={`px-3 py-2 ${h === 'genomeid' ? 'text-purple-400 font-mono' : 'text-neutral-300'}`}
                          >
                            {row[h] || '-'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-neutral-800 px-6 py-4 flex justify-end gap-3">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors"
          >
            关闭
          </button>
          <button
            onClick={handleImport}
            disabled={!file || previewData.length === 0 || isUploading}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 text-white text-sm rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            {isUploading ? '导入中...' : '开始导入'}
          </button>
        </div>
      </div>
    </div>
  );
}