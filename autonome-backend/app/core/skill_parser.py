"""
SKILL Bundle Parser - 解析 SKILL.md 文件，提取元数据、参数 Schema 和专家知识库

SKILL.md 格式规范：
1. YAML Frontmatter（---包裹）包含核心元数据
2. 第2节（## 2. 动态参数定义规范）包含参数表格
3. 第3节（## 3. 操作指令与专家级知识库）包含专家知识
"""

import os
import re
import json
from typing import Dict, List, Any, Optional
from pathlib import Path

import yaml
from app.core.logger import log


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

        Args:
            filepath: SKILL.md 文件的绝对路径

        Returns:
            解析后的字典，包含 metadata、parameters_schema、expert_knowledge
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. 提取 YAML Frontmatter
            metadata = self._extract_yaml_frontmatter(content)
            if not metadata:
                log.warning(f"[SkillParser] 无法提取 YAML 元数据: {filepath}")
                return None

            # 2. 提取参数 Schema
            parameters_schema = self._extract_parameters_schema(content)

            # 3. 提取专家知识库
            expert_knowledge = self._extract_expert_knowledge(content)

            return {
                "metadata": metadata,
                "parameters_schema": parameters_schema,
                "expert_knowledge": expert_knowledge
            }

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
        table_row_pattern = r'\|\s*`?(\w+)`?\s*\|\s*(\w+(?:\([^)]*\))?)\s*\|\s*(是|Yes|否|No|Required|Optional)?\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|'

        for match in re.finditer(table_row_pattern, section_content):
            key = match.group(1)
            type_str = match.group(2).strip()
            required_str = match.group(3).strip() if match.group(3) else ""
            default_str = match.group(4).strip() if match.group(4) else ""
            description = match.group(5).strip() if match.group(5) else ""

            # 转换类型
            json_type = self._convert_type_to_json(type_str)

            # 判断是否必填
            is_required = required_str.lower() in ['是', 'yes', 'required']

            # 构建属性
            prop = {
                "type": json_type,
                "description": description
            }

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
            "filepath": "string"
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
    """获取全局 SKILL 解析器实例"""
    global _skill_parser_instance
    if _skill_parser_instance is None:
        _skill_parser_instance = SkillBundleParser()
    return _skill_parser_instance