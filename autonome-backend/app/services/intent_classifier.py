"""
轻量级意图分类器 - 快速判断消息意图类型

功能:
1. 使用快速规则预筛选 (< 5ms)
2. 返回三元分类: casual | theory | analytical

分类结果:
- casual: 闲聊/问候，不需要任何处理
- theory: 理论知识问答，可以用主 LLM 直接回答
- analytical: 分析任务，需要技能推荐或 Agent 执行

使用场景:
- 在聊天流入口快速判断消息类型
- 决定是否需要扫描项目目录、构建 Agent
"""

import re
from typing import Tuple


class IntentClassifier:
    """
    轻量级意图分类器

    采用纯规则判断，响应时间 < 5ms:
    - casual: 闲聊/问候 (greeting, thanks, bye)
    - theory: 理论知识问答 (what is, how to understand, explain)
    - analytical: 分析任务 (分析, 处理, 执行, 特定数据格式)
    """

    # 闲聊模式：直接回复即可，不需要技能
    CASUAL_PATTERNS = [
        # 简单问候
        r'^(你好|hi|hello|嗨|您好|hey|hi there|greetings)$',
        r'^(谢谢|thanks|thx|thank you|感谢)$',
        r'^(再见|bye|拜拜|goodbye|see you)$',
        # 确认/反馈
        r'^(好|好的|ok|okay|OK|Can|yep|yes)$',
        r'^(明白了|了解|知道了|got it|understood)$',
        # 询问能做什么
        r'^(你能做什么|你会什么|有什么功能|help me|你能帮我什么)',
        # 空消息或无意义输入
        r'^[\s,!?。]*$',
    ]

    # 理论问答模式：知识型问题，不需要技能执行
    THEORY_PATTERNS = [
        # 中文理论问题
        r'^(什么是|怎么理解|如何理解|解释一下|告诉我|帮我理解)',
        r'(是什么意思|是指|定义|原理|概念)',
        r'(有什么区别|有什么不同|为什么|怎样理解|如何选择)',
        # 英文理论问题
        r'^(what is|how to understand|explain|tell me about|what do you mean)',
        r'(what is the difference|what are the differences|how does it work|why is)',
        # 不包含执行意图的理论问题
        r'^(介绍一下|简单介绍|简述|概述|说明)',
    ]

    # 分析任务触发词：需要技能推荐或 Agent 执行
    ANALYTICAL_TRIGGERS = [
        # 执行类动词
        r'(分析|处理|运行|执行|计算|生成|转换)',
        r'(帮我|请帮我|想要|需要|麻烦|能不能)',
        r'(帮我分析|帮我处理|帮我运行|帮我计算|帮我生成)',
        # 生物信息数据格式
        r'(fastq|bam|vcf|h5ad|csv|tsv|fasta|gtf|bed)',
        # 生信分析领域
        r'(单细胞|转录组|基因组|质控|差异|比对|定量)',
        r'(pipeline|流程|工作流|流水线|step)',
        # 明确技能名称
        r'(fastqc|multiqc|seurat|scanpy|cellranger|star|hisat2)',
        # 文件操作
        r'(读取|写入|导入|导出|解析|处理)',
        # 数据操作
        r'(处理我的|分析我的|查看我的|检查|质控)',
        # ✨ 工作区/文件查询（短消息拦截前的关键词检测）
        r'(文件|目录|文件夹|工作区|路径|路径|项目|列出|查看|有哪些)',
    ]

    # ✨ 工作区/文件查询关键词（用于短消息时提升为 analytical）
    WORKSPACE_QUERY_KEYWORDS = [
        '文件', '目录', '文件夹', '工作区', '项目文件',
        '有哪些', '列出', '查看', '当前路径', '所有文件'
    ]

    def classify(self, message: str) -> Tuple[str, float, str]:
        """
        快速分类消息意图

        Args:
            message: 用户消息

        Returns:
            Tuple[str, float, str]: (意图类型, 置信度, 原因)
            - intent_type: "casual" | "theory" | "analytical"
            - confidence: 0.0 - 1.0
            - reason: 分类原因描述
        """
        msg = message.strip().lower()

        # 空消息默认为 casual
        if len(msg) < 2:
            return "casual", 0.95, "空消息或过短消息"

        # 1. 检查闲聊模式
        for pattern in self.CASUAL_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return "casual", 0.95, "检测到闲聊/问候"

        # 2. 检查理论问答模式（排除带有分析意图的理论问题）
        has_analytical_intent = any(
            re.search(t, msg, re.IGNORECASE) for t in self.ANALYTICAL_TRIGGERS
        )

        for pattern in self.THEORY_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                if has_analytical_intent:
                    # 既有理论问题又有分析意图，按分析任务处理
                    return "analytical", 0.85, "检测到分析任务需求"
                else:
                    # 纯理论问题
                    return "theory", 0.85, "检测到理论知识问答需求"

        # 3. 检查分析任务触发词
        for trigger in self.ANALYTICAL_TRIGGERS:
            if re.search(trigger, msg, re.IGNORECASE):
                return "analytical", 0.90, "检测到分析任务需求"

        # 4. 默认作为分析任务处理（保守策略）
        # 如果消息长度较长，很可能是用户有实际需求
        if len(msg) > 10:
            return "analytical", 0.50, "默认判定为分析任务"

        # 5. ✨ 短消息但包含工作区/文件查询关键词 -> 提升为 analytical
        #    解决"项目文件有哪些"等短消息被误判为闲聊的问题
        if any(kw in msg for kw in self.WORKSPACE_QUERY_KEYWORDS):
            return "analytical", 0.85, "检测到工作区查询需求"

        # 6. 短消息默认为 casual
        return "casual", 0.60, "短消息默认为闲聊"


# ==========================================
# 便捷函数
# ==========================================

_classifier = IntentClassifier()


def classify_intent(message: str) -> Tuple[str, float, str]:
    """
    快速分类消息意图（便捷函数）

    Args:
        message: 用户消息

    Returns:
        Tuple[str, float, str]: (意图类型, 置信度, 原因)
    """
    return _classifier.classify(message)


log = None  # 延迟导入避免循环依赖


def _init_log():
    global log
    if log is None:
        from app.core.logger import log as _log
        log = _log


def classify_intent_with_log(message: str) -> Tuple[str, float, str]:
    """
    快速分类消息意图（带日志）

    Args:
        message: 用户消息

    Returns:
        Tuple[str, float, str]: (意图类型, 置信度, 原因)
    """
    _init_log()
    result = _classifier.classify(message)
    log.info(f"[IntentClassifier] 意图分类: type={result[0]}, confidence={result[1]}, reason={result[2]}")
    return result
