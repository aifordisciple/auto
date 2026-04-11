"""
首席研究员 Agent (Chief PI Agent) - 4+1 专家委员会的仲裁核心

核心职责:
1. 阅读四份局部策略报告
2. 冲突解决与依赖补齐
3. DAG 拓扑连线（expected_output → expected_input）
4. 输出格式绝对正确的 json_blueprint

作为"仲裁者"，首席研究员不负责具体生信细节，而是专注于:
- 汇总各专家意见
- 解决专家间的潜在冲突
- 构建正确的任务依赖关系
- 生成结构完整的蓝图

Author: Autonome AI Team
Created: 2026-03-21
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json
import re
import time

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logger import log


class ChiefPIAgent:
    """
    🧙‍♂️ Agent E: 首席研究员 (The Chief PI / Orchestrator)

    核心职责: 阅读、仲裁、排版、连线
    - 接收四份局部策略报告
    - 冲突解决与依赖补齐
    - DAG 拓扑连线（expected_output → expected_input）
    - 输出格式绝对正确的 json_blueprint

    工作机制:
    ```
    if Agent D 要求画细胞类型比例图 AND Agent C 未规划注释步骤:
        自动补齐细胞注释依赖
    ```

    关键方法:
    - arbitrate(): 仲裁各专家意见，解决冲突
    - build_dag(): 构建 DAG 拓扑，确保依赖正确
    - generate_blueprint(): 输出最终蓝图
    - arbitrate_and_generate(): 仲裁 + 蓝图生成一体化
    """

    def __init__(
        self,
        llm_config: Dict[str, str],
        project_id: int,
        project_context: str,
        available_skills: str = ""
    ):
        """
        初始化首席研究员 Agent

        Args:
            llm_config: LLM 配置（api_key, base_url, model_name）
            project_id: 项目 ID
            project_context: 项目上下文
            available_skills: 可用 SKILL 列表
        """
        self.project_id = project_id
        self.project_context = project_context
        self.available_skills = available_skills

        actual_api_key = llm_config.get("api_key", "") or "ollama-local"

        self.llm = ChatOpenAI(
            api_key=actual_api_key,
            base_url=llm_config.get("base_url", ""),
            model=llm_config.get("model_name", "gpt-4"),
            temperature=0.1,  # 低温度确保输出稳定
            max_retries=2
        )

        log.info(f"🧙‍♂️ [ChiefPIAgent] 初始化完成 - Project: {project_id}")

    async def generate_blueprint(
        self,
        user_request: str,
        expert_reports: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        生成 DAG 蓝图 - 直接输出模式

        用于 SINGLE_AGENT 模式，不依赖专家报告

        Args:
            user_request: 用户请求
            expert_reports: 专家报告（可为 None）

        Returns:
            蓝图字典
        """
        log.info(f"🧙‍♂️ [ChiefPIAgent] 直接生成蓝图")

        # 构建专家报告摘要（如果有）
        expert_summary = ""
        if expert_reports:
            expert_summary = self._summarize_expert_reports(expert_reports)

        system_prompt = self._build_system_prompt(expert_summary)

        user_prompt = f"""请分析以下用户需求，生成 json_blueprint 格式的执行蓝图。

用户需求：
{user_request}

请确保：
1. 任务颗粒度要细，每个 Task 只做一件事
2. 明确依赖关系（depends_on）
3. 明确输入输出路径
4. 探针任务先行（如果需要）
"""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = await self.llm.ainvoke(messages)
            response_content = response.content if hasattr(response, 'content') else str(response)

            blueprint = self._extract_blueprint(response_content)

            if blueprint:
                log.info(f"✅ [ChiefPIAgent] 蓝图生成成功 - {len(blueprint.get('tasks', []))} 个任务")
                return blueprint
            else:
                log.warning(f"⚠️ [ChiefPIAgent] 未能提取有效蓝图，返回默认结构")
                return self._get_default_blueprint(user_request)

        except Exception as e:
            log.error(f"❌ [ChiefPIAgent] 蓝图生成失败: {e}")
            return self._get_default_blueprint(user_request, error=str(e))

    async def arbitrate_and_generate(
        self,
        user_request: str,
        expert_reports: Any
    ) -> Dict[str, Any]:
        """
        仲裁并生成蓝图 - 专家委员会模式

        这是 FULL_PARALLEL 模式的主入口
        1. 阅读各专家报告
        2. 检测并解决冲突
        3. 补齐缺失依赖
        4. 构建 DAG 拓扑
        5. 输出最终蓝图

        Args:
            user_request: 用户请求
            expert_reports: ExpertReports 对象，包含各专家报告

        Returns:
            最终蓝图字典
        """
        log.info(f"🧙‍♂️ [ChiefPIAgent] 开始仲裁并生成蓝图")

        start_time = time.time()

        # Step 1: 提取专家报告
        reports = self._extract_expert_reports(expert_reports)
        log.info(f"📊 [ChiefPIAgent] 收到 {len(reports)} 份专家报告")

        # Step 2: 检测冲突
        conflicts = self._detect_conflicts(reports)
        if conflicts:
            log.info(f"⚠️ [ChiefPIAgent] 检测到 {len(conflicts)} 个潜在冲突")
            # 冲突将在 LLM 调用中自动解决

        # Step 3: 生成蓝图
        system_prompt = self._build_system_prompt_with_experts(reports, conflicts)

        user_prompt = f"""请基于以下专家报告，生成 json_blueprint 格式的执行蓝图。

【用户原始需求】
{user_request}

【专家报告汇总】
{self._format_expert_reports_for_prompt(reports)}

【请完成以下任务】
1. 整合各专家建议
2. 解决潜在冲突（如有）
3. 补齐缺失的依赖步骤
4. 构建 DAG 拓扑
5. 输出完整的 json_blueprint

【冲突处理说明】
{self._format_conflicts_for_prompt(conflicts)}

【依赖补齐检查】
- 如果可视化专家要求画细胞类型比例图，但未规划注释步骤 → 自动补齐细胞注释
- 如果差异分析需要聚类结果，但未规划聚类步骤 → 自动补齐聚类
- 如果功能富集需要差异基因，但未规划差异分析 → 自动补齐 DEG 分析
"""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = await self.llm.ainvoke(messages)
            response_content = response.content if hasattr(response, 'content') else str(response)

            blueprint = self._extract_blueprint(response_content)

            if blueprint:
                # 添加元数据
                blueprint["metadata"] = blueprint.get("metadata", {})
                blueprint["metadata"]["expert_sources"] = list(reports.keys())
                blueprint["metadata"]["conflicts_resolved"] = len(conflicts)
                blueprint["metadata"]["arbitration_time_ms"] = int((time.time() - start_time) * 1000)

                log.info(f"✅ [ChiefPIAgent] 仲裁完成，蓝图生成成功 - {len(blueprint.get('tasks', []))} 个任务")
                return blueprint
            else:
                log.warning(f"⚠️ [ChiefPIAgent] 蓝图提取失败，使用专家报告构建默认蓝图")
                return self._build_blueprint_from_reports(user_request, reports)

        except Exception as e:
            log.error(f"❌ [ChiefPIAgent] 仲裁失败: {e}")
            return self._build_blueprint_from_reports(user_request, reports, error=str(e))

    def _build_system_prompt(self, expert_summary: str = "") -> str:
        """构建系统提示"""
        return f"""你是 Autonome 生信分析平台的首席研究员（Chief PI），专门负责复杂任务的宏观规划和 DAG 蓝图生成。

【你的角色】
你是一位资深的生物信息学 PI，擅长：
1. 理解用户的研究目标和分析需求
2. 将复杂需求拆解为可执行的步骤
3. 分析步骤之间的依赖关系
4. 生成结构化的 DAG 执行蓝图

【当前项目上下文】
{self.project_context}

【可用 SKILL 库】
{self.available_skills if self.available_skills else "暂无预置 SKILL，将使用 Live Coding 模式"}

{expert_summary}

【⚠️ 重要：基于真实数据规划】
规划前已执行数据探测，project_context 中包含真实的文件路径、列名、数据维度。
1. **必须使用探测到的真实列名**，不要猜测或编造列名
2. **必须使用探测到的真实文件路径**，确保文件存在
3. **根据数据维度选择参数**（如批次大小、迭代次数等）
4. 如果探测结果显示文件不存在或格式异常，在蓝图中标注警告

【任务拆解铁律】
1. **基于真实数据**：使用 project_context 中的探测结果，不要猜测列名
2. **颗粒度要细**：每个 Task 只做一件事
3. **上下文传递**：下游的 expected_input = 上游的 expected_output
4. **明确路径**：所有输入输出路径必须完整明确
5. **工具匹配**：根据任务类型选择合适的工具（SKILL ID 或 execute_python_code）

【路径规范】
- 输入路径：`/workspace/project_{self.project_id}/raw_data/文件名`
- 输出路径：`/workspace/project_{self.project_id}/results/任务名/文件名`
- 环境变量：脚本中必须使用 `TASK_OUT_DIR` 环境变量

【蓝图输出格式】
你必须输出以下格式的 json_blueprint：

```json_blueprint
{{
  "project_goal": "任务总体目标描述",
  "is_complex_task": true,
  "semantic_folder_name": "rnaseq_quality_control_pipeline",
  "tasks": [
    {{
      "task_id": "task_1",
      "name": "质控过滤",
      "tool": "execute_python_code",
      "depends_on": [],
      "expected_input": "/workspace/project_{self.project_id}/raw_data/matrix.tsv",
      "expected_output": "/workspace/project_{self.project_id}/results/qc/filtered.tsv",
      "instruction": "根据探测结果中的列名进行过滤（使用真实列名如 gene_id, sample_1 等）",
      "parameters": {{
        "min_umi": 1000,
        "max_mt_percent": 15
      }}
    }},
    {{
      "task_id": "task_2",
      "name": "差异分析",
      "tool": "execute_python_code",
      "depends_on": ["task_1"],
      "expected_input": "/workspace/project_{self.project_id}/results/qc/filtered.tsv",
      "expected_output": "/workspace/project_{self.project_id}/results/deg/diff_genes.tsv",
      "instruction": "使用过滤后的数据进行差异分析",
      "parameters": {{}}
    }}
  ],
  "metadata": {{
    "expert_sources": [],
    "planning_time_ms": 0,
    "conflicts_resolved": 0
  }}
}}
```

【语义目录命名规则】
semantic_folder_name 必须符合以下规范：
1. 使用 snake_case 格式（小写字母 + 下划线）
2. 包含任务的核心语义（如 rnaseq_qc、differential_expression、fastqc_analysis）
3. 不包含时间戳和 ID（由后端自动添加）
4. 长度控制在 30 字符以内
5. 只使用字母、数字、下划线（a-z0-9_）
6. 名称应能直观反映分析内容，让用户无需打开文件夹即可理解

【任务复杂度判断标准】
- **复杂任务**（需要输出蓝图）：
  - 需要执行 3 个以上步骤
  - 步骤之间有依赖关系
  - 需要多个工具配合完成
  - 涉及完整分析流程（如 RNA-Seq 全流程、单细胞分析等）
"""

    def _build_system_prompt_with_experts(
        self,
        reports: Dict[str, Dict],
        conflicts: List[Dict]
    ) -> str:
        """构建包含专家报告的系统提示"""
        base_prompt = self._build_system_prompt()

        expert_section = """

【专家委员会模式】
你正在仲裁 4 位专业规划专家的报告：
- 🕵️‍♂️ Agent A (DataQCPlanner): 数据与质控架构师
- 🧮 Agent B (AlgorithmStatistician): 算法与统计学专家
- 🧬 Agent C (SystemsBiologist): 系统生物学与注释专家
- 🎨 Agent D (VisualArtist): 出版级可视化设计师

你的任务是：
1. 整合各专家的专业建议
2. 解决专家间的潜在冲突
3. 补齐缺失的依赖步骤
4. 构建正确的 DAG 拓扑
5. 输出完整的执行蓝图

【仲裁原则】
- 优先采纳各领域专家的专业建议
- 当建议冲突时，以更保守/稳健的方案为准
- 确保所有必要步骤都被包含
- 确保依赖关系正确（上游输出 → 下游输入）
"""
        return base_prompt + expert_section

    def _summarize_expert_reports(self, expert_reports: Any) -> str:
        """汇总专家报告为文本摘要"""
        if not expert_reports:
            return ""

        summary = "【专家报告摘要】\n"

        if hasattr(expert_reports, 'get_successful_reports'):
            reports = expert_reports.get_successful_reports()
            for name, report in reports.items():
                summary += f"- {name}: {json.dumps(report, ensure_ascii=False)[:200]}...\n"

        return summary

    def _extract_expert_reports(self, expert_reports: Any) -> Dict[str, Dict]:
        """从 ExpertReports 对象提取报告字典"""
        reports = {}

        if hasattr(expert_reports, 'data_qc_report') and expert_reports.data_qc_report:
            reports['data_qc'] = expert_reports.data_qc_report
        if hasattr(expert_reports, 'algorithm_report') and expert_reports.algorithm_report:
            reports['algorithm'] = expert_reports.algorithm_report
        if hasattr(expert_reports, 'annotation_report') and expert_reports.annotation_report:
            reports['annotation'] = expert_reports.annotation_report
        if hasattr(expert_reports, 'visualization_report') and expert_reports.visualization_report:
            reports['visualization'] = expert_reports.visualization_report

        return reports

    def _detect_conflicts(self, reports: Dict[str, Dict]) -> List[Dict]:
        """
        检测专家报告间的潜在冲突

        冲突类型:
        1. 参数不一致（如不同专家建议不同的阈值）
        2. 步骤缺失（可视化需要注释但未规划）
        3. 方法冲突（不同专家建议不同方法）

        Args:
            reports: 专家报告字典

        Returns:
            冲突列表
        """
        conflicts = []

        # 检查：可视化需要细胞类型注释，但注释专家可能未规划
        if 'visualization' in reports and 'annotation' in reports:
            viz_report = reports['visualization']
            anno_report = reports['annotation']

            # 检查可视化计划中是否涉及细胞类型
            viz_plan = viz_report.get('visualization_plan', [])
            has_cell_type_viz = any(
                'cell_type' in str(v.get('group_by', [])) or 'cell_type' in v.get('type', '').lower()
                for v in viz_plan
            )

            anno_method = anno_report.get('annotation_strategy', {}).get('method', '')

            if has_cell_type_viz and not anno_method:
                conflicts.append({
                    "type": "missing_dependency",
                    "description": "可视化计划涉及细胞类型图，但未规划细胞注释步骤",
                    "affected_agents": ["visualization", "annotation"],
                    "resolution": "需要补齐细胞类型注释步骤"
                })

        # 检查：数据格式与算法参数的一致性
        if 'data_qc' in reports and 'algorithm' in reports:
            data_format = reports['data_qc'].get('data_format', '')
            if data_format and data_format != 'unknown':
                # 数据格式已知，检查算法参数是否匹配
                pass  # 可扩展更多检查

        return conflicts

    def _format_expert_reports_for_prompt(self, reports: Dict[str, Dict]) -> str:
        """格式化专家报告用于 Prompt"""
        formatted = ""

        agent_names = {
            'data_qc': '🕵️‍♂️ Agent A (数据与质控架构师)',
            'algorithm': '🧮 Agent B (算法与统计学专家)',
            'annotation': '🧬 Agent C (系统生物学专家)',
            'visualization': '🎨 Agent D (可视化设计师)'
        }

        for name, report in reports.items():
            agent_name = agent_names.get(name, name)
            formatted += f"\n### {agent_name}\n"
            formatted += f"```json\n{json.dumps(report, ensure_ascii=False, indent=2)}\n```\n"

        return formatted

    def _format_conflicts_for_prompt(self, conflicts: List[Dict]) -> str:
        """格式化冲突信息用于 Prompt"""
        if not conflicts:
            return "未检测到潜在冲突"

        formatted = ""
        for i, conflict in enumerate(conflicts, 1):
            formatted += f"\n冲突 {i}: {conflict['description']}\n"
            formatted += f"- 类型: {conflict['type']}\n"
            formatted += f"- 涉及专家: {', '.join(conflict['affected_agents'])}\n"
            formatted += f"- 建议解决方案: {conflict['resolution']}\n"

        return formatted

    def _extract_blueprint(self, response: str) -> Optional[Dict[str, Any]]:
        """
        从响应中提取蓝图 JSON

        支持多种格式:
        - ```json_blueprint ... ```
        - ```json ... ```
        - 直接 JSON 对象

        Args:
            response: LLM 响应文本

        Returns:
            解析后的蓝图字典，失败返回 None
        """
        if not response:
            return None

        # 尝试从 json_blueprint 代码块提取
        blueprint_match = re.search(r'```json_blueprint\s*\n([\s\S]*?)```', response)
        if blueprint_match:
            try:
                data = json.loads(blueprint_match.group(1))
                if data.get("is_complex_task") and data.get("tasks"):
                    return data
            except json.JSONDecodeError as e:
                log.warning(f"⚠️ [ChiefPIAgent] 蓝图 JSON 解析失败: {e}")

        # 尝试从 json 代码块提取
        json_match = re.search(r'```json\s*\n([\s\S]*?)```', response)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if data.get("is_complex_task") and data.get("tasks"):
                    return data
            except json.JSONDecodeError:
                pass

        # 尝试直接解析包含 is_complex_task 的 JSON
        try:
            start = response.find('{')
            while start != -1:
                depth = 0
                for i in range(start, len(response)):
                    if response[i] == '{':
                        depth += 1
                    elif response[i] == '}':
                        depth -= 1
                        if depth == 0:
                            json_str = response[start:i+1]
                            try:
                                data = json.loads(json_str)
                                if data.get("is_complex_task") and data.get("tasks"):
                                    return data
                            except:
                                pass
                            break
                start = response.find('{', start + 1)
        except Exception as e:
            log.warning(f"⚠️ [ChiefPIAgent] 蓝图提取失败: {e}")

        return None

    def _get_default_blueprint(self, user_request: str, error: str = "") -> Dict[str, Any]:
        """获取默认蓝图结构"""
        return {
            "project_goal": user_request[:200],
            "is_complex_task": True,
            "tasks": [
                {
                    "task_id": "task_1",
                    "name": "数据探查",
                    "tool": "peek_tabular_data",
                    "depends_on": [],
                    "expected_input": f"/workspace/project_{self.project_id}/raw_data/",
                    "expected_output": None,
                    "instruction": "预览数据结构，确认格式和维度",
                    "parameters": {}
                }
            ],
            "metadata": {
                "expert_sources": [],
                "error": error,
                "is_default": True
            }
        }

    def _build_blueprint_from_reports(
        self,
        user_request: str,
        reports: Dict[str, Dict],
        error: str = ""
    ) -> Dict[str, Any]:
        """
        从专家报告构建蓝图（当 LLM 调用失败时的降级方案）

        Args:
            user_request: 用户请求
            reports: 专家报告
            error: 错误信息

        Returns:
            蓝图字典
        """
        log.info(f"🔧 [ChiefPIAgent] 使用降级方案构建蓝图")

        tasks = []
        task_id = 1

        # 从数据质控报告构建上游任务
        if 'data_qc' in reports:
            dq_report = reports['data_qc']
            upstream_steps = dq_report.get('upstream_steps', [])

            for step in upstream_steps:
                tasks.append({
                    "task_id": f"task_{task_id}",
                    "name": step.get('name', f'步骤 {task_id}'),
                    "tool": step.get('tool', 'execute_python_code'),
                    "depends_on": [] if task_id == 1 else [f"task_{task_id - 1}"],
                    "instruction": step.get('description', ''),
                    "parameters": {}
                })
                task_id += 1

        # 如果没有任务，添加默认探针任务
        if not tasks:
            tasks.append({
                "task_id": "task_1",
                "name": "数据探查",
                "tool": "peek_tabular_data",
                "depends_on": [],
                "instruction": "预览数据结构",
                "parameters": {}
            })

        return {
            "project_goal": user_request[:200],
            "is_complex_task": True,
            "tasks": tasks,
            "metadata": {
                "expert_sources": list(reports.keys()),
                "error": error,
                "is_fallback": True
            }
        }


log.info("🧙‍♂️ ChiefPIAgent 模块已加载")