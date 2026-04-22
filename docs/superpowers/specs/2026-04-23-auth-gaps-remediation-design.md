# 身份验证系统缺口补齐设计

## 背景

对照 `docs/modules/身份验证系统.md` 需求文档，系统已完成阶段1-4的核心工作和阶段5的OAuth。但存在以下高+中严重度缺口需要补齐。

## 缺口清单与优先级

| # | 缺口 | 严重度 | 模块 |
|---|------|--------|------|
| 1 | `settings.BASE_URL` 未定义导致OAuth运行时崩溃 | 高 | M1 |
| 2 | 2FA/TOTP 端点完全缺失 | 高 | M3 |
| 3 | 2FA 前端UI完全缺失 | 高 | M4 |
| 4 | 手机号修改无SMS验证（安全漏洞） | 高 | M6 |
| 5 | 会话内修改密码端点缺失（工作流F） | 中 | M5 |
| 6 | Schema内联在路由文件中 | 中 | M2 |
| 7 | 邮箱验证落地页缺失 | 中 | M7 |
| 8 | 无Next.js路由中间件保护 | 中 | M8 |

## 模块设计

### M1：修复 `settings.BASE_URL` 缺失

**问题：** `oauth.py` 引用 `settings.BASE_URL` 构造OAuth回调URL，但Settings类未定义此属性，运行时 `AttributeError`。

**方案：**
- 在 `app/core/config.py` Settings类中添加 `BASE_URL: str = "http://localhost:8000"`
- 环境变量 `BASE_URL` 覆盖默认值
- 检查 `.env` 和 `docker-compose.yml` 是否需要配置生产环境URL
- 纯bug修复，零风险

### M2：Schema 模块化

**问题：** 15+个Pydantic model内联在 `auth.py` 路由文件中，代码组织混乱。

**方案：**
- 创建 `app/schemas/auth.py`，提取所有auth相关schema：
  - `UserCreate`, `SMSLoginRequest`, `PasswordLoginRequest`, `EmailLoginRequest`
  - `SendSMSRequest`, `BindPhoneRequest`, `LoginResponse`, `RefreshResponse`
  - `ActiveSessionOut`, `UserInfo`, `ForgotPasswordSendRequest`, `ForgotPasswordVerifyRequest`
  - `ResetPasswordRequest`, `BindEmailRequest`, `VerifyEmailRequest`
  - 新增schema：`ChangePasswordRequest`, `ChangePhoneRequest`, `2FASetupResponse`, `2FAVerifyRequest`, `2FADisableRequest`, `2FALoginRequest`
- 创建 `app/schemas/oauth.py`，提取oauth相关schema
- `auth.py` 和 `oauth.py` 改为从对应schema模块导入
- 纯代码组织改动，不改变任何业务逻辑

### M3：2FA/TOTP 后端端点

**问题：** User模型有 `is_2fa_enabled` 和 `two_factor_secret` 字段但无API端点。

**方案：** 新增4个端点：

1. **`POST /api/auth/2fa/setup`** — 生成TOTP密钥
   - 需要已登录用户
   - 使用 `pyotp` 生成随机密钥
   - 返回 `{"secret": "<base32密钥>", "qr_uri": "otpauth://totp/Autonome:<email>?secret=<secret>&issuer=Autonome"}`
   - 密钥暂存Redis `2fa:setup:{user_id}` TTL=5分钟，不直接写入数据库（防止用户放弃设置导致脏数据）

2. **`POST /api/auth/2fa/verify`** — 验证并启用2FA
   - 输入：`secret`（从setup返回的）, `totp_code`（用户输入的6位码）
   - 使用 `pyotp.TOTP(secret).verify(totp_code)` 验证
   - 验证通过后：将密钥写入 `user.two_factor_secret`，设置 `user.is_2fa_enabled = True`
   - 删除Redis临时密钥
   - 返回备用恢复码（10个随机8位码，用户应保存）

3. **`POST /api/auth/2fa/disable`** — 禁用2FA
   - 输入：`totp_code`
   - 验证当前TOTP码
   - 设置 `user.is_2fa_enabled = False`，清空 `user.two_factor_secret`

4. **`POST /api/auth/2fa/login`** — 2FA登录验证
   - 输入：`mfa_token`（临时JWT）, `totp_code`
   - 验证 `mfa_token` 的scope为 `mfa_challenge`
   - 使用 `pyotp.TOTP(user.two_factor_secret).verify(totp_code)` 验证
   - 验证通过后下发正式双Token（Access Token + Refresh Token + HttpOnly Cookie）

**登录流程改造：**
- `/auth/login/sms` 和 `/auth/login/password` 中，如果 `user.is_2fa_enabled == True`：
  - 不下发正式Token
  - 返回 `{"status": "requires_2fa", "mfa_token": "<临时JWT, 5分钟, scope=mfa_challenge>", "user_id": "<uuid>"}`
  - 前端跳转到2FA验证步骤

**依赖：** 安装 `pyotp` 包。

**security.py 新增：**
- `create_mfa_token(user_id)` — 生成MFA挑战JWT，5分钟有效期，scope=mfa_challenge
- `verify_mfa_token(token)` — 验证MFA挑战JWT

### M4：2FA 前端UI

**问题：** SecurityPanel只有禁用的占位符toggle。

**方案：**

1. **SecurityPanel改造：**
   - 启用2FA toggle（从disabled改为可点击）
   - 点击后弹出 `TwoFASetupModal`：
     - 调用 `/auth/2fa/setup` 获取QR URI和密钥
     - 使用 `qrcode.react` 库渲染QR码
     - 用户用Authenticator App扫码
     - 输入6位验证码确认启用，调用 `/auth/2fa/verify`
     - 显示备用恢复码，提示用户保存
   - 禁用2FA按钮：需输入当前TOTP码确认，调用 `/auth/2fa/disable`

2. **登录流程改造：**
   - 登录接口返回 `requires_2fa` 时，弹出 `TwoFAVerifyModal`
   - 输入6位TOTP码后调用 `/auth/2fa/login`
   - 成功后完成登录流程（保存token、跳转）

**依赖：** 安装 `qrcode.react` npm包。

### M5：会话内修改密码端点

**问题：** 只有忘记密码流程，没有已登录用户修改密码的端点（需求文档工作流F）。

**方案：** 新增 `POST /api/auth/change-password`：

- 输入：`old_password`, `new_password`
- 验证旧密码哈希（`verify_password(old_password, user.hashed_password)`）
- 如果用户无密码（`hashed_password` 为 None），拒绝修改，提示先设置密码
- 强密码策略检查：至少8位，包含大小写字母与数字
- 更新密码哈希
- **关键安全动作：** 在同一数据库事务中：
  - 将该用户除当前session外的所有 `active_sessions` 标记为 `is_revoked = True`
  - 更新 `user.last_password_change = datetime.utcnow()`
- 返回新的Access Token（当前session不受影响）

**前端：** SecurityPanel已有密码修改UI（旧密码+新密码+确认密码表单），只需对接新端点 `/auth/change-password` 替换当前的 `PUT /users/me/password`。

### M6：手机号修改SMS验证

**问题：** ProfilePanel允许直接编辑phone_number为纯文本，无SMS验证，安全漏洞。

**方案：**

**后端：** 新增 `POST /api/auth/change-phone`：
- 输入：`new_phone`, `otp_code`, `current_password`
- 验证当前密码
- 验证新手机号的SMS OTP（复用现有 `verify_otp` 逻辑）
- 检查新手机号是否已被其他用户占用
- 更新 `user.phone_number`

**前端：**
- ProfilePanel：手机号字段改为只读显示，旁边加"修改"按钮
- 点击弹出 `ChangePhoneModal`：
  - 输入新手机号 → 发送验证码（调用 `/auth/send-sms`，需新增参数区分是修改手机号还是登录）
  - 输入验证码 + 输入当前密码 → 提交
  - 成功后更新store中的用户信息

**注意：** `/auth/send-sms` 需要支持已登录用户为新手机号发送验证码的场景。当前端点可能需要增加 `purpose` 参数（`login` vs `change_phone`）来区分。

### M7：邮箱验证落地页

**问题：** 后端有 `/auth/verify-email` 端点，但前端无页面处理邮件链接跳转。

**方案：** 新增 `autonome-studio/src/app/verify-email/page.tsx`：
- 从URL query参数读取 `token`
- 页面加载时自动调用 `POST /api/auth/verify-email` 传入token
- 显示验证状态：
  - 成功：绿色图标 + "邮箱验证成功" + 3秒后自动跳转首页
  - 失败：红色图标 + 错误信息 + "返回登录页"按钮
  - 加载中：spinner

**后端调整：** 确保 `/auth/bind-email` 发出的验证邮件链接指向 `{FRONTEND_URL}/verify-email?token=<verification_token>`。

### M8：Next.js路由中间件

**问题：** 路由保护纯客户端，用户可直接访问受保护路由。

**方案：** 新增 `autonome-studio/src/middleware.ts`：

```typescript
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const PUBLIC_PATHS = ['/login', '/forgot-password', '/verify-email', '/api'];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 公开路径放行
  if (PUBLIC_PATHS.some(path => pathname.startsWith(path))) {
    return NextResponse.next();
  }

  // 检查refresh_token Cookie是否存在
  const refreshToken = request.cookies.get('refresh_token');

  if (!refreshToken) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('redirect', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
```

**注意：** 这是轻量级路由守卫，只检查Cookie存在性。真正的鉴权仍由后端API完成。Next.js Edge Runtime无法读取HttpOnly Cookie的值，但可以检查Cookie是否存在。

## 实施顺序

按依赖关系排序：

1. **M1** (settings.BASE_URL) — 阻塞性bug，最先修
2. **M2** (Schema模块化) — 为后续模块提供schema基础
3. **M3** (2FA后端) — 为M4提供API基础
4. **M4** (2FA前端) — 依赖M3
5. **M5** (修改密码端点) — 独立模块
6. **M6** (手机号修改SMS验证) — 独立模块
7. **M7** (邮箱验证页) — 独立模块
8. **M8** (路由中间件) — 独立模块，最后加

## 不在本次范围内的项目

- 集中auth API客户端（低优先级代码组织优化）
- OAuth回调专用页面（低优先级）
- Session过期预警UI（低优先级）
- PII AES-256加密存储（需求文档提及但当前未实现，独立大模块）
- 企业SSO（SAML/OIDC）（需求文档标注为预留接口）