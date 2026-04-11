# System Learning Layer 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建系统级隐身学习层，从所有用户对话中自动提取方法论和策略，持续优化 Agent 能力。

**Architecture:** 独立 SkillBank 层，定时批量处理（Celery Beat），完全隐身注入到 Agent 上下文，不侵入现有技能中心。

**Tech Stack:** Python, SQLModel, pgvector, Celery, LangChain, OpenAI Embeddings

---

## 文件结构

```
autonome-backend/
├── app/
│   ├── models/
│   │   └── system_skill.py          # 新增: SystemSkill 数据模型
│   ├── services/
│   │   └── system_learning/
│   │       ├── __init__.py          # 新增: 模块入口
│   │       ├── method_extractor.py  # 新增: 方法提取器
│   │       ├── skill_maintainer.py  # 新增: 技能维护器
│   │       ├── skill_injector.py    # 新增: 技能注入器
│   │       ├── session_pool.py      # 新增: 会话池管理
│   │       ├── vector_index.py      # 新增: 向量索引
│   │       ├── privacy_validator.py # 新增: 隐私验证
│   │       └── batch_scheduler.py   # 新增: 定时任务调度
│   ├── api/routes/
│   │   └── system_learning.py       # 新增: 管理API
│   ├── agent/
│   │   └── bot.py                   # 修改: 集成注入逻辑
│   └── services/
│       └── success_evaluator.py     # 修改: 集成SessionPool
├── system_skillbank/                 # 新增: 系统技能存储目录
│   ├── Common/
│   ├── vectors/
│   ├── index/
│   ├── pending/
│   └── champions/
└── migrations/
    └── versions/
        └── xxx_add_system_skills.py  # 新增: 数据库迁移
```

---

## Task 1: 数据模型与数据库迁移

**Files:**
- Create: `autonome-backend/app/models/system_skill.py`
- Create: `autonome-backend/migrations/versions/20260407_add_system_skills.py`

- [ ] **Step 1: 创建 SystemSkill 数据模型**

```python
# autonome-backend/app/models/system_skill.py
"""
系统级学习技能模型

系统级技能与用户技能完全独立:
- 自动从成功会话中提取
- 完全脱敏，不包含用户数据
- 隐身注入到 Agent 上下文
- 所有用户受益
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

from app.models.enums import SkillStatus


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# pgvector Vector 类型导入
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    class Vector:
        def __init__(self, dimension=None):
            self.dimension = dimension


class MethodType:
    """方法类型枚举"""
    ANALYSIS = "analysis"           # 分析方法
    ERROR_FIX = "error_fix"         # 错误修复策略
    EXECUTION_OPT = "execution_opt" # 执行优化


class SystemSkillBase(SQLModel):
    """系统级技能基础模型"""

    # 基本信息
    method_type: str = Field(max_length=50, description="方法类型: analysis|error_fix|execution_opt")
    name: str = Field(max_length=255, description="方法名称（抽象化）")
    description: Optional[str] = Field(default=None, description="方法描述（脱敏）")

    # 可执行内容
    instructions: str = Field(description="可执行指令模板（Markdown格式）")

    # 检索字段
    triggers: List[str] = Field(default_factory=list, sa_column=Column(JSONB))
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSONB))
    examples: List[str] = Field(default_factory=list, sa_column=Column(JSONB))

    # 版本管理
    version: str = Field(default="0.1.0", max_length=50)

    # 演进追踪
    source_sessions: int = Field(default=0, description="来源会话数量")
    confidence_score: float = Field(default=0.6, ge=0.0, le=1.0, description="置信度")
    last_updated: datetime = Field(default_factory=get_utc_now)

    # 统计信息
    injection_count: int = Field(default=0, description="被注入调用次数")
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="注入后成功率")

    # 状态
    status: str = Field(default="active", max_length=20)

    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))


class SystemSkill(SystemSkillBase, table=True):
    """系统级技能数据库表"""
    __tablename__ = "system_skills"

    id: str = Field(primary_key=True, max_length=100, description="UUID")
    skill_id: str = Field(unique=True, index=True, max_length=100, description="全局唯一英文ID")

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    # 语义向量字段 (用于智能推荐)
    combined_embedding: Optional[List[float]] = Field(
        default=None,
        sa_column=Column(Vector(1536)),
        description="混合语义向量嵌入"
    )
    embedding_updated_at: Optional[datetime] = Field(
        default=None,
        description="向量嵌入最后更新时间"
    )


class SystemSkillCreate(SystemSkillBase):
    """用于创建系统技能的请求体"""
    skill_id: Optional[str] = None


class SystemSkillPublic(SystemSkillBase):
    """返回给前端的系统技能公共信息"""
    id: str
    skill_id: str
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 2: 创建数据库迁移脚本**

```python
# autonome-backend/migrations/versions/20260407_add_system_skills.py
"""add system_skills table

Revision ID: 20260407_system_skills
Revises: previous_revision
Create Date: 2026-04-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers
revision = '20260407_system_skills'
down_revision = None  # 填入上一个迁移版本
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'system_skills',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('skill_id', sa.String(100), unique=True, nullable=False),
        sa.Column('method_type', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('triggers', postgresql.JSONB(), server_default='[]'),
        sa.Column('tags', postgresql.JSONB(), server_default='[]'),
        sa.Column('examples', postgresql.JSONB(), server_default='[]'),
        sa.Column('version', sa.String(50), server_default='0.1.0'),
        sa.Column('source_sessions', sa.Integer(), server_default='0'),
        sa.Column('confidence_score', sa.Float(), server_default='0.6'),
        sa.Column('last_updated', sa.DateTime(timezone=True)),
        sa.Column('injection_count', sa.Integer(), server_default='0'),
        sa.Column('success_rate', sa.Float(), server_default='0.0'),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
        sa.Column('combined_embedding', Vector(1536)),
        sa.Column('embedding_updated_at', sa.DateTime(timezone=True)),
    )

    # 创建索引
    op.create_index('ix_system_skills_skill_id', 'system_skills', ['skill_id'])
    op.create_index('ix_system_skills_method_type', 'system_skills', ['method_type'])
    op.create_index('ix_system_skills_status', 'system_skills', ['status'])

    # 创建向量索引 (需要 pgvector 扩展)
    op.execute("""
        CREATE INDEX IF NOT EXISTS system_skills_embedding_idx
        ON system_skills
        USING ivfflat (combined_embedding vector_cosine_ops)
        WITH (lists = 100);
    """)


def downgrade():
    op.drop_index('system_skills_embedding_idx')
    op.drop_index('ix_system_skills_status')
    op.drop_index('ix_system_skills_method_type')
    op.drop_index('ix_system_skills_skill_id')
    op.drop_table('system_skills')
```

- [ ] **Step 3: 运行迁移**

```bash
cd autonome-backend
alembic revision --autogenerate -m "add system_skills table"
alembic upgrade head
```

- [ ] **Step 4: 验证表创建**

```bash
docker exec -i autonome-postgres psql -U autonome -d autonome -c "\d system_skills"
```

---

## Task 2: 隐私验证器

**Files:**
- Create: `autonome-backend/app/services/system_learning/privacy_validator.py`
- Create: `autonome-backend/app/services/system_learning/__init__.py`

- [ ] **Step 1: 创建隐私验证模块**

```python
# autonome-backend/app/services/system_learning/privacy_validator.py
"""
隐私验证器 - 确保提取内容完全脱敏

隐私保护规则:
1. 禁止提取用户数据（基因序列、样本名、具体数值）
2. 禁止提取项目路径或文件名
3. 禁止提取组织/团队/个人信息
4. 仅提取抽象化方法论
"""

import re
from typing import Tuple, List, Dict
from dataclasses import dataclass


@dataclass
class PrivacyRule:
    """隐私规则定义"""
    pattern: str
    replacement: str
    description: str
    severity: str  # error | warning


# 默认隐私规则
PRIVACY_RULES: List[PrivacyRule] = [
    # 文件路径 - 错误级别
    PrivacyRule(
        pattern=r'/[\w\-./]+\.(py|r|txt|csv|tsv|json|yaml|yml)',
        replacement='<FILE_PATH>',
        description="文件路径必须脱敏",
        severity="error"
    ),
    # 基因序列标识
    PrivacyRule(
        pattern=r'(ENSG|ENST|ENSP|ENSMUSG|ENSMUST)[0-9]+',
        replacement='<GENE_ID>',
        description="基因ID必须脱敏",
        severity="error"
    ),
    # 样本名
    PrivacyRule(
        pattern=r'(sample|Sample|SAMPLE)[_-]?[0-9]+',
        replacement='<SAMPLE_ID>',
        description="样本名必须脱敏",
        severity="error"
    ),
    # 组织/团队名
    PrivacyRule(
        pattern=r'(lab|team|group|project|org)[\w\-]+',
        replacement='<ORG>',
        description="组织名称必须脱敏",
        severity="error"
    ),
    # URL
    PrivacyRule(
        pattern=r'https?://[^\s<>"{}|\\^`\[\]]+',
        replacement='<URL>',
        description="URL必须脱敏",
        severity="error"
    ),
    # 具体数值（可配置阈值）
    PrivacyRule(
        pattern=r'\b\d{4,}\b',  # 4位以上数字
        replacement='<NUMBER>',
        description="具体数值必须脱敏",
        severity="warning"
    ),
]

# 禁止关键词
FORBIDDEN_KEYWORDS = [
    "用户名", "密码", "password", "token", "api_key", "secret",
    "项目名称", "组织名称", "团队名称", "客户名称",
]


class PrivacyValidator:
    """隐私验证器"""

    def __init__(self, rules: List[PrivacyRule] = None):
        self.rules = rules or PRIVACY_RULES

    def validate(self, content: str) -> Tuple[bool, List[str]]:
        """
        验证内容是否符合隐私规则

        Args:
            content: 待验证的内容

        Returns:
            Tuple[bool, List[str]]: (是否通过, 错误列表)
        """
        errors = []
        warnings = []

        for rule in self.rules:
            matches = re.findall(rule.pattern, content)
            if matches:
                msg = f"{rule.description}: 发现 {len(matches)} 处匹配 ({rule.pattern[:30]}...)"
                if rule.severity == "error":
                    errors.append(msg)
                else:
                    warnings.append(msg)

        # 检查禁止关键词
        content_lower = content.lower()
        for keyword in FORBIDDEN_KEYWORDS:
            if keyword.lower() in content_lower:
                errors.append(f"包含禁止关键词: {keyword}")

        return len(errors) == 0, errors + warnings

    def redact(self, content: str) -> str:
        """
        自动脱敏内容

        Args:
            content: 待脱敏的内容

        Returns:
            str: 脱敏后的内容
        """
        redacted = content
        for rule in self.rules:
            redacted = re.sub(rule.pattern, rule.replacement, redacted)
        return redacted

    def validate_candidate(self, candidate: Dict) -> Tuple[bool, List[str]]:
        """
        验证技能候选是否符合隐私规则

        Args:
            candidate: 技能候选字典，包含 name, description, instructions, triggers, tags

        Returns:
            Tuple[bool, List[str]]: (是否通过, 错误列表)
        """
        all_errors = []

        # 验证各字段
        fields_to_check = ['name', 'description', 'instructions']
        for field in fields_to_check:
            if field in candidate and candidate[field]:
                is_valid, errors = self.validate(str(candidate[field]))
                if not is_valid:
                    all_errors.extend([f"[{field}] {e}" for e in errors])

        # 验证列表字段
        for field in ['triggers', 'tags', 'examples']:
            if field in candidate and isinstance(candidate[field], list):
                for item in candidate[field]:
                    is_valid, errors = self.validate(str(item))
                    if not is_valid:
                        all_errors.extend([f"[{field}] {e}" for e in errors])

        return len(all_errors) == 0, all_errors


# 全局单例
_validator = None

def get_privacy_validator() -> PrivacyValidator:
    """获取隐私验证器单例"""
    global _validator
    if _validator is None:
        _validator = PrivacyValidator()
    return _validator
```

- [ ] **Step 2: 创建模块入口**

```python
# autonome-backend/app/services/system_learning/__init__.py
"""
系统学习模块

提供系统级自进化学习能力:
- 从成功会话中提取方法论
- 自动脱敏和验证
- 合并更新现有技能
- 隐身注入到 Agent 上下文
"""

from .privacy_validator import PrivacyValidator, get_privacy_validator
from .session_pool import SessionPool, get_session_pool
from .method_extractor import MethodExtractor, get_method_extractor
from .skill_maintainer import SkillMaintainer, get_skill_maintainer
from .skill_injector import SkillInjector, get_skill_injector
from .vector_index import SystemSkillVectorIndex, get_vector_index
from .batch_scheduler import run_learning_cycle, rebuild_vector_index

__all__ = [
    'PrivacyValidator',
    'get_privacy_validator',
    'SessionPool',
    'get_session_pool',
    'MethodExtractor',
    'get_method_extractor',
    'SkillMaintainer',
    'get_skill_maintainer',
    'SkillInjector',
    'get_skill_injector',
    'SystemSkillVectorIndex',
    'get_vector_index',
    'run_learning_cycle',
    'rebuild_vector_index',
]
```

- [ ] **Step 3: 编写单元测试**

```python
# autonome-backend/tests/services/test_privacy_validator.py
import pytest
from app.services.system_learning.privacy_validator import PrivacyValidator, get_privacy_validator


class TestPrivacyValidator:

    def setup_method(self):
        self.validator = PrivacyValidator()

    def test_validate_file_path(self):
        """测试文件路径检测"""
        content = "请处理 /data/project/sample.py 文件"
        is_valid, errors = self.validator.validate(content)
        assert not is_valid
        assert any("文件路径" in e for e in errors)

    def test_validate_gene_id(self):
        """测试基因ID检测"""
        content = "分析基因 ENSG00000123456 的表达"
        is_valid, errors = self.validator.validate(content)
        assert not is_valid
        assert any("基因ID" in e for e in errors)

    def test_validate_sample_name(self):
        """测试样本名检测"""
        content = "处理 sample_001 到 sample_100"
        is_valid, errors = self.validator.validate(content)
        assert not is_valid

    def test_validate_clean_content(self):
        """测试干净内容通过"""
        content = "使用DESeq2进行差异表达分析，输出log2FoldChange和p值"
        is_valid, errors = self.validator.validate(content)
        assert is_valid
        assert len(errors) == 0

    def test_redact_file_path(self):
        """测试自动脱敏"""
        content = "读取 /data/project/counts.csv 文件"
        redacted = self.validator.redact(content)
        assert '<FILE_PATH>' in redacted
        assert '/data/project/counts.csv' not in redacted

    def test_redact_multiple_patterns(self):
        """测试多模式脱敏"""
        content = "样本 sample_001 来自 https://example.com/data"
        redacted = self.validator.redact(content)
        assert '<SAMPLE_ID>' in redacted
        assert '<URL>' in redacted

    def test_validate_candidate(self):
        """测试技能候选验证"""
        candidate = {
            "name": "差异表达分析策略",
            "description": "用于RNA-seq数据的标准分析流程",
            "instructions": "# 目标\n执行DESeq2差异分析\n# 步骤\n1. 加载数据\n2. 运行DESeq2",
            "triggers": ["差异分析", "DESeq2"],
            "tags": ["transcriptomics", "rnaseq"]
        }
        is_valid, errors = self.validator.validate_candidate(candidate)
        assert is_valid

    def test_validate_candidate_with_sensitive_data(self):
        """测试包含敏感数据的候选"""
        candidate = {
            "name": "小鼠肝脏RNA-seq分析",
            "description": "分析 /project/mouse_liver/ 数据",
            "instructions": "处理样本 sample_001 到 sample_050",
        }
        is_valid, errors = self.validator.validate_candidate(candidate)
        assert not is_valid
```

- [ ] **Step 4: 运行测试验证**

```bash
cd autonome-backend
pytest tests/services/test_privacy_validator.py -v
```

- [ ] **Step 5: 提交代码**

```bash
git add app/services/system_learning/ tests/services/test_privacy_validator.py
git commit -m "feat(system-learning): add privacy validator for skill extraction"
```

---

## Task 3: 会话池管理

**Files:**
- Create: `autonome-backend/app/services/system_learning/session_pool.py`

- [ ] **Step 1: 创建会话池管理器**

```python
# autonome-backend/app/services/system_learning/session_pool.py
"""
会话池管理器 - 管理待处理的成功会话

功能:
1. 收集成功会话（confidence > 0.8）
2. 过滤无效会话
3. 提供批量获取接口
4. 自动清理过期会话
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import uuid

from app.core.logger import log


@dataclass
class PendingSession:
    """待处理会话"""
    session_id: str
    confidence: float
    user_id: int
    project_id: int
    message_count: int
    has_code: bool
    evaluated_at: str
    added_at: str = ""

    def __post_init__(self):
        if not self.added_at:
            self.added_at = datetime.utcnow().isoformat()


class SessionPool:
    """会话池管理器"""

    def __init__(self, pool_dir: str = None):
        """
        初始化会话池

        Args:
            pool_dir: 池存储目录，默认为 system_skillbank/pending/
        """
        if pool_dir:
            self.pool_dir = Path(pool_dir)
        else:
            # 默认路径
            backend_dir = Path(__file__).parent.parent.parent.parent
            self.pool_dir = backend_dir / "system_skillbank" / "pending"

        self.pool_file = self.pool_dir / "session_pool.json"
        self._ensure_dir()

    def _ensure_dir(self):
        """确保目录存在"""
        self.pool_dir.mkdir(parents=True, exist_ok=True)

    def _load_pool(self) -> Dict[str, Any]:
        """加载池数据"""
        if not self.pool_file.exists():
            return {"sessions": {}, "metadata": {}}

        try:
            with open(self.pool_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"加载会话池失败: {e}")
            return {"sessions": {}, "metadata": {}}

    def _save_pool(self, data: Dict[str, Any]):
        """保存池数据"""
        with open(self.pool_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_session(
        self,
        session_id: str,
        confidence: float,
        user_id: int,
        project_id: int,
        message_count: int = 0,
        has_code: bool = False
    ) -> bool:
        """
        添加会话到池中

        条件:
        - confidence > 0.8
        - 会话长度 >= 3轮（可选）
        - 包含 assistant 策略输出（可选）

        Args:
            session_id: 会话ID
            confidence: 置信度
            user_id: 用户ID
            project_id: 项目ID
            message_count: 消息数量
            has_code: 是否包含代码

        Returns:
            bool: 是否成功添加
        """
        # 验证条件
        if confidence < 0.8:
            log.debug(f"会话 {session_id} 置信度不足: {confidence}")
            return False

        if message_count < 3:
            log.debug(f"会话 {session_id} 消息数不足: {message_count}")
            return False

        # 加载现有数据
        data = self._load_pool()

        # 检查是否已存在
        if session_id in data["sessions"]:
            log.debug(f"会话 {session_id} 已在池中")
            return False

        # 添加会话
        pending = PendingSession(
            session_id=session_id,
            confidence=confidence,
            user_id=user_id,
            project_id=project_id,
            message_count=message_count,
            has_code=has_code,
            evaluated_at=datetime.utcnow().isoformat()
        )

        data["sessions"][session_id] = asdict(pending)
        data["metadata"]["last_updated"] = datetime.utcnow().isoformat()
        data["metadata"]["total_count"] = len(data["sessions"])

        self._save_pool(data)
        log.info(f"会话 {session_id} 已添加到学习池 (置信度: {confidence})")
        return True

    def get_pending_sessions(self, limit: int = 100) -> List[str]:
        """
        获取待处理会话ID列表

        Args:
            limit: 最大返回数量

        Returns:
            List[str]: 会话ID列表
        """
        data = self._load_pool()
        sessions = data.get("sessions", {})

        # 按置信度排序
        sorted_sessions = sorted(
            sessions.items(),
            key=lambda x: x[1].get("confidence", 0),
            reverse=True
        )

        return [s[0] for s in sorted_sessions[:limit]]

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """获取会话详情"""
        data = self._load_pool()
        return data.get("sessions", {}).get(session_id)

    def mark_processed(self, session_id: str, extracted: bool = True):
        """
        标记会话已处理

        Args:
            session_id: 会话ID
            extracted: 是否成功提取
        """
        data = self._load_pool()

        if session_id in data["sessions"]:
            del data["sessions"][session_id]
            data["metadata"]["last_updated"] = datetime.utcnow().isoformat()
            data["metadata"]["total_count"] = len(data["sessions"])
            data["metadata"]["processed_count"] = data["metadata"].get("processed_count", 0) + 1

            self._save_pool(data)
            log.info(f"会话 {session_id} 已标记为已处理 (提取: {extracted})")

    def cleanup_expired(self, days: int = 7) -> int:
        """
        清理过期未处理会话

        Args:
            days: 过期天数

        Returns:
            int: 清理数量
        """
        data = self._load_pool()
        sessions = data.get("sessions", {})

        cutoff = datetime.utcnow() - timedelta(days=days)
        expired = []

        for session_id, info in sessions.items():
            added_at = info.get("added_at", info.get("evaluated_at", ""))
            try:
                added_time = datetime.fromisoformat(added_at)
                if added_time < cutoff:
                    expired.append(session_id)
            except:
                pass

        for session_id in expired:
            del data["sessions"][session_id]

        if expired:
            data["metadata"]["last_updated"] = datetime.utcnow().isoformat()
            data["metadata"]["total_count"] = len(data["sessions"])
            self._save_pool(data)
            log.info(f"清理了 {len(expired)} 个过期会话")

        return len(expired)

    def get_stats(self) -> Dict[str, Any]:
        """获取池统计信息"""
        data = self._load_pool()
        sessions = data.get("sessions", {})

        if not sessions:
            return {
                "total": 0,
                "avg_confidence": 0,
                "by_user": {},
                "oldest": None
            }

        confidences = [s.get("confidence", 0) for s in sessions.values()]
        by_user = {}
        oldest = None

        for session_id, info in sessions.items():
            user_id = info.get("user_id", 0)
            by_user[user_id] = by_user.get(user_id, 0) + 1

            added = info.get("added_at", "")
            if oldest is None or (added and added < oldest):
                oldest = added

        return {
            "total": len(sessions),
            "avg_confidence": sum(confidences) / len(confidences) if confidences else 0,
            "by_user": by_user,
            "oldest": oldest
        }


# 全局单例
_pool = None

def get_session_pool() -> SessionPool:
    """获取会话池单例"""
    global _pool
    if _pool is None:
        _pool = SessionPool()
    return _pool
```

- [ ] **Step 2: 运行测试**

```bash
cd autonome-backend
pytest tests/services/test_session_pool.py -v
```

- [ ] **Step 3: 提交代码**

```bash
git add app/services/system_learning/session_pool.py
git commit -m "feat(system-learning): add session pool manager"
```

---

## Task 4: 方法提取器

**Files:**
- Create: `autonome-backend/app/services/system_learning/method_extractor.py`

- [ ] **Step 1: 创建方法提取器**

```python
# autonome-backend/app/services/system_learning/method_extractor.py
"""
方法提取器 - 从成功会话中提取抽象化方法

核心功能:
1. LLM 提取方法论
2. 自动脱敏处理
3. 隐私二次验证
4. 生成结构化候选
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import json

from app.core.logger import log
from app.services.system_learning.privacy_validator import get_privacy_validator


@dataclass
class MethodCandidate:
    """方法候选"""
    method_type: str  # analysis | error_fix | execution_opt
    name: str
    description: str
    instructions: str  # Markdown 格式
    triggers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    confidence: float = 0.6
    source_session: Optional[str] = None


# LLM 提取提示词
EXTRACTION_SYSTEM_PROMPT = """你是 AUTONOME 系统的方法提取专家。

任务：从对话中提取可复用的方法论。

【隐私规则 - 必须遵守】
- 禁止提取用户数据内容（基因序列、样本名、具体数值、项目名称）
- 禁止提取项目路径或文件名
- 禁止提取组织/团队/个人信息
- 仅提取：分析策略、参数推荐模式、错误处理逻辑

【提取要求】
1. method_type: analysis（分析方法） | error_fix（错误修复） | execution_opt（执行优化）
2. name: 抽象化名称（如"差异表达分析策略"而非"小鼠肝脏RNA-seq分析"）
3. triggers: 触发关键词（如"DESeq2"、"差异分析"、"count矩阵"）
4. instructions: 可执行指令模板（Markdown格式，包含 # 目标、# 约束、# 步骤）
5. examples: 抽象输入输出模式（用 {{value}} 替代具体值）

【输出格式】严格 JSON：
{
  "skills": [{
    "method_type": "analysis",
    "name": "技能名称",
    "description": "简要描述",
    "prompt": "# 目标\\n...\\n# 约束\\n...\\n# 步骤\\n...",
    "triggers": ["关键词1", "关键词2"],
    "tags": ["标签1", "标签2"],
    "confidence": 0.8
  }]
}

如果对话不包含可复用的方法论，返回 {"skills": []}"""

EXTRACTION_USER_PROMPT = """请从以下对话中提取方法论：

【会话内容】
{conversation}

【用户主要问题】
{primary_questions}

请提取可复用的方法论，返回 JSON 格式。"""


class MethodExtractor:
    """方法提取器"""

    def __init__(self, llm_client=None):
        """
        初始化提取器

        Args:
            llm_client: LLM 客户端（LangChain ChatOpenAI 或类似）
        """
        self.llm_client = llm_client
        self.privacy_validator = get_privacy_validator()

    def extract_from_session(
        self,
        session_messages: List[Dict[str, str]],
        session_id: str = None
    ) -> List[MethodCandidate]:
        """
        从会话中提取方法候选

        Args:
            session_messages: 消息列表 [{"role": "user|assistant", "content": "..."}]
            session_id: 会话ID（用于追踪）

        Returns:
            List[MethodCandidate]: 提取的方法候选列表
        """
        if not session_messages:
            return []

        # 1. 准备对话内容
        conversation = self._format_conversation(session_messages)
        primary_questions = self._extract_user_questions(session_messages)

        # 2. 调用 LLM 提取
        try:
            extraction_result = self._call_llm(conversation, primary_questions)
        except Exception as e:
            log.error(f"LLM 提取失败: {e}")
            return []

        # 3. 解析结果
        candidates = self._parse_extraction(extraction_result, session_id)

        # 4. 隐私验证
        valid_candidates = []
        for candidate in candidates:
            is_valid, errors = self.privacy_validator.validate_candidate({
                "name": candidate.name,
                "description": candidate.description,
                "instructions": candidate.instructions,
                "triggers": candidate.triggers,
                "tags": candidate.tags
            })

            if is_valid:
                valid_candidates.append(candidate)
            else:
                log.warning(f"方法候选隐私验证失败: {errors}")

        return valid_candidates

    def _format_conversation(self, messages: List[Dict]) -> str:
        """格式化对话内容"""
        lines = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # 截断过长内容
            if len(content) > 2000:
                content = content[:2000] + "...(truncated)"
            lines.append(f"[{role.upper()}]: {content}")
        return "\n\n".join(lines)

    def _extract_user_questions(self, messages: List[Dict]) -> str:
        """提取用户问题"""
        questions = []
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if len(content) > 500:
                    content = content[:500] + "..."
                questions.append(content)
        return "\n".join(questions[:5])  # 最多5个问题

    def _call_llm(self, conversation: str, primary_questions: str) -> Dict:
        """调用 LLM 进行提取"""
        if self.llm_client is None:
            log.warning("LLM 客户端未配置，跳过提取")
            return {"skills": []}

        user_prompt = EXTRACTION_USER_PROMPT.format(
            conversation=conversation,
            primary_questions=primary_questions
        )

        try:
            response = self.llm_client.invoke([
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ])

            content = response.content if hasattr(response, 'content') else str(response)

            # 解析 JSON
            # 清理可能的 markdown 代码块
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]

            return json.loads(content)

        except json.JSONDecodeError as e:
            log.error(f"JSON 解析失败: {e}")
            return {"skills": []}
        except Exception as e:
            log.error(f"LLM 调用失败: {e}")
            return {"skills": []}

    def _parse_extraction(
        self,
        result: Dict,
        session_id: str = None
    ) -> List[MethodCandidate]:
        """解析提取结果"""
        candidates = []

        skills = result.get("skills", [])
        for skill in skills:
            if not isinstance(skill, dict):
                continue

            # 验证必要字段
            name = skill.get("name", "").strip()
            instructions = skill.get("prompt", skill.get("instructions", "")).strip()

            if not name or not instructions:
                continue

            candidate = MethodCandidate(
                method_type=skill.get("method_type", "analysis"),
                name=name,
                description=skill.get("description", name),
                instructions=instructions,
                triggers=skill.get("triggers", []),
                tags=skill.get("tags", []),
                examples=skill.get("examples", []),
                confidence=float(skill.get("confidence", 0.6)),
                source_session=session_id
            )
            candidates.append(candidate)

        return candidates


# 全局单例
_extractor = None

def get_method_extractor(llm_client=None) -> MethodExtractor:
    """获取方法提取器单例"""
    global _extractor
    if _extractor is None:
        _extractor = MethodExtractor(llm_client)
    return _extractor
```

- [ ] **Step 2: 提交代码**

```bash
git add app/services/system_learning/method_extractor.py
git commit -m "feat(system-learning): add method extractor with LLM and privacy validation"
```

---

## Task 5: 技能注入器

**Files:**
- Create: `autonome-backend/app/services/system_learning/skill_injector.py`

- [ ] **Step 1: 创建技能注入器**

```python
# autonome-backend/app/services/system_learning/skill_injector.py
"""
技能注入器 - Agent 调用时隐身注入系统技能

核心功能:
1. 混合检索（向量 + BM25）
2. Top-K 返回
3. 隐身注入到 Agent 上下文
"""

from typing import List, Dict, Any, Optional
from sqlmodel import Session, select
import numpy as np

from app.core.logger import log
from app.core.database import engine
from app.models.system_skill import SystemSkill


class SkillInjector:
    """技能注入器 - 隐身注入系统技能到 Agent"""

    # 配置
    TOP_K = 3  # 最多注入3个技能
    SIMILARITY_THRESHOLD = 0.7  # 相似度阈值
    VECTOR_WEIGHT = 0.7  # 向量检索权重
    KEYWORD_WEIGHT = 0.3  # 关键词检索权重

    def __init__(self, session: Session = None):
        """
        初始化注入器

        Args:
            session: 数据库会话
        """
        self.session = session

    def inject_for_query(
        self,
        query: str,
        context: Dict = None,
        limit: int = None
    ) -> List[str]:
        """
        为查询注入相关系统技能

        Args:
            query: 用户查询
            context: 额外上下文
            limit: 最大返回数量

        Returns:
            List[str]: 技能指令列表，用于注入到 system prompt
        """
        limit = limit or self.TOP_K

        # 混合检索
        skills = self.hybrid_search(query, limit=limit)

        if not skills:
            return []

        # 提取指令
        instructions = []
        for skill in skills:
            instruction = self._format_instruction(skill)
            instructions.append(instruction)

            # 记录注入
            self._record_injection(skill.skill_id, query)

        log.info(f"注入 {len(instructions)} 个系统技能 (查询: {query[:50]}...)")
        return instructions

    def hybrid_search(
        self,
        query: str,
        limit: int = 5
    ) -> List[SystemSkill]:
        """
        混合检索：向量相似度 + 关键词匹配

        Args:
            query: 查询文本
            limit: 最大返回数量

        Returns:
            List[SystemSkill]: 匹配的系统技能列表
        """
        # 1. 向量检索
        vector_results = self._vector_search(query, limit=limit * 2)

        # 2. 关键词检索
        keyword_results = self._keyword_search(query, limit=limit * 2)

        # 3. 合并排序
        merged = self._merge_results(vector_results, keyword_results)

        return merged[:limit]

    def _vector_search(
        self,
        query: str,
        limit: int = 10
    ) -> List[tuple]:
        """
        向量语义检索

        Returns:
            List[tuple]: [(SystemSkill, similarity_score), ...]
        """
        try:
            # 生成查询向量
            query_embedding = self._get_embedding(query)
            if query_embedding is None:
                return []

            # 数据库查询
            session = self.session or Session(engine)
            try:
                # 使用 pgvector 余弦相似度
                statement = select(SystemSkill).where(
                    SystemSkill.status == "active",
                    SystemSkill.combined_embedding.isnot(None)
                )

                skills = session.exec(statement).all()

                # 计算相似度
                results = []
                for skill in skills:
                    if skill.combined_embedding:
                        similarity = self._cosine_similarity(
                            query_embedding,
                            skill.combined_embedding
                        )
                        if similarity >= self.SIMILARITY_THRESHOLD:
                            results.append((skill, similarity))

                # 按相似度排序
                results.sort(key=lambda x: x[1], reverse=True)
                return results[:limit]

            finally:
                if not self.session:
                    session.close()

        except Exception as e:
            log.error(f"向量检索失败: {e}")
            return []

    def _keyword_search(
        self,
        query: str,
        limit: int = 10
    ) -> List[tuple]:
        """
        关键词匹配检索

        Returns:
            List[tuple]: [(SystemSkill, match_score), ...]
        """
        try:
            session = self.session or Session(engine)
            try:
                # 提取关键词
                query_keywords = set(query.lower().split())

                statement = select(SystemSkill).where(
                    SystemSkill.status == "active"
                )
                skills = session.exec(statement).all()

                results = []
                for skill in skills:
                    # 计算关键词匹配分数
                    skill_keywords = set()
                    for trigger in (skill.triggers or []):
                        skill_keywords.update(trigger.lower().split())
                    for tag in (skill.tags or []):
                        skill_keywords.update(tag.lower().split())

                    # Jaccard 相似度
                    if skill_keywords:
                        intersection = len(query_keywords & skill_keywords)
                        union = len(query_keywords | skill_keywords)
                        score = intersection / union if union > 0 else 0

                        if score > 0:
                            results.append((skill, score))

                results.sort(key=lambda x: x[1], reverse=True)
                return results[:limit]

            finally:
                if not self.session:
                    session.close()

        except Exception as e:
            log.error(f"关键词检索失败: {e}")
            return []

    def _merge_results(
        self,
        vector_results: List[tuple],
        keyword_results: List[tuple]
    ) -> List[SystemSkill]:
        """合并向量和关键词结果"""
        # 分数归一化
        skill_scores: Dict[str, float] = {}

        # 向量结果
        for skill, score in vector_results:
            skill_scores[skill.skill_id] = skill_scores.get(skill.skill_id, 0) + \
                                           score * self.VECTOR_WEIGHT

        # 关键词结果
        for skill, score in keyword_results:
            skill_scores[skill.skill_id] = skill_scores.get(skill.skill_id, 0) + \
                                           score * self.KEYWORD_WEIGHT

        # 获取技能并排序
        session = self.session or Session(engine)
        try:
            skills = []
            for skill_id, score in sorted(skill_scores.items(),
                                          key=lambda x: x[1],
                                          reverse=True):
                statement = select(SystemSkill).where(
                    SystemSkill.skill_id == skill_id
                )
                skill = session.exec(statement).first()
                if skill:
                    skills.append(skill)
            return skills
        finally:
            if not self.session:
                session.close()

    def _format_instruction(self, skill: SystemSkill) -> str:
        """格式化技能指令"""
        return f"""## 系统学习技能: {skill.name}

{skill.instructions}

*置信度: {skill.confidence_score:.2f} | 来源会话: {skill.source_sessions}*
"""

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """获取文本向量嵌入"""
        try:
            # 使用 OpenAI Embeddings
            from langchain_openai import OpenAIEmbeddings
            import os

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return None

            embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=api_key
            )

            result = embeddings.embed_query(text)
            return result

        except Exception as e:
            log.error(f"获取向量嵌入失败: {e}")
            return None

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        a_np = np.array(a)
        b_np = np.array(b)
        return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))

    def _record_injection(self, skill_id: str, query: str):
        """记录注入事件"""
        try:
            session = self.session or Session(engine)
            try:
                statement = select(SystemSkill).where(
                    SystemSkill.skill_id == skill_id
                )
                skill = session.exec(statement).first()
                if skill:
                    skill.injection_count += 1
                    session.add(skill)
                    session.commit()
            finally:
                if not self.session:
                    session.close()
        except Exception as e:
            log.error(f"记录注入失败: {e}")


# 全局单例
_injector = None

def get_skill_injector(session: Session = None) -> SkillInjector:
    """获取技能注入器单例"""
    global _injector
    if _injector is None:
        _injector = SkillInjector(session)
    return _injector
```

- [ ] **Step 2: 提交代码**

```bash
git add app/services/system_learning/skill_injector.py
git commit -m "feat(system-learning): add skill injector with hybrid search"
```

---

## Task 6: Agent 集成

**Files:**
- Modify: `autonome-backend/app/agent/bot.py`

- [ ] **Step 1: 修改 bot.py 集成注入逻辑**

找到 `build_bio_agent` 函数，在构建 system prompt 后添加注入逻辑：

```python
# 在 autonome-backend/app/agent/bot.py 文件中
# 在 imports 部分添加:
from app.services.system_learning.skill_injector import get_skill_injector

# 在 build_bio_agent 函数中，构建 system_prompt 后添加:

    # ==========================================
    # 系统学习技能注入（隐身）
    # ==========================================
    try:
        injector = get_skill_injector()
        # 从用户第一条消息推断查询意图
        if physical_file_info:
            # 简单的意图推断
            query_hint = physical_file_info[:500] if physical_file_info else ""
            system_skills = injector.inject_for_query(query_hint, limit=3)

            if system_skills:
                system_prompt += "\n\n" + "="*50 + "\n"
                system_prompt += "【系统学习技能 - 自动推荐】\n"
                system_prompt += "="*50 + "\n\n"
                system_prompt += "\n\n---\n\n".join(system_skills)
                log.info(f"🧠 [Bot] 注入了 {len(system_skills)} 个系统学习技能")
    except Exception as e:
        log.warning(f"⚠️ [Bot] 系统技能注入失败: {e}")
```

- [ ] **Step 2: 提交代码**

```bash
git add app/agent/bot.py
git commit -m "feat(system-learning): integrate skill injector into agent"
```

---

## Task 7: SuccessEvaluator 集成

**Files:**
- Modify: `autonome-backend/app/services/success_evaluator.py`

- [ ] **Step 1: 修改 success_evaluator.py 集成 SessionPool**

```python
# 在 imports 部分添加:
from app.services.system_learning.session_pool import get_session_pool

# 在 evaluate_session 方法末尾添加:

    # ==========================================
    # 系统学习：成功会话加入 SessionPool
    # ==========================================
    try:
        if result.get("confidence", 0) > 0.8:
            pool = get_session_pool()
            pool.add_session(
                session_id=session.id,
                confidence=result["confidence"],
                user_id=session.user_id,
                project_id=session.project_id,
                message_count=len(session.messages) if hasattr(session, 'messages') else 0,
                has_code=result.get("has_code", False)
            )
    except Exception as e:
        log.warning(f"添加会话到学习池失败: {e}")
```

- [ ] **Step 2: 提交代码**

```bash
git add app/services/success_evaluator.py
git commit -m "feat(system-learning): integrate session pool into success evaluator"
```

---

## Task 8: 定时任务调度

**Files:**
- Create: `autonome-backend/app/services/system_learning/batch_scheduler.py`

- [ ] **Step 1: 创建 Celery 定时任务**

```python
# autonome-backend/app/services/system_learning/batch_scheduler.py
"""
定时任务调度 - Celery Beat

任务:
1. run_learning_cycle: 每小时执行，提取和更新系统技能
2. rebuild_vector_index: 每天执行，重建向量索引
"""

from celery import shared_task
from datetime import datetime

from app.core.logger import log
from app.services.system_learning.session_pool import get_session_pool
from app.services.system_learning.method_extractor import get_method_extractor
from app.services.system_learning.skill_maintainer import get_skill_maintainer
from app.services.system_learning.vector_index import get_vector_index


@shared_task(name="system_learning.run_learning_cycle")
def run_learning_cycle():
    """
    学习周期任务（每小时执行）

    流程:
    1. 从 SessionPool 获取待处理会话
    2. 批量提取方法候选
    3. 合并更新现有技能
    4. 更新向量索引
    5. 清理过期会话
    """
    start_time = datetime.utcnow()
    log.info("🔄 [SystemLearning] 开始学习周期")

    stats = {
        "processed_sessions": 0,
        "extracted_candidates": 0,
        "merged_skills": 0,
        "new_skills": 0,
        "errors": 0
    }

    try:
        # 1. 获取待处理会话
        pool = get_session_pool()
        session_ids = pool.get_pending_sessions(limit=100)

        if not session_ids:
            log.info("🔄 [SystemLearning] 没有待处理会话")
            return stats

        log.info(f"🔄 [SystemLearning] 处理 {len(session_ids)} 个会话")

        # 2. 批量提取
        extractor = get_method_extractor()
        maintainer = get_skill_maintainer()

        for session_id in session_ids:
            try:
                # 从数据库加载会话消息
                # 这里需要实现从 ChatSession 表加载消息的逻辑
                # session_messages = load_session_messages(session_id)
                # candidates = extractor.extract_from_session(session_messages, session_id)

                # 标记已处理
                pool.mark_processed(session_id)
                stats["processed_sessions"] += 1

            except Exception as e:
                log.error(f"处理会话 {session_id} 失败: {e}")
                stats["errors"] += 1

        # 3. 清理过期会话
        pool.cleanup_expired(days=7)

        # 4. 更新向量索引
        # index = get_vector_index()
        # index.rebuild_index()

    except Exception as e:
        log.error(f"学习周期执行失败: {e}")
        stats["errors"] += 1

    duration = (datetime.utcnow() - start_time).total_seconds()
    log.info(f"🔄 [SystemLearning] 学习周期完成: {stats}, 耗时 {duration:.2f}s")

    return stats


@shared_task(name="system_learning.rebuild_vector_index")
def rebuild_vector_index():
    """
    重建向量索引（每天执行）

    流程:
    1. 重新计算所有技能的 embedding
    2. 更新 pgvector 索引
    3. 重建 BM25 索引
    """
    log.info("🔄 [SystemLearning] 开始重建向量索引")

    try:
        index = get_vector_index()
        index.rebuild_index()
        log.info("🔄 [SystemLearning] 向量索引重建完成")
        return {"status": "success"}

    except Exception as e:
        log.error(f"重建向量索引失败: {e}")
        return {"status": "error", "message": str(e)}


# Celery Beat 配置
CELERYBEAT_SCHEDULE = {
    'system-learning-hourly': {
        'task': 'system_learning.run_learning_cycle',
        'schedule': 60 * 60,  # 每小时
    },
    'system-learning-daily-index': {
        'task': 'system_learning.rebuild_vector_index',
        'schedule': 24 * 60 * 60,  # 每天
    },
}
```

- [ ] **Step 2: 提交代码**

```bash
git add app/services/system_learning/batch_scheduler.py
git commit -m "feat(system-learning): add celery beat scheduled tasks"
```

---

## Task 9: API 路由

**Files:**
- Create: `autonome-backend/app/api/routes/system_learning.py`

- [ ] **Step 1: 创建管理 API**

```python
# autonome-backend/app/api/routes/system_learning.py
"""
系统学习管理 API

虽然是隐身系统，但提供管理接口用于:
- 查看学习统计
- 手动触发学习
- 管理系统技能
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import Optional

from app.core.database import get_session
from app.models.system_skill import SystemSkill, SystemSkillPublic
from app.services.system_learning.session_pool import get_session_pool
from app.services.system_learning.batch_scheduler import run_learning_cycle

router = APIRouter(prefix="/system-learning", tags=["System Learning"])


@router.get("/stats")
async def get_learning_stats():
    """
    获取学习统计

    返回:
    - total_skills: 系统技能总数
    - by_type: 各类型技能数量
    - pool_stats: 会话池统计
    """
    pool = get_session_pool()
    pool_stats = pool.get_stats()

    # 从数据库查询技能统计
    session = next(get_session())
    total_skills = session.exec(select(SystemSkill).where(SystemSkill.status == "active")).all()
    by_type = {"analysis": 0, "error_fix": 0, "execution_opt": 0}
    for skill in total_skills:
        if skill.method_type in by_type:
            by_type[skill.method_type] += 1

    return {
        "total_skills": len(total_skills),
        "by_type": by_type,
        "pool_stats": pool_stats
    }


@router.post("/trigger")
async def trigger_learning():
    """
    手动触发学习周期

    返回:
    - processed_sessions: 处理会话数
    - extracted_skills: 提取技能数
    - updated_skills: 更新技能数
    """
    result = run_learning_cycle()
    return result


@router.get("/skills", response_model=list[SystemSkillPublic])
async def list_system_skills(
    method_type: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_session)
):
    """列出系统技能（只读）"""
    statement = select(SystemSkill).where(SystemSkill.status == "active")

    if method_type:
        statement = statement.where(SystemSkill.method_type == method_type)

    statement = statement.limit(limit)
    skills = session.exec(statement).all()
    return skills


@router.get("/skills/{skill_id}", response_model=SystemSkillPublic)
async def get_system_skill(
    skill_id: str,
    session: Session = Depends(get_session)
):
    """获取单个系统技能详情"""
    statement = select(SystemSkill).where(SystemSkill.skill_id == skill_id)
    skill = session.exec(statement).first()

    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    return skill


@router.delete("/skills/{skill_id}")
async def delete_system_skill(
    skill_id: str,
    session: Session = Depends(get_session)
):
    """删除低质量系统技能"""
    statement = select(SystemSkill).where(SystemSkill.skill_id == skill_id)
    skill = session.exec(statement).first()

    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # 软删除：标记为 deprecated
    skill.status = "deprecated"
    session.add(skill)
    session.commit()

    return {"status": "deleted", "skill_id": skill_id}
```

- [ ] **Step 2: 注册路由**

在 `autonome-backend/app/api/main.py` 中添加:

```python
from app.api.routes.system_learning import router as system_learning_router
api_router.include_router(system_learning_router)
```

- [ ] **Step 3: 提交代码**

```bash
git add app/api/routes/system_learning.py app/api/main.py
git commit -m "feat(system-learning): add management API routes"
```

---

## Task 10: 创建系统技能存储目录

**Files:**
- Create: `autonome-backend/system_skillbank/` 目录结构

- [ ] **Step 1: 创建目录结构**

```bash
cd autonome-backend
mkdir -p system_skillbank/{Common/{analysis_methods,error_fix_strategies,execution_optimizations},vectors,index,pending,champions}
```

- [ ] **Step 2: 创建 .gitkeep 文件**

```bash
touch system_skillbank/{Common,vectors,index,pending,champions}/.gitkeep
```

- [ ] **Step 3: 提交代码**

```bash
git add system_skillbank/
git commit -m "feat(system-learning): create system skillbank directory structure"
```

---

## 验证清单

完成所有任务后，运行以下验证:

- [ ] **验证数据库表创建**

```bash
docker exec -i autonome-postgres psql -U autonome -d autonome -c "SELECT * FROM system_skills LIMIT 1;"
```

- [ ] **验证 API 可访问**

```bash
curl http://localhost:8000/api/system-learning/stats
```

- [ ] **验证注入日志**

启动应用后，观察日志中是否有 `[Bot] 注入了 X 个系统学习技能` 输出。

---

## 后续优化

1. **向量索引优化**: 使用 HNSW 索引替代 IVFFlat
2. **BM25 集成**: 集成 rank_bm25 进行关键词检索
3. **技能质量评估**: 添加自动化测试验证技能有效性
4. **监控指标**: 集成 Prometheus 指标导出
5. **人工审核**: 添加低置信度技能的人工审核流程