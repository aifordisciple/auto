# 意图路由 V2.0 升级设计

> 日期: 2026-04-23
> 状态: Draft
> 范围: 意图识别与路由系统 V2.0 完整升级

---

## 1. 背景与目标

### 现状

V2.0 升级已完成 Phase 1 + Phase 2 部分：
- IntentType 6种意图枚举 ✅
- L1 DAG 分解器（结构化输出 + TaskDAG）✅
- L2 skill_registry 参数检查 + ProbingRequest ✅
- 前端 ParameterProbingCard + ChatStage ToolInvocation ✅
- graph.py 条件路由 route_after_classifier ✅

### 未完成

| 模块 | 差距 | 严重度 |
|------|------|--------|
| L1 结构化上下文 | L1 prompt 未注入技能摘要，不知道有哪些技能可调用 | HIGH |
| L2 Active Probing 闭环 | 前端提交参数后，后端缺少接收和回注逻辑 | HIGH |
| L3 Executor | 完全缺失，技能执行仍走旧 bot.py 路径 | HIGH |
| DAG 并行执行 | orchestrator_node 只做单步转发，无拓扑排序和并行调度 | HIGH |
| 路由中间件 | 缺少 route_after_probing / route_after_execution | HIGH |
| 前端 DAG 进度可视化 | ChatStage 缺少 DAG 进度展示 | MEDIUM |
| 错误恢复 | DAG 节点执行失败后无重试/跳过机制 | LOW |
| 全场景路由覆盖 | 数据分析、文件处理、闲聊等场景路由分支未实现 | MEDIUM |

### 目标

分三阶段升级，每阶段可独立验证，不破坏现有功能：

- **Phase A**：打通核心链路（L1 结构化上下文 + L2 闭环 + 路由中间件）
- **Phase B**：实现执行能力（L3 执行器 + DAG 调度）
- **Phase C**：完善体验（前端可视化 + 错误恢复 + 全场景覆盖）

---

## 2. 架构方案：渐进式节点替换

在现有 LangGraph graph 中逐步替换/增强节点，保持 graph 结构不变，只升级节点内部逻辑。

```
现有 graph:  classifier → route → worker → ...
升级后:      classifier(增强) → route(增强) → extractor(增强) → route → executor(新增) → route → ...
```

**选择理由**：
- 每个节点可独立升级、独立测试
- 不破坏现有路由链路
- 回滚容易（恢复单个节点即可）
- 与现有 Celery/Docker 沙箱无缝对接

---

## 3. Phase A：核心链路打通

### 3.1 L1 结构化上下文增强

**问题**：L1 prompt 只有用户消息，不知道系统有哪些技能可调用。

**方案：向量搜索优先 + 全量回退**

1. **首选**：用用户消息做向量搜索，从 pgvector 中检索 Top-K（K=10~15）最相关技能，只注入这些技能摘要给 L1
2. **回退**：向量搜索无结果或服务异常时，降级到 `get_skill_summary()` 全量注入（截断到 2000 token）

**数据流**：
```
用户消息 → embedding → pgvector Top-K 检索 →
  有结果 → 注入 Top-K 技能摘要到 L1 prompt
  无结果/异常 → 降级到 get_skill_summary() 全量摘要（截断）
```

**文件变更**：

| 文件 | 改动 |
|------|------|
| `router/l1_classifier.py` | 修改 prompt 模板增加 `available_skills` 区块；节点函数中先调用向量搜索，回退到全量摘要 |
| `router/skill_registry.py` | 新增 `get_skill_summary()` 方法（回退用） |
| 复用 `skill_vector_search.py` | 调用现有 `search_skills_by_embedding()` 方法 |

**性能预期**：向量搜索 ~100ms，远快于全量注入 + LLM 处理额外 token 的时间。

### 3.2 L2 Active Probing 闭环

**问题**：L2 能生成 ProbingRequest，前端能渲染表单，但用户提交参数后没有后端接收逻辑。

**方案**：

- 新增 API 端点 `POST /api/chat/probing/submit`，接收 `{message_id, parameters}`
- 在 graph 中新增 `probing_response_node`：接收用户提交的参数，回注到 `AgentState.task_parameters`
- 新增路由函数 `route_after_probing`：probing 完成后回到 L2 重新检查，或前进到 L3

**数据流**：
```
用户提交参数 → POST /api/chat/probing/submit →
  写入 Redis (key: probing:{message_id}, value: parameters, TTL: 10min) →
  返回 200 OK →
  graph polling_response_node 轮询 Redis 读取 →
  回注到 AgentState.task_parameters →
  route_after_probing → L2(再次检查) 或 L3(执行)
```

**说明**：API 与 graph 之间通过 Redis 解耦。API 写入后立即返回，graph 节点通过 message_id 从 Redis 读取。这样避免 API 需要直接操作 AgentState 的耦合问题。

**文件变更**：

| 文件 | 改动 |
|------|------|
| `api/routes/chat.py` | 新增 probing submit 端点 |
| `router/nodes/probing_response.py` | 新增 probing_response_node |
| `router/schemas.py` | AgentState 新增 `probing_response` 字段 |
| `graph.py` | 新增 probing_response_node 和 route_after_probing 条件边 |

**ProbingResponse 数据模型**：
```python
class ProbingResponse(BaseModel):
    """用户提交的 Active Probing 参数"""
    message_id: str          # 对应的 ProbingRequest message_id
    parameters: Dict[str, Any]  # 用户填写的参数
```

### 3.3 路由中间件完善

**问题**：只有 route_after_classifier，缺少 probing 后和执行后的路由。

**新增路由函数**：

| 路由函数 | 判断逻辑 | 去向 |
|----------|----------|------|
| `route_after_l2` | L2 判断需要 probing → 挂起等待前端；参数齐全 → L3 | ask_user_node（挂起） / l3_executor_node |
| `route_after_probing` | 参数仍不完整 → 回到 L2；参数齐全 → L3 | l2_extractor_node / l3_executor_node |
| `route_after_probing` | 参数仍不完整 → 回到 L2；参数齐全 → L3 | l2_extractor_node / l3_executor_node |
| `route_after_execution` | DAG 还有未完成节点 → 继续执行；DAG 完成 → ui_state | orchestrator_node / ui_state_node |

**文件变更**：

| 文件 | 改动 |
|------|------|
| `graph.py` | 新增 3 个条件边函数，更新 graph 边定义 |
| `router/schemas.py` | AgentState 新增 `execution_status` 字段 |

**execution_status 枚举**：
```python
class ExecutionStatus(str, Enum):
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 全部完成
    FAILED = "failed"          # 执行失败
    PROBING = "probing"        # 等待用户参数
```

---

## 4. Phase B：L3 执行器 + DAG 调度

### 4.1 L3 Executor 节点

**核心思路**：L3 是薄编排层，复用现有 `skill_executor.py` 的 Docker 沙箱执行能力。

**职责**：
- 接收 TaskNode（含 skill_id + parameters）
- 调用 `skill_executor.execute_skill(skill_id, parameters)`
- 收集执行结果，更新 `AgentState.task_results`
- 处理执行超时和异常

**文件变更**：

| 文件 | 改动 |
|------|------|
| `router/nodes/l3_executor.py` | 新增 l3_executor_node |
| `router/schemas.py` | 新增 TaskResult 模型；AgentState 新增 `task_results` 字段 |

**TaskResult 数据模型**：
```python
class TaskResult(BaseModel):
    """单个 TaskNode 的执行结果"""
    task_id: str
    skill_id: str
    status: Literal["success", "failed", "timeout"]
    output: Optional[Any] = None
    error: Optional[str] = None
    execution_time_seconds: float = 0.0
```

### 4.2 DAG 调度器

**核心思路**：在 orchestrator_node 中实现 DAG 拓扑排序 + 并行调度。

**调度逻辑**：
1. 从 AgentState.dag 获取 TaskDAG
2. 拓扑排序，找出当前可执行节点（所有前置节点已完成）
3. 可执行节点并行提交给 Celery worker
4. 收集结果，更新节点状态
5. 重复直到 DAG 完成

**并行策略**：
- 同层无依赖节点并行执行（通过 Celery group + chord：group 并行提交，chord 收集结果回调）
- 每个节点执行结果写入 task_results
- 节点间参数传递：后续节点的 parameters 中可用 `${前序task_id.output.field}` 语法引用前序节点输出，orchestrator 在调度时做变量替换

**文件变更**：

| 文件 | 改动 |
|------|------|
| `router/nodes/orchestrator.py` | 重写 orchestrator_node，实现 DAG 调度 |
| `router/schemas.py` | TaskNode 新增 `status` 字段 |

**TaskNode 状态扩展**：
```python
class TaskNodeStatus(str, Enum):
    PENDING = "pending"      # 等待前置节点完成
    READY = "ready"          # 可执行
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 执行失败
    SKIPPED = "skipped"      # 因依赖失败而跳过
```

### 4.3 执行后路由

**路由逻辑**：
- DAG 还有未完成节点 → 回到 orchestrator 继续调度
- DAG 全部完成 → 进入 ui_state 推送结果
- 节点执行失败 → 标记失败，尝试继续执行无依赖的后续节点（容错）

---

## 5. Phase C：前端可视化 + 错误恢复

### 5.1 DAG 进度可视化

**改动**：
- ChatStage 中新增 DAG 进度条组件，显示各 TaskNode 状态（等待/进行中/完成/失败）
- 通过 SSE 推送节点状态变更（复用现有 chat SSE 通道）

### 5.2 错误恢复

**改动**：
- DAG 节点失败后，前端展示失败原因 + 重试按钮
- 后端支持单节点重试：`POST /api/chat/dag/retry/{task_id}`
- 重试时重置该节点状态为 READY，重新提交到 Celery

### 5.3 全场景路由覆盖

**改动**：
- graph.py 中补全所有 IntentType 的路由分支
- 数据分析 → L1 分解 → L2 参数检查 → L3 执行
- 文件处理 → 直接调用文件处理工具
- 闲聊 → 直接 LLM 回复（跳过 L2/L3）
- 技能锻造 → 走 skill_forge_node
- 系统设置 → 走 settings 相关节点

---

## 6. 升级顺序与依赖关系

```
Phase A (核心链路)
  ├── 3.1 L1 结构化上下文增强 ← 无依赖
  ├── 3.2 L2 Active Probing 闭环 ← 无依赖
  └── 3.3 路由中间件完善 ← 依赖 3.2

Phase B (执行能力) ← 依赖 Phase A
  ├── 4.1 L3 Executor 节点 ← 依赖 3.3
  └── 4.2 DAG 调度器 ← 依赖 4.1

Phase C (体验完善) ← 依赖 Phase B
  ├── 5.1 DAG 进度可视化 ← 依赖 4.2
  ├── 5.2 错误恢复 ← 依赖 4.2
  └── 5.3 全场景路由覆盖 ← 依赖 4.1
```

---

## 7. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| L1 向量搜索延迟 | Top-K 限制在 10~15，超时降级到全量摘要 |
| L2 probing 闭环破坏现有聊天 | probing_response_node 只在 execution_status=PROBING 时激活 |
| L3 复用 skill_executor 兼容性 | 先写集成测试验证 execute_skill 接口兼容 |
| DAG 并行调度死锁 | 拓扑排序 + 环检测，有环则降级为顺序执行 |
| 前端 SSE 状态推送丢失 | 前端定时轮询 DAG 状态作为兜底 |

---

## 8. 不在本次升级范围内

- LLM 模型切换/优化
- 技能市场/推荐算法升级
- 用户权限/多租户
- 性能压测与优化
