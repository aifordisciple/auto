AI 生信平台 SKILL 引擎架构与演进规划 (v2.0)1. 核心理念与工作流重塑 (Workflow Paradigm Shift)在引入 SKILL 机制后，AI 的角色将经历一次根本性的蜕变：从单纯的、容易出错的“代码生成器 (Coder)”，转变为能够统筹全局的“资深生信分析架构师 (Bioinformatics Architect)”。这种转变的核心在于控制力的提升和知识的沉淀。过去，AI 每次都在“重新发明轮子”，而现在，它将像搭积木一样，调用经过人类专家验证的高质量模块。同时，为了保持科研探索的灵活性，系统将支持“实时代码生成”与“结构化 SKILL 调用”的双轨并行。1.1 全新的人机协作双轨工作流意图理解与规划 (Planning)：深度解析：当用户输入需求（如：“帮我做一组 RNA-seq 的差异分析并画火山图”）时，AI 首先对用户的意图进行语义拆解，识别出关键实体（如数据类型：RNA-seq，分析目标：差异分析、火山图）。能力匹配 (SKILL First)：AI 优先查阅当前系统注册的 SKILL 库，寻找能够匹配这些意图的工具。动态回退 (Fallback to Code)：如果当前 SKILL 库中没有合适的工具（例如一种非常新颖的统计算法），AI 会动态回退到“实时编写代码”的模式，作为临时解决方案（即 [Live_Coding] Meta-SKILL）。工具编排 (Orchestration)：构建执行图：假设 AI 发现系统中存在现成的 [DESeq2_Analysis] 和 [Volcano_Plot] 两个原子 SKILL。它将这些 SKILL 组合，生成一个包含前后依赖关系的有向无环图 (DAG)。例如，它知道 [Volcano_Plot] 必须在 [DESeq2_Analysis] 输出结果之后才能执行。参数装填 (Parameterization)：上下文感知感知：AI 充当“粘合剂”，从数据中心的上下文（如用户当前挂载的文件、历史对话记录）中智能检索出正确的输入文件路径，并自动将其映射填充到对应 SKILL 的输入参数槽 (slots) 中。对于缺失的可选参数，它会自动填充合理的生信默认值（如 p-value = 0.05）。沙箱执行 (Execution)：安全隔离：系统接收到 AI 提交的结构化执行请求后，按 DAG 顺序在安全的 Docker 沙箱中调度执行这些 SKILL 或实时生成的代码。这种基于模板的执行方式，极大降低了因 AI 幻觉生成的恶意代码破坏宿主机环境的风险。资产沉淀与解读 (Harvest & Interpret)：结果可视化：结果生成后，前端不再展示杂乱的终端日志或原始路径，而是渲染出优雅的树状资产卡片。知识固化 (Knowledge Capture)：如果本次分析使用了“实时编写代码”的模式，并且用户对结果满意，系统将提供一个“固化为 SKILL”的选项，将其一键转换为标准的 SKILL 包。专家解读：用户审阅结果后，点击“深度解读”，AI 基于生成的图表和数据（而不是执行代码的细节），提供专业视角的生物学意义挖掘。1.2 Nextflow 混合引擎的特殊定位生信分析的真正挑战往往在于处理海量数据（如成百上千个样本的 WGS 测序）。传统的 Python/R 脚本在面对这种规模时会显得捉襟见肘。因此，我们引入 Nextflow 作为处理长流程和重度计算的核心引擎。对于长流程的“混合 SKILL”，AI 可以调用一个特殊的 Meta-SKILL：[Nextflow_Generator]。逻辑到 DSL2 的转化：AI 将梳理好的业务逻辑步骤，精确转化为支持并行计算和断点续传的 Nextflow DSL2 脚本 (.nf)。原生集群支持：该脚本可以直接提交给后端的计算集群（如 Slurm, SGE）或直接在 Docker 环境中以 Nextflow 引擎原生运行。这极大地增强了系统的吞吐量、容错性（如内存不足自动重试）和资源利用率。从一次性到永久资产：经过用户实际运行验证无误的 .nf 脚本，可以通过一个简单的操作被“一键固化”。它将作为一种全新的、包含复杂多步逻辑的“复合 SKILL”重新注册到系统的 SKILL 库中，供日后重复调用，实现平台能力的自我进化。2. SKILL 规范与数据模型设计 (SKILL Specification)为了兼顾大模型的理解能力和人类开发者的编写体验，我们摒弃纯 JSON 的配置方式，转而采用**“Markdown 声明文档 + 脚本文件夹”**的包结构 (Bundle Structure)。这与当前主流的 AI 工具定义协议（如 MCP）理念一致。2.1 目录结构 (SKILL Bundle)一个标准的 SKILL 在物理存储上是一个文件夹，包含以下核心文件：skill_volcano_plot/
├── README.md          # 核心！使用自然语言编写的 SKILL 定义、参数说明和知识库
├── main.R             # 实际执行的脚本模板 (支持 Jinja2 语法)
├── requirements.txt   # (可选) Python 依赖
└── environment.yml    # (可选) Conda 环境配置
2.2 README.md 格式规范 (The Declaration Document)这是 AI 理解该 SKILL 的唯一入口。它必须遵循特定的 Markdown 格式（Frontmatter + 内容）：---
skill_id: "volcano_plot_001"
name: "标准差异基因火山图绘制"
version: "1.0.0"
author: "System"
executor_type: "R_script"
main_entry: "main.R"
---

## 1. 技能描述 (Description)
用于绘制差异基因表达的高分辨率火山图。支持自定义显著性阈值、折叠变化阈值以及输出颜色方案。适用于从 DESeq2 或 edgeR 等工具生成的标准化分析结果。

## 2. 输入参数 (Input Parameters)

系统调度时，必须严格按照以下字段提供参数：

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|---|---|---|---|---|
| `input_matrix` | string | 是 | | 包含差异分析结果的 CSV/TSV 文件物理路径，必须包含 `log2FoldChange` 和 `pvalue` 或 `padj` 列。 |
| `pvalue_threshold` | number | 否 | 0.05 | 显著性 p-value (或 padj) 的阈值，用于判定基因是否显著表达。 |
| `lfc_threshold` | number | 否 | 1.0 | Log2 Fold Change (折叠变化) 的绝对值阈值。 |
| `color_scheme` | string | 否 | "red_blue" | 火山图的上调/下调基因配色方案。可选值: `red_blue`, `viridis`, `custom`。 |

## 3. 输出规范 (Expected Outputs)
执行完毕后，该技能将在指定的输出目录 (`TASK_OUT_DIR`) 中生成以下文件：
- `volcano_plot.png`: 高分辨率的火山图图片。
- `significant_genes_filtered.csv`: 过滤后的显著差异基因表格。

## 4. 专家知识库 (Knowledge Base / Context)
*提示给 AI 的额外信息，帮助其更好地决定何时调用或如何解读结果。*
- 当用户询问“哪些基因上调最明显”时，建议调用此工具。
- 在解读火山图时，通常横坐标代表倍数变化 (Log2FC)，纵坐标代表显著性 (-Log10 P-value)。右上角和左上角的点是生物学意义最重大的基因。
这种格式对开发者极度友好，同时，后端在加载 SKILL 时，可以轻松地将 Frontmatter 和 Markdown 表格解析为符合 OpenAI/Claude 规范的 JSON Schema 注入给大模型。2.3 特殊的 Meta-SKILL: [Live_Coding]为了保留系统的灵活性，系统内置一个特殊的 Meta-SKILL。当 AI 判定现有 SKILL 库无法满足需求时，它将调用 [Live_Coding]。定义：一个允许 AI 实时生成并执行 Python/R/Bash 脚本的沙箱通道。参数：包含 language (语言类型) 和 source_code (AI 实时生成的源码)。界面体现：前端会明确提示用户，当前正在使用“实时生成代码”模式，提示其潜在的风险，并提供代码审查界面。3. 系统接口定义 (System Interfaces)要支撑上述强大的逻辑流，后端 FastAPI 服务需要进行架构扩充，新增一个围绕 /api/skills 域的完整路由集。GET /api/skills:扫描后端的 SKILL 目录，解析所有 README.md，返回当前上下文中用户可用的所有 SKILL 列表及其结构化信息。在每一次用户发起对话前，系统会将这些信息动态注入到 LLM 的系统提示词 (System Prompt) 中。POST /api/skills/build_from_code:实现“知识固化”。接收一次成功的 [Live_Coding] 任务的 ID，系统自动提取其中的代码，利用 AI 辅助生成对应的 README.md (包括参数推断和描述)，并打包为一个新的 SKILL Bundle 持久化到服务器。POST /api/tasks/execute_skill:这是对现有任务调度接口的重大改造。接口接收结构化请求：{ "skill_id": "volcano_plot_001", "params": { "input_matrix": "/path/...", ... } }。后端根据 skill_id 找到对应的 Bundle，读取 main.R 模板，使用模板引擎 (如 Jinja2) 注入参数，最后丢给 Celery Worker 在 Docker 沙箱中执行。(注：若是 [Live_Coding] 调用，则直接执行传入的源码)。POST /api/skills/generate_nextflow:专属的 Nextflow 代码转换微服务接口。接收由 AI 生成的高层级流程逻辑描述，结合目标计算环境，返回语法正确的 Nextflow DSL2 代码，极大地降低了用户编写 Nextflow 脚本的门槛。4. 全局演进路线与升级计划 (Roadmap & Implementation Plan)考虑到将一个基于“实时代码”的平台重构为一个双轨并行的“SKILL 调度引擎”是一项系统级工程，为了在不破坏当前平台核心功能稳定性的前提下平滑过渡，建议将其拆分为四个迭代阶段（Sprint）进行：Sprint 1：底层基建重塑与 Bundle 解析器 (Foundation)这是整个大厦的地基。文件系统与解析器：在后端建立 /app/skills/ 物理目录结构。编写 Python 解析器，能够读取 SKILL Bundle 中的 README.md，将其提取为供程序内部使用的字典/对象。执行引擎改造：增强 Celery Worker 的能力。保留现有的代码直执模式 (作为 [Live_Coding] 的底座)，新增 execute_bundle 模式。该模式会读取 Bundle 中的执行模板并安全注入参数。API 与冷启动：实现基础的 SKILL 解析与列表获取 API。手动编写 2-3 个最成熟的生信 SKILL Bundle（如差异分析、PCA 绘图）放入目录作为种子。Sprint 2：大模型工具链深度对接与双轨协同 (LLM Tool Calling)赋予 AI 使用这些工具的能力，并实现智能路由。大脑升级交互：将后端系统与 OpenAI 或 Claude 原生的 function_calling 或 tools API 规范深度对接。将解析后的 SKILL 列表注册为可用工具。系统 Prompt 重塑：重写 Agent 的 System Prompt，强化其规划者角色：“你现在拥有一个技能库。请绝对优先使用注册的工具调用现成模块；只有在确实缺乏合适 SKILL 时，才调用 [Live_Coding] 工具自行编写代码。”前端交互闭环：在前端的“策略执行卡片”中，清晰地展示 AI 当前的选择：是调用了内置的 [Volcano_Plot]（展示参数），还是触发了 [Live_Coding]（展示生成的源码）。Sprint 3：知识固化与 Nextflow 引入 (Knowledge & Scale)打通资产积累和大规模计算的路径。一键固化功能：在 [Live_Coding] 执行成功的历史记录处，提供“保存为新 SKILL”的按钮。调用 /api/skills/build_from_code，利用 AI 自动生成配套的 README.md，沉淀为新的 Bundle。Nextflow 生成器：构建特定 Agent，专门负责将结构化的分析步骤翻译为地道的 Nextflow DSL2 脚本。环境准备：在后端的任务执行节点或 Docker 基础镜像中安装并配置 Nextflow 运行时环境，使平台具备执行复杂流程的能力。Sprint 4：前端 SKILL 专属工作台 (Skill Studio UI)降低使用门槛，提升产品商业化属性。独立模块：在前端左侧边栏增加一个全新的模块【技能中心 (Skill Studio)】。探索与发现：用户可以在这里浏览、搜索可用的官方和自定义 SKILL，系统解析 README.md 并在前端渲染出美观的文档说明。图形化执行 (GUI Mode)：支持系统根据解析出的参数表格，自动生成图形化表单（Web Forms）。这极大降低了小白用户的使用门槛，他们无需通过聊天界面，就能直接填表、提交任务。
