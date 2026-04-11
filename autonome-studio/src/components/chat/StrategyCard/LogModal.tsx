/**
 * 日志弹窗组件
 *
 * 通过 SSE 流式获取任务日志并显示
 * 支持自动滚动、错误高亮等功能
 */
"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Terminal, XCircle, Loader2 } from "lucide-react";
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { BASE_URL } from "@/lib/api";

interface LogModalProps {
  /** 任务 ID */
  taskId: string;
  /** 是否打开 */
  isOpen: boolean;
  /** 关闭回调 */
  onClose: () => void;
}

/**
 * 日志弹窗组件 - 显示任务执行日志
 */
export const LogModal: React.FC<LogModalProps> = ({ taskId, isOpen, onClose }) => {
  const [logs, setLogs] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const logEndRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    setLogs([]);
    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const fetchLogs = async () => {
      try {
        await fetchEventSource(`${BASE_URL}/api/tasks/${taskId}/logs/stream`, {
          method: 'GET',
          signal: controller.signal,
          onmessage(event) {
            if (event.event === 'log') {
              try {
                const data = JSON.parse(event.data);
                setLogs(prev => [...prev, data.text]);
              } catch (e) {
                // 忽略解析错误
              }
            } else if (event.event === 'done') {
              setIsLoading(false);
              controller.abort();
            }
          },
          onerror(err) {
            console.error('Log stream error:', err);
            setIsLoading(false);
          }
        });
      } catch (e) {
        setIsLoading(false);
      }
    };

    fetchLogs();

    return () => {
      controller.abort();
    };
  }, [taskId, isOpen]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          className="bg-white dark:bg-[#1a1a1c] border border-gray-200 dark:border-neutral-700 rounded-xl w-full max-w-3xl max-h-[80vh] flex flex-col shadow-2xl"
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900/50">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-green-500" />
              <span className="font-medium text-gray-900 dark:text-white">任务日志</span>
              <code className="text-xs bg-gray-200 dark:bg-neutral-800 px-2 py-0.5 rounded text-blue-600 dark:text-blue-400">{taskId.slice(0, 8)}</code>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
            >
              <XCircle className="w-5 h-5" />
            </button>
          </div>

          {/* Log Content */}
          <div className="flex-1 overflow-y-auto p-4 bg-gray-900 dark:bg-neutral-950 font-mono text-xs">
            {isLoading && logs.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-gray-500">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                加载日志中...
              </div>
            ) : logs.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-gray-500">
                暂无日志
              </div>
            ) : (
              <div className="space-y-0.5">
                {logs.map((log, i) => (
                  <div
                    key={i}
                    className={`py-0.5 px-1 hover:bg-white/5 rounded ${
                      log.includes('ERROR') || log.includes('❌') || log.includes('💥')
                        ? 'text-red-400'
                        : log.includes('WARNING') || log.includes('⚠️')
                        ? 'text-yellow-400'
                        : log.includes('✅') || log.includes('🎉') || log.includes('SUCCESS')
                        ? 'text-green-400'
                        : 'text-green-300/80'
                    }`}
                  >
                    {log}
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 border-t border-gray-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900/50">
            <div className="text-xs text-gray-500 dark:text-neutral-400">
              共 {logs.length} 条日志
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default LogModal;