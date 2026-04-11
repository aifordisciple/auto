"""
系统提示词模板

定义 Claude Code Agent 的核心行为规范和输出格式要求。

设计理念：
- 简洁高效：避免冗长的提示词
- 明确输出格式：确保策略卡片可解析
- 生信专家角色：专注于生物信息分析
"""

from typing import Optional, List, Dict, Any


# ==========================================
# 核心系统提示词
# ==========================================

SYSTEM_PROMPT = """
你是 Autonome 生信分析平台的高级专家 Agent。

## 核心能力

1. **数据分析**：熟练掌握 Python/R 进行生物信息数据分析
2. **可视化**：生成出版级质量的图表
3. **流程编排**：设计复杂的分析流程

## 工作流程

当收到用户请求时：
1. 理解分析需求
2. 使用 Read/Bash/Glob/Grep 等工具探查数据
3. 编写分析代码
4. 输出策略卡片供用户确认

## 输出格式

完成分析后，**必须**输出策略卡片：

```json_strategy
{
    "title": "任务标题",
    "description": "任务描述",
    "tool_id": "execute-python",
    "parameters": {
        "code": "执行的代码",
        "input_files": ["输入文件列表"],
        "output_files": ["输出文件列表"]
    },
    "estimated_time": "预计执行时间"
}
```

## 重要规则

1. **禁止直接执行代码**：只能输出代码和策略卡片，等待用户确认
2. **先探查后分析**：处理数据文件前，先用工具探查文件结构
3. **详细注释**：代码中必须包含中文注释
4. **错误处理**：代码中包含适当的异常处理
"""


# ==========================================
# 上下文构建函数
# ==========================================

def build_context_prompt(
    project_dir: str,
    file_tree: str,
    selected_files: List[str],
    skill_recommendations: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    构建上下文提示词

    Args:
        project_dir: 项目目录路径
        file_tree: 项目文件树
        selected_files: 用户选择的文件
        skill_recommendations: SKILL 推荐内容
        conversation_history: 历史对话

    Returns:
        格式化的上下文提示词
    """
    parts = []

    # 项目上下文
    parts.append("<context>")
    parts.append(f"项目目录: {project_dir}")
    parts.append("")
    parts.append("<file_tree>")
    parts.append(file_tree)
    parts.append("</file_tree>")

    # 用户选择的文件
    if selected_files:
        parts.append("")
        parts.append("<selected_files>")
        for f in selected_files:
            parts.append(f"- {f}")
        parts.append("</selected_files>")

    parts.append("</context>")

    # SKILL 推荐
    if skill_recommendations:
        parts.append("")
        parts.append("<available_skills>")
        parts.append(skill_recommendations)
        parts.append("</available_skills>")

    # 历史对话
    if conversation_history:
        parts.append("")
        parts.append("<conversation_history>")
        for msg in conversation_history[-5:]:  # 只保留最近 5 条
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                parts.append(f"用户: {content[:200]}...")
            else:
                parts.append(f"助手: {content[:200]}...")
        parts.append("</conversation_history>")

    return "\n".join(parts)


def build_full_prompt(
    user_message: str,
    project_dir: str,
    file_tree: str,
    selected_files: List[str],
    skill_recommendations: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    task_mode: Optional[str] = None
) -> str:
    """
    构建完整的提示词

    Args:
        user_message: 用户消息
        project_dir: 项目目录
        file_tree: 文件树
        selected_files: 选择的文件
        skill_recommendations: SKILL 推荐
        conversation_history: 历史对话
        task_mode: 任务模式（complex 等）

    Returns:
        完整的提示词
    """
    parts = []

    # 系统提示词
    parts.append(SYSTEM_PROMPT)
    parts.append("")

    # 上下文
    context = build_context_prompt(
        project_dir=project_dir,
        file_tree=file_tree,
        selected_files=selected_files,
        skill_recommendations=skill_recommendations,
        conversation_history=conversation_history
    )
    parts.append(context)

    # 任务模式
    if task_mode == "complex":
        parts.append("")
        parts.append("<task_mode>")
        parts.append("这是一个复杂任务，请输出 json_blueprint 格式的执行蓝图。")
        parts.append("</task_mode>")

    # 用户请求
    parts.append("")
    parts.append("<user_request>")
    parts.append(user_message)
    parts.append("</user_request>")

    return "\n".join(parts)