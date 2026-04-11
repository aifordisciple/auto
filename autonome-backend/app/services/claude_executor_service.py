"""
Claude Code CLI 执行器服务

负责执行 Claude Code CLI，支持宿主机和容器两种执行模式。

执行流程：
1. 读取配置（从 settings.json）
2. 设置环境变量
3. 执行 claude CLI
4. 实时流输出
5. 解析输出生成战报

安全措施：
- 执行目录限制为项目目录
- 进程资源限制
- 超时控制
"""

import os
import json
import uuid
import asyncio
import re
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from dataclasses import dataclass, field

from app.core.logger import log
from app.services.claude_config_service import claude_config_service


# ==========================================
# 数据类定义
# ==========================================

@dataclass
class ClaudeExecutionResult:
    """Claude 执行结果"""
    success: bool
    exit_code: int
    output: str
    error: str
    execution_time_seconds: float
    battle_report: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClaudeSession:
    """Claude 执行会话"""
    session_id: str
    project_id: str
    user_id: int
    mode: str  # "host" or "container"
    status: str  # "pending", "running", "completed", "error"
    process: Optional[asyncio.subprocess.Process] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_buffer: List[str] = field(default_factory=list)


# ==========================================
# 战报解析器
# ==========================================

class ClaudeOutputParser:
    """
    Claude CLI 输出解析器

    从 Claude stream-json 输出中提取：
    - 文件操作记录（Write, Edit 工具调用）
    - 命令执行记录（Bash 工具调用）
    - 执行状态
    - 最终回复
    - 文件树
    """

    # 文件操作模式（用于非 stream-json 输出的后备解析）
    FILE_CREATED_PATTERN = re.compile(r'(?:创建|创建文件|write to|created?):\s*[`"]?([^\s`"]+)[`"]?', re.IGNORECASE)
    FILE_MODIFIED_PATTERN = re.compile(r'(?:修改|更新|编辑|modified|updated?):\s*[`"]?([^\s`"]+)[`"]?', re.IGNORECASE)
    FILE_READ_PATTERN = re.compile(r'(?:读取|read):?\s*[`"]?([^\s`"]+)[`"]?', re.IGNORECASE)
    COMMAND_PATTERN = re.compile(r'(?:执行|running|execute):?\s*`([^`]+)`', re.IGNORECASE)
    ERROR_PATTERN = re.compile(r'(?:error|错误|失败|failed|exception):?\s*(.+)', re.IGNORECASE)

    def parse(self, output: str) -> Dict[str, Any]:
        """
        解析 Claude 输出，生成战报

        Args:
            output: Claude CLI 的完整输出（stream-json 格式或普通文本）

        Returns:
            战报字典
        """
        # 尝试解析 stream-json 格式
        stream_events = self._parse_stream_json(output)

        if stream_events:
            return self._parse_from_stream_events(stream_events, output)
        else:
            # 后备：使用正则表达式解析
            return self._parse_with_regex(output)

    def _parse_stream_json(self, output: str) -> List[Dict[str, Any]]:
        """解析 stream-json 格式的输出"""
        events = []
        for line in output.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError:
                continue
        return events

    def _parse_from_stream_events(self, events: List[Dict[str, Any]], raw_output: str) -> Dict[str, Any]:
        """从 stream-json 事件中提取信息"""
        files_created = []
        files_modified = []
        files_read = []
        commands_executed = []
        tool_calls = []
        assistant_messages = []
        result_content = None
        session_info = {}

        for event in events:
            event_type = event.get("type", "")

            # 初始化信息
            if event_type == "system" and event.get("subtype") == "init":
                session_info = {
                    "session_id": event.get("session_id"),
                    "cwd": event.get("cwd"),
                    "model": event.get("model"),
                    "tools": event.get("tools", []),
                    "permission_mode": event.get("permissionMode")
                }

            # 助手消息
            elif event_type == "assistant":
                message = event.get("message", {})
                content_blocks = message.get("content", [])
                for block in content_blocks:
                    if block.get("type") == "text":
                        assistant_messages.append(block.get("text", ""))

            # 工具使用
            elif event_type == "tool_use":
                tool_name = event.get("name", "")
                tool_input = event.get("input", {})
                tool_calls.append({
                    "name": tool_name,
                    "input": tool_input
                })

                # 提取文件操作
                if tool_name == "Write":
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        files_created.append(file_path)
                elif tool_name == "Edit":
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        files_modified.append(file_path)
                elif tool_name == "Read":
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        files_read.append(file_path)
                elif tool_name == "Bash":
                    command = tool_input.get("command", "")
                    if command:
                        commands_executed.append(command)

            # 工具结果
            elif event_type == "tool_result":
                # 记录工具执行结果
                pass

            # 最终结果
            elif event_type == "result":
                result_content = event.get("result", "")
                assistant_messages.append(result_content)

        # 去重
        files_created = list(set(files_created))
        files_modified = list(set(files_modified))
        files_read = list(set(files_read))

        # 生成文件树
        all_files = files_created + files_modified + files_read
        file_tree = self._generate_file_tree(all_files)

        # 合并助手消息
        final_message = "\n\n".join(assistant_messages) if assistant_messages else result_content or ""

        return {
            "success": True,
            "files_created": files_created,
            "files_modified": files_modified,
            "files_read": files_read,
            "commands_executed": commands_executed,
            "tool_calls": tool_calls,
            "file_tree": file_tree,
            "session_info": session_info,
            "summary": final_message[:500] if final_message else "",
            "output_preview": raw_output[:2000] if len(raw_output) > 2000 else raw_output,
            "assistant_message": final_message
        }

    def _parse_with_regex(self, output: str) -> Dict[str, Any]:
        """使用正则表达式解析非 stream-json 输出"""
        files_created = list(set(self.FILE_CREATED_PATTERN.findall(output)))
        files_modified = list(set(self.FILE_MODIFIED_PATTERN.findall(output)))
        commands_executed = list(set(self.COMMAND_PATTERN.findall(output)))
        errors = self.ERROR_PATTERN.findall(output)

        output_lines = output.strip().split('\n')
        summary_lines = [line for line in output_lines if line.strip() and not line.startswith('│')][:10]
        summary = '\n'.join(summary_lines)[:500]

        success = len(errors) == 0 and ('完成' in output or 'completed' in output.lower() or 'success' in output.lower())

        return {
            "success": success,
            "files_created": files_created,
            "files_modified": files_modified,
            "commands_executed": commands_executed,
            "errors": errors,
            "summary": summary,
            "output_preview": output[:1000] if len(output) > 1000 else output,
            "file_tree": self._generate_file_tree(files_created + files_modified)
        }

    def _generate_file_tree(self, files: List[str]) -> Dict[str, Any]:
        """生成文件树结构"""
        if not files:
            return {}

        tree = {}
        for file_path in files:
            # 标准化路径
            parts = file_path.strip('/').split('/')
            current = tree
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # 文件
                    current[part] = {"type": "file", "path": file_path}
                else:
                    # 目录
                    if part not in current:
                        current[part] = {"type": "directory", "children": {}}
                    current = current[part]["children"]

        return tree


# ==========================================
# 执行器服务
# ==========================================

class ClaudeExecutorService:
    """
    Claude Code CLI 执行器服务

    功能：
    - 管理执行会话
    - 宿主机执行模式
    - 容器执行模式
    - 实时流输出
    - 战报生成
    """

    def __init__(self):
        self.config_service = claude_config_service
        self.parser = ClaudeOutputParser()
        self.active_sessions: Dict[str, ClaudeSession] = {}

    def create_session(
        self,
        project_id: str,
        user_id: int,
        mode: str = "host"
    ) -> ClaudeSession:
        """
        创建新的执行会话

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            mode: 执行模式 "host" 或 "container"

        Returns:
            ClaudeSession 对象
        """
        session_id = f"claude_{uuid.uuid4().hex[:12]}"

        session = ClaudeSession(
            session_id=session_id,
            project_id=project_id,
            user_id=user_id,
            mode=mode,
            status="pending"
        )

        self.active_sessions[session_id] = session
        log.info(f"[ClaudeExecutor] 创建会话: {session_id}, mode={mode}")

        return session

    async def execute(
        self,
        session: ClaudeSession,
        prompt: str,
        output_callback: Optional[Callable[[str], None]] = None,
        resume_session_id: Optional[str] = None
    ) -> ClaudeExecutionResult:
        """
        执行 Claude Code

        Args:
            session: 执行会话
            prompt: 用户需求/提示
            output_callback: 实时输出回调函数
            resume_session_id: 要恢复的 Claude Code 会话 ID（用于 --resume）

        Returns:
            ClaudeExecutionResult 执行结果
        """
        session.status = "running"
        session.started_at = datetime.utcnow()

        start_time = datetime.utcnow()

        try:
            if session.mode == "host":
                result = await self._execute_on_host(session, prompt, output_callback, resume_session_id)
            else:
                result = await self._execute_in_container(session, prompt, output_callback, resume_session_id)

            session.status = "completed" if result.success else "error"
            session.completed_at = datetime.utcnow()

            return result

        except Exception as e:
            log.error(f"[ClaudeExecutor] 执行失败: {e}")
            session.status = "error"
            session.completed_at = datetime.utcnow()

            return ClaudeExecutionResult(
                success=False,
                exit_code=-1,
                output="",
                error=str(e),
                execution_time_seconds=(datetime.utcnow() - start_time).total_seconds()
            )

    async def _execute_on_host(
        self,
        session: ClaudeSession,
        prompt: str,
        output_callback: Optional[Callable[[str], None]] = None,
        resume_session_id: Optional[str] = None
    ) -> ClaudeExecutionResult:
        """
        在宿主机上执行 Claude CLI

        Args:
            session: 执行会话
            prompt: 用户需求
            output_callback: 输出回调
            resume_session_id: 要恢复的会话 ID

        Returns:
            执行结果
        """
        start_time = datetime.utcnow()

        # 获取项目目录
        project_dir = self._get_project_dir(session.project_id)
        if not project_dir.exists():
            return ClaudeExecutionResult(
                success=False,
                exit_code=-1,
                output="",
                error=f"项目目录不存在: {project_dir}",
                execution_time_seconds=0
            )

        # 获取环境变量
        env_vars = self.config_service.get_env_vars()

        # 构建执行环境
        execution_env = os.environ.copy()
        execution_env.update(env_vars)

        # 构建命令
        # claude -p "prompt" --output-format stream-json --verbose
        # 或 claude --resume <session_id> -p "prompt" --output-format stream-json --verbose
        # 权限通过 settings.json 中的 permissions.defaultMode: bypassPermissions 配置
        cmd = ["claude"]

        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])
            log.info(f"[ClaudeExecutor] 恢复会话: {resume_session_id}")

        cmd.extend([
            "-p", prompt,
            "--output-format", "stream-json",
            "--verbose"
        ])

        log.info(f"[ClaudeExecutor] 执行命令: claude {'--resume ' + resume_session_id if resume_session_id else ''} -p '...' --output-format stream-json --verbose")
        log.info(f"[ClaudeExecutor] 工作目录: {project_dir}")

        try:
            # 创建子进程
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
                env=execution_env
            )

            session.process = process

            # 收集输出
            stdout_buffer = []
            stderr_buffer = []

            # 并发读取 stdout 和 stderr
            async def read_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if line_str:
                        stdout_buffer.append(line_str)
                        session.output_buffer.append(line_str)

                        # 先发送原始输出（保持终端显示）
                        if output_callback:
                            await self._safe_callback(output_callback, line_str)

                        # 解析 stream-json 事件并发送结构化日志
                        parsed_event = self._parse_stream_event(line_str)
                        if parsed_event and output_callback:
                            # 发送结构化事件（JSON 格式，带有特殊标记）
                            event_msg = json.dumps(parsed_event, ensure_ascii=False)
                            await self._safe_callback(output_callback, f"__STRUCTURED_EVENT__:{event_msg}")

            async def read_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if line_str:
                        stderr_buffer.append(line_str)
                        log.debug(f"[ClaudeExecutor] stderr: {line_str}")

            # 并发执行
            await asyncio.gather(read_stdout(), read_stderr())

            # 等待进程结束
            exit_code = await process.wait()

            # 解析输出
            full_output = '\n'.join(stdout_buffer)
            full_error = '\n'.join(stderr_buffer)

            # 生成战报
            battle_report = self.parser.parse(full_output)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            log.info(f"[ClaudeExecutor] 执行完成: exit_code={exit_code}, time={execution_time:.1f}s")

            return ClaudeExecutionResult(
                success=exit_code == 0,
                exit_code=exit_code,
                output=full_output,
                error=full_error,
                execution_time_seconds=execution_time,
                battle_report=battle_report
            )

        except FileNotFoundError:
            return ClaudeExecutionResult(
                success=False,
                exit_code=-1,
                output="",
                error="Claude CLI 未安装。请运行: npm install -g @anthropic-ai/claude-code",
                execution_time_seconds=0
            )
        except Exception as e:
            log.error(f"[ClaudeExecutor] 宿主机执行错误: {e}")
            return ClaudeExecutionResult(
                success=False,
                exit_code=-1,
                output="",
                error=str(e),
                execution_time_seconds=(datetime.utcnow() - start_time).total_seconds()
            )

    async def _execute_in_container(
        self,
        session: ClaudeSession,
        prompt: str,
        output_callback: Optional[Callable[[str], None]] = None,
        resume_session_id: Optional[str] = None
    ) -> ClaudeExecutionResult:
        """
        在 Docker 容器内执行 Claude CLI

        Args:
            session: 执行会话
            prompt: 用户需求
            output_callback: 输出回调
            resume_session_id: 要恢复的会话 ID

        Returns:
            执行结果
        """
        start_time = datetime.utcnow()

        # 获取项目目录
        project_dir = self._get_project_dir(session.project_id)

        # 获取环境变量
        env_vars = self.config_service.get_env_vars()

        # 构建环境变量标志
        env_flags = []
        for key, value in env_vars.items():
            env_flags.extend(["-e", f"{key}={value}"])

        # 确保 /opt/conda/bin 在 PATH 中（claude CLI 安装位置）
        env_flags.extend(["-e", "PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"])

        # 挂载配置文件
        settings_path = self.config_service.get_settings_file_path()

        # 获取 conda 环境路径（使用环境变量，与 HOST_UPLOAD_DIR 模式一致）
        # 宿主机路径通过环境变量传入，因为容器内的路径解析不正确
        host_conda_dir = os.environ.get(
            "HOST_CONDA_DIR",
            "/opt/data1/public/software/systools/autonome/autonome_conda"
        )

        # 构建 Docker run 命令
        # 注意：autonome-tool-env 是 amd64 镜像，需要指定平台
        # Claude CLI 期望配置在 ~/.claude.json，同时需要 ~/.claude/ 目录存储项目数据
        # 使用 --user 以非 root 用户运行，允许 bypassPermissions 模式

        # 构建 claude 命令部分
        claude_cmd = ["claude"]
        if resume_session_id:
            claude_cmd.extend(["--resume", resume_session_id])
            log.info(f"[ClaudeExecutor] 容器执行恢复会话: {resume_session_id}")
        claude_cmd.extend(["-p", prompt, "--output-format", "stream-json", "--verbose"])

        cmd = [
            "docker", "run", "--rm",
            "--platform", "linux/amd64",  # 指定平台，因为镜像是 amd64
            "--user", "1000:1000",  # 以非 root 用户运行，允许绕过权限模式
            "-e", "HOME=/home/user",  # 设置 HOME 目录
            "-v", f"{project_dir}:/app/workspace",
            "-v", f"{settings_path}:/home/user/.claude.json",  # 配置文件挂载到用户目录
            "-v", f"{settings_path.parent}:/home/user/.claude",  # .claude 目录
            "-v", f"{host_conda_dir}:/opt/conda",  # 挂载 conda 环境（包含 claude CLI）
            "-w", "/app/workspace",
            *env_flags,
            "autonome-tool-env",  # 使用现有镜像
            *claude_cmd
        ]

        log.info(f"[ClaudeExecutor] 容器执行: docker run ...")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            session.process = process

            # 收集输出
            stdout_buffer = []
            stderr_buffer = []

            async def read_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if line_str:
                        stdout_buffer.append(line_str)
                        session.output_buffer.append(line_str)

                        # 先发送原始输出
                        if output_callback:
                            await self._safe_callback(output_callback, line_str)

                        # 解析 stream-json 事件并发送结构化日志
                        parsed_event = self._parse_stream_event(line_str)
                        if parsed_event and output_callback:
                            event_msg = json.dumps(parsed_event, ensure_ascii=False)
                            await self._safe_callback(output_callback, f"__STRUCTURED_EVENT__:{event_msg}")

            async def read_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if line_str:
                        stderr_buffer.append(line_str)

            await asyncio.gather(read_stdout(), read_stderr())

            exit_code = await process.wait()

            full_output = '\n'.join(stdout_buffer)
            full_error = '\n'.join(stderr_buffer)

            battle_report = self.parser.parse(full_output)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            return ClaudeExecutionResult(
                success=exit_code == 0,
                exit_code=exit_code,
                output=full_output,
                error=full_error,
                execution_time_seconds=execution_time,
                battle_report=battle_report
            )

        except Exception as e:
            log.error(f"[ClaudeExecutor] 容器执行错误: {e}")
            return ClaudeExecutionResult(
                success=False,
                exit_code=-1,
                output="",
                error=str(e),
                execution_time_seconds=(datetime.utcnow() - start_time).total_seconds()
            )

    async def _safe_callback(self, callback: Callable[[str], None], data: str) -> None:
        """安全调用回调函数"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)
        except Exception as e:
            log.error(f"[ClaudeExecutor] 回调错误: {e}")

    def _get_project_dir(self, project_id: str) -> Path:
        """获取项目目录路径"""
        from app.core.config import settings

        host_upload_dir = os.environ.get("HOST_UPLOAD_DIR", settings.UPLOAD_DIR)
        return Path(host_upload_dir) / f"project_{project_id}"

    async def stop_session(self, session_id: str) -> bool:
        """
        停止执行会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功停止
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        if session.process and session.status == "running":
            try:
                session.process.terminate()
                await asyncio.wait_for(session.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                session.process.kill()
            except Exception as e:
                log.error(f"[ClaudeExecutor] 停止会话失败: {e}")

        session.status = "stopped"
        session.completed_at = datetime.utcnow()
        log.info(f"[ClaudeExecutor] 会话已停止: {session_id}")

        return True

    def get_session(self, session_id: str) -> Optional[ClaudeSession]:
        """获取会话"""
        return self.active_sessions.get(session_id)

    def cleanup_session(self, session_id: str) -> None:
        """清理会话"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            log.info(f"[ClaudeExecutor] 会话已清理: {session_id}")

    # ==========================================
    # Stream-JSON 事件解析
    # ==========================================

    def _parse_stream_event(self, line: str) -> Optional[Dict[str, Any]]:
        """
        解析 Claude CLI stream-json 输出事件，返回结构化日志

        支持的事件类型:
        - system (init): 会话初始化信息
        - assistant: 助手消息（包含思考过程）
        - tool_use: 工具调用
        - tool_result: 工具执行结果

        Args:
            line: 单行 JSON 输出

        Returns:
            结构化日志字典，无法解析返回 None
        """
        try:
            event = json.loads(line)
            event_type = event.get("type", "")

            # 会话初始化
            if event_type == "system" and event.get("subtype") == "init":
                return {
                    "type": "session_info",
                    "model": event.get("model"),
                    "tools": event.get("tools", []),
                    "cwd": event.get("cwd"),
                    "permission_mode": event.get("permissionMode"),
                    "session_id": event.get("session_id")
                }

            # 工具调用
            elif event_type == "tool_use":
                tool_name = event.get("name", "")
                tool_input = event.get("input", {})
                return {
                    "type": "tool_call",
                    "name": tool_name,
                    "input": tool_input,
                    "call_id": event.get("id"),
                    # 提取关键参数用于预览
                    "input_preview": self._get_tool_input_preview(tool_name, tool_input)
                }

            # 工具执行结果
            elif event_type == "tool_result":
                content = event.get("content", "")
                # 截取输出预览
                if isinstance(content, list):
                    # content 可能是列表格式
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            text_parts.append(item)
                    preview = "\n".join(text_parts)[:300]
                else:
                    preview = str(content)[:300] if content else ""

                return {
                    "type": "tool_result",
                    "call_id": event.get("tool_use_id"),
                    "status": "error" if event.get("is_error") else "success",
                    "output_preview": preview
                }

            # 助手消息（思考过程）
            elif event_type == "assistant":
                message = event.get("message", {})
                content_blocks = message.get("content", [])
                # 提取文本类型的消息
                text_blocks = [
                    b.get("text", "")
                    for b in content_blocks
                    if b.get("type") == "text" and b.get("text", "").strip()
                ]
                if text_blocks:
                    return {
                        "type": "thinking",
                        "content": "\n".join(text_blocks)
                    }

            # 最终结果
            elif event_type == "result":
                result_content = event.get("result", "")
                return {
                    "type": "result",
                    "content": result_content[:500] if result_content else "",
                    "cost_usd": event.get("cost_usd"),
                    "duration_ms": event.get("duration_ms"),
                    "is_error": event.get("is_error", False)
                }

            return None

        except json.JSONDecodeError:
            return None

    def _get_tool_input_preview(self, tool_name: str, tool_input: Dict) -> str:
        """
        获取工具输入的预览字符串

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数

        Returns:
            预览字符串
        """
        if tool_name == "Read":
            return tool_input.get("file_path", "")[:100]
        elif tool_name == "Write":
            return tool_input.get("file_path", "")[:100]
        elif tool_name == "Edit":
            return tool_input.get("file_path", "")[:100]
        elif tool_name == "Bash":
            return tool_input.get("command", "")[:100]
        else:
            # 其他工具，返回 JSON 预览
            return json.dumps(tool_input, ensure_ascii=False)[:100]


# 全局单例
claude_executor_service = ClaudeExecutorService()