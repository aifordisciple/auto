"""
LLM 技能匹配器 - 使用 LLM 进行精准匹配和参数推断

功能:
1. match: 使用 LLM 进行精准意图识别和技能匹配
2. infer_parameters: 从用户查询中推断参数值
3. build_match_reason: 构建匹配原因说明

设计理念:
- 当规则匹配和向量搜索的置信度不足时，使用 LLM 进行精排
- LLM 可以理解复杂的自然语言需求，进行准确的技能推荐
- 支持参数推断，减少用户手动输入

触发条件:
- 规则匹配置信度 < 0.5
- 向量相似度 < 0.6
- 多个候选技能差距 < 0.1
- 用户查询包含复杂语义（问句、条件等）
"""

import os
import re
import json
import asyncio
from typing import Dict, List, Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logger import log
from app.core.database import engine
from sqlmodel import Session, select
from app.models.domain import SystemConfig, SkillAsset


class LLMSkillMatcher:
    """
    LLM 技能匹配器 - 使用 LLM 进行精准匹配和参数推断

    使用 LLM 进行高精度意图识别，适合在规则匹配和向量搜索
    置信度不足时进行精排。

    特点:
    1. 理解复杂自然语言需求
    2. 多技能比较和排序
    3. 参数值推断
    4. 匹配原因解释
    """

    # 默认 LLM 配置（当 SystemConfig 未配置时使用）
    DEFAULT_MODEL = "gpt-4o-mini"  # 使用性价比高的小模型
    DEFAULT_TIMEOUT = 15.0  # 超时时间（秒）- 增加以适应不同 API 响应速度
    DEFAULT_TEMPERATURE = 0.1  # 低温度确保输出稳定

    # 缓存配置
    CACHE_ENABLED = True
    CACHE_TTL = 3600  # 缓存有效期（秒）

    def __init__(self, session: Session = None):
        """
        初始化 LLM 匹配器

        Args:
            session: 数据库会话
        """
        self.session = session
        self._llm_client: Optional[ChatOpenAI] = None
        self._api_key: Optional[str] = None
        self._base_url: Optional[str] = None
        self._model_name: Optional[str] = None  # 缓存实际使用的模型名称
        self._cache: Dict[str, Dict] = {}  # 简单内存缓存

    def _init_llm_client(self) -> ChatOpenAI:
        """
        初始化 LLM 客户端

        从 SystemConfig 动态读取模型配置，支持阿里云 Dashscope 等
        非 OpenAI 官方 API。

        Returns:
            ChatOpenAI 实例
        """
        if self._llm_client:
            return self._llm_client

        try:
            # 从系统配置获取 API Key 和模型配置
            if self.session:
                config = self.session.exec(select(SystemConfig)).first()
            else:
                with Session(engine) as temp_session:
                    config = temp_session.exec(select(SystemConfig)).first()

            if config:
                self._api_key = config.openai_api_key
                self._base_url = config.openai_base_url
                # 关键修复：使用 SystemConfig 中的 default_model，而非硬编码
                self._model_name = config.default_model or self.DEFAULT_MODEL

            if not self._api_key:
                self._api_key = os.getenv("OPENAI_API_KEY")
                self._base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
                self._model_name = os.getenv("OPENAI_MODEL", self.DEFAULT_MODEL)

            if not self._api_key:
                raise ValueError("未配置 OpenAI API Key，无法使用 LLM 匹配")

            self._llm_client = ChatOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                model=self._model_name,  # 使用配置的模型
                temperature=self.DEFAULT_TEMPERATURE,
                timeout=self.DEFAULT_TIMEOUT
            )

            log.info(f"[LLMMatcher] 初始化 LLM 客户端: model={self._model_name}, base_url={self._base_url}")
            return self._llm_client

        except Exception as e:
            log.error(f"[LLMMatcher] 初始化 LLM 客户端失败: {e}")
            raise

    def _build_skill_summaries(self, skills: List[Dict[str, Any]], max_skills: int = 10) -> str:
        """
        构建技能摘要文本

        Args:
            skills: 技能列表
            max_skills: 最大技能数量

        Returns:
            技能摘要文本
        """
        summaries = []

        for i, skill in enumerate(skills[:max_skills]):
            skill_id = skill.get("skill_id", "")
            name = skill.get("name", "")
            description = skill.get("description", "") or ""

            # 截断描述
            desc_short = description[:100] + "..." if len(description) > 100 else description

            # 获取参数信息
            params_schema = skill.get("parameters_schema", {})
            properties = params_schema.get("properties", {})
            params = list(properties.keys())[:5]  # 只取前 5 个参数

            summaries.append(f"{i+1}. [{skill_id}] {name}: {desc_short}")
            if params:
                summaries.append(f"   参数: {', '.join(params)}")

        return "\n".join(summaries)

    def _build_match_prompt(
        self,
        user_query: str,
        candidate_skills: List[Dict[str, Any]],
        context: Optional[Dict] = None
    ) -> str:
        """
        构建匹配提示词

        Args:
            user_query: 用户查询
            candidate_skills: 候选技能列表
            context: 上下文信息

        Returns:
            提示词文本
        """
        skill_summaries = self._build_skill_summaries(candidate_skills)

        context_info = ""
        if context:
            if context.get("project_files"):
                context_info += f"\n项目文件: {', '.join(context['project_files'][:5])}"
            if context.get("previous_skills"):
                context_info += f"\n已用技能: {', '.join(context['previous_skills'][:3])}"

        prompt = f"""你是一个生物信息学技能匹配专家。请分析用户需求，从候选技能中选择最合适的技能。

用户输入: {user_query}

候选技能:
{skill_summaries}
{context_info}

任务:
1. 判断用户意图类型: explicit_skill(明确技能调用), implicit_skill(隐式技能需求), live_coding(需要自定义代码), general_question(知识问答)
2. 从候选技能中选择匹配的技能，按相关度排序
3. 推断可能的参数值（如果能从用户输入中推断）
4. 解释匹配原因

返回 JSON 格式:
{{
    "intent_type": "explicit_skill | implicit_skill | live_coding | general_question",
    "matched_skills": [
        {{
            "skill_id": "技能ID",
            "match_score": 0.9,
            "match_reason": "匹配原因"
        }}
    ],
    "confidence": 0.9,
    "parameters_suggestion": {{
        "参数名": "推断的值"
    }},
    "reasoning": "推理过程简述"
}}

只返回 JSON，不要其他内容。"""

        return prompt

    async def match(
        self,
        user_query: str,
        candidate_skills: List[Dict[str, Any]],
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        使用 LLM 进行精准匹配

        Args:
            user_query: 用户查询
            candidate_skills: 候选技能列表
            context: 上下文信息（项目文件、历史会话等）

        Returns:
            匹配结果:
            {
                "intent_type": "...",
                "matched_skills": [...],
                "confidence": 0.9,
                "parameters_suggestion": {...},
                "match_source": "llm",
                "reasoning": "..."
            }
        """
        # 检查缓存
        cache_key = self._get_cache_key(user_query, candidate_skills)
        if self.CACHE_ENABLED and cache_key in self._cache:
            cached = self._cache[cache_key]
            log.info(f"[LLMMatcher] 使用缓存结果: {cache_key[:20]}...")
            return cached

        try:
            # 初始化 LLM 客户端
            llm = self._init_llm_client()

            # 构建提示词
            prompt = self._build_match_prompt(user_query, candidate_skills, context)

            # 调用 LLM
            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=self.DEFAULT_TIMEOUT
            )

            # 解析响应
            content = response.content if hasattr(response, 'content') else str(response)

            # 提取 JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

                # 标准化结果格式
                result["match_source"] = "llm"

                # 确保必要字段存在
                if "intent_type" not in result:
                    result["intent_type"] = "implicit_skill"
                if "matched_skills" not in result:
                    result["matched_skills"] = []
                if "confidence" not in result:
                    result["confidence"] = 0.7
                if "parameters_suggestion" not in result:
                    result["parameters_suggestion"] = {}
                if "reasoning" not in result:
                    result["reasoning"] = "LLM 推理匹配"

                # 缓存结果
                if self.CACHE_ENABLED:
                    self._cache[cache_key] = result

                log.info(f"[LLMMatcher] 匹配成功: intent={result['intent_type']}, "
                        f"confidence={result['confidence']}, skills={len(result.get('matched_skills', []))}")

                return result

            else:
                log.warning("[LLMMatcher] 无法解析 LLM 响应")
                return self._get_default_result()

        except asyncio.TimeoutError:
            log.warning(f"[LLMMatcher] LLM 调用超时 ({self.DEFAULT_TIMEOUT}s)")
            return self._get_default_result()

        except json.JSONDecodeError as e:
            log.warning(f"[LLMMatcher] JSON 解析失败: {e}")
            return self._get_default_result()

        except Exception as e:
            log.error(f"[LLMMatcher] LLM 匹配失败: {e}")
            return self._get_default_result()

    def _get_cache_key(self, query: str, skills: List[Dict]) -> str:
        """生成缓存键"""
        skill_ids = [s.get("skill_id", "") for s in skills]
        return f"{query}:{','.join(skill_ids[:5])}"

    def _get_default_result(self) -> Dict[str, Any]:
        """获取默认结果"""
        return {
            "intent_type": "live_coding",
            "matched_skills": [],
            "confidence": 0.3,
            "parameters_suggestion": {},
            "match_source": "llm",
            "reasoning": "LLM 匹配失败，降级为默认结果"
        }

    async def infer_parameters(
        self,
        user_query: str,
        skill_id: str,
        skill_info: Dict[str, Any],
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        从用户查询中推断参数值

        Args:
            user_query: 用户查询
            skill_id: 技能 ID
            skill_info: 技能信息（包含参数 Schema）
            context: 上下文信息

        Returns:
            参数推断结果: {"param_name": "推断的值", ...}
        """
        try:
            llm = self._init_llm_client()

            # 获取参数定义
            params_schema = skill_info.get("parameters_schema", {})
            properties = params_schema.get("properties", {})

            if not properties:
                return {}

            # 构建参数推断提示词
            params_desc = []
            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "string")
                param_desc = param_info.get("description", "")
                param_default = param_info.get("default", "")
                params_desc.append(f"- {param_name} ({param_type}): {param_desc}")
                if param_default:
                    params_desc.append(f"  默认值: {param_default}")

            prompt = f"""从用户查询中推断技能参数值。

用户查询: {user_query}

技能: {skill_info.get('name', skill_id)}
参数定义:
{chr(10).join(params_desc)}

请根据用户查询推断参数值。如果无法从查询中推断，则不包含该参数。

返回 JSON 格式:
{{
    "参数名": "推断的值",
    ...
}}

只返回 JSON，不要其他内容。如果无法推断任何参数，返回 {{}}。"""

            # 调用 LLM
            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=3.0
            )

            # 解析响应
            content = response.content if hasattr(response, 'content') else str(response)
            json_match = re.search(r'\{.*\}', content, re.DOTALL)

            if json_match:
                result = json.loads(json_match.group())
                log.info(f"[LLMMatcher] 参数推断成功: skill_id={skill_id}, params={list(result.keys())}")
                return result

            return {}

        except Exception as e:
            log.error(f"[LLMMatcher] 参数推断失败: {e}")
            return {}

    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        log.info("[LLMMatcher] 缓存已清空")


# ==========================================
# 辅助函数
# ==========================================

async def match_with_llm(
    user_query: str,
    candidate_skills: List[Dict[str, Any]],
    context: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    使用 LLM 进行技能匹配（便捷函数）

    Args:
        user_query: 用户查询
        candidate_skills: 候选技能列表
        context: 上下文信息

    Returns:
        匹配结果
    """
    matcher = LLMSkillMatcher()
    return await matcher.match(user_query, candidate_skills, context)


async def infer_parameters_with_llm(
    user_query: str,
    skill_id: str,
    skill_info: Dict[str, Any],
    context: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    使用 LLM 推断参数（便捷函数）

    Args:
        user_query: 用户查询
        skill_id: 技能 ID
        skill_info: 技能信息
        context: 上下文信息

    Returns:
        参数推断结果
    """
    matcher = LLMSkillMatcher()
    return await matcher.infer_parameters(user_query, skill_id, skill_info, context)


log.info("✅ LLM 技能匹配器已加载")