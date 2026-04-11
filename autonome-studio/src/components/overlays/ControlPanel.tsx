"use client";

/**
 * 控制面板 - 科研项目指挥中心
 *
 * 从"系统监控大屏"重构为"科研视角"控制面板
 * 核心解决三个问题：
 * 1. 我的样本分析到哪一步了？
 * 2. 我花掉的算力/费用产生了什么价值？
 * 3. 我接下来需要确认什么操作？
 *
 * 四个核心模块：
 * - 工作流大厅：蓝图进度追踪、ETA 预估
 * - 账单雷达：算力消耗漏斗、技能雷达
 * - 待办中心：智能预警、待办事项
 * - 资产速递：成果画廊、交付物下载
 */

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  X,
  Target,
  Wallet,
  TrendingUp,
  TrendingDown,
  Zap,
} from "lucide-react";
import { BASE_URL, fetchAPI } from "@/lib/api";
import { useUIStore } from "@/store/useUIStore";

// 导入四个核心模块组件
import { ActiveWorkflowsPanel } from "@/app/dashboard/components/ActiveWorkflowsPanel";
import { BillingAnalyticsPanel } from "@/app/dashboard/components/BillingAnalyticsPanel";
import { ActionItemsPanel } from "@/app/dashboard/components/ActionItemsPanel";
import { RecentAssetsPanel } from "@/app/dashboard/components/RecentAssetsPanel";

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
// 组件
// ==========================================

export function ControlPanel() {
  const { isControlPanelOpen, closeAllOverlays } = useUIStore();
  const [walletOverview, setWalletOverview] = useState<WalletOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<"7d" | "30d" | "all">("30d");

  // 加载钱包概览
  useEffect(() => {
    if (!isControlPanelOpen) return;
    loadWalletOverview();
  }, [isControlPanelOpen]);

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

  // 如果状态是 false，直接不渲染
  if (!isControlPanelOpen) return null;

  return (
    // 悬浮层，从右侧滑出
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* 模糊遮罩，点击关闭 */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity"
        onClick={closeAllOverlays}
      />

      {/* 侧滑面板实体 - 更宽以容纳四宫格 */}
      <div className="relative w-[95vw] md:w-[1200px] max-w-full h-full bg-[#0a0a0a] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">

        {/* Header 区域 */}
        <div className="h-16 shrink-0 border-b border-neutral-800 px-4 md:px-6 flex items-center justify-between bg-neutral-900/40">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/20 border border-cyan-500/30 rounded-lg text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.15)]">
              <Target size={18} strokeWidth={2.5} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-neutral-200 tracking-wide">
                科研项目指挥中心
              </h2>
              <p className="text-[10px] text-neutral-500 font-mono mt-0.5">
                从科研视角追踪项目进度、算力消耗和研究成果
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* 时间范围选择器 */}
            <div className="hidden md:flex items-center gap-1 bg-neutral-800 rounded-lg p-1">
              {(["7d", "30d", "all"] as const).map((range) => (
                <button
                  key={range}
                  onClick={() => setTimeRange(range)}
                  className={`px-2 py-1 rounded-md text-xs transition-colors ${
                    timeRange === range
                      ? "bg-cyan-500/20 text-cyan-300"
                      : "text-neutral-400 hover:text-white"
                  }`}
                >
                  {range === "7d" ? "近7天" : range === "30d" ? "近30天" : "全部"}
                </button>
              ))}
            </div>

            <button
              onClick={closeAllOverlays}
              className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* 内容区域 - 可滚动 */}
        <div className="flex-1 overflow-y-auto p-4 md:p-6">
          {/* 钱包概览卡片 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6"
          >
            {/* 可用余额 */}
            <div className="bg-neutral-900 rounded-xl p-3 border border-neutral-800">
              <div className="flex items-center justify-between">
                <div className="p-1.5 bg-emerald-500/10 rounded-lg">
                  <Wallet className="w-4 h-4 text-emerald-400" />
                </div>
                <span className="text-[10px] text-neutral-500">可用余额</span>
              </div>
              <div className="mt-2">
                {isLoading ? (
                  <div className="h-6 w-16 bg-neutral-800 rounded animate-pulse" />
                ) : (
                  <span className="text-xl font-bold text-emerald-400">
                    {formatCredits(walletOverview?.current_balance || 0)}
                  </span>
                )}
                <span className="text-neutral-500 text-xs ml-1">CU</span>
              </div>
            </div>

            {/* 冻结金额 */}
            <div className="bg-neutral-900 rounded-xl p-3 border border-neutral-800">
              <div className="flex items-center justify-between">
                <div className="p-1.5 bg-amber-500/10 rounded-lg">
                  <Zap className="w-4 h-4 text-amber-400" />
                </div>
                <span className="text-[10px] text-neutral-500">冻结中</span>
              </div>
              <div className="mt-2">
                {isLoading ? (
                  <div className="h-6 w-16 bg-neutral-800 rounded animate-pulse" />
                ) : (
                  <span className="text-xl font-bold text-amber-400">
                    {formatCredits(walletOverview?.frozen_amount || 0)}
                  </span>
                )}
                <span className="text-neutral-500 text-xs ml-1">CU</span>
              </div>
            </div>

            {/* 累计消费 */}
            <div className="bg-neutral-900 rounded-xl p-3 border border-neutral-800">
              <div className="flex items-center justify-between">
                <div className="p-1.5 bg-blue-500/10 rounded-lg">
                  <TrendingUp className="w-4 h-4 text-blue-400" />
                </div>
                <span className="text-[10px] text-neutral-500">累计消费</span>
              </div>
              <div className="mt-2">
                {isLoading ? (
                  <div className="h-6 w-16 bg-neutral-800 rounded animate-pulse" />
                ) : (
                  <span className="text-xl font-bold text-blue-400">
                    {formatCredits(walletOverview?.total_consumed || 0)}
                  </span>
                )}
                <span className="text-neutral-500 text-xs ml-1">CU</span>
              </div>
            </div>

            {/* 近7天趋势 */}
            <div className="bg-neutral-900 rounded-xl p-3 border border-neutral-800">
              <div className="flex items-center justify-between">
                <div className="p-1.5 bg-purple-500/10 rounded-lg">
                  {walletOverview && walletOverview.trend_last_7_days > 0 ? (
                    <TrendingUp className="w-4 h-4 text-purple-400" />
                  ) : (
                    <TrendingDown className="w-4 h-4 text-purple-400" />
                  )}
                </div>
                <span className="text-[10px] text-neutral-500">近7天</span>
              </div>
              <div className="mt-2">
                {isLoading ? (
                  <div className="h-6 w-16 bg-neutral-800 rounded animate-pulse" />
                ) : (
                  <span className="text-xl font-bold text-purple-400">
                    {formatCredits(walletOverview?.trend_last_7_days || 0)}
                  </span>
                )}
                <span className="text-neutral-500 text-xs ml-1">CU</span>
              </div>
            </div>
          </motion.div>

          {/* 主内容区域 - 四宫格布局 */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* 模块1：工作流大厅 */}
            <ActiveWorkflowsPanel />

            {/* 模块2：账单雷达 */}
            <BillingAnalyticsPanel timeRange={timeRange} />

            {/* 模块3：待办中心 */}
            <ActionItemsPanel />

            {/* 模块4：资产速递 */}
            <RecentAssetsPanel />
          </div>
        </div>
      </div>
    </div>
  );
}