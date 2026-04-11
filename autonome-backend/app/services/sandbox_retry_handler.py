"""
沙箱自动重试处理器

检测沙箱执行失败并提取错误信息，支持自动重试机制
"""


class SandboxRetryHandler:
    """沙箱执行失败自动重试处理器"""

    MAX_RETRIES = 3  # 最大重试次数

    # 错误标记 - 用于检测执行失败
    ERROR_MARKERS = [
        'Traceback',
        'Error:',
        'Exception:',
        '❌',
        'segmentation fault',
        'Failed',
        '错误:',
    ]

    @staticmethod
    def is_execution_failed(output: str) -> bool:
        """
        检测沙箱执行是否失败

        Args:
            output: 沙箱执行输出

        Returns:
            True 表示执行失败，False 表示成功
        """
        if not output:
            return True

        output_str = str(output)

        # 检查错误标记
        for marker in SandboxRetryHandler.ERROR_MARKERS:
            if marker in output_str:
                return True

        return False

    @staticmethod
    def extract_error_message(output: str, max_lines: int = 15) -> str:
        """
        从执行输出中提取错误信息

        Args:
            output: 沙箱执行输出
            max_lines: 最大返回行数

        Returns:
            提取的错误信息
        """
        if not output:
            return "执行无输出"

        # 确保转换为字符串
        output_str = str(output) if not isinstance(output, str) else output
        lines = output_str.split('\n')
        error_lines = []

        # 查找错误起始位置
        for i, line in enumerate(lines):
            for marker in SandboxRetryHandler.ERROR_MARKERS:
                if marker in line:
                    # 捕获错误及其上下文
                    start = max(0, i - 2)
                    error_lines = lines[start:i + max_lines]
                    break
            if error_lines:
                break

        if not error_lines:
            error_lines = lines[:max_lines]

        return '\n'.join(error_lines)