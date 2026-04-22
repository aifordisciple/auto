# Autonome 外部服务配置指南

本文档说明 Autonome 身份验证系统所需的外部服务配置，包括阿里云 SMS 短信、GitHub OAuth 和微信开放平台登录。

---

## 1. 阿里云 SMS 短信服务

### 1.1 前提条件

- 已注册[阿里云账号](https://www.aliyun.com/)并完成实名认证
- 已开通短信服务（[控制台](https://dysms.console.aliyun.com/)）
- 已创建签名和模板并通过审核

### 1.2 创建签名

1. 登录 [短信服务控制台](https://dysms.console.aliyun.com/)
2. 进入「国内消息」→「签名管理」→「添加签名」
3. 填写签名名称（如 `Autonome`），选择用途为「验证码」
4. 等待审核通过（通常 2 小时内）

### 1.3 创建模板

1. 进入「国内消息」→「模板管理」→「添加模板」
2. 模板类型选择「验证码」
3. 模板内容示例：

```
您的验证码为${code}，${expire}分钟内有效，请勿泄露给他人。
```

4. 审核通过后记录**模板编码**（如 `SMS_123456789`）

### 1.4 获取 AccessKey

1. 登录阿里云控制台，鼠标悬停右上角头像 → 点击「AccessKey 管理」
2. 建议创建 RAM 子用户，仅授权 `AliyunDysmsFullAccess` 权限
3. 记录 **AccessKey ID** 和 **AccessKey Secret**

### 1.5 配置环境变量

在 `autonome-backend/.env` 中添加：

```bash
# 阿里云短信服务
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret
ALIYUN_SMS_SIGN_NAME=Autonome          # 签名名称，需与控制台一致
ALIYUN_SMS_TEMPLATE_CODE=SMS_123456789  # 模板编码
```

### 1.6 风控参数

短信发送内置以下风控规则（代码级配置，无需修改环境变量）：

| 规则 | 限制 | 说明 |
|------|------|------|
| 单号冷却 | 60 秒 | 同一手机号 60 秒内只能发送一次 |
| 单号日限 | 10 条 | 同一手机号每天最多 10 条 |
| IP 日限 | 50 条 | 同一 IP 每天最多 50 条 |
| 登录失败 | 5 次/15 分钟 | 超过则锁定 15 分钟 |

### 1.7 验证

配置完成后，可通过登录页「验证码登录」功能测试。后端日志中会输出短信发送结果：

```
docker logs autonome-api 2>&1 | grep -i sms
```

---

## 2. GitHub OAuth 登录

### 2.1 前提条件

- 已注册 [GitHub 账号](https://github.com/)
- 对组织/个人账号有 GitHub App 创建权限

### 2.2 创建 GitHub OAuth App

1. 登录 GitHub → 「Settings」→「Developer settings」→「OAuth Apps」→「New OAuth App」
2. 填写信息：

| 字段 | 值 | 说明 |
|------|------|------|
| Application name | `Autonome` | 应用显示名称 |
| Homepage URL | `http://113.44.66.210:3001` | 前端首页地址 |
| Authorization callback URL | `http://113.44.66.210:8000/api/oauth/github/callback` | 后端回调地址 |

3. 点击「Register application」
4. 记录 **Client ID**
5. 点击「Generate a new client secret」，记录 **Client Secret**（仅显示一次）

> **生产环境**：Homepage URL 和 Callback URL 需替换为正式域名（HTTPS）。

### 2.3 配置环境变量

在 `autonome-backend/.env` 中添加：

```bash
# GitHub OAuth
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
```

同时在 `.env` 中确认前端地址配置正确（OAuth 回调后重定向用）：

```bash
# 前端地址（OAuth 回调重定向目标）
FRONTEND_URL=http://113.44.66.210:3001

# Cookie 安全配置（生产环境 HTTPS 时设为 true）
COOKIE_SECURE=false
```

### 2.4 回调流程说明

```
用户点击「GitHub 登录」
  → 前端请求 GET /api/oauth/github/authorize-url 获取授权 URL
  → 浏览器跳转 GitHub 授权页
  → 用户授权后 GitHub 回调 /api/oauth/github/callback?code=xxx
  → 后端用 code 换 access_token，获取 GitHub 用户信息
  → 自动注册/登录，签发 AT+RT，设置 Cookie
  → 重定向到前端首页
```

### 2.5 账号关联规则

- **首次 GitHub 登录**：自动创建 Autonome 账号（邮箱从 GitHub 获取），创建 OAuthAccount 关联
- **邮箱匹配**：如果 GitHub 邮箱与已有 Autonome 账号一致，自动绑定
- **手动绑定**：已登录用户可在「安全设置」中绑定 GitHub 账号
- **解绑限制**：解绑后至少保留一种登录方式（密码或其他 OAuth），防止账号无法登录

### 2.6 验证

1. 访问登录页，点击底部「GitHub」按钮
2. 浏览器应跳转到 GitHub 授权页
3. 授权后自动跳回 Autonome 首页并完成登录

---

## 3. 微信开放平台扫码登录

### 3.1 前提条件

- 已注册[微信开放平台](https://open.weixin.qq.com/)账号
- 已完成开发者资质认证（需企业营业执照，个人无法申请）
- 认证费用：300 元/年

### 3.2 创建网站应用

1. 登录 [微信开放平台](https://open.weixin.qq.com/) → 「管理中心」→「网站应用」→「创建网站应用」
2. 填写信息：

| 字段 | 值 | 说明 |
|------|------|------|
| 应用名称 | `Autonome` | 微信扫码页显示的名称 |
| 应用简介 | AI-Native Bioinformatics IDE | 应用描述 |
| 应用官网 | `http://113.44.66.210:3001` | 前端首页地址 |
| 授权回调域 | `113.44.66.210` | 回调域名（不含协议和端口） |

3. 提交审核（通常 1-3 个工作日）
4. 审核通过后记录 **AppID** 和 **AppSecret**

> **生产环境**：应用官网和回调域需替换为正式域名。

### 3.3 配置环境变量

在 `autonome-backend/.env` 中添加：

```bash
# 微信开放平台（网站应用扫码登录）
WECHAT_APP_ID=your_wechat_app_id
WECHAT_APP_SECRET=your_wechat_app_secret
```

### 3.4 回调流程说明

```
用户点击「微信登录」
  → 前端请求 GET /api/oauth/wechat/qr-url 获取扫码 URL
  → 浏览器跳转微信扫码页
  → 用户扫码确认后微信回调 /api/oauth/wechat/callback?code=xxx
  → 后端用 code 换 access_token + openid
  → 自动注册/登录，签发 AT+RT，设置 Cookie
  → 重定向到前端首页
```

### 3.5 注意事项

- 微信不提供用户邮箱，自动注册时使用 `wechat_{openid}@autonome.local` 作为占位邮箱
- 如需跨应用（网站+公众号）统一用户标识，需在开放平台绑定公众号并使用 **UnionID**
- 微信扫码登录仅支持 PC 端浏览器，移动端需使用公众号网页授权（当前未实现）
- 微信 OAuth 接口已预留，未配置 AppID 时前端会提示「微信登录暂未配置」

### 3.6 验证

1. 配置完成后访问登录页，点击底部「微信」按钮
2. 浏览器应跳转到微信扫码页
3. 使用微信扫码确认后自动跳回 Autonome 首页并完成登录

---

## 4. 环境变量汇总

所有外部服务相关环境变量集中在 `autonome-backend/.env` 中：

```bash
# ── 阿里云 SMS 短信 ──
ALIYUN_ACCESS_KEY_ID=
ALIYUN_ACCESS_KEY_SECRET=
ALIYUN_SMS_SIGN_NAME=Autonome
ALIYUN_SMS_TEMPLATE_CODE=

# ── GitHub OAuth ──
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# ── 微信开放平台 ──
WECHAT_APP_ID=
WECHAT_APP_SECRET=

# ── 通用 ──
FRONTEND_URL=http://113.44.66.210:3001  # OAuth 回调重定向目标
COOKIE_SECURE=false                       # 生产环境 HTTPS 时设为 true
```

---

## 5. 故障排查

| 问题 | 可能原因 | 解决方法 |
|------|----------|----------|
| 短信发送失败 | AccessKey 错误或签名/模板未审核 | 检查 .env 配置，确认签名和模板已通过审核 |
| 短信发送频繁被拒 | 触发风控限制 | 检查 Redis 中的限流计数，等待冷却期 |
| GitHub 登录按钮无反应 | 未配置 GITHUB_CLIENT_ID | 在 .env 中配置 GitHub OAuth 参数 |
| GitHub 回调报错 | Client Secret 错误或回调 URL 不匹配 | 检查 GitHub OAuth App 设置中的回调 URL |
| GitHub 回调后白屏 | FRONTEND_URL 配置错误 | 确认 FRONTEND_URL 与前端实际地址一致 |
| 微信登录提示未配置 | 未配置 WECHAT_APP_ID | 在 .env 中配置微信开放平台参数 |
| Cookie 未设置 | 跨域或 HTTPS 配置问题 | 确认 CORS 配置和 COOKIE_SECURE 设置 |
| OAuth 回调 422 | code 已过期或重复使用 | OAuth code 只能使用一次，需重新授权 |
