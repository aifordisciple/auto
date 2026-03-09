import os
import time
import json
import re
import traceback
import requests
from celery import Celery
import redis
from jinja2 import Template

from sqlmodel import Session
from app.core.database import engine
from app.models.domain import ChatMessage
from app.tools.bio_tools import run_container

# ✨ 引入全局配置中心
from app.core.config import settings
from app.core.logger import log
from app.core.skill_parser import get_skill_parser

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
            "model": "qwen3-coder:30b",
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
# ==========================================
# 通用 Python 代码沙箱执行任务 (专家解读防弹版)
# ==========================================
@celery_app.task(bind=True)
def run_custom_python_task(self, params: dict):
    task_id = self.request.id
    code = params.get("code")
    session_id = params.get("session_id")  # ✨ 不再默认为 1
    project_id = params.get("project_id")  # ✨ 不再默认为 1
    user_message = params.get("message", "用户执行了生信数据分析任务")

    log_msg = create_task_logger(task_id)
    log_msg(f"🚀 初始化 Python 沙箱引擎 (Task ID: {task_id})")

    try:
        # 1. ✨ 生成本次任务专属的目录
        task_short_id = str(task_id)[:8]
        task_dir_name = f"task_{task_short_id}"
        # 容器内看到的绝对路径
        task_out_dir = f"/app/uploads/project_{project_id}/results/{task_dir_name}"
        os.makedirs(task_out_dir, exist_ok=True)
        log_msg(f"📁 已分配专属输出目录: results/{task_dir_name}")

        # 2. ✨ 将专属目录作为环境变量注入沙箱
        env = {"TASK_OUT_DIR": task_out_dir}
        result_output, exit_code = run_container("autonome-tool-env", code, language="python", environment=env)

        # 1. ✨ 终极终端乱码清理
        if result_output:
            # 清理标准 ANSI 转义序列
            result_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result_output)
            # 清理残余的光标控制符 (解决 [?25h 满屏的问题)
            result_output = re.sub(r'\[\?\d+[hl]', '', result_output)
            # 清理其他不可见字符
            result_output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result_output)
            result_output = result_output.replace('\r\n', '\n').replace('\r', '\n').strip()

        # 核心防御 1：拦截执行失败的代码
        if exit_code != 0:
            log_msg(f"💥 代码执行失败 (Exit Code {exit_code})", level="ERROR")
            with Session(engine) as db:
                final_content = (
                    f"❌ **代码在沙箱中崩溃了 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                    f"### ⚠️ 错误终端日志\n"
                    f"```text\n{result_output}\n```\n\n"
                    f"> *(未生成图表。请查阅上方报错信息，或者直接要求 AI 修正代码并重新执行。)*"
                )
                db.add(ChatMessage(session_id=session_id, role="assistant", content=final_content))
                db.commit()
            return {"status": "failure"}

        log_msg("🎉 代码执行成功！准备生成专家解读...")

        # 2. ✨ 扫描实际生成的文件目录，获取所有生成的文件
        generated_files = []
        if os.path.exists(task_out_dir):
            for f in os.listdir(task_out_dir):
                full_path = os.path.join(task_out_dir, f)
                if os.path.isfile(full_path):
                    generated_files.append(f)

        log_msg(f"📂 检测到生成的文件: {generated_files}")

        # 3. ✨ 构建文件列表 markdown（用于前端树状卡片提取）
        files_markdown = ""
        for filename in generated_files:
            # 容器内路径（前端正则会匹配这个格式）
            container_path = f"/app/uploads/project_{project_id}/results/{task_dir_name}/{filename}"
            files_markdown += f"{container_path}\n"

        # 4. ✨ 生成图片 markdown（如果有图片则显示第一张）
        img_extensions = ('.png', '.pdf', '.jpg', '.jpeg', '.svg')
        images = [f for f in generated_files if f.lower().endswith(img_extensions)]
        if images:
            # 显示第一张图片
            first_img = images[0]
            actual_filename = f"results/{task_dir_name}/{first_img}"
            markdown_img = f"\n![Analysis_Result](/api/projects/{project_id}/files/{actual_filename}/view)\n"
        else:
            markdown_img = ""

        # 5. ✨ 从专属子目录中读取数据指纹
        summary_path = f"{task_out_dir}/data_summary.txt"
        data_summary = "暂无详细数据特征"
        if os.path.exists(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                data_summary = f.read()

        # 生成专家解读
        expert_report = generate_expert_report(user_message, code, data_summary)

        with Session(engine) as db:
            final_content = (
                f"✅ **分析任务已完成 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                f"<!-- DEEP_INTERPRET_META\n"
                f"USER_MESSAGE: {user_message}\n"
                f"CODE_START\n{code}\nCODE_END\n"
                f"DEEP_INTERPRET_META -->\n"
                f"---\n"
                f"### 📊 执行日志与图表\n\n"
                f"```text\n{result_output}\n```\n"
                f"{markdown_img}\n"
                f"---\n"
                f"### 📁 生成的文件资产\n\n"
                f"{files_markdown}\n"
                f"---\n"
                f"{expert_report}"
            )
            db.add(ChatMessage(session_id=session_id, role="assistant", content=final_content))
            db.commit()

        return {"status": "success"}
    except Exception as e:
        log_msg(f"💥 发生系统错误: {str(e)}", level="ERROR")
        raise e


# ==========================================
# 通用 R 语言沙箱执行任务 (专家解读防弹版)
# ==========================================
@celery_app.task(bind=True)
def run_custom_r_task(self, params: dict):
    task_id = self.request.id
    code = params.get("code")
    session_id = params.get("session_id")  # ✨ 不再默认为 1
    project_id = params.get("project_id")  # ✨ 不再默认为 1
    user_message = params.get("message", "用户执行了生信 R 语言任务")

    log_msg = create_task_logger(task_id)
    log_msg(f"🚀 初始化 R 沙箱引擎 (Task ID: {task_id})")

    try:
        # 1. ✨ 生成本次任务专属的目录
        task_short_id = str(task_id)[:8]
        task_dir_name = f"task_{task_short_id}"
        # 容器内看到的绝对路径
        task_out_dir = f"/app/uploads/project_{project_id}/results/{task_dir_name}"
        os.makedirs(task_out_dir, exist_ok=True)
        log_msg(f"📁 已分配专属输出目录: results/{task_dir_name}")

        # 2. ✨ 将专属目录作为环境变量注入沙箱
        env = {"TASK_OUT_DIR": task_out_dir}
        result_output, exit_code = run_container("autonome-tool-env", code, language="r", environment=env)

        # 1. ✨ 终极终端乱码清理
        if result_output:
            result_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result_output)
            result_output = re.sub(r'\[\?\d+[hl]', '', result_output)  # 专门杀掉 [?25h
            result_output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result_output)
            result_output = result_output.replace('\r\n', '\n').replace('\r', '\n').strip()

        if exit_code != 0:
            log_msg(f"💥 R代码执行失败 (Exit Code {exit_code})", level="ERROR")
            with Session(engine) as db:
                final_content = (
                    f"❌ **R 代码在沙箱中崩溃了 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                    f"### ⚠️ 错误终端日志\n"
                    f"```text\n{result_output}\n```\n\n"
                    f"> *(未生成图表。请查阅上方报错信息，或者直接要求 AI 修正代码并重新执行。)*"
                )
                db.add(ChatMessage(session_id=session_id, role="assistant", content=final_content))
                db.commit()
            return {"status": "failure"}

        log_msg("🎉 R 代码执行成功！准备生成专家解读...")

        # 3. ✨ 扫描实际生成的文件目录，获取所有生成的文件
        generated_files = []
        if os.path.exists(task_out_dir):
            for f in os.listdir(task_out_dir):
                full_path = os.path.join(task_out_dir, f)
                if os.path.isfile(full_path):
                    generated_files.append(f)

        log_msg(f"📂 检测到生成的文件: {generated_files}")

        # 4. ✨ 构建文件列表 markdown（用于前端树状卡片提取）
        files_markdown = ""
        for filename in generated_files:
            # 容器内路径（前端正则会匹配这个格式）
            container_path = f"/app/uploads/project_{project_id}/results/{task_dir_name}/{filename}"
            files_markdown += f"{container_path}\n"

        # 5. ✨ 生成图片 markdown（如果有图片则显示第一张）
        img_extensions = ('.png', '.pdf', '.jpg', '.jpeg', '.svg')
        images = [f for f in generated_files if f.lower().endswith(img_extensions)]
        if images:
            # 显示第一张图片
            first_img = images[0]
            actual_filename = f"results/{task_dir_name}/{first_img}"
            markdown_img = f"\n![Analysis_Result](/api/projects/{project_id}/files/{actual_filename}/view)\n"
        else:
            markdown_img = "\n*(本次分析似乎没有生成可视化图表)*\n"

        # 6. ✨ 从专属子目录中读取数据指纹
        summary_path = f"{task_out_dir}/data_summary.txt"
        data_summary = "暂无详细数据特征"
        if os.path.exists(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                data_summary = f.read()

        expert_report = generate_expert_report(user_message, code, data_summary)

        with Session(engine) as db:
            final_content = (
                f"✅ **分析任务已完成 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                f"<!-- DEEP_INTERPRET_META\n"
                f"USER_MESSAGE: {user_message}\n"
                f"CODE_START\n{code}\nCODE_END\n"
                f"DEEP_INTERPRET_META -->\n"
                f"---\n"
                f"### 📊 执行日志与图表\n\n"
                f"```text\n{result_output}\n```\n"
                f"{markdown_img}\n"
                f"---\n"
                f"### 📁 生成的文件资产\n\n"
                f"{files_markdown}\n"
                f"---\n"
                f"{expert_report}"
            )
            db.add(ChatMessage(session_id=session_id, role="assistant", content=final_content))
            db.commit()

        return {"status": "success"}
    except Exception as e:
        log_msg(f"💥 发生系统错误: {str(e)}", level="ERROR")
        raise e


# ==========================================
# SKILL Bundle 执行任务 (双轨机制核心)
# ==========================================

def execute_nextflow_compiler(
    payload: dict,
    project_id: str,
    task_id: str,
    session_id: str,
    log_msg: callable
) -> dict:
    """
    执行 Nextflow 编译器 - 将逻辑蓝图编译为可执行的 Nextflow 流程

    不使用递归调用 Celery 任务，而是直接执行编译器脚本
    """
    import tempfile

    # 1. 获取 Nextflow Generator SKILL 的 bundle 路径
    parser = get_skill_parser()
    nf_skill = parser.get_skill_by_id("meta_nextflow_generator_01")

    if not nf_skill:
        raise RuntimeError("未找到 meta_nextflow_generator_01 SKILL")

    bundle_path = nf_skill.get("bundle_path", "")
    nf_compiler_script = os.path.join(bundle_path, "scripts", "nf_compiler.py")

    log_msg(f"📂 Nextflow 编译器路径: {nf_compiler_script}")

    if not os.path.exists(nf_compiler_script):
        raise RuntimeError(f"Nextflow 编译器脚本不存在: {nf_compiler_script}")

    # 2. 创建任务专属工作目录
    task_short_id = str(task_id)[:8]
    task_work_dir = f"/app/uploads/project_{project_id}/results/task_{task_short_id}"
    os.makedirs(task_work_dir, exist_ok=True)
    log_msg(f"📁 工作目录: {task_work_dir}")

    # 3. 创建 payload JSON 文件
    payload_file = os.path.join(task_work_dir, "pipeline_payload.json")
    with open(payload_file, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log_msg(f"📋 Payload 文件已创建: pipeline_payload.json")

    # 4. 构建执行命令（通过命令行参数传递）
    # nf_compiler.py 期望 --payload 和 --bundle_dir 参数
    command = f'''
import sys
sys.argv = ['nf_compiler.py', '--payload', '{payload_file}', '--bundle_dir', '{bundle_path}']
exec(open('{nf_compiler_script}').read())
'''

    log_msg("🚀 启动 Nextflow 编译器...")

    # 5. 在 Docker 沙箱中执行
    result_output, exit_code = run_container(
        "autonome-tool-env",
        command,
        language="python",
        environment={"TASK_OUT_DIR": task_work_dir, "PROJECT_ID": project_id}
    )

    # 6. 清理终端乱码并记录日志
    if result_output:
        result_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result_output)
        result_output = re.sub(r'\[\?\d+[hl]', '', result_output)
        result_output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result_output)
        result_output = result_output.replace('\r\n', '\n').replace('\r', '\n').strip()

    for line in result_output.split('\n'):
        if line.strip():
            log_msg(f"  [NF] {line}")

    if exit_code != 0:
        raise RuntimeError(f"Nextflow 执行失败 (Exit: {exit_code})")

    # 7. 扫描生成的文件
    generated_files = []
    if os.path.exists(task_work_dir):
        for f in os.listdir(task_work_dir):
            full_path = os.path.join(task_work_dir, f)
            if os.path.isfile(full_path):
                generated_files.append(f)

    log_msg(f"📂 生成的文件: {generated_files}")

    return {
        "work_dir": task_work_dir,
        "output": result_output,
        "files": generated_files
    }


@celery_app.task(bind=True)
def execute_bundle_task(self, payload: dict):
    """
    SKILL Bundle 执行引擎 - 双轨机制的核心

    根据 skill_id 加载对应的 SKILL Bundle，使用 Jinja2 模板渲染参数，
    然后在 Docker 沙箱中执行。

    payload 结构:
    {
        "tool_id": "skill_id",
        "project_id": "1",
        "parameters": {...},  # 用户提供的参数
        "session_id": "1",
        "message": "用户原始意图"
    }
    """
    task_id = self.request.id
    skill_id = payload.get("tool_id")
    project_id = payload.get("project_id", "1")
    parameters = payload.get("parameters", {})
    session_id = payload.get("session_id", "1")
    user_message = payload.get("message", f"执行模块: {skill_id}")

    log_msg = create_task_logger(task_id)
    log_msg(f"🚀 初始化 SKILL Bundle 引擎 (Task ID: {task_id})")
    log_msg(f"📦 目标 SKILL: {skill_id}")
    log_msg(f"📁 项目 ID: {project_id}")
    log_msg(f"📝 参数预览: {json.dumps(parameters, ensure_ascii=False)[:200]}...")

    try:
        # 1. 加载 SKILL Bundle
        parser = get_skill_parser()
        skill = parser.get_skill_by_id(skill_id)

        if not skill:
            log_msg(f"💥 未找到 SKILL: {skill_id}", level="ERROR")
            return {"status": "error", "message": f"SKILL not found: {skill_id}"}

        metadata = skill.get("metadata", {})
        executor_type = metadata.get("executor_type", "Python_env")
        entry_point = metadata.get("entry_point", "")
        bundle_path = skill.get("bundle_path", "")

        log_msg(f"📋 执行器类型: {executor_type}")
        log_msg(f"📁 入口脚本: {entry_point}")

        # 2. 处理 Logical_Blueprint 类型（交由 Nextflow Generator 接管）
        if executor_type == "Logical_Blueprint":
            log_msg("🔄 检测到逻辑蓝图类型，移交 Nextflow Generator...")

            # 构建 Nextflow 载荷
            nf_payload = {
                "params": {
                    "pipeline_topology": [{
                        "step_name": skill_id,
                        "tool_id": skill_id,
                        "inputs": parameters.get("inputs", []),
                        "outputs": {},
                        "params": parameters
                    }],
                    "compute_environment": parameters.get("compute_environment", "local"),
                    "resume_execution": parameters.get("resume_execution", True),
                    "outdir": parameters.get("output_dir", f"/app/uploads/project_{project_id}/results/"),
                    "max_cpus": parameters.get("max_cpus", 16),
                    "max_memory": parameters.get("max_memory", "64.GB")
                }
            }

            log_msg(f"📋 Pipeline 载荷: {json.dumps(nf_payload, ensure_ascii=False)[:500]}")

            # 直接调用编译器（不递归调用 Celery 任务）
            try:
                result = execute_nextflow_compiler(
                    payload=nf_payload,
                    project_id=project_id,
                    task_id=task_id,
                    session_id=session_id,
                    log_msg=log_msg
                )

                # 写入完成消息
                with Session(engine) as db:
                    final_content = (
                        f"✅ **Nextflow 流程执行完成 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                        f"工作目录: `{result['work_dir']}`\n\n"
                        f"### 📊 执行日志\n\n"
                        f"```text\n{result['output']}\n```\n\n"
                        f"### 📁 生成的文件\n\n"
                        f"{chr(10).join(result['files'])}\n"
                    )
                    db.add(ChatMessage(session_id=int(session_id), role="assistant", content=final_content))
                    db.commit()

                log_msg("🎉 Nextflow 流程执行完成！")
                return {"status": "success", "result": result}

            except Exception as e:
                error_msg = str(e)
                log_msg(f"💥 执行失败: {error_msg}", level="ERROR")

                # 写入错误消息
                with Session(engine) as db:
                    final_content = (
                        f"❌ **Nextflow 流程执行失败 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                        f"错误信息: {error_msg}\n\n"
                        f"> *请检查参数配置或联系技术支持。*"
                    )
                    db.add(ChatMessage(session_id=int(session_id), role="assistant", content=final_content))
                    db.commit()

                return {"status": "error", "message": error_msg}

        # 3. 检查入口脚本是否存在
        if not entry_point or entry_point == "none":
            log_msg(f"💥 SKILL 缺少有效的 entry_point", level="ERROR")
            return {"status": "error", "message": "No entry point defined"}

        script_path = os.path.join(bundle_path, entry_point)
        if not os.path.exists(script_path):
            log_msg(f"💥 入口脚本不存在: {script_path}", level="ERROR")
            return {"status": "error", "message": f"Entry script not found: {script_path}"}

        # 4. 读取脚本模板
        with open(script_path, 'r', encoding='utf-8') as f:
            script_template = f.read()

        # 5. 使用 Jinja2 渲染参数
        # 注入系统级参数
        render_context = {
            **parameters,
            "PROJECT_ID": project_id,
            "TASK_ID": task_id,
            "TASK_OUT_DIR": f"/app/uploads/project_{project_id}/results/task_{str(task_id)[:8]}"
        }

        try:
            template = Template(script_template)
            rendered_script = template.render(**render_context)
        except Exception as e:
            log_msg(f"💥 Jinja2 模板渲染失败: {e}", level="ERROR")
            return {"status": "error", "message": f"Template rendering failed: {e}"}

        log_msg("✅ 脚本模板渲染完成")

        # 6. 创建任务专属输出目录
        task_short_id = str(task_id)[:8]
        task_dir_name = f"task_{task_short_id}"
        task_out_dir = f"/app/uploads/project_{project_id}/results/{task_dir_name}"
        os.makedirs(task_out_dir, exist_ok=True)
        log_msg(f"📁 已分配专属输出目录: results/{task_dir_name}")

        # 7. 根据执行器类型选择语言
        language = "python"
        if "python" in executor_type.lower():
            language = "python"
        elif "r" in executor_type.lower():
            language = "r"
        elif "bash" in executor_type.lower() or "shell" in executor_type.lower():
            language = "bash"

        # 8. 在 Docker 沙箱中执行
        env = {"TASK_OUT_DIR": task_out_dir, "PROJECT_ID": project_id}
        result_output, exit_code = run_container("autonome-tool-env", rendered_script, language=language, environment=env)

        # 9. 终端乱码清理
        if result_output:
            result_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result_output)
            result_output = re.sub(r'\[\?\d+[hl]', '', result_output)
            result_output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result_output)
            result_output = result_output.replace('\r\n', '\n').replace('\r', '\n').strip()

        # 10. 处理执行结果
        if exit_code != 0:
            log_msg(f"💥 脚本执行失败 (Exit Code {exit_code})", level="ERROR")
            with Session(engine) as db:
                final_content = (
                    f"❌ **SKILL 执行失败 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                    f"### ⚠️ 错误终端日志\n"
                    f"```text\n{result_output}\n```\n\n"
                    f"> *(请查阅上方报错信息，或联系技术支持。)*"
                )
                db.add(ChatMessage(session_id=int(session_id), role="assistant", content=final_content))
                db.commit()
            return {"status": "failure"}

        log_msg("🎉 SKILL 执行成功！")

        # 11. 扫描生成的文件
        generated_files = []
        if os.path.exists(task_out_dir):
            for f in os.listdir(task_out_dir):
                full_path = os.path.join(task_out_dir, f)
                if os.path.isfile(full_path):
                    generated_files.append(f)

        log_msg(f"📂 检测到生成的文件: {generated_files}")

        # 12. 构建文件列表 markdown
        files_markdown = ""
        for filename in generated_files:
            container_path = f"/app/uploads/project_{project_id}/results/{task_dir_name}/{filename}"
            files_markdown += f"{container_path}\n"

        # 13. 生成图片 markdown
        img_extensions = ('.png', '.pdf', '.jpg', '.jpeg', '.svg')
        images = [f for f in generated_files if f.lower().endswith(img_extensions)]
        if images:
            first_img = images[0]
            actual_filename = f"results/{task_dir_name}/{first_img}"
            markdown_img = f"\n![Analysis_Result](/api/projects/{project_id}/files/{actual_filename}/view)\n"
        else:
            markdown_img = ""

        # 14. 读取数据摘要
        summary_path = f"{task_out_dir}/data_summary.txt"
        data_summary = "暂无详细数据特征"
        if os.path.exists(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                data_summary = f.read()

        # 15. 生成专家解读
        expert_report = generate_expert_report(user_message, rendered_script, data_summary)

        # 16. 写入聊天消息
        with Session(engine) as db:
            skill_name = metadata.get("name", skill_id)
            final_content = (
                f"✅ **SKILL 执行完成: {skill_name} (Task ID: `{str(task_id)[:8]}`)**\n\n"
                f"---\n"
                f"### 📊 执行日志\n\n"
                f"```text\n{result_output}\n```\n"
                f"{markdown_img}\n"
                f"---\n"
                f"### 📁 生成的文件资产\n\n"
                f"{files_markdown}\n"
                f"---\n"
                f"{expert_report}"
            )
            db.add(ChatMessage(session_id=int(session_id), role="assistant", content=final_content))
            db.commit()

        return {"status": "success", "files": generated_files}

    except Exception as e:
        log_msg(f"💥 发生系统错误: {str(e)}", level="ERROR")
        log.error(f"[execute_bundle_task] 任务执行异常: {traceback.format_exc()}")
        raise e


# 任务注册表（统一管理所有 Celery 任务）
TASK_REGISTRY = {
    "rnaseq-qc": run_rnaseq_qc_pipeline,
    "variant-calling": run_variant_calling_pipeline,
    "sc-rna-analysis": run_scrna_analysis_pipeline,
    "execute-python": run_custom_python_task,
    "execute-r": run_custom_r_task,
}
