"""
任务复杂度分析服务

判断任务复杂度，决定是否使用专家委员会模式
"""

from typing import Optional

from app.agent.planning_coordinator import COMPLEX_TASK_KEYWORDS, MEDIUM_TASK_KEYWORDS
from app.core.logger import log


def should_use_expert_committee(user_request: str, task_mode: Optional[str] = None) -> bool:
    """
    判断是否应该使用专家委员会模式

    Args:
        user_request: 用户请求文本
        task_mode: 用户指定的任务模式 ('complex' 强制使用, 'interactive' 不使用)

    Returns:
        True 表示应该使用专家委员会模式
    """
    # 用户明确指定复杂任务模式
    if task_mode == 'complex':
        log.info(f"🎯 [Chat] 用户指定复杂任务模式，启用专家委员会")
        return True

    # 用户明确指定交互式可视化模式 - 不使用专家委员会
    if task_mode == 'interactive':
        log.info(f"🎨 [Chat] 用户指定交互式可视化模式，不使用专家委员会")
        return False

    # 基于关键词自动判断
    request_lower = user_request.lower()

    # 统计复杂关键词命中（去重处理）
    matched_complex = set()
    for kw in COMPLEX_TASK_KEYWORDS:
        if kw.lower() in request_lower:
            normalized = kw.lower()
            if normalized in ['rna-seq', 'rnaseq']:
                normalized = 'rna-seq'
            elif normalized in ['single-cell', 'scrna', '单细胞rna']:
                normalized = 'single-cell'
            elif normalized in ['chip-seq', 'chipseq']:
                normalized = 'chip-seq'
            elif normalized in ['atac-seq', 'atacseq']:
                normalized = 'atac-seq'
            matched_complex.add(normalized)

    # 检查流程描述
    flow_indicators = ["第一步", "第二步", "第三步", "1.", "2.", "3.", "首先", "然后", "最后", "全流程", "完整分析", "端到端"]
    has_flow_description = any(ind in user_request for ind in flow_indicators)

    # 统计中等关键词命中
    matched_medium = set()
    for kw in MEDIUM_TASK_KEYWORDS:
        if kw.lower() in request_lower:
            matched_medium.add(kw.lower())

    complex_count = len(matched_complex)
    medium_count = len(matched_medium)

    # 判断是否需要专家委员会
    # 条件：>=3 个复杂关键词 或 明确流程描述
    should_use = complex_count >= 3 or has_flow_description

    if should_use:
        log.info(f"🎯 [Chat] 检测到复杂任务 (复杂关键词:{complex_count}, 流程描述:{has_flow_description})，启用专家委员会")

    return should_use