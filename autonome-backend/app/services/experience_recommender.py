"""
经验推荐器 - 语义搜索与智能推荐经验资产
"""

import json
from typing import Dict, List, Optional
from sqlmodel import Session, select
from sqlalchemy import text
from langchain_openai import OpenAIEmbeddings

from app.models.domain import ExperienceAsset, SystemConfig
from app.core.logger import log


class ExperienceRecommender:
    """
    经验推荐服务类

    使用向量语义搜索找到与用户查询相关的历史成功经验，
    支持私有经验和公开经验的混合检索。
    """

    def __init__(self, db: Session):
        self.db = db
        self._init_embeddings()

    def _init_embeddings(self):
        """初始化 Embeddings 模型"""
        config = self.db.get(SystemConfig, 1)
        if not config:
            raise ValueError("系统配置未找到")

        api_key = config.openai_api_key if config and config.openai_api_key else "ollama-local"
        base_url = config.openai_base_url if config and config.openai_base_url else "http://localhost:11434/v1"

        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=api_key,
            base_url=base_url
        )

    async def recommend(
        self,
        user_query: str,
        user_id: int,
        top_k: int = 3,
        min_similarity: float = 0.7
    ) -> List[Dict]:
        """
        推荐相关的经验资产

        Args:
            user_query: 用户查询文本
            user_id: 用户 ID
            top_k: 返回数量
            min_similarity: 最小相似度阈值

        Returns:
            推荐的经验列表，每项包含：
            {
                "experience_id": str,
                "title": str,
                "summary": str,
                "similarity": float,
                "solution_code": str,
                "key_insights": list,
                "category": str
            }
        """
        log.info(f"🎯 [ExperienceRecommender] 开始推荐，用户查询: {user_query[:50]}...")

        try:
            # 1. 生成查询向量
            query_embedding = self.embeddings.embed_query(user_query)

            # 2. 向量检索
            results = await self._vector_search(query_embedding, user_id, top_k + 2)

            # 3. 过滤低相关性结果
            filtered_results = [
                r for r in results
                if r.get("similarity", 0) >= min_similarity
            ]

            # 4. 返回 Top-K
            recommendations = filtered_results[:top_k]

            log.info(
                f"✅ [ExperienceRecommender] 找到 {len(recommendations)} 条相关经验"
            )

            return recommendations

        except Exception as e:
            log.error(f"❌ [ExperienceRecommender] 推荐失败: {e}")
            return []

    async def _vector_search(
        self,
        query_embedding: List[float],
        user_id: int,
        limit: int
    ) -> List[Dict]:
        """
        执行向量搜索

        使用 pgvector 的余弦距离操作符 <=> 进行相似度搜索
        """
        try:
            # 将向量转换为字符串格式
            embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

            # 使用原生 SQL 进行向量搜索
            # 搜索条件：用户自己的经验 OR 公开的经验
            # 排除低质量经验（usefulness_score < 0.3）
            sql = text("""
                SELECT
                    experience_id,
                    title,
                    summary,
                    solution_code,
                    key_insights,
                    category,
                    tags,
                    usefulness_score,
                    reuse_count,
                    1 - (summary_embedding <=> :embedding::vector) as similarity
                FROM experienceasset
                WHERE (source_user_id = :user_id OR is_public = true)
                    AND usefulness_score >= 0.3
                ORDER BY summary_embedding <=> :embedding::vector
                LIMIT :limit
            """)

            result = self.db.execute(
                sql,
                {"embedding": embedding_str, "user_id": user_id, "limit": limit}
            )

            rows = result.fetchall()

            # 格式化结果
            experiences = []
            for row in rows:
                experiences.append({
                    "experience_id": row[0],
                    "title": row[1],
                    "summary": row[2],
                    "solution_code": row[3],
                    "key_insights": row[4] or [],
                    "category": row[5],
                    "tags": row[6] or [],
                    "usefulness_score": float(row[7]) if row[7] else 0.0,
                    "reuse_count": row[8] or 0,
                    "similarity": round(float(row[9]), 3) if row[9] else 0.0
                })

            return experiences

        except Exception as e:
            log.error(f"向量搜索失败: {e}")
            return []

    def format_for_agent(self, recommendations: List[Dict]) -> str:
        """
        格式化推荐结果为 Agent 可用的上下文

        Args:
            recommendations: 推荐列表

        Returns:
            格式化的字符串，用于注入 Agent prompt
        """
        if not recommendations:
            return ""

        lines = ["【🧠 智能经验推荐 - 检测到相似历史成功案例】"]

        for i, rec in enumerate(recommendations, 1):
            lines.append(f"\n### 推荐 {i} (相似度: {rec['similarity']:.0%})")
            lines.append(f"- **标题**: {rec['title']}")
            lines.append(f"- **摘要**: {rec['summary'][:200]}...")

            if rec.get('key_insights'):
                lines.append(f"- **关键洞察**: {', '.join(rec['key_insights'][:3])}")

            if rec.get('solution_code'):
                code_preview = rec['solution_code'][:500]
                lines.append(f"- **解决方案代码片段**:\n```\n{code_preview}\n```")

            lines.append(f"- **分类**: {rec['category']}")

        lines.append("\n**💡 建议**: 参考上述成功经验，可以更快地解决用户问题。如果相似度很高(>0.8)，优先复用已验证的解决方案。")

        return "\n".join(lines)

    def format_for_json(self, recommendations: List[Dict]) -> str:
        """
        格式化推荐结果为 JSON 代码块，用于前端渲染

        Args:
            recommendations: 推荐列表

        Returns:
            JSON 代码块字符串
        """
        if not recommendations:
            return ""

        # 简化输出，只保留前端需要的字段
        simplified = []
        for rec in recommendations:
            simplified.append({
                "experience_id": rec["experience_id"],
                "title": rec["title"],
                "summary": rec["summary"][:150] + "..." if len(rec["summary"]) > 150 else rec["summary"],
                "similarity": rec["similarity"],
                "category": rec["category"],
                "tags": rec.get("tags", [])[:3]
            })

        return f"```recommended_experiences\n{json.dumps(simplified, ensure_ascii=False, indent=2)}\n```"

    async def search_by_keywords(
        self,
        keywords: List[str],
        user_id: int,
        top_k: int = 5
    ) -> List[Dict]:
        """
        关键词搜索（非向量搜索的备选方案）

        Args:
            keywords: 关键词列表
            user_id: 用户 ID
            top_k: 返回数量

        Returns:
            匹配的经验列表
        """
        try:
            # 构建搜索条件
            search_conditions = []
            for kw in keywords:
                search_conditions.append(
                    f"(title ILIKE '%{kw}%' OR summary ILIKE '%{kw}%' OR tags::text ILIKE '%{kw}%')"
                )

            where_clause = " OR ".join(search_conditions)

            sql = text(f"""
                SELECT
                    experience_id,
                    title,
                    summary,
                    solution_code,
                    key_insights,
                    category,
                    tags,
                    usefulness_score,
                    reuse_count
                FROM experienceasset
                WHERE ({where_clause})
                    AND (source_user_id = :user_id OR is_public = true)
                    AND usefulness_score >= 0.3
                ORDER BY usefulness_score DESC, reuse_count DESC
                LIMIT :limit
            """)

            result = self.db.execute(
                sql,
                {"user_id": user_id, "limit": top_k}
            )

            rows = result.fetchall()

            experiences = []
            for row in rows:
                experiences.append({
                    "experience_id": row[0],
                    "title": row[1],
                    "summary": row[2],
                    "solution_code": row[3],
                    "key_insights": row[4] or [],
                    "category": row[5],
                    "tags": row[6] or [],
                    "usefulness_score": float(row[7]) if row[7] else 0.0,
                    "reuse_count": row[8] or 0,
                    "similarity": 0.0  # 关键词搜索无相似度
                })

            return experiences

        except Exception as e:
            log.error(f"关键词搜索失败: {e}")
            return []

    def record_reuse(self, experience_id: str, was_helpful: Optional[bool] = None) -> bool:
        """
        记录经验被复用，并更新评分

        Args:
            experience_id: 经验 ID
            was_helpful: 是否有帮助（可选，用于调整评分）

        Returns:
            是否成功更新
        """
        try:
            experience = self.db.exec(
                select(ExperienceAsset).where(ExperienceAsset.experience_id == experience_id)
            ).first()

            if not experience:
                return False

            # 增加复用次数
            experience.reuse_count += 1

            # 根据反馈调整评分
            if was_helpful is not None:
                if was_helpful:
                    experience.usefulness_score = min(
                        experience.usefulness_score + 0.05, 1.0
                    )
                else:
                    experience.usefulness_score = max(
                        experience.usefulness_score - 0.1, 0.0
                    )

            self.db.commit()
            return True

        except Exception as e:
            log.error(f"记录复用失败: {e}")
            return False


class FeedbackProcessor:
    """反馈处理器 - 处理用户对经验资产的反馈"""

    def __init__(self, db: Session):
        self.db = db

    def process_feedback(
        self,
        experience_id: str,
        was_helpful: bool,
        user_id: int,
        comment: Optional[str] = None
    ) -> Dict:
        """
        处理用户反馈

        Args:
            experience_id: 经验 ID
            was_helpful: 是否有帮助
            user_id: 用户 ID
            comment: 反馈评论（可选）

        Returns:
            {
                "success": bool,
                "new_score": float,
                "message": str
            }
        """
        result = {
            "success": False,
            "new_score": 0.0,
            "message": ""
        }

        try:
            experience = self.db.exec(
                select(ExperienceAsset).where(ExperienceAsset.experience_id == experience_id)
            ).first()

            if not experience:
                result["message"] = "经验资产不存在"
                return result

            old_score = experience.usefulness_score

            # 调整评分
            if was_helpful:
                new_score = min(old_score + 0.05, 1.0)
                result["message"] = "感谢您的反馈！已提升该经验的有用性评分。"
            else:
                new_score = max(old_score - 0.1, 0.0)
                result["message"] = "感谢您的反馈！我们会持续改进推荐质量。"

            experience.usefulness_score = new_score

            # 如果持续负面反馈，自动降权
            if new_score < 0.3:
                log.warning(f"经验 {experience_id} 评分过低，将被隐藏")

            self.db.commit()

            result["success"] = True
            result["new_score"] = new_score

            log.info(
                f"📝 [FeedbackProcessor] 处理反馈: {experience_id}, "
                f"有帮助={was_helpful}, 新评分={new_score:.2f}"
            )

            return result

        except Exception as e:
            log.error(f"处理反馈失败: {e}")
            result["message"] = f"处理失败: {str(e)}"
            return result