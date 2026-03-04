import os
import json
import socket
from langchain_core.tools import tool
from app.core.logger import log
from app.core.config import settings


DOCKER_SOCKET = '/var/run/docker.sock'


def docker_api_request(method: str, path: str, data: str = None) -> dict:
    """直接通过 Unix socket 调用 Docker API (完美版)"""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(DOCKER_SOCKET)
    
    body = data.encode('utf-8') if data else None
    
    # ✨ 核心修复 1：使用 HTTP/1.0 强制服务器发送完毕后断开连接
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
    
    # ✨ 核心修复 2：安全地读取全部数据，直到连接自然关闭
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
        return {}

    # ✨ 核心修复 3：用最安全的截取方式提取 JSON
    start_dict = body_str.find('{')
    end_dict = body_str.rfind('}')
    
    start_list = body_str.find('[')
    end_list = body_str.rfind(']')
    
    try:
        # 如果看起来像字典
        if start_dict != -1 and end_dict != -1 and (start_list == -1 or start_dict < start_list):
            return json.loads(body_str[start_dict:end_dict+1])
        # 如果看起来像列表
        elif start_list != -1 and end_list != -1:
            return json.loads(body_str[start_list:end_list+1])
            
        return json.loads(body_str)
    except Exception as e:
        log.warning(f"JSON 解析回退, 原始数据长度: {len(body_str)}")
        return {"body": body_str}


def run_container(image: str, command: str) -> tuple[str, int]:
    """通过 Docker API 运行容器"""
    try:
        # 创建容器 - 指定平台为 amd64
        create_data = json.dumps({
            "Image": image,
            "platform": "linux/amd64",
            "Cmd": ["python", "-c", command],
            "HostConfig": {
                "Memory": 4 * 1024 * 1024 * 1024,  # 4GB
                "NetworkMode": "none",
                "CapDrop": ["ALL"],
                "Binds": ["uploads_data:/app/uploads:rw"]
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
        
        # 获取日志
        logs = docker_api_request("GET", f"/containers/{container_id}/logs?stdout=true&stderr=true&tail=100")
        log_output = json.dumps(logs) if isinstance(logs, dict) else str(logs)
        
        # 获取退出码
        exit_code = info.get('State', {}).get('ExitCode', 0)
        
        # 清理容器
        docker_api_request("DELETE", f"/containers/{container_id}?force=true")
        
        return log_output, exit_code
        
    except Exception as e:
        return f"❌ Docker API 错误: {str(e)}", 1


# ✨ 标记沙箱可用
DOCKER_SANDBOX_AVAILABLE = True
log.info("🛡️ Docker 沙箱引擎已就绪 (使用原生 socket)")


@tool
def rnaseq_qc(ref_genome: str, qual_threshold: int, remove_adapters: bool):
    """当用户要求对 RNA-Seq、Fastq 数据进行质控时，调用此工具提取参数。"""
    pass


@tool
def variant_calling(ref_genome: str, variant_type: str, min_read_depth: int):
    """当用户要求进行变异检测 (SNP/Indel) 时调用此工具。"""
    pass


@tool
def sc_rna_analysis(cluster_res: float, min_genes: int, min_cells: int):
    """当用户要求进行单细胞 RNA-seq 分析时，调用此工具。"""
    pass


@tool
def execute_python_code(code: str) -> str:
    """
    执行高算力的生信数据处理 (Scanpy 等)、分析及图表绘制代码。
    """
    # ✨ 添加调试日志：打印 AI 写的代码
    log.info("========== 🤖 AI 尝试执行的代码 ==========")
    log.info(code[:1000] if len(code) > 1000 else code)
    log.info("==========================================")
    
    if not DOCKER_SANDBOX_AVAILABLE:
        log.error("❌ Docker sandbox not available")
        return "❌ 严重系统错误：沙箱引擎未就绪。"

    log.info("🛡️ 正在拉起重型单细胞分析沙箱 (autonome-tool-env)...")
    
    try:
        result_output, exit_code = run_container(
            image='autonome-tool-env',
            command=code
        )
        
        # ✨ 添加调试日志：打印沙箱返回的结果
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


# 导出工具列表供大模型绑定
bio_tools_list = [rnaseq_qc, variant_calling, sc_rna_analysis, execute_python_code]
