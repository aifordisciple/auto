"""
UI/State Agent 节点 - 视觉微调与 SCI 级输出约束。

当用户需要调整可视化参数、配色方案或导出图表时路由到此节点。
不启动全量计算型沙箱，仅重载视图配置或执行轻量级绘图环境。
"""
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agent.router.schemas import AgentState
from app.core.logger import log

UI_STATE_SYSTEM_PROMPT = """
你是 Autonome Studio 的 [视觉感知与图形管护节点]。你负责前端绘图状态的重载和发表级图表的输出。

=== 核心输出协议 (SCI Protocol) ===

1. 【视觉专业性】：你生成的任何可视化参数或轻量级绘图脚本，必须应用专业的配色方案（如 ggsci 的 npg/jco/lancet 等）。图像输出必须强制指定分辨率至少为 300 DPI。
2. 【双格式输出】：强制要求同步生成 .pdf（用于矢量编辑）和 .png（用于网页预览）两种格式。
3. 【数据对称性（最高红线）】：严禁仅输出图像！你必须在操作中强制包含抽取底层绘图数据的逻辑，将图表中的坐标（X/Y）、分类标记、阈值等，输出为一个以 Tab 分割的 .tsv 数据文件。
====================================

你的任务是不启动全量计算型沙箱，仅重载视图配置或执行轻量级绘图环境。
"""


async def ui_state_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """处理视图微调、配色更改及图表导出的节点。"""
    intent_data = state.get("intent_data", {})

    log.info(f"[ui_state_node] 视觉微调请求, intent_data={intent_data}")

    # DAG 指针推进：记录当前子任务执行结果，推进到下一个节点
    idx = state.get("current_task_idx", 0)
    dag = state.get("dag", {})
    nodes = dag.get("nodes", [])
    task_id = nodes[idx].get("task_id", "unknown") if idx < len(nodes) else "unknown"
    task_results = state.get("task_results", {})
    task_results[task_id] = {"status": "success", "system_prompt": "UI_STATE_SYSTEM_PROMPT"}

    return {
        "intent_data": {**intent_data, "node": "ui_state_node", "system_prompt_key": "visual"},
        "current_task_idx": idx + 1,
        "task_results": task_results,
    }
