/**
 * InteractivePlotCard 工具函数
 *
 * NL2Vis 相关的辅助函数
 */

import type {
  PlotType,
  ParameterDefinition,
  InteractivePlotData,
  ParameterAdjustment,
  ExportFormat,
} from './types';

/**
 * 图表类型到 ECharts series type 的映射
 */
export const PLOT_TYPE_TO_ECHARTS: Record<PlotType, string> = {
  scatter: 'scatter',
  heatmap: 'heatmap',
  bar: 'bar',
  line: 'line',
  volcano: 'scatter', // 火山图使用自定义 scatter
  pca: 'scatter',
  boxplot: 'boxplot',
  violin: 'custom', // 小提琴图需要自定义系列
  pie: 'pie',
  treemap: 'treemap',
};

/**
 * 从后端数据生成参数初始值
 */
export function getInitialParameterValues(
  parameters: Record<string, ParameterDefinition>
): Record<string, unknown> {
  const values: Record<string, unknown> = {};

  Object.entries(parameters).forEach(([key, def]) => {
    values[key] = def.default;
  });

  return values;
}

/**
 * 解析 json_interactive_plot 代码块
 */
export function parseInteractivePlotCard(content: string): InteractivePlotData | null {
  if (!content) return null;

  // 匹配 ```json_interactive_plot ... ```
  const pattern = /```json_interactive_plot\s*([\s\S]*?)```/;
  const match = content.match(pattern);

  if (!match || !match[1]) {
    return null;
  }

  try {
    const jsonStr = match[1].trim();
    const data = JSON.parse(jsonStr) as InteractivePlotData;

    // 验证必要字段
    if (!data.plot_type || !data.title || !data.data_source) {
      console.warn('[parseInteractivePlotCard] Missing required fields');
      return null;
    }

    return data;
  } catch (e) {
    console.error('[parseInteractivePlotCard] JSON parse error:', e);
    return null;
  }
}

/**
 * 从 json_interactive_plot 代码块中提取并清理文本内容
 */
export function extractCleanText(content: string): string {
  if (!content) return content;

  // 移除 json_interactive_plot 代码块
  return content.replace(/```json_interactive_plot[\s\S]*?```/g, '').trim();
}

/**
 * 生成 ECharts 配置
 * 支持两种调用方式：
 * 1. 传入数据数组：generateEChartsConfig(plotType, data, parameters)
 * 2. 传入 InteractivePlotData：generateEChartsConfig(plotType, plotData, parameters)
 */
export function generateEChartsConfig(
  plotType: PlotType,
  dataOrPlotData: Record<string, unknown>[] | InteractivePlotData,
  parameters: Record<string, unknown>,
  baseConfig?: Record<string, unknown>
): Record<string, unknown> {
  // ✨ 判断是否传入了 InteractivePlotData（包含 plot_type 字段）
  const isPlotData = !Array.isArray(dataOrPlotData) && 'plot_type' in (dataOrPlotData as unknown as Record<string, unknown>);

  // ✨ 如果传入的是 InteractivePlotData，生成示例数据用于预览
  let data: Record<string, unknown>[];
  if (isPlotData) {
    const plotData = dataOrPlotData as InteractivePlotData;
    // 从 plotData 中提取参数覆盖
    const mergedParams = { ...plotData, ...parameters };
    data = generateSampleData(plotType, mergedParams);
  } else {
    data = dataOrPlotData as Record<string, unknown>[];
  }

  // 基础配置
  const config: Record<string, unknown> = {
    title: {
      text: (parameters.title as string) || '',
      left: 'center',
      textStyle: {
        fontSize: 14,
        fontWeight: 'bold',
        color: '#e4e4e7',
      },
    },
    tooltip: {
      trigger: plotType === 'pie' ? 'item' : 'axis',
      axisPointer: {
        type: plotType === 'scatter' ? 'cross' : 'shadow',
      },
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#3f3f46',
      textStyle: {
        color: '#e4e4e7',
      },
    },
    legend: {
      bottom: 10,
      left: 'center',
      textStyle: {
        color: '#a1a1aa',
      },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '15%',
      containLabel: true,
    },
    toolbox: {
      feature: {
        saveAsImage: {
          title: 'Save as Image',
          pixelRatio: 3,
          backgroundColor: '#0a0a0b',
        },
        dataZoom: {
          yAxisIndex: 'none',
        },
        restore: {},
      },
      right: 20,
      top: 10,
      iconStyle: {
        borderColor: '#71717a',
      },
    },
    ...baseConfig,
  };

  // 根据图表类型生成系列配置
  switch (plotType) {
    case 'scatter':
    case 'volcano':
    case 'pca':
      config.xAxis = {
        type: 'value',
        name: (parameters.x_label as string) || 'X',
        nameLocation: 'middle',
        nameGap: 30,
        nameTextStyle: { color: '#a1a1aa' },
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
        splitLine: { lineStyle: { color: '#27272a' } },
      };
      config.yAxis = {
        type: 'value',
        name: (parameters.y_label as string) || 'Y',
        nameLocation: 'middle',
        nameGap: 40,
        nameTextStyle: { color: '#a1a1aa' },
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
        splitLine: { lineStyle: { color: '#27272a' } },
      };
      config.series = [{
        type: 'scatter',
        symbolSize: (parameters.point_size as number) || 8,
        data: data,
        emphasis: {
          focus: 'series',
        },
        itemStyle: {
          color: '#a78bfa',
        },
      }];
      break;

    case 'bar':
      config.xAxis = {
        type: 'category',
        data: data.map((d: Record<string, unknown>) => d.category || d.name),
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa', rotate: 30 },
      };
      config.yAxis = {
        type: 'value',
        name: (parameters.y_label as string) || 'Value',
        nameTextStyle: { color: '#a1a1aa' },
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
        splitLine: { lineStyle: { color: '#27272a' } },
      };
      config.series = [{
        type: 'bar',
        data: data.map((d: Record<string, unknown>) => d.value),
        itemStyle: {
          color: (parameters.bar_color as string) || '#a78bfa',
          borderRadius: [4, 4, 0, 0],
        },
      }];
      break;

    case 'line':
      config.xAxis = {
        type: 'category',
        data: data.map((d: Record<string, unknown>) => d.x || d.category || d.name),
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
      };
      config.yAxis = {
        type: 'value',
        name: (parameters.y_label as string) || 'Value',
        nameTextStyle: { color: '#a1a1aa' },
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
        splitLine: { lineStyle: { color: '#27272a' } },
      };
      config.series = [{
        type: 'line',
        data: data.map((d: Record<string, unknown>) => d.y || d.value),
        smooth: (parameters.smooth as boolean) || false,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: {
          color: '#a78bfa',
          width: 2,
        },
        itemStyle: {
          color: '#a78bfa',
        },
      }];
      break;

    case 'heatmap':
      config.xAxis = {
        type: 'category',
        data: ['A', 'B', 'C', 'D', 'E'],
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
      };
      config.yAxis = {
        type: 'category',
        data: ['1', '2', '3', '4'],
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
      };
      config.visualMap = {
        min: 0,
        max: 10,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: '0%',
        textStyle: { color: '#a1a1aa' },
        inRange: {
          color: ['#1e1b4b', '#4c1d95', '#7c3aed', '#a78bfa', '#c4b5fd'],
        },
      };
      config.series = [{
        type: 'heatmap',
        data: data,
        label: {
          show: false,
        },
      }];
      break;

    case 'boxplot':
      config.xAxis = {
        type: 'category',
        data: data.map((d: Record<string, unknown>) => d.name || d.category),
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
      };
      config.yAxis = {
        type: 'value',
        name: (parameters.y_label as string) || 'Value',
        nameTextStyle: { color: '#a1a1aa' },
        axisLine: { lineStyle: { color: '#3f3f46' } },
        axisLabel: { color: '#a1a1aa' },
        splitLine: { lineStyle: { color: '#27272a' } },
      };
      config.series = [{
        type: 'boxplot',
        data: data.map((d: Record<string, unknown>) => d.boxData || [d.min, d.q1, d.median, d.q3, d.max]),
        itemStyle: {
          color: '#a78bfa',
          borderColor: '#7c3aed',
        },
      }];
      break;

    case 'pie':
      config.series = [{
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#0a0a0b',
          borderWidth: 2,
        },
        label: {
          show: true,
          formatter: '{b}: {d}%',
          color: '#a1a1aa',
        },
        data: data.map((d: Record<string, unknown>) => ({
          name: (d.name as string) || (d.label as string),
          value: d.value,
        })),
      }];
      // 饼图不需要坐标轴
      delete config.xAxis;
      delete config.yAxis;
      delete config.grid;
      break;

    default:
      console.warn(`[generateEChartsConfig] Unsupported plot type: ${plotType}`);
  }

  return config;
}

/**
 * 生成示例数据（用于预览图表）
 */
function generateSampleData(plotType: PlotType, parameters: Record<string, unknown>): Record<string, unknown>[] {
  switch (plotType) {
    case 'scatter':
    case 'volcano':
    case 'pca':
      return Array.from({ length: 50 }, () => ({
        x: Math.random() * 100,
        y: Math.random() * 100,
        name: `Point ${Math.floor(Math.random() * 100)}`,
      }));

    case 'bar':
      return [
        { name: 'Category A', value: 120 },
        { name: 'Category B', value: 200 },
        { name: 'Category C', value: 150 },
        { name: 'Category D', value: 80 },
        { name: 'Category E', value: 170 },
      ];

    case 'line':
      return [
        { x: 'Jan', value: 100 },
        { x: 'Feb', value: 120 },
        { x: 'Mar', value: 180 },
        { x: 'Apr', value: 150 },
        { x: 'May', value: 200 },
        { x: 'Jun', value: 170 },
      ];

    case 'heatmap':
      return [
        [0, 0, 5], [0, 1, 1], [0, 2, 3], [0, 3, 7],
        [1, 0, 2], [1, 1, 6], [1, 2, 4], [1, 3, 8],
        [2, 0, 3], [2, 1, 2], [2, 2, 7], [2, 3, 5],
        [3, 0, 4], [3, 1, 8], [3, 2, 2], [3, 3, 6],
      ].map(([x, y, value]) => ({ x, y, value }));

    case 'boxplot':
      return [
        { name: 'Group 1', boxData: [10, 20, 30, 40, 50] },
        { name: 'Group 2', boxData: [15, 25, 35, 45, 60] },
        { name: 'Group 3', boxData: [5, 15, 25, 35, 45] },
      ];

    case 'pie':
      return [
        { name: 'Slice A', value: 40 },
        { name: 'Slice B', value: 30 },
        { name: 'Slice C', value: 20 },
        { name: 'Slice D', value: 10 },
      ];

    default:
      return [{ x: 1, y: 1 }];
  }
}

/**
 * 格式化参数值为显示文本
 */
export function formatParameterValue(
  value: unknown,
  definition: ParameterDefinition
): string {
  if (value === null || value === undefined) {
    return String(definition.default);
  }

  switch (definition.type) {
    case 'boolean':
      return value ? 'Yes' : 'No';
    case 'slider':
    case 'number':
      return typeof value === 'number' ? value.toFixed(2) : String(value);
    default:
      return String(value);
  }
}

/**
 * 生成导出文件名
 */
export function generateExportFilename(
  title: string,
  format: ExportFormat
): string {
  // 清理标题，移除特殊字符
  const cleanTitle = title
    .replace(/[^a-zA-Z0-9\u4e00-\u9fa5]/g, '_')
    .replace(/_+/g, '_')
    .slice(0, 50);

  const timestamp = new Date().toISOString().slice(0, 10);

  const extMap: Record<ExportFormat, string> = {
    pdf: 'pdf',
    png_300dpi: 'png',
    png_600dpi: 'png',
    svg: 'svg',
    tsv: 'tsv',
  };

  return `${cleanTitle}_${timestamp}.${extMap[format]}`;
}

/**
 * 记录参数调整历史
 */
export function recordAdjustment(
  key: string,
  oldValue: unknown,
  newValue: unknown,
  history: ParameterAdjustment[]
): ParameterAdjustment[] {
  const adjustment: ParameterAdjustment = {
    timestamp: new Date().toISOString(),
    parameter_key: key,
    old_value: oldValue as string | number | boolean,
    new_value: newValue as string | number | boolean,
  };

  return [adjustment, ...history].slice(0, 50); // 保留最近 50 条
}

/**
 * 防抖函数
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  return (...args: Parameters<T>) => {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    timeoutId = setTimeout(() => {
      func(...args);
    }, wait);
  };
}

/**
 * 从数据数组推断列名
 */
export function inferColumns(data: Record<string, unknown>[]): string[] {
  if (!data || data.length === 0) return [];

  const firstRow = data[0];
  return Object.keys(firstRow);
}

/**
 * 将数据转换为 TSV 格式
 */
export function dataToTsv(data: Record<string, unknown>[]): string {
  if (!data || data.length === 0) return '';

  const columns = inferColumns(data);
  const header = columns.join('\t');
  const rows = data.map((row) =>
    columns.map((col) => {
      const value = row[col];
      if (value === null || value === undefined) return '';
      if (typeof value === 'string' && value.includes('\t')) {
        return `"${value}"`;
      }
      return String(value);
    }).join('\t')
  );

  return [header, ...rows].join('\n');
}