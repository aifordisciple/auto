"use client";

/**
 * Dashboard 控制面板 - 科研项目指挥中心
 *
 * 从"系统监控大屏"重构为"科研视角"，核心解决三个问题：
 * 1. 我的样本分析到哪一步了？
 * 2. 我花掉的算力/费用产生了什么价值？
 * 3. 我接下来需要确认什么操作？
 *
 * 已实现模块：
 * - 算力账单与技能雷达 ✅
 * - 动态科研工作流大厅 ✅
 */

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  Zap,
  Target,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { BillingAnalyticsPanel } from "./components/BillingAnalyticsPanel";
import { ActiveWorkflowsPanel } from "./components/ActiveWorkflowsPanel";
import { ActionItemsPanel } from "./components/ActionItemsPanel";
import { RecentAssetsPanel } from "./components/RecentAssetsPanel";

// ==========================================
// 类型定义
// ==========================================

interface WalletOverview {
  current_balance: number;
  frozen_amount: number;
  total_consumed: number;
  trend_last_7_days: number;
  status: string;
  low_balance_threshold: number;
}

// ==========================================
// Dashboard 主页面
// ==========================================

export default function DashboardPage() {
  const [walletOverview, setWalletOverview] = useState<WalletOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<"7d" | "30d" | "all">("30d");

  // 加载钱包概览
  useEffect(() => {
    loadWalletOverview();
  }, []);

  const loadWalletOverview = async () => {
    try {
      setIsLoading(true);
      const data = await fetchAPI("/dashboard/wallet-overview");
      setWalletOverview(data);
    } catch (error) {
      console.error("加载钱包概览失败:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // 格式化金额
  const formatCredits = (value: number) => {
    if (value >= 1000) {
      return `${(value / 1000).toFixed(1)}K`;
    }
    return value.toFixed(1);
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-white p-6">
      {/* 页面标题 */}
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Target className="w-7 h-7 text-cyan-400" />
              科研项目指挥中心
            </h1>
            <p className="text-neutral-400 mt-1">
              从科研视角追踪项目进度、算力消耗和研究成果
            </p>
          </div>

          {/* 时间范围选择器 */}
          <div className="flex items-center gap-2 bg-neutral-900 rounded-lg p-1">
            {(["7d", "30d", "all"] as const).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                  timeRange === range
                    ? "bg-cyan-500/20 text-cyan-300"
                    : "text-neutral-400 hover:text-white"
                }`}
              >
                {range === "7d" ? "近7天" : range === "30d" ? "近30天" : "全部"}
              </button>
            ))}
          </div>
        </div>

        {/* 钱包概览卡片 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8"
        >
          {/* 可用余额 */}
          <div className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
            <div className="flex items-center justify-between">
              <div className="p-2 bg-emerald-500/10 rounded-lg">
                <Wallet className="w-5 h-5 text-emerald-400" />
              </div>
              <span className="text-xs text-neutral-500">可用余额</span>
            </div>
            <div className="mt-3">
              {isLoading ? (
                <div className="h-8 w-20 bg-neutral-800 rounded animate-pulse" />
              ) : (
                <span className="text-2xl font-bold text-emerald-400">
                  {formatCredits(walletOverview?.current_balance || 0)}
                </span>
              )}
              <span className="text-neutral-500 text-sm ml-1">CU</span>
            </div>
          </div>

          {/* 冻结金额 */}
          <div className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
            <div className="flex items-center justify-between">
              <div className="p-2 bg-amber-500/10 rounded-lg">
                <Zap className="w-5 h-5 text-amber-400" />
              </div>
              <span className="text-xs text-neutral-500">冻结中</span>
            </div>
            <div className="mt-3">
              {isLoading ? (
                <div className="h-8 w-20 bg-neutral-800 rounded animate-pulse" />
              ) : (
                <span className="text-2xl font-bold text-amber-400">
                  {formatCredits(walletOverview?.frozen_amount || 0)}
                </span>
              )}
              <span className="text-neutral-500 text-sm ml-1">CU</span>
            </div>
          </div>

          {/* 累计消费 */}
          <div className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
            <div className="flex items-center justify-between">
              <div className="p-2 bg-blue-500/10 rounded-lg">
                <TrendingUp className="w-5 h-5 text-blue-400" />
              </div>
              <span className="text-xs text-neutral-500">累计消费</span>
            </div>
            <div className="mt-3">
              {isLoading ? (
                <div className="h-8 w-20 bg-neutral-800 rounded animate-pulse" />
              ) : (
                <span className="text-2xl font-bold text-blue-400">
                  {formatCredits(walletOverview?.total_consumed || 0)}
                </span>
              )}
              <span className="text-neutral-500 text-sm ml-1">CU</span>
            </div>
          </div>

          {/* 近7天趋势 */}
          <div className="bg-neutral-900 rounded-xl p-4 border border-neutral-800">
            <div className="flex items-center justify-between">
              <div className="p-2 bg-purple-500/10 rounded-lg">
                {walletOverview && walletOverview.trend_last_7_days > 0 ? (
                  <TrendingUp className="w-5 h-5 text-purple-400" />
                ) : (
                  <TrendingDown className="w-5 h-5 text-purple-400" />
                )}
              </div>
              <span className="text-xs text-neutral-500">近7天消费</span>
            </div>
            <div className="mt-3">
              {isLoading ? (
                <div className="h-8 w-20 bg-neutral-800 rounded animate-pulse" />
              ) : (
                <span className="text-2xl font-bold text-purple-400">
                  {formatCredits(walletOverview?.trend_last_7_days || 0)}
                </span>
              )}
              <span className="text-neutral-500 text-sm ml-1">CU</span>
            </div>
          </div>
        </motion.div>

        {/* 主内容区域 - 四宫格布局 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 模块1：动态科研工作流大厅 */}
          <ActiveWorkflowsPanel />

          {/* 模块2：算力账单与技能雷达 */}
          <BillingAnalyticsPanel timeRange={timeRange} />

          {/* 模块3：智能预警与待办中心 */}
          <ActionItemsPanel />

          {/* 模块4：科研资产与洞察速递 */}
          <RecentAssetsPanel />
        </div>
      </div>
    </div>
  );
}