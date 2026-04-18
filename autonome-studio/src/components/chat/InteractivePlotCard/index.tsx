/**
 * InteractivePlotCard 主组件
 *
 * NL2Vis 动态交互式可视化分析卡片
 *
 * 功能：
 * - 顶部：高保真可视化主舞台（ECharts）
 * - 底部：动态参数沙盘系统（表单控件）
 * - 导出：PDF/PNG/TSV 一键导出
 */

'use client';

import { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Download, RefreshCw, ChevronDown, ChevronUp, Loader2, Settings2, Database, CheckCircle, AlertCircle } from 'lucide-react';
import type { ECharts } from 'echarts';
import { jsPDF } from 'jspdf';
import 'svg2pdf.js';

import type {
  InteractivePlotData,
  InteractivePlotCardProps,
  ParameterAdjustment,
  ExportFormat,
} from './types';
import { getInitialParameterValues, recordAdjustment, dataToTsv } from './utils';
import { PlotCanvas } from './PlotCanvas';
import { fetchAPI } from '@/lib/api';

// ==========================================
// ✨ API 响应类型
// ==========================================

interface PlotDataResponse {
  status: string;
  data?: Record<string, unknown>[];
  columns?: string[];
  row_count?: number;
  error?: string;
}

// ✨ 默认选项配置（当 AI 未提供 options 时使用）
const DEFAULT_OPTIONS: Record<string, string[]> = {
  color_scheme: ['viridis', 'plasma', 'Set2', 'Set3', 'Dark2', 'Paired'],
  orientation: ['vertical', 'horizontal'],
};

// ✨ 获取参数选项（优先使用 AI 提供的 options，否则使用默认值）
const getParameterOptions = (key: string, options: string[] | undefined): string[] => {
  if (options && options.length > 0) {
    return options;
  }
  return DEFAULT_OPTIONS[key] || [];
};

// ==========================================
// ✨ 交互式图表卡片主组件
// ==========================================

export function InteractivePlotCard({
  data,
  messageId,
  projectId,
  onRedraw,
}: InteractivePlotCardProps) {
  // ✨ 参数状态（与全局 store 隔离）
  const [parameters, setParameters] = useState<Record<string, unknown>>(() =>
    getInitialParameterValues(data.parameters)
  );

  // ✨ 图表数据状态
  const [chartData, setChartData] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [isLoadingData, setIsLoadingData] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);

  // ✨ 参数调整历史
  const [adjustmentHistory, setAdjustmentHistory] = useState<ParameterAdjustment[]>([]);

  // ✨ 参数面板展开状态
  const [isParamPanelOpen, setIsParamPanelOpen] = useState(true);

  // ✨ 导出成功提示
  const [exportSuccess, setExportSuccess] = useState<string | null>(null);

  // ✨ ECharts 实例引用
  const chartInstanceRef = useRef<ECharts | null>(null);

  // ✨ 加载数据函数（必须定义在 useEffect 之前）
  const loadPlotData = useCallback(async () => {
    if (!data.data_source) {
      setDataError('未指定数据源');
      return;
    }

    setIsLoadingData(true);
    setDataError(null);

    try {
      const params = new URLSearchParams({
        data_source: data.data_source,
        limit: '500',
      });
      if (projectId) {
        params.append('project_id', projectId);
      }

      const response = await fetchAPI(`/plot/data?${params.toString()}`) as PlotDataResponse;

      if (response.status === 'success' && response.data) {
        setChartData(response.data);
        setColumns(response.columns || []);
      } else {
        setDataError(response.error || '加载数据失败');
      }
    } catch (err) {
      console.error('[InteractivePlotCard] 加载数据失败:', err);
      setDataError(err instanceof Error ? err.message : '加载数据失败');
    } finally {
      setIsLoadingData(false);
    }
  }, [data.data_source, projectId]);

  // ✨ 组件挂载时加载数据
  useEffect(() => {
    loadPlotData();
  }, [loadPlotData]);

  // ✨ 监听交互式图表刷新事件
  useEffect(() => {
    const handleRefresh = (event: CustomEvent) => {
      // 检查是否是当前图表的数据源
      const detail = event.detail as { data_source?: string; taskName?: string } | undefined;
      if (detail?.data_source === data.data_source || !detail?.data_source) {
        // 延迟 500ms 等待后端写入完成
        setTimeout(() => loadPlotData(), 500);
      }
    };

    window.addEventListener('interactive-plot-refresh', handleRefresh as EventListener);
    return () => {
      window.removeEventListener('interactive-plot-refresh', handleRefresh as EventListener);
    };
  }, [data.data_source, loadPlotData]);

  // ✨ 生成 ECharts 配置（基于真实数据）
  const chartConfig = useMemo(() => {
    if (!chartData.length) return null;

    // 从参数获取列名，如果未指定则使用默认值
    const xColumn = parameters.x_column as string || columns[0] || 'x';
    const yColumn = parameters.y_column as string || columns[1] || 'y';

    // 根据图表类型生成配置
    return generateChartConfig(
      data.plot_type,
      chartData,
      columns,
      { ...parameters, x_column: xColumn, y_column: yColumn },
      data.title
    );
  }, [chartData, columns, data.plot_type, data.title, parameters]);

  // ✨ 处理参数变更
  const handleParameterChange = useCallback((key: string, value: unknown) => {
    setParameters((prev) => {
      const oldValue = prev[key];
      if (oldValue !== value) {
        setAdjustmentHistory((history) =>
          recordAdjustment(key, oldValue, value, history)
        );
      }
      return { ...prev, [key]: value };
    });
  }, []);

  // ✨ 应用参数重绘图表
  const handleApply = useCallback(async () => {
    setIsLoadingData(true);
    try {
      // 参数变更已通过 useMemo 自动触发重绘
      await new Promise(resolve => setTimeout(resolve, 200));
    } finally {
      setIsLoadingData(false);
    }
  }, []);

  // ✨ 图表实例就绪回调
  const handleChartReady = useCallback((instance: unknown) => {
    chartInstanceRef.current = instance as ECharts;
  }, []);

  // ✨ 导出处理
  const handleExport = useCallback(async (format: ExportFormat) => {
    const chart = chartInstanceRef.current;
    if (!chart) {
      console.error('[InteractivePlotCard] 图表实例不存在');
      return;
    }

    try {
      const title = data.title || 'chart';
      const safeTitle = title.replace(/[^a-zA-Z0-9\u4e00-\u9fa5]/g, '_');

      switch (format) {
        case 'png_300dpi':
        case 'png_600dpi': {
          const pixelRatio = format === 'png_600dpi' ? 6 : 3;
          const dataUrl = chart.getDataURL({
            type: 'png',
            pixelRatio,
            backgroundColor: '#0a0a0b',
          });
          const link = document.createElement('a');
          link.href = dataUrl;
          link.download = `${safeTitle}_${format}.png`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          setExportSuccess('PNG 导出成功');
          break;
        }

        case 'pdf': {
          // ✨ 使用 svg2pdf.js 导出矢量 PDF
          try {
            // 获取 SVG 元素
            const svgElement = chart.getDom().querySelector('svg');
            if (!svgElement) {
              throw new Error('SVG element not found');
            }

            // 克隆 SVG 避免修改原始元素
            const clonedSvg = svgElement.cloneNode(true) as SVGSVGElement;

            // 设置 SVG 尺寸（使用实际渲染尺寸）
            const svgRect = svgElement.getBoundingClientRect();
            const svgWidth = svgRect.width;
            const svgHeight = svgRect.height;

            // 设置 SVG 的 width/height 属性（svg2pdf.js 需要这些属性）
            clonedSvg.setAttribute('width', `${svgWidth}px`);
            clonedSvg.setAttribute('height', `${svgHeight}px`);

            // 创建 PDF（横向 A4）
            const pdf = new jsPDF({
              orientation: svgWidth > svgHeight ? 'landscape' : 'portrait',
              unit: 'px',
              format: [svgWidth + 100, svgHeight + 100],
            });

            // ✨ 使用 svg2pdf.js 直接嵌入矢量 SVG
            // 计算 SVG 在 PDF 中的位置（居中）
            const xOffset = 50;
            const yOffset = 40;

            // 添加标题
            pdf.setFontSize(16);
            pdf.setTextColor(50, 50, 50);
            pdf.text(title, svgWidth / 2 + xOffset, 20, { align: 'center' });

            // 直接嵌入 SVG（矢量格式）
            await pdf.svg(clonedSvg, {
              x: xOffset,
              y: yOffset,
              width: svgWidth,
              height: svgHeight,
            });

            // 添加页脚
            pdf.setFontSize(8);
            pdf.setTextColor(150, 150, 150);
            pdf.text(`Generated by Autonome Studio - ${new Date().toLocaleString()}`, svgWidth / 2 + xOffset, svgHeight + yOffset + 20, { align: 'center' });

            // 保存 PDF
            pdf.save(`${safeTitle}.pdf`);
            setExportSuccess('PDF 导出成功（矢量格式）');
          } catch (error) {
            console.error('[InteractivePlotCard] PDF vector export error:', error);
            // 回退到 PNG 方式
            const dataUrl = chart.getDataURL({
              type: 'png',
              pixelRatio: 3,
              backgroundColor: '#0a0a0b',
            });
            const pdf = new jsPDF({
              orientation: 'landscape',
              unit: 'mm',
              format: 'a4',
            });
            pdf.setFontSize(16);
            pdf.setTextColor(50, 50, 50);
            pdf.text(title, 148.5, 15, { align: 'center' });
            pdf.addImage(dataUrl, 'PNG', 20, 25, 257, 170);
            pdf.save(`${safeTitle}.pdf`);
            setExportSuccess('PDF 导出成功');
          }
          break;
        }

        case 'tsv': {
          if (chartData.length > 0) {
            const tsvContent = dataToTsv(chartData);
            const blob = new Blob([tsvContent], { type: 'text/tab-separated-values' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${safeTitle}_data.tsv`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            setExportSuccess('TSV 数据已导出');
          }
          break;
        }

        default:
          break;
      }

      setTimeout(() => setExportSuccess(null), 3000);
    } catch (error) {
      console.error('[InteractivePlotCard] 导出失败:', error);
      setExportSuccess('导出失败');
      setTimeout(() => setExportSuccess(null), 3000);
    }
  }, [chartData, data.title, data.aspect_ratio]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="w-full bg-gradient-to-br from-neutral-900 to-neutral-950 rounded-xl border border-violet-500/20 overflow-hidden shadow-lg"
    >
      {/* ✨ 顶部标题栏 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-violet-500/10 bg-violet-500/5">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
          <h3 className="text-sm font-medium text-violet-200">{data.title}</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-neutral-500">{data.plot_type}</span>
          {isLoadingData && (
            <Loader2 size={14} className="animate-spin text-violet-400" />
          )}
        </div>
      </div>

      {/* ✨ 图表画布区域 */}
      <div className="relative min-h-[300px] bg-neutral-950">
        {dataError ? (
          <div className="flex flex-col items-center justify-center h-[300px] text-neutral-400">
            <AlertCircle size={32} className="mb-2 text-amber-400" />
            <p className="text-sm font-medium">数据处理待执行</p>
            <p className="text-xs text-neutral-500 mt-1 text-center max-w-[280px]">
              请先执行上方的数据处理代码，生成统计结果后再查看交互式图表
            </p>
            <button
              onClick={loadPlotData}
              className="mt-3 px-4 py-1.5 bg-violet-600 hover:bg-violet-700 rounded text-xs text-white transition-colors"
            >
              重新加载数据
            </button>
          </div>
        ) : isLoadingData ? (
          <div className="flex items-center justify-center h-[300px] text-neutral-500">
            <Loader2 size={24} className="animate-spin mr-2" />
            <span className="text-sm">加载数据中...</span>
          </div>
        ) : !chartData.length ? (
          <div className="flex flex-col items-center justify-center h-[300px] text-neutral-400">
            <Database size={32} className="mb-2 opacity-50" />
            <p className="text-sm">等待数据...</p>
            <p className="text-xs text-neutral-500 mt-1">
              请执行数据处理代码生成结果
            </p>
          </div>
        ) : (
          <PlotCanvas
            plotType={data.plot_type}
            config={chartConfig || {}}
            title={data.title}
            dataSource={data.data_source}
            parameters={parameters}
            onChartReady={handleChartReady}
            aspectRatio={data.aspect_ratio || 1.5}
          />
        )}
        {/* ✨ 数据源提示 */}
        {data.data_source && !dataError && (
          <div className="absolute bottom-2 right-2 flex items-center gap-1 px-2 py-1 bg-neutral-900/80 rounded text-[10px] text-neutral-500">
            <Database size={10} />
            <span className="truncate max-w-[150px]">{data.data_source.split('/').pop()}</span>
            {chartData.length > 0 && (
              <span className="text-neutral-600 ml-1">({chartData.length} 行)</span>
            )}
          </div>
        )}
      </div>

      {/* ✨ 参数沙盘控制区 */}
      <div className="border-t border-violet-500/10">
        <button
          onClick={() => setIsParamPanelOpen(!isParamPanelOpen)}
          className="w-full flex items-center justify-between px-4 py-2 bg-neutral-900/50 hover:bg-neutral-800/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Settings2 size={14} className="text-violet-400" />
            <span className="text-xs text-violet-300">参数控制面板</span>
            <span className="text-xs text-neutral-600">
              ({Object.keys(data.parameters).length} 个参数)
            </span>
          </div>
          {isParamPanelOpen ? (
            <ChevronUp size={14} className="text-neutral-500" />
          ) : (
            <ChevronDown size={14} className="text-neutral-500" />
          )}
        </button>

        <AnimatePresence>
          {isParamPanelOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="p-4 bg-neutral-900/30">
                {/* 参数控件网格 */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                  {Object.entries(data.parameters).map(([key, def]) => (
                    <div key={key} className="space-y-1">
                      <label className="text-xs text-neutral-400 flex items-center justify-between">
                        <span>{def.label}</span>
                        {def.description && (
                          <span className="text-neutral-600 text-[10px]" title={def.description}>?</span>
                        )}
                      </label>

                      {/* ✨ select 控件 - 使用实际列名作为选项 */}
                      {def.type === 'select' && (
                        <select
                          value={parameters[key] as string}
                          onChange={(e) => handleParameterChange(key, e.target.value)}
                          className="w-full bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs text-neutral-200 focus:outline-none focus:border-violet-500"
                        >
                          {/* 如果参数是列选择，使用实际列名 */}
                          {(key === 'x_column' || key === 'y_column') && columns.length > 0 ? (
                            columns.map((col) => (
                              <option key={col} value={col}>{col}</option>
                            ))
                          ) : (
                            getParameterOptions(key, def.options).map((opt) => (
                              <option key={opt} value={opt}>{opt}</option>
                            ))
                          )}
                        </select>
                      )}

                      {def.type === 'slider' && (
                        <div className="space-y-1">
                          <input
                            type="range"
                            min={def.min}
                            max={def.max}
                            step={def.step || 1}
                            value={parameters[key] as number}
                            onChange={(e) => handleParameterChange(key, Number(e.target.value))}
                            className="w-full accent-violet-500"
                          />
                          <div className="text-[10px] text-neutral-500 text-right">
                            {parameters[key] as number}
                          </div>
                        </div>
                      )}

                      {def.type === 'boolean' && (
                        <button
                          onClick={() => handleParameterChange(key, !parameters[key])}
                          className={`w-full px-2 py-1 rounded text-xs transition-colors ${
                            parameters[key] ? 'bg-violet-500 text-white' : 'bg-neutral-800 text-neutral-400'
                          }`}
                        >
                          {parameters[key] ? 'ON' : 'OFF'}
                        </button>
                      )}

                      {def.type === 'text' && (
                        <input
                          type="text"
                          value={parameters[key] as string}
                          onChange={(e) => handleParameterChange(key, e.target.value)}
                          className="w-full bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs text-neutral-200 focus:outline-none focus:border-violet-500"
                        />
                      )}

                      {def.type === 'number' && (
                        <input
                          type="number"
                          min={def.min}
                          max={def.max}
                          value={parameters[key] as number}
                          onChange={(e) => handleParameterChange(key, Number(e.target.value))}
                          className="w-full bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs text-neutral-200 focus:outline-none focus:border-violet-500"
                        />
                      )}

                      {def.type === 'color' && (
                        <input
                          type="color"
                          value={parameters[key] as string}
                          onChange={(e) => handleParameterChange(key, e.target.value)}
                          className="w-full h-6 rounded cursor-pointer"
                        />
                      )}
                    </div>
                  ))}
                </div>

                {/* 应用按钮 */}
                <div className="flex items-center justify-between mt-4 pt-3 border-t border-neutral-800">
                  <div className="text-xs text-neutral-600">
                    {adjustmentHistory.length > 0 && (
                      <span>{adjustmentHistory.length} 次调整</span>
                    )}
                  </div>
                  <button
                    onClick={handleApply}
                    disabled={isLoadingData}
                    className="flex items-center gap-2 px-4 py-1.5 bg-violet-600 hover:bg-violet-700 disabled:bg-violet-800/50 text-white text-xs rounded transition-colors"
                  >
                    {isLoadingData ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <RefreshCw size={12} />
                    )}
                    应用更改
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ✨ 导出面板 */}
      <div className="flex items-center gap-2 px-4 py-2 border-t border-violet-500/10 bg-neutral-900/30">
        <Download size={12} className="text-neutral-500" />
        <span className="text-xs text-neutral-500">导出：</span>
        <div className="flex gap-1">
          {(data.export_formats || ['pdf', 'png_300dpi', 'tsv']).map((format) => (
            <button
              key={format}
              onClick={() => handleExport(format as ExportFormat)}
              className="px-2 py-0.5 text-[10px] bg-neutral-800 hover:bg-violet-600 text-neutral-400 hover:text-white rounded transition-colors"
            >
              {format.toUpperCase().replace('_', ' ')}
            </button>
          ))}
        </div>
        {exportSuccess && (
          <div className="flex items-center gap-1 ml-auto text-[10px] text-emerald-400">
            <CheckCircle size={10} />
            <span>{exportSuccess}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ==========================================
// ✨ 图表配置生成函数
// ==========================================

function generateChartConfig(
  plotType: string,
  data: Record<string, unknown>[],
  columns: string[],
  parameters: Record<string, unknown>,
  title: string
): Record<string, unknown> {
  const xColumn = parameters.x_column as string || columns[0] || 'x';
  const yColumn = parameters.y_column as string || columns[1] || 'y';

  // 基础配置
  const config: Record<string, unknown> = {
    title: {
      text: title,
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 'bold', color: '#e4e4e7' },
    },
    tooltip: {
      trigger: plotType === 'pie' ? 'item' : 'axis',
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#3f3f46',
      textStyle: { color: '#e4e4e7' },
    },
    grid: {
      left: '5%',
      right: '5%',
      bottom: '15%',
      top: '15%',
      containLabel: true,
    },
  };

  // 根据图表类型生成系列
  switch (plotType) {
    case 'scatter':
    case 'volcano':
    case 'pca': {
      const seriesData = data.slice(0, 200).map(row => {
        const x = row[xColumn];
        const y = row[yColumn];
        return [
          typeof x === 'number' ? x : parseFloat(String(x)) || 0,
          typeof y === 'number' ? y : parseFloat(String(y)) || 0,
        ];
      }).filter(([x, y]) => !isNaN(x) && !isNaN(y));

      config.xAxis = {
        type: 'value',
        name: xColumn,
        nameTextStyle: { color: '#a1a1aa' },
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
        splitLine: { lineStyle: { color: '#27272a' } },
      };
      config.yAxis = {
        type: 'value',
        name: yColumn,
        nameTextStyle: { color: '#a1a1aa' },
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
        splitLine: { lineStyle: { color: '#27272a' } },
      };
      config.series = [{
        type: 'scatter',
        symbolSize: (parameters.point_size as number) || 8,
        data: seriesData,
        itemStyle: { color: '#a78bfa' },
      }];
      break;
    }

    case 'bar':
    case 'line': {
      const limitedData = data.slice(0, 50);
      const categories = limitedData.map(row => String(row[xColumn] || ''));
      const values = limitedData.map(row => {
        const v = row[yColumn];
        return typeof v === 'number' ? v : parseFloat(String(v)) || 0;
      });

      // ✨ 参数处理
      const colorScheme = (parameters.color_scheme as string) || 'viridis';
      const barWidth = (parameters.bar_width as number) || 0.7;
      const showValues = (parameters.show_values as boolean) ?? true;
      const orientation = (parameters.orientation as string) || 'vertical';
      const showLegend = (parameters.show_legend as boolean) ?? false;

      // ✨ 配色方案映射
      const colorMap: Record<string, string[]> = {
        viridis: ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725'],
        plasma: ['#0d0887', '#46039f', '#7201a8', '#9c179e', '#bd3786', '#d8576b', '#ed7953', '#fb9f3a', '#fdca26', '#f0f921'],
        Set2: ['#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3', '#a6d854', '#ffd92f', '#e5c494', '#b3b3b3'],
        Set3: ['#8dd3c7', '#ffffb3', '#bebada', '#fb8072', '#80b1d3', '#fdb462', '#b3de69', '#fccde5', '#d9d9d9', '#bc80bd'],
        Dark2: ['#1b9e77', '#d95f02', '#7570b3', '#e7298a', '#66a61e', '#e6ab02', '#a6761d', '#666666'],
        Paired: ['#a6cee3', '#1f78b4', '#b2df8a', '#33a02c', '#fb9a99', '#e31a1c', '#fdbf6f', '#ff7f00', '#cab2d6', '#6a3d9a'],
      };
      const colors = colorMap[colorScheme] || colorMap.viridis;

      // ✨ 根据方向决定轴配置
      const isHorizontal = orientation === 'horizontal';

      config.xAxis = {
        type: isHorizontal ? 'value' : 'category',
        data: isHorizontal ? undefined : categories,
        name: isHorizontal ? yColumn : xColumn,
        nameTextStyle: { color: '#a1a1aa' },
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa', rotate: isHorizontal ? 0 : 30 },
        splitLine: isHorizontal ? { lineStyle: { color: '#27272a' } } : undefined,
      };
      config.yAxis = {
        type: isHorizontal ? 'category' : 'value',
        data: isHorizontal ? categories : undefined,
        name: isHorizontal ? xColumn : yColumn,
        nameTextStyle: { color: '#a1a1aa' },
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
        splitLine: isHorizontal ? undefined : { lineStyle: { color: '#27272a' } },
      };

      config.series = [{
        type: plotType,
        data: values,
        smooth: (parameters.smooth as boolean) || false,
        barWidth: `${barWidth * 100}%`,
        itemStyle: plotType === 'bar'
          ? {
              color: colors[0],
              borderRadius: isHorizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
            }
          : undefined,
        lineStyle: plotType === 'line' ? { color: colors[0], width: 2 } : undefined,
        // ✨ 显示数值标签
        label: showValues && plotType === 'bar' ? {
          show: true,
          position: isHorizontal ? 'right' : 'top',
          color: '#a1a1aa',
          fontSize: 11,
          formatter: '{c}',
        } : undefined,
      }];

      // ✨ 图例
      if (showLegend) {
        config.legend = {
          show: true,
          top: 30,
          textStyle: { color: '#a1a1aa' },
        };
      }

      break;
    }

    case 'pie': {
      const pieData = data.slice(0, 10).map(row => ({
        name: String(row[xColumn] || ''),
        value: typeof row[yColumn] === 'number' ? row[yColumn] : parseFloat(String(row[yColumn])) || 0,
      }));
      config.series = [{
        type: 'pie',
        radius: ['40%', '70%'],
        data: pieData,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#0a0a0b',
          borderWidth: 2,
        },
        label: { show: true, formatter: '{b}: {d}%', color: '#a1a1aa' },
      }];
      delete config.grid;
      break;
    }

    default:
      break;
  }

  return config;
}

export default InteractivePlotCard;