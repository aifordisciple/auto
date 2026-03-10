"""
Consolidator Agent 模块

负责将成功的 DAG 蓝图逆向提取为标准 SKILL.md，实现资产固化。
"""

import os
import json
from datetime import datetime
from typing import Dict, Optional, Any

from app.core.logger import log


async def consolidate_blueprint_to_skill(
    blueprint_json: str,
    api_key: str,
    base_url: str,
    model_name: str,
    project_id: str = ""
) -> str:
    """
    将成功的 DAG 蓝图逆向提取为标准 SKILL.md

    Args:
        blueprint_json: 蓝图 JSON 字符串
        api_key: LLM API Key
        base_url: LLM Base URL
        model_name: 模型名称
        project_id: 项目 ID（可选，用于生成 skill_id）

    Returns:
        SKILL.md 格式的字符串
    """
    from openai import AsyncOpenAI

    try:
        blueprint = json.loads(blueprint_json)
    except json.JSONDecodeError as e:
        log.error(f"❌ [Consolidator] 蓝图 JSON 解析失败: {e}")
        return ""

    log.info(f"🔄 [Consolidator] 开始固化蓝图: {blueprint.get('project_goal', '未命名')}")

    # 构建固化提示
    consolidate_prompt = f"""你是一位生物信息学流程固化专家，请将以下成功的分析蓝图转换为标准的 SKILL.md 格式。

## 原始蓝图

```json
{json.dumps(blueprint, ensure_ascii=False, indent=2)}
```

## SKILL.md 格式要求

请生成一个完整的 SKILL.md 文档，包含以下部分：

### 1. 元数据区 (YAML Front Matter)
```yaml
---
skill_id: [自动生成，格式如 rna_seq_qc_001]
name: [流程名称]
version: 1.0.0
description: [一句话描述]
category: [分类：rna_seq / single_cell / variant_calling / chip_seq / atac_seq / general]
executor_type: Python_env
author: Autonome Consolidator
created_at: {datetime.now().strftime('%Y-%m-%d')}
---
```

### 2. 概述部分
- 流程目的
- 适用场景
- 输入要求
- 输出说明

### 3. 参数定义 (Parameters Schema)
```json
{{
  "type": "object",
  "properties": {{
    "input_file": {{
      "type": "string",
      "description": "输入文件路径"
    }},
    "output_dir": {{
      "type": "string",
      "default": "/app/uploads/project_{{project_id}}/results"
    }}
  }},
  "required": ["input_file"]
}}
```

### 4. 专家知识 (Expert Knowledge)
- 关键步骤说明
- 参数调优建议
- 常见问题排查

### 5. 代码模板 (Code Template)
- 整合所有任务节点的代码
- 参数化设计（支持 argparse 或环境变量）
- 模块化结构

## 输出要求

1. 直接输出 SKILL.md 的完整内容，不要包含 ```markdown 包裹
2. 确保 skill_id 唯一且有意义
3. 代码必须完整可执行
4. 参数定义要覆盖所有必要的输入

请生成 SKILL.md 内容：
"""

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": """你是一位资深的生物信息学流程固化专家，精通将复杂的分析流程转换为可复用的标准模块。

你的输出将直接保存为 SKILL.md 文件，所以：
1. 不要添加任何解释性文字
2. 直接输出 SKILL.md 的完整内容
3. 确保格式规范、代码可执行"""
                },
                {"role": "user", "content": consolidate_prompt}
            ],
            max_tokens=4000,
            temperature=0.3
        )

        skill_content = response.choices[0].message.content.strip()

        log.info(f"✅ [Consolidator] SKILL 固化成功，共 {len(skill_content)} 字符")

        return skill_content

    except Exception as e:
        log.error(f"❌ [Consolidator] SKILL 固化失败: {str(e)}")
        return ""


async def save_skill_to_file(
    skill_content: str,
    skill_id: str,
    skills_dir: str = "/app/skills"
) -> bool:
    """
    将 SKILL 内容保存到文件

    Args:
        skill_content: SKILL.md 内容
        skill_id: SKILL ID
        skills_dir: SKILL 存放目录

    Returns:
        是否保存成功
    """
    try:
        # 确保目录存在
        os.makedirs(skills_dir, exist_ok=True)

        # 生成文件名
        file_name = f"{skill_id}.md"
        file_path = os.path.join(skills_dir, file_name)

        # 检查是否已存在
        if os.path.exists(file_path):
            log.warning(f"⚠️ [Consolidator] SKILL 文件已存在，将覆盖: {file_path}")

        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(skill_content)

        log.info(f"✅ [Consolidator] SKILL 已保存: {file_path}")

        return True

    except Exception as e:
        log.error(f"❌ [Consolidator] SKILL 保存失败: {str(e)}")
        return False


def extract_skill_id(skill_content: str) -> Optional[str]:
    """
    从 SKILL 内容中提取 skill_id

    Args:
        skill_content: SKILL.md 内容

    Returns:
        skill_id 或 None
    """
    import re

    # 尝试从 YAML front matter 中提取
    match = re.search(r'^skill_id:\s*(.+)$', skill_content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    return None


async def consolidate_and_save(
    blueprint_json: str,
    api_key: str,
    base_url: str,
    model_name: str,
    skills_dir: str = "/app/skills"
) -> Dict[str, Any]:
    """
    固化蓝图并保存的完整流程

    Args:
        blueprint_json: 蓝图 JSON
        api_key: API Key
        base_url: Base URL
        model_name: 模型名称
        skills_dir: SKILL 目录

    Returns:
        包含结果的字典
    """
    # 1. 固化为 SKILL
    skill_content = await consolidate_blueprint_to_skill(
        blueprint_json=blueprint_json,
        api_key=api_key,
        base_url=base_url,
        model_name=model_name
    )

    if not skill_content:
        return {
            "success": False,
            "error": "SKILL 固化失败"
        }

    # 2. 提取 skill_id
    skill_id = extract_skill_id(skill_content)

    if not skill_id:
        # 生成默认 skill_id
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        skill_id = f"consolidated_{timestamp}"

    # 3. 保存到文件
    saved = await save_skill_to_file(
        skill_content=skill_content,
        skill_id=skill_id,
        skills_dir=skills_dir
    )

    if saved:
        return {
            "success": True,
            "skill_id": skill_id,
            "file_path": os.path.join(skills_dir, f"{skill_id}.md"),
            "content_preview": skill_content[:500] + "..."
        }
    else:
        return {
            "success": False,
            "error": "SKILL 保存失败"
        }


log.info("📦 Consolidator Agent 模块已加载")