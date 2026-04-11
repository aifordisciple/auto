"use client";

/**
 * 智能预警与待办中心面板
 *
 * 将 AI 的主动性体现在控制面板上，用户一登录就知道需要做什么
 *
 * 待办类型：
 * - strategy_confirmation: Strategy Card 等待确认
 * - quality_alert: 数据质控异常
 * - resource_warning: 资源预警
 * - system_notice: 系统通知
 */

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Sparkles,
  AlertTriangle,
  Wallet,
  Bell,
  ChevronRight,
  CheckCircle,
  XCircle,
  Eye,
  RefreshCw,
  X,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================

interface ActionItemAction {
  label: string;
  action: string;
  primary: boolean;
}

interface ActionItem {
  id: string;
  type: "strategy_confirmation" | "quality_alert" | "resource_warning" | "system_notice";
  priority: "high" | "medium" | "low";
  title: string;
  description: string;
  related_task_id?: string;
  related_skill_id?: string;
  created_at: string;
  expires_at?: string;
  actions: ActionItemAction[];
}

interface ActionItemsData {
  items: ActionItem[];
  total_count: number;
  high_priority_count: number;
}

// ==========================================
// 配置
// ==========================================

const TYPE_CONFIG = {
  strategy_confirmation: {
    icon: CheckCircle,
    color: "text-blue-400",
    bgColor: "bg-blue-500/10",
    borderColor: "border-blue-500/20",
    label: "策略确认",
  },
  quality_alert: {
    icon: AlertTriangle,
    color: "text-amber-400",
    bgColor: "bg-amber-500/10",
    borderColor: "border-amber-500/20",
    label: "质控异常",
  },
  resource_warning: {
    icon: Wallet,
    color: "text-red-400",
    bgColor: "bg-red-500/10",
    borderColor: "border-red-500/20",
    label: "资源预警",
  },
  system_notice: {
    icon: Bell,
    color: "text-cyan-400",
    bgColor: "bg-cyan-500/10",
    borderColor: "border-cyan-500/20",
    label: "系统通知",
  },
};

const PRIORITY_CONFIG = {
  high: {
    badge: "bg-amber-500/20 text-amber-300",
    label: "高优先",
  },
  medium: {
    badge: "bg-cyan-500/20 text-cyan-300",
    label: "中等",
  },
  low: {
    badge: "bg-neutral-500/20 text-neutral-400",
    label: "低优先",
  },
};

// ==========================================
// 组件
// ==========================================

export function ActionItemsPanel() {
  const [data, setData] = useState<ActionItemsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedItem, setExpandedItem] = useState<string | null>(null);

  useEffect(() => {
    loadActionItems();
    // 每 30 秒刷新一次
    const interval = setInterval(loadActionItems, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadActionItems = async () => {
    try {
      const result = await fetchAPI("/dashboard/action-items?limit=10");
      setData(result);
    } catch (error) {
      console.error("加载待办事项失败:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAction = async (item: ActionItem, action: ActionItemAction) => {
    try {
      const result = await fetchAPI(
        `/dashboard/action-items/${item.id}/action?action=${action.action}`,
        { method: "POST" }
      );

      if (result.success) {
        // 刷新列表
        loadActionItems();

        // 如果有重定向，提示用户
        if (result.redirect) {
          window.open(result.redirect, "_blank");
        }
      }
    } catch (error) {
      console.error("处理待办事项失败:", error);
    }
  };

  // 格式化时间
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return "刚刚";
    if (diffMins < 60) return `${diffMins} 分钟前`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} 小时前`;
    return `${Math.floor(diffHours / 24)} 天前`;
  };

  return (
    <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-6">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-amber-400" />
          智能预警与待办中心
        </h2>
        {data && data.high_priority_count > 0 && (
          <span className="text-xs text-amber-400 bg-amber-500/10 px-2 py-1 rounded flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            {data.high_priority_count} 个高优先
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-neutral-500">
          <CheckCircle className="w-12 h-12 mb-4 opacity-20" />
          <p className="text-sm">暂无待办事项</p>
          <p className="text-xs mt-1">一切正常</p>
        </div>
      ) : (
        <div className="space-y-3">
          <AnimatePresence>
            {data.items.map((item, index) => {
              const typeConfig = TYPE_CONFIG[item.type];
              const priorityConfig = PRIORITY_CONFIG[item.priority];
              const IconComponent = typeConfig.icon;

              return (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ delay: index * 0.05 }}
                  className={`
                    rounded-lg border p-3 transition-all cursor-pointer
                    ${typeConfig.bgColor} ${typeConfig.borderColor}
                    hover:border-opacity-40
                  `}
                  onClick={() => setExpandedItem(expandedItem === item.id ? null : item.id)}
                >
                  {/* 标题行 */}
                  <div className="flex items-start gap-3">
                    <div className={`p-2 rounded-lg ${typeConfig.bgColor}`}>
                      <IconComponent className={`w-4 h-4 ${typeConfig.color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-medium text-white truncate">
                          {item.title}
                        </h3>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${priorityConfig.badge}`}>
                          {priorityConfig.label}
                        </span>
                      </div>
                      <p className="text-xs text-neutral-400 line-clamp-2">
                        {item.description}
                      </p>
                      <span className="text-xs text-neutral-500 mt-1 block">
                        {formatTime(item.created_at)}
                      </span>
                    </div>
                    <ChevronRight
                      className={`w-4 h-4 text-neutral-500 transition-transform ${
                        expandedItem === item.id ? "rotate-90" : ""
                      }`}
                    />
                  </div>

                  {/* 展开的操作按钮 */}
                  {expandedItem === item.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      className="mt-3 pt-3 border-t border-neutral-700/50"
                    >
                      <div className="flex items-center gap-2 flex-wrap">
                        {item.actions.map((action) => (
                          <button
                            key={action.action}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleAction(item, action);
                            }}
                            className={`
                              px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
                              ${
                                action.primary
                                  ? `bg-white/10 text-white hover:bg-white/20`
                                  : `bg-neutral-700/50 text-neutral-300 hover:bg-neutral-700`
                              }
                            `}
                          >
                            {action.label}
                          </button>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      {/* 底部统计 */}
      {!isLoading && data && data.items.length > 0 && (
        <div className="mt-4 pt-4 border-t border-neutral-800 flex items-center justify-between text-xs text-neutral-500">
          <span>
            共 {data.total_count} 项待办
          </span>
          <button
            onClick={loadActionItems}
            className="flex items-center gap-1 hover:text-neutral-300 transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            刷新
          </button>
        </div>
      )}
    </div>
  );
}