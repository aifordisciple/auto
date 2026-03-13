"""
知识提取器 - 从成功会话中提取结构化知识资产
"""

import json
from typing import Dict, List, Optional
from sqlmodel import Session, select
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.models.domain import (
    ChatSession, ChatMessage, RoleEnum, ExperienceAsset,
    ExperienceAssetCreate, ExperienceType, SystemConfig, Project
)
from app.core.logger import log


class KnowledgeExtractor:
    """
    从成功会话中提取知识资产的服务类

    使用 LLM 分析对话历史，提取有价值的知识资产，
    包括标题、摘要、关键洞察、解决方案代码等。
    """

    # LLM 提取 Prompt
    EXTRACTION_PROMPT = """你是一个专业的生物信息学知识提取专家。请分析以下成功的对话会话，提取有价值的知识资产。

## 对话历史
{conversation_text}

## 提取要求
请分析这段对话，提取以下信息并以 JSON 格式输出：

1. **title**: 经验标题（简短概括，不超过50字）
2. **summary**: 经验摘要（描述用户需求 + 解决方案，100-200字）
3. **key_insights**: 关键洞察列表（3-5个关键要点，每个不超过50字）
4. **original_query**: 用户原始问题（用户最初的分析需求）
5. **solution_code**: 核心解决方案代码（如果有的话，提取关键代码片段）
6. **solution_strategy**: 解决策略描述（简述分析思路和方法）
7. **category**: 经验分类，从以下选项中选择：
   - "qc": 质量控制相关
   - "analysis": 数据分析相关
   - "visualization": 可视化相关
   - "pipeline": 流程相关
   - "general": 通用/其他
8. **tags**: 标签列表（3-5个相关标签）

## 输出格式
请严格按照以下 JSON 格式输出，不要添加任何其他文字：
```json
{{
    "title": "...",
    "summary": "...",
    "key_insights": ["...", "..."],
    "original_query": "...",
    "solution_code": "...",
    "solution_strategy": "...",
    "category": "...",
    "tags": ["...", "..."]
}}
```
"""

    def __init__(self, db: Session):
        self.db = db
        self._init_llm()

    def _init_llm(self):
        """初始化 LLM 和 Embeddings"""
        config = self.db.get(SystemConfig, 1)
        if not config:
            raise ValueError("系统配置未找到")

        api_key = config.openai_api_key if config and config.openai_api_key else "ollama-local"
        base_url = config.openai_base_url if config and config.openai_base_url else "http://localhost:11434/v1"

        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model="gpt-4o-mini",
            temperature=0.1
        )

        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=api_key,
            base_url=base_url
        )

    async def extract_from_session(
        self,
        session_id: str,
        user_id: int,
        project_id: Optional[str] = None
    ) -> Optional[ExperienceAsset]:
        """
        从会话中提取经验资产

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            project_id: 项目 ID（可选）

        Returns:
            ExperienceAsset 实例，提取失败返回 None
        """
        log.info(f"🔍 [KnowledgeExtractor] 开始提取会话 {session_id} 的知识资产")

        try:
            # 1. 获取会话消息
            messages = self._get_session_messages(session_id)
            if not messages:
                log.warning(f"会话 {session_id} 无消息，跳过提取")
                return None

            # 2. 构建对话文本
            conversation_text = self._build_conversation_text(messages)

            # 3. 调用 LLM 提取结构化知识
            extraction_result = await self._extract_with_llm(conversation_text)
            if not extraction_result:
                log.warning(f"会话 {session_id} LLM 提取失败")
                return None

            # 4. 生成向量嵌入
            text_to_embed = f"{extraction_result['title']} {extraction_result['summary']}"
            embedding = self.embeddings.embed_query(text_to_embed)

            # 5. 创建 ExperienceAsset
            experience = ExperienceAsset(
                source_session_id=session_id,
                source_user_id=user_id,
                source_project_id=project_id,
                experience_type=ExperienceType.SUCCESSFUL_SESSION,
                title=extraction_result["title"],
                summary=extraction_result["summary"],
                key_insights=extraction_result.get("key_insights", []),
                original_query=extraction_result.get("original_query", ""),
                solution_code=extraction_result.get("solution_code"),
                solution_strategy=extraction_result.get("solution_strategy"),
                category=extraction_result.get("category", "general"),
                tags=extraction_result.get("tags", []),
                summary_embedding=embedding,
                is_public=False,  # 默认私有
                is_verified=False
            )

            # 6. 保存到数据库
            self.db.add(experience)
            self.db.commit()
            self.db.refresh(experience)

            log.info(f"✅ [KnowledgeExtractor] 成功提取经验资产: {experience.experience_id}")
            return experience

        except Exception as e:
            log.error(f"❌ [KnowledgeExtractor] 提取失败: {e}")
            self.db.rollback()
            return None

    def _get_session_messages(self, session_id: str) -> List[ChatMessage]:
        """获取会话所有消息"""
        return self.db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        ).all()

    def _build_conversation_text(self, messages: List[ChatMessage]) -> str:
        """构建对话文本"""
        lines = []
        for msg in messages:
            role = "用户" if msg.role == RoleEnum.user else "助手"
            # 截断过长的消息
            content = msg.content[:2000] if len(msg.content) > 2000 else msg.content
            lines.append(f"【{role}】: {content}")

        return "\n\n".join(lines)

    async def _extract_with_llm(self, conversation_text: str) -> Optional[Dict]:
        """使用 LLM 提取结构化知识"""
        try:
            prompt = self.EXTRACTION_PROMPT.format(conversation_text=conversation_text)

            response = await self.llm.ainvoke(prompt)
            content = response.content

            # 提取 JSON 块
            json_str = self._extract_json_from_response(content)
            if not json_str:
                log.warning("LLM 响应中未找到有效 JSON")
                return None

            result = json.loads(json_str)

            # 验证必要字段
            required_fields = ["title", "summary"]
            for field in required_fields:
                if field not in result:
                    log.warning(f"LLM 响应缺少必要字段: {field}")
                    return None

            return result

        except json.JSONDecodeError as e:
            log.error(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            log.error(f"LLM 调用失败: {e}")
            return None

    def _extract_json_from_response(self, response: str) -> Optional[str]:
        """从响应中提取 JSON 块"""
        # 尝试提取 ```json ... ``` 块
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()

        # 尝试提取 ``` ... ``` 块
        if "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()

        # 尝试直接解析整个响应
        if response.strip().startswith("{"):
            return response.strip()

        return None

    async def extract_batch(
        self,
        session_ids: List[str],
        user_id: int
    ) -> List[ExperienceAsset]:
        """
        批量提取多个会话的知识资产

        Args:
            session_ids: 会话 ID 列表
            user_id: 用户 ID

        Returns:
            成功提取的经验资产列表
        """
        results = []
        for session_id in session_ids:
            experience = await self.extract_from_session(session_id, user_id)
            if experience:
                results.append(experience)

        log.info(f"📊 [KnowledgeExtractor] 批量提取完成: {len(results)}/{len(session_ids)}")
        return results

    def update_embedding(self, experience_id: str) -> bool:
        """更新经验资产的向量嵌入"""
        try:
            experience = self.db.exec(
                select(ExperienceAsset).where(ExperienceAsset.experience_id == experience_id)
            ).first()

            if not experience:
                return False

            text_to_embed = f"{experience.title} {experience.summary}"
            embedding = self.embeddings.embed_query(text_to_embed)

            experience.summary_embedding = embedding
            self.db.commit()

            return True

        except Exception as e:
            log.error(f"更新嵌入失败: {e}")
            return False