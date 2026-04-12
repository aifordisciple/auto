"""
Autonome Skills MCP Server

轻量级 MCP (Model Context Protocol) 服务，提供技能检索和 Schema 查询接口。

在 Warm Pool 容器启动时，自动注入 .claude.json 挂载该 MCP 工具，
使 Claude Code 能够通过本地 MCP 调用技能检索功能。
"""

import os
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.core.logger import log
from app.core.skill_parser import get_combined_skill_by_id, get_combined_skills


@dataclass
class SkillSchema:
    """技能 Schema"""
    skill_id: str
    name: str
    description: str
    executor_type: str
    parameters_schema: Dict[str, Any]
    category: str
    tags: List[str]


@dataclass
class SearchResult:
    """搜索结果"""
    skill_id: str
    name: str
    description: str
    match_score: float
    match_reason: str


class AutonomeSkillsMCP:
    """
    Autonome Skills MCP 服务

    提供两个主要接口：
    1. search_skills - 搜索技能
    2. get_skill_schema - 获取技能 Schema
    """

    def __init__(self):
        self._skill_cache: Dict[str, Dict[str, Any]] = {}
        self._initialized = False

    def initialize(self) -> None:
        """初始化 MCP 服务，加载技能缓存"""
        if self._initialized:
            return

        try:
            # 加载所有技能到缓存
            skills = get_combined_skills(user_id=0)
            for skill in skills:
                skill_id = skill.get('metadata', {}).get('skill_id', '')
                if skill_id:
                    self._skill_cache[skill_id] = skill

            self._initialized = True
            log.info(f"📦 [MCP] 已加载 {len(self._skill_cache)} 个技能到缓存")
        except Exception as e:
            log.error(f"❌ [MCP] 初始化失败: {e}")

    def search_skills(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索技能

        V2: 默认使用增强搜索（关键词 + 语义双轨），
        当 AUTONOME_USE_SEMANTIC_SEARCH=false 时降级为纯关键词搜索。

        Args:
            query: 搜索查询
            limit: 返回结果数量限制
            category: 可选的分类过滤

        Returns:
            匹配的技能列表
        """
        # V2: 检查是否启用语义搜索
        use_semantic = os.environ.get("AUTONOME_USE_SEMANTIC_SEARCH", "false").lower() == "true"

        if use_semantic:
            return self.search_skills_enhanced(query, limit, category)

        # 原有关键词搜索逻辑
        return self._search_skills_keyword(query, limit, category)

    def _search_skills_keyword(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        纯关键词搜索（原 search_skills 逻辑）

        Args:
            query: 搜索查询
            limit: 返回结果数量限制
            category: 可选的分类过滤

        Returns:
            匹配的技能列表
        """
        self.initialize()

        if not query:
            return []

        query_lower = query.lower()
        results = []

        for skill_id, skill in self._skill_cache.items():
            # 分类过滤
            if category:
                skill_category = skill.get('metadata', {}).get('category', '')
                if skill_category != category:
                    continue

            # 计算匹配分数
            metadata = skill.get('metadata', {})
            name = metadata.get('name', '').lower()
            description = metadata.get('description', '').lower()
            tags = ' '.join(metadata.get('tags', [])).lower()

            # 简单关键词匹配
            score = 0.0
            match_reason = ""

            if query_lower in name:
                score += 0.5
                match_reason = "名称匹配"
            if query_lower in description:
                score += 0.3
                match_reason = match_reason or "描述匹配"
            if query_lower in tags:
                score += 0.2
                match_reason = match_reason or "标签匹配"

            if score > 0:
                results.append({
                    "skill_id": skill_id,
                    "name": metadata.get('name', ''),
                    "description": metadata.get('description', ''),
                    "executor_type": metadata.get('executor_type', ''),
                    "match_score": min(score, 1.0),
                    "match_reason": match_reason,
                    "category": metadata.get('category', ''),
                    "tags": metadata.get('tags', []),
                })

        # 按匹配分数排序
        results.sort(key=lambda x: x['match_score'], reverse=True)

        return results[:limit]

    def get_skill_schema(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        获取技能 Schema

        Args:
            skill_id: 技能 ID

        Returns:
            技能详情，如果不存在则返回 None
        """
        self.initialize()

        if skill_id in self._skill_cache:
            skill = self._skill_cache[skill_id]
            metadata = skill.get('metadata', {})

            return {
                "skill_id": skill_id,
                "name": metadata.get('name', ''),
                "description": metadata.get('description', ''),
                "version": metadata.get('version', '1.0.0'),
                "executor_type": metadata.get('executor_type', 'Python_env'),
                "entry_point": skill.get('entry_point', ''),
                "timeout_seconds": metadata.get('timeout_seconds', 3600),
                "parameters_schema": skill.get('parameters_schema', {}),
                "expert_knowledge": skill.get('expert_knowledge', ''),
                "category": metadata.get('category', ''),
                "subcategory": metadata.get('subcategory', ''),
                "tags": metadata.get('tags', []),
                "visibility": metadata.get('visibility', 'private'),
            }

        return None

    def get_skill_parameters(self, skill_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取技能参数字段列表

        Args:
            skill_id: 技能 ID

        Returns:
            参数字段列表
        """
        schema = self.get_skill_schema(skill_id)
        if not schema:
            return None

        parameters_schema = schema.get('parameters_schema', {})
        properties = parameters_schema.get('properties', {})
        required = parameters_schema.get('required', [])

        result = []
        for param_name, param_def in properties.items():
            param_type = param_def.get('type', 'string')
            type_mapping = {
                'string': 'text',
                'integer': 'number',
                'number': 'number',
                'boolean': 'boolean',
                'array': 'text',
                'object': 'text'
            }

            result.append({
                'name': param_name,
                'label': param_name,
                'type': type_mapping.get(param_type, 'text'),
                'required': param_name in required,
                'default': param_def.get('default'),
                'description': param_def.get('description', ''),
            })

        return result

    def list_categories(self) -> List[str]:
        """
        获取所有技能分类

        Returns:
            分类列表
        """
        self.initialize()

        categories = set()
        for skill in self._skill_cache.values():
            category = skill.get('metadata', {}).get('category', '')
            if category:
                categories.add(category)

        return sorted(list(categories))

    def get_all_skills(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取所有技能

        Args:
            category: 可选的分类过滤

        Returns:
            技能列表
        """
        self.initialize()

        results = []
        for skill_id, skill in self._skill_cache.items():
            if category:
                skill_category = skill.get('metadata', {}).get('category', '')
                if skill_category != category:
                    continue

            metadata = skill.get('metadata', {})
            results.append({
                'skill_id': skill_id,
                'name': metadata.get('name', ''),
                'description': metadata.get('description', ''),
                'executor_type': metadata.get('executor_type', ''),
                'category': metadata.get('category', ''),
                'tags': metadata.get('tags', []),
            })

        return results

    def search_skills_enhanced(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        V2: 增强搜索（关键词 + 语义双轨加权合并）

        搜索策略：
        1. 运行关键词搜索 → keyword_results (score 0-1)
        2. 运行语义搜索 → semantic_results (score 0-1)
        3. 合并：final_score = 0.4 * keyword_score + 0.6 * semantic_score
        4. 返回 top-k by final_score

        Args:
            query: 搜索查询
            limit: 返回结果数量限制
            category: 可选的分类过滤

        Returns:
            匹配的技能列表
        """
        self.initialize()

        if not query:
            return []

        # 1. 关键词搜索
        keyword_results = self._search_skills_keyword(query, limit=limit * 2, category=category)
        keyword_scores: Dict[str, float] = {
            r['skill_id']: r['match_score'] for r in keyword_results
        }
        log.info(f"[MCP.V2] 双轨搜索: query='{query[:50]}', 关键词候选={len(keyword_results)}")

        # 2. 语义搜索
        semantic_scores: Dict[str, float] = {}
        try:
            from app.mcp.semantic_search import get_semantic_engine, is_semantic_available
            if is_semantic_available():
                engine = get_semantic_engine()
                if not engine._initialized:
                    # 首次使用，构建索引
                    all_skills = self.get_all_skills()
                    # 转换为 skill_parser 格式
                    skills_for_index = []
                    for sid, skill in self._skill_cache.items():
                        skills_for_index.append(skill)
                    engine.initialize(skills_for_index)

                semantic_results = engine.search(query, top_k=limit * 2)
                semantic_scores = {sid: score for sid, score in semantic_results}
                log.info(f"[MCP.V2] 双轨搜索: 语义候选={len(semantic_results)}")
        except Exception as e:
            log.warning(f"📦 [MCP] 语义搜索失败，降级为纯关键词: {e}")

        # 3. 合并分数
        # 收集所有候选技能 ID
        all_candidate_ids = set(keyword_scores.keys()) | set(semantic_scores.keys())

        # 加权合并：关键词 0.4 + 语义 0.6
        KEYWORD_WEIGHT = 0.4
        SEMANTIC_WEIGHT = 0.6

        merged_results: List[Dict[str, Any]] = []
        for skill_id in all_candidate_ids:
            # 分类过滤
            if category:
                skill = self._skill_cache.get(skill_id, {})
                skill_category = skill.get('metadata', {}).get('category', '')
                if skill_category != category:
                    continue

            keyword_score = keyword_scores.get(skill_id, 0.0)
            semantic_score = semantic_scores.get(skill_id, 0.0)
            final_score = KEYWORD_WEIGHT * keyword_score + SEMANTIC_WEIGHT * semantic_score

            # 获取技能元数据
            skill = self._skill_cache.get(skill_id, {})
            metadata = skill.get('metadata', {})

            # 确定匹配原因
            match_reasons = []
            if keyword_score > 0:
                match_reasons.append("关键词匹配")
            if semantic_score > 0:
                match_reasons.append("语义匹配")

            merged_results.append({
                "skill_id": skill_id,
                "name": metadata.get('name', ''),
                "description": metadata.get('description', ''),
                "executor_type": metadata.get('executor_type', ''),
                "match_score": min(final_score, 1.0),
                "match_reason": " + ".join(match_reasons),
                "category": metadata.get('category', ''),
                "tags": metadata.get('tags', []),
                # V2: 搜索详情
                "_keyword_score": keyword_score,
                "_semantic_score": semantic_score,
            })

        # 按合并分数排序
        merged_results.sort(key=lambda x: x['match_score'], reverse=True)

        return merged_results[:limit]


# 全局 MCP 实例
_mcp_instance: Optional[AutonomeSkillsMCP] = None


def get_mcp_server() -> AutonomeSkillsMCP:
    """获取 MCP 服务实例（延迟初始化）"""
    global _mcp_instance
    if _mcp_instance is None:
        _mcp_instance = AutonomeSkillsMCP()
        log.info("📦 [MCP] MCP 服务已初始化")
    return _mcp_instance


def generate_claude_mcp_config() -> dict:
    """
    V2: 生成 Claude Code 的 MCP 配置

    在 Warm Pool 容器启动时，自动注入 .claude.json 配置，
    使 Claude Code 能够通过本地 MCP 调用技能检索功能。

    Returns:
        MCP 服务器配置 dict，可直接写入 .claude.json
    """
    return {
        "mcpServers": {
            "autonome-skills": {
                "command": "python",
                "args": ["-m", "app.mcp.autonome_skills_mcp"],
                "description": "Autonome 技能检索服务 - 搜索和查询生信分析技能"
            }
        }
    }
