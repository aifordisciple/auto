"""
容器预热池服务 - 降低容器启动延迟

核心目标：
- 维护预热容器池，任务到达直接执行
- 节省 3-5s 容器启动时间

架构：
┌─────────────────────────────────────────────────────────────────┐
│                    容器预热池架构                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [预热容器池]                                                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │Python #1│ │Python #2│ │  R #1   │ │  R #2   │ │通用容器 │   │
│  │ running │ │ running │ │ running │ │ running │ │ running │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
│       │           │           │           │           │         │
│       ▼           ▼           ▼           ▼           ▼         │
│  [任务队列] ─────→ 分配容器 ─────→ exec 执行 ─────→ 归还池中    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

工作流程：
1. 应用启动时预创建容器
2. 任务到达 → 从池中获取容器 → exec 执行 → 归还
3. 空闲容器定期清理
4. 池容量动态调整

@created: 2026-03-31
@author: AI Assistant
"""

import os
import json
import socket
import time
import threading
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Queue, Empty

from app.core.logger import log
from app.core.config import settings

DOCKER_SOCKET = '/var/run/docker.sock'

# ==========================================
# 常量定义
# ==========================================

# Conda 持久化路径
CONDA_HOST_PATH = "/opt/data1/public/software/systools/autonome/autonome_conda"
CONDA_CONTAINER_PATH = "/opt/conda"

# Biosource 生信脚本库路径
BIOSOURCE_HOST_PATH = "/opt/data1/public/software/systools/autonome/biosource"
BIOSOURCE_CONTAINER_PATH = "/app/biosource"

# SKILL 技能包目录
SKILLS_HOST_PATH = "/opt/data1/public/software/systools/autonome/autonome-backend/app/skills"
SKILLS_CONTAINER_PATH = "/app/skills"

# 用户包目录
USER_PACKAGES_HOST_PATH = "/opt/data1/public/software/systools/autonome/uploads/user_packages"
USER_PACKAGES_CONTAINER_PATH = "/app/user_packages"


class ContainerType(Enum):
    """容器类型"""
    PYTHON = "python"
    R = "r"
    GENERAL = "general"


class ContainerStatus(Enum):
    """容器状态"""
    IDLE = "idle"          # 空闲，等待任务
    BUSY = "busy"          # 执行任务中
    ERROR = "error"        # 错误状态
    STOPPED = "stopped"    # 已停止


@dataclass
class PooledContainer:
    """池化容器"""
    container_id: str
    container_type: ContainerType
    status: ContainerStatus = ContainerStatus.IDLE
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    task_count: int = 0
    error_count: int = 0

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "container_id": self.container_id[:12],
            "container_type": self.container_type.value,
            "status": self.status.value,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "last_used_at": datetime.fromtimestamp(self.last_used_at).isoformat(),
            "age_seconds": int(time.time() - self.created_at),
            "idle_seconds": int(time.time() - self.last_used_at),
            "task_count": self.task_count,
            "error_count": self.error_count
        }


# ==========================================
# Docker API 辅助函数
# ==========================================

def docker_api_request(method: str, path: str, data: str = None, return_raw: bool = False, timeout: int = 30) -> Any:
    """
    直接通过 Unix socket 调用 Docker API

    Args:
        method: HTTP 方法
        path: API 路径
        data: 请求体
        return_raw: 是否返回原始文本
        timeout: socket 超时时间（秒）
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(DOCKER_SOCKET)

    body = data.encode('utf-8') if data else None

    request = f"{method} {path} HTTP/1.0\r\n"
    request += "Host: localhost\r\n"
    request += "Connection: close\r\n"
    if body:
        request += f"Content-Length: {len(body)}\r\n"
    request += "Content-Type: application/json\r\n\r\n"

    if body:
        request = request.encode('utf-8') + body
    else:
        request = request.encode('utf-8')

    sock.sendall(request)

    response = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response += chunk

    sock.close()

    if b"\r\n\r\n" in response:
        headers, raw_body = response.split(b"\r\n\r\n", 1)
    else:
        raw_body = response

    body_str = raw_body.decode('utf-8', errors='ignore').strip()

    if not body_str:
        return "" if return_raw else {}

    if return_raw:
        return body_str

    start_dict = body_str.find('{')
    end_dict = body_str.rfind('}')
    start_list = body_str.find('[')
    end_list = body_str.rfind(']')

    try:
        if start_dict != -1 and end_dict != -1 and (start_list == -1 or start_dict < start_list):
            return json.loads(body_str[start_dict:end_dict+1])
        elif start_list != -1 and end_list != -1:
            return json.loads(body_str[start_list:end_list+1])
        return json.loads(body_str)
    except Exception:
        return {"body": body_str}


# ==========================================
# 容器预热池服务
# ==========================================

class ContainerPoolService:
    """
    容器预热池服务

    功能：
    1. 维护预热容器池，快速响应任务
    2. 动态扩缩容
    3. 健康检查和自动恢复
    4. 统计监控

    使用方式：
    - 获取容器：acquire_container(container_type) → PooledContainer
    - 执行命令：exec_in_container(container, command) → (output, exit_code)
    - 归还容器：release_container(container)
    """

    # 池配置
    DEFAULT_CONFIG = {
        ContainerType.PYTHON: {
            "min_size": 2,        # 最小容器数
            "max_size": 5,        # 最大容器数
            "image": "autonome-tool-env:latest",  # 使用实际存在的镜像
            "idle_timeout": 300,  # 空闲超时（秒）
        },
        ContainerType.R: {
            "min_size": 1,        # 减少最小数量，R 使用较少
            "max_size": 3,
            "image": "autonome-tool-env:latest",  # 同一镜像支持 R
            "idle_timeout": 300,
        },
        ContainerType.GENERAL: {
            "min_size": 1,
            "max_size": 3,
            "image": "autonome-tool-env:latest",
            "idle_timeout": 600,
        }
    }

    def __init__(self):
        """初始化容器池服务"""
        # 容器池：按类型分组
        self.pools: Dict[ContainerType, List[PooledContainer]] = {
            ContainerType.PYTHON: [],
            ContainerType.R: [],
            ContainerType.GENERAL: []
        }

        # 空闲队列：用于快速获取空闲容器
        self.idle_queues: Dict[ContainerType, Queue] = {
            ContainerType.PYTHON: Queue(),
            ContainerType.R: Queue(),
            ContainerType.GENERAL: Queue()
        }

        # 锁：保证线程安全
        self.locks: Dict[ContainerType, threading.Lock] = {
            ContainerType.PYTHON: threading.Lock(),
            ContainerType.R: threading.Lock(),
            ContainerType.GENERAL: threading.Lock()
        }

        # 统计数据
        self.stats = {
            "total_created": 0,
            "total_reused": 0,
            "total_errors": 0,
            "total_wait_time_ms": 0.0,
            "tasks_served": 0
        }

        # 清理线程
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False

        log.info("[ContainerPool] 容器池服务初始化完成")

    # ==========================================
    # 核心方法：获取/归还容器
    # ==========================================

    def acquire_container(
        self,
        container_type: ContainerType,
        timeout: float = 30.0,
        user_id: Optional[int] = None
    ) -> Optional[PooledContainer]:
        """
        获取容器（从池中或创建新容器）

        Args:
            container_type: 容器类型
            timeout: 等待超时（秒）
            user_id: 用户 ID（用于用户级包管理）

        Returns:
            PooledContainer 或 None（超时）
        """
        start_time = time.time()
        lock = self.locks[container_type]

        with lock:
            # 1. 尝试从空闲队列获取
            try:
                container = self.idle_queues[container_type].get_nowait()
                if container and container.status == ContainerStatus.IDLE:
                    container.status = ContainerStatus.BUSY
                    container.last_used_at = time.time()
                    container.task_count += 1

                    self.stats["total_reused"] += 1
                    wait_time = (time.time() - start_time) * 1000
                    self.stats["total_wait_time_ms"] += wait_time
                    self.stats["tasks_served"] += 1

                    log.debug(f"[ContainerPool] 复用容器: {container.container_id[:12]}, 等待={wait_time:.1f}ms")
                    return container
            except Empty:
                pass

            # 2. 检查是否可以创建新容器
            config = self.DEFAULT_CONFIG[container_type]
            current_size = len(self.pools[container_type])

            if current_size < config["max_size"]:
                # 创建新容器
                container = self._create_container(container_type, user_id)
                if container:
                    self.pools[container_type].append(container)
                    container.status = ContainerStatus.BUSY
                    container.task_count = 1

                    self.stats["total_created"] += 1
                    self.stats["tasks_served"] += 1

                    wait_time = (time.time() - start_time) * 1000
                    self.stats["total_wait_time_ms"] += wait_time

                    log.info(f"[ContainerPool] 创建新容器: {container.container_id[:12]}, 等待={wait_time:.1f}ms")
                    return container

            # 3. 等待空闲容器
            log.warning(f"[ContainerPool] 容器池已满，等待空闲容器...")

        # 释放锁后等待
        try:
            container = self.idle_queues[container_type].get(timeout=timeout)
            if container and container.status == ContainerStatus.IDLE:
                with lock:
                    container.status = ContainerStatus.BUSY
                    container.last_used_at = time.time()
                    container.task_count += 1

                    self.stats["total_reused"] += 1
                    wait_time = (time.time() - start_time) * 1000
                    self.stats["total_wait_time_ms"] += wait_time
                    self.stats["tasks_served"] += 1

                    log.debug(f"[ContainerPool] 等待后获取容器: {container.container_id[:12]}, 等待={wait_time:.1f}ms")
                    return container
        except Empty:
            log.warning(f"[ContainerPool] 获取容器超时: {timeout}s")
            return None

        return None

    def release_container(self, container: PooledContainer) -> None:
        """
        归还容器到池中

        Args:
            container: 要归还的容器
        """
        if not container:
            return

        lock = self.locks[container.container_type]

        with lock:
            # 检查容器是否还健康
            if not self._health_check(container):
                log.warning(f"[ContainerPool] 容器不健康，移除: {container.container_id[:12]}")
                self._remove_container(container)
                return

            # 标记为空闲
            container.status = ContainerStatus.IDLE
            container.last_used_at = time.time()

            # 放入空闲队列
            self.idle_queues[container.container_type].put(container)

            log.debug(f"[ContainerPool] 容器归还: {container.container_id[:12]}")

    # ==========================================
    # 容器创建和管理
    # ==========================================

    def _create_container(
        self,
        container_type: ContainerType,
        user_id: Optional[int] = None
    ) -> Optional[PooledContainer]:
        """
        创建预热容器

        Args:
            container_type: 容器类型
            user_id: 用户 ID

        Returns:
            PooledContainer 或 None
        """
        config = self.DEFAULT_CONFIG[container_type]
        image = config["image"]

        try:
            # 准备环境变量
            env_list = [
                f"PATH={CONDA_CONTAINER_PATH}/bin:/usr/local/bin:/usr/bin:/bin",
                f"CONDA_PREFIX={CONDA_CONTAINER_PATH}",
                "PYTHONUNBUFFERED=1"  # 禁用 Python 缓冲
            ]

            # 准备挂载
            binds_list = [
                f"{CONDA_HOST_PATH}:{CONDA_CONTAINER_PATH}:ro",
                f"{SKILLS_HOST_PATH}:{SKILLS_CONTAINER_PATH}:ro",
                f"{BIOSOURCE_HOST_PATH}:{BIOSOURCE_CONTAINER_PATH}:ro"
            ]

            # 用户包挂载
            if user_id:
                host_user_pkg_dir = f"{USER_PACKAGES_HOST_PATH}/user_{user_id}"
                os.makedirs(host_user_pkg_dir, exist_ok=True)
                binds_list.append(f"{host_user_pkg_dir}:{USER_PACKAGES_CONTAINER_PATH}/user_{user_id}:rw")

            # 创建容器（保持运行状态）
            # 使用 sleep infinity 让容器保持运行
            create_data = json.dumps({
                "Image": image,
                "platform": "linux/amd64",
                "Cmd": ["sleep", "infinity"],  # 保持容器运行
                "Tty": True,
                "User": "root",
                "Env": env_list,
                "HostConfig": {
                    "Memory": 128 * 1024 * 1024 * 1024,  # 128GB
                    "NetworkMode": "none",  # 默认无网络
                    "CapDrop": ["ALL"],
                    "Binds": binds_list
                },
                "Labels": {
                    "autonome.pool": "true",
                    "autonome.type": container_type.value,
                    "autonome.created": datetime.now().isoformat()
                }
            })

            resp = docker_api_request("POST", "/containers/create", create_data, timeout=60)

            if 'Id' not in resp:
                log.error(f"[ContainerPool] 创建容器失败: {resp}")
                return None

            container_id = resp['Id']

            # 启动容器
            docker_api_request("POST", f"/containers/{container_id}/start", timeout=30)

            log.info(f"[ContainerPool] 容器已创建并启动: {container_id[:12]}, type={container_type.value}")

            return PooledContainer(
                container_id=container_id,
                container_type=container_type,
                status=ContainerStatus.IDLE
            )

        except Exception as e:
            log.error(f"[ContainerPool] 创建容器异常: {e}")
            self.stats["total_errors"] += 1
            return None

    def _health_check(self, container: PooledContainer) -> bool:
        """
        健康检查

        Args:
            container: 容器对象

        Returns:
            是否健康
        """
        try:
            info = docker_api_request("GET", f"/containers/{container.container_id}/json", timeout=10)
            status = info.get('State', {}).get('Status', 'unknown')

            if status == 'running':
                return True

            log.warning(f"[ContainerPool] 容器状态异常: {container.container_id[:12]}, status={status}")
            return False

        except Exception as e:
            log.error(f"[ContainerPool] 健康检查失败: {e}")
            return False

    def _remove_container(self, container: PooledContainer) -> None:
        """
        移除容器

        Args:
            container: 要移除的容器
        """
        try:
            # 停止容器
            docker_api_request("POST", f"/containers/{container.container_id}/stop?t=5", timeout=30)
            # 删除容器
            docker_api_request("DELETE", f"/containers/{container.container_id}?force=true", timeout=30)

            # 从池中移除
            if container in self.pools[container.container_type]:
                self.pools[container.container_type].remove(container)

            log.info(f"[ContainerPool] 容器已移除: {container.container_id[:12]}")

        except Exception as e:
            log.error(f"[ContainerPool] 移除容器失败: {e}")

    # ==========================================
    # 执行命令
    # ==========================================

    def exec_in_container(
        self,
        container: PooledContainer,
        command: List[str],
        timeout: int = 3600,
        enable_network: bool = False
    ) -> tuple[str, int]:
        """
        在容器中执行命令

        Args:
            container: 容器对象
            command: 命令列表
            timeout: 执行超时
            enable_network: 是否启用网络

        Returns:
            (输出日志, 退出码)
        """
        try:
            # 如果需要网络，重新创建容器（简化处理）
            if enable_network:
                log.warning("[ContainerPool] 网络模式需要新容器，预热容器不支持网络任务")
                return "预热容器不支持网络任务，请使用独立容器", 1

            # 创建 exec 实例
            exec_create_data = json.dumps({
                "AttachStdout": True,
                "AttachStderr": True,
                "Cmd": command,
                "Tty": True
            })

            exec_resp = docker_api_request(
                "POST",
                f"/containers/{container.container_id}/exec",
                exec_create_data,
                timeout=30
            )

            if 'Id' not in exec_resp:
                return f"创建 exec 失败: {exec_resp}", 1

            exec_id = exec_resp['Id']

            # 执行 exec
            exec_start_data = json.dumps({
                "Detach": False,
                "Tty": True
            })

            output = docker_api_request(
                "POST",
                f"/exec/{exec_id}/start",
                exec_start_data,
                return_raw=True,
                timeout=timeout
            )

            # 获取退出码
            exec_info = docker_api_request("GET", f"/exec/{exec_id}/json", timeout=10)
            exit_code = exec_info.get('ExitCode', 0)

            # 清理输出中的控制字符
            import re
            if isinstance(output, str):
                output = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', output)

            log.debug(f"[ContainerPool] exec 完成: exit_code={exit_code}")

            return output, exit_code

        except Exception as e:
            log.error(f"[ContainerPool] exec 执行失败: {e}")
            container.error_count += 1
            return f"执行失败: {str(e)}", 1

    # ==========================================
    # 池管理
    # ==========================================

    def warmup(self) -> Dict[str, int]:
        """
        预热容器池

        Returns:
            各类型预热的容器数量
        """
        log.info("[ContainerPool] 开始预热容器池...")

        results = {}

        for container_type, config in self.DEFAULT_CONFIG.items():
            min_size = config["min_size"]
            current_size = len(self.pools[container_type])

            to_create = max(0, min_size - current_size)

            for _ in range(to_create):
                container = self._create_container(container_type)
                if container:
                    self.pools[container_type].append(container)
                    self.idle_queues[container_type].put(container)

            results[container_type.value] = to_create
            log.info(f"[ContainerPool] 预热 {container_type.value}: 创建 {to_create} 个容器")

        log.info(f"[ContainerPool] 预热完成: {results}")
        return results

    def start_cleanup_thread(self, interval: int = 60) -> None:
        """
        启动清理线程

        Args:
            interval: 清理间隔（秒）
        """
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return

        self._running = True

        def cleanup_loop():
            while self._running:
                try:
                    self._cleanup_idle_containers()
                    self._ensure_min_size()
                except Exception as e:
                    log.error(f"[ContainerPool] 清理线程异常: {e}")

                time.sleep(interval)

        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()

        log.info(f"[ContainerPool] 清理线程已启动，间隔={interval}s")

    def stop_cleanup_thread(self) -> None:
        """停止清理线程"""
        self._running = False

    def _cleanup_idle_containers(self) -> None:
        """清理空闲超时的容器"""
        for container_type, config in self.DEFAULT_CONFIG.items():
            lock = self.locks[container_type]

            with lock:
                min_size = config["min_size"]
                idle_timeout = config["idle_timeout"]

                to_remove = []

                for container in self.pools[container_type]:
                    if container.status == ContainerStatus.IDLE:
                        idle_time = time.time() - container.last_used_at

                        # 超过空闲超时且超过最小数量
                        if idle_time > idle_timeout and len(self.pools[container_type]) > min_size:
                            to_remove.append(container)

                for container in to_remove:
                    log.info(f"[ContainerPool] 清理空闲容器: {container.container_id[:12]}, 空闲={int(time.time() - container.last_used_at)}s")
                    self._remove_container(container)

    def _ensure_min_size(self) -> None:
        """确保每个池至少有最小数量的容器"""
        for container_type, config in self.DEFAULT_CONFIG.items():
            lock = self.locks[container_type]

            with lock:
                min_size = config["min_size"]
                current_size = len(self.pools[container_type])

                if current_size < min_size:
                    to_create = min_size - current_size
                    log.info(f"[ContainerPool] 补充容器: {container_type.value}, 需要 {to_create} 个")

                    for _ in range(to_create):
                        container = self._create_container(container_type)
                        if container:
                            self.pools[container_type].append(container)
                            self.idle_queues[container_type].put(container)

    def clear_all(self) -> Dict[str, int]:
        """
        清空所有容器

        Returns:
            各类型清理的容器数量
        """
        log.info("[ContainerPool] 开始清空所有容器...")

        results = {}

        for container_type in self.DEFAULT_CONFIG.keys():
            lock = self.locks[container_type]

            with lock:
                count = 0
                for container in list(self.pools[container_type]):
                    self._remove_container(container)
                    count += 1

                self.pools[container_type].clear()

                # 清空队列
                while not self.idle_queues[container_type].empty():
                    try:
                        self.idle_queues[container_type].get_nowait()
                    except Empty:
                        break

                results[container_type.value] = count

        log.info(f"[ContainerPool] 清空完成: {results}")
        return results

    # ==========================================
    # 状态查询
    # ==========================================

    def get_status(self) -> Dict:
        """
        获取容器池状态

        Returns:
            状态信息
        """
        status = {
            "pools": {},
            "stats": self.stats.copy(),
            "config": {}
        }

        for container_type in self.DEFAULT_CONFIG.keys():
            lock = self.locks[container_type]

            with lock:
                pool = self.pools[container_type]
                idle_count = sum(1 for c in pool if c.status == ContainerStatus.IDLE)
                busy_count = sum(1 for c in pool if c.status == ContainerStatus.BUSY)

                status["pools"][container_type.value] = {
                    "total": len(pool),
                    "idle": idle_count,
                    "busy": busy_count,
                    "containers": [c.to_dict() for c in pool]
                }

                status["config"][container_type.value] = self.DEFAULT_CONFIG[container_type]

        # 计算平均等待时间
        if self.stats["tasks_served"] > 0:
            status["stats"]["avg_wait_time_ms"] = round(
                self.stats["total_wait_time_ms"] / self.stats["tasks_served"], 2
            )
        else:
            status["stats"]["avg_wait_time_ms"] = 0

        # 计算复用率
        if self.stats["tasks_served"] > 0:
            status["stats"]["reuse_rate"] = round(
                self.stats["total_reused"] / self.stats["tasks_served"] * 100, 2
            )
        else:
            status["stats"]["reuse_rate"] = 0

        status["timestamp"] = datetime.now().isoformat()

        return status


# ==========================================
# 全局单例
# ==========================================

_pool_service: Optional[ContainerPoolService] = None
_pool_lock = threading.Lock()


def get_container_pool() -> ContainerPoolService:
    """
    获取容器池服务单例

    Returns:
        ContainerPoolService 实例
    """
    global _pool_service

    if _pool_service is None:
        with _pool_lock:
            if _pool_service is None:
                _pool_service = ContainerPoolService()

    return _pool_service


def init_container_pool(warmup: bool = True) -> ContainerPoolService:
    """
    初始化容器池服务

    Args:
        warmup: 是否预热容器

    Returns:
        ContainerPoolService 实例
    """
    pool = get_container_pool()

    if warmup:
        pool.warmup()

    pool.start_cleanup_thread(interval=60)

    return pool


log.info("✅ 容器预热池服务已加载")