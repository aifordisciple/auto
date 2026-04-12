"""
技能参数表单构建节点 (Skill Form Builder Node)

处理 [UI_ACTION:REQUEST_SKILL_PARAMS] 指令，从 SKILL.md 读取参数 Schema，
组装 json_strategy 返回给前端渲染 StrategyCard。

V2 增强：
- 4 级参数预填策略：显式提及 > 实体提取 > 工作区状态 > 默认值
- 每个参数返回 {value, source, confidence} 供前端视觉标记
- 0 LLM Token 消耗，确定性路径
"""

import json
import os
import re
import uuid
from typing import Annotated, TypedDict, Optional

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langgraph.graph.message import add_messages

from app.core.logger import log
from app.core.skill_parser import get_combined_skill_by_id


class SkillFormBuilderState(TypedDict):
    """技能表单构建器状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    skill_id: str
    skill_params: dict
    physical_file_info: str


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
            "label": param_name,
            "type": type_mapping.get(param_type, "text"),
            "required": param_name in required_params,
            "default": default_value,
            "description": description
        })

    return result


# ==========================================
# V2: 基于上下文的参数自动预填
# ==========================================

def _prefill_parameters(
    parameters_list: list[dict],
    context: dict,
) -> list[dict]:
    """
    V2: 4 级参数预填策略

    优先级：显式提及 > 实体提取 > 工作区状态 > 默认值

    Args:
        parameters_list: 参数字段列表
        context: 上下文信息，包含：
            - user_message: 用户原始消息
            - workspace_files: 工作区文件列表
            - workspace_info: 工作区描述信息

    Returns:
        增强后的参数列表，每个参数包含 {value, source, confidence}
    """
    user_message = context.get("user_message", "")
    workspace_files = context.get("workspace_files", [])
    workspace_info = context.get("workspace_info", "")

    log.info(f"[SkillFormBuilder.V2] _prefill_parameters 开始: 参数数量={len(parameters_list)}, "
             f"user_message长度={len(user_message)}, "
             f"workspace_files数量={len(workspace_files)}, "
             f"workspace_info长度={len(workspace_info)}")

    enhanced_params = []
    for param in parameters_list:
        param_name = param["name"]
        param_type = param["type"]
        default_value = param.get("default")

        # 级别 1: 显式提及 — 用户消息中直接包含参数值
        explicit_value = _extract_explicit_mention(param_name, param_type, user_message)
        if explicit_value is not None:
            log.debug(f"[SkillFormBuilder.V2] 参数 '{param_name}' 匹配级别=explicit, value='{explicit_value}', confidence=1.0")
            enhanced_params.append({
                **param,
                "value": explicit_value,
                "source": "explicit",
                "confidence": 1.0,
            })
            continue

        # 级别 2: 实体提取 — 从用户消息中提取相关实体
        entity_value = _extract_entity(param_name, param_type, user_message, workspace_info)
        if entity_value is not None:
            log.debug(f"[SkillFormBuilder.V2] 参数 '{param_name}' 匹配级别=extracted, value='{entity_value}', confidence=0.8")
            enhanced_params.append({
                **param,
                "value": entity_value,
                "source": "extracted",
                "confidence": 0.8,
            })
            continue

        # 级别 3: 工作区状态 — 从工作区文件推断
        workspace_value = _infer_from_workspace(param_name, param_type, workspace_files, workspace_info)
        if workspace_value is not None:
            log.debug(f"[SkillFormBuilder.V2] 参数 '{param_name}' 匹配级别=workspace, value='{workspace_value}', confidence=0.6")
            enhanced_params.append({
                **param,
                "value": workspace_value,
                "source": "workspace",
                "confidence": 0.6,
            })
            continue

        # 级别 4: 默认值
        if default_value is not None:
            log.debug(f"[SkillFormBuilder.V2] 参数 '{param_name}' 匹配级别=default, value='{default_value}', confidence=0.3")
            enhanced_params.append({
                **param,
                "value": default_value,
                "source": "default",
                "confidence": 0.3,
            })
            continue

        # 无值可填
        log.debug(f"[SkillFormBuilder.V2] 参数 '{param_name}' 匹配级别=null, 无可用值, confidence=0.0")
        enhanced_params.append({
            **param,
            "value": None,
            "source": "null",
            "confidence": 0.0,
        })

    return enhanced_params


def _extract_explicit_mention(param_name: str, param_type: str, user_message: str) -> Optional[str]:
    """级别 1: 从用户消息中提取显式提及的参数值"""
    # 常见模式: "参数名=值" 或 "参数名: 值"
    patterns = [
        rf'{param_name}\s*[=:]\s*([^\s,，]+)',
        rf'--{param_name}\s+([^\s,，]+)',
        rf'-{param_name[0]}\s+([^\s,，]+)',  # 短选项
    ]
    for pattern in patterns:
        match = re.search(pattern, user_message, re.IGNORECASE)
        if match:
            value = match.group(1).strip('"\'')
            log.debug(f"[SkillFormBuilder.V2] _extract_explicit_mention 命中: param_name='{param_name}', value='{value}', pattern='{pattern}'")
            return value
    return None


def _extract_entity(param_name: str, param_type: str, user_message: str, workspace_info: str) -> Optional[str]:
    """级别 2: 从用户消息中提取相关实体"""
    # 文件路径提取
    if any(kw in param_name.lower() for kw in ["file", "path", "input", "数据", "文件"]):
        # 匹配 /workspace/... 或 uploads/... 路径
        file_patterns = [
            r'/workspace/[^\s\]\)\}]+\.\w+',
            r'uploads/[^\s\]\)\}]+\.\w+',
            r'[^\s\]\)\}]+\.(csv|tsv|txt|h5ad|fastq|bam|fq|bed|gff|vcf)',
        ]
        for pattern in file_patterns:
            match = re.search(pattern, user_message)
            if match:
                value = match.group(0)
                log.debug(f"[SkillFormBuilder.V2] _extract_entity 命中(文件路径): param_name='{param_name}', value='{value}'")
                return value

    # 数值提取
    if param_type == "number":
        num_match = re.search(r'\b(\d+\.?\d*)\b', user_message)
        if num_match:
            value = num_match.group(1)
            log.debug(f"[SkillFormBuilder.V2] _extract_entity 命中(数值): param_name='{param_name}', value='{value}'")
            return value

    return None


def _infer_from_workspace(param_name: str, param_type: str, workspace_files: list, workspace_info: str) -> Optional[str]:
    """级别 3: 从工作区状态推断参数值"""
    # 如果参数是文件路径，尝试从工作区找匹配的文件
    if any(kw in param_name.lower() for kw in ["file", "path", "input", "数据", "文件"]):
        # 常见生信文件扩展名
        bio_extensions = {".csv", ".tsv", ".txt", ".h5ad", ".fastq", ".bam", ".fq", ".bed", ".gff", ".vcf"}
        for f in workspace_files:
            if any(f.lower().endswith(ext) for ext in bio_extensions):
                log.debug(f"[SkillFormBuilder.V2] _infer_from_workspace 命中: param_name='{param_name}', value='{f}'")
                return f
    return None


async def skill_form_builder_node(state: SkillFormBuilderState) -> dict:
    """
    技能参数表单构建节点入口

    V2: 当 Router 拦截到 [UI_ACTION:REQUEST_SKILL_PARAMS] 指令时调用。
    从 SKILL.md 读取参数 Schema，使用 4 级预填策略填充参数，
    组装 json_strategy 返回给前端。

    Args:
        state: SkillFormBuilderState，包含 messages, skill_id

    Returns:
        dict: 包含 messages（带有 json_strategy）
    """
    messages = state.get("messages", [])
    skill_id = state.get("skill_id", "")
    physical_file_info = state.get("physical_file_info", "")

    if not skill_id:
        log.warning("📋 [SkillFormBuilder] 未提供 skill_id")
        return {
            "messages": [AIMessage(content="错误：未提供技能 ID")]
        }

    # 1. 从 SKILL.md 读取技能定义
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

    # V2: 使用 4 级预填策略
    user_message = ""
    if messages:
        last_msg = messages[-1]
        user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    # 从 physical_file_info 提取工作区文件列表
    workspace_files = []
    if physical_file_info:
        for line in physical_file_info.strip().split("\n"):
            line = line.strip()
            if line.startswith("- "):
                # 提取文件路径
                file_match = re.search(r'(\S+\.\w+)', line)
                if file_match:
                    workspace_files.append(file_match.group(1))

    context = {
        "user_message": user_message,
        "workspace_files": workspace_files,
        "workspace_info": physical_file_info,
    }
    enhanced_params = _prefill_parameters(parameters_list, context)

    # V2: 统计各级别预填数量
    source_counts = {}
    for p in enhanced_params:
        src = p.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
    log.info(f"[SkillFormBuilder.V2] 预填结果统计: 总参数={len(enhanced_params)}, "
             f"explicit={source_counts.get('explicit', 0)}, "
             f"extracted={source_counts.get('extracted', 0)}, "
             f"workspace={source_counts.get('workspace', 0)}, "
             f"default={source_counts.get('default', 0)}, "
             f"null={source_counts.get('null', 0)}")

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

    # V2: 使用增强参数（包含 source 和 confidence）
    strategy_data = {
        "title": skill_name,
        "description": skill_description,
        "task_summary": f"使用 {skill_name} 进行分析",
        "tool_id": skill_id,
        "parameters": {
            p["name"]: p.get("value", p.get("default"))
            for p in enhanced_params
            if p.get("value") is not None or p.get("default") is not None
        },
        "steps": default_steps,
        "estimated_time": estimated_time,
        # V2: 完整的增强参数列表（含 source/confidence 供前端视觉标记）
        "parameters_schema": enhanced_params,
    }

    # 4. 序列化为 json_strategy 代码块
    output_content = f"""```json_strategy\n{json.dumps(strategy_data, ensure_ascii=False, indent=2)}\n```"""

    log.info(f"📋 [SkillFormBuilder] 为技能 {skill_id} 生成了参数表单（V2 预填）")

    return {"messages": [AIMessage(content=output_content)]}


log.info("📋 [SkillFormBuilder] 技能参数表单构建节点已加载")
