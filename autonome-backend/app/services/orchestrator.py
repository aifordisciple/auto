"""
DAG 蓝图调度器模块

负责：
1. 从 AI 输出中提取蓝图 JSON
2. 拓扑排序 DAG 任务
3. 流式执行 DAG 节点
4. 工作区记忆（上下游文件路径传递）
5. 视觉审稿与打回重绘
"""

import os
import json
import re
import asyncio
from typing import AsyncGenerator, Dict, List, Optional, Any
from dataclasses import dataclass, field
from app.core.logger import log


@dataclass
class TaskNode:
    """DAG 任务节点"""
    task_id: str
    name: str
    tool: str
    depends_on: List[str] = field(default_factory=list)
    expected_input: Optional[str] = None
    expected_output: Optional[str] = None
    instruction: str = ""
    status: str = "pending"  # pending, running, success, failed
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Blueprint:
    """蓝图数据结构"""
    project_goal: str
    is_complex_task: bool
    tasks: List[TaskNode] = field(default_factory=list)


class BlueprintOrchestrator:
    """DAG 蓝图调度器"""

    def __init__(self, blueprint_data: Dict[str, Any]):
        self.project_goal = blueprint_data.get("project_goal", "未命名任务")
        self.is_complex_task = blueprint_data.get("is_complex_task", True)

        # 解析任务节点
        self.tasks: Dict[str, TaskNode] = {}
        for task_data in blueprint_data.get("tasks", []):
            task = TaskNode(
                task_id=task_data.get("task_id", "unknown"),
                name=task_data.get("name", "未命名任务"),
                tool=task_data.get("tool", "execute_python_code"),
                depends_on=task_data.get("depends_on", []),
                expected_input=task_data.get("expected_input"),
                expected_output=task_data.get("expected_output"),
                instruction=task_data.get("instruction", "")
            )
            self.tasks[task.task_id] = task

        # 工作区记忆：存储每个任务的输出路径
        self.workspace_memory: Dict[str, List[str]] = {}

    def topological_sort(self) -> List[str]:
        """
        Kahn 算法拓扑排序
        返回按依赖关系排序的任务 ID 列表
        """
        # 计算入度
        in_degree = {task_id: 0 for task_id in self.tasks}
        for task in self.tasks.values():
            for dep in task.depends_on:
                if dep in in_degree:
                    in_degree[task_id] = in_degree.get(task_id, 0) + 1

        # 找出所有入度为 0 的节点
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # 取出一个入度为 0 的节点
            current = queue.pop(0)
            result.append(current)

            # 减少所有依赖此节点的节点的入度
            for task in self.tasks.values():
                if current in task.depends_on:
                    in_degree[task.task_id] -= 1
                    if in_degree[task.task_id] == 0:
                        queue.append(task.task_id)

        # 检查是否有环
        if len(result) != len(self.tasks):
            log.warning(f"⚠️ [Orchestrator] 检测到 DAG 中存在环，部分任务无法执行")
            # 返回已排序的部分
            return result

        return result

    def get_upstream_outputs(self, task_id: str) -> str:
        """获取上游任务的输出路径（工作区记忆）"""
        outputs = []
        for dep_id in self.tasks[task_id].depends_on:
            if dep_id in self.workspace_memory:
                outputs.extend(self.workspace_memory[dep_id])

        if outputs:
            return "\n".join([f"- {path}" for path in outputs])
        return "无上游产物"

    async def run_dag_stream(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        project_id: str,
        session_id: str,
        enable_visual_review: bool = True,
        max_review_attempts: int = 2
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行 DAG，推送状态给前端

        Yields:
            SSE 事件字典，包含任务状态更新
        """
        import json
        from app.agent.executor_agent import build_executor_agent, execute_single_task
        from app.agent.reviewer import review_plot, extract_images_from_result

        # 获取拓扑排序后的执行顺序
        execution_order = self.topological_sort()

        log.info(f"🚀 [Orchestrator] 开始执行 DAG，共 {len(execution_order)} 个任务")
        log.info(f"📋 [Orchestrator] 执行顺序: {execution_order}")

        # 推送开始事件
        yield {
            "event": "blueprint_start",
            "data": json.dumps({
                "project_goal": self.project_goal,
                "total_tasks": len(execution_order),
                "execution_order": execution_order
            })
        }

        # 逐个执行任务
        for task_id in execution_order:
            task = self.tasks[task_id]
            task.status = "running"

            log.info(f"🔄 [Orchestrator] 执行任务: {task.name} ({task_id})")

            # 推送任务开始事件
            yield {
                "event": "task_start",
                "data": json.dumps({
                    "task_id": task_id,
                    "name": task.name,
                    "tool": task.tool,
                    "instruction": task.instruction
                })
            }

            try:
                # 构建任务上下文（包含上游产物）
                upstream_outputs = self.get_upstream_outputs(task_id)

                # ✨ 视觉审稿打回重绘机制
                review_attempts = 0
                current_instruction = task.instruction

                while review_attempts <= max_review_attempts:
                    # 执行单个任务
                    result = await execute_single_task(
                        task=task,
                        api_key=api_key,
                        base_url=base_url,
                        model_name=model_name,
                        project_id=project_id,
                        session_id=session_id,
                        upstream_outputs=upstream_outputs
                    )

                    task.result = result.get("output", "")

                    # ✨ 检查是否生成了图片，进行视觉审查
                    if enable_visual_review and task.expected_output:
                        output_ext = os.path.splitext(task.expected_output)[1].lower()
                        is_image_output = output_ext in ['.png', '.jpg', '.jpeg', '.pdf', '.svg']

                        if is_image_output and os.path.exists(task.expected_output):
                            log.info(f"🎨 [Orchestrator] 启动视觉审稿: {task.expected_output}")

                            # 推送审稿开始事件
                            yield {
                                "event": "visual_review_start",
                                "data": json.dumps({
                                    "task_id": task_id,
                                    "image_path": task.expected_output
                                })
                            }

                            # 调用视觉审稿
                            review_result = await review_plot(
                                image_path=task.expected_output,
                                task_instruction=current_instruction,
                                api_key=api_key,
                                base_url=base_url,
                                model_name=model_name
                            )

                            if review_result.startswith("PASS"):
                                log.info(f"✅ [Orchestrator] 视觉审稿通过: {task.name}")
                                # 推送审稿通过事件
                                yield {
                                    "event": "visual_review_pass",
                                    "data": json.dumps({
                                        "task_id": task_id,
                                        "review": "图表质量合格"
                                    })
                                }
                                break  # 审稿通过，退出重试循环

                            else:
                                # 审稿打回
                                review_attempts += 1
                                log.warning(f"⚠️ [Orchestrator] 视觉审稿打回 (第{review_attempts}次): {review_result}")

                                # 推送审稿打回事件
                                yield {
                                    "event": "visual_review_reject",
                                    "data": json.dumps({
                                        "task_id": task_id,
                                        "attempt": review_attempts,
                                        "review": review_result
                                    })
                                }

                                if review_attempts <= max_review_attempts:
                                    # 更新指令，包含审稿意见
                                    current_instruction = f"""{task.instruction}

【审稿人打回意见】
{review_result}

请根据上述意见修改代码，重新生成图表。注意解决审稿人指出的问题。
"""
                                else:
                                    # 达到最大重试次数，标记为部分成功
                                    log.warning(f"⚠️ [Orchestrator] 达到最大重试次数，审稿仍未通过")
                                    task.result += f"\n\n⚠️ 视觉审稿未通过: {review_result}"
                        else:
                            # 非图片输出，直接成功
                            break
                    else:
                        # 无需视觉审稿，直接成功
                        break

                task.status = "success"

                # 更新工作区记忆
                if task.expected_output:
                    self.workspace_memory[task_id] = [task.expected_output]

                log.info(f"✅ [Orchestrator] 任务完成: {task.name}")

                # 推送任务完成事件
                yield {
                    "event": "task_complete",
                    "data": json.dumps({
                        "task_id": task_id,
                        "name": task.name,
                        "status": "success",
                        "result": task.result[:500] if task.result else "",
                        "output_path": task.expected_output
                    })
                }

            except Exception as e:
                task.status = "failed"
                task.error = str(e)

                log.error(f"❌ [Orchestrator] 任务失败: {task.name} - {str(e)}")

                # 推送任务失败事件
                yield {
                    "event": "task_failed",
                    "data": json.dumps({
                        "task_id": task_id,
                        "name": task.name,
                        "status": "failed",
                        "error": str(e)
                    })
                }

                # 任务失败时可以选择继续或中止
                # 这里选择中止整个 DAG
                break

        # 推送完成事件
        success_count = sum(1 for t in self.tasks.values() if t.status == "success")
        failed_count = sum(1 for t in self.tasks.values() if t.status == "failed")

        yield {
            "event": "blueprint_complete",
            "data": json.dumps({
                "project_goal": self.project_goal,
                "total_tasks": len(self.tasks),
                "success_count": success_count,
                "failed_count": failed_count,
                "workspace_memory": self.workspace_memory
            })
        }

        log.info(f"🏁 [Orchestrator] DAG 执行完成: {success_count} 成功, {failed_count} 失败")


def extract_blueprint(text: str) -> Optional[Dict[str, Any]]:
    """
    从 AI 输出中提取蓝图 JSON

    支持两种格式：
    1. ```json_blueprint ... ```
    2. 直接的 JSON 对象
    """
    if not text:
        return None

    # 尝试从代码块中提取
    blueprint_match = re.search(r'```json_blueprint\s*\n([\s\S]*?)```', text)
    if blueprint_match:
        try:
            data = json.loads(blueprint_match.group(1))
            if data.get("is_complex_task") and data.get("tasks"):
                return data
        except json.JSONDecodeError as e:
            log.warning(f"⚠️ [Orchestrator] 蓝图 JSON 解析失败: {e}")

    # 尝试直接解析包含 is_complex_task 的 JSON
    try:
        # 查找包含 is_complex_task 的 JSON 对象
        start = text.find('{')
        while start != -1:
            # 使用括号匹配找到完整的 JSON
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        json_str = text[start:i+1]
                        try:
                            data = json.loads(json_str)
                            if data.get("is_complex_task") and data.get("tasks"):
                                return data
                        except:
                            pass
                        break
            start = text.find('{', start + 1)
    except Exception as e:
        log.warning(f"⚠️ [Orchestrator] 蓝图提取失败: {e}")

    return None


async def run_dag_stream(
    blueprint_data: Dict[str, Any],
    api_key: str,
    base_url: str,
    model_name: str,
    project_id: str,
    session_id: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    便捷函数：创建调度器并执行 DAG
    """
    orchestrator = BlueprintOrchestrator(blueprint_data)
    async for event in orchestrator.run_dag_stream(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        project_id=project_id,
        session_id=session_id
    ):
        yield event


log.info("🔄 DAG 蓝图调度器模块已加载")