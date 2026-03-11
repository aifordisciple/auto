"""
SKILL Bundle Writer - 文件系统技能包写入服务

核心功能：将锻造好的技能内容写入文件系统，生成标准目录结构

目录结构：
{skill_id}/
├── SKILL.md                 # YAML frontmatter + Markdown
├── nextflow/
│   └── process.nf           # (Logical_Blueprint 类型)
└── scripts/
    └── main.py / main.R     # 单脚本类型
"""

import os
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.core.logger import log
from app.models.skill_bundle import (
    SkillBundleContent,
    SkillBundleMetadata,
    ExecutorType,
    NextflowBundle,
    get_script_extension,
    get_script_filename,
    is_script_type,
    is_nextflow_type
)


def generate_skill_id_from_name(name: str) -> str:
    """
    根据技能名称生成唯一的 skill_id

    Args:
        name: 技能名称（可以是中文或英文）

    Returns:
        格式化的 skill_id，如 "custom_differential_expression_01"
    """
    # 转为小写并替换空格
    import re

    # 尝试提取英文字符
    english_chars = re.findall(r'[a-zA-Z]+', name)
    if english_chars:
        # 使用英文单词组合
        base_id = '_'.join(english_chars).lower()
        # 限制长度
        if len(base_id) > 40:
            base_id = base_id[:40]
    else:
        # 纯中文名称，使用随机后缀
        base_id = "custom_skill"

    # 添加序号后缀
    suffix = uuid.uuid4().hex[:4]

    return f"{base_id}_{suffix}"


def write_skill_bundle(
    content: SkillBundleContent,
    skills_dir: str = "/app/skills"
) -> Dict[str, Any]:
    """
    创建技能包目录结构并写入所有文件

    Args:
        content: 技能包内容
        skills_dir: 技能目录根路径

    Returns:
        包含 skill_id、bundle_path、files_created 的字典
    """
    skill_id = content.metadata.skill_id
    bundle_path = os.path.join(skills_dir, skill_id)
    files_created = []

    # 1. 创建目录结构
    os.makedirs(bundle_path, exist_ok=True)
    log.info(f"[SkillBundleWriter] 创建 Bundle 目录: {bundle_path}")

    # 2. 根据 executor_type 创建子目录
    executor_type = content.metadata.executor_type

    scripts_dir = os.path.join(bundle_path, "scripts")
    nextflow_dir = os.path.join(bundle_path, "nextflow")

    if is_script_type(executor_type):
        os.makedirs(scripts_dir, exist_ok=True)
        log.info(f"[SkillBundleWriter] 创建 scripts 目录: {scripts_dir}")

    if is_nextflow_type(executor_type):
        os.makedirs(nextflow_dir, exist_ok=True)
        log.info(f"[SkillBundleWriter] 创建 nextflow 目录: {nextflow_dir}")

    # 3. 写入 SKILL.md
    skill_md_path = os.path.join(bundle_path, "SKILL.md")
    skill_md_content = _generate_skill_md(content)

    with open(skill_md_path, 'w', encoding='utf-8') as f:
        f.write(skill_md_content)
    files_created.append("SKILL.md")
    log.info(f"[SkillBundleWriter] 写入 SKILL.md: {skill_md_path}")

    # 4. 写入脚本文件
    if is_script_type(executor_type) and content.script_code:
        script_filename = get_script_filename(executor_type)
        script_path = os.path.join(scripts_dir, script_filename)

        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(content.script_code)
        files_created.append(f"scripts/{script_filename}")
        log.info(f"[SkillBundleWriter] 写入脚本: {script_path}")

    # 5. 写入 Nextflow 文件
    if is_nextflow_type(executor_type) and content.nextflow_bundle:
        nf_path = os.path.join(nextflow_dir, "process.nf")
        nf_content = content.nextflow_bundle.full_code or _compose_nextflow_code(content.nextflow_bundle)

        with open(nf_path, 'w', encoding='utf-8') as f:
            f.write(nf_content)
        files_created.append("nextflow/process.nf")
        log.info(f"[SkillBundleWriter] 写入 Nextflow: {nf_path}")

    # 6. 写入额外脚本
    for script in content.additional_scripts:
        script_path = os.path.join(scripts_dir, script.filename)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script.content)
        files_created.append(f"scripts/{script.filename}")
        log.info(f"[SkillBundleWriter] 写入额外脚本: {script_path}")

    return {
        "skill_id": skill_id,
        "bundle_path": bundle_path,
        "files_created": files_created
    }


def _generate_skill_md(content: SkillBundleContent) -> str:
    """
    生成符合规范的 SKILL.md 文件内容

    格式：
    1. YAML Frontmatter (---包裹)
    2. 技能意图与功能边界
    3. 动态参数定义规范 (参数表格)
    4. 操作指令与专家级知识库

    Args:
        content: 技能包内容

    Returns:
        完整的 SKILL.md 文件内容
    """
    return _generate_skill_md_content(content.metadata, content.description, content.parameters_schema, content.expert_knowledge)


def _generate_skill_md_content(
    metadata: SkillBundleMetadata,
    description: str = "",
    parameters_schema: Dict[str, Any] = None,
    expert_knowledge: str = ""
) -> str:
    """
    生成符合规范的 SKILL.md 文件内容（支持独立调用）

    格式：
    1. YAML Frontmatter (---包裹)
    2. 技能意图与功能边界
    3. 动态参数定义规范 (参数表格)
    4. 操作指令与专家级知识库

    Args:
        metadata: 技能元数据
        description: 功能描述
        parameters_schema: 参数 Schema
        expert_knowledge: 专家知识

    Returns:
        完整的 SKILL.md 文件内容
    """
    if parameters_schema is None:
        parameters_schema = {"type": "object", "properties": {}, "required": []}

    lines = []

    # ==========================================
    # 1. YAML Frontmatter
    # ==========================================
    lines.append("---")
    lines.append("# ==========================================")
    lines.append("# 核心系统元数据 (Core System Metadata)")
    lines.append("# ------------------------------------------")
    lines.append("# 以下区域为 YAML 格式，供后端系统路由和调度引擎直接读取")
    lines.append("# ==========================================")
    lines.append("")

    meta = metadata
    lines.append(f'skill_id: "{meta.skill_id}"')
    lines.append(f'name: "{meta.name}"')
    lines.append(f'version: "{meta.version}"')
    lines.append(f'author: "{meta.author}"')
    lines.append(f'executor_type: "{meta.executor_type.value}"')

    # 入口点逻辑
    if is_script_type(meta.executor_type):
        entry_point = f"scripts/{get_script_filename(meta.executor_type)}"
    elif is_nextflow_type(meta.executor_type):
        entry_point = "none"
    else:
        entry_point = "none"

    lines.append(f'entry_point: "{entry_point}"')
    lines.append(f'timeout_seconds: {meta.timeout_seconds}')

    # 分类信息
    lines.append("# 分类信息")
    lines.append(f'category: "{meta.category}"')
    lines.append(f'category_name: "{meta.category_name}"')

    if meta.subcategory:
        lines.append(f'subcategory: "{meta.subcategory}"')
        lines.append(f'subcategory_name: "{meta.subcategory_name}"')

    # 标签
    tags_str = ", ".join([f'"{tag}"' for tag in meta.tags])
    lines.append(f'tags: [{tags_str}]')

    lines.append("---")
    lines.append("")

    # ==========================================
    # 2. 技能意图与功能边界
    # ==========================================
    lines.append("## 1. 技能意图与功能边界 (Intent & Scope)")
    lines.append("")
    lines.append("*面向 AI 的核心描述，帮助其判断在何种场景下应该召唤此工具。*")
    lines.append("")
    lines.append(description or f"{meta.name} - 由 SKILL Forge 自动生成的标准化技能包。")
    lines.append("")

    # ==========================================
    # 3. 动态参数定义规范
    # ==========================================
    lines.append("## 2. 动态参数定义规范 (Parameters Schema)")
    lines.append("")
    lines.append("*系统底层的解析器将扫描此表格并转换为严格的 JSON Schema，并在前端渲染动态配置卡片。*")
    lines.append("")

    # 参数表格
    lines.append("| 参数键名 (Key) | 数据类型 (Type) | 必填 (Required) | 默认值 (Default) | 详细描述说明 (Detailed Description) |")
    lines.append("|---|---|---|---|---|")

    properties = parameters_schema.get("properties", {})
    required_fields = parameters_schema.get("required", [])

    for param_name, param_info in properties.items():
        param_type = param_info.get("type", "string")
        param_desc = param_info.get("description", "")
        default_value = param_info.get("default", "")
        is_required = param_name in required_fields

        # 格式化必填
        required_str = "是 (Yes)" if is_required else "否 (No)"

        # 处理特殊类型
        if param_info.get("format") == "directorypath":
            param_type = "DirectoryPath"
        elif param_info.get("format") == "filepath":
            param_type = "FilePath"

        # 格式化类型
        type_display = param_type.capitalize() if param_type in ["string", "number", "integer", "boolean", "array"] else param_type

        # 处理默认值显示
        default_display = str(default_value) if default_value != "" else ""

        lines.append(f"| `{param_name}` | {type_display} | {required_str} | {default_display} | {param_desc} |")

    lines.append("")

    # ==========================================
    # 4. 操作指令与专家级知识库
    # ==========================================
    lines.append("## 3. 操作指令与专家级知识库 (Operational Directives & Expert Knowledge)")
    lines.append("")
    lines.append("*这里包含了系统赋予大模型的"锦囊妙计"，塑造其资深生信架构师的专业表现。*")
    lines.append("")

    if expert_knowledge:
        lines.append(expert_knowledge)
    else:
        lines.append("- **触发条件**：当用户需要进行相关分析时调用此技能。")
        lines.append("- **参数配置**：请根据实际数据情况配置必要的参数。")
        lines.append("- **结果解读**：请结合生物学背景对结果进行解读。")

    lines.append("")

    return "\n".join(lines)


def _compose_nextflow_code(bundle: NextflowBundle) -> str:
    """
    组合 Nextflow 代码片段为完整的 process.nf

    Args:
        bundle: Nextflow 工作流包

    Returns:
        完整的 process.nf 文件内容
    """
    lines = []

    # 添加注释头
    lines.append("// Auto-generated Nextflow Pipeline")
    lines.append(f"// Generated by SKILL Forge at {datetime.now().isoformat()}")
    lines.append("")

    # 添加 Process 定义
    for process in bundle.processes:
        lines.append(process.code)
        lines.append("")

    # 添加 Workflow
    if bundle.workflow:
        lines.append(bundle.workflow.code)
    elif bundle.processes:
        # 自动生成简单的 workflow
        lines.append("workflow {")
        for i, process in enumerate(bundle.processes):
            lines.append(f"    // Execute {process.name}")
            if i == 0:
                lines.append(f"    {process.name}(input_channel)")
            else:
                lines.append(f"    {process.name}({bundle.processes[i-1].name}.out)")
        lines.append("}")

    return "\n".join(lines)


def write_blueprint_skill(
    skill_id: str,
    name: str,
    description: str,
    parameters_schema: Dict[str, Any],
    nextflow_code: str,
    expert_knowledge: str = "",
    skills_dir: str = "/app/skills",
    category: str = "general",
    category_name: str = "通用",
    tags: List[str] = None
) -> Dict[str, Any]:
    """
    快速写入 Nextflow 蓝图技能

    这是一个便捷函数，用于快速创建 Logical_Blueprint 类型的技能包

    Args:
        skill_id: 技能 ID
        name: 技能名称
        description: 功能描述
        parameters_schema: 参数 Schema
        nextflow_code: Nextflow 代码
        expert_knowledge: 专家知识
        skills_dir: 技能目录
        category: 一级分类
        category_name: 分类显示名
        tags: 标签列表

    Returns:
        写入结果
    """
    if tags is None:
        tags = []

    # 构建元数据
    metadata = SkillBundleMetadata(
        skill_id=skill_id,
        name=name,
        executor_type=ExecutorType.LOGICAL_BLUEPRINT,
        category=category,
        category_name=category_name,
        tags=tags
    )

    # 构建 Nextflow Bundle
    nextflow_bundle = NextflowBundle(full_code=nextflow_code)

    # 构建完整内容
    content = SkillBundleContent(
        metadata=metadata,
        description=description,
        parameters_schema=parameters_schema,
        expert_knowledge=expert_knowledge,
        nextflow_bundle=nextflow_bundle
    )

    return write_skill_bundle(content, skills_dir)


def write_script_skill(
    skill_id: str,
    name: str,
    description: str,
    parameters_schema: Dict[str, Any],
    script_code: str,
    executor_type: ExecutorType,
    dependencies: List[str] = None,
    expert_knowledge: str = "",
    skills_dir: str = "/app/skills",
    category: str = "general",
    category_name: str = "通用",
    tags: List[str] = None
) -> Dict[str, Any]:
    """
    快速写入单脚本技能

    这是一个便捷函数，用于快速创建 Python_env 或 R_env 类型的技能包

    Args:
        skill_id: 技能 ID
        name: 技能名称
        description: 功能描述
        parameters_schema: 参数 Schema
        script_code: 脚本代码
        executor_type: 执行器类型
        dependencies: 依赖列表
        expert_knowledge: 专家知识
        skills_dir: 技能目录
        category: 一级分类
        category_name: 分类显示名
        tags: 标签列表

    Returns:
        写入结果
    """
    if dependencies is None:
        dependencies = []
    if tags is None:
        tags = []

    # 构建元数据
    metadata = SkillBundleMetadata(
        skill_id=skill_id,
        name=name,
        executor_type=executor_type,
        category=category,
        category_name=category_name,
        tags=tags
    )

    # 构建完整内容
    content = SkillBundleContent(
        metadata=metadata,
        description=description,
        parameters_schema=parameters_schema,
        expert_knowledge=expert_knowledge,
        script_code=script_code,
        dependencies=dependencies
    )

    return write_skill_bundle(content, skills_dir)


def generate_skill_md(
    skill_id: str,
    name: str,
    executor_type: str,
    description: str = "",
    parameters_schema: Dict[str, Any] = None,
    expert_knowledge: str = "",
    category: str = "general",
    category_name: str = "通用",
    tags: List[str] = None
) -> str:
    """
    生成 SKILL.md 内容（对外暴露的便捷函数）

    Args:
        skill_id: 技能 ID
        name: 技能名称
        executor_type: 执行器类型
        description: 功能描述
        parameters_schema: 参数 Schema
        expert_knowledge: 专家知识
        category: 一级分类
        category_name: 分类显示名
        tags: 标签列表

    Returns:
        SKILL.md 文件内容
    """
    if tags is None:
        tags = []

    metadata = SkillBundleMetadata(
        skill_id=skill_id,
        name=name,
        executor_type=ExecutorType(executor_type),
        category=category,
        category_name=category_name,
        tags=tags
    )

    return _generate_skill_md_content(
        metadata=metadata,
        description=description,
        parameters_schema=parameters_schema,
        expert_knowledge=expert_knowledge
    )


log.info("📦 SKILL Bundle Writer 已加载")