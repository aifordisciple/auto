"""模拟对话测试 - 回复评判器

使用本地 Ollama qwen3.6-ultra 模型评判回复合理性。
"""

import json
from typing import Optional

import httpx
from loguru import logger

from chat_sim.models import APIResult, JudgeResult, SimQuestion

# 评判 Prompt 模板
_JUDGE_PROMPT = """你是一个对话系统质量评判专家。请评判以下 AI 回复是否合理。

## 输入信息
- 问题: {question}
- 问题分类: {category}
- 问题难度: {difficulty}
- 期望意图: {expected_intent}
- 实际意图: {actual_intent}
- AI回复: {response}

## 评判维度
1. 相关性 (1-5): 回复是否与问题相关
2. 准确性 (1-5): 回复内容是否准确（如无法判断准确性，给3分）
3. 完整性 (1-5): 回复是否完整回答了问题
4. 意图匹配: 实际意图是否与期望一致

## 评判标准
- PASS: 所有维度 >= 3，意图匹配，回复有意义
- WARN: 有维度为 2，或意图不匹配但回复尚可
- FAIL: 有维度为 1，或回复完全无关/为空/包含错误

## 问题定位
根据问题现象定位故障模块:
- intent_router: 意图分类错误
- knowledge_base_node: 知识库查询回复不相关
- general_qa_node: 通用问答回复不相关
- small_talk_node: 闲聊回复异常
- task_node: 任务执行异常
- content_filter: 内容过滤误判
- llm_service: 回复为空/截断/格式错误
- performance: 响应超时

## 输出格式
请严格按以下 JSON 格式输出，不要包含其他内容:
```json
{{
  "verdict": "PASS/WARN/FAIL",
  "relevance": 1-5,
  "accuracy": 1-5,
  "completeness": 1-5,
  "intent_match": true/false,
  "reason": "判断原因",
  "issue_location": "故障模块或空字符串"
}}
```
"""


def _extract_json(text: str) -> str:
    """从可能包含 markdown 代码块的文本中提取 JSON"""
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start:end + 1]

    return text


async def judge_response(
    question: SimQuestion,
    api_result: APIResult,
    ollama_host: str = "http://localhost:11434",
    model: str = "qwen3.6-ultra:latest",
    total: int = 50,
) -> JudgeResult:
    """评判单条回复

    Args:
        question: 测试问题
        api_result: API 调用结果
        ollama_host: Ollama 服务地址
        model: 评判模型名称
        total: 总测试数

    Returns:
        评判结果
    """
    idx = question.id
    result = JudgeResult(question_id=idx, verdict="FAIL")

    # 如果 API 调用本身就失败了，直接标记
    if api_result.status_code != 200:
        result.verdict = "FAIL"
        result.reason = f"API 调用失败: {api_result.error}"
        result.issue_location = _locate_from_error(api_result)
        logger.info(f"[{idx}/{total}] 评判结果: {result.verdict} | 原因: {result.reason}")
        return result

    # 如果期望被过滤，检查是否确实被拦截
    if question.expected_intent == "blocked":
        if api_result.status_code == 400 or "blocked" in api_result.error.lower():
            result.verdict = "PASS"
            result.reason = "内容过滤正常拦截"
            result.intent_match = True
        else:
            result.verdict = "FAIL"
            result.reason = "期望被过滤但未被拦截"
            result.issue_location = "content_filter"
            result.intent_match = False
        logger.info(f"[{idx}/{total}] 评判结果: {result.verdict} | 原因: {result.reason}")
        return result

    # 如果回复为空，直接标记
    if not api_result.response_text.strip():
        result.verdict = "FAIL"
        result.reason = "AI 回复为空"
        result.issue_location = "llm_service"
        logger.info(f"[{idx}/{total}] 评判结果: FAIL | 原因: 回复为空")
        return result

    # 使用 LLM 评判
    prompt = _JUDGE_PROMPT.format(
        question=question.message,
        category=question.category,
        difficulty=question.difficulty,
        expected_intent=question.expected_intent,
        actual_intent=api_result.actual_intent or "unknown",
        response=api_result.response_text[:2000],  # 限制长度避免 token 过多
    )

    logger.debug(f"[{idx}/{total}] 开始 LLM 评判...")

    try:
        # 使用 Ollama 原生 API
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{ollama_host}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.1,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

        content = data.get("message", {}).get("content", "")
        logger.debug(f"[{idx}/{total}] 评判 LLM 原始输出: {content[:300]}...")

        # 解析评判结果
        json_str = _extract_json(content)
        judge_data = json.loads(json_str)

        result.verdict = judge_data.get("verdict", "FAIL").upper()
        result.relevance = int(judge_data.get("relevance", 0))
        result.accuracy = int(judge_data.get("accuracy", 0))
        result.completeness = int(judge_data.get("completeness", 0))
        result.intent_match = bool(judge_data.get("intent_match", False))
        result.reason = judge_data.get("reason", "")
        result.issue_location = judge_data.get("issue_location", "")

        # 规范化 verdict
        if result.verdict not in ("PASS", "WARN", "FAIL"):
            result.verdict = "FAIL"

    except httpx.HTTPStatusError as e:
        logger.error(f"[{idx}/{total}] 评判 LLM 调用失败: {e.response.status_code}")
        result.verdict = "WARN"
        result.reason = f"评判 LLM 调用失败，降级为规则检查"
        # 降级为简单规则检查
        result = _fallback_rule_check(question, api_result, result)
    except json.JSONDecodeError as e:
        logger.warning(f"[{idx}/{total}] 评判结果 JSON 解析失败: {e}")
        result.verdict = "WARN"
        result.reason = "评判结果解析失败，降级为规则检查"
        result = _fallback_rule_check(question, api_result, result)
    except Exception as e:
        logger.error(f"[{idx}/{total}] 评判异常: {e}")
        result.verdict = "WARN"
        result.reason = f"评判异常: {e}"
        result = _fallback_rule_check(question, api_result, result)

    logger.info(f"[{idx}/{total}] 评判结果: {result.verdict} | 原因: {result.reason}")
    if result.issue_location:
        logger.info(f"[{idx}/{total}] 问题定位: {result.issue_location}")

    return result


def _fallback_rule_check(question: SimQuestion, api_result: APIResult, result: JudgeResult) -> JudgeResult:
    """降级规则检查：当 LLM 评判不可用时使用"""
    # 意图匹配检查
    if api_result.actual_intent and question.expected_intent != "blocked":
        result.intent_match = api_result.actual_intent == question.expected_intent
        if not result.intent_match:
            result.issue_location = "intent_router"
            if result.verdict == "PASS":
                result.verdict = "WARN"
            result.reason = f"意图不匹配: expected={question.expected_intent} actual={api_result.actual_intent}"

    # 回复非空检查
    if api_result.response_text.strip():
        result.relevance = max(result.relevance, 3)
        result.completeness = max(result.completeness, 3)
    else:
        result.relevance = 1
        result.completeness = 1
        result.issue_location = "llm_service"

    return result


def _locate_from_error(api_result: APIResult) -> str:
    """根据 API 错误信息定位问题模块"""
    error = api_result.error.lower()
    if "timeout" in error:
        return "performance"
    if "connect" in error:
        return "llm_service"
    if "400" in error or "blocked" in error or "filter" in error:
        return "content_filter"
    if "503" in error:
        return "llm_service"
    return "unknown"
