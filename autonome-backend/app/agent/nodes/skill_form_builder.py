"""
技能参数表单构建节点 (Skill Form Builder Node)

处理 [UI_ACTION:REQUEST_SKILL_PARAMS] 指令，从 SKILL.md 读取参数 Schema，
组装 json_strategy 返回给前端渲染 StrategyCard。

0 LLM Token 消耗，确定性路径。
"""

import json
import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langgraph.graph.message import add_messages

from app.core.logger import log
from app.core.skill_parser import get_combined_skill_by_id


class SkillFormBuilderState(TypedDict):
    """技能表单构建器状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    skill_id: str
    skill_params: dict


def add_messages(left: list[BaseMessage], right: list[BaseMessage]) -> list[BaseMessage]:
    """消息合并"""
    return left + right


def _build_parameters_list(parameters_schema: dict) -> list[dict]:
    """
    将 JSON Schema 格式的参数转换为前端需要的格式

    Args:
        parameters_schema: JSON Schema 格式的参数定义

    Returns:
        前端需要的参数字段列表
    """
    properties = parameters_schema.get("properties", {})
    required_params = parameters_schema.get("required", [])

    result = []
    for param_name, param_def in properties.items():
        param_type = param_def.get("type", "string")
        description = param_def.get("description", "")
        default_value = param_def.get("default")

        # 类型映射：JSON Schema type -> 前端 type
        type_mapping = {
            "string": "text",
            "integer": "number",
            "number": "number",
            "boolean": "boolean",
            "array": "text",
            "object": "text"
        }

        result.append({
            "name": param_name,
            "label": param_name,  # TODO: 可以从 description 提取中文标签
            "type": type_mapping.get(param_type, "text"),
            "required": param_name in required_params,
            "default": default_value,
            "description": description
        })

    return result


async def skill_form_builder_node(state: SkillFormBuilderState) -> dict:
    """
    技能参数表单构建节点入口

    当 Router 拦截到 [UI_ACTION:REQUEST_SKILL_PARAMS] 指令时调用。
    从 SKILL.md 读取参数 Schema，组装 json_strategy 返回给前端。

    Args:
        state: SkillFormBuilderState，包含 messages, skill_id

    Returns:
        dict: 包含 messages（带有 json_strategy）
    """
    messages = state.get("messages", [])
    skill_id = state.get("skill_id", "")

    if not skill_id:
        log.warning("📋 [SkillFormBuilder] 未提供 skill_id")
        return {
            "messages": [AIMessage(content="错误：未提供技能 ID")]
        }

    # 1. 从 SKILL.md 读取技能定义
    # user_id 设为 0，因为系统预置技能不需要用户权限
    skill_def = get_combined_skill_by_id(user_id=0, skill_id=skill_id)

    if not skill_def:
        log.warning(f"📋 [SkillFormBuilder] 未找到技能: {skill_id}")
        error_content = f"错误：未找到技能 {skill_id}"
        return {"messages": [AIMessage(content=error_content)]}

    # 2. 提取元数据和参数 Schema
    metadata = skill_def.get("metadata", {})
    parameters_schema = skill_def.get("parameters_schema", {})
    expert_knowledge = skill_def.get("expert_knowledge", "")

    skill_name = metadata.get("name", "未命名技能")
    skill_description = metadata.get("description", "")
    executor_type = metadata.get("executor_type", "Python_env")
    timeout_seconds = metadata.get("timeout_seconds", 3600)

    # 3. 组装 json_strategy
    parameters_list = _build_parameters_list(parameters_schema)

    # 构建 steps 列表（基于 executor_type）
    if executor_type == "Python_env":
        default_steps = ["解析参数", "执行 Python 脚本", "收集结果"]
    elif executor_type == "R_env":
        default_steps = ["解析参数", "执行 R 脚本", "收集结果"]
    elif executor_type == "Logical_Blueprint":
        default_steps = ["解析参数", "执行 Nextflow 管道", "收集结果"]
    else:
        default_steps = ["解析参数", "执行技能", "收集结果"]

    # 估计时间（基于 timeout_seconds）
    if timeout_seconds >= 3600:
        estimated_time = "约 1 小时"
    elif timeout_seconds >= 1800:
        estimated_time = "约 30 分钟"
    elif timeout_seconds >= 600:
        estimated_time = "约 10 分钟"
    else:
        estimated_time = "约 5 分钟"

    strategy_data = {
        "title": skill_name,
        "description": skill_description,
        "task_summary": f"使用 {skill_name} 进行分析",
        "tool_id": skill_id,
        "parameters": {p["name"]: p["default"] for p in parameters_list if p.get("default") is not None},
        "steps": default_steps,
        "estimated_time": estimated_time,
        # 扩展字段：完整的参数列表供前端表单使用
        "parameters_schema": parameters_list
    }

    # 4. 序列化为 json_strategy 代码块
    output_content = f"""```json_strategy\n{json.dumps(strategy_data, ensure_ascii=False, indent=2)}\n```"""

    log.info(f"📋 [SkillFormBuilder] 为技能 {skill_id} 生成了参数表单")

    return {"messages": [AIMessage(content=output_content)]}


log.info("📋 [SkillFormBuilder] 技能参数表单构建节点已加载")
