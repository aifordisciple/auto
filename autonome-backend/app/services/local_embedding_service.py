"""
本地嵌入服务 - 使用 Ollama bge-m3 模型

功能：
1. 调用本地 Ollama API 生成文本嵌入
2. 支持批量嵌入生成
3. 内置缓存机制
4. 健康检查
5. 优雅降级

配置：
- OLLAMA_BASE_URL: Ollama 服务地址（默认 http://localhost:11434）
- OLLAMA_EMBED_MODEL: 嵌入模型名称（默认 bge-m3:latest）
"""

import os
import time
import hashlib
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

import aiohttp

from app.core.logger import log


@dataclass
class EmbeddingCache:
    """嵌入缓存"""
    cache: Dict[str, List[float]] = field(default_factory=dict)
    max_size: int = 10000

    def get(self, key: str) -> Optional[List[float]]:
        """获取缓存"""
        return self.cache.get(key)

    def set(self, key: str, value: List[float]) -> None:
        """设置缓存"""
        if len(self.cache) >= self.max_size:
            # 简单的LRU：删除最早的缓存
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]

        self.cache[key] = value

    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()

    def size(self) -> int:
        """缓存大小"""
        return len(self.cache)


class LocalEmbeddingService:
    """
    本地嵌入服务

    使用 Ollama 运行的 bge-m3 模型生成文本嵌入。
    bge-m3 特点：
    - 多语言支持（中英文）
    - 1024 维向量
    - 长文本支持（8192 tokens）
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        enable_cache: bool = True,
        cache_size: int = 10000,
    ):
        """
        初始化本地嵌入服务

        Args:
            base_url: Ollama API 地址
            model: 嵌入模型名称
            enable_cache: 是否启用缓存
            cache_size: 缓存最大条目数
        """
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_EMBED_MODEL", "bge-m3:latest")
        self.enable_cache = enable_cache
        self._cache = EmbeddingCache(max_size=cache_size) if enable_cache else None

        # 服务状态
        self.ollama_available: Optional[bool] = None
        self._last_health_check: Optional[datetime] = None

        log.info(f"[LocalEmbedding] 初始化服务: base_url={self.base_url}, model={self.model}")

    async def embed(self, text: str) -> Optional[List[float]]:
        """
        生成单个文本的嵌入向量

        Args:
            text: 输入文本

        Returns:
            嵌入向量列表，失败时返回 None
        """
        # 空文本处理
        if not text or not text.strip():
            log.warning("[LocalEmbedding] 空文本输入，返回 None")
            return None

        # 检查缓存
        if self.enable_cache and self._cache:
            cache_key = self._get_cache_key(text)
            cached = self._cache.get(cache_key)
            if cached is not None:
                log.debug(f"[LocalEmbedding] 缓存命中: {text[:30]}...")
                return cached

        # 调用 Ollama API
        try:
            embedding = await self._call_ollama_api(text)

            # 缓存结果
            if embedding and self.enable_cache and self._cache:
                self._cache.set(cache_key, embedding)

            return embedding

        except Exception as e:
            log.error(f"[LocalEmbedding] 生成嵌入失败: {e}")
            return None

    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        批量生成嵌入向量

        Args:
            texts: 文本列表

        Returns:
            嵌入向量列表
        """
        if not texts:
            return []

        # 并发调用（Ollama 支持并发）
        tasks = [self.embed(text) for text in texts]
        results = await asyncio.gather(*tasks)

        return results

    async def _call_ollama_api(self, text: str) -> Optional[List[float]]:
        """
        调用 Ollama API 生成嵌入

        Args:
            text: 输入文本

        Returns:
            嵌入向量
        """
        url = f"{self.base_url}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text,
        }

        timeout = aiohttp.ClientTimeout(total=10)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        embedding = data.get("embedding", [])

                        if embedding:
                            self.ollama_available = True
                            return embedding
                        else:
                            log.warning(f"[LocalEmbedding] 响应无嵌入数据: {data}")
                            return None
                    else:
                        error_text = await response.text()
                        log.error(f"[LocalEmbedding] API 错误: {response.status} - {error_text}")
                        self.ollama_available = False
                        return None

        except aiohttp.ClientError as e:
            log.error(f"[LocalEmbedding] 连接 Ollama 失败: {e}")
            self.ollama_available = False
            return None
        except Exception as e:
            log.error(f"[LocalEmbedding] 未知错误: {e}")
            return None

    async def check_health(self) -> Dict[str, Any]:
        """
        检查服务健康状态

        Returns:
            健康状态字典
        """
        start_time = time.time()

        # 尝试生成一个测试嵌入
        test_text = "health check"

        try:
            embedding = await self.embed(test_text)
            latency_ms = (time.time() - start_time) * 1000

            if embedding:
                self._last_health_check = datetime.utcnow()
                return {
                    "status": "healthy",
                    "model": self.model,
                    "embedding_dim": len(embedding),
                    "latency_ms": round(latency_ms, 2),
                    "cache_enabled": self.enable_cache,
                    "cache_size": self._cache.size() if self._cache else 0,
                }
            else:
                return {
                    "status": "unhealthy",
                    "model": self.model,
                    "error": "Failed to generate embedding",
                    "latency_ms": round(latency_ms, 2),
                }

        except Exception as e:
            return {
                "status": "error",
                "model": self.model,
                "error": str(e),
                "latency_ms": (time.time() - start_time) * 1000,
            }

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算余弦相似度

        Args:
            vec1: 向量1
            vec2: 向量2

        Returns:
            相似度分数 [-1, 1]
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        # 点积
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # 向量长度
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        return hashlib.md5(text.encode()).hexdigest()

    def clear_cache(self) -> None:
        """清空缓存"""
        if self._cache:
            self._cache.clear()
            log.info("[LocalEmbedding] 缓存已清空")

    def cache_size(self) -> int:
        """获取缓存大小"""
        return self._cache.size() if self._cache else 0


# ==========================================
# 全局单例
# ==========================================

_local_embedding_service: Optional[LocalEmbeddingService] = None


def get_local_embedding_service() -> LocalEmbeddingService:
    """获取本地嵌入服务单例"""
    global _local_embedding_service
    if _local_embedding_service is None:
        _local_embedding_service = LocalEmbeddingService()
    return _local_embedding_service


async def embed_text(text: str) -> Optional[List[float]]:
    """
    便捷函数：生成文本嵌入

    Args:
        text: 输入文本

    Returns:
        嵌入向量
    """
    service = get_local_embedding_service()
    return await service.embed(text)


async def embed_texts(texts: List[str]) -> List[Optional[List[float]]]:
    """
    便捷函数：批量生成文本嵌入

    Args:
        texts: 文本列表

    Returns:
        嵌入向量列表
    """
    service = get_local_embedding_service()
    return await service.embed_batch(texts)


log.info("✅ 本地嵌入服务已加载")