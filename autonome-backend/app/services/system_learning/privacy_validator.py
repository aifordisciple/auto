"""
隐私验证器 - 确保提取内容完全脱敏

隐私保护规则:
1. 禁止提取用户数据（基因序列、样本名、具体数值）
2. 禁止提取项目路径或文件名
3. 禁止提取组织/团队/个人信息
4. 仅提取抽象化方法论

这是系统学习层的关键安全组件，确保从用户对话中提取的方法论
不包含任何可识别的用户数据或敏感信息。

使用方式:
    from app.services.system_learning.privacy_validator import get_privacy_validator

    validator = get_privacy_validator()
    is_valid, errors = validator.validate(content)
    redacted_content = validator.redact(content)
"""

import re
from typing import Tuple, List, Dict, Any, Optional
from dataclasses import dataclass, field

from app.core.logger import log


@dataclass
class PrivacyRule:
    """
    隐私规则定义

    每个规则包含:
    - pattern: 正则表达式模式，用于匹配敏感信息
    - replacement: 替换文本，用于脱敏处理
    - description: 规则描述，用于错误提示
    - severity: 错误级别，error（阻止）或 warning（警告）

    属性:
        pattern: 正则表达式模式字符串
        replacement: 匹配内容的替换文本
        description: 规则的中文描述
        severity: 错误严重程度（"error" 或 "warning"）
        example: 可选的示例匹配内容，用于文档说明
    """
    pattern: str
    replacement: str
    description: str
    severity: str  # "error" | "warning"
    example: Optional[str] = None


# ============================================================================
# 默认隐私规则配置
# ============================================================================
# 这些规则覆盖了生物信息学数据分析场景中常见的敏感信息类型

PRIVACY_RULES: List[PrivacyRule] = [
    # -------------------------------------------------------------------------
    # 文件路径检测 - 错误级别
    # -------------------------------------------------------------------------
    # 匹配 Unix/Linux 文件路径，包含常见的数据文件扩展名
    # 例如: /data/project/sample.py, ./output/results.csv
    PrivacyRule(
        pattern=r'/[\w\-./]+\.(py|r|txt|csv|tsv|json|yaml|yml|fasta|fastq|bam|vcf|bed|gtf)',
        replacement='<FILE_PATH>',
        description="文件路径必须脱敏",
        severity="error",
        example="/data/project/counts.csv"
    ),

    # -------------------------------------------------------------------------
    # 相对路径检测 - 错误级别
    # -------------------------------------------------------------------------
    # 匹配相对路径格式，如 ./path/to/file 或 ../path/to/file
    PrivacyRule(
        pattern=r'\.{1,2}/[\w\-./]+\.(py|r|txt|csv|tsv|json|yaml|yml|fasta|fastq|bam|vcf|bed|gtf)',
        replacement='<FILE_PATH>',
        description="相对路径必须脱敏",
        severity="error",
        example="./output/results.tsv"
    ),

    # -------------------------------------------------------------------------
    # 基因序列标识 - 错误级别
    # -------------------------------------------------------------------------
    # Ensembl ID 格式检测，包含:
    # - ENSG: Gene ID (如 ENSG00000123456)
    # - ENST: Transcript ID (如 ENST00000234567)
    # - ENSP: Protein ID (如 ENSP00000345678)
    # - ENSMUSG: Mouse Gene ID
    # - ENSMUST: Mouse Transcript ID
    PrivacyRule(
        pattern=r'(ENSG|ENST|ENSP|ENSMUSG|ENSMUST|ENSMUSP)[0-9]+',
        replacement='<GENE_ID>',
        description="基因ID必须脱敏",
        severity="error",
        example="ENSG00000123456"
    ),

    # -------------------------------------------------------------------------
    # 样本名检测 - 错误级别
    # -------------------------------------------------------------------------
    # 匹配常见样本命名格式:
    # - sample_001, sample-001, Sample_001
    # - SAMPLE001, Sample-1, sample01
    PrivacyRule(
        pattern=r'(sample|Sample|SAMPLE)[_-]?[0-9]+',
        replacement='<SAMPLE_ID>',
        description="样本名必须脱敏",
        severity="error",
        example="sample_001"
    ),

    # -------------------------------------------------------------------------
    # 组织/团队名检测 - 错误级别
    # -------------------------------------------------------------------------
    # 匹配可能暴露组织信息的命名模式:
    # - lab-xxx, team-xxx, group-xxx
    # - project-xxx, org-xxx
    PrivacyRule(
        pattern=r'(lab|team|group|project|org|Lab|Team|Group|Project|Org)[_-]?[\w\-]+',
        replacement='<ORG>',
        description="组织名称必须脱敏",
        severity="error",
        example="lab-genomics"
    ),

    # -------------------------------------------------------------------------
    # URL 检测 - 错误级别
    # -------------------------------------------------------------------------
    # 匹配 HTTP/HTTPS URL，可能包含服务器地址或 API 端点
    PrivacyRule(
        pattern=r'https?://[^\s<>"\'{}|\\^`\[\]]+',
        replacement='<URL>',
        description="URL必须脱敏",
        severity="error",
        example="https://example.com/data"
    ),

    # -------------------------------------------------------------------------
    # 具体数值检测 - 警告级别
    # -------------------------------------------------------------------------
    # 匹配 4 位以上的数字，可能代表:
    # - 数据量（如 10000 个细胞）
    # - 参数值（如 cutoff=5000）
    # - 统计结果（如 p-value=0.0001）
    #
    # 注意: 这是警告级别，因为某些技术参数可能是合理的
    PrivacyRule(
        pattern=r'\b\d{4,}\b',
        replacement='<NUMBER>',
        description="具体数值可能需要脱敏（警告级别）",
        severity="warning",
        example="10000"
    ),

    # -------------------------------------------------------------------------
    # IP 地址检测 - 错误级别
    # -------------------------------------------------------------------------
    # 匹配 IPv4 地址，可能暴露服务器或内部网络信息
    PrivacyRule(
        pattern=r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        replacement='<IP_ADDRESS>',
        description="IP地址必须脱敏",
        severity="error",
        example="192.168.1.100"
    ),

    # -------------------------------------------------------------------------
    # UUID 检测 - 错误级别
    # -------------------------------------------------------------------------
    # 匹配 UUID 格式，可能关联特定用户或会话
    PrivacyRule(
        pattern=r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
        replacement='<UUID>',
        description="UUID必须脱敏",
        severity="error",
        example="550e8400-e29b-41d4-a716-446655440000"
    ),

    # -------------------------------------------------------------------------
    # 邮箱地址检测 - 错误级别
    # -------------------------------------------------------------------------
    # 匹配邮箱格式，直接暴露用户身份
    PrivacyRule(
        pattern=r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        replacement='<EMAIL>',
        description="邮箱地址必须脱敏",
        severity="error",
        example="user@example.com"
    ),

    # -------------------------------------------------------------------------
    # 手机号检测 - 错误级别
    # -------------------------------------------------------------------------
    # 匹配中国大陆手机号格式（11位数字，以1开头）
    PrivacyRule(
        pattern=r'\b1[3-9]\d{9}\b',
        replacement='<PHONE>',
        description="手机号码必须脱敏",
        severity="error",
        example="13812345678"
    ),

    # -------------------------------------------------------------------------
    # 时间戳检测 - 警告级别
    # -------------------------------------------------------------------------
    # 匹配 ISO 8601 格式时间戳，可能关联特定操作时间
    PrivacyRule(
        pattern=r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}',
        replacement='<TIMESTAMP>',
        description="时间戳可能需要脱敏（警告级别）",
        severity="warning",
        example="2024-01-15T10:30:00"
    ),
]


# ============================================================================
# 禁止关键词列表
# ============================================================================
# 这些关键词如果出现在内容中，直接标记为隐私违规
# 包含多语言的关键词，以适应不同用户的使用习惯

FORBIDDEN_KEYWORDS: List[str] = [
    # -------------------------------------------------------------------------
    # 认证信息关键词
    # -------------------------------------------------------------------------
    "用户名", "密码", "password", "token", "api_key", "secret",
    "apikey", "api-key", "apiKey", "accessToken", "access_token",
    "private_key", "privatekey", "credentials", "credential",

    # -------------------------------------------------------------------------
    # 项目信息关键词
    # -------------------------------------------------------------------------
    "项目名称", "项目编号", "项目代号",
    "project_name", "projectId", "project_id",

    # -------------------------------------------------------------------------
    # 组织信息关键词
    # -------------------------------------------------------------------------
    "组织名称", "团队名称", "公司名称", "实验室名称",
    "organization", "team_name", "company_name", "lab_name",

    # -------------------------------------------------------------------------
    # 个人信息关键词
    # -------------------------------------------------------------------------
    "客户名称", "病人姓名", "患者姓名", "姓名",
    "customer_name", "patient_name", "user_name",

    # -------------------------------------------------------------------------
    # 生物样本关键词
    # -------------------------------------------------------------------------
    "病人ID", "患者ID", "样本来源", "捐赠者",
    "patient_id", "donor_id", "donor_name",

    # -------------------------------------------------------------------------
    # 服务器信息关键词
    # -------------------------------------------------------------------------
    "服务器地址", "数据库地址", "服务器密码",
    "server_address", "database_host", "db_password",
]


class PrivacyValidator:
    """
    隐私验证器类

    核心功能:
    1. validate(): 验证内容是否符合隐私规则，返回是否通过和错误列表
    2. redact(): 自动脱敏内容，替换敏感信息为占位符
    3. validate_candidate(): 验证技能候选字典的所有字段

    使用示例:
        >>> validator = PrivacyValidator()
        >>> content = "处理 /data/sample_001.csv 文件"
        >>> is_valid, errors = validator.validate(content)
        >>> print(is_valid)  # False
        >>> print(errors)    # ["文件路径必须脱敏: 发现 1 处匹配..."]

        >>> redacted = validator.redact(content)
        >>> print(redacted)  # "处理 <FILE_PATH> 文件"

    设计原则:
    - 所有规则使用正则表达式进行匹配
    - 错误级别分为 error（阻止）和 warning（警告）
    - 脱敏时使用语义清晰的占位符（如 <GENE_ID>）
    - 支持自定义规则扩展
    """

    def __init__(self, rules: Optional[List[PrivacyRule]] = None):
        """
        初始化隐私验证器

        Args:
            rules: 自定义隐私规则列表，如果为 None 则使用默认规则
        """
        self.rules = rules or PRIVACY_RULES
        # 预编译正则表达式以提高性能
        self._compiled_patterns: List[re.Pattern] = []
        for rule in self.rules:
            try:
                compiled = re.compile(rule.pattern)
                self._compiled_patterns.append(compiled)
            except re.error as e:
                log.warning(f"隐私规则正则表达式编译失败: {rule.pattern}, 错误: {e}")

    def validate(self, content: str) -> Tuple[bool, List[str]]:
        """
        验证内容是否符合隐私规则

        检测流程:
        1. 遍历所有隐私规则，使用正则表达式匹配
        2. 记录匹配结果，按错误级别分类
        3. 检查禁止关键词是否出现
        4. 返回验证结果和错误列表

        Args:
            content: 待验证的内容字符串

        Returns:
            Tuple[bool, List[str]]:
                - bool: 是否通过验证（无 error 级别错误）
                - List[str]: 错误和警告消息列表

        示例:
            >>> validator = PrivacyValidator()
            >>> content = "分析基因 ENSG00000123456 的表达"
            >>> is_valid, errors = validator.validate(content)
            >>> print(is_valid)  # False
            >>> print(errors)    # ["基因ID必须脱敏: 发现 1 处匹配..."]
        """
        # 存储错误和警告消息
        errors: List[str] = []
        warnings: List[str] = []

        # -------------------------------------------------------------------------
        # 1. 正则表达式规则检测
        # -------------------------------------------------------------------------
        for i, rule in enumerate(self.rules):
            # 使用预编译的正则表达式进行匹配
            if i < len(self._compiled_patterns):
                compiled_pattern = self._compiled_patterns[i]
                matches = compiled_pattern.findall(content)
            else:
                # 如果预编译失败，直接使用正则匹配
                matches = re.findall(rule.pattern, content)

            # 如果找到匹配，记录错误或警告
            if matches:
                # 构建错误消息，包含匹配数量和模式摘要
                pattern_summary = rule.pattern[:30] if len(rule.pattern) > 30 else rule.pattern
                msg = f"{rule.description}: 发现 {len(matches)} 处匹配 (模式: {pattern_summary}...)"

                if rule.severity == "error":
                    errors.append(msg)
                else:
                    warnings.append(msg)

        # -------------------------------------------------------------------------
        # 2. 禁止关键词检测
        # -------------------------------------------------------------------------
        # 转换为小写进行不区分大小写的匹配
        content_lower = content.lower()
        for keyword in FORBIDDEN_KEYWORDS:
            if keyword.lower() in content_lower:
                errors.append(f"包含禁止关键词: {keyword}")

        # -------------------------------------------------------------------------
        # 3. 返回结果
        # -------------------------------------------------------------------------
        # 只有存在 error 级别错误时才返回 False
        # warnings 级别的错误不会阻止内容通过，但会被记录
        all_messages = errors + warnings
        is_valid = len(errors) == 0

        return is_valid, all_messages

    def redact(self, content: str) -> str:
        """
        自动脱敏内容

        将所有匹配的敏感信息替换为对应的占位符
        占位符使用语义清晰的命名，便于后续处理

        脱敏流程:
        1. 遍历所有隐私规则
        2. 使用正则表达式替换匹配内容
        3. 返回脱敏后的内容

        Args:
            content: 待脱敏的内容字符串

        Returns:
            str: 脱敏后的内容字符串，敏感信息已替换为占位符

        示例:
            >>> validator = PrivacyValidator()
            >>> content = "处理 /data/sample_001.csv 文件，基因 ENSG00000123456"
            >>> redacted = validator.redact(content)
            >>> print(redacted)
            # "处理 <FILE_PATH> 文件，基因 <GENE_ID>"
        """
        # 初始化脱敏内容
        redacted = content

        # 遍历所有规则进行替换
        for i, rule in enumerate(self.rules):
            # 使用预编译的正则表达式进行替换
            if i < len(self._compiled_patterns):
                compiled_pattern = self._compiled_patterns[i]
                redacted = compiled_pattern.sub(rule.replacement, redacted)
            else:
                # 如果预编译失败，直接使用正则替换
                redacted = re.sub(rule.pattern, rule.replacement, redacted)

        return redacted

    def validate_candidate(self, candidate: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        验证技能候选是否符合隐私规则

        技能候选是从用户对话中提取的方法论，包含多个字段
        此方法验证所有字段是否符合隐私规则

        验证流程:
        1. 验证字符串字段（name, description, instructions）
        2. 验证列表字段（triggers, tags, examples）
        3. 返回综合验证结果

        Args:
            candidate: 技能候选字典，包含以下字段:
                - name: 方法名称
                - description: 方法描述
                - instructions: 可执行指令
                - triggers: 触发关键词列表
                - tags: 标签列表
                - examples: 示例列表

        Returns:
            Tuple[bool, List[str]]:
                - bool: 是否通过验证（所有字段均无 error 级别错误）
                - List[str]: 所有字段的错误消息列表，带字段标识

        示例:
            >>> validator = PrivacyValidator()
            >>> candidate = {
            ...     "name": "差异表达分析策略",
            ...     "description": "分析 /data/project/ 数据",
            ...     "instructions": "处理样本 sample_001"
            ... }
            >>> is_valid, errors = validator.validate_candidate(candidate)
            >>> print(is_valid)  # False
            >>> print(errors)    # ["[description] 文件路径必须脱敏...", "[instructions] 样本名必须脱敏..."]
        """
        # 存储所有错误消息
        all_errors: List[str] = []

        # -------------------------------------------------------------------------
        # 1. 验证字符串字段
        # -------------------------------------------------------------------------
        # 这些字段包含核心方法论内容，必须严格验证
        string_fields = ['name', 'description', 'instructions']
        for field_name in string_fields:
            if field_name in candidate and candidate[field_name]:
                # 转换为字符串进行验证
                field_value = str(candidate[field_name])
                is_valid, field_errors = self.validate(field_value)

                # 如果验证失败，添加带字段标识的错误消息
                if not is_valid:
                    all_errors.extend([f"[{field_name}] {error}" for error in field_errors])

        # -------------------------------------------------------------------------
        # 2. 验证列表字段
        # -------------------------------------------------------------------------
        # 这些字段包含关键词和标签，可能包含敏感信息
        list_fields = ['triggers', 'tags', 'examples']
        for field_name in list_fields:
            if field_name in candidate and isinstance(candidate[field_name], list):
                field_values = candidate[field_name]

                # 验证列表中的每个元素
                for item in field_values:
                    if item:  # 跳过空元素
                        item_str = str(item)
                        is_valid, item_errors = self.validate(item_str)

                        if not is_valid:
                            all_errors.extend([f"[{field_name}] {error}" for error in item_errors])

        # -------------------------------------------------------------------------
        # 3. 返回结果
        # -------------------------------------------------------------------------
        return len(all_errors) == 0, all_errors

    def get_rule_summary(self) -> Dict[str, Any]:
        """
        获取隐私规则摘要

        返回所有规则的摘要信息，用于调试和文档

        Returns:
            Dict[str, Any]: 规则摘要字典，包含:
                - total_rules: 规则总数
                - error_rules: error 级别规则数量
                - warning_rules: warning 级别规则数量
                - forbidden_keywords: 禁止关键词数量
                - rules: 各规则详情列表

        示例:
            >>> validator = PrivacyValidator()
            >>> summary = validator.get_rule_summary()
            >>> print(summary)
            # {
            #     "total_rules": 12,
            #     "error_rules": 10,
            #     "warning_rules": 2,
            #     ...
            # }
        """
        # 统计规则数量
        error_count = sum(1 for rule in self.rules if rule.severity == "error")
        warning_count = sum(1 for rule in self.rules if rule.severity == "warning")

        # 构建规则详情列表
        rules_detail = []
        for rule in self.rules:
            rule_info = {
                "pattern": rule.pattern,
                "replacement": rule.replacement,
                "description": rule.description,
                "severity": rule.severity,
                "example": rule.example
            }
            rules_detail.append(rule_info)

        return {
            "total_rules": len(self.rules),
            "error_rules": error_count,
            "warning_rules": warning_count,
            "forbidden_keywords": len(FORBIDDEN_KEYWORDS),
            "rules": rules_detail
        }

    def add_custom_rule(self, rule: PrivacyRule) -> None:
        """
        添加自定义隐私规则

        用于扩展默认规则集，处理特定场景的隐私检测

        Args:
            rule: PrivacyRule 实例，包含 pattern、replacement、description、severity

        示例:
            >>> validator = PrivacyValidator()
            >>> custom_rule = PrivacyRule(
            ...     pattern=r'custom_pattern_\d+',
            ...     replacement='<CUSTOM>',
            ...     description="自定义规则",
            ...     severity="error"
            ... )
            >>> validator.add_custom_rule(custom_rule)
        """
        self.rules.append(rule)
        # 编译新规则的正则表达式
        try:
            compiled = re.compile(rule.pattern)
            self._compiled_patterns.append(compiled)
            log.info(f"添加自定义隐私规则: {rule.description}")
        except re.error as e:
            log.warning(f"自定义规则正则编译失败: {rule.pattern}, 错误: {e}")


# ============================================================================
# 全局单例管理
# ============================================================================
# 使用全局单例模式，避免重复创建验证器实例
# 符合项目的设计模式，提高性能和一致性

_validator: Optional[PrivacyValidator] = None


def get_privacy_validator() -> PrivacyValidator:
    """
    获取隐私验证器单例

    如果单例不存在，创建并初始化默认规则
    如果已存在，直接返回现有实例

    Returns:
        PrivacyValidator: 隐私验证器实例

    使用示例:
        >>> from app.services.system_learning.privacy_validator import get_privacy_validator
        >>> validator = get_privacy_validator()
        >>> is_valid, errors = validator.validate("内容")

    注意:
        - 此函数返回全局单例，避免重复创建
        - 如需使用自定义规则，请直接创建 PrivacyValidator 实例
    """
    global _validator
    if _validator is None:
        _validator = PrivacyValidator()
        log.info("隐私验证器单例已初始化")
    return _validator


def reset_privacy_validator() -> None:
    """
    重置隐私验证器单例

    用于测试或需要重新初始化的场景
    清除全局单例，下次调用 get_privacy_validator() 时会重新创建

    使用示例:
        >>> from app.services.system_learning.privacy_validator import reset_privacy_validator
        >>> reset_privacy_validator()
        >>> validator = get_privacy_validator()  # 创建新实例
    """
    global _validator
    _validator = None
    log.debug("隐私验证器单例已重置")