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


# 全局 MCP 实例
_mcp_instance: Optional[AutonomeSkillsMCP] = None


def get_mcp_server() -> AutonomeSkillsMCP:
    """获取 MCP 服务实例（延迟初始化）"""
    global _mcp_instance
    if _mcp_instance is None:
        _mcp_instance = AutonomeSkillsMCP()
        log.info("📦 [MCP] MCP 服务已初始化")
    return _mcp_instance
