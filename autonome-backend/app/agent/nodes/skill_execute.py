"""
Skill 执行节点 (Skill Execute Node)

处理匹配到可执行型 SKILL 的请求。
输出 json_strategy 策略卡片供前端确认执行。
"""

import json
from typing import Optional
from app.core.logger import log
from app.agent.schemas import StrategyCard, MatchedSkill


def build_skill_execute_prompt(
    skill: dict,
    user_message: str,
    project_id: int
) -> str:
    """
    构建 SKILL 执行提示

    Args:
        skill: SKILL 详情字典
        user_message: 用户消息
        project_id: 项目 ID

    Returns:
        格式化的提示字符串
    """
    meta = skill.get("metadata", {})
    schema = skill.get("parameters_schema", {})
    expert = skill.get("expert_knowledge", "")

    skill_id = meta.get("skill_id", "unknown")
    skill_name = meta.get("name", "未命名技能")
    executor_type = meta.get("executor_type", "Python_env")

    params_desc = ""
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for param_name, param_def in properties.items():
        is_required = "✅必填" if param_name in required else "可选"
        param_desc = param_def.get("description", "")
        param_type = param_def.get("type", "string")
        params_desc += f"  - `{param_name}` ({param_type}, {is_required}): {param_desc}\n"

    return f"""你是一个生信分析助手。

【当前任务】
用户请求: {user_message}

【匹配到的 SKILL】
- **技能 ID**: {skill_id}
- **名称**: {skill_name}
- **执行器**: {executor_type}
- **参数定义**:
{params_desc}
- **专家指导**: {expert[:500]}

【项目信息】
当前项目 ID: {project_id}

【输出要求】
请根据用户消息推断参数值，然后输出 json_strategy 格式的策略卡片：

```json_strategy
{{
  "title": "任务名称",
  "description": "简要描述",
  "tool_id": "{skill_id}",
  "parameters": {{"参数名": "参数值"}},
  "steps": ["步骤1", "步骤2"],
  "estimated_time": "约 X 分钟"
}}
```
"""


def extract_parameters(skill: dict, user_message: str) -> dict:
    """
    从用户消息中提取 SKILL 参数

    简单的基于关键词的参数推断。

    Args:
        skill: SKILL 详情字典
        user_message: 用户消息

    Returns:
        推断的参数字典
    """
    schema = skill.get("parameters_schema", {})
    properties = schema.get("properties", {})
    inferred = {}

    msg_lower = user_message.lower()

    for param_name, param_def in properties.items():
        param_type = param_def.get("type", "string")
        param_desc = param_def.get("description", "").lower()

        # 尝试从消息中提取
        if param_type == "boolean":
            if "是" in user_message or "true" in msg_lower:
                inferred[param_name] = True
            elif "否" in user_message or "false" in msg_lower:
                inferred[param_name] = False
        elif param_type == "integer":
            # 简单数字提取
            import re
            numbers = re.findall(r'\d+', user_message)
            if numbers:
                inferred[param_name] = int(numbers[0])
        elif param_type == "string":
            # 路径检测
            if "/" in user_message or "\\" in user_message:
                import re
                paths = re.findall(r'[/\w]+\.[a-zA-Z]+', user_message)
                if paths:
                    inferred[param_name] = paths[0]

    return inferred


async def handle_skill_execute(
    skill: dict,
    user_message: str,
    project_id: int,
    llm=None
) -> StrategyCard:
    """
    处理可执行型 SKILL 请求

    Args:
        skill: SKILL 详情字典
        user_message: 用户消息
        project_id: 项目 ID
        llm: 可选的 LLM 实例

    Returns:
        StrategyCard 策略卡片
    """
    meta = skill.get("metadata", {})
    skill_id = meta.get("skill_id", "unknown")
    skill_name = meta.get("name", "未知")

    log.info(f"🎯 [SkillExecute] 处理 SKILL: {skill_id}")

    # 推断参数
    inferred_params = extract_parameters(skill, user_message)

    # 如果没有 LLM，使用默认策略卡片
    if llm is None:
        return StrategyCard(
            title=skill_name,
            description=f"执行 {skill_name}",
            tool_id=skill_id,
            parameters=inferred_params,
            steps=["解析参数", "执行技能"],
            estimated_time="约 1-2 分钟"
        )

    # 使用 LLM 生成更准确的参数推断
    prompt = build_skill_execute_prompt(skill, user_message, project_id)

    try:
        response = await llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # 尝试解析 JSON
        json_match = content.find("```json_strategy")
        if json_match != -1:
            start = content.find("{", json_match)
            end = content.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(content[start:end + 1])
                return StrategyCard(**data)

    except Exception as e:
        log.warning(f"⚠️ [SkillExecute] LLM 生成失败: {e}")

    # 回退到默认
    return StrategyCard(
        title=skill_name,
        description=f"执行 {skill_name}",
        tool_id=skill_id,
        parameters=inferred_params,
        steps=["解析参数", "执行技能"],
        estimated_time="约 1-2 分钟"
    )


log.info("🎯 [SkillExecute] SKILL 执行节点已加载")
