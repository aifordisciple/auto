"""
技能向量化服务 - 计算技能的语义向量嵌入

功能:
1. compute_skill_embedding: 计算单个技能的语义向量
2. update_all_embeddings: 更新所有技能的向量索引
3. 混合策略: 结合意图描述、技能名称、专家知识计算综合向量

向量嵌入策略:
- 意图描述 (权重 0.5): 技能的核心功能描述
- 技能名称 + 描述 (权重 0.3): 快速识别技能
- 专家知识摘要 (权重 0.2): 深入理解技能能力

支持的嵌入模型:
- OpenAI: text-embedding-3-small (1536维)
- 阿里云 Dashscope: text-embedding-v3 (1024维)
- 本地 Ollama: bge-m3 (1024维)

使用场景:
- 技能创建/更新时触发向量计算
- 批量更新所有技能的向量索引
- 支持语义相似度搜索

缓存策略:
- 技能向量嵌入: L1 TTL=1h, L2 TTL=24h, 目标命中率 95%+
- 查询向量嵌入: L1 TTL=30min, L2 TTL=1h
"""

import os
import asyncio
import httpx
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime

from sqlmodel import Session, select
from langchain_openai import OpenAIEmbeddings

from app.core.logger import log
from app.core.database import engine
from app.models.domain import SkillAsset, SkillStatus
from app.models.config import SystemConfig
from app.services.cache_service import get_cache_service


class EmbeddingProvider:
    """嵌入模型提供者枚举"""
    OPENAI = "openai"
    DASHSCOPE = "dashscope"
    OLLAMA = "ollama"


class SkillEmbeddingService:
    """
    技能向量化服务 - 计算技能的语义向量嵌入

    支持多种嵌入模型:
    - OpenAI: text-embedding-3-small (1536维)
    - 阿里云 Dashscope: text-embedding-v3 (1024维)
    - 本地 Ollama: bge-m3 (1024维)

    混合策略:
    1. 意图描述（权重 0.5）: 技能的核心功能描述
    2. 技能名称 + 描述（权重 0.3）: 快速识别技能
    3. 专家知识摘要（权重 0.2）: 深入理解技能能力

    配置优先级:
    1. SystemConfig.embedding_* 专用配置
    2. 环境变量 EMBEDDING_API_BASE, EMBEDDING_MODEL
    3. 自动检测主模型配置是否为本地模型
    4. 默认 OpenAI
    """

    # 嵌入模型维度映射
    EMBEDDING_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-v3": 1024,  # 阿里云
        "bge-m3": 1024,
        "bge-m3:latest": 1024,
        "nomic-embed-text": 768,
        "nomic-embed-text:latest": 768,
    }

    # 默认配置
    DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
    DEFAULT_OLLAMA_MODEL = "bge-m3:latest"
    DEFAULT_OLLAMA_BASE_URL = "http://host.docker.internal:11434"

    # 权重配置
    INTENT_WEIGHT = 0.5
    NAME_DESC_WEIGHT = 0.3
    EXPERT_KNOWLEDGE_WEIGHT = 0.2

    # 最大文本长度（避免 token 过多）
    MAX_TEXT_LENGTH = 8000

    def __init__(self, session: Session = None):
        """
        初始化向量化服务

        Args:
            session: 数据库会话，如果为 None 则自动创建
        """
        self.session = session
        self._embeddings_client: Optional[OpenAIEmbeddings] = None
        self._embedding_config: Optional[Dict[str, Any]] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    def _get_system_config(self) -> Optional[SystemConfig]:
        """获取系统配置"""
        try:
            if self.session:
                return self.session.exec(select(SystemConfig)).first()
            else:
                with Session(engine) as temp_session:
                    return temp_session.exec(select(SystemConfig)).first()
        except Exception as e:
            log.warning(f"[EmbeddingService] 获取系统配置失败: {e}")
            return None

    def _detect_provider(self, api_base: str, model: str) -> str:
        """
        检测嵌入模型提供者

        Args:
            api_base: API 端点
            model: 模型名称

        Returns:
            提供者类型: openai, dashscope, ollama
        """
        api_lower = api_base.lower() if api_base else ""
        model_lower = model.lower() if model else ""

        # Ollama 检测
        if ("ollama" in api_lower or
            "localhost:11434" in api_lower or
            "host.docker.internal:11434" in api_lower or
            model_lower.startswith("bge") or
            model_lower.startswith("nomic")):
            return EmbeddingProvider.OLLAMA

        # Dashscope 检测
        if "dashscope" in api_lower:
            return EmbeddingProvider.DASHSCOPE

        return EmbeddingProvider.OPENAI

    def _get_dimension(self, model: str) -> int:
        """
        获取模型嵌入维度

        Args:
            model: 模型名称

        Returns:
            向量维度
        """
        if not model:
            return 1024  # 默认维度

        model_lower = model.lower()

        # 精确匹配
        if model in self.EMBEDDING_DIMENSIONS:
            return self.EMBEDDING_DIMENSIONS[model]

        # 模糊匹配
        for key, dim in self.EMBEDDING_DIMENSIONS.items():
            if key.lower() in model_lower or model_lower in key.lower():
                return dim

        # BGE 系列默认 1024 维
        if "bge" in model_lower:
            return 1024

        # OpenAI text-embedding 系列
        if "text-embedding" in model_lower:
            if "large" in model_lower:
                return 3072
            return 1536

        return 1024  # 默认维度

    def _get_embedding_config(self) -> Dict[str, Any]:
        """
        获取嵌入模型配置

        配置优先级:
        1. SystemConfig.embedding_* 专用配置
        2. 环境变量 EMBEDDING_API_BASE, EMBEDDING_MODEL
        3. 自动检测主模型配置是否为本地模型
        4. 默认 OpenAI

        Returns:
            Dict: {provider, api_base, model, api_key, dimension}
        """
        if self._embedding_config:
            return self._embedding_config

        config = self._get_system_config()

        # 1. 检查专用嵌入配置（SystemConfig 新增字段）
        if config:
            embed_api_base = getattr(config, 'embedding_api_base', None)
            embed_model = getattr(config, 'embedding_model', None)
            embed_api_key = getattr(config, 'embedding_api_key', None)
            embed_dimension = getattr(config, 'embedding_dimension', None)

            if embed_api_base and embed_model:
                provider = self._detect_provider(embed_api_base, embed_model)
                dimension = embed_dimension or self._get_dimension(embed_model)

                self._embedding_config = {
                    "provider": provider,
                    "api_base": embed_api_base,
                    "model": embed_model,
                    "api_key": embed_api_key or "EMPTY",
                    "dimension": dimension
                }
                log.info(f"[EmbeddingService] 使用专用嵌入配置: provider={provider}, model={embed_model}, dim={dimension}")
                return self._embedding_config

        # 2. 检查环境变量
        env_api_base = os.getenv("EMBEDDING_API_BASE")
        env_model = os.getenv("EMBEDDING_MODEL")

        if env_api_base and env_model:
            provider = self._detect_provider(env_api_base, env_model)
            dimension = self._get_dimension(env_model)

            self._embedding_config = {
                "provider": provider,
                "api_base": env_api_base,
                "model": env_model,
                "api_key": os.getenv("EMBEDDING_API_KEY", "EMPTY"),
                "dimension": dimension
            }
            log.info(f"[EmbeddingService] 使用环境变量配置: provider={provider}, model={env_model}")
            return self._embedding_config

        # 3. 自动检测主模型配置
        if config and config.openai_base_url:
            base_url = config.openai_base_url
            is_local = (
                "host.docker.internal" in base_url or
                "ollama" in base_url.lower() or
                "localhost:11434" in base_url
            )

            if is_local:
                # 本地 Ollama，使用 bge-m3
                # Ollama 原生端点不带 /v1
                ollama_base = base_url.replace("/v1", "").rstrip("/")
                self._embedding_config = {
                    "provider": EmbeddingProvider.OLLAMA,
                    "api_base": ollama_base,
                    "model": self.DEFAULT_OLLAMA_MODEL,
                    "api_key": "EMPTY",
                    "dimension": 1024
                }
                log.info(f"[EmbeddingService] 检测到本地模型，使用 Ollama 嵌入: {ollama_base}")
                return self._embedding_config

            elif "dashscope" in base_url.lower():
                # 阿里云 Dashscope
                api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
                if "coding.dashscope" in base_url.lower():
                    api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
                self._embedding_config = {
                    "provider": EmbeddingProvider.DASHSCOPE,
                    "api_base": api_base,
                    "model": "text-embedding-v3",
                    "api_key": config.openai_api_key,
                    "dimension": 1024
                }
                log.info("[EmbeddingService] 使用阿里云 Dashscope 嵌入")
                return self._embedding_config

        # 4. 默认 OpenAI
        self._embedding_config = {
            "provider": EmbeddingProvider.OPENAI,
            "api_base": "https://api.openai.com/v1",
            "model": self.DEFAULT_OPENAI_MODEL,
            "api_key": config.openai_api_key if config else os.getenv("OPENAI_API_KEY"),
            "dimension": 1536
        }
        log.info("[EmbeddingService] 使用默认 OpenAI 嵌入")
        return self._embedding_config

    @property
    def embedding_dimension(self) -> int:
        """获取当前嵌入维度"""
        config = self._get_embedding_config()
        return config["dimension"]

    async def _compute_ollama_embedding(self, text: str) -> Optional[List[float]]:
        """
        使用 Ollama 计算嵌入向量

        Ollama API 端点: POST /api/embeddings
        请求: {"model": "bge-m3", "prompt": "text"}
        响应: {"embedding": [0.1, 0.2, ...]}

        Args:
            text: 待嵌入文本

        Returns:
            嵌入向量列表，失败返回 None
        """
        config = self._get_embedding_config()

        try:
            if not self._http_client:
                self._http_client = httpx.AsyncClient(timeout=30.0)

            response = await self._http_client.post(
                f"{config['api_base']}/api/embeddings",
                json={
                    "model": config["model"],
                    "prompt": text
                }
            )

            if response.status_code == 200:
                data = response.json()
                embedding = data.get("embedding", [])
                if embedding:
                    log.debug(f"[OllamaEmbedding] 成功: model={config['model']}, dim={len(embedding)}")
                    return embedding
                else:
                    log.error(f"[OllamaEmbedding] 响应中无 embedding 字段: {data}")
                    return None
            else:
                log.error(f"[OllamaEmbedding] 请求失败: {response.status_code} - {response.text}")
                return None

        except httpx.TimeoutException:
            log.error(f"[OllamaEmbedding] 请求超时")
            return None
        except Exception as e:
            log.error(f"[OllamaEmbedding] 异常: {e}")
            return None

    def _init_embeddings_client(self) -> OpenAIEmbeddings:
        """
        初始化 OpenAI 兼容的 Embedding 客户端

        用于 OpenAI 和 Dashscope 等兼容 API。
        Ollama 使用单独的 _compute_ollama_embedding 方法。

        Returns:
            OpenAIEmbeddings 实例
        """
        if self._embeddings_client:
            return self._embeddings_client

        config = self._get_embedding_config()
        provider = config["provider"]

        # Ollama 不使用 langchain 客户端
        if provider == EmbeddingProvider.OLLAMA:
            return None

        self._embeddings_client = OpenAIEmbeddings(
            api_key=config["api_key"],
            base_url=config["api_base"],
            model=config["model"]
        )

        log.info(f"[EmbeddingService] 初始化 Embedding 客户端: provider={provider}, model={config['model']}")
        return self._embeddings_client

    def _truncate_text(self, text: str, max_length: int = None) -> str:
        """
        截断文本以避免 token 过多

        Args:
            text: 原始文本
            max_length: 最大长度

        Returns:
            截断后的文本
        """
        if max_length is None:
            max_length = self.MAX_TEXT_LENGTH

        if len(text) <= max_length:
            return text

        # 截断并添加省略号
        return text[:max_length - 3] + "..."

    def _build_embedding_text(self, skill: Dict[str, Any]) -> str:
        """
        构建用于计算向量嵌入的文本

        混合策略:
        1. 意图描述（权重 0.5）
        2. 技能名称 + 描述（权重 0.3）
        3. 专家知识摘要（权重 0.2）

        Args:
            skill: 技能数据字典

        Returns:
            用于计算向量嵌入的文本
        """
        parts = []

        # 1. 技能名称和描述（核心信息）
        name = skill.get("name", "") or ""
        description = skill.get("description", "") or ""
        if name or description:
            parts.append(f"[技能名称] {name}")
            if description:
                parts.append(f"[技能描述] {description}")

        # 2. 分类信息
        category_name = skill.get("category_name", "") or ""
        subcategory_name = skill.get("subcategory_name", "") or ""
        if category_name:
            parts.append(f"[分类] {category_name}")
        if subcategory_name:
            parts.append(f"[子分类] {subcategory_name}")

        # 3. 标签
        tags = skill.get("tags", [])
        if tags:
            parts.append(f"[标签] {', '.join(tags)}")

        # 4. 专家知识（截取摘要）
        expert_knowledge = skill.get("expert_knowledge", "") or ""
        if expert_knowledge:
            # 截取前 500 字符作为摘要
            knowledge_summary = self._truncate_text(expert_knowledge, 500)
            parts.append(f"[专家知识] {knowledge_summary}")

        # 5. 参数描述（提取关键参数）
        parameters_schema = skill.get("parameters_schema", {})
        properties = parameters_schema.get("properties", {})
        if properties:
            param_descriptions = []
            for param_name, param_info in list(properties.items())[:5]:  # 只取前 5 个参数
                param_desc = param_info.get("description", "")
                if param_desc:
                    param_descriptions.append(f"{param_name}: {param_desc}")
            if param_descriptions:
                parts.append(f"[参数] {'; '.join(param_descriptions)}")

        # 合并所有部分
        full_text = "\n".join(parts)

        # 截断到最大长度
        return self._truncate_text(full_text)

    async def compute_skill_embedding(self, skill: Dict[str, Any], use_cache: bool = True) -> Optional[List[float]]:
        """
        计算技能的语义向量

        支持 Ollama (bge-m3)、OpenAI、阿里云 Dashscope 等多种嵌入模型。
        支持缓存，相同技能内容直接返回缓存结果。

        Args:
            skill: 技能数据字典，包含 name, description, expert_knowledge 等
            use_cache: 是否使用缓存（默认启用）

        Returns:
            向量嵌入列表，失败返回 None
        """
        try:
            skill_id = skill.get("skill_id")

            # ✨ 预计算内容哈希（用于缓存键）
            content_hash = self._compute_skill_content_hash(skill)
            cache_key = f"embedding:skill:{skill_id}:{content_hash}"

            # ✨ 尝试从缓存获取
            if use_cache:
                cache = get_cache_service()
                cached = cache.get(cache_key)

                if cached is not None:
                    log.debug(f"[EmbeddingService] 技能向量缓存命中: skill_id={skill_id}")
                    return cached

            # 获取配置
            config = self._get_embedding_config()
            provider = config["provider"]

            # 构建嵌入文本
            embedding_text = self._build_embedding_text(skill)

            if not embedding_text:
                log.warning(f"[EmbeddingService] 技能文本为空，跳过: {skill_id}")
                return None

            embedding = None

            # 根据提供者选择不同的嵌入方法
            if provider == EmbeddingProvider.OLLAMA:
                # Ollama 本地嵌入
                embedding = await self._compute_ollama_embedding(embedding_text)
            else:
                # OpenAI / Dashscope 使用 langchain 客户端
                embeddings_client = self._init_embeddings_client()
                if embeddings_client:
                    embedding = await embeddings_client.aembed_query(embedding_text)

            if embedding:
                log.info(f"[EmbeddingService] 计算向量成功: skill_id={skill_id}, "
                        f"provider={provider}, dim={len(embedding)}")

                # ✨ 存入缓存（L1 TTL=1h, L2 TTL=24h）
                if use_cache:
                    cache.set(cache_key, embedding, cache_type="embedding:skill")

            return embedding

        except Exception as e:
            log.error(f"[EmbeddingService] 计算向量失败: skill_id={skill.get('skill_id')}, error={e}")
            return None

    def _compute_skill_content_hash(self, skill: Dict[str, Any]) -> str:
        """
        计算技能内容哈希，用于缓存键

        基于技能的核心字段计算哈希，内容变化时缓存失效

        Args:
            skill: 技能数据字典

        Returns:
            内容哈希字符串（12位）
        """
        # 用于计算哈希的核心字段
        hash_fields = [
            skill.get("name", "") or "",
            skill.get("description", "") or "",
            skill.get("category_name", "") or "",
            skill.get("subcategory_name", "") or "",
            str(skill.get("tags", [])),
            skill.get("expert_knowledge", "") or "",
            str(skill.get("parameters_schema", {})),
        ]

        # 合并并计算哈希
        content = "|".join(hash_fields)
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def invalidate_skill_embedding_cache(self, skill_id: str) -> int:
        """
        失效单个技能的向量嵌入缓存

        当技能内容更新或删除时，应调用此方法清除相关缓存，
        确保下次查询时重新计算最新的向量嵌入。

        Args:
            skill_id: 技能 ID

        Returns:
            删除的缓存项数量
        """
        cache = get_cache_service()
        pattern = f"embedding:skill:{skill_id}:"
        deleted = cache.invalidate_pattern(pattern)
        log.info(f"[EmbeddingService] 失效技能向量缓存: skill_id={skill_id}, 删除 {deleted} 项")
        return deleted

    def invalidate_all_skill_embedding_cache(self) -> int:
        """
        失效所有技能向量嵌入缓存

        当批量更新技能或系统维护时使用。

        Returns:
            删除的缓存项数量
        """
        cache = get_cache_service()
        deleted = cache.invalidate_pattern("embedding:skill:")
        log.info(f"[EmbeddingService] 失效所有技能向量缓存, 删除 {deleted} 项")
        return deleted

    async def update_skill_embedding(self, skill_id: str, force: bool = True) -> bool:
        """
        更新单个技能的向量嵌入

        Args:
            skill_id: 技能 ID
            force: 是否强制重新计算（不使用缓存，默认 True）

        Returns:
            是否成功
        """
        try:
            with Session(engine) as session:
                # 获取技能
                skill = session.exec(
                    select(SkillAsset).where(SkillAsset.skill_id == skill_id)
                ).first()

                if not skill:
                    log.warning(f"[EmbeddingService] 技能不存在: {skill_id}")
                    return False

                # 构建技能数据
                skill_data = {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "description": skill.description,
                    "category_name": skill.category_name,
                    "subcategory_name": skill.subcategory_name,
                    "tags": skill.tags or [],
                    "expert_knowledge": skill.expert_knowledge,
                    "parameters_schema": skill.parameters_schema
                }

                # ✨ 强制更新时清理旧缓存并重新计算
                if force:
                    self.invalidate_skill_embedding_cache(skill_id)

                # 计算向量（force 时跳过缓存）
                embedding = await self.compute_skill_embedding(skill_data, use_cache=not force)

                if embedding:
                    # 更新数据库
                    skill.combined_embedding = embedding
                    skill.embedding_updated_at = datetime.utcnow()
                    session.add(skill)
                    session.commit()

                    log.info(f"[EmbeddingService] 更新向量成功: skill_id={skill_id}")
                    return True

                return False

        except Exception as e:
            log.error(f"[EmbeddingService] 更新向量失败: skill_id={skill_id}, error={e}")
            return False

    async def update_all_embeddings(self, batch_size: int = 10) -> Dict[str, int]:
        """
        更新所有技能的向量索引

        批量处理所有已发布技能，计算并存储向量嵌入。
        支持断点续传，避免重复计算。

        Args:
            batch_size: 批量处理大小，控制 API 调用频率

        Returns:
            统计结果: {"total": N, "updated": N, "failed": N, "skipped": N}
        """
        stats = {"total": 0, "updated": 0, "failed": 0, "skipped": 0}

        log.info("[EmbeddingService] 开始批量更新向量索引")

        try:
            with Session(engine) as session:
                # 获取所有已发布技能
                skills = session.exec(
                    select(SkillAsset).where(
                        SkillAsset.status == SkillStatus.PUBLISHED
                    )
                ).all()

                stats["total"] = len(skills)
                log.info(f"[EmbeddingService] 共 {stats['total']} 个技能需要处理")

                for i, skill in enumerate(skills):
                    try:
                        # 检查是否需要更新（内容变化或向量缺失）
                        need_update = self._need_update_embedding(skill)

                        if not need_update:
                            stats["skipped"] += 1
                            continue

                        # 构建技能数据
                        skill_data = {
                            "skill_id": skill.skill_id,
                            "name": skill.name,
                            "description": skill.description,
                            "category_name": skill.category_name,
                            "subcategory_name": skill.subcategory_name,
                            "tags": skill.tags or [],
                            "expert_knowledge": skill.expert_knowledge,
                            "parameters_schema": skill.parameters_schema
                        }

                        # 计算向量
                        embedding = await self.compute_skill_embedding(skill_data)

                        if embedding:
                            skill.combined_embedding = embedding
                            skill.embedding_updated_at = datetime.utcnow()
                            session.add(skill)
                            stats["updated"] += 1
                        else:
                            stats["failed"] += 1

                        # 批量提交
                        if (i + 1) % batch_size == 0:
                            session.commit()
                            log.info(f"[EmbeddingService] 已处理 {i + 1}/{stats['total']} 个技能")

                        # 控制 API 调用频率
                        await asyncio.sleep(0.1)

                    except Exception as e:
                        log.error(f"[EmbeddingService] 处理技能失败: skill_id={skill.skill_id}, error={e}")
                        stats["failed"] += 1

                # 最终提交
                session.commit()

        except Exception as e:
            log.error(f"[EmbeddingService] 批量更新失败: {e}")

        log.info(f"[EmbeddingService] 批量更新完成: {stats}")
        return stats

    def _need_update_embedding(self, skill: SkillAsset) -> bool:
        """
        检查技能是否需要更新向量嵌入

        Args:
            skill: 技能对象

        Returns:
            是否需要更新
        """
        # 向量为空，需要更新
        if not skill.combined_embedding:
            return True

        # 向量更新时间早于技能更新时间，需要更新
        if skill.embedding_updated_at and skill.updated_at:
            if skill.embedding_updated_at < skill.updated_at:
                return True

        return False

    async def compute_query_embedding(self, query: str) -> Optional[List[float]]:
        """
        计算用户查询的向量嵌入

        支持 Ollama (bge-m3)、OpenAI、阿里云 Dashscope 等多种嵌入模型。
        支持缓存，相同查询直接返回缓存结果。

        Args:
            query: 用户查询文本

        Returns:
            向量嵌入列表，失败返回 None

        注意：此方法失败时会优雅降级，不抛出异常，
        允许匹配系统继续使用其他匹配方式（规则匹配、LLM 匹配）。
        """
        try:
            # 尝试从缓存获取
            cache = get_cache_service()
            query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
            cache_key = f"embedding:query:{query_hash}"
            cached = cache.get(cache_key)

            if cached is not None:
                log.debug(f"[EmbeddingService] 查询向量缓存命中: {query_hash}")
                return cached

            # 获取配置
            config = self._get_embedding_config()
            provider = config["provider"]

            embedding = None

            # 根据提供者选择不同的嵌入方法
            if provider == EmbeddingProvider.OLLAMA:
                # Ollama 本地嵌入
                embedding = await self._compute_ollama_embedding(query)
            else:
                # OpenAI / Dashscope 使用 langchain 客户端
                embeddings_client = self._init_embeddings_client()
                if embeddings_client:
                    embedding = await embeddings_client.aembed_query(query)

            if embedding:
                log.debug(f"[EmbeddingService] 查询向量计算成功: provider={provider}, dim={len(embedding)}")
                # 存入缓存
                cache.set(cache_key, embedding, cache_type="embedding:skill")

            return embedding

        except Exception as e:
            # 优雅降级：记录错误但不抛出异常，让匹配系统继续工作
            log.warning(f"[EmbeddingService] 计算查询向量失败（将使用其他匹配方式）: {e}")
            return None


# ==========================================
# 辅助函数
# ==========================================

async def update_skill_embedding_async(skill_id: str, force: bool = True) -> bool:
    """
    异步更新单个技能的向量嵌入

    Args:
        skill_id: 技能 ID
        force: 是否强制重新计算（不使用缓存，默认 True）

    Returns:
        是否成功
    """
    service = SkillEmbeddingService()
    return await service.update_skill_embedding(skill_id, force=force)


def invalidate_skill_cache(skill_id: str) -> int:
    """
    失效单个技能的向量缓存（同步版本）

    Args:
        skill_id: 技能 ID

    Returns:
        删除的缓存项数量
    """
    service = SkillEmbeddingService()
    return service.invalidate_skill_embedding_cache(skill_id)


async def update_all_embeddings_async() -> Dict[str, int]:
    """
    异步更新所有技能的向量索引

    Returns:
        统计结果
    """
    service = SkillEmbeddingService()
    return await service.update_all_embeddings()


log.info("✅ 技能向量化服务已加载")