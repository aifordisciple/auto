"""
知识型 SKILL 节点 (Knowledge Node)

处理匹配到知识型 SKILL（代码模式库）的请求。
参考代码模式生成代码，然后输出 json_strategy。
"""

import json
from typing import Optional
from app.core.logger import log


def build_knowledge_prompt(
    skill: dict,
    user_message: str,
    project_id: int
) -> str:
    """
    构建知识型 SKILL 参考提示

    Args:
        skill: 知识型 SKILL 详情
        user_message: 用户消息
        project_id: 项目 ID

    Returns:
        格式化的提示字符串
    """
    meta = skill.get("metadata", {})
    code_patterns = skill.get("code_patterns", [])
    expert = skill.get("expert_knowledge", "")

    skill_id = meta.get("skill_id", "unknown")
    skill_name = meta.get("name", "未命名知识库")
    tool_type = meta.get("tool_type", "python")

    # 构建代码模式示例
    patterns_md = ""
    for i, pattern in enumerate(code_patterns[:3]):  # 最多3个
        pattern_name = pattern.get("name", f"模式{i + 1}")
        pattern_code = pattern.get("code", "")

        # 截断过长代码
        if len(pattern_code) > 500:
            pattern_code = pattern_code[:500] + "\n    # ... (省略) ..."

        patterns_md += f"\n### 模式 {i + 1}: {pattern_name}\n```\n{pattern_code}\n```\n"

    return f"""你是一个生信分析专家，擅长编写数据分析代码。

【用户请求】
{user_message}

【匹配到的知识库】
- **知识库 ID**: {skill_id}
- **名称**: {skill_name}
- **语言**: {tool_type}
- **专家指导**: {expert[:300]}

【相关代码模式】{patterns_md}

【项目信息】
当前项目 ID: {project_id}
输出路径: `/workspace/project_{project_id}/results/`

【输出要求】
1. 参考上述代码模式，生成满足用户需求的代码
2. 代码必须：
   - 使用 argparse (Python) 或 optparse (R)
   - 存入 `TASK_OUT_DIR` 环境变量目录
   - 包含详细注释
   - 有错误处理
3. 先输出代码块，然后输出 json_strategy 策略卡片

```json_strategy
{{
  "title": "任务名称",
  "description": "简要描述",
  "tool_id": "execute-python" 或 "execute-r",
  "parameters": {{"参数名": "参数值"}},
  "steps": ["步骤1", "步骤2"],
  "estimated_time": "约 X 分钟"
}}
```
"""


async def handle_knowledge_skill(
    skill: dict,
    user_message: str,
    project_id: int,
    llm=None
) -> dict:
    """
    处理知识型 SKILL 请求

    Args:
        skill: 知识型 SKILL 字典
        user_message: 用户消息
        project_id: 项目 ID
        llm: 可选的 LLM 实例

    Returns:
        包含 code 和 strategy_card 的字典
    """
    meta = skill.get("metadata", {})
    skill_id = meta.get("skill_id", "unknown")
    skill_name = meta.get("name", "未知")

    log.info(f"📚 [Knowledge] 处理知识库: {skill_id}")

    if llm is None:
        # 无 LLM 时返回基础响应
        return {
            "code": f"# 参考知识库 {skill_id} 编写代码\n# {skill_name}",
            "strategy_card": {
                "title": skill_name,
                "description": f"参考 {skill_name} 执行",
                "tool_id": "execute-python",
                "parameters": {},
                "steps": ["参考代码模式", "执行"],
                "estimated_time": "约 1 分钟"
            }
        }

    # 使用 LLM 生成代码
    prompt = build_knowledge_prompt(skill, user_message, project_id)

    try:
        response = await llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # 解析代码和策略卡片
        code = ""
        strategy_card = None

        # 提取代码块
        import re
        code_blocks = re.findall(r'```(?:python|r)?\s*\n(.*?)```', content, re.DOTALL)
        if code_blocks:
            code = code_blocks[0].strip()

        # 提取 JSON 策略卡片
        json_matches = re.findall(r'```json_strategy\s*\n(.*?)```', content, re.DOTALL)
        if json_matches:
            try:
                strategy_card = json.loads(json_matches[0])
            except json.JSONDecodeError:
                pass

        if not strategy_card:
            strategy_card = {
                "title": skill_name,
                "description": f"参考 {skill_name} 生成的代码",
                "tool_id": meta.get("tool_type", "python") == "r" and "execute-r" or "execute-python",
                "parameters": {},
                "steps": ["生成代码", "执行"],
                "estimated_time": "约 1 分钟"
            }

        return {
            "code": code,
            "strategy_card": strategy_card
        }

    except Exception as e:
        log.warning(f"⚠️ [Knowledge] 生成失败: {e}")
        return {
            "code": f"# 错误: {e}",
            "strategy_card": {
                "title": skill_name,
                "description": f"执行 {skill_name} 时出错",
                "tool_id": "execute-python",
                "parameters": {},
                "steps": ["错误"],
                "estimated_time": "约 1 分钟"
            }
        }


log.info("📚 [Knowledge] 知识型 SKILL 节点已加载")
