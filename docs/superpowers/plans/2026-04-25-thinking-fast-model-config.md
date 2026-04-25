# 思考模型与极速模型配置重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将「主模型/意图识别模型」重构为「思考模型/极速模型」，极速模型用于意图识别+日常对话，思考模型用于深度思考对话。

**Architecture:** 数据库字段重命名 → 后端模型/工具函数重命名 → API 接口适配 → 前端 UI 重设计。采用一次性全量迁移，所有层同步修改。

**Tech Stack:** SQLAlchemy + Alembic (数据库迁移), FastAPI (API), React + Zustand (前端)

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `alembic/versions/xxxx_rename_llm_to_thinking_intent_to_fast.py` | 新建 | 数据库列重命名迁移 |
| `app/models/user.py` | 修改 | User 模型字段重命名 |
| `app/models/config.py` | 修改 | SystemConfig 模型字段重命名 |
| `app/utils/llm_config.py` | 修改 | 函数重命名 + 回退链调整 |
| `app/api/routes/users.py` | 修改 | API 字段重命名 + 测试端点适配 |
| `app/api/routes/chat.py` | 修改 | 模型选择逻辑（enable_think 决定用哪个模型） |
| `app/agent/router/l1_classifier.py` | 修改 | 调用 get_fast_llm_config() |
| `app/agent/router/engine.py` | 修改 | 同上 |
| `app/tasks/chat_queue_task.py` | 修改 | 调用 get_thinking_llm_config() |
| `app/services/success_evaluator.py` | 修改 | 调用 get_thinking_llm_config() |
| `app/services/tasks/sandbox_tasks.py` | 修改 | 调用 get_thinking_llm_config_standalone() |
| `app/api/routes/skills/forge.py` | 修改 | 调用 get_thinking_llm_config() |
| `app/api/routes/skills/testing.py` | 修改 | 调用 get_thinking_llm_config() |
| `app/api/routes/skills/transform.py` | 修改 | 调用 get_thinking_llm_config() |
| `autonome-studio/src/components/overlays/UserCenter/AIModelPanel.tsx` | 修改 | 前端 UI 重设计 |

---

### Task 1: 数据库迁移 — 列重命名

**Files:**
- Create: `autonome-backend/alembic/versions/xxxx_rename_llm_to_thinking_intent_to_fast.py`

- [ ] **Step 1: 创建 Alembic 迁移文件**

```python
"""rename llm_* to thinking_* and intent_* to fast_*

Revision ID: rename_thinking_fast
Revises: 1c4f6c0f4a5e
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'rename_thinking_fast'
down_revision = '1c4f6c0f4a5e'
branch_labels = None
depends_on = None


def upgrade():
    # === users 表：llm_* → thinking_* ===
    op.alter_column('users', 'llm_api_key', new_column_name='thinking_api_key')
    op.alter_column('users', 'llm_base_url', new_column_name='thinking_base_url')
    op.alter_column('users', 'llm_model_name', new_column_name='thinking_model_name')

    # === users 表：intent_* → fast_* ===
    op.alter_column('users', 'intent_api_key', new_column_name='fast_api_key')
    op.alter_column('users', 'intent_base_url', new_column_name='fast_base_url')
    op.alter_column('users', 'intent_model_name', new_column_name='fast_model_name')

    # === system_configs 表：openai_* → thinking_* ===
    op.alter_column('system_configs', 'openai_api_key', new_column_name='thinking_api_key')
    op.alter_column('system_configs', 'openai_base_url', new_column_name='thinking_base_url')
    op.alter_column('system_configs', 'default_model', new_column_name='thinking_model')

    # === system_configs 表：intent_* → fast_* ===
    op.alter_column('system_configs', 'intent_api_key', new_column_name='fast_api_key')
    op.alter_column('system_configs', 'intent_base_url', new_column_name='fast_base_url')
    op.alter_column('system_configs', 'intent_model', new_column_name='fast_model')


def downgrade():
    # === users 表：thinking_* → llm_* ===
    op.alter_column('users', 'thinking_api_key', new_column_name='llm_api_key')
    op.alter_column('users', 'thinking_base_url', new_column_name='llm_base_url')
    op.alter_column('users', 'thinking_model_name', new_column_name='llm_model_name')

    # === users 表：fast_* → intent_* ===
    op.alter_column('users', 'fast_api_key', new_column_name='intent_api_key')
    op.alter_column('users', 'fast_base_url', new_column_name='intent_base_url')
    op.alter_column('users', 'fast_model_name', new_column_name='intent_model_name')

    # === system_configs 表：thinking_* → openai_* ===
    op.alter_column('system_configs', 'thinking_api_key', new_column_name='openai_api_key')
    op.alter_column('system_configs', 'thinking_base_url', new_column_name='openai_base_url')
    op.alter_column('system_configs', 'thinking_model', new_column_name='default_model')

    # === system_configs 表：fast_* → intent_* ===
    op.alter_column('system_configs', 'fast_api_key', new_column_name='intent_api_key')
    op.alter_column('system_configs', 'fast_base_url', new_column_name='intent_base_url')
    op.alter_column('system_configs', 'fast_model', new_column_name='intent_model')
```

- [ ] **Step 2: 执行迁移**

Run: `cd autonome-backend && alembic upgrade head`
Expected: 迁移成功，无报错

- [ ] **Step 3: 验证列已重命名**

Run: `docker-compose exec postgres psql -U autonome autonome_db -c "\d users" | grep -E "thinking_|fast_"`
Expected: 看到 thinking_api_key, thinking_base_url, thinking_model_name, fast_api_key, fast_base_url, fast_model_name

---

### Task 2: 后端模型字段重命名 — User + SystemConfig

**Files:**
- Modify: `autonome-backend/app/models/user.py`
- Modify: `autonome-backend/app/models/config.py`

- [ ] **Step 1: 修改 User 模型字段**

在 `app/models/user.py` 中，将以下字段重命名：

```python
# 旧 → 新
llm_api_key     → thinking_api_key
llm_base_url    → thinking_base_url
llm_model_name  → thinking_model_name
intent_api_key  → fast_api_key
intent_base_url → fast_base_url
intent_model_name → fast_model_name
```

注意：SQLAlchemy 的 `Column` 名需要与数据库列名一致，所以 `name` 参数也要改。

- [ ] **Step 2: 修改 SystemConfig 模型字段**

在 `app/models/config.py` 中，将以下字段重命名：

```python
# 旧 → 新
openai_api_key  → thinking_api_key
openai_base_url → thinking_base_url
default_model   → thinking_model
intent_api_key  → fast_api_key
intent_base_url → fast_base_url
intent_model    → fast_model
```

- [ ] **Step 3: 验证后端启动**

Run: `docker-compose restart backend-api`
Run: `docker logs autonome-api 2>&1 | tail -10`
Expected: 无 SQLAlchemy 映射错误

---

### Task 3: 后端工具函数重命名 — llm_config.py

**Files:**
- Modify: `autonome-backend/app/utils/llm_config.py`

- [ ] **Step 1: 重命名所有函数**

| 旧函数 | 新函数 |
|--------|--------|
| `get_llm_config()` | `get_thinking_llm_config()` |
| `get_intent_llm_config()` | `get_fast_llm_config()` |
| `_resolve_user_config()` | `_resolve_user_thinking_config()` |
| `_resolve_user_intent_config()` | `_resolve_user_fast_config()` |
| `_has_user_llm_config()` | `_has_user_thinking_config()` |
| `_has_user_intent_config()` | `_has_user_fast_config()` |
| `_has_system_intent_config()` | `_has_system_fast_config()` |
| `_resolve_system_config()` | `_resolve_system_thinking_config()` |
| `get_llm_config_standalone()` | `get_thinking_llm_config_standalone()` |
| `get_intent_llm_config_standalone()` | `get_fast_llm_config_standalone()` |

- [ ] **Step 2: 更新函数内部字段引用**

在 `_resolve_user_thinking_config()` 中：`user.llm_*` → `user.thinking_*`
在 `_resolve_user_fast_config()` 中：`user.intent_*` → `user.fast_*`
在 `_resolve_system_thinking_config()` 中：`config.openai_*` / `config.default_model` → `config.thinking_*`
在 `_has_system_fast_config()` 中：`config.intent_*` → `config.fast_*`

- [ ] **Step 3: 更新极速模型回退链**

在 `get_fast_llm_config()` 中，当用户未配置极速模型时，回退到思考模型配置而非报错：

```python
async def get_fast_llm_config(session, user_id=None):
    """获取极速模型配置（意图识别 + 非思考对话）

    回退链：User.fast_* → SystemConfig.fast_* → 思考模型配置 → 环境变量
    """
    # 1. 尝试用户级极速模型配置
    if user_id:
        user = await session.get(User, user_id)
        if user and _has_user_fast_config(user):
            return _resolve_user_fast_config(user)

    # 2. 尝试系统级极速模型配置
    config = await _get_system_config(session)
    if config and _has_system_fast_config(config):
        return _resolve_system_fast_config(config)

    # 3. 回退到思考模型配置（极速未配时复用思考模型）
    return await get_thinking_llm_config(session, user_id)
```

- [ ] **Step 4: 保留旧函数名作为别名（过渡期兼容）**

在文件末尾添加：

```python
# ========== 向后兼容别名（过渡期，后续可删除）==========
get_llm_config = get_thinking_llm_config
get_intent_llm_config = get_fast_llm_config
get_llm_config_standalone = get_thinking_llm_config_standalone
get_intent_llm_config_standalone = get_fast_llm_config_standalone
```

- [ ] **Step 5: 验证后端启动**

Run: `docker-compose restart backend-api`
Expected: 无导入错误

---

### Task 4: 后端 API 路由适配 — users.py

**Files:**
- Modify: `autonome-backend/app/api/routes/users.py`

- [ ] **Step 1: 更新 LLM 配置读取接口 (GET /api/users/me/llm-config)**

将响应字段重命名：

```python
# 旧 → 新
"llm_api_key"              → "thinking_api_key"
"llm_base_url"             → "thinking_base_url"
"llm_model_name"           → "thinking_model_name"
"intent_api_key"           → "fast_api_key"
"intent_base_url"          → "fast_base_url"
"intent_model_name"        → "fast_model_name"
"is_using_user_config"     → "is_using_user_thinking_config"
"is_using_user_intent_config" → "is_using_user_fast_config"
"system_base_url"          → "system_thinking_base_url"
"system_model_name"        → "system_thinking_model_name"
"system_intent_base_url"   → "system_fast_base_url"
"system_intent_model_name" → "system_fast_model_name"
```

同时更新内部逻辑：
- `user.llm_*` → `user.thinking_*`
- `user.intent_*` → `user.fast_*`
- `config.openai_*` → `config.thinking_*`
- `config.intent_*` → `config.fast_*`
- `get_llm_config()` → `get_thinking_llm_config()`
- `get_intent_llm_config()` → `get_fast_llm_config()`
- 去掉 `use_shared_intent_model` / `is_shared_intent` 相关逻辑

- [ ] **Step 2: 更新 LLM 配置保存接口 (PUT /api/users/me/llm-config)**

请求体字段重命名：
- `llm_api_key` → `thinking_api_key`
- `llm_base_url` → `thinking_base_url`
- `llm_model_name` → `thinking_model_name`
- `intent_api_key` → `fast_api_key`
- `intent_base_url` → `fast_base_url`
- `intent_model_name` → `fast_model_name`

去掉 `use_shared_intent_model` 相关逻辑（不再支持共用）。
更新 `user.*` 字段赋值为新字段名。

- [ ] **Step 3: 更新 LLM 配置测试接口 (POST /api/users/me/llm-config/test)**

请求体字段重命名：
- `intent_*` → `fast_*`
- 测试极速模型时使用 `fast_*` 字段
- 测试思考模型时使用 `thinking_*` 字段

- [ ] **Step 4: 验证 API**

Run: `curl -s http://localhost:8000/api/users/me/llm-config -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | grep -E "thinking|fast"`
Expected: 看到 thinking_api_key, thinking_base_url, thinking_model_name, fast_api_key, fast_base_url, fast_model_name

---

### Task 5: 后端聊天路由适配 — chat.py 模型选择逻辑

**Files:**
- Modify: `autonome-backend/app/api/routes/chat.py`

- [ ] **Step 1: 更新模型选择逻辑**

在 `stream_chat_response` 函数中（约第 209 行），将：

```python
llm_cfg = get_llm_config(session, user_id)
```

改为根据 `enable_think` 选择模型：

```python
# 根据深度思考模式选择模型
# 开启思考 → 思考模型；关闭思考 → 极速模型
if enable_think:
    llm_cfg = await get_thinking_llm_config(session, user_id)
else:
    llm_cfg = await get_fast_llm_config(session, user_id)
```

- [ ] **Step 2: 更新意图识别调用**

确认意图识别部分使用 `get_fast_llm_config()`（之前是 `get_intent_llm_config()`，已有别名兼容，但应改为直接调用新名）。

- [ ] **Step 3: 更新其他引用**

在 chat.py 中搜索所有 `get_llm_config` / `get_intent_llm_config` 调用，全部替换为新函数名。

- [ ] **Step 4: 验证聊天功能**

Run: `curl -s -N http://localhost:8000/api/chat/stream -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"message":"你好","project_id":"proj_09224daaedc4","session_id":""}' | head -20`
Expected: 正常返回流式响应

---

### Task 6: 后端其他文件适配

**Files:**
- Modify: `autonome-backend/app/agent/router/l1_classifier.py`
- Modify: `autonome-backend/app/agent/router/engine.py`
- Modify: `autonome-backend/app/tasks/chat_queue_task.py`
- Modify: `autonome-backend/app/services/success_evaluator.py`
- Modify: `autonome-backend/app/services/tasks/sandbox_tasks.py`
- Modify: `autonome-backend/app/api/routes/skills/forge.py`
- Modify: `autonome-backend/app/api/routes/skills/testing.py`
- Modify: `autonome-backend/app/api/routes/skills/transform.py`

- [ ] **Step 1: l1_classifier.py — 意图识别用极速模型**

将 `get_intent_llm_config` 替换为 `get_fast_llm_config`。
将 `self.is_local` 相关逻辑中的 `_is_local_model` 调用保持不变（仍用于判断是否支持 structured_output）。

- [ ] **Step 2: engine.py — 意图识别用极速模型**

将 `get_intent_llm_config` 替换为 `get_fast_llm_config`。

- [ ] **Step 3: chat_queue_task.py — 对话用思考模型**

将 `get_llm_config` 替换为 `get_thinking_llm_config`。
注意：此文件处理异步队列任务，需要根据任务是否启用思考模式来选择模型。如果任务中有 `enable_think` 参数，则按 Task 5 的逻辑选择；否则默认用思考模型。

- [ ] **Step 4: success_evaluator.py — 评估用思考模型**

将 `get_llm_config` 替换为 `get_thinking_llm_config`。

- [ ] **Step 5: sandbox_tasks.py — 沙箱任务用思考模型**

将 `get_llm_config_standalone` 替换为 `get_thinking_llm_config_standalone`。

- [ ] **Step 6: skills/forge.py, testing.py, transform.py — 技能相关用思考模型**

将 `get_llm_config` 替换为 `get_thinking_llm_config`。

- [ ] **Step 7: 验证后端启动**

Run: `docker-compose restart backend-api && sleep 5 && docker logs autonome-api 2>&1 | tail -10`
Expected: 无导入错误

---

### Task 7: 前端 AIModelPanel 重设计

**Files:**
- Modify: `autonome-studio/src/components/overlays/UserCenter/AIModelPanel.tsx`

- [ ] **Step 1: 更新 API 字段名**

将所有 `llm_api_key` → `thinking_api_key`，`llm_base_url` → `thinking_base_url`，`llm_model_name` → `thinking_model_name`，`intent_api_key` → `fast_api_key`，`intent_base_url` → `fast_base_url`，`intent_model_name` → `fast_model_name`。

- [ ] **Step 2: 去掉「共用主模型」开关**

删除 `useSharedIntentModel` 状态及相关逻辑。极速模型和思考模型完全独立配置。

- [ ] **Step 3: 重新设计 UI 布局**

将原来的「主模型」+「意图识别模型」布局改为：

```
极速模型（⚡图标）
  用于：意图识别、日常对话
  Base URL / 模型名称 / API Key
  快速预设：[SaaS轻量] [本地轻量]

思考模型（🧠图标）
  用于：深度思考对话
  Base URL / 模型名称 / API Key
  快速预设：[SaaS旗舰] [本地旗舰]
```

- [ ] **Step 4: 更新快速预设**

| 预设 | 极速模型 | 思考模型 |
|------|---------|---------|
| SaaS轻量 | `api.openai.com/v1` + `gpt-4o-mini` | — |
| SaaS旗舰 | — | `api.openai.com/v1` + `gpt-4o` |
| 本地轻量 | `host.docker.internal:11434/v1` + `qwen3:8b` | — |
| 本地旗舰 | — | `host.docker.internal:11434/v1` + `qwen3:32b` |

- [ ] **Step 5: 更新测试按钮**

将「测试主模型」→「测试思考模型」，「测试意图识别模型」→「测试极速模型」。
测试请求体字段名同步更新。

- [ ] **Step 6: 更新配置来源显示**

将 `is_using_user_config` → `is_using_user_thinking_config`，`is_using_user_intent_config` → `is_using_user_fast_config`。
将 `system_base_url` → `system_thinking_base_url`，`system_model_name` → `system_thinking_model_name`。
将 `system_intent_base_url` → `system_fast_base_url`，`system_intent_model_name` → `system_fast_model_name`。

- [ ] **Step 7: 验证前端构建**

Run: `cd autonome-studio && npm run build`
Expected: 构建成功，无类型错误

---

### Task 8: 删除兼容别名 + 最终验证

**Files:**
- Modify: `autonome-backend/app/utils/llm_config.py`

- [ ] **Step 1: 删除 llm_config.py 末尾的兼容别名**

删除 Task 3 Step 4 添加的别名：

```python
# 删除以下行
get_llm_config = get_thinking_llm_config
get_intent_llm_config = get_fast_llm_config
get_llm_config_standalone = get_thinking_llm_config_standalone
get_intent_llm_config_standalone = get_fast_llm_config_standalone
```

- [ ] **Step 2: 全局搜索确认无遗漏**

Run: `cd autonome-backend && grep -rn "get_llm_config\|get_intent_llm_config\|llm_api_key\|llm_base_url\|llm_model_name\|intent_api_key\|intent_base_url\|intent_model_name\|openai_api_key\|openai_base_url\|default_model" --include="*.py" app/ | grep -v "__pycache__" | grep -v "thinking_\|fast_\|#.*旧\|#.*old"`
Expected: 无结果（所有旧名称已替换）

Run: `cd autonome-studio && grep -rn "llm_api_key\|llm_base_url\|llm_model_name\|intent_api_key\|intent_base_url\|intent_model_name\|useSharedIntent" --include="*.ts" --include="*.tsx" src/`
Expected: 无结果

- [ ] **Step 3: Docker 全栈验证**

Run: `docker-compose down && docker-compose up -d`
Run: `sleep 10 && docker logs autonome-api 2>&1 | tail -10`
Run: `docker logs autonome-web 2>&1 | tail -10`
Expected: 前后端均正常启动

- [ ] **Step 4: 功能验证**

1. 打开前端 http://localhost:3001，进入用户中心 AI 模型设置
2. 确认看到「极速模型」和「思考模型」两个独立配置区域
3. 配置极速模型和思考模型，保存成功
4. 发送普通消息（非思考模式），确认使用极速模型
5. 开启深度思考模式，发送消息，确认使用思考模型
6. 测试极速模型和思考模型的连接测试按钮

- [ ] **Step 5: 自动部署**

Run: `./auto_deploy.sh -s "feat: 思考模型与极速模型配置重构" -d "将主模型/意图识别模型重构为思考模型/极速模型。极速模型用于意图识别和日常对话，思考模型用于深度思考对话。数据库字段重命名(llm_*→thinking_*, intent_*→fast_*)，前端UI重新设计，去掉共用主模型开关。"`
