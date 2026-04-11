/**
 * Sample Sheet Generator - 主组件
 *
 * 四步流程：
 * 1. 扫描目录 - 选择并扫描 FastQ/单细胞数据目录
 * 2. 编辑表格 - 可视化编辑 Sample Sheet
 * 3. 定义比较组 - 设置差异分析的比较组组合（可选）
 * 4. 保存复用 - 保存到项目目录供后续使用
 *
 * 支持两种模式：
 * - FastQC 模式：扫描 FastQ 文件，自动配对双端数据
 * - 单细胞模式：扫描单细胞数据，识别 10x/h5/BD/exp 等格式
 *
 * 比较组定义（步骤 3）：
 * - 仅在单细胞模式和 RNA-seq 相关技能时启用
 * - 支持用户自定义比较组或自动推断
 */

'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  FolderOpen,
  FileText,
  Table,
  GitCompare,
  Save,
  Download,
  Upload,
  ChevronRight,
  ChevronLeft,
  Check,
  Loader2,
  AlertCircle,
  CheckCircle,
  RefreshCw,
  ArrowRight
} from "lucide-react";
import { toast } from 'sonner';
import { BASE_URL, fetchAPI } from "@/lib/api";

import { DirectoryScanner, ScanResult } from './DirectoryScanner';
import { SampleTableEditor, TableData, ColumnConfig } from './SampleTableEditor';
import { ComparisonGroupEditor } from './ComparisonGroupEditor';
import {
  validateTsvContent,
  parseTsvToTableData,
  tableDataToTsv,
  ComparisonTableData,
  ComparisonGroup,
  extractGroupsFromTableData,
  inferComparisonGroups,
  comparisonGroupsToTsv,
  validateComparisonGroups
} from './utils';

// ==========================================
// 类型定义
// ==========================================

export interface SampleSheetGeneratorProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  skillId: string;
  skillType: 'fastqc' | 'singlecell' | 'generic';
  onConfirm: (filePath: string, comparisonFilePath?: string) => void;
}

type Step = 'scan' | 'edit' | 'comparison' | 'save';

// ==========================================
// 主组件
// ==========================================

export function SampleSheetGenerator({
  isOpen,
  onClose,
  projectId,
  skillId,
  skillType,
  onConfirm
}: SampleSheetGeneratorProps) {
  // 状态管理
  const [currentStep, setCurrentStep] = useState<Step>('scan');
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [tableData, setTableData] = useState<TableData>({ columns: [], rows: [] });
  const [columnConfig, setColumnConfig] = useState<ColumnConfig[]>([]);
  const [savedFilePath, setSavedFilePath] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // ==========================================
  // 比较组状态管理
  // ==========================================

  // 比较组数据
  const [comparisonData, setComparisonData] = useState<ComparisonTableData>({ comparisons: [] });
  // 可用的分组列表（从 Sample Sheet 提取）
  const [availableGroups, setAvailableGroups] = useState<string[]>([]);
  // 保存的比较组文件路径
  const [savedComparisonFilePath, setSavedComparisonFilePath] = useState<string | null>(null);
  // 比较组文件名
  const [comparisonFilename, setComparisonFilename] = useState<string>('');

  // ==========================================
  // 文件名状态管理
  // ==========================================

  // 自定义文件名状态
  const [filename, setFilename] = useState<string>('');

  /**
   * 生成默认文件名
   * 格式：samples_yyyyMMdd_HHmmss.tsv
   * 更具可读性，便于用户识别和管理
   */
  const generateDefaultFilename = useCallback(() => {
    const now = new Date();
    const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
    const timeStr = now.toTimeString().slice(0, 8).replace(/:/g, '');
    return `samples_${dateStr}_${timeStr}.tsv`;
  }, []);

  /**
   * 初始化文件名
   * 当组件打开时，如果文件名为空则生成默认文件名
   */
  useEffect(() => {
    if (isOpen && !filename) {
      setFilename(generateDefaultFilename());
    }
    if (isOpen && !comparisonFilename) {
      // 比较组文件名：comparisons_yyyyMMdd_HHmmss.tsv
      const now = new Date();
      const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
      const timeStr = now.toTimeString().slice(0, 8).replace(/:/g, '');
      setComparisonFilename(`comparisons_${dateStr}_${timeStr}.tsv`);
    }
  }, [isOpen, filename, generateDefaultFilename, comparisonFilename]);

  /**
   * 重置状态
   * 当组件关闭时重置文件名，确保下次打开时生成新的默认文件名
   */
  useEffect(() => {
    if (!isOpen) {
      setFilename('');
      setComparisonFilename('');
      setComparisonData({ comparisons: [] });
      setAvailableGroups([]);
      setSavedComparisonFilePath(null);
    }
  }, [isOpen]);

  /**
   * 判断是否需要比较组步骤
   *
   * 条件：
   * - 单细胞模式：始终启用
   * - skillId 包含 rnaseq、rna、seq、transcriptome 关键词：启用
   * - FastQC 模式：不启用（质量控制不需要比较组）
   */
  const needsComparisonStep = useMemo(() => {
    if (skillType === 'singlecell') return true;
    if (skillType === 'fastqc') return false;

    // 检查 skillId 是否包含 RNA-seq 相关关键词
    const skillIdLower = skillId.toLowerCase();
    const rnaKeywords = ['rnaseq', 'rna', 'seq', 'transcriptome', 'transcript', 'deg', 'differential', 'diff'];
    return rnaKeywords.some(kw => skillIdLower.includes(kw));
  }, [skillType, skillId]);

  // 加载列配置
  useEffect(() => {
    loadColumnConfig();
  }, [skillId]);

  const loadColumnConfig = async () => {
    try {
      const data = await fetchAPI(`/api/skills/${skillId}/sample-sheet-config`);
      if (data.status === 'success' && data.columns) {
        setColumnConfig(data.columns);
      }
    } catch (e) {
      console.error('Failed to load column config:', e);
      // 使用默认配置
      setColumnConfig(getDefaultColumnConfig(skillType));
    }
  };

  // 获取默认列配置
  const getDefaultColumnConfig = (type: string): ColumnConfig[] => {
    if (type === 'fastqc') {
      return [
        { key: 'sample_name', label: '样本名', required: true, editable: true },
        { key: 'read1_path', label: 'Read1 路径', required: true, editable: true },
        { key: 'read2_path', label: 'Read2 路径', required: false, editable: true }
      ];
    } else if (type === 'singlecell') {
      return [
        { key: 'sample_name', label: '样本名', required: true, editable: true },
        { key: 'input_path', label: '输入路径', required: true, editable: true },
        { key: 'input_format', label: '数据格式', required: true, editable: true, options: ['10x', 'exp', 'h5', 'BD', 'rds', 'rdsraw'] },
        { key: 'group_label', label: '分组标签', required: true, editable: true }
      ];
    } else {
      return [
        { key: 'sample_name', label: '样本名', required: true, editable: true },
        { key: 'path', label: '路径', required: true, editable: true },
        { key: 'type', label: '类型', required: false, editable: true },
        { key: 'group', label: '分组', required: false, editable: true }
      ];
    }
  };

  // 处理扫描完成
  const handleScanComplete = (result: ScanResult) => {
    setScanResult(result);

    // 将扫描结果转换为表格数据
    const rows = result.samples.map(sample => {
      const row: Record<string, string> = {};

      if (skillType === 'fastqc') {
        row.sample_name = sample.name;
        row.read1_path = sample.path;
        row.read2_path = sample.read2_path || '';
      } else {
        row.sample_name = sample.name;
        row.input_path = sample.path;
        row.input_format = sample.data_type;
        row.group_label = sample.group || '';
      }

      return row;
    });

    setTableData({
      columns: columnConfig,
      rows
    });

    // 进入编辑步骤
    setCurrentStep('edit');
  };

  // 处理表格数据变更
  const handleTableChange = (data: TableData) => {
    setTableData(data);

    // 自动提取分组列表（用于比较组编辑器）
    const groups = extractGroupsFromTableData(data);
    setAvailableGroups(groups);
  };

  // 处理比较组数据变更
  const handleComparisonChange = (data: ComparisonTableData) => {
    setComparisonData(data);
  };

  // 处理导入 TSV
  const handleImportTsv = (content: string) => {
    const parsed = parseTsvToTableData(content, columnConfig);
    setTableData(parsed);
    toast.success(`已导入 ${parsed.rows.length} 行数据`);
  };

  // 处理保存
  const handleSave = async () => {
    // 验证数据
    const tsvContent = tableDataToTsv(tableData);
    const validation = validateTsvContent(tsvContent, skillType);

    if (!validation.valid) {
      toast.error(validation.errors[0] || '数据验证失败');
      return;
    }

    setIsLoading(true);

    try {
      const token = localStorage.getItem('autonome_access_token');
      // 使用用户自定义的文件名，如果为空则生成默认文件名
      const filenameToUse = filename.trim() || generateDefaultFilename();

      const res = await fetch(`${BASE_URL}/api/projects/${projectId}/sample-sheets`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          filename: filenameToUse,
          content: tsvContent,
          description: `Generated for ${skillId}`
        })
      });

      const data = await res.json();

      if (data.status === 'success') {
        setSavedFilePath(data.path);
        toast.success('Sample Sheet 已保存');

        // 根据是否需要比较组步骤，决定下一步
        if (needsComparisonStep) {
          // 提取分组列表
          const groups = extractGroupsFromTableData(tableData);
          setAvailableGroups(groups);

          // 如果分组数量 >= 2，自动推断比较组
          if (groups.length >= 2) {
            const inferred = inferComparisonGroups(groups);
            setComparisonData({ comparisons: inferred });
          }

          setCurrentStep('comparison');
        } else {
          setCurrentStep('save');
        }
      } else {
        throw new Error(data.detail || '保存失败');
      }
    } catch (e: any) {
      toast.error(`保存失败: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // 从编辑步骤跳过比较组（用户选择跳过）
  const handleSkipComparison = async () => {
    setCurrentStep('save');
  };

  // 保存比较组
  const handleSaveComparison = async () => {
    // 验证比较组
    const validation = validateComparisonGroups(comparisonData.comparisons, availableGroups);

    if (!validation.valid) {
      toast.error(validation.errors[0] || '比较组验证失败');
      return;
    }

    // 如果没有定义比较组，直接跳转
    if (comparisonData.comparisons.length === 0) {
      setCurrentStep('save');
      return;
    }

    setIsLoading(true);

    try {
      const token = localStorage.getItem('autonome_access_token');
      const filenameToUse = comparisonFilename.trim() || `comparisons_${Date.now()}.tsv`;

      const res = await fetch(`${BASE_URL}/api/projects/${projectId}/sample-sheets/comparisons`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          filename: filenameToUse,
          comparisons: comparisonData.comparisons,
          link_to_sample_sheet: filename.trim() || generateDefaultFilename()
        })
      });

      const data = await res.json();

      if (data.status === 'success') {
        setSavedComparisonFilePath(data.path);
        toast.success('比较组已保存');
        setCurrentStep('save');
      } else {
        throw new Error(data.detail || '保存失败');
      }
    } catch (e: any) {
      toast.error(`保存比较组失败: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // 确认使用
  const handleConfirm = () => {
    if (savedFilePath) {
      // 同时传递 Sample Sheet 路径和比较组文件路径
      onConfirm(savedFilePath, savedComparisonFilePath || undefined);
      onClose();
    }
  };

  // 步骤配置（动态，根据是否需要比较组步骤调整）
  const steps = useMemo(() => {
    const baseSteps = [
      { id: 'scan', label: '扫描目录', icon: FolderOpen },
      { id: 'edit', label: '编辑表格', icon: Table }
    ];

    if (needsComparisonStep) {
      baseSteps.push({ id: 'comparison', label: '定义比较组', icon: GitCompare });
    }

    baseSteps.push({ id: 'save', label: '保存复用', icon: Save });

    return baseSteps;
  }, [needsComparisonStep]);

  const currentStepIndex = steps.findIndex(s => s.id === currentStep);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-[95vw] max-w-[1200px] h-[90vh] bg-[#141416] border border-neutral-700 rounded-xl shadow-2xl flex flex-col animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="shrink-0 border-b border-neutral-800 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Table size={22} className="text-blue-400" />
            <h2 className="text-lg font-semibold text-neutral-200">Sample Sheet 生成器</h2>
            <span className="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
              {skillType === 'fastqc' ? 'FastQC 模式' : skillType === 'singlecell' ? '单细胞模式' : '通用模式'}
            </span>
          </div>

          {/* 步骤指示器 */}
          <div className="flex items-center gap-2">
            {steps.map((step, index) => {
              const StepIcon = step.icon;
              const isActive = step.id === currentStep;
              const isCompleted = index < currentStepIndex;

              return (
                <React.Fragment key={step.id}>
                  {index > 0 && (
                    <ChevronRight size={14} className="text-neutral-600" />
                  )}
                  <div
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                      isActive
                        ? 'bg-blue-500/20 text-blue-300'
                        : isCompleted
                          ? 'bg-green-500/10 text-green-400'
                          : 'bg-neutral-800 text-neutral-500'
                    }`}
                  >
                    {isCompleted ? (
                      <Check size={14} />
                    ) : (
                      <StepIcon size={14} />
                    )}
                    <span className="text-xs font-medium">{step.label}</span>
                  </div>
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {currentStep === 'scan' && (
            <DirectoryScanner
              projectId={projectId}
              skillType={skillType}
              skillId={skillId}
              onScanComplete={handleScanComplete}
              onImportTsv={handleImportTsv}
            />
          )}

          {currentStep === 'edit' && (
            <SampleTableEditor
              data={tableData}
              columnConfig={columnConfig}
              onChange={handleTableChange}
              onSave={handleSave}
              onBack={() => setCurrentStep('scan')}
              isLoading={isLoading}
              filename={filename}
              onFilenameChange={setFilename}
            />
          )}

          {/* 比较组步骤 */}
          {currentStep === 'comparison' && (
            <div className="h-full flex flex-col">
              {/* 比较组编辑器 */}
              <div className="flex-1 overflow-hidden">
                <ComparisonGroupEditor
                  availableGroups={availableGroups}
                  data={comparisonData}
                  onChange={handleComparisonChange}
                  disabled={isLoading}
                />
              </div>

              {/* 底部操作栏 */}
              <div className="shrink-0 p-4 border-t border-neutral-800 flex items-center justify-between bg-neutral-900/30">
                <button
                  onClick={() => setCurrentStep('edit')}
                  className="flex items-center gap-2 px-4 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
                >
                  <ChevronLeft size={16} />
                  返回编辑
                </button>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleSkipComparison}
                    disabled={isLoading}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
                  >
                    跳过
                  </button>
                  <button
                    onClick={handleSaveComparison}
                    disabled={isLoading || comparisonData.comparisons.length === 0}
                    className="flex items-center gap-2 px-6 py-2.5 bg-purple-600 hover:bg-purple-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white font-medium rounded-lg transition-colors"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 size={16} className="animate-spin" />
                        保存中...
                      </>
                    ) : (
                      <>
                        <Check size={16} />
                        保存比较组
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 保存完成步骤 */}
          {currentStep === 'save' && (
            <div className="h-full flex flex-col items-center justify-center gap-6">
              <div className="flex items-center justify-center w-20 h-20 rounded-full bg-green-500/10 border border-green-500/30">
                <CheckCircle size={40} className="text-green-400" />
              </div>

              <div className="text-center">
                <h3 className="text-xl font-semibold text-neutral-200 mb-2">Sample Sheet 已保存</h3>
                <p className="text-sm text-neutral-400 mb-2">
                  文件路径：<code className="text-blue-400 bg-neutral-800 px-2 py-1 rounded">{savedFilePath}</code>
                </p>
                {savedComparisonFilePath && (
                  <p className="text-sm text-neutral-400 mb-2">
                    比较组文件：<code className="text-purple-400 bg-neutral-800 px-2 py-1 rounded">{savedComparisonFilePath}</code>
                  </p>
                )}
                {comparisonData.comparisons.length > 0 && !savedComparisonFilePath && (
                  <p className="text-xs text-yellow-400 mt-2">
                    注：比较组已定义但未保存为文件
                  </p>
                )}
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => setCurrentStep(needsComparisonStep ? 'comparison' : 'edit')}
                  className="flex items-center gap-2 px-4 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
                >
                  <RefreshCw size={16} />
                  继续编辑
                </button>
                <button
                  onClick={handleConfirm}
                  className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg transition-colors"
                >
                  <Check size={16} />
                  使用此 Sample Sheet
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default SampleSheetGenerator;