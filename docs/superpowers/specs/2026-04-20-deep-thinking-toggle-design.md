# 深度思考按钮设计

## 概述

在聊天输入框发送按钮旁增加"深度思考"切换按钮，控制主聊天 LLM 是否启用 think 模式。意图分类始终 `think=False`，不受影响。

## UI 设计

- **位置**：发送按钮左侧，与发送按钮同行
- **外观**：🧠 图标按钮，选中时高亮（紫色），未选中时灰色
- **默认状态**：未选中（`enable_think=False`）
- **状态**：组件本地 `useState`，不持久化

## 数据流

```
ChatInputBox [🧠 toggle] → onSend(text, enableThink)
  → ChatStage → transport body: { data: { ..., enableThink } }
    → BFF (/api/chat/route.ts) → backend: { ..., enable_think }
      → chat.py:
        is_local ? ollama.AsyncClient(think=enable_think) : ChatOpenAI(extra_body=thinking_config)
          → StreamContentFilter → data-thinking SSE → 前端思考框
```

## 后端改动

### ChatRequest Schema

`app/schemas/chat.py` 新增字段：

```python
enable_think: bool = False  # 是否启用深度思考模式
```

### chat.py 主聊天 LLM

根据 `is_local_model` 分支处理：

**本地 Ollama**：
- `enable_think=True`：改用 `ollama.AsyncClient` 流式调用，传入 `think=True`
- `enable_think=False`：保持现有 `ChatOpenAI` 流式调用

**第三方 API**：
- `enable_think=True`：在 `ChatOpenAI` 的 `extra_body` 中传入 `thinking` 配置（如 Claude 的 `thinking: {"type": "enabled", "budget_tokens": 10000}`）
- `enable_think=False`：不传 `thinking` 配置

### 意图分类

`IntentRouterEngine.route()` 和 `L1Classifier.classify()` 始终 `enable_think=False`，不受按钮影响。

## 前端改动

### ChatInputBox

- 新增 `enableThink` 本地 state（默认 `false`）
- 发送按钮左侧渲染 🧠 切换按钮
- `onSend` 签名扩展为 `(text: string, enableThink: boolean) => void`

### ChatStage

- `handleSendWrapper` 接收 `enableThink` 参数
- 通过 `data` 字段传递给 Vercel AI SDK transport

### BFF 代理

`/api/chat/route.ts` 从请求 body 的 `data.enableThink` 提取并转发给后端。

## 不做的事

- 不持久化按钮状态（每次发送独立决定）
- 不影响意图分类的 think 模式
- 不修改 StreamContentFilter 逻辑（继续被动捕获思考内容）