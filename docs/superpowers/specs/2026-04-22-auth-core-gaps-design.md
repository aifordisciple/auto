# Autonome 身份验证系统核心缺失功能补全设计

**日期**: 2026-04-22
**范围**: 修复需求文档（身份验证系统.md）中已定义但代码中缺失的核心功能
**原则**: 增量补全，不破坏现有功能

---

## 1. OAuthAccount 模型字段修复

**问题**: `oauth.py` 使用了 `provider_name` 和 `provider_avatar_url` 字段，但 `OAuthAccount` 模型未定义，导致运行时错误。

**修改文件**:
- `autonome-backend/app/models/user.py` — OAuthAccount 添加 `provider_name` 和 `provider_avatar_url` 字段
- 生成 Alembic 迁移脚本

**具体变更**:
```python
# OAuthAccount 新增字段
provider_name: Optional[str] = Field(default=None, max_length=255, description="第三方用户显示名")
provider_avatar_url: Optional[str] = Field(default=None, max_length=512, description="第三方用户头像 URL")
```

---

## 2. OAuth 强制手机号绑定流（工作流 B）

**问题**: 当前 GitHub/微信 OAuth 回调直接自动创建 User 并签发 Token，违反需求文档"未绑定手机号的第三方 ID 必须被阻拦在临时绑定凭证状态"的要求。

### 后端变更

**`app/core/security.py` 新增**:
- `create_bind_token(provider, provider_account_id, email, name, avatar_url)` — 生成短命 JWT（10分钟，scope=bind_only）
- `verify_bind_token(token)` — 解析并验证 bind_token

**`app/api/routes/oauth.py` 修改**:
- `github_callback` 和 `wechat_callback`：当 OAuth 账号未关联已有用户时，返回 `requires_binding` + `bind_token`，而非自动创建 User
- 已关联用户的行为不变（直接签发 Token）

**`app/api/routes/auth.py` 新增端点**:
- `POST /auth/bind-phone` — 接收 `phone` + `otp_code` + `bind_token`
  - 验证 OTP（复用现有 verify_otp）
  - 验证 bind_token
  - 查找手机号对应用户：
    - 已存在：将 OAuth 账号关联到该用户（检查冲突）
    - 不存在：创建新 User + OAuthAccount
  - 签发双 Token

### 前端变更

**新增 `autonome-studio/src/components/overlays/Auth/BindPhoneModal.tsx`**:
- 不可关闭的模态框
- 手机号 + 验证码输入（复用 SMS 发送逻辑）
- 提交后调用 `/auth/bind-phone`
- 成功后关闭模态框，设置认证状态

**修改 `autonome-studio/src/app/login/page.tsx`**:
- OAuth 回调后检测 `requires_binding` 状态
- 触发 BindPhoneModal

---

## 3. 忘记密码/密码重置流（工作流 G）

**问题**: 完全缺失。用户忘记密码后无法找回账号。

### 后端变更

**`app/core/security.py` 新增**:
- `create_reset_token(user_id)` — 生成密码重置 JWT（10分钟，scope=reset_password）
- `verify_reset_token(token)` — 解析并验证 reset_token

**`app/api/routes/auth.py` 新增端点**:
- `POST /auth/forgot-password/send` — 接收手机号，发送 SMS OTP
  - 风控检查（复用现有 check_sms_rate_limit）
  - 生成 OTP 并发送
  - 返回确认信息
- `POST /auth/forgot-password/verify` — 接收手机号 + OTP
  - 验证 OTP
  - 查找用户
  - 下发 `reset_token`
- `POST /auth/reset-password` — 接收 `reset_token` + `new_password`
  - 验证 reset_token
  - 密码强度验证
  - 更新密码
  - **撤销该用户所有 ActiveSession**（安全动作）
  - 返回成功

### 前端变更

**新增 `autonome-studio/src/app/forgot-password/page.tsx`**:
- 三步流程：输入手机号 → 输入验证码 → 设置新密码
- 复用 SMS 发送组件逻辑

**修改 `autonome-studio/src/app/login/page.tsx`**:
- 密码登录 Tab 添加"忘记密码？"链接

---

## 4. 安全邮箱绑定流（工作流 E）

**问题**: 完全缺失。用户无法绑定安全邮箱作为账号恢复通道。

### 后端变更

**`app/api/routes/auth.py` 新增端点**:
- `POST /auth/bind-email` — 已登录用户请求绑定邮箱
  - 接收 `email` + `current_password`（本人校验）
  - 验证密码正确
  - 生成 `email_verification_token`（JWT，15分钟，包含 email + user_id）
  - 通过 Celery 异步发送验证邮件
  - 返回确认信息
- `POST /auth/verify-email` — 验证邮箱
  - 接收 `token`
  - 验证 token 有效性
  - 更新 User 的 `email` 和 `is_email_verified`
  - 返回成功

**邮件服务**: 新增 `app/services/email_service.py`
- 封装邮件发送逻辑（SMTP 或第三方服务）
- 支持发送验证链接邮件

### 前端变更

**修改 `SecurityPanel.tsx`**:
- 添加"安全邮箱"卡片
- 显示当前邮箱绑定状态
- 绑定流程：输入邮箱 → 验证密码 → 发送验证邮件 → 提示用户查收邮件

---

## 5. 密码修改时撤销其他会话（工作流 F 安全动作）

**问题**: 当前 `users.py` 的密码修改端点没有撤销其他设备的会话。

### 后端变更

**修改 `autonome-backend/app/api/routes/users.py`**:
- `change_password` 端点在密码更新成功后，在同一事务中：
  - 撤销该用户所有 `ActiveSession`（`is_revoked = True`）
  - 清除认证 Cookie
- 返回提示"密码已修改，其他设备已下线，请重新登录"

---

## 6. 设备管理前端 UI

**问题**: 后端已有 `/auth/sessions` 和 `/auth/sessions/{id}/revoke` 端点，但前端 SecurityPanel 缺少设备管理面板。

### 前端变更

**修改 `SecurityPanel.tsx`**:
- 添加"在线设备管理"卡片
- 调用 `GET /auth/sessions` 获取设备列表
- 每个设备显示：设备类型图标、User-Agent、IP、登录时间
- 当前设备标记"（当前设备）"
- 其他设备显示"下线"按钮，调用 `POST /auth/sessions/{id}/revoke`

---

## 实施顺序

1. OAuthAccount 模型字段修复 + 迁移（基础设施）
2. OAuth 强制手机号绑定流（安全闭环）
3. 忘记密码/密码重置流（灾难恢复）
4. 安全邮箱绑定流（防失联）
5. 密码修改撤销会话（安全加固）
6. 设备管理前端 UI（用户体验）

## 向后兼容保证

- 旧的邮箱+密码登录端点（`/auth/register`, `/auth/login`）保持不变
- 已关联 OAuth 账号的用户登录行为不变
- 所有新增端点为独立路径，不影响现有 API
- 前端新增组件为独立模块，不修改现有组件核心逻辑
