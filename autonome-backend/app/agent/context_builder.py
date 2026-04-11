"""
动态上下文构建器

根据用户消息动态检索相关 Skill 和上下文，避免全量注入导致响应慢。
"""

import re
from typing import Optional
from app.core.logger import log
from app.core.skill_parser import get_combined_skills, get_combined_skill_by_id

# 闲聊模式正则
CASUAL_PATTERNS = [
    r"^(你好|hi|hello|嗨|您好|hey)[\s,!。]*$",
    r"^(谢谢|thanks|thx)[\s,!。]*$",
    r"^(帮忙|help|帮帮我)[\s,!。]*$",
    r"^(请问|question|问一下)[\s,!。]*$",
    r"^(再见|bye|拜拜)[\s,!。]*$",
    r"^(好|好的|OK|ok|okay)[\s,!。]*$",
    r"^[/\\?]+$",
    r"^早上好|下午好|晚上好",
    r"^(最近|这几天|最近怎么样)",
]


def is_casual_chat(message: str) -> bool:
    """
    快速判断是否为闲聊/问候（无需 LLM 调用）

    Args:
        message: 用户消息

    Returns:
        True 表示闲聊
    """
    if not message:
        return False

    msg = message.strip().lower()

    # 空消息或纯符号
    if not msg or re.match(r"^[/\\?]+$", msg):
        return True

    # 匹配闲聊模式
    for pattern in CASUAL_PATTERNS:
        if re.match(pattern, msg, re.IGNORECASE):
            return True

    return False


def build_skill_catalog_md(
    user_id: int,
    user_message: str,
    top_k: int = 3
) -> tuple[str, list[dict]]:
    """
    根据用户消息动态构建 Skill 目录

    原来全量注入改为只返回 Top-K 最相关的 Skill。

    Args:
        user_id: 用户 ID
        user_message: 用户消息（用于匹配）
        top_k: 返回数量

    Returns:
        (skill_catalog_md, matched_skills)
    """
    try:
        available_skills = get_combined_skills(user_id)
        if not available_skills:
            return "*(暂无可用标准 SKILL)*\n", []

        # 分离知识型和可执行型
        knowledge_skills = [s for s in available_skills if s.get("is_knowledge_skill", False)]
        executable_skills = [s for s in available_skills if not s.get("is_knowledge_skill", False)]

        # 简单关键词匹配（避免调用 LLM）
        msg_lower = user_message.lower()
        scored_skills = []

        for s in executable_skills + knowledge_skills:
            meta = s.get("metadata", {})
            description = meta.get("description", "").lower()
            name = meta.get("name", "").lower()
            skill_id = meta.get("skill_id", "").lower()

            # 计算简单相关度
            score = 0
            keywords = msg_lower.split()

            for kw in keywords:
                if kw in description:
                    score += 1
                if kw in name:
                    score += 2
                if kw in skill_id:
                    score += 3

            if score > 0:
                scored_skills.append((score, s))

        # 按分数排序
        scored_skills.sort(key=lambda x: x[0], reverse=True)
        top_skills = [s for _, s in scored_skills[:top_k]]

        # 构建 Markdown
        skill_catalog_md = ""
        for s in top_skills:
            meta = s.get("metadata", {})
            schema = s.get("parameters_schema", {})
            expert = s.get("expert_knowledge", "")
            skill_id = meta.get("skill_id", "unknown")
            skill_name = meta.get("name", "未命名技能")
            executor_type = meta.get("executor_type", "Python_env")

            skill_catalog_md += f"### 模块 ID: `{skill_id}`\n"
            skill_catalog_md += f"- **名称**: {skill_name}\n"
            skill_catalog_md += f"- **执行器**: {executor_type}\n"
            skill_catalog_md += f"- **参数定义**: {schema.get('properties', {})}\n"
            skill_catalog_md += f"- **必填参数**: {schema.get('required', [])}\n"
            expert_preview = expert[:300] + "..." if len(expert) > 300 else expert
            skill_catalog_md += f"- **专家指导**: {expert_preview}\n\n"

        log.info(f"📦 [Context] 动态加载 {len(top_skills)}/{len(available_skills)} 个相关 Skill")
        return skill_catalog_md, top_skills

    except Exception as e:
        log.warning(f"⚠️ [Context] 加载 Skill 失败: {e}")
        return "*(暂无可用标准 SKILL)*\n", []


def build_knowledge_catalog_md(
    user_id: int,
    user_message: str,
    top_k: int = 3
) -> tuple[str, list[dict]]:
    """
    根据用户消息动态构建知识型 Skill 目录

    Args:
        user_id: 用户 ID
        user_message: 用户消息
        top_k: 返回数量

    Returns:
        (knowledge_catalog_md, matched_knowledge_skills)
    """
    try:
        available_skills = get_combined_skills(user_id)
        knowledge_skills = [s for s in available_skills if s.get("is_knowledge_skill", False)]

        if not knowledge_skills:
            return "*(暂无知识型 SKILL)*\n", []

        # 简单关键词匹配
        msg_lower = user_message.lower()
        scored_skills = []

        for s in knowledge_skills:
            meta = s.get("metadata", {})
            description = meta.get("description", "").lower()
            name = meta.get("name", "").lower()

            score = 0
            keywords = msg_lower.split()

            for kw in keywords:
                if kw in description:
                    score += 1
                if kw in name:
                    score += 2

            if score > 0:
                scored_skills.append((score, s))

        scored_skills.sort(key=lambda x: x[0], reverse=True)
        top_skills = [s for _, s in scored_skills[:top_k]]

        # 构建 Markdown
        knowledge_catalog_md = ""
        for s in top_skills:
            meta = s.get("metadata", {})
            code_patterns = s.get("code_patterns", [])
            skill_id = meta.get("skill_id", "unknown")
            skill_name = meta.get("name", "未命名技能")
            description = meta.get("description", "")
            tool_type = meta.get("tool_type", "python")
            primary_tool = meta.get("primary_tool", "")

            knowledge_catalog_md += f"### 知识库 ID: `{skill_id}`\n"
            knowledge_catalog_md += f"- **名称**: {skill_name}\n"
            knowledge_catalog_md += f"- **描述**: {description}\n"
            knowledge_catalog_md += f"- **语言**: {tool_type}\n"
            knowledge_catalog_md += f"- **核心工具**: {primary_tool}\n"
            knowledge_catalog_md += f"- **代码模式数**: {len(code_patterns)}\n"
            if code_patterns:
                knowledge_catalog_md += f"- **主要模式**: {', '.join([p.get('name', '') for p in code_patterns[:5]])}\n"
            knowledge_catalog_md += "\n"

        return knowledge_catalog_md, top_skills

    except Exception as e:
        log.warning(f"⚠️ [Context] 加载知识型 Skill 失败: {e}")
        return "*(暂无知识型 SKILL)*\n", []


def build_selected_skill_context(
    user_id: int,
    skill_id: str
) -> str:
    """
    构建预选 Skill 的上下文（当用户已选择特定 Skill 时）

    Args:
        user_id: 用户 ID
        skill_id: 技能 ID

    Returns:
        格式化的 Skill 上下文字符串
    """
    try:
        skill = get_combined_skill_by_id(user_id, skill_id)
        if not skill:
            return ""

        meta = skill.get("metadata", {})
        schema = skill.get("parameters_schema", {})
        expert = skill.get("expert_knowledge", "")

        params_desc = ""
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for param_name, param_def in properties.items():
            is_required = "✅必填" if param_name in required else "可选"
            param_desc = param_def.get("description", "")
            param_type = param_def.get("type", "string")
            params_desc += f"  - `{param_name}` ({param_type}, {is_required}): {param_desc}\n"

        context = f"""
<user_directive priority="highest">
【🚨 用户已预选指定技能，必须直接使用此技能响应请求！】
- **技能 ID**: `{skill_id}`
- **名称**: {meta.get('name', '未知')}
- **执行器**: {meta.get('executor_type', 'Python_env')}
- **参数定义** (严禁捏造参数名):
{params_desc}
- **专家指导**: {expert[:600] + "..." if len(expert) > 600 else expert}

**重要指令**：
1. 🚨 必须严格使用上面定义的参数名，绝对不能自己发明参数名！
2. 根据用户消息和上下文文件推断参数值
3. 在 json_strategy 中输出此 skill_id 和推断的 parameters
4. 参数名必须与上面列出的完全一致，区分大小写
</user_directive>
"""
        log.info(f"🎯 [Context] 注入预选技能: {skill_id}")
        return context

    except Exception as e:
        log.warning(f"⚠️ [Context] 获取预选技能详情失败: {e}")
        return ""


log.info("📦 [Context] 动态上下文构建器已加载")
