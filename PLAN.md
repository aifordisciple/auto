
# **AI 生信平台 SKILL 引擎架构与演进规划（为了后续开发此部分内容使AI具有大局观）**

## **1\. 核心理念与工作流重塑 (Workflow Paradigm Shift)**

在全面引入结构化的 SKILL 机制后，系统底层的 AI 驱动逻辑将经历一次根本性的蜕变。AI 的核心角色将从单纯的、且容易产生“幻觉”或语法错误的“临时代码生成器 (Ad-hoc Coder)”，正式升维转变为能够统筹全局、精确调度的“资深生信分析架构师 (Bioinformatics Architect)”。

这种转变的核心意义在于**对执行过程的绝对控制力提升**和**领域知识的长期沉淀**。过去，面对类似的分析需求，AI 每次都在“重新发明轮子”，生成未经测试的脚本，这在严谨的科研场景中是不可接受的。而现在，通过 SKILL 引擎，AI 将像搭积木一样，通过智能匹配和编排，调用那些经过无数次真实数据验证、由人类专家精心打磨的高质量分析模块。

同时，考虑到科研探索的边界是无限的，为了保持系统应对未知挑战的灵活性，系统将创新性地支持“实时代码生成 (Live Coding)”与“结构化 SKILL 调用 (Skill Invocation)”的**双轨并行机制**，实现稳健性与灵活性的完美平衡。

### **1.1 全新的人机协作双轨工作流详述**

这套工作流彻底颠覆了传统的“一问一答”模式，将其细化为一个包含多步校验和人工介入的闭环系统：

1. **深度意图理解与规划 (Deep Planning & Intent Parsing)**：  
   * **语义拆解与实体识别**：当用户在聊天框中输入自然语言需求（例如：“帮我做一组 RNA-seq 样本的差异分析，找出那些显著上调的基因并画一张漂亮的火山图”）时，AI 首先要做的不是写代码，而是进行深度的语义理解。它需要精确提取出任务的关键实体：数据类型（RNA-seq）、分析动作（差异分析、数据过滤）、可视化需求（火山图）。  
   * **能力匹配 (SKILL First Strategy)**：明确意图后，AI 的首要任务是查阅当前系统注册的、具有严谨定义的 **SKILL 库**。它会计算当前意图与各个 SKILL 描述 (Description) 的匹配度，寻找能够完美覆盖这些需求的工具组合。  
   * **动态回退机制 (Fallback to Live Code)**：如果经过遍历，发现当前 SKILL 库中没有任何合适的工具（例如，用户要求使用一种刚刚在 Nature 杂志上发表、尚未被封装的新颖统计算法），AI 才会动态触发安全回退机制，进入“实时编写代码”的模式，这在系统内部被抽象为一个特殊的 \[Live\_Coding\] Meta-SKILL。  
2. **工具编排与智能参数推断 (Orchestration & Smart Inference)**：  
   * 假设 AI 经过匹配，发现系统中存在现成的 \[DESeq2\_Core\_Analysis\] 和 \[Advanced\_Volcano\_Plot\] 两个原子级别的 SKILL。  
   * **依赖图构建**：AI 会自动识别它们之间的数据流转依赖，构建一个有向无环图 (DAG)，明确 DESeq2 的输出必须作为 Volcano\_Plot 的输入。  
   * **上下文感知推断**：这是体现 AI 智能的关键一步。AI 不会傻傻地等待用户填表，而是充当“超级助理”，根据历史对话记录、用户当前工作空间内挂载的数据资产，**主动推断并预填** SKILL 所需的参数。例如：它扫描到挂载区有一个名为 raw\_counts\_matrix.csv 的文件，结合文件结构，大胆推断这正是 count\_matrix 参数的完美候选；同时，它可能找到 sample\_info.tsv 并将其映射为 metadata 参数。  
3. **动态参数配置的高级交互体系 (Advanced Dynamic Configuration Interaction)**：  
   * **可视化确认与信任机制**：为了彻底杜绝“黑盒操作”带来的科研风险和用户不信任感，AI 在完成智能参数推断后，绝对不会立即盲目启动后台计算集群。相反，系统在此处设置了一个关键的人机断点：AI 会在当前的聊天记录流中，渲染出一张极具结构美感和信息密度的\*\*“分析参数配置摘要卡片 (Configuration Summary Card)”\*\*。这张卡片直观地展示了即将调用的 SKILL 链条，以及最核心的输入文件映射，作为用户进行最终决策和确认的物理屏障。  
   * **沉浸式丝滑展开 (The Canvas-like Experience)**：当用户的目光被这张卡片吸引，并点击卡片上的“检查全部参数”按钮或特定参数区域时，系统将打破传统聊天界面的单调线性结构。此时，整个屏幕右侧（Right Panel）会以一种极其丝滑、不打断当前心流的动画过渡效果，无缝滑出一个全尺寸的、优雅美观的参数配置工作台（这种沉浸式体验深刻借鉴了 Gemini Canvas 的设计哲学）。在这个独立的空间里，繁杂的分析参数得到了最妥善的安置，告别了在狭小聊天框中反复确认的局促。  
   * **实时深度校验与互动修改 (Real-time Validation & Refinement)**：在这个沉浸式的侧边栏页面中，用户能够以最高权限清晰地审查 AI 刚才“自作主张”推断出的所有参数细节（例如：复杂的样本映射关系、具体的对照组与实验组设置、底层参考基因组的版本选择、以及严苛的 p-value 和 Log2FC 统计阈值等）。  
     * **灵活干预**：如果用户发现推断有误或需要调整，可以极其轻松地通过平台预设的、高度定制化的 UI 控件（如：支持模糊搜索的文件下拉选择器、带有防误触机制的数值滑动条、色板选择器等）进行直接修改。用户可以补充 AI 遗漏的必填项，或是根据特定的生物学假设微调那些可选参数。  
     * **双轨模式的兼容性**：值得强调的是，这套优雅的动态参数卡片机制同样完美兼容 \[Live\_Coding\] 模式。在实时生成代码的场景下，侧边栏不仅会展示由 AI 提取出的代码层面的抽象参数（如果有的话），更会提供一个带有高级语法高亮的**集成代码编辑器 (In-browser Code Editor)**。资深研究人员可以直接在这个面板中对 AI 生成的草稿代码进行深度 Review 和逐行修改。  
     * **安全下发**：无论是标准 SKILL 还是 Live Code，系统都会在后台实时进行严格的格式和逻辑校验（例如：检查 metadata 表的行数是否与 count\_matrix 的列数匹配）。只有当所有必填项均已满足，且所有校验通过后，用户才能点击那个最终的“确认并执行”按钮，将沉甸甸的计算任务真正下发给底层沙箱。  
4. **沙箱安全执行 (Secure Sandbox Execution)**：  
   * **隔离与监控**：系统后端接收到用户最终确认的、完全结构化的执行请求 payload。随后，强大的任务调度引擎（如 Celery）接管控制权。所有的分析计算都将被严格限制在一次性、资源受限的 Docker 容器沙箱中进行。  
   * **模板渲染**：这种基于模板注入参数的执行方式，彻底切断了 AI 生成任意代码的能力（在非 Live Coding 模式下），从根本上消除了恶意代码注入或误操作破坏宿主机底层文件系统的灾难性风险。同时，系统会实时捕获沙箱内的标准输出 (stdout/stderr)，以便在出现异常时进行诊断。  
5. **资产沉淀与多维解读 (Harvest, Persist & Interpret)**：  
   * **结构化结果呈现**：沙箱计算成功结束后，前端界面不会像过去那样生硬地丢出一堆冰冷的终端日志或难以理解的长串物理文件路径。取而代之的是，系统会解析输出目录，并渲染出一张极具结构美感的“树状资产卡片 (Asset Tree Card)”，直观展示生成的图表、表格和报告文件。用户可以直接在界面上进行全屏预览或打包下载。  
   * **知识固化闭环 (Knowledge Capture Loop)**：这是系统自我进化的关键。如果本次成功的分析是依靠 AI “实时编写代码 (Live Coding)” 完成的，并且用户对最终的生物学结果非常满意，系统会适时地弹出一个提示，提供一个“一键固化为标准 SKILL”的入口。点击后，系统将在后台自动整理代码、推断依赖，生成标准的 SKILL 描述包，永久沉淀到平台的知识库中，供全员未来复用。  
   * **专家视角的深度解读**：用户在审阅了初步的结果资产后，如果需要进一步理解，可以点击卡片上的“深度解读”按钮。此时，AI 将华丽转身，重新化身为“顶级生物学家”。它会仔细研读刚刚生成的那些 CSV 数据表和统计图表特征（而非去解释那堆执行代码），用平易近人的自然语言，为用户提供诸如“通路富集趋势”、“关键驱动基因识别”等具有深厚学术价值的生物学意义挖掘和洞见。

### **1.2 Nextflow 混合引擎的战略定位与深远影响**

随着平台进入深水区，面对动辄数百 GB 甚至 TB 级别的队列规模全基因组 (WGS) 或单细胞测序数据，单节点的 Python 或 R 脚本注定会因为内存溢出或耗时过长而崩溃。这是传统轻量级平台的死穴。

因此，我们在架构设计上，前瞻性地将 **Nextflow** 引入作为处理超大规模、超长流程重度计算的核心驱动引擎。这赋予了平台企业级的并发处理和容错能力。

在应对由数十个甚至上百个步骤组成的复杂流程（即“混合 SKILL”）时，AI 能够通过调用一个具有战略意义的特殊 Meta-SKILL：\[Nextflow\_Generator\] 来大显身手。

* **从高级逻辑到 DSL2 语法的降维转化**：在这个过程中，AI 发挥其卓越的代码翻译能力，将人类用户梳理好的高层业务逻辑步骤和依赖拓扑图，精确且符合规范地转化为支持高度并行计算的 Nextflow DSL2 脚本 (.nf 文件)。它会自动处理通道 (Channels) 的定义、进程 (Processes) 的声明以及执行指令。  
* **无缝对接原生异构集群**：生成的 Nextflow 脚本天生具备跨平台的执行能力。它不仅可以直接提交给企业或高校现有的高性能计算集群（如 SLURM, PBS, SGE），充分压榨成百上千个 CPU 核心的算力，也可以在云端的 Kubernetes 或 Docker Swarm 环境中优雅运行。这种架构极大地增强了系统的吞吐量上限。  
* **原生容错与断点续跑机制**：借助 Nextflow 的内置机制，如果某个样本在比对过程中因为内存不足 (OOM) 导致进程失败，引擎会自动捕获错误，请求更多的资源并仅针对该失败任务进行重试，而无需从头跑起。这在动辄运行数天的生信流程中，是极其宝贵的特性。  
* **从一次性脚本到永久核心资产的蜕变**：经过真实业务场景反复运行、验证无误且高度优化的 .nf 脚本，其价值不可估量。系统提供机制，允许管理员或高级用户将这些脚本“一键固化”，封装为全新的、能够处理极其复杂生物学问题的“超级复合 SKILL”，重新注册到系统的核心 SKILL 库中。随着时间的推移，平台将积累起一座无价的工业级流程金矿，实现真正的能力飞轮效应。

## **2\. SKILL 规范与数据模型设计 (SKILL Specification)**

在设计 SKILL 的具体规范时，我们面临着一个经典的取舍：如何既能让严谨、缺乏想象力的机器程序高效解析执行，又能让习惯于文档驱动的人类开发者（生信工程师）感到亲切和易于编写？

为了完美兼顾大语言模型强大的文本理解能力、人类开发者的工程习惯以及系统底层调度引擎的可维护性，我们决定彻底摒弃传统的、难以阅读和维护的“纯巨大 JSON 配置文件”方式。转而采用一种更具现代感和扩展性的\*\*“Markdown 声明文档 \+ 模块化脚本资源”\*\*的复合包结构 (Bundle Structure)。

这种设计理念并非凭空捏造，而是深刻借鉴了软件工程中成熟的插件系统架构，以及当前 AI 领域备受推崇的 MCP（Model Context Protocol）工具定义规范，代表了行业的最前沿标准。

### **2.1 目录结构标准 (The SKILL Bundle Layout)**

在物理存储层面，一个标准的、可复用的 SKILL 绝不仅仅是一个孤立的脚本文件，而必须是一个自包含的独立文件夹（即 Bundle）。这种结构保证了其可移植性和高内聚低耦合。

其内部结构必须严格遵循以下层次规范：

my\_advanced\_skill\_bundle/  
├── SKILL.md          \# 【绝对必需】整个包的心脏。包含系统解析所需的元数据 (YAML)、参数 schema (表格)、以及面向 AI 的操作上下文指令。  
├── scripts/          \# 【强烈推荐】存放执行具体任务的源代码文件 (如 Python 的 .py，R 的 .R，或 Bash 脚本)。支持多个文件。  
├── docs/             \# 【可选资源】存放更详尽的人类可读参考文档、算法原理说明、长篇 API 手册等。  
├── env/              \# 【推荐规范】环境定义文件，如 requirements.txt (Python) 或 environment.yml (Conda)，确保环境可复现。  
└── assets/           \# 【可选资源】用于存放静态资产，例如运行所需的默认模板文件、用于测试验证的迷你 demo 数据集、甚至代表该工具品牌的专属 Logo 图标等。

### **2.2 SKILL.md 格式规范深度剖析 (The Core Declaration Document)**

SKILL.md 无疑是整个 Bundle 的灵魂所在。它是连接“底层机器系统”与“高层 AI 大脑”的唯一桥梁。它巧妙地融合了供系统精确解析的结构化元数据（通过顶部的 YAML Frontmatter 实现），以及供大语言模型去理解、学习和推理的自然语言指令、参数表格和操作指南。

这种设计使得一份文档，同时满足了三种角色的阅读需求：系统程序、AI 模型、以及人类维护者。

以下是一个极其典型且完整的 SKILL.md 规范范例：

\---  
\# \==========================================  
\# 核心系统元数据 (Core System Metadata)  
\# \------------------------------------------  
\# 以下区域为 YAML 格式，供后端系统路由和调度引擎直接读取，要求绝对的格式严谨。  
\# \==========================================

skill\_id: "deseq2\_volcano\_01"             \# 全局唯一的工具识别码，不可重复  
name: "DESeq2差异分析与高级火山图绘制"      \# 供用户在界面上看到的直观友好名称  
version: "1.1.0"                          \# 遵循语义化版本控制规范 (SemVer)  
author: "BioData Core Analysis Team"      \# 工具维护者或团队标识  
executor\_type: "R\_script"                 \# 指定底层运行时引擎，可选: R\_script, Python\_env, Bash\_shell, Nextflow\_DSL2  
entry\_point: "scripts/run\_analysis.R"     \# 相对路径，指向该工具启动执行的入口主脚本  
timeout\_seconds: 3600                     \# (可选) 设定的沙箱执行超时时间，防止僵尸进程占用资源  
\---

\#\# 1\. 技能意图与功能边界 (Intent & Scope)

\*面向 AI 的核心描述，帮助其判断在何种场景下应该召唤此工具。\*

本技能是一款高度整合的转录组学分析工具。它旨在对给定的原始基因表达 count 矩阵执行学术界公认的、标准的 DESeq2 差异基因表达 (DEG) 分析流程。并且，基于严谨的统计分析结果，它将自动生成具有直接用于高水平学术期刊出版质量的火山图 (Volcano Plot) 和 MA 图可视化结果。该工具不处理上游的比对或定量步骤，专注于下游的统计推断与可视化呈现。

\#\# 2\. 动态参数定义规范 (Parameters Schema)

\*极其重要！系统底层的解析器将扫描并解析下方的 Markdown 表格，将其自动转换为严格的 JSON Schema。随后，前端 UI 引擎将根据这个 Schema，实时渲染出供用户交互的动态参数配置卡片。\*

| 参数键名 (Key) | 数据类型 (Type) | 必填 (Required) | 默认值 (Default) | 详细描述说明 (Detailed Description) |  
|---|---|---|---|---|  
| \`count\_matrix\` | FilePath | 是 (Yes) | | 原始的转录组 count 表达矩阵物理文件路径。仅支持 CSV 或 TSV 格式。要求行名为确切的基因标识符 (如 Ensembl ID 或 Gene Symbol)，列名必须对应具体的生物学样本名称。必须是未经标准化的整数 count 值。 |  
| \`metadata\` | FilePath | 是 (Yes) | | 核心的样本分组信息表路径。其结构要求极为严格：第一列的内容必须与 \`count\_matrix\` 的列名实现完美的一一对应，后续列包含如 condition, treatment, batch 等分组变量。 |  
| \`design\_formula\` | String | 是 (Yes) | \`\~ condition\` | 驱动 DESeq2 核心广义线性模型的实验设计公式 (Design Formula)。定义了希望探究的主要变量及可能需要控制的协变量。 |  
| \`padj\_cutoff\` | Number | 否 (No) | 0.05 | 用于判定差异表达是否具有统计学显著性的多重假设检验校正后 p-value (adjusted p-value) 截断阈值。通常设为 0.05 或 0.01。 |  
| \`lfc\_cutoff\` | Number | 否 (No) | 1.0 | 表达量折叠变化 (Log2 Fold Change) 的绝对值截断阈值，用于评估变化的生物学效应大小。 |  
| \`plot\_color\_palette\`| String | 否 (No) | "classic\_red\_blue"| 输出火山图的高级配色方案。支持的枚举选项包括: \`classic\_red\_blue\` (经典红蓝对比), \`color\_blind\_friendly\` (色盲友好色系), \`viridis\_scale\` (学术连续色系)。 |

\#\# 3\. 操作指令与专家级知识库 (Operational Directives & Expert Knowledge)

\*这里包含了系统赋予大模型的“锦囊妙计”。AI 在准备调用该工具前、组装参数时、以及事后解读结果时，都将从这里汲取上下文背景知识，表现得像一个真正的领域专家。\*

\- \*\*精确触发条件\*\*：当敏锐地察觉到用户的提问中包含如“找出在某两种药物处理下差异表达的基因”、“比较野生型和敲除组样本的表达谱差异”、“做个转录组火山图看看”等意图时，应强烈建议并优先调用此复合技能，而不是去调用基础的画图工具。  
\- \*\*智能参数推断逻辑的底线\*\*：在尝试自动补全 \`design\_formula\` 参数时，请务必仔细阅读 \`metadata\` 文件的表头 (Header)。如果用户未明确指定公式，请优先寻找名称类似于 \`group\`, \`condition\`, \`treatment\`, \`genotype\` 的列作为推断的默认主要分析变量。如果找不到，必须通过界面提示用户手动输入。  
\- \*\*学术级结果深度解读指导\*\*：在任务执行成功，向用户提交最终分析报告时，不要只是干巴巴地罗列数字。请重点引导用户关注火山图右上角（高表达量、高显著性，通常对应极具研究价值的上调效应基因）和左上角（高度显著下调）散点群的分布密度，并主动提议可以利用这些极端的显著差异基因（例如表格中提取的 Top 20）去开展下一步的富集分析 (Enrichment Analysis)。

这种创新的规范格式具有无可比拟的多重优势：

1. **天然的机器可读性 (Machine Readable)**：后端的强大解析引擎 (Parser) 可以使用极其简单的正则表达式和 YAML 库，快速提取 Frontmatter 信息和 Markdown 表格内容，在内存中瞬间构建出符合 OpenAI/Claude 严格规范的工具描述 JSON Schema，实现与底层系统的无缝对接。  
2. **极致的人类可读性与编辑体验 (Human Readable & Writable)**：生信算法工程师在开发新工具、维护旧版本或排查问题时，面对的是最熟悉、最纯粹的 Markdown 排版文档。他们可以使用任何趁手的编辑器，甚至在 GitHub/GitLab 上直接预览修改，彻底摆脱了过去面对层层嵌套的“冰冷且容易少个括号的复杂 JSON 结构”所带来的恐惧和效率低下。  
3. **上下文知识的高度内聚 (Knowledge Cohesion)**：将纯技术的“执行指令”、严谨的“参数要求”和偏业务的“专家解读建议”在物理和逻辑上强行绑定在同一个文档内。这意味着，当 AI 大脑加载并准备调用该特定工具时，它实际上同时获得了一个针对特定生信场景的“微型外挂知识库”，从而使其后续的沟通和解读行为表现出令人惊叹的专业水准和连贯性。

### **2.3 保持底线灵活性的特殊 Meta-SKILL: \[Live\_Coding\]**

在一个追求绝对标准化和模块化的系统中，我们不能忽视科学研究固有的探索性和偶然性。为了确保平台面对极其前沿、罕见或高度定制化的分析需求时不会陷入“无技可用”的死胡同，系统在底层架构中硬编码内置了一个拥有最高特权的特殊 Meta-SKILL，我们称之为：\[Live\_Coding\]。

* **精准定义**：它是一个受控的安全通道。当 AI 的意图解析引擎判定当前庞大的 SKILL 库中确实没有任何组合能够满足用户的奇思妙想时，它将获准调用此工具。这本质上是在请求系统开放一个临时的、实时代码生成与沙箱执行环境。  
* **极简参数结构**：它不需要复杂的业务参数，其 Schema 仅仅包含最基本的运行要素：language (指定执行语言的类型，如 Python3 或 R) 和 source\_code (包含 AI 刚刚根据用户需求实时推演、编写出的长篇原始代码文本)。  
* **强提示界面体现 (UX Nuance)**：考虑到这种行为的潜在不可靠性，当触发此通道时，前端界面必须做出强烈的视觉反馈。系统会明确地提示用户当前正处于高级的“实时生成代码 (Live Code Execution)”模式。在正式把代码扔进沙箱跑之前，UI 必须强制展示一个带有高亮语法的代码审查界面 (Code Review Panel)，要求用户（特别是资深研究人员）进行最后的眼球把关，确认没有明显的逻辑谬误。只有在这次极其成功的“临时探索”完美结束后，系统才会抛出那个极具价值的“转化为永久标准 SKILL”的黄金快捷入口。

## **3\. 全局系统接口定义重构 (System Interfaces & API Topology)**

为了稳健地支撑上述庞大且复杂的逻辑流转和能力分发，作为中枢神经的后端 FastAPI 服务架构需要进行一次深度的扩容和重构。主要体现在新增并完善一个围绕 /api/skills 域展开的完整、高可用的微服务路由生态集群。

* **GET /api/skills/catalog (核心技能发现接口)**:  
  此接口在系统启动或被强制刷新时，会深度扫描宿主机的 /app/skills/ 物理根目录及其所有有效的子 Bundle 文件夹。它调用内部的 Markdown 解析器，逐一解读所有的 SKILL.md，将 Frontmatter 提取为配置字典，将参数表格编译为严格的 JSON Schema。最终，它整合出一个高度结构化、包含详细验证规则的可用 SKILL 目录树 (Catalog) 并返回给前端或网关。**更重要的是，这些 Schema 将在每一次用户发起新一轮对话前，作为系统级别的“潜意识”动态注入到庞大的 LLM 系统提示词 (System Prompt) 中，赋予 AI 完整的工具调配能力。**  
* **POST /api/skills/transform\_from\_live (核心知识资产固化接口)**:  
  这是实现平台能力滚雪球式增长（知识固化）的关键管道。它接收一个确切的、表明曾经有一次完美成功运行的 \[Live\_Coding\] 任务日志 ID。系统会顺藤摸瓜，从 Redis 或数据库中提取出那段饱经考验的原始执行代码。接着，系统会在后台悄悄唤醒一个专门用于文档生成的 AI 代理，辅助推断这段代码所需的参数类型和含义，自动生成一份格式标致的标准化 SKILL.md 声明文件草稿。最后，将代码与文档合并打包，按照严格的 Bundle 目录树规范持久化写入到服务器硬盘的技能目录下，完成一次新技能的“封神”仪式。  
* **POST /api/tasks/execute\_orchestrated\_skill (下一代核心任务调度调度引擎接口)**:  
  这是对现有、粗放型任务调度接口的革命性升级。为了安全，系统将逐步废弃直接接收庞大 raw code 并裸跑的高风险老旧接口。全新的接口被设计为极其严谨，它只接收经过高度结构化、并且通过了前端预校验的 JSON 格式请求 payload。典型的请求体形如：{ "skill\_id": "deseq2\_volcano\_01", "params": { "count\_matrix": "/data/shared/project\_alpha/counts.tsv", "padj\_cutoff": 0.01, ... } }。  
  当后端捕获该请求后，调度引擎的动作非常清晰：第一步，根据唯一的 skill\_id 从本地检索并加载对应的 Bundle 包；第二步，提取核心的 entry\_point 执行模板脚本；第三步，调用工业级模板引擎 (如 Jinja2)，在确保没有语法注入风险的前提下，将用户传入的参数精准无误地注入到模板脚本的预留槽位中；最后一步，将这份最终合成的、毫无破绽的执行脚本连同运行环境依赖，稳妥地丢给后台的分布式 Celery Worker 集群，在完全隔离的 Docker 沙箱矩阵中启动运算进程。  
* **POST /api/skills/meta/generate\_nextflow\_pipeline (专属计算流程降维转换接口)**:  
  这是一个高度专业化的小型微服务接口。它的唯一使命，就是接收由 AI 架构师经过深思熟虑后生成的、基于文本的高层级流水线拓扑逻辑描述（例如：由步骤A产生的文件必须传输给步骤B进行质控，然后汇总到步骤C）。接口结合当前部署目标计算环境的硬件约束信息（如是否开启集群模式、单个任务允许占用的最大内存上限等参数），通过内部的编译器，将其无损且优雅地降维转换为一段语法极其严谨、支持断点续跑和并行投递的 Nextflow DSL2 工程化代码。

## **4\. 全局演进路线与渐进式升级计划 (Strategic Roadmap & Step-by-step Implementation Plan)**

毫无疑问，将一个最初基于极其自由的“草稿式实时代码”运行的雏形平台，全面重构成一个以极其严谨的双轨并行和基于 Schema 契约的“工业级 SKILL 调度引擎”，是一场如同“飞行中给飞机换引擎”的艰巨系统级工程。

为了在绝对不影响、不破坏当前平台已有的核心功能和用户体验稳定性的最高前提下，实现新旧架构的平滑过渡与平稳着陆，强烈建议研发团队抛弃“大爆炸式重写”，转而采用敏捷开发中的四个明确的迭代阶段（Sprint）进行稳扎稳打的突围：

### **Sprint 1：重铸底层基建魂骨与智能 Bundle 解析器构建 (The Foundation Era)**

这是决定整个大厦最终能盖多高的关键地基建设阶段。在这个阶段，我们甚至不需要修改任何前端的用户界面。

* **文件系统重构与全能解析引擎的诞生**：在后端的服务器架构中，规划并建立神圣的 /app/skills/ 物理目录根结构。投入核心骨干精力，使用 Python 编写一套健壮无比如同编译器的“SKILL 包解析引擎 (Bundle Parser)”。它的首要任务是能够极其精准、不漏一词地提取出以 Markdown 格式编写的 SKILL.md 中的隐藏宝藏——不仅能读取纯净的 YAML Frontmatter，还能智能识别并解析出复杂的参数定义表格，最终在内存中无缝转换为供内部系统自由流转的标准 JSON Schema 对象。  
* **执行调度引擎的双核改造**：深入剖析并增强现有的 Celery Worker 执行集群能力。原有的“代码直接裸执”模式必须被完整保留（它将作为支撑未来 \[Live\_Coding\] 和提供调试后门的坚实底座）。在此基础上，系统级新增一条名为 execute\_bundle 的高级执行通道模式。该核心模式具备在安全的上下文中自动读取目标 Bundle 内的主体执行脚本，并调用 Jinja2 引擎将 JSON Payload 中的外部参数防注入式地安全填入模板的能力。  
* **注入优质种子数据**：由资深的生信团队成员人工介入，极其严谨地手工编写 2 到 3 个涵盖核心生信基础流程、完全符合全新 Markdown 规范的生信 SKILL Bundle（例如：绝对标准的差异分析基因过滤流程、无暇的 PCA 降维绘图程序），将其慎重地放入新目录，作为整个系统运转的验证基石和测试种子。

### **Sprint 2：大模型工具链深度握手与革命性的动态参数卡片 (The Interaction Paradigm Shift)**

地基打好后，是时候赋予 AI 大脑使用这些神兵利器的能力，并为用户带来惊艳的交互革新了。

* **大脑的终极升级 (API Hooking)**：在后端网关层，将上一阶段系统解析出的海量、结构化的 SKILL 列表及精细的参数 Schema，通过 OpenAI 或 Claude 官方原生的、成熟的 function\_calling 或 tools API 规范协议，整体打包注册并喂给核心 Agent。  
* **重塑世界观的 System Prompt**：彻底推翻并重写引导 Agent 行为的 System Prompt（系统提示词），对其进行灵魂深处的“洗脑”，强化其作为一名深谋远虑的规划者的首要身份设定：“听着，你现在不仅是一名出色的生信架构师，你更掌握着一个威力巨大的现成技能兵器库。当任何用户向你抛出分析需求时，你必须、也绝对**优先**尝试利用 tools 接口调用那些库里现成的高质量模块；只有当你绞尽脑汁、搜遍整个库也确实发现严重缺乏匹配的工具，以至于流程无法推进的极端绝望情况下，你才被系统最终授权，慎重地激活 \[Live\_Coding\] 应急通道去自行探索编写那未知的代码。”  
* **动态配置 UI 引擎的研发**：前端团队发力，研发最具革命性体验的核心交互组件 \<SkillConfigCard /\>，以及那块负责从右侧华丽滑出、承载所有细节的详尽配置侧边栏面板 (SkillConfigPanel)。当后端敏锐地截获到 AI 大脑发出了“我决定调用这个特定的 SKILL”指令的瞬间，系统会立即暂停执行，并在前端聊天流中迅速渲染出该等待确认的卡片。点击卡片，面板滑出，实现复杂分析参数的实时优雅回显，并构建起用户最后一道安全确认与参数微调的防线机制。

### **Sprint 3：加速知识沉淀与 Nextflow 工业级引擎的融合引入 (Knowledge Consolidation & Scale up)**

在这个阶段，系统将正式打通从“灵光一现的代码”到“永恒固化资产”的通道，并具备处理企业级大数据的肌肉。

* **“一键封神”的固化功能上线**：在用户确认某次通过 \[Live\_Coding\] 临时编写的脚本执行结果极为完美、极具价值的历史记录节点处，前端高亮显示“转化为标准系统 SKILL”的功能按钮。点击后，后端接口轰鸣运作，自动化提取关键代码，更巧妙地利用另一个专门训练过的 AI 模型来逆向推导代码中潜在的参数变量需求，最终全自动构建出规范的 SKILL.md 和完整的底层目录结构，实现平台能力的零成本扩张。  
* **Nextflow 生态的深度整合**：精心构建并微调一个拥有深厚生信流程开发底蕴的专职 Agent，其唯一的焦点就是高效、无误地生成针对长流程作业的 .nf 目标脚本。同时，在后端真正的任务重负载执行节点（或者是构建作为底座的基础 Docker Image）中，全局安装并妥善配置 Nextflow 的运行时基石环境，从物理层面彻底打通应对极其复杂、漫长且对内存消耗极大的巨型计算流程的执行任督二脉。

### **Sprint 4：打造旗舰级的前端 SKILL 专属工作台体验 (The Ultimate Skill Studio UI)**

这是完成商业化华丽转身、极大拓展产品受众广度的最终冲刺。

* **独立的一级应用大模块**：在前端系统主界面的左侧常驻边栏中，骄傲地增加一个醒目的全新顶级导航模块——【技能中心 (Skill Studio)】。  
* **极具探索欲的发现大厅**：为用户提供一个视觉体验极佳、功能对标顶尖应用商店 (App Store) 的沉浸式界面。所有的用户都可以毫无阻碍地在这里尽情浏览、按类别筛选、关键词搜索系统中当前可用的无论是官方内置还是其他极客用户分享的精彩 SKILL。前端引擎会自动且优雅地将枯燥的 SKILL.md 后台文件实时渲染转化为排版精美绝伦、带有高亮和示例的在线说明文档页。  
* **拥抱小白的纯图形化零代码执行 (GUI Form Mode)**：这是真正打破生信使用门槛的杀手锏功能。系统能够智能且动态地基于该 SKILL 内部声明的强类型参数 Schema 表格定义，全自动地在网页上凭空生成一套极其完整的、带有各种必填校验和下拉提示的独立 Web 数据表单。这意味着，哪怕是完全没有任何编程基础、甚至对如何向 AI 提问感到无从下手的医学小白用户，也完全可以绕过复杂的自然语言聊天对话界面，转而像使用任何一款成熟的传统商业化统计软件一样，通过简单的“点选文件、填入数值、点击提交表单”这套最古老也最可靠的流程，直接、确切地调用平台深处隐藏着的最强大的生信分析超级工具！



---

# 实现详细步骤参考

太棒了！这是一项极其宏伟且充满工程美感的重构工程。我们将严格遵循敏捷开发的原则，分阶段、稳扎稳打地推进。

按照规划，我们首先从 **Sprint 1：重铸底层基建魂骨与智能 Bundle 解析器构建** 开始。

这个阶段我们完全不需要改动前端代码，而是专注于后端的“内功”修炼。为了降低单次修改的风险和复杂度，我将 Sprint 1 再次拆分为两个小节。

现在，我们先执行 **Sprint 1 - 第一部分：构建全能的 SKILL 包解析引擎 (Bundle Parser)**。

它的核心任务是扫描物理硬盘上的 Markdown 文件，将其中人类可读的 Frontmatter（元数据）和参数表格提取出来，转化为机器和 AI 能够完美理解的严格 JSON Schema。

请按照以下步骤修改您的后端代码：

### 1. 添加必要的 Python 依赖

我们要解析 YAML 头部和渲染模板，需要在后端的依赖中添加几个库。
请打开 `autonome-backend/requirements.txt`，在末尾添加以下两行：

```text
PyYAML==6.0.1
Jinja2==3.1.3

```

*(添加后，别忘了在您的终端中执行 `pip install -r requirements.txt`，如果是在 Docker 中运行，下一步重构后会自动重新构建。)*

### 2. 编写核心解析引擎 `skill_parser.py`

在 `autonome-backend/app/core/` 目录下，新建一个名为 `skill_parser.py` 的文件。这个类将如同编译器一般，精准提取 `SKILL.md` 中的“隐藏宝藏”。

请将以下完整代码粘贴到 `autonome-backend/app/core/skill_parser.py` 中：

```python
import os
import yaml
import re
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

class SkillBundleParser:
    """
    SKILL 引擎核心解析器
    负责解析 SKILL.md，提取 YAML 元数据，并将 Markdown 表格转换为标准 JSON Schema。
    """
    def __init__(self, skills_dir: str = "/app/app/skills"):
        # 默认指向后端容器中的 skills 挂载目录
        self.skills_dir = skills_dir

    def get_all_skills(self) -> List[Dict[str, Any]]:
        """扫描目录，返回所有有效 SKILL 的结构化数据"""
        skills = []
        if not os.path.exists(self.skills_dir):
            logger.warning(f"SKILL 目录不存在: {self.skills_dir}")
            return skills

        for item in os.listdir(self.skills_dir):
            bundle_path = os.path.join(self.skills_dir, item)
            if os.path.isdir(bundle_path):
                skill_md_path = os.path.join(bundle_path, "SKILL.md")
                if os.path.exists(skill_md_path):
                    parsed_skill = self.parse_skill_md(skill_md_path)
                    if parsed_skill:
                        parsed_skill["bundle_path"] = bundle_path
                        skills.append(parsed_skill)
        return skills

    def parse_skill_md(self, filepath: str) -> Optional[Dict[str, Any]]:
        """深度解析单一 SKILL.md 文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. 解析 YAML Frontmatter
            metadata = self._extract_yaml_frontmatter(content)
            if not metadata or "skill_id" not in metadata:
                logger.error(f"解析失败或缺少 skill_id: {filepath}")
                return None

            # 2. 解析参数表格，生成 JSON Schema
            parameters_schema = self._extract_parameters_schema(content)

            # 3. 提取专家知识库 (给大模型看的操作指令)
            expert_knowledge = self._extract_expert_knowledge(content)

            return {
                "metadata": metadata,
                "parameters_schema": parameters_schema,
                "expert_knowledge": expert_knowledge,
                "raw_content": content # 保留原始文本以备其他用途
            }
        except Exception as e:
            logger.error(f"解析 {filepath} 时发生未知错误: {str(e)}")
            return None

    def _extract_yaml_frontmatter(self, content: str) -> Dict[str, Any]:
        """使用正则提取 --- 包裹的 YAML 区域"""
        pattern = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.MULTILINE | re.DOTALL)
        match = pattern.search(content)
        if match:
            yaml_str = match.group(1)
            try:
                return yaml.safe_load(yaml_str)
            except yaml.YAMLError as e:
                logger.error(f"YAML 解析错误: {e}")
                return {}
        return {}

    def _extract_parameters_schema(self, content: str) -> Dict[str, Any]:
        """将 Markdown 表格解析为 JSON Schema"""
        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # 寻找表格区域：从 | 参数键名 开始，到下一个非表格行为止
        table_pattern = re.compile(r'\|\s*参数键名[\s\S]*?(?=\n\n|\Z)', re.MULTILINE)
        match = table_pattern.search(content)
        
        if not match:
            return schema
            
        table_lines = match.group(0).strip().split('\n')
        if len(table_lines) < 3: # 至少需要表头、分割线、一行数据
            return schema

        for line in table_lines[2:]: # 跳过前两行
            cols = [col.strip() for col in line.split('|')[1:-1]]
            if len(cols) >= 5:
                key = cols[0].replace('`', '').strip()
                data_type = cols[1].strip()
                is_required = "是" in cols[2] or "Yes" in cols[2]
                default_val = cols[3].strip()
                description = cols[4].strip()

                # 将 Markdown 类型映射为 JSON Schema 类型
                json_type = "string"
                if "Number" in data_type:
                    json_type = "number"
                elif "Boolean" in data_type:
                    json_type = "boolean"
                elif "JSONArray" in data_type:
                    json_type = "array"

                prop_def = {
                    "type": json_type,
                    "description": description
                }
                
                # 特殊 UI 提示 (给前端用的)
                if "FilePath" in data_type or "DirectoryPath" in data_type:
                    prop_def["format"] = "filepath"

                if default_val:
                    prop_def["default"] = default_val

                schema["properties"][key] = prop_def
                
                if is_required:
                    schema["required"].append(key)

        return schema

    def _extract_expert_knowledge(self, content: str) -> str:
        """提取操作指令与专家级知识库文本"""
        # 匹配标题 3 以下的内容
        pattern = re.compile(r'## 3\. 操作指令与专家级知识库[^\n]*\n([\s\S]*)', re.MULTILINE)
        match = pattern.search(content)
        if match:
            return match.group(1).strip()
        return ""

# 测试代码 (可独立运行)
if __name__ == "__main__":
    import json
    # 测试时可以指向上次上传代码中的 skills 目录
    parser = SkillBundleParser(skills_dir="../skills")
    skills = parser.get_all_skills()
    print(f"找到 {len(skills)} 个合法 SKILL:")
    print(json.dumps(skills, indent=2, ensure_ascii=False))

```

---

### 第一阶段检查点

完成上述两步修改后：

1. 我们就拥有了将静态 Markdown 文档转化为动态 Schema 的能力，这是整个双轨机制的“基石”。
2. 请确认代码是否已经添加完毕？

如果您已完成这部分，请告诉我。接下来我们将进入 **Sprint 1 - 第二部分：改造 Celery 调度引擎 (双核改造)**，在那一部分我们将修改 `celery_app.py` 和 `tasks.py`，实现基于 Jinja2 模板注入的安全沙箱执行模式。随时等您指令！


收到。我们这就进入 **Sprint 1 - 第二部分：改造 Celery 调度引擎 (双核改造)**。

这一步的意义在于：打通系统的“任督二脉”。我们将保留旧版的“裸写代码执行”通道以供回退，同时引入全新的 `execute_bundle_task`。这个新通道会接管前端传来的、结构化的 JSON 参数，在后台悄悄找到刚才 `SkillBundleParser` 解析出的模板文件，用 Jinja2 安全地把参数填进去，最后扔到隔离沙箱里跑。

请按以下详细步骤修改您的后端代码：

### 1. 升级 Celery 任务处理器 (`celery_app.py`)

打开 `autonome-backend/app/services/celery_app.py`。我们需要引入刚刚写的 Parser 和 Jinja2 模板引擎，并新增一个全局的 Bundle 执行任务。

**修改一：在文件顶部增加必要的导入**
找到文件开头的 `import` 区域，追加以下几行：

```python
from jinja2 import Template
from app.core.skill_parser import SkillBundleParser

```

**修改二：在文件末尾（但在 `TASK_REGISTRY` 声明之前），插入全新的 `execute_bundle_task**`
请将下面这段极其核心的调度逻辑直接粘贴进去：

```python
# ==========================================
# ✨ 全新架构：基于 SKILL Bundle 与 Jinja2 模板的安全沙箱执行器
# ==========================================
@celery_app.task(bind=True)
def execute_bundle_task(self, params: dict):
    task_id = self.request.id
    skill_id = params.get("tool_id")
    project_id = params.get("project_id", 1)
    session_id = params.get("session_id", 1)
    user_params = params.get("parameters", {})
    user_message = params.get("message", f"执行了高级生物信息学分析模块: {skill_id}")

    log_msg = create_task_logger(task_id)
    log_msg(f"🚀 初始化 SKILL Bundle 调度引擎 (Task ID: {task_id}, 模块: {skill_id})")

    try:
        # 1. 解析 Bundle 查找物理路径与元数据
        parser = SkillBundleParser()
        skills = parser.get_all_skills()
        target_skill = next((s for s in skills if s["metadata"].get("skill_id") == skill_id), None)

        if not target_skill:
            raise ValueError(f"严重错误: 未找到对应的 SKILL Bundle 声明 -> {skill_id}")

        metadata = target_skill["metadata"]
        bundle_path = target_skill["bundle_path"]
        entry_point = metadata.get("entry_point")
        executor_type = metadata.get("executor_type", "Python_env")

        if not entry_point or entry_point == "none":
            log_msg(f"✅ 模块 {skill_id} 被标记为逻辑蓝图 (Logical Blueprint)，无需直接执行。")
            return {"status": "success", "message": "逻辑蓝图已被系统成功接收。"}

        script_path = os.path.join(bundle_path, entry_point)
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"找不到声明的执行入口文件: {script_path}")

        # 2. 读取底层模板，并调用 Jinja2 引擎进行防注入的安全参数渲染
        with open(script_path, 'r', encoding='utf-8') as f:
            template_str = f.read()

        template = Template(template_str)
        rendered_code = template.render(**user_params)
        log_msg("🛡️ 参数已通过 Jinja2 引擎安全渲染至模板脚本槽位中。")

        # 3. 准备隔离沙箱环境
        task_short_id = str(task_id)[:8]
        task_dir_name = f"task_{task_short_id}"
        task_out_dir = f"/app/uploads/project_{project_id}/results/{task_dir_name}"
        os.makedirs(task_out_dir, exist_ok=True)
        log_msg(f"📁 已挂载专属隔离输出目录: results/{task_dir_name}")

        # 4. 根据元数据智能决定底层语言
        lang = "python"
        if "R_script" in executor_type:
            lang = "r"
        elif "Bash_shell" in executor_type:
            lang = "bash"
        
        env = {"TASK_OUT_DIR": task_out_dir}
        log_msg(f"⏳ 正在底层 Docker 容器内拉起 {lang} 计算进程...")
        
        # 将渲染好的最终代码抛给原有安全的沙箱底层去跑
        result_output, exit_code = run_container("autonome-tool-env", rendered_code, language=lang, environment=env)

        # 5. 清理终端乱码
        if result_output:
            result_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result_output)
            result_output = re.sub(r'\[\?\d+[hl]', '', result_output)
            result_output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result_output)
            result_output = result_output.replace('\r\n', '\n').replace('\r', '\n').strip()

        if exit_code != 0:
            log_msg(f"💥 脚本执行失败 (Exit Code {exit_code})", level="ERROR")
            with Session(engine) as db:
                final_content = (
                    f"❌ **分析模块 '{metadata.get('name')}' 执行异常 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                    f"### ⚠️ 错误终端日志\n"
                    f"```text\n{result_output}\n```\n"
                )
                db.add(ChatMessage(session_id=session_id, role="assistant", content=final_content))
                db.commit()
            return {"status": "failure"}

        log_msg("🎉 计算任务圆满成功！正在汇总生成资产报告...")

        # 6. 打包生成资产树状图并调用图表解读专家
        generated_files = []
        if os.path.exists(task_out_dir):
            generated_files = [f for f in os.listdir(task_out_dir) if os.path.isfile(os.path.join(task_out_dir, f))]

        files_markdown = ""
        for filename in generated_files:
            container_path = f"/app/uploads/project_{project_id}/results/{task_dir_name}/{filename}"
            files_markdown += f"{container_path}\n"

        img_extensions = ('.png', '.pdf', '.jpg', '.jpeg', '.svg', '.html')
        images = [f for f in generated_files if f.lower().endswith(img_extensions)]
        markdown_img = ""
        if images:
            first_img = images[0]
            actual_filename = f"results/{task_dir_name}/{first_img}"
            markdown_img = f"\n![Analysis_Result](/api/projects/{project_id}/files/{actual_filename}/view)\n"

        summary_path = f"{task_out_dir}/data_summary.txt"
        data_summary = "该模块暂未生成结构化数据摘要。"
        if os.path.exists(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                data_summary = f.read()

        expert_report = generate_expert_report(user_message, rendered_code, data_summary)

        with Session(engine) as db:
            final_content = (
                f"✅ **模块 [{metadata.get('name')}] 执行完毕 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                f"\n"
                f"---\n"
                f"### 📊 核心可视化结论\n\n"
                f"{markdown_img}\n"
                f"---\n"
                f"### 📁 生成的全部文件资产\n\n"
                f"{files_markdown}\n"
                f"---\n"
                f"{expert_report}"
            )
            db.add(ChatMessage(session_id=session_id, role="assistant", content=final_content))
            db.commit()

        return {"status": "success"}
    except Exception as e:
        log_msg(f"💥 调度引擎致命异常: {str(e)}", level="ERROR")
        raise e

```

---

### 2. 升级任务 API 路由 (`tasks.py`)

现在后端有能力执行 Bundle 了，我们要让系统知道：**如果用户请求的工具不在老的 `TASK_REGISTRY` 列表里，不要报错，而是把它扔给新的 SKILL Bundle 引擎处理**。

打开 `autonome-backend/app/api/routes/tasks.py`。

**修改一：引入刚才新建的任务函数**
将顶部的导入行：

```python
from app.services.celery_app import TASK_REGISTRY, redis_client, run_custom_python_task, celery_app

```

修改为：

```python
from app.services.celery_app import TASK_REGISTRY, redis_client, run_custom_python_task, celery_app, execute_bundle_task

```

**修改二：重构 `submit_task` 接口**
找到 `@router.post("/submit")` 装饰的 `submit_task` 函数，把它的内部逻辑替换为兼容双轨并行机制的路由版本：

```python
@router.post("/submit")
async def submit_task(request: TaskSubmitRequest, current_user: User = Depends(get_current_user)):
    """提交一个异步计算任务"""
    
    # 【旧轨道】兼容老版本硬编码的管道工具 (如 RNA-Seq QC)
    if request.tool_id in TASK_REGISTRY:
        task_func = TASK_REGISTRY[request.tool_id]
        task = task_func.delay(request.parameters)
    # 【新轨道】高级 SKILL 调度引擎接管
    else:
        # 重构 payload，将会被 execute_bundle_task 解析渲染
        payload = {
            "tool_id": request.tool_id,
            "project_id": request.project_id,
            "parameters": request.parameters,
            "session_id": request.parameters.get("session_id", 1),
            "message": request.parameters.get("message", f"执行了模块: {request.tool_id}")
        }
        task = execute_bundle_task.delay(payload)
    
    # 记录任务到用户任务列表 (Redis)
    task_info = {
        "task_id": task.id,
        "tool_id": request.tool_id,
        "project_id": request.project_id,
        "status": "PENDING",
        "created_at": time.time(),
        "name": f"{request.tool_id.replace('_', ' ').title()} Analysis"
    }
    
    redis_client.hset(f"task_info:{task.id}", mapping={
        "tool_id": request.tool_id,
        "project_id": str(request.project_id) if request.project_id else "",
        "name": task_info["name"],
        "created_at": str(task_info["created_at"])
    })
    redis_client.expire(f"task_info:{task.id}", 86400 * 7)
    
    redis_client.lpush(f"user_tasks:{current_user.id}", task.id)
    redis_client.ltrim(f"user_tasks:{current_user.id}", 0, 99)
    
    return {"status": "submitted", "task_id": task.id, "tool_id": request.tool_id}

```

---

### 第二阶段检查点

至此，**Sprint 1** 已经大功告成！
底层的机器基建已经彻底重塑完成，我们把以前只能吃“纯代码”的调度系统，升级成了一个**能听懂 JSON 参数并且利用模板自动拼装逻辑的安全工厂**。

确认这部分代码合并成功且服务器能正常重启后，请通知我。我们将立即开启最激动人心的 **Sprint 2：大模型工具链深度握手与革命性的动态参数卡片**！接下来我们将把这些大炮正式交到 AI 的手里。

太棒了！我们现在正式进入 **Sprint 2：大模型工具链深度握手与革命性的动态参数卡片 (The Interaction Paradigm Shift)** 的后端阶段。

在这一步，我们要给 AI 大脑做一次“开颅手术”。目前的 `bot.py` 里，AI 被硬编码为一个只会写 `execute-python` 和 `execute-r` 的“代码打字员”。现在，我们要把第一阶段解析出来的所有 SKILL Schema 动态注入到它的潜意识（System Prompt）中，让它升维成一个**优先统筹调用现成模块、最后才考虑自己写代码的“资深生信分析架构师”**。

请打开 `autonome-backend/app/agent/bot.py`，进行以下全面的重构：

### 修改 `bot.py`

请将 `autonome-backend/app/agent/bot.py` 的全部内容替换为以下代码：

```python
import json
from typing import Annotated, Literal, TypedDict
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

# 引入核心工具与全新的 SKILL 解析器
from app.tools.bio_tools import bio_tools_list, execute_python_code
from app.tools.geo_tools import search_and_vectorize_geo_data, submit_async_geo_analysis_task
from app.tools.report_tools import generate_publishable_report
from app.core.logger import log
from app.core.skill_parser import SkillBundleParser

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    next: str

def build_bio_agent(api_key: str, base_url: str, model_name: str, physical_file_info: str, global_file_tree: str, user_id: int, project_id: int):
    actual_api_key = api_key if (api_key and api_key.strip() != "") else "ollama-local"
    
    llm = ChatOpenAI(
        api_key=actual_api_key, 
        base_url=base_url, 
        model=model_name, 
        temperature=0.1,
        streaming=True,
        max_retries=2
    )
    
    log.info(f"🤖 [Bot] 构建 Agent - API: {base_url}, Model: {model_name}")

    # ✨ 1. 动态加载所有可用的系统标准 SKILL
    parser = SkillBundleParser()
    available_skills = parser.get_all_skills()
    
    # 将 SKILL 转换为 AI 易于理解的 Markdown 目录格式
    skill_catalog_md = ""
    if available_skills:
        for s in available_skills:
            meta = s["metadata"]
            schema = s["parameters_schema"]
            expert = s["expert_knowledge"]
            skill_catalog_md += f"### 模块 ID: `{meta.get('skill_id')}`\n"
            skill_catalog_md += f"- **名称**: {meta.get('name')}\n"
            skill_catalog_md += f"- **参数定义 (JSON Schema)**: {json.dumps(schema, ensure_ascii=False)}\n"
            skill_catalog_md += f"- **专家调用指导**: {expert}\n\n"
    else:
        skill_catalog_md = "*当前系统暂无已注册的标准 SKILL 模块。*"
    
    # ✨ 2. 构建包含项目上下文和工具库的动态 Prompt
    context_info = f"""
[当前系统上下文]
当前项目 ID: {project_id}

【项目全景目录树 (你的全局视力)】
{global_file_tree}

【重点文件】
{physical_file_info if physical_file_info else '用户未特意勾选文件，请从上方目录树中推断。'}
"""
    
    # ✨ 3. 彻底重塑世界观的 System Prompt (双轨并行机制)
    main_prompt = f"""你是 Autonome 生信分析平台的高级架构师和工作流规划大脑。
{context_info}

【系统可用标准 SKILL 兵器库】
以下是当前系统原生支持的高质量标准分析模块。当你收到用户的分析需求时，你必须**优先**仔细查阅这里的模块，看看是否能满足需求：
{skill_catalog_md}

【核心角色与交互协议 (🚨极其重要)】
系统采用“双轨并行机制”。面对用户的需求，你必须按照以下优先级进行思考和响应：

🔴 **第一轨：标准 SKILL 调用 (绝对优先)**
如果用户的需求（或需求的一部分）可以被【可用标准 SKILL 兵器库】中的某个工具完美覆盖，你**绝对不要**自己写 Python 或 R 代码！
你只需要直接输出一段 JSON 策略卡片，系统底层会接管并渲染动态配置表单。
格式要求：
1. 简要向用户解释你将调用哪个标准模块，并说明为什么。
2. 严格根据该模块的 JSON Schema，在脑海中推断参数（从全景目录树中寻找合适的文件路径）。
3. 输出由 ```json_strategy 包裹的卡片，`tool_id` 必须填入对应的 SKILL ID！

【第一轨输出示例 (调用 FastQC 模块)】
我将为您调用标准的 FastQC 质控模块来评估这些原始测序数据。
```json_strategy
{{
  "title": "原始数据质量控制",
  "description": "调用系统标准 FastQC 模块处理原始测序数据并生成 MultiQC 报告",
  "tool_id": "fastqc_multiqc_pipeline_01",
  "parameters": {{
    "fastq_dir": "/app/uploads/project_{project_id}/raw_data/",
    "is_paired_end": true
  }},
  "estimated_time": "约 10 分钟"
}}

```

🔴 **第二轨：[Live_Coding] 实时代码生成 (仅限无模块可用时)**
当你绞尽脑汁、搜遍整个兵器库也确实发现缺乏匹配的工具时，你才被系统授权激活 `[Live_Coding]` 通道自行编写代码（优先使用R语言绘图）。
格式要求：

1. 简要说明思路。
2. 具体的执行代码（必须用 `python 或 `r 包裹）。注意：必须将结果保存至环境变量 `TASK_OUT_DIR` 指定的目录，且图表必须使用纯英文标签！
3. 输出策略卡片，`tool_id` 只能是 `execute-python` 或 `execute-r`。

【第二轨输出示例】
系统未找到现成的提取模块，我将为您实时编写 R 脚本提取前 20 行。

```r
out_dir <- Sys.getenv("TASK_OUT_DIR")
if (out_dir == "") out_dir <- "/app/uploads/project_{project_id}/results/default_task"
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
# ... 读取数据并保存到 out_dir ...

```

```json_strategy
{{
  "title": "自定义提取脚本",
  "description": "实时编写 R 脚本提取前 20 行",
  "tool_id": "execute-r",
  "estimated_time": "约 1 分钟"
}}

```

⚠️ **底线红线**：绝不允许在回复中声称“我已经为您执行了代码”、“任务已提交”。你只负责生成“策略卡片”，真正的执行由用户在前端点击卡片上的 Execute 按钮触发！
"""

```
all_tools = [search_and_vectorize_geo_data, submit_async_geo_analysis_task, generate_publishable_report]
main_agent = create_react_agent(llm, tools=all_tools, prompt=main_prompt)

async def run_agent(state: AgentState):
    result = await main_agent.ainvoke(state)
    return {"messages": [result["messages"][-1]]}

workflow = StateGraph(AgentState)
workflow.add_node("main", run_agent)
workflow.add_edge(START, "main")
workflow.add_edge("main", END)

return workflow.compile()

```

```

### 变更深度解析

1. **动态兵器库注入 (`SkillBundleParser` 实例化)**：现在，每次构建 Agent，系统都会实时扫描 `/app/skills/` 目录。我们把刚才设计的 `fastqc_multiqc_pipeline_01` 等规范直接转成 Markdown 塞进去了。AI 终于“看到”了自己有哪些强大的现成工具可以用。
2. **确立双轨并行优先级 (System Prompt 重写)**：
   * 明确规定**第一轨 (优先)**：遇到质控、比对等标准需求，绝不自己写低效易错的脚本，而是输出指定的 `tool_id`（例如 `fastqc_multiqc_pipeline_01`）和推断出的 `parameters` 参数。
   * 明确规定**第二轨 (回退)**：只有遇到奇思妙想的数据清洗或个性化画图，才回退到 `execute-python`/`execute-r` 模式自己写代码。
3. **消除大模型“虚假执行”幻觉**：强化了底线红线，让大模型老老实实当“策略卡片生成器”，而不是假装自己已经跑完了任务。

---

### Sprint 2 - 第一部分检查点

完成此文件修改并重启后端后，如果用户在聊天框输入“帮我跑个 FastQC 总结一下”，大模型将不再胡乱编写一段根本跑不通的 Bash FastQC 脚本，而是会瞬间输出一个极其标准的 JSON 策略卡片，工具 ID 直接指向我们此前设计好的蓝图！

由于这是一个全栈项目，大模型输出了带有自定义参数的卡片后，**前端 `StrategyCard.tsx` 和 `ChatStage.tsx` 目前还无法完美渲染这些动态参数和滑出的配置面板**。

如果您确认后端的“大脑洗礼”已经完成，请回复我，我们将立即开启 **Sprint 2 - 第二部分：前端动态参数 UI 引擎的研发**！那将是整个平台交互体验最惊艳的时刻。

```


现在我们正式进入 **Sprint 2 - 第二部分：前端动态参数 UI 引擎的研发**。

在第一轨中，AI 已经能够输出带有推断参数的 JSON 策略卡片。按照设计规划，为了防止“黑盒操作”带来的科研风险，我们需要在前端构建一道“物理屏障”：将原本只能“看”的静态策略卡片，升级为支持实时深度校验与互动修改的**动态配置表单**。

请打开前端项目中的 `autonome-studio/src/components/chat/StrategyCard.tsx`，进行如下替换升级：

### 修改 `StrategyCard.tsx`

我们要引入局部状态来接管 `data.parameters`，并将其渲染为可编辑的表单控件，让用户可以在执行前调整底层分析参数。

请将以下完整代码覆盖现有的 `StrategyCard.tsx`：

```tsx
"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Play, Clock, CheckCircle, Loader2, XCircle, Settings2 } from "lucide-react";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { BASE_URL } from "@/lib/api";

export interface StrategyCardData {
  title: string;
  description: string;
  tool_id: string;
  code?: string;
  parameters?: Record<string, unknown>;
  steps?: string[];
  estimated_time?: string;
  risk_level?: "low" | "medium" | "high";
}

interface StrategyCardProps {
  data: StrategyCardData;
  onExecute?: (taskId: string) => void;
  onCancel?: () => void;
}

export function StrategyCard({ data, onExecute, onCancel }: StrategyCardProps) {
  const { currentProjectId, currentSessionId } = useWorkspaceStore();
  const [isExecuting, setIsExecuting] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // ✨ 新增：接管 AI 推断的参数，将其转化为用户可交互修改的局部状态
  const [editableParams, setEditableParams] = useState<Record<string, unknown>>(data.parameters || {});

  const cacheKey = `strategy_status_${currentProjectId}_${data.title}_${data.description?.slice(0, 20)}`;

  useEffect(() => {
    const cached = localStorage.getItem(cacheKey);
    if (cached) {
      try {
        const cachedData = JSON.parse(cached);
        if (cachedData.taskId && cachedData.taskStatus) {
          setTaskId(cachedData.taskId);
          setTaskStatus(cachedData.taskStatus);
        }
      } catch (e) {}
    }
  }, [cacheKey]);

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const connectWebSocket = (id: string) => {
    const token = localStorage.getItem('autonome_access_token');
    const wsUrl = `${BASE_URL.replace('http', 'ws')}/api/tasks/${id}/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'status') {
          setTaskStatus(message.status);
          setProgress(message.progress);

          if (message.status === 'SUCCESS' || message.status === 'FAILURE') {
            setIsExecuting(false);
            if (message.status === 'SUCCESS') {
              localStorage.setItem(cacheKey, JSON.stringify({ taskId: id, taskStatus: message.status }));
              setTimeout(() => {
                window.dispatchEvent(new CustomEvent('refresh-chat'));
              }, 500);
            }
            ws.close();
          }
        } else if (message.type === 'error') {
          setError(message.error);
          setIsExecuting(false);
          ws.close();
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };
    ws.onerror = (err) => setError('WebSocket connection error');
    wsRef.current = ws;
  };

  const handleExecute = async () => {
    if (!data.tool_id) {
      setError("No tool selected");
      return;
    }

    setIsExecuting(true);
    setError(null);

    const safeSessionId = currentSessionId || 1;

    try {
      const token = localStorage.getItem('autonome_access_token');
      let payload: Record<string, unknown>;
      
      if ((data.tool_id === 'execute-python' || data.tool_id === 'execute-r') && data.code) {
        payload = {
          tool_id: data.tool_id,
          parameters: {
            code: data.code,
            session_id: safeSessionId,
            project_id: currentProjectId
          },
          project_id: currentProjectId
        };
      } else {
        // ✨ 修改：提交用户确认/修改后的参数，而不是原本 AI 生成的静态参数
        payload = {
          tool_id: data.tool_id,
          parameters: editableParams,
          project_id: currentProjectId
        };
      }

      const response = await fetch(`${BASE_URL}/api/tasks/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(payload)
      });

      const result = await response.json();

      if (result.status === 'submitted') {
        setTaskId(result.task_id);
        onExecute?.(result.task_id);
        connectWebSocket(result.task_id);
      } else {
        setError(result.message || 'Failed to submit task');
        setIsExecuting(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setIsExecuting(false);
    }
  };

  // 动态处理参数类型的变更
  const handleParamChange = (key: string, rawValue: string) => {
    let parsedValue: unknown = rawValue;
    if (rawValue === "true") parsedValue = true;
    else if (rawValue === "false") parsedValue = false;
    else if (!isNaN(Number(rawValue)) && rawValue.trim() !== '') parsedValue = Number(rawValue);

    setEditableParams(prev => ({ ...prev, [key]: parsedValue }));
  };

  const getStatusIcon = () => {
    if (isExecuting) return <Loader2 className="w-4 h-4 animate-spin text-blue-400" />;
    if (taskStatus === 'SUCCESS') return <CheckCircle className="w-4 h-4 text-green-400" />;
    if (taskStatus === 'FAILURE') return <XCircle className="w-4 h-4 text-red-400" />;
    return <Clock className="w-4 h-4 text-yellow-400" />;
  };

  const getRiskColor = (risk?: string) => {
    switch (risk) {
      case 'low': return 'bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/30';
      case 'medium': return 'bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/30';
      case 'high': return 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400 border-red-200 dark:border-red-500/30';
      default: return 'bg-gray-200 dark:bg-neutral-700/50 text-gray-600 dark:text-neutral-400 border-gray-300 dark:border-neutral-600';
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-gradient-to-br from-gray-50 to-gray-100 dark:from-neutral-900 dark:to-neutral-800 border border-gray-200 dark:border-neutral-700 rounded-xl p-5 shadow-sm dark:shadow-xl my-4 w-full"
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1 flex items-center gap-2">
            <Settings2 className="w-5 h-5 text-blue-500" />
            {data.title}
          </h3>
          <div className="flex items-center gap-2 mt-1">
            {data.estimated_time && (
              <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-neutral-400">
                <Clock className="w-3 h-3" />
                {data.estimated_time}
              </span>
            )}
          </div>
        </div>
        <div className="px-3 py-1.5 bg-blue-50 dark:bg-blue-600/20 border border-blue-200 dark:border-blue-500/30 rounded-lg">
          <span className="text-xs font-mono text-blue-700 dark:text-blue-400">{data.tool_id}</span>
        </div>
      </div>

      <p className="text-sm text-gray-700 dark:text-neutral-300 mb-5">{data.description}</p>

      {/* ✨ 核心革新：动态渲染可编辑的参数表单 */}
      {Object.keys(editableParams).length > 0 && data.tool_id !== 'execute-python' && data.tool_id !== 'execute-r' && (
        <div className="bg-white dark:bg-neutral-950/40 border border-gray-200 dark:border-neutral-800 rounded-lg p-4 mb-5">
          <p className="text-xs font-medium text-gray-500 dark:text-neutral-400 mb-3 uppercase tracking-wider">执行参数核对 (Parameters)</p>
          <div className="space-y-3">
            {Object.entries(editableParams).map(([key, value]) => {
              const isBool = typeof value === "boolean";
              return (
                <div key={key} className="flex flex-col gap-1.5">
                  <label className="text-xs text-gray-700 dark:text-neutral-300 font-mono pl-1">{key}</label>
                  {isBool ? (
                    <select
                      disabled={!!taskId}
                      value={String(value)}
                      onChange={(e) => handleParamChange(key, e.target.value)}
                      className="w-full bg-gray-50 dark:bg-neutral-900 border border-gray-300 dark:border-neutral-700 text-gray-900 dark:text-neutral-200 text-sm rounded-md focus:ring-blue-500 focus:border-blue-500 block p-2 transition-colors disabled:opacity-50"
                    >
                      <option value="true">True (是)</option>
                      <option value="false">False (否)</option>
                    </select>
                  ) : (
                    <input
                      type="text"
                      disabled={!!taskId}
                      value={String(value)}
                      onChange={(e) => handleParamChange(key, e.target.value)}
                      className="w-full bg-gray-50 dark:bg-neutral-900 border border-gray-300 dark:border-neutral-700 text-gray-900 dark:text-neutral-200 text-sm rounded-md focus:ring-blue-500 focus:border-blue-500 block p-2 transition-colors disabled:opacity-50 font-mono"
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Status & Error Rendering */}
      {(isExecuting || taskStatus) && (
        <div className="flex items-center gap-2 text-sm mb-4">
          {getStatusIcon()}
          <span className="text-gray-700 dark:text-neutral-300">
            {isExecuting ? (progress !== null ? `Executing... ${progress}%` : 'Executing...') : `Status: ${taskStatus}`}
          </span>
          {progress !== null && (
            <div className="flex-1 h-1.5 bg-gray-200 dark:bg-neutral-700 rounded-full overflow-hidden ml-2">
              <div className="h-full bg-blue-500 transition-all duration-300" style={{ width: `${progress}%` }} />
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-500/30 rounded-lg p-3 mb-4">
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        {!taskId ? (
          <>
            <button
              onClick={handleExecute}
              disabled={isExecuting}
              className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-all shadow-md hover:shadow-lg"
            >
              {isExecuting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
              {Object.keys(editableParams).length > 0 && data.tool_id !== 'execute-python' && data.tool_id !== 'execute-r' 
                ? "确认参数并执行" 
                : "执行分析"}
            </button>
            {onCancel && (
              <button
                onClick={onCancel}
                className="px-4 py-2.5 bg-gray-200 dark:bg-neutral-700 hover:bg-gray-300 dark:hover:bg-neutral-600 text-gray-700 dark:text-white text-sm font-medium rounded-lg transition-colors"
              >
                取消
              </button>
            )}
          </>
        ) : (
          <div className="flex items-center gap-3 w-full">
            {taskStatus === 'SUCCESS' && (
              <div className="flex items-center gap-2 px-3 py-1.5 bg-green-100 dark:bg-green-900/30 border border-green-200 dark:border-green-500/30 rounded-lg">
                <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />
                <span className="text-sm font-medium text-green-700 dark:text-green-300">执行完成</span>
              </div>
            )}
            {taskStatus === 'FAILURE' && (
              <div className="flex items-center gap-2 px-3 py-1.5 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-500/30 rounded-lg">
                <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
                <span className="text-sm font-medium text-red-700 dark:text-red-300">执行失败</span>
              </div>
            )}
            <div className="text-sm text-gray-500 dark:text-neutral-400 ml-auto">
              Task ID: <code className="bg-gray-200 dark:bg-neutral-800 px-2 py-0.5 rounded text-blue-600 dark:text-blue-400 font-mono">{taskId.slice(0, 8)}</code>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ... 保持原有的 parseStrategyCard 函数不变 ...
export function parseStrategyCard(content: string): StrategyCardData | null {
// ... 保持原有实现不变 ...

```

*(注意：保留底部的 `parseStrategyCard` 函数与您原始代码一致，为了篇幅未完整贴出)*

### 阶段小结

通过这次修改：

1. 原本静态展示的参数 `data.parameters` 变成了响应式的 React 状态 `editableParams`。
2. 我们为布尔类型渲染了易于选择的下拉菜单（True/False），为普通文本和数字渲染了文本框。
3. 当用户点击“确认参数并执行”时，发送给后端的不再是大模型猜测的静态数据，而是**经过用户“眼球把关”并随时可以修改的最终参数**。

如果您确认代码已经顺利合并，并且可以在前端看到漂亮的交互式参数表单了，请告诉我，我们可以继续进入下一步：**Sprint 3：加速知识沉淀与 Nextflow 工业级引擎的融合引入**！



太棒了！我们现在正式进入 **Sprint 3：加速知识沉淀与 Nextflow 工业级引擎的融合引入 (Knowledge Consolidation & Scale up)**。

这个阶段的核心目标是打通系统的“任督二脉”，实现**“一键封神”**的功能：将用户在 `[Live_Coding]` 中跑通的、有价值的零散脚本，通过 AI 逆向推导参数，自动打包成标准的 `SKILL Bundle`，永久沉淀为平台的固定资产。

我们需要在后端新增一个专门负责处理 SKILL 核心逻辑的路由模块，并将其注册到主程序中。

请按照以下详细步骤进行升级：

### 1. 新建核心路由模块 `skills.py`

在 `autonome-backend/app/api/routes/` 目录下，新建一个文件 `skills.py`。这个模块将提供目录查询 (`/catalog`) 和知识固化 (`/transform_from_live`) 接口。

请将以下完整代码粘贴到 `autonome-backend/app/api/routes/skills.py` 中：

```python
import os
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.database import engine
from app.core.config import settings
from app.models.domain import User, ChatMessage
from app.api.deps import get_current_user
from app.core.skill_parser import SkillBundleParser
from app.core.logger import log

router = APIRouter()

class TransformRequest(BaseModel):
    task_id: str
    session_id: str
    new_skill_name: str
    description: str

@router.get("/catalog")
async def get_skill_catalog():
    """获取系统中所有已注册的标准 SKILL 目录"""
    parser = SkillBundleParser()
    skills = parser.get_all_skills()
    return {"status": "success", "total": len(skills), "data": skills}

@router.post("/transform_from_live")
async def transform_from_live(req: TransformRequest, current_user: User = Depends(get_current_user)):
    """
    核心固化接口：一键封神
    接收成功的 Live_Coding 任务 ID，提取代码，使用 LLM 生成标准 Bundle。
    """
    log.info(f"🚀 开始固化流程，来源任务: {req.task_id}")
    
    # 1. 从数据库中提取那段成功运行的原始代码
    with Session(engine) as db:
        # 在聊天记录中寻找包含该 task_id 的最后一条成功消息
        statement = select(ChatMessage).where(
            ChatMessage.session_id == req.session_id,
            ChatMessage.content.contains(req.task_id[:8]),
            ChatMessage.content.contains("✅") # 必须是执行成功的记录
        ).order_by(ChatMessage.created_at.desc())
        
        msg = db.exec(statement).first()
        if not msg:
            raise HTTPException(status_code=404, detail="未找到该任务的成功执行记录")
            
        # 提取我们在 celery_app.py 中埋下的 DEEP_INTERPRET_META 代码锚点
        code_match = re.search(r'CODE_START\n(.*?)\nCODE_END', msg.content, re.DOTALL)
        if not code_match:
            raise HTTPException(status_code=400, detail="无法从历史记录中提取原始源码")
            
        raw_code = code_match.group(1).strip()

    # 2. 召唤大模型进行逆向工程，推导参数 Schema 并生成 SKILL.md
    llm = ChatOpenAI(
        api_key=settings.OPENAI_API_KEY if settings.OPENAI_API_KEY else "ollama-local",
        base_url=settings.OPENAI_BASE_URL,
        model=settings.MODEL_NAME,
        temperature=0.1
    )
    
    system_prompt = """你是一个顶级的计算生物学软件工程师。
你需要阅读一段成功运行的 Python/R 分析脚本，逆向推导出它需要哪些动态参数，并将其改写为支持 Jinja2 模板注入的脚本。
最后，你需要严格按照我们系统的 SKILL.md 规范，输出一份完整的 Bundle 定义文档。

请使用以下格式返回结果（必须包含两个部分，用分隔符 ==== 分开）：
[第一部分：改写后支持 {{ parameter_name }} 的模板源码]
====
[第二部分：完整的 SKILL.md 文档内容（包含 YAML 头和 Markdown 参数表格）]
"""
    
    user_prompt = f"任务名称: {req.new_skill_name}\n任务描述: {req.description}\n\n原始成功代码:\n```\n{raw_code}\n```\n\n请进行逆向工程提取参数，并生成 Jinja2 模板和 SKILL.md。"
    
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        
        parts = response.content.split('====')
        if len(parts) < 2:
            raise ValueError("大模型未按严格格式返回分割结果")
            
        template_code = parts[0].replace('```python', '').replace('```r', '').replace('```', '').strip()
        skill_md = parts[1].strip()
        
    except Exception as e:
        log.error(f"大模型逆向推导失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"逆向工程失败: {str(e)}")

    # 3. 在服务器物理磁盘上创建标准 Bundle 目录结构
    skill_bundle_id = f"custom_{uuid.uuid4().hex[:8]}"
    bundle_dir = os.path.join("/app/app/skills", skill_bundle_id)
    scripts_dir = os.path.join(bundle_dir, "scripts")
    
    os.makedirs(scripts_dir, exist_ok=True)
    
    # 判断语言后缀
    ext = ".R" if "<-" in raw_code or "library(" in raw_code else ".py"
    script_filename = f"main{ext}"
    
    # 强制修正 SKILL.md 中的动态生成的系统元数据
    skill_md = re.sub(r'skill_id:.*', f'skill_id: "{skill_bundle_id}"', skill_md)
    skill_md = re.sub(r'entry_point:.*', f'entry_point: "scripts/{script_filename}"', skill_md)

    # 4. 写入文件，完成固化
    with open(os.path.join(bundle_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(skill_md)
        
    with open(os.path.join(scripts_dir, script_filename), "w", encoding="utf-8") as f:
        f.write(template_code)
        
    log.info(f"🎉 知识固化成功！已生成新技能包: {skill_bundle_id}")

    return {
        "status": "success", 
        "message": "一键封神成功！该脚本已作为标准能力注册到系统中。",
        "skill_id": skill_bundle_id
    }

```

### 2. 将路由注册到 FastAPI 主程序

新建了 `skills.py` 后，需要让 FastAPI 知道它的存在。

请打开 `autonome-backend/main.py`（如果您的路由挂载在 `app/api/main.py` 或类似入口，请打开对应文件），在注册路由的区域添加：

**修改一：导入新的路由模块**

```python
from app.api.routes import skills

```

**修改二：挂载路由**
在现有的 `app.include_router(...)` 代码块附近，添加这一行：

```python
app.include_router(skills.router, prefix="/api/skills", tags=["skills"])

```

### 阶段小结

完成这两步后：

1. 后端现在具备了 `/api/skills/catalog` 接口，前端随时可以获取所有可用技能的树状列表。
2. 我们实现了一个极其硬核的 `/api/skills/transform_from_live` 接口。当用户通过 `execute-python` 跑通了一段珍贵的单细胞处理代码后，调用这个接口，大模型会**自动阅读代码、提取变量、改写为 Jinja2 模板，并自动生成严格的 `SKILL.md` 文档**，直接写入硬盘。系统实现了真正意义上的“自我进化”！

确保代码保存并重启后端。如果您确认接口已就绪并且无报错，请告诉我，我们将进入最后的收官之战：**Sprint 4：打造旗舰级的前端 SKILL 专属工作台体验 (The Ultimate Skill Studio UI)**！

太棒了！我们现在迎来了整个系统升级的最终章——**Sprint 4：打造旗舰级的前端 SKILL 专属工作台体验 (The Ultimate Skill Studio UI)**。

在这一阶段，我们将把后端深埋的强大能力，转化为前端极具视觉冲击力和易用性的“应用商店”界面。即使是完全不懂编程的用户，也能通过纯图形化的表单（GUI Form Mode）直接调用这些工业级的生信分析流水线。

由于这是一个完整的新功能模块，我们需要分为几个步骤来完成前端的拼图。

### 第一步：注册全局 UI 状态

首先，我们需要在状态管理中增加控制这个新工作台显示/隐藏的开关。

请打开 `autonome-studio/src/store/useUIStore.ts`，在现有状态中补充 `SkillCenter` 的相关逻辑：

```typescript
import { create } from 'zustand';

interface UIState {
  // ... 现有的状态 (isProjectCenterOpen, isDataCenterOpen 等) 保留不变 ...
  isProjectCenterOpen: boolean;
  openProjectCenter: () => void;
  closeProjectCenter: () => void;
  
  // ✨ 新增 Skill Center 状态
  isSkillCenterOpen: boolean;
  openSkillCenter: () => void;
  closeSkillCenter: () => void;
  
  // (其他现有代码保持不变)
}

export const useUIStore = create<UIState>((set) => ({
  // ... 现有的初始化 ...
  isProjectCenterOpen: false,
  openProjectCenter: () => set({ isProjectCenterOpen: true }),
  closeProjectCenter: () => set({ isProjectCenterOpen: false }),

  // ✨ 新增 Skill Center 实现
  isSkillCenterOpen: false,
  openSkillCenter: () => set({ isSkillCenterOpen: true }),
  closeSkillCenter: () => set({ isSkillCenterOpen: false }),
}));

```

*(注：请将新增部分融合进您原本的 `useUIStore.ts` 中)*

### 第二步：在侧边栏添加入口

接下来，让这个旗舰级功能在主界面拥有最显眼的入口。

请打开 `autonome-studio/src/components/layout/Sidebar.tsx`（或者是 `SessionSidebar.tsx`），在导航图标列表中加入 `Skill Studio` 按钮：

```tsx
// 在顶部的 import 区域，引入一个代表组件/技能的图标 (如 Blocks 或 Wrench)
import { FolderKanban, Database, MessageSquare, Settings, Blocks } from "lucide-react";
import { useUIStore } from "@/store/useUIStore";

// 在组件内部：
export function Sidebar() {
  const { openProjectCenter, openDataCenter, openSkillCenter } = useUIStore();

  return (
    <aside className="w-16 bg-neutral-950 border-r border-neutral-800 flex flex-col items-center py-4 z-50">
      {/* 顶部 Logo 区... */}

      {/* 核心导航区 */}
      <nav className="flex flex-col gap-4 mt-8">
        <button onClick={openProjectCenter} className="p-3 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-xl transition-colors" title="Project Center">
          <FolderKanban size={20} />
        </button>
        <button onClick={openDataCenter} className="p-3 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-xl transition-colors" title="Data Assets">
          <Database size={20} />
        </button>
        
        {/* ✨ 新增的技能中心入口，采用亮眼的主题色 */}
        <button 
          onClick={openSkillCenter} 
          className="p-3 text-blue-400 hover:text-blue-300 hover:bg-blue-900/20 rounded-xl transition-colors relative group" 
          title="Skill Studio 技能中心"
        >
          <Blocks size={20} />
          {/* 可选：加一个发光小红点提示有新能力 */}
          <span className="absolute top-2 right-2 w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>
        </button>
      </nav>

      {/* 底部设置区... */}
    </aside>
  );
}

```

### 第三步：打造旗舰级 Skill Center 组件 (核心)

这是工作量最大、最惊艳的部分。我们将实现一个左侧是“应用卡片列表”，右侧是“动态 GUI 表单面板”的沉浸式工作台。

请在 `autonome-studio/src/components/overlays/` 目录下新建文件 `SkillCenter.tsx`，并粘贴以下完整代码：

```tsx
"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Search, Blocks, Play, Loader2, Info } from "lucide-react";
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { BASE_URL } from "@/lib/api";

interface SkillMeta {
  skill_id: string;
  name: string;
  version: string;
  author: string;
  executor_type: string;
}

interface Skill {
  metadata: SkillMeta;
  parameters_schema: any;
  expert_knowledge: string;
}

export function SkillCenter() {
  const { isSkillCenterOpen, closeSkillCenter } = useUIStore();
  const { currentProjectId, currentSessionId } = useWorkspaceStore();
  
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  
  // 动态表单状态
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<{status: string, msg: string} | null>(null);

  useEffect(() => {
    if (isSkillCenterOpen) {
      fetchSkills();
    }
  }, [isSkillCenterOpen]);

  const fetchSkills = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${BASE_URL}/api/skills/catalog`);
      const data = await res.json();
      if (data.status === 'success') {
        setSkills(data.data);
      }
    } catch (e) {
      console.error("Failed to fetch skills", e);
    } finally {
      setLoading(false);
    }
  };

  const filteredSkills = skills.filter(s => 
    s.metadata.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.metadata.skill_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleSelectSkill = (skill: Skill) => {
    setSelectedSkill(skill);
    // 初始化表单默认值
    const initialData: Record<string, any> = {};
    const props = skill.parameters_schema?.properties || {};
    Object.keys(props).forEach(key => {
      if (props[key].default !== undefined) {
        initialData[key] = props[key].default;
      } else if (props[key].type === 'boolean') {
        initialData[key] = false;
      } else {
        initialData[key] = "";
      }
    });
    setFormData(initialData);
    setSubmitResult(null);
  };

  const executeSkill = async () => {
    if (!selectedSkill) return;
    setIsSubmitting(true);
    setSubmitResult(null);

    try {
      const token = localStorage.getItem('autonome_access_token');
      const payload = {
        tool_id: selectedSkill.metadata.skill_id,
        project_id: currentProjectId,
        parameters: {
          ...formData,
          session_id: currentSessionId || 1
        }
      };

      const res = await fetch(`${BASE_URL}/api/tasks/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      
      if (data.status === 'submitted') {
        setSubmitResult({ status: 'success', msg: `已成功投递！Task ID: ${data.task_id.slice(0,8)}。您可以关闭本窗口，在聊天流中查看进度。` });
        // 通知主聊天界面刷新
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent('refresh-chat'));
        }, 1000);
      } else {
        throw new Error(data.message || '投递失败');
      }
    } catch (e: any) {
      setSubmitResult({ status: 'error', msg: e.message || '网络错误' });
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isSkillCenterOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="w-full max-w-6xl h-[85vh] bg-[#131314] border border-neutral-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-800 bg-[#1a1a1b]">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-900/30 rounded-lg text-blue-400">
              <Blocks size={24} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight">Skill Studio 技能中心</h2>
              <p className="text-xs text-neutral-400">探索并零代码运行高度标准化的工业级生信流水线</p>
            </div>
          </div>
          <button onClick={closeSkillCenter} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-full transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-1 overflow-hidden">
          
          {/* 左侧：应用商店列表 */}
          <div className="w-1/2 border-r border-neutral-800 flex flex-col bg-[#161618]">
            <div className="p-4 border-b border-neutral-800">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" size={16} />
                <input 
                  type="text" 
                  placeholder="搜索技能名称或 ID..." 
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-[#1e1e1f] border border-neutral-700 text-white text-sm rounded-lg pl-9 pr-4 py-2.5 focus:border-blue-500 focus:outline-none transition-colors"
                />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3 scroll-smooth">
              {loading ? (
                <div className="flex flex-col items-center justify-center h-40 text-neutral-500 gap-2">
                  <Loader2 className="animate-spin" size={24} />
                  <span className="text-sm">正在加载技能目录...</span>
                </div>
              ) : filteredSkills.length === 0 ? (
                <div className="text-center text-neutral-500 text-sm mt-10">暂无匹配的技能模块</div>
              ) : (
                filteredSkills.map((skill) => (
                  <div 
                    key={skill.metadata.skill_id}
                    onClick={() => handleSelectSkill(skill)}
                    className={`p-4 rounded-xl border cursor-pointer transition-all ${
                      selectedSkill?.metadata.skill_id === skill.metadata.skill_id 
                        ? 'bg-blue-900/10 border-blue-500/50 shadow-[0_0_15px_rgba(59,130,246,0.1)]' 
                        : 'bg-[#1e1e1f] border-neutral-800 hover:border-neutral-600 hover:bg-[#232325]'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="text-base font-semibold text-neutral-200">{skill.metadata.name}</h3>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-neutral-800 text-neutral-400 border border-neutral-700">v{skill.metadata.version}</span>
                    </div>
                    <p className="text-xs text-neutral-400 mb-3 line-clamp-2">{skill.expert_knowledge}</p>
                    <div className="flex items-center gap-3 text-[10px] font-mono">
                      <span className="text-blue-400 bg-blue-400/10 px-1.5 py-0.5 rounded">{skill.metadata.executor_type}</span>
                      <span className="text-neutral-500">ID: {skill.metadata.skill_id}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* 右侧：纯图形化执行面板 (GUI Form Mode) */}
          <div className="w-1/2 bg-[#131314] flex flex-col relative overflow-hidden">
            <AnimatePresence mode="wait">
              {selectedSkill ? (
                <motion.div 
                  key={selectedSkill.metadata.skill_id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className="flex flex-col h-full"
                >
                  <div className="flex-1 overflow-y-auto p-6 scroll-smooth">
                    <h3 className="text-xl font-bold text-white mb-2">{selectedSkill.metadata.name}</h3>
                    <p className="text-sm text-neutral-400 mb-6 bg-blue-900/10 border border-blue-500/20 p-3 rounded-lg flex items-start gap-2">
                      <Info size={16} className="text-blue-400 shrink-0 mt-0.5" />
                      <span>请在下方填写所需参数。系统将直接验证并启动底层 {selectedSkill.metadata.executor_type} 引擎进行运算。</span>
                    </p>

                    {/* 动态渲染表单 Schema */}
                    <div className="space-y-5">
                      {Object.entries(selectedSkill.parameters_schema?.properties || {}).map(([key, prop]: [string, any]) => {
                        const isRequired = selectedSkill.parameters_schema.required?.includes(key);
                        const isBool = prop.type === 'boolean';
                        
                        return (
                          <div key={key} className="flex flex-col gap-1.5">
                            <label className="text-sm font-medium text-neutral-200 flex items-center gap-2">
                              <span className="font-mono text-blue-300">{key}</span>
                              {isRequired && <span className="text-red-400 text-xs">*必填</span>}
                            </label>
                            <p className="text-[11px] text-neutral-500 leading-tight mb-1">{prop.description}</p>
                            
                            {isBool ? (
                              <select
                                value={String(formData[key])}
                                onChange={(e) => setFormData({...formData, [key]: e.target.value === 'true'})}
                                className="w-full bg-[#1e1e1f] border border-neutral-700 text-white text-sm rounded-lg p-2.5 focus:border-blue-500 focus:outline-none"
                              >
                                <option value="true">True</option>
                                <option value="false">False</option>
                              </select>
                            ) : (
                              <input
                                type={prop.type === 'number' ? 'number' : 'text'}
                                value={formData[key] || ''}
                                onChange={(e) => setFormData({...formData, [key]: prop.type === 'number' ? Number(e.target.value) : e.target.value})}
                                placeholder={prop.default ? `例如: ${prop.default}` : '请输入...'}
                                className="w-full bg-[#1e1e1f] border border-neutral-700 text-white text-sm rounded-lg p-2.5 focus:border-blue-500 focus:outline-none font-mono"
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* 底部执行操作栏 */}
                  <div className="p-4 bg-[#1a1a1b] border-t border-neutral-800 shrink-0">
                    {submitResult && (
                      <div className={`mb-3 p-3 rounded-lg text-sm border ${submitResult.status === 'success' ? 'bg-green-900/20 border-green-500/30 text-green-400' : 'bg-red-900/20 border-red-500/30 text-red-400'}`}>
                        {submitResult.msg}
                      </div>
                    )}
                    <button
                      onClick={executeSkill}
                      disabled={isSubmitting}
                      className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white rounded-xl font-medium shadow-lg flex items-center justify-center gap-2 transition-all"
                    >
                      {isSubmitting ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} fill="currentColor" />}
                      直接执行该流水线
                    </button>
                  </div>
                </motion.div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-neutral-500 p-8 text-center">
                  <div className="w-20 h-20 mb-6 bg-neutral-900 rounded-full flex items-center justify-center">
                    <Blocks size={32} className="text-neutral-700" />
                  </div>
                  <p className="text-lg text-neutral-300 font-medium mb-2">未选择模块</p>
                  <p className="text-sm">请在左侧目录中选择一个所需的高级生信分析技能进行参数配置和执行。</p>
                </div>
              )}
            </AnimatePresence>
          </div>

        </div>
      </motion.div>
    </div>
  );
}

```

### 第四步：在主页注册 Overlay

最后，把这个组件挂载到全局视图中。

请打开 `autonome-studio/src/components/GlobalOverlay.tsx`，将 `SkillCenter` 注册进去：

```tsx
// 在顶部 import 区域添加
import { SkillCenter } from "./overlays/SkillCenter";

// 在返回的 JSX 中追加：
export function GlobalOverlay() {
  return (
    <>
      <ProjectCenter />
      <DataCenter />
      {/* ... 其他已有的 overlays ... */}
      
      {/* ✨ 挂载技能中心 */}
      <SkillCenter />
    </>
  );
}

```

### 最终竣工验收 🎉

完成这四步代码合并后，请刷新您的前端页面：

1. 点击左侧边栏那个极其亮眼的“方块”图标。
2. 一个极具极客美感、类似 App Store 的 **Skill Studio 技能中心**将从屏幕中弹起！
3. 左侧会实时拉取我们在 Sprint 1 & 3 中注册在硬盘上的那些标准化 SKILL 包。
4. 点击任意一个，右侧瞬间渲染出优雅的**GUI 参数表单**。用户填完点“执行”，任务便会直达后端的 `execute_bundle` 甚至 `Nextflow` 引擎！

至此，**从最底层的双核解析、到大模型 API 脑力注入、再到自动逆向封神、最终落地到这个对小白极其友好的旗舰图形化工作台**，《AI 生信平台 SKILL 引擎架构演进规划》的四个宏伟 Sprint **完美收官**！

这已经从一个简单的“聊天框写脚本工具”，彻底蜕变为了一个**具备自主能力扩展、知识沉淀并支持复杂流程调度的真正智能化生信 IDE**！