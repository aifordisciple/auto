/**
 * DirectoryScanner - 目录扫描组件
 *
 * 功能：
 * 1. 选择要扫描的目录
 * 2. 配置扫描选项（递归、自动配对等）
 * 3. 预览扫描结果
 * 4. 支持导入现有 TSV 文件
 */

'use client';

import React, { useState, useRef } from 'react';
import {
  FolderOpen,
  Search,
  Loader2,
  Upload,
  FileText,
  ChevronRight,
  CheckCircle,
  AlertCircle
} from "lucide-react";
import { toast } from 'sonner';
import { BASE_URL, fetchAPI } from "@/lib/api";
import { FilePickerButton } from "@/components/FilePicker";

// ==========================================
// 类型定义
// ==========================================

export interface SampleEntry {
  name: string;
  path: string;
  data_type: string;
  group: string;
  read2_path?: string | null;
}

export interface ScanResult {
  samples: SampleEntry[];
  tsv_content: string;
  summary: {
    total_samples: number;
    data_types: Record<string, number>;
    groups: Record<string, number>;
  };
  warnings?: string[];  // 新增：警告信息
}

interface DirectoryScannerProps {
  projectId: string;
  skillType: 'fastqc' | 'singlecell' | 'generic';
  skillId?: string;  // 新增：用于判断 RNA-seq 等流程
  onScanComplete: (result: ScanResult) => void;
  onImportTsv: (content: string) => void;
}

// ==========================================
// 组件
// ==========================================

export function DirectoryScanner({
  projectId,
  skillType,
  skillId = '',
  onScanComplete,
  onImportTsv
}: DirectoryScannerProps) {
  // 状态
  const [directory, setDirectory] = useState('');
  const [recursive, setRecursive] = useState(true);
  const [autoPair, setAutoPair] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [previewData, setPreviewData] = useState<ScanResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 执行扫描
  const handleScan = async () => {
    if (!directory) {
      toast.error('请选择要扫描的目录');
      return;
    }

    setIsScanning(true);
    setPreviewData(null);

    // ==========================================
    // 确定扫描类型
    // - fastqc 技能：使用 fastqc 扫描
    // - singlecell 技能：使用 singlecell 扫描
    // - RNA-seq 相关技能（包含 rnaseq, rna, transcriptome 等）：使用 fastqc 扫描
    // - 其他 generic 类型：默认使用 fastqc 扫描（处理 FastQ 文件）
    // ==========================================
    const skillIdLower = skillId.toLowerCase();
    const isRnaSeq = ['rnaseq', 'rna', 'seq', 'transcriptome', 'transcript', 'deg', 'differential'].some(kw => skillIdLower.includes(kw));

    // 判断扫描类型：单细胞扫描只用于明确的单细胞技能
    const actualScanType = skillType === 'singlecell' ? 'singlecell' : 'fastqc';

    try {
      const token = localStorage.getItem('autonome_access_token');

      const res = await fetch(`${BASE_URL}/api/projects/${projectId}/sample-sheets/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          directory,
          scan_type: actualScanType,
          recursive,
          auto_pair: autoPair
        })
      });

      const data = await res.json();

      if (data.status === 'success') {
        setPreviewData(data);

        // 显示警告信息（如果有）
        if (data.warnings && data.warnings.length > 0) {
          data.warnings.forEach((warning: string) => {
            toast.warning(warning, { duration: 8000 });
          });
        }

        if (data.samples.length > 0) {
          toast.success(`发现 ${data.samples.length} 个样本`);
        } else {
          toast.info('未发现匹配的数据文件，请检查目录内容或选择正确的技能类型');
        }
      } else {
        throw new Error(data.detail || '扫描失败');
      }
    } catch (e: any) {
      toast.error(`扫描失败: ${e.message}`);
    } finally {
      setIsScanning(false);
    }
  };

  // 确认使用扫描结果
  const handleConfirmScan = () => {
    if (previewData) {
      onScanComplete(previewData);
    }
  };

  // 处理导入文件
  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const content = await file.text();
      onImportTsv(content);
      toast.success(`已导入文件: ${file.name}`);
    } catch (e: any) {
      toast.error(`导入失败: ${e.message}`);
    }

    // 重置 input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="h-full flex">
      {/* 左侧：扫描配置 */}
      <div className="w-[320px] border-r border-neutral-800 p-6 flex flex-col gap-6">
        {/* 目录选择 */}
        <div>
          <label className="text-sm font-medium text-neutral-300 mb-2 block">
            数据目录
          </label>
          <FilePickerButton
            projectId={projectId}
            value={directory}
            onChange={setDirectory}
            type="directory"
            placeholder="选择包含数据的目录..."
          />
          <p className="text-xs text-neutral-500 mt-1.5">
            选择包含 FastQ 或单细胞数据的目录
          </p>
        </div>

        {/* 扫描选项 */}
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-neutral-300">扫描选项</h4>

          <label className="flex items-center gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
              className="w-4 h-4 rounded border-neutral-600 bg-neutral-800 text-blue-500 focus:ring-blue-500/30"
            />
            <span className="text-sm text-neutral-400 group-hover:text-neutral-300 transition-colors">
              递归扫描子目录
            </span>
          </label>

          {skillType === 'fastqc' && (
            <label className="flex items-center gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={autoPair}
                onChange={(e) => setAutoPair(e.target.checked)}
                className="w-4 h-4 rounded border-neutral-600 bg-neutral-800 text-blue-500 focus:ring-blue-500/30"
              />
              <span className="text-sm text-neutral-400 group-hover:text-neutral-300 transition-colors">
                自动配对双端数据
              </span>
            </label>
          )}
        </div>

        {/* 扫描按钮 */}
        <button
          onClick={handleScan}
          disabled={isScanning || !directory}
          className="flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white font-medium rounded-lg transition-colors"
        >
          {isScanning ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              扫描中...
            </>
          ) : (
            <>
              <Search size={18} />
              开始扫描
            </>
          )}
        </button>

        {/* 导入 TSV */}
        <div className="pt-4 border-t border-neutral-800">
          <h4 className="text-sm font-medium text-neutral-300 mb-3">或导入已有文件</h4>
          <input
            ref={fileInputRef}
            type="file"
            accept=".tsv,.txt,.csv"
            onChange={handleImportFile}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 rounded-lg transition-colors"
          >
            <Upload size={16} />
            导入 TSV 文件
          </button>
        </div>
      </div>

      {/* 右侧：预览结果 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {previewData ? (
          <>
            {/* 摘要信息 */}
            <div className="shrink-0 p-4 border-b border-neutral-800 bg-neutral-900/30">
              <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                  <CheckCircle size={16} className="text-green-400" />
                  <span className="text-sm font-medium text-neutral-300">
                    发现 {previewData.summary.total_samples} 个样本
                  </span>
                </div>

                {Object.keys(previewData.summary.data_types).length > 0 && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-neutral-500">数据类型:</span>
                    {Object.entries(previewData.summary.data_types).map(([type, count]) => (
                      <span key={type} className="px-2 py-0.5 bg-neutral-800 text-neutral-300 rounded">
                        {type}: {count}
                      </span>
                    ))}
                  </div>
                )}

                {Object.keys(previewData.summary.groups).length > 0 && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-neutral-500">分组:</span>
                    {Object.entries(previewData.summary.groups).map(([group, count]) => (
                      <span key={group} className="px-2 py-0.5 bg-blue-500/10 text-blue-300 rounded border border-blue-500/20">
                        {group}: {count}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* 样本列表 */}
            <div className="flex-1 overflow-auto p-4 custom-scrollbar">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-[#141416] z-10">
                  <tr className="border-b border-neutral-800">
                    {skillType === 'fastqc' ? (
                      <>
                        <th className="text-left py-2 px-3 text-neutral-400 font-medium">样本名</th>
                        <th className="text-left py-2 px-3 text-neutral-400 font-medium">Read1 路径</th>
                        <th className="text-left py-2 px-3 text-neutral-400 font-medium">Read2 路径</th>
                        <th className="text-left py-2 px-3 text-neutral-400 font-medium">类型</th>
                      </>
                    ) : (
                      <>
                        <th className="text-left py-2 px-3 text-neutral-400 font-medium">样本名</th>
                        <th className="text-left py-2 px-3 text-neutral-400 font-medium">输入路径</th>
                        <th className="text-left py-2 px-3 text-neutral-400 font-medium">格式</th>
                        <th className="text-left py-2 px-3 text-neutral-400 font-medium">分组</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {previewData.samples.map((sample, index) => (
                    <tr key={index} className="border-b border-neutral-800/50 hover:bg-neutral-800/30 transition-colors">
                      <td className="py-2 px-3 text-neutral-200">{sample.name}</td>
                      <td className="py-2 px-3 text-neutral-400 font-mono text-xs truncate max-w-[300px]" title={sample.path}>
                        {sample.path}
                      </td>
                      {skillType === 'fastqc' ? (
                        <>
                          <td className="py-2 px-3 text-neutral-400 font-mono text-xs truncate max-w-[200px]" title={sample.read2_path || ''}>
                            {sample.read2_path || <span className="text-neutral-600 italic">单端</span>}
                          </td>
                          <td className="py-2 px-3">
                            <span className={`px-2 py-0.5 rounded text-xs ${
                              sample.data_type === 'paired' ? 'bg-blue-500/10 text-blue-400' : 'bg-neutral-800 text-neutral-400'
                            }`}>
                              {sample.data_type}
                            </span>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="py-2 px-3">
                            <span className="px-2 py-0.5 rounded text-xs bg-purple-500/10 text-purple-400 border border-purple-500/20">
                              {sample.data_type}
                            </span>
                          </td>
                          <td className="py-2 px-3">
                            {sample.group ? (
                              <span className="px-2 py-0.5 rounded text-xs bg-green-500/10 text-green-400">
                                {sample.group}
                              </span>
                            ) : (
                              <span className="text-neutral-600 italic text-xs">待填写</span>
                            )}
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 确认按钮 */}
            <div className="shrink-0 p-4 border-t border-neutral-800 flex justify-end gap-3">
              <button
                onClick={() => setPreviewData(null)}
                className="px-4 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
              >
                重新扫描
              </button>
              <button
                onClick={handleConfirmScan}
                className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg transition-colors"
              >
                使用这些样本
                <ChevronRight size={16} />
              </button>
            </div>
          </>
        ) : (
          // 空状态
          <div className="flex-1 flex flex-col items-center justify-center gap-4">
            <div className="w-20 h-20 rounded-full bg-neutral-800/50 flex items-center justify-center">
              <FolderOpen size={36} className="text-neutral-600" />
            </div>
            <div className="text-center">
              <h3 className="text-lg font-medium text-neutral-300 mb-1">选择目录开始扫描</h3>
              <p className="text-sm text-neutral-500 max-w-md">
                {skillType === 'fastqc'
                  ? '选择包含 FastQ 文件的目录，系统将自动识别并配对双端数据'
                  : '选择包含单细胞数据的目录，系统将识别 10x、h5、BD 等格式'
                }
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default DirectoryScanner;