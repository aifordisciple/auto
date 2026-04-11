/**
 * InteractivePlotCard 类型定义
 *
 * NL2Vis 动态交互式可视化分析卡片的类型系统
 */

/**
 * 支持的图表类型
 */
export type PlotType =
  | 'scatter'      // 散点图
  | 'heatmap'      // 热图
  | 'bar'          // 柱状图
  | 'line'         // 折线图
  | 'volcano'      // 火山图
  | 'pca'          // PCA 图
  | 'boxplot'      // 箱线图
  | 'violin'       // 小提琴图
  | 'pie'          // 饼图
  | 'treemap';     // 树图

/**
 * 参数控件类型
 */
export type ParamControlType =
  | 'select'       // 下拉选择框
  | 'slider'       // 数值滑块
  | 'boolean'      // 开关按钮
  | 'text'         // 文本输入框
  | 'color'        // 颜色选择器
  | 'number';      // 数字输入框

/**
 * 参数定义结构
 */
export interface ParameterDefinition {
  /** 参数键名 */
  key: string;
  /** 显示标签 */
  label: string;
  /** 控件类型 */
  type: ParamControlType;
  /** 默认值 */
  default: string | number | boolean;
  /** 选项列表（select 类型） */
  options?: string[];
  /** 最小值（slider/number 类型） */
  min?: number;
  /** 最大值（slider/number 类型） */
  max?: number;
  /** 步进值（slider 类型） */
  step?: number;
  /** 帮助提示 */
  description?: string;
}

/**
 * 导出格式类型
 */
export type ExportFormat = 'pdf' | 'png_300dpi' | 'png_600dpi' | 'svg' | 'tsv';

/**
 * 交互式图表卡片数据结构
 * 后端 Agent 输出的 json_interactive_plot 格式
 */
export interface InteractivePlotData {
  /** 图表类型 */
  plot_type: PlotType;
  /** 图表标题 */
  title: string;
  /** 图表描述 */
  description?: string;
  /** 数据源路径 */
  data_source: string;
  /** 参数定义列表 */
  parameters: Record<string, ParameterDefinition>;
  /** ECharts 默认配置 */
  default_config?: Record<string, unknown>;
  /** 支持的导出格式 */
  export_formats?: ExportFormat[];
  /** 数据列信息（可选，用于自动推断） */
  columns?: string[];
  /** 图表宽高比 */
  aspect_ratio?: number;
}

/**
 * 参数调整历史记录
 */
export interface ParameterAdjustment {
  /** 时间戳 */
  timestamp: string;
  /** 参数键名 */
  parameter_key: string;
  /** 旧值 */
  old_value: string | number | boolean;
  /** 新值 */
  new_value: string | number | boolean;
}

/**
 * InteractivePlotCard 组件 Props
 */
export interface InteractivePlotCardProps {
  /** 图表数据 */
  data: InteractivePlotData;
  /** 消息 ID */
  messageId?: string;
  /** 项目 ID */
  projectId?: string;
  /** 重绘回调 */
  onRedraw?: (params: Record<string, unknown>) => void;
}

/**
 * PlotCanvas 组件 Props
 */
export interface PlotCanvasProps {
  /** 图表类型 */
  plotType: PlotType;
  /** ECharts 配置 */
  config: Record<string, unknown>;
  /** 图表标题 */
  title: string;
  /** 数据源路径 */
  dataSource: string;
  /** 当前参数值 */
  parameters: Record<string, unknown>;
  /** 图表实例引用回调 */
  onChartReady?: (instance: unknown) => void;
  /** 宽高比 */
  aspectRatio?: number;
}

/**
 * ParameterConsole 组件 Props
 */
export interface ParameterConsoleProps {
  /** 参数定义 */
  parameters: Record<string, ParameterDefinition>;
  /** 当前值 */
  values: Record<string, unknown>;
  /** 值变更回调 */
  onChange: (key: string, value: unknown) => void;
  /** 应用按钮回调 */
  onApply: () => void;
  /** 是否正在加载 */
  isLoading?: boolean;
  /** 参数调整历史 */
  adjustmentHistory: ParameterAdjustment[];
}

/**
 * ExportPanel 组件 Props
 */
export interface ExportPanelProps {
  /** 支持的导出格式 */
  formats: ExportFormat[];
  /** 图表标题（用于文件名） */
  title: string;
  /** 数据源路径 */
  dataSource: string;
  /** ECharts 实例 */
  chartInstance: unknown;
  /** 当前参数值（用于 TSV 导出） */
  parameters: Record<string, unknown>;
  /** 项目 ID */
  projectId?: string;
}

/**
 * 图表数据响应结构
 */
export interface PlotDataResponse {
  status: 'success' | 'error';
  data?: Record<string, unknown>[];
  columns?: string[];
  error?: string;
}

/**
 * 重绘请求结构
 */
export interface RedrawRequest {
  plot_type: PlotType;
  data_source: string;
  parameters: Record<string, unknown>;
  project_id?: string;
}

/**
 * 重绘响应结构
 */
export interface RedrawResponse {
  status: 'success' | 'error';
  config?: Record<string, unknown>;
  data?: Record<string, unknown>[];
  error?: string;
}