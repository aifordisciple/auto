"""
沙箱执行任务

包含 Python 和 R 语言的沙箱代码执行任务，支持 AI 自动修复重试
"""

import os
import re
import json
import time
import traceback

from celery import Celery
from sqlmodel import Session

from app.core.database import engine
from app.core.logger import log
from app.models.domain import SystemConfig
from app.services.task_logger import create_task_logger, safe_add_chat_message, redis_client
from app.services.code_fixer import fix_code_with_llm
from app.utils.argparse_injector import inject_python_argparse_params, inject_r_argparse_params
from app.tools.bio_tools import run_container


def register_sandbox_tasks(celery_app: Celery):
    """
    注册沙箱执行任务到 Celery

    Args:
        celery_app: Celery 应用实例
    """

    def _clean_terminal_output(output: str) -> str:
        """
        清理终端输出中的 ANSI 转义序列和乱码

        Args:
            output: 原始终端输出

        Returns:
            清理后的输出
        """
        if not output:
            return output

        # 清理标准 ANSI 转义序列
        output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', output)
        # 清理残余的光标控制符 (解决 [?25h 满屏的问题)
        output = re.sub(r'\[\?\d+[hl]', '', output)
        # 清理其他不可见字符
        output = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', output)
        # 统一换行符
        output = output.replace('\r\n', '\n').replace('\r', '\n').strip()

        return output

    def _log_output_lines(log_msg, output: str, prefix: str = ""):
        """
        分段记录输出内容

        Args:
            log_msg: 日志函数
            output: 输出内容
            prefix: 行前缀
        """
        if not output:
            return

        lines = output.split('\n')
        log_msg(f"📤 沙箱输出 ({len(lines)} 行):")

        if len(lines) > 20:
            for line in lines[:10]:
                log_msg(f"   {prefix}{line[:100]}")
            log_msg(f"   ... (中间省略 {len(lines) - 20} 行) ...")
            for line in lines[-10:]:
                log_msg(f"   {prefix}{line[:100]}")
        else:
            for line in lines[:15]:
                log_msg(f"   {prefix}{line[:100]}")

    def _get_llm_config() -> tuple:
        """
        从数据库获取 LLM 配置

        Returns:
            (api_key, base_url, model_name) 元组
        """
        with Session(engine) as db:
            config = db.get(SystemConfig, 1)
            if config:
                api_key = config.openai_api_key or os.getenv("OPENAI_API_KEY", "")
                base_url = config.openai_base_url or "https://api.openai.com/v1"
                model_name = config.default_model or "gpt-3.5-turbo"
            else:
                api_key = os.getenv("OPENAI_API_KEY", "")
                base_url = "https://api.openai.com/v1"
                model_name = "gpt-3.5-turbo"

        return api_key, base_url, model_name

    def _build_success_message(
        task_id: str,
        task_dir_name: str,
        user_message: str,
        task_summary: str,
        code: str,
        project_id: int,
        task_out_dir: str,
        elapsed_time: float,
        generated_files: list,
        image_paths: list,
        data_summary: str
    ) -> str:
        """
        构建任务成功的消息内容

        Args:
            task_id: 任务 ID
            task_dir_name: 任务目录名
            user_message: 用户消息
            task_summary: 任务概述
            code: 执行的代码
            project_id: 项目 ID
            task_out_dir: 任务输出目录
            elapsed_time: 执行时间
            generated_files: 生成的文件列表
            image_paths: 图像路径列表
            data_summary: 数据摘要

        Returns:
            Markdown 格式的消息内容
        """
        # 构建文件列表 markdown
        files_markdown = ""
        for filename in generated_files:
            container_path = f"/workspace/project_{project_id}/results/{task_dir_name}/{filename}"
            files_markdown += f"{container_path}\n"

        # 优先使用 AI 生成的 task_summary
        if task_summary:
            display_summary = task_summary
        else:
            display_summary = user_message[:50] + "..." if len(user_message) > 50 else user_message

        # 构建元数据
        image_paths_json = json.dumps(image_paths)

        final_content = (
            f"<!-- TASK_ID: {task_id} -->\n"
            f"<!-- TASK_NAME: {task_dir_name} -->\n"
            f"<!-- DEEP_INTERPRET_META\n"
            f"USER_MESSAGE: {user_message}\n"
            f"CODE_START\n{code}\nCODE_END\n"
            f"IMAGE_PATHS: {image_paths_json}\n"
            f"DATA_SUMMARY: {data_summary[:500]}\n"
            f"DEEP_INTERPRET_META -->\n\n"
            f"✅ **分析任务已完成**\n\n"
            f"| 项目 | 内容 |\n"
            f"|------|------|\n"
            f"| 任务概述 | {display_summary} |\n"
            f"| 生成文件 | {len(generated_files)} 个 |\n"
            f"| 执行时间 | {elapsed_time:.1f} 秒 |\n\n"
            f"### 📁 生成的文件资产\n\n{files_markdown}"
        )

        return final_content

    def _build_error_message(
        task_id: str,
        task_dir_name: str,
        max_retries: int,
        last_error: str,
        language: str = "python"
    ) -> str:
        """
        构建任务失败的消息内容

        Args:
            task_id: 任务 ID
            task_dir_name: 任务目录名
            max_retries: 最大重试次数
            last_error: 最后的错误信息
            language: 语言类型

        Returns:
            Markdown 格式的错误消息
        """
        lang_label = "R" if language.lower() == "r" else "Python"

        if language.lower() == "r":
            suggestions = (
                "- 检查 R 包是否已正确安装\n"
                "- 验证数据文件路径和格式\n"
                "- 在聊天中向 AI 描述具体问题，请求帮助"
            )
        else:
            suggestions = (
                "- 检查数据文件是否存在且格式正确\n"
                "- 尝试简化代码逻辑\n"
                "- 在聊天中向 AI 描述具体问题，请求帮助"
            )

        final_content = (
            f"<!-- TASK_ID: {task_id} -->\n"
            f"<!-- TASK_NAME: {task_dir_name} -->\n"
            f"❌ **{lang_label} 代码执行失败 (Task ID: `{str(task_id)[:8]}`)**\n\n"
            f"AI 已尝试自动修复 {max_retries} 次，但仍然失败。\n\n"
            f"### ⚠️ 最终错误日志\n"
            f"```text\n{last_error}\n```\n\n"
            f"### 💡 建议\n"
            f"{suggestions}"
        )

        return final_content

    @celery_app.task(bind=True)
    def run_custom_python_task(self, params: dict):
        """
        Python 代码沙箱执行任务

        在 Docker 沙箱中执行 Python 代码，支持：
        - argparse 参数自动注入
        - AI 自动修复重试（最多 3 次）
        - 生成文件自动扫描
        - 执行结果消息推送

        Args:
            params: 任务参数字典，包含:
                - code: Python 代码
                - session_id: 会话 ID
                - project_id: 项目 ID
                - message: 用户消息
                - task_name: 任务名称
                - task_summary: 任务概述
                - user_params: 用户参数

        Returns:
            {"status": "success"} 或抛出异常
        """
        task_id = self.request.id
        code = params.get("code")
        session_id = params.get("session_id")
        project_id = params.get("project_id")
        user_message = params.get("message", "用户执行了生信数据分析任务")
        task_name = params.get("task_name")
        task_summary = params.get("task_summary")
        user_params = params.get("user_params", {})

        log_msg, send_code_update = create_task_logger(task_id)
        log_msg(f"🚀 初始化 Python 沙箱引擎 (Task ID: {task_id})")
        log_msg(f"📋 项目 ID: {project_id}, 会话 ID: {session_id}")

        # 检测并注入 argparse 参数
        if user_params and code:
            uses_argparse = "argparse" in code or "ArgumentParser" in code or "add_argument" in code
            if uses_argparse:
                log_msg(f"🔧 检测到 argparse 参数解析，准备注入参数...")
                code = inject_python_argparse_params(code, user_params, log_msg)

        try:
            # 生成本次任务专属的目录
            task_short_id = str(task_id)[:8]
            task_dir_name = task_name if task_name else f"task_{task_short_id}"
            task_out_dir = f"/workspace/project_{project_id}/results/{task_dir_name}"
            os.makedirs(task_out_dir, exist_ok=True)
            log_msg(f"📁 已分配专属输出目录: results/{task_dir_name}")

            # 记录任务信息
            log_msg(f"📝 准备执行 Python 代码 ({len(code)} 字符, {len(code.split(chr(10)))} 行)")

            # 记录沙箱启动
            log_msg(f"🛡️ 启动安全沙箱容器 (autonome-tool-env)...")
            log_msg(f"⏳ 执行中... ")

            # 将专属目录作为环境变量注入沙箱
            env = {"TASK_OUT_DIR": task_out_dir}
            start_time = time.time()
            result_output, exit_code, _ = run_container("autonome-tool-env", code, language="python", environment=env)
            elapsed_time = time.time() - start_time

            log_msg(f"⏱️ 执行耗时: {elapsed_time:.1f} 秒")
            log_msg(f"🔢 退出码: {exit_code}")

            # 清理终端乱码
            result_output = _clean_terminal_output(result_output)

            # 记录沙箱输出
            _log_output_lines(log_msg, result_output)

            # 处理执行失败
            if exit_code != 0:
                log_msg(f"💥 代码执行失败 (Exit Code {exit_code})", level="ERROR")

                # 检测超时错误
                is_timeout = "执行超时" in result_output or "timeout" in result_output.lower()

                if is_timeout:
                    log_msg(f"⏰ 检测到执行超时！", level="ERROR")
                    log_msg(f"   可能原因:", level="ERROR")
                    log_msg(f"   1. 代码中存在死循环或无限递归", level="ERROR")
                    log_msg(f"   2. 处理的数据量过大，需要分批处理", level="ERROR")
                    log_msg(f"   3. 耗时操作（如大规模矩阵运算）未优化", level="ERROR")
                    log_msg(f"💡 建议:", level="WARNING")
                    log_msg(f"   - 检查代码中的循环和递归逻辑", level="WARNING")
                    log_msg(f"   - 对大数据进行采样或分批处理", level="WARNING")
                    log_msg(f"   - 使用更高效的算法或库（如 numpy 向量化）", level="WARNING")
                else:
                    # 详细记录错误信息
                    if result_output:
                        log_msg(f"🔴 完整错误日志:", level="ERROR")
                        for line in result_output.split('\n')[-50:]:
                            log_msg(f"   {line}", level="ERROR")

                    # 启动 AI 自动修复重试逻辑
                    log_msg(f"🔧 启动 AI 自动修复引擎...", level="WARNING")
                    max_retries = 3
                    current_code = code
                    last_error = result_output

                    for retry_attempt in range(1, max_retries + 1):
                        log_msg(f"🔄 第 {retry_attempt}/{max_retries} 次尝试修复...")

                        # 更新任务状态为 RETRY
                        self.update_state(state='PROGRESS', meta={
                            'progress': 0,
                            'status': 'RETRY',
                            'attempt': retry_attempt,
                            'max_retries': max_retries
                        })

                        # 获取 LLM 配置
                        api_key, base_url, model_name = _get_llm_config()

                        # 调用 AI 修复代码
                        log_msg(f"📡 正在调用修复 API: {base_url}, model: {model_name}")
                        log_msg(f"📝 代码长度: {len(current_code)} 字符, 错误信息长度: {len(last_error)} 字符")
                        fix_start_time = time.time()
                        fixed_code = fix_code_with_llm(current_code, last_error, api_key, base_url, model_name)
                        fix_elapsed = time.time() - fix_start_time
                        log_msg(f"⏱️ API 调用耗时: {fix_elapsed:.1f} 秒")

                        if not fixed_code:
                            log_msg(f"❌ AI 修复失败，无法生成新代码", level="ERROR")
                            break

                        log_msg(f"✅ AI 已生成修复代码，正在重新执行...")

                        # 发送代码更新事件到前端
                        send_code_update(fixed_code, language="python", attempt=retry_attempt)

                        log_msg(f"📝 修复后的代码预览:")
                        for line in fixed_code.split('\n')[:10]:
                            log_msg(f"   {line}")
                        if len(fixed_code.split('\n')) > 10:
                            log_msg(f"   ... (共 {len(fixed_code.split(chr(10)))} 行)")

                        # 重新执行修复后的代码
                        start_time = time.time()
                        result_output, exit_code, _ = run_container("autonome-tool-env", fixed_code, language="python", environment=env)
                        elapsed_time = time.time() - start_time

                        log_msg(f"⏱️ 执行耗时: {elapsed_time:.1f} 秒")
                        log_msg(f"🔢 退出码: {exit_code}")

                        if exit_code == 0:
                            log_msg(f"🎉 AI 修复成功！代码已正确执行")
                            code = fixed_code
                            break
                        else:
                            log_msg(f"❌ 修复后代码仍然失败", level="ERROR")
                            current_code = fixed_code
                            last_error = result_output

                            log_msg(f"🔴 新的错误:", level="ERROR")
                            for line in result_output.split('\n')[-30:]:
                                log_msg(f"   {line}", level="ERROR")

                    # 检查是否修复成功
                    if exit_code != 0:
                        log_msg(f"💥 AI 修复 {max_retries} 次后仍失败，返回错误报告", level="ERROR")
                        final_content = _build_error_message(task_id, task_dir_name, max_retries, last_error, "python")
                        safe_add_chat_message(session_id, "assistant", final_content)
                        raise Exception(f"代码执行失败: AI 修复 {max_retries} 次后仍失败")

            log_msg("🎉 代码执行成功！准备生成专家解读...")

            # 保存最后一次成功执行的代码到 Redis
            redis_client.hset(f"task_info:{task_id}", "final_code", code)
            log_msg(f"📝 已保存最终执行代码 ({len(code)} 字符)")

            # 扫描生成的文件
            generated_files = []
            if os.path.exists(task_out_dir):
                for f in os.listdir(task_out_dir):
                    full_path = os.path.join(task_out_dir, f)
                    if os.path.isfile(full_path):
                        generated_files.append(f)

            log_msg(f"📂 检测到生成的文件: {generated_files}")

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

            # 构建成功消息
            final_content = _build_success_message(
                task_id, task_dir_name, user_message, task_summary,
                code, project_id, task_out_dir, elapsed_time,
                generated_files, image_paths, data_summary
            )
            safe_add_chat_message(session_id, "assistant", final_content)

            return {"status": "success"}

        except Exception as e:
            log_msg(f"💥 发生系统错误: {str(e)}", level="ERROR")
            raise e

    @celery_app.task(bind=True)
    def run_custom_r_task(self, params: dict):
        """
        R 代码沙箱执行任务

        在 Docker 沙箱中执行 R 代码，支持：
        - R argparse 参数自动注入
        - AI 自动修复重试（最多 3 次）
        - 生成文件自动扫描
        - 执行结果消息推送

        Args:
            params: 任务参数字典，包含:
                - code: R 代码
                - session_id: 会话 ID
                - project_id: 项目 ID
                - message: 用户消息
                - task_name: 任务名称
                - task_summary: 任务概述
                - user_params: 用户参数

        Returns:
            {"status": "success"} 或抛出异常
        """
        task_id = self.request.id
        code = params.get("code")
        session_id = params.get("session_id")
        project_id = params.get("project_id")
        user_message = params.get("message", "用户执行了生信 R 语言任务")
        task_name = params.get("task_name")
        task_summary = params.get("task_summary")
        user_params = params.get("user_params", {})

        log_msg, send_code_update = create_task_logger(task_id)
        log_msg(f"🚀 初始化 R 沙箱引擎 (Task ID: {task_id})")
        log_msg(f"📋 项目 ID: {project_id}, 会话 ID: {session_id}")

        # 检测并注入 argparse 参数
        if user_params and code:
            uses_argparse = "argparse" in code.lower() or "ArgumentParser" in code or "add_argument" in code
            if uses_argparse:
                log_msg(f"🔧 检测到 argparse 参数解析，准备注入参数...")
                code = inject_r_argparse_params(code, user_params, log_msg)

        try:
            # 生成本次任务专属的目录
            task_short_id = str(task_id)[:8]
            task_dir_name = task_name if task_name else f"task_{task_short_id}"
            task_out_dir = f"/workspace/project_{project_id}/results/{task_dir_name}"
            os.makedirs(task_out_dir, exist_ok=True)
            log_msg(f"📁 已分配专属输出目录: results/{task_dir_name}")

            # 记录任务信息
            log_msg(f"📝 准备执行 R 代码 ({len(code)} 字符, {len(code.split(chr(10)))} 行)")

            # 记录沙箱启动
            log_msg(f"🛡️ 启动安全沙箱容器 (autonome-tool-env)...")
            log_msg(f"⏳ 执行中... ")

            # 将专属目录作为环境变量注入沙箱
            env = {"TASK_OUT_DIR": task_out_dir}
            start_time = time.time()
            result_output, exit_code, _ = run_container("autonome-tool-env", code, language="r", environment=env)
            elapsed_time = time.time() - start_time

            log_msg(f"⏱️ 执行耗时: {elapsed_time:.1f} 秒")
            log_msg(f"🔢 退出码: {exit_code}")

            # 清理终端乱码
            result_output = _clean_terminal_output(result_output)

            # 记录沙箱输出
            _log_output_lines(log_msg, result_output)

            # 处理执行失败
            if exit_code != 0:
                log_msg(f"💥 R代码执行失败 (Exit Code {exit_code})", level="ERROR")

                # 检测超时错误
                is_timeout = "执行超时" in result_output or "timeout" in result_output.lower()

                if is_timeout:
                    log_msg(f"⏰ 检测到执行超时！", level="ERROR")
                    log_msg(f"   可能原因:", level="ERROR")
                    log_msg(f"   1. R 代码中存在死循环", level="ERROR")
                    log_msg(f"   2. 处理的数据量过大", level="ERROR")
                    log_msg(f"   3. 复杂的统计运算或绘图", level="ERROR")
                    log_msg(f"💡 建议:", level="WARNING")
                    log_msg(f"   - 检查 R 代码中的循环逻辑", level="WARNING")
                    log_msg(f"   - 使用 data.table 或 dplyr 优化数据处理", level="WARNING")
                    log_msg(f"   - 减少数据量或分批处理", level="WARNING")
                else:
                    # 详细记录错误信息
                    if result_output:
                        log_msg(f"🔴 完整错误日志:", level="ERROR")
                        for line in result_output.split('\n')[-50:]:
                            log_msg(f"   {line}", level="ERROR")

                    # 启动 AI 自动修复重试逻辑
                    log_msg(f"🔧 启动 AI 自动修复引擎...", level="WARNING")
                    max_retries = 3
                    current_code = code
                    last_error = result_output

                    for retry_attempt in range(1, max_retries + 1):
                        log_msg(f"🔄 第 {retry_attempt}/{max_retries} 次尝试修复...")

                        # 更新任务状态为 RETRY
                        self.update_state(state='PROGRESS', meta={
                            'progress': 0,
                            'status': 'RETRY',
                            'attempt': retry_attempt,
                            'max_retries': max_retries
                        })

                        # 获取 LLM 配置
                        api_key, base_url, model_name = _get_llm_config()

                        # 调用 AI 修复代码（指定 R 语言）
                        log_msg(f"📡 正在调用修复 API: {base_url}, model: {model_name}")
                        log_msg(f"📝 代码长度: {len(current_code)} 字符, 错误信息长度: {len(last_error)} 字符")
                        fix_start_time = time.time()
                        fixed_code = fix_code_with_llm(current_code, last_error, api_key, base_url, model_name, language="r")
                        fix_elapsed = time.time() - fix_start_time
                        log_msg(f"⏱️ API 调用耗时: {fix_elapsed:.1f} 秒")

                        if not fixed_code:
                            log_msg(f"❌ AI 修复失败，无法生成新代码", level="ERROR")
                            break

                        log_msg(f"✅ AI 已生成修复代码，正在重新执行...")

                        # 发送代码更新事件到前端
                        send_code_update(fixed_code, language="r", attempt=retry_attempt)

                        log_msg(f"📝 修复后的 R 代码预览:")
                        for line in fixed_code.split('\n')[:10]:
                            log_msg(f"   {line}")
                        if len(fixed_code.split('\n')) > 10:
                            log_msg(f"   ... (共 {len(fixed_code.split(chr(10)))} 行)")

                        # 重新执行修复后的代码
                        start_time = time.time()
                        result_output, exit_code, _ = run_container("autonome-tool-env", fixed_code, language="r", environment=env)
                        elapsed_time = time.time() - start_time

                        log_msg(f"⏱️ 执行耗时: {elapsed_time:.1f} 秒")
                        log_msg(f"🔢 退出码: {exit_code}")

                        if exit_code == 0:
                            log_msg(f"🎉 AI 修复成功！R 代码已正确执行")
                            code = fixed_code
                            break
                        else:
                            log_msg(f"❌ 修复后代码仍然失败", level="ERROR")
                            current_code = fixed_code
                            last_error = result_output

                            log_msg(f"🔴 新的错误:", level="ERROR")
                            for line in result_output.split('\n')[-20:]:
                                log_msg(f"   {line}", level="ERROR")

                    # 检查是否修复成功
                    if exit_code != 0:
                        log_msg(f"💥 AI 修复 {max_retries} 次后仍失败，返回错误报告", level="ERROR")
                        final_content = _build_error_message(task_id, task_dir_name, max_retries, last_error, "r")
                        safe_add_chat_message(session_id, "assistant", final_content)
                        raise Exception(f"R 代码执行失败: AI 修复 {max_retries} 次后仍失败")

            log_msg("🎉 R 代码执行成功！准备生成专家解读...")

            # 保存最后一次成功执行的代码到 Redis
            redis_client.hset(f"task_info:{task_id}", "final_code", code)
            log_msg(f"📝 已保存最终执行代码 ({len(code)} 字符)")

            # 扫描生成的文件
            generated_files = []
            if os.path.exists(task_out_dir):
                for f in os.listdir(task_out_dir):
                    full_path = os.path.join(task_out_dir, f)
                    if os.path.isfile(full_path):
                        generated_files.append(f)

            log_msg(f"📂 检测到生成的文件: {generated_files}")

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

            # 构建成功消息
            final_content = _build_success_message(
                task_id, task_dir_name, user_message, task_summary,
                code, project_id, task_out_dir, elapsed_time,
                generated_files, image_paths, data_summary
            )
            safe_add_chat_message(session_id, "assistant", final_content)

            return {"status": "success"}

        except Exception as e:
            log_msg(f"💥 发生系统错误: {str(e)}", level="ERROR")
            raise e

    return {
        "run_custom_python_task": run_custom_python_task,
        "run_custom_r_task": run_custom_r_task,
    }