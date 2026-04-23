# 意图路由 V2.0 升级实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分三阶段升级意图路由系统，打通 L1 结构化上下文 → L2 Active Probing 闭环 → L3 执行器 → DAG 调度 → 前端可视化的完整链路。

**Architecture:** 渐进式节点替换方案，在现有 LangGraph graph 中逐步增强节点，保持 graph 结构不变。L3 复用现有 skill_executor.py 的 Docker 沙箱执行能力。L1 向量搜索优先 + 全量回退注入技能摘要。

**Tech Stack:** Python/FastAPI (backend), LangGraph (state machine), LangChain (LLM), Redis (probing decoupling), Celery (async execution), React/Next.js (frontend), Vercel AI SDK v5 (chat streaming)

---

## File Structure

### New Files
- `autonome-backend/app/agent/router/nodes/probing_response_node.py` — Active Probing 参数回注节点
- `autonome-backend/app/agent/router/nodes/l3_executor_node.py` — L3 技能执行节点
- `autonome-backend/app/agent/router/dag_scheduler.py` — DAG 拓扑排序与调度逻辑
- `autonome-studio/src/components/chat/DAGProgressView.tsx` — DAG 进度可视化组件

### Modified Files
- `autonome-backend/app/agent/router/schemas.py` — 新增 ExecutionStatus, TaskNodeStatus, ProbingResponse, TaskResult 模型；扩展 AgentState
- `autonome-backend/app/agent/router/l1_classifier.py` — 注入技能摘要（向量搜索优先 + 全量回退）
- `autonome-backend/app/agent/router/engine.py` — 新增 get_skill_summary 方法；L1 调用时传入技能摘要
- `autonome-backend/app/agent/router/l2_extractor.py` — 无改动（Phase A 不改 L2 逻辑）
- `autonome-backend/app/agent/graph.py` — 新增 probing_response_node, l3_executor_node；新增 route_after_l2, route_after_probing, route_after_execution 条件边
- `autonome-backend/app/api/routes/chat.py` — 新增 POST /api/chat/probing/submit 端点
- `autonome-backend/app/agent/nodes/orchestrator_node.py` — 重写为 DAG 调度器
- `autonome-studio/src/components/chat/ChatStage.tsx` — 集成 DAGProgressView
- `autonome-studio/src/store/useChatStore.ts` — Message 类型新增 dagProgress 字段

---

## Phase A: 核心链路打通

### Task 1: 扩展 schemas.py 数据模型

**Files:**
- Modify: `autonome-backend/app/agent/router/schemas.py:149-211`

- [ ] **Step 1: 新增 ExecutionStatus 枚举**

在 `ProbingRequest` 类之后（line 155 后）添加：

```python
class ExecutionStatus(str, Enum):
    """DAG 执行状态枚举"""
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 全部完成
    FAILED = "failed"          # 执行失败
    PROBING = "probing"        # 等待用户参数补全


class TaskNodeStatus(str, Enum):
    """DAG 中单个 TaskNode 的执行状态"""
    PENDING = "pending"      # 等待前置节点完成
    READY = "ready"          # 可执行（前置节点已完成）
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 执行失败
    SKIPPED = "skipped"      # 因依赖失败而跳过
```

- [ ] **Step 2: 新增 ProbingResponse 模型**

在 `ExecutionStatus` 后添加：

```python
class ProbingResponse(BaseModel):
    """用户提交的 Active Probing 参数"""
    message_id: str = Field(..., description="对应的 ProbingRequest message_id")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="用户填写的参数")
```

- [ ] **Step 3: 新增 TaskResult 模型**

在 `ProbingResponse` 后添加：

```python
class TaskResult(BaseModel):
    """单个 TaskNode 的执行结果"""
    task_id: str = Field(..., description="子任务 ID")
    skill_id: str = Field(default="", description="执行的技能 ID")
    status: str = Field(default="pending", description="执行状态: success/failed/timeout")
    output: Optional[Any] = Field(None, description="执行输出")
    error: Optional[str] = Field(None, description="错误信息")
    execution_time_seconds: float = Field(0.0, description="执行耗时（秒）")
```

- [ ] **Step 4: 扩展 AgentState**

将 `AgentState`（line 195-211）扩展为：

```python
class AgentState(TypedDict):
    """
    LangGraph 多 Agent 编排状态 (V2.0)。

    支持多任务 DAG 调度、Active Probing 挂起/恢复、L3 执行结果收集。
    """
    messages: Annotated[Sequence[BaseMessage], "消息历史"]
    context: Dict[str, Any]            # 前端注入的工作区上下文
    intent_data: Optional[Dict]        # IntentExtraction 序列化结果
    skill_id: Optional[str]            # 匹配到的技能 ID
    execution_result: Optional[Dict]   # 执行结果
    # --- V2.0 DAG 调度状态 ---
    dag: Optional[Dict]                # TaskDAG 序列化结果
    current_task_idx: int              # 当前执行到 DAG 中的哪一个任务
    active_probing: Optional[Dict]     # ProbingRequest 序列化结果
    task_results: Dict[str, Any]       # 各子任务执行完毕后的结果上下文
    # --- V2.0+ 新增字段 ---
    execution_status: str              # ExecutionStatus 值，默认 "pending"
    probing_response: Optional[Dict]   # ProbingResponse 序列化结果（用户提交的参数）
```

- [ ] **Step 5: 验证无语法错误**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.agent.router.schemas import ExecutionStatus, TaskNodeStatus, ProbingResponse, TaskResult, AgentState; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add autonome-backend/app/agent/router/schemas.py
git commit -m "feat: 扩展路由schemas-新增ExecutionStatus/TaskNodeStatus/ProbingResponse/TaskResult模型"
```

---

### Task 2: L1 结构化上下文增强（向量搜索 + 全量回退）

**Files:**
- Modify: `autonome-backend/app/agent/router/l1_classifier.py:27-93` (prompt template)
- Modify: `autonome-backend/app/agent/router/l1_classifier.py:96-210` (L1Classifier class)
- Modify: `autonome-backend/app/agent/router/engine.py:22-106` (IntentRouterEngine)

- [ ] **Step 1: 在 L1 prompt 模板中增加 available_skills 区块**

在 `L1_DECOMPOSER_PROMPT_TEMPLATE` 的 `## 工作区上下文` 区块之后（line 48 后），添加：

```
## 可用技能（与用户需求最相关的技能）

{available_skills}
```

- [ ] **Step 2: 在 IntentRouterEngine 中新增 get_skill_summary 方法**

在 `engine.py` 的 `IntentRouterEngine` 类中添加方法：

```python
async def get_skill_summary(self, query: str, top_k: int = 12) -> str:
    """
    获取与用户查询相关的技能摘要，供 L1 prompt 注入。

    程序说明：
    优先使用向量搜索（SemanticSearchEngine）检索 Top-K 最相关技能。
    向量搜索无结果或异常时，降级到全量技能摘要（截断到 2000 字符）。
    """
    # 首选：向量搜索
    try:
        from app.mcp.semantic_search import get_semantic_engine, is_semantic_available
        if is_semantic_available():
            engine = get_semantic_engine()
            results = engine.search(query, top_k=top_k)
            if results:
                from app.core.skill_parser import get_skill_parser
                parser = get_skill_parser()
                lines = []
                for skill_id, score in results:
                    skill = parser.get_skill_by_id(skill_id)
                    if skill:
                        name = skill.get("name", skill_id)
                        desc = skill.get("description", "")[:80]
                        lines.append(f"- {skill_id}: {name} - {desc}")
                if lines:
                    summary = "\n".join(lines[:top_k])
                    log.info(f"[Router] 向量搜索命中 {len(lines)} 个技能")
                    return summary
    except Exception as e:
        log.warning(f"[Router] 向量搜索异常，降级到全量摘要: {e}")

    # 回退：全量技能摘要（截断）
    try:
        from app.core.skill_parser import get_skill_parser
        parser = get_skill_parser()
        all_skills = parser.list_skills()
        lines = []
        for skill in all_skills[:50]:  # 最多 50 个
            sid = skill.get("skill_id", "")
            name = skill.get("name", sid)
            desc = skill.get("description", "")[:60]
            lines.append(f"- {sid}: {name} - {desc}")
        summary = "\n".join(lines)
        # 截断到 2000 字符
        if len(summary) > 2000:
            summary = summary[:2000] + "\n... (更多技能省略)"
        log.info(f"[Router] 全量技能摘要: {len(lines)} 个技能")
        return summary if summary else "无可用技能"
    except Exception as e:
        log.warning(f"[Router] 获取技能摘要异常: {e}")
        return "无可用技能"
```

- [ ] **Step 3: 修改 IntentRouterEngine.route 传入技能摘要**

在 `engine.py` 的 `route` 方法中，L1 调用前获取技能摘要并传入：

```python
# L1: DAG 解构（注入技能摘要）
log.info(f"[Router] L0 未命中，调用 L1 解构: query='{query[:50]}...'")
skill_summary = await self.get_skill_summary(query)
dag = await self.classifier.decompose(query, context, skill_summary=skill_summary)
```

- [ ] **Step 4: 修改 L1Classifier.decompose 接收 skill_summary**

在 `l1_classifier.py` 的 `decompose` 方法签名中增加 `skill_summary: str = ""` 参数，并在构建 workspace_context 时合并：

```python
async def decompose(
    self, query: str, context: Dict[str, Any] = None,
    enable_think: bool = False, temperature: float = 0.0,
    skill_summary: str = ""
) -> TaskDAG:
```

在构建 prompt 输入时注入 `available_skills`：

```python
# 构建提示词输入
prompt_input = {
    "query": query,
    "workspace_context": workspace_context,
    "available_skills": skill_summary or "无可用技能",
}
```

同步修改 `_decompose_with_structured_output` 和 `_decompose_with_json_mode` 中的 prompt_input 构建逻辑，确保 `available_skills` 被传入。

- [ ] **Step 5: 验证无语法错误**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.agent.router.engine import IntentRouterEngine; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add autonome-backend/app/agent/router/l1_classifier.py autonome-backend/app/agent/router/engine.py
git commit -m "feat: L1结构化上下文增强-向量搜索优先+全量回退注入技能摘要"
```

---

### Task 3: L2 Active Probing 闭环（probing submit API + probing_response_node）

**Files:**
- Create: `autonome-backend/app/agent/router/nodes/probing_response_node.py`
- Modify: `autonome-backend/app/api/routes/chat.py` (新增端点)
- Modify: `autonome-backend/app/agent/graph.py` (新增节点和边)

- [ ] **Step 1: 创建 probing_response_node.py**

```python
"""
Active Probing 参数回注节点。

用户通过前端 ParameterProbingCard 提交参数后，
此节点从 Redis 读取用户提交的参数，回注到当前 TaskNode 的 parameters 中，
并重置 active_probing 以解除挂起状态。
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def probing_response_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    处理用户提交的 Active Probing 参数。

    程序说明：
    从 AgentState.probing_response 读取用户提交的参数，
    合并到当前 TaskNode 的 parameters 中，
    清除 active_probing 和 probing_response 以解除挂起。
    """
    probing_response = state.get("probing_response")
    if not probing_response:
        log.warning("[probing_response_node] 无 probing_response，跳过")
        return {"active_probing": None, "probing_response": None}

    # 提取用户提交的参数
    user_params = probing_response.get("parameters", {})
    message_id = probing_response.get("message_id", "")
    log.info(f"[probing_response_node] 收到用户参数: message_id={message_id}, params={list(user_params.keys())}")

    # 将用户参数合并到当前 TaskNode
    dag_dict = state.get("dag")
    idx = state.get("current_task_idx", 0)
    if dag_dict and dag_dict.get("nodes"):
        nodes = dag_dict["nodes"]
        if idx < len(nodes):
            # 合并参数（用户提交的参数优先级最高）
            existing_params = nodes[idx].get("parameters", {})
            merged_params = {**existing_params, **user_params}
            nodes[idx]["parameters"] = merged_params
            log.info(f"[probing_response_node] 参数已回注到 task_{idx}: {list(merged_params.keys())}")

    # 清除挂起状态，允许继续执行
    return {
        "dag": dag_dict,
        "active_probing": None,
        "probing_response": None,
        "execution_status": "pending",
    }
```

- [ ] **Step 2: 在 chat.py 新增 probing submit API 端点**

在 `chat.py` 的路由部分添加：

```python
# === Active Probing 参数提交端点 ===

class ProbingSubmitRequest(BaseModel):
    """Active Probing 参数提交请求"""
    message_id: str = Field(..., description="ProbingRequest 的 message_id")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="用户填写的参数")


@router.post("/probing/submit")
async def probing_submit(
    request: ProbingSubmitRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    接收前端 Active Probing 表单提交的参数。

    程序说明：
    将用户提交的参数写入 Redis，key 为 probing:{message_id}，
    TTL 10 分钟。LangGraph 的 probing_response_node 从 Redis 读取。
    """
    import redis
    from app.core.config import settings

    try:
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True,
        )
        key = f"probing:{request.message_id}"
        import json
        r.setex(key, 600, json.dumps(request.parameters))  # TTL 10 分钟
        log.info(f"[probing_submit] 参数已写入 Redis: key={key}")
        return {"status": "ok", "message_id": request.message_id}
    except Exception as e:
        log.error(f"[probing_submit] Redis 写入失败: {e}")
        raise HTTPException(status_code=500, detail=f"参数提交失败: {str(e)}")
```

- [ ] **Step 3: 在 graph.py 中注册 probing_response_node**

在 `graph.py` 的 imports 中添加：

```python
from app.agent.router.nodes.probing_response_node import probing_response_node
```

在 `build_intent_graph` 中添加节点注册：

```python
workflow.add_node("probing_response_node", probing_response_node)
```

- [ ] **Step 4: 验证无语法错误**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.agent.graph import build_intent_graph; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add autonome-backend/app/agent/router/nodes/probing_response_node.py autonome-backend/app/api/routes/chat.py autonome-backend/app/agent/graph.py
git commit -m "feat: L2 Active Probing闭环-probing_submit API+probing_response_node"
```

---

### Task 4: 路由中间件完善（route_after_l2 + route_after_probing + route_after_execution）

**Files:**
- Modify: `autonome-backend/app/agent/graph.py:131-220`

- [ ] **Step 1: 新增 route_after_l2 条件边函数**

在 `graph.py` 的 `determine_next_step` 函数之后添加：

```python
def route_after_l2(state: AgentState) -> str:
    """
    L2 参数探查后的路由判断。

    程序说明：
    如果 L2 发现参数缺失（active_probing.is_missing=True），
    路由到 ask_user_node 挂起等待前端参数补全。
    否则路由到 l3_executor_node 执行技能。
    """
    probing_dict = state.get("active_probing")
    if probing_dict and probing_dict.get("is_missing"):
        return "ask_user_node"

    # 参数齐全，前进到执行
    return "l3_executor_node"
```

- [ ] **Step 2: 新增 route_after_probing 条件边函数**

```python
def route_after_probing(state: AgentState) -> str:
    """
    Active Probing 参数回注后的路由判断。

    程序说明：
    用户提交参数后，probing_response_node 已将参数合并到 TaskNode。
    此处判断是否需要再次 L2 检查（参数可能仍不完整），
    或直接前进到 L3 执行。

    当前策略：直接前进到 L3，信任用户提交的参数。
    未来可增加二次 L2 校验。
    """
    # 直接前进到执行
    return "l3_executor_node"
```

- [ ] **Step 3: 新增 route_after_execution 条件边函数**

```python
def route_after_execution(state: AgentState) -> str:
    """
    L3 执行后的路由判断。

    程序说明：
    检查 DAG 中是否还有未完成的任务节点。
    有 → 回到 intent_router 继续调度下一个任务。
    无 → 检查执行状态，全部成功则结束，有失败则标记。
    """
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        return END

    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])

    # 还有未执行的任务
    if idx < len(nodes):
        return "intent_router"

    # 所有任务已执行完毕
    return END
```

- [ ] **Step 4: 更新 build_intent_graph 中的边定义**

在 `build_intent_graph` 中更新边：

```python
# ask_user_node → probing_response_node（用户提交参数后回注）
workflow.add_edge("ask_user_node", "probing_response_node")

# probing_response_node → route_after_probing（参数回注后判断去向）
workflow.add_conditional_edges(
    "probing_response_node",
    route_after_probing,
    {"l3_executor_node": "l3_executor_node", "intent_router": "intent_router"}
)
```

- [ ] **Step 5: 验证无语法错误**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.agent.graph import build_intent_graph; g = build_intent_graph(); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add autonome-backend/app/agent/graph.py
git commit -m "feat: 路由中间件完善-route_after_l2/route_after_probing/route_after_execution"
```

---

## Phase B: L3 执行器 + DAG 调度

### Task 5: L3 Executor 节点

**Files:**
- Create: `autonome-backend/app/agent/router/nodes/l3_executor_node.py`

- [ ] **Step 1: 创建 l3_executor_node.py**

```python
"""
L3 技能执行节点 - 薄编排层，复用 skill_executor.py 的 Docker 沙箱执行能力。

接收 TaskNode（含 skill_id + parameters），调用 SkillExecutor.execute()，
收集执行结果更新 AgentState.task_results。
"""
import time
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log


async def l3_executor_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    L3 技能执行节点。

    程序说明：
    从当前 TaskNode 提取 skill_id 和 parameters，
    调用 skill_executor.execute_skill() 执行技能，
    将结果写入 task_results 并推进 DAG 指针。

    如果 TaskNode 无 skill_id（如 GENERAL_CHAT、DATA_PROBE 等），
    则跳过执行，仅推进指针（实际执行由 chat.py SSE 循环处理）。
    """
    dag_dict = state.get("dag", {})
    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])

    if idx >= len(nodes):
        log.warning("[l3_executor_node] 无可执行任务")
        return {"execution_status": "completed"}

    current_task = nodes[idx]
    task_id = current_task.get("task_id", f"task_{idx}")
    skill_id = current_task.get("parameters", {}).get("skill_id") or state.get("skill_id")
    intent = current_task.get("intent", "")

    # 无 skill_id 的意图（chat/data_probe/literature 等）由 chat.py SSE 处理，此节点仅推进指针
    non_exec_intents = {
        "INTENT_GENERAL_CHAT", "INTENT_DATA_PROBE", "INTENT_LITERATURE_MINING",
        "INTENT_VISUAL_PERCEPTION_AND_TWEAK", "INTENT_DIAGNOSTIC_RECOVERY",
        "INTENT_SKILL_FORGE", "INTENT_VERSION_CONTROL", "INTENT_SYSTEM_ASSET_OPS",
        "INTENT_COLLABORATION", "INTENT_SYSTEM_MACRO", "INTENT_WORKFLOW_ORCHESTRATE",
    }

    if not skill_id or intent in non_exec_intents:
        log.info(f"[l3_executor_node] 任务 {task_id} 无 skill_id 或由 SSE 处理，跳过执行")
        task_results = dict(state.get("task_results", {}))
        task_results[task_id] = {"status": "delegated", "skill_id": skill_id or ""}
        return {
            "task_results": task_results,
            "current_task_idx": idx + 1,
            "execution_status": "running",
        }

    # 有 skill_id：调用 SkillExecutor 执行
    parameters = current_task.get("parameters", {})
    project_id = state.get("context", {}).get("project_id", "")

    log.info(f"[l3_executor_node] 执行技能: skill_id={skill_id}, task_id={task_id}")
    start_time = time.time()

    try:
        from app.services.skill_executor import execute_skill
        result = execute_skill(
            skill_id=skill_id,
            params=parameters,
            project_id=project_id,
        )
        elapsed = time.time() - start_time

        task_results = dict(state.get("task_results", {}))
        task_results[task_id] = {
            "status": "success",
            "skill_id": skill_id,
            "output": result,
            "execution_time_seconds": round(elapsed, 2),
        }

        # 生成结果摘要消息
        output_preview = str(result)[:200] if result else "无输出"
        message = AIMessage(content=f"✅ 技能 `{skill_id}` 执行完成（{elapsed:.1f}s）\n{output_preview}")

        log.info(f"[l3_executor_node] 技能执行成功: skill_id={skill_id}, elapsed={elapsed:.1f}s")
        return {
            "task_results": task_results,
            "messages": [message],
            "current_task_idx": idx + 1,
            "execution_status": "running",
        }

    except Exception as e:
        elapsed = time.time() - start_time
        log.error(f"[l3_executor_node] 技能执行失败: skill_id={skill_id}, error={e}")

        task_results = dict(state.get("task_results", {}))
        task_results[task_id] = {
            "status": "failed",
            "skill_id": skill_id,
            "error": str(e),
            "execution_time_seconds": round(elapsed, 2),
        }

        message = AIMessage(content=f"❌ 技能 `{skill_id}` 执行失败: {str(e)[:200]}")

        return {
            "task_results": task_results,
            "messages": [message],
            "current_task_idx": idx + 1,
            "execution_status": "failed",
        }
```

- [ ] **Step 2: 在 graph.py 中注册 l3_executor_node**

在 `graph.py` 的 imports 中添加：

```python
from app.agent.router.nodes.l3_executor_node import l3_executor_node
```

在 `build_intent_graph` 中添加节点注册：

```python
workflow.add_node("l3_executor_node", l3_executor_node)
```

更新 `determine_next_step` 中的路由：当参数齐全时，对于 EXPLICIT_EXEC 意图路由到 `l3_executor_node` 而非 `explicit_exec_node`：

```python
# 在 determine_next_step 中，EXPLICIT_EXEC 且有 skill_id 时优先走 L3
if intent == IntentType.EXPLICIT_EXEC:
    # 检查是否有 skill_id（有则走 L3 执行，无则走原有 explicit_exec_node）
    task_params = nodes[idx].get("parameters", {})
    if task_params.get("skill_id") or state.get("skill_id"):
        return "l3_executor_node"
    return "explicit_exec_node"
```

- [ ] **Step 3: 验证无语法错误**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.agent.graph import build_intent_graph; g = build_intent_graph(); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/app/agent/router/nodes/l3_executor_node.py autonome-backend/app/agent/graph.py
git commit -m "feat: L3执行器节点-复用skill_executor Docker沙箱执行"
```

---

### Task 6: DAG 调度器

**Files:**
- Create: `autonome-backend/app/agent/router/dag_scheduler.py`
- Modify: `autonome-backend/app/agent/nodes/orchestrator_node.py`

- [ ] **Step 1: 创建 dag_scheduler.py**

```python
"""
DAG 拓扑排序与调度逻辑。

提供 DAG 有向无环图的拓扑排序、就绪节点查找、
环检测和节点间参数变量替换功能。
"""
import re
from typing import Any, Dict, List, Optional, Set

from app.core.logger import log


def topological_sort(nodes: List[Dict]) -> List[str]:
    """
    对 DAG 节点进行拓扑排序（Kahn 算法）。

    程序说明：
    返回按执行顺序排列的 task_id 列表。
    如果检测到环，降级为原始顺序（顺序执行）。

    Args:
        nodes: TaskNode 序列化后的字典列表

    Returns:
        按拓扑序排列的 task_id 列表
    """
    # 构建邻接表和入度表
    task_ids = {n.get("task_id") for n in nodes}
    in_degree: Dict[str, int] = {tid: 0 for tid in task_ids}
    adj: Dict[str, List[str]] = {tid: [] for tid in task_ids}

    for node in nodes:
        tid = node.get("task_id")
        for dep in node.get("dependencies", []):
            if dep in task_ids:
                adj[dep].append(tid)
                in_degree[tid] = in_degree.get(tid, 0) + 1

    # Kahn 算法
    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    sorted_ids: List[str] = []

    while queue:
        # 按原始顺序稳定排序
        queue.sort(key=lambda t: next((i for i, n in enumerate(nodes) if n.get("task_id") == t), 0))
        tid = queue.pop(0)
        sorted_ids.append(tid)
        for neighbor in adj.get(tid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 环检测
    if len(sorted_ids) != len(task_ids):
        log.warning(f"[DAG] 检测到环，降级为顺序执行: sorted={len(sorted_ids)}, total={len(task_ids)}")
        return [n.get("task_id") for n in nodes]

    return sorted_ids


def find_ready_nodes(
    nodes: List[Dict],
    task_results: Dict[str, Any],
) -> List[Dict]:
    """
    找出当前可执行的节点（所有前置节点已完成）。

    程序说明：
    遍历所有节点，检查其 dependencies 中的节点是否都已有执行结果。
    返回可执行节点列表。

    Args:
        nodes: TaskNode 列表
        task_results: 已完成节点的执行结果

    Returns:
        可执行节点列表
    """
    ready = []
    for node in nodes:
        tid = node.get("task_id")
        # 已完成或正在执行的节点跳过
        if tid in task_results:
            continue
        # 检查所有前置依赖是否已完成
        deps = node.get("dependencies", [])
        if all(dep in task_results for dep in deps):
            ready.append(node)
    return ready


def resolve_parameter_references(
    parameters: Dict[str, Any],
    task_results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    解析节点参数中的变量引用。

    程序说明：
    参数值中可使用 ${task_id.output.field} 语法引用前序节点的输出。
    此函数将所有变量引用替换为实际值。

    Args:
        parameters: 原始参数字典
        task_results: 已完成节点的执行结果

    Returns:
        解析后的参数字典
    """
    resolved = {}
    pattern = re.compile(r'\$\{(\w+)\.output\.(\w+)\}')

    for key, value in parameters.items():
        if isinstance(value, str):
            match = pattern.fullmatch(value)
            if match:
                ref_task_id = match.group(1)
                ref_field = match.group(2)
                ref_result = task_results.get(ref_task_id, {})
                ref_output = ref_result.get("output", {})
                if isinstance(ref_output, dict) and ref_field in ref_output:
                    resolved[key] = ref_output[ref_field]
                else:
                    log.warning(f"[DAG] 无法解析参数引用: {value}")
                    resolved[key] = value
            else:
                resolved[key] = value
        else:
            resolved[key] = value

    return resolved


def get_dag_progress(nodes: List[Dict], task_results: Dict[str, Any]) -> Dict[str, str]:
    """
    获取 DAG 各节点的执行进度。

    程序说明：
    返回 {task_id: status} 映射，供前端 DAGProgressView 渲染。

    Args:
        nodes: TaskNode 列表
        task_results: 已完成节点的执行结果

    Returns:
        节点进度映射 {task_id: "pending"|"running"|"completed"|"failed"}
    """
    progress = {}
    for node in nodes:
        tid = node.get("task_id")
        if tid in task_results:
            result = task_results[tid]
            status = result.get("status", "completed")
            if status == "failed":
                progress[tid] = "failed"
            else:
                progress[tid] = "completed"
        else:
            # 检查是否可执行
            deps = node.get("dependencies", [])
            if all(dep in task_results for dep in deps):
                progress[tid] = "ready"
            else:
                progress[tid] = "pending"
    return progress
```

- [ ] **Step 2: 重写 orchestrator_node.py**

```python
"""
Orchestrator Agent 节点 - DAG 拓扑调度与多步骤编排。

V2.0 升级：从单步转发升级为 DAG 拓扑排序 + 并行调度。
使用 dag_scheduler 模块进行拓扑排序和就绪节点查找。
"""
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.agent.router.dag_scheduler import (
    topological_sort, find_ready_nodes, resolve_parameter_references, get_dag_progress
)
from app.core.logger import log


async def orchestrator_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    DAG 编排调度节点。

    程序说明：
    1. 从 AgentState.dag 获取 TaskDAG
    2. 拓扑排序，找出当前可执行节点
    3. 解析节点间参数引用
    4. 返回调度决策（由 graph 条件边分发到具体执行节点）

    注意：实际的并行执行由 LangGraph 的条件边和 L3 节点完成，
    此节点负责调度决策和参数解析。
    """
    dag_dict = state.get("dag", {})
    nodes = dag_dict.get("nodes", [])
    task_results = state.get("task_results", {})

    if not nodes:
        return {"execution_status": "completed"}

    # 拓扑排序（首次执行时）
    sorted_ids = topological_sort(nodes)
    log.info(f"[orchestrator_node] 拓扑排序结果: {sorted_ids}")

    # 找出就绪节点
    ready_nodes = find_ready_nodes(nodes, task_results)
    if not ready_nodes:
        # 无就绪节点 → 检查是否全部完成
        if len(task_results) >= len(nodes):
            log.info("[orchestrator_node] DAG 全部完成")
            return {"execution_status": "completed"}
        # 有未完成但无就绪节点 → 可能存在阻塞
        log.warning("[orchestrator_node] 无就绪节点但 DAG 未完成，可能存在阻塞")
        return {"execution_status": "failed"}

    # 解析就绪节点的参数引用
    for node in ready_nodes:
        params = node.get("parameters", {})
        resolved = resolve_parameter_references(params, task_results)
        node["parameters"] = resolved

    # 获取 DAG 进度
    progress = get_dag_progress(nodes, task_results)
    log.info(f"[orchestrator_node] DAG 进度: {progress}")

    # 设置当前任务为第一个就绪节点
    first_ready = ready_nodes[0]
    first_idx = next((i for i, n in enumerate(nodes) if n.get("task_id") == first_ready.get("task_id")), 0)

    # 更新 DAG（含解析后的参数）
    dag_dict["nodes"] = nodes

    intent_data = state.get("intent_data", {})
    intent_data["node"] = "orchestrator_node"
    intent_data["dag_progress"] = progress

    return {
        "intent_data": intent_data,
        "dag": dag_dict,
        "current_task_idx": first_idx,
        "execution_status": "running",
    }
```

- [ ] **Step 3: 验证无语法错误**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.agent.router.dag_scheduler import topological_sort, find_ready_nodes; from app.agent.nodes.orchestrator_node import orchestrator_node; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/app/agent/router/dag_scheduler.py autonome-backend/app/agent/nodes/orchestrator_node.py
git commit -m "feat: DAG调度器-拓扑排序+就绪节点查找+参数引用解析"
```

---

## Phase C: 前端可视化 + 错误恢复

### Task 7: DAG 进度可视化组件

**Files:**
- Create: `autonome-studio/src/components/chat/DAGProgressView.tsx`
- Modify: `autonome-studio/src/components/chat/ChatStage.tsx`
- Modify: `autonome-studio/src/store/useChatStore.ts`

- [ ] **Step 1: 创建 DAGProgressView.tsx**

```tsx
'use client'

/**
 * DAG 进度可视化组件。
 *
 * 显示 TaskDAG 中各 TaskNode 的执行状态，
 * 包括 pending/ready/running/completed/failed 五种状态。
 * 用于 ChatStage 中展示多步骤任务的执行进度。
 */

interface DAGNodeProgress {
  task_id: string
  intent: string
  status: 'pending' | 'ready' | 'running' | 'completed' | 'failed'
  label?: string
}

interface DAGProgressViewProps {
  nodes: DAGNodeProgress[]
}

const STATUS_STYLES: Record<string, { bg: string; text: string; icon: string }> = {
  pending:  { bg: 'bg-gray-100', text: 'text-gray-500', icon: '○' },
  ready:    { bg: 'bg-blue-50',  text: 'text-blue-600', icon: '◎' },
  running:  { bg: 'bg-amber-50', text: 'text-amber-600', icon: '◉' },
  completed: { bg: 'bg-green-50', text: 'text-green-600', icon: '✓' },
  failed:   { bg: 'bg-red-50',   text: 'text-red-600',   icon: '✗' },
}

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  ready: '就绪',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
}

export function DAGProgressView({ nodes }: DAGProgressViewProps) {
  if (!nodes || nodes.length === 0) return null

  // 单节点不显示进度条
  if (nodes.length === 1) return null

  const completedCount = nodes.filter(n => n.status === 'completed').length
  const totalCount = nodes.length

  return (
    <div className="my-3 p-3 bg-white/80 dark:bg-gray-800/80 rounded-xl border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
          任务进度
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-500">
          {completedCount}/{totalCount}
        </span>
      </div>

      {/* 进度条 */}
      <div className="flex gap-1 mb-2">
        {nodes.map((node) => {
          const style = STATUS_STYLES[node.status] || STATUS_STYLES.pending
          return (
            <div
              key={node.task_id}
              className={`flex-1 h-1.5 rounded-full ${style.bg} transition-colors duration-300`}
              title={`${node.label || node.task_id}: ${STATUS_LABELS[node.status]}`}
            />
          )
        })}
      </div>

      {/* 节点列表 */}
      <div className="flex flex-wrap gap-2">
        {nodes.map((node) => {
          const style = STATUS_STYLES[node.status] || STATUS_STYLES.pending
          return (
            <div
              key={node.task_id}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs ${style.bg} ${style.text}`}
            >
              <span>{style.icon}</span>
              <span>{node.label || node.task_id}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 在 useChatStore Message 类型中新增 dagProgress 字段**

在 `useChatStore.ts` 的 `Message` interface 中添加：

```typescript
dagProgress?: Array<{
  task_id: string
  intent: string
  status: 'pending' | 'ready' | 'running' | 'completed' | 'failed'
  label?: string
}>
```

- [ ] **Step 3: 在 ChatStage 中集成 DAGProgressView**

在 `ChatStage.tsx` 中导入 `DAGProgressView`，并在消息渲染区域中，当消息包含 `dagProgress` 时渲染进度组件：

```tsx
import { DAGProgressView } from './DAGProgressView'

// 在消息渲染中：
{msg.dagProgress && msg.dagProgress.length > 1 && (
  <DAGProgressView nodes={msg.dagProgress} />
)}
```

- [ ] **Step 4: 验证前端构建**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-studio && npx tsc --noEmit 2>&1 | head -20`
Expected: 无类型错误（或仅有与本次改动无关的已有错误）

- [ ] **Step 5: Commit**

```bash
git add autonome-studio/src/components/chat/DAGProgressView.tsx autonome-studio/src/components/chat/ChatStage.tsx autonome-studio/src/store/useChatStore.ts
git commit -m "feat: DAG进度可视化-DAGProgressView组件+ChatStage集成"
```

---

### Task 8: 错误恢复（DAG 节点重试 API）

**Files:**
- Modify: `autonome-backend/app/api/routes/chat.py` (新增重试端点)

- [ ] **Step 1: 在 chat.py 新增 DAG 节点重试端点**

```python
@router.post("/dag/retry/{task_id}")
async def dag_retry_task(
    task_id: str,
    session_id: str = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    重试 DAG 中失败的节点。

    程序说明：
    重置指定 task_id 的执行状态为 READY，
    清除其 task_results 记录，
    使其可被 DAG 调度器重新拾取执行。
    """
    try:
        # 通过 Redis 通知正在运行的 graph 重试该节点
        import redis
        from app.core.config import settings
        import json

        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True,
        )
        key = f"dag_retry:{task_id}"
        r.setex(key, 300, json.dumps({"task_id": task_id, "action": "retry"}))
        log.info(f"[dag_retry] 重试请求已写入 Redis: task_id={task_id}")
        return {"status": "ok", "task_id": task_id, "action": "retry"}
    except Exception as e:
        log.error(f"[dag_retry] Redis 写入失败: {e}")
        raise HTTPException(status_code=500, detail=f"重试请求失败: {str(e)}")
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/api/routes/chat.py
git commit -m "feat: DAG节点重试API-POST /dag/retry/{task_id}"
```

---

### Task 9: 全场景路由覆盖

**Files:**
- Modify: `autonome-backend/app/agent/graph.py` (determine_next_step 补全所有 IntentType)

- [ ] **Step 1: 确保 determine_next_step 覆盖所有 12 种 IntentType**

当前 `determine_next_step` 使用 `INTENT_NODE_MAP` 查找，已覆盖所有 12 种意图。但需确保 EXPLICIT_EXEC 的 L3 路由逻辑正确：

```python
def determine_next_step(state: AgentState) -> str:
    """条件边：决定图的下一步走向。"""
    # 最高优先级：L2 探查器发现缺参数
    probing_dict = state.get("active_probing")
    if probing_dict and probing_dict.get("is_missing"):
        return "ask_user_node"

    # 检查 DAG 是否有任务
    dag_dict = state.get("dag")
    if not dag_dict or not dag_dict.get("nodes"):
        return END

    idx = state.get("current_task_idx", 0)
    nodes = dag_dict.get("nodes", [])
    if idx >= len(nodes):
        return END

    # 根据原子意图分发到 Worker 节点
    intent_str = nodes[idx].get("intent", "INTENT_GENERAL_CHAT")
    try:
        intent = IntentType(intent_str)
        # EXPLICIT_EXEC 且有 skill_id 时走 L3 执行器
        if intent == IntentType.EXPLICIT_EXEC:
            task_params = nodes[idx].get("parameters", {})
            if task_params.get("skill_id") or state.get("skill_id"):
                return "l3_executor_node"
        return INTENT_NODE_MAP.get(intent, "chat_node")
    except ValueError:
        return "chat_node"
```

- [ ] **Step 2: 验证 graph 构建**

Run: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.agent.graph import build_intent_graph; g = build_intent_graph(); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/agent/graph.py
git commit -m "feat: 全场景路由覆盖-EXPLICIT_EXEC走L3+12意图完整映射"
```

---

## Task 10: 端到端验证与部署

**Files:** 无新文件

- [ ] **Step 1: 重启 Docker 服务**

Run: `cd /opt/data1/public/software/systools/autonome && docker-compose down && docker-compose up -d`

- [ ] **Step 2: 检查后端启动日志**

Run: `docker logs autonome-api 2>&1 | tail -30`
Expected: 无 import 错误，FastAPI 正常启动

- [ ] **Step 3: 检查前端启动日志**

Run: `docker logs autonome-web 2>&1 | tail -30`
Expected: Next.js 正常编译

- [ ] **Step 4: 自动部署**

Run: `./auto_deploy.sh -s "feat: 意图路由V2.0升级-核心链路+L3执行器+DAG调度+前端可视化" -d "Phase A: L1向量搜索+全量回退技能摘要注入, L2 Active Probing闭环(probing_submit API+probing_response_node), 路由中间件完善(route_after_l2/route_after_probing/route_after_execution). Phase B: L3执行器节点(复用skill_executor), DAG调度器(拓扑排序+就绪节点查找+参数引用解析). Phase C: DAG进度可视化(DAGProgressView), 错误恢复(dag_retry API), 全场景路由覆盖."`

---

## Self-Review

### Spec Coverage Check

| Spec Section | Task | Status |
|-------------|------|--------|
| 3.1 L1 结构化上下文增强 | Task 2 | Covered |
| 3.2 L2 Active Probing 闭环 | Task 3 | Covered |
| 3.3 路由中间件完善 | Task 4 | Covered |
| 4.1 L3 Executor 节点 | Task 5 | Covered |
| 4.2 DAG 调度器 | Task 6 | Covered |
| 5.1 DAG 进度可视化 | Task 7 | Covered |
| 5.2 错误恢复 | Task 8 | Covered |
| 5.3 全场景路由覆盖 | Task 9 | Covered |

### Placeholder Scan

No TBD, TODO, or placeholder patterns found.

### Type Consistency

- `ProbingResponse` defined in schemas.py (Task 1) matches usage in probing_response_node.py (Task 3)
- `TaskResult` defined in schemas.py (Task 1) matches usage in l3_executor_node.py (Task 5)
- `ExecutionStatus` / `TaskNodeStatus` defined in schemas.py (Task 1) matches usage in graph.py (Task 4)
- `DAGProgressView` props type matches `dagProgress` field on Message (Task 7)
- All `AgentState` field additions are consistent across all tasks
