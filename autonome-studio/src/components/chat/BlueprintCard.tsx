"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Play,
  CheckCircle,
  Clock,
  Loader2,
  XCircle,
  ArrowRight,
  Eye,
  FileText,
  Database,
  Code,
  GitBranch,
  Sparkles,
  Save,
  Download
} from "lucide-react";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { BASE_URL } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================

export interface TaskNode {
  task_id: string;
  name: string;
  tool: string;
  depends_on: string[];
  expected_input?: string;
  expected_output?: string;
  instruction: string;
  status?: "pending" | "running" | "success" | "failed";
}

export interface BlueprintData {
  project_goal: string;
  is_complex_task: boolean;
  tasks: TaskNode[];
}

interface BlueprintCardProps {
  content: string;
  onExecute?: (blueprintId: string) => void;
}

// ==========================================
// 蓝图可视化卡片组件
// ==========================================

export function BlueprintCard({ content, onExecute }: BlueprintCardProps) {
  const { currentProjectId } = useWorkspaceStore();
  const [isExecuting, setIsExecuting] = useState(false);
  const [blueprintId, setBlueprintId] = useState<string | null>(null);
  const [taskStatuses, setTaskStatuses] = useState<Record<string, string>>({});

  // ✨ 固化相关状态
  const [isConsolidating, setIsConsolidating] = useState(false);
  const [consolidatedSkillId, setConsolidatedSkillId] = useState<string | null>(null);

  // 解析蓝图数据
  let blueprint: BlueprintData | null = null;
  try {
    blueprint = JSON.parse(content);
  } catch (e) {
    console.error("Failed to parse blueprint:", e);
    return null;
  }

  if (!blueprint || !blueprint.is_complex_task || !blueprint.tasks?.length) {
    return null;
  }

  // 拓扑排序获取执行顺序
  const getExecutionOrder = (tasks: TaskNode[]): TaskNode[] => {
    const taskMap = new Map(tasks.map(t => [t.task_id, t]));
    const visited = new Set<string>();
    const result: TaskNode[] = [];

    const visit = (taskId: string) => {
      if (visited.has(taskId)) return;
      visited.add(taskId);

      const task = taskMap.get(taskId);
      if (task) {
        for (const dep of task.depends_on || []) {
          visit(dep);
        }
        result.push(task);
      }
    };

    for (const task of tasks) {
      visit(task.task_id);
    }

    return result;
  };

  const orderedTasks = getExecutionOrder(blueprint.tasks);

  // 获取任务状态图标
  const getTaskIcon = (task: TaskNode) => {
    const status = taskStatuses[task.task_id] || task.status || "pending";

    switch (status) {
      case "running":
        return <Loader2 className="w-4 h-4 animate-spin text-blue-400" />;
      case "success":
        return <CheckCircle className="w-4 h-4 text-green-400" />;
      case "failed":
        return <XCircle className="w-4 h-4 text-red-400" />;
      default:
        return <Clock className="w-4 h-4 text-yellow-400" />;
    }
  };

  // 获取工具图标
  const getToolIcon = (tool: string) => {
    if (tool.includes("peek") || tool.includes("scan")) {
      return <Eye className="w-4 h-4" />;
    }
    if (tool.includes("python") || tool.includes("code")) {
      return <Code className="w-4 h-4" />;
    }
    if (tool.includes("data") || tool.includes("file")) {
      return <Database className="w-4 h-4" />;
    }
    return <FileText className="w-4 h-4" />;
  };

  // 执行蓝图
  const handleExecuteBlueprint = async () => {
    if (!currentProjectId) return;

    setIsExecuting(true);

    try {
      const token = localStorage.getItem("autonome_access_token");

      const response = await fetch(`${BASE_URL}/api/blueprint/execute`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          project_id: currentProjectId,
          blueprint: blueprint
        })
      });

      const result = await response.json();

      if (result.blueprint_id) {
        setBlueprintId(result.blueprint_id);
        onExecute?.(result.blueprint_id);
      }
    } catch (error) {
      console.error("Failed to execute blueprint:", error);
    } finally {
      setIsExecuting(false);
    }
  };

  // ✨ 固化为 SKILL
  const handleConsolidate = async () => {
    if (!blueprint || isConsolidating) return;

    setIsConsolidating(true);

    try {
      const token = localStorage.getItem("autonome_access_token");

      const response = await fetch(`${BASE_URL}/api/skills/consolidate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          blueprint_json: JSON.stringify(blueprint),
          project_id: currentProjectId
        })
      });

      const result = await response.json();

      if (result.success && result.skill_id) {
        setConsolidatedSkillId(result.skill_id);
      }
    } catch (error) {
      console.error("Failed to consolidate blueprint:", error);
    } finally {
      setIsConsolidating(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-gradient-to-br from-indigo-50/50 to-purple-50/50 dark:from-indigo-950/30 dark:to-purple-950/30 border border-indigo-200 dark:border-indigo-800/50 rounded-xl p-5 shadow-lg my-4 max-w-3xl"
    >
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-100 dark:bg-indigo-900/50 rounded-lg">
            <GitBranch className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              复杂任务蓝图
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {blueprint.project_goal}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-100 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700/50 rounded-full">
          <Sparkles className="w-4 h-4 text-purple-600 dark:text-purple-400" />
          <span className="text-xs font-medium text-purple-700 dark:text-purple-300">
            PI Agent 规划
          </span>
        </div>
      </div>

      {/* 任务流程时间线 */}
      <div className="bg-white/50 dark:bg-black/20 rounded-lg p-4 mb-4">
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3 flex items-center gap-2">
          <ArrowRight className="w-3 h-3" />
          执行流程 ({orderedTasks.length} 个步骤)
        </p>

        <div className="space-y-3">
          {orderedTasks.map((task, index) => (
            <div key={task.task_id} className="flex items-start gap-3">
              {/* 步骤序号 */}
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center">
                <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">
                  {index + 1}
                </span>
              </div>

              {/* 任务卡片 */}
              <div className="flex-1 bg-gray-100/50 dark:bg-neutral-800/50 rounded-lg p-3 border border-gray-200 dark:border-neutral-700">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {getToolIcon(task.tool)}
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {task.name}
                    </span>
                  </div>
                  {getTaskIcon(task)}
                </div>

                <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                  {task.instruction}
                </p>

                {/* 输入输出标签 */}
                <div className="flex flex-wrap gap-2">
                  {task.expected_input && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs rounded">
                      <Database className="w-3 h-3" />
                      输入: {task.expected_input.split("/").pop()}
                    </span>
                  )}
                  {task.expected_output && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded">
                      <FileText className="w-3 h-3" />
                      输出: {task.expected_output.split("/").pop()}
                    </span>
                  )}
                </div>

                {/* 依赖关系 */}
                {task.depends_on && task.depends_on.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-gray-200 dark:border-neutral-700">
                    <span className="text-xs text-gray-500 dark:text-gray-500">
                      依赖: {task.depends_on.map(d => {
                        const depTask = blueprint?.tasks.find(t => t.task_id === d);
                        return depTask?.name || d;
                      }).join(" -> ")}
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 执行按钮 */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-600 dark:text-gray-400">
          <span className="font-medium">{orderedTasks.length}</span> 个任务将按拓扑顺序执行
        </div>

        <div className="flex items-center gap-3">
          {/* ✨ 固化按钮 */}
          <button
            onClick={handleConsolidate}
            disabled={isConsolidating || !!consolidatedSkillId}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all ${
              consolidatedSkillId
                ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-700"
                : isConsolidating
                ? "bg-gray-200 dark:bg-neutral-700 text-gray-500 dark:text-gray-400 cursor-not-allowed"
                : "bg-amber-500 hover:bg-amber-600 text-white shadow-md hover:shadow-lg"
            }`}
          >
            {consolidatedSkillId ? (
              <>
                <CheckCircle className="w-4 h-4" />
                已固化: {consolidatedSkillId}
              </>
            ) : isConsolidating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                固化中...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                固化为 SKILL
              </>
            )}
          </button>

          {/* 执行按钮 */}
          <button
            onClick={handleExecuteBlueprint}
            disabled={isExecuting || !!blueprintId}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium text-sm transition-all ${
              blueprintId
                ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-700"
                : isExecuting
                ? "bg-gray-200 dark:bg-neutral-700 text-gray-500 dark:text-gray-400 cursor-not-allowed"
                : "bg-indigo-600 hover:bg-indigo-700 text-white shadow-md hover:shadow-lg"
            }`}
          >
            {blueprintId ? (
              <>
                <CheckCircle className="w-4 h-4" />
                执行中
              </>
            ) : isExecuting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                启动中...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                执行蓝图
              </>
            )}
          </button>
        </div>
      </div>
    </motion.div>
  );
}

// ==========================================
// 蓝图解析工具函数
// ==========================================

export function parseBlueprint(content: string): BlueprintData | null {
  if (!content) return null;

  try {
    // 从 json_blueprint 代码块中提取
    const blueprintMatch = content.match(/```json_blueprint\s*\n([\s\S]*?)```/);
    if (blueprintMatch) {
      const data = JSON.parse(blueprintMatch[1]);
      if (data.is_complex_task && data.tasks?.length > 0) {
        return data;
      }
    }

    // 也尝试直接解析整个内容（如果内容本身就是 JSON）
    const directParse = JSON.parse(content);
    if (directParse.is_complex_task && directParse.tasks?.length > 0) {
      return directParse;
    }

    return null;
  } catch (e) {
    return null;
  }
}