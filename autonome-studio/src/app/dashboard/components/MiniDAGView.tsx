"use client";

/**
 * 微缩 DAG 视图组件
 *
 * 以简化的 SVG 形式展示蓝图执行进度
 * 复用 DAGCanvas 的设计语言，但缩小为迷你视图
 */

import { useMemo } from "react";

// ==========================================
// 类型定义
// ==========================================

interface MiniDAGNode {
  task_id: string;
  name: string;
  status: "pending" | "running" | "success" | "failed";
  position?: { x: number; y: number };
}

interface MiniDAGViewProps {
  nodes: MiniDAGNode[];
  size?: number; // 正方形尺寸
}

// ==========================================
// 状态颜色配置
// ==========================================

const STATUS_COLORS = {
  pending: "#6b7280", // gray
  running: "#3b82f6", // blue
  success: "#22c55e", // green
  failed: "#ef4444", // red
};

// ==========================================
// 组件
// ==========================================

export function MiniDAGView({ nodes, size = 80 }: MiniDAGViewProps) {
  // 计算节点位置（简化版：水平排列）
  const layoutNodes = useMemo(() => {
    const nodeSize = 12;
    const gap = 8;
    const totalWidth = nodes.length * (nodeSize + gap) - gap;

    return nodes.map((node, index) => ({
      ...node,
      x: (size - totalWidth) / 2 + index * (nodeSize + gap),
      y: size / 2 - nodeSize / 2,
      size: nodeSize,
    }));
  }, [nodes, size]);

  if (!nodes || nodes.length === 0) {
    return (
      <div
        className="flex items-center justify-center bg-neutral-800/50 rounded"
        style={{ width: size, height: size }}
      >
        <span className="text-xs text-neutral-500">无任务</span>
      </div>
    );
  }

  return (
    <svg width={size} height={size} className="bg-neutral-800/30 rounded">
      {/* 连接线 */}
      {layoutNodes.slice(0, -1).map((node, index) => {
        const nextNode = layoutNodes[index + 1];
        return (
          <line
            key={`line-${node.task_id}`}
            x1={node.x + node.size}
            y1={node.y + node.size / 2}
            x2={nextNode.x}
            y2={nextNode.y + nextNode.size / 2}
            stroke="#374151"
            strokeWidth="2"
          />
        );
      })}

      {/* 节点 */}
      {layoutNodes.map((node) => (
        <g key={node.task_id}>
          <rect
            x={node.x}
            y={node.y}
            width={node.size}
            height={node.size}
            rx={3}
            fill={STATUS_COLORS[node.status]}
            opacity={node.status === "pending" ? 0.5 : 1}
          />
          {/* 运行中的动画效果 */}
          {node.status === "running" && (
            <rect
              x={node.x}
              y={node.y}
              width={node.size}
              height={node.size}
              rx={3}
              fill="none"
              stroke="#60a5fa"
              strokeWidth="2"
              className="animate-pulse"
            />
          )}
        </g>
      ))}
    </svg>
  );
}