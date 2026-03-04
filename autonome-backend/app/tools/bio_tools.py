import os
import docker
from langchain_core.tools import tool
from app.core.logger import log
from app.core.config import settings

# ✨ 修复 Docker-in-Docker 问题：使用 Unix socket 而不是 from_env()
# 设置环境变量让 docker 客户端使用 Unix socket
os.environ['DOCKER_HOST'] = 'unix:///var/run/docker.sock'

try:
    docker_client = docker.from_env()
    docker_client.ping()
    log.info("🛡️ Docker 沙箱引擎已就绪")
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

    # ✨ 获取我们在 Compose 中传入的宿主机物理路径，若无则降级为相对路径
    host_upload_dir = os.getenv("HOST_UPLOAD_DIR", os.path.abspath(settings.UPLOAD_DIR))

    log.info("🛡️ 正在拉起重型单细胞分析沙箱 (autonome-tool-env)...")
    
    try:
        container = docker_client.containers.run(
            image="autonome-tool-env",  # ✨ 换上你的专属生信大镜像！
            command=["python", "-c", code],
            
            # 🛡️ 释放算力：单细胞动辄十几万细胞，内存至少给 4G (按你机器配置可上调至 8g/16g)
            mem_limit="4g",
            
            # 依然保持断网与剥夺权限，保证绝对安全
            network_disabled=True,
            cap_drop=["ALL"],
            
            # ✨ 核心挂载：将宿主机的 uploads 挂载进去，给读写(rw)权限
            # 这样沙箱既能读取用户上传的 h5ad，也能把画好的 UMAP PNG 存出来！
            volumes={
                host_upload_dir: {'bind': '/app/uploads', 'mode': 'rw'}
            },
            
            detach=False,
            remove=True,
            stdout=True,
            stderr=True
        )
        
        result_output = container.decode('utf-8').strip()
        # ✨ 添加调试日志：打印沙箱返回的结果
        log.info("========== 📦 沙箱返回的结果 ==========")
        log.info(result_output[:500] if len(result_output) > 500 else result_output)
        log.info("========================================")
        log.info("✅ 单细胞流程执行完毕并销毁。")
        return result_output

    except docker.errors.ContainerError as e:
        error_msg = e.stderr.decode('utf-8').strip()
        log.error(f"⚠️ 算法报错:\n{error_msg}")
        return f"❌ 代码报错:\n{error_msg}\n请根据此报错修正代码。"
        
    except docker.errors.APIError as e:
        log.error(f"💥 沙箱引擎物理熔断: {str(e)}")
        if "OOMKilled" in str(e) or e.status_code == 137:
            return "❌ 执行失败：生信矩阵过大导致 OOM (内存超限)，已被沙箱熔断。"
        return f"❌ 沙箱系统异常: {str(e)}"
    
    except Exception as e:
        return f"❌ 未知沙箱错误: {str(e)}"


# 导出工具列表供大模型绑定
bio_tools_list = [rnaseq_qc, variant_calling, sc_rna_analysis, execute_python_code]
