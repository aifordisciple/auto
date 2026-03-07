"use client";

import { useEffect, useRef, useState } from "react";
import { X, Terminal, CheckCircle2, Loader2, AlertCircle, CircleDashed, ListTodo, RefreshCw, Trash2 } from "lucide-react";
import { useTaskStore, Task } from "../../store/useTaskStore";
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { BASE_URL, fetchAPI } from "../../lib/api";

// 状态配置
const statusConfig: Record<string, { icon: any; color: string; bg: string; border: string; label: string }> = {
  PENDING: { icon: CircleDashed, color: "text-neutral-500", bg: "bg-neutral-500/10", border: "border-neutral-800", label: "队列中" },
  STARTED: { icon: Loader2, color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/30", label: "启动中" },
  PROGRESS: { icon: Loader2, color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/30", label: "分析中" },
  SUCCESS: { icon: CheckCircle2, color: "text-emerald-500", bg: "bg-emerald-500/10", border: "border-emerald-500/30", label: "已完成" },
  FAILURE: { icon: AlertCircle, color: "text-red-500", bg: "bg-red-500/10", border: "border-red-500/30", label: "异常中止" },
  RETRY: { icon: RefreshCw, color: "text-yellow-500", bg: "bg-yellow-500/10", border: "border-yellow-500/30", label: "重试中" },
};

// 默认配置
const defaultConfig = { icon: CircleDashed, color: "text-neutral-400", bg: "bg-neutral-500/10", border: "border-neutral-800", label: "未知" };

function getStatusConfig(status: string) {
  return statusConfig[status] || defaultConfig;
}

function formatTime(timestamp: number) {
  const diff = Date.now() / 1000 - timestamp;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

export function TaskCenter() {
  const { tasks, activeTaskId, logs, isLoading, fetchTasks, setActiveTaskId, appendLog, clearLogs } = useTaskStore();
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // 加载任务列表
  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 5000); // 每5秒刷新
    return () => clearInterval(interval);
  }, [fetchTasks]);

  // 自动滚动日志
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // 连接日志流
  useEffect(() => {
    if (!selectedTask) return;
    
    setActiveTaskId(selectedTask);
    clearLogs();
    
    const controller = new AbortController();
    const connectToLogStream = async () => {
      try {
        await fetchEventSource(`${BASE_URL}/api/tasks/${selectedTask}/logs/stream`, {
          method: 'GET',
          signal: controller.signal,
          onmessage(event) {
            if (event.event === 'log') appendLog(JSON.parse(event.data).text);
            else if (event.event === 'done') controller.abort();
          },
          onerror(err) { console.error(err); }
        });
      } catch (e) { console.error(e); }
    };
    connectToLogStream();
    return () => controller.abort();
  }, [selectedTask, setActiveTaskId, appendLog, clearLogs]);

  // 新增：删除并终止任务
  const handleDeleteTask = async (e: React.MouseEvent, task: Task) => {
    e.stopPropagation(); // 阻止点击卡片触发进入日志视图的事件

    const isRunning = task.status === 'STARTED' || task.status === 'PROGRESS';
    const msg = isRunning
      ? `⚠️ 警告：该任务正在后台算力集群中运行！\n\n确定要强制终止并彻底删除任务 ${task.task_id.slice(0,8)} 吗？`
      : `确定要从历史看板中清理该任务吗？`;

    if (!window.confirm(msg)) return;

    try {
      await fetchAPI(`/api/tasks/${task.task_id}`, { method: 'DELETE' });
      // 如果删除的是当前正在查看的任务，退出日志视图
      if (selectedTask === task.task_id) {
        setSelectedTask(null);
      }
      fetchTasks(); // 刷新看板
    } catch (err) {
      alert("❌ 删除任务失败，请检查网络。");
    }
  };

  // 按列分组任务
  const columns = [
    { key: 'PENDING', title: '队列中', tasks: tasks.filter(t => t.status === 'PENDING') },
    { key: 'STARTED', title: '启动中', tasks: tasks.filter(t => t.status === 'STARTED') },
    { key: 'PROGRESS', title: '分析中', tasks: tasks.filter(t => t.status === 'PROGRESS') },
    { key: 'SUCCESS', title: '已完成', tasks: tasks.filter(t => t.status === 'SUCCESS') },
    { key: 'FAILURE', title: '异常中止', tasks: tasks.filter(t => t.status === 'FAILURE') },
  ];

  return (
    <div className="flex h-full">
      {/* 看板视图 */}
      <div className={`flex-1 p-4 flex gap-3 transition-all duration-300 ${selectedTask ? '-translate-x-full opacity-0 absolute' : 'translate-x-0 opacity-100'}`}>
        {columns.map(col => (
          <div key={col.key} className="flex-1 flex flex-col bg-[#1a1a1b] border border-neutral-800/60 rounded-xl overflow-hidden min-w-0">
            <div className="px-3 py-2.5 border-b border-neutral-800/60 bg-neutral-900/50 text-sm font-medium text-neutral-300 flex items-center justify-between shrink-0">
              <span>{col.title}</span>
              <span className="text-xs px-1.5 py-0.5 bg-neutral-800 rounded-full">{col.tasks.length}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-2">
              {col.tasks.length === 0 ? (
                <div className="text-center text-neutral-600 text-xs py-8">暂无任务</div>
              ) : (
                col.tasks.map(task => {
                  const Cfg = getStatusConfig(task.status);
                  const Icon = Cfg.icon;
                  return (
                    <div 
                      key={task.task_id}
                      onClick={() => setSelectedTask(task.task_id)}
                      className={`p-3 rounded-lg border ${Cfg.border} ${Cfg.bg} hover:bg-neutral-800/50 cursor-pointer transition-all group`}
                    >
                      {/* 卡片头部：悬浮删除按钮 */}
                      <div className="flex justify-between items-start mb-1.5 relative">
                        <span className="text-[10px] font-mono text-neutral-500">{task.task_id.slice(0, 8)}...</span>

                        <div className="flex items-center gap-1.5">
                          {/* 默认显示的状态图标 */}
                          <Icon size={14} className={`${Cfg.color} ${task.status === 'PROGRESS' || task.status === 'STARTED' ? 'animate-spin' : ''} group-hover:opacity-0 transition-opacity absolute right-0`} />

                          {/* Hover 时才显示的红色终止/删除按钮 (覆盖在原来的图标上) */}
                          <button
                            onClick={(e) => handleDeleteTask(e, task)}
                            className="text-red-400 hover:text-red-300 hover:bg-red-500/20 p-1 rounded opacity-0 group-hover:opacity-100 transition-all absolute right-0 -top-1"
                            title={task.status === 'PROGRESS' || task.status === 'STARTED' ? "强制终止并删除" : "删除记录"}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>
                      <h4 className="text-xs text-neutral-200 font-medium leading-snug group-hover:text-blue-400 transition-colors line-clamp-2">{task.name}</h4>
                      {task.status === 'PROGRESS' && task.progress !== null && (
                        <div className="mt-2">
                          <div className="w-full bg-neutral-800 rounded-full h-1">
                            <div className="bg-blue-500 h-1 rounded-full transition-all" style={{ width: `${task.progress}%` }}></div>
                          </div>
                          <span className="text-[10px] text-neutral-500 mt-1 block">{task.progress}%</span>
                        </div>
                      )}
                      <div className="mt-2 flex items-center justify-between text-[10px] text-neutral-500">
                        <span>{formatTime(task.created_at)}</span>
                        <span className="flex items-center gap-1 hover:text-neutral-300"><Terminal size={10}/> 日志</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 日志视图 */}
      <div className={`absolute inset-0 bg-[#0a0a0b] flex flex-col transition-all duration-300 ${selectedTask ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0 pointer-events-none'}`}>
        <div className="px-4 py-2.5 border-b border-neutral-800 bg-neutral-900/50 flex items-center gap-3 shrink-0">
          <button 
            onClick={() => setSelectedTask(null)} 
            className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded flex items-center gap-1.5 text-sm transition-colors"
          >
            <X size={14} /> 返回看板
          </button>
          <div className="h-4 w-px bg-neutral-800"></div>
          <span className="text-xs font-mono text-neutral-400">Task: {selectedTask?.slice(0, 12)}...</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">
            {tasks.find(t => t.task_id === selectedTask)?.status || 'LOADING'}
          </span>
        </div>
        
        <div className="flex-1 p-4 overflow-y-auto">
          {!selectedTask ? (
            <div className="text-neutral-600 text-center mt-20">选择任务查看日志...</div>
          ) : logs.length === 0 ? (
            <div className="text-neutral-600 text-center mt-20 flex items-center justify-center gap-2">
              <Loader2 size={16} className="animate-spin" /> 等待日志输出...
            </div>
          ) : (
            <pre className="font-mono text-xs text-green-400/90 leading-relaxed whitespace-pre-wrap">
              {logs.map((log, i) => (
                <div key={i} className="hover:bg-white/5 px-1 py-0.5 rounded">{log}</div>
              ))}
              <span className="animate-pulse inline-block w-2 h-3 bg-green-500 ml-1 align-middle"></span>
              <div ref={terminalEndRef} />
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
