"""
Claude 容器池管理器

管理 Docker 沙箱容器池的生命周期:
- 预热池 (pre-warm): 启动时创建指定数量的空闲容器
- 动态分配: 按需从池中分配容器给用户会话
- 空闲回收: 长时间未使用的容器自动销毁以节省资源
- 并发控制: 每用户最多 N 个并发容器

容器分配策略:
- 优先分配预热池中的闲置容器
- 池不足时动态创建新容器
- 容器使用完毕后标记为 idle (保留一段时间)
"""

import os
import time
import asyncio
import subprocess
from typing import Optional, Dict, List
from datetime import datetime, timezone
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.core.database import engine
from app.core.logger import log
from app.models.claude import ClaudeContainer


# ==========================================
# 配置常量
# ==========================================

# 预热池大小 (启动时创建的容器数)
POOL_MIN_SIZE = int(os.environ.get("CLAUDE_POOL_MIN", "1"))
# 最大容器数 (防止资源耗尽)
POOL_MAX_SIZE = int(os.environ.get("CLAUDE_POOL_MAX", "5"))
# 每用户最大并发容器数
USER_MAX_CONCURRENT = int(os.environ.get("CLAUDE_USER_MAX_CONCURRENT", "3"))
# 空闲容器超时回收 (秒, 默认 30 分钟)
IDLE_TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_IDLE_TIMEOUT", "1800"))
# 容器回收检查间隔 (秒)
RECLAIM_INTERVAL_SECONDS = int(os.environ.get("CLAUDE_RECLAIM_INTERVAL", "300"))

# Claude 沙箱 Docker 镜像
CLAUDE_SANDBOX_IMAGE = os.environ.get(
    "CLAUDE_SANDBOX_IMAGE", "autonome-claude-sandbox:latest"
)

# Redis 地址 (容器内使用的地址)
CLAUDE_REDIS_URL = os.environ.get("CLAUDE_REDIS_URL", "redis://claude-redis:6380/0")


@dataclass
class PoolStats:
    """容器池状态统计"""
    total: int = 0
    idle: int = 0
    busy: int = 0
    idle_timeout_count: int = 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "idle": self.idle,
            "busy": self.busy,
            "idle_timeout_count": self.idle_timeout_count,
        }


class ClaudeContainerPool:
    """Claude 沙箱容器池管理器"""

    def __init__(self):
        self._reclaim_task: Optional[asyncio.Task] = None

    # ==========================================
    # 容器生命周期管理
    # ==========================================

    def _create_container(self, session_id: str, user_id: int) -> Optional[str]:
        """
        通过 docker CLI 创建 Claude 沙箱容器

        Args:
            session_id: 关联的 Claude Session ID
            user_id: 用户 ID

        Returns:
            容器 ID, 失败返回 None
        """
        try:
            result = subprocess.run(
                [
                    "docker", "run", "-d",
                    "--name", f"claude-sandbox-{session_id[:8]}",
                    "--network", "autonome_claude_net",
                    "--memory", "2g",
                    "--memory-swap", "4g",
                    "--cpus", "2",
                    "-e", f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
                    "-e", f"CLAUDE_SESSION_ID={session_id}",
                    "-e", f"REDIS_URL={CLAUDE_REDIS_URL}",
                    "-e", f"USER_ID={user_id}",
                    "-e", f"CLAUDE_MODEL={os.environ.get('CLAUDE_MODEL', '')}",
                    "-v", f"claude_workspace_{session_id}:/workspace",
                    CLAUDE_SANDBOX_IMAGE,
                    "python3", "/app/app/sandbox/agent_service/main.py",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                log.error(f"创建容器失败: {result.stderr}")
                return None

            container_id = result.stdout.strip()
            log.info(f"容器已创建: {container_id[:12]} for session {session_id}")
            return container_id

        except subprocess.TimeoutExpired:
            log.error(f"创建容器超时: session {session_id}")
            return None
        except Exception as e:
            log.error(f"创建容器异常: {e}")
            return None

    def _remove_container(self, container_id: str) -> bool:
        """销毁指定容器"""
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_id],
                capture_output=True,
                timeout=10,
            )
            log.info(f"容器已销毁: {container_id[:12]}")
            return True
        except Exception as e:
            log.error(f"销毁容器失败 {container_id[:12]}: {e}")
            return False

    # ==========================================
    # 分配与回收
    # ==========================================

    async def allocate(
        self,
        session_id: str,
        user_id: int,
    ) -> Optional[str]:
        """
        为会话分配一个容器

        分配策略:
        1. 检查用户是否已达并发上限
        2. 尝试从池中找空闲容器
        3. 池中无可用容器时动态创建
        4. 持久化分配记录到数据库
        """
        with Session(engine) as db:
            # 检查用户并发上限
            user_busy_count = len(db.exec(
                select(ClaudeContainer).where(
                    ClaudeContainer.user_id == user_id,
                    ClaudeContainer.status == "busy",
                )
            ).all())

            if user_busy_count >= USER_MAX_CONCURRENT:
                log.warning(f"用户 {user_id} 已达并发上限 {USER_MAX_CONCURRENT}")
                return None

            # 尝试从池中获取空闲容器
            idle_container = db.exec(
                select(ClaudeContainer)
                .where(ClaudeContainer.status == "idle")
                .order_by(ClaudeContainer.last_used_at.desc())
                .limit(1)
            ).first()

            if idle_container:
                # 复用已有容器
                idle_container.status = "busy"
                idle_container.user_id = user_id
                idle_container.session_id = session_id
                idle_container.last_used_at = datetime.now(timezone.utc)

                # 更新容器内 agent_service 的 session ID 环境变量
                # 预热容器的 CLAUDE_SESSION_ID 为 "prewarm"，需要更新为真实 session_id
                try:
                    subprocess.run(
                        ["docker", "exec", idle_container.container_id,
                         "sh", "-c",
                         f"export CLAUDE_SESSION_ID={session_id}"],
                        capture_output=True, timeout=5,
                    )
                except Exception:
                    pass  # 非致命，agent_service 可通过 Redis 消息获取 session_id

                db.add(idle_container)
                db.commit()
                log.info(f"分配复用容器: {idle_container.container_id[:12]} → session {session_id}")
                return idle_container.container_id

            # 检查总容器数是否已达上限
            total_count = len(db.exec(select(ClaudeContainer)).all())
            if total_count >= POOL_MAX_SIZE:
                log.warning(f"容器池已达上限 {POOL_MAX_SIZE}")
                return None

            # 创建新容器
            container_id = self._create_container(session_id, user_id)
            if not container_id:
                return None

            # 持久化到数据库
            container_rec = ClaudeContainer(
                container_id=container_id,
                status="busy",
                user_id=user_id,
                session_id=session_id,
            )
            db.add(container_rec)
            db.commit()

            return container_id

    async def release(self, session_id: str) -> None:
        """
        释放会话占用的容器 (标记为 idle)

        Args:
            session_id: 要释放的会话 ID
        """
        with Session(engine) as db:
            containers = db.exec(
                select(ClaudeContainer).where(
                    ClaudeContainer.session_id == session_id,
                    ClaudeContainer.status == "busy",
                )
            ).all()

            for container in containers:
                container.status = "idle"
                container.user_id = None
                container.session_id = None
                container.last_used_at = datetime.now(timezone.utc)
                db.add(container)
                log.info(f"容器已释放: {container.container_id[:12]} ← session {session_id}")
            db.commit()

    # ==========================================
    # 预热池管理
    # ==========================================

    async def pre_warm(self) -> int:
        """
        预热容器池 (启动时调用)

        创建 POOL_MIN_SIZE 个空闲容器并注册到数据库。
        返回成功创建的容器数。
        """
        with Session(engine) as db:
            # 统计当前空闲容器数
            idle_count = len(db.exec(
                select(ClaudeContainer).where(ClaudeContainer.status == "idle")
            ).all())

            needed = max(0, POOL_MIN_SIZE - idle_count)
            created = 0

            for i in range(needed):
                container_id = self._create_container("prewarm", 0)
                if container_id:
                    container_rec = ClaudeContainer(
                        container_id=container_id,
                        status="idle",
                    )
                    db.add(container_rec)
                    created += 1

            if created > 0:
                db.commit()
                log.info(f"预热完成: 创建了 {created} 个容器")

            return created

    async def reclaim_idle(self) -> int:
        """
        回收超时空闲容器

        销毁超过 IDLE_TIMEOUT_SECONDS 未使用的空闲容器,
        保持池中至少有 POOL_MIN_SIZE 个容器可用。

        返回回收的容器数。
        """
        with Session(engine) as db:
            now = datetime.now(timezone.utc)
            idle_containers = db.exec(
                select(ClaudeContainer)
                .where(ClaudeContainer.status == "idle")
                .order_by(ClaudeContainer.last_used_at)
            ).all()

            idle_count = len(idle_containers)
            # 保留 POOL_MIN_SIZE 个空闲容器, 回收其余超时的
            reclaim_count = 0

            for container in idle_containers:
                if idle_count - reclaim_count <= POOL_MIN_SIZE:
                    break

                age = (now - container.last_used_at).total_seconds()
                if age > IDLE_TIMEOUT_SECONDS:
                    self._remove_container(container.container_id)
                    db.delete(container)
                    reclaim_count += 1

            if reclaim_count > 0:
                db.commit()
                log.info(f"空闲回收: 销毁了 {reclaim_count} 个容器")

            return reclaim_count

    # ==========================================
    # 后台回收任务
    # ==========================================

    async def start_reclaim_loop(self) -> None:
        """启动后台回收循环 (asyncio task)"""
        log.info(f"容器回收循环已启动 (间隔: {RECLAIM_INTERVAL_SECONDS}s)")

        while True:
            try:
                await asyncio.sleep(RECLAIM_INTERVAL_SECONDS)
                await self.reclaim_idle()
            except asyncio.CancelledError:
                log.info("容器回收循环已取消")
                break
            except Exception as e:
                log.error(f"容器回收异常: {e}")

    def start(self) -> None:
        """启动后台回收任务"""
        try:
            loop = asyncio.get_event_loop()
            self._reclaim_task = loop.create_task(self.start_reclaim_loop())
        except RuntimeError:
            # 无事件循环 (非异步上下文), 跳过后台任务
            pass

    def stop(self) -> None:
        """停止后台任务"""
        if self._reclaim_task:
            self._reclaim_task.cancel()

    # ==========================================
    # 统计信息
    # ==========================================

    async def get_stats(self) -> PoolStats:
        """获取容器池统计"""
        with Session(engine) as db:
            all_containers = db.exec(select(ClaudeContainer)).all()

            stats = PoolStats()
            stats.total = len(all_containers)

            now = datetime.now(timezone.utc)
            for c in all_containers:
                if c.status == "idle":
                    stats.idle += 1
                    age = (now - c.last_used_at).total_seconds()
                    if age > IDLE_TIMEOUT_SECONDS:
                        stats.idle_timeout_count += 1
                elif c.status == "busy":
                    stats.busy += 1

            return stats


# 全局单例
_container_pool: Optional[ClaudeContainerPool] = None


def get_container_pool() -> ClaudeContainerPool:
    """获取容器池单例"""
    global _container_pool
    if _container_pool is None:
        _container_pool = ClaudeContainerPool()
    return _container_pool
