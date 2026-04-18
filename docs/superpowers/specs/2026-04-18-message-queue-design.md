# 消息队列与流式输出修复设计

**日期:** 2026-04-18
**状态:** 已批准

---

## 概述

为 Autonome Studio 添加消息队列功能，允许用户在 AI 回复期间连续发送消息，消息进入后端持久化队列顺序处理。同时修复 SSE 流式输出被代理缓冲导致"一瞬间全部出现"的问题。

## 需求

1. **消息队列**：用户可连续发送消息，消息排队后 AI 逐个处理
2. **队列管理**：用户可查看、删除、编辑、调整顺序、清空队列
3. **后端持久化**：队列存储在数据库 + Redis，刷新页面后可恢复
4. **流式输出修复**：AI 回复应逐 token 流动输出，而非一次性出现

## 方案选择

| 方案 | 描述 | 持久化 | 复杂度 |
|------|------|--------|--------|
| A (选定) | 前端队列 + Redis 后端队列 + Celery 顺序消费 | 是 | 中 |
| B | 纯前端串行 SSE | 否 | 低 |
| C | 后端全管控 + WebSocket | 是 | 高 |

选择方案 A：利用现有 Celery + Redis 基础设施，满足持久化需求，前端改动可控。

---

## 第 1 节：数据模型与后端队列

### 新增数据库模型：ChatQueueItem

```python
class ChatQueueItem(SQLModel, table=True):
    __tablename__ = "chat_queue_item"

    id: str                         # UUID, 主键
    session_id: str                 # FK → chatsession.id
    project_id: str                 # FK → project.id
    user_id: str                    # FK → user.id
    status: str                     # pending | processing | completed | failed | cancelled
    message: str                    # 用户消息内容
    attachments: Optional[dict]     # JSONB: files, images, skill 等
    position: int                   # 队列中的位置（用于排序）
    result_message_id: Optional[str] # 处理完成后关联的 ChatMessage.id
    error: Optional[str]            # 失败原因
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
```

### Redis 队列结构

- 每个 session 一个 Redis List：`chat_queue:{session_id}`
- 存储 queue_item_id
- Celery worker 用 `BLPOP` 阻塞消费，保证顺序

### 新增 API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/chat/queue` | 提交消息到队列 |
| GET | `/api/chat/queue/{session_id}` | 获取队列状态 |
| PATCH | `/api/chat/queue/{item_id}` | 编辑/取消队列项 |
| DELETE | `/api/chat/queue/{item_id}` | 删除队列项 |
| DELETE | `/api/chat/queue/session/{session_id}` | 清空队列 |
| PATCH | `/api/chat/queue/reorder` | 调整顺序 |

### Celery Task

新增 `process_chat_queue_item` task：
1. 从 Redis 取出 item_id
2. 更新状态为 processing
3. 调用现有 LLM 流式逻辑
4. 通过 Redis pub/sub (`chat_stream:{session_id}`) 将 SSE 事件推送给 SSE 连接进程
5. SSE 连接进程订阅 Redis channel，将事件转发给前端
6. 更新状态为 completed

**SSE 推送机制**：Celery worker 无法直接持有 SSE 连接，因此采用 Redis pub/sub 中转：
- Celery worker 将 SSE 事件发布到 `chat_stream:{session_id}` channel
- SSE 连接进程（FastAPI 端）订阅该 channel，实时转发给前端
- 这与现有 SSE 架构兼容，无需引入 WebSocket

---

## 第 2 节：SSE 推送与消息关联

### SSE 事件扩展

在现有事件类型基础上新增：

| 事件 | 数据 | 用途 |
|------|------|------|
| `queue_start` | `{"queue_item_id": "...", "user_message": "..."}` | 标识开始处理哪个队列项 |
| `queue_progress` | `{"queue_item_id": "...", "position": 2, "total": 5}` | 队列进度通知 |
| `queue_complete` | `{"queue_item_id": "...", "result_message_id": "..."}` | 队列项处理完成 |
| `queue_error` | `{"queue_item_id": "...", "error": "..."}` | 队列项处理失败 |
| `queue_done` | `{}` | 全部队列项处理完毕 |

现有 `message`/`ai_message_id`/`ai_message_content`/`done` 事件保持不变。前端通过 `queue_start` 事件知道当前流式内容属于哪个队列项。

### SSE 连接策略

复用现有 SSE 连接。前端在第一个消息发送时建立 SSE 连接，该连接保持打开，后端顺序推送所有队列项的回复。全部队列项处理完毕后发送 `queue_done` 事件，前端可选择关闭连接或保持等待新消息。

```
前端 SSE 连接 (长连接)
  ├── queue_start(item_1) → message chunks → done → queue_complete(item_1)
  ├── queue_start(item_2) → message chunks → done → queue_complete(item_2)
  └── queue_done (全部完成)
```

### SSE 防缓冲头修复

在 `EventSourceResponse` 中添加：

```python
headers={
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}
```

应用于 `chat.py` 和 `tasks.py` 中的所有 `EventSourceResponse` 调用。

---

## 第 3 节：前端队列管理与 UI

### 前端状态扩展

在 `useChatStore` 中新增：

```typescript
// 队列状态
queueItems: ChatQueueItem[]          // 当前会话的队列项
isQueueActive: boolean               // 队列是否正在处理

// 队列操作
addToQueue(message, attachments)     // 添加到队列（替代直接发送）
removeFromQueue(itemId)              // 删除队列项
updateQueueItem(itemId, updates)     // 编辑队列项
reorderQueue(itemIds)                // 调整顺序
clearQueue()                         // 清空队列
```

### 发送流程变更

```
用户点击发送
  ├── AI 空闲 → 直接发送（现有逻辑，走 /api/chat/stream）
  └── AI 忙碌 → POST /api/chat/queue → 消息进入队列
                  前端立即显示用户消息 + "排队中" 标签
```

### UI：聊天区嵌入指示器

在聊天区域底部（输入框上方）显示队列指示器。

**队列有消息时：**

```
┌─────────────────────────────────────────┐
│ 📋 队列中: 3条消息  [展开] [清空]        │
├─────────────────────────────────────────┤  ← 展开后
│ 1. "请分析这个基因的表达..."  [编辑][删除] │
│ 2. "帮我画一个火山图"       [编辑][删除] │
│ 3. "生成差异分析报告"       [编辑][删除] │
│                    [拖拽调整顺序]         │
└─────────────────────────────────────────┘
```

**队列项状态标签：**

- `pending` — 灰色 "排队中 #2"
- `processing` — 蓝色脉冲 "处理中..."
- `completed` — 绿色 "已完成"（短暂显示后消失）
- `failed` — 红色 "失败" + 重试按钮

### 用户消息气泡增强

排队中的用户消息在气泡右上角显示状态标签，AI 回复到达时标签变为"回复中"，完成后标签消失。

---

## 第 4 节：错误处理与边界情况

### 错误场景

| 场景 | 处理方式 |
|------|----------|
| 队列项处理失败 | 标记 `failed`，SSE 推送 `queue_error` 事件，前端显示重试按钮，继续处理下一条 |
| 用户取消正在处理的项 | 中断当前 SSE 流，标记 `cancelled`，继续处理下一条 |
| 用户取消排队中的项 | 直接从 Redis list 移除，标记 `cancelled` |
| SSE 连接断开 | 前端自动重连，GET `/api/chat/queue/{session_id}` 恢复队列状态，processing 项重试 |
| 计费不足 | 队列项标记 `failed`，error="余额不足"，后续项仍排队但暂停处理，提示用户充值 |
| 队列项超时 | Celery task 设置 `time_limit`，超时后标记 `failed` |

### 并发控制

- 每个 session 同时只有 1 个 processing 项
- Celery worker 用 Redis 锁 `chat_queue_lock:{session_id}` 防止并发处理
- 前端 `isQueueActive` 状态防止重复提交

### 队列容量限制

- 每个 session 最多 20 条排队消息
- 超出时前端提示"队列已满，请等待当前消息处理完成"

---

## 涉及文件

### 后端新增

| 文件 | 用途 |
|------|------|
| `app/models/chat_queue.py` | ChatQueueItem 模型 |
| `app/api/routes/chat_queue.py` | 队列 API 路由 |
| `app/services/chat_queue_service.py` | 队列业务逻辑 |
| `app/tasks/chat_queue_task.py` | Celery task 定义 |

### 后端修改

| 文件 | 修改内容 |
|------|----------|
| `app/models/domain.py` | 重导出 ChatQueueItem |
| `app/api/routes/chat.py` | SSE 防缓冲头 + 队列事件推送 |
| `app/api/routes/tasks.py` | SSE 防缓冲头 |
| `app/services/celery_app.py` | 注册新 task |
| `main.py` | 注册新路由 |

### 前端修改

| 文件 | 修改内容 |
|------|----------|
| `src/store/useChatStore.ts` | 新增队列状态和操作 |
| `src/hooks/useChatStream.ts` | 处理队列 SSE 事件 + 发送逻辑变更 |
| `src/components/chat/ChatStage.tsx` | 队列指示器集成 |
| `src/components/chat/QueueIndicator.tsx` | 新增：队列指示器组件 |
| `src/components/chat/QueueItemCard.tsx` | 新增：队列项卡片组件 |
| `src/components/chat/MessageBubble.tsx` | 消息气泡状态标签 |
| `src/lib/api.ts` | 新增队列 API 调用 |
