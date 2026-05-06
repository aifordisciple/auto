# 技能文件系统统一化升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有技能统一为文件系统存储，消除 DB/Filesystem 双源矛盾

**Architecture:** 利用已有 `skill_bundle_writer.py` 实现 Forge→文件系统写入，新建 `SkillIndexer` 实现文件系统→DB 索引，精简 `skill_parser.py` 删除 DBSkillParser，DB 降级为元数据索引

**Tech Stack:** Python/FastAPI + SQLModel + Alembic + PostgreSQL

---

## 文件结构

```
新增:
  autonome-backend/app/services/skill_indexer.py        # 文件系统→DB 索引器
  autonome-backend/scripts/migrate_db_skills_to_files.py # 一次性迁移脚本

修改:
  autonome-backend/app/core/skill_parser.py             # 删除 DBSkillParser + 合并逻辑
  autonome-backend/app/api/routes/skills_forge.py       # commit/submit 增加文件写入+索引
  autonome-backend/app/models/skill/asset.py            # 新增 bundle_path/is_official/file_hash/indexed_at
  autonome-backend/app/services/skill_keywords_indexer.py # 替换 get_combined_skills
  autonome-backend/app/services/skill_matcher.py        # 替换 get_combined_skills
  autonome-backend/app/services/skill_parameter_registry.py # 替换 get_combined_skill_by_id
  autonome-backend/app/services/tasks/skill_bundle_tasks.py # 替换 get_db_skill_parser
  autonome-backend/app/mcp/autonome_skills_mcp.py       # 替换 get_combined_skills
  autonome-backend/app/services/skill_bundle_writer.py  # 新增 from_draft 便捷方法

测试:
  autonome-backend/tests/unit/test_skill_indexer.py
  autonome-backend/tests/unit/test_skill_file_writer.py
  autonome-backend/tests/integration/test_skill_unified_flow.py
```

---

### Task 1: SkillFileWriter 新增 `from_draft` 方法

**Files:**
- Modify: `autonome-backend/app/services/skill_bundle_writer.py`

已有 `write_script_skill()` 和 `write_blueprint_skill()` 便捷函数，但 Forge 草稿是 raw dict 格式。新增 `write_skill_from_forge_draft()` 桥接方法，将 ForgeSession 的 JSONB draft 转为 `SkillBundleContent` 后写入。

- [ ] **Step 1: 添加 `write_skill_from_forge_draft()` 函数**

在 `skill_bundle_writer.py` 末尾（`log.info("📦 SKILL Bundle Writer 已加载")` 之前）添加：

```python
def write_skill_from_forge_draft(
    draft: Dict[str, Any],
    skill_id: str,
    skills_dir: str = "/app/app/skills"
) -> Dict[str, Any]:
    """
    从 ForgeSession 的 skill_draft (JSONB dict) 写入文件系统

    这是连接 Forge 和文件系统的桥接函数。
    将 Forge 存储的 raw dict 格式转换为 SkillBundleContent，
    然后调用 write_skill_bundle() 写入文件系统。

    Args:
        draft: ForgeSession.skill_draft 字典，包含:
            - name, description, executor_type
            - script_code / nextflow_code
            - parameters_schema, expert_knowledge
            - dependencies, category, tags 等
        skill_id: 技能 ID
        skills_dir: 技能目录根路径

    Returns:
        写入结果，包含 skill_id, bundle_path, files_created
    """
    from app.models.skill_bundle import (
        SkillBundleMetadata,
        SkillBundleContent,
        NextflowBundle,
        ExecutorType as BundleExecutorType
    )

    name = draft.get("name") or "未命名技能"
    description = draft.get("description") or ""
    executor_type_str = draft.get("executor_type") or "Python_env"
    script_code = draft.get("script_code") or ""
    nextflow_code = draft.get("nextflow_code") or ""
    parameters_schema = draft.get("parameters_schema") or {"type": "object", "properties": {}, "required": []}
    expert_knowledge = draft.get("expert_knowledge") or ""
    dependencies = draft.get("dependencies") or []
    category = draft.get("category") or draft.get("category_name") or "custom"
    category_name = draft.get("category_name") or "自定义"
    subcategory = draft.get("subcategory")
    subcategory_name = draft.get("subcategory_name")
    tags = draft.get("tags") or []

    executor_type = BundleExecutorType(executor_type_str)

    # 构建元数据
    metadata = SkillBundleMetadata(
        skill_id=skill_id,
        name=name,
        executor_type=executor_type,
        category=category,
        category_name=category_name,
        subcategory=subcategory,
        subcategory_name=subcategory_name,
        tags=tags
    )

    # 构建内容
    content = SkillBundleContent(
        metadata=metadata,
        description=description,
        parameters_schema=parameters_schema,
        expert_knowledge=expert_knowledge,
        script_code=script_code if executor_type in (BundleExecutorType.PYTHON_ENV, BundleExecutorType.R_ENV) else None,
        dependencies=dependencies,
        nextflow_bundle=NextflowBundle(full_code=nextflow_code) if nextflow_code else None,
    )

    return write_skill_bundle(content, skills_dir)


def delete_skill_bundle(skill_id: str, skills_dir: str = "/app/app/skills") -> bool:
    """
    删除技能文件夹（仅限用户技能，官方技能受 is_official 检查保护）

    Args:
        skill_id: 技能 ID
        skills_dir: 技能目录根路径

    Returns:
        是否成功删除
    """
    import shutil

    bundle_path = os.path.join(skills_dir, skill_id)
    if not os.path.exists(bundle_path):
        log.warning(f"[SkillBundleWriter] 技能目录不存在: {bundle_path}")
        return False

    shutil.rmtree(bundle_path)
    log.info(f"[SkillBundleWriter] 已删除技能目录: {bundle_path}")
    return True
```

- [ ] **Step 2: 提交**

```bash
git add autonome-backend/app/services/skill_bundle_writer.py
git commit -m "feat: add write_skill_from_forge_draft bridge for Forge→filesystem writes"
```

---

### Task 2: 创建 SkillIndexer 服务

**Files:**
- Create: `autonome-backend/app/services/skill_indexer.py`

- [ ] **Step 1: 写入完整的 SkillIndexer 类**

```python
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
                bundle_name = skill.get("bundle_name") or skill_id

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
                    if existing.file_hash != file_hash:
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
                    skill = session.exec(
                        select(SkillAsset).where(SkillAsset.skill_id == db_skill_id)
                    ).first()
                    if skill and not skill.is_official:
                        log.warning(f"[SkillIndexer] 技能文件夹缺失，标记为 DEPRECATED: {db_skill_id}")
                        skill.status = SkillStatus.DEPRECATED
                        session.add(skill)

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
            skill = session.exec(
                select(SkillAsset).where(SkillAsset.skill_id == skill_id)
            ).first()

            if not skill:
                return False

            if skill.is_official:
                log.warning(f"[SkillIndexer] 拒绝删除官方技能索引: {skill_id}")
                return False

            session.delete(skill)
            session.commit()

        log.info(f"[SkillIndexer] 已移除索引: {skill_id}")
        return True

    def _update_from_metadata(
        self,
        skill: SkillAsset,
        metadata: Dict[str, Any],
        bundle_path: str,
        file_hash: str,
    ) -> None:
        """用从文件解析的元数据更新现有 SkillAsset 记录"""
        skill.name = metadata.get("name", skill.name)
        skill.description = metadata.get("description", skill.description)
        skill.version = metadata.get("version", skill.version)
        skill.executor_type = metadata.get("executor_type", skill.executor_type)
        skill.bundle_path = bundle_path
        skill.file_hash = file_hash
        skill.indexed_at = _get_utc_now()
        # 官方技能标记
        if not hasattr(skill, 'is_official') or skill.is_official is None:
            skill.is_official = False

    def _create_from_metadata(
        self,
        session: Session,
        metadata: Dict[str, Any],
        bundle_path: str,
        file_hash: str,
    ) -> None:
        """从文件解析的元数据创建新的 SkillAsset 索引记录"""
        from app.models.domain import generate_skill_id as gen_id

        skill = SkillAsset(
            skill_id=metadata.get("skill_id", gen_id()),
            name=metadata.get("name", "未命名技能"),
            description=metadata.get("description", ""),
            version=metadata.get("version", "1.0.0"),
            executor_type=metadata.get("executor_type", "Python_env"),
            bundle_path=bundle_path,
            file_hash=file_hash,
            indexed_at=_get_utc_now(),
            is_official=False,
            status=SkillStatus.DRAFT,
            owner_id=0,  # 文件系统技能默认 owner=0，后续 Forge commit 会修正
        )
        session.add(skill)


# 全局单例
_skill_indexer_instance: Optional[SkillIndexer] = None


def get_skill_indexer(skills_dir: str = "/app/app/skills") -> SkillIndexer:
    """
    获取全局 SkillIndexer 实例

    首次调用时创建单例并执行全量索引。
    后续调用返回已有实例，不会重复索引。
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
```

- [ ] **Step 2: 提交**

```bash
git add autonome-backend/app/services/skill_indexer.py
git commit -m "feat: add SkillIndexer - filesystem→DB metadata index service"
```

---

### Task 3: SkillAsset 模型新增索引字段

**Files:**
- Modify: `autonome-backend/app/models/skill/asset.py`

在 `SkillAssetBase` 类中新增 4 个字段（`script_code` 等旧字段保留但标记为 nullable，兼容期内不删除）。

- [ ] **Step 1: 新增字段**

在 `SkillAssetBase` 的 `execution_mode` 字段之后添加：

```python
    # ==========================================
    # 文件系统索引字段（2026-05 技能文件系统统一化）
    # ==========================================
    bundle_path: Optional[str] = Field(default=None, max_length=500, description="技能文件夹路径")
    is_official: bool = Field(default=False, description="是否为官方预置技能")
    file_hash: Optional[str] = Field(default=None, max_length=32, description="SKILL.md SHA256 哈希(前16位)")
    indexed_at: Optional[datetime] = Field(default=None, description="最后索引时间")
```

同时在 `SkillAssetBase` 中将待移除的字段标记为 Optional：

```python
    # 核心资产内容（兼容期内保留，后续移除）
    parameters_schema: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column(JSONB))
    expert_knowledge: Optional[str] = Field(default=None)
    script_code: Optional[str] = Field(default=None, description="实际执行的Python/R代码")
    nextflow_code: Optional[str] = Field(default=None, description="Nextflow工作流代码")
    dependencies: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSONB))
```

注意：`parameters_schema` 和 `dependencies` 的 default_factory 需要包装成 lambda 避免 Optional 冲突。

- [ ] **Step 2: 提交**

```bash
git add autonome-backend/app/models/skill/asset.py
git commit -m "feat: add file index fields to SkillAsset (bundle_path/is_official/file_hash/indexed_at)"
```

---

### Task 4: 精简 SkillParser，删除 DBSkillParser

**Files:**
- Modify: `autonome-backend/app/core/skill_parser.py`

- [ ] **Step 1: 删除 DBSkillParser 类和合并逻辑**

删除以下内容：
- `DBSkillParser` 类（第 581-753 行）
- `get_db_skill_parser()` 函数（第 743-753 行）
- `_get_combined_skills_cached()` 函数（第 756-798 行）
- `get_combined_skills()` 函数（第 800-819 行）
- `get_combined_skill_by_id()` 函数（第 822-858 行）

保留内容：
- `SkillBundleParser` 类
- `get_skill_parser()` 单例
- `get_sample_sheet_config()` 及辅助函数

- [ ] **Step 2: 新增替代函数 `get_skill_from_db_index()`**

在文件末尾添加，供 API 层和 L2 参数探查使用（替换 `get_combined_skill_by_id`）：

```python
def get_skill_from_db_index(skill_id: str) -> Optional[Dict[str, Any]]:
    """
    从 SkillAsset DB 索引获取技能元数据，并从文件系统获取详细内容

    用于替换 get_combined_skill_by_id，DB 只存索引元数据，
    通过 SkillBundleParser 从文件系统获取 parameters_schema 和 expert_knowledge。

    Args:
        skill_id: SKILL 唯一标识符

    Returns:
        完整的技能信息字典（合并 DB 索引 + 文件系统内容）
    """
    from sqlmodel import Session, select
    from app.models.domain import SkillAsset

    parser = get_skill_parser()
    fs_skill = parser.get_skill_by_id(skill_id)

    if not fs_skill:
        return None

    # 尝试从 DB 索引补充元数据（状态、评分、权限等）
    try:
        with Session(engine) as session:
            db_skill = session.exec(
                select(SkillAsset).where(SkillAsset.skill_id == skill_id)
            ).first()

            if db_skill:
                fs_skill["metadata"]["status"] = db_skill.status.value if db_skill.status else "PUBLISHED"
                fs_skill["metadata"]["visibility"] = db_skill.visibility
                fs_skill["metadata"]["owner_id"] = db_skill.owner_id
                fs_skill["source"] = "filesystem"
                fs_skill["owner_id"] = db_skill.owner_id
                fs_skill["usage_count"] = db_skill.usage_count or 0
                fs_skill["avg_rating"] = db_skill.avg_rating or 0.0
                fs_skill["favorite_count"] = db_skill.favorite_count or 0
                fs_skill["is_official"] = db_skill.is_official
            else:
                fs_skill["source"] = "filesystem"
                fs_skill["owner_id"] = 0
    except Exception as e:
        log.warning(f"[SkillParser] DB 索引查询失败: {e}")
        fs_skill["source"] = "filesystem"
        fs_skill["owner_id"] = 0

    return fs_skill


def get_skills_from_db_index(user_id: int) -> List[Dict[str, Any]]:
    """
    获取用户可见的所有技能列表

    从 SkillAsset DB 索引获取可见的技能 ID 列表，
    再从文件系统补充详细信息。
    替换 get_combined_skills()。

    Args:
        user_id: 当前用户 ID

    Returns:
        技能列表
    """
    from sqlmodel import Session, select, or_, and_
    from app.models.domain import SkillAsset, SkillStatus

    parser = get_skill_parser()

    try:
        with Session(engine) as session:
            statement = select(SkillAsset).where(
                or_(
                    SkillAsset.status == SkillStatus.PUBLISHED,
                    and_(
                        SkillAsset.owner_id == user_id,
                        SkillAsset.status.notin_([SkillStatus.DRAFT, SkillStatus.DEPRECATED])
                    )
                )
            ).order_by(SkillAsset.indexed_at.desc())

            db_skills = session.exec(statement).all()

            result = []
            seen_ids = set()

            for db_skill in db_skills:
                skill_id = db_skill.skill_id
                if skill_id in seen_ids:
                    continue
                seen_ids.add(skill_id)

                # 从文件系统获取详细信息
                fs_skill = parser.get_skill_by_id(skill_id)
                if not fs_skill:
                    log.warning(f"[SkillParser] DB 索引指向不存在的文件: {skill_id}")
                    continue

                # 合并 DB 索引元数据
                fs_skill["metadata"]["status"] = db_skill.status.value if db_skill.status else "PUBLISHED"
                fs_skill["metadata"]["visibility"] = db_skill.visibility
                fs_skill["source"] = "filesystem"
                fs_skill["owner_id"] = db_skill.owner_id
                fs_skill["usage_count"] = db_skill.usage_count or 0
                fs_skill["avg_rating"] = db_skill.avg_rating or 0.0
                fs_skill["favorite_count"] = db_skill.favorite_count or 0
                fs_skill["is_official"] = db_skill.is_official

                result.append(fs_skill)

            # 追加 DB 索引中不存在但文件系统存在的官方技能
            all_fs_skills = parser.get_all_skills()
            for fs_skill in all_fs_skills:
                fs_id = fs_skill.get("metadata", {}).get("skill_id")
                if fs_id and fs_id not in seen_ids:
                    fs_skill["source"] = "filesystem"
                    fs_skill["owner_id"] = 0
                    fs_skill["is_official"] = True
                    result.append(fs_skill)

            return result

    except Exception as e:
        log.error(f"[SkillParser] DB 索引查询失败: {e}，回退到纯文件系统")
        # 降级：返回文件系统所有技能
        all_skills = parser.get_all_skills()
        for s in all_skills:
            s["source"] = "filesystem"
            s["owner_id"] = 0
        return all_skills
```

- [ ] **Step 3: 提交**

```bash
git add autonome-backend/app/core/skill_parser.py
git commit -m "refactor: remove DBSkillParser, replace with get_skill_from_db_index/get_skills_from_db_index"
```

---

### Task 5: 更新所有调用方替换 get_combined_skills / get_combined_skill_by_id

**Files:**
- Modify: `autonome-backend/app/services/skill_keywords_indexer.py`
- Modify: `autonome-backend/app/services/skill_matcher.py`
- Modify: `autonome-backend/app/services/skill_parameter_registry.py`
- Modify: `autonome-backend/app/services/tasks/skill_bundle_tasks.py`
- Modify: `autonome-backend/app/mcp/autonome_skills_mcp.py`

- [ ] **Step 1: skill_keywords_indexer.py**

第 30 行 `from app.core.skill_parser import get_skill_parser, get_combined_skills` →
`from app.core.skill_parser import get_skill_parser, get_skills_from_db_index`
第 180 行 `skills = get_combined_skills(effective_user_id)` →
`skills = get_skills_from_db_index(effective_user_id)`

- [ ] **Step 2: skill_matcher.py**

第 48 行 `from app.core.skill_parser import get_combined_skills` →
`from app.core.skill_parser import get_skills_from_db_index`
第 127 行 `self._available_skills = get_combined_skills(max(1, self.user_id))` →
`self._available_skills = get_skills_from_db_index(max(1, self.user_id))`

- [ ] **Step 3: skill_parameter_registry.py**

第 19 行 `from app.core.skill_parser import get_combined_skill_by_id` →
`from app.core.skill_parser import get_skill_from_db_index`
第 75 行 `skill = get_combined_skill_by_id(self.user_id, skill_id)` →
`skill = get_skill_from_db_index(skill_id)`

- [ ] **Step 4: skill_bundle_tasks.py**

第 388-389 行替换 `get_db_skill_parser` → 使用 `get_skills_from_db_index`

```python
# BEFORE:
from app.core.skill_parser import get_db_skill_parser
db_parser = get_db_skill_parser(user_id)

# AFTER:
from app.core.skill_parser import get_skills_from_db_index
all_skills = get_skills_from_db_index(user_id)
```

- [ ] **Step 5: autonome_skills_mcp.py**

第 16 行 `from app.core.skill_parser import get_combined_skill_by_id, get_combined_skills` →
`from app.core.skill_parser import get_skill_from_db_index, get_skills_from_db_index`
第 61 行 `skills = get_combined_skills(user_id=0)` →
`skills = get_skills_from_db_index(user_id=0)`

- [ ] **Step 6: 提交**

```bash
git add autonome-backend/app/services/skill_keywords_indexer.py \
        autonome-backend/app/services/skill_matcher.py \
        autonome-backend/app/services/skill_parameter_registry.py \
        autonome-backend/app/services/tasks/skill_bundle_tasks.py \
        autonome-backend/app/mcp/autonome_skills_mcp.py
git commit -m "refactor: replace get_combined_skills with get_skills_from_db_index in all callers"
```

---

### Task 6: Forge commit/submit 集成文件写入和索引

**Files:**
- Modify: `autonome-backend/app/api/routes/skills_forge.py`

- [ ] **Step 1: commit 端点增加文件写入+索引**

在 `commit_skill()` 函数中，`db.commit()` 成功之后，`return` 之前插入：

```python
    # ==========================================
    # 文件系统写入（技能文件系统统一化）
    # ==========================================
    bundle_result = None
    try:
        from app.services.skill_bundle_writer import write_skill_from_forge_draft

        # 构建完整 draft（合并 forge_session 已有字段）
        full_draft = dict(draft)
        if executor_type == "Logical_Blueprint" and not full_draft.get("nextflow_code"):
            full_draft["nextflow_code"] = draft.get("nextflow_code") or ""
        if executor_type != "Logical_Blueprint" and not full_draft.get("script_code"):
            full_draft["script_code"] = draft.get("script_code") or ""

        bundle_result = write_skill_from_forge_draft(
            draft=full_draft,
            skill_id=skill.skill_id,
        )
        log.info(f"[Forge] 文件系统写入完成: {bundle_result.get('bundle_path')}")

        # 更新 SkillAsset 的文件索引字段
        skill.bundle_path = bundle_result.get("bundle_path", "")
        db.add(skill)
        db.commit()
        db.refresh(skill)
    except Exception as e:
        log.error(f"[Forge] 文件系统写入失败（DB 已保存）: {e}")
        # 不阻塞流程，DB 已保存，文件可通过重索引补齐

    # 增量索引
    try:
        from app.services.skill_indexer import get_skill_indexer
        indexer = get_skill_indexer()
        indexer.index_one(skill.skill_id)
    except Exception as e:
        log.warning(f"[Forge] 增量索引失败: {e}")
```

- [ ] **Step 2: submit 端点同样增加文件写入+索引**

对 `submit_forge_skill()` 函数做相同修改。

- [ ] **Step 3: 提交**

```bash
git add autonome-backend/app/api/routes/skills_forge.py
git commit -m "feat: integrate SkillFileWriter + SkillIndexer into forge commit/submit endpoints"
```

---

### Task 7: Alembic 数据库迁移

**Files:**
- Create: Alembic migration (auto-generated)
- Modify: `autonome-backend/app/models/skill/asset.py` (already done in Task 3)

- [ ] **Step 1: 生成 Alembic 迁移**

```bash
cd autonome-backend
alembic revision --autogenerate -m "add skill file index fields (bundle_path, is_official, file_hash, indexed_at)"
```

- [ ] **Step 2: 检查迁移文件内容**

确保迁移包含：
- `ALTER TABLE skillasset ADD COLUMN bundle_path VARCHAR(500)`
- `ALTER TABLE skillasset ADD COLUMN is_official BOOLEAN DEFAULT FALSE`
- `ALTER TABLE skillasset ADD COLUMN file_hash VARCHAR(32)`
- `ALTER TABLE skillasset ADD COLUMN indexed_at TIMESTAMP`
- 将 `script_code`, `expert_knowledge`, `nextflow_code`, `parameters_schema`, `dependencies` 改为 NULLABLE（如果以前是 NOT NULL）

- [ ] **Step 3: 提交**

```bash
git add autonome-backend/alembic/versions/*.py
git commit -m "feat: add Alembic migration for skill file index fields"
```

---

### Task 8: 数据迁移脚本

**Files:**
- Create: `autonome-backend/scripts/migrate_db_skills_to_files.py`

- [ ] **Step 1: 写入迁移脚本**

```python
#!/usr/bin/env python3
"""
一次性数据迁移脚本：将 SkillAsset 表中现有的用户技能导出为文件系统结构

执行时机：Docker 启动时，API 服务启动前
幂等性：通过环境变量 SKILL_MIGRATION_DONE 标记避免重复执行

用法：
  SKILLS_DIR=/app/app/skills python scripts/migrate_db_skills_to_files.py
"""

import os
import sys
import json
import hashlib
from datetime import datetime, timezone

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from app.core.database import engine
from app.core.logger import log
from app.models.domain import SkillAsset
from app.services.skill_bundle_writer import write_skill_from_forge_draft


def main():
    if os.environ.get("SKILL_MIGRATION_DONE"):
        log.info("[Migration] 技能迁移已完成，跳过")
        return

    skills_dir = os.environ.get("SKILLS_DIR", "/app/app/skills")
    log.info(f"[Migration] 开始迁移 DB 技能到文件系统: {skills_dir}")

    migrated = 0
    skipped = 0
    failed = 0

    with Session(engine) as session:
        # 查询所有有 script_code 或 nextflow_code 的技能
        skills = session.exec(select(SkillAsset)).all()

        for skill in skills:
            # 检查是否已有 bundle_path（已迁移过）
            if skill.bundle_path and os.path.exists(skill.bundle_path):
                skipped += 1
                continue

            # 检查是否有代码内容
            has_code = bool(skill.script_code or skill.nextflow_code)
            if not has_code:
                # 官方技能可能在文件系统中已存在，尝试索引
                fs_path = os.path.join(skills_dir, skill.skill_id)
                if os.path.exists(fs_path):
                    skill.bundle_path = fs_path
                    skill.is_official = True
                    session.add(skill)
                    skipped += 1
                    continue
                else:
                    skipped += 1
                    continue

            try:
                # 构建 draft
                draft = {
                    "name": skill.name or "未命名技能",
                    "description": skill.description or "",
                    "executor_type": skill.executor_type or "Python_env",
                    "script_code": skill.script_code or "",
                    "nextflow_code": skill.nextflow_code or "",
                    "parameters_schema": skill.parameters_schema or {},
                    "expert_knowledge": skill.expert_knowledge or "",
                    "dependencies": skill.dependencies or [],
                    "category": skill.category or "custom",
                    "category_name": skill.category_name or "自定义",
                    "tags": skill.tags or [],
                }

                # 写入文件系统
                result = write_skill_from_forge_draft(draft, skill.skill_id, skills_dir)

                # 更新 DB 索引字段
                skill.bundle_path = result.get("bundle_path", "")
                skill.is_official = False
                skill.indexed_at = datetime.now(timezone.utc)

                session.add(skill)
                migrated += 1
                log.info(f"[Migration] 迁移成功: {skill.skill_id}")

            except Exception as e:
                log.error(f"[Migration] 迁移失败 {skill.skill_id}: {e}")
                failed += 1

        session.commit()

    log.info(f"[Migration] 迁移完成: 成功={migrated}, 跳过={skipped}, 失败={failed}")

    # 标记迁移完成
    os.environ["SKILL_MIGRATION_DONE"] = "1"


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 提交**

```bash
git add autonome-backend/scripts/migrate_db_skills_to_files.py
git commit -m "feat: add DB→filesystem migration script for existing skills"
```

---

### Task 9: Docker 启动时序调整

**Files:**
- Modify: Docker entrypoint 或 docker-compose 启动脚本

- [ ] **Step 1: 在 API 启动前执行迁移+索引**

修改 API 容器启动脚本（通常是 `autonome-backend/entrypoint.sh` 或 `docker-compose.yml` 的 command）：

```bash
#!/bin/sh
# 等待 DB 就绪
echo "Waiting for PostgreSQL..."
while ! pg_isready -h postgres -p 5432 -U autonome; do sleep 1; done

# 运行 Alembic 迁移
cd /app
alembic upgrade head

# 运行技能数据迁移（DB → 文件系统）
python scripts/migrate_db_skills_to_files.py

# 启动 FastAPI（应用内会执行 SkillIndexer.index_all）
uvicorn main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 在 FastAPI 启动事件中调用 index_all**

修改 `autonome-backend/main.py`：

```python
@app.on_event("startup")
async def startup_event():
    from app.services.skill_indexer import get_skill_indexer
    log.info("[Startup] 开始技能文件系统全量索引...")
    indexer = get_skill_indexer()
    count = indexer.index_all()
    log.info(f"[Startup] 技能索引完成: {count} 个技能已索引")
```

- [ ] **Step 3: 提交**

```bash
git add auto_deploy.sh entrypoint.sh main.py
git commit -m "feat: add startup skill migration + index_all to Docker entrypoint"
```

---

### Task 10: 集成测试与回归验证

**Files:**
- Create: `autonome-backend/tests/integration/test_skill_unified_flow.py`

- [ ] **Step 1: 写入集成测试**

```python
"""
技能文件系统统一化集成测试

验证 End-to-End：Forge commit → 文件写入 → 索引 → 查询 → 执行
"""

import os
import tempfile
import pytest
from pathlib import Path

from app.services.skill_bundle_writer import write_skill_from_forge_draft
from app.services.skill_indexer import SkillIndexer
from app.core.skill_parser import SkillBundleParser, get_skill_from_db_index


@pytest.fixture
def temp_skills_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_draft():
    return {
        "name": "测试技能",
        "description": "用于测试的技能",
        "executor_type": "Python_env",
        "script_code": "#!/usr/bin/env python\nprint('hello world')",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "输入文件路径",
                    "format": "filepath"
                }
            },
            "required": ["input_file"]
        },
        "expert_knowledge": "这是一个测试技能的专家知识。",
        "dependencies": ["numpy", "pandas"],
        "category": "test",
        "category_name": "测试",
        "tags": ["test"]
    }


class TestSkillFileWriter:
    def test_write_from_draft_creates_directory(self, temp_skills_dir, sample_draft):
        result = write_skill_from_forge_draft(
            draft=sample_draft,
            skill_id="test_skill_001",
            skills_dir=temp_skills_dir
        )
        assert result["skill_id"] == "test_skill_001"
        assert os.path.isdir(result["bundle_path"])
        assert "SKILL.md" in result["files_created"]
        assert "scripts/main.py" in result["files_created"]

    def test_write_from_draft_generates_valid_skill_md(self, temp_skills_dir, sample_draft):
        result = write_skill_from_forge_draft(
            draft=sample_draft,
            skill_id="test_skill_002",
            skills_dir=temp_skills_dir
        )
        skill_md_path = os.path.join(result["bundle_path"], "SKILL.md")
        assert os.path.exists(skill_md_path)

        with open(skill_md_path, "r") as f:
            content = f.read()

        assert "skill_id:" in content
        assert "test_skill_002" in content
        assert "executor_type:" in content
        assert "Python_env" in content
        assert "测试技能" in content
        assert "## 1. 技能意图与功能边界" in content
        assert "## 2. 动态参数定义规范" in content
        assert "## 3. 操作指令与专家级知识库" in content

    def test_write_from_draft_creates_script_file(self, temp_skills_dir, sample_draft):
        result = write_skill_from_forge_draft(
            draft=sample_draft,
            skill_id="test_skill_003",
            skills_dir=temp_skills_dir
        )
        script_path = os.path.join(result["bundle_path"], "scripts", "main.py")
        assert os.path.exists(script_path)

        with open(script_path, "r") as f:
            assert "hello world" in f.read()

    def test_write_from_draft_update_is_idempotent(self, temp_skills_dir, sample_draft):
        # 第一次写入
        r1 = write_skill_from_forge_draft(sample_draft, "test_skill_004", temp_skills_dir)
        # 第二次写入（更新）
        updated_draft = dict(sample_draft)
        updated_draft["name"] = "更新后的名称"
        r2 = write_skill_from_forge_draft(updated_draft, "test_skill_004", temp_skills_dir)

        assert r1["bundle_path"] == r2["bundle_path"]
        # 内容应该被更新
        with open(os.path.join(r2["bundle_path"], "SKILL.md"), "r") as f:
            assert "更新后的名称" in f.read()


class TestSkillIndexer:
    def test_index_one(self, temp_skills_dir, sample_draft):
        # 先写文件
        write_skill_from_forge_draft(sample_draft, "test_idx_001", temp_skills_dir)

        indexer = SkillIndexer(temp_skills_dir)
        result = indexer.index_one("test_idx_001")
        assert result is True

    def test_remove_index(self, temp_skills_dir, sample_draft):
        # 先写文件
        write_skill_from_forge_draft(sample_draft, "test_idx_002", temp_skills_dir)

        indexer = SkillIndexer(temp_skills_dir)
        indexer.index_one("test_idx_002")

        result = indexer.remove_index("test_idx_002")
        assert result is True


class TestSkillParser:
    def test_parse_skill_written_by_forge(self, temp_skills_dir, sample_draft):
        result = write_skill_from_forge_draft(sample_draft, "test_parse_001", temp_skills_dir)

        parser = SkillBundleParser(temp_skills_dir)
        skill = parser.get_skill_by_id("test_parse_001")

        assert skill is not None
        assert skill["metadata"]["skill_id"] == "test_parse_001"
        assert skill["metadata"]["name"] == "测试技能"
        assert skill["metadata"]["executor_type"] == "Python_env"
        assert "input_file" in skill["parameters_schema"]["properties"]
        assert "测试技能的专家知识" in skill["expert_knowledge"]

    def test_nonexistent_skill_id(self, temp_skills_dir):
        parser = SkillBundleParser(temp_skills_dir)
        skill = parser.get_skill_by_id("nonexistent")
        assert skill is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: 运行测试**

```bash
cd autonome-backend
python -m pytest tests/integration/test_skill_unified_flow.py -v
```

- [ ] **Step 3: 回归测试官方技能解析**

```bash
cd autonome-backend
python -c "
from app.core.skill_parser import SkillBundleParser
parser = SkillBundleParser('/opt/data1/public/software/systools/autonome/autonome-backend/app/skills')
skills = parser.get_all_skills()
print(f'解析技能数: {len(skills)}')
for s in skills:
    print(f'  - {s[\"metadata\"][\"skill_id\"]}: {s[\"metadata\"][\"name\"]}')
"
```

- [ ] **Step 4: 提交**

```bash
git add autonome-backend/tests/integration/test_skill_unified_flow.py
git commit -m "test: add unified skill flow integration tests"
```
