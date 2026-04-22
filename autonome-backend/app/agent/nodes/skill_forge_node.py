"""
Skill Forge Agent 节点 - 代码生成与执行。

当用户需要生成或执行生信分析代码时路由到此节点。
使用 SkillExecutor 在 Docker 沙箱中执行代码。

升级要点：
- 新增 FORGE_SYSTEM_PROMPT 约束代码生成行为
- 支持 DAG 指针推进（current_task_idx + task_results）
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log

FORGE_SYSTEM_PROMPT = """
=== 最高优先级系统指令（违背将导致任务熔断） ===

1. 【非破坏性更新】：当你对现有代码进行修改、优化或 Bug 修复时，绝对禁止删除或截断历史版本中的 `@ProgramExplanation`（程序说明）和任何原有的中文行级注释。你只能追加或修改，绝不能抹除前人的上下文。
2. 【强制参数系统】：所有生成的独立脚本必须使用标准的参数解析库（Python 使用 `argparse`，R 使用 `optparse` 或 `commandArgs`）。
3. 【生信默认值】：必须为所有参数设定符合真实生信分析经验的默认值（如 k-mer 默认为 3，p-value 默认为 0.05）。
====================================================
"""


async def skill_forge_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Skill Forge Agent 节点。

    处理代码生成/执行请求。
    实际的 SkillExecutor 调用和 LLM 代码生成在 chat.py 的 SSE 循环中完成。

    升级：增加 DAG 指针推进和 system_prompt_key 标记。
    """
    intent_data = state.get("intent_data", {})
    entities = intent_data.get("entities", {})

    log.info(f"[skill_forge_node] 处理代码生成请求, entities={entities}")

    # DAG 指针推进：记录当前子任务执行结果，推进到下一个节点
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "system_prompt": "FORGE_SYSTEM_PROMPT"}

    return {
        "intent_data": {**intent_data, "node": "skill_forge_node", "system_prompt_key": "forge"},
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
