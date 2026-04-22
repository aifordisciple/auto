/**
 * RBAC 角色权限管理面板
 *
 * 阶段四：管理员专用的角色/权限/审计日志管理
 *
 * 功能：
 * - 角色管理（CRUD + 权限分配）
 * - 权限列表查看
 * - 审计日志查询
 */

"use client";

import { useState, useEffect, useCallback } from 'react';
import { rbacApi, type RoleOut, type PermissionOut, type AuditLogOut } from '@/lib/api/rbac';
import {
  Shield, Plus, Trash2, Edit3, Check, X, ChevronDown, ChevronRight,
  ScrollText, Users, Key, Loader2, AlertCircle, Search, RefreshCw,
} from 'lucide-react';

// ==========================================
// 子 Tab 类型
// ==========================================

type SubTab = 'roles' | 'audit';

// ==========================================
// RBAC 管理面板
// ==========================================

export function RbacPanel() {
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('roles');

  return (
    <div className="h-full flex flex-col">
      {/* 子 Tab 切换 */}
      <div className="shrink-0 border-b border-neutral-800 px-4 pt-4 flex gap-2">
        <SubTabButton
          active={activeSubTab === 'roles'}
          onClick={() => setActiveSubTab('roles')}
          icon={<Shield size={14} />}
          label="角色权限"
        />
        <SubTabButton
          active={activeSubTab === 'audit'}
          onClick={() => setActiveSubTab('audit')}
          icon={<ScrollText size={14} />}
          label="审计日志"
        />
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeSubTab === 'roles' && <RolesPermissionsTab />}
        {activeSubTab === 'audit' && <AuditLogsTab />}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────
// 子 Tab 按钮
// ──────────────────────────────────────────────

function SubTabButton({ active, onClick, icon, label }: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium transition-colors ${
        active
          ? 'bg-orange-500/20 text-orange-400 border border-b-0 border-orange-500/30'
          : 'text-neutral-400 hover:text-white hover:bg-neutral-800'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

// ──────────────────────────────────────────────
// 角色权限 Tab
// ──────────────────────────────────────────────

function RolesPermissionsTab() {
  const [roles, setRoles] = useState<RoleOut[]>([]);
  const [permissions, setPermissions] = useState<PermissionOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 新建角色表单
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newRoleName, setNewRoleName] = useState('');
  const [newRoleDesc, setNewRoleDesc] = useState('');
  const [creating, setCreating] = useState(false);

  // 编辑角色权限
  const [editingRoleId, setEditingRoleId] = useState<number | null>(null);
  const [selectedPermIds, setSelectedPermIds] = useState<Set<number>>(new Set());
  const [savingPerms, setSavingPerms] = useState(false);

  // 消息提示
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rolesRes, permsRes] = await Promise.all([
        rbacApi.listRoles(),
        rbacApi.listPermissions(),
      ]);
      setRoles(rolesRes.roles);
      setPermissions(permsRes.permissions);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 创建角色
  const handleCreateRole = async () => {
    if (!newRoleName.trim()) return;
    setCreating(true);
    try {
      const res = await rbacApi.createRole({
        name: newRoleName.trim(),
        description: newRoleDesc.trim() || undefined,
      });
      if (res.success) {
        setMessage({ type: 'success', text: `角色 "${newRoleName}" 创建成功` });
        setNewRoleName('');
        setNewRoleDesc('');
        setShowCreateForm(false);
        loadData();
      } else {
        setMessage({ type: 'error', text: res.message || '创建失败' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '创建失败' });
    } finally {
      setCreating(false);
    }
  };

  // 删除角色
  const handleDeleteRole = async (roleId: number, roleName: string) => {
    if (!confirm(`确定删除角色 "${roleName}"？此操作不可撤销。`)) return;
    try {
      const res = await rbacApi.deleteRole(roleId);
      if (res.success) {
        setMessage({ type: 'success', text: `角色 "${roleName}" 已删除` });
        loadData();
      } else {
        setMessage({ type: 'error', text: res.message || '删除失败' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '删除失败' });
    }
  };

  // 开始编辑角色权限
  const startEditPermissions = (role: RoleOut) => {
    setEditingRoleId(role.id);
    setSelectedPermIds(new Set(role.permissions.map(p => p.id)));
  };

  // 保存角色权限
  const handleSavePermissions = async () => {
    if (editingRoleId === null) return;
    setSavingPerms(true);
    try {
      const res = await rbacApi.setRolePermissions(editingRoleId, Array.from(selectedPermIds));
      if (res.success) {
        setMessage({ type: 'success', text: '权限更新成功' });
        setEditingRoleId(null);
        loadData();
      } else {
        setMessage({ type: 'error', text: res.message || '更新失败' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '更新失败' });
    } finally {
      setSavingPerms(false);
    }
  };

  // 按模块分组权限
  const permissionsByModule = permissions.reduce<Record<string, PermissionOut[]>>((acc, p) => {
    const mod = p.module || 'other';
    if (!acc[mod]) acc[mod] = [];
    acc[mod].push(p);
    return acc;
  }, {});

  // ── 加载状态 ──
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-orange-400" size={24} />
        <span className="ml-2 text-neutral-400">加载中...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="text-red-400" size={24} />
        <p className="text-red-400 text-sm">{error}</p>
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-neutral-800 text-neutral-300 hover:text-white text-sm transition-colors"
        >
          <RefreshCw size={14} />
          重试
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 消息提示 */}
      {message && (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
          message.type === 'success' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
        }`}>
          {message.type === 'success' ? <Check size={14} /> : <AlertCircle size={14} />}
          {message.text}
          <button onClick={() => setMessage(null)} className="ml-auto"><X size={14} /></button>
        </div>
      )}

      {/* 操作栏 */}
      <div className="flex items-center justify-between">
        <h3 className="text-white font-medium flex items-center gap-2">
          <Shield size={16} className="text-orange-400" />
          角色管理
        </h3>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-500/20 text-orange-400 hover:bg-orange-500/30 text-sm transition-colors"
        >
          <Plus size={14} />
          新建角色
        </button>
      </div>

      {/* 新建角色表单 */}
      {showCreateForm && (
        <div className="bg-neutral-800/50 rounded-lg p-4 border border-neutral-700 space-y-3">
          <input
            type="text"
            value={newRoleName}
            onChange={e => setNewRoleName(e.target.value)}
            placeholder="角色名称"
            className="w-full px-3 py-2 rounded-lg bg-neutral-900 border border-neutral-700 text-white text-sm placeholder:text-neutral-500 focus:outline-none focus:border-orange-500/50"
          />
          <input
            type="text"
            value={newRoleDesc}
            onChange={e => setNewRoleDesc(e.target.value)}
            placeholder="角色描述（可选）"
            className="w-full px-3 py-2 rounded-lg bg-neutral-900 border border-neutral-700 text-white text-sm placeholder:text-neutral-500 focus:outline-none focus:border-orange-500/50"
          />
          <div className="flex gap-2">
            <button
              onClick={handleCreateRole}
              disabled={creating || !newRoleName.trim()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-500 text-white text-sm hover:bg-orange-600 disabled:opacity-50 transition-colors"
            >
              {creating ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
              创建
            </button>
            <button
              onClick={() => { setShowCreateForm(false); setNewRoleName(''); setNewRoleDesc(''); }}
              className="px-3 py-1.5 rounded-lg bg-neutral-700 text-neutral-300 text-sm hover:text-white transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* 角色列表 */}
      <div className="space-y-3">
        {roles.map(role => (
          <div key={role.id} className="bg-neutral-800/50 rounded-lg border border-neutral-700 overflow-hidden">
            {/* 角色头部 */}
            <div className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3">
                <div className={`w-2 h-2 rounded-full ${
                  role.name === 'admin' ? 'bg-red-400' :
                  role.name === 'researcher' ? 'bg-blue-400' :
                  role.name === 'viewer' ? 'bg-green-400' :
                  'bg-neutral-400'
                }`} />
                <div>
                  <span className="text-white font-medium text-sm">{role.name}</span>
                  {role.is_default && (
                    <span className="ml-2 px-1.5 py-0.5 rounded text-xs bg-blue-500/20 text-blue-400">默认</span>
                  )}
                </div>
                {role.description && (
                  <span className="text-neutral-500 text-xs">— {role.description}</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => editingRoleId === role.id ? setEditingRoleId(null) : startEditPermissions(role)}
                  className="flex items-center gap-1 px-2 py-1 rounded text-xs text-neutral-400 hover:text-orange-400 hover:bg-neutral-700 transition-colors"
                >
                  <Key size={12} />
                  权限
                </button>
                {role.name !== 'admin' && (
                  <button
                    onClick={() => handleDeleteRole(role.id, role.name)}
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs text-neutral-400 hover:text-red-400 hover:bg-neutral-700 transition-colors"
                  >
                    <Trash2 size={12} />
                    删除
                  </button>
                )}
              </div>
            </div>

            {/* 当前权限标签 */}
            {editingRoleId !== role.id && role.permissions.length > 0 && (
              <div className="px-4 pb-3 flex flex-wrap gap-1.5">
                {role.permissions.map(p => (
                  <span key={p.id} className="px-2 py-0.5 rounded text-xs bg-neutral-700 text-neutral-300">
                    {p.code}
                  </span>
                ))}
              </div>
            )}

            {/* 权限编辑面板 */}
            {editingRoleId === role.id && (
              <div className="border-t border-neutral-700 p-4 space-y-3">
                <p className="text-neutral-400 text-xs">选择此角色拥有的权限：</p>
                {Object.entries(permissionsByModule).map(([mod, perms]) => (
                  <div key={mod}>
                    <p className="text-neutral-500 text-xs font-medium mb-1.5 uppercase tracking-wider">{mod}</p>
                    <div className="flex flex-wrap gap-2">
                      {perms.map(p => (
                        <label
                          key={p.id}
                          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs cursor-pointer transition-colors ${
                            selectedPermIds.has(p.id)
                              ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                              : 'bg-neutral-700 text-neutral-400 border border-transparent hover:border-neutral-600'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedPermIds.has(p.id)}
                            onChange={() => {
                              const next = new Set(selectedPermIds);
                              if (next.has(p.id)) next.delete(p.id);
                              else next.add(p.id);
                              setSelectedPermIds(next);
                            }}
                            className="sr-only"
                          />
                          {p.code}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={handleSavePermissions}
                    disabled={savingPerms}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-500 text-white text-sm hover:bg-orange-600 disabled:opacity-50 transition-colors"
                  >
                    {savingPerms ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                    保存权限
                  </button>
                  <button
                    onClick={() => setEditingRoleId(null)}
                    className="px-3 py-1.5 rounded-lg bg-neutral-700 text-neutral-300 text-sm hover:text-white transition-colors"
                  >
                    取消
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 权限总览 */}
      <div className="mt-6">
        <h3 className="text-white font-medium flex items-center gap-2 mb-3">
          <Key size={16} className="text-orange-400" />
          权限总览
        </h3>
        <div className="space-y-3">
          {Object.entries(permissionsByModule).map(([mod, perms]) => (
            <div key={mod} className="bg-neutral-800/30 rounded-lg p-3">
              <p className="text-neutral-500 text-xs font-medium mb-2 uppercase tracking-wider">{mod}</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {perms.map(p => (
                  <div key={p.id} className="flex items-center gap-2 text-sm">
                    <ChevronRight size={12} className="text-orange-400/60" />
                    <span className="text-neutral-300">{p.code}</span>
                    {p.description && <span className="text-neutral-600 text-xs">— {p.description}</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────
// 审计日志 Tab
// ──────────────────────────────────────────────

function AuditLogsTab() {
  const [logs, setLogs] = useState<AuditLogOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 筛选条件
  const [filterAction, setFilterAction] = useState('');
  const [filterResourceType, setFilterResourceType] = useState('');

  const limit = 20;

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await rbacApi.listAuditLogs({
        page,
        limit,
        action: filterAction || undefined,
        resource_type: filterResourceType || undefined,
      });
      setLogs(res.logs);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [page, filterAction, filterResourceType]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const totalPages = Math.ceil(total / limit);

  // 操作类型标签颜色
  const actionColor = (action: string): string => {
    if (action.includes('create')) return 'text-green-400 bg-green-500/20';
    if (action.includes('delete')) return 'text-red-400 bg-red-500/20';
    if (action.includes('update') || action.includes('change')) return 'text-amber-400 bg-amber-500/20';
    return 'text-blue-400 bg-blue-500/20';
  };

  // 格式化时间
  const formatTime = (iso: string | null): string => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  };

  return (
    <div className="space-y-4">
      {/* 筛选栏 */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Search size={14} className="text-neutral-500" />
          <input
            type="text"
            value={filterAction}
            onChange={e => { setFilterAction(e.target.value); setPage(1); }}
            placeholder="操作类型筛选"
            className="px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-white text-sm placeholder:text-neutral-500 focus:outline-none focus:border-orange-500/50 w-40"
          />
        </div>
        <input
          type="text"
          value={filterResourceType}
          onChange={e => { setFilterResourceType(e.target.value); setPage(1); }}
          placeholder="资源类型筛选"
          className="px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-white text-sm placeholder:text-neutral-500 focus:outline-none focus:border-orange-500/50 w-40"
        />
        <button
          onClick={loadLogs}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 text-neutral-300 hover:text-white text-sm transition-colors"
        >
          <RefreshCw size={14} />
          刷新
        </button>
        <span className="text-neutral-500 text-xs ml-auto">共 {total} 条</span>
      </div>

      {/* 加载状态 */}
      {loading && (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="animate-spin text-orange-400" size={20} />
          <span className="ml-2 text-neutral-400 text-sm">加载中...</span>
        </div>
      )}

      {/* 错误 */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/20 text-red-400 text-sm">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {/* 日志列表 */}
      {!loading && !error && (
        <div className="space-y-2">
          {logs.length === 0 ? (
            <p className="text-neutral-500 text-sm text-center py-10">暂无审计日志</p>
          ) : (
            logs.map(log => (
              <div key={log.id} className="bg-neutral-800/50 rounded-lg border border-neutral-700 px-4 py-3">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${actionColor(log.action)}`}>
                      {log.action}
                    </span>
                    {log.resource_type && (
                      <span className="px-1.5 py-0.5 rounded text-xs bg-neutral-700 text-neutral-400">
                        {log.resource_type}
                      </span>
                    )}
                    {log.resource_id && (
                      <span className="text-neutral-600 text-xs">#{log.resource_id}</span>
                    )}
                  </div>
                  <span className="text-neutral-500 text-xs">{formatTime(log.created_at)}</span>
                </div>
                {log.detail && (
                  <p className="text-neutral-400 text-xs mt-1">{log.detail}</p>
                )}
                <div className="flex items-center gap-3 mt-1.5 text-xs text-neutral-600">
                  {log.user_id && <span>用户 #{log.user_id}</span>}
                  {log.ip_address && <span>IP: {log.ip_address}</span>}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 rounded-lg bg-neutral-800 text-neutral-300 text-sm hover:text-white disabled:opacity-30 transition-colors"
          >
            上一页
          </button>
          <span className="text-neutral-400 text-sm">{page} / {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1 rounded-lg bg-neutral-800 text-neutral-300 text-sm hover:text-white disabled:opacity-30 transition-colors"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
