// ==========================================
// RBAC 角色权限管理 API
// ==========================================

import { fetchAPI } from '../api';

// ──────────────────────────────────────────────
// 类型定义
// ──────────────────────────────────────────────

export interface PermissionOut {
  id: number;
  code: string;
  name: string;
  module: string;
  description: string | null;
}

export interface RoleOut {
  id: number;
  name: string;
  description: string | null;
  is_default: boolean;
  created_at: string | null;
  permissions: Pick<PermissionOut, 'id' | 'code' | 'name' | 'module'>[];
}

export interface AuditLogOut {
  id: number;
  user_id: number | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  detail: string | null;
  ip_address: string | null;
  created_at: string | null;
}

export interface UserRolesOut {
  user_id: number;
  primary_role: { id: number; name: string } | null;
  roles: { id: number; name: string; description: string | null }[];
  permissions: string[];
}

// ──────────────────────────────────────────────
// API 方法
// ──────────────────────────────────────────────

export const rbacApi = {
  // ── 角色管理 ──

  /** 角色列表 */
  listRoles: async (): Promise<{ roles: RoleOut[] }> => {
    return fetchAPI('/rbac/roles');
  },

  /** 创建角色 */
  createRole: async (data: {
    name: string;
    description?: string;
    is_default?: boolean;
  }): Promise<{ success: boolean; role?: { id: number; name: string }; message?: string }> => {
    return fetchAPI('/rbac/roles', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /** 更新角色 */
  updateRole: async (
    roleId: number,
    data: { name?: string; description?: string; is_default?: boolean }
  ): Promise<{ success: boolean; message?: string }> => {
    return fetchAPI(`/rbac/roles/${roleId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /** 删除角色 */
  deleteRole: async (roleId: number): Promise<{ success: boolean; message?: string }> => {
    return fetchAPI(`/rbac/roles/${roleId}`, {
      method: 'DELETE',
    });
  },

  // ── 权限管理 ──

  /** 权限列表 */
  listPermissions: async (): Promise<{ permissions: PermissionOut[] }> => {
    return fetchAPI('/rbac/permissions');
  },

  /** 设置角色权限（全量替换） */
  setRolePermissions: async (
    roleId: number,
    permissionIds: number[]
  ): Promise<{ success: boolean; message?: string }> => {
    return fetchAPI(`/rbac/roles/${roleId}/permissions`, {
      method: 'PUT',
      body: JSON.stringify({ permission_ids: permissionIds }),
    });
  },

  // ── 用户角色管理 ──

  /** 查询用户角色 */
  getUserRoles: async (userId: number): Promise<UserRolesOut> => {
    return fetchAPI(`/rbac/users/${userId}/roles`);
  },

  /** 设置用户角色 */
  setUserRoles: async (
    userId: number,
    roleIds: number[]
  ): Promise<{ success: boolean; message?: string }> => {
    return fetchAPI(`/rbac/users/${userId}/roles`, {
      method: 'PUT',
      body: JSON.stringify({ role_ids: roleIds }),
    });
  },

  // ── 审计日志 ──

  /** 审计日志查询 */
  listAuditLogs: async (params?: {
    user_id?: number;
    action?: string;
    resource_type?: string;
    page?: number;
    limit?: number;
  }): Promise<{
    total: number;
    page: number;
    limit: number;
    logs: AuditLogOut[];
  }> => {
    const query = new URLSearchParams();
    if (params?.user_id) query.set('user_id', String(params.user_id));
    if (params?.action) query.set('action', params.action);
    if (params?.resource_type) query.set('resource_type', params.resource_type);
    if (params?.page) query.set('page', String(params.page));
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString();
    return fetchAPI(`/rbac/audit-logs${qs ? `?${qs}` : ''}`);
  },
};
