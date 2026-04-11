/**
 * ActionMenu 数据类型定义
 */

export interface ActionMenuOption {
  skill_id: string;
  name: string;
  match_score: number;
  match_reason?: string;
}

export interface ActionMenuData {
  title?: string;
  message?: string;
  options: ActionMenuOption[];
}
