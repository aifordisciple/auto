"use client";

/**
 * 动态科研工作流大厅面板
 *
 * 展示用户正在执行的蓝图工作流，包含：
 * - 微缩 DAG 进度视图
 * - ETA 预估
 * - 进度条
 */

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  RefreshCw,
  ChevronRight,
  Terminal,
  CheckCircle,
  Clock,
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { MiniDAGView } from "./MiniDAGView";
import { ETABadge } from "./ETABadge";

// ==========================================
// 类型定义
// ==========================================

interface MiniDAGNode {
  task_id: string;
  name: string;
  status: "pending" | "running" | "success" | "failed";
}

interface ActiveWorkflow {
  task_id: string;
  project_goal: string;
  status: "running" | "pending" | "paused";
  progress: number;
  completed_tasks: number;
  total_tasks: number;
  eta_seconds: number | null;
  started_at: string | null;
  mini_dag: MiniDAGNode[];
}

interface ActiveWorkflowsData {
  workflows: ActiveWorkflow[];
  total_count: number;
}

// ==========================================
// 组件
// ==========================================

export function ActiveWorkflowsPanel() {
  const [data, setData] = useState<ActiveWorkflowsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadWorkflows();
    // 每 10 秒刷新一次
    const interval = setInterval(loadWorkflows, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadWorkflows = async () => {
    try {
      const result = await fetchAPI("/dashboard/active-workflows?limit=5");
      setData(result);
    } catch (error) {
      console.error("加载工作流数据失败:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // 格式化开始时间
  const formatStartTime = (isoString: string | null) => {
    if (!isoString) return "刚刚";
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

  // 获取进度条颜色
  const getProgressColor = (progress: number) => {
    if (progress >= 80) return "bg-emerald-500";
    if (progress >= 50) return "bg-blue-500";
    if (progress >= 20) return "bg-amber-500";
    return "bg-neutral-500";
  };

  return (
    <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-6">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <RefreshCw className="w-5 h-5 text-cyan-400" />
          动态科研工作流大厅
        </h2>
        {data && data.total_count > 0 && (
          <span className="text-xs text-cyan-400 bg-cyan-500/10 px-2 py-1 rounded">
            {data.total_count} 个活跃
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : !data || data.workflows.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-neutral-500">
          <Terminal className="w-12 h-12 mb-4 opacity-20" />
          <p className="text-sm">暂无正在执行的工作流</p>
          <p className="text-xs mt-1">开始一个新的分析任务吧</p>
        </div>
      ) : (
        <div className="space-y-4">
          {data.workflows.map((workflow, index) => (
            <motion.div
              key={workflow.task_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
              className="bg-neutral-800/50 rounded-lg p-4 border border-neutral-700/50 hover:border-neutral-600 transition-colors"
            >
              <div className="flex items-start gap-4">
                {/* 微缩 DAG 视图 */}
                <MiniDAGView
                  nodes={workflow.mini_dag}
                  size={80}
                />

                {/* 详情 */}
                <div className="flex-1 min-w-0">
                  {/* 项目目标 */}
                  <h3 className="text-sm font-medium text-white truncate">
                    {workflow.project_goal}
                  </h3>

                  {/* 进度条 */}
                  <div className="mt-2">
                    <div className="flex items-center justify-between text-xs text-neutral-500 mb-1">
                      <span>
                        {workflow.completed_tasks} / {workflow.total_tasks} 任务
                      </span>
                      <span>{workflow.progress.toFixed(0)}%</span>
                    </div>
                    <div className="h-1.5 bg-neutral-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${getProgressColor(workflow.progress)} transition-all duration-500`}
                        style={{ width: `${workflow.progress}%` }}
                      />
                    </div>
                  </div>

                  {/* 底部信息 */}
                  <div className="mt-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {/* ETA */}
                      <ETABadge
                        etaSeconds={workflow.eta_seconds}
                        isCompleted={workflow.progress >= 100}
                      />

                      {/* 开始时间 */}
                      <span className="text-xs text-neutral-500">
                        {formatStartTime(workflow.started_at)}
                      </span>
                    </div>

                    {/* 查看详情按钮 */}
                    <button
                      className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                      onClick={() => {
                        // TODO: 跳转到任务详情
                        window.open(`/chat?task=${workflow.task_id}`, "_blank");
                      }}
                    >
                      查看详情
                      <ExternalLink className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>

              {/* 任务状态步骤 */}
              <div className="mt-3 pt-3 border-t border-neutral-700/50">
                <div className="flex items-center gap-2 text-xs overflow-x-auto pb-1">
                  {workflow.mini_dag.slice(0, 5).map((node, idx) => (
                    <div key={node.task_id} className="flex items-center gap-1 whitespace-nowrap">
                      {node.status === "success" ? (
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                      ) : node.status === "running" ? (
                        <RefreshCw className="w-3.5 h-3.5 text-blue-400 animate-spin" />
                      ) : node.status === "failed" ? (
                        <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                      ) : (
                        <Clock className="w-3.5 h-3.5 text-neutral-500" />
                      )}
                      <span
                        className={
                          node.status === "success"
                            ? "text-emerald-400"
                            : node.status === "running"
                            ? "text-blue-400"
                            : node.status === "failed"
                            ? "text-red-400"
                            : "text-neutral-500"
                        }
                      >
                        {node.name}
                      </span>
                      {idx < Math.min(workflow.mini_dag.length, 5) - 1 && (
                        <ChevronRight className="w-3 h-3 text-neutral-600" />
                      )}
                    </div>
                  ))}
                  {workflow.mini_dag.length > 5 && (
                    <span className="text-neutral-600 text-xs">
                      +{workflow.mini_dag.length - 5} 更多
                    </span>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}