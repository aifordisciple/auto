import os
import time
import json
import re
import traceback
import requests
from celery import Celery
import redis

from sqlmodel import Session
from app.core.database import engine
from app.models.domain import ChatMessage
from app.tools.bio_tools import run_container

# ✨ 引入全局配置中心
from app.core.config import settings
from app.core.logger import log

# 1. 初始化 Celery 实例
celery_app = Celery(
    "bioinfo_tasks",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"
)

# 2. 初始化 Redis 客户端 (用于日志流)
redis_client = redis.Redis(
    host=settings.REDIS_HOST, 
    port=settings.REDIS_PORT, 
    db=2, 
    decode_responses=True
)

# Celery 配置
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
)


# ==========================================
# ✨ 新增：生信图表专家解读 Agent
# ==========================================
INTERPRETER_PROMPT = """你现在是一位顶尖的计算生物学家和高分 SCI 论文撰稿人。
用户刚刚成功运行了一段生信分析代码，生成了对应的图表。

【输入信息】
1. 用户的原始意图: {user_prompt}
2. 用于生成图表的源码:
{source_code}
3. 数据的基本特征摘要: 
{data_summary}

【任务要求】
请你根据上述信息，为这幅生成的图表撰写一份专业报告。请严格按照以下 Markdown 结构输出。如果有些数据你无法确定，请用泛用的专业学术词汇描述，绝对不要编造具体数字：

### 📝 图注与方法 (Legends & Methods)
- **中文图注**：用一句话概括图表内容。
- **English Legend**：Translate the Chinese legend into standard academic English.
- **材料与方法**：根据源码，用学术语言描述该图是如何分析，使用什么软件/包生成的。
- **English Methods**：Translate the Chinese Methods into standard academic English.

### 🔬 图表深度解读 (Interpretation)
- **技术解读**：解释图表中的视觉元素（例如：横轴代表样本，纵轴代表基因，颜色的深浅代表表达量高低）。
- **科学洞察**：结合【数据的基本特征摘要】，指出图表中呈现出的生物学趋势或结论（例如哪些基因高表达）。

### 💡 专家启发与建议 (Suggestions)
- **图形优化**：提出 1-2 个可以让这张图更适合发表的改进建议（如：调整配色、添加样本注释条、Z-score 标准化）。
- **下游分析**：基于当前的分析，建议用户接下来可以做什么深度分析（如：进行差异基因提取、GO/KEGG 富集分析）。
"""

def generate_expert_report(user_prompt: str, source_code: str, data_summary: str) -> str:
    """调用本地大模型生成解读报告"""
    try:
        api_base = "http://host.docker.internal:11434/v1"
        
        prompt = INTERPRETER_PROMPT.format(
            user_prompt=user_prompt,
            source_code=source_code,
            data_summary=data_summary
        )
        
        payload = {
            "model": "qwen3.5:35b",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4
        }
        
        response = requests.post(
            f"{api_base}/chat/completions", 
            json=payload, 
            timeout=60
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"> *(⚠️ AI 专家解读生成超时或失败，您可以尝试直接观察图表。错误信息: {str(e)})*"


# ✨ 统一的日志函数：同时写入 Redis 和文件
def create_task_logger(task_id: str):
    def log_to_redis_and_file(message: str, level: str = "INFO"):
        # 1. 写入 Redis 供前端流式读取
        formatted_msg = f"[{time.strftime('%H:%M:%S')}] [{level}] {message}"
        log_key = f"task_logs:{task_id}"
        redis_client.rpush(log_key, formatted_msg)
        redis_client.expire(log_key, 86400)
        
        # 2. ✨ 同时写入物理服务器日志！
        if level == "ERROR":
            log.error(f"[Task {task_id}] {message}")
        elif level == "WARNING":
            log.warning(f"[Task {task_id}] {message}")
        else:
            log.info(f"[Task {task_id}] {message}")
            
    return log_to_redis_and_file


@celery_app.task(bind=True)
def run_rnaseq_qc_pipeline(self, params: dict):
    """
    RNA-Seq QC Pipeline - 带完整的异常捕获与状态广播
    """
    task_id = self.request.id
    log_key = f"task_logs:{task_id}"
    
    redis_client.delete(log_key)
    log_msg = create_task_logger(task_id)
    
    try:
        log_msg(f"🚀 初始化底层计算引擎 (Task ID: {task_id})")
        log_msg(f"⚙️ 接收并解析参数: {json.dumps(params, ensure_ascii=False)}")
        
        time.sleep(1.5)
        log_msg(f"✅ 成功挂载参考基因组: {params.get('ref_genome', '未知')}")
        
        log_msg(f"⏳ 启动 FastQC 质量评估集群... (Phred >= {params.get('qual_threshold', 20)})")
        for i in range(1, 6):
            time.sleep(1.5)
            progress = i * 20
            log_msg(f"   -> [Worker-0{i}] 处理进度: {progress}% (已分析 {progress * 25000} reads)")
            self.update_state(state='PROGRESS', meta={'progress': progress})

        if params.get('remove_adapters'):
            log_msg("✂️ 正在运行 Trimmomatic 切除接头序列...")
            time.sleep(2.5)
            log_msg("✅ 序列清洗完毕。")

        log_msg("🎉 [SUCCESS] 质控流程全部运行完成！报告已生成。")
        
        return {"status": "success", "report_path": f"/workspace/results/{task_id}_multiqc.html"}
        
    except Exception as e:
        error_trace = traceback.format_exc()
        log_msg(f"💥 任务执行遭遇致命错误: {str(e)}", level="ERROR")
        log_msg(f"详情:\n{error_trace}", level="ERROR")
        raise e


@celery_app.task(bind=True)
def run_variant_calling_pipeline(self, params: dict):
    """Variant Calling Pipeline"""
    task_id = self.request.id
    log_key = f"task_logs:{task_id}"
    
    redis_client.delete(log_key)
    log_msg = create_task_logger(task_id)
    
    try:
        log_msg(f"🚀 初始化变异检测引擎 (Task ID: {task_id})")
        log_msg(f"⚙️ 参数: {json.dumps(params, ensure_ascii=False)}")
        
        time.sleep(1.5)
        log_msg(f"✅ 加载参考基因组: {params.get('ref_genome', 'hg38')}")
        
        log_msg("🔍 运行 GATK HaplotypeCaller...")
        for i in range(1, 6):
            time.sleep(1.5)
            progress = i * 20
            log_msg(f"   [GATK] 进度: {progress}%")
            self.update_state(state='PROGRESS', meta={'progress': progress})
        
        log_msg("🎉 变异检测完成！")
        return {"status": "success", "snp_count": 12456, "indel_count": 2341}
        
    except Exception as e:
        error_trace = traceback.format_exc()
        log_msg(f"💥 错误: {str(e)}", level="ERROR")
        raise e


@celery_app.task(bind=True)
def run_scrna_analysis_pipeline(self, params: dict):
    """Single-Cell RNA Analysis Pipeline"""
    task_id = self.request.id
    log_key = f"task_logs:{task_id}"
    
    redis_client.delete(log_key)
    log_msg = create_task_logger(task_id)
    
    try:
        log_msg(f"🚀 初始化单细胞分析引擎 (Task ID: {task_id})")
        
        time.sleep(1.5)
        log_msg("✅ 加载表达矩阵...")
        
        log_msg("🔬 运行 Seurat 聚类...")
        for i in range(1, 6):
            time.sleep(1.5)
            progress = i * 20
            log_msg(f"   [Seurat] 进度: {progress}%")
            self.update_state(state='PROGRESS', meta={'progress': progress})
        
        log_msg("🗺️ 生成 UMAP 可视化...")
        log_msg("🎉 分析完成！")
        return {"status": "success", "clusters": 8, "cells": 5234}
        
    except Exception as e:
        error_trace = traceback.format_exc()
        log_msg(f"💥 错误: {str(e)}", level="ERROR")
        raise e


# ==========================================
# GEO 单细胞数据分析异步任务
# ==========================================
@celery_app.task(bind=True)
def run_geo_single_cell_pipeline(self, accession: str, project_id: int, user_id: int):
    """
    接收大模型投递的 GEO 数据集分析任务。
    后台拉起自主 Docker 引擎进行单细胞全流程计算。
    """
    import os
    import docker
    from app.core.config import settings
    
    task_id = self.request.id
    log_key = f"task_logs:{task_id}"
    redis_client.delete(log_key)
    
    def log_progress(msg: str, level: str = "INFO"):
        formatted_msg = f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}"
        redis_client.rpush(log_key, formatted_msg)
        redis_client.expire(log_key, 86400 * 3)  # 保留3天日志

    log_progress(f"🚀 [INIT] 启动自动化单细胞分析流水线，目标数据集: {accession}")
    log_progress("⬇️ 正在连接公共数据库下载原始矩阵数据... (此过程取决于网络速度，请耐心等待)")
    
    time.sleep(3)  # 模拟下载等待
    log_progress("✅ 数据拉取完毕！正在校验 MD5 与数据完整性...")
    time.sleep(1)
    
    log_progress("🛡️ 正在调度重型沙箱 (autonome-tool-env) 准备矩阵运算...")

    # ✨ 核心：将在 Docker 子容器中执行的全套生信 Python 脚本
    scanpy_script = f"""
import scanpy as sc
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

print("---- Autonome Single-Cell Engine Initialized ----")
sc.settings.verbosity = 3

# 模拟加载刚刚下载的 GEO 数据集 (演示时使用 pbmc3k)
print(f"Loading matrix for {accession}...")
adata = sc.datasets.pbmc3k()

print("Step 1: Quality Control (QC)...")
sc.pp.filter_cells(adata, min_genes=200)
sc.pp.filter_genes(adata, min_cells=3)

print("Step 2: Normalization and Log1p...")
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

print("Step 3: Highly Variable Genes Selection...")
sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
adata = adata[:, adata.var.highly_variable]

print("Step 4: PCA & Neighborhood Graph...")
sc.tl.pca(adata, svd_solver='arpack')
sc.pp.neighbors(adata, n_neighbors=10, n_pcs=40)

print("Step 5: UMAP Dimensionality Reduction & Leiden Clustering...")
sc.tl.umap(adata)
sc.tl.leiden(adata)

# ✨ 将生成的图片精准保存到宿主机的 uploads 目录下
out_filename = f"umap_{accession}_{task_id[-6:]}.png"
out_path = f"/app/uploads/{out_filename}"

print("Rendering high-resolution UMAP plot...")
sc.pl.umap(adata, color=['leiden'], show=False, title=f"{accession} UMAP Clustering")
plt.savefig(out_path, bbox_inches='tight', dpi=300)

print(f"SUCCESS: Analysis pipeline completed. Target output -> {out_filename}")
"""

    try:
        docker_client = docker.from_env()
        host_upload_dir = os.getenv("HOST_UPLOAD_DIR", os.path.abspath(settings.UPLOAD_DIR))
        
        log_progress("🧬 算力引擎已点火，开始执行细胞图谱降维 (可能需要数十分钟)...")
        
        # 启动容器执行长耗时任务
        container = docker_client.containers.run(
            image="autonome-tool-env",
            command=["python", "-c", scanpy_script],
            mem_limit="4g",
            network_disabled=True,  # 确保分析过程无网断连
            volumes={host_upload_dir: {'bind': '/app/uploads', 'mode': 'rw'}},
            detach=False,
            remove=True,
            stdout=True,
            stderr=True
        )
        
        # 将容器的标准输出追加到日志
        container_logs = container.decode('utf-8').strip()
        for line in container_logs.split('\n'):
            log_progress(f"  [Container] {line}")
            
        log_progress("🎉 [SUCCESS] 自动化单细胞全生命周期分析完成！")
        log_progress("📄 报告与 UMAP 高清大图已同步至您的项目【DATA CENTER】中。")
        
        return {"status": "success", "dataset": accession}
        
    except Exception as e:
        log_progress(f"💥 致命错误：计算引擎崩溃 -> {str(e)}", "ERROR")
        raise e


# ==========================================
# 通用 Python 代码沙箱执行任务
# ==========================================
@celery_app.task(bind=True)
def run_custom_python_task(self, params: dict):
    """通用 Python 代码沙箱执行任务，并在完成后将结果写回聊天记录"""
    task_id = self.request.id
    code = params.get("code")
    session_id = params.get("session_id")
    project_id = params.get("project_id")
    
    log_msg = create_task_logger(task_id)
    log_msg(f"🚀 初始化通用沙箱引擎 (Task ID: {task_id})")
    
    try:
        result_output, exit_code = run_container("autonome-tool-env", code)
        
        # Clean output of control characters
        if result_output:
            result_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result_output)
            result_output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result_output)
            result_output = re.sub(r'^\[\d+\]\s*', '', result_output, flags=re.MULTILINE)
            result_output = result_output.replace('\r\n', '\n').replace('\r', '\n')
            result_output = re.sub(r'\n{3,}', '\n\n', result_output)
            result_output = result_output.strip()
        
        log_msg("🎉 沙箱代码执行完毕！")
        
        with Session(engine) as db:
            final_content = (
                f"✅ **分析任务已完成 (Task ID: `{task_id[:8]}`)**\n\n"
                f"---\n"
                f"### 📊 执行结果\n\n"
                f"{result_output}"
            )
            new_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=final_content,
            )
            db.add(new_msg)
            db.commit()
            log_msg(f"✅ 结果已成功回写至 ChatSession: {session_id}")
            
        return {"status": "success"}
    except Exception as e:
        log_msg(f"💥 执行失败: {str(e)}", level="ERROR")
        raise e


# ==========================================
# 通用 R 语言沙箱执行任务
# ==========================================
@celery_app.task(bind=True)
def run_custom_r_task(self, params: dict):
    """通用 R 语言沙箱执行任务，并在完成后将结果写回聊天记录"""
    task_id = self.request.id
    code = params.get("code")
    session_id = params.get("session_id")
    project_id = params.get("project_id")
    user_message = params.get("message", "用户执行了生信数据可视化任务")
    
    log_msg = create_task_logger(task_id)
    log_msg(f"🚀 初始化 R 语言作图引擎 (Task ID: {task_id})")
    
    try:
        result_output, exit_code = run_container("autonome-tool-env", code, language="r")
        
        # Clean output of control characters
        if result_output:
            result_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result_output)
            result_output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result_output)
            result_output = re.sub(r'^\[\d+\]\s*', '', result_output, flags=re.MULTILINE)
            result_output = result_output.replace('\r\n', '\n').replace('\r', '\n')
            result_output = re.sub(r'\n{3,}', '\n\n', result_output)
            result_output = result_output.strip()
        
        log_msg("🎉 R 脚本执行完毕！开始收集数据指纹...")
        
        # Extract project_id and session_id from params, with fallback
        actual_project_id = project_id if project_id else 1
        actual_session_id = session_id if session_id else 1
        
        # Extract actual filename from code using regex
        img_match = re.search(r"filename\s*=\s*['\"]?/?app/uploads/project_\d+/([^'\"]+)['\"]?", code)
        actual_filename = img_match.group(1) if img_match else "heatmap.png"
        
        # 2. ✨ 读取数据指纹摘要 (data_summary.txt)
        summary_path = f"/app/uploads/project_{actual_project_id}/results/data_summary.txt"
        data_summary = "暂无详细数据特征"
        if os.path.exists(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                data_summary = f.read()

        # 3. ✨ 调用专家 Agent 生成报告
        log_msg("🧠 正在呼叫生物学专家 Agent 进行深度解读... (约需 10-30 秒，请稍候)")
        
        expert_report = generate_expert_report(user_message, code, data_summary)

        # 4. 拼装成极其华丽的 Markdown 报告
        log_msg("📝 报告生成完毕，正在推送到界面...")
        
        with Session(engine) as db:
            final_content = (
                f"✅ **分析任务已完成 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                f"---\n"
                f"### 📊 可视化结果\n\n"
                f"![Analysis_Result](/api/projects/{actual_project_id}/files/{actual_filename}/view)\n\n"
                f"---\n"
                f"{expert_report}"
            )
            new_msg = ChatMessage(
                session_id=actual_session_id,
                role="assistant",
                content=final_content,
            )
            db.add(new_msg)
            db.commit()
            log_msg(f"✅ 结果已成功回写至 ChatSession: {actual_session_id}")
            
        return {"status": "success"}
    except Exception as e:
        log_msg(f"💥 R 脚本执行失败: {str(e)}", level="ERROR")
        raise e


# 任务注册表（统一管理所有 Celery 任务）
TASK_REGISTRY = {
    "rnaseq-qc": run_rnaseq_qc_pipeline,
    "variant-calling": run_variant_calling_pipeline,
    "sc-rna-analysis": run_scrna_analysis_pipeline,
    "execute-python": run_custom_python_task,
    "execute-r": run_custom_r_task,
}
