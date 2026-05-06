"""
SKILL Bundle 执行任务

包含 SKILL Bundle 执行引擎和 Nextflow 编译器
"""

import os
import re
import json
import time
import shutil
import traceback
import subprocess
from datetime import datetime

from celery import Celery
from jinja2 import Template
from sqlmodel import Session, select

from app.core.database import engine
from app.core.logger import log
from app.core.skill_parser import get_skill_parser
from app.models.domain import SkillExecutionHistory, SkillAsset, User
from app.services.task_logger import create_task_logger, safe_add_chat_message, redis_client
from app.utils.command_builder import build_command_line_args
from app.tools.bio_tools import run_container, run_nextflow_in_sandbox

# 语义化目录命名和元数据注入
from app.utils.semantic_naming import generate_semantic_dir_name
from app.utils.task_metadata import inject_metadata_files


def register_skill_bundle_tasks(celery_app: Celery):
    """
    注册 SKILL Bundle 执行任务到 Celery

    Args:
        celery_app: Celery 应用实例
    """

    def execute_nextflow_compiler(
        payload: dict,
        project_id: str,
        task_id: str,
        session_id: str,
        log_msg: callable,
        skill_parameters: dict = None
    ) -> dict:
        """
        执行 Nextflow 编译器 - 将逻辑蓝图编译为可执行的 Nextflow 流程

        流程:
        1. 在 API 容器中生成 Nextflow 脚本（需要访问 skills 目录）
        2. 在沙箱中执行 Nextflow（使用 conda 环境）

        Args:
            payload: Nextflow 载荷
            project_id: 项目 ID
            task_id: 任务 ID
            session_id: 会话 ID
            log_msg: 日志函数
            skill_parameters: 技能参数

        Returns:
            执行结果字典
        """
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

        # 2. 创建任务专属工作目录（使用语义化命名）
        task_short_id = str(task_id)[:8]

        # ✨ 优先从 payload 获取 AI 生成的语义名
        semantic_name = payload.get("semantic_folder_name")
        if not semantic_name and skill_parameters:
            semantic_name = skill_parameters.get("semantic_folder_name")

        # 生成完整的语义化目录名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if semantic_name:
            # 清理语义名（确保只包含合法字符）
            semantic_name = re.sub(r"[^a-z0-9_]", "", semantic_name.lower())[:30]
            full_dir_name = f"{timestamp}_{semantic_name}_{task_short_id}"
        else:
            full_dir_name = f"{timestamp}_pipeline_{task_short_id}"

        task_work_dir = f"/workspace/project_{project_id}/results/{full_dir_name}"
        os.makedirs(task_work_dir, exist_ok=True)
        log_msg(f"📁 语义化工作目录: {full_dir_name}")

        # 3. 创建 payload JSON 文件
        payload_file = os.path.join(task_work_dir, "pipeline_payload.json")
        with open(payload_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log_msg(f"📋 Payload 文件已创建: pipeline_payload.json")

        # 4. 在 API 容器中执行 nf_compiler.py（生成脚本）
        cmd = [
            "python", nf_compiler_script,
            "--payload", payload_file,
            "--bundle_dir", bundle_path,
            "--compile-only"
        ]

        log_msg("🚀 启动 Nextflow 编译器...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=task_work_dir,
                env={**os.environ, "TASK_OUT_DIR": task_work_dir, "PROJECT_ID": project_id}
            )

            result_output = result.stdout
            if result.stderr:
                result_output += "\n" + result.stderr

            exit_code = result.returncode

        except subprocess.TimeoutExpired:
            raise RuntimeError("Nextflow 编译器执行超时 (>5分钟)")
        except Exception as e:
            raise RuntimeError(f"执行编译器失败: {str(e)}")

        # 5. 清理终端乱码并记录日志
        if result_output:
            result_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result_output)
            result_output = re.sub(r'\[\?\d+[hl]', '', result_output)
            result_output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result_output)
            result_output = result_output.replace('\r\n', '\n').replace('\r', '\n').strip()

        for line in result_output.split('\n'):
            if line.strip():
                log_msg(f"  [NF] {line}")

        if exit_code != 0:
            raise RuntimeError(f"Nextflow 编译失败 (Exit: {exit_code})")

        # 6. 扫描生成的文件
        generated_files = []
        process_blocks_files = []
        if os.path.exists(task_work_dir):
            for f in os.listdir(task_work_dir):
                full_path = os.path.join(task_work_dir, f)
                if os.path.isfile(full_path):
                    generated_files.append(f)
            # 检查 process_blocks 目录
            pb_dir = os.path.join(task_work_dir, "process_blocks")
            if os.path.exists(pb_dir):
                for f in os.listdir(pb_dir):
                    process_blocks_files.append(f"process_blocks/{f}")

        all_files = generated_files + process_blocks_files
        log_msg(f"📂 生成的文件: {all_files}")

        # 7. 检查是否生成了 main.nf
        main_nf_path = os.path.join(task_work_dir, "main.nf")
        if not os.path.exists(main_nf_path):
            raise RuntimeError("main.nf 未生成")

        log_msg("✅ Nextflow 脚本编译完成！")

        # 8. 在沙箱中执行 Nextflow（使用 conda 环境）
        log_msg("🚀 在沙箱中启动 Nextflow 执行...")

        # 提取 Nextflow 参数
        params_source = skill_parameters or payload.get("params", {}).get("pipeline_topology", [{}])[0].get("params", {})

        # 将相对路径转换为绝对路径
        project_root = f"/workspace/project_{project_id}"

        # 支持 sample_sheet 参数（新参数体系）
        sample_sheet = params_source.get("sample_sheet")
        output_dir = params_source.get("output_dir", "./qc_reports")

        if sample_sheet:
            log_msg(f"📋 使用 sample_sheet 参数: {sample_sheet}")

            if not sample_sheet.startswith("/"):
                sample_sheet = os.path.join(project_root, sample_sheet)

            if not os.path.exists(sample_sheet):
                raise RuntimeError(f"Sample Sheet 文件不存在: {sample_sheet}")

            # 复制 sample_sheet 到工作目录
            dest_sample_sheet = os.path.join(task_work_dir, "sample_sheet.tsv")
            shutil.copy(sample_sheet, dest_sample_sheet)
            log_msg(f"📄 已复制 sample_sheet 到工作目录: {dest_sample_sheet}")

            if not output_dir.startswith("/"):
                output_dir = os.path.join(task_work_dir, output_dir)

            max_memory = params_source.get("max_memory", 16)
            ncpus = params_source.get("ncpus", 4)

            nf_params = {
                "sample_sheet": "./sample_sheet.tsv",
                "output_dir": output_dir,
                "threads_per_sample": params_source.get("threads_per_sample", 4),
                "max_memory": max_memory,
                "ncpus": ncpus
            }
        else:
            # 旧参数体系：使用 fastq_dir（向后兼容）
            log_msg("📋 使用 fastq_dir 参数（旧参数体系）")

            fastq_dir = params_source.get("fastq_dir", "./fastq")
            if not fastq_dir.startswith("/"):
                fastq_dir = os.path.join(project_root, fastq_dir)

            if not output_dir.startswith("/"):
                output_dir = os.path.join(task_work_dir, output_dir)

            max_memory = params_source.get("max_memory", 16)
            ncpus = params_source.get("ncpus", 4)

            nf_params = {
                "fastq_dir": fastq_dir,
                "is_paired_end": params_source.get("is_paired_end", True),
                "file_pattern": params_source.get("file_pattern", "*_{1,2}.fastq.gz"),
                "threads_per_sample": params_source.get("threads_per_sample", 4),
                "outdir": output_dir,
                "max_memory": max_memory,
                "ncpus": ncpus
            }

        log_msg(f"📋 Nextflow 参数: {json.dumps(nf_params, ensure_ascii=False)}")

        # 检查执行模式
        execution_mode = payload.get("execution_mode", "docker")
        log_msg(f"📋 执行模式: {execution_mode}")

        # 执行 Nextflow
        if execution_mode == "native":
            nextflow_path = shutil.which("nextflow")

            if nextflow_path:
                log_msg(f"🚀 使用宿主机 Nextflow 原生执行: {nextflow_path}")

                cmd_args = []
                for k, v in nf_params.items():
                    if isinstance(v, bool):
                        if v:
                            cmd_args.append(f"--{k}")
                    elif isinstance(v, str):
                        cmd_args.extend([f"--{k}", v])
                    else:
                        cmd_args.extend([f"--{k}", str(v)])

                start_time = time.time()
                try:
                    cmd = [nextflow_path, "run", os.path.join(task_work_dir, "main.nf")] + cmd_args + ["-resume"]
                    log_msg(f"📋 执行命令: {' '.join(cmd)}")

                    result_proc = subprocess.run(
                        cmd,
                        cwd=task_work_dir,
                        capture_output=True,
                        text=True,
                        timeout=3600  # 1 小时超时
                    )

                    nf_output = result_proc.stdout + "\n" + result_proc.stderr
                    nf_exit_code = result_proc.returncode
                    elapsed = time.time() - start_time
                    log_msg(f"⏱️ Nextflow 执行耗时: {elapsed:.1f} 秒")

                except subprocess.TimeoutExpired:
                    nf_output = "执行超时"
                    nf_exit_code = 1
                except Exception as e:
                    nf_output = f"执行异常: {str(e)}"
                    nf_exit_code = 1
            else:
                log_msg("⚠️ 宿主机未安装 Nextflow，降级到 Docker 沙箱执行")
                nf_output, nf_exit_code = run_nextflow_in_sandbox(
                    work_dir=task_work_dir,
                    params=nf_params,
                    log_callback=log_msg
                )
        else:
            # Docker 沙箱执行（默认）
            nf_output, nf_exit_code = run_nextflow_in_sandbox(
                work_dir=task_work_dir,
                params=nf_params,
                log_callback=log_msg
            )

        if nf_exit_code != 0:
            raise RuntimeError(f"Nextflow 执行失败 (Exit: {nf_exit_code})")

        log_msg("🎉 Nextflow 流程执行完成！")

        # 9. 扫描最终生成的文件
        final_files = []
        if os.path.exists(task_work_dir):
            for root, dirs, files in os.walk(task_work_dir):
                for f in files:
                    rel_path = os.path.relpath(os.path.join(root, f), task_work_dir)
                    final_files.append(rel_path)

        log_msg(f"📂 最终生成的文件: {final_files[:20]}...")

        return {
            "work_dir": task_work_dir,
            "output": result_output + "\n" + nf_output,
            "files": final_files
        }

    @celery_app.task(bind=True)
    def execute_bundle_task(self, payload: dict):
        """
        SKILL Bundle 执行引擎 - 双轨机制的核心

        根据 skill_id 加载对应的 SKILL Bundle，使用 Jinja2 模板渲染参数，
        然后在 Docker 沙箱中执行。

        Args:
            payload: 任务载荷字典，包含:
                - tool_id: skill_id
                - project_id: 项目 ID
                - parameters: 用户提供的参数
                - session_id: 会话 ID
                - message: 用户原始意图
                - task_summary: AI 生成的任务概述
                - user_id: 用户 ID

        Returns:
            {"status": "success", "files": [...]} 或抛出异常
        """
        task_id = self.request.id
        skill_id = payload.get("tool_id")
        project_id = payload.get("project_id", "1")
        parameters = payload.get("parameters", {})
        session_id = payload.get("session_id", "1")
        user_message = payload.get("message", f"执行模块: {skill_id}")
        task_summary = payload.get("task_summary")
        user_id = payload.get("user_id", 1)

        log_msg, _ = create_task_logger(task_id)
        log_msg(f"🚀 初始化 SKILL Bundle 引擎 (Task ID: {task_id})")
        log_msg(f"📦 目标 SKILL: {skill_id}")
        log_msg(f"📁 项目 ID: {project_id}")
        log_msg(f"📝 参数预览: {json.dumps(parameters, ensure_ascii=False)[:200]}...")

        # 创建执行历史记录
        history_id = None
        try:
            with Session(engine) as db:
                history = SkillExecutionHistory(
                    skill_id=skill_id,
                    skill_name=skill_id,
                    user_id=user_id,
                    project_id=project_id,
                    session_id=session_id,
                    parameters=parameters,
                    status="PENDING"
                )
                db.add(history)
                db.commit()
                db.refresh(history)
                history_id = history.id
                log_msg(f"📝 已创建执行历史记录: ID={history_id}")
        except Exception as e:
            log_msg(f"⚠️ 创建执行历史记录失败: {e}", level="WARNING")

        # 加载 SKILL
        parser = get_skill_parser()
        skill = parser.get_skill_by_id(skill_id)

        if not skill:
            log_msg(f"💥 文件系统中未找到 SKILL: {skill_id}", level="ERROR")
            return {"status": "error", "message": f"SKILL not found: {skill_id}"}

        metadata = skill.get("metadata", {})
        skill_name = metadata.get("name", skill_id)
        skill_category = metadata.get("category_name", "未分类")
        skill_subcategory = metadata.get("subcategory_name", "")
        skill_version = metadata.get("version", "1.0.0")
        executor_type = metadata.get("executor_type", "Python_env")

        # 发送"正在执行"消息
        try:
            params_table_rows = []
            param_count = 0
            for k, v in parameters.items():
                if k not in ["session_id", "project_id", "code", "message", "task_name"]:
                    value_str = str(v) if v is not None else ""
                    if len(value_str) > 100:
                        value_str = value_str[:100] + "..."
                    params_table_rows.append(f"| {k} | `{value_str}` |")
                    param_count += 1
                    if param_count >= 15:
                        params_table_rows.append(f"| ... | *(还有 {len(parameters) - 15} 个参数)* |")
                        break

            params_table = "| 参数 | 值 |\n|------|----|\n" + "\n".join(params_table_rows) if params_table_rows else "| 使用默认参数配置 |"

            progress_message = (
                f"⏳ **正在执行 SKILL**\n\n"
                f"---\n\n"
                f"### 📦 SKILL 信息\n\n"
                f"| 属性 | 值 |\n"
                f"|------|----|\n"
                f"| **名称** | {skill_name} |\n"
                f"| **ID** | `{skill_id}` |\n"
                f"| **版本** | {skill_version} |\n"
                f"| **分类** | {skill_category}" + (f" / {skill_subcategory}" if skill_subcategory else "") + " |\n"
                f"| **执行器** | {executor_type} |\n\n"
                f"---\n\n"
                f"### 📋 参数配置\n\n"
                f"{params_table}\n\n"
                f"---\n\n"
                f"### 📊 任务信息\n\n"
                f"| 属性 | 值 |\n"
                f"|------|----|\n"
                f"| **Task ID** | `{str(task_id)}` |\n"
                f"| **项目 ID** | `{project_id}` |\n"
                f"| **会话 ID** | `{session_id}` |\n\n"
                f"> *任务正在后台执行，完成后将自动更新结果...*"
            )

            safe_add_chat_message(session_id, "assistant", progress_message)
            log_msg(f"📢 已发送执行开始消息到聊天")
        except Exception as e:
            log_msg(f"⚠️ 发送执行开始消息失败: {e}", level="WARNING")

        try:
            # 获取 SKILL 资源
            entry_point = metadata.get("entry_point", "")
            bundle_path = skill.get("bundle_path", "")
            script_code = skill.get("script_code", "")
            skill_source = skill.get("source", "filesystem")
            parameters_schema = skill.get("parameters_schema", {})

            log_msg(f"📋 执行器类型: {executor_type}")
            log_msg(f"📋 SKILL 来源: {skill_source}")

            # 处理 Logical_Blueprint 类型
            if executor_type == "Logical_Blueprint":
                log_msg("🔄 检测到逻辑蓝图类型，移交 Nextflow Generator...")

                # 检查执行模式
                execution_mode = "docker"
                try:
                    with Session(engine) as db:
                        skill_record = db.exec(
                            select(SkillAsset).where(SkillAsset.skill_id == skill_id)
                        ).first()
                        if skill_record and skill_record.execution_mode == "native":
                            from app.services.native_executor import is_official_skill
                            if is_official_skill(skill_id, skill_record.owner_id):
                                execution_mode = "native"
                                log_msg(f"✅ 技能 {skill_id} 使用原生执行模式")
                            else:
                                log_msg(f"⚠️ 非官方技能 {skill_id} 尝试使用原生执行，已降级为 Docker")
                except Exception as e:
                    log_msg(f"⚠️ 获取执行模式失败: {e}，使用默认 Docker 模式")

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
                        "outdir": parameters.get("output_dir", f"/workspace/project_{project_id}/results/"),
                        "max_cpus": parameters.get("ncpus", 16),
                        "max_memory": f"{parameters.get('max_memory', 128)}.GB"
                    },
                    "execution_mode": execution_mode
                }

                log_msg(f"📋 Pipeline 载荷: {json.dumps(nf_payload, ensure_ascii=False)[:500]}")

                try:
                    result = execute_nextflow_compiler(
                        payload=nf_payload,
                        project_id=project_id,
                        task_id=task_id,
                        session_id=session_id,
                        log_msg=log_msg,
                        skill_parameters=parameters
                    )

                    # 更新执行历史记录为成功状态
                    if history_id:
                        try:
                            with Session(engine) as db:
                                history_record = db.get(SkillExecutionHistory, history_id)
                                if history_record:
                                    history_record.skill_name = skill_name
                                    history_record.status = "SUCCESS"
                                    history_record.result_summary = f"成功生成 {len(result.get('files', []))} 个文件"
                                    db.commit()
                                    log_msg(f"✅ 已更新执行历史记录: ID={history_id}, 状态=SUCCESS")
                        except Exception as e:
                            log_msg(f"⚠️ 更新执行历史记录失败: {e}", level="WARNING")

                    final_content = (
                        f"✅ **Nextflow 流程执行完成 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                        f"工作目录: `{result['work_dir']}`\n\n"
                        f"### 📊 执行日志\n\n"
                        f"```text\n{result['output'][-3000:]}\n```\n\n"
                        f"### 📁 生成的文件\n\n"
                        f"{chr(10).join(f'- {f}' for f in result['files'][:30])}\n"
                    )
                    safe_add_chat_message(session_id, "assistant", final_content)

                    log_msg("🎉 Nextflow 流程执行完成！")
                    return {"status": "success", "result": result}

                except Exception as e:
                    error_msg = str(e)
                    log_msg(f"💥 执行失败: {error_msg}", level="ERROR")

                    if history_id:
                        try:
                            with Session(engine) as db:
                                history_record = db.get(SkillExecutionHistory, history_id)
                                if history_record:
                                    history_record.skill_name = skill_name
                                    history_record.status = "FAILURE"
                                    history_record.result_summary = f"执行失败: {error_msg[:200]}"
                                    db.commit()
                                    log_msg(f"✅ 已更新执行历史记录: ID={history_id}, 状态=FAILURE")
                        except Exception as ex:
                            log_msg(f"⚠️ 更新执行历史记录失败: {ex}", level="WARNING")

                    final_content = (
                        f"❌ **Nextflow 流程执行失败 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                        f"错误信息: {error_msg}\n\n"
                        f"> *请检查参数配置或联系技术支持。*"
                    )
                    safe_add_chat_message(session_id, "assistant", final_content)

                    return {"status": "error", "message": error_msg}

            # 获取脚本模板
            script_template = ""
            if skill_source == "database" and script_code:
                script_template = script_code
                log_msg(f"✅ 已加载数据库脚本代码 ({len(script_code)} 字符)")
            else:
                if not entry_point or entry_point == "none":
                    log_msg(f"💥 SKILL 缺少有效的 entry_point", level="ERROR")
                    return {"status": "error", "message": "No entry point defined"}

                script_path = os.path.join(bundle_path, entry_point)
                if not os.path.exists(script_path):
                    log_msg(f"💥 入口脚本不存在: {script_path}", level="ERROR")
                    return {"status": "error", "message": f"Entry script not found: {script_path}"}

                with open(script_path, 'r', encoding='utf-8') as f:
                    script_template = f.read()
                log_msg(f"✅ 已加载文件系统脚本: {entry_point}")

            # ==========================================
            # 语义化目录命名 (Semantic Directory Naming)
            # ==========================================
            # 格式: YYYYMMDD_HHMMSS_ALIAS_SHORTID
            # 多级语义来源 fallback，确保命名有意义

            # 获取用户提供的别名
            raw_task_alias = parameters.get("task_alias") or parameters.get("task_name")
            user_message_for_alias = parameters.get("message", "") or user_message

            # 获取技能元数据中的分类信息（用于多级 fallback）
            skill_category_name = metadata.get("category_name", "")
            skill_subcategory_name = metadata.get("subcategory_name", "")
            skill_description = metadata.get("description", "")

            # 判断别名是否有意义（不是随机字符串）
            alias_is_meaningful = False
            if raw_task_alias and len(raw_task_alias) >= 4:
                alias_lower = raw_task_alias.lower()
                has_vowel = any(c in alias_lower for c in 'aeiou')
                has_common_word = any(word in alias_lower for word in ['qc', 'seq', 'rna', 'dna', 'fastq', 'analysis', 'data', 'sample', 'quality', 'control', 'gene', 'protein', 'align', 'count', 'diff', 'express'])
                alias_is_meaningful = has_vowel or has_common_word

            # ✨ 优先从参数中获取 AI 生成的语义名
            ai_semantic_name = parameters.get("semantic_folder_name")

            # 确定最终的语义别名（多级 fallback）
            if ai_semantic_name:
                # 优先级1：AI 生成的语义名
                final_alias = ai_semantic_name
                log_msg(f"🎯 使用 AI 生成的语义名: {final_alias}")
            elif alias_is_meaningful:
                # 优先级2：用户提供了有意义的别名
                final_alias = raw_task_alias
            elif user_message_for_alias and len(user_message_for_alias) > 10:
                # 优先级3：从用户消息生成语义别名
                final_alias = None  # 让 generate_semantic_dir_name 从消息生成
            else:
                # 优先级4-7：使用 extract_semantic_from_metadata 多源提取
                from app.utils.semantic_naming import extract_semantic_from_metadata
                final_alias = extract_semantic_from_metadata(
                    skill_name=skill_name,
                    skill_id=skill_id,
                    category_name=skill_category_name,
                    subcategory_name=skill_subcategory_name,
                    description=skill_description,
                )
                log_msg(f"🔍 从元数据提取语义别名: {final_alias}")

            semantic_dir_name = generate_semantic_dir_name(
                skill_id=skill_id,
                task_id=task_id,
                task_alias=final_alias,
                user_message=user_message_for_alias if not final_alias else None,
                timestamp=datetime.now(),
            )

            task_out_dir = f"/workspace/project_{project_id}/results/{semantic_dir_name}"

            log_msg(f"📁 语义化输出目录: {semantic_dir_name}")

            # 文件路径参数转换
            schema_props = parameters_schema.get("properties", {})
            project_base_dir = f"/workspace/project_{project_id}"

            processed_params = {}
            for k, v in parameters.items():
                if v is None or v == "":
                    processed_params[k] = v
                    continue

                param_def = schema_props.get(k, {})
                param_format_raw = param_def.get("format", "") if isinstance(param_def, dict) else ""
                param_format = param_format_raw.lower().replace("-", "") if param_format_raw else ""

                if param_format in ["filepath", "directorypath"]:
                    if isinstance(v, str) and not v.startswith("/"):
                        new_path = f"{project_base_dir}/{v}"
                        processed_params[k] = new_path
                    else:
                        processed_params[k] = v
                else:
                    processed_params[k] = v

            parameters = processed_params

            # 构建渲染上下文
            render_context = {
                **parameters,
                "PROJECT_ID": project_id,
                "TASK_ID": task_id,
                "TASK_OUT_DIR": task_out_dir,
                "output_dir": task_out_dir
            }

            try:
                template = Template(script_template)
                rendered_script = template.render(**render_context)
            except Exception as e:
                log_msg(f"💥 Jinja2 模板渲染失败: {e}", level="ERROR")
                return {"status": "error", "message": f"Template rendering failed: {e}"}

            log_msg("✅ 脚本模板渲染完成")

            # 根据执行器类型选择语言
            language = "python"
            if "python" in executor_type.lower():
                language = "python"
            elif "r" in executor_type.lower():
                language = "r"
            elif "bash" in executor_type.lower() or "shell" in executor_type.lower():
                language = "bash"

            # 创建输出目录
            os.makedirs(task_out_dir, exist_ok=True)
            log_msg(f"📁 已分配专属输出目录: results/{semantic_dir_name}")

            # 检测是否支持命令行参数
            uses_cmdline_args = (
                "argparse" in rendered_script or
                "ArgumentParser" in rendered_script or
                "optparse" in rendered_script or
                "make_option" in rendered_script or
                "commandArgs" in rendered_script or
                "parse_args" in rendered_script
            )

            use_cli_mode = metadata.get("use_cli_args", True)
            script_path_for_cli = ""

            if use_cli_mode and uses_cmdline_args:
                log_msg("🔧 使用命令行参数模式执行")
                cli_args = build_command_line_args(parameters, schema_props, language)
                log_msg(f"🔧 命令行参数: {' '.join(cli_args)}")

                if skill_source == "filesystem":
                    host_upload_dir = os.environ.get("HOST_UPLOAD_DIR", "/workspace")

                    if bundle_path.startswith(host_upload_dir) or bundle_path.startswith("/workspace"):
                        script_path_for_cli = bundle_path.replace(host_upload_dir, "/workspace")
                        if entry_point:
                            script_path_for_cli = os.path.join(script_path_for_cli, entry_point)
                    else:
                        src_script = os.path.join(bundle_path, entry_point) if entry_point else bundle_path
                        script_path_for_cli = os.path.join(task_out_dir, "skill_script.r" if language == "r" else "skill_script.py")
                        shutil.copy(src_script, script_path_for_cli)
                        log_msg(f"📄 已复制脚本到: {script_path_for_cli}")
                else:
                    script_filename = "skill_script.r" if language == "r" else "skill_script.py"
                    script_path_for_cli = os.path.join(task_out_dir, script_filename)

                    with open(script_path_for_cli, 'w', encoding='utf-8') as f:
                        f.write(rendered_script)

                    log_msg(f"📄 已写入脚本到: {script_path_for_cli}")

                if script_path_for_cli:
                    if language == "python":
                        full_cmd = ["python", script_path_for_cli] + cli_args
                    elif language == "r":
                        full_cmd = ["Rscript", script_path_for_cli] + cli_args
                    else:
                        full_cmd = ["python", script_path_for_cli] + cli_args

                    log_msg(f"🔧 完整执行命令: {' '.join(full_cmd)}")

                    env = {"TASK_OUT_DIR": task_out_dir, "PROJECT_ID": project_id}
                    start_time = time.time()
                    result_output, exit_code, _ = run_container(
                        "autonome-tool-env",
                        full_cmd,
                        language=language,
                        environment=env,
                        cli_mode=True
                    )
                    elapsed_time = time.time() - start_time
                else:
                    use_cli_mode = False

            if not use_cli_mode or not uses_cmdline_args:
                log_msg("📝 使用 Jinja2 渲染模式执行")
                log_msg(f"⏳ 执行中... ")

                env = {"TASK_OUT_DIR": task_out_dir, "PROJECT_ID": project_id}
                start_time = time.time()
                result_output, exit_code, _ = run_container("autonome-tool-env", rendered_script, language=language, environment=env)
                elapsed_time = time.time() - start_time

            log_msg(f"⏱️ 执行耗时: {elapsed_time:.1f} 秒")
            log_msg(f"🔢 退出码: {exit_code}")

            # 清理终端乱码
            if result_output:
                result_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result_output)
                result_output = re.sub(r'\[\?\d+[hl]', '', result_output)
                result_output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', result_output)
                result_output = result_output.replace('\r\n', '\n').replace('\r', '\n').strip()

                output_lines = result_output.split('\n')
                log_msg(f"📤 沙箱输出 ({len(output_lines)} 行):")
                if len(output_lines) > 20:
                    for line in output_lines[:10]:
                        log_msg(f"   {line[:100]}")
                    log_msg(f"   ... (中间省略 {len(output_lines) - 20} 行) ...")
                    for line in output_lines[-10:]:
                        log_msg(f"   {line[:100]}")
                else:
                    for line in output_lines[:15]:
                        log_msg(f"   {line[:100]}")

            # 处理执行失败
            if exit_code != 0:
                log_msg(f"💥 脚本执行失败 (Exit Code {exit_code})", level="ERROR")

                is_timeout = "执行超时" in result_output or "timeout" in result_output.lower()

                if history_id:
                    try:
                        with Session(engine) as db:
                            history_record = db.get(SkillExecutionHistory, history_id)
                            if history_record:
                                history_record.skill_name = skill_name
                                history_record.status = "FAILURE"
                                history_record.execution_time = elapsed_time
                                history_record.result_summary = f"执行失败: Exit Code {exit_code}"
                                db.commit()
                                log_msg(f"✅ 已更新执行历史记录: ID={history_id}, 状态=FAILURE")
                    except Exception as e:
                        log_msg(f"⚠️ 更新执行历史记录失败: {e}", level="WARNING")

                if is_timeout:
                    final_content = (
                        f"<!-- TASK_ID: {task_id} -->\n"
                        f"<!-- TASK_NAME: {semantic_dir_name} -->\n"
                        f"⏰ **SKILL 执行超时 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                        f"SKILL: **{skill_name}**\n\n"
                        f"代码在沙箱中运行超过了时间限制。\n\n"
                        f"### 💡 解决建议\n"
                        f"- 减少输入数据量或使用采样数据\n"
                        f"- 检查 SKILL 参数配置\n"
                        f"- 联系 SKILL 作者或技术支持\n"
                    )
                else:
                    final_content = (
                        f"<!-- TASK_ID: {task_id} -->\n"
                        f"<!-- TASK_NAME: {semantic_dir_name} -->\n"
                        f"❌ **SKILL 执行失败 (Task ID: `{str(task_id)[:8]}`)**\n\n"
                        f"### ⚠️ 错误终端日志\n"
                        f"```text\n{result_output}\n```\n\n"
                        f"> *(请查阅上方报错信息，或联系技术支持。)*"
                    )

                safe_add_chat_message(session_id, "assistant", final_content)
                raise Exception(f"SKILL 执行失败: {skill_name}")

            log_msg("🎉 SKILL 执行成功！")

            # 扫描生成的文件
            generated_files = []
            if os.path.exists(task_out_dir):
                for f in os.listdir(task_out_dir):
                    full_path = os.path.join(task_out_dir, f)
                    if os.path.isfile(full_path):
                        generated_files.append(f)

            log_msg(f"📂 检测到生成的文件: {generated_files}")

            # ==========================================
            # 元数据烙印 (Metadata Injection)
            # ==========================================
            # 在输出目录中自动生成 run_parameters.tsv 和 README_autonome.md
            # 确保分析结果具备完全可复现性
            try:
                metadata_files = inject_metadata_files(
                    output_dir=task_out_dir,
                    task_id=task_id,
                    skill_id=skill_id,
                    skill_name=skill_name,
                    user_message=user_message,
                    parameters=parameters,
                    docker_image="autonome-tool-env",
                    entry_point=entry_point or "scripts/main.py",
                    timestamp=datetime.now(),
                    semantic_dir_name=semantic_dir_name,
                    project_id=project_id,
                    executor_type=executor_type,
                    duration=elapsed_time,
                    skill_metadata={
                        "skill_id": skill_id,
                        "name": skill_name,
                        "version": metadata.get("version", "1.0.0"),
                        "executor_type": executor_type,
                        "entry_point": entry_point,
                        "docker_image": "autonome-tool-env",
                    },
                )
                log_msg(f"📄 已注入元数据文件: run_parameters.tsv, README_autonome.md")
            except Exception as meta_err:
                log_msg(f"⚠️ 元数据注入失败: {meta_err}", level="WARNING")

            # 构建文件列表
            files_markdown = ""
            for filename in generated_files:
                container_path = f"/workspace/project_{project_id}/results/{semantic_dir_name}/{filename}"
                files_markdown += f"{container_path}\n"

            # 读取数据摘要
            summary_path = f"{task_out_dir}/data_summary.txt"
            data_summary = "暂无详细数据特征"
            if os.path.exists(summary_path):
                with open(summary_path, 'r', encoding='utf-8') as f:
                    data_summary = f.read()

            # 构建图像路径列表
            img_extensions = ('.png', '.pdf', '.jpg', '.jpeg', '.svg')
            images = [f for f in generated_files if f.lower().endswith(img_extensions)]
            image_paths = []
            for img_name in images[:3]:
                img_path = os.path.join(task_out_dir, img_name)
                if os.path.exists(img_path):
                    image_paths.append(img_path)

            # 更新执行历史记录
            if history_id:
                try:
                    with Session(engine) as db:
                        history_record = db.get(SkillExecutionHistory, history_id)
                        if history_record:
                            history_record.skill_name = skill_name
                            history_record.status = "SUCCESS"
                            history_record.execution_time = elapsed_time
                            history_record.output_dir = task_out_dir
                            history_record.result_summary = f"成功生成 {len(generated_files)} 个文件"
                            log_msg(f"✅ 已更新执行历史记录: ID={history_id}, 状态=SUCCESS")
                except Exception as e:
                    log_msg(f"⚠️ 更新执行历史记录失败: {e}", level="WARNING")

            # 构建成功消息
            if task_summary:
                display_summary = task_summary
            else:
                display_summary = user_message[:50] + "..." if len(user_message) > 50 else user_message

            image_paths_json = json.dumps(image_paths)
            final_content = (
                f"<!-- TASK_ID: {task_id} -->\n"
                f"<!-- TASK_NAME: {semantic_dir_name} -->\n"
                f"<!-- DEEP_INTERPRET_META\n"
                f"USER_MESSAGE: {user_message}\n"
                f"CODE_START\n{rendered_script}\nCODE_END\n"
                f"IMAGE_PATHS: {image_paths_json}\n"
                f"DATA_SUMMARY: {data_summary[:500]}\n"
                f"DEEP_INTERPRET_META -->\n\n"
                f"✅ **SKILL 执行完成: {skill_name}**\n\n"
                f"| 项目 | 内容 |\n"
                f"|------|------|\n"
                f"| 任务概述 | {display_summary} |\n"
                f"| 生成文件 | {len(generated_files)} 个 |\n"
                f"| 执行时间 | {elapsed_time:.1f} 秒 |\n\n"
                f"### 📁 生成的文件资产\n\n{files_markdown}"
            )
            safe_add_chat_message(session_id, "assistant", final_content)

            return {"status": "success", "files": generated_files}

        except Exception as e:
            log_msg(f"💥 发生系统错误: {str(e)}", level="ERROR")
            log.error(f"[execute_bundle_task] 任务执行异常: {traceback.format_exc()}")

            if history_id:
                try:
                    with Session(engine) as db:
                        history_record = db.get(SkillExecutionHistory, history_id)
                        if history_record:
                            history_record.status = "FAILURE"
                            history_record.result_summary = f"系统错误: {str(e)[:200]}"
                            db.commit()
                            log_msg(f"✅ 已更新执行历史记录: ID={history_id}, 状态=FAILURE")
                except Exception as ex:
                    log_msg(f"⚠️ 更新执行历史记录失败: {ex}", level="WARNING")

            raise e

    return {
        "execute_bundle_task": execute_bundle_task,
    }