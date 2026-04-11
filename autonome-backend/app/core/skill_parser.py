"""
SKILL Bundle Parser - 解析 SKILL.md 文件，提取元数据、参数 Schema 和专家知识库

支持两种数据源：
1. 文件系统：解析 /app/skills 目录下的 SKILL.md 文件（用于官方预置技能）
2. 数据库：查询 SkillAsset 表（用于用户自定义技能，支持 RBAC 权限过滤）

支持两种 SKILL 类型：
1. 可执行型 (executable)：完整流程调度，输出 json_strategy 卡片
2. 知识型 (knowledge)：代码模式库，AI 直接参考生成代码

SKILL.md 格式规范：

【可执行型 SKILL】（原有规范）
1. YAML Frontmatter（---包裹）包含核心元数据，必须有 skill_id 和 executor_type
2. 第2节（## 2. 动态参数定义规范）包含参数表格
3. 第3节（## 3. 操作指令与专家级知识库）包含专家知识

【知识型 SKILL】（OpenClaw 规范）
1. YAML Frontmatter 包含 name, description, tool_type, primary_tool
2. 正文包含代码模式库（Code Patterns）和专家指导
3. 无需参数表格，AI 直接参考生成代码
"""

import os
import re
import json
import copy
from functools import lru_cache
from typing import Dict, List, Any, Optional

import yaml
from sqlmodel import Session, select, or_, and_
from app.core.logger import log
from app.core.database import engine
from app.models.domain import SkillAsset, SkillStatus


class SkillBundleParser:
    """SKILL Bundle 解析器，负责解析 SKILL.md 文件并提取结构化信息"""

    def __init__(self, skills_dir: str = "/app/app/skills"):
        """
        初始化解析器

        Args:
            skills_dir: SKILL Bundle 存放目录路径（容器内路径）
        """
        self.skills_dir = skills_dir
        log.info(f"[SkillParser] 初始化 SKILL 解析器，目录: {skills_dir}")

    def get_all_skills(self) -> List[Dict[str, Any]]:
        """
        扫描 skills 目录，解析所有 SKILL.md 文件

        Returns:
            包含所有 SKILL 信息的列表，每个元素包含：
            - metadata: YAML 元数据
            - parameters_schema: JSON Schema 格式的参数定义
            - expert_knowledge: 专家知识库文本
            - bundle_path: Bundle 目录路径
        """
        skills = []

        if not os.path.exists(self.skills_dir):
            log.warning(f"[SkillParser] SKILL 目录不存在: {self.skills_dir}")
            return skills

        # 遍历所有子目录
        for bundle_name in os.listdir(self.skills_dir):
            bundle_path = os.path.join(self.skills_dir, bundle_name)
            skill_md_path = os.path.join(bundle_path, "SKILL.md")

            if os.path.isdir(bundle_path) and os.path.exists(skill_md_path):
                skill_data = self.parse_skill_md(skill_md_path)
                if skill_data:
                    skill_data["bundle_path"] = bundle_path
                    skill_data["bundle_name"] = bundle_name
                    skills.append(skill_data)
                    log.info(f"[SkillParser] 成功解析 SKILL: {skill_data['metadata'].get('skill_id', bundle_name)}")

        log.info(f"[SkillParser] 共解析 {len(skills)} 个 SKILL Bundle")
        return skills

    def parse_skill_md(self, filepath: str) -> Optional[Dict[str, Any]]:
        """
        解析单个 SKILL.md 文件

        支持两种 SKILL 类型：
        1. 可执行型 (executable)：完整流程调度
        2. 知识型 (knowledge)：代码模式库

        Args:
            filepath: SKILL.md 文件的绝对路径

        Returns:
            解析后的字典，包含 metadata、parameters_schema、expert_knowledge
            知识型 SKILL 还会包含 code_patterns 字段
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. 提取 YAML Frontmatter
            metadata = self._extract_yaml_frontmatter(content)
            if not metadata:
                log.warning(f"[SkillParser] 无法提取 YAML 元数据: {filepath}")
                return None

            # 2. 判断 SKILL 类型
            skill_type = self._determine_skill_type(metadata, content)
            metadata["skill_type"] = skill_type

            # 3. 根据类型选择解析逻辑
            if skill_type == "knowledge":
                # 知识型 SKILL（OpenClaw 格式）
                result = self._parse_knowledge_skill(content, metadata)
            else:
                # 可执行型 SKILL（原有格式）
                # 提取参数 Schema
                parameters_schema = self._extract_parameters_schema(content)

                # 提取专家知识库
                expert_knowledge = self._extract_expert_knowledge(content)

                result = {
                    "metadata": metadata,
                    "parameters_schema": parameters_schema,
                    "expert_knowledge": expert_knowledge,
                    "is_knowledge_skill": False
                }

            return result

        except Exception as e:
            log.error(f"[SkillParser] 解析 SKILL.md 失败 ({filepath}): {e}")
            return None

    def _extract_yaml_frontmatter(self, content: str) -> Dict[str, Any]:
        """
        从 SKILL.md 内容中提取 YAML Frontmatter

        YAML Frontmatter 位于文件开头，由 --- 包裹
        """
        # 匹配 --- ... --- 之间的内容
        pattern = r'^---\s*\n(.*?)\n---'
        match = re.search(pattern, content, re.DOTALL)

        if match:
            yaml_content = match.group(1)
            try:
                # 移除注释行（以 # 开头的行）
                yaml_lines = []
                for line in yaml_content.split('\n'):
                    # 保留非注释行和键值对中的注释
                    stripped = line.strip()
                    if stripped.startswith('#') and ':' not in stripped:
                        continue
                    yaml_lines.append(line)
                clean_yaml = '\n'.join(yaml_lines)

                metadata = yaml.safe_load(clean_yaml)
                if metadata:
                    # 提取分类信息
                    metadata['category'] = metadata.get('category', 'general')
                    metadata['category_name'] = metadata.get('category_name', '通用')
                    metadata['subcategory'] = metadata.get('subcategory')
                    metadata['subcategory_name'] = metadata.get('subcategory_name')
                    metadata['tags'] = metadata.get('tags', [])

                    # 提取依赖信息（新增）
                    if 'dependencies' in metadata:
                        deps = metadata['dependencies']
                        if isinstance(deps, dict):
                            # 处理结构化依赖格式 {"python": [...], "r": [...]}
                            metadata['dependencies_dict'] = deps
                            # 扁平化依赖列表
                            flat_deps = []
                            for lang, pkg_list in deps.items():
                                if isinstance(pkg_list, list):
                                    flat_deps.extend(pkg_list)
                            metadata['dependencies'] = flat_deps
                        elif isinstance(deps, list):
                            metadata['dependencies'] = deps

                    # 提取文档链接（新增）
                    if 'documentation' in metadata:
                        metadata['documentation_links'] = metadata['documentation']

                    # 提取发布信息（新增）
                    metadata['visibility'] = metadata.get('visibility', 'public')
                    metadata['license'] = metadata.get('license', 'MIT')

                return metadata if metadata else {}
            except yaml.YAMLError as e:
                log.error(f"[SkillParser] YAML 解析错误: {e}")
                return {}

        return {}

    def _extract_parameters_schema(self, content: str) -> Dict[str, Any]:
        """
        从 SKILL.md 内容中提取参数表格，转换为 JSON Schema 格式

        目标格式：
        {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string|number|boolean|...",
                    "description": "...",
                    "default": "...",
                    "required": true/false
                }
            },
            "required": ["param1", "param2"]
        }
        """
        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }

        # 匹配第2节的参数表格
        # 表格格式: | 参数键名 | 数据类型 | 必填 | 默认值 | 详细描述说明 |
        section_pattern = r'## 2\..*?(?=## 3\.|## 3 |$)'
        section_match = re.search(section_pattern, content, re.DOTALL)

        if not section_match:
            return schema

        section_content = section_match.group(0)

        # 匹配表格行
        # 格式: | key | Type | Required/Yes/No | Default | Description |
        # 支持必填列格式: 是, 是, 否, 否, Required, Optional
        # 排除标题行（包含"参数键名"）和分隔行（以|---开头）
        table_row_pattern = r'\|\s*`?(\w+)`?\s*\|\s*(\w+(?:\([^)]*\))?)\s*\|\s*(是(?:\s*\(Yes\))?|Yes|否(?:\s*\(No\))?|No|Required|Optional)?\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|'

        for match in re.finditer(table_row_pattern, section_content):
            key = match.group(1)
            type_str = match.group(2).strip()
            required_str = match.group(3).strip() if match.group(3) else ""
            default_str = match.group(4).strip() if match.group(4) else ""
            description = match.group(5).strip() if match.group(5) else ""

            # 跳过表格标题行和分隔行
            if key in ['参数键名', 'Key', 'key', '参数'] or type_str.startswith('-') or key.startswith('-'):
                continue

            # 转换类型
            json_type = self._convert_type_to_json(type_str)

            # 判断是否必填（支持 "是" 和 "是" 两种格式）
            is_required = required_str.lower() in ['是', 'yes', 'required'] or required_str.startswith('是')

            # 构建属性
            prop = {
                "type": json_type,
                "description": description
            }

            # 保留原始类型信息（用于前端渲染不同的UI组件）
            type_lower = type_str.lower()
            if type_lower in ['directorypath', 'filepath']:
                prop["format"] = type_lower
            elif type_lower == 'sampletable':
                # 样本表类型：设置 format 为 sample-table
                prop["format"] = "sample-table"
                # 样本表类型的描述通常包含格式说明
                if "样本表" in description or "sample table" in description.lower():
                    prop["format_description"] = "TSV格式: sample_name<TAB>path<TAB>type<TAB>group"

            # 检查描述中是否包含 format: sample-table 标记
            if 'format: sample-table' in description.lower() or '支持 `format: sample-table' in description:
                prop["format"] = "sample-table"

            # 处理默认值
            if default_str and default_str.lower() not in ['', '无', 'none', 'n/a']:
                prop["default"] = self._parse_default_value(default_str, json_type)

            schema["properties"][key] = prop

            if is_required:
                schema["required"].append(key)

        return schema

    def _convert_type_to_json(self, type_str: str) -> str:
        """
        将 SKILL.md 中的类型标识转换为 JSON Schema 类型

        支持的特殊类型：
        - SampleTable: 样本表类型，映射为 object，设置 format 为 sample-table
        - FilePath/DirectoryPath: 文件/目录路径，映射为 string，设置 format
        """
        type_lower = type_str.lower()

        type_mapping = {
            "string": "string",
            "number": "number",
            "integer": "integer",
            "boolean": "boolean",
            "bool": "boolean",
            "array": "array",
            "jsonarray": "array",
            "object": "object",
            "directorypath": "string",
            "filepath": "string",
            "sampletable": "object",  # 样本表类型
        }

        # 检查是否包含某个类型关键字
        for key, json_type in type_mapping.items():
            if key in type_lower:
                return json_type

        return "string"  # 默认为 string

    def _parse_default_value(self, value_str: str, json_type: str):
        """
        解析默认值字符串为对应类型
        """
        if json_type == "boolean":
            return value_str.lower() in ['true', 'yes', '是', '1']
        elif json_type in ["number", "integer"]:
            try:
                return float(value_str) if json_type == "number" else int(value_str)
            except ValueError:
                return value_str
        else:
            # 移除引号
            return value_str.strip('"\'')

    def _extract_expert_knowledge(self, content: str) -> str:
        """
        从 SKILL.md 内容中提取专家知识库部分（第3节）

        专家知识库位于 ## 3. 操作指令与专家级知识库 之后的内容
        """
        # 匹配第3节直到文档结束或下一个同级标题
        pattern = r'## 3\..*?(?=## [0-4]\.|## [A-Z]|$$)'
        match = re.search(pattern, content, re.DOTALL)

        if match:
            knowledge = match.group(0)
            # 移除标题行本身
            knowledge = re.sub(r'^## 3\..*?\n', '', knowledge, count=1)
            return knowledge.strip()

        return ""

    # ==========================================
    # 知识型 SKILL 解析方法 (OpenClaw 规范)
    # ==========================================

    def _determine_skill_type(self, metadata: Dict[str, Any], content: str) -> str:
        """
        判断 SKILL 类型：knowledge | executable

        判断逻辑：
        1. 显式声明 skill_type 优先
        2. 隐式判断：有 executor_type 则为 executable
        3. 默认为知识型（OpenClaw 格式）

        Args:
            metadata: 已解析的 YAML 元数据
            content: SKILL.md 完整内容

        Returns:
            "knowledge" 或 "executable"
        """
        # 1. 显式声明优先
        if "skill_type" in metadata:
            return metadata["skill_type"]

        # 2. 隐式判断：有 executor_type 或 skill_id 则为 executable
        if "executor_type" in metadata or "skill_id" in metadata:
            return "executable"

        # 3. 默认为知识型（OpenClaw 格式）
        return "knowledge"

    def _parse_knowledge_skill(self, content: str, metadata: Dict[str, Any], bundle_path: str = "") -> Dict[str, Any]:
        """
        解析知识型 SKILL（OpenClaw 格式）

        知识型 SKILL 特点：
        - 元数据极简（name, description, tool_type, primary_tool）
        - 包含大量可复用的代码模式（Code Patterns）
        - 无系统调度概念，AI 直接参考生成代码

        Args:
            content: SKILL.md 完整内容
            metadata: YAML 元数据
            bundle_path: Bundle 目录路径

        Returns:
            解析后的字典，包含 metadata, code_patterns, expert_knowledge 等
        """
        # 生成 skill_id（如果没有显式定义）
        # 使用 name 字段转换为 snake_case 作为 skill_id
        skill_name = metadata.get("name", "unknown")
        skill_id = skill_name.lower().replace("-", "_").replace(" ", "_")

        # 提取代码模式
        code_patterns = self._extract_code_patterns(content)

        # 提取专家知识（对于知识型 SKILL，专家知识是整个文档内容）
        expert_knowledge = self._extract_knowledge_expert_content(content)

        # 构建返回结构（与可执行型 SKILL 保持兼容）
        result = {
            "metadata": {
                "skill_id": metadata.get("skill_id", skill_id),
                "skill_type": "knowledge",
                "name": skill_name,
                "description": metadata.get("description", ""),
                "tool_type": metadata.get("tool_type", "python"),
                "primary_tool": metadata.get("primary_tool", ""),
                "version": metadata.get("version", "1.0.0"),
                "category": metadata.get("category", "knowledge"),
                "category_name": metadata.get("category_name", "知识库"),
                "tags": metadata.get("tags", []),
            },
            "parameters_schema": {
                "type": "object",
                "properties": {},
                "required": []
            },
            "expert_knowledge": expert_knowledge,
            "code_patterns": code_patterns,
            "is_knowledge_skill": True
        }

        log.info(f"[SkillParser] 解析知识型 SKILL: {skill_id}, 代码模式数: {len(code_patterns)}")
        return result

    def _extract_code_patterns(self, content: str) -> List[Dict[str, str]]:
        """
        提取 SKILL.md 中的代码模式块

        知识型 SKILL 的代码模式格式：
        ### Pattern Name
        Description...
        ```python
        code here
        ```

        或直接在 ## Code Patterns 节下：
        ```python
        code here
        ```

        Args:
            content: SKILL.md 完整内容

        Returns:
            代码模式列表，每个元素包含 name, code, language
        """
        patterns = []

        # 模式1: 匹配 ### Pattern Name 后的代码块
        # 格式：### Pattern Name\n...```python\n...```
        named_pattern_regex = r'###\s*(.+?)\n.*?```(\w+)?\n(.*?)```'
        for match in re.finditer(named_pattern_regex, content, re.DOTALL):
            pattern_name = match.group(1).strip()
            language = match.group(2) if match.group(2) else "python"
            code = match.group(3).strip()

            # 跳过表格标题行等非代码模式
            if pattern_name.lower() in ['required imports', 'code patterns']:
                continue

            patterns.append({
                "name": pattern_name,
                "language": language,
                "code": code
            })

        # 模式2: 匹配 ## Code Patterns 节下的代码块（无标题）
        code_section = re.search(r'##\s*Code Patterns\s*\n(.*?)(?=##\s|$)', content, re.DOTALL | re.IGNORECASE)
        if code_section:
            section_content = code_section.group(1)
            # 匹配所有代码块
            code_block_regex = r'```(\w+)?\n(.*?)```'
            for idx, match in enumerate(re.finditer(code_block_regex, section_content, re.DOTALL)):
                language = match.group(1) if match.group(1) else "python"
                code = match.group(2).strip()

                # 检查是否已经被命名模式捕获（避免重复）
                code_hash = hash(code)
                already_captured = any(hash(p.get("code", "")) == code_hash for p in patterns)

                if not already_captured:
                    patterns.append({
                        "name": f"Pattern {idx + 1}",
                        "language": language,
                        "code": code
                    })

        # 模式3: 匹配所有独立的代码块（作为补充）
        # 当没有明确的 Code Patterns 节时，提取所有代码块
        if not patterns:
            code_block_regex = r'```(\w+)?\n(.*?)```'
            for idx, match in enumerate(re.finditer(code_block_regex, content, re.DOTALL)):
                language = match.group(1) if match.group(1) else "python"
                code = match.group(2).strip()

                # 跳过 YAML frontmatter 中的代码块
                if code.startswith('---') or len(code) < 20:
                    continue

                patterns.append({
                    "name": f"Code Example {idx + 1}",
                    "language": language,
                    "code": code
                })

        return patterns

    def _extract_knowledge_expert_content(self, content: str) -> str:
        """
        提取知识型 SKILL 的专家知识内容

        对于知识型 SKILL，专家知识是整个文档内容（去除 YAML frontmatter）
        因为这些内容都是为了帮助 AI 生成正确的代码

        Args:
            content: SKILL.md 完整内容

        Returns:
            专家知识文本
        """
        # 移除 YAML frontmatter
        clean_content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)
        return clean_content.strip()

    def get_skill_by_id(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 skill_id 获取对应的 SKILL 信息

        Args:
            skill_id: SKILL 的唯一标识符

        Returns:
            SKILL 信息字典，如果未找到则返回 None
        """
        skills = self.get_all_skills()
        for skill in skills:
            if skill.get("metadata", {}).get("skill_id") == skill_id:
                return skill
        return None

    def get_skill_bundle_path(self, skill_id: str) -> Optional[str]:
        """
        根据 skill_id 获取 Bundle 目录路径

        Args:
            skill_id: SKILL 的唯一标识符

        Returns:
            Bundle 目录路径，如果未找到则返回 None
        """
        skill = self.get_skill_by_id(skill_id)
        return skill.get("bundle_path") if skill else None


# 全局单例
_skill_parser_instance = None

def get_skill_parser() -> SkillBundleParser:
    """获取全局 SKILL 解析器实例（文件系统版本）"""
    global _skill_parser_instance
    if _skill_parser_instance is None:
        _skill_parser_instance = SkillBundleParser()
    return _skill_parser_instance


class DBSkillParser:
    """
    数据库 SKILL 解析器 - 支持基于用户 ID 的 RBAC 权限过滤

    查询规则：
    - 用户可以看到所有 PUBLISHED 状态的技能（公共技能）
    - 用户可以看到自己创建的所有状态技能（私有技能）
    """

    def __init__(self, user_id: int):
        """
        初始化数据库解析器

        Args:
            user_id: 当前用户 ID，用于权限过滤
        """
        self.user_id = user_id
        log.info(f"[DBSkillParser] 初始化数据库 SKILL 解析器，用户 ID: {user_id}")

    def get_all_skills(self) -> List[Dict[str, Any]]:
        """
        获取当前用户可见的所有 SKILL

        注意：
        - 草稿状态 (DRAFT) 的技能不会显示在执行列表中
        - 已下架 (DEPRECATED) 的技能也不会显示

        Returns:
            包含所有可见 SKILL 信息的列表
        """
        skills_list = []
        try:
            with Session(engine) as session:
                # RBAC 权限过滤：
                # 1. 所有 PUBLISHED 状态的技能（公共技能）
                # 2. 用户自己创建的非 DRAFT/DEPRECATED 状态技能
                # 注意：DRAFT 草稿和 DEPRECATED 已下架不显示在执行列表中
                statement = select(SkillAsset).where(
                    or_(
                        SkillAsset.status == SkillStatus.PUBLISHED,
                        and_(
                            SkillAsset.owner_id == self.user_id,
                            SkillAsset.status.notin_([SkillStatus.DRAFT, SkillStatus.DEPRECATED])
                        )
                    )
                ).order_by(SkillAsset.created_at.desc())

                db_skills = session.exec(statement).all()

                for s in db_skills:
                    # 判断技能类型：数据库中的技能默认为可执行型
                    # 除非显式声明为知识型
                    skill_type = getattr(s, 'skill_type', 'executable') if hasattr(s, 'skill_type') else 'executable'
                    is_knowledge = skill_type == 'knowledge'

                    # 将数据库模型转为 AI 熟悉的旧版 JSON 结构，保持向下兼容
                    skills_list.append({
                        "metadata": {
                            "skill_id": s.skill_id,
                            "skill_type": skill_type,
                            "name": s.name,
                            "description": s.description,
                            "executor_type": s.executor_type,
                            "version": s.version,
                            "author": f"user_{s.owner_id}",
                            "status": s.status.value if s.status else "DRAFT",
                            # 新增分类信息
                            "category": s.category,
                            "category_name": s.category_name,
                            "subcategory": s.subcategory,
                            "subcategory_name": s.subcategory_name,
                            "tags": s.tags or [],
                            # 新增发布信息
                            "visibility": s.visibility,
                            "license": s.license,
                        },
                        "parameters_schema": s.parameters_schema or {},
                        "expert_knowledge": s.expert_knowledge or "暂无专家指导。",
                        "script_code": s.script_code,
                        "dependencies": s.dependencies or [],
                        "source": "database",  # 标记来源
                        "owner_id": s.owner_id,
                        "is_knowledge_skill": is_knowledge,
                        # 新增统计信息
                        "usage_count": s.usage_count or 0,
                        "avg_rating": s.avg_rating or 0.0,
                        "favorite_count": s.favorite_count or 0
                    })

            log.info(f"[DBSkillParser] 查询到 {len(skills_list)} 个可见 SKILL")
            return skills_list

        except Exception as e:
            log.error(f"[DBSkillParser] 从数据库加载 SKILL 失败: {e}")
            return []

    def get_skill_by_id(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 skill_id 获取单个 SKILL（带权限检查）

        Args:
            skill_id: SKILL 的唯一标识符

        Returns:
            SKILL 信息字典，如果无权限或不存在则返回 None
        """
        try:
            with Session(engine) as session:
                skill = session.exec(
                    select(SkillAsset).where(SkillAsset.skill_id == skill_id)
                ).first()

                if not skill:
                    return None

                # 权限检查：必须是 PUBLISHED 或 自己创建的
                if skill.status != SkillStatus.PUBLISHED and skill.owner_id != self.user_id:
                    log.warning(f"[DBSkillParser] 用户 {self.user_id} 无权访问 SKILL: {skill_id}")
                    return None

                # 判断技能类型
                skill_type = getattr(skill, 'skill_type', 'executable') if hasattr(skill, 'skill_type') else 'executable'
                is_knowledge = skill_type == 'knowledge'

                return {
                    "metadata": {
                        "skill_id": skill.skill_id,
                        "skill_type": skill_type,
                        "name": skill.name,
                        "description": skill.description,
                        "executor_type": skill.executor_type,
                        "version": skill.version,
                        "author": f"user_{skill.owner_id}",
                        "status": skill.status.value if skill.status else "DRAFT",
                        # 新增分类信息
                        "category": skill.category,
                        "category_name": skill.category_name,
                        "subcategory": skill.subcategory,
                        "subcategory_name": skill.subcategory_name,
                        "tags": skill.tags or [],
                        # 新增发布信息
                        "visibility": skill.visibility,
                        "license": skill.license,
                    },
                    "parameters_schema": skill.parameters_schema or {},
                    "expert_knowledge": skill.expert_knowledge or "暂无专家指导。",
                    "script_code": skill.script_code,
                    "dependencies": skill.dependencies or [],
                    "source": "database",
                    "owner_id": skill.owner_id,
                    "is_knowledge_skill": is_knowledge,
                    # 新增统计信息
                    "usage_count": skill.usage_count or 0,
                    "avg_rating": skill.avg_rating or 0.0,
                    "favorite_count": skill.favorite_count or 0
                }

        except Exception as e:
            log.error(f"[DBSkillParser] 查询 SKILL 失败: {e}")
            return None


def get_db_skill_parser(user_id: int) -> DBSkillParser:
    """
    获取数据库 SKILL 解析器实例

    Args:
        user_id: 当前用户 ID

    Returns:
        DBSkillParser 实例
    """
    return DBSkillParser(user_id=user_id)


@lru_cache(maxsize=128)
def _get_combined_skills_cached(user_id: int) -> tuple:
    """
    内部缓存版本（返回 tuple 避免列表被修改污染缓存）
    """
    all_skills = []
    seen_skill_ids = set()

    # 1. 从数据库加载技能（优先级高，包含影子记录）
    try:
        db_parser = get_db_skill_parser(user_id)
        db_skills = db_parser.get_all_skills()
        for skill in db_skills:
            skill_id = skill.get("metadata", {}).get("skill_id")
            if skill_id and skill_id not in seen_skill_ids:
                seen_skill_ids.add(skill_id)
                skill["source"] = "database"
                all_skills.append(skill)
        log.info(f"[CombinedSkills] 从数据库加载 {len(db_skills)} 个技能")
    except Exception as e:
        log.warning(f"[CombinedSkills] 数据库技能加载失败: {e}")

    # 2. 从文件系统补充缺失的官方预置技能
    try:
        fs_parser = get_skill_parser()
        fs_skills = fs_parser.get_all_skills()
        added_count = 0
        for skill in fs_skills:
            skill_id = skill.get("metadata", {}).get("skill_id")
            if skill_id and skill_id not in seen_skill_ids:
                seen_skill_ids.add(skill_id)
                skill["source"] = "filesystem"
                skill["owner_id"] = 0  # 官方技能
                all_skills.append(skill)
                added_count += 1
        if added_count > 0:
            log.info(f"[CombinedSkills] 从文件系统补充 {added_count} 个官方技能")
    except Exception as e:
        log.warning(f"[CombinedSkills] 文件系统技能加载失败: {e}")

    log.info(f"[CombinedSkills] 总计 {len(all_skills)} 个可用技能")
    return tuple(all_skills)  # tuple 不可变，避免缓存污染


def get_combined_skills(user_id: int) -> List[Dict[str, Any]]:
    """
    获取合并的 SKILL 列表（文件系统 + 数据库）

    这是供 AI Agent 使用的主要接口，返回用户可见的所有技能

    去重逻辑：
    - 如果 skill_id 同时存在于文件系统和数据库，优先使用数据库版本（包含用户修改的配置）
    - 文件系统技能作为补充，只添加数据库中不存在的技能

    注意：内部使用 LRU 缓存，返回深拷贝以避免缓存污染

    Args:
        user_id: 当前用户 ID

    Returns:
        合并后的 SKILL 列表（深拷贝）
    """
    cached = _get_combined_skills_cached(user_id)
    return copy.deepcopy(list(cached))


def get_combined_skill_by_id(user_id: int, skill_id: str) -> Optional[Dict[str, Any]]:
    """
    根据 skill_id 获取技能详情（文件系统 + 数据库合并查询）

    这是供 AI Agent 获取单个技能详情的主要接口，支持官方预置技能和用户自定义技能。

    Args:
        user_id: 当前用户 ID（用于数据库技能的权限检查）
        skill_id: SKILL 的唯一标识符

    Returns:
        技能详情字典，如果未找到或无权限则返回 None
    """
    # 1. 先尝试从文件系统查找（官方预置技能）
    try:
        fs_parser = get_skill_parser()
        fs_skill = fs_parser.get_skill_by_id(skill_id)
        if fs_skill:
            fs_skill["source"] = "filesystem"
            fs_skill["owner_id"] = 0
            log.info(f"[CombinedSkill] 从文件系统找到技能: {skill_id}")
            return fs_skill
    except Exception as e:
        log.warning(f"[CombinedSkill] 文件系统查询失败: {e}")

    # 2. 再尝试从数据库查找（用户自定义技能）
    try:
        db_parser = get_db_skill_parser(user_id)
        db_skill = db_parser.get_skill_by_id(skill_id)
        if db_skill:
            log.info(f"[CombinedSkill] 从数据库找到技能: {skill_id}")
            return db_skill
    except Exception as e:
        log.warning(f"[CombinedSkill] 数据库查询失败: {e}")

    log.warning(f"[CombinedSkill] 未找到技能: {skill_id}")
    return None


# ==========================================
# Sample Sheet 配置提取
# ==========================================

def get_sample_sheet_config(skill_id: str) -> Dict[str, Any]:
    """
    从 SKILL.md 中提取 Sample Sheet 列配置

    根据参数表格中的 sample_table 类型参数，提取其列定义信息。
    如果 SKILL.md 中没有明确定义列配置，则根据 skill_id 返回默认配置。

    Args:
        skill_id: SKILL 的唯一标识符

    Returns:
        包含列配置的字典：
        {
            "has_sample_table": bool,  # 是否有 sample-table 类型参数
            "param_name": str,         # 参数名（如 sample_sheet）
            "format_type": str,        # 格式类型（fastqc/singlecell/generic）
            "columns": [               # 列定义
                {
                    "key": "sample_name",
                    "label": "样本名",
                    "required": True,
                    "editable": True,
                    "options": None  # 下拉选项（如有）
                }
            ],
            "description": str         # 格式说明
        }
    """
    log.info(f"[SampleSheetConfig] 提取 SKILL 列配置: {skill_id}")

    # 获取 SKILL 信息
    parser = get_skill_parser()
    skill = parser.get_skill_by_id(skill_id)

    if not skill:
        # 尝试从数据库查找
        # 这里使用默认用户 ID，实际使用时应该传入 user_id
        log.warning(f"[SampleSheetConfig] 未找到 SKILL: {skill_id}")
        return _get_default_sample_sheet_config(skill_id)

    # 检查参数中是否有 sample-table 格式
    schema = skill.get("parameters_schema", {})
    properties = schema.get("properties", {})

    sample_table_param = None
    for param_name, prop in properties.items():
        if prop.get("format") == "sample-table":
            sample_table_param = param_name
            break

    if not sample_table_param:
        log.info(f"[SampleSheetConfig] SKILL 无 sample-table 参数: {skill_id}")
        return {
            "has_sample_table": False,
            "param_name": None,
            "format_type": "none",
            "columns": [],
            "description": "该 SKILL 不需要 Sample Sheet 输入"
        }

    # 根据 skill_id 确定格式类型
    format_type = _detect_format_type(skill_id)

    # 获取列配置
    columns = _get_columns_for_format(format_type)

    return {
        "has_sample_table": True,
        "param_name": sample_table_param,
        "format_type": format_type,
        "columns": columns,
        "description": _get_format_description(format_type)
    }


def _detect_format_type(skill_id: str) -> str:
    """
    根据 skill_id 检测 Sample Sheet 格式类型

    Args:
        skill_id: SKILL ID

    Returns:
        格式类型：fastqc, singlecell, rnaseq, generic
    """
    skill_id_lower = skill_id.lower()

    if "fastqc" in skill_id_lower or "fastq" in skill_id_lower:
        return "fastqc"
    elif "singlecell" in skill_id_lower or "single_cell" in skill_id_lower or "sc" in skill_id_lower:
        return "singlecell"
    elif "rnaseq" in skill_id_lower or "rna" in skill_id_lower:
        return "rnaseq"
    else:
        return "generic"


def _get_columns_for_format(format_type: str) -> List[Dict[str, Any]]:
    """
    获取指定格式类型的列定义

    Args:
        format_type: 格式类型

    Returns:
        列定义列表
    """
    if format_type == "fastqc":
        return [
            {
                "key": "sample_name",
                "label": "样本名",
                "required": True,
                "editable": True,
                "description": "样本唯一标识符"
            },
            {
                "key": "read1_path",
                "label": "Read1 路径",
                "required": True,
                "editable": True,
                "description": "Read1 FastQ 文件路径"
            },
            {
                "key": "read2_path",
                "label": "Read2 路径",
                "required": False,
                "editable": True,
                "description": "Read2 FastQ 文件路径（双端测序）"
            }
        ]
    elif format_type == "singlecell":
        return [
            {
                "key": "sample_name",
                "label": "样本名",
                "required": True,
                "editable": True,
                "description": "样本唯一标识符"
            },
            {
                "key": "input_path",
                "label": "输入路径",
                "required": True,
                "editable": True,
                "description": "数据文件或目录路径"
            },
            {
                "key": "input_format",
                "label": "数据格式",
                "required": True,
                "editable": True,
                "options": ["10x", "exp", "h5", "BD", "rds", "rdsraw"],
                "description": "数据格式类型"
            },
            {
                "key": "group_label",
                "label": "分组标签",
                "required": True,
                "editable": True,
                "description": "分组标签，用于差异分析"
            }
        ]
    elif format_type == "rnaseq":
        return [
            {
                "key": "sample_name",
                "label": "样本名",
                "required": True,
                "editable": True,
                "description": "样本唯一标识符"
            },
            {
                "key": "read1_path",
                "label": "Read1 路径",
                "required": True,
                "editable": True,
                "description": "Read1 FastQ 文件路径"
            },
            {
                "key": "read2_path",
                "label": "Read2 路径",
                "required": True,
                "editable": True,
                "description": "Read2 FastQ 文件路径（双端测序）"
            },
            {
                "key": "group_label",
                "label": "分组标签",
                "required": True,
                "editable": True,
                "description": "分组标签，用于差异分析（如 Control, Treatment）"
            }
        ]
    else:
        # 通用格式
        return [
            {
                "key": "sample_name",
                "label": "样本名",
                "required": True,
                "editable": True,
                "description": "样本唯一标识符"
            },
            {
                "key": "path",
                "label": "路径",
                "required": True,
                "editable": True,
                "description": "数据文件路径"
            },
            {
                "key": "type",
                "label": "类型",
                "required": False,
                "editable": True,
                "description": "数据类型"
            },
            {
                "key": "group",
                "label": "分组",
                "required": False,
                "editable": True,
                "description": "分组标签"
            }
        ]


def _get_format_description(format_type: str) -> str:
    """获取格式说明文本"""
    if format_type == "fastqc":
        return "FastQC Sample Sheet：包含样本名、Read1 路径、Read2 路径（可选）"
    elif format_type == "singlecell":
        return "单细胞 Sample Sheet：包含样本名、输入路径、数据格式、分组标签"
    elif format_type == "rnaseq":
        return "RNA-seq Sample Sheet：包含样本名、Read1 路径、Read2 路径、分组标签"
    else:
        return "通用 Sample Sheet：包含样本名、路径、类型、分组"


def _get_default_sample_sheet_config(skill_id: str) -> Dict[str, Any]:
    """获取默认的 Sample Sheet 配置（当 SKILL 未找到时）"""
    format_type = _detect_format_type(skill_id)

    return {
        "has_sample_table": True,
        "param_name": "sample_sheet",
        "format_type": format_type,
        "columns": _get_columns_for_format(format_type),
        "description": _get_format_description(format_type)
    }