"""
锻造会话 Agent - 支持多轮对话的智能技能锻造

核心功能：
1. 通过对话理解用户需求
2. 使用 craft_skill 工具生成/更新技能草稿
3. 支持附件内容分析
4. 保持对话上下文连贯性
"""

import json
from typing import Dict, Any, List, Optional, AsyncIterator

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.logger import log


# ==========================================
# 锻造师系统提示词
# ==========================================
FORGE_SYSTEM_PROMPT = """你是 Autonome 系统的专业技能锻造师（Skill Forger）。

你的任务是通过多轮对话理解用户需求，帮助他们锻造出标准化的生物信息学分析技能。

## 工作流程

1. **需求收集**：通过对话逐步收集关键信息
   - 数据格式（fastq, bam, h5ad, mtx 等）
   - 分析目标（质控、比对、定量、差异分析等）
   - 参数需求（阈值、线程数、输出格式等）
   - 依赖库（scanpy, seurat, DESeq2 等）

2. **技能锻造**：当收集到足够信息时，使用 `craft_skill` 工具生成技能草稿
   - 技能名称和描述
   - 参数 Schema（JSON Schema 格式）
   - 可执行代码（Python/R/Nextflow）
   - 专家知识文档

3. **迭代优化**：根据用户反馈持续改进技能

## 代码规范（必须遵守）

### Python 脚本
- 使用 argparse 接收命令行参数
- 每个参数必须有默认值和帮助文本
- 添加详尽的中文注释
- 表格输出使用 TSV 格式

### R 脚本
- 使用 commandArgs(trailingOnly=TRUE) 或 optparse 包
- 同样需要默认值和注释

### Nextflow 工作流
- 使用 DSL2 语法
- 参数通过 params 定义
- 每个 process 设置合理的资源限制

## 参数 Schema 格式

```json
{
  "type": "object",
  "properties": {
    "input_file": {
      "type": "string",
      "format": "filepath",
      "description": "输入文件路径",
      "default": ""
    },
    "output_dir": {
      "type": "string",
      "format": "directorypath",
      "description": "输出目录",
      "default": "./output"
    },
    "threshold": {
      "type": "number",
      "description": "过滤阈值",
      "default": 0.05
    },
    "threads": {
      "type": "integer",
      "description": "线程数",
      "default": 4
    }
  },
  "required": ["input_file"]
}
```

## 何时调用 craft_skill 工具

当用户描述足够清晰时（包含明确的分析目标和基本参数信息），立即调用工具生成技能草稿。
不要等待用户说出"开始锻造"等指令，主动判断时机。

## 对话风格

- 专业但不生硬
- 主动询问关键缺失信息
- 给出具体的技术建议
- 当用户需求模糊时，提供选项让其选择
"""


# ==========================================
# 工具定义
# ==========================================
@tool
def craft_skill(
    name: str,
    description: str,
    executor_type: str,
    script_code: str,
    parameters_schema: str,
    expert_knowledge: str = "",
    dependencies: str = "[]"
) -> str:
    """
    锻造技能草稿。当收集到足够信息时调用此工具生成技能。

    Args:
        name: 技能名称（中文）
        description: 一句话功能描述
        executor_type: 执行器类型 (Python_env/R_env/Logical_Blueprint)
        script_code: 完整的可执行代码
        parameters_schema: 参数 Schema（JSON 字符串）
        expert_knowledge: 专家知识文档（可选）
        dependencies: 依赖包列表（JSON 数组字符串，可选）

    Returns:
        技能草稿 JSON 字符串
    """
    try:
        # 验证 parameters_schema 是有效 JSON
        params = json.loads(parameters_schema)
    except json.JSONDecodeError:
        params = {"type": "object", "properties": {}, "required": []}

    try:
        deps = json.loads(dependencies)
    except json.JSONDecodeError:
        deps = []

    result = {
        "name": name,
        "description": description,
        "executor_type": executor_type,
        "script_code": script_code,
        "parameters_schema": params,
        "expert_knowledge": expert_knowledge or "暂无专家指导",
        "dependencies": deps
    }

    return json.dumps(result, ensure_ascii=False)


# ==========================================
# 锻造 Agent 类
# ==========================================
class ForgeAgent:
    """锻造会话 Agent"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        executor_type: str = "Python_env",
        skill_draft: Optional[Dict[str, Any]] = None
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.executor_type = executor_type
        self.skill_draft = skill_draft or {}

        # 初始化 LLM
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.3,
            streaming=True
        )

        # 绑定工具
        self.tools = [craft_skill]
        self.llm_with_tools = self.llm.bind_tools(self.tools)

    def _build_system_message(self, attachments: List[str] = []) -> str:
        """构建系统消息，包含当前状态上下文"""
        context = f"当前执行器类型偏好: {self.executor_type}\n\n"

        if self.skill_draft:
            context += f"当前技能草稿状态:\n```json\n{json.dumps(self.skill_draft, ensure_ascii=False, indent=2)}\n```\n\n"

        if attachments:
            context += f"用户上传的附件: {', '.join(attachments)}\n\n"

        return FORGE_SYSTEM_PROMPT + "\n\n" + context

    async def chat_stream(
        self,
        message: str,
        history: List[Dict[str, str]] = [],
        attachments: List[str] = []
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        流式对话

        Args:
            message: 用户消息
            history: 历史对话记录
            attachments: 附件路径列表

        Yields:
            事件字典，包含 type 和 content 字段
        """
        log.info(f"🔨 [ForgeAgent] 开始处理消息，历史长度: {len(history)}")

        # 构建消息列表
        messages = [SystemMessage(content=self._build_system_message(attachments))]

        # 添加历史消息
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        # 添加当前用户消息
        # 如果有附件，附加信息
        if attachments:
            attachment_info = f"\n\n[用户上传了以下附件供分析]\n" + "\n".join(f"- {att}" for att in attachments)
            message = message + attachment_info

        messages.append(HumanMessage(content=message))

        # 流式调用 LLM
        full_response = ""

        try:
            async for chunk in self.llm_with_tools.astream(messages):
                # 处理文本内容
                if chunk.content:
                    full_response += chunk.content
                    yield {
                        "type": "text",
                        "content": chunk.content
                    }

                # 处理工具调用
                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    pass  # 工具调用片段，等待完整调用

            # 检查是否有完整的工具调用
            if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                for tool_call in chunk.tool_calls:
                    if tool_call["name"] == "craft_skill":
                        log.info(f"🔨 [ForgeAgent] 检测到 craft_skill 工具调用")

                        # 解析工具参数
                        args = tool_call["args"]

                        # 构建技能草稿
                        skill_draft = {
                            "name": args.get("name", "未命名技能"),
                            "description": args.get("description", ""),
                            "executor_type": args.get("executor_type", self.executor_type),
                            "script_code": args.get("script_code", ""),
                            "parameters_schema": args.get("parameters_schema", {}),
                            "expert_knowledge": args.get("expert_knowledge", ""),
                            "dependencies": args.get("dependencies", [])
                        }

                        # 更新内部状态
                        self.skill_draft = skill_draft

                        # 返回技能更新事件
                        yield {
                            "type": "skill_update",
                            "data": skill_draft
                        }

                        log.info(f"✅ [ForgeAgent] 技能草稿已更新: {skill_draft.get('name')}")

        except Exception as e:
            log.error(f"🔥 [ForgeAgent] 对话处理失败: {e}")
            yield {
                "type": "error",
                "content": f"处理失败: {str(e)}"
            }

    async def chat(self, message: str, history: List[Dict[str, str]] = [], attachments: List[str] = []) -> Dict[str, Any]:
        """
        非流式对话（用于测试）

        Returns:
            {"response": str, "skill_draft": Optional[Dict]}
        """
        full_text = ""
        skill_draft = None

        async for event in self.chat_stream(message, history, attachments):
            if event["type"] == "text":
                full_text += event["content"]
            elif event["type"] == "skill_update":
                skill_draft = event["data"]

        return {
            "response": full_text,
            "skill_draft": skill_draft
        }


# ==========================================
# 辅助函数
# ==========================================
def build_forge_agent(
    api_key: str,
    base_url: str,
    model_name: str,
    executor_type: str = "Python_env",
    skill_draft: Optional[Dict[str, Any]] = None
) -> ForgeAgent:
    """
    构建锻造 Agent 实例

    Args:
        api_key: OpenAI API Key
        base_url: API Base URL
        model_name: 模型名称
        executor_type: 执行器类型偏好
        skill_draft: 现有技能草稿（用于继续锻造）

    Returns:
        ForgeAgent 实例
    """
    return ForgeAgent(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        executor_type=executor_type,
        skill_draft=skill_draft
    )


log.info("🔨 Forge Agent 已加载")