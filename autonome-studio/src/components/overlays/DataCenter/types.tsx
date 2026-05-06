/**
 * DataCenter 类型定义
 */
import React from 'react';
import { Folder, Dna, Database, History } from "lucide-react";

/**
 * Tab 类型定义
 */
export type TabType = 'files' | 'genomes' | 'databases' | 'history';

/**
 * Tab 配置项接口
 */
export interface TabConfig {
  id: TabType;
  label: string;
  icon: React.ReactNode;
  color: string;
}

/**
 * Tab 配置列表
 */
export const TABS: TabConfig[] = [
  { id: 'files', label: '项目数据', icon: <Folder size={14} />, color: 'bg-data text-data-foreground' },
  { id: 'genomes', label: '参考基因组', icon: <Dna size={14} />, color: 'bg-success text-success-foreground' },
  { id: 'databases', label: '分析数据库', icon: <Database size={14} />, color: 'bg-action text-action-foreground' },
  { id: 'history', label: '即席分析', icon: <History size={14} />, color: 'bg-deep-think text-deep-think-foreground' },
];