"""
DAG 蓝图调度器模块

负责：
1. 从 AI 输出中提取蓝图 JSON
2. 拓扑排序 DAG 任务
3. 流式执行 DAG 节点
4. 工作区记忆（上下游文件路径传递）
5. 视觉审稿与打回重绘
6. 语义化步骤目录命名
"""

import os
import json
import re
import asyncio
import time
from typing import AsyncGenerator, Dict, List, Optional, Any
from dataclasses import dataclass, field
from app.core.logger import log

# 语义化目录命名
from app.utils.semantic_naming import generate_step_dir_name


# ✨ 超时配置常量
TASK_EXECUTION_TIMEOUT = 1800  # 单个任务执行超时（30分钟）- 增加以适应 FastQC/比对等 I/O 密集型任务
AGENT_INVOKE_TIMEOUT = 180     # Agent 调用超时（3分钟）
VISUAL_REVIEW_TIMEOUT = 60     # 视觉审稿超时（1分钟）
HEARTBEAT_INTERVAL = 30        # 心跳间隔（30秒）

# ✨ 任务类型默认超时映射（秒）
TASK_TYPE_TIMEOUT_MAP = {
    "fastqc": 1800,           # FastQC 质控：30分钟
    "alignment": 3600,        # 比对任务：1小时
    "quantification": 1800,   # 定量任务：30分钟
    "differential": 600,      # 差异分析：10分钟
    "visualization": 600,     # 可视化：10分钟
    "annotation": 1800,       # 注释任务：30分钟
    "default": 1800,          # 默认：30分钟
}

# ✨ 自愈机制配置常量
MAX_DEBUG_RETRIES = 3        # Debugger 最大重试次数
DEBUG_RETRY_DELAY = 2        # 重试间隔（秒）


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
    # ✨ 任务级超时配置（秒），None 表示使用默认值
    timeout_seconds: Optional[int] = None


def get_task_timeout(task: TaskNode) -> int:
    """
    获取任务的超时时间

    优先级：
    1. 任务自定义 timeout_seconds
    2. 根据任务名称推断（fastqc, alignment 等）
    3. 默认值（30分钟）

    Args:
        task: 任务节点

    Returns:
        超时时间（秒）
    """
    # 1. 使用任务自定义超时
    if task.timeout_seconds:
        return task.timeout_seconds

    # 2. 根据任务名称推断
    task_name_lower = task.name.lower()
    tool_lower = task.tool.lower()

    # 检查任务名称中的关键词
    for keyword, timeout in TASK_TYPE_TIMEOUT_MAP.items():
        if keyword in task_name_lower or keyword in tool_lower:
            return timeout

    # 3. 使用默认值
    return TASK_TYPE_TIMEOUT_MAP["default"]


@dataclass
class Blueprint:
    """蓝图数据结构"""
    project_goal: str
    is_complex_task: bool
    tasks: List[TaskNode] = field(default_factory=list)
    # ✨ AI 生成的语义化目录名（不含时间戳和ID）
    semantic_folder_name: Optional[str] = None


class BlueprintOrchestrator:
    """DAG 蓝图调度器"""

    def __init__(
        self,
        blueprint_data: Dict[str, Any],
        blueprint_root_dir: Optional[str] = None,
        blueprint_id: Optional[str] = None,
    ):
        """
        初始化蓝图调度器

        Args:
            blueprint_data: 蓝图 JSON 数据
            blueprint_root_dir: 蓝图根目录（语义化路径）
            blueprint_id: 蓝图唯一 ID（用于步骤命名）
        """
        self.project_goal = blueprint_data.get("project_goal", "未命名任务")
        self.is_complex_task = blueprint_data.get("is_complex_task", True)

        # ✨ AI 生成的语义化目录名
        self.semantic_folder_name = blueprint_data.get("semantic_folder_name")

        # 蓝图级联命名参数
        self.blueprint_root_dir = blueprint_root_dir
        self.blueprint_id = blueprint_id

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
                instruction=task_data.get("instruction", ""),
                timeout_seconds=task_data.get("timeout_seconds")  # ✨ 支持自定义超时
            )
            self.tasks[task.task_id] = task

        # 工作区记忆：存储每个任务的输出路径
        self.workspace_memory: Dict[str, List[str]] = {}

        # 步骤计数器（用于级联命名）
        self._step_counter = 0

    def topological_sort(self) -> List[str]:
        """
        Kahn 算法拓扑排序
        返回按依赖关系排序的任务 ID 列表

        Raises:
            ValueError: 如果存在循环依赖或缺失的依赖节点
        """
        # 检查缺失的依赖节点
        missing_deps = set()
        for task_id, task in self.tasks.items():
            for dep in task.depends_on:
                if dep not in self.tasks:
                    missing_deps.add(dep)

        if missing_deps:
            log.error(f"❌ [Orchestrator] 发现缺失的依赖节点: {missing_deps}")
            raise ValueError(f"DAG 中存在缺失的依赖节点: {missing_deps}")

        # 计算入度
        in_degree = {task_id: 0 for task_id in self.tasks}
        for task_id, task in self.tasks.items():
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
            # 找出循环依赖的节点
            cycle_nodes = [tid for tid in self.tasks if tid not in result]
            log.error(f"❌ [Orchestrator] 检测到 DAG 中存在循环依赖，涉及节点: {cycle_nodes}")
            raise ValueError(f"DAG 中存在循环依赖，涉及节点: {cycle_nodes}")

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

        # ✨ 心跳状态
        heartbeat_active = True
        last_heartbeat = time.time()

        async def heartbeat_generator():
            """后台心跳任务"""
            while heartbeat_active:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if heartbeat_active:
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps({
                            "timestamp": time.time(),
                            "status": "running"
                        })
                    }

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

            # ✨ 推送心跳事件（保持连接活跃）
            if time.time() - last_heartbeat > HEARTBEAT_INTERVAL:
                last_heartbeat = time.time()
                yield {
                    "event": "heartbeat",
                    "data": json.dumps({
                        "timestamp": last_heartbeat,
                        "current_task": task.name,
                        "progress": f"{execution_order.index(task_id) + 1}/{len(execution_order)}"
                    })
                }

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

                # ==========================================
                # ✨ 语义化步骤目录命名 (Semantic Step Directory)
                # ==========================================
                # 如果有蓝图根目录，使用级联命名
                step_output_dir = None
                if self.blueprint_root_dir:
                    self._step_counter += 1
                    step_dir_name = generate_step_dir_name(
                        step_number=self._step_counter,
                        skill_id=task.tool,
                        task_id=task_id,
                    )
                    step_output_dir = os.path.join(self.blueprint_root_dir, step_dir_name)
                    os.makedirs(step_output_dir, exist_ok=True)
                    log.info(f"📁 [Orchestrator] 步骤 {self._step_counter} 输出目录: {step_dir_name}")

                # ==========================================
                # ✨ Debugger 自愈机制：最多重试 MAX_DEBUG_RETRIES 次
                # ==========================================
                debug_retry_count = 0
                last_error = None
                current_instruction = task.instruction  # 可能在调试过程中被修改

                while debug_retry_count < MAX_DEBUG_RETRIES:
                    # ✨ 视觉审稿打回重绘机制
                    review_attempts = 0

                    while review_attempts <= max_review_attempts:
                        # ✨ 添加任务执行超时
                        try:
                            result = await asyncio.wait_for(
                                execute_single_task(
                                    task=task,
                                    api_key=api_key,
                                    base_url=base_url,
                                    model_name=model_name,
                                    project_id=project_id,
                                    session_id=session_id,
                                    upstream_outputs=upstream_outputs,
                                    enhanced_instruction=current_instruction,  # ✨ 传递增强指令
                                    step_output_dir=step_output_dir,  # ✨ 语义化步骤目录
                                    step_number=self._step_counter if self.blueprint_root_dir else None,
                                ),
                                timeout=get_task_timeout(task)  # ✨ 动态超时
                            )
                        except asyncio.TimeoutError:
                            task_timeout = get_task_timeout(task)
                            log.error(f"⏰ [Orchestrator] 任务执行超时: {task.name} (超时设置: {task_timeout}秒)")
                            task.status = "timeout"
                            task.error = f"任务执行超时（>{task_timeout}秒）"
                            raise TimeoutError(f"任务 {task.name} 执行超时")

                        task.result = result.get("output", "")

                        # ✨ Debugger 自愈机制：检查执行是否成功
                        execution_error = extract_execution_error(result)
                        if execution_error:
                            debug_retry_count += 1
                            last_error = execution_error

                            log.warning(f"🔧 [Debugger] 检测到执行错误 (尝试 {debug_retry_count}/{MAX_DEBUG_RETRIES}): {execution_error[:200]}")

                            # 推送调试重试事件
                            yield {
                                "event": "debug_retry",
                                "data": json.dumps({
                                    "task_id": task_id,
                                    "attempt": debug_retry_count,
                                    "max_attempts": MAX_DEBUG_RETRIES,
                                    "error": execution_error[:500]
                                })
                            }

                            if debug_retry_count < MAX_DEBUG_RETRIES:
                                # 更新指令，包含错误信息，让 Agent 自行修复
                                current_instruction = f"""{task.instruction}

【⚠️ 代码执行报错 - 请分析并修复】
{execution_error}

【修复提示】
1. 仔细阅读错误信息，分析根本原因
2. 检查文件路径是否正确（使用 scan_workspace 确认）
3. 检查列名是否正确（使用 peek_tabular_data 确认）
4. 检查数据类型转换是否正确
5. 修复后重新执行，确保保留参数系统和详细注释！

【重要提醒】
- 必须保留 argparse 参数系统
- 所有输出必须保存到 TASK_OUT_DIR 环境变量指定的目录
- 关键步骤必须有详细注释
"""
                                log.info(f"🔄 [Debugger] 注入错误上下文，准备第 {debug_retry_count + 1} 次重试")
                                await asyncio.sleep(DEBUG_RETRY_DELAY)
                                continue  # 跳出视觉审稿循环，进入下一次调试重试
                            else:
                                # 达到最大重试次数，任务失败
                                log.error(f"❌ [Debugger] 达到最大重试次数 {MAX_DEBUG_RETRIES}，任务失败")
                                task.status = "failed"
                                task.error = f"执行失败（已重试 {MAX_DEBUG_RETRIES} 次）: {execution_error}"
                                raise Exception(task.error)
                        else:
                            # 执行成功，退出调试重试循环
                            debug_retry_count = MAX_DEBUG_RETRIES  # 标记成功，退出外层循环
                            break

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
                                    break  # 审稿通过，退出视觉审稿循环

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
                                        # 达到最大重试次数，标记为审稿未通过
                                        log.warning(f"⚠️ [Orchestrator] 达到最大审稿重试次数，审稿仍未通过")
                                        task.status = "review_failed"
                                        task.result += f"\n\n⚠️ 视觉审稿未通过: {review_result}"
                                        break  # 退出视觉审稿循环
                            else:
                                # 非图片输出或文件不存在，直接成功
                                break
                        else:
                            # 无需视觉审稿，直接成功
                            break

                    # ==========================================
                    # ✨ 根据执行结果设置最终状态
                    # ==========================================
                    if task.status == "review_failed":
                        # 审稿未通过，推送特殊完成事件
                        log.info(f"⚠️ [Orchestrator] 任务完成（审稿未通过）: {task.name}")
                        yield {
                            "event": "task_complete",
                            "data": json.dumps({
                                "task_id": task_id,
                                "name": task.name,
                                "status": "review_failed",
                                "result": task.result[:500] if task.result else "",
                                "output_path": task.expected_output,
                                "warning": "视觉审稿未通过，图表可能存在质量问题"
                            })
                        }
                    else:
                        # 正常成功
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
        review_failed_count = sum(1 for t in self.tasks.values() if t.status == "review_failed")

        # ✨ 停止心跳
        heartbeat_active = False

        yield {
            "event": "blueprint_complete",
            "data": json.dumps({
                "project_goal": self.project_goal,
                "total_tasks": len(self.tasks),
                "success_count": success_count,
                "failed_count": failed_count,
                "review_failed_count": review_failed_count,
                "workspace_memory": self.workspace_memory
            })
        }

        log.info(f"🏁 [Orchestrator] DAG 执行完成: {success_count} 成功, {failed_count} 失败, {review_failed_count} 审稿未通过")


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


# ==========================================
# ✨ Debugger 自愈机制辅助函数
# ==========================================

def extract_execution_error(result: Dict[str, Any]) -> Optional[str]:
    """
    从执行结果中提取错误信息

    检测以下错误模式：
    1. 状态为 failed
    2. 输出中包含 ❌ 标记
    3. 输出中包含 Python/R 异常堆栈

    Args:
        result: 执行结果字典，包含 status, output, error 等字段

    Returns:
        提取的错误信息字符串，无错误返回 None
    """
    if result.get("status") == "failed":
        # 优先返回明确的错误信息
        if result.get("error"):
            return result["error"]
        if result.get("output"):
            # 尝试从输出中提取错误
            output = result["output"]
            # 检测 ❌ 标记
            if "❌" in output:
                # 提取包含 ❌ 的行及其上下文
                lines = output.split("\n")
                error_lines = []
                for i, line in enumerate(lines):
                    if "❌" in line:
                        # 获取上下文（前后各2行）
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        error_lines.extend(lines[start:end])
                        break
                if error_lines:
                    return "\n".join(error_lines)
            # 检测 Python 异常
            if "Traceback" in output or "Error:" in output or "Exception:" in output:
                # 提取异常部分
                lines = output.split("\n")
                error_start = None
                for i, line in enumerate(lines):
                    if "Traceback" in line or line.strip().startswith("Error") or line.strip().startswith("Exception"):
                        error_start = i
                        break
                if error_start is not None:
                    return "\n".join(lines[error_start:error_start + 10])  # 返回最多10行错误信息
        return "执行失败（未知错误）"
    return None


def is_execution_success(result: Dict[str, Any]) -> bool:
    """
    判断执行结果是否成功

    检查：
    1. 状态为 success
    2. 输出中没有 ❌ 标记（可能是部分成功但有警告）
    """
    if result.get("status") != "success":
        return False

    output = result.get("output", "")
    # 检查是否有致命错误标记
    fatal_markers = ["❌ 代码执行报错", "❌ Docker API 错误", "❌ 创建容器失败", "❌ 执行超时"]
    for marker in fatal_markers:
        if marker in output:
            return False

    return True