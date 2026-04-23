"""
DAG 拓扑排序与调度逻辑。

提供 DAG 有向无环图的拓扑排序、就绪节点查找、
环检测和节点间参数变量替换功能。
"""
import re
from typing import Any, Dict, List, Optional, Set

from app.core.logger import log


def topological_sort(nodes: List[Dict]) -> List[str]:
    """
    对 DAG 节点进行拓扑排序（Kahn 算法）。

    程序说明：
    返回按执行顺序排列的 task_id 列表。
    如果检测到环，降级为原始顺序（顺序执行）。

    Args:
        nodes: TaskNode 序列化后的字典列表

    Returns:
        按拓扑序排列的 task_id 列表
    """
    # 构建邻接表和入度表
    task_ids = {n.get("task_id") for n in nodes}
    in_degree: Dict[str, int] = {tid: 0 for tid in task_ids}
    adj: Dict[str, List[str]] = {tid: [] for tid in task_ids}

    for node in nodes:
        tid = node.get("task_id")
        for dep in node.get("dependencies", []):
            if dep in task_ids:
                adj[dep].append(tid)
                in_degree[tid] = in_degree.get(tid, 0) + 1

    # Kahn 算法
    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    sorted_ids: List[str] = []

    while queue:
        # 按原始顺序稳定排序
        queue.sort(key=lambda t: next((i for i, n in enumerate(nodes) if n.get("task_id") == t), 0))
        tid = queue.pop(0)
        sorted_ids.append(tid)
        for neighbor in adj.get(tid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 环检测
    if len(sorted_ids) != len(task_ids):
        log.warning(f"[DAG] 检测到环，降级为顺序执行: sorted={len(sorted_ids)}, total={len(task_ids)}")
        return [n.get("task_id") for n in nodes]

    return sorted_ids


def find_ready_nodes(
    nodes: List[Dict],
    task_results: Dict[str, Any],
) -> List[Dict]:
    """
    找出当前可执行的节点（所有前置节点已完成）。

    程序说明：
    遍历所有节点，检查其 dependencies 中的节点是否都已有执行结果。
    返回可执行节点列表。

    Args:
        nodes: TaskNode 列表
        task_results: 已完成节点的执行结果

    Returns:
        可执行节点列表
    """
    ready = []
    for node in nodes:
        tid = node.get("task_id")
        # 已完成或正在执行的节点跳过
        if tid in task_results:
            continue
        # 检查所有前置依赖是否已完成
        deps = node.get("dependencies", [])
        if all(dep in task_results for dep in deps):
            ready.append(node)
    return ready


def resolve_parameter_references(
    parameters: Dict[str, Any],
    task_results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    解析节点参数中的变量引用。

    程序说明：
    参数值中可使用 ${task_id.output.field} 语法引用前序节点的输出。
    此函数将所有变量引用替换为实际值。

    Args:
        parameters: 原始参数字典
        task_results: 已完成节点的执行结果

    Returns:
        解析后的参数字典
    """
    resolved = {}
    pattern = re.compile(r'\$\{(\w+)\.output\.(\w+)\}')

    for key, value in parameters.items():
        if isinstance(value, str):
            match = pattern.fullmatch(value)
            if match:
                ref_task_id = match.group(1)
                ref_field = match.group(2)
                ref_result = task_results.get(ref_task_id, {})
                ref_output = ref_result.get("output", {})
                if isinstance(ref_output, dict) and ref_field in ref_output:
                    resolved[key] = ref_output[ref_field]
                else:
                    log.warning(f"[DAG] 无法解析参数引用: {value}")
                    resolved[key] = value
            else:
                resolved[key] = value
        else:
            resolved[key] = value

    return resolved


def get_dag_progress(nodes: List[Dict], task_results: Dict[str, Any]) -> Dict[str, str]:
    """
    获取 DAG 各节点的执行进度。

    程序说明：
    返回 {task_id: status} 映射，供前端 DAGProgressView 渲染。

    Args:
        nodes: TaskNode 列表
        task_results: 已完成节点的执行结果

    Returns:
        节点进度映射 {task_id: "pending"|"ready"|"completed"|"failed"}
    """
    progress = {}
    for node in nodes:
        tid = node.get("task_id")
        if tid in task_results:
            result = task_results[tid]
            status = result.get("status", "completed")
            if status == "failed":
                progress[tid] = "failed"
            else:
                progress[tid] = "completed"
        else:
            # 检查是否可执行
            deps = node.get("dependencies", [])
            if all(dep in task_results for dep in deps):
                progress[tid] = "ready"
            else:
                progress[tid] = "pending"
    return progress
