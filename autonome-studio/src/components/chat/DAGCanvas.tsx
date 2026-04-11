"use client";

/**
 * DAGCanvas.tsx - 交互式 DAG 可视化组件
 *
 * 使用 React Flow 实现交互式 DAG 图展示，支持：
 * - 自动布局（dagre 算法）
 * - 节点状态实时更新
 * - 点击节点查看详情
 * - 依赖关系可视化
 */

import React, { useCallback, useMemo, useState } from "react";
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  NodeProps,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from "reactflow";
import "reactflow/dist/style.css";
import dagre from "dagre";
import {
  Play,
  CheckCircle,
  Clock,
  Loader2,
  XCircle,
  AlertCircle,
  Eye,
  Code,
  Database,
  FileText,
  GitBranch,
} from "lucide-react";

// ==========================================
// 类型定义
// ==========================================

export type TaskStatus = "pending" | "running" | "success" | "failed" | "review_failed";

export interface DAGTaskNode {
  task_id: string;
  name: string;
  tool: string;
  depends_on: string[];
  expected_input?: string;
  expected_output?: string;
  instruction: string;
  status?: TaskStatus;
  result?: string;
  error?: string;
}

export interface DAGBlueprint {
  project_goal: string;
  is_complex_task: boolean;
  tasks: DAGTaskNode[];
}

interface DAGCanvasProps {
  blueprint: DAGBlueprint;
  taskStatuses?: Record<string, TaskStatus>;
  onNodeClick?: (taskId: string) => void;
  className?: string;
}

// ==========================================
// dagre 布局配置
// ==========================================

const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

const NODE_WIDTH = 280;
const NODE_HEIGHT = 120;

/**
 * 使用 dagre 算法自动布局 DAG
 */
const getLayoutedElements = (
  nodes: Node[],
  edges: Edge[],
  direction = "TB"
) => {
  const isHorizontal = direction === "LR";
  dagreGraph.setGraph({ rankdir: direction, nodesep: 80, ranksep: 100 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    node.position = {
      x: nodeWithPosition.x - NODE_WIDTH / 2,
      y: nodeWithPosition.y - NODE_HEIGHT / 2,
    };
    return node;
  });

  return { nodes: layoutedNodes, edges };
};

// ==========================================
// 自定义节点组件
// ==========================================

interface CustomNodeData {
  task: DAGTaskNode;
  status: TaskStatus;
  onNodeClick?: (taskId: string) => void;
}

const CustomNode: React.FC<NodeProps<CustomNodeData>> = ({ data, selected }) => {
  const { task, status, onNodeClick } = data;

  // 获取状态图标
  const getStatusIcon = () => {
    switch (status) {
      case "running":
        return <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />;
      case "success":
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case "failed":
        return <XCircle className="w-5 h-5 text-red-400" />;
      case "review_failed":
        return <AlertCircle className="w-5 h-5 text-amber-400" />;
      default:
        return <Clock className="w-5 h-5 text-gray-400" />;
    }
  };

  // 获取工具图标
  const getToolIcon = () => {
    if (task.tool.includes("peek") || task.tool.includes("scan")) {
      return <Eye className="w-4 h-4" />;
    }
    if (task.tool.includes("python") || task.tool.includes("code")) {
      return <Code className="w-4 h-4" />;
    }
    if (task.tool.includes("data") || task.tool.includes("file")) {
      return <Database className="w-4 h-4" />;
    }
    return <FileText className="w-4 h-4" />;
  };

  // 状态边框颜色
  const getBorderColor = () => {
    switch (status) {
      case "running":
        return "border-blue-400 shadow-blue-400/30";
      case "success":
        return "border-green-400 shadow-green-400/30";
      case "failed":
        return "border-red-400 shadow-red-400/30";
      case "review_failed":
        return "border-amber-400 shadow-amber-400/30";
      default:
        return "border-gray-300 dark:border-gray-600";
    }
  };

  const getBgColor = () => {
    switch (status) {
      case "running":
        return "bg-blue-50 dark:bg-blue-950/30";
      case "success":
        return "bg-green-50 dark:bg-green-950/30";
      case "failed":
        return "bg-red-50 dark:bg-red-950/30";
      case "review_failed":
        return "bg-amber-50 dark:bg-amber-950/30";
      default:
        return "bg-white dark:bg-neutral-800";
    }
  };

  return (
    <div
      className={`
        w-[280px] rounded-lg border-2 shadow-lg cursor-pointer transition-all duration-200
        ${getBorderColor()} ${getBgColor()}
        ${selected ? "ring-2 ring-indigo-400 ring-offset-2" : ""}
      `}
      onClick={() => onNodeClick?.(task.task_id)}
    >
      {/* 输入 Handle */}
      {task.depends_on.length > 0 && (
        <Handle
          type="target"
          position={Position.Top}
          className="w-3 h-3 bg-gray-400 dark:bg-gray-500"
        />
      )}

      {/* 节点内容 */}
      <div className="p-3">
        {/* 标题栏 */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-indigo-100 dark:bg-indigo-900/50">
              {getToolIcon()}
            </div>
            <span className="font-medium text-sm text-gray-900 dark:text-white truncate max-w-[180px]">
              {task.name}
            </span>
          </div>
          {getStatusIcon()}
        </div>

        {/* 指令描述 */}
        <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2 mb-2">
          {task.instruction}
        </p>

        {/* 输入输出标签 */}
        <div className="flex flex-wrap gap-1.5">
          {task.expected_input && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs rounded">
              <Database className="w-3 h-3" />
              输入
            </span>
          )}
          {task.expected_output && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 text-xs rounded">
              <FileText className="w-3 h-3" />
              输出
            </span>
          )}
        </div>
      </div>

      {/* 输出 Handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-gray-400 dark:bg-gray-500"
      />
    </div>
  );
};

// 节点类型映射
const nodeTypes = {
  dagNode: CustomNode,
};

// ==========================================
// 主组件
// ==========================================

export function DAGCanvas({
  blueprint,
  taskStatuses = {},
  onNodeClick,
  className = "",
}: DAGCanvasProps) {
  // 将蓝图任务转换为 React Flow 节点和边
  const { initialNodes, initialEdges } = useMemo(() => {
    const nodes: Node[] = blueprint.tasks.map((task, index) => ({
      id: task.task_id,
      type: "dagNode",
      position: { x: 0, y: 0 }, // 将由 dagre 布局
      data: {
        task,
        status: taskStatuses[task.task_id] || task.status || "pending",
        onNodeClick,
      },
    }));

    const edges: Edge[] = blueprint.tasks.flatMap((task) =>
      task.depends_on.map((dep) => ({
        id: `${dep}-${task.task_id}`,
        source: dep,
        target: task.task_id,
        type: "smoothstep",
        animated: taskStatuses[task.task_id] === "running",
        style: {
          stroke:
            taskStatuses[task.task_id] === "success"
              ? "#22c55e"
              : taskStatuses[task.task_id] === "failed"
              ? "#ef4444"
              : "#94a3b8",
          strokeWidth: 2,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color:
            taskStatuses[task.task_id] === "success"
              ? "#22c55e"
              : taskStatuses[task.task_id] === "failed"
              ? "#ef4444"
              : "#94a3b8",
        },
      }))
    );

    // 应用 dagre 布局
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      nodes,
      edges
    );

    return { initialNodes: layoutedNodes, initialEdges: layoutedEdges };
  }, [blueprint, taskStatuses, onNodeClick]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // MiniMap 节点颜色
  const nodeColor = useCallback((node: Node) => {
    const status = node.data?.status || "pending";
    switch (status) {
      case "running":
        return "#3b82f6";
      case "success":
        return "#22c55e";
      case "failed":
        return "#ef4444";
      case "review_failed":
        return "#f59e0b";
      default:
        return "#94a3b8";
    }
  }, []);

  return (
    <div className={`w-full h-[400px] bg-gray-50 dark:bg-neutral-900 rounded-lg ${className}`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.5}
        maxZoom={1.5}
      >
        <Background color="#aaa" gap={16} />
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={nodeColor}
          nodeStrokeWidth={3}
          zoomable
          pannable
          className="!bg-gray-100 dark:!bg-neutral-800"
        />
      </ReactFlow>
    </div>
  );
}

export default DAGCanvas;