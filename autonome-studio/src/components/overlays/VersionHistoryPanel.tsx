"use client";

import React, { useState, useEffect } from 'react';
import { skillForgeApi, SkillAsset } from '@/lib/api';
import {
  GitBranch, Loader2, Clock, RotateCcw, Eye, X, CheckCircle,
  AlertTriangle, Code, FileJson
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface Version {
  id: number;
  version: string;
  change_log: string | null;
  created_at: string;
  created_by: number;
}

interface VersionHistoryPanelProps {
  skill: SkillAsset;
  onClose: () => void;
  onRollback: () => void;
}

export function VersionHistoryPanel({ skill, onClose, onRollback }: VersionHistoryPanelProps) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedVersion, setSelectedVersion] = useState<Version | null>(null);
  const [versionDetail, setVersionDetail] = useState<any | null>(null);
  const [isRollingBack, setIsRollingBack] = useState(false);

  // 加载版本历史
  useEffect(() => {
    loadVersions();
  }, [skill.skill_id]);

  const loadVersions = async () => {
    setIsLoading(true);
    try {
      const response = await skillForgeApi.getVersions(skill.skill_id);
      if (response.status === 'success') {
        setVersions(response.data || []);
      }
    } catch (e) {
      console.error('Failed to load versions:', e);
    } finally {
      setIsLoading(false);
    }
  };

  // 回滚版本
  const handleRollback = async (versionId: number, versionName: string) => {
    if (!confirm(`确定要回滚到版本 ${versionName} 吗？当前内容将被覆盖。`)) {
      return;
    }

    setIsRollingBack(true);
    try {
      await skillForgeApi.rollbackVersion(skill.skill_id, versionId);
      alert(`✅ 已成功回滚到版本 ${versionName}`);
      onRollback();
      onClose();
    } catch (e: any) {
      alert(`回滚失败: ${e.message}`);
    } finally {
      setIsRollingBack(false);
    }
  };

  // 格式化日期
  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-neutral-800 shrink-0">
        <div className="flex items-center gap-2">
          <GitBranch size={18} className="text-blue-500" />
          <div>
            <h2 className="font-semibold text-gray-900 dark:text-white text-sm">版本历史</h2>
            <p className="text-xs text-gray-500 dark:text-neutral-500">{skill.name}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      {/* 当前版本信息 */}
      <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/20 border-b border-blue-100 dark:border-blue-800 shrink-0">
        <div className="flex items-center gap-2">
          <CheckCircle size={14} className="text-blue-500" />
          <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">
            当前版本: v{skill.version}
          </span>
        </div>
      </div>

      {/* 版本列表 */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex items-center justify-center h-32 text-gray-400 dark:text-neutral-500">
            <Loader2 size={24} className="animate-spin" />
          </div>
        ) : versions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-gray-400 dark:text-neutral-500">
            <GitBranch size={32} className="mb-2 opacity-50" />
            <span className="text-sm">暂无版本历史</span>
            <span className="text-xs mt-1">保存技能时会自动创建版本快照</span>
          </div>
        ) : (
          <div className="space-y-3">
            {versions.map((v, index) => {
              const isCurrent = v.version === skill.version;

              return (
                <motion.div
                  key={v.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className={`relative bg-white dark:bg-neutral-800/50 border rounded-lg p-3 transition-all ${
                    isCurrent
                      ? 'border-blue-300 dark:border-blue-600 ring-1 ring-blue-200 dark:ring-blue-800'
                      : 'border-gray-200 dark:border-neutral-700 hover:border-gray-300 dark:hover:border-neutral-600'
                  }`}
                >
                  {/* 版本号和状态 */}
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium text-gray-900 dark:text-white">
                        v{v.version}
                      </span>
                      {isCurrent && (
                        <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400 text-[10px] rounded-full font-medium">
                          当前
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-gray-400 dark:text-neutral-500">
                      #{v.id}
                    </span>
                  </div>

                  {/* 变更日志 */}
                  {v.change_log && (
                    <p className="text-xs text-gray-500 dark:text-neutral-400 mb-2 line-clamp-2">
                      {v.change_log}
                    </p>
                  )}

                  {/* 创建时间 */}
                  <div className="flex items-center gap-1 text-[10px] text-gray-400 dark:text-neutral-500 mb-3">
                    <Clock size={10} />
                    <span>{formatDate(v.created_at)}</span>
                  </div>

                  {/* 操作按钮 */}
                  <div className="flex items-center gap-2 pt-2 border-t border-gray-100 dark:border-neutral-700">
                    <button
                      onClick={() => setSelectedVersion(v)}
                      className="flex items-center gap-1 px-3 py-1 bg-gray-100 dark:bg-neutral-700 hover:bg-gray-200 dark:hover:bg-neutral-600 text-gray-600 dark:text-neutral-300 text-xs rounded transition-colors"
                    >
                      <Eye size={12} />
                      详情
                    </button>
                    {!isCurrent && (
                      <button
                        onClick={() => handleRollback(v.id, v.version)}
                        disabled={isRollingBack}
                        className="flex items-center gap-1 px-3 py-1 bg-orange-100 dark:bg-orange-900/30 hover:bg-orange-200 dark:hover:bg-orange-900/50 text-orange-600 dark:text-orange-400 text-xs rounded transition-colors disabled:opacity-50"
                      >
                        {isRollingBack ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <RotateCcw size={12} />
                        )}
                        回滚
                      </button>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* 版本详情弹窗 */}
      <AnimatePresence>
        {selectedVersion && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSelectedVersion(null)}
            className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center cursor-pointer"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={e => e.stopPropagation()}
              className="bg-white dark:bg-[#1e1e20] rounded-xl shadow-2xl w-[600px] max-h-[70vh] flex flex-col overflow-hidden cursor-default"
            >
              <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-neutral-800">
                <div className="flex items-center gap-2">
                  <GitBranch size={16} className="text-blue-500" />
                  <h3 className="font-semibold text-gray-900 dark:text-white">
                    版本 v{selectedVersion.version}
                  </h3>
                </div>
                <button
                  onClick={() => setSelectedVersion(null)}
                  className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-white"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-4">
                <div className="space-y-4">
                  <div>
                    <label className="text-xs text-gray-500 dark:text-neutral-500 font-medium mb-1 block">
                      变更说明
                    </label>
                    <p className="text-sm text-gray-700 dark:text-neutral-300">
                      {selectedVersion.change_log || '无变更说明'}
                    </p>
                  </div>

                  <div>
                    <label className="text-xs text-gray-500 dark:text-neutral-500 font-medium mb-1 block">
                      创建时间
                    </label>
                    <p className="text-sm text-gray-700 dark:text-neutral-300">
                      {formatDate(selectedVersion.created_at)}
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-4 border-t border-gray-200 dark:border-neutral-800 flex justify-end gap-2">
                <button
                  onClick={() => setSelectedVersion(null)}
                  className="px-4 py-2 text-gray-600 dark:text-neutral-400 text-sm"
                >
                  关闭
                </button>
                <button
                  onClick={() => {
                    handleRollback(selectedVersion.id, selectedVersion.version);
                    setSelectedVersion(null);
                  }}
                  disabled={selectedVersion.version === skill.version || isRollingBack}
                  className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-300 disabled:dark:bg-neutral-600 disabled:cursor-not-allowed text-white text-sm rounded-lg transition-colors"
                >
                  <RotateCcw size={14} />
                  回滚到此版本
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}