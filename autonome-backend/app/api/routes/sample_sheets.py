"""
Sample Sheet API Routes - Sample Sheet 生成与管理 API

提供以下端点：
- POST /api/projects/{id}/sample-sheets/generate - 扫描目录生成 Sample Sheet
- POST /api/projects/{id}/sample-sheets - 保存 Sample Sheet
- GET /api/projects/{id}/sample-sheets - 获取已保存列表
- GET /api/projects/{id}/sample-sheets/{filename} - 获取单个文件内容
- GET /api/skills/{skill_id}/sample-sheet-config - 获取 SKILL 列配置
"""

import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.database import engine
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User
from app.services.sample_sheet_generator import (
    get_sample_sheet_generator,
    SampleSheetGenerator,
    SampleEntry,
    ComparisonGroupEntry
)


# ==========================================
# Router 配置
# ==========================================

router = APIRouter(prefix="/api", tags=["sample-sheets"])


# ==========================================
# 请求/响应模型
# ==========================================

class GenerateRequest(BaseModel):
    """生成 Sample Sheet 请求"""
    directory: str = Field(..., description="要扫描的目录路径")
    scan_type: str = Field(default="fastqc", description="扫描类型: fastqc 或 singlecell")
    recursive: bool = Field(default=True, description="是否递归扫描子目录")
    auto_pair: bool = Field(default=True, description="是否自动配对双端数据（仅 FastQC 模式）")


class SampleEntryResponse(BaseModel):
    """单个样本条目响应"""
    name: str
    path: str
    data_type: str
    group: str
    read2_path: Optional[str] = None


class GenerateResponse(BaseModel):
    """生成 Sample Sheet 响应"""
    status: str = "success"
    samples: List[SampleEntryResponse]
    tsv_content: str
    column_config: List[dict]
    summary: dict
    warnings: Optional[List[str]] = None  # 新增：警告信息列表


class SaveRequest(BaseModel):
    """保存 Sample Sheet 请求"""
    filename: str = Field(..., description="文件名")
    content: str = Field(..., description="TSV 内容")
    description: Optional[str] = Field(default="", description="描述说明")


class SaveResponse(BaseModel):
    """保存响应"""
    status: str = "success"
    filename: str
    path: str


class SavedSheetInfo(BaseModel):
    """已保存的 Sample Sheet 信息"""
    filename: str
    path: str
    description: Optional[str]
    created_at: Optional[str]
    size_bytes: int


class ColumnConfig(BaseModel):
    """列配置"""
    key: str
    label: str
    required: bool
    editable: bool
    options: Optional[List[str]] = None


# ==========================================
# 比较组相关模型
# ==========================================

class ComparisonGroupRequest(BaseModel):
    """单个比较组请求"""
    case_group: str = Field(..., description="实验组/处理组")
    control_group: str = Field(..., description="对照组")
    comparison_name: Optional[str] = Field(default=None, description="比较组名称，默认自动生成")


class ComparisonGroupResponse(BaseModel):
    """单个比较组响应"""
    case_group: str
    control_group: str
    comparison_name: str


class SaveComparisonRequest(BaseModel):
    """保存比较组请求"""
    filename: str = Field(..., description="比较组文件名")
    comparisons: List[ComparisonGroupRequest] = Field(..., description="比较组列表")
    link_to_sample_sheet: Optional[str] = Field(default=None, description="关联的 Sample Sheet 文件名")


class SaveComparisonResponse(BaseModel):
    """保存比较组响应"""
    status: str = "success"
    filename: str
    path: str
    total_comparisons: int


class InferComparisonRequest(BaseModel):
    """自动推断比较组请求"""
    sample_sheet_path: Optional[str] = Field(default=None, description="Sample Sheet 文件路径")
    groups: Optional[List[str]] = Field(default=None, description="分组列表（可选，若提供则直接使用）")


class InferComparisonResponse(BaseModel):
    """自动推断比较组响应"""
    status: str = "success"
    groups: List[str]
    comparisons: List[ComparisonGroupResponse]
    tsv_content: str


# ==========================================
# API 端点
# ==========================================

@router.post("/projects/{project_id}/sample-sheets/generate", response_model=GenerateResponse)
async def generate_sample_sheet(
    project_id: str,
    request: GenerateRequest,
    current_user: User = Depends(get_current_user)
):
    """
    扫描目录生成 Sample Sheet

    扫描指定目录，自动识别样本并生成 Sample Sheet TSV 文件。

    支持：
    - FastQC 模式：扫描 FastQ 文件，自动配对双端数据
    - 单细胞模式：扫描单细胞数据，识别 10x/h5/BD/exp 等格式
    """
    log.info(f"[SampleSheets] 用户 {current_user.id} 请求生成 Sample Sheet: {request.directory}")

    generator = get_sample_sheet_generator()

    # ==========================================
    # 路径处理：将相对路径转换为项目目录下的绝对路径
    # ==========================================
    # 前端 FilePicker 返回的是相对路径（如 raw_data/fastq）
    # 需要转换为容器内的绝对路径（如 /workspace/project_123/raw_data/fastq）
    directory = request.directory

    # 判断是否为绝对路径
    if not os.path.isabs(directory):
        # 相对路径：拼接项目目录
        base_dir = f"/workspace/project_{project_id}"
        directory = os.path.join(base_dir, directory)
        log.info(f"[SampleSheets] 相对路径转换为绝对路径: {request.directory} -> {directory}")

    # 安全检查：防止路径穿越攻击
    if ".." in directory:
        raise HTTPException(status_code=400, detail="非法的目录路径")

    # 检查目录是否存在
    if not os.path.exists(directory):
        log.error(f"[SampleSheets] 目录不存在: {directory}")
        raise HTTPException(status_code=404, detail=f"目录不存在: {directory}")

    if not os.path.isdir(directory):
        log.error(f"[SampleSheets] 路径不是目录: {directory}")
        raise HTTPException(status_code=400, detail=f"路径不是目录: {directory}")

    try:
        # 根据扫描类型执行不同的扫描逻辑
        warnings = []  # 初始化警告列表

        if request.scan_type.lower() == "fastqc":
            samples = generator.scan_fastq_directory(
                directory=directory,
                recursive=request.recursive,
                auto_pair=request.auto_pair
            )
            tsv_content = generator.generate_fastqc_tsv(samples)
        elif request.scan_type.lower() in ["singlecell", "single_cell", "sc"]:
            # 单细胞扫描器返回 (samples, warnings) 元组
            samples, warnings = generator.scan_singlecell_directory(
                directory=directory,
                recursive=request.recursive
            )
            tsv_content = generator.generate_singlecell_tsv(samples)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的扫描类型: {request.scan_type}"
            )

        # 获取列配置
        column_config = generator.get_column_config(request.scan_type)

        # 生成摘要
        summary = {
            "total_samples": len(samples),
            "scan_type": request.scan_type,
            "directory": directory,  # 使用转换后的绝对路径
            "original_directory": request.directory,  # 保留原始输入路径
            "data_types": {},
            "groups": {}
        }

        for sample in samples:
            # 统计数据类型
            if sample.data_type not in summary["data_types"]:
                summary["data_types"][sample.data_type] = 0
            summary["data_types"][sample.data_type] += 1

            # 统计分组
            if sample.group:
                if sample.group not in summary["groups"]:
                    summary["groups"][sample.group] = 0
                summary["groups"][sample.group] += 1

        # 转换样本为响应格式
        sample_responses = [
            SampleEntryResponse(
                name=s.name,
                path=s.path,
                data_type=s.data_type,
                group=s.group,
                read2_path=s.read2_path
            ) for s in samples
        ]

        log.info(f"[SampleSheets] 成功生成 {len(samples)} 个样本")

        return GenerateResponse(
            status="success",
            samples=sample_responses,
            tsv_content=tsv_content,
            column_config=column_config,
            summary=summary,
            warnings=warnings if warnings else None
        )

    except Exception as e:
        log.error(f"[SampleSheets] 生成失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成 Sample Sheet 失败: {str(e)}")


@router.post("/projects/{project_id}/sample-sheets", response_model=SaveResponse)
async def save_sample_sheet(
    project_id: str,
    request: SaveRequest,
    current_user: User = Depends(get_current_user)
):
    """
    保存 Sample Sheet 文件

    将用户编辑后的 Sample Sheet 保存到项目目录中。
    """
    log.info(f"[SampleSheets] 用户 {current_user.id} 保存 Sample Sheet: {request.filename}")

    # 构建保存路径
    # Sample Sheet 保存在项目目录下的 sample_sheets 子目录
    base_dir = f"/workspace/project_{project_id}"
    sheets_dir = os.path.join(base_dir, "sample_sheets")

    # 确保目录存在
    os.makedirs(sheets_dir, exist_ok=True)

    # 处理文件名，确保以 .tsv 结尾
    filename = request.filename
    if not filename.endswith('.tsv'):
        filename += '.tsv'

    # 安全检查：防止路径遍历攻击
    if '..' in filename or '/' in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    filepath = os.path.join(sheets_dir, filename)

    try:
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(request.content)

        log.info(f"[SampleSheets] 成功保存到: {filepath}")

        return SaveResponse(
            status="success",
            filename=filename,
            path=filepath
        )

    except Exception as e:
        log.error(f"[SampleSheets] 保存失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.get("/projects/{project_id}/sample-sheets")
async def list_sample_sheets(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取项目中已保存的 Sample Sheet 列表
    """
    log.info(f"[SampleSheets] 用户 {current_user.id} 获取 Sample Sheet 列表")

    base_dir = f"/workspace/project_{project_id}"
    sheets_dir = os.path.join(base_dir, "sample_sheets")

    sheets = []

    if os.path.exists(sheets_dir):
        for filename in os.listdir(sheets_dir):
            if filename.endswith('.tsv'):
                filepath = os.path.join(sheets_dir, filename)
                stat = os.stat(filepath)

                sheets.append({
                    "filename": filename,
                    "path": filepath,
                    "size_bytes": stat.st_size,
                    "created_at": stat.st_ctime,
                    "modified_at": stat.st_mtime
                })

    # 按修改时间排序（最新的在前）
    sheets.sort(key=lambda x: x["modified_at"], reverse=True)

    return {
        "status": "success",
        "sheets": sheets,
        "total": len(sheets)
    }


@router.get("/projects/{project_id}/sample-sheets/{filename}")
async def get_sample_sheet_content(
    project_id: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取单个 Sample Sheet 文件内容
    """
    log.info(f"[SampleSheets] 用户 {current_user.id} 获取文件内容: {filename}")

    # 安全检查
    if '..' in filename or '/' in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    base_dir = f"/workspace/project_{project_id}"
    filepath = os.path.join(base_dir, "sample_sheets", filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            "status": "success",
            "filename": filename,
            "content": content
        }

    except Exception as e:
        log.error(f"[SampleSheets] 读取文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")


@router.delete("/projects/{project_id}/sample-sheets/{filename}")
async def delete_sample_sheet(
    project_id: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """
    删除 Sample Sheet 文件
    """
    log.info(f"[SampleSheets] 用户 {current_user.id} 删除文件: {filename}")

    # 安全检查
    if '..' in filename or '/' in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    base_dir = f"/workspace/project_{project_id}"
    filepath = os.path.join(base_dir, "sample_sheets", filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        os.remove(filepath)
        log.info(f"[SampleSheets] 成功删除: {filepath}")

        return {
            "status": "success",
            "message": f"已删除 {filename}"
        }

    except Exception as e:
        log.error(f"[SampleSheets] 删除失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/skills/{skill_id}/sample-sheet-config")
async def get_skill_sample_sheet_config(
    skill_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取指定 SKILL 的 Sample Sheet 列配置

    根据 SKILL 类型返回对应的列定义，用于前端渲染表格编辑器。
    """
    log.info(f"[SampleSheets] 获取 SKILL 列配置: {skill_id}")

    generator = get_sample_sheet_generator()

    # 根据 skill_id 判断类型
    skill_type = "unknown"
    if "fastqc" in skill_id.lower():
        skill_type = "fastqc"
    elif "singlecell" in skill_id.lower() or "single_cell" in skill_id.lower():
        skill_type = "singlecell"

    column_config = generator.get_column_config(skill_type)

    return {
        "status": "success",
        "skill_id": skill_id,
        "skill_type": skill_type,
        "columns": column_config
    }


@router.post("/projects/{project_id}/sample-sheets/validate")
async def validate_sample_sheet(
    project_id: str,
    request: SaveRequest,
    current_user: User = Depends(get_current_user)
):
    """
    验证 Sample Sheet 内容的有效性

    检查：
    - 列数一致性
    - 必填列存在
    - 样本名唯一性
    - 路径有效性（可选）
    """
    log.info(f"[SampleSheets] 验证 Sample Sheet: {request.filename}")

    generator = get_sample_sheet_generator()

    # 根据 skill_id 或文件名判断类型
    skill_type = "fastqc"  # 默认
    if "singlecell" in request.filename.lower() or "sc" in request.filename.lower():
        skill_type = "singlecell"

    result = generator.validate_tsv_content(request.content, skill_type)

    return {
        "status": "success",
        "validation": result
    }


# ==========================================
# 比较组 API 端点
# ==========================================

@router.post("/projects/{project_id}/sample-sheets/comparisons", response_model=SaveComparisonResponse)
async def save_comparison_groups(
    project_id: str,
    request: SaveComparisonRequest,
    current_user: User = Depends(get_current_user)
):
    """
    保存比较组定义文件

    将用户定义的比较组保存为 TSV 格式文件，与 Sample Sheet 配套使用。

    文件格式：
    # Comparison Table
    # case_group\tcontrol_group\tcomparison_name
    Treatment\tControl\tTreatment_vs_Control
    """
    log.info(f"[SampleSheets] 用户 {current_user.id} 保存比较组: {request.filename}")

    generator = get_sample_sheet_generator()

    # 构建保存路径
    base_dir = f"/workspace/project_{project_id}"
    sheets_dir = os.path.join(base_dir, "sample_sheets")

    # 确保目录存在
    os.makedirs(sheets_dir, exist_ok=True)

    # 处理文件名，确保以 .tsv 结尾
    filename = request.filename
    if not filename.endswith('.tsv'):
        filename += '.tsv'

    # 安全检查：防止路径穿越攻击
    if '..' in filename or '/' in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    filepath = os.path.join(sheets_dir, filename)

    # 转换请求为 ComparisonGroupEntry 对象
    comparisons = [
        ComparisonGroupEntry(
            case_group=comp.case_group,
            control_group=comp.control_group,
            comparison_name=comp.comparison_name
        ) for comp in request.comparisons
    ]

    # 验证比较组
    # 需要从关联的 sample_sheet 获取可用分组
    available_groups = []
    if request.link_to_sample_sheet:
        # 安全检查：防止路径穿越攻击
        if '..' in request.link_to_sample_sheet or '/' in request.link_to_sample_sheet:
            raise HTTPException(status_code=400, detail="无效的关联文件名")
        sample_sheet_path = os.path.join(sheets_dir, request.link_to_sample_sheet)
        if os.path.exists(sample_sheet_path):
            with open(sample_sheet_path, 'r', encoding='utf-8') as f:
                content = f.read()
                available_groups = generator.extract_groups_from_sample_sheet(content)

    # 如果没有关联 sample_sheet，从比较组本身提取分组
    if not available_groups:
        available_groups = [comp.case_group for comp in request.comparisons] + \
                          [comp.control_group for comp in request.comparisons]
        available_groups = list(set(available_groups))

    validation = generator.validate_comparison_groups(comparisons, available_groups)
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=f"比较组验证失败: {validation['errors']}")

    try:
        # 生成 TSV 内容
        tsv_content = generator.generate_comparison_tsv(comparisons)

        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(tsv_content)

        log.info(f"[SampleSheets] 成功保存比较组到: {filepath}")

        return SaveComparisonResponse(
            status="success",
            filename=filename,
            path=filepath,
            total_comparisons=len(comparisons)
        )

    except Exception as e:
        log.error(f"[SampleSheets] 保存比较组失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.get("/projects/{project_id}/sample-sheets/comparisons/{filename}")
async def get_comparison_groups(
    project_id: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取比较组定义文件内容

    返回已保存的比较组 TSV 文件内容，解析为结构化数据。
    """
    log.info(f"[SampleSheets] 用户 {current_user.id} 获取比较组文件: {filename}")

    # 安全检查
    if '..' in filename or '/' in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    base_dir = f"/workspace/project_{project_id}"
    filepath = os.path.join(base_dir, "sample_sheets", filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        generator = get_sample_sheet_generator()
        comparisons = generator.parse_comparison_tsv(content)

        # 转换为响应格式
        comparison_responses = [
            ComparisonGroupResponse(
                case_group=comp.case_group,
                control_group=comp.control_group,
                comparison_name=comp.comparison_name
            ) for comp in comparisons
        ]

        return {
            "status": "success",
            "filename": filename,
            "content": content,
            "comparisons": comparison_responses,
            "total_comparisons": len(comparisons)
        }

    except Exception as e:
        log.error(f"[SampleSheets] 读取比较组文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"读取失败: {str(e)}")


@router.post("/projects/{project_id}/sample-sheets/infer-comparisons", response_model=InferComparisonResponse)
async def infer_comparison_groups(
    project_id: str,
    request: InferComparisonRequest,
    current_user: User = Depends(get_current_user)
):
    """
    从 Sample Sheet 或分组列表自动推断比较组

    两种输入方式：
    1. 提供 sample_sheet_path：从文件中读取 group_label 列推断
    2. 直接提供 groups 列表：直接从分组列表推断

    推断规则：
    - 对照组关键词（control, normal, wildtype）优先排序
    - 生成所有两两组合，格式为 {case}_vs_{control}
    """
    log.info(f"[SampleSheets] 用户 {current_user.id} 请求自动推断比较组")

    generator = get_sample_sheet_generator()

    groups = []

    # 方式一：从 Sample Sheet 读取分组
    if request.sample_sheet_path:
        # 处理路径
        sample_sheet_path = request.sample_sheet_path

        # 如果是相对路径，转换为绝对路径
        if not os.path.isabs(sample_sheet_path):
            base_dir = f"/workspace/project_{project_id}"
            sample_sheet_path = os.path.join(base_dir, "sample_sheets", sample_sheet_path)

        # 安全检查
        if '..' in sample_sheet_path:
            raise HTTPException(status_code=400, detail="无效的文件路径")

        if not os.path.exists(sample_sheet_path):
            raise HTTPException(status_code=404, detail=f"Sample Sheet 文件不存在: {request.sample_sheet_path}")

        try:
            with open(sample_sheet_path, 'r', encoding='utf-8') as f:
                content = f.read()
                groups = generator.extract_groups_from_sample_sheet(content)

        except Exception as e:
            log.error(f"[SampleSheets] 读取 Sample Sheet 失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"读取 Sample Sheet 失败: {str(e)}")

    # 方式二：直接使用提供的分组列表
    elif request.groups:
        groups = request.groups

    else:
        raise HTTPException(status_code=400, detail="请提供 sample_sheet_path 或 groups 参数")

    # 推断比较组
    comparisons = generator.infer_comparison_groups(groups)

    # 生成 TSV 内容
    tsv_content = generator.generate_comparison_tsv(comparisons)

    # 转换为响应格式
    comparison_responses = [
        ComparisonGroupResponse(
            case_group=comp.case_group,
            control_group=comp.control_group,
            comparison_name=comp.comparison_name
        ) for comp in comparisons
    ]

    return InferComparisonResponse(
        status="success",
        groups=groups,
        comparisons=comparison_responses,
        tsv_content=tsv_content
    )


@router.get("/projects/{project_id}/sample-sheets/comparison-files")
async def list_comparison_files(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取项目中已保存的比较组文件列表

    返回 sample_sheets 目录下所有比较组相关的 TSV 文件。
    """
    log.info(f"[SampleSheets] 用户 {current_user.id} 获取比较组文件列表")

    base_dir = f"/workspace/project_{project_id}"
    sheets_dir = os.path.join(base_dir, "sample_sheets")

    files = []

    if os.path.exists(sheets_dir):
        for filename in os.listdir(sheets_dir):
            # 比较组文件通常以 comparison 或 comparisons 命名
            # 或者包含 vs 关键词
            if filename.endswith('.tsv'):
                filepath = os.path.join(sheets_dir, filename)

                # 尝试读取文件内容判断是否为比较组文件
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        first_lines = f.read(500)

                    # 比较组文件特征：包含 Comparison Table 注释或 case_group 列
                    if 'comparison' in first_lines.lower() or 'case_group' in first_lines.lower():
                        stat = os.stat(filepath)
                        files.append({
                            "filename": filename,
                            "path": filepath,
                            "size_bytes": stat.st_size,
                            "created_at": stat.st_ctime,
                            "modified_at": stat.st_mtime,
                            "type": "comparison"
                        })

                except Exception:
                    pass

    # 按修改时间排序（最新的在前）
    files.sort(key=lambda x: x["modified_at"], reverse=True)

    return {
        "status": "success",
        "files": files,
        "total": len(files)
    }