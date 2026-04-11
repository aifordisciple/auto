"""
执行计划数据结构模块

定义超级执行者 V2 的核心数据结构：
- ExecutionStepType: 执行步骤类型枚举
- ExecutionStatus: 执行状态枚举
- ExecutionStep: 执行步骤
- ExecutionPlan: 执行计划（DAG 结构）
- ExecutionResult: 执行结果
"""

from typing import TypedDict, List, Dict, Any, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


# ==========================================
# ✨ 枚举定义
# ==========================================

class ExecutionStepType(str, Enum):
    """执行步骤类型"""
    CODE_EXECUTION = "code_execution"      # 代码执行 (Python/R)
    DATA_PROBE = "data_probe"              # 数据探查 (预览文件、查看目录)
    FILE_OPERATION = "file_operation"      # 文件操作 (复制、移动、删除)
    SKILL_CALL = "skill_call"              # 技能调用 (使用预定义 SKILL)
    CONDITION_CHECK = "condition_check"    # 条件检查


class ExecutionStatus(str, Enum):
    """执行状态"""
    PENDING = "pending"                    # 待执行
    WAITING_CONFIRM = "waiting_confirm"    # 等待用户确认
    CONFIRMED = "confirmed"                # 已确认
    RUNNING = "running"                    # 执行中
    SUCCESS = "success"                    # 成功
    FAILED = "failed"                      # 失败
    SKIPPED = "skipped"                    # 跳过


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"            # 低风险：只读操作
    MEDIUM = "medium"      # 中风险：创建文件
    HIGH = "high"          # 高风险：删除、覆盖操作


# ==========================================
# ✨ 执行步骤
# ==========================================

@dataclass
class ExecutionStep:
    """
    执行步骤

    表示执行计划中的一个原子操作单元。
    """
    # 基本信息
    step_id: str                           # 步骤唯一标识 (step_1, step_2, ...)
    name: str                              # 步骤名称 (简短描述)
    description: str                       # 步骤详细描述
    step_type: ExecutionStepType           # 步骤类型

    # 工具和参数
    tool_id: str                           # 工具ID: execute-python, scan_workspace, skill_id 等
    parameters: Dict[str, Any] = field(default_factory=dict)

    # 代码内容（仅 code_execution 类型）
    code: Optional[str] = None
    language: Optional[Literal["python", "r"]] = None

    # 依赖关系 (DAG 边)
    depends_on: List[str] = field(default_factory=list)  # 依赖的 step_id 列表

    # 输入输出
    input_files: List[str] = field(default_factory=list)    # 输入文件路径
    output_files: List[str] = field(default_factory=list)   # 输出文件路径

    # 执行配置
    timeout: int = 300                     # 超时时间（秒）
    retry_on_failure: bool = True          # 失败时是否重试
    max_retries: int = 3                   # 最大重试次数

    # 执行状态
    status: ExecutionStatus = ExecutionStatus.PENDING
    output: Optional[str] = None           # 执行输出
    error: Optional[str] = None            # 错误信息
    exit_code: int = 0                     # 退出码
    retry_count: int = 0                   # 已重试次数
    execution_time: float = 0.0            # 执行耗时（秒）
    generated_files: List[str] = field(default_factory=list)  # 生成的文件路径

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 JSON 序列化）"""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "step_type": self.step_type.value,
            "tool_id": self.tool_id,
            "parameters": self.parameters,
            "code": self.code,
            "language": self.language,
            "depends_on": self.depends_on,
            "input_files": self.input_files,
            "output_files": self.output_files,
            "timeout": self.timeout,
            "retry_on_failure": self.retry_on_failure,
            "max_retries": self.max_retries,
            "status": self.status.value,
            "output": self.output[:500] if self.output and len(self.output) > 500 else self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "retry_count": self.retry_count,
            "execution_time": self.execution_time,
            "generated_files": self.generated_files
        }


# ==========================================
# ✨ 执行计划 (DAG 结构)
# ==========================================

@dataclass
class ExecutionPlan:
    """
    执行计划（DAG 结构）

    表示一个完整的任务执行计划，包含多个步骤及其依赖关系。
    """
    # 基本信息
    plan_id: str                           # 计划唯一标识
    user_intent: str                       # 用户原始意图描述
    raw_input: str = ""                    # 用户原始输入

    # 步骤列表（DAG 节点）
    steps: List[ExecutionStep] = field(default_factory=list)

    # 执行顺序（拓扑排序后的 step_id 列表）
    execution_order: List[str] = field(default_factory=list)

    # 全局配置
    project_id: str = ""
    user_id: int = 0
    output_dir: str = ""

    # 元数据
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    estimated_time: str = ""               # 预计执行时间
    risk_level: RiskLevel = RiskLevel.LOW  # 风险等级

    # 提示和注意事项
    notes: List[str] = field(default_factory=list)

    # 执行状态
    status: ExecutionStatus = ExecutionStatus.PENDING
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0

    def __post_init__(self):
        """初始化后处理"""
        self.total_steps = len(self.steps)

    def get_step(self, step_id: str) -> Optional[ExecutionStep]:
        """获取指定步骤"""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_dependent_steps(self, step_id: str) -> List[ExecutionStep]:
        """获取依赖于指定步骤的所有步骤"""
        return [s for s in self.steps if step_id in s.depends_on]

    def get_ready_steps(self) -> List[ExecutionStep]:
        """
        获取可执行的步骤（依赖已满足）

        返回状态为 PENDING 且所有依赖都已成功的步骤。
        """
        ready = []
        for step in self.steps:
            if step.status != ExecutionStatus.PENDING:
                continue

            # 检查所有依赖是否已完成
            deps_satisfied = True
            for dep_id in step.depends_on:
                dep_step = self.get_step(dep_id)
                if dep_step is None or dep_step.status != ExecutionStatus.SUCCESS:
                    deps_satisfied = False
                    break

            if deps_satisfied:
                ready.append(step)

        return ready

    def get_parallel_steps(self) -> List[List[ExecutionStep]]:
        """
        获取可并行执行的步骤层级

        返回层级列表，同一层级的步骤可以并行执行。
        """
        if self.execution_order:
            # 已有排序结果，直接使用
            pass
        else:
            self.topological_sort()

        # 按依赖深度分组
        levels: List[List[ExecutionStep]] = []
        assigned = set()

        while len(assigned) < len(self.steps):
            level = []
            for step in self.steps:
                if step.step_id in assigned:
                    continue
                # 检查所有依赖是否已分配
                if all(dep_id in assigned for dep_id in step.depends_on):
                    level.append(step)

            if not level:
                # 存在循环依赖，退出
                break

            for step in level:
                assigned.add(step.step_id)
            levels.append(level)

        return levels

    def topological_sort(self) -> List[str]:
        """
        拓扑排序，返回执行顺序

        使用 Kahn's 算法进行拓扑排序。
        """
        # 计算入度
        in_degree = {s.step_id: len(s.depends_on) for s in self.steps}

        # 入度为 0 的节点入队
        queue = [s.step_id for s in self.steps if in_degree[s.step_id] == 0]
        result = []

        while queue:
            # 取出一个节点
            current = queue.pop(0)
            result.append(current)

            # 减少依赖于当前节点的节点的入度
            for step in self.steps:
                if current in step.depends_on:
                    in_degree[step.step_id] -= 1
                    if in_degree[step.step_id] == 0:
                        queue.append(step.step_id)

        self.execution_order = result
        return result

    def update_progress(self):
        """更新执行进度"""
        self.completed_steps = sum(1 for s in self.steps if s.status == ExecutionStatus.SUCCESS)
        self.failed_steps = sum(1 for s in self.steps if s.status == ExecutionStatus.FAILED)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 JSON 序列化）"""
        return {
            "plan_id": self.plan_id,
            "user_intent": self.user_intent,
            "raw_input": self.raw_input[:500] if len(self.raw_input) > 500 else self.raw_input,
            "steps": [s.to_dict() for s in self.steps],
            "execution_order": self.execution_order,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "output_dir": self.output_dir,
            "created_at": self.created_at,
            "estimated_time": self.estimated_time,
            "risk_level": self.risk_level.value,
            "notes": self.notes,
            "status": self.status.value,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionPlan':
        """从字典创建实例"""
        steps = []
        for step_data in data.get("steps", []):
            step = ExecutionStep(
                step_id=step_data["step_id"],
                name=step_data["name"],
                description=step_data.get("description", ""),
                step_type=ExecutionStepType(step_data["step_type"]),
                tool_id=step_data["tool_id"],
                parameters=step_data.get("parameters", {}),
                code=step_data.get("code"),
                language=step_data.get("language"),
                depends_on=step_data.get("depends_on", []),
                input_files=step_data.get("input_files", []),
                output_files=step_data.get("output_files", []),
                timeout=step_data.get("timeout", 300),
                retry_on_failure=step_data.get("retry_on_failure", True),
                max_retries=step_data.get("max_retries", 3),
                status=ExecutionStatus(step_data.get("status", "pending")),
                output=step_data.get("output"),
                error=step_data.get("error"),
                exit_code=step_data.get("exit_code", 0),
                retry_count=step_data.get("retry_count", 0),
                execution_time=step_data.get("execution_time", 0.0),
                generated_files=step_data.get("generated_files", [])
            )
            steps.append(step)

        return cls(
            plan_id=data["plan_id"],
            user_intent=data["user_intent"],
            raw_input=data.get("raw_input", ""),
            steps=steps,
            execution_order=data.get("execution_order", []),
            project_id=data.get("project_id", ""),
            user_id=data.get("user_id", 0),
            output_dir=data.get("output_dir", ""),
            created_at=data.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S")),
            estimated_time=data.get("estimated_time", ""),
            risk_level=RiskLevel(data.get("risk_level", "low")),
            notes=data.get("notes", []),
            status=ExecutionStatus(data.get("status", "pending")),
            total_steps=data.get("total_steps", len(steps)),
            completed_steps=data.get("completed_steps", 0),
            failed_steps=data.get("failed_steps", 0)
        )


# ==========================================
# ✨ 执行结果
# ==========================================

@dataclass
class ExecutionResult:
    """
    执行结果

    表示执行计划完成后的汇总结果。
    """
    plan_id: str
    success: bool

    # 步骤统计
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    total_retries: int = 0

    # 执行时间
    execution_time: float = 0.0            # 总执行时间（秒）
    start_time: str = ""
    end_time: str = ""

    # 输出目录
    output_dir: str = ""

    # 生成的文件
    generated_files: List[Dict[str, Any]] = field(default_factory=list)

    # 步骤执行摘要
    step_summaries: List[Dict[str, Any]] = field(default_factory=list)

    # 路径映射（假路径 -> 真实路径）
    path_mappings: Dict[str, str] = field(default_factory=dict)

    # 错误信息
    errors: List[str] = field(default_factory=list)

    # 最终输出（用于展示给用户）
    final_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 JSON 序列化）"""
        return {
            "plan_id": self.plan_id,
            "success": self.success,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "total_retries": self.total_retries,
            "execution_time": self.execution_time,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "output_dir": self.output_dir,
            "generated_files": self.generated_files,
            "step_summaries": self.step_summaries,
            "path_mappings": self.path_mappings,
            "errors": self.errors,
            "final_output": self.final_output
        }


# ==========================================
# ✨ 辅助函数
# ==========================================

def generate_plan_id() -> str:
    """生成计划 ID"""
    return f"plan_{uuid.uuid4().hex[:12]}"


def generate_step_id(order: int) -> str:
    """生成步骤 ID"""
    return f"step_{order + 1}"


# ==========================================
# ✨ 模块初始化
# ==========================================

from app.core.logger import log
log.info("📋 执行计划数据结构模块已加载")