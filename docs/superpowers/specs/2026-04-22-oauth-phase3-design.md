# Phase 3: OAuth 第三方登录设计

## 概述

阶段三实现 GitHub OAuth + 微信扫码登录，前端登录页重构为多 Tab 模式。

## 后端设计

### 新增路由模块: `app/api/routes/oauth.py`

与 `auth.py` 分离，职责清晰。

### 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/oauth/github/callback` | GET | GitHub 回调，code 换 token，自动注册/登录 |
| `/api/oauth/wechat/qr-url` | GET | 获取微信扫码登录 URL |
| `/api/oauth/wechat/callback` | GET | 微信回调，自动注册/登录 |
| `/api/oauth/bind` | POST | 已登录用户绑定 OAuth 账号 |
| `/api/oauth/unbind` | POST | 已登录用户解绑 OAuth 账号 |
| `/api/oauth/accounts` | GET | 查询当前用户已绑定的 OAuth 账号 |

### OAuth 流程

**GitHub:**
1. 前端跳转 GitHub 授权页（`https://github.com/login/oauth/authorize`）
2. 用户授权后 GitHub 回调 `/api/oauth/github/callback?code=xxx`
3. 后端用 code 换 access_token，获取 GitHub 用户信息
4. 查找 OAuthAccount(provider='github', provider_account_id=github_id)
5. 已关联：签发 AT+RT，设置 Cookie，重定向到前端
6. 未关联：自动创建 User + OAuthAccount，签发 AT+RT，重定向到前端

**微信（预留接口）:**
1. 前端请求 `/api/oauth/wechat/qr-url` 获取扫码 URL
2. 用户扫码后微信回调 `/api/oauth/wechat/callback?code=xxx`
3. 后端用 code 换 access_token + openid
4. 关联/注册逻辑同 GitHub

### 账号关联规则

- 首次 OAuth 登录：自动创建 User（email 从 GitHub 获取，hashed_password=None），创建 OAuthAccount
- 已有账号绑定：已登录用户通过 `/oauth/bind` 端点绑定
- 解绑：至少保留一种登录方式（密码或至少一个 OAuth），防止账号无法登录
- 同一 GitHub/微信账号不能绑定到多个 Autonome 用户

### 配置项

- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`

## 前端设计

### 登录页重构

多 Tab 模式：
1. 邮箱密码登录
2. 手机验证码登录
3. GitHub 登录（跳转按钮）
4. 微信登录（扫码按钮，预留）

### OAuth 账号管理

用户设置页新增 OAuth 账号绑定/解绑功能。
