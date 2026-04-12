"""
PTY Manager - Claude Code PTY 会话管理器

通过伪终端（PTY）拉起 Claude Code 进程，
实现与其输出流的高效交互。
"""

import os
import pty
import select
import subprocess
import time
import re
import json
import fcntl
import struct
import termios
import asyncio
from typing import Tuple, Optional, Callable, AsyncIterator, Any
from dataclasses import dataclass
from enum import Enum

from app.core.logger import log
from app.utils.ansi_cleaner import ANSICleaner


class PTYState(Enum):
    """PTY 会话状态"""
    IDLE = "idle"
    RUNNING = "running"
    CLOSED = "closed"


@dataclass
class PTYConfig:
    """PTY 配置"""
    rows: int = 24
    cols: int = 80
    timeout: float = 1.0  # 读取超时（秒）
    max_retries: int = 3


class PTYExtractionError(Exception):
    """PTY 结果提取错误（细粒度）"""

    class ErrorType(Enum):
        MARKER_NOT_FOUND = "marker_not_found"      # 未找到锚点标记
        JSON_INVALID = "json_invalid"              # JSON 格式无效
        JSON_TRUNCATED = "json_truncated"          # JSON 被截断
        EMPTY_OUTPUT = "empty_output"              # 输出为空

    def __init__(self, error_type: "PTYExtractionError.ErrorType", message: str, raw_snippet: str = ""):
        self.error_type = error_type
        self.message = message
        self.raw_snippet = raw_snippet
        super().__init__(message)


@dataclass
class PTYResult:
    """
    V2: PTY 执行结果（结构化返回）

    替代原来的 Optional[dict] 返回，提供更丰富的错误信息和执行统计。
    """
    success: bool
    raw_output: str = ""
    structured_data: Optional[dict] = None
    error: Optional[str] = None
    error_type: Optional[str] = None  # PTYExtractionError.ErrorType value
    timed_out: bool = False
    execution_time_ms: int = 0


class PTYManager:
    """
    Claude Code PTY 会话管理器

    功能：
    - 通过 PTY 拉起 Claude Code 进程
    - 实时读取输出（ANSI 清洗）
    - 发送输入
    - 流式回调支持
    """

    def __init__(self, config: Optional[PTYConfig] = None):
        self.config = config or PTYConfig()
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.state = PTYState.IDLE
        self._output_buffer = ""

    def start_session(self, command: list[str], cwd: Optional[str] = None) -> bool:
        """
        启动 PTY 会话

        Args:
            command: 要执行的命令列表
            cwd: 工作目录

        Returns:
            True 如果启动成功
        """
        if self.state == PTYState.RUNNING:
            log.warning("⚠️ [PTY] 会话已在运行中")
            return False

        try:
            # 创建 PTY 对
            self.master_fd, self.slave_fd = pty.openpty()

            # 设置终端窗口大小
            winsize = struct.pack('HHHH', self.config.rows, self.config.cols, 0, 0)
            fcntl.ioctl(self.slave_fd, termios.TIOCSWINSZ, winsize)

            # Fork 进程
            self.pid = os.fork()

            if self.pid == 0:
                # 子进程
                try:
                    # 创建新会话
                    os.setsid()

                    # 设置 CTTY
                    fcntl.ioctl(self.slave_fd, termios.TIOCSCTTY, 0)

                    # 重定向标准输入/输出/错误
                    os.dup2(self.slave_fd, 0)
                    os.dup2(self.slave_fd, 1)
                    os.dup2(self.slave_fd, 2)

                    # 关闭不需要的 fd
                    os.close(self.master_fd)
                    os.close(self.slave_fd)

                    # 切换工作目录
                    if cwd:
                        os.chdir(cwd)

                    # 执行命令
                    os.execvp(command[0], command)
                except Exception as e:
                    os._exit(1)
            else:
                # 父进程
                os.close(self.slave_fd)
                self.slave_fd = None
                self.state = PTYState.RUNNING
                log.info(f"🚀 [PTY] 会话已启动，PID={self.pid}")
                return True

        except Exception as e:
            log.error(f"❌ [PTY] 启动会话失败: {e}")
            self._cleanup()
            return False

    def read_output(self, timeout: Optional[float] = None, clean_ansi: bool = True) -> str:
        """
        读取输出

        Args:
            timeout: 读取超时（秒），None 使用默认配置
            clean_ansi: 是否清洗 ANSI 转义序列

        Returns:
            读取到的输出
        """
        if self.state != PTYState.RUNNING or self.master_fd is None:
            return ""

        timeout = timeout or self.config.timeout
        data = b""

        try:
            # 使用 select 等待数据
            r, _, _ = select.select([self.master_fd], [], [], timeout)

            if r:
                chunk = os.read(self.master_fd, 65536)
                if chunk:
                    data += chunk
                    # 继续读取直到没有更多数据
                    while True:
                        r, _, _ = select.select([self.master_fd], [], [], 0.1)
                        if not r:
                            break
                        chunk = os.read(self.master_fd, 65536)
                        if not chunk:
                            break
                        data += chunk

        except OSError as e:
            if e.errno != 5:  # EBADF (Bad file descriptor) - 可能是正常关闭
                log.error(f"⚠️ [PTY] 读取输出失败: {e}")

        result = data.decode('utf-8', errors='replace')

        if clean_ansi:
            result = ANSICleaner.clean(result)

        self._output_buffer += result
        return result

    def read_output_callback(
        self,
        callback: Callable[[str], None],
        timeout: Optional[float] = None,
        clean_ansi: bool = True
    ) -> None:
        """
        读取输出并通过回调函数处理

        Args:
            callback: 处理每一块输出的回调函数
            timeout: 读取超时（秒）
            clean_ansi: 是否清洗 ANSI 转义序列
        """
        if self.state != PTYState.RUNNING or self.master_fd is None:
            return

        timeout = timeout or self.config.timeout

        try:
            while True:
                r, _, _ = select.select([self.master_fd], [], [], timeout)
                if not r:
                    break

                chunk = os.read(self.master_fd, 4096)
                if not chunk:
                    break

                result = chunk.decode('utf-8', errors='replace')
                if clean_ansi:
                    result = ANSICleaner.clean(result)

                callback(result)

        except OSError as e:
            if e.errno != 5:
                log.error(f"⚠️ [PTY] 读取输出失败: {e}")

    def write(self, data: str) -> bool:
        """
        写入数据

        Args:
            data: 要写入的数据

        Returns:
            True 如果写入成功
        """
        if self.state != PTYState.RUNNING or self.master_fd is None:
            return False

        try:
            os.write(self.master_fd, data.encode('utf-8'))
            return True
        except OSError as e:
            log.error(f"⚠️ [PTY] 写入失败: {e}")
            return False

    def write_line(self, line: str) -> bool:
        """
        写入一行数据（自动添加换行）

        Args:
            line: 要写入的行

        Returns:
            True 如果写入成功
        """
        return self.write(line + '\n')

    def resize(self, rows: int, cols: int) -> bool:
        """
        调整终端大小

        Args:
            rows: 行数
            cols: 列数

        Returns:
            True 如果调整成功
        """
        if self.state != PTYState.RUNNING or self.master_fd is None:
            return False

        try:
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            self.config.rows = rows
            self.config.cols = cols
            return True
        except Exception as e:
            log.error(f"⚠️ [PTY] 调整大小失败: {e}")
            return False

    def send_interrupt(self) -> bool:
        """
        发送中断信号 (Ctrl+C)

        Returns:
            True 如果发送成功
        """
        return self.write('\x03')  # ETX (End of Text)

    def send_eof(self) -> bool:
        """
        发送 EOF (Ctrl+D)

        Returns:
            True 如果发送成功
        """
        return self.write('\x04')  # EOT (End of Transmission)

    def is_alive(self) -> bool:
        """
        检查进程是否存活

        Returns:
            True 如果进程仍在运行
        """
        if self.pid is None:
            return False

        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid == 0:
                return True  # 进程仍在运行
            else:
                self.state = PTYState.CLOSED
                return False
        except ChildProcessError:
            return False

    def get_output_buffer(self) -> str:
        """
        获取累积的输出缓冲区

        Returns:
            累积的输出
        """
        return self._output_buffer

    def clear_output_buffer(self) -> None:
        """清空输出缓冲区"""
        self._output_buffer = ""

    def close(self) -> None:
        """
        关闭 PTY 会话

        注意：会等待进程结束
        """
        self._cleanup()
        log.info("👋 [PTY] 会话已关闭")

    def _cleanup(self) -> None:
        """清理资源"""
        self.state = PTYState.CLOSED

        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except OSError:
                pass
            self.slave_fd = None

        if self.pid is not None:
            try:
                # 如果进程还在运行，发送 SIGTERM
                os.kill(self.pid, 15)
                time.sleep(0.1)

                # 检查是否已终止
                pid, _ = os.waitpid(self.pid, os.WNOHANG)
                if pid == 0:
                    # 还没终止，强制杀死
                    os.kill(self.pid, 9)
                    os.waitpid(self.pid, 0)
            except (ChildProcessError, ProcessLookupError, PermissionError):
                pass
            self.pid = None

    # ==========================================
    # V2: 沙箱化规划支持
    # ==========================================

    # 结构化输出锚点标记
    RESULT_START_MARKER = "[AUTONOME_RESULT_START]"
    RESULT_END_MARKER = "[AUTONOME_RESULT_END]"

    async def launch_claude_code(
        self,
        workspace_path: str,
        prompt: str,
        mcp_config: Optional[dict] = None,
        timeout: int = 300,
        callback: Optional[Callable[[str], None]] = None,
        container_id: Optional[str] = None,
    ) -> str:
        """
        V2: 在 PTY 中启动 Claude Code 并流式读取输出

        支持两种模式：
        1. 本地 PTY 模式（默认）：直接在主机启动 Claude Code
        2. 容器模式（container_id 非空）：通过 docker exec 在容器内执行

        Args:
            workspace_path: 工作区路径（只读挂载）
            prompt: 发送给 Claude Code 的提示
            mcp_config: MCP 服务器配置
            timeout: 超时时间（秒）
            callback: 流式输出回调
            container_id: 可选的容器 ID，提供时通过 docker exec 执行

        Returns:
            完整的 Claude Code 输出
        """
        # V2: 容器模式 - 通过 docker exec 执行
        if container_id:
            return await self._launch_claude_code_in_container(
                container_id=container_id,
                workspace_path=workspace_path,
                prompt=prompt,
                mcp_config=mcp_config,
                timeout=timeout,
                callback=callback,
            )

        # 构建 Claude Code 命令
        claude_cmd = ["claude", "--print", prompt]

        # 设置环境变量
        env = os.environ.copy()
        if mcp_config:
            env["CLAUDE_MCP_CONFIG"] = json.dumps(mcp_config)

        # 启动 PTY 会话
        if not self.start_session(claude_cmd, cwd=workspace_path):
            raise RuntimeError("Failed to start Claude Code PTY session")

        # 流式读取输出直到完成或超时
        full_output = ""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if not self.is_alive():
                # 进程已结束，读取剩余输出
                remaining = self.read_output(timeout=1.0)
                if remaining:
                    full_output += remaining
                    if callback:
                        callback(remaining)
                break

            chunk = self.read_output(timeout=1.0)
            if chunk:
                full_output += chunk
                if callback:
                    callback(chunk)

            await asyncio.sleep(0.05)

        # 超时处理
        if self.is_alive():
            log.warning(f"⚠️ [PTY] Claude Code 超时 ({timeout}s)，发送中断")
            self.send_interrupt()
            await asyncio.sleep(1.0)
            if self.is_alive():
                self._cleanup()

        return full_output

    async def _launch_claude_code_in_container(
        self,
        container_id: str,
        workspace_path: str,
        prompt: str,
        mcp_config: Optional[dict] = None,
        timeout: int = 300,
        callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        V2: 在容器内通过 docker exec 启动 Claude Code

        使用容器预热池中的容器执行 Claude Code，
        实现沙箱化隔离规划。

        Args:
            container_id: 容器 ID
            workspace_path: 工作区路径（容器内路径）
            prompt: 发送给 Claude Code 的提示
            mcp_config: MCP 服务器配置
            timeout: 超时时间（秒）
            callback: 流式输出回调

        Returns:
            完整的 Claude Code 输出
        """
        # 构建 docker exec 命令
        exec_cmd = [
            "docker", "exec",
            "-i",
            container_id,
            "claude", "--print", prompt,
        ]

        # 设置环境变量（通过 -e 传递）
        env_vars = []
        if mcp_config:
            env_vars.extend(["-e", f"CLAUDE_MCP_CONFIG={json.dumps(mcp_config)}"])

        # 插入环境变量到 docker exec 命令
        if env_vars:
            exec_cmd = ["docker", "exec", "-i"] + env_vars + [container_id, "claude", "--print", prompt]

        log.info(f"🐳 [PTY] 在容器 {container_id[:12]} 中启动 Claude Code")

        # 启动 PTY 会话
        if not self.start_session(exec_cmd, cwd=workspace_path):
            raise RuntimeError(f"Failed to start Claude Code in container {container_id[:12]}")

        # 流式读取输出直到完成或超时
        full_output = ""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if not self.is_alive():
                remaining = self.read_output(timeout=1.0)
                if remaining:
                    full_output += remaining
                    if callback:
                        callback(remaining)
                break

            chunk = self.read_output(timeout=1.0)
            if chunk:
                full_output += chunk
                if callback:
                    callback(chunk)

            await asyncio.sleep(0.05)

        # 超时处理
        if self.is_alive():
            log.warning(f"⚠️ [PTY] 容器内 Claude Code 超时 ({timeout}s)，发送中断")
            self.send_interrupt()
            await asyncio.sleep(1.0)
            if self.is_alive():
                self._cleanup()

        log.info(f"[PTY.V2] 容器执行完成: container={container_id[:12]}, output_len={len(full_output)}, timed_out={self.is_alive()}")
        return full_output

    @classmethod
    def extract_structured_result(cls, raw_output: str) -> Optional[dict]:
        """
        V2: 从 PTY 输出中提取结构化 JSON 结果

        查找 [AUTONOME_RESULT_START] { JSON } [AUTONOME_RESULT_END] 标记，
        提取并解析其中的 JSON。

        Args:
            raw_output: Claude Code 的原始输出

        Returns:
            解析后的 dict，如果未找到标记则返回 None

        Raises:
            PTYExtractionError: 细粒度错误（标记未找到/JSON无效/JSON截断）
        """
        if not raw_output:
            raise PTYExtractionError(
                PTYExtractionError.ErrorType.EMPTY_OUTPUT,
                "PTY 输出为空"
            )

        # 1. ANSI 清洗
        cleaned = ANSICleaner.clean(raw_output)

        # 2. 查找锚点标记
        start_idx = cleaned.find(cls.RESULT_START_MARKER)
        end_idx = cleaned.find(cls.RESULT_END_MARKER)

        if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
            # 细粒度错误：区分"完全没标记"和"只有开始标记"（JSON被截断）
            if start_idx != -1 and end_idx == -1:
                raise PTYExtractionError(
                    PTYExtractionError.ErrorType.JSON_TRUNCATED,
                    "找到 [AUTONOME_RESULT_START] 但未找到 [AUTONOME_RESULT_END]，JSON 可能被截断",
                    raw_snippet=cleaned[start_idx:start_idx + 200]
                )
            raise PTYExtractionError(
                PTYExtractionError.ErrorType.MARKER_NOT_FOUND,
                "未找到结构化输出锚点标记",
                raw_snippet=cleaned[:200]
            )

        # 3. 提取 JSON 字符串
        json_str = cleaned[start_idx + len(cls.RESULT_START_MARKER):end_idx].strip()

        # 4. 解析 JSON（带修复）
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # 尝试 json_repair
            try:
                from json_repair import repair_json
                repaired = repair_json(json_str)
                return json.loads(repaired)
            except Exception:
                raise PTYExtractionError(
                    PTYExtractionError.ErrorType.JSON_INVALID,
                    f"JSON 解析失败: {str(e)}",
                    raw_snippet=json_str[:200]
                )

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False


def create_pty_session(command: list[str], cwd: Optional[str] = None) -> Optional[PTYManager]:
    """
    创建 PTY 会话的便捷函数

    Args:
        command: 要执行的命令列表
        cwd: 工作目录

    Returns:
        PTYManager 实例，如果失败则返回 None
    """
    manager = PTYManager()
    if manager.start_session(command, cwd):
        return manager
    return None
