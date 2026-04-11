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
"""

import os
import json
import asyncio
from typing import Annotated, Optional

from langchain_core.messages import BaseMessage, AIMessage
from langchain_openai import ChatOpenAI

from app.core.logger import log
from app.agent.schemas import IntentClassification
from app.services.pty_manager import PTYManager, PTYConfig
from app.utils.result_extractor import ResultExtractor
from app.mcp.autonome_skills_mcp import get_mcp_server


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

【输出要求】
完成规划后，必须在 PTY 中输出以下格式的结果：

[AUTONOME_RESULT_START]
{{
  "plan": "简要规划描述",
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
"""


class SandboxPlanner:
    """
    沙箱规划器

    整合 PTY Manager + MCP + Result Extractor
    """

    def __init__(self):
        self.mcp = get_mcp_server()
        self.pty: Optional[PTYManager] = None

    async def plan(
        self,
        user_message: str,
        workspace_info: str,
        container_id: Optional[str] = None,
        timeout: int = 60
    ) -> Optional[dict]:
        """
        执行沙箱规划

        Args:
            user_message: 用户消息
            workspace_info: 工作区信息
            container_id: 可选的容器 ID
            timeout: 超时时间（秒）

        Returns:
            规划结果字典，如果失败则返回 None
        """
        # 构建 Prompt
        prompt = SANDBOX_PLANNER_PROMPT.format(
            user_message=user_message,
            workspace_info=workspace_info or "无"
        )

        try:
            # 启动 PTY 会话
            self.pty = PTYManager(PTYConfig(timeout=5.0))
            if container_id:
                # 在指定容器中执行
                command = ["docker", "exec", "-it", container_id, "claude", "--print"]
            else:
                # 本地执行
                command = ["claude", "--print"]

            # 启动会话
            if not self.pty.start_session(command):
                log.error("❌ [SandboxPlanner] PTY 会话启动失败")
                return None

            # 等待 Claude Code 启动
            await asyncio.sleep(2)

            # 发送规划 Prompt
            self.pty.write(prompt + "\n")

            # 读取输出直到找到结果或超时
            output = ""
            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < timeout:
                chunk = self.pty.read_output(timeout=2.0)
                output += chunk

                # 检查是否找到结果
                result = ResultExtractor.extract(output)
                if result:
                    log.info("✅ [SandboxPlanner] 成功提取结果")
                    return result

                # 检查进程是否还在运行
                if not self.pty.is_alive():
                    break

                await asyncio.sleep(0.5)

            # 超时或进程结束，返回累积的输出
            log.warning(f"⚠️ [SandboxPlanner] 规划未完成，输出长度: {len(output)}")
            return None

        except Exception as e:
            log.error(f"❌ [SandboxPlanner] 规划失败: {e}")
            return None

        finally:
            # 清理
            if self.pty:
                self.pty.close()
                self.pty = None

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


async def sandbox_planner_node(state: dict) -> dict:
    """
    沙箱规划节点入口

    当 Router 判断为 VAGUE_ANALYSIS 或 PIPELINE_BUILD 意图时调用。
    通过沙箱化的 Claude Code 进行规划。

    Args:
        state: 包含 messages, intent, physical_file_info 的状态

    Returns:
        dict: 包含规划结果的消息
    """
    messages = state.get("messages", [])
    intent = state.get("intent")
    physical_file_info = state.get("physical_file_info", "")

    if not messages:
        log.warning("📋 [SandboxPlanner] 收到空消息")
        return {
            "messages": [AIMessage(content="抱歉，我没有理解您的需求，请重试。")],
            "next": "end"
        }

    # 获取用户消息
    last_msg = messages[-1]
    user_message = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    log.info(f"📋 [SandboxPlanner] 开始规划: {user_message[:50]}...")

    try:
        planner = get_sandbox_planner()
        result = await planner.plan(
            user_message=user_message,
            workspace_info=physical_file_info
        )

        if result:
            # 构建返回消息
            output_content = f"""根据您的需求，我制定了以下规划：

**{result.get('plan', '分析规划')}**

步骤：
{chr(10).join([f"{i+1}. **{step.get('name', '')}**: {step.get('instruction', '')}" for i, step in enumerate(result.get('steps', []))])}

预计时间：{result.get('estimated_time', '未知')}

```json_strategy
{json.dumps(result, ensure_ascii=False, indent=2)}
```"""
            return {
                "messages": [AIMessage(content=output_content)],
                "next": "end"
            }
        else:
            # 规划失败，返回错误消息
            return {
                "messages": [AIMessage(content="抱歉，规划失败。请尝试更具体地描述您的需求。")],
                "next": "end"
            }

    except Exception as e:
        log.error(f"📋 [SandboxPlanner] 规划异常: {e}")
        return {
            "messages": [AIMessage(content=f"抱歉，规划过程出现错误：{str(e)[:100]}")],
            "next": "end"
        }


log.info("📋 [SandboxPlanner] 沙箱规划节点已加载")
