"""模拟对话测试 - 问题生成器

用 LLM 动态生成不同类型、不同难度的测试问题。
复用后端 LLM 配置，通过 OpenAI 兼容协议调用。
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# 将后端路径加入 sys.path，复用 LLM 配置
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "autonome-backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from chat_sim.models import SimQuestion

# 问题生成 Prompt 模板
_GENERATE_PROMPT = """你是一个对话系统测试专家。请为生物信息学 AI 助手生成 {total} 条测试问题。

要求：
1. 问题必须覆盖以下分类和数量：
{category_requirements}

2. 每个分类内按难度分配：
   - easy: 简单直接的问题
   - medium: 需要一定专业知识的问题
   - hard: 复杂、多步骤或需要深度推理的问题

3. 特殊分类说明：
   - knowledge_base: 生物信息学知识查询（如基因、蛋白质、算法等）
   - general_qa: 通用编程/技术问题
   - small_talk: 闲聊、打招呼、趣味问题
   - task: 需要执行具体操作的任务（如格式转换、流程设计）
   - content_filter: 包含可能触发内容过滤的敏感词（如疾病、暴力相关），或边界输入（空消息、超长文本、特殊字符）
   - edge_case: 极短问题、多语言混合、模糊表述、拼写错误等

4. 请严格按以下 JSON 格式输出，不要包含其他内容：
```json
[
  {{
    "id": 1,
    "message": "用户消息内容",
    "category": "分类",
    "difficulty": "easy/medium/hard",
    "expected_intent": "期望意图(chat/skill_forge/explicit_skill/diagnostic/literature/data_probe)",
    "description": "测试目的说明"
  }}
]
```

注意：
- content_filter 类的 expected_intent 统一填 "blocked"（期望被过滤拦截）
- edge_case 类的 expected_intent 根据问题内容填写最可能的意图
- 问题内容要真实、多样，模拟真实用户输入
- 不要生成违法内容，content_filter 类用医学/科研相关敏感词即可
"""


def _get_category_requirements(categories: dict) -> str:
    """生成分类要求描述"""
    lines = []
    difficulty_desc = {
        "knowledge_base": "easy:3 medium:4 hard:3",
        "general_qa": "easy:3 medium:4 hard:3",
        "small_talk": "easy:4 medium:3 hard:1",
        "task": "easy:2 medium:3 hard:3",
        "content_filter": "触发过滤:4 边界输入:2",
        "edge_case": "easy:2 medium:3 hard:3",
    }
    for cat, count in categories.items():
        diff = difficulty_desc.get(cat, "easy:1 medium:1 hard:1")
        lines.append(f"   - {cat}: {count}条 ({diff})")
    return "\n".join(lines)


def _get_llm_config():
    """获取 LLM 配置，优先从后端系统设置 API 获取"""
    import httpx

    # 从后端 API 获取系统配置
    try:
        api_base = os.environ.get("API_BASE_URL", "http://localhost:8000")
        # 先尝试无需认证的端点
        resp = httpx.get(f"{api_base}/api/system/settings", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            config = data.get("data", data) if isinstance(data, dict) else {}
            api_key = config.get("openai_api_key", "")
            base_url_llm = config.get("openai_base_url", "")
            model = config.get("default_model", "")
            if api_key and base_url_llm and model:
                logger.info(f"问题生成器 | 从系统设置获取 LLM: model={model} base_url={base_url_llm}")
                return api_key, base_url_llm, model
    except Exception as e:
        logger.debug(f"问题生成器 | 从 API 获取配置失败: {e}")

    # 尝试从后端 .env 加载
    env_file = _BACKEND_DIR / ".env"
    env_vars = {}
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")

    api_key = os.environ.get("OPENAI_API_KEY", env_vars.get("OPENAI_API_KEY", ""))
    base_url_llm = os.environ.get("OPENAI_BASE_URL", env_vars.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    model = os.environ.get("SIM_TEST_MODEL", env_vars.get("DEFAULT_MODEL", "gpt-4o-mini"))

    return api_key, base_url_llm, model


async def generate_questions(
    total: int = 50,
    categories: Optional[dict] = None,
    save_path: Optional[str] = None,
) -> list[SimQuestion]:
    """用 LLM 动态生成测试问题

    Args:
        total: 问题总数
        categories: 分类及数量映射，如 {"knowledge_base": 10, ...}
        save_path: 生成问题保存路径

    Returns:
        生成的测试问题列表
    """
    if categories is None:
        categories = {
            "knowledge_base": 10,
            "general_qa": 10,
            "small_talk": 8,
            "task": 8,
            "content_filter": 6,
            "edge_case": 8,
        }

    api_key, base_url, model = _get_llm_config()
    logger.info(f"问题生成器 | model={model} base_url={base_url}")

    prompt = _GENERATE_PROMPT.format(
        total=total,
        category_requirements=_get_category_requirements(categories),
    )

    # 使用 httpx 直接调用 OpenAI 兼容 API
    import httpx

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # 确保 base_url 以 /chat/completions 结尾
    chat_url = base_url.rstrip("/")
    if not chat_url.endswith("/chat/completions"):
        chat_url = f"{chat_url}/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 4096,
    }

    logger.info(f"问题生成器 | 开始生成 {total} 条测试问题...")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(chat_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        logger.debug(f"问题生成器 | LLM 原始输出: {content[:500]}...")

        # 提取 JSON 部分（可能被 markdown 代码块包裹）
        json_str = _extract_json(content)
        questions_data = json.loads(json_str)

    except httpx.HTTPStatusError as e:
        logger.error(f"问题生成器 | LLM API 调用失败: {e.response.status_code} {e.response.text}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"问题生成器 | JSON 解析失败: {e}")
        logger.error(f"问题生成器 | 原始内容: {content[:1000]}")
        raise
    except Exception as e:
        logger.error(f"问题生成器 | 生成失败: {e}")
        raise

    # 转换为 SimQuestion 列表
    questions = []
    for item in questions_data:
        q = SimQuestion(
            id=item["id"],
            message=item["message"],
            category=item["category"],
            difficulty=item["difficulty"],
            expected_intent=item["expected_intent"],
            description=item["description"],
        )
        questions.append(q)
        logger.debug(f"问题生成器 | #{q.id} [{q.category}/{q.difficulty}] {q.message[:60]}...")

    logger.info(f"问题生成器 | 成功生成 {len(questions)} 条测试问题")

    # 保存生成的问题
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump([_question_to_dict(q) for q in questions], f, ensure_ascii=False, indent=2)
        logger.info(f"问题生成器 | 问题已保存到 {save_path}")

    return questions


def load_questions(path: str) -> list[SimQuestion]:
    """从 JSON 文件加载测试问题"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        SimQuestion(
            id=item["id"],
            message=item["message"],
            category=item["category"],
            difficulty=item["difficulty"],
            expected_intent=item["expected_intent"],
            description=item["description"],
        )
        for item in data
    ]


def _extract_json(text: str) -> str:
    """从可能包含 markdown 代码块的文本中提取 JSON"""
    # 尝试提取 ```json ... ``` 块
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 尝试直接找 JSON 数组
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        return text[start:end + 1]

    return text


def _question_to_dict(q: SimQuestion) -> dict:
    return {
        "id": q.id,
        "message": q.message,
        "category": q.category,
        "difficulty": q.difficulty,
        "expected_intent": q.expected_intent,
        "description": q.description,
    }
