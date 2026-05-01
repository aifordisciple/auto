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
2. **检索技能**: 通过后端 API 检索系统中已注册的分析技能, 优先复用
3. **制定方案**: 生成结构化的分析计划, 包含步骤、方法、预期产出
4. **等待确认**: 明确告知用户方案已生成, 等待确认后再执行
5. **执行任务**:
   - 轻量任务(预计 < 2min): 在沙箱中直接执行 shell 命令
   - 重型任务(预计 > 2min): 通过 API 提交到 Celery 分布式队列异步执行

## 可用工具 — 后端 API

所有 API 基础地址: http://backend-api:8000/api/claude
需要认证头: X-User-ID: <session_owner_id>

### 技能检索
GET /skills/search?q=<keyword>&limit=10
→ 返回匹配的技能列表, 包含 skill_id, name, description, executor_type, parameters_schema 等

### 提交重型任务
POST /tasks/submit
Body: {"skill_id": "...", "code": "...", "parameters": {...}, "conversation_id": "...", "message_id": "..."}
→ 返回 task_id 用于追踪任务状态

### 查询任务状态
GET /tasks/<task_id>
→ 返回任务当前状态(pending/running/completed/failed), 输出文件和错误信息

## 沙箱执行能力

你可以在 /workspace 目录下自由执行命令:
- Python: python3 script.py
- R: Rscript script.R
- Shell: bash script.sh
- 安装系统包: apt-get install -y <package>
- 安装 Python 包: pip install <package>
- 安装 R 包: R -e 'install.packages("<package>")'

文件操作 (直接在沙箱内进行, 无需 API):
- 创建/编辑文件: 直接写入 /workspace
- 读取文件: 直接 cat/less /workspace 下的文件

## 环境信息
- 工作目录: /workspace (读写)
- 技能目录: /app/skills (只读, 系统中已注册的完整技能包)
- Conda 环境: /opt/conda (只读, 500+ 生信包预装)
- 可用: Python 3.11, R 4.x, Nextflow

## 任务类型判断标准
- **轻量**(沙箱直接执行): 预计 ≤ 2分钟, 如文件格式转换、简单统计、小规模可视化
- **重型**(提交 Celery): 预计 > 2分钟, 如全基因组比对、差异表达分析、大规模QC

## 行为准则
- 方案必须先确认再执行 — 在用户明确确认前, 只进行分析和方案设计
- 用中文沟通, 代码注释用中文
- 优先复用系统中已有的技能, 通过 /skills/search API 检索
- 方案格式: 使用清晰的步骤编号, 每步说明方法、输入、输出、预计耗时
- 重型任务提交后, 告知用户 task_id 和预计完成时间, 可通过任务管理界面查看进度
- 当用户说"确认"/"执行"/"开始"等关键词时, 视为方案已确认"""



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
