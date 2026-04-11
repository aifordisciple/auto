"use client";

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { X, UploadCloud, Loader2, Pause, Play, Trash2, CheckCircle, AlertCircle, FileText } from "lucide-react";
import { fetchAPI } from "@/lib/api";

// 默认分段大小：5MB
const DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024;

interface UploadTask {
  id: string;
  file: File;
  targetPath: string;
  uploadId: string | null;
  totalChunks: number;
  uploadedChunks: number[];
  status: 'pending' | 'uploading' | 'paused' | 'completed' | 'error';
  error: string | null;
  startTime: number;
}

interface UploadManagerProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  targetPath: string;
  files: File[];
  onComplete: () => void;
}

export function UploadManager({ isOpen, onClose, projectId, targetPath, files, onComplete }: UploadManagerProps) {
  const [tasks, setTasks] = useState<UploadTask[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());

  // 初始化上传任务
  useEffect(() => {
    if (isOpen && files.length > 0) {
      const newTasks: UploadTask[] = files.map(file => ({
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        file,
        targetPath,
        uploadId: null,
        totalChunks: Math.ceil(file.size / DEFAULT_CHUNK_SIZE),
        uploadedChunks: [],
        status: 'pending',
        error: null,
        startTime: Date.now()
      }));
      setTasks(newTasks);
    }
  }, [isOpen, files, targetPath]);

  // 上传单个分段
  const uploadChunk = async (task: UploadTask, chunkIndex: number, uploadId: string, controller: AbortController) => {
    const start = chunkIndex * DEFAULT_CHUNK_SIZE;
    const end = Math.min(start + DEFAULT_CHUNK_SIZE, task.file.size);
    const chunkBlob = task.file.slice(start, end);

    const formData = new FormData();
    formData.append("upload_id", uploadId);
    formData.append("chunk_index", chunkIndex.toString());
    formData.append("chunk", chunkBlob, `${task.file.name}.part${chunkIndex}`);

    const token = localStorage.getItem('autonome_access_token');
    const baseUrl = typeof window !== 'undefined' ? `http://${window.location.hostname}:8000` : 'http://localhost:8000';

    const response = await fetch(`${baseUrl}/api/projects/${projectId}/uploads/chunk`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData,
      signal: controller.signal
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || '分段上传失败');
    }

    return response.json();
  };

  // 初始化上传会话
  const initUploadSession = async (task: UploadTask) => {
    const result = await fetchAPI(`/api/projects/${projectId}/uploads/init`, {
      method: 'POST',
      body: JSON.stringify({
        filename: task.file.name,
        file_size: task.file.size,
        chunk_size: DEFAULT_CHUNK_SIZE,
        target_path: task.targetPath
      })
    });

    if (result.status !== 'success') {
      throw new Error(result.message || '初始化上传失败');
    }

    return result;
  };

  // 完成上传
  const completeUpload = async (uploadId: string) => {
    const formData = new FormData();
    formData.append("upload_id", uploadId);

    return fetchAPI(`/api/projects/${projectId}/uploads/complete`, {
      method: 'POST',
      body: formData
    });
  };

  // 处理单个任务的上传
  const processTask = async (task: UploadTask) => {
    const controller = new AbortController();
    abortControllersRef.current.set(task.id, controller);

    try {
      // 1. 初始化上传会话
      const initResult = await initUploadSession(task);
      const uploadId = initResult.upload_id;

      setTasks(prev => prev.map(t =>
        t.id === task.id ? { ...t, uploadId, status: 'uploading' } : t
      ));

      // 2. 上传所有分段
      for (let i = 0; i < initResult.total_chunks; i++) {
        if (controller.signal.aborted) {
          throw new Error('上传已暂停');
        }

        // 检查是否已上传（断点续传）
        setTasks(prev => {
          const current = prev.find(t => t.id === task.id);
          if (current && current.uploadedChunks.includes(i)) {
            return prev;
          }
          return prev;
        });

        await uploadChunk({ ...task, uploadId } as UploadTask, i, uploadId, controller);

        setTasks(prev => prev.map(t =>
          t.id === task.id ? {
            ...t,
            uploadedChunks: [...t.uploadedChunks, i],
            status: 'uploading'
          } : t
        ));
      }

      // 3. 完成上传
      await completeUpload(uploadId);

      setTasks(prev => prev.map(t =>
        t.id === task.id ? { ...t, status: 'completed' } : t
      ));

    } catch (error: any) {
      if (error.name === 'AbortError') {
        setTasks(prev => prev.map(t =>
          t.id === task.id ? { ...t, status: 'paused' } : t
        ));
      } else {
        setTasks(prev => prev.map(t =>
          t.id === task.id ? { ...t, status: 'error', error: error.message } : t
        ));
      }
    }
  };

  // 开始/继续上传
  const startUpload = async () => {
    setIsProcessing(true);

    for (const task of tasks) {
      if (task.status === 'pending' || task.status === 'paused' || task.status === 'error') {
        await processTask(task);
      }
    }

    setIsProcessing(false);
  };

  // 监听任务状态变化，全部完成时触发回调
  useEffect(() => {
    if (tasks.length > 0 && tasks.every(t => t.status === 'completed')) {
      onComplete();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks]);

  // 暂停上传
  const pauseTask = (taskId: string) => {
    const controller = abortControllersRef.current.get(taskId);
    if (controller) {
      controller.abort();
    }
  };

  // 继续上传
  const resumeTask = async (task: UploadTask) => {
    if (!task.uploadId) {
      await processTask(task);
    } else {
      // 获取上传状态
      try {
        const status = await fetchAPI(`/api/projects/${projectId}/uploads/${task.uploadId}/status`);
        if (status.status === 'success') {
          setTasks(prev => prev.map(t =>
            t.id === task.id ? {
              ...t,
              uploadedChunks: status.uploaded_chunks,
              status: 'uploading'
            } : t
          ));
          await processTask({ ...task, uploadedChunks: status.uploaded_chunks });
        }
      } catch (e) {
        await processTask(task);
      }
    }
  };

  // 取消上传
  const cancelTask = async (task: UploadTask) => {
    if (task.uploadId) {
      try {
        await fetchAPI(`/api/projects/${projectId}/uploads/${task.uploadId}`, { method: 'DELETE' });
      } catch (e) {
        // 忽略错误
      }
    }

    const controller = abortControllersRef.current.get(task.id);
    if (controller) {
      controller.abort();
    }

    setTasks(prev => prev.filter(t => t.id !== task.id));
  };

  // 格式化进度
  const getProgress = (task: UploadTask) => {
    return Math.round((task.uploadedChunks.length / task.totalChunks) * 100);
  };

  // 格式化文件大小
  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  // 全部完成检查
  const allCompleted = tasks.length > 0 && tasks.every(t => t.status === 'completed');
  const hasUploading = tasks.some(t => t.status === 'uploading');

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#1a1a1c] border border-neutral-700 rounded-xl w-full max-w-2xl max-h-[80vh] shadow-2xl flex flex-col animate-in zoom-in-95 duration-200">

        {/* Header */}
        <div className="h-14 shrink-0 border-b border-neutral-800 px-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/20 border border-purple-500/30 rounded-lg text-purple-400">
              <UploadCloud size={18} />
            </div>
            <div>
              <h3 className="text-white font-semibold text-sm tracking-wide">上传管理器</h3>
              <p className="text-[10px] text-neutral-500 font-mono">{tasks.length} 个文件 • 目标: {targetPath}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={hasUploading}
            className="p-1.5 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors disabled:opacity-50"
          >
            <X size={18} />
          </button>
        </div>

        {/* Task List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {tasks.map(task => (
            <div key={task.id} className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <FileText size={20} className="text-blue-400 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-neutral-200 truncate font-medium">{task.file.name}</p>
                    <p className="text-xs text-neutral-500 mt-0.5">{formatSize(task.file.size)}</p>

                    {/* Progress Bar */}
                    {task.status !== 'pending' && (
                      <div className="mt-2">
                        <div className="h-1.5 bg-neutral-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-300 ${
                              task.status === 'completed' ? 'bg-green-500' :
                              task.status === 'error' ? 'bg-red-500' :
                              'bg-purple-500'
                            }`}
                            style={{ width: `${getProgress(task)}%` }}
                          />
                        </div>
                        <p className="text-xs text-neutral-500 mt-1">
                          {getProgress(task)}% • {task.uploadedChunks.length}/{task.totalChunks} 分段
                        </p>
                      </div>
                    )}

                    {/* Error Message */}
                    {task.error && (
                      <p className="text-xs text-red-400 mt-2 flex items-center gap-1">
                        <AlertCircle size={12} />
                        {task.error}
                      </p>
                    )}
                  </div>
                </div>

                {/* Status & Actions */}
                <div className="flex items-center gap-2 shrink-0">
                  {task.status === 'pending' && (
                    <span className="text-xs text-neutral-500 bg-neutral-800 px-2 py-1 rounded">等待中</span>
                  )}
                  {task.status === 'uploading' && (
                    <button
                      onClick={() => pauseTask(task.id)}
                      className="p-1.5 text-yellow-400 hover:bg-yellow-500/10 rounded transition-colors"
                      title="暂停"
                    >
                      <Pause size={16} />
                    </button>
                  )}
                  {task.status === 'paused' && (
                    <button
                      onClick={() => resumeTask(task)}
                      className="p-1.5 text-green-400 hover:bg-green-500/10 rounded transition-colors"
                      title="继续"
                    >
                      <Play size={16} />
                    </button>
                  )}
                  {task.status === 'error' && (
                    <button
                      onClick={() => resumeTask(task)}
                      className="p-1.5 text-blue-400 hover:bg-blue-500/10 rounded transition-colors"
                      title="重试"
                    >
                      <RefreshCw size={16} />
                    </button>
                  )}
                  {task.status === 'completed' && (
                    <CheckCircle size={18} className="text-green-500" />
                  )}
                  {task.status !== 'completed' && task.status !== 'uploading' && (
                    <button
                      onClick={() => cancelTask(task)}
                      className="p-1.5 text-red-400 hover:bg-red-500/10 rounded transition-colors"
                      title="取消"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-neutral-800 p-4 flex items-center justify-between bg-neutral-900/40">
          <div className="text-sm text-neutral-500">
            {allCompleted ? (
              <span className="text-green-400">✓ 全部上传完成</span>
            ) : (
              <span>{tasks.filter(t => t.status === 'completed').length}/{tasks.length} 已完成</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              disabled={hasUploading}
              className="px-4 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors disabled:opacity-50"
            >
              {allCompleted ? '关闭' : '取消'}
            </button>
            {!allCompleted && (
              <button
                onClick={startUpload}
                disabled={isProcessing || hasUploading}
                className="flex items-center gap-2 px-5 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white text-sm font-medium rounded-lg transition-colors"
              >
                {isProcessing || hasUploading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    上传中...
                  </>
                ) : (
                  <>
                    <UploadCloud size={16} />
                    开始上传
                  </>
                )}
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}

// Icon import for RefreshCw
import { RefreshCw } from "lucide-react";