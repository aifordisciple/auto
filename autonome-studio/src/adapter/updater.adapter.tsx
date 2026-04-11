/**
 * 自动更新模块
 *
 * 提供桌面端自动更新功能：
 * - 后台检查更新
 * - 下载进度显示
 * - 安装更新
 */

import { useState, useEffect, useCallback } from 'react';
import { isTauri } from './platform';

// ============================================
// 类型定义
// ============================================

export interface UpdateInfo {
  version: string;
  release_notes?: string;
  release_date?: string;
  download_url?: string;
}

export interface UpdateProgress {
  downloaded: number;
  total: number;
  percentage: number;
}

export type UpdateStatus = 'checking' | 'available' | 'downloading' | 'ready' | 'error' | 'none';

// ============================================
// 更新检查 Hook
// ============================================

export function useAutoUpdate() {
  const [status, setStatus] = useState<UpdateStatus>('none');
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [progress, setProgress] = useState<UpdateProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 检查更新
  const checkForUpdates = useCallback(async () => {
    if (!isTauri()) {
      console.warn('自动更新仅在桌面端可用');
      return;
    }

    setStatus('checking');
    setError(null);

    try {
      const { invoke } = await import('@tauri-apps/api/core');
      const result = await invoke<UpdateInfo | null>('check_for_updates');

      if (result) {
        setUpdateInfo(result);
        setStatus('available');
      } else {
        setStatus('none');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '检查更新失败');
      setStatus('error');
    }
  }, []);

  // 下载并安装更新
  const downloadAndInstall = useCallback(async () => {
    if (!isTauri() || !updateInfo) return;

    setStatus('downloading');
    setError(null);

    try {
      const { invoke } = await import('@tauri-apps/api/core');

      // 监听下载进度（事件名与 Rust 后端一致）
      const unlisten = await import('@tauri-apps/api/event').then(({ listen }) =>
        listen<{ downloaded: number; total: number }>('update-progress', (event) => {
          const { downloaded, total } = event.payload;
          setProgress({
            downloaded,
            total,
            percentage: total > 0 ? (downloaded / total) * 100 : 0,
          });
        })
      );

      // 监听安装完成事件
      const unlistenInstalled = await import('@tauri-apps/api/event').then(({ listen }) =>
        listen('update-installed', () => {
          setStatus('ready');
        })
      );

      await invoke('download_and_install_update');
      unlisten();
      unlistenInstalled();
    } catch (err) {
      setError(err instanceof Error ? err.message : '下载更新失败');
      setStatus('error');
    }
  }, [updateInfo]);

  // 启动时自动检查更新
  useEffect(() => {
    if (isTauri()) {
      // 延迟检查，避免影响启动
      const timer = setTimeout(() => {
        checkForUpdates();
      }, 10000);

      return () => clearTimeout(timer);
    }
  }, [checkForUpdates]);

  return {
    status,
    updateInfo,
    progress,
    error,
    checkForUpdates,
    downloadAndInstall,
  };
}

// ============================================
// 更新通知组件
// ============================================

export interface UpdateNotificationProps {
  status: UpdateStatus;
  updateInfo: UpdateInfo | null;
  progress: UpdateProgress | null;
  error: string | null;
  onDownload: () => void;
  onDismiss: () => void;
}

export function UpdateNotification({
  status,
  updateInfo,
  progress,
  error,
  onDownload,
  onDismiss,
}: UpdateNotificationProps) {
  if (status === 'none' || status === 'checking') return null;

  return (
    <div className="fixed bottom-4 right-4 max-w-sm bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50">
      {/* 可用更新 */}
      {status === 'available' && updateInfo && (
        <div className="p-4">
          <div className="flex items-start gap-3">
            <div className="text-2xl">🎉</div>
            <div className="flex-1">
              <h3 className="font-semibold text-white">发现新版本</h3>
              <p className="text-sm text-gray-400 mt-1">
                v{updateInfo.version} 已发布
              </p>
              {updateInfo.release_notes && (
                <p className="text-xs text-gray-500 mt-2 line-clamp-2">
                  {updateInfo.release_notes}
                </p>
              )}
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button
              onClick={onDownload}
              className="flex-1 px-3 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
            >
              立即下载
            </button>
            <button
              onClick={onDismiss}
              className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-colors"
            >
              稍后提醒
            </button>
          </div>
        </div>
      )}

      {/* 下载中 */}
      {status === 'downloading' && progress && (
        <div className="p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="animate-spin text-2xl">⬇️</div>
            <div className="flex-1">
              <h3 className="font-semibold text-white">正在下载更新</h3>
              <p className="text-sm text-gray-400">
                {progress.percentage.toFixed(1)}%
              </p>
            </div>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all"
              style={{ width: `${progress.percentage}%` }}
            />
          </div>
        </div>
      )}

      {/* 准备安装 */}
      {status === 'ready' && (
        <div className="p-4">
          <div className="flex items-center gap-3">
            <div className="text-2xl">✅</div>
            <div className="flex-1">
              <h3 className="font-semibold text-white">更新已就绪</h3>
              <p className="text-sm text-gray-400">
                重启应用以完成安装
              </p>
            </div>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="w-full mt-4 px-3 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-sm font-medium transition-colors"
          >
            重启并安装
          </button>
        </div>
      )}

      {/* 错误 */}
      {status === 'error' && error && (
        <div className="p-4">
          <div className="flex items-center gap-3">
            <div className="text-2xl">❌</div>
            <div className="flex-1">
              <h3 className="font-semibold text-red-400">更新失败</h3>
              <p className="text-sm text-gray-400">{error}</p>
            </div>
          </div>
          <button
            onClick={onDismiss}
            className="w-full mt-4 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-colors"
          >
            关闭
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================
// 获取版本信息
// ============================================

export async function getAppVersion(): Promise<string> {
  if (!isTauri()) {
    return 'web';
  }

  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<string>('get_app_version');
  } catch {
    return 'unknown';
  }
}