"use client";

/**
 * 算力账单与技能雷达面板
 *
 * 将计费与业务价值绑定，帮助用户理解：
 * - 钱花在了哪里（消耗漏斗）
 * - 常用什么技能（技能雷达）
 * - 推荐的进阶技能
 *
 * 使用 ECharts 进行图表渲染
 */

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import * as echarts from "echarts";
import {
  Sparkles,
  ChevronRight,
  CheckCircle,
  DollarSign,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================

interface WalletOverview {
  current_balance: number;
  frozen_amount: number;
  total_consumed: number;
  trend_last_7_days: number;
}

interface FunnelItem {
  task_type: string;
  task_type_display: string;
  count: number;
  total_cost: number;
  percentage: number;
}

interface SkillRadarItem {
  skill_id: string;
  skill_name: string;
  usage_count: number;
  success_rate: number;
  avg_execution_time: number;
  total_cost: number;
}

interface RecommendedSkill {
  skill_id: string;
  skill_name: string;
  reason: string;
  category: string;
}

interface BillingAnalyticsData {
  wallet_overview: WalletOverview;
  funnel_data: FunnelItem[];
  skill_radar: SkillRadarItem[];
  recommended_skills: RecommendedSkill[];
}

interface BillingAnalyticsPanelProps {
  timeRange: "7d" | "30d" | "all";
}

// ==========================================
// 颜色配置
// ==========================================

const TASK_TYPE_COLORS: Record<string, string> = {
  chat: "#3b82f6", // blue
  sandbox_python: "#06b6d4", // cyan
  sandbox_r: "#0891b2", // darker cyan
  skill_python: "#22c55e", // green
  skill_r: "#16a34a", // darker green
  skill_nextflow: "#a855f7", // purple
  blueprint: "#8b5cf6", // violet
  terminal: "#6366f1", // indigo
  super_executor: "#ec4899", // pink
};

const CHART_COLORS = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#8b5cf6",
  "#06b6d4",
  "#ec4899",
  "#6366f1",
];

// ==========================================
// 组件
// ==========================================

export function BillingAnalyticsPanel({ timeRange }: BillingAnalyticsPanelProps) {
  const [data, setData] = useState<BillingAnalyticsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"funnel" | "radar">("funnel");

  // ECharts refs
  const pieChartRef = useRef<HTMLDivElement>(null);
  const radarChartRef = useRef<HTMLDivElement>(null);
  const pieChartInstance = useRef<echarts.ECharts | null>(null);
  const radarChartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    loadBillingData();
  }, [timeRange]);

  // 组件卸载时销毁 ECharts 实例
  useEffect(() => {
    return () => {
      pieChartInstance.current?.dispose();
      radarChartInstance.current?.dispose();
    };
  }, []);

  // 初始化和更新饼图
  useEffect(() => {
    if (!data || !pieChartRef.current || activeTab !== "funnel") return;

    // 销毁旧实例，避免重复初始化警告
    if (pieChartInstance.current) {
      pieChartInstance.current.dispose();
      pieChartInstance.current = null;
    }

    pieChartInstance.current = echarts.init(pieChartRef.current, "dark", {
      renderer: "svg",
    });

    const pieData = data.funnel_data.map((item, index) => ({
      name: item.task_type_display,
      value: item.total_cost,
      percentage: item.percentage,
      count: item.count,
      itemStyle: {
        color: TASK_TYPE_COLORS[item.task_type] || CHART_COLORS[index % CHART_COLORS.length],
      },
    }));

    const option: echarts.EChartsOption = {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        formatter: (params: any) => {
          return `${params.name}<br/>${params.value.toFixed(1)} CU (${params.data.percentage}%)`;
        },
      },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          center: ["50%", "50%"],
          avoidLabelOverlap: false,
          label: {
            show: false,
          },
          emphasis: {
            label: {
              show: true,
              fontSize: 12,
              fontWeight: "bold",
              color: "#fff",
            },
          },
          labelLine: {
            show: false,
          },
          data: pieData,
        },
      ],
    };

    pieChartInstance.current.setOption(option);

    // 响应式
    const handleResize = () => pieChartInstance.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [data, activeTab]);

  // 初始化和更新雷达图
  useEffect(() => {
    if (!data || !radarChartRef.current || activeTab !== "radar") return;

    // 销毁旧实例，避免重复初始化警告
    if (radarChartInstance.current) {
      radarChartInstance.current.dispose();
      radarChartInstance.current = null;
    }

    radarChartInstance.current = echarts.init(radarChartRef.current, "dark", {
      renderer: "svg",
    });

    // 准备雷达图数据
    const topSkills = data.skill_radar.slice(0, 6);
    const indicators = topSkills.map((skill) => ({
      name: skill.skill_name.length > 6 ? skill.skill_name.slice(0, 6) + "..." : skill.skill_name,
      max: 100,
    }));

    // 归一化数据
    const maxUsage = Math.max(...topSkills.map((s) => s.usage_count), 1);
    const usageData = topSkills.map((skill) => (skill.usage_count / maxUsage) * 100);
    const successData = topSkills.map((skill) => skill.success_rate);

    const option: echarts.EChartsOption = {
      backgroundColor: "transparent",
      radar: {
        indicator: indicators,
        axisName: {
          color: "#9ca3af",
          fontSize: 11,
        },
        splitLine: {
          lineStyle: {
            color: "#374151",
          },
        },
        splitArea: {
          show: false,
        },
        axisLine: {
          lineStyle: {
            color: "#374151",
          },
        },
      },
      legend: {
        bottom: 0,
        textStyle: {
          color: "#9ca3af",
          fontSize: 11,
        },
      },
      series: [
        {
          type: "radar",
          data: [
            {
              value: usageData,
              name: "使用频率",
              lineStyle: {
                color: "#22c55e",
              },
              areaStyle: {
                color: "rgba(34, 197, 94, 0.2)",
              },
              itemStyle: {
                color: "#22c55e",
              },
            },
            {
              value: successData,
              name: "成功率",
              lineStyle: {
                color: "#3b82f6",
              },
              areaStyle: {
                color: "rgba(59, 130, 246, 0.2)",
              },
              itemStyle: {
                color: "#3b82f6",
              },
            },
          ],
        },
      ],
    };

    radarChartInstance.current.setOption(option);

    const handleResize = () => radarChartInstance.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [data, activeTab]);

  const loadBillingData = async () => {
    try {
      setIsLoading(true);
      const result = await fetchAPI(`/dashboard/billing-analytics?time_range=${timeRange}`);
      setData(result);
    } catch (error) {
      console.error("加载账单分析数据失败:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // 格式化金额
  const formatCost = (value: number) => {
    if (value >= 1000) {
      return `${(value / 1000).toFixed(1)}K`;
    }
    return value.toFixed(1);
  };

  return (
    <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-6">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-emerald-400" />
          算力账单与技能雷达
        </h2>

        {/* Tab 切换 */}
        <div className="flex items-center gap-1 bg-neutral-800 rounded-lg p-1">
          <button
            onClick={() => setActiveTab("funnel")}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${
              activeTab === "funnel"
                ? "bg-emerald-500/20 text-emerald-300"
                : "text-neutral-400 hover:text-white"
            }`}
          >
            消耗漏斗
          </button>
          <button
            onClick={() => setActiveTab("radar")}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${
              activeTab === "radar"
                ? "bg-emerald-500/20 text-emerald-300"
                : "text-neutral-400 hover:text-white"
            }`}
          >
            技能雷达
          </button>
        </div>
      </div>

      {isLoading ? (
        // 加载状态
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 左侧：图表区域 */}
          <div className="min-h-[280px]" ref={activeTab === "funnel" ? pieChartRef : radarChartRef} />

          {/* 右侧：详情列表 */}
          <div>
            {activeTab === "funnel" ? (
              // 消耗明细列表
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-neutral-500 mb-2 px-2">
                  <span>任务类型</span>
                  <span>消费金额</span>
                </div>
                {data?.funnel_data.slice(0, 6).map((item, index) => (
                  <motion.div
                    key={item.task_type}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className="flex items-center justify-between p-2 rounded-lg hover:bg-neutral-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{
                          backgroundColor:
                            TASK_TYPE_COLORS[item.task_type] || CHART_COLORS[index],
                        }}
                      />
                      <span className="text-sm text-neutral-300">
                        {item.task_type_display}
                      </span>
                      <span className="text-xs text-neutral-500">({item.count}次)</span>
                    </div>
                    <span className="text-sm font-medium text-emerald-400">
                      {formatCost(item.total_cost)} CU
                    </span>
                  </motion.div>
                ))}
              </div>
            ) : (
              // 技能使用列表
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-neutral-500 mb-2 px-2">
                  <span>技能名称</span>
                  <span>使用次数 / 成功率</span>
                </div>
                {data?.skill_radar.slice(0, 6).map((skill, index) => (
                  <motion.div
                    key={`skill-${skill.skill_id}-${index}`}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className="flex items-center justify-between p-2 rounded-lg hover:bg-neutral-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <CheckCircle
                        className={`w-4 h-4 ${
                          skill.success_rate >= 80
                            ? "text-emerald-400"
                            : skill.success_rate >= 50
                            ? "text-amber-400"
                            : "text-red-400"
                        }`}
                      />
                      <span className="text-sm text-neutral-300 truncate max-w-[120px]">
                        {skill.skill_name}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="text-neutral-400">{skill.usage_count}次</span>
                      <span
                        className={`font-medium ${
                          skill.success_rate >= 80
                            ? "text-emerald-400"
                            : skill.success_rate >= 50
                            ? "text-amber-400"
                            : "text-red-400"
                        }`}
                      >
                        {skill.success_rate.toFixed(0)}%
                      </span>
                    </div>
                  </motion.div>
                ))}
              </div>
            )}

            {/* 推荐技能 */}
            {data?.recommended_skills && data.recommended_skills.length > 0 && (
              <div className="mt-4 pt-4 border-t border-neutral-800">
                <div className="flex items-center gap-2 mb-3">
                  <Sparkles className="w-4 h-4 text-purple-400" />
                  <span className="text-sm font-medium text-neutral-300">推荐技能</span>
                </div>
                <div className="space-y-2">
                  {data.recommended_skills.slice(0, 3).map((skill, index) => (
                    <div
                      key={`rec-${skill.skill_id}-${index}`}
                      className="flex items-center justify-between p-2 bg-purple-500/5 rounded-lg border border-purple-500/10 hover:border-purple-500/20 transition-colors cursor-pointer"
                    >
                      <div>
                        <span className="text-sm text-purple-300">{skill.skill_name}</span>
                        <p className="text-xs text-neutral-500 mt-0.5">{skill.reason}</p>
                      </div>
                      <ChevronRight className="w-4 h-4 text-purple-400" />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 底部统计 */}
      {!isLoading && data && (
        <div className="mt-4 pt-4 border-t border-neutral-800 flex items-center justify-between text-xs text-neutral-500">
          <span>
            总消费:{" "}
            <span className="text-emerald-400 font-medium">
              {formatCost(data.funnel_data.reduce((sum, item) => sum + item.total_cost, 0))} CU
            </span>
          </span>
          <span>
            技能调用:{" "}
            <span className="text-blue-400 font-medium">
              {data.skill_radar.reduce((sum, skill) => sum + skill.usage_count, 0)} 次
            </span>
          </span>
        </div>
      )}
    </div>
  );
}