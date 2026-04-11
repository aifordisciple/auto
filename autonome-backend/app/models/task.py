"""
任务记录模型模块

包含任务记录模型
"""

from typing import Optional
from sqlmodel import SQLModel, Field, Index
from datetime import datetime


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 任务记录表 (Task Record)
# ==========================================
class TaskRecord(SQLModel, table=True):
    """
    任务记录表

    存储所有分析任务的执行记录，包括语义化目录名和蓝图级联信息。
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    tool_id: str
    parameters: str
    status: str = Field(index=True)
    result: Optional[str] = None
    project_id: str = Field(foreign_key="project.id", index=True)  # ✨ 外键改为 str
    created_at: datetime = Field(default_factory=get_utc_now)
    completed_at: Optional[datetime] = None

    # ==========================================
    # 语义化目录命名字段 (Semantic Directory Naming)
    # ==========================================
    # 语义化目录名，格式: YYYYMMDD_HHMMSS_SKILL_ALIAS_SHORTID
    # 用于替代纯 UUID 目录名，提供人类可读的结果目录
    semantic_dir_name: Optional[str] = Field(default=None, index=True)

    # ==========================================
    # 蓝图级联任务字段 (Blueprint Cascade)
    # ==========================================
    # 蓝图根任务 ID，用于标识多步骤工作流中的根任务
    # 当 task_mode='complex' 时，此字段指向蓝图的主任务 ID
    blueprint_root_id: Optional[str] = Field(default=None, index=True)

    # 步骤序号，用于蓝图中的步骤排序 (1-based)
    # 单独任务为 None，蓝图步骤为 1, 2, 3...
    step_number: Optional[int] = Field(default=None)

    # 用户提供的任务别名（可选）
    # 用于语义化目录名中的 TASK_ALIAS 组件
    task_alias: Optional[str] = Field(default=None)

    # ==========================================
    # 复合索引定义（性能优化）
    # ==========================================
    __table_args__ = (
        # 任务列表按项目+状态+时间筛选（高频查询）
        Index('ix_task_record_project_status_time', 'project_id', 'status', 'created_at'),
        # 蓝图任务查询（根任务查找）
        Index('ix_task_record_blueprint', 'blueprint_root_id', 'step_number'),
    )