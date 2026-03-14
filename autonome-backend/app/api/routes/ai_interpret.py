"""
结果智能解读 API - 提供分析结果的 AI 智能解读

核心端点:
- POST /interpret: 解读分析结果
- POST /interpret/chart: 解读图表
- POST /interpret/table: 解读数据表格
"""

import re
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
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
class InterpretRequest(BaseModel):
    """结果解读请求"""
    result_type: str = Field(description="结果类型: chart/table/text/file_list")
    result_content: str = Field(description="结果内容")
    analysis_type: Optional[str] = Field(default=None, description="分析类型: deg/qc/clustering/visualization")
    context: Optional[str] = Field(default=None, description="分析上下文")


class ChartInterpretRequest(BaseModel):
    """图表解读请求"""
    chart_type: str = Field(description="图表类型: volcano/heatmap/scatter/bar/line/umap")
    chart_data: Dict[str, Any] = Field(description="图表数据")
    analysis_context: Optional[str] = Field(default=None)


class TableInterpretRequest(BaseModel):
    """表格解读请求"""
    headers: List[str]
    rows: List[List[Any]]
    analysis_type: Optional[str] = Field(default=None)


# ==========================================
# 响应模型
# ==========================================
class InterpretationResponse(BaseModel):
    """解读响应"""
    summary: str
    key_findings: List[str]
    recommendations: List[str]
    detailed_analysis: str


class ChartInterpretResponse(BaseModel):
    """图表解读响应"""
    chart_description: str
    key_observations: List[str]
    statistical_insights: List[str]
    biological_meaning: str
    recommendations: List[str]


class TableInterpretResponse(BaseModel):
    """表格解读响应"""
    overview: str
    statistics: Dict[str, Any]
    notable_values: List[Dict[str, Any]]
    patterns: List[str]


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
# POST /interpret - 综合结果解读
# ==========================================
@router.post("/interpret", response_model=InterpretationResponse)
async def interpret_result(
    request: InterpretRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    AI 智能解读分析结果

    根据结果类型提供专业的生物学解读
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    import json

    api_key, base_url, model_name = get_api_config(session)

    analysis_context = request.analysis_type or "生物信息学分析"
    context = request.context or ""

    system_prompt = f"""你是一个资深的生物信息学专家，专门解读各类分析结果。

你熟悉以下分析类型：
- 差异基因分析 (DEG)
- 质量控制 (QC)
- 聚类分析 (Clustering)
- 单细胞分析 (scRNA-seq)
- 功能富集分析 (GO/KEGG)
- 变异分析 (Variant Calling)

请提供专业、准确、易懂的结果解读，包括：
1. 结果摘要
2. 关键发现
3. 后续分析建议
4. 详细分析

返回 JSON 格式：
{{
    "summary": "结果摘要（2-3句话）",
    "key_findings": ["关键发现1", "关键发现2"],
    "recommendations": ["建议1", "建议2"],
    "detailed_analysis": "详细分析"
}}"""

    user_prompt = f"""请解读以下{analysis_context}结果：

结果类型: {request.result_type}
结果内容:
{request.result_content}

{f'分析上下文: {context}' if context else ''}

请提供专业的生物学解读。"""

    try:
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.3
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

        log.info(f"🧬 [AIInterpret] 结果解读完成，用户: {current_user.id}")

        return InterpretationResponse(
            summary=result.get("summary", ""),
            key_findings=result.get("key_findings", []),
            recommendations=result.get("recommendations", []),
            detailed_analysis=result.get("detailed_analysis", "")
        )

    except Exception as e:
        log.error(f"🔥 [AIInterpret] 结果解读失败: {e}")
        return InterpretationResponse(
            summary=f"解读失败: {str(e)}",
            key_findings=[],
            recommendations=[],
            detailed_analysis=""
        )


# ==========================================
# POST /interpret/chart - 图表解读
# ==========================================
@router.post("/interpret/chart", response_model=ChartInterpretResponse)
async def interpret_chart(
    request: ChartInterpretRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    AI 图表解读

    专业解读各类分析图表
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    import json

    api_key, base_url, model_name = get_api_config(session)

    chart_contexts = {
        "volcano": "差异基因火山图，展示基因的差异表达显著性",
        "heatmap": "表达热图，展示基因/样本的表达模式",
        "scatter": "散点图，展示变量间关系",
        "bar": "条形图，展示分类数据统计",
        "line": "折线图，展示趋势变化",
        "umap": "UMAP 降维图，展示样本/细胞分布"
    }

    chart_desc = chart_contexts.get(request.chart_type, "数据可视化图表")

    system_prompt = f"""你是一个生物信息学可视化专家，专门解读各类分析图表。

当前图表类型: {request.chart_type} - {chart_desc}

请提供：
1. 图表描述
2. 关键观察点
3. 统计见解
4. 生物学意义
5. 后续建议

返回 JSON 格式：
{{
    "chart_description": "图表内容描述",
    "key_observations": ["观察点1", "观察点2"],
    "statistical_insights": ["统计见解1"],
    "biological_meaning": "生物学意义解释",
    "recommendations": ["后续建议"]
}}"""

    user_prompt = f"""请解读以下{request.chart_type}图表：

图表数据:
{request.chart_data}

{f'分析上下文: {request.analysis_context}' if request.analysis_context else ''}

请提供专业的图表解读。"""

    try:
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=0.3
        )

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        content = response.content

        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            result = json.loads(content)

        log.info(f"🧬 [AIInterpret] 图表解读完成: {request.chart_type}")

        return ChartInterpretResponse(
            chart_description=result.get("chart_description", ""),
            key_observations=result.get("key_observations", []),
            statistical_insights=result.get("statistical_insights", []),
            biological_meaning=result.get("biological_meaning", ""),
            recommendations=result.get("recommendations", [])
        )

    except Exception as e:
        log.error(f"🔥 [AIInterpret] 图表解读失败: {e}")
        return ChartInterpretResponse(
            chart_description=f"解读失败: {str(e)}",
            key_observations=[],
            statistical_insights=[],
            biological_meaning="",
            recommendations=[]
        )


# ==========================================
# POST /interpret/table - 表格解读
# ==========================================
@router.post("/interpret/table", response_model=TableInterpretResponse)
async def interpret_table(
    request: TableInterpretRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    AI 表格数据解读

    解读表格数据，发现关键模式和异常值
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    import json

    api_key, base_url, model_name = get_api_config(session)

    # 格式化表格
    table_str = "| " + " | ".join(request.headers) + " |\n"
    table_str += "| " + " | ".join(["---"] * len(request.headers)) + " |\n"
    for row in request.rows[:20]:  # 限制行数
        table_str += "| " + " | ".join(str(v) for v in row) + " |\n"

    analysis_type = request.analysis_type or "数据表格"

    system_prompt = f"""你是一个生物信息学数据分析专家，专门解读各类分析结果表格。

请分析表格数据并提供：
1. 数据概览
2. 关键统计信息
3. 值得关注的数值
4. 数据模式

返回 JSON 格式：
{{
    "overview": "数据概览",
    "statistics": {{"指标": 值}},
    "notable_values": [{{"row": 行, "column": 列, "value": 值, "reason": "关注原因"}}],
    "patterns": ["发现的模式1"]
}}"""

    user_prompt = f"""请解读以下{analysis_type}表格：

{table_str}

请分析数据并提供专业解读。"""

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

        content = response.content

        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            result = json.loads(content)

        log.info(f"🧬 [AIInterpret] 表格解读完成")

        return TableInterpretResponse(
            overview=result.get("overview", ""),
            statistics=result.get("statistics", {}),
            notable_values=result.get("notable_values", []),
            patterns=result.get("patterns", [])
        )

    except Exception as e:
        log.error(f"🔥 [AIInterpret] 表格解读失败: {e}")
        return TableInterpretResponse(
            overview=f"解读失败: {str(e)}",
            statistics={},
            notable_values=[],
            patterns=[]
        )


log.info("✅ 结果智能解读 API 已加载")