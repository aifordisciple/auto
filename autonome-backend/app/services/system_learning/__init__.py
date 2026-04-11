"""
系统学习模块 (System Learning Module)

提供系统级自进化学习能力:
- 从成功会话中提取方法论
- 自动脱敏和验证
- 合并更新现有技能
- 隐身注入到 Agent 上下文

架构设计:
    ┌─────────────────────────────────────────────────────────────────┐
    │                      用户对话数据流                              │
    └─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │  SuccessEvaluator → SessionPool (收集成功会话)                  │
    └─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼ (定时批量处理)
    ┌─────────────────────────────────────────────────────────────────┐
    │  MethodExtractor → PrivacyValidator (提取+脱敏)                 │
    └─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │  SkillMaintainer (合并更新) → SystemSkillBank                   │
    └─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼ (Agent 调用时)
    ┌─────────────────────────────────────────────────────────────────┐
    │  SkillInjector (隐身注入) → Agent System Prompt                 │
    └─────────────────────────────────────────────────────────────────┘

核心组件:
    - PrivacyValidator: 隐私验证器，确保提取内容完全脱敏
    - SessionPool: 会话池管理器，收集待处理的成功会话
    - MethodExtractor: 方法提取器，从会话中提取方法论
    - SkillMaintainer: 技能维护器，合并更新现有技能
    - SkillInjector: 技能注入器，隐身注入到 Agent 上下文
    - SystemSkillVectorIndex: 向量索引，支持语义检索

使用方式:
    from app.services.system_learning import get_privacy_validator
    from app.services.system_learning import get_session_pool
    from app.services.system_learning import get_method_extractor
    from app.services.system_learning import get_skill_injector

    # 验证内容隐私
    validator = get_privacy_validator()
    is_valid, errors = validator.validate(content)

    # 添加成功会话
    pool = get_session_pool()
    pool.add_session(session_id, confidence, user_id, project_id)

    # 注入系统技能
    injector = get_skill_injector()
    instructions = injector.inject_for_query(user_query)

注意:
    - 此模块完全隐身，用户不可见
    - 仅学习抽象方法论，不记录用户数据
    - 所有提取内容必须通过隐私验证
"""

# 隐私验证器
from .privacy_validator import (
    PrivacyValidator,
    PrivacyRule,
    PRIVACY_RULES,
    FORBIDDEN_KEYWORDS,
    get_privacy_validator,
    reset_privacy_validator,
)

# 会话池管理器
from .session_pool import (
    SessionPool,
    PendingSession,
    SessionPoolConfig,
    get_session_pool,
    reset_session_pool,
)

# 方法提取器
from .method_extractor import (
    MethodExtractor,
    MethodCandidate,
    get_method_extractor,
    reset_method_extractor,
)

# 技能注入器
from .skill_injector import (
    SkillInjector,
    InjectorConfig,
    get_skill_injector,
    reset_skill_injector,
)

# 其他组件将在后续任务中实现后取消注释
# from .session_pool import SessionPool, get_session_pool
# from .method_extractor import MethodExtractor, get_method_extractor
# from .skill_maintainer import SkillMaintainer, get_skill_maintainer
# from .skill_injector import SkillInjector, get_skill_injector
# from .vector_index import SystemSkillVectorIndex, get_vector_index
# from .batch_scheduler import run_learning_cycle, rebuild_vector_index


__all__ = [
    # 隐私验证器
    'PrivacyValidator',
    'PrivacyRule',
    'PRIVACY_RULES',
    'FORBIDDEN_KEYWORDS',
    'get_privacy_validator',
    'reset_privacy_validator',
    # 会话池管理器
    'SessionPool',
    'PendingSession',
    'SessionPoolConfig',
    'get_session_pool',
    'reset_session_pool',
    # 方法提取器
    'MethodExtractor',
    'MethodCandidate',
    'get_method_extractor',
    'reset_method_extractor',
    # 技能注入器
    'SkillInjector',
    'InjectorConfig',
    'get_skill_injector',
    'reset_skill_injector',
    # 技能维护器（待实现）
    # 'SkillMaintainer',
    # 'get_skill_maintainer',
    # 向量索引（待实现）
    # 'SystemSkillVectorIndex',
    # 'get_vector_index',
    # 定时任务（待实现）
    # 'run_learning_cycle',
    # 'rebuild_vector_index',
]


# 模块版本信息
__version__ = '0.1.0'
__author__ = 'AUTONOME System Learning Team'