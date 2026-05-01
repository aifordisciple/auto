/**
 * TaskCard — Claude Code 提交的重型任务状态展示组件
 *
 * 显示通过 Celery 异步执行的生信分析任务状态。
 * 支持 pending/running/completed/failed 四种状态的可视化展示。
 */
'use client';

import { useEffect, useState, useCallback } from 'react';
import { fetchAPI } from '@/lib/api';

interface TaskInfo {
  task_id: string;
  skill_id?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  output_files?: Array<{ name: string; path: string; size?: number }>;
  error_text?: string;
  started_at?: string;
  completed_at?: string;
}

interface TaskCardProps {
  taskId: string;
  skillName?: string;
}

const STATUS_CONFIG = {
  pending: { label: '排队中', color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/30' },
  running: { label: '运行中', color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  completed: { label: '已完成', color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30' },
  failed: { label: '失败', color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' },
} as const;

export function TaskCard({ taskId, skillName }: TaskCardProps) {
  const [task, setTask] = useState<TaskInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchTask = useCallback(async () => {
    try {
      const res = await fetchAPI(`/api/claude/tasks/${taskId}`);
      if (res.ok) {
        const data = await res.json();
        setTask(data as TaskInfo);
        setError(null);
      }
    } catch (err) {
      setError('无法获取任务状态');
    }
  }, [taskId]);

  useEffect(() => {
    fetchTask();

    // 如果任务未完成，每隔 5 秒轮询
    if (!task || task.status === 'pending' || task.status === 'running') {
      const interval = setInterval(fetchTask, 5000);
      return () => clearInterval(interval);
    }
  }, [taskId, task?.status, fetchTask]);

  if (error) {
    return (
      <div className="border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
        任务状态获取失败: {error}
      </div>
    );
  }

  if (!task) {
    return (
      <div className="border border-gray-700 rounded-lg p-3 text-sm text-gray-500">
        加载任务信息...
      </div>
    );
  }

  const config = STATUS_CONFIG[task.status];

  return (
    <div className={`border rounded-lg overflow-hidden mb-2 ${config.border}`}>
      {/* 状态栏 */}
      <div className={`flex items-center justify-between px-3 py-2 ${config.bg}`}>
        <div className="flex items-center gap-2">
          <span className="text-xs">🔧</span>
          <span className="text-sm font-medium text-gray-200">
            {skillName || task.skill_id || '重型任务'}
          </span>
        </div>
        <span className={`text-xs font-medium ${config.color}`}>
          {config.label}
        </span>
      </div>

      {/* 详情 */}
      <div className="px-3 py-2 text-xs text-gray-400 space-y-1">
        <div>
          <span className="text-gray-500">任务ID: </span>
          <code className="text-gray-300">{taskId.slice(0, 8)}...</code>
        </div>
        {task.started_at && (
          <div>
            <span className="text-gray-500">开始时间: </span>
            {new Date(task.started_at).toLocaleString()}
          </div>
        )}
        {task.completed_at && (
          <div>
            <span className="text-gray-500">完成时间: </span>
            {new Date(task.completed_at).toLocaleString()}
          </div>
        )}

        {/* 输出文件 */}
        {task.output_files && task.output_files.length > 0 && (
          <div className="mt-2">
            <div className="text-gray-500 mb-1">输出文件:</div>
            {task.output_files.map((f, i) => (
              <div key={i} className="flex items-center gap-2 text-gray-300 ml-2">
                <span>📄</span>
                <span>{f.name}</span>
                {f.size && (
                  <span className="text-gray-500">
                    ({(f.size / 1024).toFixed(1)} KB)
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* 错误信息 */}
        {task.error_text && (
          <div className="mt-2 p-2 bg-red-500/10 rounded border border-red-500/20 text-red-400">
            {task.error_text}
          </div>
        )}
      </div>
    </div>
  );
}
