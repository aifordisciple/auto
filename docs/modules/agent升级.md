
1. **Orchestrator Agent**：负责 Pipeline 级别的意图串联与 Nextflow 代码生成。
2. **Skill Forge Agent**：执行原子脚本的编写与代码重构，内置强制注释保留审计器。
3. **Explicit Skill Agent**：负责 Docker 暖池沙箱的生命周期管理及结果提取。
4. **UI/State Agent**：不重启后端，直接重载前端可视化参数，生成 SCI 图表及制图数据。
5. **System/Asset Agent**：对接系统底层进行资源与账单运维。
6. **Data Probe Agent**：快速预览矩阵元数据与分布。
7. **Literature Agent**：对接 PDF 多模态处理，提供方法学溯源。
8. **Diagnostic Agent**：读取异常日志并输出自愈策略。

为了确保架构落地的严谨性，我们将严格按照你列出的 **1 到 8 的顺序**，对现有的 LangGraph 节点进行逐一重构和升级。

考虑到代码的完整性和细节深度，我们先在这一步完成前四个最核心的**工程与计算、视图层智能体 (Agents 1-4)**。完成后你可以在本地测试，我们再继续推进后四个。

请确保你的 `AgentState` 已经包含了 `dag`, `current_task_idx`, `task_results` 等图谱流转所必需的状态字段。

---

### 1. Orchestrator Agent (工作流编排节点)
**职责**：拦截硬编码，生成工业级 Nextflow DSL2 流程，确保通道隔离和数据落盘。

请创建或更新文件 `autonome-backend/app/agent/nodes/orchestrator_node.py`：

```python
from langchain_core.prompts import ChatPromptTemplate
from app.agent.graph import AgentState

ORCHESTRATOR_SYSTEM_PROMPT = """
你是 Autonome Studio 的 [Orchestrator 工作流编排大师]。
你的唯一目标是将用户的复杂宏观生物学分析需求，转化为工业级的 Nextflow (DSL2) 流程代码。

=== 核心编排规范 (工业级约束) ===
1. 【通道与进程解耦】：必须使用 Nextflow DSL2 语法，明确分离 `Channel` 定义与 `Process` 定义。
2. 【参数化一切】：绝不硬编码任何文件路径或核心阈值！所有变量必须通过 `params.xxx` 暴露。
3. 【强制数据落盘】：每个 `Process` 必须包含 `publishDir "${params.outdir}/xxx", mode: 'copy'` 指令，确保中间结果（如 .rds, .bam, .tsv）能被正确挂载回用户的资产面板。
4. 【配置文件分离】：你必须同时提供 `main.nf` (核心逻辑) 和 `nextflow.config` (资源与环境配置，需指定 docker container)。

=== 输出格式 ===
请使用以下格式输出，切勿使用常规的 Markdown 代码块反引号，必须使用 ### 标签包裹代码：
###nextflow
// main.nf content here
###
###config
// nextflow.config content here
###
"""

async def orchestrator_node(state: AgentState, llm) -> AgentState:
    """负责 Pipeline 级别的意图串联与 Nextflow 代码生成"""
    idx = state.get("current_task_idx", 0)
    current_task = state["dag"].nodes[idx]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", ORCHESTRATOR_SYSTEM_PROMPT),
        ("human", "请为以下需求编排 Nextflow 流程：\n{instruction}\n\n涉及的基础资产ID: {assets}\n推断参数: {params}")
    ])
    
    chain = prompt | llm
    response = await chain.ainvoke({
        "instruction": current_task.raw_instruction,
        "assets": current_task.resolved_assets,
        "params": current_task.parameters
    })
    
    state["task_results"][current_task.task_id] = {
        "status": "pipeline_generated",
        "node_type": "orchestrator",
        "output": response.content
    }
    
    state["current_task_idx"] += 1
    state["messages"].append(response)
    
    return state
```

---

### 2. Skill Forge Agent (代码锻造节点)
**职责**：执行原子脚本的编写与重构，强制要求参数系统，并且**绝对禁止丢失历史注释**。

请创建或更新文件 `autonome-backend/app/agent/nodes/skill_forge_node.py`：

```python
from langchain_core.prompts import ChatPromptTemplate
from app.agent.graph import AgentState

FORGE_SYSTEM_PROMPT = """
你是一个顶级的生物信息学研发架构师，现在负责 Autonome Studio 的 [Skill Forge 代码锻造节点]。

=== 最高优先级系统指令（违背将导致任务熔断） ===
1. 【非破坏性更新】：当你对现有代码进行修改、优化或 Bug 修复时，绝对禁止删除或截断历史版本中的 `@ProgramExplanation`（程序说明）和任何原有的中文行级注释。你只能追加或修改代码逻辑，绝不能抹除前人的上下文注释。
2. 【强制参数系统】：所有生成的独立脚本必须使用标准的参数解析库（Python 使用 `argparse`，R 使用 `optparse` 或 `commandArgs`）。
3. 【生信默认值】：必须为所有参数设定符合真实生信分析经验的默认值（如 k-mer 默认为 3，p-value 默认为 0.05）。

请将生成的代码包裹在 ###python 或 ###R 等标签中输出。
"""

async def skill_forge_node(state: AgentState, llm) -> AgentState:
    """执行原子脚本的编写与代码重构，内置强制注释保留审计器"""
    idx = state.get("current_task_idx", 0)
    current_task = state["dag"].nodes[idx]
    
    # 获取对话上下文，以便 LLM 知道之前的代码长什么样
    messages = state.get("messages", [])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", FORGE_SYSTEM_PROMPT),
        ("human", "任务指令: {instruction}\n挂载资产: {assets}\n\n如有历史代码上下文，请务必进行【非破坏性更新】，保留所有中文注释。")
    ])
    
    chain = prompt | llm
    response = await chain.ainvoke({
        "instruction": current_task.raw_instruction,
        "assets": current_task.resolved_assets
    })
    
    state["task_results"][current_task.task_id] = {
        "status": "code_forged",
        "node_type": "skill_forge",
        "output": response.content
    }
    
    state["current_task_idx"] += 1
    state["messages"].append(response)
    
    return state
```

---

### 3. Explicit Skill Agent (显式技能执行节点)
**职责**：接收完备参数，生成对接 Docker 暖池沙箱的最终执行命令。

请创建或更新文件 `autonome-backend/app/agent/nodes/explicit_skill_node.py`：

```python
from langchain_core.prompts import ChatPromptTemplate
from app.agent.graph import AgentState

EXPLICIT_EXEC_SYSTEM_PROMPT = """
你是 Autonome Studio 的 [Explicit Skill Agent 显式执行节点]。
你负责管理 Docker 暖池沙箱的生命周期和任务派发。前置的 L2 层探针已经确认参数是完备的。

=== 执行派发准则 ===
1. 提取上下文中的资产 ID (`resolved_assets`) 和执行参数 (`parameters`)。
2. 严禁大模型“幻觉”捏造参数，直接将参数安全地映射到目标工具的 CLI 调用命令中。
3. 生成对应的入口调用命令（例如：`Rscript run_deseq2.R --input {asset} --pvalue {p_val}`）。
4. 将最终的执行命令和所需的环境要求结构化输出。

请将生成的执行载荷包裹在 ###bash 标签中输出。
"""

async def explicit_skill_node(state: AgentState, llm) -> AgentState:
    """负责 Docker 暖池沙箱的生命周期管理及结果提取 (派发指令生成)"""
    idx = state.get("current_task_idx", 0)
    current_task = state["dag"].nodes[idx]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", EXPLICIT_EXEC_SYSTEM_PROMPT),
        ("human", "执行指令: {instruction}\n挂载资产ID: {assets}\n校验完毕的参数: {params}")
    ])
    
    chain = prompt | llm
    response = await chain.ainvoke({
        "instruction": current_task.raw_instruction,
        "assets": current_task.resolved_assets,
        "params": current_task.parameters
    })
    
    # 实际架构中，系统会抓取这段 bash 并通过 Celery/Docker SDK 发送给沙箱
    state["task_results"][current_task.task_id] = {
        "status": "dispatched_to_sandbox",
        "node_type": "explicit_exec",
        "payload": response.content
    }
    
    state["current_task_idx"] += 1
    state["messages"].append(response)
    
    return state
```

---

### 4. UI/State Agent (视图微调与状态节点)
**职责**：这是实现 SCI 级图表输出规范和数据对称性（图表 + TSV）的核心枢纽，不随意重启厚重的沙箱。

请创建或更新文件 `autonome-backend/app/agent/nodes/ui_state_node.py`：

```python
from langchain_core.prompts import ChatPromptTemplate
from app.agent.graph import AgentState

UI_STATE_SYSTEM_PROMPT = """
你是 Autonome Studio 的 [UI/State Agent 视图微调节点]。
你的职责是不重启耗时的后端计算沙箱，直接重载前端可视化组件参数，或执行极轻量级的绘图脚本。

=== 核心输出协议 (SCI Protocol - 违背将引发熔断) ===
1. 【发表级视觉】：生成的绘图配置必须采用专业科研配色（如 ggsci 的 npg/jco/lancet）。必须强制要求输出分辨率至少 300 DPI。
2. 【多格式制图】：必须强制要求同步生成 `.pdf`（供论文排版使用）和 `.png`（供前端预览使用）双版本图像。
3. 【数据对称性 (Data Symmetry)】：严禁仅输出图像！你生成的制图逻辑中，必须包含将该图形底层对应的坐标数据、阈值分类数据（如上调/下调标签）导出为一个以 Tab 分割的 `.tsv` 文件的代码/配置。

请将前端组件状态 JSON 包裹在 ###json 标签中，或将轻量级绘图重载命令包裹在 ###R / ###python 标签中输出。
"""

async def ui_state_node(state: AgentState, llm) -> AgentState:
    """直接重载前端可视化参数，生成 SCI 图表及对应制图数据 TSV"""
    idx = state.get("current_task_idx", 0)
    current_task = state["dag"].nodes[idx]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", UI_STATE_SYSTEM_PROMPT),
        ("human", "视图微调需求: {instruction}\n当前视图涉及的资产: {assets}\n微调参数: {params}")
    ])
    
    chain = prompt | llm
    response = await chain.ainvoke({
        "instruction": current_task.raw_instruction,
        "assets": current_task.resolved_assets,
        "params": current_task.parameters
    })
    
    state["task_results"][current_task.task_id] = {
        "status": "view_updated",
        "node_type": "ui_state",
        "output": response.content
    }
    
    state["current_task_idx"] += 1
    state["messages"].append(response)
    
    return state
```

收到。我们继续按照你的顺序，完成剩下 4 个核心运维、探究与智能节点的升级。这批节点是系统从“单纯执行代码”向“Agentic 智能操作系统”跨越的关键。

请确保继续在 `autonome-backend/app/agent/nodes/` 目录下创建或更新这些文件。

---

### 5. System/Asset Agent (系统与资产节点)
**职责**：对接底层 K8s/Docker 算力池、文件系统网关以及 Stripe 计费。执行诸如节点切换、文件迁移、成本预估等操作。

请创建或更新文件 `autonome-backend/app/agent/nodes/system_asset_node.py`：

```python
from langchain_core.prompts import ChatPromptTemplate
from app.agent.graph import AgentState

SYSTEM_ASSET_SYSTEM_PROMPT = """
你是 Autonome Studio 的 [System & Asset Agent 系统与资产管护节点]。
你拥有直接调用底层 Kubernetes/Docker 调度器、文件存储网关以及 Stripe 计费 API 的权限。

=== 操作准则 ===
1. 【算力调度】：当用户请求（或 Diagnostic 节点建议）切换高配节点时，请输出明确的调度标签（如 `node_selector: high-mem` 或 `M3-Ultra-pool`）。
2. 【文件系统管护】：对资产目录进行增删改查、冷热数据归档（Archiving）时，生成对应的 POSIX 文件操作命令或内部 API 载荷。
3. 【计费与配额】：当涉及 Stripe 扣费预估时，根据任务消耗输出结构化的成本清单。
4. 【安全第一】：如果涉及删除（Delete）操作，必须确保使用的是软删除（放入回收站），或者在执行载荷中明确标记 `require_user_confirmation: true`。

请将底层的执行载荷（JSON 或 Shell 命令）包裹在 ###json 或 ###bash 标签中输出，并在外部附上一段给用户的友好解释。
"""

async def system_asset_node(state: AgentState, llm) -> AgentState:
    """对接系统底层进行资源与账单运维"""
    idx = state.get("current_task_idx", 0)
    current_task = state["dag"].nodes[idx]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_ASSET_SYSTEM_PROMPT),
        ("human", "运维指令: {instruction}\n涉及资产ID: {assets}\n提取参数: {params}\n\n(系统上下文：当前默认挂载 warm-pool 容器池)")
    ])
    
    chain = prompt | llm
    
    response = await chain.ainvoke({
        "instruction": current_task.raw_instruction,
        "assets": current_task.resolved_assets,
        "params": current_task.parameters
    })
    
    state["task_results"][current_task.task_id] = {
        "status": "ops_dispatched",
        "node_type": "system_asset",
        "output": response.content
    }
    
    state["current_task_idx"] += 1
    state["messages"].append(response)
    
    return state
```

---

### 6. Data Probe Agent (数据探针节点)
**职责**：作为重型计算前的前置侦察兵，利用极低延迟的脚本/命令快速拉取矩阵元数据与分布。

请创建或更新文件 `autonome-backend/app/agent/nodes/data_probe_node.py`：

```python
from langchain_core.prompts import ChatPromptTemplate
from app.agent.graph import AgentState

DATA_PROBE_SYSTEM_PROMPT = """
你是 [Data Probe Agent 数据探针节点]。你是系统的轻骑兵侦察员。
你的任务是在极短的时间内（毫秒级到秒级）提取大型矩阵或结构化数据的元信息（如行列数、NA比例、分布极值、Header 格式）。

=== 探针行为准则 ===
1. 【绝对轻量化】：严禁将整个 GB 级大文件读入内存。
   - 对 CSV/TSV：优先生成 `head`, `awk`, `wc -l`, `cut` 等 Linux 流式读取命令。
   - 对 RDS/H5AD：优先生成仅读取 `metadata` 或 `dim()` 的极简 R/Python 脚本，绝不执行耗时的聚类或降维。
2. 【输出精准】：探针脚本的 stdout 必须只包含用户或系统需要的核心数值，不要打印冗长的过程日志。
3. 【条件分支判定】：如果指令暗示这是一个条件判断（例如“看看 NA 比例，如果大于 5% 就...”），你生成的脚本必须明确输出这个判断指标，以便下游节点读取。

请将生成的轻量级探针命令包裹在 ###bash 或 ###python 标签中输出。
"""

async def data_probe_node(state: AgentState, llm) -> AgentState:
    """快速预览矩阵元数据与分布，常作为 DAG 决策分支前置"""
    idx = state.get("current_task_idx", 0)
    current_task = state["dag"].nodes[idx]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", DATA_PROBE_SYSTEM_PROMPT),
        ("human", "探测目标: {instruction}\n目标资产ID: {assets}\n参数: {params}")
    ])
    
    chain = prompt | llm
    response = await chain.ainvoke({
        "instruction": current_task.raw_instruction,
        "assets": current_task.resolved_assets,
        "params": current_task.parameters
    })
    
    state["task_results"][current_task.task_id] = {
        "status": "probe_generated",
        "node_type": "data_probe",
        "output": response.content
    }
    
    state["current_task_idx"] += 1
    state["messages"].append(response)
    
    return state
```

---

### 7. Literature Agent (文献与图谱解析节点)
**职责**：对接 pgvector 和多模态处理引擎，逆向提取文献中的超参数和视觉映射事实，防范大模型幻觉。

请创建或更新文件 `autonome-backend/app/agent/nodes/literature_node.py`：

```python
from langchain_core.prompts import ChatPromptTemplate
from app.agent.graph import AgentState

LITERATURE_SYSTEM_PROMPT = """
你是 Autonome Studio 的 [Literature Agent 文献与图谱解析专家]。
你的任务是对用户上传的 PDF 文献截图、Methodology 描述或结果图表进行逆向工程。

=== 知识提取纪律 (反幻觉机制) ===
1. 【忠于原文】：你提取的任何软件版本号、聚类算法名称、过滤阈值（如 p-value, Log2FC），必须 100% 来源于提供的上下文资产。如果上下文中没有提及，必须明确回答“文献未提供该参数”，绝不可捏造或使用你的经验默认值。
2. 【视觉特征结构化】：如果任务涉及“看图复刻”（如复刻热图），你必须提取以下视觉维度：
   - 调色板风格 (Palette, 如 Red-White-Blue, JCO, NPG)
   - 聚类树状态 (是否包含行列 Dendrogram)
   - 几何元素 (点大小映射逻辑、透明度等)
3. 【为下游铺路】：你的输出往往是供后续 `Skill Forge` (代码锻造) 或 `UI/State` (视图微调) 使用的事实依据。请确保输出高度结构化。

请将提取到的结构化事实和参数包裹在 ###json 标签中，或以清晰的 Markdown 列表呈现。
"""

async def literature_node(state: AgentState, llm) -> AgentState:
    """对接 PDF 多模态处理，提供方法学溯源"""
    idx = state.get("current_task_idx", 0)
    current_task = state["dag"].nodes[idx]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", LITERATURE_SYSTEM_PROMPT),
        ("human", "解析需求: {instruction}\n目标文献/图像资产ID: {assets}\n\n(系统旁白：请假设底层多模态/RAG引擎已经将图像或 PDF 核心内容转换为当前文本供你分析)")
    ])
    
    chain = prompt | llm
    
    response = await chain.ainvoke({
        "instruction": current_task.raw_instruction,
        "assets": current_task.resolved_assets
    })
    
    state["task_results"][current_task.task_id] = {
        "status": "knowledge_extracted",
        "node_type": "literature",
        "output": response.content
    }
    
    state["current_task_idx"] += 1
    state["messages"].append(response)
    
    return state
```

---

### 8. Diagnostic Agent (错误诊断与自愈节点)
**职责**：读取非零退出码和崩溃日志，不再把全屏红字扔给用户，而是直接输出诊断结果并提供自动修复的载荷，联动 Skill Forge 节点实现“自愈”。

请创建或更新文件 `autonome-backend/app/agent/nodes/diagnostic_node.py`：

```python
from langchain_core.prompts import ChatPromptTemplate
from app.agent.graph import AgentState

DIAGNOSTIC_SYSTEM_PROMPT = """
你是 Autonome Studio 的 [Diagnostic Agent 错误诊断老中医]。
当底层的 R/Python 脚本或 Nextflow 工作流执行失败时，由你接管。

=== 诊断与自愈规范 ===
你的输出必须包含以下三个结构化部分：
1. 【根因分析 (Root Cause)】：用一句话向用户解释为什么挂了（如：缺失 R 包、内存溢出 OOM、输入矩阵含有 NA 值、API 限流等），绝不要直接贴出冗长的代码栈追踪。
2. 【自愈策略 (Healing Strategy)】：
   - 若是环境缺失：输出 `BiocManager::install(...)` 等环境修复指令。
   - 若是资源不足：建议用户授权切换大内存节点。
   - 若是代码逻辑报错：明确指出需要在代码哪一行增加预处理（如 `dropna()`, 数据类型强转）。
3. 【流转建议】：如果错误可以通过修改代码解决，请明确声明“已生成代码补丁，建议交由 Skill Forge 节点重构执行”。

请保持冷静、专业的基调，让科研人员感到一切异常都在系统掌控之中。
"""

async def diagnostic_node(state: AgentState, llm) -> AgentState:
    """读取异常日志并输出自愈策略"""
    idx = state.get("current_task_idx", 0)
    current_task = state["dag"].nodes[idx]
    
    # 在真实流转中，这里会去 state 中抓取上一步执行节点的 stderr 报错信息
    simulated_stderr = current_task.parameters.get("stderr", "Execution halted: Exit Code 1. Check upstream logs.")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", DIAGNOSTIC_SYSTEM_PROMPT),
        ("human", "求助指令: {instruction}\n崩溃涉及资产: {assets}\n捕获的系统错误日志 (Stderr): {stderr}")
    ])
    
    chain = prompt | llm
    
    response = await chain.ainvoke({
        "instruction": current_task.raw_instruction,
        "assets": current_task.resolved_assets,
        "stderr": simulated_stderr
    })
    
    state["task_results"][current_task.task_id] = {
        "status": "diagnosed",
        "node_type": "diagnostic",
        "output": response.content
    }
    
    state["current_task_idx"] += 1
    state["messages"].append(response)
    
    return state
```

---

### 全局串联指南 (Graph Integration)

现在 1 到 8 号智能体代码已全部齐备。你需要打开核心状态机文件（目前代码库中的 `autonome-backend/app/agent/graph.py` 或你新建的路由入口），将这 8 个节点编织进你的 LangGraph 中：

```python
# ... 引入你刚刚写好的这 8 个节点
from app.agent.nodes.orchestrator_node import orchestrator_node
from app.agent.nodes.skill_forge_node import skill_forge_node
from app.agent.nodes.explicit_skill_node import explicit_skill_node
from app.agent.nodes.ui_state_node import ui_state_node
from app.agent.nodes.system_asset_node import system_asset_node
from app.agent.nodes.data_probe_node import data_probe_node
from app.agent.nodes.literature_node import literature_node
from app.agent.nodes.diagnostic_node import diagnostic_node

# 构建状态机
# workflow = StateGraph(AgentState)

# 注册核心节点
workflow.add_node("orchestrator_node", orchestrator_node)
workflow.add_node("skill_forge_node", skill_forge_node)
workflow.add_node("explicit_exec_node", explicit_skill_node)
workflow.add_node("ui_state_node", ui_state_node)
workflow.add_node("system_asset_node", system_asset_node)
workflow.add_node("data_probe_node", data_probe_node)
workflow.add_node("literature_node", literature_node)
workflow.add_node("diagnostic_node", diagnostic_node)

# ... 配置条件路由 Edge 等逻辑
```
