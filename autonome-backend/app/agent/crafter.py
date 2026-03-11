"""
SKILL Crafter Agent - AI 智能锻造引擎

功能：将非结构化素材（代码、文献、文本指令）逆向提炼为标准技能包

三大铁律强制注入：
1. 参数自动化抽取 - 必须使用 argparse (Python) 或 optparse/commandArgs (R)
2. 强制保全与重写注释 - 详尽的中文块级注释和行级注释
3. 强制 TSV 格式输出 - 表格数据必须输出为 Tab 分割的 .tsv 格式

支持 4 种执行器类型：
- Python_env: 单 Python 脚本
- R_env: 单 R 脚本
- Logical_Blueprint: Nextflow 工作流
- Python_Package: 完整 Python 包
"""

import json
import re
from typing import Dict, Any, Optional

from langchain_openai import ChatOpenAI
from app.core.logger import log
from app.models.skill_bundle import ExecutorType, is_script_type, is_nextflow_type


def extract_crafted_skill(text: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 的回复中提取 JSON 结构化数据

    支持多种格式：
    1. ***json_skill ... *** 包裹格式
    2. ```json ... ``` 代码块格式
    3. 直接 JSON 对象

    Args:
        text: LLM 返回的原始文本

    Returns:
        解析后的 JSON 字典，如果解析失败则返回 None
    """
    # 方法1: 匹配 ***json_skill ... *** 格式
    pattern1 = r'\*\*\*json_skill\s*(.*?)\s*\*\*\*'
    match = re.search(pattern1, text, re.DOTALL | re.IGNORECASE)

    if match:
        try:
            json_str = match.group(1).strip()
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            log.warning(f"[extract_crafted_skill] 方法1 JSON 解析失败: {e}")

    # 方法2: 匹配 ```json ... ``` 代码块格式
    pattern2 = r'```json\s*(.*?)\s*```'
    match = re.search(pattern2, text, re.DOTALL | re.IGNORECASE)

    if match:
        try:
            json_str = match.group(1).strip()
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            log.warning(f"[extract_crafted_skill] 方法2 JSON 解析失败: {e}")

    # 方法3: 匹配 ``` ... ``` 代码块（无语言标记）
    pattern3 = r'```\s*(.*?)\s*```'
    match = re.search(pattern3, text, re.DOTALL)

    if match:
        try:
            json_str = match.group(1).strip()
            # 检查是否以 { 开头
            if json_str.startswith('{'):
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            log.warning(f"[extract_crafted_skill] 方法3 JSON 解析失败: {e}")

    # 方法4: 尝试找到最大的 JSON 对象
    try:
        # 使用更精确的正则匹配完整的 JSON 对象
        # 找到第一个 { 和最后一个 } 的位置
        start_idx = text.find('{')
        if start_idx != -1:
            # 从后往前找最后一个 }
            end_idx = text.rfind('}')
            if end_idx > start_idx:
                json_str = text[start_idx:end_idx + 1]
                return json.loads(json_str)
    except json.JSONDecodeError as e:
        log.warning(f"[extract_crafted_skill] 方法4 JSON 解析失败: {e}")

    log.error(f"[extract_crafted_skill] 所有提取方法均失败，原始文本前500字符: {text[:500]}")
    return None


async def craft_skill_from_material(
    raw_material: str,
    api_key: str,
    base_url: str,
    model_name: str,
    executor_type: str = "Python_env"
) -> Dict[str, Any]:
    """
    智能锻造引擎 (Crafter Agent)：
    输入非结构化素材，输出标准化的技能资产配置（含Schema和重构后的代码）

    Args:
        raw_material: 原始素材（代码/指令/文献段落）
        api_key: OpenAI API Key
        base_url: API Base URL
        model_name: 模型名称
        executor_type: 执行器类型 (Python_env/R_env/Logical_Blueprint/Python_Package)

    Returns:
        锻造后的技能资产字典，包含：
        - name: 技能名称
        - description: 一句话简介
        - executor_type: 执行器类型 (Python_env/R_env/Logical_Blueprint)
        - parameters_schema: JSON Schema 格式的参数定义
        - expert_knowledge: 专家指导
        - script_code: 重构后的完整代码 (单脚本类型)
        - nextflow_code: Nextflow 工作流代码 (Logical_Blueprint 类型)
        - dependencies: 依赖包列表
    """
    log.info(f"🔨 [Crafter Forge] 正在启动技能锻造炉... 执行器类型: {executor_type}")

    # 根据执行器类型选择锻造策略
    if is_nextflow_type(ExecutorType(executor_type)):
        return await _craft_blueprint_skill(raw_material, api_key, base_url, model_name)
    else:
        return await _craft_script_skill(raw_material, api_key, base_url, model_name, executor_type)


async def _craft_script_skill(
    raw_material: str,
    api_key: str,
    base_url: str,
    model_name: str,
    executor_type: str
) -> Dict[str, Any]:
    """
    单脚本锻造 (Python_env / R_env)
    """

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,  # 保持极低的温度以保证代码严谨性
        max_tokens=4000
    )

    # 根据执行器类型设置默认值提示
    if executor_type == "R_env":
        default_executor = "R_env"
        arg_parser_note = "使用 commandArgs(trailingOnly=TRUE) 或 optparse 包接收参数"
    else:
        default_executor = "Python_env"
        arg_parser_note = "使用 argparse 接收参数"

    # 参数类型识别规范（关键！）
    param_type_guide = """
【参数类型识别规范 - 必须严格遵守】

根据参数的语义和用途，设置正确的 type 和 format 字段：

1. **文件路径参数** (type: string, format: filepath)
   - 参数名包含: file, input, output, path, filename, 数据文件
   - 示例: input_file, output_path, bam_file, vcf_file, fastq_file
   - 值为具体的文件路径，如 "/data/sample.bam"

2. **目录路径参数** (type: string, format: directorypath)
   - 参数名包含: dir, directory, folder, 目录, 文件夹
   - 示例: input_dir, output_dir, work_dir, data_directory
   - 值为目录路径，如 "/data/results/"

3. **数值参数** (type: number 或 integer)
   - 参数名包含: threshold, value, count, size, length, num, ratio, score
   - 示例: p_value (number), min_length (integer), threads (integer)
   - 整数用 integer，浮点数用 number

4. **布尔参数** (type: boolean)
   - 参数名以 is_, has_, use_, enable_ 开头
   - 示例: is_paired, has_header, use_cache, enable_filter
   - 值为 true 或 false

5. **枚举参数** (type: string, enum: [...])
   - 参数值只能是预定义的几个选项
   - 示例: mode 可选 ["fast", "standard", "strict"]

6. **普通字符串参数** (type: string)
   - 不符合以上任何特征的普通文本参数
   - 示例: sample_name, gene_id, pattern

【JSON Schema 示例】
{
  "input_file": {
    "type": "string",
    "format": "filepath",
    "description": "输入 BAM 文件路径",
    "default": ""
  },
  "output_dir": {
    "type": "string",
    "format": "directorypath",
    "description": "输出结果目录",
    "default": "./results"
  },
  "p_value": {
    "type": "number",
    "description": "显著性 P 值阈值",
    "default": 0.05
  },
  "threads": {
    "type": "integer",
    "description": "并行线程数",
    "default": 4
  },
  "is_paired": {
    "type": "boolean",
    "description": "是否为双端测序",
    "default": true
  }
}
"""

    crafter_prompt = f"""你是 Autonome 系统的首席技能锻造师 (Skill Architect)。
你的任务是接收用户提供的【原始生信分析素材】，将其逆向提炼、重构为一个符合 Autonome 标准的【工业级可复用技能包】。

【原始素材】
{raw_material}

【目标执行器类型】
{executor_type}

【锻造铁律与重构规范】
1. **参数自动化抽取**：找出原始代码中所有"应该被用户自定义的变量"（如：输入文件路径、P-value阈值等），将它们抽取为 JSON Schema 参数。{arg_parser_note}，必须设置默认值！

2. **强制保全与重写注释**：为重构后的代码加上极度详尽的中文块级注释和行级注释。

3. **强制 TSV 格式输出**：如果该技能有表格数据落地，生成 Tab 分割的 `.tsv` 格式。

{param_type_guide}

【输出格式】
请严格按照以下 JSON 格式输出，不要添加任何额外文字：

```json
{{
  "name": "技能名称（中文）",
  "description": "一句话简介",
  "executor_type": "{default_executor}",
  "parameters_schema": {{
    "type": "object",
    "properties": {{
      "input_file": {{ "type": "string", "format": "filepath", "description": "输入文件路径", "default": "" }},
      "output_dir": {{ "type": "string", "format": "directorypath", "description": "输出目录", "default": "./output" }}
    }},
    "required": ["input_file"]
  }},
  "expert_knowledge": "专家指导内容",
  "script_code": "重构后的完整代码",
  "dependencies": ["pandas", "numpy"]
}}
```

请直接输出上述 JSON 格式的内容，不要包含任何其他文字说明！"""

    try:
        response = await llm.ainvoke([{"role": "user", "content": crafter_prompt}])
        log.info(f"📝 [Crafter Forge] LLM 返回内容长度: {len(response.content)}")

        # 记录原始返回内容（调试用）
        log.debug(f"📝 [Crafter Forge] LLM 原始返回: {response.content[:1000]}...")

        crafted_data = extract_crafted_skill(response.content)

        if not crafted_data:
            log.error("AI 返回的内容未包含有效的 JSON 结构")
            log.error(f"AI 原始返回内容: {response.content}")
            raise ValueError(f"AI 返回的内容未包含有效的 JSON 结构。原始返回前200字符: {response.content[:200]}")

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


async def _craft_blueprint_skill(
    raw_material: str,
    api_key: str,
    base_url: str,
    model_name: str
) -> Dict[str, Any]:
    """
    Nextflow 工作流锻造 (Logical_Blueprint)

    将需求转换为 Nextflow DSL2 工作流代码
    """
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,
        max_tokens=6000  # Nextflow 工作流可能需要更多 tokens
    )

    # 参数类型识别规范
    param_type_guide = """
【参数类型识别规范 - 必须严格遵守】

根据参数的语义和用途，设置正确的 type 和 format 字段：

1. **文件路径参数** (type: string, format: filepath)
   - 参数名包含: file, input, output, path, filename
   - 示例: input_file, output_path, bam_file, fastq_file

2. **目录路径参数** (type: string, format: directorypath)
   - 参数名包含: dir, directory, folder
   - 示例: input_dir, output_dir, work_dir

3. **数值参数** (type: number 或 integer)
   - 参数名包含: threshold, value, count, size, threads
   - 整数用 integer，浮点数用 number

4. **布尔参数** (type: boolean)
   - 参数名以 is_, has_, use_ 开头

5. **普通字符串参数** (type: string)
   - 不符合以上任何特征的普通文本参数
"""

    blueprint_prompt = f"""你是 Autonome 系统的首席 Nextflow 工作流架构师 (Pipeline Architect)。
你的任务是接收用户提供的【原始生信分析需求】，将其转换为符合 Nextflow DSL2 规范的【工业级并行工作流】。

【原始素材】
{raw_material}

【Nextflow 工作流锻造规范】
1. **流程拆解**：将需求拆解为多个独立的 Process 节点，每个 Process 应该是单一职责的原子操作
2. **Channel 设计**：使用 `Channel.fromFilePairs` 处理配对数据，`Channel.fromPath` 处理单个文件
3. **参数化**：所有配置项（路径、线程数、阈值等）必须通过 `params` 定义，每个参数必须有默认值
4. **资源管理**：为每个 Process 设置合理的 `cpus` 和 `memory`，使用 `tag` 标记任务

{param_type_guide}

【输出格式】
请严格按照以下 JSON 格式输出，不要添加任何额外文字：

```json
{{
  "name": "工作流名称（中文）",
  "description": "一句话简介",
  "executor_type": "Logical_Blueprint",
  "parameters_schema": {{
    "type": "object",
    "properties": {{
      "input_dir": {{ "type": "string", "format": "directorypath", "description": "输入数据目录", "default": "./data" }},
      "threads": {{ "type": "integer", "description": "并行线程数", "default": 4 }}
    }},
    "required": ["input_dir"]
  }},
  "expert_knowledge": "专家指导内容",
  "nextflow_code": "完整的 Nextflow DSL2 代码",
  "dependencies": ["nextflow", "fastqc"]
}}
```

请直接输出上述 JSON 格式的内容，不要包含任何其他文字说明！"""

    try:
        response = await llm.ainvoke([{"role": "user", "content": blueprint_prompt}])
        log.info(f"📝 [Crafter Forge - Blueprint] LLM 返回内容长度: {len(response.content)}")

        crafted_data = extract_crafted_skill(response.content)

        if not crafted_data:
            log.error("AI 返回的内容未包含有效的 JSON 结构")
            raise ValueError("AI 返回的内容未包含有效的 ***json_skill 结构。")

        # 验证必要字段
        required_fields = ["name", "description", "executor_type"]
        for field in required_fields:
            if field not in crafted_data:
                raise ValueError(f"锻造结果缺少必要字段: {field}")

        # 验证 Nextflow 代码存在
        if "nextflow_code" not in crafted_data or not crafted_data["nextflow_code"]:
            raise ValueError("Nextflow 工作流锻造结果缺少 nextflow_code 字段")

        # 设置默认值
        if "parameters_schema" not in crafted_data:
            crafted_data["parameters_schema"] = {"type": "object", "properties": {}, "required": []}
        if "expert_knowledge" not in crafted_data:
            crafted_data["expert_knowledge"] = "暂无专家指导。"
        if "dependencies" not in crafted_data:
            crafted_data["dependencies"] = []
        if "script_code" not in crafted_data:
            crafted_data["script_code"] = None  # Blueprint 类型不需要 script_code

        # 强制设置 executor_type
        crafted_data["executor_type"] = "Logical_Blueprint"

        log.info(f"✅ [Crafter Forge - Blueprint] 工作流锻造成功: {crafted_data.get('name')}")
        return crafted_data

    except Exception as e:
        log.error(f"Nextflow 工作流锻造失败: {e}")
        raise Exception(f"Nextflow 工作流锻造失败: {str(e)}")


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

        # 调用锻造引擎 - 使用 Logical_Blueprint 类型
        return await craft_skill_from_material(
            material, api_key, base_url, model_name, executor_type="Logical_Blueprint"
        )

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