"""
SKILL Executor - SKILL 执行器

整合样本表预处理和并行执行，支持：
- 样本表解析与参数预处理
- 多种执行器类型（Python_env, R_env, Logical_Blueprint）
- 向后兼容旧参数格式
- Docker 沙箱实际执行（非模拟模式）
- 用户级包依赖检查（新增）
- 原生执行模式（仅官方技能可用）
- 执行监控记录（新增）
- 自动重试机制（新增）
"""

import time
import random
import asyncio
from typing import Dict, Any, Optional, List, Callable, Awaitable
from pathlib import Path
import os
import json
from datetime import datetime, timezone
from enum import Enum

from app.core.logger import log
from app.core.sample_table import SampleTable
from app.core.skill_parser import get_skill_parser, SkillBundleParser


class SkillExecutionError(Exception):
    """SKILL 执行错误"""
    pass


class MissingDependencyError(Exception):
    """缺失依赖错误"""
    def __init__(self, missing_packages: List[Dict[str, str]]):
        self.missing_packages = missing_packages
        message = f"缺失依赖包: {', '.join(p['name'] for p in missing_packages)}"
        super().__init__(message)


# ✨ 沙箱执行超时配置
SKILL_EXECUTION_TIMEOUT = 3600  # 默认 1 小时

# ✨ 重试配置
DEFAULT_RETRY_CONFIG = {
    "max_retries": 3,
    "base_delay": 1.0,
    "max_delay": 60.0,
    "jitter_factor": 0.1,
}


# ==========================================
# 重试错误检测
# ==========================================

# 可重试错误关键词
RETRYABLE_ERROR_PATTERNS = [
    # 网络错误
    "connection refused",
    "network is unreachable",
    "timeout",
    "etimedout",
    "econnrefused",
    "econnreset",
    "econnaborted",
    "socket error",
    "connection reset",
    # 资源错误
    "out of memory",
    "resource temporarily unavailable",
    "too many open files",
    "cannot allocate memory",
    # Docker 错误
    "docker daemon not responding",
    "container exited with error",
    "cannot connect to the docker daemon",
    "docker is unavailable",
    "no such container",
    "container not found",
    # 临时性错误
    "temporary failure",
    "try again",
    "please retry",
]

# 不可重试错误关键词
NON_RETRYABLE_ERROR_PATTERNS = [
    # 代码错误
    "syntaxerror",
    "importerror",
    "modulenotfounderror",
    "keyerror",
    "valueerror",
    "typeerror",
    "attributeerror",
    "nameerror",
    "indexerror",
    # 权限错误
    "permission denied",
    "access denied",
    "unauthorized",
    "forbidden",
    # 配置错误
    "configerror",
    "invalid parameter",
    "missing required",
]


def is_retryable_error(error: Exception) -> bool:
    """
    判断错误是否可重试

    Args:
        error: 异常对象

    Returns:
        True 如果错误可重试，否则 False
    """
    error_message = str(error).lower()

    # 先检查不可重试错误
    for pattern in NON_RETRYABLE_ERROR_PATTERNS:
        if pattern in error_message:
            return False

    # 检查可重试错误
    for pattern in RETRYABLE_ERROR_PATTERNS:
        if pattern in error_message:
            return True

    # 默认不可重试
    return False


# ==========================================
# 指数退避计算
# ==========================================

def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.1,
) -> float:
    """
    计算指数退避时间

    使用指数增长 + 随机抖动策略

    Args:
        attempt: 当前重试次数（从1开始）
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        jitter_factor: 抖动因子（0-1）

    Returns:
        退避时间（秒）
    """
    # 指数增长：base_delay * 2^(attempt-1)
    delay = base_delay * (2 ** (attempt - 1))

    # 添加随机抖动（在限制之前）
    jitter = delay * jitter_factor * random.random()
    delay = delay + jitter

    # 限制最大值（在抖动之后）
    delay = min(delay, max_delay)

    return round(delay, 3)


# ==========================================
# 熔断器
# ==========================================

class CircuitState(str, Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态，允许请求
    OPEN = "open"          # 熔断状态，拒绝请求
    HALF_OPEN = "half_open"  # 半开状态，允许探测请求


class CircuitBreaker:
    """
    熔断器

    防止级联失败，当连续失败达到阈值时打开熔断器

    状态转换：
    - CLOSED -> OPEN: 连续失败次数达到阈值
    - OPEN -> HALF_OPEN: 超时后进入半开状态
    - HALF_OPEN -> CLOSED: 探测成功
    - HALF_OPEN -> OPEN: 探测失败
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
    ):
        """
        初始化熔断器

        Args:
            failure_threshold: 失败阈值
            reset_timeout: 重置超时时间（秒）
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._last_failure_time: Optional[float] = None

    def is_open(self) -> bool:
        """检查熔断器是否打开"""
        if self._state == CircuitState.OPEN:
            # 检查是否应该进入半开状态
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.reset_timeout:
                    self._state = CircuitState.HALF_OPEN
                    return False
            return True
        return False

    def should_allow(self) -> bool:
        """
        检查是否应该允许请求

        Returns:
            True 如果允许请求，否则 False
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.HALF_OPEN:
            return True

        if self._state == CircuitState.OPEN:
            # 检查超时
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.reset_timeout:
                    self._state = CircuitState.HALF_OPEN
                    return True
            return False

        return False

    def record_success(self) -> None:
        """记录成功"""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """记录失败"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下失败，立即打开
            self._state = CircuitState.OPEN
        elif self._failure_count >= self.failure_threshold:
            # 达到阈值，打开熔断器
            self._state = CircuitState.OPEN

    def get_state(self) -> CircuitState:
        """获取当前状态"""
        return self._state


# ==========================================
# 重试追踪器
# ==========================================

class RetryTracker:
    """
    重试追踪器

    记录重试过程中的详细信息
    """

    def __init__(self, skill_id: str):
        self.skill_id = skill_id
        self._attempts: List[Dict[str, Any]] = []
        self._start_time = time.time()

    def record_attempt(self, success: bool, error: Optional[str] = None) -> None:
        """
        记录一次尝试

        Args:
            success: 是否成功
            error: 错误信息（如果有）
        """
        self._attempts.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "error": error,
        })

    def get_summary(self) -> Dict[str, Any]:
        """
        获取重试摘要

        Returns:
            包含重试信息的字典
        """
        total_attempts = len(self._attempts)
        failed_attempts = sum(1 for a in self._attempts if not a["success"])
        success = any(a["success"] for a in self._attempts)

        return {
            "skill_id": self.skill_id,
            "total_attempts": total_attempts,
            "failed_attempts": failed_attempts,
            "success": success,
            "duration_seconds": round(time.time() - self._start_time, 2),
            "attempts": self._attempts,
        }


# ==========================================
# 重试配置获取
# ==========================================

def get_retry_config(skill_def: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    获取重试配置

    优先级：技能定义 > 默认配置

    Args:
        skill_def: 技能定义（可选）

    Returns:
        重试配置字典
    """
    config = DEFAULT_RETRY_CONFIG.copy()

    if skill_def:
        retry_config = skill_def.get("retry", {})
        if retry_config:
            config.update(retry_config)

    return config


# ==========================================
# 带重试的执行函数
# ==========================================

async def execute_with_retry(
    execute_func: Callable[[], Awaitable[Dict[str, Any]]],
    skill_id: str,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.1,
) -> Dict[str, Any]:
    """
    带自动重试的执行函数

    Args:
        execute_func: 执行函数（异步）
        skill_id: 技能 ID
        max_retries: 最大重试次数
        base_delay: 基础延迟时间
        max_delay: 最大延迟时间
        jitter_factor: 抖动因子

    Returns:
        执行结果字典
    """
    tracker = RetryTracker(skill_id)
    last_error = None

    for attempt in range(max_retries + 1):  # 初始 + 重试
        try:
            result = await execute_func()

            # 记录成功
            tracker.record_attempt(success=True)

            # 添加重试信息到结果
            if tracker.get_summary()["total_attempts"] > 1:
                result["retry_info"] = tracker.get_summary()

            return result

        except Exception as e:
            last_error = e
            error_message = str(e)

            # 记录失败
            tracker.record_attempt(success=False, error=error_message)

            # 检查是否可重试
            if not is_retryable_error(e):
                log.warning(f"[Retry] 不可重试错误: {error_message}")
                return {
                    "status": "failed",
                    "error": error_message,
                    "skill_id": skill_id,
                    "retry_info": tracker.get_summary(),
                }

            # 检查是否还有重试次数
            if attempt >= max_retries:
                log.warning(f"[Retry] 达到最大重试次数: {max_retries}")
                return {
                    "status": "failed",
                    "error": error_message,
                    "skill_id": skill_id,
                    "retry_info": tracker.get_summary(),
                }

            # 计算退避时间
            backoff = calculate_backoff(
                attempt + 1,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter_factor=jitter_factor,
            )

            log.info(
                f"[Retry] 第 {attempt + 1}/{max_retries} 次重试，"
                f"等待 {backoff:.2f}s，错误: {error_message[:100]}"
            )

            # 等待退避时间
            await asyncio.sleep(backoff)

    # 不应该到达这里
    return {
        "status": "failed",
        "error": str(last_error),
        "skill_id": skill_id,
        "retry_info": tracker.get_summary(),
    }


class SkillExecutor:
    """
    SKILL 执行器

    负责：
    1. 预处理参数（解析样本表）
    2. 根据执行器类型分发执行
    3. 向后兼容处理

    Examples:
        executor = SkillExecutor("singlecell_seurat_pipeline_01", params, project_id)
        result = executor.execute()
    """

    def __init__(
        self,
        skill_id: str,
        params: Dict[str, Any],
        project_id: str,
        task_id: Optional[str] = None,
        user_id: Optional[int] = None,  # ✨ 新增：用户 ID，用于包依赖检查
        skip_dependency_check: bool = False,  # ✨ 新增：跳过依赖检查
    ):
        """
        初始化 SKILL 执行器

        Args:
            skill_id: SKILL 唯一标识符
            params: 执行参数
            project_id: 项目 ID
            task_id: 任务 ID（可选）
            user_id: 用户 ID（可选，用于包依赖检查）
            skip_dependency_check: 是否跳过依赖检查（默认 False）
        """
        self.skill_id = skill_id
        self.params = params.copy()  # 避免修改原始参数
        self.project_id = project_id
        self.task_id = task_id
        self.user_id = user_id
        self.skip_dependency_check = skip_dependency_check

        # 样本表（解析后）
        self.sample_table: Optional[SampleTable] = None

        # 加载 SKILL 定义
        parser = get_skill_parser()
        self.skill_def = parser.get_skill_by_id(skill_id)

        if not self.skill_def:
            raise SkillExecutionError(f"SKILL not found: {skill_id}")

        log.info(f"[SkillExecutor] 初始化执行器: {skill_id}, project={project_id}, user_id={user_id}")

    def preprocess(self) -> None:
        """
        预处理参数

        主要工作：
        1. 解析样本表（如果提供）
        2. 转换为旧格式参数（向后兼容）
        3. 注入系统变量（PROJECT_ID, TASK_OUT_DIR）
        """
        # 1. 处理样本表
        if "sample_table" in self.params and self.params["sample_table"]:
            self._process_sample_table()

        # 2. 注入系统变量
        self._inject_system_vars()

        log.info(f"[SkillExecutor] 预处理完成，参数数量: {len(self.params)}")

    def _process_sample_table(self) -> None:
        """
        处理样本表参数

        支持两种输入方式：
        1. 文件路径（以 / 或 ./ 开头）
        2. TSV 内容字符串
        """
        table_input = self.params["sample_table"]

        if not table_input:
            return

        try:
            # 判断输入类型
            if table_input.startswith("/") or table_input.startswith("./"):
                # 文件路径
                log.info(f"[SkillExecutor] 从文件加载样本表: {table_input}")
                self.sample_table = SampleTable.from_file(table_input)
            else:
                # TSV 内容
                log.info("[SkillExecutor] 解析内嵌样本表内容")
                # 检测是否有表头
                has_header = self._detect_header(table_input)
                self.sample_table = SampleTable.parse(table_input, has_header=has_header)

            # 验证样本表
            errors = self.sample_table.validate()
            if errors:
                raise SkillExecutionError(f"样本表验证失败: {', '.join(errors)}")

            # 转换为旧格式并合并
            legacy_params = self.sample_table.to_legacy_format()
            for key, value in legacy_params.items():
                # 如果原参数中没有对应字段，则填充
                if key not in self.params or not self.params[key]:
                    self.params[key] = value

            # 保存解析后的结构（供脚本使用）
            self.params["_sample_table_parsed"] = self.sample_table.model_dump()
            self.params["_sample_table_summary"] = self.sample_table.summary()

            log.info(
                f"[SkillExecutor] 样本表解析完成: "
                f"{self.sample_table.sample_count} 样本, "
                f"{self.sample_table.group_count} 分组"
            )

        except Exception as e:
            log.error(f"[SkillExecutor] 样本表处理失败: {e}")
            raise SkillExecutionError(f"样本表处理失败: {str(e)}")

    def _detect_header(self, content: str) -> bool:
        """
        检测 TSV 内容是否包含表头

        启发式规则：
        - 第一行第一列是已知的表头名称
        - 或第一行包含 path/type/group 等关键词
        """
        lines = [l for l in content.strip().split("\n") if l.strip() and not l.startswith("#")]
        if not lines:
            return False

        first_line = lines[0].lower()
        header_indicators = ["name", "sample", "path", "input", "type", "group"]

        return any(indicator in first_line for indicator in header_indicators)

    def _inject_system_vars(self) -> None:
        """注入系统变量"""
        # 项目 ID
        self.params["PROJECT_ID"] = self.project_id

        # 任务输出目录
        if self.task_id:
            self.params["TASK_ID"] = self.task_id
            self.params["TASK_OUT_DIR"] = f"/workspace/project_{self.project_id}/results/task_{self.task_id}"
        else:
            self.params["TASK_OUT_DIR"] = f"/workspace/project_{self.project_id}/results/default"

        # 确保输出目录存在
        out_dir = self.params.get("output_dir") or self.params["TASK_OUT_DIR"]
        self.params["output_dir"] = out_dir

    def execute(self) -> Dict[str, Any]:
        """
        执行 SKILL

        根据技能配置的执行模式，选择 Docker 容器执行或原生系统执行。

        Returns:
            执行结果字典
        """
        # ✨ 记录开始时间
        start_time = time.time()

        # 预处理
        self.preprocess()

        # ✨ 依赖检查（新增）
        if not self.skip_dependency_check and self.user_id:
            missing = self.check_dependencies()
            if missing:
                log.warning(f"[SkillExecutor] 缺失依赖包: {missing}")
                return {
                    "status": "missing_dependencies",
                    "error": f"缺失依赖包，请先安装",
                    "missing_packages": missing,
                    "skill_id": self.skill_id,
                    "install_hint": self._generate_install_hint(missing),
                }

        # 获取执行器类型
        executor_type = self.skill_def.get("metadata", {}).get("executor_type", "Python_env")

        # ✨ 获取执行模式（Docker 或 Native）
        execution_mode = self._get_execution_mode()

        log.info(f"[SkillExecutor] 开始执行，类型: {executor_type}, 模式: {execution_mode}")

        try:
            # ✨ 根据执行模式分发
            if execution_mode == "native":
                log.info(f"[SkillExecutor] 使用原生执行模式")
                # Logical_Blueprint 类型需要特殊处理（Nextflow 工作流）
                if executor_type == "Logical_Blueprint":
                    result = self._execute_nextflow_native()
                else:
                    result = self._execute_native(executor_type)
            else:
                # Docker 模式（默认）
                if executor_type == "Logical_Blueprint":
                    result = self._execute_nextflow()
                elif executor_type == "Python_env":
                    result = self._execute_python()
                elif executor_type == "R_env":
                    result = self._execute_r()
                elif executor_type == "Bash_env":
                    result = self._execute_bash()
                else:
                    raise SkillExecutionError(f"未知的执行器类型: {executor_type}")

        except Exception as e:
            log.error(f"[SkillExecutor] 执行失败: {e}")
            result = {
                "status": "failed",
                "error": str(e),
                "skill_id": self.skill_id,
            }

        # ✨ 记录监控数据
        execution_time = time.time() - start_time
        self._record_execution(result.get("status", "failed"), execution_time, result.get("error"))

        return result

    async def execute_async_with_retry(self) -> Dict[str, Any]:
        """
        异步执行 SKILL，带自动重试

        使用指数退避策略重试可重试错误

        Returns:
            执行结果字典
        """
        retry_config = get_retry_config(self.skill_def)

        tracker = RetryTracker(self.skill_id)
        last_error = None
        max_retries = retry_config["max_retries"]

        for attempt in range(max_retries + 1):  # 初始 + 重试
            try:
                # 执行技能
                result = self.execute()

                # 检查结果状态
                if result.get("status") == "success":
                    tracker.record_attempt(success=True)

                    # 添加重试信息
                    if tracker.get_summary()["total_attempts"] > 1:
                        result["retry_info"] = tracker.get_summary()

                    return result

                # 执行失败，检查是否可重试
                error_message = result.get("error", "Unknown error")
                tracker.record_attempt(success=False, error=error_message)

                # 构造异常用于判断
                error = Exception(error_message)

                if not is_retryable_error(error):
                    log.warning(f"[SkillExecutor] 不可重试错误: {error_message}")
                    result["retry_info"] = tracker.get_summary()
                    return result

                # 检查是否还有重试次数
                if attempt >= max_retries:
                    log.warning(f"[SkillExecutor] 达到最大重试次数: {max_retries}")
                    result["retry_info"] = tracker.get_summary()
                    return result

                # 计算退避时间
                backoff = calculate_backoff(
                    attempt + 1,
                    base_delay=retry_config["base_delay"],
                    max_delay=retry_config["max_delay"],
                    jitter_factor=retry_config["jitter_factor"],
                )

                log.info(
                    f"[SkillExecutor] 第 {attempt + 1}/{max_retries} 次重试，"
                    f"等待 {backoff:.2f}s，错误: {error_message[:100]}"
                )

                # 等待退避时间
                await asyncio.sleep(backoff)

            except Exception as e:
                last_error = e
                error_message = str(e)
                tracker.record_attempt(success=False, error=error_message)

                if not is_retryable_error(e):
                    log.warning(f"[SkillExecutor] 不可重试异常: {error_message}")
                    return {
                        "status": "failed",
                        "error": error_message,
                        "skill_id": self.skill_id,
                        "retry_info": tracker.get_summary(),
                    }

                if attempt >= max_retries:
                    return {
                        "status": "failed",
                        "error": error_message,
                        "skill_id": self.skill_id,
                        "retry_info": tracker.get_summary(),
                    }

                # 计算退避
                backoff = calculate_backoff(
                    attempt + 1,
                    base_delay=retry_config["base_delay"],
                    max_delay=retry_config["max_delay"],
                    jitter_factor=retry_config["jitter_factor"],
                )

                log.info(
                    f"[SkillExecutor] 异常重试 {attempt + 1}/{max_retries}，"
                    f"等待 {backoff:.2f}s"
                )

                await asyncio.sleep(backoff)

        return {
            "status": "failed",
            "error": str(last_error) if last_error else "Unknown error",
            "skill_id": self.skill_id,
            "retry_info": tracker.get_summary(),
        }

    def _record_execution(self, status: str, execution_time: float, error_message: Optional[str] = None):
        """
        记录技能执行监控数据

        Args:
            status: 执行状态
            execution_time: 执行时间（秒）
            error_message: 错误信息（可选）
        """
        # 监控记录
        try:
            from app.services.skill_monitor import record_skill_execution

            # 映射状态到监控状态
            monitor_status = "SUCCESS" if status == "success" else "FAILURE"
            if "timeout" in str(error_message).lower():
                monitor_status = "TIMEOUT"

            record_skill_execution(
                skill_id=self.skill_id,
                status=monitor_status,
                execution_time=execution_time,
                error_message=error_message
            )
        except Exception as e:
            log.warning(f"[SkillExecutor] 记录监控数据失败: {e}")

    def _get_execution_mode(self) -> str:
        """
        获取技能执行模式

        优先级：
        1. 从数据库中读取技能的 execution_mode 字段
        2. 如果未设置，默认返回 "docker"

        Returns:
            "docker" 或 "native"
        """
        try:
            from sqlmodel import select
            from app.core.database import get_session
            from app.models.domain import SkillAsset

            # 获取数据库会话
            session_gen = get_session()
            session = next(session_gen)

            try:
                # 查询技能的执行模式
                statement = select(SkillAsset).where(SkillAsset.skill_id == self.skill_id)
                skill = session.exec(statement).first()

                if skill and skill.execution_mode == "native":
                    # ✨ 安全检查：验证是否为官方技能
                    from app.services.native_executor import is_official_skill

                    if not is_official_skill(self.skill_id, skill.owner_id):
                        log.warning(
                            f"[SkillExecutor] 非官方技能 {self.skill_id} 尝试使用原生执行，"
                            f"已降级为 Docker 模式"
                        )
                        return "docker"

                    log.info(f"[SkillExecutor] 技能 {self.skill_id} 配置为原生执行模式")
                    return "native"

                return "docker"

            finally:
                session.close()

        except Exception as e:
            log.warning(f"[SkillExecutor] 获取执行模式失败: {e}，使用默认 Docker 模式")
            return "docker"

    def _execute_native(self, executor_type: str) -> Dict[str, Any]:
        """
        原生执行技能脚本

        直接在宿主机环境中执行脚本，绕过 Docker 容器。
        仅限官方技能使用。

        Args:
            executor_type: 执行器类型 (Python_env, R_env, Bash_env)

        Returns:
            执行结果字典
        """
        from app.services.native_executor import run_native

        # 获取入口脚本路径
        entry_point = self.skill_def.get("metadata", {}).get("entry_point")
        bundle_path = self.skill_def.get("bundle_path")

        if not entry_point or not bundle_path:
            raise SkillExecutionError("SKILL 缺少 entry_point 或 bundle_path")

        script_path = str(Path(bundle_path) / entry_point)

        if not Path(script_path).exists():
            raise SkillExecutionError(f"入口脚本不存在: {script_path}")

        log.info(f"[SkillExecutor] 原生执行脚本: {script_path}")

        # 确定语言类型
        language_map = {
            "Python_env": "python",
            "R_env": "r",
            "Bash_env": "bash",
        }
        language = language_map.get(executor_type, "python")

        # 构建命令行参数
        args_list = self._build_command_args()

        # 调用原生执行器
        output, exit_code, billing_info = run_native(
            script_path=script_path,
            command=args_list,
            language=language,
            environment=self._build_environment(),
            timeout=self._get_timeout(),
            user_id=self.user_id,
            skill_id=self.skill_id,
        )

        # 解析执行结果
        if exit_code == 0:
            log.info(f"[SkillExecutor] 原生执行成功")
            return {
                "status": "success",
                "executor": f"native_{language}",
                "execution_mode": "native",
                "skill_id": self.skill_id,
                "project_id": self.project_id,
                "output": output[:2000] if len(output) > 2000 else output,
                "output_dir": self.params.get("output_dir"),
                "sample_count": self.sample_table.sample_count if self.sample_table else 0,
                "duration_seconds": billing_info.get("duration_seconds", 0),
            }
        else:
            log.error(f"[SkillExecutor] 原生执行失败: {output[:500]}")
            return {
                "status": "failed",
                "error": output[:1000],
                "exit_code": exit_code,
                "execution_mode": "native",
                "skill_id": self.skill_id,
            }

    def check_dependencies(self) -> List[Dict[str, str]]:
        """
        检查 SKILL 依赖是否已安装

        Returns:
            缺失的依赖包列表 [{"name": "numpy", "language": "python"}, ...]
        """
        # 从 SKILL 定义中获取依赖列表
        dependencies = self._extract_dependencies()

        if not dependencies:
            log.info(f"[SkillExecutor] SKILL 无依赖声明，跳过检查")
            return []

        log.info(f"[SkillExecutor] 检查依赖: {dependencies}")

        # 使用包安装服务检查
        from app.core.database import get_session
        from app.services.package_installer import PackageInstaller

        missing = []
        try:
            # 获取数据库会话
            session_gen = get_session()
            session = next(session_gen)

            try:
                installer = PackageInstaller(session)
                missing = installer.check_missing_dependencies(
                    user_id=self.user_id,
                    required_packages=dependencies,
                )
            finally:
                session.close()
        except Exception as e:
            log.warning(f"[SkillExecutor] 依赖检查失败: {e}")
            # 检查失败时，假设所有依赖都已安装（降级处理）
            return []

        return missing

    def _extract_dependencies(self) -> List[Dict[str, str]]:
        """
        从 SKILL 定义中提取依赖列表

        支持的依赖格式：
        1. metadata.dependencies: ["numpy", "pandas"]
        2. metadata.dependencies: [{"name": "numpy", "language": "python"}]

        Returns:
            依赖列表
        """
        metadata = self.skill_def.get("metadata", {})
        raw_deps = metadata.get("dependencies", [])

        if not raw_deps:
            return []

        dependencies = []
        for dep in raw_deps:
            if isinstance(dep, str):
                # 简单字符串格式，默认为 Python 包
                dependencies.append({
                    "name": dep,
                    "language": "python",
                })
            elif isinstance(dep, dict):
                # 详细格式
                dependencies.append({
                    "name": dep.get("name"),
                    "language": dep.get("language", "python"),
                    "version": dep.get("version"),
                })

        return dependencies

    def _generate_install_hint(self, missing: List[Dict[str, str]]) -> str:
        """
        生成安装提示信息

        Args:
            missing: 缺失的包列表

        Returns:
            安装提示文本
        """
        if not missing:
            return ""

        hints = ["需要安装以下包："]
        for pkg in missing:
            name = pkg.get("name")
            lang = pkg.get("language", "python")
            if lang == "python":
                hints.append(f"  - {name} (pip install {name})")
            else:
                hints.append(f"  - {name} (R: install.packages('{name}'))")

        hints.append("\n您可以通过以下方式安装：")
        hints.append("1. 在聊天中告诉我：'请安装 xxx 包'")
        hints.append("2. 使用包管理界面安装")

        return "\n".join(hints)

    def _execute_nextflow(self) -> Dict[str, Any]:
        """
        执行 Nextflow 流程

        Logical_Blueprint 类型的 SKILL 会被编译为 Nextflow DSL2 脚本
        """
        # 导入 Nextflow 编译器
        try:
            from app.skills.meta_nextflow_generator_bundle.scripts.nf_compiler import NextflowCompiler
        except ImportError:
            log.warning("[SkillExecutor] Nextflow 编译器不可用，使用模拟执行")
            return self._execute_mock("nextflow")

        compiler = NextflowCompiler()

        # 获取流程拓扑
        topology = self.params.get("pipeline_topology", [])

        # 编译流程
        main_nf = compiler.generate_main_script(topology, self.sample_table)

        log.info(f"[SkillExecutor] Nextflow 流程编译完成，长度: {len(main_nf)}")

        # TODO: 实际执行 Nextflow
        # result = run_nextflow(main_nf, self.params["TASK_OUT_DIR"])

        return {
            "status": "success",
            "executor": "nextflow",
            "main_nf": main_nf[:1000] + "..." if len(main_nf) > 1000 else main_nf,
            "sample_count": self.sample_table.sample_count if self.sample_table else 0,
        }

    def _execute_nextflow_native(self) -> Dict[str, Any]:
        """
        原生执行 Nextflow 流程

        对于 Logical_Blueprint 类型的技能，原生模式下：
        1. 检查宿主机是否安装了 Nextflow
        2. 如果已安装，直接在宿主机执行
        3. 如果未安装，降级到 Docker 沙箱执行

        注意：Nextflow 流程中的各个进程可能仍然需要 Docker 容器
        """
        import shutil
        from app.tools.bio_tools import run_nextflow_in_sandbox

        # 检查宿主机是否安装了 nextflow
        nextflow_path = shutil.which("nextflow")

        if not nextflow_path:
            log.warning(
                f"[SkillExecutor] 宿主机未安装 Nextflow，降级到 Docker 沙箱执行。"
                f"技能: {self.skill_id}"
            )
            # 降级到 Docker 沙箱执行
            result = self._execute_nextflow()
            result["execution_mode"] = "docker_fallback"
            result["fallback_reason"] = "宿主机未安装 Nextflow"
            return result

        log.info(f"[SkillExecutor] 使用宿主机 Nextflow: {nextflow_path}")

        # 获取工作目录
        work_dir = self.params.get("TASK_OUT_DIR") or self.params.get("output_dir")
        if not work_dir:
            raise SkillExecutionError("Nextflow 流程需要 TASK_OUT_DIR 或 output_dir 参数")

        # 构建 Nextflow 参数
        nf_params = self._build_nextflow_params()

        # 获取流程入口文件
        bundle_path = self.skill_def.get("bundle_path")
        main_nf_path = Path(bundle_path) / "nextflow" / "main.nf" if bundle_path else None

        # 如果没有 main.nf，尝试使用 process.nf
        if not main_nf_path or not main_nf_path.exists():
            main_nf_path = Path(bundle_path) / "nextflow" / "process.nf" if bundle_path else None

        if not main_nf_path or not main_nf_path.exists():
            log.warning(f"[SkillExecutor] 未找到 main.nf 或 process.nf，使用 Docker 沙箱")
            result = self._execute_nextflow()
            result["execution_mode"] = "docker_fallback"
            result["fallback_reason"] = "未找到 Nextflow 入口文件"
            return result

        # 执行 Nextflow
        try:
            import subprocess
            import time

            start_time = time.time()

            # 构建命令
            cmd = [nextflow_path, "run", str(main_nf_path)]
            for key, value in nf_params.items():
                if isinstance(value, bool):
                    if value:
                        cmd.append(f"--{key}")
                elif isinstance(value, str):
                    cmd.extend([f"--{key}", value])
                else:
                    cmd.extend([f"--{key}", str(value)])

            cmd.append("-resume")

            log.info(f"[SkillExecutor] 执行命令: {' '.join(cmd)}")

            # 设置环境变量
            env = os.environ.copy()
            env.update(self._build_environment())

            # 执行
            process = subprocess.run(
                cmd,
                cwd=work_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self._get_timeout()
            )

            duration = time.time() - start_time
            output = process.stdout + "\n" + process.stderr

            if process.returncode == 0:
                log.info(f"[SkillExecutor] Nextflow 原生执行成功，耗时: {duration:.1f}s")
                return {
                    "status": "success",
                    "executor": "nextflow_native",
                    "execution_mode": "native",
                    "skill_id": self.skill_id,
                    "project_id": self.project_id,
                    "output": output[:5000],
                    "output_dir": work_dir,
                    "sample_count": self.sample_table.sample_count if self.sample_table else 0,
                    "duration_seconds": duration,
                }
            else:
                log.error(f"[SkillExecutor] Nextflow 原生执行失败: {process.stderr[:500]}")
                return {
                    "status": "failed",
                    "executor": "nextflow_native",
                    "execution_mode": "native",
                    "skill_id": self.skill_id,
                    "error": process.stderr[:1000],
                    "exit_code": process.returncode,
                    "output": output[:5000],
                }

        except subprocess.TimeoutExpired:
            log.error(f"[SkillExecutor] Nextflow 执行超时")
            return {
                "status": "failed",
                "error": f"执行超时（{self._get_timeout()}秒）",
                "skill_id": self.skill_id,
                "execution_mode": "native",
            }
        except Exception as e:
            log.error(f"[SkillExecutor] Nextflow 原生执行异常: {e}")
            # 降级到 Docker 执行
            result = self._execute_nextflow()
            result["execution_mode"] = "docker_fallback"
            result["fallback_reason"] = str(e)
            return result

    def _build_nextflow_params(self) -> dict:
        """
        构建 Nextflow 流程参数

        从 skill_def 和 params 中提取并合并参数
        """
        params = {}

        # 从 skill_def 的 parameters_schema 中提取默认值
        schema = self.skill_def.get("parameters_schema", {})
        properties = schema.get("properties", {})
        for key, prop in properties.items():
            if "default" in prop:
                params[key] = prop["default"]

        # 用用户传入的参数覆盖默认值
        for key, value in self.params.items():
            if key not in ["TASK_OUT_DIR", "sample_sheet"]:
                params[key] = value

        # 添加样本表参数
        if self.sample_table:
            params["sample_sheet"] = self.params.get("sample_sheet", "")

        return params

    def _execute_python(self) -> Dict[str, Any]:
        """
        执行 Python 脚本

        在 Docker 沙箱中执行入口脚本
        """
        from app.tools.bio_tools import run_container

        # 获取入口脚本路径
        entry_point = self.skill_def.get("metadata", {}).get("entry_point")
        bundle_path = self.skill_def.get("bundle_path")

        if not entry_point or not bundle_path:
            raise SkillExecutionError("SKILL 缺少 entry_point 或 bundle_path")

        script_path = Path(bundle_path) / entry_point

        if not script_path.exists():
            raise SkillExecutionError(f"入口脚本不存在: {script_path}")

        log.info(f"[SkillExecutor] Python 入口脚本: {script_path}")

        # ==========================================
        # ✨ 实际 Docker 沙箱执行
        # ==========================================
        try:
            # 构建命令行参数
            args_list = self._build_command_args()

            # ✨ 将宿主机路径转换为容器内路径
            # bundle_path 格式为 /opt/data1/.../app/skills/skill_name
            # 需要转换为 /app/skills/skill_name
            container_script_path = self._convert_to_container_path(script_path)

            # 使用 cli_mode=True 执行脚本
            cmd = ["python", container_script_path] + args_list

            log.info(f"[SkillExecutor] 执行命令: {' '.join(cmd)}")

            # 调用 Docker 沙箱
            output, exit_code = run_container(
                image='autonome-tool-env',
                command=cmd,
                language="python",
                environment=self._build_environment(),
                timeout=self._get_timeout(),
                cli_mode=True,
                user_id=self.user_id,  # ✨ 传递用户 ID
            )

            # 解析执行结果
            if exit_code == 0:
                log.info(f"[SkillExecutor] Python 脚本执行成功")
                return {
                    "status": "success",
                    "executor": "python",
                    "skill_id": self.skill_id,
                    "project_id": self.project_id,
                    "output": output[:2000] if len(output) > 2000 else output,
                    "output_dir": self.params.get("output_dir"),
                    "sample_count": self.sample_table.sample_count if self.sample_table else 0,
                }
            else:
                log.error(f"[SkillExecutor] Python 脚本执行失败: {output[:500]}")
                return {
                    "status": "failed",
                    "error": output[:1000],
                    "exit_code": exit_code,
                    "skill_id": self.skill_id,
                }

        except Exception as e:
            log.error(f"[SkillExecutor] Python 执行异常: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "skill_id": self.skill_id,
            }

    def _execute_r(self) -> Dict[str, Any]:
        """
        执行 R 脚本

        在 Docker 沙箱中执行 R 脚本
        """
        from app.tools.bio_tools import run_container

        entry_point = self.skill_def.get("metadata", {}).get("entry_point")
        bundle_path = self.skill_def.get("bundle_path")

        if not entry_point or not bundle_path:
            raise SkillExecutionError("SKILL 缺少 entry_point 或 bundle_path")

        script_path = Path(bundle_path) / entry_point

        if not script_path.exists():
            raise SkillExecutionError(f"入口脚本不存在: {script_path}")

        log.info(f"[SkillExecutor] R 入口脚本: {script_path}")

        # ==========================================
        # ✨ 实际 Docker 沙箱执行
        # ==========================================
        try:
            # 构建命令行参数
            args_list = self._build_command_args()

            # ✨ 将宿主机路径转换为容器内路径
            container_script_path = self._convert_to_container_path(script_path)

            # 使用 cli_mode=True 执行脚本
            cmd = ["Rscript", container_script_path] + args_list

            log.info(f"[SkillExecutor] 执行命令: {' '.join(cmd)}")

            # 调用 Docker 沙箱
            output, exit_code = run_container(
                image='autonome-tool-env',
                command=cmd,
                language="r",
                environment=self._build_environment(),
                timeout=self._get_timeout(),
                cli_mode=True,
                user_id=self.user_id,  # ✨ 传递用户 ID
            )

            # 解析执行结果
            if exit_code == 0:
                log.info(f"[SkillExecutor] R 脚本执行成功")
                return {
                    "status": "success",
                    "executor": "r",
                    "skill_id": self.skill_id,
                    "project_id": self.project_id,
                    "output": output[:2000] if len(output) > 2000 else output,
                    "output_dir": self.params.get("output_dir"),
                    "sample_count": self.sample_table.sample_count if self.sample_table else 0,
                }
            else:
                log.error(f"[SkillExecutor] R 脚本执行失败: {output[:500]}")
                return {
                    "status": "failed",
                    "error": output[:1000],
                    "exit_code": exit_code,
                    "skill_id": self.skill_id,
                }

        except Exception as e:
            log.error(f"[SkillExecutor] R 执行异常: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "skill_id": self.skill_id,
            }

    def _execute_bash(self) -> Dict[str, Any]:
        """
        执行 Bash 脚本
        """
        from app.tools.bio_tools import run_container

        log.info("[SkillExecutor] Bash 执行器")

        entry_point = self.skill_def.get("metadata", {}).get("entry_point")
        bundle_path = self.skill_def.get("bundle_path")

        if not entry_point or not bundle_path:
            raise SkillExecutionError("SKILL 缺少 entry_point 或 bundle_path")

        script_path = Path(bundle_path) / entry_point

        if not script_path.exists():
            raise SkillExecutionError(f"入口脚本不存在: {script_path}")

        try:
            # ✨ 将宿主机路径转换为容器内路径
            container_script_path = self._convert_to_container_path(script_path)

            cmd = ["bash", container_script_path] + self._build_command_args()

            output, exit_code = run_container(
                image='autonome-tool-env',
                command=cmd,
                language="bash",
                environment=self._build_environment(),
                timeout=self._get_timeout(),
                cli_mode=True,
                user_id=self.user_id,  # ✨ 传递用户 ID
            )

            if exit_code == 0:
                return {
                    "status": "success",
                    "executor": "bash",
                    "skill_id": self.skill_id,
                    "output": output[:2000],
                }
            else:
                return {
                    "status": "failed",
                    "error": output[:1000],
                    "skill_id": self.skill_id,
                }

        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "skill_id": self.skill_id,
            }

    # ==========================================
    # ✨ 辅助方法
    # ==========================================

    def _build_command_args(self) -> list:
        """
        构建命令行参数列表

        从 self.params 中提取参数，转换为命令行格式
        """
        args = []
        for key, value in self.params.items():
            # 跳过内部参数
            if key.startswith("_"):
                continue
            # 跳过 None 值
            if value is None:
                continue
            # 跳过空列表和空字典
            if isinstance(value, (list, dict)) and not value:
                continue

            if isinstance(value, bool):
                if value:
                    args.append(f"--{key}")
            elif isinstance(value, list):
                # 列表参数：逗号分隔
                args.append(f"--{key}")
                args.append(",".join(str(v) for v in value))
            elif isinstance(value, dict):
                # 字典参数：JSON 字符串
                args.append(f"--{key}")
                args.append(json.dumps(value))
            else:
                args.append(f"--{key}")
                args.append(str(value))

        return args

    def _build_environment(self) -> Dict[str, str]:
        """
        构建环境变量字典

        包含：
        - TASK_OUT_DIR: 任务输出目录
        - PROJECT_ID: 项目 ID
        - TASK_ID: 任务 ID
        - 所有 self.params 中的参数（大写形式）
        """
        env = {
            "TASK_OUT_DIR": self.params.get("TASK_OUT_DIR", f"/workspace/project_{self.project_id}/results/default"),
            "PROJECT_ID": self.project_id,
        }

        if self.task_id:
            env["TASK_ID"] = self.task_id

        # 添加用户参数到环境变量（大写形式）
        for key, value in self.params.items():
            if not key.startswith("_") and isinstance(value, (str, int, float)):
                env[key.upper()] = str(value)

        return env

    def _get_timeout(self) -> int:
        """
        获取执行超时时间

        优先使用 SKILL 定义中的 timeout_seconds，否则使用默认值
        """
        timeout = self.skill_def.get("metadata", {}).get("timeout_seconds")
        if timeout:
            return int(timeout)
        return SKILL_EXECUTION_TIMEOUT

    def _convert_to_container_path(self, host_path: Path) -> str:
        """
        将宿主机路径转换为 Docker 容器内路径

        Args:
            host_path: 宿主机上的文件路径

        Returns:
            容器内的文件路径字符串

        Examples:
            /opt/data1/.../app/skills/my_skill/scripts/main.py
            -> /app/skills/my_skill/scripts/main.py
        """
        # 定义路径映射规则
        path_mappings = [
            # SKILL 脚本路径映射
            ("/opt/data1/public/software/systools/autonome/autonome-backend/app/skills", "/app/skills"),
            # BIOSOURCE 脚本路径映射
            ("/opt/data1/public/software/systools/autonome/biosource", "/app/biosource"),
        ]

        host_path_str = str(host_path)

        for host_prefix, container_prefix in path_mappings:
            if host_path_str.startswith(host_prefix):
                container_path = host_path_str.replace(host_prefix, container_prefix, 1)
                log.info(f"[SkillExecutor] 路径映射: {host_path_str} -> {container_path}")
                return container_path

        # 如果没有匹配的映射规则，返回原始路径（可能是容器内路径）
        return host_path_str

    def _execute_mock(self, executor_type: str) -> Dict[str, Any]:
        """
        模拟执行（用于测试/开发）

        Args:
            executor_type: 执行器类型

        Returns:
            模拟的执行结果
        """
        return {
            "status": "success",
            "executor": executor_type,
            "skill_id": self.skill_id,
            "project_id": self.project_id,
            "params_summary": {
                "sample_count": self.sample_table.sample_count if self.sample_table else 0,
                "group_count": self.sample_table.group_count if self.sample_table else 0,
                "groups": dict(self.sample_table.groups) if self.sample_table else {},
                "output_dir": self.params.get("output_dir"),
            },
            "message": "SKILL 执行完成（模拟模式）",
        }


def execute_skill(
    skill_id: str,
    params: Dict[str, Any],
    project_id: str,
    task_id: Optional[str] = None,
    user_id: Optional[int] = None,
    skip_dependency_check: bool = False,
) -> Dict[str, Any]:
    """
    便捷函数：执行 SKILL

    Args:
        skill_id: SKILL 唯一标识符
        params: 执行参数
        project_id: 项目 ID
        task_id: 任务 ID
        user_id: 用户 ID（用于包依赖检查）
        skip_dependency_check: 是否跳过依赖检查

    Returns:
        执行结果

    Examples:
        result = execute_skill(
            "singlecell_seurat_pipeline_01",
            {"sample_table": "Sample1\\t/data/s1\\t10x\\tControl"},
            "project_123",
            user_id=1
        )
    """
    executor = SkillExecutor(skill_id, params, project_id, task_id, user_id, skip_dependency_check)
    return executor.execute()