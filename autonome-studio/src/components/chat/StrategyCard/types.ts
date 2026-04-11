/**
 * StrategyCard 类型定义
 *
 * 包含策略卡片相关的所有类型和接口
 */

// ✨ 导入 InteractivePlotCard 类型用于可视化配置
import type { PlotType, ParameterDefinition, ExportFormat } from '../InteractivePlotCard/types';

/**
 * 任务模式类型
 */
export type TaskMode = 'normal' | 'interactive_visualization';

/**
 * 可视化配置结构（用于交互式可视化模式）
 */
export interface VisualizationConfig {
  /** 图表类型 */
  plot_type: PlotType;
  /** 图表标题 */
  title: string;
  /** 图表描述 */
  description?: string;
  /** 数据源路径（相对路径，如 results.tsv） */
  data_source: string;
  /** 参数定义列表 */
  parameters: Record<string, ParameterDefinition>;
  /** ECharts 默认配置 */
  default_config?: Record<string, unknown>;
  /** 支持的导出格式 */
  export_formats?: ExportFormat[];
  /** 图表宽高比 */
  aspect_ratio?: number;
}

/**
 * 策略卡片数据结构
 */
export interface StrategyCardData {
  /** 任务标题 */
  title: string;
  /** 任务描述 */
  description: string;
  /** AI 生成的任务概述（1-3句话） */
  task_summary?: string;
  /** 工具 ID */
  tool_id: string;
  /** 代码内容 */
  code?: string;
  /** 参数 */
  parameters?: Record<string, unknown>;
  /** 执行步骤 */
  steps?: string[];
  /** 预估时间 */
  estimated_time?: string;
  /** 风险等级 */
  risk_level?: "low" | "medium" | "high";
  /** ✨ 任务模式（交互式可视化时为 interactive_visualization） */
  task_mode?: TaskMode;
  /** ✨ 可视化配置（交互式可视化模式时必须提供） */
  visualization_config?: VisualizationConfig;
  /** ✨ V2: AI 推断的参数列表（用于视觉标记） */
  ai_inferred_params?: string[];
}

/**
 * StrategyCard 组件 Props
 */
export interface StrategyCardProps {
  /** 策略卡片数据 */
  data: StrategyCardData;
  /** 消息 ID */
  messageId?: string;
  /** 消息内容 */
  messageContent?: string;
  /** 执行回调 */
  onExecute?: (taskId: string) => void;
  /** 取消回调 */
  onCancel?: () => void;
}

/**
 * 任务状态枚举
 */
export type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'timeout' | 'cancelled';

/**
 * WebSocket 消息类型
 */
export interface TaskWebSocketMessage {
  type: 'status' | 'progress' | 'result' | 'error' | 'log' | 'code_update';
  task_id: string;
  status?: TaskStatus;
  progress?: number;
  result?: unknown;
  error?: string;
  log?: string;
  code?: string;
}