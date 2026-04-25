# 即席交互式分析意图 (INTENT_ADHOC_INTERACTIVE_ANALYSIS) 设计文档

> 日期: 2026-04-25
> 状态: Draft
> 方案: 方案 C — 独立新节点 + 复用 Active Probing 挂起机制

---

## 1. 概述

### 1.1 问题定义

生信分析用户常处于"既不想纯手写代码，又发现系统里没有现成工具"的中间态。例如：用户上传 `counts.csv`，说"请用这个数据绘制一个热图"，但技能库中没有热图技能。

当前系统只能走 Skill Forge（纯代码生成）或 General Chat（闲聊），无法提供"生成带参数卡片的可交互分析"体验。

### 1.2 解决方案

新增第 13 种原子意图 `INTENT_ADHOC_INTERACTIVE_ANALYSIS`（即席交互式分析），实现：

1. L1 智能识别"有数据文件 + 分析需求 + 无技能匹配"的场景
2. 新节点 `adhoc_analysis_node` 调用 LLM 生成"策略包"（策略描述 + 代码 + 参数 Schema）
3. 复用 Active Probing 挂起机制，向前端推送"分析策略卡片"
4. 用户在卡片上修改参数或通过聊天交互，点击执行后 Docker 沙箱运行
5. 执行结果渲染在卡片下方

### 1.3 设计原则

- **职责清晰**：`adhoc_analysis_node` 只做策略生成，不与 Skill Forge 混杂
- **复用成熟机制**：Active Probing 的挂起/恢复已稳定运行，不引入新的状态管理
- **扩展成本低**：只需扩展 `ask_user_node` 和 `ProbingRequest`，不需要全新的 ToolCall 流程
- **分阶段实现**：Phase 1 先跑通核心流转（生成→卡片→执行），Phase 2 再做固化技能

### 1.4 触发边界（智能边界）

由 L1 分类器根据上下文智能判断：
- 有数据文件 + 分析需求 + 无技能匹配 → 即席分析
- 用户明确要求"写代码/脚本" → Skill Forge
- 有技能匹配 → Explicit Exec

---

## 2. 后端协议与数据模型

### 2.1 IntentType 新增枚举

文件：`autonome-backend/app/agent/router/schemas.py`

```python
class IntentType(str, Enum):
    # ... 保留原有 12 种意图 ...
    # 组1 新增：计算与编排
    ADHOC_INTERACTIVE_ANALYSIS = "INTENT_ADHOC_INTERACTIVE_ANALYSIS"
```

### 2.2 INTENT_NODE_MAP 新增映射

```python
INTENT_NODE_MAP: Dict[IntentType, str] = {
    # ... 保留原有映射 ...
    IntentType.ADHOC_INTERACTIVE_ANALYSIS: "adhoc_analysis_node",
}
```

### 2.3 TaskNode 扩展

新增 `adhoc_metadata` 字段，存放策略包：

```python
class TaskNode(BaseModel):
    # ... 保留原有字段 ...
    adhoc_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="即席分析元数据：策略描述、生成的代码、参数 Schema、输入映射。仅 ADHOC_INTERACTIVE_ANALYSIS 意图时有值"
    )
```

`adhoc_metadata` 结构：

```json
{
  "strategy": "使用 ComplexHeatmap 对表达矩阵进行行标准化并绘制聚类热图",
  "code": "library(optparse)\n...\n",
  "code_language": "r",
  "parameter_schema": {
    "type": "object",
    "properties": {
      "cluster_rows": { "type": "boolean", "title": "行聚类", "default": true },
      "color_palette": { "type": "string", "title": "配色方案", "enum": ["npg", "jco", "lancet"], "default": "npg" }
    }
  },
  "input_mapping": {
    "input_file_param": "input",
    "file_id": "file_abc123"
  }
}
```

### 2.4 ProbingRequest 扩展

新增 `render_type` 和 `adhoc_card_data` 字段：

```python
class ProbingRequest(BaseModel):
    # ... 保留原有字段 ...
    render_type: str = Field(
        default="parameter_probing",
        description="渲染类型：parameter_probing(参数反问) | adhoc_card(即席分析卡片)"
    )
    adhoc_card_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="即席分析卡片数据（仅 render_type=adhoc_card 时有值）"
    )
```

### 2.5 AgentState 扩展

无需新增字段。`active_probing` 中已可承载扩展后的 `ProbingRequest`。

---

## 3. L1 分类器升级

### 3.1 意图描述注入

文件：`autonome-backend/app/agent/router/l1_classifier.py`

在 `L1_DECOMPOSER_PROMPT_TEMPLATE` 的"可用意图类型"表格中新增：

```
| 即席分析 | INTENT_ADHOC_INTERACTIVE_ANALYSIS | 有数据文件+分析需求+无技能匹配 |
```

### 3.2 判定规则注入

在"指令"部分追加：

```
6. 即席分析判定原则：
   - 如果用户指令包含具体数据文件，且要求进行通用的分析/可视化操作（非系统预设标准技能），优先路由为 INTENT_ADHOC_INTERACTIVE_ANALYSIS
   - 如果用户明确说"写代码"、"写脚本"、"帮我写一个..."，路由为 INTENT_SKILL_FORGE
   - 如果技能库中有匹配的技能，路由为 INTENT_EXPLICIT_EXEC
```

### 3.3 JSON 格式输出扩展

在 `_decompose_with_json_mode` 的 `json_instruction` 中追加 `INTENT_ADHOC_INTERACTIVE_ANALYSIS` 枚举值。

---

## 4. L2 参数探测器升级

### 4.1 PROBING_INTENTS 扩展

文件：`autonome-backend/app/agent/router/l2_extractor.py`

```python
PROBING_INTENTS: Set[IntentType] = {
    IntentType.EXPLICIT_EXEC,
    IntentType.SKILL_FORGE,
    IntentType.DATA_PROBE,
    IntentType.LITERATURE_MINING,
    IntentType.ADHOC_INTERACTIVE_ANALYSIS,  # 新增
}
```

### 4.2 ENRICHMENT_INTENTS 扩展

```python
ENRICHMENT_INTENTS: Set[IntentType] = {
    IntentType.SKILL_FORGE,
    IntentType.EXPLICIT_EXEC,
    IntentType.DATA_PROBE,
    IntentType.LITERATURE_MINING,
    IntentType.ADHOC_INTERACTIVE_ANALYSIS,  # 新增
}
```

### 4.3 即席分析参数检查

在 `check_task_parameters` 中新增分支：

```python
if task.intent == IntentType.ADHOC_INTERACTIVE_ANALYSIS:
    return _check_adhoc_analysis_params(task, context)
```

`_check_adhoc_analysis_params` 逻辑：
- 即席分析必须至少有一个 `resolved_assets`（输入文件）
- 如果缺失，返回 ProbingRequest 要求用户指定文件
- 如果有文件，放行

---

## 5. 核心执行节点（adhoc_analysis_node）

### 5.1 文件位置

`autonome-backend/app/agent/nodes/adhoc_analysis_node.py`（新建）

### 5.2 节点职责

1. 从 `AgentState` 中获取当前 TaskNode 的指令和文件信息
2. 调用 LLM（thinking 模型）生成策略包
3. 将策略包存入 `TaskNode.adhoc_metadata`
4. 生成 `ProbingRequest(render_type="adhoc_card")` 触发前端渲染
5. 不推进 `current_task_idx`，等待用户确认

### 5.3 LLM Prompt 设计

```
你是一个生物信息学即席分析专家。
用户希望对文件 {file_id} 进行以下分析：{instruction}

你的任务是生成一份"分析策略包"，必须包含以下 JSON 格式的内容：
1. strategy: 简洁的文字描述分析逻辑
2. code: 完整的、带参数系统的 Python 或 R 代码
3. code_language: "python" 或 "r"
4. parameter_schema: 符合 JSON Schema 规范的参数定义，包含默认值
5. input_mapping: 将用户指定的文件 ID 映射到代码的输入参数名

代码要求：
- 必须使用 argparse(Python) 或 optparse(R) 参数系统
- 必须为所有参数设定符合生信经验的默认值
- 输出目录使用 TASK_OUT_DIR 环境变量
```

### 5.4 LLM 配置

使用 `get_thinking_llm_config`（深度推理模型），因为策略包生成需要：
- 理解用户的分析意图
- 选择合适的分析方法和 R/Python 包
- 生成带参数系统的完整代码
- 设计合理的参数 Schema

### 5.5 状态输出

```python
return {
    "intent_data": {**intent_data, "node": "adhoc_analysis_node"},
    "active_probing": probing_request.model_dump(),
    # 不推进 current_task_idx
}
```

---

## 6. LangGraph 图编排

### 6.1 graph.py 变更

文件：`autonome-backend/app/agent/graph.py`

1. 导入 `adhoc_analysis_node`
2. 在 `build_intent_graph` 中添加节点：`workflow.add_node("adhoc_analysis_node", adhoc_analysis_node)`
3. 将 `"adhoc_analysis_node"` 加入 `all_worker_nodes`
4. `determine_next_step` 中新增路由：`IntentType.ADHOC_INTERACTIVE_ANALYSIS` → `"adhoc_analysis_node"`

### 6.2 ask_user_node 扩展

当前 `ask_user_node` 只构造 `request_parameters` ToolCall。扩展后：

```python
async def ask_user_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    probing_dict = state.get("active_probing")
    probing = ProbingRequest(**probing_dict)

    if probing.render_type == "adhoc_card":
        # 即席分析卡片：使用 render_adhoc_card ToolCall
        tool_call = {
            "name": "render_adhoc_card",
            "args": {
                "strategy": probing.adhoc_card_data.get("strategy", ""),
                "code": probing.adhoc_card_data.get("code", ""),
                "code_language": probing.adhoc_card_data.get("code_language", "python"),
                "parameter_schema": probing.adhoc_card_data.get("parameter_schema", {}),
                "input_mapping": probing.adhoc_card_data.get("input_mapping", {}),
            },
            "id": f"call_adhoc_{current_idx}",
        }
    else:
        # 原有参数反问逻辑
        tool_call = {
            "name": "request_parameters",
            "args": {
                "message": probing.message_to_user,
                "schema": probing.ui_schema,
            },
            "id": f"call_probe_{current_idx}",
        }

    return {"messages": [AIMessage(content="", tool_calls=[tool_call])]}
```

### 6.3 probing_response_node 扩展

当 `render_type == "adhoc_card"` 时，`probing_response_node` 需要：
- 从 `addToolResult` 的 result 中提取用户修改后的参数（`result.action === 'execute'` 时，`result.payload.parameters` 为最终参数）
- 将用户参数覆盖 `adhoc_metadata.parameter_schema` 中的默认值
- 将最终参数存入 `TaskNode.parameters`，代码快照存入 `TaskNode.parameters.code_snapshot`
- 供 `l3_executor_node` 使用：从 `parameters.code_snapshot` 取代码，从 `parameters` 取命令行参数

### 6.4 l3_executor_node 执行路径

即席分析的执行需要特殊处理：
- 从 `adhoc_metadata.code` 获取脚本内容
- 将脚本写入临时文件
- 从合并后的参数构建命令行参数
- 使用 `run_container` 在 Docker 沙箱中执行
- 返回结果文件树

---

## 7. 前端 AdhocAnalysisCard 组件

### 7.1 文件位置

`autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx`（新建）

### 7.2 组件 Props

```typescript
interface AdhocAnalysisCardProps {
  toolCallId: string
  args: {
    strategy: string
    code: string
    code_language: 'python' | 'r'
    parameter_schema: Record<string, SchemaProperty>
    input_mapping: Record<string, string>
  }
  addToolResult: (result: { toolCallId: string; result: any }) => void
}
```

### 7.3 组件结构

四个区域：

1. **策略说明区**（顶部，靛蓝色背景）
   - 标题："即席分析就绪"
   - 策略文字描述

2. **参数面板**（中部，网格布局）
   - 根据 `parameter_schema` 动态渲染表单
   - 支持：下拉框（enum）、复选框（boolean）、数字输入（number）、文本输入（string）
   - 预填默认值

3. **代码预览区**（折叠）
   - 点击"查看/编辑底层代码"展开
   - 语法高亮显示代码

4. **操作区**（底部，灰色背景）
   - "执行分析"按钮（主按钮，靛蓝色）
   - "固化为团队技能"按钮（次按钮，outline）

### 7.4 执行流程

用户点击"执行分析"：
1. 收集表单中的当前参数值
2. 合并 `input_mapping` 中的文件映射
3. 包含代码快照（`code`），防止后端丢失上下文
4. 调用 `addToolResult({ toolCallId, result: { action: 'execute', payload } })`
5. 后端收到后恢复 LangGraph 状态机，进入 `l3_executor_node`

### 7.5 固化技能流程（Phase 2）

用户点击"固化为团队技能"：
1. 弹出技能编辑表单
2. 预填：代码、参数 Schema、名称（从策略描述提取）
3. 用户补充：分类、标签、描述
4. 调用 Skill Forge API 创建技能
5. 成功后显示提示"技能已固化到团队库"

### 7.6 结果渲染

执行完成后，在卡片下方追加结果区：
- 成功状态：绿色背景，显示文件树和图片预览
- 失败状态：红色背景，显示错误信息和重试按钮

### 7.7 ChatStage 集成

在 `ChatStage.tsx` 的消息渲染逻辑中：
- 检测 `toolInvocation.toolName === "render_adhoc_card"`
- 挂起状态（无 result）→ 渲染 `AdhocAnalysisCard`
- 完成状态（有 result）→ 渲染结果区

### 7.8 混合交互模式

用户可以在聊天中修改参数：
- 后端收到消息后，检查是否有挂起的即席分析
- 如果是参数修改意图（如"把配色改成 Lancet"），更新 `adhoc_metadata` 中的参数
- 前端收到更新后刷新卡片

---

## 8. 分阶段实现计划

### Phase 1：核心流转（本次实现）

1. 后端协议升级（schemas.py、l1_classifier.py、l2_extractor.py）
2. 新增 adhoc_analysis_node
3. graph.py 图编排变更
4. ask_user_node 扩展
5. 前端 AdhocAnalysisCard 组件
6. ChatStage 集成
7. 执行闭环（probing_response_node → l3_executor_node）

### Phase 2：固化技能（后续迭代）

1. 固化技能表单组件
2. Skill Forge API 调用
3. 技能库写入

### Phase 3：增强体验（远期）

1. 聊天交互修改参数
2. 代码在线编辑
3. 执行结果可视化增强
4. 分析历史记录

---

## 9. 错误处理

| 场景 | 处理策略 |
|------|----------|
| LLM 策略包生成失败 | 降级为 Skill Forge（代码生成但不带参数卡片） |
| LLM 输出格式错误 | 使用 json_repair 修复，修复失败则降级 |
| Docker 执行失败 | 返回错误信息，允许用户修改参数后重新执行 |
| 用户取消 | 清除 active_probing，恢复到正常聊天状态 |
| 输入文件不存在 | L2 拦截，要求用户重新指定文件 |

---

## 10. 关键文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `autonome-backend/app/agent/router/schemas.py` | 修改 | 新增 IntentType 枚举、TaskNode.adhoc_metadata、ProbingRequest 扩展 |
| `autonome-backend/app/agent/router/l1_classifier.py` | 修改 | L1 提示词新增意图描述和判定规则 |
| `autonome-backend/app/agent/router/l2_extractor.py` | 修改 | 新增即席分析参数检查 |
| `autonome-backend/app/agent/nodes/adhoc_analysis_node.py` | 新建 | 核心执行节点 |
| `autonome-backend/app/agent/graph.py` | 修改 | 图编排变更 |
| `autonome-studio/src/components/chat/components/AdhocAnalysisCard.tsx` | 新建 | 前端策略卡片组件 |
| `autonome-studio/src/components/chat/components/index.ts` | 修改 | 导出新组件 |
| `autonome-studio/src/components/chat/ChatStage.tsx` | 修改 | ToolCall 渲染逻辑集成 |
