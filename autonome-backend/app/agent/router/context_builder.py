"""
L1 上下文构建器 - 将原始前端上下文转换为结构化 WorkspaceContext。

核心功能：
1. build_workspace_context(context): 从原始字典构建 WorkspaceContext 模型
2. format_workspace_context_for_prompt(ws): 将 WorkspaceContext 格式化为 L1 提示词文本

设计原则：
- 防御性解析：所有字段都有默认值，不会因缺失字段而报错
- 信息密度控制：recent_files 和 active_skills 限制最多 10 项
- 类型推断：从文件扩展名推断文件类型，供 L1 指代消解使用

V2.1 新增（Phase 2）：
- 替代 L1 中 str(context) 的原始注入方式
- 为指代消解提供结构化的实体列表（文件 ID、技能 ID）
"""
from typing import Any, Dict, List

from app.agent.router.schemas import WorkspaceContext
from app.core.logger import log


# 文件扩展名 → 生物信息学文件类型映射
FILE_TYPE_MAP = {
    ".h5ad": "AnnData",
    ".csv": "CSV",
    ".tsv": "TSV",
    ".txt": "TXT",
    ".fastq": "FASTQ",
    ".fq": "FASTQ",
    ".bam": "BAM",
    ".sam": "SAM",
    ".bed": "BED",
    ".gff": "GFF",
    ".gtf": "GTF",
    ".fa": "FASTA",
    ".fasta": "FASTA",
    ".pdf": "PDF",
    ".rds": "RDS",
    ".mtx": "MTX",
    ".vcf": "VCF",
    ".pdb": "PDB",
    ".sra": "SRA",
    ".fastq.gz": "FASTQ (gzipped)",
    ".tar.gz": "Archive (gzipped)",
}


def build_workspace_context(context: Dict[str, Any]) -> WorkspaceContext:
    """
    从原始前端上下文字典构建结构化 WorkspaceContext。

    程序说明：
    前端注入的 context 是一个扁平字典，字段名和类型不固定。
    此函数防御性地提取各字段，确保不会因缺失或类型不匹配而报错。
    提取后的 WorkspaceContext 供 format_workspace_context_for_prompt 使用。

    Args:
        context: 前端注入的工作区上下文字典

    Returns:
        WorkspaceContext: 结构化的工作区上下文模型
    """
    if not context:
        return WorkspaceContext()

    # 提取活跃文件
    active_file = context.get("active_file")
    active_file_type = _infer_file_type(active_file) if active_file else None

    # 提取最近文件列表
    context_files = context.get("context_files", [])
    recent_files = _parse_file_list(context_files)

    # 提取可用技能
    available_skills = context.get("available_skills", [])
    active_skills = _parse_skill_list(available_skills)

    # 提取上次执行结果
    last_execution_status = context.get("last_execution_status")
    last_execution_result = context.get("last_execution_result")
    # last_execution_result 可能是 dict 或 str，统一转为 str 并截断
    if last_execution_result and not isinstance(last_execution_result, str):
        last_execution_result = str(last_execution_result)[:200]

    # 生成工作区摘要
    workspace_summary = _generate_summary(
        active_file, recent_files, active_skills, last_execution_status
    )

    ws_ctx = WorkspaceContext(
        active_file=active_file,
        active_file_type=active_file_type,
        recent_files=recent_files[:10],  # 限制最多 10 个
        active_skills=active_skills[:10],
        last_execution_status=last_execution_status,
        last_execution_result=last_execution_result,
        workspace_summary=workspace_summary,
    )

    log.debug(
        f"[ContextBuilder] 构建上下文: active_file={active_file}, "
        f"recent_files={len(recent_files)}, active_skills={len(active_skills)}, "
        f"last_status={last_execution_status}"
    )

    return ws_ctx


def format_workspace_context_for_prompt(ws: WorkspaceContext) -> str:
    """
    将 WorkspaceContext 格式化为 L1 提示词中的结构化文本。

    程序说明：
    按照固定的 Markdown 格式输出各上下文段落，确保 LLM 能可靠解析。
    每个段落使用 ### 标题分隔，列表项使用 - 前缀。
    空字段不输出，避免冗余信息干扰 LLM。

    Args:
        ws: 结构化的工作区上下文模型

    Returns:
        格式化的上下文文本，供 L1 提示词模板填充
    """
    sections = []

    # 活跃文件
    if ws.active_file:
        file_info = f"- 文件: {ws.active_file}"
        if ws.active_file_type:
            file_info += f" (类型: {ws.active_file_type})"
        sections.append(f"### 当前活跃文件\n{file_info}")

    # 最近文件列表
    if ws.recent_files:
        files_str = "\n".join(
            f"  - {f['name']} (ID: {f['id']}, 类型: {f['type']})"
            for f in ws.recent_files
        )
        sections.append(f"### 最近文件列表\n{files_str}")

    # 可用技能
    if ws.active_skills:
        skills_str = "\n".join(
            f"  - {s['name']} (ID: {s['id']}, 分类: {s['category']})"
            for s in ws.active_skills
        )
        sections.append(f"### 可用技能\n{skills_str}")

    # 上次执行结果
    if ws.last_execution_status:
        result_str = f"- 状态: {ws.last_execution_status}"
        if ws.last_execution_result:
            result_str += f"\n- 摘要: {ws.last_execution_result}"
        sections.append(f"### 上次执行结果\n{result_str}")

    # 工作区摘要
    if ws.workspace_summary:
        sections.append(f"### 工作区摘要\n{ws.workspace_summary}")

    if not sections:
        return "无可用上下文"

    return "\n\n".join(sections)


def _infer_file_type(filename: str) -> str:
    """
    从文件名推断生物信息学文件类型。

    程序说明：
    优先匹配复合扩展名（如 .fastq.gz），再匹配简单扩展名。
    未匹配时返回 "unknown"。

    Args:
        filename: 文件名或路径

    Returns:
        文件类型字符串
    """
    if not filename:
        return "unknown"

    filename_lower = filename.lower()

    # 优先匹配复合扩展名
    for ext, ftype in FILE_TYPE_MAP.items():
        if ext.startswith(".") and "." in ext[1:]:
            if filename_lower.endswith(ext):
                return ftype

    # 匹配简单扩展名
    for ext, ftype in FILE_TYPE_MAP.items():
        if ext.startswith(".") and "." not in ext[1:]:
            if filename_lower.endswith(ext):
                return ftype

    return "unknown"


def _parse_file_list(context_files: Any) -> List[Dict[str, str]]:
    """
    解析前端传入的文件列表。

    程序说明：
    防御性解析：context_files 可能是 list、dict 或 None。
    每个文件项提取 id、name、type 三个字段，缺失时使用空字符串。
    从文件名推断类型，覆盖前端未提供 type 的情况。

    Args:
        context_files: 前端传入的文件列表

    Returns:
        标准化的文件列表
    """
    if not isinstance(context_files, list):
        return []

    result = []
    for f in context_files:
        if isinstance(f, dict):
            name = f.get("name", "")
            result.append({
                "id": f.get("id", ""),
                "name": name,
                "type": f.get("type", "") or _infer_file_type(name),
            })
        elif isinstance(f, str):
            result.append({
                "id": f,
                "name": f,
                "type": _infer_file_type(f),
            })

    return result


def _parse_skill_list(available_skills: Any) -> List[Dict[str, str]]:
    """
    解析前端传入的技能列表。

    程序说明：
    防御性解析：available_skills 可能是 list、dict 或 None。
    每个技能项提取 id、name、category 三个字段，缺失时使用空字符串。

    Args:
        available_skills: 前端传入的技能列表

    Returns:
        标准化的技能列表
    """
    if not isinstance(available_skills, list):
        return []

    result = []
    for s in available_skills:
        if isinstance(s, dict):
            result.append({
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "category": s.get("category", ""),
            })
        elif isinstance(s, str):
            result.append({
                "id": s,
                "name": s,
                "category": "",
            })

    return result


def _generate_summary(
    active_file: str,
    recent_files: List[Dict[str, str]],
    active_skills: List[Dict[str, str]],
    last_status: str,
) -> str:
    """
    生成工作区自然语言摘要。

    程序说明：
    将工作区状态转换为简短的自然语言描述，供 LLM 快速理解上下文。
    摘要包含：活跃文件、文件数量、技能数量、上次执行状态。
    各部分用中文分号分隔，确保语义清晰。

    Args:
        active_file: 当前活跃文件
        recent_files: 最近文件列表
        active_skills: 可用技能列表
        last_status: 上次执行状态

    Returns:
        工作区自然语言摘要
    """
    parts = []
    if active_file:
        parts.append(f"用户正在查看 {active_file}")
    if recent_files:
        parts.append(f"工作区有 {len(recent_files)} 个文件")
    if active_skills:
        parts.append(f"有 {len(active_skills)} 个可用技能")
    if last_status == "failed":
        parts.append("上次执行失败，可能需要诊断")

    return "；".join(parts) if parts else ""