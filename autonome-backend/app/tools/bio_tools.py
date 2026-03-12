import os
import json
import socket
import re
import time
from langchain_core.tools import tool
from app.core.logger import log
from app.core.config import settings

DOCKER_SOCKET = '/var/run/docker.sock'

# ✨ Conda 持久化路径（挂载到宿主机）
CONDA_HOST_PATH = "/opt/data1/public/software/systools/autonome/autonome_conda"
CONDA_CONTAINER_PATH = "/opt/conda"

# ✨ 新增 return_raw 参数，专门用于读取纯文本日志，防止把报错日志强行解析为 JSON
def docker_api_request(method: str, path: str, data: str = None, return_raw: bool = False, timeout: int = 30):
    """直接通过 Unix socket 调用 Docker API (完美版)

    Args:
        method: HTTP 方法
        path: API 路径
        data: 请求体
        return_raw: 是否返回原始文本
        timeout: socket 超时时间（秒）
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)  # ✨ 设置 socket 超时，防止阻塞
    sock.connect(DOCKER_SOCKET)

    body = data.encode('utf-8') if data else None

    # 使用 HTTP/1.0 强制服务器发送完毕后断开连接
    request = f"{method} {path} HTTP/1.0\r\n"
    request += "Host: localhost\r\n"
    request += "Connection: close\r\n"
    if body:
        request += f"Content-Length: {len(body)}\r\n"
    request += "Content-Type: application/json\r\n\r\n"

    if body:
        request = request.encode('utf-8') + body
    else:
        request = request.encode('utf-8')

    sock.sendall(request)

    # 安全地读取全部数据，直到连接自然关闭
    response = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break  # 服务器断开连接时，安全退出
        response += chunk

    sock.close()

    # 解析响应（分离 Headers 和 Body）
    if b"\r\n\r\n" in response:
        headers, raw_body = response.split(b"\r\n\r\n", 1)
    else:
        raw_body = response

    body_str = raw_body.decode('utf-8', errors='ignore').strip()

    if not body_str:
        return "" if return_raw else {}

    # ✨ 核心修复 2：如果是获取日志，直接返回纯文本，不走 JSON 解析！
    if return_raw:
        return body_str

    # 用最安全的截取方式提取 JSON
    start_dict = body_str.find('{')
    end_dict = body_str.rfind('}')

    start_list = body_str.find('[')
    end_list = body_str.rfind(']')

    try:
        if start_dict != -1 and end_dict != -1 and (start_list == -1 or start_dict < start_list):
            return json.loads(body_str[start_dict:end_dict+1])
        elif start_list != -1 and end_list != -1:
            return json.loads(body_str[start_list:end_list+1])

        return json.loads(body_str)
    except Exception as e:
        log.warning(f"JSON 解析回退, 原始数据长度: {len(body_str)}")
        return {"body": body_str}


def run_container(image: str, command: str, language: str = "python", environment: dict = None, timeout: int = 3600) -> tuple[str, int]:
    """通过 Docker API 运行容器（基础沙箱，无网络，有 conda）

    Args:
        image: Docker 镜像名称
        command: 要执行的命令
        language: 语言类型 "python" 或 "r"
        environment: 环境变量字典
        timeout: 容器执行超时时间（秒），默认 3600 秒（1小时）以适应生信分析任务

    Returns:
        (输出日志, 退出码) 元组
    """
    try:
        # 根据语言选择执行命令
        if language.lower() == "r":
            cmd = ["Rscript", "-e", command]
        else:
            cmd = ["python", "-c", command]

        # ✨ 核心修复 1：读取在 docker-compose 中配置的物理机绝对路径
        host_upload_dir = os.environ.get("HOST_UPLOAD_DIR", "/app/uploads")

        # ✨ 新增：准备环境变量（如果有）
        env_list = []
        if environment:
            for key, value in environment.items():
                env_list.append(f"{key}={value}")

        # ✨ 添加 conda 环境变量
        env_list.append(f"PATH={CONDA_CONTAINER_PATH}/bin:/usr/local/bin:/usr/bin:/bin")
        env_list.append(f"CONDA_PREFIX={CONDA_CONTAINER_PATH}")

        # 创建容器
        create_data = json.dumps({
            "Image": image,
            "platform": "linux/amd64",
            "Cmd": cmd,
            "Tty": True,
            "User": "root",
            "Env": env_list if env_list else None,
            "HostConfig": {
                "Memory": 4 * 1024 * 1024 * 1024,  # 4GB
                "NetworkMode": "none",
                "CapDrop": ["ALL"],
                # ✨ 挂载 uploads 和 conda 目录
                "Binds": [
                    f"{host_upload_dir}:/app/uploads:rw",
                    f"{CONDA_HOST_PATH}:{CONDA_CONTAINER_PATH}:rw"
                ]
            },
            "Volumes": {"/app/uploads": {}, CONDA_CONTAINER_PATH: {}},
            "WorkingDir": "/app"
        })

        resp = docker_api_request("POST", "/containers/create", create_data, timeout=30)

        if 'Id' not in resp:
            return f"❌ 创建容器失败: {resp}", 1

        container_id = resp['Id']

        # 启动容器
        docker_api_request("POST", f"/containers/{container_id}/start", timeout=30)

        # ✨ 等待容器完成（带超时和 sleep，避免忙等待）
        start_time = time.time()
        while True:
            info = docker_api_request("GET", f"/containers/{container_id}/json", timeout=30)
            status = info.get('State', {}).get('Status')

            # ✨ 超时检查
            elapsed = time.time() - start_time
            if elapsed > timeout:
                docker_api_request("POST", f"/containers/{container_id}/stop?t=10", timeout=30)
                log.warning(f"[run_container] 容器执行超时 ({timeout}s)，已强制停止")
                # 清理容器
                docker_api_request("DELETE", f"/containers/{container_id}?force=true", timeout=30)
                return f"❌ 执行超时 (超过 {timeout} 秒)", 1

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

        # 清理容器
        docker_api_request("DELETE", f"/containers/{container_id}?force=true", timeout=30)

        return str(log_output), exit_code

    except socket.timeout:
        log.error("[run_container] Docker API 请求超时")
        return "❌ Docker API 请求超时", 1
    except Exception as e:
        return f"❌ Docker API 错误: {str(e)}", 1


def run_nextflow_in_sandbox(
    work_dir: str,
    params: dict,
    log_callback: callable = None
) -> tuple[str, int]:
    """
    在沙箱中执行 Nextflow 流程

    特点：
    1. 挂载 conda 目录（包含 nextflow, fastqc, multiqc 等）
    2. 允许网络（用于下载缺失的 conda 包）
    3. 自动检测并安装缺失软件
    """
    try:
        host_upload_dir = os.environ.get("HOST_UPLOAD_DIR", "/app/uploads")
        params_json = json.dumps(params)

        # 构建执行脚本（注意：不使用 f-string，避免花括号冲突）
        nf_script = '''
import subprocess
import sys
import os
import json

# 设置环境
os.environ["PATH"] = "''' + CONDA_CONTAINER_PATH + '''/bin:" + os.environ.get("PATH", "")
os.environ["NXF_HOME"] = "''' + CONDA_CONTAINER_PATH + '''/nextflow"

def check_and_install(tool_name, conda_package=None):
    """检查工具是否存在，不存在则用 conda 安装"""
    conda_package = conda_package or tool_name
    try:
        subprocess.run(["which", tool_name], check=True, capture_output=True)
        print(f"✅ {tool_name} 已安装")
        return True
    except:
        print(f"📥 {tool_name} 未安装，正在使用 conda 安装...")
        result = subprocess.run([
            "''' + CONDA_CONTAINER_PATH + '''/bin/conda", "install", "-y", "-c", "bioconda", "-c", "conda-forge", conda_package
        ], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {tool_name} 安装成功")
            return True
        else:
            print(f"❌ {tool_name} 安装失败: {result.stderr}")
            return False

# 检查必要工具
tools_needed = ["nextflow", "fastqc", "multiqc"]
for tool in tools_needed:
    if not check_and_install(tool):
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
                "Memory": 8 * 1024 * 1024 * 1024,  # 8GB
                # ✨ 允许网络（用于 conda 安装）
                "NetworkMode": "bridge",
                "Binds": [
                    f"{host_upload_dir}:/app/uploads:rw",
                    f"{CONDA_HOST_PATH}:{CONDA_CONTAINER_PATH}:rw"
                ]
            },
            "Volumes": {"/app/uploads": {}, CONDA_CONTAINER_PATH: {}},
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

        # ANSI 转义码清理函数
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

        while True:
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
    代码生成的任何图表或文件必须保存在 /app/uploads 挂载目录中。

    Args:
        code: 包含有效 Python 语法的字符串代码。
        environment: 可选的环境变量字典，如 {"TASK_OUT_DIR": "/app/uploads/project_1/results", "PROJECT_ID": "1"}
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