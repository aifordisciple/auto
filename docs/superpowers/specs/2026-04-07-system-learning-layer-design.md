# System Learning Layer - 系统级自进化学习层设计文档

**日期**: 2026-04-07
**状态**: 设计完成，待实施
**参考**: AutoSkill-main (ECNU-ICALK)

---

## 1. 概述

### 1.1 目标

构建一个**系统级隐身学习层**，从所有用户对话中自动提取方法论和策略，持续优化 Agent 能力，所有用户受益。

### 1.2 核心特性

| 维度 | 决策 |
|------|------|
| 系统定位 | 独立SkillBank层，不侵入现有技能中心 |
| 触发时机 | 定时批量处理（Celery Beat，每小时） |
| 学习内容 | 全流程方法（分析策略 + 错误修复 + 执行优化） |
| 可见性 | 完全隐身，Agent自动调用，用户无感知 |
| 数据隐私 | 抽象化+脱敏（不保留用户项目数据） |
| 演进方式 | 合并更新（验证后版本递增） |

### 1.3 与现有系统的关系

```
┌─────────────────────────────────────────────────────────────────┐
│                     AUTONOME 技能生态系统                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────────┐     ┌─────────────────────┐         │
│   │  用户技能系统        │     │  系统学习层 (新增)   │         │
│   │  (SkillAsset)       │     │  (SystemSkill)      │         │
│   │                     │     │                     │         │
│   │  - 用户创建          │     │  - 自动学习          │         │
│   │  - 手动编辑          │     │  - 脱敏提取          │         │
│   │  - 技能中心可见      │     │  - 隐身注入          │         │
│   │  - 执行器运行        │     │  - Agent优先调用     │         │
│   └─────────────────────┘     └─────────────────────┘         │
│              │                          │                      │
│              └──────────┬───────────────┘                      │
│                         │                                      │
│                         ▼                                      │
│              ┌─────────────────────┐                          │
│              │      Agent (bot.py) │                          │
│              │  统一调用入口        │                          │
│              └─────────────────────┘                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     SYSTEM LEARNING LAYER                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   用户对话 ──────────────────────┐                              │
│      ↓                           │                              │
│   ChatMessage/BehaviorRecord     │                              │
│      ↓                           │  定时批量触发                 │
│   ┌─────────────────┐            │  (Celery Beat, 每小时)       │
│   │  Session Pool   │◄───────────┘                              │
│   │  (筛选成功会话) │                                           │
│   │  confidence>0.8 │                                           │
│   └─────────────────┘                                           │
│          ↓                                                      │
│   ┌─────────────────────────────────────┐                      │
│   │        Method Extractor             │                      │
│   │  (LLM提取抽象策略 + 脱敏处理)        │                      │
│   └─────────────────────────────────────┘                      │
│          ↓                                                      │
│   ┌─────────────────────────────────────┐                      │
│   │        Skill Bank (Common/)         │  ← 系统级技能存储      │
│   │  ├── analysis_methods/              │                      │
│   │  ├── error_fix_strategies/          │                      │
│   │  └── execution_optimizations/       │                      │
│   └─────────────────────────────────────┘                      │
│          ↓                                                      │
│   ┌─────────────────────────────────────┐                      │
│   │        Skill Maintainer             │                      │
│   │  (合并+版本更新+验证)                │                      │
│   └─────────────────────────────────────┘                      │
│          ↓                                                      │
│   ┌─────────────────────────────────────┐                      │
│   │        Vector Index                 │                      │
│   │  (pgvector语义向量 + BM25关键词)     │                      │
│   └─────────────────────────────────────┘                      │
│          ↓                                                      │
│   ┌─────────────────────────────────────┐                      │
│   │        Skill Injector               │  ← Agent调用时注入     │
│   │  (检索匹配→注入到Agent上下文)        │                      │
│   └─────────────────────────────────────┘                      │
│          ↓                                                      │
│   Agent (bot.py) ─── 自动使用系统技能 ─── 用户无感知             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
1. 数据收集阶段（每小时）
   ┌──────────────────────────────────────────────────────────────┐
   │ ChatSession → SuccessEvaluator → SessionPool                │
   │ (所有会话)    (筛选成功会话)      (待处理池)                  │
   └──────────────────────────────────────────────────────────────┘

2. 提取阶段
   ┌──────────────────────────────────────────────────────────────┐
   │ SessionPool → MethodExtractor → MethodCandidates            │
   │              (LLM+脱敏)         (候选方法)                   │
   └──────────────────────────────────────────────────────────────┘

3. 维护阶段
   ┌──────────────────────────────────────────────────────────────┐
   │ MethodCandidates → SkillMaintainer → SystemSkills            │
   │                   (合并/更新)        (持久化)                │
   └──────────────────────────────────────────────────────────────┘

4. 注入阶段（实时）
   ┌──────────────────────────────────────────────────────────────┐
   │ UserQuery → SkillInjector → Agent Context                   │
   │            (检索系统技能)   (隐身注入)                       │
   └──────────────────────────────────────────────────────────────┘
```

---

## 3. 数据模型

### 3.1 SystemSkill 数据库模型

```python
# autonome-backend/app/models/system_skill.py

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, JSON
from pgvector.sqlalchemy import Vector

class SystemSkill(SQLModel, table=True):
    """系统级学习技能 - 独立于用户技能"""
    __tablename__ = "system_skills"

    # 基本信息
    id: str = Field(primary_key=True)  # UUID
    method_type: str  # analysis | error_fix | execution_opt
    name: str  # 方法名称（抽象化）
    description: str  # 方法描述（脱敏）

    # 可执行内容
    instructions: str  # 可执行指令模板（Markdown格式）

    # 检索字段
    triggers: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    examples: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    # 版本管理
    version: str = "0.1.0"  # 语义版本

    # 演进追踪
    source_sessions: int = 0  # 来源会话数量
    confidence_score: float = 0.6  # 置信度（基于验证成功率）
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # 向量检索
    combined_embedding: Optional[bytes] = Field(default=None, sa_column=Column(Vector(1536)))

    # 统计信息
    injection_count: int = 0  # 被注入调用次数
    success_rate: float = 0.0  # 注入后成功率

    # 元数据
    metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
```

### 3.2 文件存储结构

```
autonome-backend/app/system_skillbank/
├── Common/
│   ├── analysis_methods/
│   │   ├── differential_expression_analysis/
│   │   │   └── SKILL.md
│   │   └── quality_control_pipeline/
│   │       └── SKILL.md
│   ├── error_fix_strategies/
│   │   ├── memory_overflow_handling/
│   │   │   └── SKILL.md
│   │   └── parameter_validation/
│   │       └── SKILL.md
│   └── execution_optimizations/
│       ├── parallel_processing_config/
│       │   └── SKILL.md
│       └── resource_cleanup_pattern/
│           └── SKILL.md
├── vectors/
│   ├── openai-embedding.meta.json
│   ├── openai-embedding.ids.txt
│   └── openai-embedding.vecs.f32
├── index/
│   ├── system-skills-bm25.*
│   └── usage_stats.json
├── pending/
│   ├── session_pool.json      # 待处理会话池
│   └── extracted_candidates/  # 待合并候选
└── champions/
    └── <skill-id>/            # 当前最优版本
```

### 3.3 SKILL.md 格式

```yaml
---
skill_id: "system_deseq2_analysis_method_01"
name: "DESeq2差异表达分析方法论"
method_type: "analysis_methods"
version: "0.2.3"
source_sessions: 47
confidence_score: 0.89
triggers:
  - "差异表达分析"
  - "DESeq2"
  - "count矩阵分析"
tags:
  - "transcriptomics"
  - "differential-expression"
  - "rnaseq"
---

## 1. 目标 (Goal)

执行标准的DESeq2差异表达分析流程，输出差异基因列表。

## 2. 约束与风格 (Constraints & Style)

### 必须遵守
- 使用DESeq2 R包进行标准化
- 输出必须包含: log2FoldChange, pvalue, padj
- FDR阈值默认0.05

### 禁止操作
- 禁止跳过质量控制步骤
- 禁止忽略多重检验校正

## 3. 工作流程 (Workflow)

1. 数据加载与预处理
   - 检查: count矩阵格式正确性
   - 失败回退: 提示用户检查输入格式

2. DESeq2对象创建
   - 检查: 分组信息与样本匹配

3. 差异分析
   - 输出: results表格

4. 结果过滤与可视化
   - 输出: MA图、火山图、热图
```

---

## 4. 核心组件设计

### 4.1 Method Extractor（方法提取器）

**文件**: `autonome-backend/app/services/system_learning/method_extractor.py`

**职责**: 从成功会话中提取抽象化方法

```python
class MethodExtractor:
    """从对话中提取抽象化方法"""

    EXTRACTION_PROMPT = """
    从以下Agent对话中提取可复用的方法论。

    【隐私规则 - 必须遵守】
    - 禁止提取用户数据内容（基因序列、样本名、具体数值、项目名称）
    - 禁止提取项目路径或文件名
    - 禁止提取组织/团队/个人信息
    - 仅提取：分析策略、参数推荐模式、错误处理逻辑

    【提取要求】
    1. method_type: analysis | error_fix | execution_opt
    2. name: 抽象化名称（如"差异表达分析策略"而非"小鼠肝脏RNA-seq分析"）
    3. triggers: 触发关键词（如"DESeq2"、"差异分析"、"count矩阵"）
    4. instructions: 可执行指令模板（参数用占位符 {{param_type}}）
    5. examples: 抽象输入输出模式（具体值用 {{value}} 替代）

    【输出格式】
    {
      "skills": [{
        "name": "...",
        "description": "...",
        "prompt": "...",
        "triggers": [...],
        "tags": [...],
        "confidence": 0.0-1.0
      }]
    }
    """

    def extract_from_session(self, session: ChatSession) -> List[MethodCandidate]:
        """
        从单个会话提取方法候选

        流程:
        1. 筛选assistant消息中的策略性内容
        2. LLM提取
        3. 脱敏验证（二次检查）
        4. 返回候选方法列表
        """
        pass

    def validate_privacy(self, candidate: MethodCandidate) -> bool:
        """
        验证候选方法是否完全脱敏

        检查项:
        - 无具体数值（检查数字模式）
        - 无文件路径（检查路径模式）
        - 无项目名称（检查命名模式）
        - 无组织/团队名称
        """
        pass
```

### 4.2 Skill Maintainer（技能维护器）

**文件**: `autonome-backend/app/services/system_learning/skill_maintainer.py`

**职责**: 合并更新 + 版本管理

```python
class SkillMaintainer:
    """合并更新 + 版本管理"""

    def merge_or_create(self, candidate: MethodCandidate) -> SystemSkill:
        """
        合并或创建系统技能

        流程:
        1. 向量检索相似技能（threshold=0.85）
        2. 若存在相似：
           - LLM判断是否合并（参考AutoSkill的_should_merge）
           - 合并后版本递增（patch: 0.1.0 → 0.1.1）
           - 更新confidence_score
        3. 若不存在：
           - 创建新技能（v0.1.0）
           - 加入待验证队列
        """
        pass

    def merge_skills(self, existing: SystemSkill, candidate: MethodCandidate) -> SystemSkill:
        """
        合并两个技能

        策略:
        - instructions: 保留更详细/结构化的版本
        - triggers/tags: 取并集去重
        - version: patch版本+1
        - source_sessions: 累加
        """
        pass

    def validate_skill(self, skill: SystemSkill) -> bool:
        """
        验证技能有效性

        检查项:
        1. 用历史会话模拟验证
        2. 检查脱敏完整性
        3. 检查指令可执行性
        """
        pass
```

### 4.3 Skill Injector（技能注入器）

**文件**: `autonome-backend/app/services/system_learning/skill_injector.py`

**职责**: Agent调用时透明注入系统技能

```python
class SkillInjector:
    """Agent调用时透明注入系统技能"""

    def inject_for_query(self, query: str, context: Dict) -> List[str]:
        """
        为查询注入相关系统技能

        流程:
        1. 向量+BM25混合检索
        2. 返回top-3系统技能的instructions
        3. 注入到Agent上下文（不显示给用户）

        返回:
        - List[str]: 技能指令列表，注入到system prompt
        """
        pass

    def hybrid_search(self, query: str, limit: int = 5) -> List[SystemSkill]:
        """
        混合检索

        策略:
        - pgvector语义相似度: 权重0.7
        - BM25关键词匹配: 权重0.3
        - 加权排序返回top-k
        """
        pass
```

### 4.4 Batch Scheduler（批量调度器）

**文件**: `autonome-backend/app/services/system_learning/batch_scheduler.py`

**职责**: Celery Beat定时任务

```python
from celery import shared_task
from celery.schedules import crontab

class SystemLearningScheduler:
    """Celery Beat定时任务"""

    @shared_task
    def run_learning_cycle():
        """
        学习周期（每小时执行）

        流程:
        1. 从SessionPool筛选成功会话（confidence>0.8）
        2. 批量提取方法候选（并行处理）
        3. 合并更新现有技能
        4. 更新向量索引
        5. 清理过期会话池
        """
        pass

    @shared_task
    def rebuild_vector_index():
        """
        重建向量索引（每天执行）

        流程:
        1. 重新计算所有技能的embedding
        2. 更新pgvector索引
        3. 重建BM25索引
        """
        pass

# Celery Beat 配置
CELERYBEAT_SCHEDULE = {
    'system-learning-hourly': {
        'task': 'app.services.system_learning.batch_scheduler.run_learning_cycle',
        'schedule': crontab(minute=0),  # 每小时整点
    },
    'system-learning-daily-index': {
        'task': 'app.services.system_learning.batch_scheduler.rebuild_vector_index',
        'schedule': crontab(hour=3, minute=0),  # 每天凌晨3点
    },
}
```

### 4.5 Session Pool（会话池）

**文件**: `autonome-backend/app/services/system_learning/session_pool.py`

**职责**: 管理待处理会话

```python
class SessionPool:
    """管理待处理会话"""

    def add_session(self, session_id: str, confidence: float, metadata: Dict):
        """
        添加会话到池中

        条件:
        - confidence > 0.8
        - 会话长度 >= 3轮
        - 包含assistant策略输出
        """
        pass

    def get_pending_sessions(self, limit: int = 100) -> List[str]:
        """获取待处理会话ID列表"""
        pass

    def mark_processed(self, session_id: str):
        """标记会话已处理"""
        pass

    def cleanup_expired(self, days: int = 7):
        """清理过期未处理会话"""
        pass
```

---

## 5. Agent集成点

### 5.1 bot.py 集成

```python
# autonome-backend/app/agent/bot.py

from app.services.system_learning.skill_injector import SkillInjector

class AutonomeBot:
    def __init__(self):
        # ... 现有初始化 ...
        self.skill_injector = SkillInjector()  # 新增

    async def process_query(self, query: str, context: Dict):
        """
        处理用户查询（集成系统技能注入）
        """
        # 步骤1: 注入系统技能（隐身，用户无感知）
        system_skills = self.skill_injector.inject_for_query(query, context)

        # 步骤2: 构建增强上下文
        enhanced_system_prompt = self._build_system_prompt()
        if system_skills:
            enhanced_system_prompt += "\n\n【系统学习技能】\n"
            enhanced_system_prompt += "\n\n".join(system_skills)

        # 步骤3: 继续现有Agent逻辑
        # ... 现有代码 ...
```

### 5.2 SuccessEvaluator 集成

```python
# autonome-backend/app/services/success_evaluator.py

from app.services.system_learning.session_pool import SessionPool

class SuccessEvaluator:
    def __init__(self):
        # ... 现有初始化 ...
        self.session_pool = SessionPool()  # 新增

    async def evaluate_session(self, session: ChatSession) -> Dict:
        """
        评估会话质量（现有逻辑）
        """
        result = await self._evaluate_session_internal(session)

        # 新增: 成功会话加入SessionPool
        if result.get("confidence", 0) > 0.8:
            self.session_pool.add_session(
                session_id=session.id,
                confidence=result["confidence"],
                metadata={
                    "user_id": session.user_id,
                    "project_id": session.project_id,
                    "evaluated_at": datetime.utcnow().isoformat()
                }
            )

        return result
```

---

## 6. API设计（可选）

虽然是隐身系统，但提供管理API用于：
- 查看学习统计
- 手动触发学习
- 管理系统技能

```python
# autonome-backend/app/api/routes/system_learning.py

from fastapi import APIRouter

router = APIRouter(prefix="/system-learning", tags=["System Learning"])

@router.get("/stats")
async def get_learning_stats():
    """
    获取学习统计

    返回:
    - total_skills: 系统技能总数
    - by_type: 各类型技能数量
    - recent_updates: 最近更新
    - top_skills: 使用最多的技能
    """
    pass

@router.post("/trigger")
async def trigger_learning():
    """
    手动触发学习周期

    返回:
    - processed_sessions: 处理会话数
    - extracted_skills: 提取技能数
    - updated_skills: 更新技能数
    """
    pass

@router.get("/skills")
async def list_system_skills(method_type: str = None):
    """列出系统技能（只读）"""
    pass

@router.get("/skills/{skill_id}")
async def get_system_skill(skill_id: str):
    """获取单个系统技能详情"""
    pass

@router.delete("/skills/{skill_id}")
async def delete_system_skill(skill_id: str):
    """删除低质量系统技能"""
    pass
```

---

## 7. 隐私保护机制

### 7.1 脱敏规则

```python
PRIVACY_RULES = {
    "redact_patterns": [
        # 项目/文件路径
        (r'/[\w\-./]+', '<PATH>'),

        # 具体数值
        (r'\b\d+\.?\d*\b', '<NUMBER>'),

        # 基因序列标识
        (r'(ENSG|ENST|ENSP)\d+', '<GENE_ID>'),

        # 样本名
        (r'sample[_\-]?\d+', '<SAMPLE>'),

        # 组织/团队名
        (r'(lab|team|group|project|org)[\w\-]+', '<ORG>'),

        # 日期
        (r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', '<DATE>'),

        # URL
        (r'https?://[^\s]+', '<URL>'),
    ],

    "forbidden_keywords": [
        "用户名", "密码", "token", "api_key",
        "项目名称", "组织名称", "团队名称"
    ]
}
```

### 7.2 二次验证

```python
def validate_privacy(content: str) -> Tuple[bool, str]:
    """
    二次验证脱敏完整性

    返回:
    - (is_valid, reason)
    """
    # 检查是否包含敏感模式
    for pattern, _ in PRIVACY_RULES["redact_patterns"]:
        if re.search(pattern, content):
            return False, f"Contains sensitive pattern: {pattern}"

    # 检查是否包含禁止关键词
    for keyword in PRIVACY_RULES["forbidden_keywords"]:
        if keyword in content.lower():
            return False, f"Contains forbidden keyword: {keyword}"

    return True, "OK"
```

---

## 8. 监控与指标

### 8.1 关键指标

| 指标 | 描述 | 阈值 |
|------|------|------|
| `learning_cycle_duration` | 学习周期耗时 | < 5分钟 |
| `extraction_success_rate` | 提取成功率 | > 70% |
| `privacy_validation_rate` | 脱敏验证通过率 | > 95% |
| `skill_merge_rate` | 合并率 | 30-50% |
| `injection_hit_rate` | 注入命中率 | > 60% |
| `injection_success_rate` | 注入后成功率 | > 75% |

### 8.2 日志格式

```python
# 学习周期日志
{
    "event": "learning_cycle_complete",
    "timestamp": "2026-04-07T10:00:00Z",
    "processed_sessions": 150,
    "extracted_candidates": 23,
    "merged_skills": 8,
    "new_skills": 3,
    "duration_seconds": 180
}

# 技能注入日志
{
    "event": "skill_injected",
    "skill_id": "system_deseq2_analysis_method_01",
    "query": "帮我做差异表达分析",
    "similarity_score": 0.89,
    "injection_rank": 1
}
```

---

## 9. 实施计划

### 9.1 阶段划分

**Phase 1: 基础设施（第1-2周）**
- 数据库模型（SystemSkill表）
- 文件存储结构（system_skillbank/）
- 向量索引基础设施

**Phase 2: 核心组件（第3-4周）**
- MethodExtractor（LLM提取 + 脱敏）
- SkillMaintainer（合并 + 版本管理）
- SkillInjector（检索 + 注入）

**Phase 3: 调度与集成（第5周）**
- BatchScheduler（Celery任务）
- SessionPool（会话池管理）
- Agent集成（bot.py修改）
- SuccessEvaluator集成

**Phase 4: 监控与优化（第6周）**
- 监控指标
- 日志系统
- 性能优化
- 文档完善

### 9.2 文件清单

| 文件 | 类型 | 描述 |
|------|------|------|
| `app/models/system_skill.py` | 数据模型 | SystemSkill表定义 |
| `app/services/system_learning/__init__.py` | 模块入口 | 导出公共接口 |
| `app/services/system_learning/method_extractor.py` | 核心服务 | 方法提取器 |
| `app/services/system_learning/skill_maintainer.py` | 核心服务 | 技能维护器 |
| `app/services/system_learning/skill_injector.py` | 核心服务 | 技能注入器 |
| `app/services/system_learning/batch_scheduler.py` | 调度服务 | 定时任务 |
| `app/services/system_learning/session_pool.py` | 辅助服务 | 会话池管理 |
| `app/services/system_learning/vector_index.py` | 辅助服务 | 向量索引 |
| `app/services/system_learning/privacy_validator.py` | 辅助服务 | 隐私验证 |
| `app/api/routes/system_learning.py` | API路由 | 管理接口 |
| `app/agent/bot.py` | 修改 | 集成注入逻辑 |
| `app/services/success_evaluator.py` | 修改 | 集成SessionPool |
| `migrations/versions/xxx_add_system_skills.py` | 数据库迁移 | 创建表 |

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 隐私泄露 | 高 | 多层脱敏验证 + 人工抽检 |
| 学习质量低 | 中 | 置信度阈值 + 成功会话筛选 |
| 注入干扰Agent | 中 | 相似度阈值 + 限制注入数量(<=3) |
| 资源消耗大 | 中 | 定时批量处理 + 向量索引优化 |
| 技能冲突 | 低 | 优先级系统 + 版本管理 |

---

## 11. 参考资源

- AutoSkill源码: `AutoSkill-main/autoskill/`
- 关键文件:
  - `models.py` - 数据模型参考
  - `management/extraction.py` - 提取逻辑参考
  - `management/maintenance.py` - 维护逻辑参考
  - `client.py` - SDK接口参考