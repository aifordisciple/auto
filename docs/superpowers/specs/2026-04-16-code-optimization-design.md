# AUTONOME 全面代码优化设计文档

**日期**: 2026-04-16
**方案**: 分层渐进式（方案 A）
**原则**: 每阶段独立可验证，不影响现有功能

---

## P0: 安全修复（~8 文件）

### P0.1 统一 SECRET_KEY

**问题**: `config.py` 和 `security.py` 各定义了不同的 SECRET_KEY 默认值，`deps.py` 使用 `security.py` 的版本。

**方案**:
- `security.py` 改为从 `config.py` 的 Settings 读取 SECRET_KEY
- 删除 `security.py` 中的硬编码 `SECRET_KEY` 常量
- `config.py` 中的默认值改为空字符串，启动时校验非空

**文件**:
- `autonome-backend/app/core/security.py` — 删除硬编码 SECRET_KEY，从 settings 读取
- `autonome-backend/app/core/config.py` — SECRET_KEY 默认值改为必填项

### P0.2 DEBUG 默认值修正

**问题**: `config.py` 中 `DEBUG: bool = True`，生产环境风险高。

**方案**: 改为 `DEBUG: bool = False`，开发环境通过 `.env` 设置 `DEBUG=true`

**文件**:
- `autonome-backend/app/core/config.py`

### P0.3 移除硬编码 IP

**问题**: `useWorkspaceStore.ts` 中硬编码 `113.44.66.210:8000`

**方案**: 移除硬编码 IP，使用 `lib/api.ts` 的 `BASE_URL`

**文件**:
- `autonome-studio/src/store/useWorkspaceStore.ts`

### P0.4 统一 OpenAI Base URL

**问题**: `https://api.openai.com/v1` 在 4 个文件中重复定义

**方案**: 在 `config.py` 中添加 `OPENAI_BASE_URL` 设置，所有引用处改为从 settings 读取

**文件**:
- `autonome-backend/app/core/config.py` — 添加 OPENAI_BASE_URL
- `autonome-backend/app/services/tasks/sandbox_tasks.py`
- `autonome-backend/app/api/routes/system.py`
- `autonome-backend/app/models/config.py`

---

## P1: 重复代码消除（~25 文件）

### P1.1 Docker 路径常量统一

**问题**: 6 个文件各自定义 Docker 挂载路径常量，`sandbox_config.py` 已有但无人导入。

**方案**:
- 确保 `sandbox_config.py` 导出所有路径常量
- 所有使用方改为 `from app.core.sandbox_config import ...`
- 删除各文件中的重复定义

**文件**:
- `autonome-backend/app/core/sandbox_config.py` — 确保导出完整
- `autonome-backend/app/tools/bio_tools.py` — 删除重复常量，导入
- `autonome-backend/app/services/container_pool_service.py` — 同上
- `autonome-backend/app/services/terminal_manager.py` — 同上
- `autonome-backend/app/services/native_executor.py` — 同上
- `autonome-backend/app/services/package_installer.py` — 同上

### P1.2 提取 docker_api_request 共享函数

**问题**: `bio_tools.py` 和 `container_pool_service.py` 有完全相同的 `docker_api_request` 函数。

**方案**: 提取到 `app/core/docker_api.py`，两处改为导入

**新文件**: `autonome-backend/app/core/docker_api.py`
**修改文件**:
- `autonome-backend/app/tools/bio_tools.py`
- `autonome-backend/app/services/container_pool_service.py`

### P1.3 前端 BASE_URL 和 Auth 统一

**问题**: 21 处重复定义 BASE_URL，19 处手动构建 auth header，30+ 处直接 `localStorage.getItem`。

**方案**:
- 所有文件统一从 `lib/api.ts` 导入 `BASE_URL` 和 `getToken`
- 所有 `fetch()` 调用改为 `fetchAPI()` 或至少使用 `getToken()` + `BASE_URL`
- 移除 `localStorage.getItem('autonome_access_token')` 直接调用

**文件**: 涉及 ~15 个前端文件

### P1.4 Asset Tree 逻辑提取

**问题**: 资产树构建和渲染逻辑在 3 个文件中重复。

**方案**: 提取到 `components/chat/shared/AssetTree.tsx`

**新文件**: `autonome-studio/src/components/chat/shared/AssetTree.tsx`
**修改文件**:
- `autonome-studio/src/components/MarkdownBlock.tsx`
- `autonome-studio/src/components/chat/MemoizedMessageItem.tsx`
- `autonome-studio/src/components/chat/components/ExecutionResultCard.tsx`

### P1.5 容器挂载配置统一

**问题**: 4 个文件重复构建 Docker mount binds 和环境变量。

**方案**: 使用 `sandbox_config.py` 中已有的 `get_container_mounts()` 和 `get_container_env()` 函数

**文件**:
- `autonome-backend/app/tools/bio_tools.py`
- `autonome-backend/app/services/container_pool_service.py`
- `autonome-backend/app/services/terminal_manager.py`

---

## P2: 代码清理（~40 文件）

### P2.1 后端 print() → log.info()

**问题**: 30+ 处 `print()` 应改为 `log.info()`

**方案**: 逐文件替换，保留 `package_installer.py` 中作为子进程验证命令的 `print('OK')`

**文件**: 8 个后端文件

### P2.2 前端 console.log() 清理

**问题**: ~70 处 `console.log()` 在生产代码中

**方案**:
- 开发调试日志（如 `[ForgePanel] 初始化...`）直接删除
- 错误处理中的 `console.error` 保留但添加条件（`if (process.env.NODE_ENV === 'development')`）
- 性能日志（`[PERF]`）移除

**文件**: ~20 个前端文件

### P2.3 修正 loguru 直接导入

**问题**: 11 个文件 `from loguru import logger` 绕过配置的 logger

**方案**: 统一改为 `from app.core.logger import log`

**文件**: 10 个后端文件（排除 logger.py 自身）

### P2.4 移除不必要的 React import

**问题**: 30+ 文件有不必要的 `import React from 'react'`

**方案**: 仅在使用 `React.xxx` API（如 `React.useState`）时保留，否则删除

**文件**: ~30 个前端文件

### P2.5 datetime.utcnow() 修正

**问题**: 11 处使用已弃用的 `datetime.utcnow()`

**方案**: 替换为 `datetime.now(timezone.utc)`

**文件**: 7 个后端文件

### P2.6 魔法数字提取为常量

**问题**: `3600`（超时）出现 16+ 次，截断长度 `[:2000]`/`[:5000]` 出现 11 次

**方案**:
- `sandbox_config.py` 中定义 `DEFAULT_EXECUTION_TIMEOUT = 3600`
- `skill_executor.py` 中定义 `MAX_OUTPUT_LENGTH = 5000`, `MAX_ERROR_LENGTH = 2000`

**文件**: ~10 个后端文件

---

## P3: 大文件拆分（~15 文件）

### P3.1 api.ts 按域拆分

**问题**: 1808 行，所有 API 调用集中在一个文件

**方案**: 拆分为域模块，`api.ts` 保留核心工具函数并 re-export

```
lib/api.ts              → 核心工具 (BASE_URL, getToken, fetchAPI, cachedFetch) + re-export
lib/api/skillForge.ts   → skillForgeApi
lib/api/admin.ts        → adminApi
lib/api/database.ts     → databaseApi
lib/api/billing.ts      → billingApi
lib/api/chat.ts         → chatApi
lib/api/project.ts      → projectApi
```

### P3.2 skill_executor.py 策略模式拆分

**问题**: 1603 行，混合 Docker/Nextflow/Native/Mock 执行逻辑

**方案**: 按执行策略拆分

```
services/skill_executor.py          → 编排器 + 公共接口
services/executors/docker_executor.py   → Docker 执行
services/executors/nextflow_executor.py → Nextflow 执行
services/executors/native_executor.py   → Native 执行（已有，调整导入）
services/executors/base.py              → 基类 + 共享常量
```

### P3.3 dashboard.py 子路由拆分

**问题**: 1305 行，混合统计/通知/系统健康

**方案**: 拆分为子路由

```
api/routes/dashboard.py          → 主路由 + re-export
api/routes/dashboard/stats.py    → 统计接口
api/routes/dashboard/system.py   → 系统健康接口
```

### P3.4 admin.py 子路由拆分

**问题**: 944 行，混合用户/技能/计费/系统管理

**方案**: 拆分为子路由

```
api/routes/admin.py              → 主路由 + re-export
api/routes/admin/users.py        → 用户管理
api/routes/admin/skills.py       → 技能管理
api/routes/admin/billing.py      → 计费管理
```

---

## 验证策略

每个阶段完成后：
1. `docker-compose down && docker-compose up -d`
2. 检查后端日志无报错：`docker logs autonome-api | tail -30`
3. 检查前端日志无报错：`docker logs autonome-web | tail -30`
4. 基本功能冒烟测试：登录、聊天、技能执行

---

## 不在本次范围内

- `learning_tasks.py` 中的模拟代码（需要业务决策是否删除）
- `pipeline_tasks.py` 中的模拟代码（同上）
- `: any` 类型替换（需要逐个分析，风险较高）
- ECharts tree-shaking（优化效果有限）
- 新增测试（本次聚焦重构，不新增功能）
