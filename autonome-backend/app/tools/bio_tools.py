import os
import json
import socket
import re
from langchain_core.tools import tool
from app.core.logger import log
from app.core.config import settings

DOCKER_SOCKET = '/var/run/docker.sock'

# ✨ 新增 return_raw 参数，专门用于读取纯文本日志，防止把报错日志强行解析为 JSON
def docker_api_request(method: str, path: str, data: str = None, return_raw: bool = False):
    """直接通过 Unix socket 调用 Docker API (完美版)"""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
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


def run_container(image: str, command: str, language: str = "python", environment: dict = None) -> tuple[str, int]:
    """通过 Docker API 运行容器"""
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

        # 创建容器
        create_data = json.dumps({
            "Image": image,
            "platform": "linux/amd64",
            "Cmd": cmd,
            # ✨ 核心修复 3：开启 Tty。这会让 Docker 放弃写入 8 字节的二进制头部流，彻底解决乱码问题
            "Tty": True,
            "User": "root",  # 以 root 身份运行
            "Env": env_list if env_list else None,
            "HostConfig": {
                "Memory": 4 * 1024 * 1024 * 1024,  # 4GB
                "NetworkMode": "none",
                "CapDrop": ["ALL"],
                # ✨ 核心修复 1：将写死的 uploads_data 替换为动态获取的物理机绝对路径
                "Binds": [f"{host_upload_dir}:/app/uploads:rw"]
            },
            "Volumes": {"/app/uploads": {}},
            "WorkingDir": "/app"
        })
        
        resp = docker_api_request("POST", "/containers/create", create_data)
        
        if 'Id' not in resp:
            return f"❌ 创建容器失败: {resp}", 1
            
        container_id = resp['Id']
        
        # 启动容器
        docker_api_request("POST", f"/containers/{container_id}/start")
        
        # 等待容器完成
        while True:
            info = docker_api_request("GET", f"/containers/{container_id}/json")
            if info.get('State', {}).get('Status') == 'exited':
                break
        
        # ✨ 核心修复 2：使用 return_raw=True 提取纯文本日志
        log_output = docker_api_request("GET", f"/containers/{container_id}/logs?stdout=true&stderr=true&tail=100", return_raw=True)
        
        # 防御性清理：剔除无法显示的特殊控制符（保留换行符）
        if isinstance(log_output, str):
            log_output = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', log_output)
        
        # 获取退出码
        exit_code = info.get('State', {}).get('ExitCode', 0)
        
        # 清理容器
        docker_api_request("DELETE", f"/containers/{container_id}?force=true")
        
        return str(log_output), exit_code
        
    except Exception as e:
        return f"❌ Docker API 错误: {str(e)}", 1


# ✨ 标记沙箱可用
DOCKER_SANDBOX_AVAILABLE = True
log.info("🛡️ Docker 沙箱引擎已就绪 (纯净算力版)")

@tool
def execute_python_code(code: str) -> str:
    """
    在安全的 Docker 沙箱中执行 Python 数据科学和生信分析代码。
    此工具拥有完整的 matplotlib, pandas, scanpy 等数据科学生态。
    代码生成的任何图表或文件必须保存在 /app/uploads 挂载目录中。
    
    Args:
        code: 包含有效 Python 语法的字符串代码。
    """
    log.info("========== 🤖 AI 尝试执行的代码 ==========")
    log.info(code[:1000] if len(code) > 1000 else code)
    log.info("==========================================")
    
    if not DOCKER_SANDBOX_AVAILABLE:
        log.error("❌ Docker sandbox not available")
        return "❌ 严重系统错误：沙箱引擎未就绪。"

    log.info("🛡️ 正在拉起重型分析沙箱...")
    
    try:
        result_output, exit_code = run_container(
            image='autonome-tool-env',
            command=code
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


# ✨ 核心修改：只导出这一个真正的底层算力工具！
bio_tools_list = [execute_python_code]