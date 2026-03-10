#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nextflow 工业级分布式流水线生成与调度引擎 (nf_compiler)
功能: 接收 AI 架构师生成的结构化 JSON Payload，动态编译 Nextflow DSL2 脚本，并拉起底层计算集群。
"""

import json
import os
import sys
import argparse
import subprocess
import logging
from pathlib import Path

# 配置全局日志，方便在 Celery Worker 或后台追踪
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [NF_Compiler] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 尝试导入 Jinja2，用于高级模板渲染（确保环境中已安装 jinja2）
try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    logger.error("缺少依赖库 Jinja2。请执行: pip install jinja2")
    sys.exit(1)


class NextflowCompiler:
    def __init__(self, payload_path: str, bundle_dir: str):
        self.payload_path = Path(payload_path)
        self.bundle_dir = Path(bundle_dir)
        self.work_dir = self.payload_path.parent  # 通常在每次任务独立的沙箱或临时目录中执行
        self.payload = self._load_payload()
        
        # 初始化 Jinja2 环境，指向 bundle 下的 templates 目录
        self.jinja_env = Environment(
            loader=FileSystemLoader(self.bundle_dir / "templates"),
            trim_blocks=True,
            lstrip_blocks=True
        )

    def _load_payload(self) -> dict:
        """加载并验证前端传入的 JSON Payload"""
        try:
            with open(self.payload_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"成功加载任务 Payload: {self.payload_path}")
            return data
        except Exception as e:
            logger.error(f"解析 Payload 失败: {str(e)}")
            sys.exit(1)

    def generate_config(self):
        """生成 nextflow.config 配置文件，处理计算资源和异构集群调度"""
        params = self.payload.get("params", {})
        compute_env = params.get("compute_environment", "local")
        max_cpus = params.get("max_cpus", 16)
        max_memory = params.get("max_memory", "64.GB")
        outdir = params.get("outdir", str(self.work_dir / "results"))

        config_content = f"""
        // 自动生成的 Nextflow 全局配置文件
        params {{
            outdir = '{outdir}'
            max_cpus = {max_cpus}
            max_memory = '{max_memory}'
        }}

        profiles {{
            local {{
                process.executor = 'local'
            }}
            slurm {{
                process.executor = 'slurm'
                process.queue = 'compute'
                process.memory = '{max_memory}'
                process.cpus = {max_cpus}
            }}
            k8s {{
                process.executor = 'k8s'
                k8s.computeResourceType = 'Job'
            }}
        }}

        // 默认激活前端选择的环境
        process.profile = '{compute_env}'
        
        // 开启执行报告和资源消耗追踪
        timeline.enabled = true
        report.enabled = true
        """
        config_file = self.work_dir / "nextflow.config"
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)
        logger.info(f"生成配置文件成功: {config_file}")

    def generate_main_script(self):
        """
        核心编排逻辑：将 JSON 拓扑降维编译为 main.nf
        这里展示如何基于 payload 动态组装 workflow 和 processes
        """
        params = self.payload.get("params", {})
        topology = params.get("pipeline_topology", [])
        
        if not topology:
            logger.error("流水线拓扑 (pipeline_topology) 为空，无法生成脚本！")
            sys.exit(1)

        # 1. 收集需要引入的 Process 模块
        # 假设我们将生信工具的 nf 定义放在 templates/process_blocks 下
        includes = []
        for step in topology:
            tool_id = step.get("tool_id")
            step_name = step.get("step_name")
            # 简化演示：动态生成 include 语句 (实际生产中需确保 process_blocks 下存在这些 .nf)
            includes.append(f"include {{ {tool_id.upper()} as {step_name.upper()} }} from './process_blocks/{tool_id}.nf'")

        # 2. 动态构建 workflow 连线逻辑
        workflow_lines = ["workflow {"]
        
        for step in topology:
            step_name = step.get("step_name").upper()
            inputs = step.get("inputs", [])
            
            # 解析该步骤的输入。
            # 如果输入是 raw_data（外部文件），则创建 Channel.fromPath
            # 如果输入是 upstream_step（上游输出），则直接引用上游的 out channel
            parsed_inputs = []
            for inp in inputs:
                if inp.startswith("file://"):
                    path = inp.replace("file://", "")
                    # 处理 FastQC 常见的双端匹配模式
                    if "fastq" in path or "fq" in path:
                         parsed_inputs.append(f"Channel.fromFilePairs('{path}')")
                    else:
                         parsed_inputs.append(f"Channel.fromPath('{path}')")
                elif inp.startswith("channel://"):
                    channel_name = inp.replace("channel://", "")
                    parsed_inputs.append(channel_name)
                else:
                    parsed_inputs.append(f"'{inp}'") # 作为普通值传入
            
            # 组装 DSL2 函数调用: MULTIQC( FASTQC.out.mix().collect() )
            input_str = ", ".join(parsed_inputs)
            workflow_lines.append(f"    {step_name}( {input_str} )")

        workflow_lines.append("}")

        # 3. 拼装为完整的 main.nf 文件
        main_nf_content = "\n".join(includes) + "\n\n" + "\n".join(workflow_lines)
        
        main_file = self.work_dir / "main.nf"
        with open(main_file, "w", encoding="utf-8") as f:
            f.write(main_nf_content)
            
        logger.info(f"生成核心流水线脚本成功: {main_file}")

    def execute_pipeline(self):
        """拉起底层 Nextflow 进程执行计算任务"""
        params = self.payload.get("params", {})
        resume = params.get("resume_execution", True)
        
        cmd = ["nextflow", "run", "main.nf"]
        
        # 处理断点续跑
        if resume:
            cmd.append("-resume")
            logger.info("已启用断点续跑 (-resume) 机制")

        logger.info(f"即将执行命令: {' '.join(cmd)}")
        
        # 启动子进程，并将输出实时打到 stdout（供 Celery/WebSocket 截获推送到前端）
        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(self.work_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in process.stdout:
                print(line.strip())  # 实时打印执行进度
                
            process.wait()
            if process.returncode != 0:
                logger.error(f"Nextflow 任务执行失败，退出码: {process.returncode}")
                sys.exit(process.returncode)
            else:
                logger.info("Nextflow 任务完美执行完毕！")
                
        except Exception as e:
            logger.error(f"启动 Nextflow 进程时发生异常: {str(e)}")
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonome Nextflow Compiler")
    parser.add_argument("--payload", required=True, help="包含完整执行指令和拓扑图的 JSON 文件路径")
    parser.add_argument("--bundle_dir", required=True, help="Nextflow Generator SKILL 所在的物理根目录")
    parser.add_argument("--compile-only", action="store_true", help="仅生成脚本，不执行 Nextflow")

    args = parser.parse_args()

    # 初始化并启动编译与执行流程
    compiler = NextflowCompiler(payload_path=args.payload, bundle_dir=args.bundle_dir)
    compiler.generate_config()
    compiler.generate_main_script()

    if not args.compile_only:
        compiler.execute_pipeline()
    else:
        logger.info("📋 仅编译模式：已生成 main.nf 和 nextflow.config，跳过执行")
        logger.info(f"📁 输出目录: {compiler.work_dir}")