import os
import json
import socket
import re
import time
from langchain_core.tools import tool
from app.core.logger import log
from app.core.config import settings
from app.core.docker_api import docker_api_request
from app.core.sandbox_config import (
    DOCKER_SOCKET,
    CONDA_HOST_PATH, CONDA_CONTAINER_PATH,
    BIOSOURCE_HOST_PATH, BIOSOURCE_CONTAINER_PATH,
    SKILLS_HOST_PATH, SKILLS_CONTAINER_PATH,
    USER_PACKAGES_HOST_PATH, USER_PACKAGES_CONTAINER_PATH,
    DEFAULT_EXECUTION_TIMEOUT,
)


def run_container_simple(
    image: str,
    command,
    language: str = "python",
    environment: dict = None,
    timeout: int = DEFAULT_EXECUTION_TIMEOUT,
    cli_mode: bool = False,
    user_id: int = None,
    enable_network: bool = False,
) -> tuple[str, int]:
    """简化版容器执行（向后兼容）

    不包含计费功能，返回值与旧版 run_container 相同。

    Args:
        同 run_container，但不包含 billing_context

    Returns:
        (输出日志, 退出码) 元组
    """
    output, exit_code, _ = run_container(
        image=image,
        command=command,
        language=language,
        environment=environment,
        timeout=timeout,
        cli_mode=cli_mode,
        user_id=user_id,
        enable_network=enable_network,
        billing_context=None,
    )
    return output, exit_code


def run_container(
    image: str,
    command,  # 可以是字符串（脚本代码）或列表（完整命令）
    language: str = "python",
    environment: dict = None,
    timeout: int = DEFAULT_EXECUTION_TIMEOUT,
    cli_mode: bool = False,
    user_id: int = None,  # ✨ 新增：用户 ID，用于用户级包管理
    enable_network: bool = False,  # ✨ 新增：是否启用网络（用于包安装）
    billing_context: dict = None,  # ✨ 新增：计费上下文
    log_callback: callable = None,  # ✨ 新增：实时日志回调，用于 SSE 流式推送
) -> tuple[str, int, dict]:  # ✨ 修改：返回 (日志, 退出码, 计费信息)
    """通过 Docker API 运行容器（基础沙箱，支持用户级包管理和计费）

    Args:
        image: Docker 镜像名称
        command: 要执行的命令。cli_mode=False 时为脚本代码字符串，cli_mode=True 时为完整命令列表
        language: 语言类型 "python" 或 "r"（仅 cli_mode=False 时使用）
        environment: 环境变量字典
        timeout: 容器执行超时时间（秒），默认 3600 秒（1小时）以适应生信分析任务
        cli_mode: True 时 command 为完整命令列表，False 时为脚本代码字符串
        user_id: 用户 ID，用于注入用户级包环境变量。None 时不使用用户包
        enable_network: 是否启用网络（默认禁用，包安装时需要启用）
        billing_context: 计费上下文，包含：
            - wallet_id: 钱包 ID
            - billing_user_id: 用户 ID
            - project_id: 项目 ID
            - task_type: 任务类型 (TaskType)
            - compute_record_id: 已创建的计算记录 ID（可选）
            - estimated_cost: 预估费用（可选）
        log_callback: 实时日志回调函数，接收单行日志字符串。用于 SSE 流式推送。

    Returns:
        (输出日志, 退出码, 计费信息) 元组
        计费信息包含: duration_seconds, cost_credits, compute_record_id

    用户级包管理说明：
        - 当传入 user_id 时，自动挂载用户包目录并注入环境变量
        - Python 包路径: /app/user_packages/user_{user_id}/python
        - R 包路径: /app/user_packages/user_{user_id}/r
        - 环境变量优先级：用户包 > 系统包（conda）

    计费说明：
        - 传入 billing_context 时，自动进行预授权冻结和执行后结算
        - 执行前：冻结预估费用（estimated_cost 或基于 timeout 估算）
        - 执行后：结算实际费用（按时长计费）
    """
    # ✨ 容器 ID 初始化（用于异常清理）
    container_id = None

    # ✨ 计费信息初始化
    billing_info = {
        "duration_seconds": 0,
        "cost_credits": 0.0,
        "compute_record_id": None,
    }

    # ✨ 计费服务初始化（如果提供了 billing_context）
    billing_service = None
    compute_record = None
    meter = None

    if billing_context:
        try:
            from app.core.database import engine
            from sqlmodel import Session
            from app.services.billing_service import BillingService
            from app.models.billing import TaskType
            from app.services.meters.executor_meter import ExecutorMeter

            session = Session(engine)
            billing_service = BillingService(session)

            # 获取钱包
            wallet = billing_service.get_wallet(billing_context["wallet_id"])

            # 预估费用
            estimated_cost = billing_context.get("estimated_cost")
            if not estimated_cost:
                # 基于 timeout 预估：每分钟 0.1 CU
                estimated_cost = max(timeout / 60.0 * 0.1, 1.0)

            # 检查余额
            if not billing_service.check_available(wallet, estimated_cost):
                return f"❌ 余额不足，需要 {estimated_cost:.2f} CU", 1, billing_info

            # 创建计算记录
            task_type = billing_context.get("task_type", TaskType.SANDBOX_PYTHON)
            compute_record = billing_service.create_compute_record(
                wallet_id=wallet.wallet_id,
                user_id=billing_context.get("billing_user_id", user_id),
                task_type=task_type,
                task_name=f"Docker Sandbox: {language}",
                project_id=billing_context.get("project_id"),
                estimated_cost=estimated_cost,
            )

            # 冻结费用
            billing_service.freeze_credits(
                wallet_id=wallet.wallet_id,
                amount=estimated_cost,
                record_id=compute_record.record_id,
            )

            billing_info["compute_record_id"] = compute_record.record_id

            # 创建计量器
            meter = ExecutorMeter(billing_service)
            meter.start_metering(compute_record.record_id, {"timeout": timeout})

            log.info(f"[run_container] 💰 预授权冻结: {estimated_cost:.2f} CU, record_id={compute_record.record_id}")

        except Exception as e:
            log.warning(f"[run_container] 计费初始化失败: {e}")
            # 计费失败不阻止执行，但记录错误
            billing_service = None
            meter = None

    try:
        # ✨ 脚本写入路径：使用任务输出目录（由 Celery 任务创建并传入）
        task_out_dir = environment.get("TASK_OUT_DIR", "/workspace") if environment else "/workspace"

        # ✨ 确保目录存在
        os.makedirs(task_out_dir, exist_ok=True)

        # ✨ 新增：准备环境变量（如果有）
        env_list = []
        if environment:
            for key, value in environment.items():
                env_list.append(f"{key}={value}")

        # ✨ 添加 conda 环境变量
        env_list.append(f"PATH={CONDA_CONTAINER_PATH}/bin:/usr/local/bin:/usr/bin:/bin")
        env_list.append(f"CONDA_PREFIX={CONDA_CONTAINER_PATH}")

        # ==========================================
        # ✨ 用户级包管理：环境变量注入
        # ==========================================
        user_pkg_binds = []  # 用户包目录挂载列表
        if user_id:
            # 用户包容器内路径
            user_pkg_dir = f"{USER_PACKAGES_CONTAINER_PATH}/user_{user_id}"
            user_python_dir = f"{user_pkg_dir}/python"
            user_r_dir = f"{user_pkg_dir}/r"
            # ✨ 新增：用户级 Conda 环境路径
            user_conda_envs_dir = f"{user_pkg_dir}/conda_envs"
            user_conda_pkgs_dir = f"{user_pkg_dir}/conda_pkgs"

            # 宿主机用户包路径
            host_user_pkg_dir = f"{USER_PACKAGES_HOST_PATH}/user_{user_id}"

            # 确保用户包目录存在
            os.makedirs(os.path.join(host_user_pkg_dir, "python"), exist_ok=True)
            os.makedirs(os.path.join(host_user_pkg_dir, "r"), exist_ok=True)
            # ✨ 新增：创建用户级 Conda 环境目录
            os.makedirs(os.path.join(host_user_pkg_dir, "conda_envs"), exist_ok=True)
            os.makedirs(os.path.join(host_user_pkg_dir, "conda_pkgs"), exist_ok=True)

            # ✨ 注入 Python 用户包路径（优先级最高）
            # PYTHONPATH 格式：用户包:系统包
            python_path = f"{user_python_dir}:{CONDA_CONTAINER_PATH}/lib/python3.10/site-packages"
            env_list.append(f"PYTHONPATH={python_path}")

            # ✨ 注入 R 用户包路径
            # R_LIBS_USER: 用户 R 包目录
            # R_LIBS: 完整搜索路径（用户包:系统包）
            env_list.append(f"R_LIBS_USER={user_r_dir}")
            env_list.append(f"R_LIBS={user_r_dir}:{CONDA_CONTAINER_PATH}/lib/R/library")

            # ✨ 新增：注入用户级 Conda 环境变量
            # CONDA_ENVS_PATH: 用户 Conda 环境存储路径
            env_list.append(f"CONDA_ENVS_PATH={user_conda_envs_dir}")
            # CONDA_PKGS_DIRS: 用户 Conda 包缓存路径
            env_list.append(f"CONDA_PKGS_DIRS={user_conda_pkgs_dir}")

            # 添加用户包目录挂载
            user_pkg_binds.append(f"{host_user_pkg_dir}:{user_pkg_dir}:rw")

            log.info(f"[run_container] 📦 用户包目录已启用: user_id={user_id}")
            log.info(f"   Python 路径: {python_path}")
            log.info(f"   R 路径: {user_r_dir}:{CONDA_CONTAINER_PATH}/lib/R/library")
            log.info(f"   Conda 环境路径: {user_conda_envs_dir}")

        # ==========================================
        # ✨ 核心修改：支持命令行模式和代码注入模式
        # ==========================================
        if cli_mode and isinstance(command, list):
            # ========== 命令行模式：直接执行命令 ==========
            cmd = command
            log.info(f"[run_container] 🐳 命令行模式执行:")
            log.info(f"   完整命令: {' '.join(cmd)}")
        else:
            # ========== 代码注入模式：写入脚本文件后执行 ==========
            if language.lower() == "r":
                # 使用固定文件名，覆盖旧脚本
                script_name = "latest_script.R"
                script_path = os.path.join(task_out_dir, script_name)

                # 写入 R 代码到文件
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(command)

                log.info(f"[run_container] 📝 R 脚本已写入: {script_path}")

                # 容器内路径（与写入路径一致，因为两个容器挂载相同）
                cmd = ["Rscript", script_path]
            else:
                # 使用固定文件名，覆盖旧脚本
                script_name = "latest_script.py"
                script_path = os.path.join(task_out_dir, script_name)
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(command)
                log.info(f"[run_container] 📝 Python 脚本已写入: {script_path}")
                cmd = ["python", script_path]

            log.info(f"[run_container] 📝 脚本模式执行: {' '.join(cmd)}")

        # ✨ 记录完整的 Docker 执行命令
        cmd_str = " ".join(cmd)
        host_upload_dir = os.environ.get("HOST_UPLOAD_DIR", "/workspace")

        # ✨ 网络模式：默认禁用，包安装时启用
        network_mode = "bridge" if enable_network else "none"

        log.info(f"[run_container] 🐳 Docker 执行命令:")
        log.info(f"  Image: {image}")
        log.info(f"  Platform: linux/amd64")
        log.info(f"  Command: {cmd_str}")
        log.info(f"  Environment: {env_list}")
        log.info(f"  User ID: {user_id}")
        log.info(f"  Network: {network_mode}")
        log.info(f"  Mounts: {host_upload_dir}:/workspace, conda, skills, biosource" + (f", user_packages" if user_id else ""))
        log.info(f"  Working Dir: {task_out_dir}")
        log.info(f"  Memory: 128GB")

        # ✨ 构建挂载目录列表
        # ✨ Conda 只读挂载：保护官方环境，防止用户篡改
        # 用户级包通过 /app/user_packages/user_{id}/ 目录安装
        binds_list = [
            f"{host_upload_dir}:/workspace:rw",
            f"{CONDA_HOST_PATH}:{CONDA_CONTAINER_PATH}:ro",  # ✨ 只读：官方环境不可篡改
            f"{SKILLS_HOST_PATH}:{SKILLS_CONTAINER_PATH}:ro",  # ✨ SKILL 脚本库（只读）
            f"{BIOSOURCE_HOST_PATH}:{BIOSOURCE_CONTAINER_PATH}:ro"  # ✨ 生信脚本库（只读）
        ]
        # ✨ 添加用户包目录挂载
        binds_list.extend(user_pkg_binds)

        # ✨ 构建卷声明
        volumes_dict = {
            "/workspace": {},
            CONDA_CONTAINER_PATH: {},
            SKILLS_CONTAINER_PATH: {},
            BIOSOURCE_CONTAINER_PATH: {}
        }
        # ✨ 添加用户包容器卷
        if user_id:
            volumes_dict[f"{USER_PACKAGES_CONTAINER_PATH}/user_{user_id}"] = {}

        # ✨ 创建容器：挂载 uploads, conda, skills, biosource, user_packages 目录
        create_data = json.dumps({
            "Image": image,
            "platform": "linux/amd64",
            "Cmd": cmd,
            "Tty": True,
            "User": "root",
            "Env": env_list if env_list else None,
            "HostConfig": {
                "Memory": 128 * 1024 * 1024 * 1024,  # 128GB
                "NetworkMode": network_mode,  # ✨ 支持网络模式切换
                "CapDrop": ["ALL"] if not enable_network else [],  # ✨ 有网络时不 drop capabilities
                # ✨ 挂载 uploads, conda, skills, biosource, user_packages 目录
                "Binds": binds_list
            },
            "Volumes": volumes_dict,
            "WorkingDir": task_out_dir  # ✨ 设置工作目录为任务输出目录
        })

        resp = docker_api_request("POST", "/containers/create", create_data, timeout=30)

        if 'Id' not in resp:
            return f"❌ 创建容器失败: {resp}", 1, billing_info

        container_id = resp['Id']

        # 启动容器
        docker_api_request("POST", f"/containers/{container_id}/start", timeout=30)
        log.info(f"[run_container] 🚀 容器已启动 {container_id[:12]}，等待执行完成...")

        # ✨ 等待容器完成（带超时和 sleep，避免忙等待）
        # 当提供 log_callback 时，实时读取日志并回调
        start_time = time.time()
        last_log_size = 0
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        while True:
            info = docker_api_request("GET", f"/containers/{container_id}/json", timeout=30)
            status = info.get('State', {}).get('Status', 'unknown')

            # ✨ 实时日志流：当提供 log_callback 时，增量读取容器日志
            if log_callback:
                try:
                    current_log = docker_api_request(
                        "GET",
                        f"/containers/{container_id}/logs?stdout=true&stderr=true&tail=100",
                        return_raw=True,
                        timeout=10,
                    )
                    if current_log and len(current_log) > last_log_size:
                        new_content = current_log[last_log_size:]
                        last_log_size = len(current_log)
                        for line in new_content.split('\n'):
                            clean_line = ansi_escape.sub('', line)
                            clean_line = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', clean_line)
                            if clean_line.strip():
                                log_callback(clean_line.strip())
                except Exception:
                    pass  # 日志读取失败不影响主流程

            # ✨ 超时检查
            elapsed = time.time() - start_time
            if elapsed > timeout:
                docker_api_request("POST", f"/containers/{container_id}/stop?t=10", timeout=30)
                log.warning(f"[run_container] 容器执行超时 ({timeout}s)，已强制停止")
                # 清理容器
                docker_api_request("DELETE", f"/containers/{container_id}?force=true", timeout=30)

                # ✨ 计费结算（超时）
                billing_info["duration_seconds"] = int(elapsed)
                if billing_service and compute_record:
                    try:
                        billing_service.refund_frozen_credits(
                            wallet_id=billing_context["wallet_id"],
                            record_id=compute_record.record_id,
                        )
                        log.info(f"[run_container] 💰 超时退款: record_id={compute_record.record_id}")
                    except Exception as e:
                        log.error(f"[run_container] 退款失败: {e}")

                return f"❌ 执行超时 (超过 {timeout} 秒)", 1, billing_info

            if status == 'exited':
                break

            time.sleep(0.5)  # ✨ 避免 CPU 忙等待

        # 使用 return_raw=True 提取纯文本日志
        log_output = docker_api_request("GET", f"/containers/{container_id}/logs?stdout=true&stderr=true&tail=100", return_raw=True, timeout=30)

        # 防御性清理：剔除无法显示的特殊控制符
        if isinstance(log_output, str):
            log_output = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', log_output)

        # 获取退出码
        exit_code = info.get('State', {}).get('ExitCode', 0)

        # 计算执行时长
        duration = time.time() - start_time if 'start_time' in dir() else 0
        billing_info["duration_seconds"] = int(duration)

        # ✨ 计费结算
        if billing_service and compute_record and meter:
            try:
                # 停止计量
                if meter:
                    meter.set_container_id(container_id)
                    result = meter.stop_metering(compute_record.record_id)
                    billing_info["cost_credits"] = result.cost_credits

                # 结算费用
                actual_cost = billing_info["cost_credits"] or (duration / 60.0 * 0.1)
                billing_service.settle_frozen_credits(
                    wallet_id=billing_context["wallet_id"],
                    record_id=compute_record.record_id,
                    actual_cost=actual_cost,
                    execution_details={
                        "exit_code": exit_code,
                        "duration_seconds": duration,
                        "image": image,
                        "language": language,
                    },
                )

                log.info(f"[run_container] 💰 结算完成: {actual_cost:.2f} CU, duration={duration:.1f}s")

            except Exception as e:
                log.error(f"[run_container] 结算失败: {e}")
            finally:
                # 关闭数据库会话
                try:
                    session.close()
                except:
                    pass

        # 清理容器
        docker_api_request("DELETE", f"/containers/{container_id}?force=true", timeout=30)

        return str(log_output), exit_code, billing_info

    except socket.timeout:
        log.error("[run_container] Docker API 请求超时")

        # ✨ 清理容器（防止僵尸容器堆积）
        if container_id:
            try:
                docker_api_request("POST", f"/containers/{container_id}/stop?t=5", timeout=10)
                docker_api_request("DELETE", f"/containers/{container_id}?force=true", timeout=10)
                log.info(f"[run_container] 🧹 已清理超时容器: {container_id[:12]}")
            except Exception as cleanup_err:
                log.warning(f"[run_container] 容器清理失败: {cleanup_err}")

        # ✨ 计费退款（异常情况）
        if billing_service and compute_record:
            try:
                billing_service.refund_frozen_credits(
                    wallet_id=billing_context["wallet_id"],
                    record_id=compute_record.record_id,
                )
                session.close()
            except:
                pass

        return "❌ Docker API 请求超时", 1, billing_info

    except Exception as e:
        log.error(f"[run_container] Docker API 错误: {str(e)}")

        # ✨ 清理容器（防止僵尸容器堆积）
        if container_id:
            try:
                docker_api_request("POST", f"/containers/{container_id}/stop?t=5", timeout=10)
                docker_api_request("DELETE", f"/containers/{container_id}?force=true", timeout=10)
                log.info(f"[run_container] 🧹 已清理异常容器: {container_id[:12]}")
            except Exception as cleanup_err:
                log.warning(f"[run_container] 容器清理失败: {cleanup_err}")

        # ✨ 计费退款（异常情况）
        if billing_service and compute_record:
            try:
                billing_service.refund_frozen_credits(
                    wallet_id=billing_context["wallet_id"],
                    record_id=compute_record.record_id,
                )
                session.close()
            except:
                pass

        return f"❌ Docker API 错误: {str(e)}", 1, billing_info


def run_nextflow_in_sandbox(
    work_dir: str,
    params: dict,
    log_callback: callable = None,
    timeout_seconds: int = DEFAULT_EXECUTION_TIMEOUT
) -> tuple[str, int]:
    """
    在沙箱中执行 Nextflow 流程

    特点：
    1. 挂载 conda 目录（包含 nextflow, fastqc, multiqc 等）- 只读
    2. 允许网络（用于 Nextflow 下载流程依赖）
    3. 检查必要工具，如缺失则报错（Conda 只读，无法动态安装）

    注意：nextflow, fastqc, multiqc 等工具需在 Docker 镜像中预装
    """
    container_id = None
    try:
        host_upload_dir = os.environ.get("HOST_UPLOAD_DIR", "/workspace")
        params_json = json.dumps(params)

        # 构建执行脚本（注意：不使用 f-string，避免花括号冲突）
        # ✨ 修改：移除动态 conda install，因为 Conda 目录现在是只读的
        nf_script = '''
import subprocess
import sys
import os
import json

# 设置环境
os.environ["PATH"] = "''' + CONDA_CONTAINER_PATH + '''/bin:" + os.environ.get("PATH", "")
os.environ["NXF_HOME"] = "''' + CONDA_CONTAINER_PATH + '''/nextflow"

def check_tool(tool_name):
    """检查工具是否存在（只检查，不安装）"""
    try:
        subprocess.run(["which", tool_name], check=True, capture_output=True)
        print(f"✅ {tool_name} 已安装")
        return True
    except:
        print(f"❌ {tool_name} 未安装")
        return False

# 检查必要工具（只检查，不安装 - Conda 目录只读）
tools_needed = ["nextflow", "fastqc", "multiqc"]
missing_tools = []
for tool in tools_needed:
    if not check_tool(tool):
        missing_tools.append(tool)

if missing_tools:
    print(f"\\n❌ 缺少必要工具: {', '.join(missing_tools)}")
    print("请在 Docker 镜像中预装这些工具，或使用用户级环境安装")
    sys.exit(1)

# 执行 Nextflow
print("\\n🚀 启动 Nextflow 流程...")
work_dir = "''' + work_dir + '''"

# 构建参数（使用 json.loads 解析 JSON 字符串）
import json
params_json_raw = r"""''' + params_json + '''"""
params_dict = json.loads(params_json_raw)
params_str = ""
for k, v in params_dict.items():
    if isinstance(v, str):
        params_str += f" --{k} \\"{v}\\""
    elif isinstance(v, bool):
        if v:
            params_str += f" --{k}"
    else:
        params_str += f" --{k} {v}"

cmd = f"nextflow run main.nf{params_str} -resume"
print(f"执行命令: {cmd}")

result = subprocess.run(cmd, shell=True, cwd=work_dir, capture_output=False)
sys.exit(result.returncode)
'''

        # 创建容器（允许网络用于 conda 安装）
        create_data = json.dumps({
            "Image": "autonome-tool-env",
            "platform": "linux/amd64",
            "Cmd": ["python", "-c", nf_script],
            "Tty": True,
            "User": "root",
            "Env": [
                f"PATH={CONDA_CONTAINER_PATH}/bin:/usr/local/bin:/usr/bin:/bin",
                f"CONDA_PREFIX={CONDA_CONTAINER_PATH}",
                f"TASK_OUT_DIR={work_dir}"
            ],
            "HostConfig": {
                "Memory": 128 * 1024 * 1024 * 1024,  # 128GB
                # ✨ 允许网络（用于 conda 安装）
                "NetworkMode": "bridge",
                "Binds": [
                    f"{host_upload_dir}:/workspace:rw",
                    f"{CONDA_HOST_PATH}:{CONDA_CONTAINER_PATH}:ro",  # ✨ 只读：官方环境不可篡改
                    f"{BIOSOURCE_HOST_PATH}:{BIOSOURCE_CONTAINER_PATH}:ro",  # ✨ 挂载生信脚本库（只读）
                    f"{SKILLS_HOST_PATH}:{SKILLS_CONTAINER_PATH}:ro"  # ✨ 挂载 SKILL 脚本库（只读）
                ]
            },
            "Volumes": {"/workspace": {}, CONDA_CONTAINER_PATH: {}, BIOSOURCE_CONTAINER_PATH: {}, SKILLS_CONTAINER_PATH: {}},
            "WorkingDir": work_dir
        })

        resp = docker_api_request("POST", "/containers/create", create_data)

        if 'Id' not in resp:
            error_msg = f"❌ 创建容器失败: {resp}"
            if log_callback:
                log_callback(error_msg)
            return error_msg, 1

        container_id = resp['Id']

        # 启动容器
        docker_api_request("POST", f"/containers/{container_id}/start")

        # ✨ 实时读取日志
        import time
        import re
        log_output = ""
        last_size = 0
        start_time = time.time()

        # ANSI 转义码清理函数
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

        while True:
            # ✨ 超时检查：防止容器挂起导致无限循环
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                log.warning(f"[run_nextflow_in_sandbox] 容器执行超时 ({timeout_seconds}s)，强制终止")
                if log_callback:
                    log_callback(f"⚠️ 执行超时 ({timeout_seconds}s)，强制终止容器")
                break

            info = docker_api_request("GET", f"/containers/{container_id}/json")
            status = info.get('State', {}).get('Status')

            # 读取日志
            current_log = docker_api_request(
                "GET",
                f"/containers/{container_id}/logs?stdout=true&stderr=true&tail=100",
                return_raw=True
            )

            if current_log and len(current_log) > last_size:
                new_content = current_log[last_size:]
                log_output = current_log
                last_size = len(current_log)

                # 回调日志（清理 ANSI 转义码）
                if log_callback:
                    for line in new_content.split('\n'):
                        # 清理 ANSI 转义码和不可见字符
                        clean_line = ansi_escape.sub('', line)
                        clean_line = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', clean_line)
                        if clean_line.strip():
                            log_callback(clean_line.strip())

            if status == 'exited':
                break

            time.sleep(1)

        exit_code = info.get('State', {}).get('ExitCode', 0)

        # 清理容器
        docker_api_request("DELETE", f"/containers/{container_id}?force=true")

        return log_output, exit_code

    except Exception as e:
        error_msg = f"❌ Nextflow 执行错误: {str(e)}"
        log.error(f"[run_nextflow_in_sandbox] {error_msg}")

        # ✨ 清理容器（防止僵尸容器堆积）
        if container_id:
            try:
                docker_api_request("POST", f"/containers/{container_id}/stop?t=5", timeout=10)
                docker_api_request("DELETE", f"/containers/{container_id}?force=true", timeout=10)
                log.info(f"[run_nextflow_in_sandbox] 🧹 已清理异常容器: {container_id[:12]}")
            except Exception as cleanup_err:
                log.warning(f"[run_nextflow_in_sandbox] 容器清理失败: {cleanup_err}")

        if log_callback:
            log_callback(error_msg)
        return error_msg, 1


# ✨ 标记沙箱可用
DOCKER_SANDBOX_AVAILABLE = True
log.info("🛡️ Docker 沙箱引擎已就绪 (纯净算力版)")

@tool
def execute_python_code(code: str, environment: dict = None) -> str:
    """
    在安全的 Docker 沙箱中执行 Python 数据科学和生信分析代码。
    此工具拥有完整的 matplotlib, pandas, scanpy 等数据科学生态。
    代码生成的任何图表或文件必须保存在 /workspace 挂载目录中。

    Args:
        code: 包含有效 Python 语法的字符串代码。
        environment: 可选的环境变量字典，如 {"TASK_OUT_DIR": "/workspace/project_1/results", "PROJECT_ID": "1"}
    """
    log.info("========== 🤖 AI 尝试执行的代码 ==========")
    log.info(code[:1000] if len(code) > 1000 else code)
    log.info("==========================================")

    if environment:
        log.info(f"🔧 [Sandbox] 环境变量注入: {environment}")

    if not DOCKER_SANDBOX_AVAILABLE:
        log.error("❌ Docker sandbox not available")
        return "❌ 严重系统错误：沙箱引擎未就绪。"

    log.info("🛡️ 正在拉起重型分析沙箱...")

    try:
        result_output, exit_code = run_container(
            image='autonome-tool-env',
            command=code,
            environment=environment
        )
        
        log.info("========== 📦 沙箱返回的结果 ==========")
        log.info(result_output[:500] if len(result_output) > 500 else result_output)
        log.info("========================================")
        
        if exit_code == 0:
            log.info("✅ 代码执行成功")
        else:
            log.warning(f"⚠️ 代码执行返回非零退出码: {exit_code}")
            
        return result_output

    except Exception as e:
        log.error(f"⚠️ 沙箱执行报错: {str(e)}")
        return f"❌ 代码执行报错:\n{str(e)}\n请根据此报错修正代码。"


# ✨ 核心修改：导出底层算力工具 + 环境探针工具
from app.tools.probe_tools import probe_tools_list

bio_tools_list = [execute_python_code] + probe_tools_list


# ==========================================
# 容器预热池集成 - 节省 3-5s 启动时间
# ==========================================

def run_container_pooled(
    code: str,
    language: str = "python",
    environment: dict = None,
    timeout: int = DEFAULT_EXECUTION_TIMEOUT,
    user_id: int = None,
) -> tuple[str, int]:
    """
    使用预热容器池执行代码（快速响应）

    相比 run_container，节省 3-5s 容器启动时间。
    适用于无网络需求的简单任务。

    Args:
        code: 要执行的代码
        language: "python" 或 "r"
        environment: 环境变量
        timeout: 超时时间
        user_id: 用户 ID

    Returns:
        (输出日志, 退出码)

    限制：
        - 不支持网络（预热容器默认无网络）
        - 不支持计费（简化版本）
        - 不支持自定义镜像
    """
    try:
        from app.services.container_pool_service import get_container_pool, ContainerType

        pool = get_container_pool()

        # 确定容器类型
        if language.lower() == "r":
            container_type = ContainerType.R
        else:
            container_type = ContainerType.PYTHON

        # 获取预热容器
        container = pool.acquire_container(container_type, timeout=30, user_id=user_id)

        if not container:
            log.warning("[run_container_pooled] 获取预热容器失败，回退到普通模式")
            return run_container_simple(
                image='autonome-tool-env',
                command=code,
                language=language,
                environment=environment,
                timeout=timeout,
                user_id=user_id,
                enable_network=False
            )

        try:
            # 准备执行命令
            task_out_dir = environment.get("TASK_OUT_DIR", "/workspace") if environment else "/workspace"

            # 写入脚本到共享目录
            import os
            os.makedirs(task_out_dir, exist_ok=True)

            if language.lower() == "r":
                script_name = "pooled_script.R"
                script_path = os.path.join(task_out_dir, script_name)
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(code)
                cmd = ["Rscript", script_path]
            else:
                script_name = "pooled_script.py"
                script_path = os.path.join(task_out_dir, script_name)
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(code)
                cmd = ["python", script_path]

            log.info(f"[run_container_pooled] 🚀 使用预热容器执行: {container.container_id[:12]}")

            # 在容器中执行
            output, exit_code = pool.exec_in_container(container, cmd, timeout=timeout)

            log.info(f"[run_container_pooled] ✅ 执行完成: exit_code={exit_code}")

            return output, exit_code

        finally:
            # 归还容器
            pool.release_container(container)

    except ImportError:
        log.warning("[run_container_pooled] 容器池服务不可用，回退到普通模式")
        return run_container_simple(
            image='autonome-tool-env',
            command=code,
            language=language,
            environment=environment,
            timeout=timeout,
            user_id=user_id,
            enable_network=False
        )
    except Exception as e:
        log.error(f"[run_container_pooled] 执行失败: {e}")
        return f"❌ 执行失败: {str(e)}", 1


# ✨ Phase 5: 静默重试的错误类型（数据相关错误，可重试）
SILENT_RETRY_ERRORS = (
    KeyError,           # 字典键不存在
    IndexError,         # 列表索引越界
    TypeError,          # 类型错误（通常是 None 或类型不匹配）
    ValueError,         # 值错误（通常是空值或类型转换失败）
    AttributeError,     # 属性不存在
    NameError,         # 变量名不存在
    UnicodeDecodeError, # Unicode 解码错误
)

# ✨ Phase 5: 最大静默重试次数
MAX_SILENT_RETRIES = 2


def _emit_thought_stream(code: str, step: str) -> None:
    """
    ✨ Phase 5.1: 科技感迷你终端日志 - 发射思想流

    在执行过程中输出 AI 的"思考"日志，增强用户体验。

    Args:
        code: 正在执行的代码
        step: 当前步骤描述
    """
    # 根据代码前几行判断操作类型
    code_preview = code.strip()[:100] if code else ""

    # 根据步骤选择合适的 emoji 和日志级别
    thought_indicators = {
        "probe": ("🔍", "正在探查数据结构..."),
        "parse": ("📊", "正在解析数据维度..."),
        "transform": ("🔄", "正在进行数据转换..."),
        "filter": ("🎯", "正在筛选目标数据..."),
        "aggregate": ("📈", "正在进行聚合计算..."),
        "plot": ("📉", "正在生成可视化..."),
        "save": ("💾", "正在保存结果..."),
        "execute": ("⚡", "正在执行核心逻辑..."),
    }

    emoji, description = thought_indicators.get(step, ("🤔", f"正在执行: {step}"))

    # 输出科技感思想流日志
    log.info(f"✨ [Agent-思考] {emoji} {description}")
    if step == "probe" and len(code) > 50:
        log.info(f"✨ [Agent-思考] 📋 代码预览: {code_preview[:80]}...")


def _is_retryable_error(error: Exception) -> bool:
    """
    ✨ Phase 5.2: 判断错误是否可静默重试

    Args:
        error: 捕获的异常

    Returns:
        True if the error is data-related and potentially transient
    """
    # ✨ KeyError 和 IndexError 通常是数据问题，可能重试后消失（数据已准备好）
    # ✨ TypeError/ValueError 通常是空值问题，重试可能因为数据已就绪而成功
    # ✨ 其他错误（语法错误、逻辑错误）不应重试
    return isinstance(error, SILENT_RETRY_ERRORS)


def execute_python_code_pooled(code: str, environment: dict = None) -> str:
    """
    使用预热池执行 Python 代码（LangChain 工具）

    ✨ Phase 5 升级：
    - 5.1 科技感迷你终端日志：展示 AI 执行过程中的"思考"
    - 5.2 静默重试机制：对数据相关错误自动重试（最多2次）
    - 5.3 错误卡片仅在重试耗尽后抛出

    Args:
        code: 包含有效 Python 语法的字符串代码
        environment: 可选的环境变量字典

    Returns:
        执行结果
    """
    log.info("========== 🤖 AI 尝试执行的代码（预热池）==========")
    log.info(code[:1000] if len(code) > 1000 else code)
    log.info("================================================")

    if environment:
        log.info(f"🔧 [Sandbox-Pooled] 环境变量注入: {environment}")

    if not DOCKER_SANDBOX_AVAILABLE:
        log.error("❌ Docker sandbox not available")
        return "❌ 严重系统错误：沙箱引擎未就绪。"

    log.info("🛡️ 使用预热容器快速执行...")

    # ✨ Phase 5.1: 发射思想流 - 执行前探查
    _emit_thought_stream(code, "probe")

    # ✨ Phase 5.2: 静默重试机制
    last_error = None
    for attempt in range(MAX_SILENT_RETRIES + 1):
        try:
            # ✨ Phase 5.1: 根据代码内容发射相关思想流
            code_lower = code.lower()
            if "filter" in code_lower or "mask" in code_lower:
                _emit_thought_stream(code, "filter")
            elif "groupby" in code_lower or "agg" in code_lower or "sum" in code_lower:
                _emit_thought_stream(code, "aggregate")
            elif "plot" in code_lower or "fig" in code_lower or "plt" in code_lower:
                _emit_thought_stream(code, "plot")
            elif "save" in code_lower or "to_csv" in code_lower or "to_h5ad" in code_lower:
                _emit_thought_stream(code, "save")
            elif "transform" in code_lower or "normalize" in code_lower or "scale" in code_lower:
                _emit_thought_stream(code, "transform")
            else:
                _emit_thought_stream(code, "execute")

            result_output, exit_code = run_container_pooled(
                code=code,
                language="python",
                environment=environment
            )

            log.info("========== 📦 预热池返回的结果 ==========")
            log.info(result_output[:500] if len(result_output) > 500 else result_output)
            log.info("=========================================")

            if exit_code == 0:
                log.info("✅ 代码执行成功")
            else:
                log.warning(f"⚠️ 代码执行返回非零退出码: {exit_code}")
                # ✨ Phase 5.3: 非零退出码也视为执行失败，尝试重试
                raise RuntimeError(f"代码执行失败，退出码: {exit_code}")

            # 执行成功，返回结果
            return result_output

        except Exception as e:
            last_error = e
            error_type = type(e).__name__

            # ✨ Phase 5.2: 判断是否可重试
            if _is_retryable_error(e) and attempt < MAX_SILENT_RETRIES:
                log.warning(
                    f"⚡ [静默重试] 第 {attempt + 1} 次尝试失败: {error_type} - {str(e)[:100]}"
                )
                log.info(f"🔄 [静默重试] 正在自动重试（第 {attempt + 2} 次 / 共 {MAX_SILENT_RETRIES + 1} 次）...")
                continue  # 继续重试
            else:
                # ✨ Phase 5.3: 重试耗尽或不可重试的错误，不再静默处理
                if attempt >= MAX_SILENT_RETRIES:
                    log.error(
                        f"❌ [最终失败] 已达到最大重试次数 {MAX_SILENT_RETRIES}，"
                        f"错误类型: {error_type}, 错误信息: {str(e)[:200]}"
                    )
                else:
                    log.error(f"❌ [不可重试] 错误类型: {error_type}, 错误信息: {str(e)[:200]}")
                break

    # ✨ Phase 5.3: 只有在所有重试都失败后才返回错误信息
    error_msg = f"❌ 代码执行报错:\n{str(last_error)}\n请根据此报错修正代码。"
    return error_msg