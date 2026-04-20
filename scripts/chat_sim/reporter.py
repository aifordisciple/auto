"""模拟对话测试 - 报告生成器

生成控制台摘要 + JSON 详细报告。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from chat_sim.models import JudgeResult, TestItem, TestReport, Verdict


def generate_report(items: list[TestItem], save_path: Optional[str] = None) -> TestReport:
    """生成测试报告

    Args:
        items: 测试项列表
        save_path: 报告保存路径

    Returns:
        测试报告
    """
    report = TestReport(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total=len(items),
    )

    # 统计
    category_data = {}
    for item in items:
        cat = item.question.category
        if cat not in category_data:
            category_data[cat] = {"total": 0, "pass": 0, "warn": 0, "fail": 0}

        category_data[cat]["total"] += 1

        if item.judge_result:
            v = item.judge_result.verdict
            if v == Verdict.PASS:
                report.passed += 1
                category_data[cat]["pass"] += 1
            elif v == Verdict.WARN:
                report.warned += 1
                category_data[cat]["warn"] += 1
            else:
                report.failed += 1
                category_data[cat]["fail"] += 1
        else:
            report.failed += 1
            category_data[cat]["fail"] += 1

    report.pass_rate = (report.passed / report.total * 100) if report.total > 0 else 0
    report.category_stats = category_data
    report.items = items

    # 控制台输出
    _print_console_report(report)

    # 保存 JSON 报告
    if save_path:
        _save_json_report(report, save_path)

    return report


def _print_console_report(report: TestReport):
    """控制台输出测试报告"""
    print("\n")
    print("=" * 55)
    print("  模拟对话测试报告")
    print(f"  时间: {report.timestamp}")
    print(f"  总计: {report.total} | 通过: {report.passed} | 警告: {report.warned} | 失败: {report.failed}")
    print(f"  通过率: {report.pass_rate:.1f}%")
    print("=" * 55)

    # 分类统计
    print("\n分类统计:")
    for cat, stats in sorted(report.category_stats.items()):
        pass_count = stats["pass"]
        total = stats["total"]
        warn_count = stats["warn"]
        fail_count = stats["fail"]
        print(f"  {cat:20s}: {pass_count}/{total} 通过", end="")
        if warn_count:
            print(f" | {warn_count} 警告", end="")
        if fail_count:
            print(f" | {fail_count} 失败", end="")
        print()

    # 失败和警告详情
    fail_items = [i for i in report.items if i.judge_result and i.judge_result.verdict in (Verdict.FAIL, Verdict.WARN)]
    if fail_items:
        print(f"\n{'失败/警告详情:'}")
        for item in fail_items:
            jr = item.judge_result
            q = item.question
            tag = jr.verdict
            location = jr.issue_location or "unknown"
            print(f"  #{q.id} [{tag}] {location} - {jr.reason}")
            print(f"    问题: {q.message[:80]}{'...' if len(q.message) > 80 else ''}")
            if q.expected_intent != "blocked" and item.api_result:
                print(f"    期望意图: {q.expected_intent} | 实际意图: {item.api_result.actual_intent or 'unknown'}")
            print()

    print("=" * 55)

    # 修复建议
    if report.failed > 0:
        _print_fix_suggestions(fail_items)


def _print_fix_suggestions(fail_items: list[TestItem]):
    """输出修复建议"""
    # 按问题定位分组
    location_groups = {}
    for item in fail_items:
        if not item.judge_result:
            continue
        loc = item.judge_result.issue_location or "unknown"
        if loc not in location_groups:
            location_groups[loc] = []
        location_groups[loc].append(item)

    print("\n修复建议（按问题模块分组）:")
    for location, items in sorted(location_groups.items()):
        print(f"\n  [{location}] ({len(items)} 个问题)")
        for item in items:
            q = item.question
            jr = item.judge_result
            print(f"    - #{q.id} {q.message[:60]}{'...' if len(q.message) > 60 else ''}")
            print(f"      原因: {jr.reason}")

    # 定位提示
    location_hints = {
        "intent_router": "检查 app/agent/router/ 下的意图分类逻辑和 prompt",
        "knowledge_base_node": "检查知识库检索和 RAG 生成逻辑",
        "general_qa_node": "检查通用 QA 节点的 LLM 调用和 prompt",
        "small_talk_node": "检查闲聊节点的回复生成逻辑",
        "task_node": "检查任务节点的执行和回复逻辑",
        "content_filter": "检查 app/core/content_filter.py 的过滤规则",
        "llm_service": "检查 LLM 服务可用性和配置",
        "performance": "检查服务性能和超时配置",
    }
    print("\n定位提示:")
    for location in location_groups:
        hint = location_hints.get(location, "请检查相关模块")
        print(f"  {location}: {hint}")


def _save_json_report(report: TestReport, save_path: str):
    """保存 JSON 格式报告"""
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    data = {
        "timestamp": report.timestamp,
        "total": report.total,
        "passed": report.passed,
        "warned": report.warned,
        "failed": report.failed,
        "pass_rate": round(report.pass_rate, 1),
        "category_stats": report.category_stats,
        "items": [_item_to_dict(item) for item in report.items],
    }

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"报告已保存到 {save_path}")


def _item_to_dict(item: TestItem) -> dict:
    """将 TestItem 转为可序列化的 dict"""
    result = {
        "question": {
            "id": item.question.id,
            "message": item.question.message,
            "category": item.question.category,
            "difficulty": item.question.difficulty,
            "expected_intent": item.question.expected_intent,
            "description": item.question.description,
        },
    }

    if item.api_result:
        result["api_result"] = {
            "status_code": item.api_result.status_code,
            "elapsed_ms": round(item.api_result.elapsed_ms, 1),
            "response_text": item.api_result.response_text[:500],
            "actual_intent": item.api_result.actual_intent,
            "session_id": item.api_result.session_id,
            "error": item.api_result.error,
        }

    if item.judge_result:
        result["judge_result"] = {
            "verdict": item.judge_result.verdict,
            "relevance": item.judge_result.relevance,
            "accuracy": item.judge_result.accuracy,
            "completeness": item.judge_result.completeness,
            "intent_match": item.judge_result.intent_match,
            "reason": item.judge_result.reason,
            "issue_location": item.judge_result.issue_location,
        }

    return result
