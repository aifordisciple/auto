"""
Genome API 路由 - 参考基因组资产管理

功能说明：
- 提供参考基因组的 CRUD 操作
- 支持与 besaltpipe 流程框架无缝集成
- 权限控制：公开/团队/私有级别
- TSV 批量导入/导出功能
- 文件路径验证功能

权限逻辑：
- 管理员可创建公开基因组（所有用户可见）
- 普通用户只能创建私有基因组
- 用户可将私有基因组共享给特定用户
"""

import os
import csv
import io
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select, or_

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User,
    GenomeAsset,
    GenomeAssetCreate,
    GenomeAssetUpdate,
    GenomeAssetPublic,
    get_utc_now
)

router = APIRouter()


# ==========================================
# 辅助函数
# ==========================================

def check_genome_access(genome: GenomeAsset, user: User, require_owner: bool = False) -> bool:
    """
    检查用户是否有权限访问基因组

    权限规则：
    - 公开基因组：所有登录用户可查看
    - 私有基因组：仅所有者可查看
    - 共享基因组：所有者和被共享用户可查看
    - require_owner=True 时，必须为所有者

    参数：
        genome: 基因组对象
        user: 当前用户
        require_owner: 是否要求所有者权限

    返回：
        bool: 是否有权限
    """
    if require_owner:
        # 需要所有者权限（用于编辑、删除等操作）
        return genome.owner_id == user.id or user.is_superuser

    # 查看权限
    if genome.visibility == "public":
        return True
    if genome.owner_id == user.id:
        return True
    if user.id in genome.shared_with:
        return True
    # 管理员可查看所有基因组
    if user.is_superuser:
        return True
    return False


def can_create_public(user: User) -> bool:
    """检查用户是否可以创建公开基因组"""
    return user.is_superuser


# ==========================================
# 请求模型
# ==========================================

class ShareRequest(BaseModel):
    """共享请求"""
    user_ids: List[int] = Field(description="要共享给的用户 ID 列表")


class ValidateRequest(BaseModel):
    """验证请求"""
    paths: Optional[List[str]] = Field(default=None, description="要验证的路径列表，为空则验证所有路径")


# ==========================================
# API 端点
# ==========================================

@router.get("/", response_model=List[GenomeAssetPublic])
async def list_genomes(
    species: Optional[str] = Query(None, description="按物种筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    include_inactive: bool = Query(False, description="是否包含禁用的基因组"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    获取基因组列表

    返回用户有权访问的所有基因组：
    - 所有公开基因组
    - 用户创建的私有基因组
    - 共享给用户的基因组

    参数：
        species: 按物种筛选
        search: 搜索 genomeid、species、version
        include_inactive: 是否包含禁用的基因组
    """
    # 构建基础查询：获取公开的、自己的、共享给自己的基因组
    statement = select(GenomeAsset)

    # 权限过滤
    conditions = [
        GenomeAsset.visibility == "public",  # 公开的
        GenomeAsset.owner_id == current_user.id,  # 自己的
    ]
    # 注意：shared_with 是 JSONB 数组，需要特殊处理
    # 使用 PostgreSQL 的 @> 操作符检查数组是否包含元素

    statement = statement.where(or_(*conditions))

    # 物种筛选
    if species:
        statement = statement.where(GenomeAsset.species == species)

    # 搜索
    if search:
        search_pattern = f"%{search}%"
        statement = statement.where(
            or_(
                GenomeAsset.genomeid.ilike(search_pattern),
                GenomeAsset.species.ilike(search_pattern),
                GenomeAsset.version.ilike(search_pattern)
            )
        )

    # 状态筛选
    if not include_inactive:
        statement = statement.where(GenomeAsset.is_active == True)

    # 排序
    statement = statement.order_by(GenomeAsset.created_at.desc())

    genomes = session.exec(statement).all()

    # 额外过滤：检查 shared_with 数组
    # SQLModel 的 or_ 条件无法直接处理 JSONB 数组包含查询
    # 所以我们在 Python 层面进行二次过滤
    all_genomes = []
    for genome in genomes:
        if genome.visibility == "public":
            all_genomes.append(genome)
        elif genome.owner_id == current_user.id:
            all_genomes.append(genome)
        elif current_user.id in genome.shared_with:
            all_genomes.append(genome)
        elif current_user.is_superuser:
            all_genomes.append(genome)

    return all_genomes


@router.get("/species/list")
async def list_species(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    获取物种列表及计数

    返回所有有基因组的物种及其数量，用于筛选下拉框
    """
    # 获取所有可见基因组
    statement = select(GenomeAsset).where(GenomeAsset.is_active == True)
    genomes = session.exec(statement).all()

    # 过滤权限
    visible_genomes = [
        g for g in genomes
        if g.visibility == "public"
        or g.owner_id == current_user.id
        or current_user.id in g.shared_with
        or current_user.is_superuser
    ]

    # 统计物种
    species_count: Dict[str, int] = {}
    for genome in visible_genomes:
        species_count[genome.species] = species_count.get(genome.species, 0) + 1

    # 转换为列表并排序
    result = [
        {"species": species, "count": count}
        for species, count in sorted(species_count.items(), key=lambda x: -x[1])
    ]

    return {"status": "success", "data": result}


@router.get("/{genomeid}", response_model=GenomeAssetPublic)
async def get_genome(
    genomeid: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """获取单个基因组详情"""
    genome = session.exec(
        select(GenomeAsset).where(GenomeAsset.genomeid == genomeid)
    ).first()

    if not genome:
        raise HTTPException(status_code=404, detail=f"基因组 '{genomeid}' 不存在")

    if not check_genome_access(genome, current_user):
        raise HTTPException(status_code=403, detail="无权访问此基因组")

    return genome


@router.get("/{genomeid}/config")
async def get_genome_config(
    genomeid: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    获取基因组配置（besaltpipe 兼容格式）

    返回与 besaltpipe Genome.allgenome[genomeid] 相同格式的字典
    用于 SKILL 执行时获取基因组配置
    """
    genome = session.exec(
        select(GenomeAsset).where(GenomeAsset.genomeid == genomeid)
    ).first()

    if not genome:
        raise HTTPException(status_code=404, detail=f"基因组 '{genomeid}' 不存在")

    if not check_genome_access(genome, current_user):
        raise HTTPException(status_code=403, detail="无权访问此基因组")

    return genome.to_besaltpipe_dict()


@router.post("/", response_model=GenomeAssetPublic)
async def create_genome(
    genome_in: GenomeAssetCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    创建新基因组

    权限规则：
    - 管理员可创建公开基因组（visibility=public）
    - 普通用户只能创建私有基因组（visibility=private）
    """
    # 检查 genomeid 是否已存在
    existing = session.exec(
        select(GenomeAsset).where(GenomeAsset.genomeid == genome_in.genomeid)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"基因组标识 '{genome_in.genomeid}' 已存在")

    # 权限检查：普通用户不能创建公开基因组
    if genome_in.visibility == "public" and not can_create_public(current_user):
        raise HTTPException(status_code=403, detail="普通用户只能创建私有基因组")

    # 创建基因组
    genome_data = genome_in.model_dump()
    genome = GenomeAsset(
        **genome_data,
        owner_id=current_user.id
    )

    session.add(genome)
    session.commit()
    session.refresh(genome)

    log.info(f"用户 {current_user.email} 创建了基因组 {genome.genomeid}")

    return genome


@router.put("/{genomeid}", response_model=GenomeAssetPublic)
async def update_genome(
    genomeid: str,
    genome_in: GenomeAssetUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """更新基因组信息"""
    genome = session.exec(
        select(GenomeAsset).where(GenomeAsset.genomeid == genomeid)
    ).first()

    if not genome:
        raise HTTPException(status_code=404, detail=f"基因组 '{genomeid}' 不存在")

    # 权限检查：需要所有者权限
    if not check_genome_access(genome, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权修改此基因组")

    # 更新字段
    update_data = genome_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(genome, key, value)

    genome.updated_at = get_utc_now()
    session.add(genome)
    session.commit()
    session.refresh(genome)

    log.info(f"用户 {current_user.email} 更新了基因组 {genome.genomeid}")

    return genome


@router.delete("/{genomeid}")
async def delete_genome(
    genomeid: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """删除基因组"""
    genome = session.exec(
        select(GenomeAsset).where(GenomeAsset.genomeid == genomeid)
    ).first()

    if not genome:
        raise HTTPException(status_code=404, detail=f"基因组 '{genomeid}' 不存在")

    # 权限检查：需要所有者权限
    if not check_genome_access(genome, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权删除此基因组")

    session.delete(genome)
    session.commit()

    log.info(f"用户 {current_user.email} 删除了基因组 {genomeid}")

    return {"status": "success", "message": f"基因组 '{genomeid}' 已删除"}


@router.post("/{genomeid}/share")
async def share_genome(
    genomeid: str,
    share_in: ShareRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    共享基因组给其他用户

    将私有基因组共享给指定用户列表
    """
    genome = session.exec(
        select(GenomeAsset).where(GenomeAsset.genomeid == genomeid)
    ).first()

    if not genome:
        raise HTTPException(status_code=404, detail=f"基因组 '{genomeid}' 不存在")

    # 权限检查：需要所有者权限
    if not check_genome_access(genome, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权共享此基因组")

    # 验证用户 ID 是否存在
    valid_user_ids = []
    for user_id in share_in.user_ids:
        user = session.get(User, user_id)
        if user:
            valid_user_ids.append(user_id)
        else:
            log.warning(f"共享失败：用户 ID {user_id} 不存在")

    # 更新共享列表（合并现有共享）
    current_shared = list(set(genome.shared_with + valid_user_ids))
    genome.shared_with = current_shared
    genome.updated_at = get_utc_now()

    session.add(genome)
    session.commit()

    log.info(f"用户 {current_user.email} 将基因组 {genomeid} 共享给了 {len(valid_user_ids)} 个用户")

    return {
        "status": "success",
        "message": f"已共享给 {len(valid_user_ids)} 个用户",
        "shared_with": current_shared
    }


@router.post("/{genomeid}/unshare")
async def unshare_genome(
    genomeid: str,
    share_in: ShareRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """取消共享基因组"""
    genome = session.exec(
        select(GenomeAsset).where(GenomeAsset.genomeid == genomeid)
    ).first()

    if not genome:
        raise HTTPException(status_code=404, detail=f"基因组 '{genomeid}' 不存在")

    if not check_genome_access(genome, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权取消共享")

    # 从共享列表中移除用户
    genome.shared_with = [uid for uid in genome.shared_with if uid not in share_in.user_ids]
    genome.updated_at = get_utc_now()

    session.add(genome)
    session.commit()

    return {"status": "success", "message": f"已取消共享给 {len(share_in.user_ids)} 个用户"}


@router.post("/{genomeid}/validate")
async def validate_genome_paths(
    genomeid: str,
    validate_in: ValidateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    验证基因组文件路径是否存在

    检查指定的路径列表是否存在，或检查所有配置的路径
    """
    genome = session.exec(
        select(GenomeAsset).where(GenomeAsset.genomeid == genomeid)
    ).first()

    if not genome:
        raise HTTPException(status_code=404, detail=f"基因组 '{genomeid}' 不存在")

    if not check_genome_access(genome, current_user):
        raise HTTPException(status_code=403, detail="无权访问此基因组")

    # 获取要验证的路径
    path_fields = [
        "genome", "chrlen", "gff", "gffdb", "gtf", "geneanno", "genelen", "genome_info",
        "bowtie2_index", "bowtie1_index", "bwa_index", "star_index", "hisat2_index",
        "novoalign_index", "minimap2_index", "minimap2_juncbed", "rsem_index", "noncode_index",
        "ref10x", "sc_star", "sc_gtf", "godes", "known_lncRNA"
    ]

    results = {}

    if validate_in.paths:
        # 验证指定路径
        for path in validate_in.paths:
            exists = os.path.exists(path) if path else False
            results[path] = {"exists": exists, "is_directory": os.path.isdir(path) if exists else False}
    else:
        # 验证所有配置的路径
        for field in path_fields:
            path = getattr(genome, field, None)
            if path:
                exists = os.path.exists(path)
                results[field] = {
                    "path": path,
                    "exists": exists,
                    "is_directory": os.path.isdir(path) if exists else False
                }

    # 统计
    total = len(results)
    existing = sum(1 for r in results.values() if r.get("exists", False))

    return {
        "status": "success",
        "genomeid": genomeid,
        "total_paths": total,
        "existing_paths": existing,
        "missing_paths": total - existing,
        "results": results
    }


@router.post("/{genomeid}/toggle-active")
async def toggle_genome_active(
    genomeid: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """切换基因组启用/禁用状态"""
    genome = session.exec(
        select(GenomeAsset).where(GenomeAsset.genomeid == genomeid)
    ).first()

    if not genome:
        raise HTTPException(status_code=404, detail=f"基因组 '{genomeid}' 不存在")

    if not check_genome_access(genome, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权修改此基因组")

    genome.is_active = not genome.is_active
    genome.updated_at = get_utc_now()

    session.add(genome)
    session.commit()

    status = "已启用" if genome.is_active else "已禁用"
    log.info(f"用户 {current_user.email} {status} 基因组 {genomeid}")

    return {
        "status": "success",
        "is_active": genome.is_active,
        "message": f"基因组 '{genomeid}' {status}"
    }


@router.post("/import-tsv")
async def import_genomes_tsv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    从 TSV 文件批量导入基因组

    仅管理员可用，用于从 genome_db.xls 导入现有数据
    TSV 格式与 genome_db.xls 完全兼容
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="仅管理员可导入基因组")

    # 读取文件内容
    content = await file.read()
    content_str = content.decode('utf-8')

    # 解析 TSV
    reader = csv.DictReader(io.StringIO(content_str), delimiter='\t')

    imported = []
    skipped = []
    errors = []

    for row_num, row in enumerate(reader, start=2):  # 从第2行开始（第1行是标题）
        try:
            genomeid = row.get('genomeid', '').strip()
            if not genomeid:
                errors.append(f"第 {row_num} 行：缺少 genomeid")
                continue

            # 检查是否已存在
            existing = session.exec(
                select(GenomeAsset).where(GenomeAsset.genomeid == genomeid)
            ).first()
            if existing:
                skipped.append({"genomeid": genomeid, "reason": "已存在"})
                continue

            # 创建基因组
            genome = GenomeAsset(
                genomeid=genomeid,
                species=row.get('species', ''),
                version=row.get('version', ''),
                species_code=row.get('species_code') or None,
                url=row.get('url') or None,
                date=row.get('date') or None,
                genome=row.get('genome', ''),
                chrlen=row.get('chrlen') or None,
                gff=row.get('gff') or None,
                gffdb=row.get('gffdb') or None,
                gtf=row.get('gtf') or None,
                geneanno=row.get('geneanno') or None,
                genelen=row.get('genelen') or None,
                genome_info=row.get('genome_info') or None,
                bowtie2_index=row.get('bowtie2_index') or None,
                bowtie1_index=row.get('bowtie1_index') or None,
                bwa_index=row.get('bwa_index') or None,
                star_index=row.get('star_index') or None,
                hisat2_index=row.get('hisat2_index') or None,
                novoalign_index=row.get('novoalign_index') or None,
                minimap2_index=row.get('minimap2_index') or None,
                minimap2_juncbed=row.get('minimap2_juncbed') or None,
                rsem_index=row.get('rsem_index') or None,
                noncode_index=row.get('noncode_index') or None,
                ref10x=row.get('ref10x') or None,
                sc_star=row.get('sc_star') or None,
                sc_gtf=row.get('sc_gtf') or None,
                godes=row.get('godes') or None,
                kg=row.get('kg') or None,
                known_lncRNA=row.get('known_lncRNA') or None,
                bsgenome=row.get('bsgenome') or None,
                geneid_or_symbol=row.get('geneid_or_symbol', 'symbol'),
                owner_id=current_user.id,
                visibility="public"
            )

            session.add(genome)
            imported.append(genomeid)

        except Exception as e:
            errors.append(f"第 {row_num} 行：{str(e)}")

    session.commit()

    log.info(f"管理员 {current_user.email} 导入了 {len(imported)} 个基因组")

    return {
        "status": "success",
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "imported": imported,
        "skipped": skipped,
        "errors": errors
    }


@router.get("/export/tsv")
async def export_genomes_tsv(
    species: Optional[str] = Query(None, description="按物种筛选"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    导出基因组为 TSV 格式

    导出用户可见的所有基因组，格式与 genome_db.xls 兼容
    """
    # 获取基因组列表
    statement = select(GenomeAsset).where(GenomeAsset.is_active == True)
    if species:
        statement = statement.where(GenomeAsset.species == species)

    genomes = session.exec(statement).all()

    # 过滤权限
    visible_genomes = [
        g for g in genomes
        if g.visibility == "public"
        or g.owner_id == current_user.id
        or current_user.id in g.shared_with
        or current_user.is_superuser
    ]

    # 生成 TSV 内容
    output = io.StringIO()
    fieldnames = [
        'genomeid', 'species', 'version', 'species_code', 'url', 'date',
        'genome', 'chrlen', 'gff', 'gffdb', 'gtf', 'geneanno', 'genelen', 'genome_info',
        'bowtie2_index', 'bowtie1_index', 'bwa_index', 'star_index', 'hisat2_index',
        'novoalign_index', 'minimap2_index', 'minimap2_juncbed', 'rsem_index', 'noncode_index',
        'ref10x', 'sc_star', 'sc_gtf', 'godes', 'kg', 'known_lncRNA', 'bsgenome', 'geneid_or_symbol'
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter='\t', extrasaction='ignore')
    writer.writeheader()

    for genome in visible_genomes:
        row = {field: getattr(genome, field, '') or '' for field in fieldnames}
        writer.writerow(row)

    # 返回文件流
    output.seek(0)
    content = output.getvalue()

    return StreamingResponse(
        iter([content]),
        media_type="text/tab-separated-values",
        headers={
            "Content-Disposition": f"attachment; filename=genome_db_{get_utc_now().strftime('%Y%m%d')}.tsv"
        }
    )