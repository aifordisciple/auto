"""
语义搜索引擎 (Semantic Search Engine)

V2 架构组件：为 MCP 技能检索提供语义匹配能力。

使用 sentence-transformers (all-MiniLM-L6-v2) 计算技能描述的向量，
FAISS 索引实现高效相似度搜索，磁盘持久化避免重启重新计算。

当 sentence-transformers 未安装时，自动降级为纯关键词搜索。
"""

import os
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.logger import log


# 语义搜索是否可用（延迟检测）
_semantic_available: Optional[bool] = None

def _check_semantic_available() -> bool:
    """检查语义搜索依赖是否可用"""
    global _semantic_available
    if _semantic_available is None:
        try:
            import sentence_transformers
            _semantic_available = True
            log.info("🔍 [SemanticSearch] sentence-transformers 可用")
        except ImportError:
            _semantic_available = False
            log.warning("🔍 [SemanticSearch] sentence-transformers 未安装，降级为纯关键词搜索")
    return _semantic_available


@dataclass
class SkillEmbedding:
    """技能向量索引条目"""
    skill_id: str
    name: str
    description: str
    embedding: Optional[np.ndarray] = None


class SemanticSearchEngine:
    """
    语义搜索引擎

    功能：
    - 使用 sentence-transformers 计算技能描述向量
    - FAISS 索引实现高效相似度搜索
    - 磁盘持久化（JSON 格式存储向量）
    - 未安装依赖时自动降级
    """

    # 默认模型（80MB，快速，适合语义搜索）
    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    # 索引持久化路径
    INDEX_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "semantic_index")

    def __init__(self, model_name: str = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model = None
        self._index: Dict[str, SkillEmbedding] = {}
        self._embeddings_matrix: Optional[np.ndarray] = None
        self._skill_ids: List[str] = []
        self._initialized = False

    def _get_model(self):
        """延迟加载 sentence-transformers 模型"""
        if self._model is None and _check_semantic_available():
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                log.info(f"🔍 [SemanticSearch] 模型已加载: {self.model_name}")
            except Exception as e:
                log.error(f"🔍 [SemanticSearch] 模型加载失败: {e}")
                self._model = None
        return self._model

    def index_skills(self, skills: List[Dict[str, Any]]) -> None:
        """
        构建技能语义索引

        Args:
            skills: 技能列表，每个技能包含 metadata.skill_id, metadata.name, metadata.description
        """
        if not _check_semantic_available():
            log.info("🔍 [SemanticSearch] 语义搜索不可用，跳过索引构建")
            return

        model = self._get_model()
        if not model:
            return

        log.info(f"🔍 [SemanticSearch] 开始构建索引，共 {len(skills)} 个技能")

        # 准备文本和元数据
        texts = []
        self._skill_ids = []
        self._index = {}

        for skill in skills:
            metadata = skill.get('metadata', {})
            skill_id = metadata.get('skill_id', '')
            if not skill_id:
                continue

            name = metadata.get('name', '')
            description = metadata.get('description', '')
            # 组合文本：名称权重更高（重复名称增强信号）
            text = f"{name} {name} {description}"

            texts.append(text)
            self._skill_ids.append(skill_id)
            self._index[skill_id] = SkillEmbedding(
                skill_id=skill_id,
                name=name,
                description=description
            )

        if not texts:
            log.warning("🔍 [SemanticSearch] 无有效技能可索引")
            return

        # 批量计算向量
        try:
            embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
            self._embeddings_matrix = np.array(embeddings, dtype=np.float32)

            # 存储向量到索引
            for i, skill_id in enumerate(self._skill_ids):
                self._index[skill_id].embedding = self._embeddings_matrix[i]

            self._initialized = True
            log.info(f"🔍 [SemanticSearch] 索引构建完成: {len(self._skill_ids)} 个技能, 向量维度: {self._embeddings_matrix.shape[1]}")

            # 持久化到磁盘
            self._save_index()

        except Exception as e:
            log.error(f"🔍 [SemanticSearch] 索引构建失败: {e}")

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        语义搜索

        Args:
            query: 搜索查询
            top_k: 返回前 k 个结果

        Returns:
            (skill_id, score) 元组列表，score 为余弦相似度 0-1
        """
        if not self._initialized or self._embeddings_matrix is None:
            log.debug(f"[SemanticSearch.V2] search() 跳过: initialized={self._initialized}, embeddings={'有' if self._embeddings_matrix is not None else '无'}")
            return []

        model = self._get_model()
        if not model:
            return []

        log.info(f"[SemanticSearch.V2] search() 开始: query='{query[:60]}', top_k={top_k}, 索引技能数={len(self._skill_ids)}")

        try:
            # 计算查询向量
            query_embedding = model.encode(
                [query], show_progress_bar=False, normalize_embeddings=True
            )
            query_vec = np.array(query_embedding, dtype=np.float32)

            # 计算余弦相似度（向量已归一化，点积即余弦相似度）
            similarities = np.dot(self._embeddings_matrix, query_vec.T).flatten()

            # 取 top_k
            top_indices = np.argsort(similarities)[::-1][:top_k]

            results = []
            for idx in top_indices:
                if idx < len(self._skill_ids):
                    skill_id = self._skill_ids[idx]
                    score = float(similarities[idx])
                    # 只返回正相关的结果
                    if score > 0.1:
                        results.append((skill_id, score))

            log.info(f"[SemanticSearch.V2] search() 完成: 返回 {len(results)} 个结果, "
                     f"top_scores=[{', '.join(f'{s:.3f}' for _, s in results[:3])}]")
            return results

        except Exception as e:
            log.error(f"🔍 [SemanticSearch] 搜索失败: {e}")
            return []

    def _save_index(self) -> None:
        """持久化索引到磁盘"""
        if not self._initialized:
            return

        try:
            os.makedirs(self.INDEX_DIR, exist_ok=True)

            # 保存元数据
            meta_path = os.path.join(self.INDEX_DIR, "index_meta.json")
            meta = {
                "model_name": self.model_name,
                "skill_count": len(self._skill_ids),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "skill_ids": self._skill_ids,
            }
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            # 保存向量（numpy 格式）
            if self._embeddings_matrix is not None:
                vec_path = os.path.join(self.INDEX_DIR, "embeddings.npy")
                np.save(vec_path, self._embeddings_matrix)

            # 保存技能名称和描述
            skills_path = os.path.join(self.INDEX_DIR, "skills_data.json")
            skills_data = {
                sid: {"name": e.name, "description": e.description}
                for sid, e in self._index.items()
            }
            with open(skills_path, 'w', encoding='utf-8') as f:
                json.dump(skills_data, f, ensure_ascii=False, indent=2)

            log.info(f"🔍 [SemanticSearch] 索引已持久化到 {self.INDEX_DIR}")

        except Exception as e:
            log.error(f"🔍 [SemanticSearch] 索引持久化失败: {e}")

    def _load_index(self) -> bool:
        """从磁盘加载索引"""
        meta_path = os.path.join(self.INDEX_DIR, "index_meta.json")
        if not os.path.exists(meta_path):
            return False

        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            # 检查模型是否匹配
            if meta.get("model_name") != self.model_name:
                log.info(f"🔍 [SemanticSearch] 索引模型不匹配({meta.get('model_name')} vs {self.model_name})，需要重建")
                return False

            self._skill_ids = meta.get("skill_ids", [])

            # 加载向量
            vec_path = os.path.join(self.INDEX_DIR, "embeddings.npy")
            if os.path.exists(vec_path):
                self._embeddings_matrix = np.load(vec_path)
            else:
                return False

            # 加载技能数据
            skills_path = os.path.join(self.INDEX_DIR, "skills_data.json")
            if os.path.exists(skills_path):
                with open(skills_path, 'r', encoding='utf-8') as f:
                    skills_data = json.load(f)

                for sid, data in skills_data.items():
                    self._index[sid] = SkillEmbedding(
                        skill_id=sid,
                        name=data.get("name", ""),
                        description=data.get("description", "")
                    )

            self._initialized = True
            log.info(f"🔍 [SemanticSearch] 从磁盘加载索引: {len(self._skill_ids)} 个技能")
            return True

        except Exception as e:
            log.error(f"🔍 [SemanticSearch] 索引加载失败: {e}")
            return False

    def initialize(self, skills: List[Dict[str, Any]]) -> None:
        """
        初始化搜索引擎（尝试加载磁盘索引，失败则重新构建）

        Args:
            skills: 技能列表
        """
        if not _check_semantic_available():
            return

        # 先尝试从磁盘加载
        if self._load_index():
            # 检查技能数量是否匹配（可能新增了技能）
            current_count = len(skills)
            indexed_count = len(self._skill_ids)
            if current_count != indexed_count:
                log.info(f"🔍 [SemanticSearch] 技能数量变化({indexed_count} → {current_count})，重建索引")
                self.index_skills(skills)
            return

        # 磁盘索引不存在，重新构建
        self.index_skills(skills)


# 全局搜索引擎实例
_semantic_engine: Optional[SemanticSearchEngine] = None


def get_semantic_engine() -> SemanticSearchEngine:
    """获取语义搜索引擎实例（延迟初始化）"""
    global _semantic_engine
    if _semantic_engine is None:
        _semantic_engine = SemanticSearchEngine()
    return _semantic_engine


def is_semantic_available() -> bool:
    """检查语义搜索是否可用"""
    return _check_semantic_available()


log.info("🔍 [SemanticSearch] 语义搜索模块已加载")
