# 身份验证系统补全设计

日期: 2026-04-24
状态: 待审核

## 背景

对照 `docs/modules/身份验证系统.md` 规范文档，5 阶段升级的核心功能已全部实现。但审查发现 7 个差距需要补全，以确保系统完全符合规范要求。

## 差距清单与修复方案

### 1. Cloudflare Turnstile 人机验证集成 (高严重度)

**问题**: 规范要求"集成 Cloudflare Turnstile 或极验验证"，当前前端无 CAPTCHA 组件，后端 `/send-sms` 也不校验 captcha_token。

**修复方案**:

#### 后端变更

- `app/core/config.py`: 新增 `TURNSTILE_SECRET_KEY` 配置项（默认空，空则跳过校验）
- `app/api/routes/auth.py` `/send-sms` 端点:
  - `SendSMSRequest` schema 新增可选 `captcha_token` 字段
  - 当 `TURNSTILE_SECRET_KEY` 非空时，调用 Turnstile Siteverify API 校验 token
  - 校验失败返回 400 "人机验证失败，请重试"
- 新建 `app/services/turnstile_service.py`: 封装 Turnstile Siteverify API 调用

#### 前端变更

- `autonome-studio/src/components/TurnstileWidget.tsx`: 封装 Turnstile React 组件
  - 使用 `@cloudflare/turnstile-react` 或原生 script 加载
  - props: `siteKey`, `onVerify(token)`, `onError`, `onExpire`
  - 组件卸载时自动重置
- 登录页 `login/page.tsx`: SMS Tab 发送按钮前触发 Turnstile 验证，成功后将 token 传入 `/send-sms`
- 注册页 `register/page.tsx`: 同上
- `BindPhoneModal.tsx`: 同上
- 环境变量: `NEXT_PUBLIC_TURNSTILE_SITE_KEY`

**降级策略**: `TURNSTILE_SECRET_KEY` 为空时后端跳过校验，前端不渲染 Widget，确保开发环境不受影响。

---

### 2. "撤销所有其他会话"按钮 (中严重度)

**问题**: SecurityPanel 只能逐个踢人，规范要求"一键清理所有或指定终端会话"。

**修复方案**:

#### 后端变更

- `app/api/routes/auth.py` 新增端点:
  ```
  POST /auth/sessions/revoke-others
  ```
  - 需要认证 (`get_current_user`)
  - 撤销当前用户除当前 session 外的所有 `ActiveSession`
  - 通过 Cookie 中的 `refresh_token` 哈希匹配当前 session
  - 返回 `{"status": "success", "revoked_count": N}`

#### 前端变更

- `SecurityPanel.tsx` 设备管理卡片:
  - 当存在 2+ 个会话时，显示"下线所有其他设备"按钮（红色，带确认弹窗）
  - 调用 `/auth/sessions/revoke-others`，成功后刷新会话列表

---

### 3. 登录初始化校验 Hook (中严重度)

**问题**: 刷新页面后，localStorage 中持久化的 `isAuthenticated: true` 可能已过期（服务端已撤销 session），但前端不会主动校验。

**修复方案**:

#### 前端变更

- `useAuthStore.ts` 新增 `initializeAuth()` 方法:
  ```typescript
  initializeAuth: async () => {
    const { isAuthenticated, fetchProfile, clearAll } = get();
    if (!isAuthenticated) return; // 未登录，无需校验
    try {
      await fetchProfile(); // 调用 /auth/me 验证会话
    } catch {
      clearAll(); // 会话已失效，清除本地状态
    }
  }
  ```
- 在应用入口（`layout.tsx` 或顶层 Provider）调用 `initializeAuth()`
- 使用 `useEffect` + 空依赖数组，仅在应用启动时执行一次

**注意**: `fetchProfile` 已有失败时 `clearAll()` 的逻辑，所以 `initializeAuth` 本质上是确保应用启动时主动触发一次校验。

---

### 4. 限流错误友好提示 (中严重度)

**问题**: 后端风控已返回含时长的 reason（如"登录失败次数过多，请5分钟后重试"），但前端可能未完整展示。

**修复方案**:

#### 后端变更

- `auth_risk_control.py` 的 `check_login_risk` 已返回含时长的 reason，无需修改
- `auth.py` 的 `/login/password` 和 `/login` 端点已将 reason 作为 429 的 detail 返回，无需修改

#### 前端变更

- `fetchAPI` 的错误处理已正确提取 `detail` 字段（第 188 行），无需修改
- 登录页的错误展示已使用 `err.message`（第 233/267/299/339 行），无需修改
- **但需确认**: 429 状态码的 `detail` 是否被正确提取。当前 `fetchAPI` 第 183-193 行对非 200 响应统一处理，会提取 `errorData.detail`，所以 429 的 detail 已被正确传递。

**结论**: 此差距实际已通过后端返回详细 reason + 前端统一错误提取解决，无需额外代码修改。但需验证端到端流程。

---

### 5. 注册页隐私协议勾选 (低严重度)

**问题**: 规范要求"服务等级协议 (SLA) 与隐私保护声明 (PIPL/GDPR) 的强制勾选流程"。

**修复方案**:

#### 前端变更

- `register/page.tsx` Step 2 底部增加:
  - 复选框: "我已阅读并同意《服务条款》和《隐私政策》"
  - 未勾选时，注册按钮 disabled
  - 链接指向 `/terms` 和 `/privacy`（可后续创建页面内容）

---

### 6. 密码修改时间显示 (低严重度)

**问题**: SecurityPanel 的 `lastPasswordChange` 始终为 null，未从 API 获取。

**修复方案**:

#### 后端变更

- `auth.py` `_build_user_info()` 已包含 `created_at`，需新增 `last_password_change` 字段:
  ```python
  "last_password_change": user.last_password_change.isoformat() if user.last_password_change else None,
  ```

#### 前端变更

- `useAuthStore.ts` `UserState` 新增 `last_password_change: string | null`
- `fetchProfile()` 解析并存储 `last_password_change`
- `SecurityPanel.tsx` 使用 `user?.last_password_change` 替代当前的 `lastPasswordChange` 状态（移除无用的 useState）

---

### 7. OAuth 回调前端中间页 (中严重度)

**问题**: OAuth 回调直接由后端处理并重定向到前端，前端无法优雅处理 loading 状态和错误。

**修复方案**:

#### 前端变更

- 新增 `autonome-studio/src/app/oauth/callback/page.tsx`:
  - 作为 OAuth 回调的中间页
  - 读取 URL query 参数: `requires_binding`, `bind_ref`, `provider_name`, `oauth_error`
  - 显示 loading spinner（短暂过渡）
  - 如果有 `oauth_error`，显示错误提示并提供"返回登录"按钮
  - 如果有 `requires_binding`，重定向到 `/login?requires_binding=true&bind_ref=xxx&provider_name=xxx`
  - 否则重定向到 `/`

#### 后端变更

- `oauth.py` 的 GitHub/WeChat callback 端点:
  - 成功登录: 重定向到 `FRONTEND_URL/oauth/callback?status=success`
  - 需要绑定: 重定向到 `FRONTEND_URL/oauth/callback?requires_binding=true&bind_ref=xxx&provider_name=xxx`
  - 错误: 重定向到 `FRONTEND_URL/oauth/callback?oauth_error=xxx`

**注意**: 此变更需要修改后端 OAuth 回调的重定向目标。当前后端直接重定向到 `/login?xxx`，改为先到 `/oauth/callback` 中间页。

---

## 实施顺序

1. **后端: Turnstile 服务 + config** (差距1)
2. **后端: /sessions/revoke-others 端点** (差距2)
3. **后端: _build_user_info 增加 last_password_change** (差距6)
4. **后端: OAuth 回调重定向调整** (差距7)
5. **前端: Turnstile Widget 组件** (差距1)
6. **前端: 登录/注册/BindPhoneModal 集成 Turnstile** (差距1)
7. **前端: SecurityPanel 撤销所有会话按钮** (差距2)
8. **前端: useAuthStore initializeAuth** (差距3)
9. **前端: 注册页隐私协议勾选** (差距5)
10. **前端: SecurityPanel 密码修改时间** (差距6)
11. **前端: OAuth 回调中间页** (差距7)

## 风险控制

- 所有变更向后兼容：Turnstile 未配置时自动跳过
- 不修改任何现有端点的核心逻辑，仅新增端点和扩展现有 schema
- 前端变更均为增量修改，不替换现有组件
