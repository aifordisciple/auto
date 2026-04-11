"""
Analysis Database API 路由 - 分析数据库管理

功能说明：
- 提供分析数据库的 CRUD 操作
- 管理 GO/KEGG、蛋白质、信号通路等数据库
- 权限控制：公开/团队/私有级别
- 使用统计与热度排序

数据库类型：
- annotation: 注释数据库（GO、KEGG、InterPro 等）
- pathway: 信号通路（Reactome、WikiPathways 等）
- protein: 蛋白质数据库（UniProt、PDB 等）
- variant: 变异数据库（dbSNP、ClinVar 等）
- regulation: 调控数据库（ENCODE、TFbind 等）
- metabolism: 代谢数据库（KEGG Compound、HMDB 等）
- custom: 用户自定义数据库
"""

import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select, or_

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import (
    User,
    AnalysisDatabase,
    AnalysisDatabaseCreate,
    AnalysisDatabaseUpdate,
    AnalysisDatabasePublic,
    get_utc_now
)

router = APIRouter()


# ==========================================
# 辅助函数
# ==========================================

def check_database_access(db: AnalysisDatabase, user: User, require_owner: bool = False) -> bool:
    """
    检查用户是否有权限访问数据库

    权限规则：
    - 公开数据库：所有登录用户可查看
    - 私有数据库：仅所有者可查看
    - 共享数据库：所有者和被共享用户可查看
    - require_owner=True 时，必须为所有者

    参数：
        db: 数据库对象
        user: 当前用户
        require_owner: 是否要求所有者权限

    返回：
        bool: 是否有权限
    """
    if require_owner:
        return db.owner_id == user.id or user.is_superuser

    if db.visibility == "public":
        return True
    if db.owner_id == user.id:
        return True
    if user.id in db.shared_with:
        return True
    if user.is_superuser:
        return True
    return False


def can_create_public(user: User) -> bool:
    """检查用户是否可以创建公开数据库"""
    return user.is_superuser


# ==========================================
# 请求模型
# ==========================================

class ShareRequest(BaseModel):
    """共享请求"""
    user_ids: List[int] = Field(description="要共享给的用户 ID 列表")


class IncrementUsageRequest(BaseModel):
    """增加使用次数请求"""
    increment: int = Field(default=1, description="增加的使用次数")


# ==========================================
# API 端点
# ==========================================

@router.get("/", response_model=List[AnalysisDatabasePublic])
async def list_databases(
    db_type: Optional[str] = Query(None, description="按数据库类型筛选"),
    species: Optional[str] = Query(None, description="按物种筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    include_inactive: bool = Query(False, description="是否包含禁用的数据库"),
    sort_by: str = Query("created_at", description="排序字段: created_at/usage_count/name"),
    sort_order: str = Query("desc", description="排序方向: asc/desc"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    获取数据库列表

    返回用户有权访问的所有数据库：
    - 所有公开数据库
    - 用户创建的私有数据库
    - 共享给用户的数据库

    参数：
        db_type: 按数据库类型筛选
        species: 按物种筛选
        search: 搜索 db_id、name、description
        include_inactive: 是否包含禁用的数据库
        sort_by: 排序字段
        sort_order: 排序方向
    """
    # 构建基础查询
    statement = select(AnalysisDatabase)

    # 权限过滤
    conditions = [
        AnalysisDatabase.visibility == "public",
        AnalysisDatabase.owner_id == current_user.id,
    ]
    statement = statement.where(or_(*conditions))

    # 类型筛选
    if db_type:
        statement = statement.where(AnalysisDatabase.db_type == db_type)

    # 物种筛选
    if species:
        statement = statement.where(AnalysisDatabase.species == species)

    # 搜索
    if search:
        search_pattern = f"%{search}%"
        statement = statement.where(
            or_(
                AnalysisDatabase.db_id.ilike(search_pattern),
                AnalysisDatabase.name.ilike(search_pattern),
                AnalysisDatabase.description.ilike(search_pattern)
            )
        )

    # 状态筛选
    if not include_inactive:
        statement = statement.where(AnalysisDatabase.is_active == True)

    # 排序
    sort_column = getattr(AnalysisDatabase, sort_by, AnalysisDatabase.created_at)
    if sort_order == "asc":
        statement = statement.order_by(sort_column.asc())
    else:
        statement = statement.order_by(sort_column.desc())

    databases = session.exec(statement).all()

    # 额外过滤：检查 shared_with 数组
    visible_databases = []
    for db in databases:
        if db.visibility == "public":
            visible_databases.append(db)
        elif db.owner_id == current_user.id:
            visible_databases.append(db)
        elif current_user.id in db.shared_with:
            visible_databases.append(db)
        elif current_user.is_superuser:
            visible_databases.append(db)

    return visible_databases


@router.get("/types/list")
async def list_database_types(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    获取数据库类型列表及计数

    返回所有数据库类型及其数量，用于筛选下拉框
    """
    # 定义所有支持的类型
    all_types = [
        {"type": "annotation", "name": "注释数据库", "description": "GO、KEGG、InterPro 等"},
        {"type": "pathway", "name": "信号通路", "description": "Reactome、WikiPathways 等"},
        {"type": "protein", "name": "蛋白质数据库", "description": "UniProt、PDB 等"},
        {"type": "variant", "name": "变异数据库", "description": "dbSNP、ClinVar 等"},
        {"type": "regulation", "name": "调控数据库", "description": "ENCODE、TFbind 等"},
        {"type": "metabolism", "name": "代谢数据库", "description": "KEGG Compound、HMDB 等"},
        {"type": "custom", "name": "自定义数据库", "description": "用户上传的自定义数据库"},
    ]

    # 获取类型统计
    statement = select(AnalysisDatabase).where(AnalysisDatabase.is_active == True)
    databases = session.exec(statement).all()

    type_count: Dict[str, int] = {}
    for db in databases:
        type_count[db.db_type] = type_count.get(db.db_type, 0) + 1

    # 合并统计
    result = []
    for type_info in all_types:
        result.append({
            **type_info,
            "count": type_count.get(type_info["type"], 0)
        })

    return {"status": "success", "data": result}


@router.get("/species/list")
async def list_species(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """获取物种列表及计数"""
    statement = select(AnalysisDatabase).where(AnalysisDatabase.is_active == True)
    databases = session.exec(statement).all()

    # 统计物种
    species_count: Dict[str, int] = {}
    for db in databases:
        if db.species:
            species_count[db.species] = species_count.get(db.species, 0) + 1

    result = [
        {"species": species, "count": count}
        for species, count in sorted(species_count.items(), key=lambda x: -x[1])
    ]

    return {"status": "success", "data": result}


@router.get("/{db_id}", response_model=AnalysisDatabasePublic)
async def get_database(
    db_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """获取单个数据库详情"""
    db = session.exec(
        select(AnalysisDatabase).where(AnalysisDatabase.db_id == db_id)
    ).first()

    if not db:
        raise HTTPException(status_code=404, detail=f"数据库 '{db_id}' 不存在")

    if not check_database_access(db, current_user):
        raise HTTPException(status_code=403, detail="无权访问此数据库")

    return db


@router.post("/", response_model=AnalysisDatabasePublic)
async def create_database(
    db_in: AnalysisDatabaseCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    创建新数据库

    权限规则：
    - 管理员可创建公开数据库（visibility=public）
    - 普通用户只能创建私有数据库（visibility=private）
    """
    # 检查 db_id 是否已存在
    existing = session.exec(
        select(AnalysisDatabase).where(AnalysisDatabase.db_id == db_in.db_id)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"数据库标识 '{db_in.db_id}' 已存在")

    # 权限检查：普通用户不能创建公开数据库
    if db_in.visibility == "public" and not can_create_public(current_user):
        raise HTTPException(status_code=403, detail="普通用户只能创建私有数据库")

    # 创建数据库
    db_data = db_in.model_dump()
    db = AnalysisDatabase(
        **db_data,
        owner_id=current_user.id
    )

    session.add(db)
    session.commit()
    session.refresh(db)

    log.info(f"用户 {current_user.email} 创建了数据库 {db.db_id}")

    return db


@router.put("/{db_id}", response_model=AnalysisDatabasePublic)
async def update_database(
    db_id: str,
    db_in: AnalysisDatabaseUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """更新数据库信息"""
    db = session.exec(
        select(AnalysisDatabase).where(AnalysisDatabase.db_id == db_id)
    ).first()

    if not db:
        raise HTTPException(status_code=404, detail=f"数据库 '{db_id}' 不存在")

    # 权限检查：需要所有者权限
    if not check_database_access(db, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权修改此数据库")

    # 更新字段
    update_data = db_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db, key, value)

    db.updated_at = get_utc_now()
    session.add(db)
    session.commit()
    session.refresh(db)

    log.info(f"用户 {current_user.email} 更新了数据库 {db.db_id}")

    return db


@router.delete("/{db_id}")
async def delete_database(
    db_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """删除数据库"""
    db = session.exec(
        select(AnalysisDatabase).where(AnalysisDatabase.db_id == db_id)
    ).first()

    if not db:
        raise HTTPException(status_code=404, detail=f"数据库 '{db_id}' 不存在")

    # 权限检查：需要所有者权限
    if not check_database_access(db, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权删除此数据库")

    session.delete(db)
    session.commit()

    log.info(f"用户 {current_user.email} 删除了数据库 {db_id}")

    return {"status": "success", "message": f"数据库 '{db_id}' 已删除"}


@router.post("/{db_id}/share")
async def share_database(
    db_id: str,
    share_in: ShareRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """共享数据库给其他用户"""
    db = session.exec(
        select(AnalysisDatabase).where(AnalysisDatabase.db_id == db_id)
    ).first()

    if not db:
        raise HTTPException(status_code=404, detail=f"数据库 '{db_id}' 不存在")

    if not check_database_access(db, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权共享此数据库")

    # 验证用户 ID 是否存在
    valid_user_ids = []
    for user_id in share_in.user_ids:
        user = session.get(User, user_id)
        if user:
            valid_user_ids.append(user_id)

    # 更新共享列表
    current_shared = list(set(db.shared_with + valid_user_ids))
    db.shared_with = current_shared
    db.updated_at = get_utc_now()

    session.add(db)
    session.commit()

    log.info(f"用户 {current_user.email} 将数据库 {db_id} 共享给了 {len(valid_user_ids)} 个用户")

    return {
        "status": "success",
        "message": f"已共享给 {len(valid_user_ids)} 个用户",
        "shared_with": current_shared
    }


@router.post("/{db_id}/unshare")
async def unshare_database(
    db_id: str,
    share_in: ShareRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """取消共享数据库"""
    db = session.exec(
        select(AnalysisDatabase).where(AnalysisDatabase.db_id == db_id)
    ).first()

    if not db:
        raise HTTPException(status_code=404, detail=f"数据库 '{db_id}' 不存在")

    if not check_database_access(db, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权取消共享")

    db.shared_with = [uid for uid in db.shared_with if uid not in share_in.user_ids]
    db.updated_at = get_utc_now()

    session.add(db)
    session.commit()

    return {"status": "success", "message": f"已取消共享给 {len(share_in.user_ids)} 个用户"}


@router.post("/{db_id}/toggle-active")
async def toggle_database_active(
    db_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """切换数据库启用/禁用状态"""
    db = session.exec(
        select(AnalysisDatabase).where(AnalysisDatabase.db_id == db_id)
    ).first()

    if not db:
        raise HTTPException(status_code=404, detail=f"数据库 '{db_id}' 不存在")

    if not check_database_access(db, current_user, require_owner=True):
        raise HTTPException(status_code=403, detail="无权修改此数据库")

    db.is_active = not db.is_active
    db.updated_at = get_utc_now()

    session.add(db)
    session.commit()

    status = "已启用" if db.is_active else "已禁用"
    log.info(f"用户 {current_user.email} {status} 数据库 {db_id}")

    return {
        "status": "success",
        "is_active": db.is_active,
        "message": f"数据库 '{db_id}' {status}"
    }


@router.post("/{db_id}/increment-usage")
async def increment_database_usage(
    db_id: str,
    usage_in: IncrementUsageRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    增加数据库使用次数

    当 SKILL 执行时引用数据库，调用此接口更新使用统计
    """
    db = session.exec(
        select(AnalysisDatabase).where(AnalysisDatabase.db_id == db_id)
    ).first()

    if not db:
        raise HTTPException(status_code=404, detail=f"数据库 '{db_id}' 不存在")

    db.usage_count += usage_in.increment
    db.last_used_at = get_utc_now()
    db.updated_at = get_utc_now()

    session.add(db)
    session.commit()

    return {
        "status": "success",
        "usage_count": db.usage_count,
        "last_used_at": db.last_used_at.isoformat() if db.last_used_at else None
    }


@router.get("/{db_id}/validate")
async def validate_database_path(
    db_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """验证数据库路径是否存在"""
    db = session.exec(
        select(AnalysisDatabase).where(AnalysisDatabase.db_id == db_id)
    ).first()

    if not db:
        raise HTTPException(status_code=404, detail=f"数据库 '{db_id}' 不存在")

    if not check_database_access(db, current_user):
        raise HTTPException(status_code=403, detail="无权访问此数据库")

    path = db.path
    exists = os.path.exists(path) if path else False
    is_directory = os.path.isdir(path) if exists else False

    return {
        "status": "success",
        "db_id": db_id,
        "path": path,
        "exists": exists,
        "is_directory": is_directory,
        "file_format": db.file_format
    }