"""
L1 LLM 解构层 - 大模型结构化意图解构与任务图谱生成。

使用用户配置的 LLM（通过 get_thinking_llm_config 三级 fallback 解析），
将用户输入解构为 TaskDAG（有向无环图），支持多任务分解、
依赖标注和指代消解。

双模式：
- 本地模型（Ollama）: 采用原生异步客户端 (AsyncClient)，支持 think 模式控制和强制 JSON 输出。
- 第三方 API: with_structured_output (function calling)
"""
from typing import Any, Dict
import json
import ollama
from json_repair import repair_json

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.agent.router.schemas import TaskDAG, TaskNode, IntentType
from app.agent.router.context_builder import build_workspace_context, format_workspace_context_for_prompt
from app.core.logger import log
from app.utils.llm_config import get_thinking_llm_config, get_fast_llm_config, _is_local_model, _is_ollama


# L1 意图解构系统提示词（v4: 扩展意图触发场景 + 6 组边界规则 + ADHOC 兜底优先级）
L1_DECOMPOSER_PROMPT_TEMPLATE = """你是一个专业的意图解构器，负责将用户的自然语言输入解析为结构化的任务图谱（TaskDAG）。

## 可用意图类型（13 种原子意图）

| 意图 | 枚举值 | 触发场景 | 典型表述 | 不要混淆 |
|------|--------|----------|----------|----------|
| 工作流编排 | INTENT_WORKFLOW_ORCHESTRATE | 多步骤流程编排、Nextflow/Snakemake 流水线、多个技能串联、自动化 pipeline | "编排一个 RNA-seq 流程"、"用 Nextflow 把 FastQC 和 HISAT2 连起来" | 单技能执行(→EXPLICIT_EXEC)、写单脚本(→SKILL_FORGE) |
| 技能锻造 | INTENT_SKILL_FORGE | 创建/修改代码脚本、修改已有代码逻辑、重构代码、加功能 | "写一个 R 脚本"、"帮我加一段清洗逻辑"、"重构一下这个脚本" | 描述大纲(→GENERAL_CHAT)、单技能执行(→EXPLICIT_EXEC) |
| 显式执行 | INTENT_EXPLICIT_EXEC | 明确调用已注册技能（跑 FastQC、跑 Cell Ranger、跑 DESeq2），单工具执行 | "跑一遍 FastQC"、"用 DESeq2 算一下"、"调用 Cellpose" | 多技能串联(→WORKFLOW_ORCHESTRATE) |
| 版本控制 | INTENT_VERSION_CONTROL | 回滚/撤销、版本对比、历史查看、环境差异对比 | "回滚到昨天版本"、"对比两次运行结果"、"撤销操作" | 纯报错诊断(→DIAGNOSTIC_RECOVERY) |
| 视觉微调 | INTENT_VISUAL_PERCEPTION_AND_TWEAK | 配色/阈值/DPI/样式调整、图表格式修改、截图导出 | "换成 Nature 配色"、"DPI 改成 600"、"导出高清 PDF" | 数据分析(→DATA_PROBE/ADHOC) |
| 数据探查 | INTENT_DATA_PROBE | 数据查询/预览/统计、文件系统探索、数据结构检查 | "查看 h5ad 结构"、"有哪些文件"、"检查 NA 比例" | 文献提取(→LITERATURE_MINING) |
| 文献挖掘 | INTENT_LITERATURE_MINING | 从论文/文献/PDF 中提取信息、对比两篇文献、文献知识问答 | "这篇文献用了什么方法"、"提取 Table S1 数据"、"对比文献 A 和 B" | 普通知识问答(→GENERAL_CHAT) |
| 系统资产 | INTENT_SYSTEM_ASSET_OPS | 文件移动/删除/归档、计算节点/实例切换、积分/配额查询、环境打包/自定义镜像、数据库挂载/卸载、任务启停/取消 | "移动文件到 Raw_Data"、"切换高配实例"、"查积分"、"打包镜像"、"停掉任务" | 报错诊断(→DIAGNOSTIC_RECOVERY)、技能执行(→EXPLICIT_EXEC) |
| 团队协作 | INTENT_COLLABORATION | 共享/权限管理、分享链接、团队技能库、克隆工作区、导出审计日志 | "分享给李教授"、"生成分享链接"、"加入项目"、"发布到团队技能库" | 文件管理(→SYSTEM_ASSET_OPS) |
| 诊断恢复 | INTENT_DIAGNOSTIC_RECOVERY | 用户正在经历的真实报错/崩溃，需要诊断和修复 | "脚本挂了报 Error"、"OOMKilled"、"进程卡住了" | 假设性讨论(→GENERAL_CHAT)、修改代码修bug(→SKILL_FORGE) |
| 即席分析 | INTENT_ADHOC_INTERACTIVE_ANALYSIS | 用户提供数据文件+分析需求，但无匹配的预设技能，需要交互式探索分析 | "用这个 CSV 画个热图"、"算一下 GC 含量分布" | 有匹配技能(→EXPLICIT_EXEC)、写完整脚本(→SKILL_FORGE) |
| 通用问答 | INTENT_GENERAL_CHAT | 闲聊、概念解释、流程大纲、步骤列举、知识对比、假设性讨论 | "什么是 drop-out？"、"GATK WES 的 10 步大纲"、"如果遇到报错怎么办" | 需要执行(→SKILL_FORGE/WORKFLOW)、文献操作(→LITERATURE_MINING) |
| 系统宏 | INTENT_SYSTEM_MACRO | 系统命令(/status /help)、短确认(继续/确定/好) | "/status"、"继续"、"好的" | 非确认的短文本(→L1判断) |

**DATA_PROBE 子意图说明**：
- 当用户询问"有哪些文件"、"目录结构"、"项目文件"等文件系统探索类问题时，
  parameters 中必须设置 `probe_type: "workspace_scan"`，表示扫描工作区目录，无需 input_file
- 当用户询问"查看数据结构"、"预览文件"等需要指定文件的问题时，
  parameters 中需包含 `input_file`，表示探查特定文件

## ⚠️ 关键区分规则：6 组意图边界（必须严格遵守）

### 边界 1: WORKFLOW_ORCHESTRATE vs SKILL_FORGE vs EXPLICIT_EXEC

| 判断维度 | WORKFLOW_ORCHESTRATE | SKILL_FORGE | EXPLICIT_EXEC |
|---------|---------------------|-------------|---------------|
| 工具数量 | 多个工具/技能串联 | 单个脚本/工具 | 单个已注册技能 |
| 典型关键词 | 编排/流程/pipeline/Nextflow/Snakemake | 写脚本/修改代码/重构/加逻辑 | 跑/运行/调用+技能名 |
| 举例 | "用 Nextflow 连 FastQC 和 HISAT2" | "写一个 PCA 脚本"、"帮我加清洗逻辑" | "跑 FastQC"、"用 DESeq2 算" |

**关键判断**：
- "跑 ESTIMATE" / "跑 Cell Ranger" / "跑 Monocle3" → INTENT_EXPLICIT_EXEC（单工具执行，不是工作流）
- "写一个 Nextflow 脚本" → INTENT_WORKFLOW_ORCHESTRATE（Nextflow 是工作流引擎）
- "先跑 STAR 再跑 featureCounts 最后算 TPM" → INTENT_WORKFLOW_ORCHESTRATE（多步骤串联）

### 边界 2: DIAGNOSTIC_RECOVERY vs SKILL_FORGE vs GENERAL_CHAT

| 判断维度 | DIAGNOSTIC_RECOVERY | SKILL_FORGE | GENERAL_CHAT |
|---------|---------------------|-------------|--------------|
| 用户意图 | 诊断+修复运行时错误 | 修改代码逻辑/修 bug | 假设性讨论错误概念 |
| 典型表述 | "报错了"、"脚本挂了" | "帮我加清洗逻辑"、"修复这个 bug" | "如果遇到报错怎么办" |
| 举例 | "Python 报 ValueError" | "代码报 NaN error，帮我加过滤逻辑" | "遇到 OOMKilled 有几种思路" |

**关键判断**：
- 用户正在经历报错 + 要求修改代码 → INTENT_SKILL_FORGE（"帮我加逻辑修复报错"）
- 用户正在经历报错 + 要求诊断原因 → INTENT_DIAGNOSTIC_RECOVERY（"为什么报错了"）
- 用户只是假设性讨论 → INTENT_GENERAL_CHAT（"如果遇到报错怎么办"）

### 边界 3: SYSTEM_ASSET_OPS vs DIAGNOSTIC_RECOVERY vs EXPLICIT_EXEC

| 判断维度 | SYSTEM_ASSET_OPS | DIAGNOSTIC_RECOVERY | EXPLICIT_EXEC |
|---------|-----------------|---------------------|---------------|
| 核心动作 | 资源管理/文件管理/环境管理 | 诊断报错/修复环境 | 执行分析技能 |
| 典型表述 | 移动/删除/归档/挂载/切换节点/积分/镜像 | 报错/崩溃/诊断/日志 | 跑XX分析/用XX工具 |
| 举例 | "删掉 failed 文件"、"切高配实例" | "脚本报错了" | "跑 FastQC" |

**关键判断**：
- "帮我切到大内存节点" → INTENT_SYSTEM_ASSET_OPS（资源调度，不是执行分析）
- "停掉任务并删掉中间文件" → INTENT_SYSTEM_ASSET_OPS（任务控制+文件管理）

### 边界 4: ADHOC_INTERACTIVE_ANALYSIS vs DATA_PROBE vs SKILL_FORGE

| 判断维度 | ADHOC_INTERACTIVE_ANALYSIS | DATA_PROBE | SKILL_FORGE |
|---------|---------------------------|------------|-------------|
| 核心区别 | 有数据+要分析+无预设技能 | 查看数据结构/统计 | 写完整脚本 |
| 典型表述 | "用这个 CSV 画个图"、"算一下分布" | "查看数据结构"、"有多少行列" | "写个 Python 脚本" |
| 举例 | "画相关性热图" | "检查 NA 比例" | "写个 K-means 脚本" |

**关键判断**：
- 用户有文件 + 想做探索性分析 → INTENT_ADHOC_INTERACTIVE_ANALYSIS
- 用户只想查看/检查数据 → INTENT_DATA_PROBE
- 用户明确说"写脚本" → INTENT_SKILL_FORGE

### 边界 5: LITERATURE_MINING vs DATA_PROBE vs GENERAL_CHAT

| 判断维度 | LITERATURE_MINING | DATA_PROBE | GENERAL_CHAT |
|---------|-------------------|------------|--------------|
| 数据来源 | 论文/文献/PDF | 数据文件（h5ad/CSV 等） | 无特定数据源 |
| 典型表述 | "这篇文献"、"文章里"、"PDF 中" | "这个 h5ad"、"数据集里" | "XX 的原理是什么" |
| 举例 | "提取 Table S1 数据" | "查看 h5ad 结构" | "解释 UMAP 原理" |

**关键判断**：
- "总结这篇论文的流程" → INTENT_LITERATURE_MINING（不是 GENERAL_CHAT，因为有具体文献）
- "对比文献 A 和文献 B" → INTENT_LITERATURE_MINING
- "解释 XX 原理"（无文献来源）→ INTENT_GENERAL_CHAT

### 边界 6: COLLABORATION vs SYSTEM_ASSET_OPS

| 判断维度 | COLLABORATION | SYSTEM_ASSET_OPS |
|---------|--------------|-----------------|
| 核心动作 | 共享/权限/团队协作 | 文件管理/资源管理/环境管理 |
| 典型表述 | 分享/权限/协同/团队 | 移动/删除/节点/积分/镜像 |
| 举例 | "分享给李教授"、"发布到团队技能库" | "删掉文件"、"切换节点" |

**关键判断**：
- "把文件分享给 XX" → INTENT_COLLABORATION
- "把文件移动到 XX 文件夹" → INTENT_SYSTEM_ASSET_OPS
- "克隆工作区给实习生" → INTENT_COLLABORATION（涉及人员协作，不是纯资源管理）

## 工作区上下文

{workspace_context}

## 可用技能（与用户需求最相关的技能）

{available_skills}

## 指令

1. 分析用户输入，识别其中包含的一个或多个原子意图
2. 对于复杂查询，将其拆解为多个 TaskNode，按执行顺序排列
3. 如果多个任务之间有依赖关系，在 dependencies 中标注前置 task_id
4. 对指代词（"这个文件"、"上面的结果"等）进行消解，填入 resolved_assets
5. 从用户输入中提取关键参数，填入 parameters
6. 即席分析判定原则：
   - 只有当用户指令包含具体数据文件，且要求进行轻量级的探索性分析/可视化操作，
     且技能库中无直接匹配的预设技能时，才路由为 INTENT_ADHOC_INTERACTIVE_ANALYSIS
   - 如果用户明确说"写代码/脚本"，路由为 INTENT_SKILL_FORGE（即使有数据文件）
   - 如果技能库中有匹配的技能（如 FastQC、Cell Ranger、DESeq2），路由为 INTENT_EXPLICIT_EXEC
   - 如果用户只是查看/检查数据结构，路由为 INTENT_DATA_PROBE
   - ADHOC 是兜底意图，不是默认首选：只有当 DATA_PROBE/SKILL_FORGE/EXPLICIT_EXEC 都不适用时才使用
7. 报错修复合意图判定原则：
   - 用户报告报错 + 要求诊断原因 → INTENT_DIAGNOSTIC_RECOVERY
   - 用户报告报错 + 要求修改代码修复 → INTENT_SKILL_FORGE
   - 用户报告报错 + 要求重新执行 → INTENT_EXPLICIT_EXEC（或双意图）
   - 用户报告报错 + 要求对比环境差异 → INTENT_VERSION_CONTROL
   - 判断关键：用户的核心诉求是"诊断"还是"修代码"还是"重新执行"

## 指代消解规则 (Coreference Resolution)

当用户输入包含指代词时，必须将其映射到工作区上下文中的具体实体，并填入 resolved_assets：

| 指代词模式 | 映射目标 | resolved_assets 填写 |
|-----------|---------|---------------------|
| "这个文件"、"这个数据"、"它" | 当前活跃文件 | [active_file ID] |
| "上面的结果"、"上次的结果" | 上次执行结果 | [result ID] |
| "那个技能"、"XX技能" | 可用技能中匹配项 | [skill_id] |
| "左侧文件"、"文件列表中的XX" | 最近文件中匹配项 | [file_id] |

**关键约束**：
1. 如果指代词可以消解，必须在 resolved_assets 中填入具体的 ID
2. 如果指代词无法消解（上下文中无匹配实体），保留 raw_instruction 中的原始指代词，不要猜测或编造 ID
3. 多个指代词指向同一实体时，resolved_assets 中只保留一个 ID

## 输出格式

返回一个 TaskDAG JSON 对象，格式如下：

```json
{{
  "nodes": [
    {{
      "task_id": "task_1",
      "intent": "INTENT_EXPLICIT_EXEC",
      "raw_instruction": "运行 FastQC 对 sample.fastq 进行质量控制",
      "dependencies": [],
      "resolved_assets": ["file_id_123"],
      "parameters": {{"skill_name": "fastqc", "input_file": "sample.fastq"}}
    }}
  ],
  "is_conditional": false
}}
```

对于简单查询，只需返回包含单个节点的 DAG。"""


class L1Classifier:
    """
    L1 LLM 结构化意图解构器。

    从用户中心配置解析 LLM，支持本地原生模型和第三方 API 双模式。
    将用户查询解构为 TaskDAG，支持多任务分解与依赖标注。
    保留类名 L1Classifier 以兼容已有导入，实际功能已升级为 DAG 解构器。
    """

    def __init__(self, session, user_id: str):
        """
        初始化解构器。

        程序说明：
        优先使用极速模型配置（get_fast_llm_config），
        未配置时自动回退到思考模型配置（get_thinking_llm_config）。
        构建针对第三方 API 的 ChatOpenAI 实例。
        本地模式的客户端将在具体调用时动态生成。

        Args:
            session: 数据库会话（用于 get_fast_llm_config 解析用户配置）
            user_id: 当前用户 ID
        """
        # 优先使用极速模型，未配置时回退到思考模型
        self.llm_config = get_fast_llm_config(session, user_id)
        self.is_local = _is_local_model(self.llm_config.base_url)

        # 关键区分：本地模型 ≠ Ollama 原生服务
        # host.docker.internal:8008/v1 是 OpenAI 兼容 API（vLLM/LiteLLM），不是 Ollama
        # 只有真正的 Ollama 服务才需要使用 ollama.AsyncClient 原生客户端
        # 其他本地服务（vLLM、LiteLLM 等）走 ChatOpenAI 兼容路径
        self.is_ollama = _is_ollama(self.llm_config.base_url)

        # 构建第三方 API 使用的 LLM 实例
        api_key = self.llm_config.api_key or "not-needed"
        self.primary_llm = ChatOpenAI(
            api_key=api_key,
            base_url=self.llm_config.base_url,
            model=self.llm_config.model_name,
            temperature=0.0
        )

        # 构建提示词模板 (仅供第三方 API 模式使用)
        # v3: 使用 L1_DECOMPOSER_PROMPT_TEMPLATE，包含 workspace_context 占位符
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", L1_DECOMPOSER_PROMPT_TEMPLATE),
            ("human", "User Query: {query}")
        ])

        log.info(
            f"[L1] 初始化解构器: model={self.llm_config.model_name}, "
            f"base_url={self.llm_config.base_url}, is_local={self.is_local}, "
            f"is_ollama={self.is_ollama}, source={self.llm_config.source}"
        )

    async def decompose(
        self,
        query: str,
        context: Dict[str, Any] = None,
        enable_think: bool = False,
        temperature: float = 0.0,
        skill_summary: str = ""
    ) -> TaskDAG:
        """
        执行意图解构，生成 TaskDAG。

        程序说明：
        作为解构任务的主入口，根据配置的 LLM 环境自动路由到对应的处理引擎。
        将用户查询解构为包含一个或多个 TaskNode 的 TaskDAG。
        包含参数系统，支持向下透传推理模式开关及采样温度设定。
        V2.0 新增 skill_summary 参数：向 L1 提示词注入与用户需求最相关的技能摘要，
        帮助 LLM 更准确地识别 INTENT_EXPLICIT_EXEC 意图并推断 skill_id。

        Args:
            query (str): 用户自然语言输入。
            context (Dict[str, Any]): 工作区上下文。默认值为 None。
            enable_think (bool): 是否开启大模型的推理思考模式。默认值为 False。
            temperature (float): 采样温度，控制输出稳定性。默认值为 0.0。
            skill_summary (str): 可用技能摘要文本，用于增强 L1 解构的结构化上下文。默认值为 ""。

        Returns:
            TaskDAG: 解构后的任务图谱，包含一个或多个 TaskNode
        """
        log.info(f"[L1] 正在调用 LLM 解构: query='{query[:50]}...'")

        # V2.1: 使用结构化上下文替代 str(context) 原始注入
        # build_workspace_context 将原始字典转换为 WorkspaceContext 模型
        # format_workspace_context_for_prompt 将模型格式化为 L1 提示词文本
        ws_ctx = build_workspace_context(context or {})
        workspace_context = format_workspace_context_for_prompt(ws_ctx)

        try:
            # 路由决策：只有真正的 Ollama 原生服务才走 ollama.AsyncClient 路径
            # 其他本地服务（vLLM、LiteLLM 等 host.docker.internal:xxxx/v1）走 ChatOpenAI 兼容路径
            if self.is_ollama:
                result = await self._decompose_with_json_mode(
                    query=query,
                    context=context,
                    enable_think=enable_think,
                    temperature=temperature,
                    skill_summary=skill_summary
                )
            else:
                result = await self._decompose_with_structured_output(
                    query=query,
                    workspace_context=workspace_context,
                    skill_summary=skill_summary
                )

            # 验证解构结果：至少包含一个节点
            if not result.nodes:
                log.warning("[L1] DAG 节点为空，降级为通用问答单节点")
                return TaskDAG(nodes=[
                    TaskNode(
                        task_id="task_1",
                        intent=IntentType.GENERAL_CHAT,
                        raw_instruction=query
                    )
                ])

            return result

        except Exception as e:
            log.error(f"[L1] 解构失败: {str(e)}")
            # 异常兜底：返回通用问答单节点 DAG
            return TaskDAG(nodes=[
                TaskNode(
                    task_id="task_1",
                    intent=IntentType.GENERAL_CHAT,
                    raw_instruction=query
                )
            ])

    async def _decompose_with_structured_output(
        self, query: str, workspace_context: str, skill_summary: str = ""
    ) -> TaskDAG:
        """
        第三方 API 模式：使用 with_structured_output (function calling)。

        程序说明：
        通过 LangChain 的 with_structured_output 方法，将 LLM 输出
        直接约束为 TaskDAG 结构，确保类型安全和格式正确。
        workspace_context 已在 decompose() 中格式化，此处直接传入模板。
        V2.0 新增 available_skills 占位符填充，注入与用户需求相关的技能摘要。
        """
        llm_with_schema = self.primary_llm.with_structured_output(TaskDAG)
        chain = self.prompt_template | llm_with_schema
        result = await chain.ainvoke({
            "workspace_context": workspace_context,
            "available_skills": skill_summary or "无可用技能",
            "query": query
        })
        return result

    async def _decompose_with_json_mode(
        self,
        query: str,
        context: Dict[str, Any],
        enable_think: bool = False,
        temperature: float = 0.0,
        skill_summary: str = ""
    ) -> TaskDAG:
        """
        本地模型模式：原生 Ollama API + JSON mode + 手动解析。

        程序说明：
        由于 Langchain 的 ChatOpenAI 依赖于兼容 /v1 端点，无法原生支持 think 参数控制，
        此方法改用 ollama.AsyncClient 直接发起请求，确保异步性能。
        通过参数系统传入的 enable_think，在 API 层面直接关闭深度推理模型 (如 Qwen3) 的思考过程。
        利用原生 format='json' 约束，确保输出结构稳定性。
        V2.0 新增 available_skills 占位符填充，注入与用户需求相关的技能摘要。

        Args:
            query (str): 用户查询。
            context (Dict[str, Any]): 上下文。
            enable_think (bool): 控制思考模式的参数。
            temperature (float): 采样温度参数。
            skill_summary (str): 可用技能摘要文本，用于增强 L1 解构的结构化上下文。默认值为 ""。
        """
        # 提取 Ollama 服务的基础 URL，移除可能存在的 /v1 兼容后缀
        host = self.llm_config.base_url
        if host and host.endswith('/v1'):
            host = host[:-3]
        if not host:
            host = "http://localhost:11434"

        # 构建原生异步客户端
        client = ollama.AsyncClient(host=host)

        # 在提示词中追加严格的 JSON 格式要求
        # 注意：使用原生客户端时，不再需要处理 LangChain ChatPromptTemplate 的双括号转义问题
        # v3: JSON 格式要求更新为 TaskDAG 结构
        json_instruction = (
            "\n\n请严格按照以下 JSON 格式输出，不要输出任何其他内容：\n"
            '{\n'
            '  "nodes": [\n'
            '    {\n'
            '      "task_id": "task_1",\n'
            '      "intent": "INTENT_GENERAL_CHAT|INTENT_WORKFLOW_ORCHESTRATE|INTENT_SKILL_FORGE|INTENT_EXPLICIT_EXEC|INTENT_VERSION_CONTROL|INTENT_VISUAL_PERCEPTION_AND_TWEAK|INTENT_DATA_PROBE|INTENT_LITERATURE_MINING|INTENT_SYSTEM_ASSET_OPS|INTENT_COLLABORATION|INTENT_DIAGNOSTIC_RECOVERY|INTENT_ADHOC_INTERACTIVE_ANALYSIS",\n'
            '      "raw_instruction": "用户的具体指令",\n'
            '      "dependencies": [],\n'
            '      "resolved_assets": [],\n'
            '      "parameters": {}\n'
            '    }\n'
            '  ],\n'
            '  "is_conditional": false\n'
            '}'
        )

        # V2.1: 使用结构化上下文替代 str(context) 原始注入
        # 与 decompose() 保持一致，确保本地模型和第三方 API 使用相同的上下文格式
        ws_ctx = build_workspace_context(context or {})
        workspace_context = format_workspace_context_for_prompt(ws_ctx)
        system_msg = L1_DECOMPOSER_PROMPT_TEMPLATE.format(
            workspace_context=workspace_context,
            available_skills=skill_summary or "无可用技能"
        ) + json_instruction
        user_msg = f"User Query: {query}"

        messages = [
            {'role': 'system', 'content': system_msg},
            {'role': 'user', 'content': user_msg}
        ]

        raw_content = ""
        try:
            # 发送 API 请求：利用原生参数控制思考模式与 JSON 格式
            response: Dict[str, Any] = await client.chat(
                model=self.llm_config.model_name,
                messages=messages,
                think=enable_think,
                format='json',
                options={
                    'temperature': temperature
                }
            )

            raw_content = response['message']['content'].strip()

            # 手动解析 JSON 响应为 TaskDAG
            repaired = repair_json(raw_content)
            parsed = json.loads(repaired)
            return TaskDAG(**parsed)

        except Exception as parse_err:
            log.warning(f"[L1] 本地 API 调用或 JSON 解析失败: {parse_err}, 原始响应: {raw_content[:200]}")
            return self._fallback_intent_from_text(raw_content)

    def _fallback_intent_from_text(self, text: str) -> TaskDAG:
        """
        从 LLM 原始文本响应中提取意图（JSON 解析失败时的兜底）。

        程序说明：
        当 JSON 解析失败时，遍历文本寻找匹配的 IntentType 枚举值，
        返回包含单个 TaskNode 的 TaskDAG 作为降级结果。
        支持 v2 旧枚举值到 v3 新枚举值的映射，确保向后兼容。
        """
        # v2 旧意图值 → v3 新 IntentType 的映射表，兼容旧模型输出
        legacy_intent_map: Dict[str, IntentType] = {
            "diagnostic": IntentType.DIAGNOSTIC_RECOVERY,
            "literature": IntentType.LITERATURE_MINING,
            "data_probe": IntentType.DATA_PROBE,
            "skill_forge": IntentType.SKILL_FORGE,
            "explicit_skill": IntentType.EXPLICIT_EXEC,
            "chat": IntentType.GENERAL_CHAT,
        }

        text_lower = text.lower()

        # 优先匹配 v3 新枚举值（INTENT_ 前缀格式）
        for intent in IntentType:
            if intent.value in text_lower:
                return TaskDAG(nodes=[
                    TaskNode(
                        task_id="task_1",
                        intent=intent,
                        raw_instruction=text[:200]
                    )
                ])

        # 其次匹配 v2 旧枚举值（兼容旧模型）
        for legacy_key, mapped_intent in legacy_intent_map.items():
            if legacy_key in text_lower:
                return TaskDAG(nodes=[
                    TaskNode(
                        task_id="task_1",
                        intent=mapped_intent,
                        raw_instruction=text[:200]
                    )
                ])

        # 最终兜底：通用问答
        return TaskDAG(nodes=[
            TaskNode(
                task_id="task_1",
                intent=IntentType.GENERAL_CHAT,
                raw_instruction=text[:200]
            )
        ])
