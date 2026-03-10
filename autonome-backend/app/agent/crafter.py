"""
SKILL Crafter Agent - AI 智能锻造引擎

功能：将非结构化素材（代码、文献、文本指令）逆向提炼为标准技能包

三大铁律强制注入：
1. 参数自动化抽取 - 必须使用 argparse (Python) 或 optparse/commandArgs (R)
2. 强制保全与重写注释 - 详尽的中文块级注释和行级注释
3. 强制 TSV 格式输出 - 表格数据必须输出为 Tab 分割的 .tsv 格式
"""

import json
import re
from typing import Dict, Any, Optional

from langchain_openai import ChatOpenAI
from app.core.logger import log


def extract_crafted_skill(text: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 的回复中提取被 ***json_skill 包裹的结构化数据

    Args:
        text: LLM 返回的原始文本

    Returns:
        解析后的 JSON 字典，如果解析失败则返回 None
    """
    # 匹配 ***json_skill ... *** 格式
    pattern = r'\*\*\*json_skill\s*(.*?)\s*\*\*\*'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)

    if match:
        try:
            json_str = match.group(1).strip()
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            log.error(f"解析锻造技能 JSON 失败: {e}")
            return None

    # 尝试直接解析 JSON（如果模型没有使用包裹标记）
    try:
        # 尝试找到 JSON 对象
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group(0))
    except json.JSONDecodeError:
        pass

    return None


async def craft_skill_from_material(
    raw_material: str,
    api_key: str,
    base_url: str,
    model_name: str
) -> Dict[str, Any]:
    """
    智能锻造引擎 (Crafter Agent)：
    输入非结构化素材，输出标准化的技能资产配置（含Schema和重构后的代码）

    Args:
        raw_material: 原始素材（代码/指令/文献段落）
        api_key: OpenAI API Key
        base_url: API Base URL
        model_name: 模型名称

    Returns:
        锻造后的技能资产字典，包含：
        - name: 技能名称
        - description: 一句话简介
        - executor_type: 执行器类型 (Python_env/R_env)
        - parameters_schema: JSON Schema 格式的参数定义
        - expert_knowledge: 专家指导
        - script_code: 重构后的完整代码
        - dependencies: 依赖包列表
    """
    log.info("🔨 [Crafter Forge] 正在启动技能锻造炉...")

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,  # 保持极低的温度以保证代码严谨性
        max_tokens=4000
    )

    crafter_prompt = f"""你是 Autonome 系统的首席技能锻造师 (Skill Architect)。
你的任务是接收用户提供的【原始生信分析素材】（可能是一段写死的代码、一段文献的方法描述、或简单的自然语言指令），将其逆向提炼、重构为一个符合 Autonome 标准的【工业级可复用技能包】。

【原始素材】
{raw_material}

【🚨 锻造铁律与重构规范 (绝不可违反)】
无论原始代码多么糟糕，你重构输出的 `script_code` 必须严格满足以下"三大思想钢印"：

1. **参数自动化抽取**：找出原始代码中所有"应该被用户自定义的变量"（如：输入文件路径、P-value阈值、图表标题、颜色等），将它们抽取为 JSON Schema 参数。并在脚本中**强制使用 `argparse` (Python) 或 `optparse/commandArgs` (R) 接收这些参数，必须设置默认值！** 绝不允许在代码里写死任何特定的物理文件路径！

2. **强制保全与重写注释**：为重构后的代码加上极度详尽的中文块级注释和行级注释，解释每一步的生物学意义或数据转换逻辑。

3. **强制 TSV 格式输出**：如果该技能有表格数据落地，强行将输出逻辑修改为生成 Tab 分割的 `.tsv` 格式。如果是生成图片，强制设置英文标签。

【输出格式强制要求】
请直接输出一个严谨的 JSON 对象，并用 ***json_skill 包裹。JSON 结构必须完全符合以下定义：

***json_skill
{{
  "name": "这里写提炼出的技能名称（简明扼要，中文）",
  "description": "这里写一句话简介",
  "executor_type": "Python_env",  // 根据代码判断是 Python_env 还是 R_env
  "parameters_schema": {{
    "type": "object",
    "properties": {{
      "input_matrix": {{ "type": "string", "description": "输入表达矩阵路径", "default": "" }},
      "p_value": {{ "type": "number", "description": "显著性阈值", "default": 0.05 }}
    }},
    "required": ["input_matrix"]
  }},
  "expert_knowledge": "这里写几百字的专家指导，包括这个脚本的生物学原理、测试建议、以及参数调节建议。",
  "script_code": "这里填入你重构后的完整 Python 或 R 代码（包含 argparse 解析、详尽注释。注意对代码中的字符串转义，确保 JSON 格式正确。）",
  "dependencies": ["pandas", "numpy", "scanpy"]  // 列出代码需要的 Python 或 R 包
}}
***

开始你的锻造！只输出 ***json_skill 包裹的 JSON，不要输出任何额外的闲聊解释！"""

    try:
        response = await llm.ainvoke([{"role": "user", "content": crafter_prompt}])
        log.info(f"📝 [Crafter Forge] LLM 返回内容长度: {len(response.content)}")

        crafted_data = extract_crafted_skill(response.content)

        if not crafted_data:
            log.error("AI 返回的内容未包含有效的 JSON 结构")
            raise ValueError("AI 返回的内容未包含有效的 ***json_skill 结构。")

        # 验证必要字段
        required_fields = ["name", "description", "executor_type", "script_code"]
        for field in required_fields:
            if field not in crafted_data:
                raise ValueError(f"锻造结果缺少必要字段: {field}")

        # 设置默认值
        if "parameters_schema" not in crafted_data:
            crafted_data["parameters_schema"] = {"type": "object", "properties": {}, "required": []}
        if "expert_knowledge" not in crafted_data:
            crafted_data["expert_knowledge"] = "暂无专家指导。"
        if "dependencies" not in crafted_data:
            crafted_data["dependencies"] = []

        log.info(f"✅ [Crafter Forge] 技能锻造成功: {crafted_data.get('name')}")
        return crafted_data

    except Exception as e:
        log.error(f"技能锻造失败: {e}")
        raise Exception(f"AI 智能锻造失败: {str(e)}")


async def craft_skill_from_blueprint(
    blueprint_json: str,
    api_key: str,
    base_url: str,
    model_name: str
) -> Dict[str, Any]:
    """
    从 DAG 蓝图锻造技能（用于蓝图固化功能）

    Args:
        blueprint_json: DAG 蓝图 JSON 字符串
        api_key: OpenAI API Key
        base_url: API Base URL
        model_name: 模型名称

    Returns:
        锻造后的技能资产字典
    """
    log.info("🔨 [Crafter Forge] 正在从蓝图锻造技能...")

    # 将蓝图解析为素材
    try:
        blueprint = json.loads(blueprint_json)
        tasks = blueprint.get("tasks", [])

        # 构建素材描述
        material = f"这是一个由多个分析步骤组成的 DAG 蓝图：\n\n"
        for i, task in enumerate(tasks, 1):
            material += f"步骤 {i}: {task.get('name', '未知步骤')}\n"
            material += f"  - 描述: {task.get('description', '无')}\n"
            material += f"  - 工具: {task.get('tool', '未知')}\n"
            if task.get("parameters"):
                material += f"  - 参数: {json.dumps(task.get('parameters'), ensure_ascii=False)}\n"
            material += "\n"

        # 调用锻造引擎
        return await craft_skill_from_material(material, api_key, base_url, model_name)

    except json.JSONDecodeError as e:
        log.error(f"蓝图 JSON 解析失败: {e}")
        raise ValueError(f"蓝图 JSON 解析失败: {str(e)}")


def generate_skill_id_from_name(name: str) -> str:
    """
    根据技能名称生成唯一的 skill_id

    Args:
        name: 技能名称

    Returns:
        格式化的 skill_id，如 "custom_differential_expression"
    """
    import uuid

    # 将中文名称转为拼音或使用默认前缀
    # 简单处理：使用时间戳 + 随机字符串
    prefix = "custom"
    suffix = uuid.uuid4().hex[:8]

    return f"{prefix}_{suffix}"


log.info("🔨 SKILL Crafter Agent 已加载")