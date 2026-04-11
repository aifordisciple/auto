"""
自动技能草稿服务

实现"零确认转化"功能：
1. 从成功的会话中自动提取代码块和策略
2. 后台异步调用 Crafter Agent 生成技能草稿
3. 保存草稿到 pending_skill_drafts 表
4. 用户可在技能工厂中查看、编辑、一键发布
"""

import os
import json
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from sqlmodel import Session, select
from langchain_openai import ChatOpenAI

from app.models.domain import (
    ChatMessage, RoleEnum, SystemConfig, User,
    PendingSkillDraft, PendingSkillDraftCreate,
    DraftStatus, TriggerSource
)
from app.core.logger import log
from app.services.success_evaluator import SuccessEvaluator


class AutoSkillDraftService:
    """
    自动技能草稿服务

    核心功能：
    - 智能触发判断：基于代码复杂度、执行时长、成功信号
    - 后台异步生成：不阻塞用户操作
    - 草稿管理：查看、编辑、发布、忽略
    """

    def __init__(self, db: Session):
        self.db = db
        self.evaluator = SuccessEvaluator(db)
        self._init_llm()

    def _init_llm(self):
        """初始化 LLM 配置"""
        config = self.db.get(SystemConfig, 1)
        if not config:
            raise ValueError("系统配置未找到")

        self.api_key = config.openai_api_key if config and config.openai_api_key else "ollama-local"
        self.base_url = config.openai_base_url if config and config.openai_base_url else "http://localhost:11434/v1"
        self.model_name = config.default_model if config and config.default_model else "gpt-4o-mini"

        # 判断是否是本地模型
        is_local_model = self.base_url and (
            "host.docker.internal" in self.base_url or
            "ollama" in self.base_url or
            "localhost" in self.base_url
        )

        # 对于本地模型，使用空字符串作为API key
        if is_local_model:
            self.api_key = self.api_key if self.api_key is not None else ""
        else:
            env_api_key = os.getenv("OPENAI_API_KEY")
            self.api_key = self.api_key if self.api_key and self.api_key != "ollama-local" else env_api_key

    async def check_and_create_draft(
        self,
        session_id: str,
        user_id: int,
        project_id: Optional[str] = None,
        execution_time: Optional[float] = None,
        has_output_files: bool = False
    ) -> Optional[PendingSkillDraft]:
        """
        检查是否满足触发条件，如果满足则自动创建技能草稿

        这是核心入口方法，在聊天流结束后调用

        Args:
            session_id: 会话ID
            user_id: 用户ID
            project_id: 项目ID
            execution_time: 执行时长(秒)
            has_output_files: 是否有输出文件

        Returns:
            创建的草稿实例，不满足条件返回 None
        """
        log.info(f"🔍 [AutoSkillDraft] 检查会话 {session_id} 是否触发技能草稿生成...")

        # 1. 判断是否触发
        trigger_result = self.evaluator.should_trigger_skill_draft(
            session_id=session_id,
            execution_time=execution_time,
            has_output_files=has_output_files
        )

        if not trigger_result["should_trigger"]:
            log.info(f"⏭️ [AutoSkillDraft] 会话 {session_id} 不满足触发条件，跳过")
            return None

        # 2. 检查是否已有草稿（避免重复创建）
        existing = self.db.exec(
            select(PendingSkillDraft).where(
                PendingSkillDraft.session_id == session_id,
                PendingSkillDraft.status == DraftStatus.PENDING
            )
        ).first()

        if existing:
            log.info(f"⏭️ [AutoSkillDraft] 会话 {session_id} 已有待处理草稿，跳过")
            return existing

        # 3. 构建原始素材
        raw_material = self._build_raw_material(
            session_id=session_id,
            code_blocks=trigger_result["code_blocks"],
            strategies=trigger_result["strategies"]
        )

        # 4. 检测执行器类型
        executor_type = self.evaluator.detect_executor_type(trigger_result["code_blocks"])

        # 5. 调用 Crafter Agent 生成草稿
        try:
            crafted_result = await self._craft_skill_draft(raw_material, executor_type)

            if not crafted_result:
                log.warning(f"⚠️ [AutoSkillDraft] 会话 {session_id} 技能锻造失败")
                return None

            # 6. 创建草稿记录
            draft = PendingSkillDraft(
                user_id=user_id,
                session_id=session_id,
                project_id=project_id,
                trigger_source=trigger_result["trigger_source"],
                trigger_score=trigger_result["trigger_score"],
                trigger_reason=trigger_result["trigger_reason"],
                raw_material=raw_material,
                code_blocks=trigger_result["code_blocks"],
                strategies=trigger_result["strategies"],
                draft_name=crafted_result.get("name", "未命名技能"),
                draft_description=crafted_result.get("description", ""),
                executor_type=executor_type,
                parameters_schema=crafted_result.get("parameters_schema", {}),
                expert_knowledge=crafted_result.get("expert_knowledge", ""),
                script_code=crafted_result.get("script_code", ""),
                dependencies=crafted_result.get("dependencies", []),
                status=DraftStatus.PENDING
            )

            self.db.add(draft)
            self.db.commit()
            self.db.refresh(draft)

            log.info(f"✅ [AutoSkillDraft] 成功创建技能草稿 ID={draft.id}, 名称={draft.draft_name}")

            return draft

        except Exception as e:
            log.error(f"❌ [AutoSkillDraft] 创建草稿失败: {e}")
            self.db.rollback()
            return None

    def _build_raw_material(
        self,
        session_id: str,
        code_blocks: List[Dict],
        strategies: List[Dict]
    ) -> str:
        """
        构建用于锻造的原始素材
        """
        material_parts = []

        # 获取用户消息
        messages = self.db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        ).all()

        user_messages = [m for m in messages if m.role == RoleEnum.user]

        # 添加用户需求描述
        if user_messages:
            material_parts.append("【用户需求】")
            for msg in user_messages[-3:]:  # 最近3条用户消息
                if msg.content:
                    material_parts.append(f"- {msg.content[:500]}")
            material_parts.append("")

        # 添加代码
        if code_blocks:
            material_parts.append("【分析代码】")
            for i, block in enumerate(code_blocks[-3:], 1):  # 最近3个代码块
                material_parts.append(f"### 代码片段 {i} ({block['language']})")
                material_parts.append(block["code"])
                material_parts.append("")

        # 添加策略信息
        if strategies:
            material_parts.append("【执行策略】")
            for strategy in strategies[-2:]:  # 最近2个策略
                material_parts.append(f"- 标题: {strategy.get('title', '未知')}")
                material_parts.append(f"- 描述: {strategy.get('description', '未知')}")
                if strategy.get('parameters'):
                    material_parts.append(f"- 参数: {json.dumps(strategy['parameters'], ensure_ascii=False)}")
                material_parts.append("")

        return "\n".join(material_parts)

    async def _craft_skill_draft(
        self,
        raw_material: str,
        executor_type: str
    ) -> Optional[Dict]:
        """
        调用 Crafter Agent 生成技能草稿
        """
        try:
            from app.agent.crafter import craft_skill_from_material

            crafted_result = await craft_skill_from_material(
                raw_material=raw_material,
                api_key=self.api_key,
                base_url=self.base_url,
                model_name=self.model_name,
                executor_type=executor_type
            )

            return crafted_result

        except Exception as e:
            log.error(f"Crafter Agent 调用失败: {e}")
            return None

    # ==========================================
    # 草稿管理方法
    # ==========================================

    def get_user_drafts(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[PendingSkillDraft]:
        """
        获取用户的技能草稿列表
        """
        query = select(PendingSkillDraft).where(
            PendingSkillDraft.user_id == user_id
        ).order_by(PendingSkillDraft.created_at.desc())

        if status:
            query = query.where(PendingSkillDraft.status == status)

        query = query.offset(offset).limit(limit)

        return self.db.exec(query).all()

    def get_draft(self, draft_id: int, user_id: int) -> Optional[PendingSkillDraft]:
        """
        获取单个草稿详情
        """
        return self.db.exec(
            select(PendingSkillDraft).where(
                PendingSkillDraft.id == draft_id,
                PendingSkillDraft.user_id == user_id
            )
        ).first()

    def update_draft(
        self,
        draft_id: int,
        user_id: int,
        **updates
    ) -> Optional[PendingSkillDraft]:
        """
        更新草稿内容
        """
        draft = self.get_draft(draft_id, user_id)
        if not draft:
            return None

        for key, value in updates.items():
            if hasattr(draft, key):
                setattr(draft, key, value)

        draft.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(draft)

        return draft

    def dismiss_draft(self, draft_id: int, user_id: int) -> bool:
        """
        忽略草稿
        """
        draft = self.get_draft(draft_id, user_id)
        if not draft:
            return False

        draft.status = DraftStatus.DISMISSED
        draft.updated_at = datetime.utcnow()
        self.db.commit()

        log.info(f"🗑️ [AutoSkillDraft] 草稿 {draft_id} 已忽略")
        return True

    async def publish_draft(
        self,
        draft_id: int,
        user_id: int,
        skill_name: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """
        发布草稿为正式技能

        Args:
            draft_id: 草稿ID
            user_id: 用户ID
            skill_name: 可选的自定义技能名称
            category: 可选的分类
            tags: 可选的标签列表

        Returns:
            发布结果，包含 skill_id 等信息
        """
        from app.models.domain import SkillAsset, SkillStatus, generate_skill_id

        draft = self.get_draft(draft_id, user_id)
        if not draft:
            return None

        if draft.status == DraftStatus.PUBLISHED:
            return {"error": "草稿已发布", "skill_id": draft.published_skill_id}

        try:
            # 生成技能ID
            skill_id = generate_skill_id()

            # 使用自定义名称（如果有）
            final_name = skill_name or draft.draft_name

            # 创建正式技能
            skill = SkillAsset(
                skill_id=skill_id,
                name=final_name,
                description=draft.draft_description,
                version="1.0.0",
                executor_type=draft.executor_type,
                parameters_schema=draft.parameters_schema,
                expert_knowledge=draft.expert_knowledge,
                script_code=draft.script_code,
                owner_id=user_id,
                status=SkillStatus.DRAFT,  # 初始为草稿状态，用户可以进一步编辑
                category=category or "general",
                tags=tags or []
            )

            self.db.add(skill)

            # 更新草稿状态
            draft.status = DraftStatus.PUBLISHED
            draft.published_skill_id = skill_id
            draft.updated_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(skill)

            log.info(f"🚀 [AutoSkillDraft] 草稿 {draft_id} 已发布为技能 {skill_id}")

            return {
                "skill_id": skill_id,
                "name": final_name,
                "status": "DRAFT",
                "message": "技能已创建，可在技能工厂中进一步完善"
            }

        except Exception as e:
            log.error(f"❌ [AutoSkillDraft] 发布草稿失败: {e}")
            self.db.rollback()
            return None

    def get_draft_stats(self, user_id: int) -> Dict:
        """
        获取用户的草稿统计信息
        """
        drafts = self.db.exec(
            select(PendingSkillDraft).where(PendingSkillDraft.user_id == user_id)
        ).all()

        stats = {
            "total": len(drafts),
            "pending": 0,
            "reviewed": 0,
            "published": 0,
            "dismissed": 0,
            "failed": 0
        }

        for draft in drafts:
            if draft.status == DraftStatus.PENDING:
                stats["pending"] += 1
            elif draft.status == DraftStatus.REVIEWED:
                stats["reviewed"] += 1
            elif draft.status == DraftStatus.PUBLISHED:
                stats["published"] += 1
            elif draft.status == DraftStatus.DISMISSED:
                stats["dismissed"] += 1
            elif draft.status == DraftStatus.FAILED:
                stats["failed"] += 1

        return stats


# ==========================================
# 异步任务包装器
# ==========================================

async def async_check_and_create_draft(
    db: Session,
    session_id: str,
    user_id: int,
    project_id: Optional[str] = None,
    execution_time: Optional[float] = None,
    has_output_files: bool = False
) -> Optional[PendingSkillDraft]:
    """
    异步检查并创建技能草稿

    这是一个便捷函数，用于在后台任务中调用
    """
    service = AutoSkillDraftService(db)
    return await service.check_and_create_draft(
        session_id=session_id,
        user_id=user_id,
        project_id=project_id,
        execution_time=execution_time,
        has_output_files=has_output_files
    )