"""
Claude Code CLI Agent

核心 Agent 类，负责：
1. 构建上下文提示词
2. 调用 Claude Code CLI 执行
3. 解析响应，提取策略卡片
4. 会话管理（支持多轮对话连续性）

设计理念：
- 复用现有 claude_executor_service
- 支持 --resume 会话恢复
- SSE 流式输出
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.core.logger import log
from app.models.domain import ClaudeCodeSession, ClaudeCodeSessionStatus
from app.services.claude_executor_service import (
    claude_executor_service,
    ClaudeSession,
    ClaudeExecutionResult
)
from app.agent.response_parser import claude_response_parser, ParsedResponse
from app.agent.prompts import build_full_prompt, build_skill_catalog


# ==========================================
# 常量配置
# ==========================================

# 会话过期时间（小时）
SESSION_EXPIRE_HOURS = 24

# 检查 Claude CLI 是否可用的缓存时间（秒）
CLI_CHECK_CACHE_SECONDS = 60


# ==========================================
# 数据类定义
# ==========================================

@dataclass
class AgentContext:
    """Agent 执行上下文"""
    project_id: str
    project_dir: str
    user_id: int
    session_id: str  # ChatSession ID

    # 上下文信息
    global_file_tree: str = ""
    selected_files: List[str] = field(default_factory=list)
    available_skills: List[Dict[str, Any]] = field(default_factory=list)
    skill_recommendations: List[Dict[str, Any]] = field(default_factory=list)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)

    # 配置
    task_mode: Optional[str] = None
    selected_skill_id: Optional[str] = None


@dataclass
class AgentResponse:
    """Agent 响应结构"""
    text_content: str = ""
    strategy_card: Optional[Dict[str, Any]] = None
    blueprint: Optional[Dict[str, Any]] = None
    battle_report: Optional[Dict[str, Any]] = None
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    session_id: Optional[str] = None  # Claude Code session_id


# ==========================================
# Claude Code Agent 类
# ==========================================

class ClaudeCodeAgent:
    """
    Claude Code CLI Agent

    核心功能：
    1. 构建上下文 prompt
    2. 调用 Claude CLI 执行（支持 --resume）
    3. 解析响应，提取策略卡片
    4. 会话管理（持久化 session_id）
    """

    # CLI 可用性缓存
    _cli_available_cache: Optional[bool] = None
    _cli_check_time: Optional[datetime] = None

    def __init__(self, context: AgentContext, db_session: Optional[Session] = None):
        """
        初始化 Agent

        Args:
            context: Agent 执行上下文
            db_session: 数据库会话（用于会话持久化）
        """
        self.context = context
        self.db_session = db_session

    def build_prompt(self, user_message: str) -> str:
        """
        构建完整的 prompt

        包括：
        - 系统提示词
        - 项目上下文
        - SKILL 目录
        - 历史对话
        - 用户请求
        """
        # 构建 SKILL 推荐文本
        skill_text = ""
        if self.context.skill_recommendations or self.context.available_skills:
            skill_text = build_skill_catalog(
                skills=self.context.available_skills,
                recommendations=self.context.skill_recommendations
            )

        return build_full_prompt(
            user_message=user_message,
            project_dir=self.context.project_dir,
            file_tree=self.context.global_file_tree,
            selected_files=self.context.selected_files,
            skill_recommendations=skill_text,
            conversation_history=self.context.conversation_history,
            task_mode=self.context.task_mode
        )

    async def execute(
        self,
        user_message: str,
        mode: str = "host",
        output_callback: Optional[Callable[[str], None]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Claude Code

        Args:
            user_message: 用户消息
            mode: 执行模式 "host" 或 "container"
            output_callback: 输出回调函数

        Yields:
            SSE 事件字典
        """
        log.info(f"[ClaudeCodeAgent] 开始执行, user_id={self.context.user_id}, project={self.context.project_id}")

        # 构建完整 prompt
        prompt = self.build_prompt(user_message)

        # 获取活跃会话（如果有）
        active_session = await self._get_active_session()

        # 执行
        full_output = ""

        try:
            if active_session:
                # 恢复会话
                log.info(f"[ClaudeCodeAgent] 恢复会话: {active_session.claude_session_id}")
                async for event in self._execute_with_resume(
                    active_session.claude_session_id,
                    prompt,
                    mode,
                    output_callback
                ):
                    if event.get("event") == "raw_output":
                        full_output += event.get("data", "")
                    yield event
            else:
                # 新会话
                log.info(f"[ClaudeCodeAgent] 启动新会话")
                async for event in self._execute_new_session(prompt, mode, output_callback):
                    if event.get("event") == "raw_output":
                        full_output += event.get("data", "")
                    yield event

        except Exception as e:
            log.error(f"[ClaudeCodeAgent] 执行失败: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

        # 解析响应
        parsed = claude_response_parser.parse(full_output)

        # 保存 session_id
        if parsed.session_id:
            await self._save_session(parsed.session_id)

        # 输出策略卡片事件
        if parsed.strategy_card:
            yield {
                "event": "strategy_card",
                "data": json.dumps(parsed.strategy_card, ensure_ascii=False)
            }

        if parsed.blueprint:
            yield {
                "event": "blueprint",
                "data": json.dumps(parsed.blueprint, ensure_ascii=False)
            }

        # 输出完成事件
        yield {
            "event": "done",
            "data": json.dumps({
                "session_id": parsed.session_id,
                "files_created": parsed.files_created,
                "files_modified": parsed.files_modified
            })
        }

    async def _execute_new_session(
        self,
        prompt: str,
        mode: str,
        output_callback: Optional[Callable[[str], None]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行新会话"""
        # 创建 Claude 会话
        claude_session = claude_executor_service.create_session(
            project_id=self.context.project_id,
            user_id=self.context.user_id,
            mode=mode
        )

        # 构建回调，同时收集输出和发送事件
        collected_output = []

        async def combined_callback(line: str):
            collected_output.append(line)
            if output_callback:
                await output_callback(line)

        # 执行
        result = await claude_executor_service.execute(
            session=claude_session,
            prompt=prompt,
            output_callback=combined_callback
        )

        # 输出文本事件
        if result.output:
            # 解析战报
            if result.battle_report:
                assistant_msg = result.battle_report.get("assistant_message", "")
                if assistant_msg:
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "text", "content": assistant_msg}, ensure_ascii=False)
                    }

            yield {
                "event": "raw_output",
                "data": result.output
            }

    async def _execute_with_resume(
        self,
        claude_session_id: str,
        prompt: str,
        mode: str,
        output_callback: Optional[Callable[[str], None]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """使用 --resume 恢复会话执行"""
        # 创建 Claude 会话（用于管理进程）
        claude_session = claude_executor_service.create_session(
            project_id=self.context.project_id,
            user_id=self.context.user_id,
            mode=mode
        )

        # 构建回调，同时收集输出和发送事件
        collected_output = []

        async def combined_callback(line: str):
            collected_output.append(line)
            if output_callback:
                await output_callback(line)

        # 执行，传入 resume_session_id
        result = await claude_executor_service.execute(
            session=claude_session,
            prompt=prompt,
            output_callback=combined_callback,
            resume_session_id=claude_session_id
        )

        # 输出文本事件
        if result.output:
            # 解析战报
            if result.battle_report:
                assistant_msg = result.battle_report.get("assistant_message", "")
                if assistant_msg:
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "text", "content": assistant_msg}, ensure_ascii=False)
                    }

            yield {
                "event": "raw_output",
                "data": result.output
            }

    # ==========================================
    # 会话管理
    # ==========================================

    async def _get_active_session(self) -> Optional[ClaudeCodeSession]:
        """
        获取活跃的 Claude Code 会话

        检查条件：
        1. 同一用户 + 同一项目 + 同一 ChatSession
        2. 状态为 active
        3. 未过期（24小时内）

        Returns:
            活跃会话或 None
        """
        if not self.db_session:
            return None

        try:
            # 使用 exec() 返回的对象调用 first()
            statement = (
                select(ClaudeCodeSession)
                .where(
                    ClaudeCodeSession.user_id == self.context.user_id,
                    ClaudeCodeSession.project_id == self.context.project_id,
                    ClaudeCodeSession.chat_session_id == self.context.session_id,
                    ClaudeCodeSession.status == ClaudeCodeSessionStatus.ACTIVE.value
                )
                .order_by(ClaudeCodeSession.last_message_at.desc())
            )
            session = self.db_session.exec(statement).first()

            if session:
                # 检查是否过期
                age = datetime.utcnow() - session.last_message_at.replace(tzinfo=None)
                if age > timedelta(hours=SESSION_EXPIRE_HOURS):
                    # 标记为过期
                    session.status = ClaudeCodeSessionStatus.EXPIRED.value
                    self.db_session.add(session)
                    self.db_session.commit()
                    log.info(f"[ClaudeCodeAgent] 会话已过期: {session.claude_session_id}")
                    return None

                log.info(f"[ClaudeCodeAgent] 找到活跃会话: {session.claude_session_id}")
                return session

        except Exception as e:
            log.error(f"[ClaudeCodeAgent] 获取活跃会话失败: {e}")

        return None

    async def _save_session(self, claude_session_id: str) -> Optional[ClaudeCodeSession]:
        """
        保存 Claude Code 会话 ID

        Args:
            claude_session_id: Claude Code CLI 返回的 session_id

        Returns:
            创建的会话对象
        """
        if not self.db_session or not claude_session_id:
            return None

        try:
            # 检查是否已存在
            statement = select(ClaudeCodeSession).where(
                ClaudeCodeSession.claude_session_id == claude_session_id
            )
            existing = self.db_session.exec(statement).first()

            if existing:
                # 更新最后消息时间
                existing.last_message_at = datetime.utcnow()
                existing.message_count += 1
                self.db_session.add(existing)
            else:
                # 创建新会话
                new_session = ClaudeCodeSession(
                    user_id=self.context.user_id,
                    project_id=self.context.project_id,
                    chat_session_id=self.context.session_id,
                    claude_session_id=claude_session_id,
                    status=ClaudeCodeSessionStatus.ACTIVE.value,
                    last_message_at=datetime.utcnow(),
                    message_count=1
                )
                self.db_session.add(new_session)

            self.db_session.commit()
            log.info(f"[ClaudeCodeAgent] 保存会话: {claude_session_id}")

        except Exception as e:
            log.error(f"[ClaudeCodeAgent] 保存会话失败: {e}")

        return None

    async def _expire_session(self, session: ClaudeCodeSession):
        """标记会话为过期"""
        if not self.db_session:
            return

        try:
            session.status = ClaudeCodeSessionStatus.EXPIRED.value
            self.db_session.add(session)
            self.db_session.commit()
            log.info(f"[ClaudeCodeAgent] 会话已标记过期: {session.claude_session_id}")
        except Exception as e:
            log.error(f"[ClaudeCodeAgent] 标记会话过期失败: {e}")

    # ==========================================
    # 静态方法：CLI 可用性检查
    # ==========================================

    @classmethod
    async def check_cli_available(cls) -> bool:
        """
        检查 Claude CLI 是否可用（通过 Docker 容器）

        检查条件：
        1. Docker 命令可用
        2. autonome-tool-env 镜像存在

        Returns:
            True 表示可用
        """
        now = datetime.utcnow()

        # 检查缓存
        if cls._cli_available_cache is not None and cls._cli_check_time:
            age = (now - cls._cli_check_time).total_seconds()
            if age < CLI_CHECK_CACHE_SECONDS:
                return cls._cli_available_cache

        # 检查 Docker 是否可用
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "images", "-q", "autonome-tool-env",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10.0)

            # 如果有输出，说明镜像存在
            available = bool(stdout.strip())
            log.info(f"[ClaudeCodeAgent] Docker 镜像检查: autonome-tool-env {'存在' if available else '不存在'}")

        except (FileNotFoundError, asyncio.TimeoutError) as e:
            log.warning(f"[ClaudeCodeAgent] Docker 检查失败: {e}")
            available = False
        except Exception as e:
            log.warning(f"[ClaudeCodeAgent] CLI 检查异常: {e}")
            available = False

        # 更新缓存
        cls._cli_available_cache = available
        cls._cli_check_time = now

        return available


# ==========================================
# 便捷函数
# ==========================================