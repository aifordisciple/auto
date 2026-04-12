"""
沙箱规划节点 (Sandbox Planner Node)

V2 架构核心组件：通过 PTY 拉起 Claude Code，结合 MCP 检索技能，
从 Claude Code 输出中提取 [AUTONOME_RESULT_START] 包裹的 JSON 结果。

工作流程：
1. 从 Warm Pool 获取容器
2. 启动 PTY 会话
3. Claude Code + MCP 检索技能
4. 提取 [AUTONOME_RESULT_START] JSON
5. 销毁容器

V2 增强：
- plan() 返回 StrategyCard 兼容结构
- event_callback 支持实时 SSE 事件推送
- 失败时回退到 super_executor_v4
- 环境变量 AUTONOME_USE_SANDBOX_PLANNER 门控
- 2 次静默重试自愈（M5.2 前置）
"""

import os
import json
import asyncio
import time
from typing import Annotated, Optional, Callable

from langchain_core.messages import BaseMessage, AIMessage
from langchain_openai import ChatOpenAI

from app.core.logger import log
from app.agent.schemas import IntentClassification, StrategyCard
from app.services.pty_manager import PTYManager, PTYConfig, PTYResult, PTYExtractionError
from app.utils.result_extractor import ResultExtractor
from app.mcp.autonome_skills_mcp import get_mcp_server


# 环境变量门控
USE_SANDBOX_PLANNER = os.environ.get("AUTONOME_USE_SANDBOX_PLANNER", "false").lower() == "true"
SANDBOX_MAX_RETRIES = int(os.environ.get("AUTONOME_SANDBOX_MAX_RETRIES", "2"))
SANDBOX_TIMEOUT = int(os.environ.get("AUTONOME_SANDBOX_TIMEOUT", "120"))


# 沙箱规划 Prompt
SANDBOX_PLANNER_PROMPT = """你是一个生信系统的规划专家。

【任务】
分析用户需求，使用可用工具规划分析步骤。

【用户需求】
{user_message}

【工作区信息】
{workspace_info}

【可用工具】
1. scan_workspace - 扫描工作区目录
2. peek_tabular_data - 预览数据表头
3. search_skills - 搜索技能（通过 MCP 调用）
4. execute_python_code - 执行 Python 代码

{retry_context}

【输出要求】
完成规划后，必须在 PTY 中输出以下格式的结果：

[AUTONOME_RESULT_START]
{{
  "plan": "简要规划描述",
  "skill_id": "匹配的技能ID（如有）",
  "tool_id": "使用的工具ID",
  "title": "策略卡片标题",
  "description": "策略卡片描述",
  "parameters": {{}},
  "steps": [
    {{
      "task_id": "task_1",
      "name": "任务名称",
      "tool": "使用的工具",
      "instruction": "具体执行指令"
    }}
  ],
  "estimated_time": "预计时间"
}}
[AUTONOME_RESULT_END]

【规划原则】
1. 颗粒度要细：每个任务应该是一个独立的可执行单元
2. 探针先行：先探查数据再规划
3. 合理依赖：确保任务之间的依赖关系清晰
4. 优先匹配已有技能：如果 search_skills 找到匹配的技能，优先使用技能而非 Live Coding
"""


class SandboxPlanner:
    """
    沙箱规划器

    整合 PTY Manager + MCP + Result Extractor
    V2: 支持 event_callback、重试、回退
    """

    def __init__(self):
        self.mcp = get_mcp_server()
        self.pty: Optional[PTYManager] = None

    async def plan(
        self,
        user_message: str,
        workspace_info: str,
        workspace_path: Optional[str] = None,
        container_id: Optional[str] = None,
        timeout: int = None,
        event_callback: Optional[Callable[[str, dict], None]] = None,
        max_retries: int = None,
    ) -> PTYResult:
        """
        V2: 执行沙箱规划（带重试和事件回调）

        流程：
        1. 从 Warm Pool 提取容器（或使用指定容器）
        2. 只读挂载用户工作区
        3. PTY 启动 Claude Code
        4. Claude Code 探查数据 + 调用 MCP search_skills
        5. Claude Code 输出 [AUTONOME_RESULT_START] JSON
        6. 提取 JSON，销毁容器
        7. 失败时重试（最多 max_retries 次）
        8. 异步补充新容器入池

        Args:
            user_message: 用户消息
            workspace_info: 工作区信息
            workspace_path: 工作区路径（用于只读挂载）
            container_id: 可选的容器 ID（从 Warm Pool 获取）
            timeout: 超时时间（秒），None 使用环境变量默认值
            event_callback: 事件回调函数，接收 (event_type, event_data)
            max_retries: 最大重试次数，None 使用环境变量默认值

        Returns:
            PTYResult: 结构化结果（包含 success/structured_data/error 等）
        """
        timeout = timeout or SANDBOX_TIMEOUT
        max_retries = max_retries if max_retries is not None else SANDBOX_MAX_RETRIES

        last_error = None
        last_error_type = None

        for attempt in range(max_retries + 1):
            attempt_start = time.time()

            # 发出规划状态事件
            if event_callback:
                event_callback("planner_status", {
                    "phase": "planning",
                    "attempt": attempt + 1,
                    "max_attempts": max_retries + 1,
                    "message": f"正在规划（第 {attempt + 1} 次尝试）..."
                })

            # 构建重试上下文
            retry_context = ""
            if attempt > 0 and last_error:
                retry_context = f"""【重试上下文】
这是第 {attempt + 1} 次尝试。前一次尝试失败，错误信息：
{last_error}

请根据错误信息调整你的规划策略。"""

            prompt = SANDBOX_PLANNER_PROMPT.format(
                user_message=user_message,
                workspace_info=workspace_info or "无",
                retry_context=retry_context
            )

            try:
                self.pty = PTYManager(PTYConfig(timeout=5.0))

                # 获取 MCP 配置
                mcp_config = None
                try:
                    from app.mcp.autonome_skills_mcp import generate_claude_mcp_config
                    mcp_config = generate_claude_mcp_config()
                except Exception:
                    pass

                # 定义流式回调：将 PTY 输出转发为 planner_log 事件
                def pty_stream_callback(chunk: str):
                    if event_callback and chunk:
                        event_callback("planner_log", {
                            "source": "claude_code",
                            "chunk": chunk[:500],  # 限制单块大小
                            "attempt": attempt + 1
                        })

                # 每次尝试递增超时
                attempt_timeout = timeout + attempt * 30

                output = await self.pty.launch_claude_code(
                    workspace_path=workspace_path or os.getcwd(),
                    prompt=prompt,
                    mcp_config=mcp_config,
                    timeout=attempt_timeout,
                    callback=pty_stream_callback,
                    container_id=container_id,
                )

                # 提取结构化结果
                try:
                    result = PTYManager.extract_structured_result(output)
                    if result:
                        execution_time_ms = int((time.time() - attempt_start) * 1000)

                        # 转换为 StrategyCard 兼容结构
                        strategy_card = self._to_strategy_card(result, user_message)

                        if event_callback:
                            event_callback("planner_result", {
                                "success": True,
                                "plan": result.get("plan", ""),
                                "skill_id": result.get("skill_id", ""),
                                "steps_count": len(result.get("steps", [])),
                                "execution_time_ms": execution_time_ms,
                                "attempt": attempt + 1
                            })

                        log.info(f"✅ [SandboxPlanner] 成功提取结构化结果（第 {attempt + 1} 次尝试）")
                        return PTYResult(
                            success=True,
                            raw_output=output,
                            structured_data=strategy_card,
                            execution_time_ms=execution_time_ms
                        )

                except PTYExtractionError as e:
                    last_error = f"{e.error_type.value}: {e.message}"
                    last_error_type = e.error_type.value
                    log.warning(f"⚠️ [SandboxPlanner] 提取失败（尝试 {attempt + 1}）: {e.message}")

                    # 回退：尝试 ResultExtractor
                    try:
                        fallback_result = ResultExtractor.extract(output)
                        if fallback_result:
                            execution_time_ms = int((time.time() - attempt_start) * 1000)
                            strategy_card = self._to_strategy_card(fallback_result, user_message)
                            log.info(f"✅ [SandboxPlanner] 通过 ResultExtractor 提取结果")
                            return PTYResult(
                                success=True,
                                raw_output=output,
                                structured_data=strategy_card,
                                execution_time_ms=execution_time_ms
                            )
                    except Exception:
                        pass

            except Exception as e:
                last_error = str(e)
                last_error_type = "pty_error"
                log.error(f"❌ [SandboxPlanner] PTY 执行失败（尝试 {attempt + 1}）: {e}")

            finally:
                if self.pty:
                    self.pty.close()
                    self.pty = None

            # 重试前等待（指数退避）
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 1s, 2s
                log.info(f"🔄 [SandboxPlanner] 等待 {wait_time}s 后重试...")
                if event_callback:
                    event_callback("planner_status", {
                        "phase": "retrying",
                        "attempt": attempt + 1,
                        "max_attempts": max_retries + 1,
                        "wait_seconds": wait_time,
                        "last_error": last_error[:200] if last_error else "",
                        "message": f"第 {attempt + 1} 次尝试失败，{wait_time}s 后重试..."
                    })
                await asyncio.sleep(wait_time)

        # 所有重试耗尽
        total_time_ms = int((time.time() - attempt_start) * 1000) if 'attempt_start' in dir() else 0
        log.error(f"❌ [SandboxPlanner] 所有 {max_retries + 1} 次尝试均失败")

        if event_callback:
            event_callback("planner_result", {
                "success": False,
                "error": last_error,
                "error_type": last_error_type,
                "attempts": max_retries + 1
            })

        return PTYResult(
            success=False,
            error=f"规划失败（{max_retries + 1} 次尝试）: {last_error}",
            error_type=last_error_type,
            execution_time_ms=total_time_ms
        )

    def _to_strategy_card(self, plan_result: dict, user_message: str) -> dict:
        """
        将沙箱规划结果转换为 StrategyCard 兼容结构

        Args:
            plan_result: 沙箱规划输出的原始 dict
            user_message: 原始用户消息

        Returns:
            StrategyCard 兼容的 dict
        """
        return {
            "title": plan_result.get("title", plan_result.get("plan", "分析规划")),
            "description": plan_result.get("description", plan_result.get("plan", "")),
            "task_summary": plan_result.get("plan", ""),
            "tool_id": plan_result.get("tool_id", plan_result.get("skill_id", "sandbox_planner")),
            "parameters": plan_result.get("parameters", {}),
            "steps": [
                step.get("instruction", step.get("name", ""))
                for step in plan_result.get("steps", [])
            ],
            "estimated_time": plan_result.get("estimated_time", "约 1 分钟"),
            "skill_id": plan_result.get("skill_id", ""),
            # 保留原始规划数据供前端解析
            "_raw_plan": plan_result,
        }

    async def search_skills_via_mcp(self, query: str, limit: int = 5) -> list:
        """
        通过 MCP 搜索技能

        Args:
            query: 搜索查询
            limit: 结果数量限制

        Returns:
            技能列表
        """
        return self.mcp.search_skills(query, limit=limit)


# 全局规划器实例
_sandbox_planner: Optional[SandboxPlanner] = None


def get_sandbox_planner() -> SandboxPlanner:
    """获取沙箱规划器实例"""
    global _sandbox_planner
    if _sandbox_planner is None:
        _sandbox_planner = SandboxPlanner()
    return _sandbox_planner


def is_sandbox_planner_enabled() -> bool:
    """检查沙箱规划器是否启用"""
    return USE_SANDBOX_PLANNER


async def sandbox_planner_node(state: dict) -> dict:
    """
    沙箱规划节点入口

    V2: 当 Router 判断为 VAGUE_ANALYSIS 意图时调用。
    通过沙箱化的 Claude Code 进行规划。
    失败时返回 fallback=True 标记，供调用方回退到 super_executor_v4。

    容器池集成：当 AUTONOME_USE_CONTAINER_POOL=true 时，
    从预热池获取容器执行规划，完成后归还。

    Args:
        state: 包含 messages, intent, physical_file_info 的状态

    Returns:
        dict: 包含规划结果的消息，fallback=True 表示需要回退
    """
    messages = state.get("messages", [])
    intent = state.get("intent")
    physical_file_info = state.get("physical_file_info", "")

    if not messages:
        log.warning("📋 [SandboxPlanner] 收到空消息")
        return {
            "messages": [AIMessage(content="抱歉，我没有理解您的需求，请重试。")],
            "next": "end",
            "fallback": True
        }

    # 获取用户消息
    last_msg = messages[-1]
    user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    log.info(f"📋 [SandboxPlanner] 开始规划: {user_message[:50]}...")

    # V2: 容器池集成
    container_id = None
    pooled_container = None
    use_container_pool = os.environ.get("AUTONOME_USE_CONTAINER_POOL", "false").lower() == "true"

    if use_container_pool:
        try:
            from app.services.container_pool_service import get_container_pool
            pool = get_container_pool()
            pooled_container = pool.acquire_container(container_type="general")
            if pooled_container:
                container_id = pooled_container.container_id
                log.info(f"📋 [SandboxPlanner] 从容器池获取容器: {container_id[:12]}")
            else:
                log.warning("📋 [SandboxPlanner] 容器池无可用容器，使用本地模式")
        except Exception as pool_err:
            log.warning(f"📋 [SandboxPlanner] 容器池获取失败: {pool_err}，使用本地模式")

    try:
        planner = get_sandbox_planner()
        result = await planner.plan(
            user_message=user_message,
            workspace_info=physical_file_info,
            container_id=container_id,
        )

        if result.success and result.structured_data:
            # 构建返回消息（StrategyCard 格式）
            card = result.structured_data
            raw_plan = card.get("_raw_plan", {})

            output_content = f"""根据您的需求，我制定了以下规划：

**{card.get('title', '分析规划')}**

{card.get('description', '')}

步骤：
{chr(10).join([f"{i+1}. **{step.get('name', '')}**: {step.get('instruction', '')}" for i, step in enumerate(raw_plan.get('steps', []))])}

预计时间：{card.get('estimated_time', '未知')}

```json_strategy
{json.dumps(card, ensure_ascii=False, indent=2)}
```"""
            return {
                "messages": [AIMessage(content=output_content)],
                "next": "end",
                "fallback": False
            }
        else:
            # 规划失败，标记需要回退
            log.warning(f"📋 [SandboxPlanner] 规划失败: {result.error}")
            return {
                "messages": [],
                "next": "super_executor",
                "fallback": True,
                "planner_error": result.error
            }

    except Exception as e:
        log.error(f"📋 [SandboxPlanner] 规划异常: {e}")
        return {
            "messages": [],
            "next": "super_executor",
            "fallback": True,
            "planner_error": str(e)[:200]
        }

    finally:
        # V2: 归还容器到池中
        if pooled_container:
            try:
                from app.services.container_pool_service import get_container_pool
                pool = get_container_pool()
                pool.release_container(pooled_container)
                log.info(f"📋 [SandboxPlanner] 容器已归还: {container_id[:12] if container_id else 'N/A'}")
            except Exception as release_err:
                log.warning(f"📋 [SandboxPlanner] 容器归还失败: {release_err}")


log.info(f"📋 [SandboxPlanner] 沙箱规划节点已加载 (enabled={USE_SANDBOX_PLANNER})")
