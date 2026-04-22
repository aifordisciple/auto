# Phase 4: RBAC 权限模型 + 管理后台设计

## 概述

阶段四实现 RBAC（基于角色的访问控制）权限模型，包含角色-权限二级结构、鉴权中间件、管理 API、审计日志，以及前端 admin 面板扩展。

## 数据模型

### 新增表

**roles**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| name | String(50) UNIQUE | 角色名 |
| description | String(200) | 角色描述 |
| is_default | Boolean | 是否新用户默认角色 |
| created_at | DateTime | 创建时间 |

**permissions**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| code | String(100) UNIQUE | 权限码（如 project:create） |
| name | String(100) | 显示名称 |
| module | String(50) | 所属模块 |
| description | String(200) | 权限描述 |

**role_permissions**（关联表）：role_id FK → roles.id, permission_id FK → permissions.id

**user_roles**（关联表）：user_id FK → users.id, role_id FK → roles.id

**audit_logs**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | FK → users.id (nullable) | 操作用户 |
| action | String(100) | 操作类型 |
| resource_type | String(50) | 资源类型 |
| resource_id | String(50) | 资源ID |
| detail | Text (JSON) | 操作详情 |
| ip_address | String(50) | IP 地址 |
| created_at | DateTime | 操作时间 |

### 预置角色

- `admin` — 管理员，拥有所有权限
- `researcher` — 研究员，可创建项目/技能/执行分析（默认角色）
- `viewer` — 观察者，只读权限

### 预置权限

- `project:create/read/update/delete`
- `skill:create/read/update/delete/execute`
- `admin:user_manage/role_manage/system_config`
- `data:read/export`

### User 模型变更

`users` 表新增 `role_id` 字段（FK → roles.id, nullable），作为用户主角色。同时保留 `user_roles` 多对多关联用于附加角色。

## 鉴权中间件

文件：`app/api/deps_rbac.py`

核心函数：
- `require_permission(code: str)` → 返回 Depends，校验当前用户是否拥有指定权限
- `require_role(name: str)` → 返回 Depends，校验当前用户是否拥有指定角色
- `get_user_permissions(user, db)` → 获取用户所有权限（主角色 + 附加角色）

鉴权逻辑：
1. 从 `get_current_user` 获取当前用户
2. 查用户主角色 + 附加角色
3. 合并所有角色的权限
4. 检查是否包含目标权限/角色
5. `admin` 角色自动拥有所有权限

用法：
```python
@router.post("/projects", dependencies=[Depends(require_permission("project:create"))])
@router.get("/admin/users", dependencies=[Depends(require_role("admin"))])
```

## 管理 API

文件：`app/api/routes/rbac.py`

| 端点 | 方法 | 功能 | 权限 |
|------|------|------|------|
| `/api/rbac/roles` | GET | 角色列表 | admin |
| `/api/rbac/roles` | POST | 创建角色 | admin |
| `/api/rbac/roles/{id}` | PUT | 更新角色 | admin |
| `/api/rbac/roles/{id}` | DELETE | 删除角色 | admin |
| `/api/rbac/permissions` | GET | 权限列表 | admin |
| `/api/rbac/roles/{id}/permissions` | PUT | 设置角色权限 | admin |
| `/api/rbac/users/{id}/roles` | PUT | 设置用户角色 | admin |
| `/api/rbac/users/{id}/roles` | GET | 查询用户角色 | admin |
| `/api/rbac/audit-logs` | GET | 审计日志查询 | admin |

## 审计日志

通过 `AuditLogger` 工具类统一记录，记录内容：
- 用户登录/登出
- 角色变更
- 权限变更
- 管理员操作

## 前端扩展

在已有 admin 面板中新增 RBAC 管理 Tab：
1. 角色管理 — 列表/创建/编辑/删除角色，分配权限
2. 用户角色 — 在用户管理中增加角色分配功能
3. 审计日志 — 操作日志查询表格

## 迁移策略

1. Alembic 迁移：新增 5 张表 + users 表新增 role_id 列
2. 迁移中自动插入预置角色和权限数据
3. 现有 `is_superuser=True` 用户自动关联 admin 角色
4. 现有普通用户自动关联 researcher 角色
5. `is_superuser` 字段保留，admin 角色与 is_superuser 双重判断

## 向后兼容

- `is_superuser` 保留，现有管理员功能不受影响
- 现有端点不加权限校验（渐进式），仅新增 admin 管理端点加 RBAC 校验
- `get_current_user` 依赖不变，RBAC 是可选的额外层
