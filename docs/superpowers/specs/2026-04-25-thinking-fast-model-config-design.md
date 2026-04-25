# 思考模型与极速模型配置重构设计

> 日期: 2026-04-25
> 状态: 已批准

## 背景

当前系统将 AI 模型分为「主模型」和「意图识别模型」两个概念：
- 主模型：用于对话回复
- 意图识别模型：用于意图分类，可独立配置或与主模型共用

这种命名和用途划分不够直观。用户更自然的理解是：
- **极速模型**：快速响应，用于意图识别和日常对话
- **思考模型**：深度推理，用于需要深度思考的对话

## 设计目标

1. 将「主模型」重命名为「思考模型」，「意图识别模型」重命名为「极速模型」
2. 极速模型用于：意图识别 + 非思考模式对话
3. 思考模型用于：深度思考模式对话
4. 用户手动在聊天界面切换「深度思考」开关来选择模型
5. 两个模型完全独立配置，去掉「共用主模型」开关
6. 数据库字段、API 字段、代码函数全部同步重命名

## 第一部分：数据模型

### User 表字段重命名

| 旧字段 | 新字段 | 用途 |
|--------|--------|------|
| `llm_api_key` | `thinking_api_key` | 思考模型 API Key |
| `llm_base_url` | `thinking_base_url` | 思考模型 Base URL |
| `llm_model_name` | `thinking_model_name` | 思考模型名称 |
| `intent_api_key` | `fast_api_key` | 极速模型 API Key |
| `intent_base_url` | `fast_base_url` | 极速模型 Base URL |
| `intent_model_name` | `fast_model_name` | 极速模型名称 |

### SystemConfig 表字段重命名

| 旧字段 | 新字段 | 用途 |
|--------|--------|------|
| `openai_api_key` | `thinking_api_key` | 思考模型 API Key |
| `openai_base_url` | `thinking_base_url` | 思考模型 Base URL |
| `default_model` | `thinking_model` | 思考模型名称 |
| `intent_api_key` | `fast_api_key` | 极速模型 API Key |
| `intent_base_url` | `fast_base_url` | 极速模型 Base URL |
| `intent_model` | `fast_model` | 极速模型名称 |

### Alembic 迁移

使用 `op.alter_column` 重命名列，数据无需迁移（只改列名）。迁移必须在代码部署前执行。

## 第二部分：模型选择逻辑

### 聊天时的模型路由

```
用户发送消息
    |
    +-- 意图识别（始终用极速模型）
    |   +-- get_fast_llm_config()
    |
    +-- 对话回复
        +-- 深度思考模式开启 -> get_thinking_llm_config()
        +-- 深度思考模式关闭 -> get_fast_llm_config()
```

### 配置回退链

**思考模型** `get_thinking_llm_config()`：
```
User.thinking_* -> SystemConfig.thinking_* -> 环境变量(OPENAI_API_KEY等)
```

**极速模型** `get_fast_llm_config()`：
```
User.fast_* -> SystemConfig.fast_* -> 思考模型配置 -> 环境变量
```

极速模型回退到思考模型配置，确保即使用户只配了思考模型也能正常工作。

### 函数重命名

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

## 第三部分：前端配置界面

### AIModelPanel 重新设计

去掉「共用主模型」开关，两个模型并列展示：

```
+-----------------------------------------+
|  AI 模型设置                             |
+-----------------------------------------+
|                                         |
|  极速模型                                |
|  用于：意图识别、日常对话                   |
|  +---------------------------------+    |
|  | Base URL: [________________]    |    |
|  | 模型名称: [________________]    |    |
|  | API Key:  [________________]    |    |
|  | 快速预设: [SaaS轻量] [本地轻量]  |    |
|  +---------------------------------+    |
|                                         |
|  思考模型                                |
|  用于：深度思考对话                        |
|  +---------------------------------+    |
|  | Base URL: [________________]    |    |
|  | 模型名称: [________________]    |    |
|  | API Key:  [________________]    |    |
|  | 快速预设: [SaaS旗舰] [本地旗舰]  |    |
|  +---------------------------------+    |
|                                         |
|  配置来源: 个人配置 / 系统全局配置          |
|                                         |
|  [测试极速] [测试思考] [保存] [恢复默认]    |
+-----------------------------------------+
```

### 快速预设

| 预设 | 极速模型 | 思考模型 |
|------|---------|---------|
| SaaS | `api.openai.com/v1` + `gpt-4o-mini` | `api.openai.com/v1` + `gpt-4o` |
| 本地 | `host.docker.internal:11434/v1` + `qwen3:8b` | `host.docker.internal:11434/v1` + `qwen3:32b` |

### 聊天界面思考模式开关

现有 `enable_think` 开关保留，UI 文案调整为「使用思考模型」。开启时用思考模型，关闭时用极速模型。

## 第四部分：API 接口变更

### REST API 字段重命名

**GET/PUT `/api/users/me/llm-config`**：

| 旧字段 | 新字段 |
|--------|--------|
| `llm_api_key` | `thinking_api_key` |
| `llm_base_url` | `thinking_base_url` |
| `llm_model_name` | `thinking_model_name` |
| `intent_api_key` | `fast_api_key` |
| `intent_base_url` | `fast_base_url` |
| `intent_model_name` | `fast_model_name` |
| `is_using_user_config` | `is_using_user_thinking_config` |
| `is_using_user_intent_config` | `is_using_user_fast_config` |
| `system_base_url` | `system_thinking_base_url` |
| `system_model_name` | `system_thinking_model_name` |
| `system_intent_base_url` | `system_fast_base_url` |
| `system_intent_model_name` | `system_fast_model_name` |

**POST `/api/users/me/llm-config/test`**：请求体中 `intent_*` 字段改为 `fast_*`，后端根据是否有 `fast_*` 字段判断测试哪个模型。

### chat.py 模型选择

```python
# 之前：始终用主模型对话
llm_cfg = get_llm_config(session, user_id)

# 之后：根据思考模式选择模型
if request.enable_think:
    llm_cfg = get_thinking_llm_config(session, user_id)
else:
    llm_cfg = get_fast_llm_config(session, user_id)
```

意图识别始终用极速模型（函数名从 `get_intent_llm_config` 改为 `get_fast_llm_config`）。

## 第五部分：改动范围

### 需要修改的文件

| 文件 | 改动内容 |
|------|---------|
| `app/models/user.py` | 字段重命名 `llm_*` -> `thinking_*`，`intent_*` -> `fast_*` |
| `app/models/config.py` | 字段重命名 `openai_*` -> `thinking_*`，`intent_*` -> `fast_*` |
| `app/utils/llm_config.py` | 函数重命名 + 回退链调整（极速回退到思考） |
| `app/api/routes/users.py` | API 字段重命名 + 测试端点逻辑适配 |
| `app/api/routes/chat.py` | 模型选择逻辑：`enable_think` 决定用思考/极速模型 |
| `app/agent/router/l1_classifier.py` | 调用 `get_fast_llm_config()` |
| `app/agent/router/engine.py` | 同上 |
| `app/tasks/chat_queue_task.py` | 调用 `get_thinking_llm_config()` |
| `alembic/versions/` | 新增迁移：重命名列 |
| `AIModelPanel.tsx` | 重新设计 UI，去掉共用开关，双模型并列 |

### 不需要改动的部分

- 聊天界面的 `enable_think` 开关已有，只需调整文案
- `_is_local_model()` / `_is_ollama()` 逻辑不变
- Ollama 原生客户端 / ChatOpenAI 选择逻辑不变
- 意图识别的 L0/L1/L2 管道逻辑不变

### 风险点

1. **前端旧缓存**：API 字段名变更后，用户浏览器可能有旧 JS 缓存，Next.js 重新构建后自动失效
2. **迁移顺序**：Alembic 迁移必须在代码部署前执行，否则代码引用新列名但数据库还是旧列名