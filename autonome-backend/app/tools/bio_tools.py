import os
import json
import subprocess
from langchain_core.tools import tool
from app.core.logger import log
from app.core.config import settings


# ✨ 使用 subprocess 调用 docker CLI 避免 urllib3 兼容性问题
def run_docker_container(image: str, command: str) -> tuple[str, int]:
    """
    使用 subprocess 运行 docker 容器
    返回: (output, exit_code)
    """
    docker_cmd = [
        'docker', 'run', '--rm',
        '--memory=4g',
        '--network=none',
        '--cap-drop=ALL',
        '-v', 'uploads_data:/app/uploads:rw',
        image,
        'python', '-c', command
    ]
    
    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        return result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "❌ 代码执行超时 (5分钟)", 1
    except Exception as e:
        return f"❌ Docker 执行失败: {str(e)}", 1


# ✨ 标记沙箱可用
DOCKER_SANDBOX_AVAILABLE = True
log.info("🛡️ Docker 沙箱引擎已就绪 (使用 subprocess)")


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
        # ✨ 使用 subprocess 调用 docker
        result_output, exit_code = run_docker_container(
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
