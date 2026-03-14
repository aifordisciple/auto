"""
AI 代码辅助 API - 提供代码补全、代码审查、错误诊断等功能

核心端点:
- POST /complete: AI 代码补全
- POST /review: AI 代码审查
- POST /diagnose: AI 错误诊断
- POST /optimize: AI 代码优化建议
"""

import re
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from sqlmodel import Session

from app.core.database import get_session
from app.core.logger import log
from app.api.deps import get_current_user
from app.models.domain import User, SystemConfig
from app.core.config import settings

router = APIRouter()


# ==========================================
# 请求模型
# ==========================================
class CodeCompletionRequest(BaseModel):
    """代码补全请求"""
    code: str = Field(description="当前代码内容")
    cursor_position: int = Field(description="光标位置")
    language: str = Field(default="python", description="编程语言")
    context: Optional[str] = Field(default=None, description="额外上下文（如技能描述）")


class CodeReviewRequest(BaseModel):
    """代码审查请求"""
    code: str
    language: str = "python"


class ErrorDiagnosisRequest(BaseModel):
    """错误诊断请求"""
    code: str
    error_message: str
    language: str = "python"


class OptimizationRequest(BaseModel):
    """优化建议请求"""
    code: str
    language: str = "python"
    focus: Optional[str] = Field(default="performance", description="优化焦点: performance/readability/memory")


# ==========================================
# 辅助函数
# ==========================================
def get_api_config(session: Session) -> tuple:
    """获取 API 配置"""
    config = session.get(SystemConfig, 1)
    if not config:
        return settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL, settings.DEFAULT_MODEL

    api_key = config.openai_api_key or settings.OPENAI_API_KEY
    base_url = config.openai_base_url or settings.OPENAI_BASE_URL
    model_name = config.default_model or settings.DEFAULT_MODEL

    return api_key, base_url, model_name


# ==========================================
# POST /complete - AI 代码补全
# ==========================================
class CompletionResponse(BaseModel):
    """补全响应"""
    completion: str
    description: str


@router.post("/complete")
async def code_completion(
    request: CodeCompletionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    AI 代码补全

    根据当前代码上下文，提供智能补全建议
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    api_key, base_url, model_name = get_api_config(session)

    # 提取光标前的代码
    code_before_cursor = request.code[:request.cursor_position]
    code_after_cursor = request.code[request.cursor_position:]

    # 构建提示词
    language_map = {
        "python": "Python",
        "r": "R",
        "groovy": "Nextflow DSL2"
    }
    lang = language_map.get(request.language, request.language)

    system_prompt = f"""你是一个专业的{lang}代码助手，专门帮助生物信息学工程师编写分析代码。

你的任务是根据代码上下文，提供最合适的代码补全。

规则：
1. 只返回需要补全的代码，不要返回已有代码
2. 保持代码风格一致
3. 遵循生物信息学最佳实践
4. 如果是函数定义，补全函数体
5. 如果是注释，补全注释内容
6. 代码要简洁、高效、可读性好"""

    user_prompt = f"""请补全以下{lang}代码：

```{request.language}
{code_before_cursor}
<|CURSOR|>
{code_after_cursor}
```

{'上下文：' + request.context if request.context else ''}

请提供光标位置 <|CURSOR|> 处的代码补全。只返回需要补全的代码片段，不要包含已有代码。"""

    try:
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.2
        )

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        completion = response.content.strip()

        # 清理 markdown 代码块标记
        completion = re.sub(r'^```[\w]*\n?', '', completion)
        completion = re.sub(r'\n?```$', '', completion)

        log.info(f"🤖 [AIAssistant] 代码补全完成，用户: {current_user.id}")

        return CompletionResponse(
            completion=completion,
            description="AI 代码补全建议"
        )

    except Exception as e:
        log.error(f"🔥 [AIAssistant] 代码补全失败: {e}")
        return CompletionResponse(
            completion="",
            description=f"补全失败: {str(e)}"
        )


# ==========================================
# POST /review - AI 代码审查
# ==========================================
class ReviewResponse(BaseModel):
    """审查响应"""
    issues: List[Dict[str, Any]]
    suggestions: List[str]
    score: int
    summary: str


@router.post("/review", response_model=ReviewResponse)
async def code_review(
    request: CodeReviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    AI 代码审查

    分析代码质量，发现潜在问题，提供改进建议
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    import json

    api_key, base_url, model_name = get_api_config(session)

    language_map = {
        "python": "Python",
        "r": "R",
        "groovy": "Nextflow DSL2"
    }
    lang = language_map.get(request.language, request.language)

    system_prompt = f"""你是一个资深的{lang}代码审查专家，专门审查生物信息学分析代码。

请从以下维度审查代码：
1. **正确性**: 逻辑是否正确，边界条件处理
2. **健壮性**: 错误处理、异常捕获
3. **性能**: 算法效率、资源使用
4. **可读性**: 代码风格、命名规范
5. **安全性**: 输入验证、敏感信息处理
6. **生信规范**: 参数解析、输出格式、注释规范

返回 JSON 格式：
{{
    "issues": [
        {{"line": 行号, "severity": "high/medium/low", "type": "问题类型", "description": "问题描述", "suggestion": "修复建议"}}
    ],
    "suggestions": ["整体改进建议1", "整体改进建议2"],
    "score": 85,
    "summary": "整体评价摘要"
}}"""

    user_prompt = f"""请审查以下{lang}代码：

```{request.language}
{request.code}
```

请按 JSON 格式返回审查结果。"""

    try:
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.1
        )

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        content = response.content

        # 提取 JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            result = json.loads(content)

        log.info(f"🤖 [AIAssistant] 代码审查完成，用户: {current_user.id}")

        return ReviewResponse(
            issues=result.get("issues", []),
            suggestions=result.get("suggestions", []),
            score=result.get("score", 0),
            summary=result.get("summary", "")
        )

    except Exception as e:
        log.error(f"🔥 [AIAssistant] 代码审查失败: {e}")
        return ReviewResponse(
            issues=[],
            suggestions=[],
            score=0,
            summary=f"审查失败: {str(e)}"
        )


# ==========================================
# POST /diagnose - AI 错误诊断
# ==========================================
class DiagnosisResponse(BaseModel):
    """诊断响应"""
    root_cause: str
    solution: str
    fixed_code: Optional[str] = None
    references: List[str] = []


@router.post("/diagnose", response_model=DiagnosisResponse)
async def diagnose_error(
    request: ErrorDiagnosisRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    AI 错误诊断

    分析代码错误原因，提供修复方案
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    import json

    api_key, base_url, model_name = get_api_config(session)

    language_map = {
        "python": "Python",
        "r": "R",
        "groovy": "Nextflow DSL2"
    }
    lang = language_map.get(request.language, request.language)

    system_prompt = f"""你是一个{lang}错误诊断专家，帮助生物信息学工程师分析和修复代码错误。

请分析错误原因，并提供：
1. 根本原因分析
2. 详细的修复步骤
3. 修复后的完整代码（如果适用）
4. 相关参考文档或链接

返回 JSON 格式：
{{
    "root_cause": "错误的根本原因",
    "solution": "修复方案详细说明",
    "fixed_code": "修复后的完整代码（可选）",
    "references": ["参考链接1", "参考链接2"]
}}"""

    user_prompt = f"""请诊断以下{lang}代码错误：

代码：
```{request.language}
{request.code}
```

错误信息：
```
{request.error_message}
```

请分析错误原因并提供修复方案。"""

    try:
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.1
        )

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        content = response.content

        # 提取 JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            result = json.loads(content)

        log.info(f"🤖 [AIAssistant] 错误诊断完成，用户: {current_user.id}")

        return DiagnosisResponse(
            root_cause=result.get("root_cause", ""),
            solution=result.get("solution", ""),
            fixed_code=result.get("fixed_code"),
            references=result.get("references", [])
        )

    except Exception as e:
        log.error(f"🔥 [AIAssistant] 错误诊断失败: {e}")
        return DiagnosisResponse(
            root_cause=f"诊断失败: {str(e)}",
            solution="",
            references=[]
        )


# ==========================================
# POST /optimize - AI 代码优化建议
# ==========================================
class OptimizationResponse(BaseModel):
    """优化响应"""
    current_issues: List[str]
    optimizations: List[Dict[str, Any]]
    optimized_code: Optional[str] = None
    expected_improvement: str


@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_code(
    request: OptimizationRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    AI 代码优化

    分析代码并提供优化建议
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    import json

    api_key, base_url, model_name = get_api_config(session)

    language_map = {
        "python": "Python",
        "r": "R",
        "groovy": "Nextflow DSL2"
    }
    lang = language_map.get(request.language, request.language)

    focus_map = {
        "performance": "性能优化（执行速度、内存使用）",
        "readability": "可读性优化（代码风格、命名、注释）",
        "memory": "内存优化（减少内存占用）"
    }
    focus_desc = focus_map.get(request.focus, "综合优化")

    system_prompt = f"""你是一个{lang}代码优化专家，专门优化生物信息学分析代码。

优化焦点：{focus_desc}

请分析代码并提供：
1. 当前存在的问题
2. 具体的优化建议（包含优化前后的对比）
3. 优化后的完整代码
4. 预期的改进效果

返回 JSON 格式：
{{
    "current_issues": ["问题1", "问题2"],
    "optimizations": [
        {{"description": "优化描述", "before": "优化前代码片段", "after": "优化后代码片段", "benefit": "预期收益"}}
    ],
    "optimized_code": "优化后的完整代码",
    "expected_improvement": "预期改进效果描述"
}}"""

    user_prompt = f"""请优化以下{lang}代码：

```{request.language}
{request.code}
```

优化焦点：{focus_desc}"""

    try:
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.1
        )

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        content = response.content

        # 提取 JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            result = json.loads(content)

        log.info(f"🤖 [AIAssistant] 代码优化完成，用户: {current_user.id}")

        return OptimizationResponse(
            current_issues=result.get("current_issues", []),
            optimizations=result.get("optimizations", []),
            optimized_code=result.get("optimized_code"),
            expected_improvement=result.get("expected_improvement", "")
        )

    except Exception as e:
        log.error(f"🔥 [AIAssistant] 代码优化失败: {e}")
        return OptimizationResponse(
            current_issues=[f"优化失败: {str(e)}"],
            optimizations=[],
            expected_improvement=""
        )


log.info("✅ AI 代码辅助 API 已加载")