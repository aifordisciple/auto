/**
 * SkillExecutePanel 类型定义
 *
 * 包含技能执行面板相关的所有类型和接口
 */

/**
 * 技能参数定义
 */
export interface SkillParameter {
  type?: string;
  format?: string;
  description?: string;
  default?: unknown;
}

/**
 * 技能参数 Schema
 */
export interface SkillSchema {
  type: string;
  properties: Record<string, SkillParameter>;
  required: string[];
  /** 自定义扩展字段：保存参数顺序 */
  'x-parameter-order'?: string[];
}

/**
 * 技能定义
 */
export interface Skill {
  skill_id: string;
  name: string;
  description?: string;
  version: string;
  author: string;
  executor_type: string;
  timeout_seconds: number;
  parameters_schema: SkillSchema;
  bundle_name: string;
  category?: string;
  category_name?: string;
  subcategory?: string;
  subcategory_name?: string;
  tags?: string[];
  /** 基础分析标记，用于 Tools 按钮快速筛选 */
  is_basic_analysis?: boolean;
}

/**
 * 分类定义
 */
export interface Category {
  id: string;
  name: string;
  icon: string;
  description?: string;
  subcategories?: Category[];
}

/**
 * SkillExecutePanel 组件 Props
 */
export interface SkillExecutePanelProps {
  onDataCenterOpen?: () => void;
  selectedSkillFromMarket?: Skill | null;
  /** ✨ 预选技能 ID（用于从推荐卡片直接打开） */
  preSelectedSkillId?: string | null;
}