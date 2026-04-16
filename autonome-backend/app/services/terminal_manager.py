"""
Web Terminal 管理器

负责 Docker 容器生命周期管理，为浏览器终端提供隔离的执行环境。

安全配置：
- NetworkMode: none (无网络访问)
- CapDrop: ALL (移除所有 Linux capabilities)
- SecurityOpt: no-new-privileges (禁止提权)
- 资源限制: 4GB 内存, 2 CPU, 256 PIDs (防 fork bomb)
- 文件隔离: 只挂载当前项目目录
"""

import os
import json
import socket
import asyncio
import uuid
import time
import threading
from typing import Optional, Dict
from pathlib import Path

from app.core.logger import log
from app.core.config import settings

# ==========================================
# Docker 挂载路径配置（与 bio_tools.py 保持一致）
# ==========================================
DOCKER_SOCKET = '/var/run/docker.sock'

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


class TerminalSession:
    """终端会话对象，封装容器信息和通信"""

    def __init__(self, session_id: str, container_id: str, project_id: str, user_id: int):
        self.session_id = session_id
        self.container_id = container_id
        self.project_id = project_id
        self.user_id = user_id
        self.created_at = time.time()
        self.last_activity = time.time()  # ✨ 最后活跃时间，用于自动回收


class TerminalManager:
    """
    终端会话管理器

    负责：
    1. 创建 PTY 容器（Tty=True, OpenStdin=True）
    2. 双向字节流泵：WebSocket ↔ Docker attach socket
    3. 会话生命周期管理
    4. 资源限制和安全配置
    5. ✨ 自动回收超时会话（防止僵尸容器堆积）
    """

    # ✨ 终端会话最大存活时间（秒），默认 2 小时
    SESSION_MAX_TTL = 7200
    # ✨ 会话空闲超时时间（秒），默认 30 分钟无活动则回收
    SESSION_IDLE_TIMEOUT = 1800
    # ✨ 清理线程检查间隔（秒）
    CLEANUP_INTERVAL = 60

    def __init__(self):
        # 活跃会话字典：session_id -> TerminalSession
        self.active_sessions: Dict[str, TerminalSession] = {}
        # ✨ 清理线程
        self._cleanup_thread: Optional[threading.Thread] = None

    def _docker_api_request(
        self,
        method: str,
        path: str,
        data: dict = None,
        timeout: int = 30
    ) -> dict:
        """直接通过 Unix socket 调用 Docker API"""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(DOCKER_SOCKET)

        body = json.dumps(data).encode('utf-8') if data else None

        # 构建请求
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

        # 读取响应
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk

        sock.close()

        # 解析响应
        if b"\r\n\r\n" in response:
            headers, raw_body = response.split(b"\r\n\r\n", 1)
        else:
            raw_body = response

        body_str = raw_body.decode('utf-8', errors='ignore').strip()

        if not body_str:
            return {}

        # 提取 JSON
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

    async def create_session(
        self,
        project_id: str,
        user_id: int,
        cols: int = 80,
        rows: int = 24
    ) -> Optional[TerminalSession]:
        """
        创建新的终端会话

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            cols: 终端列数
            rows: 终端行数

        Returns:
            TerminalSession 对象，失败返回 None
        """
        try:
            # 生成唯一会话 ID
            session_id = str(uuid.uuid4())

            # 构建项目目录路径
            host_upload_dir = os.environ.get("HOST_UPLOAD_DIR", settings.UPLOAD_DIR)
            project_dir = Path(host_upload_dir) / f"project_{project_id}"

            # 确保项目目录存在
            project_dir.mkdir(parents=True, exist_ok=True)

            # 用户包目录
            user_pkg_dir = f"{USER_PACKAGES_CONTAINER_PATH}/user_{user_id}"
            host_user_pkg_dir = f"{USER_PACKAGES_HOST_PATH}/user_{user_id}"
            os.makedirs(host_user_pkg_dir, exist_ok=True)

            # 环境变量
            env_list = [
                f"PATH={CONDA_CONTAINER_PATH}/bin:/usr/local/bin:/usr/bin:/bin",
                f"CONDA_PREFIX={CONDA_CONTAINER_PATH}",
                f"TERM=xterm-256color",
                f"COLUMNS={cols}",
                f"LINES={rows}",
                # Python 用户包路径
                f"PYTHONPATH={user_pkg_dir}/python:{CONDA_CONTAINER_PATH}/lib/python3.10/site-packages",
                # R 用户包路径
                f"R_LIBS_USER={user_pkg_dir}/r",
                f"R_LIBS={user_pkg_dir}/r:{CONDA_CONTAINER_PATH}/lib/R/library",
            ]

            # 挂载配置
            binds_list = [
                f"{project_dir}:/workspace:rw",  # 项目目录（读写）
                f"{CONDA_HOST_PATH}:{CONDA_CONTAINER_PATH}:ro",  # Conda（只读）
                f"{SKILLS_HOST_PATH}:{SKILLS_CONTAINER_PATH}:ro",  # SKILL 脚本库
                f"{BIOSOURCE_HOST_PATH}:{BIOSOURCE_CONTAINER_PATH}:ro",  # 生信脚本库
                f"{host_user_pkg_dir}:{user_pkg_dir}:rw",  # 用户包目录
            ]

            # 创建 PTY 容器
            create_data = {
                "Image": "autonome-tool-env",
                "platform": "linux/amd64",
                "Tty": True,  # 启用 PTY
                "OpenStdin": True,  # 允许输入
                "AttachStdin": True,
                "AttachStdout": True,
                "AttachStderr": True,
                "User": "root",
                "Env": env_list,
                "Cmd": ["/bin/bash", "-l"],  # 登录 shell
                "HostConfig": {
                    "Memory": 4 * 1024 * 1024 * 1024,  # 4GB
                    "NanoCpus": 2_000_000_000,  # 2 CPUs
                    "PidsLimit": 256,  # 防止 fork bomb
                    "NetworkMode": "none",  # 无网络访问
                    "CapDrop": ["ALL"],  # 移除所有 capabilities
                    "SecurityOpt": ["no-new-privileges"],  # 禁止提权
                    "Binds": binds_list
                },
                "WorkingDir": "/workspace"
            }

            log.info(f"[Terminal] 🐳 创建终端容器: session={session_id}, project={project_id}, user={user_id}")

            resp = self._docker_api_request("POST", "/containers/create", create_data)

            if 'Id' not in resp:
                log.error(f"[Terminal] 创建容器失败: {resp}")
                return None

            container_id = resp['Id']

            # 启动容器
            self._docker_api_request("POST", f"/containers/{container_id}/start")
            log.info(f"[Terminal] ✅ 容器已启动: {container_id[:12]}")

            # 创建会话对象
            session = TerminalSession(
                session_id=session_id,
                container_id=container_id,
                project_id=project_id,
                user_id=user_id
            )

            self.active_sessions[session_id] = session
            return session

        except Exception as e:
            log.error(f"[Terminal] 创建会话失败: {e}")
            return None

    async def attach_to_session(
        self,
        session_id: str,
        websocket_send_callback
    ) -> Optional[socket.socket]:
        """
        连接到容器的 PTY

        Args:
            session_id: 会话 ID
            websocket_send_callback: 发送数据到 WebSocket 的回调函数

        Returns:
            Docker attach socket，失败返回 None
        """
        session = self.active_sessions.get(session_id)
        if not session:
            log.error(f"[Terminal] 会话不存在: {session_id}")
            return None

        try:
            # 创建到 Docker 的 socket 连接
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(60)  # 较长的超时，因为终端会话可能持续很久
            sock.connect(DOCKER_SOCKET)

            # 发送 attach 请求
            container_id = session.container_id
            request = (
                f"POST /containers/{container_id}/attach?stream=1&stdin=1&stdout=1&stderr=1 HTTP/1.1\r\n"
                f"Host: localhost\r\n"
                f"Connection: Upgrade\r\n"
                f"Upgrade: tcp\r\n"
                f"\r\n"
            )
            sock.sendall(request.encode('utf-8'))

            # 等待响应
            response = b""
            while b"\r\n\r\n" not in response:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                response += chunk

            # 设置非阻塞模式
            sock.setblocking(False)

            log.info(f"[Terminal] 🔗 已连接到容器 PTY: {container_id[:12]}")
            return sock

        except Exception as e:
            log.error(f"[Terminal] 连接 PTY 失败: {e}")
            return None

    async def resize_terminal(
        self,
        session_id: str,
        cols: int,
        rows: int
    ) -> bool:
        """
        调整终端大小

        Args:
            session_id: 会话 ID
            cols: 新的列数
            rows: 新的行数

        Returns:
            成功返回 True
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        try:
            resize_data = {"h": rows, "w": cols}
            self._docker_api_request(
                "POST",
                f"/containers/{session.container_id}/resize?h={rows}&w={cols}",
                resize_data
            )
            log.debug(f"[Terminal] 终端大小已调整: {cols}x{rows}")
            return True
        except Exception as e:
            log.error(f"[Terminal] 调整终端大小失败: {e}")
            return False

    async def destroy_session(self, session_id: str) -> bool:
        """
        销毁终端会话，强制删除容器

        Args:
            session_id: 会话 ID

        Returns:
            成功返回 True
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return True  # 会话不存在，视为已销毁

        try:
            container_id = session.container_id

            # 停止容器
            try:
                self._docker_api_request("POST", f"/containers/{container_id}/stop?t=5", timeout=10)
            except Exception:
                pass  # 容器可能已经停止

            # 强制删除容器
            self._docker_api_request("DELETE", f"/containers/{container_id}?force=true", timeout=10)
            log.info(f"[Terminal] 🗑️ 容器已销毁: {container_id[:12]}")

            # 移除会话记录
            del self.active_sessions[session_id]
            return True

        except Exception as e:
            log.error(f"[Terminal] 销毁会话失败: {e}")
            # 即使失败也移除会话记录
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            return False

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        """获取会话对象，并更新最后活跃时间"""
        session = self.active_sessions.get(session_id)
        if session:
            session.last_activity = time.time()
        return session

    def touch_activity(self, session_id: str) -> None:
        """✨ 更新会话活跃时间（WebSocket 收发数据时调用）"""
        session = self.active_sessions.get(session_id)
        if session:
            session.last_activity = time.time()

    def start_cleanup_thread(self) -> None:
        """✨ 启动后台清理线程，自动回收超时的终端会话"""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return

        def _cleanup_loop():
            while True:
                try:
                    self._cleanup_expired_sessions()
                except Exception as e:
                    log.error(f"[Terminal] 清理线程异常: {e}")
                time.sleep(self.CLEANUP_INTERVAL)

        self._cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True, name="terminal-cleanup")
        self._cleanup_thread.start()
        log.info(f"[Terminal] 🧹 清理线程已启动 (TTL={self.SESSION_MAX_TTL}s, idle={self.SESSION_IDLE_TIMEOUT}s)")

    def _cleanup_expired_sessions(self) -> None:
        """✨ 清理超时的终端会话，防止僵尸容器堆积"""
        now = time.time()
        expired_sessions = []

        for session_id, session in list(self.active_sessions.items()):
            age = now - session.created_at
            idle = now - session.last_activity

            # 超过最大存活时间 或 超过空闲超时时间
            if age > self.SESSION_MAX_TTL or idle > self.SESSION_IDLE_TIMEOUT:
                reason = "TTL过期" if age > self.SESSION_MAX_TTL else "空闲超时"
                expired_sessions.append((session_id, reason))

        for session_id, reason in expired_sessions:
            session = self.active_sessions.get(session_id)
            if session:
                log.info(f"[Terminal] 🧹 自动回收会话 {session_id[:8]}... (原因: {reason})")
                try:
                    # 同步调用 destroy_session 的核心逻辑
                    container_id = session.container_id
                    try:
                        self._docker_api_request("POST", f"/containers/{container_id}/stop?t=5", timeout=10)
                    except Exception:
                        pass
                    self._docker_api_request("DELETE", f"/containers/{container_id}?force=true", timeout=10)
                    log.info(f"[Terminal] 🗑️ 僵尸容器已清理: {container_id[:12]}")
                except Exception as e:
                    log.warning(f"[Terminal] 清理容器失败: {e}")
                finally:
                    if session_id in self.active_sessions:
                        del self.active_sessions[session_id]

        if expired_sessions:
            log.info(f"[Terminal] 🧹 本轮清理完成，回收 {len(expired_sessions)} 个会话")


# 全局单例
terminal_manager = TerminalManager()