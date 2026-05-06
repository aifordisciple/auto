"""
技能参数注册表 - 从 SKILL.md / 数据库动态拉取参数定义。

供 L2 Active Probing 使用，将技能的 parameters_schema 转换为
前端 JSON Schema 表单定义，实现动态参数探查。

核心功能：
1. get_parameters_schema(skill_id): 获取技能的完整参数 schema
2. get_required_params(skill_id): 获取技能的必填参数名列表
3. build_ui_schema(skill_id, missing_params): 构建前端表单 JSON Schema

数据源：
- 文件系统：通过 skill_parser.get_skill_from_db_index() 解析 SKILL.md
- 数据库：通过 SkillAsset.parameters_schema JSONB 列读取
- 优先级：文件系统 > 数据库（与 skill_parser 保持一致）
"""
from typing import Any, Dict, List, Optional

from app.core.skill_parser import get_skill_from_db_index
from app.core.logger import log


# 自定义 format 字段的前端提示映射
FORMAT_HINTS = {
    "filepath": "请输入文件路径",
    "directorypath": "请输入目录路径",
    "sample-table": "请输入样本表路径",
}


class SkillParameterRegistry:
    """
    技能参数注册表：从 SKILL.md / DB 动态拉取参数定义。

    程序说明：
    封装 skill_parser.get_skill_from_db_index()，为 L2 参数探查提供
    技能的 parameters_schema 查询和前端表单 JSON Schema 生成能力。
    当技能不存在或无参数定义时，返回 None / 空列表，确保 L2 能优雅降级。
    """

    def __init__(self, session, user_id):
        """
        初始化参数注册表。

        程序说明：
        保存数据库会话和用户 ID，用于 skill_parser 的 RBAC 权限过滤。
        skill_parser 内部使用 LRU 缓存，避免重复解析 SKILL.md 文件。
        user_id 统一转为 int 类型，因为 skill_parser.get_skill_from_db_index 要求 int。

        Args:
            session: 数据库会话（skill_parser 内部自行创建会话，此处保留以兼容接口）
            user_id: 当前用户 ID（int 或 str，内部转为 int）
        """
        self.session = session
        # skill_parser.get_skill_from_db_index 要求 user_id 为 int
        self.user_id = int(user_id) if user_id is not None else 0

    async def get_parameters_schema(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        获取技能的完整参数 schema。

        程序说明：
        调用 skill_parser.get_skill_from_db_index() 获取技能详情，
        从中提取 parameters_schema 字段。该字段包含 properties（各参数定义）
        和 required（必填参数名列表），遵循标准 JSON Schema 格式。

        Args:
            skill_id: 技能的唯一标识符

        Returns:
            参数 schema dict，格式: {"type": "object", "properties": {...}, "required": [...]}
            如果技能不存在或无参数定义，返回 None
        """
        try:
            skill = get_skill_from_db_index(skill_id)
            if not skill:
                log.debug(f"[SkillParamRegistry] 技能不存在: {skill_id}")
                return None

            schema = skill.get("parameters_schema")
            if not schema or not schema.get("properties"):
                log.debug(f"[SkillParamRegistry] 技能无参数定义: {skill_id}")
                return None

            log.debug(f"[SkillParamRegistry] 获取参数 schema: {skill_id}, "
                      f"properties={len(schema.get('properties', {}))}, "
                      f"required={schema.get('required', [])}")
            return schema

        except Exception as e:
            log.warning(f"[SkillParamRegistry] 获取参数 schema 失败: {skill_id}, error={e}")
            return None

    async def get_required_params(self, skill_id: str) -> List[str]:
        """
        获取技能的必填参数名列表。

        程序说明：
        从 parameters_schema 的 required 数组中提取必填参数名。
        如果技能不存在或无必填参数，返回空列表。

        Args:
            skill_id: 技能的唯一标识符

        Returns:
            必填参数名列表，如 ["sample_sheet", "output_dir"]
            如果技能不存在，返回空列表
        """
        schema = await self.get_parameters_schema(skill_id)
        if not schema:
            return []
        return schema.get("required", [])

    async def build_ui_schema(
        self,
        skill_id: str,
        missing_params: List[str]
    ) -> Dict[str, Any]:
        """
        从技能 schema 构建前端 JSON Schema 表单定义。

        程序说明：
        仅包含缺失参数的属性定义，供 ParameterProbingCard 渲染。
        处理自定义 format 字段（filepath、directorypath、sample-table），
        为前端添加提示信息。保留参数的 enum、default、minimum、maximum
        等约束，确保前端表单的输入验证与技能定义一致。

        Args:
            skill_id: 技能的唯一标识符
            missing_params: 缺失的参数名列表

        Returns:
            JSON Schema object，格式: {"type": "object", "properties": {...}, "required": [...]}
        """
        schema = await self.get_parameters_schema(skill_id)
        if not schema:
            # 技能不存在时，返回通用 fallback schema
            return _build_fallback_ui_schema(missing_params)

        all_properties = schema.get("properties", {})
        filtered_properties = {}
        required_list = []

        for param_name in missing_params:
            if param_name in all_properties:
                # 从技能 schema 中复制该参数的定义
                prop = dict(all_properties[param_name])

                # 为自定义 format 字段添加前端提示
                format_type = prop.get("format")
                if format_type and format_type in FORMAT_HINTS:
                    prop["hint"] = FORMAT_HINTS[format_type]

                # 确保 title 字段存在（前端渲染需要）
                if "title" not in prop:
                    prop["title"] = param_name

                filtered_properties[param_name] = prop
                required_list.append(param_name)
            else:
                # 参数不在技能 schema 中，使用通用 string 定义
                filtered_properties[param_name] = {
                    "type": "string",
                    "title": param_name,
                }
                required_list.append(param_name)

        ui_schema = {
            "type": "object",
            "properties": filtered_properties,
            "required": required_list
        }

        log.debug(f"[SkillParamRegistry] 构建 UI schema: skill_id={skill_id}, "
                  f"missing={missing_params}, properties={list(filtered_properties.keys())}")

        return ui_schema


def _build_fallback_ui_schema(missing_params: List[str]) -> Dict[str, Any]:
    """
    构建通用 fallback UI schema（当技能不存在时使用）。

    程序说明：
    当 skill_id 无法解析或 skill_registry 不可用时，
    为缺失参数生成简单的 string 类型表单定义。
    特殊处理 species 参数（添加 enum 选项）和 input_file 参数（添加 filepath hint）。

    Args:
        missing_params: 缺失的参数名列表

    Returns:
        JSON Schema object
    """
    properties = {}

    # species 参数：添加常见物种 enum
    if "species" in missing_params:
        properties["species"] = {
            "type": "string",
            "title": "物种 (Species)",
            "enum": ["Human", "Mouse", "Rat", "Zebrafish"],
            "default": "Human"
        }

    # input_file 参数：添加 filepath hint
    if "input_file" in missing_params:
        properties["input_file"] = {
            "type": "string",
            "title": "输入文件路径",
            "hint": "请输入文件路径"
        }

    # 其他参数：通用 string 定义
    for param in missing_params:
        if param not in properties:
            properties[param] = {
                "type": "string",
                "title": param,
            }

    return {
        "type": "object",
        "properties": properties,
        "required": missing_params
    }