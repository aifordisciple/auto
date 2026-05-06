"""
SkillIndexer - 技能索引器

从文件系统扫描技能文件夹，解析 SKILL.md，同步到 SkillAsset 数据库表。
维护 DB 作为文件系统的元数据索引。

职责：
- 启动时全量索引：index_all()
- 变更时增量索引：index_one()
- 删除时移除索引：remove_index()
- 文件变更检测：通过 file_hash 对比
"""

import os
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.logger import log
from app.core.database import engine
from app.core.skill_parser import SkillBundleParser
from app.models.domain import SkillAsset, SkillStatus


def _compute_file_hash(content: str) -> str:
    """计算内容 SHA256 哈希"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SkillIndexer:
    """
    技能索引器

    从文件系统的技能文件夹扫描并解析 SKILL.md，
    将元数据同步到 SkillAsset 数据库表。
    """

    def __init__(self, skills_dir: str = "/app/app/skills"):
        self.skills_dir = skills_dir
        self.parser = SkillBundleParser(skills_dir)
        log.info(f"[SkillIndexer] 初始化索引器，目录: {skills_dir}")

    def index_all(self) -> int:
        """
        全量索引所有技能文件夹

        流程：
        1. 扫描 skills_dir 下所有包含 SKILL.md 的文件夹
        2. 解析每个 SKILL.md 获取元数据
        3. 计算 file_hash
        4. 对比 DB 中现有记录的 hash，有变化才 upsert
        5. 标记 DB 中对应文件已不存在的记录

        Returns:
            索引的技能数量
        """
        skills = self.parser.get_all_skills()
        indexed_count = 0
        indexed_ids = set()

        with Session(engine) as session:
            for skill in skills:
                metadata = skill.get("metadata", {})
                skill_id = metadata.get("skill_id")
                if not skill_id:
                    continue

                indexed_ids.add(skill_id)
                bundle_path = skill.get("bundle_path") or ""

                # 计算 SKILL.md 的 hash
                skill_md_path = os.path.join(bundle_path, "SKILL.md")
                file_hash = ""
                if os.path.exists(skill_md_path):
                    with open(skill_md_path, "r", encoding="utf-8") as f:
                        file_hash = _compute_file_hash(f.read())

                # 查询现有记录
                existing = session.exec(
                    select(SkillAsset).where(SkillAsset.skill_id == skill_id)
                ).first()

                if existing:
                    # 仅当 hash 变化时才更新
                    if not existing.file_hash or existing.file_hash != file_hash:
                        self._update_from_metadata(existing, metadata, bundle_path, file_hash)
                        indexed_count += 1
                else:
                    # 新建索引记录
                    self._create_from_metadata(session, metadata, bundle_path, file_hash)
                    indexed_count += 1

            # 标记 DB 中文件已不存在的技能
            all_db_ids = session.exec(select(SkillAsset.skill_id)).all()
            for db_skill_id in all_db_ids:
                if db_skill_id not in indexed_ids:
                    skill_rec = session.exec(
                        select(SkillAsset).where(SkillAsset.skill_id == db_skill_id)
                    ).first()
                    if skill_rec and not skill_rec.is_official:
                        log.warning(f"[SkillIndexer] 技能文件夹缺失，标记为 DEPRECATED: {db_skill_id}")
                        skill_rec.status = SkillStatus.DEPRECATED
                        session.add(skill_rec)

            session.commit()

        log.info(f"[SkillIndexer] 全量索引完成: {indexed_count} 个技能已更新")
        return indexed_count

    def index_one(self, skill_id: str) -> bool:
        """
        增量索引单个技能（Forge commit 后调用）

        Args:
            skill_id: 技能 ID

        Returns:
            是否索引成功
        """
        skill = self.parser.get_skill_by_id(skill_id)
        if not skill:
            log.warning(f"[SkillIndexer] 未找到技能: {skill_id}")
            return False

        metadata = skill.get("metadata", {})
        bundle_path = skill.get("bundle_path") or ""

        # 计算 file_hash
        skill_md_path = os.path.join(bundle_path, "SKILL.md")
        file_hash = ""
        if os.path.exists(skill_md_path):
            with open(skill_md_path, "r", encoding="utf-8") as f:
                file_hash = _compute_file_hash(f.read())

        with Session(engine) as session:
            existing = session.exec(
                select(SkillAsset).where(SkillAsset.skill_id == skill_id)
            ).first()

            if existing:
                self._update_from_metadata(existing, metadata, bundle_path, file_hash)
            else:
                self._create_from_metadata(session, metadata, bundle_path, file_hash)

            session.commit()

        log.info(f"[SkillIndexer] 增量索引完成: {skill_id}")
        return True

    def remove_index(self, skill_id: str) -> bool:
        """
        从 DB 索引中移除技能

        Args:
            skill_id: 技能 ID

        Returns:
            是否移除成功
        """
        with Session(engine) as session:
            skill_rec = session.exec(
                select(SkillAsset).where(SkillAsset.skill_id == skill_id)
            ).first()

            if not skill_rec:
                return False

            if skill_rec.is_official:
                log.warning(f"[SkillIndexer] 拒绝删除官方技能索引: {skill_id}")
                return False

            session.delete(skill_rec)
            session.commit()

        log.info(f"[SkillIndexer] 已移除索引: {skill_id}")
        return True

    def _update_from_metadata(
        self,
        skill_rec: SkillAsset,
        metadata: Dict[str, Any],
        bundle_path: str,
        file_hash: str,
    ) -> None:
        """用从文件解析的元数据更新现有 SkillAsset 记录"""
        skill_rec.name = metadata.get("name") or skill_rec.name
        skill_rec.description = metadata.get("description") or skill_rec.description
        skill_rec.version = metadata.get("version") or skill_rec.version
        skill_rec.executor_type = metadata.get("executor_type") or skill_rec.executor_type
        skill_rec.bundle_path = bundle_path
        skill_rec.file_hash = file_hash
        skill_rec.indexed_at = _get_utc_now()
        # 保留已有的 owner_id 不覆盖

    def _create_from_metadata(
        self,
        session: Session,
        metadata: Dict[str, Any],
        bundle_path: str,
        file_hash: str,
    ) -> None:
        """从文件解析的元数据创建新的 SkillAsset 索引记录"""
        skill_rec = SkillAsset(
            skill_id=metadata.get("skill_id", ""),
            name=metadata.get("name") or "未命名技能",
            description=metadata.get("description") or "",
            version=metadata.get("version") or "1.0.0",
            executor_type=metadata.get("executor_type") or "Python_env",
            bundle_path=bundle_path,
            file_hash=file_hash,
            indexed_at=_get_utc_now(),
            is_official=False,
            status=SkillStatus.PUBLISHED,
            owner_id=0,  # 文件系统技能默认 owner=0
        )
        session.add(skill_rec)


# 全局单例
_skill_indexer_instance: Optional[SkillIndexer] = None


def get_skill_indexer(skills_dir: str = "/app/app/skills") -> SkillIndexer:
    """
    获取全局 SkillIndexer 实例

    首次调用时创建单例。
    后续调用返回已有实例，不会重复执行 index_all。
    """
    global _skill_indexer_instance
    if _skill_indexer_instance is None:
        _skill_indexer_instance = SkillIndexer(skills_dir)
    return _skill_indexer_instance


def reindex_all(skills_dir: str = "/app/app/skills") -> int:
    """
    强制执行一次全量重索引

    可用于手动触发或 API 端点调用。
    """
    indexer = SkillIndexer(skills_dir)
    return indexer.index_all()
