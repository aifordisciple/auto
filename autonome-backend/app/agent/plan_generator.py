"""
执行计划生成器

使用 LLM 解析用户输入，生成结构化的执行计划（ExecutionPlan）。
"""

import json
import re
import os
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator
import httpx

from app.agent.execution_plan import (
    ExecutionPlan,
    ExecutionStep,
    ExecutionStepType,
    ExecutionStatus,
    RiskLevel,
    generate_plan_id,
    generate_step_id
)
from app.agent.tools import get_tool_registry, get_tools_for_prompt
from app.core.logger import log
from app.core.content_filter import preprocess_llm_response


# ==========================================
# ✨ LLM Prompt 模板
# ==========================================

EXECUTION_PLAN_SYSTEM_PROMPT = """你是一个智能任务规划和执行专家。你的职责是将用户的自然语言指令或代码转换为结构化的执行计划。

## 可用工具

{tools_description}

## 任务要求

请分析用户输入，生成一个执行计划（JSON格式）。执行计划需要：

1. **理解用户意图**：分析用户想要完成什么任务
2. **识别操作类型**：
   - 代码执行（Python/R 代码块）
   - 数据探查（预览文件、查看目录）
   - 文件操作（复制、移动、删除）
   - 技能调用（使用预定义的 SKILL）
3. **提取关键信息**：
   - 代码块内容
   - 文件路径引用
   - 参数值
4. **分析依赖关系**：
   - 哪些步骤必须先执行
   - 哪些步骤可以并行执行
   - 输入输出依赖
5. **风险评估**：
   - 是否有破坏性操作（删除、覆盖）
   - 是否需要用户确认

## 输出格式

请输出 JSON 格式的执行计划，包裹在 ```json_execution_plan 代码块中：

```json_execution_plan
{{
  "user_intent": "用户意图描述",
  "risk_level": "low | medium | high",
  "estimated_time": "预计执行时间",
  "notes": ["需要用户注意的事项"],
  "steps": [
    {{
      "step_id": "step_1",
      "name": "步骤名称",
      "description": "步骤描述",
      "step_type": "code_execution | data_probe | file_operation | skill_call",
      "tool_id": "execute-python | scan-workspace | ...",
      "parameters": {{}},
      "code": "代码内容（如果是代码执行）",
      "language": "python | r",
      "depends_on": [],
      "input_files": ["输入文件路径"],
      "output_files": ["输出文件路径"],
      "timeout": 300
    }}
  ]
}}
```

## 重要规则

1. **探针先行**：处理数据文件前，必须先添加数据探查步骤
2. **路径解析**：将用户提到的文件名转换为完整路径（项目目录: {project_dir}）
3. **依赖分析**：正确设置步骤间的依赖关系
4. **参数推断**：根据上下文推断合理的参数值
5. **安全检查**：对于破坏性操作，设置 risk_level = "high"
6. **步骤命名**：使用 step_1, step_2 等命名，按执行顺序排列
"""

EXECUTION_PLAN_USER_PROMPT = """## 用户输入

{user_input}

## 项目上下文

- 项目 ID: {project_id}
- 项目目录: {project_dir}
- 可用文件: {available_files}

请分析用户输入并生成执行计划。"""


# ==========================================
# ✨ 执行计划生成器类
# ==========================================

class ExecutionPlanGenerator:
    """
    执行计划生成器

    使用 LLM 将用户输入转换为结构化的执行计划。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

    async def generate(
        self,
        user_input: str,
        project_id: str,
        project_dir: str,
        available_files: List[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        生成执行计划

        Args:
            user_input: 用户输入（自然语言、代码或混合内容）
            project_id: 项目 ID
            project_dir: 项目目录路径
            available_files: 项目中可用的文件列表

        Yields:
            SSE 事件字典
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        log.info(f"🧠 [PlanGenerator] 开始生成执行计划...")

        # 推送状态
        yield {
            "event": "status_update",
            "data": json.dumps({
                "status": "parsing",
                "message": "正在解析用户指令..."
            })
        }

        # 准备 Prompt
        tools_desc = get_tools_for_prompt()
        system_prompt = EXECUTION_PLAN_SYSTEM_PROMPT.format(
            tools_description=tools_desc,
            project_dir=project_dir
        )
        user_prompt = EXECUTION_PLAN_USER_PROMPT.format(
            user_input=user_input,
            project_id=project_id,
            project_dir=project_dir,
            available_files=", ".join(available_files[:20]) if available_files else "（未提供）"
        )

        try:
            # 创建 LLM 客户端，使用共享的 HTTP 客户端
            actual_api_key = self.api_key if (self.api_key and self.api_key.strip()) else "ollama-local"
            async_client = get_async_http_client()

            llm = ChatOpenAI(
                api_key=actual_api_key,
                base_url=self.base_url,
                model=self.model_name,
                temperature=0.1,
                max_retries=2,
                request_timeout=120,  # 增加超时时间
                http_async_client=async_client  # 使用共享客户端
            )

            # 调用 LLM
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            try:
                response = await llm.ainvoke(messages)
                llm_response = response.content
            except Exception as invoke_error:
                # 捕获调用错误，避免 httpx 关闭错误传播
                log.error(f"[PlanGenerator] LLM 调用错误: {invoke_error}")
                raise invoke_error

            log.info(f"[PlanGenerator] LLM 响应长度: {len(llm_response)} 字符")

            # 解析执行计划
            plan = self._parse_llm_response(llm_response, user_input, project_id, project_dir)

            if plan:
                log.info(f"✅ [PlanGenerator] 执行计划生成成功: {len(plan.steps)} 个步骤")

                yield {
                    "event": "execution_plan",
                    "data": json.dumps(plan.to_dict())
                }

                # 推送需要用户确认的状态
                yield {
                    "event": "status_update",
                    "data": json.dumps({
                        "status": "waiting_confirm",
                        "message": "执行计划已生成，等待确认..."
                    })
                }
            else:
                # 解析失败，回退到简单模式
                log.warning(f"[PlanGenerator] 无法解析执行计划，回退到简单模式")
                plan = self._create_fallback_plan(user_input, project_id, project_dir)

                yield {
                    "event": "execution_plan",
                    "data": json.dumps(plan.to_dict())
                }

        except Exception as e:
            log.error(f"❌ [PlanGenerator] 生成失败: {str(e)}")
            yield {
                "event": "error",
                "data": json.dumps({"error": f"执行计划生成失败: {str(e)}"})
            }

    def _parse_llm_response(
        self,
        response: str,
        user_input: str,
        project_id: str,
        project_dir: str
    ) -> Optional[ExecutionPlan]:
        """
        解析 LLM 响应，提取执行计划

        Args:
            response: LLM 响应文本
            user_input: 原始用户输入
            project_id: 项目 ID
            project_dir: 项目目录

        Returns:
            ExecutionPlan 或 None
        """
        # 尝试从代码块中提取 JSON
        json_match = re.search(r'```json_execution_plan\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试查找任意 JSON 代码块
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析整个响应
                json_str = response

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        # 验证必要字段
        if "steps" not in data:
            return None

        # 构建 ExecutionPlan
        try:
            steps = []
            for i, step_data in enumerate(data.get("steps", [])):
                step = ExecutionStep(
                    step_id=step_data.get("step_id", generate_step_id(i)),
                    name=step_data.get("name", f"步骤 {i + 1}"),
                    description=step_data.get("description", ""),
                    step_type=ExecutionStepType(step_data.get("step_type", "code_execution")),
                    tool_id=step_data.get("tool_id", "execute-python"),
                    parameters=step_data.get("parameters", {}),
                    code=step_data.get("code"),
                    language=step_data.get("language"),
                    depends_on=step_data.get("depends_on", []),
                    input_files=step_data.get("input_files", []),
                    output_files=step_data.get("output_files", []),
                    timeout=step_data.get("timeout", 300)
                )
                steps.append(step)

            risk_level = RiskLevel.LOW
            if data.get("risk_level") == "medium":
                risk_level = RiskLevel.MEDIUM
            elif data.get("risk_level") == "high":
                risk_level = RiskLevel.HIGH

            plan = ExecutionPlan(
                plan_id=generate_plan_id(),
                user_intent=data.get("user_intent", "执行用户任务"),
                raw_input=user_input,
                steps=steps,
                project_id=project_id,
                output_dir=os.path.join(project_dir, "super_executor_output"),
                estimated_time=data.get("estimated_time", ""),
                risk_level=risk_level,
                notes=data.get("notes", [])
            )

            # 生成执行顺序
            plan.topological_sort()

            return plan

        except Exception as e:
            log.error(f"[PlanGenerator] 解析执行计划失败: {str(e)}")
            return None

    def _create_fallback_plan(
        self,
        user_input: str,
        project_id: str,
        project_dir: str
    ) -> ExecutionPlan:
        """
        创建回退执行计划

        当 LLM 解析失败时，尝试提取代码块并直接执行。
        """
        steps = []

        # 尝试提取 Python 代码块
        python_pattern = r'```(?:python|py)\s*([\s\S]*?)```'
        for match in re.finditer(python_pattern, user_input, re.IGNORECASE):
            code = match.group(1).strip()
            if code:
                steps.append(ExecutionStep(
                    step_id=generate_step_id(len(steps)),
                    name=f"执行 Python 代码块",
                    description="执行用户提供的 Python 代码",
                    step_type=ExecutionStepType.CODE_EXECUTION,
                    tool_id="execute-python",
                    parameters={"code": code, "language": "python"},
                    code=code,
                    language="python"
                ))

        # 尝试提取 R 代码块
        r_pattern = r'```(?:r|R)\s*([\s\S]*?)```'
        for match in re.finditer(r_pattern, user_input, re.IGNORECASE):
            code = match.group(1).strip()
            if code:
                steps.append(ExecutionStep(
                    step_id=generate_step_id(len(steps)),
                    name=f"执行 R 代码块",
                    description="执行用户提供的 R 代码",
                    step_type=ExecutionStepType.CODE_EXECUTION,
                    tool_id="execute-r",
                    parameters={"code": code, "language": "r"},
                    code=code,
                    language="r"
                ))

        if not steps:
            # 没有代码块，创建数据探查步骤
            steps.append(ExecutionStep(
                step_id="step_1",
                name="扫描项目目录",
                description="扫描项目目录结构",
                step_type=ExecutionStepType.DATA_PROBE,
                tool_id="scan-workspace",
                parameters={"directory_path": project_dir}
            ))

        plan = ExecutionPlan(
            plan_id=generate_plan_id(),
            user_intent="执行用户任务（回退模式）",
            raw_input=user_input,
            steps=steps,
            project_id=project_id,
            output_dir=os.path.join(project_dir, "super_executor_output"),
            risk_level=RiskLevel.LOW
        )

        plan.topological_sort()
        return plan


# ==========================================
# ✨ 辅助函数
# ==========================================

# 全局异步 HTTP 客户端（避免重复创建和关闭）
_global_async_client = None


def get_async_http_client():
    """获取全局异步 HTTP 客户端"""
    global _global_async_client
    if _global_async_client is None:
        _global_async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
    return _global_async_client


def extract_code_blocks(text: str) -> List[Dict[str, Any]]:
    """
    从文本中提取代码块

    Args:
        text: 包含代码块的文本

    Returns:
        代码块列表
    """
    # 🔧 预处理：过滤 thinking 标签
    text = preprocess_llm_response(text)

    blocks = []

    # Python 代码块
    python_pattern = r'```(?:python|py)\s*([\s\S]*?)```'
    for match in re.finditer(python_pattern, text, re.IGNORECASE):
        blocks.append({
            "language": "python",
            "code": match.group(1).strip()
        })

    # R 代码块
    r_pattern = r'```(?:r|R)\s*([\s\S]*?)```'
    for match in re.finditer(r_pattern, text, re.IGNORECASE):
        blocks.append({
            "language": "r",
            "code": match.group(1).strip()
        })

    return blocks


# ==========================================
# ✨ 模块初始化
# ==========================================

log.info("🧠 执行计划生成器模块已加载")