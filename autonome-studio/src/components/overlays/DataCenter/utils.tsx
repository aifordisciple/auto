/**
 * DataCenter 工具函数
 *
 * 包含文件图标、大小格式化、时间格式化等辅助函数
 */
import React from 'react';
import { Table2, FileText, Image as ImageIcon } from "lucide-react";

/**
 * 根据文件名分配图标
 */
export const getFileIcon = (filename: string): React.ReactNode => {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tsv') || lower.endsWith('.csv') || lower.endsWith('.txt') || lower.endsWith('.log')) {
    return <Table2 size={16} className="text-blue-400 shrink-0" />;
  }
  if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.pdf') || lower.endsWith('.svg')) {
    return <ImageIcon size={16} className="text-pink-400 shrink-0" />;
  }
  if (lower.endsWith('.html') || lower.endsWith('.htm')) {
    return <FileText size={16} className="text-orange-400 shrink-0" />;
  }
  return <FileText size={16} className="text-neutral-400 shrink-0" />;
};

/**
 * 智能格式化文件大小
 */
export const formatBytes = (bytes?: number): string => {
  if (bytes === undefined || bytes === null) return '';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

/**
 * 格式化时间
 *
 * 智能显示相对时间或绝对时间
 */
export const formatDateTime = (timestamp?: string | number): string => {
  if (!timestamp) return '';
  try {
    // 后端返回的是秒级时间戳，需要转换为毫秒
    const ts = typeof timestamp === 'number' ? timestamp * 1000 : parseInt(timestamp) * 1000;
    const date = new Date(ts);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    // 小于1分钟
    if (diff < 60000) return '刚刚';
    // 小于1小时
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    // 小于24小时
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
    // 小于7天
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`;

    // 其他显示日期
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    // 如果是今年，不显示年份
    if (date.getFullYear() === now.getFullYear()) {
      return `${month}-${day} ${hours}:${minutes}`;
    }
    return `${date.getFullYear()}-${month}-${day}`;
  } catch {
    return '';
  }
};