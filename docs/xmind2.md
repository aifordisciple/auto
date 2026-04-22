# AUTONOME STUDIO 功能分类总览

## 用户与认证

### 账号注册

- 邮箱密码注册 — `auth/register/` 页面，表单校验 | `routes/auth.py` POST /register，密码哈希+邮箱校验
- 邮箱验证 — 注册后发送验证邮件提示 | `services/email_service.py` 发送验证链接

### 账号登录

- 邮箱密码登录 — `auth/login/` 页面，登录表单 | `routes/auth.py` POST /login，JWT签发
- OAuth2.0 登录 — GitHub/微信登录按钮，回调页 `auth/callback/` | `routes/auth.py` OAuth流程，账号关联

### Token管理

- Access Token — 自动附加到请求头，过期拦截 | `core/security.py` JWT签发/验证，15min过期
- Refresh Token — 静默刷新，无感续期 | `routes/auth.py` POST /refresh，7天过期

### 个人资料

- 头像上传 — `UserProfile.tsx` 头像裁剪上传 | `routes/users.py` PUT /me/avatar，文件存储
- 信息编辑 — `UserProfile.tsx` 表单编辑 | `routes/users.py` PUT /me，字段校验

### 偏好设置

- 主题/语言 — `settings/` 页面，Zustand持久化 | `routes/users.py` PUT /me/preferences

---

## 权限与角色 (RBAC)

### 角色管理

- 角色CRUD — 管理后台角色管理页面 | `routes/rbac.py` 角色增删改查API
- 角色继承 — 角色树形展示，继承关系配置 | `models/rbac.py` Role自引用，`deps_rbac.py` 继承解析

### 权限分配

- 用户角色绑定 — 用户详情页分配角色 | `routes/rbac.py` POST /users/{id}/roles
- 权限定义 — 权限列表管理 | `models/rbac.py` Permission模型，资源+操作粒度

### 权限校验

- 接口级鉴权 — 后端依赖注入校验 | `deps_rbac.py` 依赖注入，角色/权限装饰器
- 前端权限控制 — 组件级权限判断，菜单/按钮显隐 | `useAuthStore.ts` 角色/权限状态

---

## 项目管理

### 项目CRUD

- 创建项目 — `ProjectManager.tsx` 新建表单 | `routes/projects.py` POST /，项目初始化
- 编辑项目 — 项目设置页，名称/描述修改 | `routes/projects.py` PUT /{id}
- 删除项目 — 确认弹窗，级联删除提示 | `routes/projects.py` DELETE /{id}，软删除
- 项目列表 — `projects/` 页面，卡片/列表视图 | `routes/projects.py` GET /，分页+筛选

### 成员管理

- 邀请成员 — 成员管理面板，邮箱邀请 | `routes/projects.py` POST /{id}/members
- 角色分配 — 成员角色下拉选择 | `routes/projects.py` PUT /{id}/members/{uid}
- 移除成员 — 成员列表操作按钮 | `routes/projects.py` DELETE /{id}/members/{uid}

### 文件管理

- 文件上传 — 拖拽上传组件 | `routes/files.py` POST /upload，多文件支持
- 文件浏览 — 文件树组件，目录导航 | `routes/files.py` GET /{project_id}/files
- 文件下载 — 右键菜单下载 | `routes/files.py` GET /files/{id}/download

---

## AI 对话

### 对话管理

- 新建对话 — 侧边栏新建按钮 | `routes/chat.py` POST /conversations
- 对话历史 — 侧边栏对话列表 | `routes/chat.py` GET /conversations
- 删除对话 — 对话项右键删除 | `routes/chat.py` DELETE /conversations/{id}

### 消息交互

- 发送消息 — `MessageInput.tsx` 输入框+发送 | `routes/chat.py` POST /conversations/{id}/messages
- 流式响应 — SSE事件流，逐字渲染 | `routes/chat.py` GET /stream，Server-Sent Events
- 代码块渲染 — `CodeBlock.tsx` 语法高亮+复制 | 前端组件
- Markdown渲染 — 消息内容Markdown解析 | 前端组件

### Agent路由

- 意图识别 — 查询意图分类 | `services/intent_recognition.py` 意图分类
- 工具调度 — LangGraph工具节点 | `agent/bot.py` 工具调度
- 技能匹配 — 三阶段混合匹配 | `services/skill_matcher.py` 统一匹配器

---

## 技能系统

### 技能执行

- 技能浏览 — `SkillExecutePanel.tsx` 分类浏览 | `routes/skills.py` GET /，分类+标签筛选
- 参数填写 — 动态参数表单，类型校验 | `services/skill_parser.py` 参数定义解析
- 执行提交 — 执行按钮+进度展示 | `services/skill_executor.py` Docker沙箱调度
- 结果展示 — 结果面板，表格/图表/文件 | `routes/skills.py` GET /executions/{id}

### 技能推荐

- 智能推荐 — 推荐技能卡片 | `routes/skill_recommend.py` POST /recommend
- 参数推断 — 推荐参数预填 | `services/llm_skill_matcher.py` LLM参数推断
- 反馈闭环 — 推荐结果点赞/踩 | `routes/skill_recommend.py` POST /feedback

### 技能锻造

- 创建技能 — `ForgePanel.tsx` 向导式创建 | `routes/skills_forge.py` POST /，SKILL.md生成
- 编辑技能 — 代码编辑器+参数配置 | `routes/skills_forge.py` PUT /{id}
- AI辅助 — Crafter Agent交互 | `agent/crafter.py` 辅助生成技能包

### 技能市场

- 浏览市场 — `SkillMarketPanel.tsx` 搜索+分类 | `routes/skills_market.py` GET /market
- 发布技能 — 发布按钮+版本说明 | `routes/skills_market.py` POST /publish
- 评分评论 — 星级评分+评论框 | `routes/skills_market.py` POST /{id}/rate
- 安装技能 — 安装按钮+依赖检查 | `routes/skills_market.py` POST /{id}/install

### 我的技能

- 已创建技能 — `MySkillsPanel.tsx` 创建列表 | `routes/skills.py` GET /my/created
- 已收藏技能 — 收藏列表 | `routes/skills.py` GET /my/favorites
- 执行历史 — 历史记录列表 | `routes/skills.py` GET /my/history

### 技能管理

- 分类管理 — `SettingsPanel.tsx` 分类CRUD | `routes/skills.py` 分类管理API
- 标签管理 — 标签CRUD | `routes/skills.py` 标签管理API
- 审核队列 — 待审核技能列表 | `routes/skills_market.py` GET /pending

---

## 数据集管理

### 数据集CRUD

- 创建数据集 — `DatasetBrowser.tsx` 新建表单 | `routes/datasets.py` POST /，元数据初始化
- 编辑数据集 — 编辑弹窗 | `routes/datasets.py` PUT /{id}
- 删除数据集 — 确认弹窗 | `routes/datasets.py` DELETE /{id}

### 文件管理

- 上传文件 — 拖拽上传，进度条 | `routes/datasets.py` POST /{id}/files
- 数据预览 — 表格预览组件，分页 | `routes/datasets.py` GET /{id}/preview
- 元数据管理 — 文件属性编辑 | `routes/datasets.py` PUT /files/{fid}/meta

---

## 工作流

### 工作流编辑

- 可视化编辑 — `WorkflowEditor.tsx` 节点拖拽+连线 | `routes/workflows.py` CRUD
- 节点配置 — 节点属性面板 | `routes/workflows.py` PUT /{id}/nodes

### 工作流执行

- 运行工作流 — 运行按钮+参数配置 | `routes/workflows.py` POST /{id}/run
- 状态追踪 — 运行状态面板，实时更新 | `routes/workflows.py` GET /runs/{rid}
- 日志查看 — 运行日志流 | `routes/workflows.py` GET /runs/{rid}/logs

---

## 计费系统

### 积分管理

- 余额查询 — 顶部栏积分显示 | `routes/billing.py` GET /balance
- 消费记录 — 消费历史列表 | `routes/billing.py` GET /transactions
- 充值 — 充值弹窗 | `routes/billing.py` POST /recharge
- 积分扣减 — 执行前自动扣减 | `services/skill_executor.py` 执行前扣减

### 订阅管理

- 订阅计划 — 订阅页面 | `routes/billing.py` GET /plans
- 订阅/续费 — 订阅操作 | `routes/billing.py` POST /subscribe

---

## 通知系统

### 消息通知

- 通知列表 — `NotificationPanel.tsx` 下拉面板 | `routes/notifications.py` GET /
- 标记已读 — 单条/全部已读 | `routes/notifications.py` PUT /{id}/read
- 实时推送 — WebSocket/SSE 新消息提醒 | `routes/notifications.py` SSE推送

---

## 管理后台

### 用户管理

- 用户列表 — 管理页面用户表格 | `routes/admin.py` GET /admin/users
- 禁用/启用 — 操作按钮 | `routes/admin.py` PUT /admin/users/{id}/status
- 角色分配 — 角色选择 | `routes/rbac.py` POST /users/{id}/roles

### 系统配置

- 参数配置 — 配置编辑页 | `routes/admin.py` GET/PUT /admin/config

### 数据统计

- 使用统计 — 统计仪表盘 | `routes/admin.py` GET /admin/stats

### 技能审核

- 审核队列 — 待审核列表 | `routes/skills_market.py` GET /pending
- 通过/拒绝 — 审核操作 | `routes/skills_market.py` PUT /{id}/review

---

## 全局功能

### 全局搜索

- 跨模块搜索 — `CommandBar.tsx` Cmd+K搜索 | `routes/search.py` GET /search
- 快捷跳转 — 搜索结果点击跳转 | 前端路由

### 主题系统

- 深色/浅色 — 主题切换按钮，CSS变量 | 前端样式

### 国际化

- 中英文 — i18n语言包切换 | 前端国际化

### 响应式

- 移动端适配 — 响应式布局断点 | 前端布局
