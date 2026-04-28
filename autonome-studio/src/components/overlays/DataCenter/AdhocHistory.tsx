/**
 * 即席分析历史列表组件
 *
 * 展示当前项目下所有即席分析执行记录，支持回溯、重执行、对比和删除。
 * 作为 DataCenter 侧边栏的一个 Tab 使用。
 */
'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { RefreshCw, Trash2, Eye, Play, ChevronRight, X, Loader2, FileText, CheckCircle2, XCircle } from 'lucide-react';

/**
 * 历史记录数据结构（与后端 API 返回一致）
 */
interface AdhocHistoryItem {
  id: number;
  message_id: string;
  strategy: string;
  code_language: string;
  code_snapshot: string;
  parameters: Record<string, unknown>;
  output_dir: string | null;
  output_files: string[];
  status: 'running' | 'success' | 'failed';
  output_text: string | null;
  error_text: string | null;
  created_at: string | null;
  completed_at: string | null;
}

interface AdhocHistoryResponse {
  items: AdhocHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

interface AdhocHistoryProps {
  /** 当前项目 ID */
  projectId: string;
  /** 高亮数据中心路径回调 */
  onNavigateToOutput?: (outputDir: string) => void;
  /** 重新执行回调 */
  onRerun?: (item: AdhocHistoryItem) => void;
  /** 是否可见 */
  visible?: boolean;
  /** 关闭回调 */
  onClose?: () => void;
}

const PAGE_SIZE = 20;

/**
 * 即席分析历史列表组件
 */
const AdhocHistory: React.FC<AdhocHistoryProps> = ({
  projectId,
  onNavigateToOutput,
  onRerun,
  visible = true,
  onClose,
}) => {
  const [items, setItems] = useState<AdhocHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  // 重新执行状态
  const [rerunningId, setRerunningId] = useState<number | null>(null);
  const [rerunLogs, setRerunLogs] = useState<string[]>([]);
  const [rerunProgress, setRerunProgress] = useState<{ step: number; total: number; message: string; percent: number } | null>(null);
  const [rerunResult, setRerunResult] = useState<{ status: string; output_files: string[] } | null>(null);
  const rerunAbortRef = useRef<AbortController | null>(null);

  /** 加载历史列表 */
  const loadHistory = useCallback(async (newOffset = 0) => {
    if (!projectId) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        project_id: projectId,
        limit: String(PAGE_SIZE),
        offset: String(newOffset),
      });
      const res = await fetch(`/api/chat/adhoc/history?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AdhocHistoryResponse = await res.json();
      setItems(data.items);
      setTotal(data.total);
      setOffset(newOffset);
    } catch (err) {
      console.error('加载即席分析历史失败:', err);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (visible) {
      loadHistory(0);
    }
  }, [visible, loadHistory]);

  /** 删除单条记录 */
  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (deleting) return;
    setDeleting(id);
    try {
      const res = await fetch(`/api/chat/adhoc/history/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setItems(prev => prev.filter(item => item.id !== id));
      setTotal(prev => prev - 1);
    } catch (err) {
      console.error('删除历史记录失败:', err);
    } finally {
      setDeleting(null);
    }
  };

  /** 重新执行历史记录 */
  const handleRerun = async (item: AdhocHistoryItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (rerunningId) return;

    setRerunningId(item.id);
    setExpandedId(item.id);
    setRerunLogs([]);
    setRerunProgress(null);
    setRerunResult(null);

    try {
      // Step 1: 从 DB 恢复策略包到 Redis
      const rerunRes = await fetch(`/api/chat/adhoc/rerun/${item.id}`, { method: 'POST' });
      if (!rerunRes.ok) {
        const errData = await rerunRes.json().catch(() => ({}));
        throw new Error((errData as { detail?: string }).detail || `HTTP ${rerunRes.status}`);
      }
      const rerunData = await rerunRes.json();
      const messageId = rerunData.message_id;

      // Step 2: SSE 流式执行
      const abortController = new AbortController();
      rerunAbortRef.current = abortController;

      const execRes = await fetch('/api/chat/adhoc/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message_id: messageId,
          payload: {
            parameters: item.parameters || {},
            code_snapshot: item.code_snapshot,
          },
        }),
        signal: abortController.signal,
      });

      if (!execRes.ok) {
        throw new Error(`执行请求失败: HTTP ${execRes.status}`);
      }

      // Step 3: 读取 SSE 流
      const reader = execRes.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === 'progress') {
              setRerunProgress({ step: data.step, total: data.total, message: data.message, percent: data.percent });
            } else if (data.type === 'log') {
              setRerunLogs(prev => [...prev, `[${data.category}] ${data.line}`]);
            } else if (data.type === 'result') {
              setRerunResult({ status: data.status, output_files: data.output_files?.map((f: { name: string }) => f.name) || [] });
            } else if (data.type === 'done') {
              break;
            }
          } catch {
            // skip non-JSON lines
          }
        }
      }

      // 刷新历史列表
      loadHistory();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知错误';
      if (err instanceof DOMException && err.name === 'AbortError') {
        setRerunLogs(prev => [...prev, '[系统] 执行已取消']);
      } else {
        setRerunLogs(prev => [...prev, `[错误] ${msg}`]);
        setRerunResult({ status: 'failed', output_files: [] });
      }
    } finally {
      setRerunningId(null);
    }
  };

  /** 格式化时间 */
  const formatTime = (isoStr: string | null) => {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const m = String(d.getMinutes()).padStart(2, '0');
    return `${month}-${day} ${h}:${m}`;
  };

  /** 截断文本 */
  const truncate = (text: string, max: number) =>
    text.length > max ? text.slice(0, max) + '...' : text;

  /** 过滤后的列表 */
  const filteredItems = statusFilter === 'all'
    ? items
    : items.filter(item => item.status === statusFilter);

  /** 分页 */
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  if (!visible) return null;

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="shrink-0 px-4 py-3 flex items-center justify-between border-b border-neutral-800">
        <h3 className="text-sm font-semibold text-neutral-200 flex items-center gap-2">
          <FileText size={16} className="text-purple-400" />
          即席分析历史
          {total > 0 && (
            <span className="text-[11px] text-neutral-500 font-normal">({total})</span>
          )}
        </h3>
        <div className="flex items-center gap-1">
          <button
            onClick={() => loadHistory(0)}
            disabled={loading}
            className="p-2 min-h-[36px] min-w-[36px] text-neutral-500 hover:text-neutral-200 hover:bg-neutral-800 rounded-lg transition-colors"
            title="刷新"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 min-h-[36px] min-w-[36px] text-neutral-500 hover:text-neutral-200 hover:bg-neutral-800 rounded-lg transition-colors"
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* 状态筛选 */}
      <div className="shrink-0 px-4 py-2 flex items-center gap-2 border-b border-neutral-800/50">
        {(['all', 'success', 'failed'] as const).map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`text-[11px] px-2.5 py-1 rounded-full transition-colors ${
              statusFilter === s
                ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                : 'text-neutral-500 hover:text-neutral-300 border border-transparent'
            }`}
          >
            {s === 'all' ? '全部' : s === 'success' ? '成功' : '失败'}
          </button>
        ))}
      </div>

      {/* 列表 */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {loading && items.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-neutral-500">
            <Loader2 size={20} className="animate-spin mr-2" />
            <span className="text-sm">加载中...</span>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-neutral-600 gap-2">
            <FileText size={32} className="opacity-20" />
            <p className="text-sm">暂无即席分析历史</p>
            <p className="text-[11px]">执行即席分析后会自动记录在此处</p>
          </div>
        ) : (
          <div className="py-1">
            {filteredItems.map(item => (
              <div key={item.id} className="border-b border-neutral-800/30 last:border-b-0">
                {/* 主行 */}
                <div
                  className="flex items-center gap-2 px-4 py-2.5 hover:bg-neutral-800/50 cursor-pointer transition-colors group"
                  onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                >
                  {/* 状态图标 */}
                  {item.status === 'success' ? (
                    <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                  ) : item.status === 'failed' ? (
                    <XCircle size={14} className="text-red-400 shrink-0" />
                  ) : (
                    <Loader2 size={14} className="text-yellow-400 animate-spin shrink-0" />
                  )}

                  {/* 策略描述 */}
                  <span className="flex-1 text-sm text-neutral-300 truncate">
                    {truncate(item.strategy, 50)}
                  </span>

                  {/* 语言和文件数标签 */}
                  <span className="text-[10px] px-1.5 py-0.5 bg-neutral-800 rounded text-neutral-500 font-mono shrink-0">
                    {item.code_language}
                  </span>
                  {item.output_files.length > 0 && (
                    <span className="text-[10px] text-neutral-500 shrink-0">
                      {item.output_files.length} 文件
                    </span>
                  )}

                  {/* 时间 */}
                  <span className="text-[10px] text-neutral-600 shrink-0 w-16 text-right">
                    {formatTime(item.created_at)}
                  </span>

                  {/* 操作按钮 */}
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                    {item.output_dir && onNavigateToOutput && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onNavigateToOutput(item.output_dir!); }}
                        className="p-1.5 min-h-[32px] min-w-[32px] text-neutral-500 hover:text-emerald-400 hover:bg-emerald-500/10 rounded transition-colors"
                        title="查看输出"
                      >
                        <Eye size={13} />
                      </button>
                    )}
                    <button
                      onClick={(e) => handleRerun(item, e)}
                      disabled={rerunningId === item.id}
                      className="p-1.5 min-h-[32px] min-w-[32px] text-neutral-500 hover:text-blue-400 hover:bg-blue-500/10 rounded transition-colors disabled:opacity-50"
                      title="重新执行"
                    >
                      {rerunningId === item.id ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Play size={13} />
                      )}
                    </button>
                    <button
                      onClick={(e) => handleDelete(item.id, e)}
                      disabled={deleting === item.id}
                      className="p-1.5 min-h-[32px] min-w-[32px] text-neutral-500 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors disabled:opacity-50"
                      title="删除"
                    >
                      {deleting === item.id ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Trash2 size={13} />
                      )}
                    </button>
                  </div>

                  {/* 展开箭头 */}
                  <ChevronRight
                    size={14}
                    className={`text-neutral-600 shrink-0 transition-transform ${expandedId === item.id ? 'rotate-90' : ''}`}
                  />
                </div>

                {/* 展开详情 */}
                {expandedId === item.id && (
                  <div className="px-4 pb-3 pl-10 space-y-2">
                    {/* 参数列表 */}
                    {Object.keys(item.parameters).length > 0 && (
                      <div>
                        <span className="text-[10px] text-neutral-600 uppercase tracking-wider">参数</span>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {Object.entries(item.parameters).map(([k, v]) => (
                            <span
                              key={k}
                              className="text-[10px] px-2 py-0.5 bg-neutral-800/50 rounded text-neutral-400 border border-neutral-700/30"
                            >
                              {k}: {String(v)}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 输出文件列表 */}
                    {item.output_files.length > 0 && (
                      <div>
                        <span className="text-[10px] text-neutral-600 uppercase tracking-wider">输出文件</span>
                        <div className="mt-1 space-y-0.5">
                          {item.output_files.map((f, i) => (
                            <div key={i} className="text-[11px] text-neutral-400 font-mono">
                              {f}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 代码快照预览 */}
                    {item.code_snapshot && (
                      <div>
                        <span className="text-[10px] text-neutral-600 uppercase tracking-wider">代码快照</span>
                        <pre className="mt-1 text-[10px] text-neutral-500 bg-neutral-900 rounded p-2 max-h-32 overflow-y-auto font-mono leading-relaxed">
                          {item.code_snapshot.slice(0, 500)}
                          {item.code_snapshot.length > 500 && '\n...'}
                        </pre>
                      </div>
                    )}

                    {/* 错误信息 */}
                    {item.status === 'failed' && item.error_text && (
                      <div>
                        <span className="text-[10px] text-red-500 uppercase tracking-wider">错误信息</span>
                        <pre className="mt-1 text-[10px] text-red-400/70 bg-red-500/5 rounded p-2 max-h-24 overflow-y-auto font-mono leading-relaxed border border-red-500/10">
                          {item.error_text.slice(0, 300)}
                        </pre>
                      </div>
                    )}

                    {/* 重新执行进度（仅当正在重新执行此条记录时显示） */}
                    {rerunningId === item.id && (
                      <div className="border-t border-neutral-700/50 pt-2 mt-2">
                        <span className="text-[10px] text-indigo-400 uppercase tracking-wider flex items-center gap-1">
                          <Loader2 size={10} className="animate-spin" />
                          重新执行中...
                        </span>
                        {/* 进度条 */}
                        {rerunProgress && (
                          <div className="mt-2">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-[10px] text-neutral-300">
                                [{rerunProgress.step}/{rerunProgress.total}] {rerunProgress.message}
                              </span>
                              <span className="text-[9px] text-neutral-500">{rerunProgress.percent}%</span>
                            </div>
                            <div className="w-full bg-neutral-700 rounded-full h-1">
                              <div
                                className="bg-indigo-500 h-1 rounded-full transition-all duration-500"
                                style={{ width: `${rerunProgress.percent}%` }}
                              />
                            </div>
                          </div>
                        )}
                        {/* 日志 */}
                        {rerunLogs.length > 0 && (
                          <pre className="mt-2 text-[9px] text-neutral-400 bg-neutral-900 rounded p-2 max-h-32 overflow-y-auto font-mono leading-relaxed">
                            {rerunLogs.slice(-30).join('\n')}
                          </pre>
                        )}
                        {/* 结果 */}
                        {rerunResult && (
                          <div className={`mt-2 text-[10px] px-2 py-1 rounded ${
                            rerunResult.status === 'success'
                              ? 'text-emerald-400 bg-emerald-500/10'
                              : 'text-red-400 bg-red-500/10'
                          }`}>
                            {rerunResult.status === 'success'
                              ? `✅ 执行成功 — ${rerunResult.output_files.length} 个输出文件`
                              : '❌ 执行失败'}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="shrink-0 px-4 py-2 border-t border-neutral-800 flex items-center justify-between">
          <span className="text-[10px] text-neutral-600">
            {currentPage} / {totalPages} 页
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => loadHistory(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0 || loading}
              className="px-2 py-1 text-[10px] text-neutral-500 hover:text-neutral-200 hover:bg-neutral-800 rounded transition-colors disabled:opacity-30"
            >
              上一页
            </button>
            <button
              onClick={() => loadHistory(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total || loading}
              className="px-2 py-1 text-[10px] text-neutral-500 hover:text-neutral-200 hover:bg-neutral-800 rounded transition-colors disabled:opacity-30"
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdhocHistory;
