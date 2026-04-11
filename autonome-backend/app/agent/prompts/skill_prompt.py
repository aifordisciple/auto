"""
SKILL 相关提示词模板

将 SKILL 信息格式化为提示词，供 Claude Code 参考。

设计理念：
- 简洁呈现：只展示关键信息
- 按相关度排序：优先展示推荐技能
- 清晰的参数说明：便于 Claude Code 理解和调用
"""

from typing import List, Dict, Any, Optional


def _get_skill_id(skill: Any) -> str:
    """获取技能 ID（兼容字典和对象）"""
    if isinstance(skill, dict):
        return skill.get("skill_id", skill.get("metadata", {}).get("skill_id", ""))
    return getattr(skill, "skill_id", "")


def format_skill_for_prompt(skill: Any, index: int = 1) -> str:
    """
    格式化单个 SKILL 供提示词使用

    Args:
        skill: SKILL 信息（可以是字典或对象）
        index: 序号

    Returns:
        格式化的 SKILL 描述
    """
    lines = []

    # 处理字典或对象两种格式
    if isinstance(skill, dict):
        metadata = skill.get("metadata", {})
        skill_id = metadata.get("skill_id", skill.get("skill_id", "unknown"))
        name = metadata.get("name", skill.get("name", "未命名技能"))
        description = metadata.get("description", skill.get("description", "暂无描述"))
        executor_type = metadata.get("executor_type", "Python_env")
    else:
        # 对象格式（如 TempSkill 或 SkillAsset）
        skill_id = getattr(skill, "skill_id", "unknown")
        name = getattr(skill, "name", "未命名技能")
        description = getattr(skill, "description", "暂无描述")
        executor_type = getattr(skill, "executor_type", "Python_env")
        metadata = {}

    lines.append(f"### {index}. {name}")
    lines.append(f"- **skill_id**: `{skill_id}`")
    lines.append(f"- **描述**: {description}")
    lines.append(f"- **执行器**: {executor_type}")

    # 参数定义
    params = metadata.get("parameters", []) if isinstance(metadata, dict) else []
    if params:
        lines.append("- **参数**:")
        for param in params[:5]:  # 最多显示 5 个参数
            param_name = param.get("name", param.get("key", ""))
            param_desc = param.get("description", "")
            required = param.get("required", False)
            req_mark = "*" if required else ""
            lines.append(f"  - `{param_name}`{req_mark}: {param_desc}")

    return "\n".join(lines)


def build_skill_catalog(
    skills: List[Any],
    recommendations: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    构建 SKILL 目录提示词

    Args:
        skills: 可用 SKILL 列表（可以是字典或对象）
        recommendations: 推荐的 SKILL（带评分）

    Returns:
        格式化的 SKILL 目录
    """
    if not skills and not recommendations:
        return ""

    lines = []
    lines.append("## 可用技能 (SKILL)")
    lines.append("")
    lines.append("以下是您可以直接调用的技能，如果适合用户需求，请输出对应的 json_strategy：")
    lines.append("")

    # 推荐技能（优先展示）
    if recommendations:
        lines.append("### 推荐技能")
        lines.append("")
        for i, rec in enumerate(recommendations[:3], 1):  # 最多 3 个推荐
            skill = rec.get("skill", {})
            score = rec.get("score", 0)
            reasons = rec.get("reasons", [])

            lines.append(format_skill_for_prompt(skill, i))

            if score > 0:
                lines.append(f"- **匹配度**: {score:.0%}")
            if reasons:
                lines.append(f"- **推荐理由**: {'; '.join(reasons[:2])}")

            lines.append("")

    # 其他可用技能
    other_skills = []
    if skills:
        recommended_ids = set()
        if recommendations:
            for rec in recommendations:
                skill = rec.get("skill", {})
                skill_id = _get_skill_id(skill)
                if skill_id:
                    recommended_ids.add(skill_id)

        for skill in skills:
            skill_id = _get_skill_id(skill)
            if skill_id not in recommended_ids:
                other_skills.append(skill)

    if other_skills:
        lines.append("### 其他可用技能")
        lines.append("")
        for i, skill in enumerate(other_skills[:5], 1):  # 最多 5 个其他技能
            lines.append(format_skill_for_prompt(skill, i))
            lines.append("")

    # 使用说明
    lines.append("### 调用方式")
    lines.append("")
    lines.append("如果要使用某个技能，请在代码块后输出 json_strategy：")
    lines.append("")
    lines.append('```json_strategy')
    lines.append('{')
    lines.append('    "title": "技能调用标题",')
    lines.append('    "tool_id": "skill_id",  // 使用上面列出的 skill_id')
    lines.append('    "parameters": {')
    lines.append('        // 根据技能参数定义填写')
    lines.append('    }')
    lines.append('}')
    lines.append('```')

    return "\n".join(lines)


def format_skill_for_agent_context(skill: Dict[str, Any]) -> str:
    """
    格式化 SKILL 供 Agent 上下文使用（精简版）

    Args:
        skill: SKILL 信息

    Returns:
        精简的 SKILL 描述
    """
    metadata = skill.get("metadata", {})
    skill_id = metadata.get("skill_id", skill.get("skill_id", ""))
    name = metadata.get("name", skill.get("name", ""))

    return f"- `{skill_id}`: {name}"