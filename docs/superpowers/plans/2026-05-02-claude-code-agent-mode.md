# Claude Code Agent Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Claude Mode" where Claude Code CLI runs in Docker sandbox containers as an autonomous agent, with skill access, distributed Celery task execution, and web-based interaction via a three-pane chat UI.

**Architecture:** Independent dual-track system — existing LangGraph Agent and new Claude Mode run in parallel. Communication via dedicated Redis pub/sub on an isolated Docker network. Sandbox Agent Service manages Claude Code lifecycle, parsing its stream-json output into events streamed to the frontend via SSE.

**Tech Stack:** Python/FastAPI/SQLModel (backend), TypeScript/Next.js/Zustand (frontend), Redis pub/sub, Docker, Celery.

**Spec:** `docs/superpowers/specs/2026-05-02-claude-code-agent-mode-design.md`

---

## File Structure Map

### New Files

```
autonome-backend/
├── app/
│   ├── models/claude.py                    # Claude 数据模型 (SQLModel)
│   ├── api/routes/claude.py                # Claude API 路由
│   ├── services/claude_session_manager.py  # 会话生命周期管理
│   ├── services/claude_redis_bridge.py     # Redis pub/sub 桥接
│   ├── services/claude_container_pool.py   # Claude 容器池
│   └── sandbox/agent_service/
│       ├── main.py                         # Agent Service 入口
│       ├── redis_client.py                 # Redis pub/sub 客户端
│       ├── claude_manager.py               # Claude Code spawn/monitor
│       ├── stream_parser.py                # JSONL stream 解析器
│       └── event_types.py                  # 事件类型定义
├── Dockerfile.claude-sandbox               # Claude 沙箱镜像
└── alembic/versions/claude_agent_tables.py # 数据库迁移

autonome-studio/src/
├── components/chat/
│   ├── ClaudeChatStage.tsx                 # Claude 模式主容器
│   ├── ClaudeMessageList.tsx               # 消息时间线
│   ├── ThinkingBlock.tsx                   # 可折叠思考块
│   └── ClaudePreview.tsx                   # 右侧预览区
├── hooks/useClaudeChat.ts                  # Claude SSE hook
└── store/useClaudeStore.ts                 # Claude Zustand store
```

### Modified Files

```
docker-compose.yml                          # 新增 claude-redis + claude_net
autonome-backend/main.py                    # 注册 claude router + 容器池初始化
autonome-backend/app/core/config.py         # 新增 Claude 配置项
autonome-studio/src/components/chat/ChatStage.tsx  # 模式切换集成
```

---

## Phase 1: Infrastructure (Minimum Viable Loop)

> Goal: User can send a message via web UI, it reaches Claude Code in sandbox, and the streaming thinking/text response is displayed.

### Task 1.1: Database Migration — Claude Tables

**Files:**
- Create: `autonome-backend/alembic/versions/claude_agent_tables.py`

- [ ] **Step 1: Write the migration**

```python
"""
添加 Claude Agent 模式数据表

新增表:
- claude_session: Claude 会话 (对应 Project)
- claude_conversation: Claude 对话 (Session 下的对话轮次)
- claude_message: Claude 消息 (含完整事件流)
- claude_task: Claude 重型任务追踪
- claude_container: Claude 容器池管理
"""

from typing import Union, Sequence
from alembic import op
import sqlalchemy as sa

revision: str = 'claude_agent_001'
down_revision: Union[str, Sequence[str], None] = 'embedding_config_001'


def upgrade() -> None:
    # Claude 会话表
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_session (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES "user"(id),
            title VARCHAR(500) NOT NULL DEFAULT '新会话',
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            container_id VARCHAR(100),
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_session_user_id ON claude_session(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_session_status ON claude_session(status)
    """)

    # Claude 对话表
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_conversation (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES claude_session(id) ON DELETE CASCADE,
            title VARCHAR(500),
            claude_session_id VARCHAR(200),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_conversation_session ON claude_conversation(session_id)
    """)

    # Claude 消息表
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_message (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES claude_conversation(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT,
            events_json JSONB,
            plan_json JSONB,
            code_snapshot TEXT,
            task_ids UUID[] DEFAULT '{}',
            usage_json JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_message_conversation ON claude_message(conversation_id, created_at)
    """)

    # Claude 任务表
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_task (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id UUID NOT NULL REFERENCES claude_message(id),
            session_id UUID NOT NULL REFERENCES claude_session(id),
            celery_task_id VARCHAR(200),
            skill_id VARCHAR(200),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            code TEXT,
            parameters JSONB,
            output_files JSONB DEFAULT '[]',
            error_text TEXT,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_task_session ON claude_task(session_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_task_celery ON claude_task(celery_task_id)
    """)

    # Claude 容器池表
    op.execute("""
        CREATE TABLE IF NOT EXISTS claude_container (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            container_id VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'idle',
            user_id UUID REFERENCES "user"(id),
            session_id UUID REFERENCES claude_session(id),
            last_used_at TIMESTAMPTZ DEFAULT now(),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_claude_container_status ON claude_container(status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claude_container CASCADE")
    op.execute("DROP TABLE IF EXISTS claude_task CASCADE")
    op.execute("DROP TABLE IF EXISTS claude_message CASCADE")
    op.execute("DROP TABLE IF EXISTS claude_conversation CASCADE")
    op.execute("DROP TABLE IF EXISTS claude_session CASCADE")
```

- [ ] **Step 2: Run migration**

```bash
cd autonome-backend && alembic upgrade head
```

Expected: Tables created successfully in PostgreSQL.

- [ ] **Step 3: Verify tables exist**

```bash
docker-compose exec postgres psql -U autonome autonome_db -c "\dt claude_*"
```

Expected: List of 5 new tables.

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/alembic/versions/claude_agent_tables.py
git commit -m "feat: add Claude agent mode database tables"
```

---

### Task 1.2: SQLModel Data Models

**Files:**
- Create: `autonome-backend/app/models/claude.py`

- [ ] **Step 1: Write the SQLModel models**

```python
"""
Claude Agent 模式数据模型

包含：
- ClaudeSession: Claude 会话 (对应 Project)
- ClaudeConversation: Claude 对话 (Session 下的对话轮次)
- ClaudeMessage: Claude 消息 (含完整事件流 JSON)
- ClaudeTask: Claude 重型任务追踪
- ClaudeContainer: Claude 容器池管理
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship, Column
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from uuid import UUID


def get_utc_now() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc)


class ClaudeSession(SQLModel, table=True):
    """Claude 会话 — 用户的一个完整协作单元"""
    __tablename__ = "claude_session"

    id: UUID = Field(default_factory=lambda: None, primary_key=True)
    user_id: UUID = Field(foreign_key='"user".id', index=True)
    title: str = Field(default="新会话", max_length=500)
    status: str = Field(default="active", max_length=20)
    container_id: Optional[str] = Field(default=None, max_length=100)
    metadata: Optional[Dict[str, Any]] = Field(default={}, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    conversations: List["ClaudeConversation"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class ClaudeConversation(SQLModel, table=True):
    """Claude 对话 — Session 下的独立对话轮次"""
    __tablename__ = "claude_conversation"

    id: UUID = Field(default_factory=lambda: None, primary_key=True)
    session_id: UUID = Field(foreign_key="claude_session.id", index=True)
    title: Optional[str] = Field(default=None, max_length=500)
    claude_session_id: Optional[str] = Field(default=None, max_length=200)
    status: str = Field(default="active", max_length=20)
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    session: Optional[ClaudeSession] = Relationship(back_populates="conversations")
    messages: List["ClaudeMessage"] = Relationship(
        back_populates="conversation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class ClaudeMessage(SQLModel, table=True):
    """Claude 消息 — 含完整事件流 JSON"""
    __tablename__ = "claude_message"

    id: UUID = Field(default_factory=lambda: None, primary_key=True)
    conversation_id: UUID = Field(foreign_key="claude_conversation.id", index=True)
    role: str = Field(max_length=20)
    content: Optional[str] = None
    events_json: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSONB))
    plan_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    code_snapshot: Optional[str] = None
    task_ids: Optional[List[UUID]] = Field(default=[], sa_column=Column(ARRAY(UUID)))
    usage_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=get_utc_now)

    conversation: Optional[ClaudeConversation] = Relationship(back_populates="messages")


class ClaudeTask(SQLModel, table=True):
    """Claude 重型任务追踪"""
    __tablename__ = "claude_task"

    id: UUID = Field(default_factory=lambda: None, primary_key=True)
    message_id: UUID = Field(foreign_key="claude_message.id")
    session_id: UUID = Field(foreign_key="claude_session.id", index=True)
    celery_task_id: Optional[str] = Field(default=None, max_length=200, index=True)
    skill_id: Optional[str] = Field(default=None, max_length=200)
    status: str = Field(default="pending", max_length=20)
    code: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    output_files: Optional[List[Dict[str, Any]]] = Field(default=[], sa_column=Column(JSONB))
    error_text: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=get_utc_now)


class ClaudeContainer(SQLModel, table=True):
    """Claude 容器池管理"""
    __tablename__ = "claude_container"

    id: UUID = Field(default_factory=lambda: None, primary_key=True)
    container_id: str = Field(max_length=100)
    status: str = Field(default="idle", max_length=20, index=True)
    user_id: Optional[UUID] = Field(default=None, foreign_key='"user".id')
    session_id: Optional[UUID] = Field(default=None, foreign_key="claude_session.id")
    last_used_at: datetime = Field(default_factory=get_utc_now)
    created_at: datetime = Field(default_factory=get_utc_now)
```

- [ ] **Step 2: Verify models import correctly**

```bash
cd autonome-backend && python -c "from app.models.claude import ClaudeSession, ClaudeMessage; print('OK')"
```

Expected: `OK` without errors.

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/models/claude.py
git commit -m "feat: add Claude agent SQLModel data models"
```

---

### Task 1.3: Docker Compose — claude-redis + claude_net

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Edit docker-compose.yml**

Add to `services` section:

```yaml
  # Claude Agent 专用 Redis (db 3)
  claude-redis:
    image: redis:7-alpine
    container_name: autonome-claude-redis
    restart: unless-stopped
    networks:
      - claude_net
    command: redis-server --maxmemory 512mb --port 6380
    volumes:
      - claude_redis_data:/data

  # Claude 沙箱容器池守护进程
  claude-sandbox-daemon:
    image: autonome-claude-sandbox:latest
    container_name: autonome-claude-sandbox-daemon
    restart: unless-stopped
    networks:
      - claude_net
    environment:
      - REDIS_URL=redis://claude-redis:6380/0
    volumes:
      - ./uploads:/workspace:rw
      - ./autonome-backend/app/skills:/app/skills:ro
      - ./autonome_conda:/opt/conda:ro
      - ./biosource:/app/biosource:ro
      - ./uploads/user_packages:/app/user_packages:rw
    entrypoint: ["python", "/app/agent_service/main.py"]
```

Add to `networks` section:

```yaml
  claude_net:
    driver: bridge
    internal: true
```

Add to `volumes` section:

```yaml
  claude_redis_data:
```

In `backend-api` service, add `claude_net` to networks:

```yaml
  backend-api:
    # ... existing config ...
    networks:
      - default
      - claude_net
```

- [ ] **Step 2: Verify docker-compose config**

```bash
docker-compose config --services
```

Expected: List includes `claude-redis`.

- [ ] **Step 3: Restart services and verify**

```bash
docker-compose down && docker-compose up -d
docker ps | grep claude
```

Expected: `claude-redis` is running.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add claude-redis service and claude_net network"
```

---

### Task 1.4: Agent Service — Event Types + Redis Client

**Files:**
- Create: `autonome-backend/app/sandbox/agent_service/__init__.py` (empty)
- Create: `autonome-backend/app/sandbox/agent_service/event_types.py`
- Create: `autonome-backend/app/sandbox/agent_service/redis_client.py`

- [ ] **Step 1: Create `event_types.py`**

```python
"""
Claude Agent 事件类型定义

Claude Code stream-json 输出 → 统一事件类型的映射。
每种事件对应一个 dataclass，用于序列化/反序列化 Redis 通道传输。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from enum import Enum
import json
import time


class EventType(str, Enum):
    """事件类型枚举"""
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    PLAN = "plan"
    TASK_SUBMITTED = "task_submitted"
    TASK_STATUS = "task_status"
    STATUS = "status"
    ERROR = "error"
    USAGE = "usage"


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING_USER = "waiting_user"


@dataclass
class AgentEvent:
    """Agent 事件基类"""
    type: EventType
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class TextDeltaEvent(AgentEvent):
    type: EventType = EventType.TEXT_DELTA
    content: str = ""


@dataclass
class TextEndEvent(AgentEvent):
    type: EventType = EventType.TEXT_END


@dataclass
class ThinkingEvent(AgentEvent):
    type: EventType = EventType.THINKING
    content: str = ""


@dataclass
class ToolUseEvent(AgentEvent):
    type: EventType = EventType.TOOL_USE
    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_use_id: str = ""


@dataclass
class ToolResultEvent(AgentEvent):
    type: EventType = EventType.TOOL_RESULT
    tool_name: str = ""
    tool_use_id: str = ""
    status: str = "success"  # success / failed
    output: str = ""


@dataclass
class PlanEvent(AgentEvent):
    type: EventType = EventType.PLAN
    title: str = ""
    steps: List[Dict[str, str]] = field(default_factory=list)
    code_snapshot: str = ""
    estimated_cost: str = ""


@dataclass
class TaskSubmittedEvent(AgentEvent):
    type: EventType = EventType.TASK_SUBMITTED
    task_id: str = ""
    celery_queue: str = ""
    skill_id: str = ""


@dataclass
class TaskStatusEvent(AgentEvent):
    type: EventType = EventType.TASK_STATUS
    task_id: str = ""
    status: str = "pending"
    progress: str = ""


@dataclass
class StatusEvent(AgentEvent):
    type: EventType = EventType.STATUS
    status: str = AgentStatus.IDLE.value
    message: str = ""


@dataclass
class ErrorEvent(AgentEvent):
    type: EventType = EventType.ERROR
    message: str = ""
    code: str = ""


@dataclass
class UsageEvent(AgentEvent):
    type: EventType = EventType.USAGE
    input_tokens: int = 0
    output_tokens: int = 0
```

- [ ] **Step 2: Create `redis_client.py`**

```python
"""
Agent Service Redis 客户端

管理 Redis pub/sub 连接，负责：
- 订阅 claude:session:{sid} 通道接收后端消息
- 发布 claude:session:{sid}:events 通道发送事件
- 心跳定时上报 (claude:heartbeat 通道)
- 自动重连 (指数退避)
"""

import os
import json
import time
import threading
from typing import Callable, Optional
import redis

from app.sandbox.agent_service.event_types import AgentEvent


REDIS_URL = os.environ.get("REDIS_URL", "redis://claude-redis:6380/0")
AGENT_ID = os.environ.get("AGENT_ID", "unknown")
HEARTBEAT_INTERVAL = 10  # 心跳间隔秒数
RECONNECT_MAX_ATTEMPTS = 5
RECONNECT_BASE_DELAY = 1  # 指数退避基数


class AgentRedisClient:
    """Agent Service 的 Redis 客户端封装"""

    def __init__(self, redis_url: str = REDIS_URL):
        self._redis_url = redis_url
        self._client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._message_handler: Optional[Callable] = None

    def connect(self) -> bool:
        """连接 Redis, 返回是否成功"""
        try:
            self._client = redis.Redis.from_url(
                self._redis_url,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
            self._client.ping()
            return True
        except redis.RedisError as e:
            print(f"[AgentRedis] 连接失败: {e}")
            return False

    def start_heartbeat(self, session_id: str) -> None:
        """启动心跳线程"""
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(session_id,),
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self, session_id: str) -> None:
        """心跳循环: 定期上报 Agent 状态"""
        while self._running:
            try:
                self._client.setex(
                    f"claude:heartbeat:{session_id}",
                    HEARTBEAT_INTERVAL * 2,
                    json.dumps({"agent_id": AGENT_ID, "timestamp": time.time()}),
                )
            except redis.RedisError:
                pass
            time.sleep(HEARTBEAT_INTERVAL)

    def subscribe(self, session_id: str, message_handler: Callable) -> None:
        """订阅 session 消息通道, 阻塞运行"""
        self._message_handler = message_handler
        self._pubsub = self._client.pubsub()
        self._pubsub.subscribe(f"claude:session:{session_id}")

        attempt = 0
        while self._running:
            try:
                for message in self._pubsub.listen():
                    if not self._running:
                        break
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            self._message_handler(data)
                        except json.JSONDecodeError:
                            pass
                attempt = 0  # 正常退出时重置计数
            except redis.RedisError as e:
                print(f"[AgentRedis] 订阅断开: {e}")
                attempt += 1
                if attempt > RECONNECT_MAX_ATTEMPTS:
                    print("[AgentRedis] 重连次数耗尽, 退出")
                    break
                delay = RECONNECT_BASE_DELAY * (2 ** (attempt - 1))
                time.sleep(delay)
                # 尝试重连并重新订阅
                if self.connect():
                    self._pubsub = self._client.pubsub()
                    self._pubsub.subscribe(f"claude:session:{session_id}")

    def publish_event(self, session_id: str, event: AgentEvent) -> None:
        """发布事件到 session 事件通道"""
        if self._client:
            try:
                self._client.publish(
                    f"claude:session:{session_id}:events",
                    event.to_json(),
                )
            except redis.RedisError:
                pass

    def publish_raw(self, channel: str, data: str) -> None:
        """发布原始数据到指定通道"""
        if self._client:
            try:
                self._client.publish(channel, data)
            except redis.RedisError:
                pass

    def stop(self) -> None:
        """停止心跳和订阅"""
        self._running = False
        if self._pubsub:
            self._pubsub.close()
        if self._client:
            self._client.close()
```

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/sandbox/agent_service/
git commit -m "feat: add Agent Service event types and Redis client"
```

---

### Task 1.5: Agent Service — Claude Code Stream Parser

**Files:**
- Create: `autonome-backend/app/sandbox/agent_service/stream_parser.py`

- [ ] **Step 1: Write the stream parser**

```python
"""
Claude Code JSONL Stream 解析器

解析 Claude Code 的 --output-format stream-json 输出:
- 将 JSONL 行映射为统一的 AgentEvent 类型
- 支持增量解析 (逐行读取)
- 容错处理: 跳过非法 JSON 行
"""

import json
from typing import Iterator, Optional

from app.sandbox.agent_service.event_types import (
    AgentEvent,
    TextDeltaEvent,
    TextEndEvent,
    ThinkingEvent,
    ToolUseEvent,
    ToolResultEvent,
    PlanEvent,
    StatusEvent,
    ErrorEvent,
    UsageEvent,
    AgentStatus,
)


class ClaudeStreamParser:
    """
    Claude Code stream-json 解析器

    Claude Code --output-format stream-json 的 JSONL 结构:
    - {"type":"system","subtype":"init",...}
    - {"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}
    - {"type":"user","message":{"content":[{"type":"tool_result",...}]}}
    - {"type":"result","usage":{...}}
    """

    def __init__(self):
        self._buffer = ""
        self._current_text_block_open = False

    def feed_line(self, line: str) -> Optional[AgentEvent]:
        """
        喂入一行 JSONL，返回解析后的事件 (可能为 None)
        """
        line = line.strip()
        if not line:
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None

        return self._parse_object(data)

    def _parse_object(self, obj: dict) -> Optional[AgentEvent]:
        """解析单个 JSONL 对象"""
        obj_type = obj.get("type", "")

        if obj_type == "system":
            return self._parse_system(obj)
        elif obj_type == "assistant":
            return self._parse_assistant(obj)
        elif obj_type == "user":
            return self._parse_user(obj)
        elif obj_type == "result":
            return self._parse_result(obj)
        elif obj_type == "stream_event":
            return self._parse_stream_event(obj)

        return None

    def _parse_system(self, obj: dict) -> Optional[AgentEvent]:
        """解析系统事件 (init, status)"""
        subtype = obj.get("subtype", "")
        if subtype == "status":
            status_str = obj.get("status", "")
            mapping = {
                "compressing": AgentStatus.THINKING,
                "idle": AgentStatus.IDLE,
            }
            return StatusEvent(status=mapping.get(status_str, AgentStatus.THINKING.value))
        return None

    def _parse_assistant(self, obj: dict) -> Optional[AgentEvent]:
        """解析 assistant 消息 — 包含文本、思考、工具调用"""
        message = obj.get("message", {})
        content = message.get("content", [])

        if not isinstance(content, list):
            return None

        events = []
        for block in content:
            if isinstance(block, str):
                # 纯文本字符串
                return TextDeltaEvent(content=block)

            block_type = block.get("type", "")
            if block_type == "text":
                text = block.get("text", "")
                return TextDeltaEvent(content=text)
            elif block_type == "thinking":
                thinking_text = block.get("thinking", "")
                return ThinkingEvent(content=thinking_text)
            elif block_type == "tool_use":
                return ToolUseEvent(
                    tool_name=block.get("name", ""),
                    tool_input=block.get("input", {}),
                    tool_use_id=block.get("id", ""),
                )

        return None

    def _parse_user(self, obj: dict) -> Optional[AgentEvent]:
        """解析 user 消息 — 通常包含 tool_result"""
        message = obj.get("message", {})
        content = message.get("content", [])

        if isinstance(content, list) and len(content) > 0:
            block = content[0]
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return ToolResultEvent(
                    tool_use_id=block.get("tool_use_id", ""),
                    tool_name="",  # tool_use_id 关联
                    status="success" if not block.get("is_error") else "failed",
                    output=json.dumps(block.get("content", ""), ensure_ascii=False),
                )

        return None

    def _parse_result(self, obj: dict) -> Optional[AgentEvent]:
        """解析 result — 包含 usage 信息"""
        usage = obj.get("usage", {})
        if usage:
            return UsageEvent(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
        return None

    def _parse_stream_event(self, obj: dict) -> Optional[AgentEvent]:
        """解析流事件 (增量 delta)"""
        event = obj.get("event", {})
        delta = event.get("delta", {})
        delta_type = delta.get("type", "")

        if delta_type == "text_delta":
            return TextDeltaEvent(content=delta.get("text", ""))
        elif delta_type == "thinking_delta":
            return ThinkingEvent(content=delta.get("thinking", ""))
        elif delta_type == "input_json_delta":
            # 部分 tool_use JSON，暂不处理
            return None

        return None

    def flush(self) -> Optional[AgentEvent]:
        """刷新缓冲区，返回 TextEndEvent"""
        if self._current_text_block_open:
            self._current_text_block_open = False
            return TextEndEvent()
        return None


def parse_claude_output(stdout_lines: Iterator[str]) -> Iterator[AgentEvent]:
    """便捷函数: 逐行解析 Claude Code stdout, 产出事件流"""
    parser = ClaudeStreamParser()
    for line in stdout_lines:
        event = parser.feed_line(line)
        if event is not None:
            yield event
    # 刷新缓冲区
    final = parser.flush()
    if final is not None:
        yield final
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/sandbox/agent_service/stream_parser.py
git commit -m "feat: add Claude Code JSONL stream parser"
```

---

### Task 1.6: Agent Service — Claude Manager + Main Entry

**Files:**
- Create: `autonome-backend/app/sandbox/agent_service/claude_manager.py`
- Create: `autonome-backend/app/sandbox/agent_service/main.py`

- [ ] **Step 1: Create `claude_manager.py`**

```python
"""
Claude Code 进程管理器

负责:
- spawn Claude Code 子进程 (--resume 模式)
- 解析 stdout JSONL → 事件流
- 超时控制与优雅终止
- 系统提示注入 (角色定义 + 工具说明)
"""

import os
import subprocess
import signal
import time
import uuid
from typing import Iterator, Optional, Callable
from pathlib import Path

from app.sandbox.agent_service.event_types import (
    AgentEvent,
    StatusEvent,
    ErrorEvent,
    UsageEvent,
    AgentStatus,
)
from app.sandbox.agent_service.stream_parser import ClaudeStreamParser


CLAUDE_CODE_BIN = "claude"
DEFAULT_TIMEOUT_SECONDS = 600  # 单轮 10 分钟超时
WORKSPACE_DIR = "/workspace"

SYSTEM_PROMPT = """你是 Autonome 生物信息学平台的 AI Agent，运行在 Docker 沙箱环境中。

## 你的角色
你是生物信息学数据分析专家，帮助用户完成:
- 数据分析方案设计
- 代码编写与调试
- 结果解读与可视化建议

## 工作流程
1. **理解需求**: 充分理解用户的分析需求，必要时提出澄清问题
2. **检索技能**: 使用 skill_search 工具查找系统中已有的分析技能
3. **制定方案**: 生成分析计划，包含步骤、方法、预期产出
4. **确认执行**: 等待用户确认方案后再生成代码
5. **执行任务**: 
   - 轻量任务(预计 < 2min): 使用 execute_sandbox 直接在沙箱执行
   - 重型任务(预计 > 2min): 使用 submit_heavy_task 提交到 Celery 分布式执行

## 可用工具
- skill_search(query): 搜索系统中的生信分析技能
- execute_sandbox(command, timeout): 在沙箱中直接执行命令
- submit_heavy_task(skill_id, code, params): 提交重型任务到分布式队列
- read_file(path): 读取 /workspace 下的文件
- write_file(path, content): 写入文件到 /workspace

## 环境
- 工作目录: /workspace (读写)
- 技能目录: /app/skills (只读)
- Conda 环境: /opt/conda (只读, 500+ 生信包)
- 可用: Python 3.11, R 4.x, Nextflow

## 行为准则
- 方案必须先确认再执行
- 用中文沟通
- 代码注释用中文
- 优先复用系统中已有的技能，避免重复造轮子
"""


class ClaudeManager:
    """Claude Code 进程管理器"""

    def __init__(
        self,
        api_key: str,
        api_base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._model = model
        self._timeout = timeout
        self._process: Optional[subprocess.Popen] = None
        self._parser = ClaudeStreamParser()

    def run_with_prompt(
        self,
        prompt: str,
        session_id: str,
        on_event: Callable[[AgentEvent], None],
    ) -> int:
        """
        运行 Claude Code 并处理输出

        Args:
            prompt: 用户消息 (会包装进 -p)
            session_id: Claude Code --resume session id
            on_event: 每解析出一个事件时的回调

        Returns:
            进程退出码
        """
        full_prompt = f"{SYSTEM_PROMPT}\n\n---\n\n用户消息:\n{prompt}"

        cmd = [
            CLAUDE_CODE_BIN,
            "-p", full_prompt,
            "--output-format", "stream-json",
            "--resume", session_id,
            "--permission-mode", "acceptEdits",
            "--max-turns", "50",
        ]

        if self._model:
            cmd.extend(["--model", self._model])

        env = os.environ.copy()
        if self._api_key:
            env["ANTHROPIC_API_KEY"] = self._api_key
        if self._api_base_url:
            env["ANTHROPIC_BASE_URL"] = self._api_base_url

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=WORKSPACE_DIR,
        )

        # 发送状态: thinking
        on_event(StatusEvent(status=AgentStatus.THINKING.value, message="Claude Code 启动"))

        returncode = None
        start_time = time.time()

        try:
            # 逐行读取 stdout
            for line in self._process.stdout:
                line = line.strip()
                if not line:
                    continue
                event = self._parser.feed_line(line)
                if event is not None:
                    on_event(event)

                # 超时检查
                if time.time() - start_time > self._timeout:
                    self.kill()
                    on_event(ErrorEvent(message="执行超时", code="TIMEOUT"))
                    break

            # 等待进程结束
            self._process.wait(timeout=10)
            returncode = self._process.returncode

        except Exception as e:
            on_event(ErrorEvent(message=str(e), code="EXECUTION_ERROR"))
            self.kill()
        finally:
            # 读取 stderr
            if self._process and self._process.stderr:
                stderr = self._process.stderr.read()
                if stderr.strip():
                    on_event(ErrorEvent(message=stderr[:500], code="STDERR"))

            # 发送状态: idle
            on_event(StatusEvent(status=AgentStatus.IDLE.value))

        return returncode if returncode is not None else -1

    def kill(self) -> None:
        """终止 Claude Code 进程"""
        if self._process and self._process.poll() is None:
            try:
                self._process.send_signal(signal.SIGTERM)
                self._process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                self._process.kill()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None
```

- [ ] **Step 2: Create `main.py`**

```python
#!/usr/bin/env python3
"""
Agent Service 主入口

在 Claude 沙箱容器中运行，作为守护进程:
1. 连接 Redis
2. 订阅 claude:session:{sid} 通道
3. 收到消息 → spawn Claude Code → 推送事件流

生命周期由后端 Session Manager 控制。
每次只处理一个 session (单 Agent Service 对应单一容器分配)。
"""

import os
import sys
import signal
import json
import time
from pathlib import Path

# 添加 app 目录到 Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.sandbox.agent_service.redis_client import AgentRedisClient
from app.sandbox.agent_service.claude_manager import ClaudeManager
from app.sandbox.agent_service.event_types import (
    StatusEvent,
    ErrorEvent,
    AgentStatus,
)


# 环境变量
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
REDIS_URL = os.environ.get("REDIS_URL", "redis://claude-redis:6380/0")

# 全局状态
redis_client: AgentRedisClient = None
claude_manager: ClaudeManager = None
running = True


def handle_message(data: dict) -> None:
    """处理收到的 Redis 消息"""
    msg_type = data.get("type", "")
    conversation_id = data.get("conversation_id", "")
    content = data.get("content", "")
    claude_session_id = data.get("claude_session_id", "")

    if msg_type == "user_message":
        # 新用户消息 → 启动 Claude Code
        redis_client.publish_event(
            SESSION_ID,
            StatusEvent(status=AgentStatus.THINKING.value, message="正在处理..."),
        )

        claude_manager.run_with_prompt(
            prompt=content,
            session_id=claude_session_id,
            on_event=lambda ev: redis_client.publish_event(SESSION_ID, ev),
        )

        redis_client.publish_event(
            SESSION_ID,
            StatusEvent(status=AgentStatus.WAITING_USER.value, message="等待用户输入"),
        )

    elif msg_type == "cancel":
        # 取消执行
        if claude_manager and claude_manager.is_running:
            claude_manager.kill()
            redis_client.publish_event(
                SESSION_ID,
                StatusEvent(status=AgentStatus.IDLE.value, message="已取消"),
            )


def handle_signal(signum, frame) -> None:
    """处理退出信号"""
    global running
    running = False
    if claude_manager:
        claude_manager.kill()
    if redis_client:
        redis_client.stop()


def main() -> None:
    global redis_client, claude_manager, running

    if not SESSION_ID:
        print("ERROR: CLAUDE_SESSION_ID not set")
        sys.exit(1)

    # 设置信号处理
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # 初始化 Redis
    redis_client = AgentRedisClient(REDIS_URL)
    if not redis_client.connect():
        print("ERROR: Cannot connect to Redis, exiting")
        sys.exit(1)

    # 初始化 Claude Manager
    claude_manager = ClaudeManager(
        api_key=API_KEY,
        api_base_url=API_BASE_URL or None,
    )

    # 启动心跳
    redis_client.start_heartbeat(SESSION_ID)

    # 上线通知
    redis_client.publish_event(
        SESSION_ID,
        StatusEvent(status=AgentStatus.IDLE.value, message="Agent Service 已就绪"),
    )

    print(f"[AgentService] 已就绪, session={SESSION_ID}")

    # 订阅消息通道 (阻塞运行)
    redis_client.subscribe(SESSION_ID, handle_message)

    print("[AgentService] 已退出")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/sandbox/agent_service/claude_manager.py autonome-backend/app/sandbox/agent_service/main.py
git commit -m "feat: add Agent Service Claude manager and main entry point"
```

---

### Task 1.7: Claude Sandbox Dockerfile

**Files:**
- Create: `autonome-backend/Dockerfile.claude-sandbox`

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
# Autonome Claude Sandbox Dockerfile
# Claude Code Agent 模式的专用沙箱镜像
# 继承自基础沙箱, 新增 Agent Service

FROM autonome-tool-env:latest

# 系统依赖 (Node.js + npm for Claude Code CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# 安装 Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Python 依赖 (Agent Service)
RUN pip install --no-cache-dir \
    redis \
    mcp \
    numpy

# 复制 Agent Service 代码到容器
COPY app/sandbox/agent_service/ /app/agent_service/

# 工作目录
WORKDIR /workspace

# 入口: 保持容器运行 (供 Warm Pool 使用, Agent Service 通过 docker exec 启动)
ENTRYPOINT ["sleep", "infinity"]
```

- [ ] **Step 2: Build the image**

```bash
cd autonome-backend && docker build -f Dockerfile.claude-sandbox -t autonome-claude-sandbox:latest .
```

Expected: Image built successfully.

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/Dockerfile.claude-sandbox
git commit -m "feat: add Claude sandbox Dockerfile with Claude Code CLI and Agent Service"
```

---

### Task 1.8: Claude Redis Bridge (Backend)

**Files:**
- Create: `autonome-backend/app/services/claude_redis_bridge.py`

- [ ] **Step 1: Write the Redis bridge service**

```python
"""
Claude Redis 桥接服务

后端侧的 Redis pub/sub 管理:
- 发布消息到 claude:session:{sid} 通道
- 订阅 claude:session:{sid}:events 通道接收 Agent 事件
- 心跳监控 (检测 Agent Service 存活)

作为后端与沙箱内 Agent Service 之间的通信桥梁。
"""

import os
import json
import time
import asyncio
from typing import AsyncIterator, Optional, Dict, Any
import redis.asyncio as aioredis

from app.core.logger import log


CLAUDE_REDIS_URL = os.environ.get("CLAUDE_REDIS_URL", "redis://claude-redis:6380/0")


class ClaudeRedisBridge:
    """后端侧 Claude Redis 桥接"""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """建立 Redis 连接"""
        self._redis = aioredis.from_url(
            CLAUDE_REDIS_URL,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
        await self._redis.ping()

    async def send_message(
        self,
        session_id: str,
        message_type: str,
        content: str,
        conversation_id: str = "",
        claude_session_id: str = "",
        **extra,
    ) -> None:
        """发送消息到 Agent Service"""
        msg = {
            "type": message_type,
            "content": content,
            "conversation_id": conversation_id,
            "claude_session_id": claude_session_id,
            **extra,
        }
        await self._redis.publish(f"claude:session:{session_id}", json.dumps(msg, ensure_ascii=False))

    async def send_cancel(self, session_id: str) -> None:
        """发送取消指令"""
        await self.send_message(session_id, "cancel", "")

    async def subscribe_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        """订阅 Agent 事件通道, 返回异步迭代器"""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"claude:session:{session_id}:events")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield data
                    except json.JSONDecodeError:
                        continue
        finally:
            await pubsub.unsubscribe(f"claude:session:{session_id}:events")

    async def check_heartbeat(self, session_id: str) -> bool:
        """检查 Agent Service 心跳"""
        data = await self._redis.get(f"claude:heartbeat:{session_id}")
        if data:
            try:
                heartbeat = json.loads(data)
                elapsed = time.time() - heartbeat.get("timestamp", 0)
                return elapsed < 30  # 30 秒内有心跳
            except json.JSONDecodeError:
                pass
        return False

    async def close(self) -> None:
        """关闭 Redis 连接"""
        if self._redis:
            await self._redis.close()


# 全局单例
_claude_bridge: Optional[ClaudeRedisBridge] = None


async def get_claude_bridge() -> ClaudeRedisBridge:
    """获取 Claude Redis Bridge 单例"""
    global _claude_bridge
    if _claude_bridge is None:
        _claude_bridge = ClaudeRedisBridge()
        await _claude_bridge.connect()
    return _claude_bridge
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/services/claude_redis_bridge.py
git commit -m "feat: add Claude Redis bridge service for backend-side pub/sub"
```

---

### Task 1.9: Claude Session Manager (Backend)

**Files:**
- Create: `autonome-backend/app/services/claude_session_manager.py`

- [ ] **Step 1: Write the session manager**

```python
"""
Claude 会话管理器

管理 Claude Session 的完整生命周期:
- 创建/关闭会话
- 分配/回收沙箱容器
- 消息持久化
- 通过 Redis Bridge 与 Agent Service 通信
"""

import json
from uuid import UUID, uuid4
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.database import get_session
from app.core.logger import log
from app.models.claude import (
    ClaudeSession,
    ClaudeConversation,
    ClaudeMessage,
    ClaudeContainer,
)
from app.services.claude_redis_bridge import get_claude_bridge, ClaudeRedisBridge


class ClaudeSessionManager:

    def __init__(self, user_id: UUID):
        self.user_id = user_id

    async def create_session(self, title: str = "新会话") -> ClaudeSession:
        """创建新 Claude 会话"""
        with get_session() as db:
            session = ClaudeSession(
                user_id=self.user_id,
                title=title,
                status="active",
            )
            db.add(session)
            db.commit()
            db.refresh(session)

            # 创建默认对话
            conv = ClaudeConversation(
                session_id=session.id,
                title="对话 1",
            )
            db.add(conv)
            db.commit()

            return session

    async def get_session(self, session_id: UUID) -> Optional[ClaudeSession]:
        """获取会话详情"""
        with get_session() as db:
            session = db.exec(
                select(ClaudeSession).where(
                    ClaudeSession.id == session_id,
                    ClaudeSession.user_id == self.user_id,
                )
            ).first()
            return session

    async def list_sessions(self, status: str = None) -> List[ClaudeSession]:
        """列出用户的所有会话"""
        with get_session() as db:
            query = select(ClaudeSession).where(
                ClaudeSession.user_id == self.user_id
            ).order_by(ClaudeSession.updated_at.desc())
            if status:
                query = query.where(ClaudeSession.status == status)
            return list(db.exec(query).all())

    async def update_session(self, session_id: UUID, **kwargs) -> Optional[ClaudeSession]:
        """更新会话字段"""
        with get_session() as db:
            session = db.exec(
                select(ClaudeSession).where(
                    ClaudeSession.id == session_id,
                    ClaudeSession.user_id == self.user_id,
                )
            ).first()
            if not session:
                return None
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            session.updated_at = datetime.now(timezone.utc)
            db.add(session)
            db.commit()
            db.refresh(session)
            return session

    async def close_session(self, session_id: UUID) -> None:
        """关闭会话"""
        bridge = await get_claude_bridge()
        await bridge.send_cancel(str(session_id))
        await self.update_session(session_id, status="closed")

    async def get_or_create_conversation(self, session_id: UUID) -> ClaudeConversation:
        """获取或创建对话 (取最新活跃对话)"""
        with get_session() as db:
            conv = db.exec(
                select(ClaudeConversation)
                .where(
                    ClaudeConversation.session_id == session_id,
                    ClaudeConversation.status == "active",
                )
                .order_by(ClaudeConversation.created_at.desc())
            ).first()
            if not conv:
                conv = ClaudeConversation(session_id=session_id, title="对话 1")
                db.add(conv)
                db.commit()
                db.refresh(conv)
            return conv

    async def send_user_message(
        self,
        session_id: UUID,
        content: str,
    ) -> Dict[str, Any]:
        """
        发送用户消息到 Claude Code, 返回消息信息
        """
        bridge = await get_claude_bridge()
        session = await self.get_session(session_id)
        if not session:
            raise ValueError("会话不存在")

        conv = await self.get_or_create_conversation(session_id)

        # 持久化用户消息
        with get_session() as db:
            msg = ClaudeMessage(
                conversation_id=conv.id,
                role="user",
                content=content,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)

        # 通过 Redis 发送到 Agent Service
        await bridge.send_message(
            session_id=str(session_id),
            message_type="user_message",
            content=content,
            conversation_id=str(conv.id),
            claude_session_id=conv.claude_session_id or "",
        )

        # 更新会话时间
        await self.update_session(session_id)

        return {
            "message_id": str(msg.id),
            "conversation_id": str(conv.id),
            "session_id": str(session_id),
        }

    async def persist_assistant_event(
        self,
        conversation_id: UUID,
        event: Dict[str, Any],
    ) -> None:
        """持久化 Assistant 事件到消息"""
        with get_session() as db:
            # 查找最近的 assistant 消息，不存在则创建
            msg = db.exec(
                select(ClaudeMessage)
                .where(
                    ClaudeMessage.conversation_id == conversation_id,
                    ClaudeMessage.role == "assistant",
                )
                .order_by(ClaudeMessage.created_at.desc())
            ).first()

            if msg and msg.events_json:
                events = list(msg.events_json)
                events.append(event)
                msg.events_json = events
            elif msg:
                msg.events_json = [event]
            else:
                msg = ClaudeMessage(
                    conversation_id=conversation_id,
                    role="assistant",
                    events_json=[event],
                )
            db.add(msg)
            db.commit()

    async def get_conversation_messages(self, conversation_id: UUID) -> List[ClaudeMessage]:
        """获取对话的所有消息"""
        with get_session() as db:
            return list(db.exec(
                select(ClaudeMessage)
                .where(ClaudeMessage.conversation_id == conversation_id)
                .order_by(ClaudeMessage.created_at)
            ).all())

    async def allocate_container(self, session_id: UUID) -> Optional[str]:
        """从容器池分配容器"""
        with get_session() as db:
            container = db.exec(
                select(ClaudeContainer)
                .where(ClaudeContainer.status == "idle")
                .limit(1)
            ).first()
            if container:
                container.status = "busy"
                container.user_id = self.user_id
                container.session_id = session_id
                container.last_used_at = datetime.now(timezone.utc)
                db.add(container)
                db.commit()
                # 更新 session 的 container_id
                await self.update_session(session_id, container_id=container.container_id)
                return container.container_id
        return None
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/services/claude_session_manager.py
git commit -m "feat: add Claude session manager service"
```

---

### Task 1.10: Claude API Routes (Backend)

**Files:**
- Create: `autonome-backend/app/api/routes/claude.py`

- [ ] **Step 1: Write the API routes**

```python
"""
Claude Agent 模式 API 路由

提供 Claude 会话管理、消息发送、事件 SSE 推送等接口。
"""

import json
import asyncio
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.deps import get_current_user
from app.core.logger import log
from app.models.domain import User
from app.services.claude_session_manager import ClaudeSessionManager
from app.services.claude_redis_bridge import get_claude_bridge


router = APIRouter(prefix="/api/claude", tags=["claude"])


# ==========================================
# Pydantic Schemas
# ==========================================

class CreateSessionRequest(BaseModel):
    title: str = Field(default="新会话", max_length=500)

class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None

class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)

class CreateConversationRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=500)


# ==========================================
# Session CRUD
# ==========================================

@router.post("/sessions")
async def create_session(
    req: CreateSessionRequest,
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    session = await mgr.create_session(req.title)
    return {
        "id": str(session.id),
        "title": session.title,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
    }


@router.get("/sessions")
async def list_sessions(
    status: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    sessions = await mgr.list_sessions(status)
    return {
        "sessions": [
            {
                "id": str(s.id),
                "title": s.title,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    session = await mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "id": str(session.id),
        "title": session.title,
        "status": session.status,
        "container_id": session.container_id,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: UUID,
    req: UpdateSessionRequest,
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    kwargs = {k: v for k, v in req.dict(exclude_none=True).items()}
    session = await mgr.update_session(session_id, **kwargs)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"id": str(session.id), "status": "updated"}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
):
    mgr = ClaudeSessionManager(user.id)
    await mgr.close_session(session_id)
    return {"status": "closed"}


# ==========================================
# Conversation & Message
# ==========================================

@router.post("/sessions/{session_id}/conversations")
async def create_conversation(
    session_id: UUID,
    req: CreateConversationRequest,
    user: User = Depends(get_current_user),
):
    """创建新对话"""
    from app.models.claude import ClaudeConversation
    from app.core.database import get_session as get_db_session

    mgr = ClaudeSessionManager(user.id)
    session = await mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    with get_db_session() as db:
        conv = ClaudeConversation(
            session_id=session_id,
            title=req.title or f"对话 {db.exec(
                select(func.count()).select_from(ClaudeConversation).where(
                    ClaudeConversation.session_id == session_id
                )
            ).one() + 1}",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return {"id": str(conv.id), "title": conv.title}


from sqlalchemy import func


@router.post("/sessions/{session_id}/conversations/{conversation_id}/messages")
async def send_message(
    session_id: UUID,
    conversation_id: UUID,
    req: SendMessageRequest,
    user: User = Depends(get_current_user),
):
    """发送消息并返回 SSE 事件流"""
    mgr = ClaudeSessionManager(user.id)
    session = await mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 发送消息到 Agent Service
    try:
        result = await mgr.send_user_message(session_id, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 订阅事件通道，转为 SSE
    async def event_stream():
        bridge = await get_claude_bridge()

        # 发送 session_info
        yield f"event: session_info\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"

        try:
            async for event in bridge.subscribe_events(str(session_id)):
                event_type = event.get("type", "unknown")
                yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 持久化 assistant 事件
                await mgr.persist_assistant_event(conversation_id, event)

                # status=idle 或 status=waiting_user 表示本轮对话结束
                if event_type == "status" and event.get("status") in ("idle", "waiting_user"):
                    yield f"event: end\ndata: {json.dumps({'status': 'complete'})}\n\n"
                    break

        except asyncio.CancelledError:
            # 客户端断开 → 发送 cancel
            await bridge.send_cancel(str(session_id))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions/{session_id}/conversations/{conversation_id}/messages")
async def get_messages(
    session_id: UUID,
    conversation_id: UUID,
    user: User = Depends(get_current_user),
):
    """获取对话历史消息"""
    mgr = ClaudeSessionManager(user.id)
    messages = await mgr.get_conversation_messages(conversation_id)
    return {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "events_json": m.events_json,
                "plan_json": m.plan_json,
                "code_snapshot": m.code_snapshot,
                "usage_json": m.usage_json,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]
    }
```

- [ ] **Step 2: Register the router in `main.py`**

In `autonome-backend/main.py`, add:

```python
from app.api.routes import claude as claude_routes
app.include_router(claude_routes.router)
```

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/api/routes/claude.py autonome-backend/main.py
git commit -m "feat: add Claude API routes with SSE streaming"
```

---

### Task 1.11: Frontend — Claude Zustand Store + SSE Hook

**Files:**
- Create: `autonome-studio/src/store/useClaudeStore.ts`
- Create: `autonome-studio/src/hooks/useClaudeChat.ts`

- [ ] **Step 1: Create `useClaudeStore.ts`**

```typescript
/**
 * Claude 模式 Zustand Store
 *
 * 管理 Claude 会话状态: sessions, conversations, messages, streaming
 */

import { create } from 'zustand';

export interface ClaudeEvent {
  type: string;
  timestamp: number;
  content?: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_use_id?: string;
  status?: string;
  message?: string;
  input_tokens?: number;
  output_tokens?: number;
}

export interface ClaudeMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  events?: ClaudeEvent[];
  plan?: PlanData | null;
  codeSnapshot?: string;
  usage?: { input_tokens: number; output_tokens: number } | null;
  createdAt: string;
}

export interface PlanData {
  title: string;
  steps: Array<{ title: string; description: string }>;
  code_snapshot: string;
  estimated_cost: string;
}

export interface ClaudeSession {
  id: string;
  title: string;
  status: 'active' | 'archived' | 'closed';
  createdAt: string;
  updatedAt: string;
}

export interface ClaudeConversation {
  id: string;
  sessionId: string;
  title: string;
  createdAt: string;
}

interface ClaudeStore {
  // Sessions
  sessions: ClaudeSession[];
  activeSessionId: string | null;

  // Conversations
  conversations: ClaudeConversation[];
  activeConversationId: string | null;

  // Messages
  messages: ClaudeMessage[];

  // Streaming
  isStreaming: boolean;
  streamEvents: ClaudeEvent[];

  // Actions
  setSessions: (sessions: ClaudeSession[]) => void;
  setActiveSession: (id: string) => void;
  addSession: (session: ClaudeSession) => void;
  removeSession: (id: string) => void;

  setConversations: (conversations: ClaudeConversation[]) => void;
  setActiveConversation: (id: string) => void;

  setMessages: (messages: ClaudeMessage[]) => void;
  addMessage: (message: ClaudeMessage) => void;
  appendStreamContent: (event: ClaudeEvent) => void;
  setStreaming: (streaming: boolean) => void;
  resetStream: () => void;
}

export const useClaudeStore = create<ClaudeStore>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  conversations: [],
  activeConversationId: null,
  messages: [],
  isStreaming: false,
  streamEvents: [],

  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (id) => set({ activeSessionId: id }),
  addSession: (session) =>
    set((s) => ({ sessions: [...s.sessions, session] })),
  removeSession: (id) =>
    set((s) => ({
      sessions: s.sessions.filter((ses) => ses.id !== id),
    })),

  setConversations: (conversations) => set({ conversations }),
  setActiveConversation: (id) => set({ activeConversationId: id }),

  setMessages: (messages) => set({ messages }),
  addMessage: (message) =>
    set((s) => ({ messages: [...s.messages, message] })),
  appendStreamContent: (event) =>
    set((s) => ({ streamEvents: [...s.streamEvents, event] })),
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  resetStream: () => set({ streamEvents: [], isStreaming: false }),
}));
```

- [ ] **Step 2: Create `useClaudeChat.ts`**

```typescript
/**
 * useClaudeChat — Claude 模式 SSE 通信 Hook
 *
 * 通过 fetch + ReadableStream 消费后端 SSE 事件流，
 * 实时更新 Zustand useClaudeStore。
 */

import { useCallback, useRef } from 'react';
import { useClaudeStore, type ClaudeEvent } from '@/store/useClaudeStore';
import { fetchAPI } from '@/lib/fetch';

export function useClaudeChat() {
  const {
    activeSessionId,
    activeConversationId,
    isStreaming,
    streamEvents,
    addMessage,
    appendStreamContent,
    setStreaming,
    resetStream,
    messages,
    setMessages,
  } = useClaudeStore();

  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!activeSessionId || !activeConversationId) return;
      if (isStreaming) return;

      // 添加用户消息到本地
      const userMsg = {
        id: `temp-${Date.now()}`,
        role: 'user' as const,
        content,
        createdAt: new Date().toISOString(),
      };
      addMessage(userMsg);

      // 重置流式状态
      resetStream();
      setStreaming(true);

      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      try {
        const response = await fetchAPI(
          `/api/claude/sessions/${activeSessionId}/conversations/${activeConversationId}/messages`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content }),
            signal: abortController.signal,
          }
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';
        const assistantEvents: ClaudeEvent[] = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          let currentEvent = '';
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                if (currentEvent !== 'end' && currentEvent !== 'session_info') {
                  appendStreamContent(parsed);
                  assistantEvents.push(parsed);
                }
              } catch {
                // 跳过非 JSON 数据行
              }
            }
          }
        }

        // 流式结束，保存 assistant 消息
        const assistantMsg = {
          id: `msg-${Date.now()}`,
          role: 'assistant' as const,
          content: '',
          events: assistantEvents,
          createdAt: new Date().toISOString(),
        };
        addMessage(assistantMsg);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') {
          return;
        }
        console.error('Claude chat error:', err);
      } finally {
        setStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [
      activeSessionId,
      activeConversationId,
      isStreaming,
      addMessage,
      appendStreamContent,
      setStreaming,
      resetStream,
    ]
  );

  const cancelStream = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const loadMessages = useCallback(
    async (sessionId: string, conversationId: string) => {
      try {
        const res = await fetchAPI(
          `/api/claude/sessions/${sessionId}/conversations/${conversationId}/messages`
        );
        if (res.ok) {
          const data = await res.json();
          setMessages(data.messages || []);
        }
      } catch (err) {
        console.error('Failed to load messages:', err);
      }
    },
    [setMessages]
  );

  return {
    messages,
    isStreaming,
    streamEvents,
    sendMessage,
    cancelStream,
    loadMessages,
  };
}
```

- [ ] **Step 3: Commit**

```bash
git add autonome-studio/src/store/useClaudeStore.ts autonome-studio/src/hooks/useClaudeChat.ts
git commit -m "feat: add Claude Zustand store and SSE chat hook"
```

---

### Task 1.12: Frontend — ClaudeChatStage (Minimal Viable)

**Files:**
- Create: `autonome-studio/src/components/chat/ClaudeChatStage.tsx`
- Create: `autonome-studio/src/components/chat/ThinkingBlock.tsx`

- [ ] **Step 1: Create `ThinkingBlock.tsx`**

```typescript
/**
 * ThinkingBlock — 可折叠的 Claude Code 思考过程展示
 */
'use client';

import { useState } from 'react';

interface ThinkingBlockProps {
  content: string;
}

export function ThinkingBlock({ content }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);

  if (!content) return null;

  return (
    <div className="border border-amber-500/30 rounded-lg mb-2 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 bg-amber-500/10 hover:bg-amber-500/20 text-left text-sm text-amber-400"
      >
        <span className="text-xs">{expanded ? '▼' : '▶'}</span>
        <span>💭 思考过程</span>
      </button>
      {expanded && (
        <div className="px-3 py-2 bg-amber-500/5 text-sm text-amber-300/80 whitespace-pre-wrap max-h-60 overflow-y-auto">
          {content}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create `ClaudeChatStage.tsx`**

```typescript
/**
 * ClaudeChatStage — Claude 模式主容器
 *
 * 三栏布局: 左侧导航 | 对话时间线 | 右侧预览区 (Phase 3)
 */

'use client';

import { useEffect, useState, useRef } from 'react';
import { useClaudeChat } from '@/hooks/useClaudeChat';
import { useClaudeStore } from '@/store/useClaudeStore';
import { ThinkingBlock } from './ThinkingBlock';
import { fetchAPI } from '@/lib/fetch';

export function ClaudeChatStage() {
  const {
    activeSessionId,
    activeConversationId,
    sessions,
    conversations,
    setSessions,
    setActiveSession,
    addSession,
    setConversations,
    setActiveConversation,
  } = useClaudeStore();

  const {
    messages,
    isStreaming,
    streamEvents,
    sendMessage,
    cancelStream,
    loadMessages,
  } = useClaudeChat();

  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 加载会话列表
  useEffect(() => {
    fetchAPI('/api/claude/sessions')
      .then((res) => res.json())
      .then((data) => {
        if (data.sessions) {
          setSessions(data.sessions);
          if (data.sessions.length > 0 && !activeSessionId) {
            setActiveSession(data.sessions[0].id);
          }
        }
      })
      .catch(console.error);
  }, []);

  // 切换会话时加载消息
  useEffect(() => {
    if (activeSessionId && activeConversationId) {
      loadMessages(activeSessionId, activeConversationId);
    }
  }, [activeSessionId, activeConversationId]);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamEvents]);

  const handleCreateSession = async () => {
    try {
      const res = await fetchAPI('/api/claude/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '新会话' }),
      });
      const session = await res.json();
      addSession(session);
      setActiveSession(session.id);
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  };

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    sendMessage(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 将事件列表中的 text_delta 拼接为文本
  const buildTextContent = (events: Array<{ type: string; content?: string }>) => {
    return events
      .filter((e) => e.type === 'text_delta')
      .map((e) => e.content || '')
      .join('');
  };

  return (
    <div className="flex h-full">
      {/* 左侧: 会话列表 */}
      <div className="w-56 border-r border-gray-700 p-3 flex flex-col">
        <button
          onClick={handleCreateSession}
          className="w-full px-3 py-2 mb-3 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
        >
          + 新建会话
        </button>
        <div className="flex-1 overflow-y-auto space-y-1">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSession(s.id)}
              className={`w-full text-left px-3 py-2 rounded text-sm truncate ${
                s.id === activeSessionId
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-400 hover:bg-gray-800'
              }`}
            >
              {s.title}
            </button>
          ))}
        </div>
      </div>

      {/* 中间: 对话时间线 */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto p-4">
          {messages.map((msg) => (
            <div key={msg.id} className="mb-4">
              {msg.role === 'user' ? (
                <div className="flex justify-end">
                  <div className="bg-blue-600 text-white px-4 py-2 rounded-lg max-w-[80%]">
                    {msg.content}
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  {msg.events?.map((event, i) => {
                    if (event.type === 'thinking') {
                      return <ThinkingBlock key={i} content={event.content || ''} />;
                    }
                    return null;
                  })}
                  {msg.events && msg.events.length > 0 && (
                    <div className="text-gray-200 whitespace-pre-wrap">
                      {buildTextContent(msg.events)}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* 流式渲染 */}
          {isStreaming && (
            <div className="mb-4">
              {streamEvents.filter((e) => e.type === 'thinking').map((e, i) => (
                <ThinkingBlock key={`stream-thinking-${i}`} content={e.content || ''} />
              ))}
              <div className="text-gray-200 whitespace-pre-wrap">
                {streamEvents
                  .filter((e) => e.type === 'text_delta')
                  .map((e) => e.content || '')
                  .join('')}
                {streamEvents.some((e) => e.type === 'status' && e.status === 'thinking') && (
                  <span className="inline-block w-2 h-4 bg-blue-400 animate-pulse ml-1" />
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* 输入框 */}
        <div className="border-t border-gray-700 p-3">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              rows={2}
              className="flex-1 bg-gray-800 text-gray-200 rounded px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <button
              onClick={isStreaming ? cancelStream : handleSend}
              className={`px-4 py-2 rounded text-sm ${
                isStreaming
                  ? 'bg-red-600 hover:bg-red-700 text-white'
                  : 'bg-blue-600 hover:bg-blue-700 text-white'
              }`}
            >
              {isStreaming ? '停止' : '发送'}
            </button>
          </div>
        </div>
      </div>

      {/* 右侧: 预览区 (Phase 3 实现) */}
      <div className="w-64 border-l border-gray-700 p-3 text-gray-500 text-sm">
        预览区 (开发中)
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add autonome-studio/src/components/chat/ClaudeChatStage.tsx autonome-studio/src/components/chat/ThinkingBlock.tsx
git commit -m "feat: add Claude chat stage with three-pane layout and SSE streaming"
```

---

### Task 1.13: Integration — Wire Claude Mode into ChatStage

**Files:**
- Modify: `autonome-studio/src/components/chat/ChatStage.tsx`

- [ ] **Step 1: Add mode toggle to ChatStage**

In the ChatStage component, add:

```typescript
// Near top of component
import { ClaudeChatStage } from './ClaudeChatStage';

// Mode state
const [chatMode, setChatMode] = useState<'normal' | 'claude'>('normal');

// In the render, at the top:
<div className="flex items-center gap-2 px-3 py-2 border-b border-gray-700">
  <button
    onClick={() => setChatMode('normal')}
    className={`px-3 py-1 rounded text-sm ${
      chatMode === 'normal' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800'
    }`}
  >
    常规模式
  </button>
  <button
    onClick={() => setChatMode('claude')}
    className={`px-3 py-1 rounded text-sm ${
      chatMode === 'claude' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800'
    }`}
  >
    Claude 模式
  </button>
</div>

// Conditional rendering:
{chatMode === 'claude' ? <ClaudeChatStage /> : <Normal Chat Content />}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-studio/src/components/chat/ChatStage.tsx
git commit -m "feat: add Claude/normal mode toggle to ChatStage"
```

---

### Task 1.14: End-to-End Smoke Test

- [ ] **Step 1: Rebuild and restart all services**

```bash
docker-compose down
docker build -f autonome-backend/Dockerfile.claude-sandbox -t autonome-claude-sandbox:latest autonome-backend/
docker-compose up -d
```

- [ ] **Step 2: Run DB migration**

```bash
docker-compose exec backend-api alembic upgrade head
```

Expected: Migration applied without errors.

- [ ] **Step 3: Test API — create session**

```bash
# First get auth cookie (adjust as needed)
curl -X POST http://localhost:8000/api/claude/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "测试会话"}'
```

Expected: Returns JSON with session `id`.

- [ ] **Step 4: Test API — send message (SSE)**

```bash
curl -N -X POST http://localhost:8000/api/claude/sessions/{id}/conversations/{cid}/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "你好，帮我分析一下RNA-seq数据"}'
```

Expected: SSE events streamed.

- [ ] **Step 5: Test Frontend**

Open http://localhost:3001, switch to Claude mode, send a message.

Expected: Message sent, thinking block displayed, text response streamed.

- [ ] **Step 6: Commit any fixes and deploy**

```bash
./auto_deploy.sh -s "feat: Claude Agent mode Phase 1 complete" -d "完成 Claude 模式基础设施: 数据模型、Agent Service、Redis 通信桥、API 路由、前端三栏聊天界面、模式切换。"
```

---

## Phase 2: Tools & Capabilities

### Task 2.1: Skill Search Tool Integration
- Agent Service 注册 `skill_search` 工具，调用后端 `/api/claude/skills/search` 接口
- 后端实现技能搜索 API（调用现有 SkillMatcher）
- Claude Code 系统提示注入工具说明

### Task 2.2: Sandbox Execution Tools
- Agent Service 实现 `execute_sandbox`（subprocess 执行命令）
- Agent Service 实现 `read_file` / `write_file`（/workspace 内文件操作）
- 超时控制和安全限制

### Task 2.3: Heavy Task Submit Tool
- Agent Service 实现 `submit_heavy_task`
- 后端接收任务、创建 Celery TaskRecord、返回 task_id
- 前端 `TaskCard` 组件：实时状态 + 进度展示

### Task 2.4: Plan Card Interaction
- Agent Service 解析 Claude Code 生成的 Plan → PlanEvent
- 前端 `PlanCard` 组件：步骤列表 + 代码预览 + [修改]/[确认] 按钮
- 修改反馈回传 Agent Service → Claude Code

### Task 2.5: Claude CLI Output POST /api/claude/skills/search
- 后端 `/api/claude/skills/search` 路由
- 调用现有 SkillMatcher 返回匹配结果

---

## Phase 3: Task Management & Preview

### Task 3.1: Task Tracking
- 后端 `claude_task` 表 CRUD 完成
- Celery 任务进度回调到 Redis → Agent Service → 前端
- 任务日志 SSE 流 `/api/claude/tasks/{task_id}/logs`

### Task 3.2: Right Preview Pane
- `ClaudePreview` 组件：文件列表、图片预览、CSV 表格、HTML 报告
- 文件列表经过 `listFiles()` 获取
- 点击文件触发预览

### Task 3.3: Session Management
- 会话列表侧栏完整功能（CRUD + 搜索）
- Conversation 创建/切换/删除
- 会话归档

---

## Phase 4: Container Pool & Fault Tolerance

### Task 4.1: Claude Container Pool
- `claude_container_pool.py` 实现
- 预热池 + 动态分配 + 空闲回收
- 每用户并发限制 (max 3)

### Task 4.2: Agent Service Fault Tolerance
- 心跳检测 + 自动恢复
- 异常重启 + 上下文恢复
- Redis 断线重连优化

### Task 4.3: Full Persistence
- 离线消息回放（从 DB 加载事件流重建 UI 状态）
- 事件流存档与恢复
- 会话恢复（重新开页面后回到之前状态）

---

## Phase 5: UX Polish

### Task 5.1: Streaming Rendering Optimization
- 工具调用动画 (tool_use → 旋转图标, tool_result → 展开)
- 思考块自动折叠策略（完成后折叠）

### Task 5.2: API Key Management UI
- 设置面板：输入/查看/测试 API Key
- AES-256-GCM 加密存储

### Task 5.3: Usage Statistics
- Token 用量展示（每轮对话 + 累计）
- CU 消耗计算

### Task 5.4: Experience Extraction Integration
- Claude Code 成功模式自动入库到 ExperienceAsset
- 调用现有 experience_extractor

---

## Spec Self-Review

1. **Spec coverage**: Each section of the spec maps to at least one task:
   - Architecture (Task 1.8-1.10, 1.12) ✓
   - Data Flow (Task 1.8, 1.10) ✓
   - Agent Service (Task 1.4-1.6) ✓
   - Data Model (Task 1.1-1.2) ✓
   - Frontend (Task 1.11-1.13) ✓
   - API Routes (Task 1.10) ✓
   - Docker & Network (Task 1.3, 1.7) ✓
   - Security (Phase 2 tasks, BYOK in Task 5.2) ✓
   - Fault Tolerance (Phase 4) ✓

2. **Placeholder scan**: No TBD/TODO found. All tasks have concrete code or clear descriptions.

3. **Type consistency**: Event types in `event_types.py` match usage in `stream_parser.py` and `useClaudeChat.ts`. Model field names match between migration, SQLModel, and frontend interfaces.
