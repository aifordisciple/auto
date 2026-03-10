"""
SKILL Tester - 沙箱自动化测试引擎

功能：
1. 将生成的代码投入 Docker 沙箱执行
2. 如果报错则调用 LLM 自我修复（Debugger Agent）
3. 最多重试 3 次
4. 返回测试结果和最终代码
"""

import re
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from app.core.logger import log

# 尝试导入沙箱执行工具
try:
    from app.tools.bio_tools import execute_python_code
    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False
    log.warning("[Skill Tester] bio_tools 未找到，沙箱测试功能将受限")


def extract_code_from_response(text: str) -> str:
    """
    从 LLM 的回复中提取修复后的代码

    支持格式：
    - ***python ... ***
    - ```python ... ```
    - 直接返回代码

    Args:
        text: LLM 返回的原始文本

    Returns:
        提取出的代码字符串
    """
    # 优先匹配 ***python ... *** 格式
    pattern = r'\*\*\*(?:python|r)\s*(.*?)\s*\*\*\*'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 匹配 ```python ... ``` 格式
    pattern = r'```(?:python|r)\s*(.*?)\s*```'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 如果没有代码块标记，尝试直接返回整个文本
    # 但这需要确保文本主要是代码
    if 'def ' in text or 'import ' in text or 'library(' in text:
        return text.strip()

    return text.strip()


def check_execution_success(output: str) -> bool:
    """
    检查沙箱执行结果是否成功

    Args:
        output: 沙箱执行输出

    Returns:
        True 如果执行成功，False 如果失败
    """
    if not output:
        return False

    # 检查是否包含错误标记
    error_markers = ['❌', 'Error:', 'Exception:', 'Traceback', '错误']
    success_markers = ['✅', '成功', '完成', 'Success']

    output_str = str(output)

    # 如果包含错误标记
    for marker in error_markers:
        if marker in output_str:
            return False

    # 如果包含成功标记
    for marker in success_markers:
        if marker in output_str:
            return True

    # 默认认为没有错误就是成功
    return True


async def auto_test_and_heal_skill(
    script_code: str,
    test_instruction: str,
    api_key: str,
    base_url: str,
    model_name: str
) -> Dict[str, Any]:
    """
    沙箱试炼与自愈循环：
    将代码投入沙箱运行，如果报错则调用 LLM 自我修复，最多重试 3 次。

    Args:
        script_code: 需要测试的代码
        test_instruction: 测试环境变量或传参模拟代码
        api_key: OpenAI API Key
        base_url: API Base URL
        model_name: 模型名称

    Returns:
        测试结果字典，包含：
        - status: "success" 或 "failed"
        - final_code: 最终代码（可能被修复过）
        - logs: 执行日志
        - attempts: 尝试次数
    """
    log.info("🧪 [Skill Tester] 进入沙箱试炼场...")

    if not SANDBOX_AVAILABLE:
        log.warning("[Skill Tester] 沙箱不可用，跳过实际执行")
        return {
            "status": "skipped",
            "final_code": script_code,
            "logs": "沙箱执行环境不可用，测试已跳过。请在实际环境中验证代码。",
            "attempts": 0
        }

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
        temperature=0.1
    )

    current_code = script_code
    max_retries = 3
    execution_logs = ""
    is_success = False
    attempts = 0

    # 准备给 Debugger 的基础提示词
    system_prompt = """你是一个高级生信 Debugger。
你的任务是修复报错的生信分析代码。

【🚨 强制规范】：
修复代码时，绝对不能删除原有的 argparse 参数解析系统和原有的详细注释！必须保持代码的工业级规范。

请将修复后的完整代码用 ***python 或 ***r 包裹输出。只输出代码，不要输出额外的解释。"""

    chat_history = [HumanMessage(content=system_prompt)]

    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        log.info(f"▶️ [Skill Tester] 正在执行第 {attempts}/{max_retries + 1} 次沙箱测试...")

        # 1. 在原代码前面注入测试指令（模拟前端传入的测试参数）
        test_run_code = f"# [Auto-Injected Test Env]\n{test_instruction}\n\n{current_code}"

        # 2. 调用沙箱执行
        try:
            output = execute_python_code(test_run_code)
        except Exception as e:
            output = f"❌ 沙箱执行异常: {str(e)}"

        execution_logs += f"\n--- Attempt {attempts} ---\n{output}\n"

        # 3. 判断是否成功
        if check_execution_success(output):
            log.info(f"✅ [Skill Tester] 第 {attempts} 次执行成功！代码通过试炼！")
            is_success = True
            break
        else:
            log.warning(f"🔴 [Skill Tester] 第 {attempts} 次执行失败")

            if attempt < max_retries:
                # 触发自愈逻辑
                error_msg = f"""代码执行报错！

报错信息如下：
{output}

请分析错误原因，并输出修复后的完整代码（使用 ***python 包裹）。
注意：保持原有的参数解析系统和注释！"""

                chat_history.append(HumanMessage(content=error_msg))

                try:
                    response = await llm.ainvoke(chat_history)
                    chat_history.append(AIMessage(content=response.content))

                    # 提取新代码
                    new_code = extract_code_from_response(response.content)
                    if new_code:
                        current_code = new_code
                        log.info("🟢 [Skill Tester] Debugger 已生成新的修复代码，准备重试。")
                    else:
                        log.error("Debugger 没有返回有效的代码块，中断重试。")
                        break
                except Exception as e:
                    log.error(f"Debugger 调用大模型失败: {e}")
                    break
            else:
                log.error("❌ [Skill Tester] 已达到最大重试次数，试炼失败。")

    result = {
        "status": "success" if is_success else "failed",
        "final_code": current_code,
        "logs": execution_logs,
        "attempts": attempts
    }

    if is_success:
        log.info(f"🎉 [Skill Tester] 沙箱试炼完成！共尝试 {attempts} 次")
    else:
        log.warning(f"⚠️ [Skill Tester] 沙箱试炼失败！共尝试 {attempts} 次")

    return result


def security_check(script_code: str) -> tuple[bool, str]:
    """
    静态代码安全扫描

    在投入沙箱前，检查代码是否包含危险的模块或关键字

    Args:
        script_code: 待检查的代码

    Returns:
        (is_safe, error_message)
    """
    # 危险关键字黑名单
    dangerous_keywords = [
        'os.environ',      # 窃取环境变量
        'subprocess.call', # 执行系统命令
        'subprocess.run',  # 执行系统命令
        'subprocess.Popen',
        'eval(',           # 动态执行代码
        'exec(',           # 动态执行代码
        '__import__',      # 动态导入
        'socket.socket',   # 网络探测
        'requests.get',    # 网络请求
        'requests.post',
        'urllib.request',
        'shutil.rmtree',   # 删除目录
        'os.system',       # 执行系统命令
        'os.popen',
    ]

    # R 语言危险关键字
    r_dangerous_keywords = [
        'system(',
        'system2(',
        'shell(',
    ]

    all_dangerous = dangerous_keywords + r_dangerous_keywords

    for keyword in all_dangerous:
        if keyword in script_code:
            # 进一步检查是否是在注释中
            lines = script_code.split('\n')
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue  # 注释中的不算
                if keyword in line:
                    return False, f"安全警报：代码包含高风险模块或关键字 ({keyword})，拒绝执行。"

    return True, ""


log.info("🧪 SKILL Tester 已加载")