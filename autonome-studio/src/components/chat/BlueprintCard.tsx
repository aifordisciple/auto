"use client";

import { useState, useEffect, useRef } from "react";
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
  Download,
  Settings,
  X,
} from "lucide-react";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { BASE_URL } from "@/lib/api";
import { DAGCanvas, TaskStatus } from "./DAGCanvas";

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
  status?: TaskStatus;
}

export interface BlueprintData {
  project_goal: string;
  is_complex_task: boolean;
  tasks: TaskNode[];
}

interface BlueprintCardProps {
  data?: BlueprintData;       // 已解析的蓝图数据对象（优先使用）
  content?: string;           // 原始 JSON 字符串（兼容旧用法）
  onExecute?: (blueprintId: string) => void;
  taskStatuses?: Record<string, TaskStatus>;
}

// ==========================================
// 节点编辑抽屉组件
// ==========================================

interface NodeEditorDrawerProps {
  task: TaskNode | null;
  isOpen: boolean;
  onClose: () => void;
  onSave?: (taskId: string, updates: Partial<TaskNode>) => void;
}

function NodeEditorDrawer({ task, isOpen, onClose, onSave }: NodeEditorDrawerProps) {
  if (!isOpen || !task) return null;

  return (
    <motion.div
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      className="fixed right-0 top-0 h-full w-80 bg-white dark:bg-neutral-900 border-l border-gray-200 dark:border-neutral-700 shadow-xl z-50 overflow-y-auto"
    >
      <div className="p-4">
        {/* 标题栏 */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            编辑节点
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-neutral-800 transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* 任务信息 */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              任务名称
            </label>
            <input
              type="text"
              value={task.name}
              readOnly
              className="w-full px-3 py-2 bg-gray-100 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-lg text-gray-900 dark:text-white"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              工具
            </label>
            <input
              type="text"
              value={task.tool}
              readOnly
              className="w-full px-3 py-2 bg-gray-100 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-lg text-gray-900 dark:text-white"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              指令描述
            </label>
            <textarea
              value={task.instruction}
              readOnly
              rows={4}
              className="w-full px-3 py-2 bg-gray-100 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-lg text-gray-900 dark:text-white resize-none"
            />
          </div>

          {task.expected_input && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                输入路径
              </label>
              <input
                type="text"
                value={task.expected_input}
                readOnly
                className="w-full px-3 py-2 bg-gray-100 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-lg text-sm text-gray-600 dark:text-gray-400"
              />
            </div>
          )}

          {task.expected_output && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                输出路径
              </label>
              <input
                type="text"
                value={task.expected_output}
                readOnly
                className="w-full px-3 py-2 bg-gray-100 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-lg text-sm text-gray-600 dark:text-gray-400"
              />
            </div>
          )}

          {task.depends_on.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                依赖任务
              </label>
              <div className="flex flex-wrap gap-1.5">
                {task.depends_on.map((dep) => (
                  <span
                    key={dep}
                    className="px-2 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 text-xs rounded"
                  >
                    {dep}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 操作按钮 */}
        <div className="mt-6 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-gray-100 dark:bg-neutral-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-neutral-700 transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </motion.div>
  );
}

// ==========================================
// 蓝图可视化卡片组件
// ==========================================

export function BlueprintCard({ data, content, onExecute, taskStatuses: externalTaskStatuses }: BlueprintCardProps) {
  const { currentProjectId } = useWorkspaceStore();
  const [isExecuting, setIsExecuting] = useState(false);
  const [blueprintId, setBlueprintId] = useState<string | null>(null);
  const [taskStatuses, setTaskStatuses] = useState<Record<string, TaskStatus>>(externalTaskStatuses || {});

  // ✨ 固化相关状态
  const [isConsolidating, setIsConsolidating] = useState(false);
  const [consolidatedSkillId, setConsolidatedSkillId] = useState<string | null>(null);

  // ✨ 节点编辑抽屉状态
  const [selectedTask, setSelectedTask] = useState<TaskNode | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // ✨ 视图模式：dag（交互式DAG）或 timeline（垂直时间线）
  const [viewMode, setViewMode] = useState<"dag" | "timeline">("dag");

  // ✨ SSE EventSource 引用（用于清理）
  const eventSourceRef = useRef<EventSource | null>(null);

  // ✨ 组件卸载时清理 EventSource
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  // 解析蓝图数据：优先使用已解析的 data 对象，否则尝试解析 content 字符串
  let blueprint: BlueprintData | null = data || null;

  // 如果没有 data，尝试从 content 解析
  if (!blueprint && content) {
    try {
      blueprint = JSON.parse(content);
    } catch (e) {
      console.error("Failed to parse blueprint:", e);
      return null;
    }
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

  // 处理节点点击
  const handleNodeClick = (taskId: string) => {
    const task = blueprint?.tasks.find(t => t.task_id === taskId);
    if (task) {
      setSelectedTask(task);
      setIsDrawerOpen(true);
    }
  };

  // 执行蓝图（Celery 异步模式）
  const handleExecuteBlueprint = async () => {
    if (!currentProjectId) return;

    setIsExecuting(true);

    try {
      const token = localStorage.getItem("autonome_access_token");

      // ==========================================
      // Step 1: 提交任务获取 task_id
      // ==========================================
      const submitResponse = await fetch(`${BASE_URL}/api/blueprint/execute`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          project_id: currentProjectId,
          blueprint_json: blueprint
        })
      });

      if (!submitResponse.ok) {
        const errorData = await submitResponse.json();
        throw new Error(errorData.detail || "提交任务失败");
      }

      const submitResult = await submitResponse.json();
      const taskId = submitResult.task_id;

      if (!taskId) {
        throw new Error("未获取到任务 ID");
      }

      console.log("📋 Blueprint task submitted:", taskId);
      setBlueprintId(taskId);
      setIsExecuting(false); // 提交完成，进入监听状态

      // ==========================================
      // Step 2: 连接 SSE 事件流
      // ==========================================
      // 清理旧的 EventSource
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      // EventSource 不支持自定义 header，通过 query parameter 传递 token
      const sseUrl = token
        ? `${BASE_URL}/api/blueprint/${taskId}/events/stream?token=${encodeURIComponent(token)}`
        : `${BASE_URL}/api/blueprint/${taskId}/events/stream`;

      const eventSource = new EventSource(sseUrl);
      eventSourceRef.current = eventSource;

      // ==========================================
      // SSE 事件监听：使用 addEventListener 监听各类型事件
      // 注意：SSE 的 event 字段通过 addEventListener 监听，不在 data JSON 中
      // ==========================================

      // 蓝图开始事件
      eventSource.addEventListener("blueprint_start", (event) => {
        console.log("🚀 Blueprint started:", event.data);
      });

      // 任务开始事件
      eventSource.addEventListener("task_start", (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log("▶️ Task started:", data.task_id);
          setTaskStatuses(prev => ({
            ...prev,
            [data.task_id]: "running"
          }));
        } catch (e) {
          console.error("Failed to parse task_start event:", e);
        }
      });

      // 任务完成事件
      eventSource.addEventListener("task_complete", (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log("✅ Task complete:", data.task_id, data.status);
          setTaskStatuses(prev => ({
            ...prev,
            [data.task_id]: data.status || "success"
          }));
        } catch (e) {
          console.error("Failed to parse task_complete event:", e);
        }
      });

      // 任务失败事件
      eventSource.addEventListener("task_failed", (event) => {
        try {
          const data = JSON.parse(event.data);
          console.error("❌ Task failed:", data.task_id, data.error);
          setTaskStatuses(prev => ({
            ...prev,
            [data.task_id]: "failed"
          }));
        } catch (e) {
          console.error("Failed to parse task_failed event:", e);
        }
      });

      // 蓝图完成事件
      eventSource.addEventListener("blueprint_complete", (event) => {
        console.log("🎉 Blueprint complete:", event.data);
        eventSource.close();
        eventSourceRef.current = null;
      });

      // 蓝图错误事件
      eventSource.addEventListener("blueprint_error", (event) => {
        console.error("❌ Blueprint error:", event.data);
        eventSource.close();
        eventSourceRef.current = null;
      });

      // 流结束事件
      eventSource.addEventListener("done", () => {
        console.log("🏁 Event stream done");
        eventSource.close();
        eventSourceRef.current = null;
      });

      // 心跳事件（保持连接）
      eventSource.addEventListener("heartbeat", () => {
        // 心跳事件，无需处理
      });

      // 连接错误处理
      eventSource.onerror = (error) => {
        console.error("SSE connection error:", error);
        eventSource.close();
        eventSourceRef.current = null;
      };

    } catch (error) {
      console.error("Failed to execute blueprint:", error);
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
    <>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gradient-to-br from-indigo-50/50 to-purple-50/50 dark:from-indigo-950/30 dark:to-purple-950/30 border border-indigo-200 dark:border-indigo-800/50 rounded-xl p-5 shadow-lg my-4 max-w-4xl"
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
          <div className="flex items-center gap-2">
            {/* 视图切换按钮 */}
            <div className="flex items-center bg-gray-100 dark:bg-neutral-800 rounded-lg p-1">
              <button
                onClick={() => setViewMode("dag")}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  viewMode === "dag"
                    ? "bg-white dark:bg-neutral-700 text-indigo-600 dark:text-indigo-400 shadow"
                    : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                }`}
              >
                DAG 图
              </button>
              <button
                onClick={() => setViewMode("timeline")}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  viewMode === "timeline"
                    ? "bg-white dark:bg-neutral-700 text-indigo-600 dark:text-indigo-400 shadow"
                    : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                }`}
              >
                时间线
              </button>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-100 dark:bg-purple-900/30 border border-purple-200 dark:border-purple-700/50 rounded-full">
              <Sparkles className="w-4 h-4 text-purple-600 dark:text-purple-400" />
              <span className="text-xs font-medium text-purple-700 dark:text-purple-300">
                PI Agent 规划
              </span>
            </div>
          </div>
        </div>

        {/* DAG 可视化区域 */}
        {viewMode === "dag" ? (
          <DAGCanvas
            blueprint={blueprint}
            taskStatuses={taskStatuses}
            onNodeClick={handleNodeClick}
            className="mb-4"
          />
        ) : (
          /* 垂直时间线视图 */
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
                  <div
                    className="flex-1 bg-gray-100/50 dark:bg-neutral-800/50 rounded-lg p-3 border border-gray-200 dark:border-neutral-700 cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-600 transition-colors"
                    onClick={() => handleNodeClick(task.task_id)}
                  >
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
        )}

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

      {/* 节点编辑抽屉 */}
      <NodeEditorDrawer
        task={selectedTask}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
      />
    </>
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