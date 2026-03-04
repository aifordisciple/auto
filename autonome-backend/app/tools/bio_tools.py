import os
import docker
from docker import APIClient
from langchain_core.tools import tool
from app.core.logger import log
from app.core.config import settings

# ✨ 修复 Docker-in-Docker 问题：直接使用 Unix socket
try:
    docker_client = APIClient(base_url='unix:///var/run/docker.sock')
    docker_client.ping()
    log.info("🛡️ Docker 沙箱引擎已就绪 (via Unix Socket)")
except Exception as e:
    log.warning(f"Docker client 初始化失败，沙箱可能无法运行: {e}")
    docker_client = None


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
    """当用户要求进行单细胞 RNA-seq 分析时调用此工具。"""
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
    
    if not docker_client:
        log.error("❌ Docker client 未初始化")
        return "❌ 严重系统错误：沙箱引擎未连接。"

    # 获取宿主机物理路径
    host_upload_dir = os.getenv("HOST_UPLOAD_DIR", os.path.abspath(settings.UPLOAD_DIR))

    log.info("🛡️ 正在拉起重型单细胞分析沙箱 (autonome-tool-env)...")
    
    try:
        # ✨ 创建 host_config 来配置宿主机资源
        host_config = docker_client.create_host_config(
            mem_limit='4g',
            binds=[f'{host_upload_dir}:/app/uploads:rw'],
            network_mode='none',
            cap_drop=['ALL'],
        )
        
        # 创建容器
        container = docker_client.create_container(
            image='autonome-tool-env',
            command=['python', '-c', code],
            host_config=host_config,
        )
        
        # 启动容器
        docker_client.start(container['Id'])
        # 使用 APIClient 创建容器
        container_config = {
            'image': 'autonome-tool-env',
            'command': ['python', '-c', code],
            'mem_limit': '4g',
            'network_disabled': True,
            'cap_drop': ['ALL'],
            'host_config': {
                'binds': {host_upload_dir: {'bind': '/app/uploads', 'mode': 'rw'}},
                'mem_limit': '4g',
            }
        }
        
        # 创建并启动容器
        container = docker_client.create_container(**container_config)
        docker_client.start(container['Id'])
        
        # 等待容器执行完成
        result = docker_client.wait(container['Id'])
        
        # 获取日志
        logs = docker_client.logs(container['Id'], stdout=True, stderr=True, tail=100)
        result_output = logs.decode('utf-8').strip()
        
        # 清理容器
        docker_client.remove_container(container['Id'], force=True)
        # 使用 APIClient 创建容器
        container_config = {
            'Image': 'autonome-tool-env',
            'Command': ['python', '-c', code],
            'Memory': 4 * 1024 * 1024 * 1024,  # 4GB
            'NetworkDisabled': True,
            'CapDrop': ['ALL'],
            'HostConfig': {
                'Binds': [f'{host_upload_dir}:/app/uploads:rw'],
                'Memory': 4 * 1024 * 1024 * 1024,
            }
        }
        
        # 创建并启动容器
        container = docker_client.create_container(**container_config)
        docker_client.start(container['Id'])
        
        # 等待容器执行完成
        result = docker_client.wait(container['Id'])
        
        # 获取日志
        logs = docker_client.logs(container['Id'], stdout=True, stderr=True, tail=100)
        result_output = logs.decode('utf-8').strip()
        
        # 清理容器
        docker_client.remove_container(container['Id'], force=True)
        
        # ✨ 添加调试日志：打印沙箱返回的结果
        log.info("========== 📦 沙箱返回的结果 ==========")
        log.info(result_output[:500] if len(result_output) > 500 else result_output)
        log.info("========================================")
        log.info("✅ 单细胞流程执行完毕并销毁。")
        return result_output

    except Exception as e:
        log.error(f"⚠️ 沙箱执行报错: {str(e)}")
        return f"❌ 代码执行报错:\n{str(e)}\n请根据此报错修正代码。"


# 导出工具列表供大模型绑定
bio_tools_list = [rnaseq_qc, variant_calling, sc_rna_analysis, execute_python_code]
