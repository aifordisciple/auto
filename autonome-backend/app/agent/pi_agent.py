"""
PI Agent (Principal Investigator Agent) 模块

负责复杂任务的宏观规划，生成 DAG 蓝图。
与主 Agent 分离，专注于任务拆解和依赖分析。

升级说明 (2026-03-21):
- 新增专家委员会模式（4+1 生信专家并行规划）
- 支持三种规划模式：SINGLE_AGENT / DUAL_AGENT / FULL_PARALLEL
- 保留原有单 Agent 实现作为降级方案
"""

from typing import Annotated, Optional, Dict, Any, List, Literal
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
import json

from app.core.logger import log
from app.tools.probe_tools import peek_tabular_data, scan_workspace

# 导入专家委员会规划模块
from app.agent.planning_coordinator import (
    PlanningCoordinator,
    PlanningContext,
    PlanningMode,
    execute_planning
)


class PIState(dict):
    """PI Agent 状态"""
    messages: list
    project_context: str
    user_request: str
    blueprint: Optional[Dict[str, Any]] = None


def build_pi_agent(
    api_key: str,
    base_url: str,
    model_name: str,
    project_id: int,
    project_context: str,
    available_skills: str = ""
):
    """
    构建 PI Agent - 专注于复杂任务规划和 DAG 蓝图生成

    Args:
        api_key: LLM API Key
        base_url: LLM Base URL
        model_name: 模型名称
        project_id: 项目 ID
        project_context: 项目上下文信息（文件树、用户选择的文件等）
        available_skills: 可用的 SKILL 列表（Markdown 格式）

    Returns:
        编译后的 PI Agent
    """
    actual_api_key = api_key if (api_key and api_key.strip() != "") else "ollama-local"

    llm = ChatOpenAI(
        api_key=actual_api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,
        streaming=True,
        max_retries=2,
        max_tokens=128000  # 增大 token 限制，支持复杂任务蓝图生成
    )

    log.info(f"🧠 [PI Agent] 构建 - Model: {model_name}, Project: {project_id}")

    # PI Agent 专用 Prompt - 专注于任务规划和 DAG 生成
    system_prompt = f"""你是 Autonome 生信分析平台的首席规划专家（Principal Investigator），专门负责复杂任务的宏观规划和 DAG 蓝图生成。

【你的角色】
你是一位资深的生物信息学 PI，擅长：
1. 理解用户的研究目标和分析需求
2. 将复杂需求拆解为可执行的步骤
3. 分析步骤之间的依赖关系
4. 生成结构化的 DAG 执行蓝图

【当前项目上下文】
{project_context}

【可用 SKILL 库】
{available_skills if available_skills else "暂无预置 SKILL，将使用 Live Coding 模式"}

【你的工具】
1. 🔍 peek_tabular_data: 预览表格数据结构
2. 🔍 scan_workspace: 扫描目录结构

【任务拆解铁律】
1. **颗粒度要细**：每个 Task 只做一件事
2. **上下文传递**：下游的 expected_input = 上游的 expected_output
3. **探针先行**：DAG 第一个节点通常是探针任务
4. **明确路径**：所有输入输出路径必须完整明确
5. **工具匹配**：根据任务类型选择合适的工具

【蓝图输出格式】
当用户提出复杂任务时，你必须输出 json_blueprint 格式的蓝图：

```json_blueprint
{{
  "project_goal": "任务总体目标描述",
  "is_complex_task": true,
  "tasks": [
    {{
      "task_id": "task_1",
      "name": "数据探查",
      "tool": "peek_tabular_data",
      "depends_on": [],
      "expected_input": "/workspace/project_X/raw_data/matrix.tsv",
      "expected_output": null,
      "instruction": "调用探针预览数据结构，确认表头和维度"
    }},
    {{
      "task_id": "task_2",
      "name": "质控过滤",
      "tool": "execute_python_code",
      "depends_on": ["task_1"],
      "expected_input": "/workspace/project_X/raw_data/matrix.tsv",
      "expected_output": "/workspace/project_X/results/filtered.tsv",
      "instruction": "根据探查结果过滤低质量样本"
    }}
  ]
}}
```

【任务复杂度判断标准】
- **复杂任务**（需要输出蓝图）：
  - 需要执行 3 个以上步骤
  - 步骤之间有依赖关系
  - 需要多个工具配合完成
  - 涉及完整分析流程（如 RNA-Seq 全流程、单细胞分析等）

- **简单任务**（直接输出策略卡片）：
  - 单步骤操作
  - 无依赖关系
  - 单一工具可完成

【工具选择指南】
| 任务类型 | 工具 |
|---------|------|
| 数据预览 | peek_tabular_data |
| 目录扫描 | scan_workspace |
| Python 分析 | execute_python_code |
| R 分析 | execute_r_code |
| SKILL 调用 | 使用 skill_id |

【路径规范】
- 输入路径：`/workspace/project_{project_id}/raw_data/文件名`
- 输出路径：`/workspace/project_{project_id}/results/任务名/文件名`
- 环境变量：脚本中必须使用 `TASK_OUT_DIR` 环境变量

【执行流程】
1. 分析用户需求，判断任务复杂度
2. 如果是复杂任务，输出 json_blueprint
3. 如果是简单任务，建议用户使用主 Agent
4. 确保蓝图中所有路径和依赖关系正确
"""

    # PI Agent 只需要探针工具
    tools = [peek_tabular_data, scan_workspace]

    agent = create_react_agent(llm, tools=tools, prompt=system_prompt)

    return agent


async def generate_blueprint(
    user_request: str,
    api_key: str,
    base_url: str,
    model_name: str,
    project_id: int,
    project_context: str,
    available_skills: str = "",
    use_expert_committee: bool = True,
    force_planning_mode: Optional[str] = None
) -> Dict[str, Any]:
    """
    生成 DAG 蓝图

    Args:
        user_request: 用户请求
        api_key: LLM API Key
        base_url: LLM Base URL
        model_name: 模型名称
        project_id: 项目 ID
        project_context: 项目上下文
        available_skills: 可用 SKILL 列表
        use_expert_committee: 是否使用专家委员会模式（默认 True）
        force_planning_mode: 强制规划模式（"single" / "dual" / "full"）

    Returns:
        蓝图字典或错误信息
    """
    log.info(f"🧠 [PI Agent] 开始生成蓝图 - 请求: {user_request[:100]}...")
    log.info(f"🧠 [PI Agent] 专家委员会模式: {use_expert_committee}, 强制模式: {force_planning_mode}")

    # ========================================
    # 专家委员会模式（推荐）
    # ========================================
    if use_expert_committee:
        log.info(f"🎯 [PI Agent] 使用专家委员会模式")

        llm_config = {
            "api_key": api_key,
            "base_url": base_url,
            "model_name": model_name
        }

        try:
            result = await execute_planning(
                user_request=user_request,
                llm_config=llm_config,
                project_id=project_id,
                project_context=project_context,
                available_skills=available_skills,
                force_mode=force_planning_mode
            )

            if result.get("status") in ["success", "success_with_degradation"]:
                return {
                    "status": result["status"],
                    "blueprint": result.get("blueprint"),
                    "metadata": result.get("metadata", {}),
                    "raw_response": None
                }
            else:
                # 专家委员会失败，降级到单 Agent
                log.warning(f"⚠️ [PI Agent] 专家委员会失败，降级到单 Agent 模式")
                # 继续执行下面的单 Agent 逻辑

        except Exception as e:
            log.error(f"❌ [PI Agent] 专家委员会执行失败: {e}，降级到单 Agent")
            # 继续执行下面的单 Agent 逻辑

    # ========================================
    # 单 Agent 模式（原有实现，作为降级方案）
    # ========================================
    try:
        agent = build_pi_agent(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            project_id=project_id,
            project_context=project_context,
            available_skills=available_skills
        )

        # 构建请求
        prompt = f"""请分析以下用户需求，如果这是一个复杂任务，请输出 json_blueprint 格式的执行蓝图。

用户需求：
{user_request}

请根据需求复杂度决定输出格式：
- 如果是复杂任务（多步骤、有依赖），输出 json_blueprint
- 如果是简单任务，说明原因并建议使用简单策略卡片
"""

        messages = [{"role": "user", "content": prompt}]

        result = await agent.ainvoke({"messages": messages})

        # 提取响应
        final_message = result["messages"][-1]
        response_content = final_message.content if hasattr(final_message, 'content') else str(final_message)

        # 尝试提取蓝图 JSON
        blueprint = extract_blueprint_from_response(response_content)

        if blueprint:
            log.info(f"✅ [PI Agent] 蓝图生成成功 - {len(blueprint.get('tasks', []))} 个任务")
            return {
                "status": "success",
                "blueprint": blueprint,
                "raw_response": response_content,
                "metadata": {
                    "planning_mode": "single_agent",
                    "expert_committee_enabled": use_expert_committee
                }
            }
        else:
            log.warning(f"⚠️ [PI Agent] 未能提取有效蓝图")
            return {
                "status": "simple_task",
                "message": "该任务较为简单，建议使用简单策略卡片执行",
                "raw_response": response_content
            }

    except Exception as e:
        log.error(f"❌ [PI Agent] 蓝图生成失败: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


def extract_blueprint_from_response(response: str) -> Optional[Dict[str, Any]]:
    """
    从 PI Agent 响应中提取蓝图 JSON

    Args:
        response: Agent 响应文本

    Returns:
        解析后的蓝图字典，失败返回 None
    """
    import re

    if not response:
        return None

    # 尝试从代码块中提取
    blueprint_match = re.search(r'```json_blueprint\s*\n([\s\S]*?)```', response)
    if blueprint_match:
        try:
            data = json.loads(blueprint_match.group(1))
            if data.get("is_complex_task") and data.get("tasks"):
                return data
        except json.JSONDecodeError as e:
            log.warning(f"⚠️ [PI Agent] 蓝图 JSON 解析失败: {e}")

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
        log.warning(f"⚠️ [PI Agent] 蓝图提取失败: {e}")

    return None


def is_complex_task(user_request: str) -> bool:
    """
    快速判断用户请求是否为复杂任务

    用于路由决策，快速判断是否需要 PI Agent

    Args:
        user_request: 用户请求文本

    Returns:
        True 表示复杂任务，需要 PI Agent
    """
    # 复杂任务关键词
    complex_keywords = [
        # 流程类
        "全流程", "完整分析", "pipeline", "流程", "端到端",
        # 多步骤类
        "然后", "接着", "之后", "首先", "其次", "最后",
        "步骤", "阶段", "依次", "顺序",
        # 分析类型
        "RNA-Seq", "rna-seq", "rnaseq", "转录组",
        "单细胞", "single-cell", "scRNA",
        "ChIP-Seq", "chip-seq",
        "ATAC-Seq", "atac-seq",
        "甲基化", "methylation",
        "全基因组", "WGS", "WES",
        # 具体流程
        "质控", "比对", "定量", "差异", "注释", "富集",
        "预处理", "标准化", "归一化",
        "降维", "聚类", "注释",
        # 文献相关
        "复刻", "复现", "重现", "文献", "Figure",
    ]

    request_lower = user_request.lower()

    # 检查关键词
    keyword_count = sum(1 for kw in complex_keywords if kw.lower() in request_lower)

    # 3个以上关键词视为复杂任务
    if keyword_count >= 3:
        return True

    # 检查是否包含明确的流程描述
    flow_indicators = ["第一步", "第二步", "第三步", "1.", "2.", "3."]
    if any(ind in user_request for ind in flow_indicators):
        return True

    return False


log.info("🧠 PI Agent 模块已加载（支持专家委员会模式）")