"""
AI 代码修复服务

调用 LLM 修复沙箱执行失败的代码，支持 Python 和 R 语言
"""

import re
import traceback
import httpx

from app.core.logger import log


# ==========================================
# AI 代码修复 Prompt 模板
# ==========================================

CODE_FIXER_PROMPT_PYTHON = """你是一位资深的生信代码调试专家。用户的 Python 代码在沙箱中执行失败，请分析错误并修复代码。

【原始代码】
```python
{code}
```

【错误信息】
{error_msg}

【修复要求】
1. 仔细分析错误原因
2. 生成修复后的完整代码
3. 保持代码的参数系统和注释
4. 只输出修复后的代码，用 ```python 包裹

修复后的代码："""

CODE_FIXER_PROMPT_R = """你是一位资深的 R 语言生信代码调试专家。用户的 R 代码在沙箱中执行失败，请分析错误并修复代码。

【原始代码】
```r
{code}
```

【错误信息】
{error_msg}

【修复要求】
1. 仔细分析 R 语言错误原因（注意 R 的错误信息格式）
2. 生成修复后的完整 R 代码
3. 保持代码的结构和注释
4. 检查常见的 R 错误：变量未定义、包未加载、数据框列名错误、路径问题等
5. 只输出修复后的代码，用 ```r 包裹

修复后的 R 代码："""


def fix_code_with_llm(
    code: str,
    error_msg: str,
    api_key: str,
    base_url: str,
    model_name: str,
    language: str = "python",
    timeout: int = 90
) -> str:
    """
    调用 LLM 修复代码（带精细超时保护）

    使用 httpx.Timeout 对象明确指定各阶段超时时间：
    - connect: 连接建立超时 (10秒)
    - read: 读取响应超时 (由 timeout 参数控制，默认 90 秒)
    - write: 写入请求超时 (30秒)
    - pool: 从连接池获取连接超时 (10秒)

    Args:
        code: 原始代码
        error_msg: 错误信息
        api_key: OpenAI API Key
        base_url: API Base URL
        model_name: 模型名称
        language: 语言类型 ("python" 或 "r")
        timeout: 读取超时时间（秒）

    Returns:
        修复后的代码，失败返回 None
    """
    try:
        from openai import OpenAI

        # 使用 httpx.Timeout 对象明确指定各阶段超时时间
        timeout_config = httpx.Timeout(
            connect=10.0,           # 连接建立超时 10 秒
            read=float(timeout),    # 读取响应超时 (由参数控制)
            write=30.0,             # 写入请求超时 30 秒
            pool=10.0               # 从连接池获取连接超时 10 秒
        )
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_config)

        # 根据语言选择 prompt
        if language.lower() == "r":
            prompt = CODE_FIXER_PROMPT_R.format(code=code, error_msg=error_msg[:3000])
        else:
            prompt = CODE_FIXER_PROMPT_PYTHON.format(code=code, error_msg=error_msg[:3000])

        log.info(f"[Code Fixer] 正在调用 LLM API: base_url={base_url}, model={model_name}, language={language}")
        log.info(f"[Code Fixer] 代码长度: {len(code)} 字符, 错误信息长度: {len(error_msg)} 字符")

        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000
        )

        fixed_code = response.choices[0].message.content
        log.info(f"[Code Fixer] LLM API 调用成功，返回内容长度: {len(fixed_code) if fixed_code else 0} 字符")

        # 提取代码块 - 支持 python 和 r
        code_match = re.search(r'```(?:python|r)?\s*\n([\s\S]*?)```', fixed_code)
        if code_match:
            return code_match.group(1).strip()

        return fixed_code.strip()

    except httpx.ConnectTimeout as e:
        log.error(f"[Code Fixer] 连接超时: 无法连接到 {base_url} - {e}")
        return None
    except httpx.ReadTimeout as e:
        log.error(f"[Code Fixer] 读取超时: API 响应时间超过 {timeout} 秒 - {e}")
        return None
    except httpx.WriteTimeout as e:
        log.error(f"[Code Fixer] 写入超时: 发送请求超时 - {e}")
        return None
    except httpx.PoolTimeout as e:
        log.error(f"[Code Fixer] 连接池超时: 获取连接超时 - {e}")
        return None
    except Exception as e:
        log.error(f"[Code Fixer] LLM 修复失败: {type(e).__name__}: {e}")
        log.error(f"[Code Fixer] 异常堆栈: {traceback.format_exc()}")
        return None