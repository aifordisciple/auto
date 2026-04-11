"""
SKILL Crafter Agent - AI 智能锻造引擎

功能：将非结构化素材（代码、文献、文本指令）逆向提炼为标准技能包

四大铁律强制注入：
1. 参数自动化抽取 - 必须使用 argparse (Python) 或 optparse/commandArgs (R)
2. 强制保全与重写注释 - 详尽的中文块级注释和行级注释
3. 强制 TSV 格式输出 - 表格数据必须输出为 Tab 分割的 .tsv 格式
4. 发表级图形输出 - 必须输出符合发表标准的高质量图形（300 DPI、PDF矢量、色盲友好配色）

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
from app.core.content_filter import preprocess_llm_response
from app.models.skill_bundle import ExecutorType, is_script_type, is_nextflow_type

# 尝试导入 json_repair，如果失败则使用内置方法
try:
    from json_repair import repair_json
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False
    log.warning("json_repair 未安装，将使用内置的 JSON 修复方法")


# ==========================================
# ✨ 分离格式解析函数（新增）
# ==========================================
def _parse_separated_format(text: str) -> Optional[Dict[str, Any]]:
    """
    解析分离格式输出

    格式示例：
    ---AUTONOME_SKILL_METADATA---
    ```json
    {...}
    ```
    ---AUTONOME_SCRIPT_CODE---
    ```python
    ...
    ```
    ---AUTONOME_END---

    Args:
        text: LLM 返回的原始文本

    Returns:
        解析后的技能字典，失败返回 None
    """
    # 检查是否包含分离格式标记
    if '---AUTONOME_SKILL_METADATA---' not in text:
        return None

    log.info("[分离格式] 检测到分离格式标记，开始解析...")

    # 1. 提取元数据 JSON 部分
    # 支持多种格式：```json 或直接内容
    metadata_patterns = [
        r'---AUTONOME_SKILL_METADATA---\s*```json\s*(.*?)\s*```',
        r'---AUTONOME_SKILL_METADATA---\s*```\s*(.*?)\s*```',
        r'---AUTONOME_SKILL_METADATA---\s*(\{.*?\})\s*(?=---AUTONOME_SCRIPT_CODE---|---AUTONOME_END---)',
    ]

    metadata = None
    for pattern in metadata_patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            metadata_str = match.group(1).strip()
            metadata = _try_parse_metadata_json(metadata_str)
            if metadata:
                log.info(f"[分离格式] 成功解析元数据 JSON，长度: {len(metadata_str)}")
                break

    if not metadata:
        log.warning("[分离格式] 元数据 JSON 解析失败")
        return None

    # 2. 提取代码部分
    # 支持 Python/R/Bash/Nextflow 多种语言
    # 注意：使用更健壮的正则，避免代码中的 ``` 干扰
    code_patterns = [
        # 带语言标记的代码块（贪婪匹配到最后一个 ```）
        (r'---AUTONOME_SCRIPT_CODE---\s*```python\s*(.*)\s*```', 'python'),
        (r'---AUTONOME_SCRIPT_CODE---\s*```r\s*(.*)\s*```', 'r'),
        (r'---AUTONOME_SCRIPT_CODE---\s*```bash\s*(.*)\s*```', 'bash'),
        (r'---AUTONOME_SCRIPT_CODE---\s*```shell\s*(.*)\s*```', 'bash'),
        # 无语言标记的代码块
        (r'---AUTONOME_SCRIPT_CODE---\s*```\s*(.*)\s*```', None),
    ]

    script_code = None
    for pattern, lang in code_patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            script_code = match.group(1).strip()
            log.info(f"[分离格式] 成功提取代码（模式1），语言: {lang or 'unknown'}，长度: {len(script_code)}")
            break

    # 回退策略1: 提取到 ---AUTONOME_END--- 标记
    if not script_code:
        end_pattern = r'---AUTONOME_SCRIPT_CODE---\s*```(?:python|r|bash|shell)?\s*(.*?)\s*---AUTONOME_END---'
        match = re.search(end_pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            script_code = match.group(1).strip()
            # 移除可能的结尾 ```
            if script_code.endswith('```'):
                script_code = script_code[:-3].strip()
            log.info(f"[分离格式] 成功提取代码（回退策略1），长度: {len(script_code)}")

    # 回退策略2: 直接提取从标记到文本结尾（可能 AI 没有输出结束标记）
    if not script_code and '---AUTONOME_SCRIPT_CODE---' in text:
        start_idx = text.find('---AUTONOME_SCRIPT_CODE---')
        if start_idx != -1:
            # 找到代码开始位置
            code_start = text.find('```', start_idx)
            if code_start != -1:
                # 跳过语言标记（如 ```r 或 ```python）
                code_start = text.find('\n', code_start) + 1
                # 提取到文本结尾
                script_code = text[code_start:].strip()
                # 移除可能的结尾标记
                if '---AUTONOME_END---' in script_code:
                    script_code = script_code[:script_code.find('---AUTONOME_END---')].strip()
                if script_code.endswith('```'):
                    script_code = script_code[:-3].strip()
                log.info(f"[分离格式] 成功提取代码（回退策略2），长度: {len(script_code)}")

    # 3. 检查 Nextflow 代码（Logical_Blueprint 类型）
    if '---AUTONOME_NEXTFLOW_CODE---' in text:
        nf_patterns = [
            r'---AUTONOME_NEXTFLOW_CODE---\s*```nextflow\s*(.*?)\s*```',
            r'---AUTONOME_NEXTFLOW_CODE---\s*```groovy\s*(.*?)\s*```',
            r'---AUTONOME_NEXTFLOW_CODE---\s*```\s*(.*?)\s*```',
        ]
        for pattern in nf_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                metadata['nextflow_code'] = match.group(1).strip()
                log.info(f"[分离格式] 成功提取 Nextflow 代码，长度: {len(metadata['nextflow_code'])}")
                break

    # 4. 合并代码到元数据
    if script_code:
        metadata['script_code'] = script_code

    # 5. 验证结构完整性
    if not _validate_skill_structure(metadata):
        log.warning("[分离格式] 结构验证失败")
        return None

    log.info(f"[分离格式] 解析完成，技能名称: {metadata.get('name', 'unknown')}")
    return metadata


def _try_parse_metadata_json(json_str: str) -> Optional[Dict[str, Any]]:
    """
    尝试解析元数据 JSON（不含代码，解析难度大大降低）

    Args:
        json_str: JSON 字符串（不含代码字段）

    Returns:
        解析后的字典，失败返回 None
    """
    # 方法1: 直接解析
    try:
        result = json.loads(json_str)
        if isinstance(result, dict):
            log.debug("[元数据JSON] 直接解析成功")
            return result
    except json.JSONDecodeError as e:
        log.debug(f"[元数据JSON] 直接解析失败: {e}")

    # 方法2: 使用 json_repair 库
    if HAS_JSON_REPAIR:
        try:
            result = repair_json(json_str, return_objects=True)
            if isinstance(result, dict):
                log.debug("[元数据JSON] json_repair 解析成功")
                return result
            elif isinstance(result, str):
                result = json.loads(result)
                if isinstance(result, dict):
                    log.debug("[元数据JSON] json_repair 解析成功")
                    return result
        except Exception as e:
            log.debug(f"[元数据JSON] json_repair 解析失败: {e}")

    # 方法3: 使用内置修复方法
    try:
        fixed_json = _fix_json_string(json_str)
        result = json.loads(fixed_json)
        if isinstance(result, dict):
            log.debug("[元数据JSON] 内置修复解析成功")
            return result
    except json.JSONDecodeError as e:
        log.debug(f"[元数据JSON] 内置修复解析失败: {e}")

    return None


def extract_crafted_skill(text: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 的回复中提取 JSON 结构化数据

    支持多种格式：
    0. 【优先】分离格式：---AUTONOME_SKILL_METADATA--- ... ---AUTONOME_SCRIPT_CODE--- ...
    1. ***json_skill ... *** 包裹格式
    2. ```json ... ``` 代码块格式
    3. 直接 JSON 对象
    4. 分析文本后的 JSON（LLM 先分析再输出 JSON 的情况）

    增强特性：
    - 分离格式无需代码转义（新增）
    - 使用 json_repair 库进行智能 JSON 修复
    - 多策略容错提取
    - 详细的日志记录
    - 结构验证

    Args:
        text: LLM 返回的原始文本

    Returns:
        解析后的 JSON 字典，如果解析失败则返回 None
    """
    # 🔧 预处理：过滤 thinking 标签
    text = preprocess_llm_response(text)

    # 记录原始文本长度用于调试
    original_text_len = len(text)
    log.info(f"[extract_crafted_skill] 预处理后文本长度: {original_text_len}")

    # ==========================================
    # 策略0: 【最高优先】解析分离格式
    # ==========================================
    separated_result = _parse_separated_format(text)
    if separated_result:
        log.info("[extract_crafted_skill] 使用分离格式解析成功")
        return separated_result

    # 策略1: 查找 ```json 代码块
    json_block_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if json_block_match:
        json_str = json_block_match.group(1).strip()
        result = _try_parse_json(json_str, 'json_block')
        if result:
            return result

    # 策略2: 查找 ***json_skill 特殊标记
    special_match = re.search(r'\*\*\*json_skill\s*(.*?)\s*\*\*\*', text, re.DOTALL | re.IGNORECASE)
    if special_match:
        json_str = special_match.group(1).strip()
        result = _try_parse_json(json_str, 'special_marker')
        if result:
            return result

    # 策略3: 查找任意 ``` 代码块（内容以 { 开头）
    generic_match = re.search(r'```\s*(\{.*?)\s*```', text, re.DOTALL)
    if generic_match:
        json_str = generic_match.group(1).strip()
        result = _try_parse_json(json_str, 'generic_code_block')
        if result:
            return result

    # 策略4: 查找文本中的 JSON 对象（从第一个 { 到最后一个 }）
    start_idx = text.find('{')
    if start_idx != -1:
        # 找到最后一个 }
        end_idx = text.rfind('}')
        if end_idx > start_idx:
            json_str = text[start_idx:end_idx + 1]
            result = _try_parse_json(json_str, 'bracket_extraction')
            if result:
                return result

    log.error(f"[extract_crafted_skill] 所有提取策略均失败，原始文本前500字符: {text[:500]}")
    return None


def _try_parse_json(json_str: str, strategy_name: str) -> Optional[Dict[str, Any]]:
    """
    尝试解析 JSON 字符串，支持多种修复策略

    Args:
        json_str: JSON 字符串
        strategy_name: 策略名称（用于日志）

    Returns:
        解析后的字典，失败返回 None
    """
    # 方法1: 直接解析
    try:
        result = json.loads(json_str)
        if _validate_skill_structure(result):
            log.info(f"[extract_crafted_skill] 使用策略 '{strategy_name}' 直接解析成功")
            return result
    except json.JSONDecodeError as e:
        log.debug(f"[extract_crafted_skill] 策略 '{strategy_name}' 直接解析失败: {e}")

    # 方法2: 使用 json_repair 库（如果可用）
    if HAS_JSON_REPAIR:
        try:
            result = repair_json(json_str, return_objects=True)
            if isinstance(result, dict) and _validate_skill_structure(result):
                log.info(f"[extract_crafted_skill] 使用策略 '{strategy_name}' + json_repair 解析成功")
                return result
            elif isinstance(result, str):
                # repair_json 可能返回字符串，需要再次解析
                result = json.loads(result)
                if _validate_skill_structure(result):
                    log.info(f"[extract_crafted_skill] 使用策略 '{strategy_name}' + json_repair 解析成功")
                    return result
        except Exception as e:
            log.debug(f"[extract_crafted_skill] 策略 '{strategy_name}' json_repair 解析失败: {e}")

    # 方法3: 使用内置修复方法
    try:
        fixed_json = _fix_json_string(json_str)
        result = json.loads(fixed_json)
        if _validate_skill_structure(result):
            log.info(f"[extract_crafted_skill] 使用策略 '{strategy_name}' + 内置修复解析成功")
            return result
    except json.JSONDecodeError as e:
        log.debug(f"[extract_crafted_skill] 策略 '{strategy_name}' 内置修复解析失败: {e}")

    log.warning(f"[extract_crafted_skill] 策略 '{strategy_name}' 所有解析方法均失败")
    return None


def _fix_json_string(json_str: str) -> str:
    """
    修复常见的 JSON 格式问题

    主要处理：
    1. 字符串中未转义的换行符
    2. 字符串中未转义的引号

    Args:
        json_str: 原始 JSON 字符串

    Returns:
        修复后的 JSON 字符串
    """
    import re

    # 方法：使用状态机逐字符处理
    # 跟踪当前是否在字符串内部
    result = []
    in_string = False
    escape_next = False
    string_start_char = None

    i = 0
    while i < len(json_str):
        char = json_str[i]

        if escape_next:
            # 上一个字符是反斜杠，当前字符直接追加
            result.append(char)
            escape_next = False
            i += 1
            continue

        if char == '\\':
            # 遇到转义符
            result.append(char)
            escape_next = True
            i += 1
            continue

        if char in ('"', "'"):
            if not in_string:
                # 进入字符串
                in_string = True
                string_start_char = char
                result.append(char)
            elif char == string_start_char:
                # 离开字符串
                in_string = False
                string_start_char = None
                result.append(char)
            else:
                # 字符串内的引号，需要转义
                result.append('\\')
                result.append(char)
            i += 1
            continue

        if in_string:
            # 在字符串内部
            if char == '\n':
                # 换行符需要转义
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            elif char == '\t':
                result.append('\\t')
            else:
                result.append(char)
        else:
            # 不在字符串内部
            result.append(char)

        i += 1

    return ''.join(result)


def _validate_skill_structure(data: Dict[str, Any]) -> bool:
    """
    验证技能结构的完整性

    检查是否包含必要的字段

    Args:
        data: 解析后的 JSON 字典

    Returns:
        是否通过验证
    """
    # 检查是否是字典
    if not isinstance(data, dict):
        return False

    # 检查必要字段：至少要有 name 和 executor_type
    required_fields = ["name"]
    for field in required_fields:
        if field not in data:
            log.warning(f"[validate_skill_structure] 缺少必要字段: {field}")
            return False

    return True


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
        max_tokens=128000  # 增大 token 限制，支持长代码输出
    )

    # 根据执行器类型设置默认值提示
    if executor_type == "R_env":
        default_executor = "R_env"
        arg_parser_note = "使用 commandArgs(trailingOnly=TRUE) 或 optparse 包接收参数"
        code_language = "r"
        code_language_display = "R"
    else:
        default_executor = "Python_env"
        arg_parser_note = "使用 argparse 接收参数"
        code_language = "python"
        code_language_display = "Python"

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

【核心任务】
接收用户提供的非结构化生信分析素材，在**绝对不改变核心算法逻辑**的前提下，将其逆向提炼、参数化，并重构为符合 Autonome 标准的工业级技能包 (JSON格式)。

<raw_material>
{raw_material}
</raw_material>

<environment>
目标执行器: {executor_type}
参数接收规范: {arg_parser_note}
</environment>

<rules>
【锻造铁律与重构规范】（必须严格遵守）

1.  代码重构底线：

      - 务必保留原始的逻辑和算法，仅调整格式、补充参数解析和修复明显错误。
      - 强制添加极度详尽的中文块级注释和行级注释。

2.  参数自动化抽取（核心）：

      - 仅抽取"具有实际业务调节意义"的变量（如：输入输出路径、P-value阈值、分组列名等）。不要把内部运算的临时变量暴露为参数！
      - 抽取出的参数名必须与代码中参数系统设置的长参完全一致，且必须赋予合理的默认值。

3.  参数类型识别映射表：

      - 文件路径: 包含 file, input, output, path (设为 type: string, format: filepath)
      - 目录路径: 包含 dir, folder, 目录 (设为 type: string, format: directorypath)
      - 数值型: 包含 threshold, value, count, p_value, size (设为 type: number 或 integer)
      - 布尔型: 以 is_, has_, use_, enable_ 开头 (设为 type: boolean)
      - 枚举型: 仅限几个固定选项 (设为 type: string, enum: [...])

4.  数据与图形输出规范：

      - 表格落地：若输出表格数据，强制修改为 Tab 分割的 `.tsv` 格式。
      - 图形落地：若有绘图输出，必须达到发表级标准。
          * 双格式输出：默认输出 PDF（矢量图）与 PNG（300 DPI 分辨率）。
          * 美学标准：纯英文标签、使用清晰无衬线字体（14pt）、无粗体、色盲友好配色（如 viridis）。
          * 注意：这些基础美学标准（如 300 DPI, 字体大小）请直接在代码中**硬编码**，不要抽取为外部参数（以免给用户造成过重的配置负担），除非用户原始需求中明确要求调节尺寸。

</rules>

<output_format>
【输出格式 - 极其重要！】

你必须**严格按以下分离格式输出**，将 JSON 元数据和代码分开，避免代码中的转义问题！

---AUTONOME_SKILL_METADATA---
```json
{{
  "thought_process": "简要分析素材的核心逻辑，列出你打算抽取的参数列表，并说明你做了哪些规范化重构（限100字）。",
  "name": "提炼出的技能名称（简短中文）",
  "description": "一句话简介",
  "executor_type": "{default_executor}",
  "parameters_schema": {{
    "type": "object",
    "properties": {{
      "input_file": {{ "type": "string", "format": "filepath", "description": "输入文件路径", "default": "" }},
      "p_value": {{ "type": "number", "description": "显著性 P 值阈值", "default": 0.05 }}
    }},
    "required": ["input_file"]
  }},
  "expert_knowledge": "详细的专家指导内容（此处换行无需转义，直接换行即可）",
  "dependencies": ["pandas", "matplotlib"]
}}
```
---AUTONOME_SCRIPT_CODE---
```{code_language}
# 重构后的完整执行代码
# 注意：代码块中的双引号、单引号、换行符都无需转义！
# 可以直接写正常的 {code_language_display} 代码

import argparse

def main():
    parser = argparse.ArgumentParser(description='...')
    parser.add_argument('--input_file', type=str, required=True)
    parser.add_argument('--p_value', type=float, default=0.05)
    args = parser.parse_args()

    # 核心分析逻辑...
    print(f"Input: {{args.input_file}}")
    print(f"P-value: {{args.p_value}}")

if __name__ == '__main__':
    main()
```
---AUTONOME_END---

【关键注意事项】
1. **必须**包含所有三个分隔标记：`---AUTONOME_SKILL_METADATA---`、`---AUTONOME_SCRIPT_CODE---`、`---AUTONOME_END---`
2. JSON 元数据中**不要**包含 `script_code` 字段（代码在单独的块中）
3. 代码块中**无需任何转义**，直接写正常的 Python/R 代码
4. 使用 ` ```python ` 或 ` ```r ` 包裹代码（根据执行器类型）
5. 不要在输出前添加任何分析文本，直接以 `---AUTONOME_SKILL_METADATA---` 开头
</output_format>
"""

    try:
        # ==========================================
        # 打印发送给 LLM 的完整 Prompt（调试用）
        # ==========================================
        log.info("=" * 80)
        log.info("📤 [Crafter Forge] 发送给 LLM 的完整 Prompt:")
        log.info("-" * 80)
        log.info(crafter_prompt)
        log.info("=" * 80)

        response = await llm.ainvoke([{"role": "user", "content": crafter_prompt}])
        log.info(f"📝 [Crafter Forge] LLM 返回内容长度: {len(response.content)}")

        # ==========================================
        # 打印 LLM 返回的完整内容（调试用）
        # ==========================================
        log.info("=" * 80)
        log.info("📥 [Crafter Forge] LLM 返回的完整内容:")
        log.info("-" * 80)
        log.info(response.content)
        log.info("=" * 80)

        crafted_data = extract_crafted_skill(response.content)

        if not crafted_data:
            log.error("AI 返回的内容未包含有效的 JSON 结构")
            log.error(f"AI 原始返回内容: {response.content}")
            raise ValueError(f"AI 返回的内容未包含有效的 JSON 结构。原始返回前200字符: {response.content[:200]}")

        # 验证必要字段
        required_fields = ["name", "description", "executor_type"]
        for field in required_fields:
            if field not in crafted_data:
                raise ValueError(f"锻造结果缺少必要字段: {field}")

        # 检查代码字段（script_code 或 nextflow_code 至少有一个）
        if "script_code" not in crafted_data and "nextflow_code" not in crafted_data:
            log.warning("锻造结果缺少代码字段，尝试从原始内容重新提取...")
            # 不抛出异常，允许后续处理

        # 设置默认值
        if "parameters_schema" not in crafted_data:
            crafted_data["parameters_schema"] = {"type": "object", "properties": {}, "required": []}
        if "expert_knowledge" not in crafted_data:
            crafted_data["expert_knowledge"] = "暂无专家指导。"
        if "dependencies" not in crafted_data:
            crafted_data["dependencies"] = []
        if "script_code" not in crafted_data:
            crafted_data["script_code"] = ""  # 默认空字符串

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
        max_tokens=128000  # Nextflow 工作流可能需要更多 tokens
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
5. **发表级图形输出**：如有图形输出，需符合发表标准（300 DPI 以上、PDF 矢量格式优先、色盲友好配色、规范字体和尺寸）

{param_type_guide}

【输出格式 - 极其重要！】

你必须**严格按以下分离格式输出**，将 JSON 元数据和 Nextflow 代码分开，避免代码中的转义问题！

---AUTONOME_SKILL_METADATA---
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
  "expert_knowledge": "专家指导内容（此处换行无需转义）",
  "dependencies": ["nextflow", "fastqc"]
}}
```
---AUTONOME_NEXTFLOW_CODE---
```nextflow
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

// Nextflow DSL2 工作流代码
// 注意：代码块中的双引号、单引号、换行符都无需转义！

workflow {{
    // 工作流主体
}}

process EXAMPLE {{
    cpus 4
    memory '8.GB'

    input:
    path input_file

    output:
    path 'output/*'

    script:
    """
    # 你的处理逻辑
    """
}}
```
---AUTONOME_END---

【关键注意事项】
1. **必须**包含所有三个分隔标记：`---AUTONOME_SKILL_METADATA---`、`---AUTONOME_NEXTFLOW_CODE---`、`---AUTONOME_END---`
2. JSON 元数据中**不要**包含 `nextflow_code` 字段（代码在单独的块中）
3. 代码块中**无需任何转义**，直接写正常的 Nextflow DSL2 代码
4. 不要在输出前添加任何分析文本，直接以 `---AUTONOME_SKILL_METADATA---` 开头"""

    try:
        # ==========================================
        # 打印发送给 LLM 的完整 Prompt（调试用）
        # ==========================================
        log.info("=" * 80)
        log.info("📤 [Crafter Forge - Blueprint] 发送给 LLM 的完整 Prompt:")
        log.info("-" * 80)
        log.info(blueprint_prompt)
        log.info("=" * 80)

        response = await llm.ainvoke([{"role": "user", "content": blueprint_prompt}])
        log.info(f"📝 [Crafter Forge - Blueprint] LLM 返回内容长度: {len(response.content)}")

        # ==========================================
        # 打印 LLM 返回的完整内容（调试用）
        # ==========================================
        log.info("=" * 80)
        log.info("📥 [Crafter Forge - Blueprint] LLM 返回的完整内容:")
        log.info("-" * 80)
        log.info(response.content)
        log.info("=" * 80)

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