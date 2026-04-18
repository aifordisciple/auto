"use client";

/**
 * PackageManager - 用户包管理组件
 *
 * 核心功能：
 * 1. 显示用户已安装的包列表（Python/R）
 * 2. 安装新包（支持指定版本）
 * 3. 删除已安装的包
 * 4. 显示配额信息（已用空间、剩余空间）
 * 5. 搜索可安装的包
 *
 * 设计理念：
 * - 用户包独立存储，不污染系统环境
 * - 完整的安装日志和审计追踪
 * - 配额管理防止滥用
 */

import { useState, useEffect, useCallback } from 'react';
import { useUIStore } from "@/store/useUIStore";
import {
  X, Package, Search, Trash2, Download, AlertCircle,
  CheckCircle, Clock, HardDrive, Box, FileCode
} from "lucide-react";
import { BASE_URL } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

type PackageLanguage = 'python' | 'r';
type PackageStatus = 'PENDING' | 'INSTALLED' | 'FAILED' | 'REMOVED';

interface UserPackage {
  id: number;
  package_id: string;
  name: string;
  version: string | null;
  language: PackageLanguage;
  status: PackageStatus;
  size_bytes: number;
  description: string | null;
  created_at: string;
  updated_at: string;
  error_message?: string;
}

interface PackageQuota {
  user_id: number;
  total_packages: number;
  total_size_bytes: number;
  max_packages: number;
  max_size_bytes: number;
  available_size_bytes: number;
}

interface InstallRequest {
  name: string;
  version?: string;
  language: PackageLanguage;
}

// ==========================================
// 辅助函数
// ==========================================

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function getStatusIcon(status: PackageStatus) {
  switch (status) {
    case 'INSTALLED':
      return <CheckCircle className="w-4 h-4 text-green-500" />;
    case 'PENDING':
      return <Clock className="w-4 h-4 text-yellow-500 animate-spin" />;
    case 'FAILED':
      return <AlertCircle className="w-4 h-4 text-red-500" />;
    default:
      return <Package className="w-4 h-4 text-gray-500" />;
  }
}

function getStatusColor(status: PackageStatus): string {
  switch (status) {
    case 'INSTALLED':
      return 'bg-green-500/20 text-green-400';
    case 'PENDING':
      return 'bg-yellow-500/20 text-yellow-400';
    case 'FAILED':
      return 'bg-red-500/20 text-red-400';
    default:
      return 'bg-gray-500/20 text-gray-400';
  }
}

// ==========================================
// 主组件
// ==========================================

export function PackageManager() {
  const { isPackageManagerOpen, closeAllOverlays } = useUIStore();

  // 状态
  const [activeTab, setActiveTab] = useState<PackageLanguage>('python');
  const [packages, setPackages] = useState<UserPackage[]>([]);
  const [quota, setQuota] = useState<PackageQuota | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [installName, setInstallName] = useState('');
  const [installVersion, setInstallVersion] = useState('');
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // ==========================================
  // 数据加载
  // ==========================================

  const fetchPackages = useCallback(async () => {
    if (!isPackageManagerOpen) return;

    setLoading(true);
    try {
      const response = await fetch(`${BASE_URL}/api/packages/list?language=${activeTab}`, {
        credentials: 'include',
      });

      if (!response.ok) throw new Error('获取包列表失败');

      const data = await response.json();
      setPackages(data.packages || []);
      setQuota(data.quota);
    } catch (err) {
      console.error('[PackageManager] 获取包列表失败:', err);
      setError('获取包列表失败');
    } finally {
      setLoading(false);
    }
  }, [isPackageManagerOpen, activeTab]);

  useEffect(() => {
    fetchPackages();
  }, [fetchPackages]);

  // ==========================================
  // 安装包
  // ==========================================

  const handleInstall = async () => {
    if (!installName.trim()) {
      setError('请输入包名称');
      return;
    }

    setInstalling(true);
    setError(null);
    setSuccess(null);

    try {
      const payload: InstallRequest = {
        name: installName.trim(),
        language: activeTab,
      };

      if (installVersion.trim()) {
        payload.version = installVersion.trim();
      }

      const response = await fetch(`${BASE_URL}/api/packages/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (data.success) {
        setSuccess(`包 ${installName} 安装成功`);
        setInstallName('');
        setInstallVersion('');
        fetchPackages();
      } else {
        setError(data.error || data.message || '安装失败');
      }
    } catch (err) {
      console.error('[PackageManager] 安装失败:', err);
      setError('安装请求失败');
    } finally {
      setInstalling(false);
    }
  };

  // ==========================================
  // 删除包
  // ==========================================

  const handleRemove = async (pkg: UserPackage) => {
    if (!confirm(`确定要删除包 ${pkg.name} 吗？`)) return;

    try {
      const response = await fetch(`${BASE_URL}/api/packages/${pkg.id}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      const data = await response.json();

      if (data.success) {
        setSuccess(`包 ${pkg.name} 已删除`);
        fetchPackages();
      } else {
        setError(data.message || '删除失败');
      }
    } catch (err) {
      console.error('[PackageManager] 删除失败:', err);
      setError('删除请求失败');
    }
  };

  // ==========================================
  // 清除提示
  // ==========================================

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [success]);

  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  // ==========================================
  // 过滤包列表
  // ==========================================

  const filteredPackages = packages.filter(pkg =>
    pkg.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // ==========================================
  // 渲染
  // ==========================================

  if (!isPackageManagerOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-4xl max-h-[80vh] flex flex-col shadow-2xl">

        {/* ========== 头部 ========== */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <Package className="w-6 h-6 text-blue-400" />
            <h2 className="text-xl font-semibold text-white">包管理器</h2>
          </div>
          <button
            onClick={closeAllOverlays}
            className="p-1 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* ========== 配额信息 ========== */}
        {quota && (
          <div className="px-4 py-3 bg-gray-800/50 border-b border-gray-700">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-4">
                <span className="text-gray-400">
                  已安装: <span className="text-white font-medium">{quota.total_packages}</span> / {quota.max_packages} 个包
                </span>
                <span className="text-gray-400">
                  已用空间: <span className="text-white font-medium">{formatSize(quota.total_size_bytes)}</span> / {formatSize(quota.max_size_bytes)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <HardDrive className="w-4 h-4 text-gray-400" />
                <span className="text-green-400">剩余 {formatSize(quota.available_size_bytes)}</span>
              </div>
            </div>
            {/* 进度条 */}
            <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 transition-all duration-300"
                style={{ width: `${(quota.total_size_bytes / quota.max_size_bytes) * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* ========== 提示信息 ========== */}
        {error && (
          <div className="mx-4 mt-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="mx-4 mt-4 p-3 bg-green-500/20 border border-green-500/30 rounded-lg flex items-center gap-2 text-green-400">
            <CheckCircle className="w-5 h-5 flex-shrink-0" />
            <span>{success}</span>
          </div>
        )}

        {/* ========== Tab 切换 ========== */}
        <div className="flex border-b border-gray-700">
          <button
            onClick={() => setActiveTab('python')}
            className={`flex items-center gap-2 px-6 py-3 text-sm font-medium transition-colors ${activeTab === 'python'
                ? 'text-blue-400 border-b-2 border-blue-400 bg-blue-500/10'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
          >
            <FileCode className="w-4 h-4" />
            Python
          </button>
          <button
            onClick={() => setActiveTab('r')}
            className={`flex items-center gap-2 px-6 py-3 text-sm font-medium transition-colors ${activeTab === 'r'
                ? 'text-blue-400 border-b-2 border-blue-400 bg-blue-500/10'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
          >
            <Box className="w-4 h-4" />
            R
          </button>
        </div>

        {/* ========== 安装区域 ========== */}
        <div className="p-4 border-b border-gray-700 bg-gray-800/30">
          <div className="flex gap-2">
            <input
              type="text"
              value={installName}
              onChange={(e) => setInstallName(e.target.value)}
              placeholder={`输入 ${activeTab === 'python' ? 'pip' : 'CRAN'} 包名称...`}
              className="flex-1 px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            <input
              type="text"
              value={installVersion}
              onChange={(e) => setInstallVersion(e.target.value)}
              placeholder="版本 (可选)"
              className="w-32 px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={handleInstall}
              disabled={installing || !installName.trim()}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors flex items-center gap-2"
            >
              {installing ? (
                <>
                  <Clock className="w-4 h-4 animate-spin" />
                  安装中...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  安装
                </>
              )}
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            提示：安装可能需要几分钟时间。部分包可能需要系统依赖。
          </p>
        </div>

        {/* ========== 搜索框 ========== */}
        <div className="p-4 border-b border-gray-700">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索已安装的包..."
              className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* ========== 包列表 ========== */}
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Clock className="w-8 h-8 text-blue-400 animate-spin" />
            </div>
          ) : filteredPackages.length === 0 ? (
            <div className="text-center py-12">
              <Package className="w-12 h-12 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400">
                {searchQuery ? '未找到匹配的包' : `暂无已安装的 ${activeTab.toUpperCase()} 包`}
              </p>
              <p className="text-gray-500 text-sm mt-2">
                在上方输入包名称进行安装
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredPackages.map((pkg) => (
                <div
                  key={pkg.id}
                  className="flex items-center justify-between p-4 bg-gray-800/50 border border-gray-700 rounded-lg hover:bg-gray-800 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    {getStatusIcon(pkg.status)}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-white font-medium">{pkg.name}</span>
                        {pkg.version && (
                          <span className="text-xs text-gray-500 bg-gray-700 px-2 py-0.5 rounded">
                            v{pkg.version}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
                        <span className={`px-2 py-0.5 rounded ${getStatusColor(pkg.status)}`}>
                          {pkg.status}
                        </span>
                        <span>{formatSize(pkg.size_bytes)}</span>
                        <span>•</span>
                        <span>{new Date(pkg.created_at).toLocaleDateString()}</span>
                      </div>
                      {pkg.error_message && (
                        <p className="mt-1 text-xs text-red-400 truncate max-w-md">
                          {pkg.error_message}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {pkg.status === 'INSTALLED' && (
                      <button
                        onClick={() => handleRemove(pkg)}
                        className="p-2 hover:bg-red-500/20 text-gray-400 hover:text-red-400 rounded-lg transition-colors"
                        title="删除包"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                    {pkg.status === 'FAILED' && (
                      <button
                        onClick={() => {
                          setInstallName(pkg.name);
                          setInstallVersion(pkg.version || '');
                        }}
                        className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
                      >
                        重试
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ========== 底部信息 ========== */}
        <div className="p-4 border-t border-gray-700 bg-gray-800/30">
          <p className="text-xs text-gray-500 text-center">
            用户包安装在独立目录中，不会影响系统环境。安装的包在所有分析中可用。
          </p>
        </div>
      </div>
    </div>
  );
}