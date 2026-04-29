"""
技能收割机 (Skill Harvester) — 从成功的即席分析中自动生成技能草稿。

程序说明：
当即席分析在 Docker 沙箱中成功执行后，评估执行结果的质量和复杂度，
满足条件时自动将代码转化为参数化的技能草稿（PendingSkillDraft），
用户可在前端 SkillCenter 的"收割"Tab 中审核并一键发布为 SkillAsset。

收割流程：
1. 执行成功 → SuccessEvaluator.should_trigger_skill_draft() 评估触发条件
2. 满足条件 → 剥离硬编码路径，生成参数化代码模板
3. LLM 生成技能元数据（名称、描述、专家知识、标签）
4. 写入 PendingSkillDraft 表（status=PENDING）
5. 前端通知用户"有新的技能草稿待审核"

设计原则：
- 非阻塞异步（fire-and-forget），失败不影响主流程
- 复用 SuccessEvaluator 的触发判断逻辑
- 复用 _summarize_experience() 的 LLM 调用模式
- 零外部依赖，纯 LangGraph + PostgreSQL 原生实现
"""
import json
import os
import re
from typing import Optional, List, Dict, Any

from sqlmodel import Session, select

from app.core.database import engine
from app.core.logger import log
from app.models.skill.draft import (
    PendingSkillDraft,
    DraftStatus,
    TriggerSource,
)


# 收割触发阈值
HARVEST_MIN_CODE_LENGTH = 50       # 最小代码行数
HARVEST_MIN_COMPLEXITY = 0.4       # 最小代码复杂度
HARVEST_MIN_EXECUTION_TIME = 20    # 最小执行时间（秒）
HARVEST_MIN_CONFIDENCE = 0.7       # 最小成功置信度


async def harvest_skill_from_execution(
    code: str,
    strategy_pack: Dict[str, Any],
    instruction: str,
    language: str,
    output_files: List[str],
    execution_time: float,
    user_id: int,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    record_id: Optional[int] = None,
    llm_session=None,
) -> Optional[PendingSkillDraft]:
    """
    从成功的即席分析执行中自动收割技能草稿。

    触发条件检查：
    1. 代码长度 >= HARVEST_MIN_CODE_LENGTH
    2. 执行时间 >= HARVEST_MIN_EXECUTION_TIME
    3. 有输出文件
    4. 代码复杂度 >= HARVEST_MIN_COMPLEXITY

    Args:
        code: 最终执行成功的代码
        strategy_pack: LLM 生成的策略包（含策略、参数 schema 等）
        instruction: 用户原始分析需求
        language: 代码语言 (python / r)
        output_files: 输出文件列表
        execution_time: 执行耗时（秒）
        user_id: 用户 ID
        project_id: 项目 ID（可选）
        session_id: 聊天会话 ID（可选）
        record_id: AdhocAnalysisRecord ID（可选，用于追溯）
        llm_session: LLM config 需要的数据库会话

    Returns:
        PendingSkillDraft 或 None（不满足触发条件或收割失败）
    """
    try:
        # 1. 快速预筛选：避免为太简单的分析创建技能
        if len(code) < HARVEST_MIN_CODE_LENGTH:
            log.debug(f"[SkillHarvester] 代码太短 ({len(code)} 字符)，跳过收割")
            return None

        # 2. 评估触发条件
        trigger_source, trigger_score, trigger_reason = _evaluate_trigger(
            code=code,
            execution_time=execution_time,
            has_output_files=len(output_files) > 0,
            confidence=_estimate_confidence(strategy_pack, output_files),
        )

        if not trigger_source:
            log.info(
                f"[SkillHarvester] 未满足收割触发条件: {trigger_reason}"
            )
            return None

        log.info(
            f"[SkillHarvester] 触发技能收割: source={trigger_source}, "
            f"score={trigger_score:.2f}, reason={trigger_reason}"
        )

        # 3. 剥离硬编码路径，生成参数化代码模板
        parameterized_code = _strip_hardcoded_paths(code)

        # 4. 提取参数 schema
        parameters_schema = _extract_parameter_schema(strategy_pack)

        # 5. LLM 生成技能元数据
        skill_metadata = await _generate_skill_metadata(
            instruction=instruction,
            code=parameterized_code,
            language=language,
            parameter_schema=parameters_schema,
            output_files=output_files,
            session=llm_session,
            user_id=user_id,
        )

        if not skill_metadata:
            log.warning("[SkillHarvester] 技能元数据生成失败，跳过收割")
            return None

        # 6. 推断执行器类型
        executor_type = "R_env" if language in ("r", "R") else "Python_env"

        # 7. 提取依赖包
        dependencies = _extract_dependencies(code, language)

        # 8. 写入 PendingSkillDraft
        with Session(engine) as db_session:
            draft = PendingSkillDraft(
                user_id=user_id,
                session_id=session_id or "",
                project_id=project_id,
                trigger_source=trigger_source,
                trigger_score=trigger_score,
                trigger_reason=trigger_reason,
                raw_material=f"分析需求: {instruction}\n\n代码:\n{code[:5000]}",
                code_blocks=[{"language": language, "code": parameterized_code}],
                strategies=[strategy_pack.get("strategy", "")] if strategy_pack.get("strategy") else [],
                draft_name=skill_metadata.get("name", f"即席分析: {instruction[:50]}"),
                draft_description=skill_metadata.get("description", ""),
                executor_type=executor_type,
                parameters_schema=parameters_schema,
                expert_knowledge=skill_metadata.get("expert_knowledge", ""),
                script_code=parameterized_code,
                dependencies=dependencies,
                status=DraftStatus.PENDING,
            )
            db_session.add(draft)
            db_session.commit()
            db_session.refresh(draft)

            log.info(
                f"[SkillHarvester] 技能草稿已创建: id={draft.id}, "
                f"name={draft.draft_name}, executor={executor_type}, "
                f"params={len(parameters_schema.get('properties', {}))}"
            )
            return draft

    except Exception as e:
        log.error(f"[SkillHarvester] 技能收割失败（非致命）: {e}")
        return None


def _evaluate_trigger(
    code: str,
    execution_time: float,
    has_output_files: bool,
    confidence: float,
) -> tuple:
    """
    评估是否触发技能收割。

    Returns:
        (trigger_source, trigger_score, trigger_reason)
        trigger_source 为空字符串表示不触发
    """
    trigger_reasons = []
    trigger_score = 0.0
    trigger_source = ""

    # 代码复杂度评估（简化版，基于代码特征）
    code_complexity = _calculate_code_complexity(code)

    if code_complexity >= HARVEST_MIN_COMPLEXITY:
        trigger_reasons.append(f"代码复杂度 {code_complexity:.1%}")
        trigger_score = max(trigger_score, code_complexity)
        trigger_source = TriggerSource.CODE_COMPLEXITY

    if execution_time >= HARVEST_MIN_EXECUTION_TIME:
        trigger_reasons.append(f"执行时长 {execution_time:.0f}s")
        trigger_score = max(trigger_score, 0.6)
        if not trigger_source:
            trigger_source = TriggerSource.EXECUTION_TIME

    if has_output_files:
        trigger_reasons.append("有输出文件")
        trigger_score = max(trigger_score, 0.5)
        if not trigger_source:
            trigger_source = TriggerSource.OUTPUT_FILE

    if confidence >= HARVEST_MIN_CONFIDENCE:
        trigger_reasons.append(f"成功置信度 {confidence:.0%}")
        trigger_score = max(trigger_score, confidence)
        if not trigger_source:
            trigger_source = TriggerSource.SUCCESS_SIGNAL

    if not trigger_reasons:
        return "", 0.0, "未满足触发条件"

    return trigger_source, trigger_score, " | ".join(trigger_reasons)


def _calculate_code_complexity(code: str) -> float:
    """
    简化版代码复杂度计算。

    评分维度：
    - 代码行数 (0.3)
    - 参数系统检测 (0.3)
    - 输出操作 (0.2)
    - 函数/类定义 (0.1)
    - 注释密度 (0.1)
    """
    if not code:
        return 0.0

    lines = code.split("\n")
    total_lines = len(lines)
    if total_lines < 20:
        return 0.0

    # 行数评分（20-200 行之间线性增长）
    line_score = min(1.0, total_lines / 200) * 0.3

    # 参数系统评分
    has_argparse = bool(re.search(r'argparse|optparse|commandArgs', code))
    param_score = (1.0 if has_argparse else 0.0) * 0.3

    # 输出操作评分
    has_output = bool(re.search(
        r'(plt\.savefig|ggsave|write\.csv|write\.table|to_csv|to_csv|fwrite|saveRDS|pdf\(|png\()',
        code
    ))
    output_score = (1.0 if has_output else 0.0) * 0.2

    # 函数/类定义评分
    has_functions = bool(re.search(r'\bdef\s+\w+|function\s*\(|<- function', code))
    func_score = (1.0 if has_functions else 0.0) * 0.1

    # 注释密度评分
    comment_lines = sum(1 for l in lines if l.strip().startswith('#'))
    comment_density = comment_lines / total_lines if total_lines > 0 else 0
    comment_score = min(1.0, comment_density / 0.1) * 0.1  # 期望 10% 注释率

    return line_score + param_score + output_score + func_score + comment_score


def _estimate_confidence(strategy_pack: Dict[str, Any], output_files: List[str]) -> float:
    """
    基于策略包完整度和输出文件估计成功置信度。
    """
    confidence = 0.5  # 基线

    # 策略包完整性
    if strategy_pack.get("strategy"):
        confidence += 0.1
    if strategy_pack.get("code"):
        confidence += 0.1
    if strategy_pack.get("parameter_schema", {}).get("properties"):
        confidence += 0.1

    # 有输出文件
    if output_files:
        confidence += 0.1
        # 有多种类型的输出文件更好
        extensions = set(os.path.splitext(f)[1].lower() for f in output_files)
        if len(extensions) >= 2:
            confidence += 0.1

    return min(1.0, confidence)


def _strip_hardcoded_paths(code: str) -> str:
    """
    将硬编码的 /workspace/ 路径替换为参数占位符注释。

    注意：不做直接替换（会影响代码逻辑），而是添加注释标记，
    供用户在审核时手动调整。自动替换风险太高（可能错误替换）。
    实际参数化由用户在前端草稿编辑器中完成。

    策略：在代码顶部添加注释，标注需要参数化的路径。
    """
    hardcoded_paths = re.findall(r'["\'](/workspace/[^"\']{10,})["\']', code)
    if not hardcoded_paths:
        return code

    # 去重
    unique_paths = list(set(hardcoded_paths))[:10]

    # 在代码顶部添加参数化提示注释
    if language := _detect_language(code):
        if language in ("python",):
            param_note_lines = [
                "# === 自动收割提示：以下路径建议参数化 ===",
            ]
            for i, path in enumerate(unique_paths):
                param_name = f"input_file_{i+1}" if i > 0 else "input_file"
                param_note_lines.append(
                    f"# TODO: 将 '{path}' 替换为 argparse 参数 (如 --{param_name})"
                )
            param_note_lines.append("# === 参数化提示结束 ===\n")
        else:
            param_note_lines = [
                "# === 自动收割提示：以下路径建议参数化 ===",
            ]
            for i, path in enumerate(unique_paths):
                param_name = f"input_file_{i+1}" if i > 0 else "input_file"
                param_note_lines.append(
                    f"# TODO: 将 '{path}' 替换为 optparse/commandArgs 参数 (如 --{param_name})"
                )
            param_note_lines.append("# === 参数化提示结束 ===\n")
    else:
        return code

    return "\n".join(param_note_lines) + "\n" + code


def _detect_language(code: str) -> str:
    """检测代码语言"""
    if re.search(r'library\s*\(|ggplot|ggsave|<\-\s*', code):
        return "r"
    return "python"


def _extract_parameter_schema(strategy_pack: Dict[str, Any]) -> Dict[str, Any]:
    """
    从策略包中提取参数 schema。
    """
    schema = strategy_pack.get("parameter_schema", {})
    if schema and isinstance(schema, dict):
        return schema

    # 尝试从代码中推断参数
    return {
        "type": "object",
        "properties": {},
        "required": [],
    }


def _extract_dependencies(code: str, language: str) -> List[str]:
    """
    从代码中提取依赖包列表。
    """
    dependencies = []

    if language in ("python",):
        # Python: import xxx 和 from xxx import
        import_matches = re.findall(r'(?:^import\s+(\w+)|^from\s+(\w+)\s+import)', code, re.MULTILINE)
        for match in import_matches:
            pkg = match[0] or match[1]
            if pkg and pkg not in dependencies:
                dependencies.append(pkg)
    elif language in ("r", "R"):
        # R: library(xxx) 和 xxx::
        lib_matches = re.findall(r'library\s*\(\s*["\']?(\w+)["\']?\s*\)', code)
        for pkg in lib_matches:
            if pkg and pkg not in dependencies:
                dependencies.append(pkg)

    return dependencies


async def _generate_skill_metadata(
    instruction: str,
    code: str,
    language: str,
    parameter_schema: Dict[str, Any],
    output_files: List[str],
    session=None,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, str]]:
    """
    使用 LLM 生成技能元数据（名称、描述、专家知识、标签）。

    复用与 experience_extractor._summarize_experience() 相同的 LLM 调用模式。
    """
    try:
        from app.utils.llm_config import get_fast_llm_config_standalone
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm_config = get_fast_llm_config_standalone(user_id=user_id)
        llm = ChatOpenAI(
            api_key=llm_config.api_key or "not-needed",
            base_url=llm_config.base_url,
            model=llm_config.model_name,
            temperature=0.0,
        )

        params_list = list(parameter_schema.get("properties", {}).keys())
        params_desc = ", ".join(params_list) if params_list else "无参数"

        lang_display = "Python" if language in ("python",) else "R"
        output_preview = ", ".join(output_files[:5]) if output_files else "无"

        prompt = f"""你是一个生物信息学技能管理专家。请为以下成功执行的即席分析代码生成技能元数据。

用户需求：{instruction}
代码语言：{lang_display}
参数列表：{params_desc}
输出文件：{output_preview}

代码摘要（前 1000 字符）：
```{language}
{code[:1000]}
```

请生成以下技能元数据，输出严格 JSON 格式：
```json
{{
  "name": "技能名称（中文，20字以内，如：基因表达差异分析热图）",
  "description": "技能描述（中文，2-3句话，说明功能、输入输出、适用场景）",
  "expert_knowledge": "专家知识（中文，3-5条操作指南和注意事项，基于代码中使用的生物信息学最佳实践）",
  "tags": ["标签1", "标签2", "标签3"]
}}
```

要求：
- name 要具体、有辨识度，不要泛泛（避免使用"数据分析"这类大词）
- description 要说明这个技能解决了什么问题、输入什么、输出什么
- expert_knowledge 要包含实用的操作建议（如配色方案选择、参数推荐值、常见陷阱）
- tags 全部使用小写英文，覆盖分析类型和技术栈"""

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="请输出严格 JSON 格式的技能元数据。"),
        ]

        response = await llm.ainvoke(messages)
        raw = response.content.strip()

        # 清理 markdown 标记
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        import json as json_mod
        from json_repair import repair_json
        repaired = repair_json(raw)
        result = json_mod.loads(repaired)

        return {
            "name": result.get("name", instruction[:50]),
            "description": result.get("description", ""),
            "expert_knowledge": result.get("expert_knowledge", ""),
            "tags": result.get("tags", []),
        }

    except Exception as e:
        log.error(f"[SkillHarvester] 技能元数据 LLM 生成失败: {e}")
        # 降级：返回基于规则的基本元数据
        return {
            "name": instruction[:50],
            "description": f"从即席分析自动收割的{lang_display}技能。参数: {params_desc}",
            "expert_knowledge": "",
            "tags": [],
        }
