'use client'

/**
 * DAG 进度可视化组件。
 *
 * 显示 TaskDAG 中各 TaskNode 的执行状态，
 * 包括 pending/ready/running/completed/failed 五种状态。
 * 用于 ChatStage 中展示多步骤任务的执行进度。
 */

interface DAGNodeProgress {
  task_id: string
  intent: string
  status: 'pending' | 'ready' | 'running' | 'completed' | 'failed'
  label?: string
}

interface DAGProgressViewProps {
  nodes: DAGNodeProgress[]
}

const STATUS_STYLES: Record<string, { bg: string; text: string; icon: string }> = {
  pending:  { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-500 dark:text-gray-400', icon: '○' },
  ready:    { bg: 'bg-blue-50 dark:bg-blue-900/30', text: 'text-blue-600 dark:text-blue-400', icon: '◎' },
  running:  { bg: 'bg-amber-50 dark:bg-amber-900/30', text: 'text-amber-600 dark:text-amber-400', icon: '◉' },
  completed: { bg: 'bg-green-50 dark:bg-green-900/30', text: 'text-green-600 dark:text-green-400', icon: '✓' },
  failed:   { bg: 'bg-red-50 dark:bg-red-900/30', text: 'text-red-600 dark:text-red-400', icon: '✗' },
}

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  ready: '就绪',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
}

export function DAGProgressView({ nodes }: DAGProgressViewProps) {
  if (!nodes || nodes.length === 0) return null

  // 单节点不显示进度条
  if (nodes.length === 1) return null

  const completedCount = nodes.filter(n => n.status === 'completed').length
  const totalCount = nodes.length

  return (
    <div className="my-3 p-3 bg-white/80 dark:bg-gray-800/80 rounded-xl border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
          任务进度
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-500">
          {completedCount}/{totalCount}
        </span>
      </div>

      {/* 进度条 */}
      <div className="flex gap-1 mb-2">
        {nodes.map((node) => {
          const style = STATUS_STYLES[node.status] || STATUS_STYLES.pending
          return (
            <div
              key={node.task_id}
              className={`flex-1 h-1.5 rounded-full ${style.bg} transition-colors duration-300`}
              title={`${node.label || node.task_id}: ${STATUS_LABELS[node.status]}`}
            />
          )
        })}
      </div>

      {/* 节点列表 */}
      <div className="flex flex-wrap gap-2">
        {nodes.map((node) => {
          const style = STATUS_STYLES[node.status] || STATUS_STYLES.pending
          return (
            <div
              key={node.task_id}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs ${style.bg} ${style.text}`}
            >
              <span>{style.icon}</span>
              <span>{node.label || node.task_id}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}