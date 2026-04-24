# Autonome 身份验证系统升级补全设计

> 日期: 2026-04-24
> 状态: Draft
> 方案: 增量修补（方案A）

---

## 背景

对照 `docs/modules/身份验证系统.md` 需求文档审计现有代码，发现9项未完成或有缺陷的问题。本设计采用增量修补策略，逐项修复，最小化改动范围，确保不破坏现有功能。

---

## 修复项清单

### 1. 注册端点不匹配修复

**问题**: 前端 `register/page.tsx` 发送 `phone_number`、`sms_code`、`password`、`full_name`，但后端 `UserCreate` schema 只有 `email`+`password`，注册路由不支持短信验证。前端还错误地使用 `/auth/forgot-password/verify` 来验证注册的短信OTP。

**修复方案**:

1. **后端 `UserCreate` schema 扩展** (`app/schemas/user.py`):
   - `phone_number: Optional[str]` — 手机号（正则验证 `^1[3-9]\d{9}$`）
   - `sms_code: Optional[str]` — 短信验证码（6位数字）
   - `full_name: Optional[str]` — 用户姓名
   - `email: Optional[EmailStr]` — 改为可选
   - 验证逻辑：`phone_number + sms_code` 或 `email + password` 至少一组必填

2. **注册路由改造** (`POST /auth/register`):
   - 如果提供 `phone_number + sms_code`：先验证短信码（复用 `auth_risk_control.verify_otp`），再创建用户
   - 如果提供 `email + password`：走原有邮箱注册流程
   - 两种方式都支持 `full_name`
   - 手机号注册时自动生成虚拟邮箱 `{phone}@autonome.local`（仅用于数据库 email 唯一约束，不发送邮件）

3. **前端不变**：当前前端代码已正确发送所需字段

**影响范围**: `autonome-backend/app/schemas/user.py`、`autonome-backend/app/api/routes/auth.py`

---

### 2. RBAC迁移缺失

**问题**: `roles`、`permissions`、`role_permissions`、`user_roles`、`audit_logs` 表在模型中定义，但没有对应的 Alembic 迁移脚本。

**修复方案**:

1. 创建 Alembic 迁移脚本 `20260424_add_rbac_tables.py`:
   - `roles` 表（id, name, description, is_default, created_at, updated_at）
   - `permissions` 表（id, name, code, module, description, created_at）
   - `role_permissions` 关联表（role_id, permission_id）
   - `user_roles` 关联表（user_id, role_id, granted_at, granted_by）
   - `audit_logs` 表（id, user_id, action, resource_type, resource_id, detail, ip_address, created_at）
   - 所有外键约束和索引

2. 迁移脚本中添加默认数据:
   - 默认角色：admin, user
   - 默认权限：基于需求文档中的权限矩阵
   - admin 角色拥有所有权限

3. 幂等处理：检查表是否已存在，避免重复创建

**影响范围**: `autonome-backend/alembic/versions/` 新增迁移文件

---

### 3. 密码修改端点重复

**问题**: `auth.py` 的 `POST /change-password` 和 `users.py` 的 `POST /me/password` 功能重复，行为不一致。

**修复方案**:

1. **统一到 `auth.py`**: 保留 `auth.py` 的 `POST /change-password`，行为为:
   - 验证旧密码
   - 更新密码哈希
   - 撤销除当前会话外的所有其他会话（保留当前设备在线）
   - 当前设备保持登录状态

2. **删除 `users.py` 中的 `POST /me/password`**: 避免重复和混淆

3. **前端确认**: 检查前端是否调用了 `/users/me/password`，如有则改为调用 `/auth/change-password`

**影响范围**: `autonome-backend/app/api/routes/auth.py`、`autonome-backend/app/api/routes/users.py`

---

### 4. OAuth access_token 加密存储

**问题**: `OAuthAccount.access_token` 明文存储第三方token，数据库泄露后可被利用。

**修复方案**:

1. 在 `security.py` 中添加辅助方法:
   - `encrypt_oauth_token(token: str) -> str` — 使用 Fernet 对称加密
   - `decrypt_oauth_token(encrypted: str) -> str` — 解密
   - 密钥从 `settings.SECRET_KEY` 派生（取前32字节作为Fernet密钥）

2. 修改 `OAuthAccount` 模型:
   - 保持 `access_token` 字段名不变，但存储加密值（避免迁移复杂度）
   - 添加注释标记该字段存储的是加密值

3. 修改 OAuth 路由:
   - 存储 token 时加密
   - 读取 token 时解密

4. 迁移脚本: 将现有明文token加密更新

**影响范围**: `app/core/security.py`、`app/models/user.py`、`app/api/routes/oauth.py`、新增迁移

---

### 5. SECURE_COOKIES 生产环境强制

**问题**: `SECURE_COOKIES` 默认 False，生产环境无强制验证。

**修复方案**:

1. 在 `config.py` 中添加启动检查:
   - 如果 `ENVIRONMENT=production` 且 `SECURE_COOKIES=False`，打印 WARNING 级别日志
   - 不强制报错退出（避免阻断部署），但记录醒目警告

2. 在 `main.py` 启动事件中调用检查函数

**影响范围**: `app/core/config.py`、`app/main.py`

---

### 6. 2FA恢复码改存数据库

**问题**: 2FA恢复码存Redis（1年TTL），Redis重启会丢失。

**修复方案**:

1. 新增 `TwoFactorRecoveryCode` 模型:
   ```python
   class TwoFactorRecoveryCode(Base):
       __tablename__ = "two_factor_recovery_codes"
       id = Column(UUID, primary_key=True, default=uuid.uuid4)
       user_id = Column(UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
       code_hash = Column(String(255), nullable=False)  # bcrypt hash
       is_used = Column(Boolean, default=False)
       used_at = Column(DateTime, nullable=True)
       created_at = Column(DateTime, default=datetime.utcnow)
   ```

2. 创建对应迁移脚本

3. 修改2FA setup逻辑: 恢复码存入数据库而非Redis

4. 修改2FA验证逻辑: 从数据库查询恢复码，使用后标记 `is_used=True`

**影响范围**: `app/models/user.py`、`app/api/routes/auth.py`、新增迁移

---

### 7. 微信登录对接

**问题**: 登录页有微信按钮，后端OAuth路由已实现，但前端按钮可能未正确对接。

**修复方案**:

1. 检查前端微信按钮的 onClick 逻辑
2. 确保调用后端 `/api/oauth/wechat/qr-url` 获取扫码URL
3. 确认 OAuth callback 页面正确处理微信回调

**影响范围**: `autonome-studio/src/app/login/page.tsx`

---

### 8. 安全邮箱绑定UI

**问题**: 后端有 `/bind-email` 和 `/verify-email`，但前端安全中心缺少对应UI。

**修复方案**:

1. 在安全中心 SecurityPanel 中添加"安全邮箱绑定"区块:
   - 显示当前绑定状态（已绑定/未绑定）
   - 绑定流程：输入邮箱 → 验证当前密码 → 发送验证邮件 → 邮件确认
   - 已绑定可更换或解绑

**影响范围**: 前端 SecurityPanel 组件

---

### 9. 设备管理UI

**问题**: 后端有 `/sessions` 和 `/sessions/{id}/revoke`，但前端安全中心缺少设备管理面板。

**修复方案**:

1. 在安全中心 SecurityPanel 中添加"在线设备管理"区块:
   - 调用 `/auth/sessions` 获取活跃会话列表
   - 显示设备类型、IP、登录时间、User-Agent
   - 当前设备标记"当前"
   - 其他设备显示"下线"按钮
   - 一键"全部下线"按钮

**影响范围**: 前端 SecurityPanel 组件

---

## 实施顺序

按依赖关系排序：

1. **安全加固** (修复项 4, 5, 6) — 基础安全，优先处理
2. **后端功能修复** (修复项 1, 2, 3) — 核心功能补全
3. **前端补全** (修复项 7, 8, 9) — UI层补全

每个修复项独立部署验证，确保不破坏现有功能。

---

## 验证标准

每个修复项完成后需验证：

1. 现有登录流程（邮箱+密码、手机号+验证码）不受影响
2. 现有OAuth流程（GitHub）不受影响
3. 现有2FA流程不受影响
4. Docker服务正常启动
5. 前端页面正常渲染
