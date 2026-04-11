"""
Prompt 模板包

包含 Claude Code Agent 所需的各种提示词模板：
- 系统提示词
- SKILL 相关提示词
- 输出格式规范
"""

from app.agent.prompts.system_prompt import SYSTEM_PROMPT, build_context_prompt, build_full_prompt
from app.agent.prompts.skill_prompt import build_skill_catalog, format_skill_for_prompt

__all__ = [
    "SYSTEM_PROMPT",
    "build_context_prompt",
    "build_full_prompt",
    "build_skill_catalog",
    "format_skill_for_prompt",
]