"""模拟对话测试 - API 调用器

调用真实后端 /api/chat/stream 端点，解析 SSE 流式响应。
记录充足日志，便于定位问题。
"""

import json
import time
from typing import Optional

import httpx
from loguru import logger

from chat_sim.models import APIResult, SimQuestion

# 超时配置（秒）
TIMEOUT_MAP = {
    "easy": 30,
    "medium": 45,
    "hard": 60,
}


async def login(base_url: str, email: str, password: str) -> str:
    """登录获取 JWT token

    Args:
        base_url: API 基础地址
        email: 测试账号邮箱
        password: 测试账号密码

    Returns:
        JWT access_token
    """
    url = f"{base_url}/api/auth/login"
    # OAuth2 密码流使用 form data
    form_data = {
        "username": email,
        "password": password,
    }

    logger.info(f"API调用器 | 登录测试账号: {email}")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, data=form_data)
        if resp.status_code != 200:
            logger.error(f"API调用器 | 登录失败: {resp.status_code} {resp.text}")
            raise RuntimeError(f"登录失败: {resp.status_code} {resp.text}")

        data = resp.json()
        token = data.get("access_token", "")
        if not token:
            raise RuntimeError("登录响应中无 access_token")

    logger.info("API调用器 | 登录成功，获取 token")
    return token


async def get_project_id(base_url: str, token: str) -> str:
    """获取第一个项目 ID，用于聊天请求

    Args:
        base_url: API 基础地址
        token: JWT token

    Returns:
        项目 ID
    """
    url = f"{base_url}/api/projects"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.error(f"API调用器 | 获取项目列表失败: {resp.status_code}")
            raise RuntimeError(f"获取项目列表失败: {resp.status_code}")

        data = resp.json()
        # 适配 {"status": "success", "data": [...]} 格式
        if isinstance(data, dict) and "data" in data:
            projects = data["data"]
        elif isinstance(data, list):
            projects = data
        else:
            projects = data.get("items", [])

        if not projects:
            logger.warning("API调用器 | 无可用项目，使用默认 project_id='default'")
            return "default"

        project_id = projects[0].get("id", "default")
        logger.info(f"API调用器 | 使用项目: {project_id}")
        return str(project_id)


async def call_chat(
    base_url: str,
    token: str,
    question: SimQuestion,
    project_id: str,
    session_id: Optional[str] = None,
    total: int = 50,
) -> APIResult:
    """调用聊天 API 并解析 SSE 流式响应

    Args:
        base_url: API 基础地址
        token: JWT token
        question: 测试问题
        project_id: 项目 ID
        session_id: 会话 ID（None 则新建）
        total: 总测试数（用于日志显示）

    Returns:
        API 调用结果
    """
    idx = question.id
    url = f"{base_url}/api/chat/stream"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    }

    # 构造请求体
    body = {
        "project_id": project_id,
        "message": question.message,
        "context_files": [],
        "session_id": session_id,
    }

    timeout = TIMEOUT_MAP.get(question.difficulty, 45)
    logger.info(f"[{idx}/{total}] 发送问题 | category={question.category} difficulty={question.difficulty}")
    logger.info(f"[{idx}/{total}] 问题内容: {question.message[:100]}{'...' if len(question.message) > 100 else ''}")
    logger.debug(f"[{idx}/{total}] 完整请求体: {json.dumps(body, ensure_ascii=False)}")

    start_time = time.monotonic()
    result = APIResult(question_id=idx, status_code=0, elapsed_ms=0)

    try:
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                result.status_code = resp.status_code

                if resp.status_code != 200:
                    error_body = await resp.aread()
                    error_text = error_body.decode("utf-8", errors="replace")
                    result.error = f"HTTP {resp.status_code}: {error_text[:500]}"
                    logger.error(f"[{idx}/{total}] API调用失败 | status={resp.status_code} error={error_text[:200]}")
                    return result

                # 解析 SSE 流
                text_chunks = []
                raw_events = []

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue

                    # SSE 格式: "data: {json}" 或 "data-xxx: {json}"
                    if line.startswith("data:"):
                        event_data = line[5:].strip()
                    elif line.startswith("data-"):
                        # 如 "data-intent: {...}" 或 "data-session_info: {...}"
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            event_data = parts[1].strip()
                        else:
                            continue
                    elif line.startswith(":"):
                        # SSE 注释，跳过
                        continue
                    elif line.startswith("event:") or line.startswith("id:") or line.startswith("retry:"):
                        # 标准 SSE 字段，跳过
                        continue
                    else:
                        # 尝试直接解析为 JSON
                        event_data = line

                    # 尝试解析 JSON
                    try:
                        parsed = json.loads(event_data)
                        raw_events.append(parsed)

                        # SSE 事件格式: {"type": "data-intent", "data": {...}}
                        # 或直接: {"intent": "chat", ...}
                        event_type = parsed.get("type", "")
                        event_data_inner = parsed.get("data", {})

                        # 提取意图 (data-intent 事件)
                        if event_type == "data-intent" and isinstance(event_data_inner, dict):
                            intent = event_data_inner.get("intent", "")
                            if intent:
                                result.actual_intent = intent
                                logger.debug(f"[{idx}/{total}] 意图识别: {intent} (confidence={event_data_inner.get('confidence', 'N/A')})")

                        # 提取会话 ID (data-session_info 事件)
                        if event_type == "data-session_info" and isinstance(event_data_inner, dict):
                            sid = event_data_inner.get("session_id", "")
                            if sid:
                                result.session_id = sid

                        # 提取 AI 消息 ID (data-ai_message_id 事件)
                        if event_type == "data-ai_message_id" and isinstance(event_data_inner, dict):
                            mid = event_data_inner.get("message_id", "")
                            if mid:
                                result.ai_message_id = mid

                        # 提取完整 AI 消息内容 (data-ai_message_content 事件)
                        if event_type == "data-ai_message_content" and isinstance(event_data_inner, dict):
                            content = event_data_inner.get("content", "")
                            if isinstance(content, str) and len(content) > len(result.response_text):
                                result.response_text = content

                        # 提取文本增量 (text-delta 事件)
                        if event_type == "text-delta":
                            delta = parsed.get("delta", "")
                            if isinstance(delta, str):
                                text_chunks.append(delta)

                        # 兼容：无 type 字段的直接格式
                        if not event_type:
                            if "intent" in parsed and isinstance(parsed["intent"], str):
                                result.actual_intent = parsed["intent"]
                            if "session_id" in parsed:
                                result.session_id = parsed["session_id"]
                            if "delta" in parsed and isinstance(parsed["delta"], str):
                                text_chunks.append(parsed["delta"])
                            if "content" in parsed and isinstance(parsed["content"], str) and len(parsed["content"]) > len(result.response_text):
                                result.response_text = parsed["content"]

                    except json.JSONDecodeError:
                        # 非 JSON 数据，可能是纯文本
                        raw_events.append({"raw": event_data})

                # 如果没有从 ai_message_content 获取到完整文本，拼接增量
                if not result.response_text and text_chunks:
                    result.response_text = "".join(text_chunks)

                result.raw_events = raw_events

    except httpx.TimeoutException:
        result.error = f"请求超时 ({timeout}s)"
        logger.error(f"[{idx}/{total}] 请求超时 | timeout={timeout}s")
    except httpx.ConnectError as e:
        result.error = f"连接失败: {e}"
        logger.error(f"[{idx}/{total}] 连接失败 | error={e}")
    except Exception as e:
        result.error = f"未知错误: {e}"
        logger.error(f"[{idx}/{total}] 未知错误 | error={e}")

    elapsed = (time.monotonic() - start_time) * 1000
    result.elapsed_ms = elapsed

    # 响应日志
    if result.status_code == 200:
        resp_summary = result.response_text[:200] if result.response_text else "(空回复)"
        logger.info(f"[{idx}/{total}] 收到回复 | status=200 time={elapsed:.0f}ms intent={result.actual_intent}")
        logger.info(f"[{idx}/{total}] 回复摘要: {resp_summary}{'...' if len(result.response_text) > 200 else ''}")
        logger.debug(f"[{idx}/{total}] 完整回复: {result.response_text[:1000]}")
    else:
        logger.warning(f"[{idx}/{total}] 响应异常 | status={result.status_code} error={result.error}")

    # 意图匹配检查
    if result.actual_intent and question.expected_intent != "blocked":
        if result.actual_intent != question.expected_intent:
            logger.warning(
                f"[{idx}/{total}] 意图不匹配 | expected={question.expected_intent} actual={result.actual_intent}"
            )

    return result
