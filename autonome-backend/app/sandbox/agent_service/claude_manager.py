"""
Claude Code 进程管理器

负责:
- spawn Claude Code 子进程 (--resume 模式)
- 解析 stdout JSONL → 事件流
- 超时控制与优雅终止
- 系统提示注入 (角色定义 + 工具说明)
"""

import os
import subprocess
import signal
import time
import json
from typing import Optional, Callable

from app.sandbox.agent_service.event_types import (
    AgentEvent,
    StatusEvent,
    ErrorEvent,
    AgentStatus,
)
from app.sandbox.agent_service.stream_parser import ClaudeStreamParser


CLAUDE_CODE_BIN = "claude"
DEFAULT_TIMEOUT_SECONDS = 600
WORKSPACE_DIR = "/workspace"

SYSTEM_PROMPT = """你是 Autonome 生物信息学平台的 AI Agent, 运行在 Docker 沙箱环境中。

## 你的角色
你是生物信息学数据分析专家, 帮助用户完成:
- 数据分析方案设计
- 代码编写与调试
- 结果解读与可视化建议

## 工作流程
1. **理解需求**: 充分理解用户的分析需求, 必要时提出澄清问题
2. **检索技能**: 使用 skill_search 工具查找系统中已有的分析技能
3. **制定方案**: 生成分析计划, 包含步骤、方法、预期产出
4. **确认执行**: 等待用户确认方案后再生成代码
5. **执行任务**:
   - 轻量任务(预计 < 2min): 使用 execute_sandbox 直接在沙箱执行
   - 重型任务(预计 > 2min): 使用 submit_heavy_task 提交到 Celery 分布式执行

## 可用工具
- skill_search(query): 搜索系统中的生信分析技能
- execute_sandbox(command, timeout): 在沙箱中直接执行命令
- submit_heavy_task(skill_id, code, params): 提交重型任务到分布式队列
- read_file(path): 读取 /workspace 下的文件
- write_file(path, content): 写入文件到 /workspace

## 环境
- 工作目录: /workspace (读写)
- 技能目录: /app/skills (只读)
- Conda 环境: /opt/conda (只读, 500+ 生信包)
- 可用: Python 3.11, R 4.x

## 行为准则
- 方案必须先确认再执行
- 用中文沟通
- 代码注释用中文
- 优先复用系统中已有的技能, 避免重复造轮子
"""


class ClaudeManager:
    """Claude Code 进程管理器"""

    def __init__(
        self,
        api_key: str,
        api_base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._model = model
        self._timeout = timeout
        self._process: Optional[subprocess.Popen] = None
        self._parser = ClaudeStreamParser()

    def run_with_prompt(
        self,
        prompt: str,
        session_id: str,
        on_event: Callable[[AgentEvent], None],
    ) -> int:
        """
        运行 Claude Code 并处理输出

        Args:
            prompt: 用户消息
            session_id: Claude Code --resume session id
            on_event: 每解析出一个事件时的回调

        Returns:
            进程退出码
        """
        full_prompt = f"{SYSTEM_PROMPT}\n\n---\n\n用户消息:\n{prompt}"

        cmd = [
            CLAUDE_CODE_BIN,
            "-p", full_prompt,
            "--output-format", "stream-json",
            "--resume", session_id,
            "--permission-mode", "acceptEdits",
            "--max-turns", "50",
        ]

        if self._model:
            cmd.extend(["--model", self._model])

        env = os.environ.copy()
        if self._api_key:
            env["ANTHROPIC_API_KEY"] = self._api_key
        if self._api_base_url:
            env["ANTHROPIC_BASE_URL"] = self._api_base_url

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=WORKSPACE_DIR,
        )

        on_event(StatusEvent(status=AgentStatus.THINKING.value, message="Claude Code 启动"))

        returncode = None
        start_time = time.time()

        try:
            for line in self._process.stdout:
                line = line.strip()
                if not line:
                    continue
                event = self._parser.feed_line(line)
                if event is not None:
                    on_event(event)

                if time.time() - start_time > self._timeout:
                    self.kill()
                    on_event(ErrorEvent(message="执行超时", code="TIMEOUT"))
                    break

            self._process.wait(timeout=10)
            returncode = self._process.returncode

        except Exception as e:
            on_event(ErrorEvent(message=str(e), code="EXECUTION_ERROR"))
            self.kill()
        finally:
            if self._process and self._process.stderr:
                try:
                    stderr = self._process.stderr.read()
                    if stderr.strip():
                        on_event(ErrorEvent(message=stderr[:500], code="STDERR"))
                except Exception:
                    pass
            on_event(StatusEvent(status=AgentStatus.IDLE.value))

        return returncode if returncode is not None else -1

    def kill(self) -> None:
        """终止 Claude Code 进程"""
        if self._process and self._process.poll() is None:
            try:
                self._process.send_signal(signal.SIGTERM)
                self._process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    self._process.kill()
                except Exception:
                    pass

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None
