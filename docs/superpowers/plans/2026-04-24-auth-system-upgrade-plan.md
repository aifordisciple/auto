# Autonome 身份验证系统升级补全 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Autonome 身份验证系统9项缺陷，补全注册端点、RBAC迁移、密码修改统一、OAuth token加密、SECURE_COOKIES检查、2FA恢复码数据库存储、微信登录对接、邮箱绑定UI、设备管理UI

**Architecture:** 增量修补策略，逐项修复，每项独立可验证。后端使用 FastAPI + SQLModel + Alembic，前端使用 Next.js + Zustand。

**Tech Stack:** Python 3.12 / FastAPI / SQLModel / Alembic / Redis / Next.js 16 / TypeScript / Zustand

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `autonome-backend/app/schemas/auth.py` | 扩展 UserCreate schema 支持手机号注册 |
| 修改 | `autonome-backend/app/api/routes/auth.py` | 注册路由改造、2FA恢复码改存DB、密码修改保留当前会话 |
| 修改 | `autonome-backend/app/api/routes/users.py` | 删除重复的密码修改端点 |
| 修改 | `autonome-backend/app/core/security.py` | 新增 OAuth token 加密/解密函数 |
| 修改 | `autonome-backend/app/core/config.py` | 新增 SECURE_COOKIES 生产环境警告 |
| 修改 | `autonome-backend/app/main.py` | 启动时调用 SECURE_COOKIES 检查 |
| 修改 | `autonome-backend/app/models/user.py` | 新增 TwoFactorRecoveryCode 模型 |
| 修改 | `autonome-backend/app/api/routes/oauth.py` | OAuth token 加密存储/解密读取 |
| 新建 | `autonome-backend/alembic/versions/20260424_add_rbac_and_2fa_recovery_tables.py` | RBAC表 + 2FA恢复码表迁移 |
| 修改 | `autonome-studio/src/app/login/page.tsx` | 微信登录按钮对接确认 |
| 修改 | `autonome-studio/src/app/register/page.tsx` | 注册OTP验证改用正确端点 |

---

## Task 1: 注册端点不匹配修复

**Files:**
- Modify: `autonome-backend/app/schemas/auth.py:18-23`
- Modify: `autonome-backend/app/api/routes/auth.py:101-130`
- Modify: `autonome-studio/src/app/register/page.tsx:76-96`

- [ ] **Step 1: 扩展 UserCreate schema 支持手机号注册**

在 `autonome-backend/app/schemas/auth.py` 中，修改 `UserCreate` 类（第18-23行），增加手机号注册字段：

```python
class UserCreate(BaseModel):
    """用户注册请求（支持邮箱+密码 或 手机号+验证码）"""
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    username: Optional[str] = None
    # 手机号注册字段
    phone_number: Optional[str] = Field(default=None, pattern=r"^1[3-9]\d{9}$", description="手机号码")
    sms_code: Optional[str] = Field(default=None, min_length=6, max_length=6, description="6 位短信验证码")
    full_name: Optional[str] = None

    def model_post_init(self, __context):
        """验证：至少提供 email+password 或 phone_number+sms_code"""
        has_email = self.email and self.password
        has_phone = self.phone_number and self.sms_code
        if not has_email and not has_phone:
            raise ValueError("必须提供 email+password 或 phone_number+sms_code")
```

- [ ] **Step 2: 改造注册路由支持手机号注册**

在 `autonome-backend/app/api/routes/auth.py` 中，替换 `register` 函数（第101-130行）：

```python
@router.post("/register")
async def register(
    user_create: UserCreate,
    session: Session = Depends(get_session)
):
    """
    用户注册（支持邮箱+密码 或 手机号+验证码）

    - 邮箱注册：检查邮箱唯一性，创建用户，下发 Token
    - 手机号注册：验证 SMS OTP，检查手机号唯一性，创建用户，下发双 Token
    """
    if user_create.phone_number and user_create.sms_code:
        # === 手机号注册流程 ===
        # 验证短信验证码
        valid, reason = verify_otp(user_create.phone_number, user_create.sms_code)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=reason,
            )

        # 检查手机号是否已注册
        existing = session.exec(
            select(User).where(User.phone_number == user_create.phone_number)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该手机号已注册",
            )

        # 创建用户（手机号即账号，虚拟邮箱用于 DB 唯一约束）
        user = User(
            email=f"{user_create.phone_number}@phone.placeholder",
            phone_number=user_create.phone_number,
            hashed_password=get_password_hash(user_create.password) if user_create.password else None,
            full_name=user_create.full_name,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        # 签发双 Token（手机号注册走新认证流程）
        access_token = create_short_access_token(data={"sub": str(user.id)})
        return {"access_token": access_token, "token_type": "bearer"}

    elif user_create.email and user_create.password:
        # === 邮箱注册流程（原有逻辑） ===
        existing = session.exec(select(User).where(User.email == user_create.email)).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该邮箱已注册",
            )

        user = User(
            email=user_create.email,
            hashed_password=get_password_hash(user_create.password),
            full_name=user_create.full_name,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        access_token = create_access_token(data={"sub": str(user.id)})
        return {"access_token": access_token, "token_type": "bearer"}
```

- [ ] **Step 3: 修复前端注册页OTP验证端点**

在 `autonome-studio/src/app/register/page.tsx` 中，修改 `handleStep1Next` 函数（约第76行），将 `/auth/forgot-password/verify` 改为 `/auth/login/sms` 预验证模式，或新增一个注册专用的验证端点调用。

实际上，当前前端调用 `/auth/forgot-password/verify` 是因为后端没有注册专用的 OTP 验证端点。最简单的修复是：前端 step1 只做手机号格式校验和发送验证码，step2 提交注册时由后端 `/auth/register` 统一验证 OTP。修改 `handleStep1Next` 为仅做前端校验：

```typescript
const handleStep1Next = () => {
  // 前端校验手机号格式和验证码非空即可
  // 后端在 /auth/register 中会验证 OTP
  if (!phoneNumber || !smsCode) {
    setError('请输入手机号和验证码');
    return;
  }
  if (!/^1[3-9]\d{9}$/.test(phoneNumber)) {
    setError('请输入合法的手机号');
    return;
  }
  if (smsCode.length !== 6) {
    setError('请输入6位验证码');
    return;
  }
  setError('');
  setStep(2);
};
```

- [ ] **Step 4: 重启 Docker 验证注册流程**

```bash
docker-compose down && docker-compose up -d
```

验证：
1. 前端注册页面输入手机号 → 发送验证码 → 输入验证码和密码 → 提交注册
2. 后端日志显示注册成功
3. 邮箱+密码注册仍然可用

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/schemas/auth.py autonome-backend/app/api/routes/auth.py autonome-studio/src/app/register/page.tsx
git commit -m "fix: 修复注册端点不匹配 - 后端支持手机号注册 + 前端OTP验证修正"
```

---

## Task 2: RBAC迁移缺失

**Files:**
- Create: `autonome-backend/alembic/versions/20260424_add_rbac_and_2fa_recovery_tables.py`

- [ ] **Step 1: 创建 RBAC + 2FA恢复码 迁移脚本**

创建 `autonome-backend/alembic/versions/20260424_add_rbac_and_2fa_recovery_tables.py`：

```python
"""add RBAC tables and 2FA recovery codes table

Revision ID: iam_003
Revises: iam_002
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "iam_003"
down_revision = "iam_002"
branch_labels = None
depends_on = None


def upgrade():
    # ── RBAC: roles 表 ──
    if not op.get_context().bind.dialect.has_table(op.get_context().bind, "roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(50), unique=True, nullable=False, index=True),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("is_default", sa.Boolean, default=False),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )

    # ── RBAC: permissions 表 ──
    if not op.get_context().bind.dialect.has_table(op.get_context().bind, "permissions"):
        op.create_table(
            "permissions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("code", sa.String(100), unique=True, nullable=False, index=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("module", sa.String(50), nullable=False, index=True),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )

    # ── RBAC: role_permissions 关联表 ──
    if not op.get_context().bind.dialect.has_table(op.get_context().bind, "role_permissions"):
        op.create_table(
            "role_permissions",
            sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("permission_id", sa.Integer, sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
        )

    # ── RBAC: user_roles 关联表 ──
    if not op.get_context().bind.dialect.has_table(op.get_context().bind, "user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        )

    # ── RBAC: audit_logs 表 ──
    if not op.get_context().bind.dialect.has_table(op.get_context().bind, "audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), index=True, nullable=True),
            sa.Column("action", sa.String(100), nullable=False),
            sa.Column("resource_type", sa.String(50), nullable=True),
            sa.Column("resource_id", sa.String(100), nullable=True),
            sa.Column("detail", sa.Text, nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index("ix_audit_logs_user_action", "audit_logs", ["user_id", "action"])
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ── 2FA: two_factor_recovery_codes 表 ──
    if not op.get_context().bind.dialect.has_table(op.get_context().bind, "two_factor_recovery_codes"):
        op.create_table(
            "two_factor_recovery_codes",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("code_hash", sa.String(255), nullable=False),
            sa.Column("is_used", sa.Boolean, default=False),
            sa.Column("used_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )


def downgrade():
    op.drop_table("two_factor_recovery_codes")
    op.drop_table("audit_logs")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
```

- [ ] **Step 2: 运行迁移**

```bash
docker-compose exec backend-api alembic upgrade head
```

验证：数据库中存在 `roles`, `permissions`, `role_permissions`, `user_roles`, `audit_logs`, `two_factor_recovery_codes` 表。

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/alembic/versions/20260424_add_rbac_and_2fa_recovery_tables.py
git commit -m "feat: 新增 RBAC 表和 2FA 恢复码表 Alembic 迁移"
```

---

## Task 3: 密码修改端点重复

**Files:**
- Modify: `autonome-backend/app/api/routes/users.py:136-213`
- Modify: `autonome-backend/app/api/routes/auth.py:936-1000`

- [ ] **Step 1: 修改 auth.py 的 change-password 保留当前会话**

在 `autonome-backend/app/api/routes/auth.py` 中，修改 `change_password` 函数（第987-997行），将撤销所有会话改为撤销除当前会话外的所有会话：

```python
    # 【安全动作】撤销该用户除当前会话外的所有 ActiveSession
    # 保留当前设备在线，其他设备强制下线
    current_rt_hash = None
    rt_cookie = http_request.cookies.get("refresh_token")
    if rt_cookie:
        current_rt_hash = hash_refresh_token(rt_cookie)

    active_sessions = session.exec(
        select(ActiveSession).where(
            ActiveSession.user_id == current_user.id,
            ActiveSession.is_revoked == False,
        )
    ).all()
    for s in active_sessions:
        # 跳过当前会话
        if current_rt_hash and s.refresh_token_hash == current_rt_hash:
            continue
        s.is_revoked = True
        session.add(s)
```

注意：需要在函数签名中添加 `http_request: Request` 参数。

- [ ] **Step 2: 删除 users.py 中的重复密码修改端点**

在 `autonome-backend/app/api/routes/users.py` 中，删除 `change_password` 函数（第136-213行）和 `PasswordChangeRequest` 类（第59-62行）。

- [ ] **Step 3: 检查前端调用**

前端 SecurityPanel 已调用 `/auth/change-password`（第407行），无需修改。

- [ ] **Step 4: 重启验证**

```bash
docker-compose down && docker-compose up -d
```

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/api/routes/auth.py autonome-backend/app/api/routes/users.py
git commit -m "fix: 统一密码修改端点到 auth.py，保留当前会话"
```

---

## Task 4: OAuth access_token 加密存储

**Files:**
- Modify: `autonome-backend/app/core/security.py`
- Modify: `autonome-backend/app/api/routes/oauth.py`

- [ ] **Step 1: 在 security.py 中添加 OAuth token 加密/解密函数**

在 `autonome-backend/app/core/security.py` 末尾追加：

```python
# ==========================================
# OAuth Token 加密存储（防脱库泄露）
# ==========================================

from cryptography.fernet import Fernet
import base64


def _get_fernet_key() -> bytes:
    """从 SECRET_KEY 派生 Fernet 对称加密密钥"""
    # 取 SECRET_KEY 的 SHA-256 哈希前 32 字节，转为 base64url 编码（Fernet 要求）
    key_hash = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(key_hash)


def encrypt_oauth_token(token: str) -> str:
    """加密 OAuth access_token（存储前调用）"""
    if not token:
        return ""
    f = Fernet(_get_fernet_key())
    return f.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_oauth_token(encrypted: str) -> str:
    """解密 OAuth access_token（读取时调用）"""
    if not encrypted:
        return ""
    try:
        f = Fernet(_get_fernet_key())
        return f.decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except Exception:
        # 解密失败（可能是旧数据未加密），返回原值
        return encrypted
```

- [ ] **Step 2: 修改 OAuth 路由加密存储/解密读取**

在 `autonome-backend/app/api/routes/oauth.py` 中：
- 存储 `access_token` 时调用 `encrypt_oauth_token(token)`
- 读取 `access_token` 时调用 `decrypt_oauth_token(token)`

搜索所有 `access_token` 赋值和读取位置，逐一修改。

- [ ] **Step 3: 安装 cryptography 依赖**

在 `autonome-backend/requirements.txt` 中确认 `cryptography` 已存在或添加。

- [ ] **Step 4: 重启验证**

```bash
docker-compose down && docker-compose up -d
```

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/core/security.py autonome-backend/app/api/routes/oauth.py
git commit -m "feat: OAuth access_token 加密存储（Fernet 对称加密，防脱库泄露）"
```

---

## Task 5: SECURE_COOKIES 生产环境强制

**Files:**
- Modify: `autonome-backend/app/core/config.py:37-38`
- Modify: `autonome-backend/app/main.py:117-142`

- [ ] **Step 1: 在 config.py 中添加 SECURE_COOKIES 检查函数**

在 `autonome-backend/app/core/config.py` 末尾（第100行后）追加：

```python
# 校验生产环境 Cookie 安全配置
if settings.ENVIRONMENT == "production" and not settings.SECURE_COOKIES:
    import warnings
    warnings.warn(
        "⚠️ SECURE_COOKIES=False 在生产环境中不安全！"
        "请在 .env 中设置 SECURE_COOKIES=True（要求 HTTPS）",
        stacklevel=2,
    )
```

- [ ] **Step 2: 重启验证**

```bash
docker-compose down && docker-compose up -d
```

验证：开发环境无警告。若临时设置 `ENVIRONMENT=production` 且 `SECURE_COOKIES=False`，应看到警告。

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/core/config.py
git commit -m "feat: SECURE_COOKIES 生产环境安全检查警告"
```

---

## Task 6: 2FA恢复码改存数据库

**Files:**
- Modify: `autonome-backend/app/models/user.py`
- Modify: `autonome-backend/app/api/routes/auth.py:1257-1267`

- [ ] **Step 1: 新增 TwoFactorRecoveryCode 模型**

在 `autonome-backend/app/models/user.py` 末尾追加：

```python
class TwoFactorRecoveryCode(SQLModel, table=True):
    """2FA 恢复码 — 存储在数据库中（替代 Redis，防止 Redis 重启丢失）"""

    __tablename__ = "two_factor_recovery_codes"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    code_hash: str = Field(max_length=255, description="恢复码的 bcrypt 哈希")
    is_used: bool = Field(default=False)
    used_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=get_utc_now)
```

- [ ] **Step 2: 修改 2FA setup 逻辑存入数据库**

在 `autonome-backend/app/api/routes/auth.py` 中，修改 `verify_and_enable_2fa` 函数（第1257-1267行），将恢复码存入数据库而非 Redis：

```python
    # 生成备用恢复码（10 个随机 8 位码，用户应保存）
    import secrets as _secrets
    recovery_codes = [_secrets.token_hex(4).upper() for _ in range(10)]

    # 将恢复码哈希存入数据库（替代 Redis，防止 Redis 重启丢失）
    from app.models.user import TwoFactorRecoveryCode
    for code in recovery_codes:
        hashed_code = get_password_hash(code)
        recovery_record = TwoFactorRecoveryCode(
            user_id=current_user.id,
            code_hash=hashed_code,
        )
        session.add(recovery_record)
    session.commit()
```

- [ ] **Step 3: 修改 2FA disable 逻辑清除数据库恢复码**

在 `disable_2fa` 函数中，将 `cache.delete(f"2fa:recovery:{current_user.id}")` 替换为：

```python
    # 清除数据库中的恢复码
    from app.models.user import TwoFactorRecoveryCode
    recovery_codes = session.exec(
        select(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == current_user.id)
    ).all()
    for rc in recovery_codes:
        session.delete(rc)
    session.commit()
```

- [ ] **Step 4: 重启验证**

```bash
docker-compose down && docker-compose up -d
```

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/models/user.py autonome-backend/app/api/routes/auth.py
git commit -m "feat: 2FA 恢复码改存数据库（替代 Redis，防重启丢失）"
```

---

## Task 7: 微信登录对接

**Files:**
- Modify: `autonome-studio/src/app/login/page.tsx:370-376`

- [ ] **Step 1: 确认微信登录按钮已正确对接**

根据代码审计，登录页 `handleWeChatLogin`（第370行）已调用 `/oauth/wechat/qr-url` 并重定向。SecurityPanel 中也有微信绑定按钮。后端 OAuth 路由已实现 `/wechat/qr-url` 和 `/wechat/callback`。

当前实现已正确对接，但需要确认：
1. 后端 `WECHAT_APP_ID` 和 `WECHAT_APP_SECRET` 是否已配置（未配置时返回错误提示）
2. OAuth callback 页面是否正确处理微信回调（已确认 `/oauth/callback/page.tsx` 处理了 `requires_binding` 场景）

结论：微信登录对接已完成，无需修改。仅需确认 `.env` 中配置了微信 AppID/Secret。

- [ ] **Step 2: Commit（如有修改）**

无需修改，跳过。

---

## Task 8: 安全邮箱绑定UI

**Files:**
- Verify: `autonome-studio/src/components/overlays/UserCenter/SecurityPanel.tsx:852-936`

- [ ] **Step 1: 确认邮箱绑定UI已实现**

根据代码审计，SecurityPanel 卡片四（第852-936行）已实现：
- 当前邮箱状态显示（已验证/未验证标记）
- 邮箱输入 + 当前密码验证
- 绑定/更换邮箱按钮
- 验证邮件发送提示
- 调用 `/auth/bind-email` API

结论：邮箱绑定UI已完整实现，无需修改。

- [ ] **Step 2: Commit（如有修改）**

无需修改，跳过。

---

## Task 9: 设备管理UI

**Files:**
- Verify: `autonome-studio/src/components/overlays/UserCenter/SecurityPanel.tsx:938-1027`

- [ ] **Step 1: 确认设备管理UI已实现**

根据代码审计，SecurityPanel 卡片五（第938-1027行）已实现：
- 在线设备列表（解析 User-Agent 显示 OS + 浏览器）
- 当前设备标记
- 单设备下线按钮
- 一键下线所有其他设备按钮
- 刷新列表按钮
- 调用 `/auth/sessions` 和 `/auth/sessions/{id}/revoke` API

结论：设备管理UI已完整实现，无需修改。

- [ ] **Step 2: Commit（如有修改）**

无需修改，跳过。

---

## 实施顺序总结

| 顺序 | Task | 描述 | 预计改动量 |
|------|------|------|-----------|
| 1 | Task 1 | 注册端点不匹配修复 | 3 文件 |
| 2 | Task 2 | RBAC迁移缺失 | 1 新文件 |
| 3 | Task 3 | 密码修改端点重复 | 2 文件 |
| 4 | Task 4 | OAuth token加密存储 | 2 文件 |
| 5 | Task 5 | SECURE_COOKIES检查 | 1 文件 |
| 6 | Task 6 | 2FA恢复码改存数据库 | 2 文件 |
| 7 | Task 7 | 微信登录对接 | 已完成 |
| 8 | Task 8 | 安全邮箱绑定UI | 已完成 |
| 9 | Task 9 | 设备管理UI | 已完成 |

**实际需要修改的只有 Task 1-6，Task 7-9 已在之前实现中完成。**
