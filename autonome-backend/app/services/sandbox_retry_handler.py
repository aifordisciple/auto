"""
沙箱自动重试处理器

检测沙箱执行失败并提取错误信息，支持自动重试机制（最多2次）。
"""

import asyncio
from typing import Callable, Optional, Tuple
from app.core.logger import log


class SandboxRetryHandler:
    """沙箱执行失败自动重试处理器"""

    MAX_RETRIES = 2  # ✨ 静默重试次数（不含首次执行）
    ERROR_MARKERS = [
        'Traceback',
        'Error:',
        'Exception:',
        '❌',
        'segmentation fault',
        'Failed',
        '错误:',
        'FileNotFoundError',
        'KeyError',
        'TypeError',
    ]

    @staticmethod
    def is_execution_failed(output: str) -> bool:
        """检测沙箱执行是否失败"""
        if not output:
            return True
        output_str = str(output)
        for marker in SandboxRetryHandler.ERROR_MARKERS:
            if marker in output_str:
                return True
        return False

    @staticmethod
    def extract_error_message(output: str, max_lines: int = 15) -> str:
        """从执行输出中提取错误信息"""
        if not output:
            return "执行无输出"

        output_str = str(output) if not isinstance(output, str) else output
        lines = output_str.split('\n')
        error_lines = []

        for i, line in enumerate(lines):
            for marker in SandboxRetryHandler.ERROR_MARKERS:
                if marker in line:
                    start = max(0, i - 2)
                    error_lines = lines[start:i + max_lines]
                    break
            if error_lines:
                break

        if not error_lines:
            error_lines = lines[:max_lines]

        return '\n'.join(error_lines)

    @classmethod
    async def execute_with_retry(
        cls,
        execute_func: Callable[[], Tuple[bool, str]],
        max_retries: Optional[int] = None
    ) -> Tuple[bool, str, int]:
        """
        执行函数并自动重试

        Args:
            execute_func: 执行函数，返回 (is_success, output) 元组
            max_retries: 最大重试次数，默认为 MAX_RETRIES

        Returns:
            (is_success, final_output, retry_count) 元组
        """
        max_retries = max_retries if max_retries is not None else cls.MAX_RETRIES

        retry_count = 0
        is_success = False
        final_output = ""

        # 首次执行
        try:
            is_success, final_output = execute_func()
        except Exception as e:
            log.error(f"⚠️ [SandboxRetry] 首次执行异常: {e}")
            final_output = str(e)
            is_success = False

        # 如果失败，尝试静默重试
        while not is_success and retry_count < max_retries:
            retry_count += 1
            log.info(f"🔄 [SandboxRetry] 第 {retry_count} 次重试...")

            # 等待一小段时间（指数退避）
            await asyncio.sleep(0.5 * (2 ** retry_count))

            try:
                is_success, final_output = execute_func()
            except Exception as e:
                log.error(f"⚠️ [SandboxRetry] 第 {retry_count} 次重试异常: {e}")
                final_output = str(e)
                is_success = False

        if is_success:
            log.info(f"✅ [SandboxRetry] 执行成功（重试 {retry_count} 次）")
        else:
            log.warning(f"❌ [SandboxRetry] 执行失败（已重试 {retry_count} 次）")

        return is_success, final_output, retry_count

    @classmethod
    def should_show_troubleshoot_card(
        cls,
        output: str,
        retry_count: int,
        max_retries: Optional[int] = None
    ) -> bool:
        """
        判断是否应该显示 TroubleShoot 卡片

        Args:
            output: 最终执行输出
            retry_count: 已重试次数
            max_retries: 最大重试次数

        Returns:
            True 如果应该显示 TroubleShoot 卡片
        """
        max_retries = max_retries if max_retries is not None else cls.MAX_RETRIES

        # 只有在彻底失败后才显示 TroubleShoot 卡片
        if retry_count >= max_retries:
            return True

        # 即使还有重试次数，但错误是"不可恢复"的，也显示
        unrecoverable_markers = [
            'OutOfMemoryError',
            'OOM',
            'MemoryError',
            'Segmentation fault',
            'signal SIGKILL',
            'cannot allocate memory',
        ]

        output_lower = output.lower() if output else ""
        for marker in unrecoverable_markers:
            if marker.lower() in output_lower:
                return True

        return False