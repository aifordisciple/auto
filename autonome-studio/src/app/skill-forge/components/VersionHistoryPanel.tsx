/**
 * 技能版本历史面板 - 展示版本列表、支持版本对比和回滚
 */

'use client';

import { useState, useEffect } from 'react';
import {
  History, GitBranch, RotateCcw, Plus, CheckCircle, Clock,
  Loader2, AlertCircle, ChevronDown, ChevronUp, X, FileCode
} from 'lucide-react';
import { fetchAPI, BASE_URL } from '@/lib/api';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';

// ==========================================
// 类型定义
// ==========================================

interface SkillVersion {
  id: number;
  version: string;
  change_log: string | null;
  created_at: string;
  created_by: number;
}

interface VersionDetail {
  id: number;
  skill_id: string;
  version: string;
  script_code: string | null;
  parameters_schema: Record<string, any>;
  expert_knowledge: string | null;
  change_log: string | null;
  created_at: string;
}

interface VersionHistoryPanelProps {
  skillId: string;
  skillName: string;
  currentVersion: string;
  isOwner: boolean;
  onRollback?: () => void;
  onVersionCreated?: () => void;
}

// ==========================================
// 子组件：版本时间线
// ==========================================

function VersionTimeline({
  versions,
  currentVersion,
  selectedVersion,
  onSelect,
  onRollback,
  isOwner
}: {
  versions: SkillVersion[];
  currentVersion: string;
  selectedVersion: number | null;
  onSelect: (id: number) => void;
  onRollback: (id: number) => void;
  isOwner: boolean;
}) {
  return (
    <div className="relative">
      {/* 时间线 */}
      <div className="absolute left-[11px] top-0 bottom-0 w-0.5 bg-neutral-700" />

      <div className="space-y-3">
        {versions.map((v, index) => {
          const isCurrent = v.version === currentVersion;
          const isSelected = selectedVersion === v.id;

          return (
            <motion.div
              key={v.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
              className="relative pl-8"
            >
              {/* 时间线节点 */}
              <div
                className={`absolute left-0 top-1 w-6 h-6 rounded-full border-2 flex items-center justify-center ${
                  isCurrent
                    ? 'bg-green-500/20 border-green-500'
                    : isSelected
                    ? 'bg-blue-500/20 border-blue-500'
                    : 'bg-neutral-800 border-neutral-600'
                }`}
              >
                {isCurrent ? (
                  <CheckCircle size={12} className="text-green-400" />
                ) : (
                  <GitBranch size={12} className="text-neutral-400" />
                )}
              </div>

              {/* 版本卡片 */}
              <button
                onClick={() => onSelect(v.id)}
                className={`w-full text-left p-3 rounded-lg border transition-all ${
                  isSelected
                    ? 'bg-blue-500/10 border-blue-500/30'
                    : 'bg-neutral-800/50 border-neutral-700 hover:border-neutral-600'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-neutral-200">
                      v{v.version}
                    </span>
                    {isCurrent && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-green-500/20 text-green-400 border border-green-500/30">
                        当前版本
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-neutral-500">
                    {new Date(v.created_at).toLocaleString()}
                  </span>
                </div>

                {v.change_log && (
                  <p className="text-xs text-neutral-400 line-clamp-1">
                    {v.change_log}
                  </p>
                )}

                {/* 操作按钮 */}
                {isSelected && !isCurrent && isOwner && (
                  <div className="mt-2 pt-2 border-t border-neutral-700">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onRollback(v.id);
                      }}
                      className="flex items-center gap-1.5 px-2 py-1 text-xs text-orange-400 hover:bg-orange-500/10 rounded transition-colors"
                    >
                      <RotateCcw size={12} />
                      回滚到此版本
                    </button>
                  </div>
                )}
              </button>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

// ==========================================
// 子组件：创建版本对话框
// ==========================================

function CreateVersionDialog({
  isOpen,
  onClose,
  onCreate,
  isLoading
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (version: string, changeLog: string) => void;
  isLoading: boolean;
}) {
  const [version, setVersion] = useState('');
  const [changeLog, setChangeLog] = useState('');

  const handleCreate = () => {
    if (!version.trim()) {
      toast.error('请输入版本号');
      return;
    }
    onCreate(version.trim(), changeLog.trim());
    setVersion('');
    setChangeLog('');
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl w-full max-w-md overflow-hidden"
      >
        <div className="flex items-center justify-between p-4 border-b border-neutral-800">
          <h3 className="text-lg font-semibold text-white">创建新版本</h3>
          <button
            onClick={onClose}
            className="p-1 text-neutral-400 hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div>
            <label className="text-xs text-neutral-500 mb-1 block">版本号</label>
            <input
              type="text"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="例如: 1.1.0"
              className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="text-xs text-neutral-500 mb-1 block">变更说明（可选）</label>
            <textarea
              value={changeLog}
              onChange={(e) => setChangeLog(e.target.value)}
              placeholder="描述此版本的变更内容..."
              rows={3}
              className="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none resize-none"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-neutral-800">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-neutral-400 hover:text-white transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleCreate}
            disabled={isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white text-sm rounded-lg transition-colors"
          >
            {isLoading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Plus size={16} />
            )}
            创建版本
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ==========================================
// 子组件：版本详情对比
// ==========================================

function VersionDiffView({
  version,
  currentScript,
  onClose
}: {
  version: VersionDetail | null;
  currentScript: string | null;
  onClose: () => void;
}) {
  if (!version) return null;

  return (
    <div className="mt-4 p-3 bg-neutral-800/50 border border-neutral-700 rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-neutral-300">
          版本 v{version.version} 详情
        </h4>
        <button
          onClick={onClose}
          className="text-xs text-neutral-500 hover:text-neutral-300"
        >
          关闭
        </button>
      </div>

      {/* 变更说明 */}
      {version.change_log && (
        <div className="mb-3 p-2 bg-neutral-900/50 rounded text-xs text-neutral-400">
          {version.change_log}
        </div>
      )}

      {/* 参数 Schema */}
      {Object.keys(version.parameters_schema || {}).length > 0 && (
        <div className="mb-3">
          <h5 className="text-xs text-neutral-500 mb-1">参数定义</h5>
          <div className="text-xs font-mono text-neutral-400 bg-neutral-900/50 p-2 rounded max-h-32 overflow-auto">
            <pre>{JSON.stringify(version.parameters_schema, null, 2)}</pre>
          </div>
        </div>
      )}

      {/* 代码预览 */}
      {version.script_code && (
        <div>
          <h5 className="text-xs text-neutral-500 mb-1 flex items-center gap-1">
            <FileCode size={12} />
            代码预览
          </h5>
          <div className="text-xs font-mono text-green-400/80 bg-neutral-950 p-2 rounded max-h-48 overflow-auto">
            <pre>{version.script_code.slice(0, 2000)}{version.script_code.length > 2000 ? '...' : ''}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

// ==========================================
// 主组件
// ==========================================

export function VersionHistoryPanel({
  skillId,
  skillName,
  currentVersion,
  isOwner,
  onRollback,
  onVersionCreated
}: VersionHistoryPanelProps) {
  const [versions, setVersions] = useState<SkillVersion[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [versionDetail, setVersionDetail] = useState<VersionDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);

  // 加载版本历史
  useEffect(() => {
    loadVersions();
  }, [skillId]);

  const loadVersions = async () => {
    setIsLoading(true);
    try {
      const response = await fetchAPI(`/api/skills/${skillId}/versions`);
      if (response.status === 'success') {
        setVersions(response.data || []);
      }
    } catch (e) {
      console.error('Failed to load versions:', e);
      toast.error('加载版本历史失败');
    } finally {
      setIsLoading(false);
    }
  };

  // 选择版本查看详情
  const handleSelectVersion = async (id: number) => {
    if (selectedVersion === id) {
      setSelectedVersion(null);
      setVersionDetail(null);
      return;
    }

    setSelectedVersion(id);

    // 加载版本详情
    try {
      const response = await fetchAPI(`/api/skills/${skillId}/versions/${id}`);
      if (response.status === 'success') {
        setVersionDetail(response.data);
      }
    } catch (e) {
      console.error('Failed to load version detail:', e);
    }
  };

  // 回滚版本
  const handleRollback = async (versionId: number) => {
    if (!confirm('确定要回滚到此版本吗？当前修改将被覆盖。')) {
      return;
    }

    setIsRollingBack(true);
    try {
      const response = await fetchAPI(`/api/skills/${skillId}/rollback/${versionId}`, {
        method: 'POST'
      });

      if (response.status === 'success') {
        toast.success('版本回滚成功');
        onRollback?.();
        loadVersions();
      }
    } catch (e) {
      console.error('Failed to rollback:', e);
      toast.error('版本回滚失败');
    } finally {
      setIsRollingBack(false);
    }
  };

  // 创建新版本
  const handleCreateVersion = async (version: string, changeLog: string) => {
    setIsCreating(true);
    try {
      const params = new URLSearchParams({ version });
      if (changeLog) {
        params.append('change_log', changeLog);
      }

      const response = await fetchAPI(`/api/skills/${skillId}/versions?${params.toString()}`, {
        method: 'POST'
      });

      if (response.status === 'success') {
        toast.success('版本创建成功');
        setShowCreateDialog(false);
        onVersionCreated?.();
        loadVersions();
      }
    } catch (e: any) {
      console.error('Failed to create version:', e);
      toast.error(e.message || '版本创建失败');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="border border-neutral-800 rounded-lg overflow-hidden">
      {/* 标题栏 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 bg-neutral-800/50 hover:bg-neutral-800 transition-colors"
      >
        <div className="flex items-center gap-2">
          <History size={16} className="text-neutral-400" />
          <span className="text-sm font-medium text-neutral-300">版本历史</span>
          <span className="text-xs text-neutral-500">({versions.length} 个版本)</span>
        </div>
        {isExpanded ? (
          <ChevronUp size={16} className="text-neutral-500" />
        ) : (
          <ChevronDown size={16} className="text-neutral-500" />
        )}
      </button>

      {/* 内容区 */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4">
              {/* 创建版本按钮 */}
              {isOwner && (
                <button
                  onClick={() => setShowCreateDialog(true)}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 mb-4 bg-blue-600/10 hover:bg-blue-600/20 border border-blue-500/30 rounded-lg text-blue-400 text-sm transition-colors"
                >
                  <Plus size={16} />
                  创建新版本
                </button>
              )}

              {/* 版本列表 */}
              {isLoading ? (
                <div className="flex items-center justify-center h-24 text-neutral-500">
                  <Loader2 size={24} className="animate-spin" />
                </div>
              ) : versions.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-24 text-neutral-600">
                  <Clock size={24} className="mb-2 opacity-50" />
                  <p className="text-sm">暂无版本历史</p>
                </div>
              ) : (
                <>
                  <VersionTimeline
                    versions={versions}
                    currentVersion={currentVersion}
                    selectedVersion={selectedVersion}
                    onSelect={handleSelectVersion}
                    onRollback={handleRollback}
                    isOwner={isOwner}
                  />

                  {/* 版本详情 */}
                  {versionDetail && (
                    <VersionDiffView
                      version={versionDetail}
                      currentScript={null}
                      onClose={() => {
                        setSelectedVersion(null);
                        setVersionDetail(null);
                      }}
                    />
                  )}
                </>
              )}

              {/* 回滚加载状态 */}
              {isRollingBack && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
                  <div className="bg-neutral-900 border border-neutral-700 rounded-lg p-4 flex items-center gap-3">
                    <Loader2 size={20} className="animate-spin text-blue-400" />
                    <span className="text-sm text-neutral-300">正在回滚版本...</span>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 创建版本对话框 */}
      <CreateVersionDialog
        isOpen={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onCreate={handleCreateVersion}
        isLoading={isCreating}
      />
    </div>
  );
}