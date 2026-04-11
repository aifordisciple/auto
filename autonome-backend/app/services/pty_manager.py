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
import fcntl
import struct
import termios
from typing import Tuple, Optional, Callable
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

    def __del__(self):
        """析构函数，确保资源被释放"""
        self._cleanup()

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
