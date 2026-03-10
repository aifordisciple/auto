"""
Executor Agent 模块

负责执行单个 DAG 节点任务。
拥有探针工具和沙箱执行能力。
"""

import os
import json
from typing import Dict, Optional, Any
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.core.logger import log
from app.tools.probe_tools import peek_tabular_data, scan_workspace
from app.tools.bio_tools import execute_python_code


def build_executor_agent(
    api_key: str,
    base_url: str,
    model_name: str,
    project_id: str
):
    """
    构建执行单个 DAG 节点的 Agent

    拥有探针 + 沙箱工具，能够：
    1. 预览数据结构
    2. 执行分析代码
    3. 生成结果文件
    """
    actual_api_key = api_key if (api_key and api_key.strip() != "") else "ollama-local"

    llm = ChatOpenAI(
        api_key=actual_api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1,
        streaming=True,
        max_retries=2
    )

    log.info(f"🤖 [Executor] 构建 Executor Agent - Model: {model_name}")

    # 工具列表：探针 + 沙箱执行
    tools = [
        peek_tabular_data,      # 探针：预览表格
        scan_workspace,         # 探针：扫描目录
        execute_python_code     # 沙箱：执行代码
    ]

    system_prompt = f"""你是 Autonome 的任务执行专家，专门负责执行 DAG 流水线中的单个节点任务。

【当前上下文】
- 项目 ID: {project_id}
- 工作目录: /app/uploads/project_{project_id}/

【你的能力】
1. 🔍 数据探针：
   - peek_tabular_data: 预览表格文件的表头、维度和前几行数据
   - scan_workspace: 扫描目录下的所有文件和文件夹

2. 🚀 代码执行：
   - execute_python_code: 在 Docker 沙箱中执行 Python 代码

【执行规则】
1. **先探查，再执行**：处理数据前，先用探针了解数据结构
2. **参数化代码**：代码必须包含 argparse 或环境变量读取
3. **输出到指定目录**：所有结果文件保存到 TASK_OUT_DIR 环境变量指定的目录
4. **详细注释**：关键步骤必须有行内注释

【输出要求】
1. 执行成功后，简要说明生成了哪些文件
2. 如果报错，分析原因并尝试修复
3. 不要生成策略卡片，专注于执行当前任务

【代码规范】
```python
import os
import pandas as pd

# 获取任务输出目录
out_dir = os.environ.get('TASK_OUT_DIR', f'/app/uploads/project_{project_id}/results/default')
os.makedirs(out_dir, exist_ok=True)

# 读取数据（使用探针确认过的路径）
df = pd.read_csv('YOUR_DATA_PATH', sep='\\t')

# 处理逻辑
...

# 保存结果
df.to_csv(f'{{out_dir}}/result.tsv', sep='\\t', index=False)
print(f"✅ 结果已保存到 {{out_dir}}/result.tsv")
```
"""

    agent = create_react_agent(llm, tools=tools, prompt=system_prompt)

    return agent


async def execute_single_task(
    task: Any,  # TaskNode
    api_key: str,
    base_url: str,
    model_name: str,
    project_id: str,
    session_id: str,
    upstream_outputs: str = ""
) -> Dict[str, Any]:
    """
    执行单个 DAG 节点任务

    Args:
        task: TaskNode 对象，包含任务信息
        api_key: LLM API Key
        base_url: LLM Base URL
        model_name: 模型名称
        project_id: 项目 ID
        session_id: 会话 ID
        upstream_outputs: 上游任务的输出路径（工作区记忆）

    Returns:
        包含执行结果的字典
    """
    log.info(f"🎯 [Executor] 执行任务: {task.name}")

    # 构建 Executor Agent
    agent = build_executor_agent(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        project_id=project_id
    )

    # 构建任务提示
    task_prompt = f"""请执行以下任务：

**任务名称**: {task.name}
**任务描述**: {task.instruction}
**使用工具**: {task.tool}

**输入文件**: {task.expected_input or '根据上下文确定'}
**期望输出**: {task.expected_output or '根据任务内容确定'}

**上游节点实际产物**:
{upstream_outputs}

请按照任务描述完成这个任务，并确保输出文件保存到正确的位置。
"""

    if task.tool == "peek_tabular_data":
        task_prompt += "\n\n注意：这是一个数据探查任务，请调用 peek_tabular_data 工具预览数据结构。"
    elif task.tool == "scan_workspace":
        task_prompt += "\n\n注意：这是一个目录扫描任务，请调用 scan_workspace 工具扫描目录。"
    else:
        task_prompt += f"\n\n注意：这是一个代码执行任务，请生成并执行 Python 代码完成任务。输出目录请使用环境变量 TASK_OUT_DIR。"

    # 执行 Agent
    messages = [{"role": "user", "content": task_prompt}]

    try:
        result = await agent.ainvoke({"messages": messages})

        # 提取最终响应
        final_message = result["messages"][-1]
        output = final_message.content if hasattr(final_message, 'content') else str(final_message)

        log.info(f"✅ [Executor] 任务完成: {task.name}")

        return {
            "status": "success",
            "output": output
        }

    except Exception as e:
        log.error(f"❌ [Executor] 任务执行失败: {str(e)}")

        return {
            "status": "failed",
            "output": "",
            "error": str(e)
        }


log.info("🚀 Executor Agent 模块已加载")