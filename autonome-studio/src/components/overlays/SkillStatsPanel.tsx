"use client";

import React, { useState, useEffect } from 'react';
import { skillForgeApi, SkillAsset } from '@/lib/api';
import {
  BarChart3, TrendingUp, TrendingDown, Clock, Star, X, Loader2,
  CheckCircle, XCircle, Minus
} from 'lucide-react';
import { motion } from 'framer-motion';

interface Stats {
  total_executions: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  avg_execution_time: number;
  rating: {
    average: number;
    count: number;
  };
  trend: Array<{ date: string; count: number }>;
}

interface ExecutionHistory {
  id: number;
  user_id: number;
  project_id: string;
  status: string;
  execution_time: number | null;
  result_summary: string | null;
  created_at: string;
}

interface SkillStatsPanelProps {
  skill: SkillAsset;
  onClose: () => void;
}

export function SkillStatsPanel({ skill, onClose }: SkillStatsPanelProps) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [history, setHistory] = useState<ExecutionHistory[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // 加载统计数据
  useEffect(() => {
    loadData();
  }, [skill.skill_id]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [statsRes, historyRes] = await Promise.all([
        skillForgeApi.getStats(skill.skill_id),
        skillForgeApi.getExecutionHistory(skill.skill_id, 10)
      ]);

      if (statsRes.status === 'success') {
        setStats(statsRes.data);
      }
      if (historyRes.status === 'success') {
        setHistory(historyRes.data || []);
      }
    } catch (e) {
      console.error('Failed to load stats:', e);
    } finally {
      setIsLoading(false);
    }
  };

  // 格式化时间
  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${Math.round(seconds)}秒`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`;
    return `${(seconds / 3600).toFixed(1)}小时`;
  };

  // 格式化日期
  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // 获取趋势图最大值
  const maxCount = stats?.trend ? Math.max(...stats.trend.map(t => t.count), 1) : 1;

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-neutral-800 shrink-0">
        <div className="flex items-center gap-2">
          <BarChart3 size={18} className="text-blue-500" />
          <div>
            <h2 className="font-semibold text-gray-900 dark:text-white text-sm">使用统计</h2>
            <p className="text-xs text-gray-500 dark:text-neutral-500">{skill.name}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 size={24} className="animate-spin text-gray-400" />
        </div>
      ) : stats ? (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* 核心指标 */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-white dark:bg-neutral-800/50 border border-gray-200 dark:border-neutral-700 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-gray-900 dark:text-white">
                {stats.total_executions}
              </div>
              <div className="text-xs text-gray-500 dark:text-neutral-500 mt-1">总执行次数</div>
            </div>
            <div className="bg-white dark:bg-neutral-800/50 border border-gray-200 dark:border-neutral-700 rounded-lg p-3 text-center">
              <div className={`text-2xl font-bold ${
                stats.success_rate >= 80 ? 'text-green-500' :
                stats.success_rate >= 50 ? 'text-yellow-500' : 'text-red-500'
              }`}>
                {stats.success_rate}%
              </div>
              <div className="text-xs text-gray-500 dark:text-neutral-500 mt-1">成功率</div>
            </div>
            <div className="bg-white dark:bg-neutral-800/50 border border-gray-200 dark:border-neutral-700 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-gray-900 dark:text-white">
                {formatTime(stats.avg_execution_time)}
              </div>
              <div className="text-xs text-gray-500 dark:text-neutral-500 mt-1">平均耗时</div>
            </div>
          </div>

          {/* 成功/失败统计 */}
          <div className="bg-white dark:bg-neutral-800/50 border border-gray-200 dark:border-neutral-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-700 dark:text-neutral-300">执行结果分布</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle size={14} className="text-green-500" />
                <span className="text-sm text-gray-600 dark:text-neutral-400">成功</span>
                <span className="font-medium text-gray-900 dark:text-white">{stats.success_count}</span>
              </div>
              <div className="flex items-center gap-2">
                <XCircle size={14} className="text-red-500" />
                <span className="text-sm text-gray-600 dark:text-neutral-400">失败</span>
                <span className="font-medium text-gray-900 dark:text-white">{stats.failure_count}</span>
              </div>
            </div>

            {/* 进度条 */}
            {stats.total_executions > 0 && (
              <div className="mt-3 h-2 bg-gray-200 dark:bg-neutral-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full transition-all"
                  style={{ width: `${stats.success_rate}%` }}
                />
              </div>
            )}
          </div>

          {/* 评分 */}
          {stats.rating.count > 0 && (
            <div className="bg-white dark:bg-neutral-800/50 border border-gray-200 dark:border-neutral-700 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Star size={16} className="text-yellow-500 fill-yellow-500" />
                  <span className="text-sm font-medium text-gray-700 dark:text-neutral-300">
                    用户评分
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-xl font-bold text-gray-900 dark:text-white">
                    {stats.rating.average}
                  </span>
                  <span className="text-sm text-gray-500 dark:text-neutral-500">/ 5.0</span>
                  <span className="text-xs text-gray-400 dark:text-neutral-500 ml-2">
                    ({stats.rating.count} 条评价)
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* 使用趋势 */}
          {stats.trend.length > 0 && (
            <div className="bg-white dark:bg-neutral-800/50 border border-gray-200 dark:border-neutral-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-700 dark:text-neutral-300">最近30天趋势</span>
                <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-neutral-500">
                  <TrendingUp size={12} />
                  共 {stats.trend.reduce((sum, t) => sum + t.count, 0)} 次
                </div>
              </div>

              {/* 简易柱状图 */}
              <div className="flex items-end gap-1 h-16">
                {stats.trend.slice(-14).map((item, index) => (
                  <div
                    key={item.date}
                    className="flex-1 bg-blue-400 dark:bg-blue-500 rounded-t transition-all hover:bg-blue-500 dark:hover:bg-blue-400"
                    style={{ height: `${(item.count / maxCount) * 100}%`, minHeight: item.count > 0 ? '4px' : '0' }}
                    title={`${item.date}: ${item.count} 次`}
                  />
                ))}
              </div>
              <div className="flex justify-between mt-2 text-[10px] text-gray-400 dark:text-neutral-500">
                <span>{stats.trend[0]?.date || ''}</span>
                <span>{stats.trend[stats.trend.length - 1]?.date || ''}</span>
              </div>
            </div>
          )}

          {/* 最近执行记录 */}
          {history.length > 0 && (
            <div className="bg-white dark:bg-neutral-800/50 border border-gray-200 dark:border-neutral-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-700 dark:text-neutral-300">最近执行记录</span>
              </div>

              <div className="space-y-2">
                {history.slice(0, 5).map((h) => (
                  <div
                    key={h.id}
                    className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-neutral-700 last:border-0"
                  >
                    <div className="flex items-center gap-2">
                      {h.status === 'SUCCESS' ? (
                        <CheckCircle size={12} className="text-green-500" />
                      ) : h.status === 'FAILURE' ? (
                        <XCircle size={12} className="text-red-500" />
                      ) : (
                        <Minus size={12} className="text-gray-400" />
                      )}
                      <span className="text-xs text-gray-600 dark:text-neutral-400">
                        {formatDate(h.created_at)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-neutral-500">
                      {h.execution_time && (
                        <span className="flex items-center gap-1">
                          <Clock size={10} />
                          {formatTime(h.execution_time)}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-neutral-500">
          <span>暂无统计数据</span>
        </div>
      )}
    </div>
  );
}