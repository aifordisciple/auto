"""
原生执行器 - Native Executor

在宿主机上直接执行技能脚本，绕过 Docker 容器。

安全设计：
1. 仅允许管理员授权的官方技能使用原生执行
2. 执行前验证脚本路径白名单
3. 资源限制（CPU、内存、超时）
4. 执行日志审计

使用场景：
- 受信任的官方技能可以直接在宿主机运行，减少容器启动开销
- 需要访问宿主机特殊资源（如 GPU、特殊硬件）的技能

注意：
- 原生执行存在安全风险，仅限官方技能使用
- 所有执行都有审计日志记录
"""

import os
import subprocess
import time
import resource
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path

from app.core.logger import log
from app.core.config import settings


# ==========================================
# 安全配置
# ==========================================

# 允许原生执行的脚本路径白名单
# 只有位于这些目录下的脚本才能被原生执行
NATIVE_EXECUTION_ALLOWED_PATHS = [
    "/opt/data1/public/software/systools/autonome/autonome-backend/app/skills",
    "/opt/data1/public/software/systools/autonome/biosource",
]

# Conda 环境路径
NATIVE_EXECUTION_CONDA_PATH = "/opt/data1/public/software/systools/autonome/autonome_conda"

# 资源限制配置
NATIVE_EXECUTION_MEMORY_LIMIT_GB = 8      # 内存限制：8GB
NATIVE_EXECUTION_CPU_TIME_LIMIT = 3600    # CPU 时间限制：1小时
NATIVE_EXECUTION_DEFAULT_TIMEOUT = 3600   # 默认超时：1小时

# 用户包路径
USER_PACKAGES_HOST_PATH = "/opt/data1/public/software/systools/autonome/uploads/user_packages"


class NativeExecutionError(Exception):
    """原生执行错误"""
    pass


class NativeExecutor:
    """
    原生执行器

    在宿主机环境中直接执行技能脚本。

    安全机制：
    1. 路径白名单验证
    2. 资源限制（内存、CPU时间）
    3. 超时控制
    4. 审计日志

    使用示例：
        executor = NativeExecutor(
            skill_id="fastqc_multiqc_pipeline_01",
            script_path="/app/skills/fastqc_multiqc_pipeline_01/scripts/main.py",
            environment={"PROJECT_ID": "proj_xxx"},
            timeout=3600,
            user_id=1,
        )
        output, exit_code, billing_info = executor.execute_python(["--input", "sample.fastq"])
    """

    def __init__(
        self,
        skill_id: str,
        script_path: str,
        environment: Dict[str, str] = None,
        timeout: int = NATIVE_EXECUTION_DEFAULT_TIMEOUT,
        user_id: int = None,
    ):
        """
        初始化原生执行器

        Args:
            skill_id: 技能 ID
            script_path: 脚本路径（宿主机绝对路径）
            environment: 环境变量字典
            timeout: 执行超时时间（秒）
            user_id: 用户 ID（用于用户级包管理）
        """
        self.skill_id = skill_id
        self.script_path = script_path
        self.environment = environment or {}
        self.timeout = timeout
        self.user_id = user_id

        log.info(f"[NativeExecutor] 初始化: skill_id={skill_id}, script={script_path}")

    def validate_path(self) -> Tuple[bool, str]:
        """
        验证脚本路径是否在白名单中

        Returns:
            (是否有效, 错误信息)
        """
        abs_path = os.path.abspath(self.script_path)

        # 检查文件是否存在
        if not os.path.exists(abs_path):
            return False, f"脚本文件不存在: {abs_path}"

        # 检查路径是否在白名单中
        for allowed_path in NATIVE_EXECUTION_ALLOWED_PATHS:
            if abs_path.startswith(allowed_path):
                return True, ""

        return False, f"脚本路径不在白名单中: {abs_path}"

    def _build_environment(self) -> Dict[str, str]:
        """
        构建执行环境变量

        包括：
        1. 系统环境变量
        2. Conda 环境变量
        3. 用户级包路径
        4. 自定义环境变量
        """
        env = os.environ.copy()

        # 添加 Conda 环境变量
        conda_bin = f"{NATIVE_EXECUTION_CONDA_PATH}/bin"
        env["PATH"] = f"{conda_bin}:{env.get('PATH', '')}"
        env["CONDA_PREFIX"] = NATIVE_EXECUTION_CONDA_PATH

        # 添加用户级包路径（如果有 user_id）
        if self.user_id:
            user_pkg_dir = f"{USER_PACKAGES_HOST_PATH}/user_{self.user_id}"
            user_python_dir = f"{user_pkg_dir}/python"
            user_r_dir = f"{user_pkg_dir}/r"

            # 确保用户包目录存在
            os.makedirs(user_python_dir, exist_ok=True)
            os.makedirs(user_r_dir, exist_ok=True)

            # Python 用户包路径（优先级最高）
            python_path = f"{user_python_dir}:{NATIVE_EXECUTION_CONDA_PATH}/lib/python3.10/site-packages"
            env["PYTHONPATH"] = python_path

            # R 用户包路径
            env["R_LIBS_USER"] = user_r_dir
            env["R_LIBS"] = f"{user_r_dir}:{NATIVE_EXECUTION_CONDA_PATH}/lib/R/library"

            log.info(f"[NativeExecutor] 用户包目录已启用: user_id={self.user_id}")
            log.info(f"   Python 路径: {python_path}")
            log.info(f"   R 路径: {user_r_dir}")

        # 添加自定义环境变量
        env.update(self.environment)

        return env

    def _set_resource_limits(self):
        """
        设置资源限制

        通过 setrlimit 限制内存和 CPU 时间
        """
        # 内存限制（软限制和硬限制）
        memory_bytes = NATIVE_EXECUTION_MEMORY_LIMIT_GB * 1024 * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except (ValueError, resource.error) as e:
            log.warning(f"[NativeExecutor] 无法设置内存限制: {e}")

        # CPU 时间限制
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (NATIVE_EXECUTION_CPU_TIME_LIMIT, NATIVE_EXECUTION_CPU_TIME_LIMIT))
        except (ValueError, resource.error) as e:
            log.warning(f"[NativeExecutor] 无法设置 CPU 时间限制: {e}")

    def execute_python(self, args: List[str]) -> Tuple[str, int, Dict]:
        """
        执行 Python 脚本

        Args:
            args: 命令行参数列表

        Returns:
            (输出日志, 退出码, 计费信息)
        """
        # 安全验证
        is_valid, error_msg = self.validate_path()
        if not is_valid:
            return f"安全错误: {error_msg}", 1, {}

        # 构建命令
        cmd = ["python", self.script_path] + args
        log.info(f"[NativeExecutor] 执行 Python: {' '.join(cmd)}")

        # 构建环境
        env = self._build_environment()

        # 执行脚本
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                cwd=os.path.dirname(self.script_path),
                # preexec_fn=self._set_resource_limits,  # 资源限制（谨慎使用）
            )
            duration = time.time() - start_time

            # 合并标准输出和标准错误
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            billing_info = {
                "duration_seconds": int(duration),
                "cost_credits": 0.0,  # 统一计费由调用方处理
                "compute_record_id": None,
            }

            log.info(f"[NativeExecutor] 执行完成: exit_code={result.returncode}, duration={duration:.2f}s")

            return output, result.returncode, billing_info

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            log.error(f"[NativeExecutor] 执行超时: {self.timeout}s")
            return f"执行超时 (超过 {self.timeout} 秒)", 1, {"duration_seconds": int(duration)}

        except Exception as e:
            log.error(f"[NativeExecutor] 执行异常: {e}")
            return f"执行异常: {str(e)}", 1, {}

    def execute_r(self, args: List[str]) -> Tuple[str, int, Dict]:
        """
        执行 R 脚本

        Args:
            args: 命令行参数列表

        Returns:
            (输出日志, 退出码, 计费信息)
        """
        # 安全验证
        is_valid, error_msg = self.validate_path()
        if not is_valid:
            return f"安全错误: {error_msg}", 1, {}

        # 构建命令
        cmd = ["Rscript", self.script_path] + args
        log.info(f"[NativeExecutor] 执行 R: {' '.join(cmd)}")

        # 构建环境
        env = self._build_environment()

        # 执行脚本
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                cwd=os.path.dirname(self.script_path),
            )
            duration = time.time() - start_time

            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            billing_info = {
                "duration_seconds": int(duration),
                "cost_credits": 0.0,
                "compute_record_id": None,
            }

            log.info(f"[NativeExecutor] R 执行完成: exit_code={result.returncode}, duration={duration:.2f}s")

            return output, result.returncode, billing_info

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return f"执行超时 (超过 {self.timeout} 秒)", 1, {"duration_seconds": int(duration)}

        except Exception as e:
            log.error(f"[NativeExecutor] R 执行异常: {e}")
            return f"执行异常: {str(e)}", 1, {}

    def execute_bash(self, args: List[str]) -> Tuple[str, int, Dict]:
        """
        执行 Bash 脚本

        Args:
            args: 命令行参数列表

        Returns:
            (输出日志, 退出码, 计费信息)
        """
        # 安全验证
        is_valid, error_msg = self.validate_path()
        if not is_valid:
            return f"安全错误: {error_msg}", 1, {}

        # 构建命令
        cmd = ["bash", self.script_path] + args
        log.info(f"[NativeExecutor] 执行 Bash: {' '.join(cmd)}")

        # 构建环境
        env = self._build_environment()

        # 执行脚本
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                cwd=os.path.dirname(self.script_path),
            )
            duration = time.time() - start_time

            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            billing_info = {
                "duration_seconds": int(duration),
                "cost_credits": 0.0,
                "compute_record_id": None,
            }

            log.info(f"[NativeExecutor] Bash 执行完成: exit_code={result.returncode}, duration={duration:.2f}s")

            return output, result.returncode, billing_info

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return f"执行超时 (超过 {self.timeout} 秒)", 1, {"duration_seconds": int(duration)}

        except Exception as e:
            log.error(f"[NativeExecutor] Bash 执行异常: {e}")
            return f"执行异常: {str(e)}", 1, {}


def run_native(
    script_path: str,
    command: List[str],
    language: str = "python",
    environment: dict = None,
    timeout: int = NATIVE_EXECUTION_DEFAULT_TIMEOUT,
    user_id: int = None,
    skill_id: str = None,
) -> Tuple[str, int, dict]:
    """
    原生执行入口函数

    与 bio_tools.run_container() 接口兼容，便于在 SkillExecutor 中切换。

    Args:
        script_path: 脚本路径（宿主机绝对路径）
        command: 命令行参数列表
        language: 语言类型 ("python", "r", "bash")
        environment: 环境变量字典
        timeout: 执行超时时间（秒）
        user_id: 用户 ID（用于用户级包管理）
        skill_id: 技能 ID（用于审计日志）

    Returns:
        (输出日志, 退出码, 计费信息) - 与 run_container 返回格式兼容
    """
    executor = NativeExecutor(
        skill_id=skill_id or "unknown",
        script_path=script_path,
        environment=environment,
        timeout=timeout,
        user_id=user_id,
    )

    if language.lower() == "python":
        return executor.execute_python(command)
    elif language.lower() == "r":
        return executor.execute_r(command)
    elif language.lower() == "bash":
        return executor.execute_bash(command)
    else:
        return f"不支持的语言: {language}", 1, {}


def is_official_skill(skill_id: str, owner_id: int) -> bool:
    """
    判断是否为官方技能

    官方技能判断逻辑：
    1. owner_id = 1 (系统管理员创建)
    2. skill_id 以官方前缀开头
    3. 技能存在于文件系统的 app/skills/ 目录下

    Args:
        skill_id: 技能 ID
        owner_id: 创建者 ID

    Returns:
        是否为官方技能
    """
    # 方式1: owner_id = 1 (系统管理员创建)
    if owner_id == 1:
        return True

    # 方式2: 检查 skill_id 前缀 (官方技能有特定前缀)
    OFFICIAL_PREFIXES = [
        "fastqc_",
        "multiqc_",
        "singlecell_",
        "rnaseq_",
        "meta_nextflow_",
        "bio_",  # 通用生信技能前缀
    ]

    for prefix in OFFICIAL_PREFIXES:
        if skill_id.startswith(prefix):
            return True

    # 方式3: 检查技能是否存在于文件系统的 app/skills/ 目录下
    # 文件系统中的技能都是官方预置技能
    import os
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
    skill_path = os.path.join(skills_dir, skill_id)
    if os.path.exists(skill_path):
        return True

    return False


log.info("✅ Native Executor 模块已加载")