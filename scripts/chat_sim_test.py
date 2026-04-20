#!/usr/bin/env python3
"""模拟对话测试 - 主入口

用法:
  python scripts/chat_sim_test.py                    # 默认50条全分类测试
  python scripts/chat_sim_test.py --count 20         # 只测20条
  python scripts/chat_sim_test.py --category task    # 只测任务类
  python scripts/chat_sim_test.py --verbose          # 详细日志
  python scripts/chat_sim_test.py --no-judge         # 跳过LLM评判
  python scripts/chat_sim_test.py --config PATH      # 指定配置文件
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger

# 将 scripts 目录加入 path，使 chat_sim 包可导入
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from chat_sim.caller import call_chat, get_project_id, login
from chat_sim.generator import generate_questions, load_questions
from chat_sim.judge import judge_response
from chat_sim.models import TestItem, TestReport
from chat_sim.reporter import generate_report


def load_config(config_path: str) -> dict:
    """加载配置文件"""
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
        return _default_config()

    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def _default_config() -> dict:
    """默认配置"""
    return {
        "api": {"base_url": "http://localhost:8000", "auth_token": ""},
        "test_account": {"email": "test@autonome.ai", "password": "test123456"},
        "questions": {
            "total": 50,
            "categories": {
                "knowledge_base": 10,
                "general_qa": 10,
                "small_talk": 8,
                "task": 8,
                "content_filter": 6,
                "edge_case": 8,
            },
        },
        "judge": {
            "model": "qwen3.6-ultra:latest",
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "pass_threshold": 3,
        },
        "timeout": {"easy": 30, "medium": 45, "hard": 60},
        "logging": {"level": "INFO", "save_path": "scripts/test_data/logs/"},
    }


def setup_logging(level: str, save_path: str):
    """配置 Loguru 日志"""
    logger.remove()  # 移除默认 handler

    # 控制台输出
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )

    # 文件输出
    Path(save_path).mkdir(parents=True, exist_ok=True)
    log_file = Path(save_path) / f"sim_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logger.add(
        str(log_file),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
        encoding="utf-8",
    )
    logger.info(f"日志文件: {log_file}")


async def run_test(config: dict, args: argparse.Namespace):
    """执行模拟对话测试"""
    start_time = time.monotonic()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 配置提取
    api_base = config["api"]["base_url"]
    test_email = config["test_account"]["email"]
    test_password = config["test_account"]["password"]
    judge_config = config.get("judge", {})
    questions_config = config.get("questions", {})

    # 问题数量和分类
    total = args.count or questions_config.get("total", 50)
    categories = questions_config.get("categories", None)

    # 如果指定了单个分类
    if args.category:
        categories = {args.category: total}
        logger.info(f"仅测试分类: {args.category}")

    # 数据保存路径
    test_data_dir = SCRIPTS_DIR / "test_data"
    test_data_dir.mkdir(parents=True, exist_ok=True)

    # ===== 第1步: 登录获取 token =====
    logger.info("=" * 40)
    logger.info("第1步: 登录获取认证 token")
    logger.info("=" * 40)

    token = config["api"].get("auth_token", "")
    if not token:
        try:
            token = await login(api_base, test_email, test_password)
        except Exception as e:
            logger.error(f"登录失败: {e}")
            logger.error("请检查配置文件中的 test_account 设置")
            return

    # ===== 第2步: 获取项目 ID =====
    logger.info("=" * 40)
    logger.info("第2步: 获取项目 ID")
    logger.info("=" * 40)

    try:
        project_id = await get_project_id(api_base, token)
    except Exception as e:
        logger.warning(f"获取项目 ID 失败: {e}，使用默认值")
        project_id = "default"

    # ===== 第3步: 生成测试问题 =====
    logger.info("=" * 40)
    logger.info(f"第3步: 生成 {total} 条测试问题")
    logger.info("=" * 40)

    questions_path = str(test_data_dir / f"sim_questions_{timestamp}.json")

    try:
        questions = await generate_questions(
            total=total,
            categories=categories,
            save_path=questions_path,
        )
    except Exception as e:
        logger.error(f"问题生成失败: {e}")
        logger.error("请检查 LLM 配置（OPENAI_API_KEY, OPENAI_BASE_URL, DEFAULT_MODEL）")
        return

    if not questions:
        logger.error("未生成任何问题，测试终止")
        return

    logger.info(f"成功生成 {len(questions)} 条测试问题")

    # ===== 第4步: 逐条调用 API =====
    logger.info("=" * 40)
    logger.info(f"第4步: 逐条调用聊天 API ({len(questions)} 条)")
    logger.info("=" * 40)

    items: list[TestItem] = []
    session_id = None  # 同一会话内测试

    for i, q in enumerate(questions):
        api_result = await call_chat(
            base_url=api_base,
            token=token,
            question=q,
            project_id=project_id,
            session_id=session_id,
            total=len(questions),
        )

        # 记住会话 ID，后续消息在同一会话中
        if api_result.session_id and not session_id:
            session_id = api_result.session_id
            logger.info(f"使用会话: {session_id}")

        item = TestItem(question=q, api_result=api_result)
        items.append(item)

        # 简短间隔，避免过快请求
        await asyncio.sleep(0.5)

    # ===== 第5步: 评判回复 =====
    logger.info("=" * 40)
    logger.info(f"第5步: 评判回复合理性 ({len(items)} 条)")
    logger.info("=" * 40)

    if args.no_judge:
        logger.info("跳过 LLM 评判（--no-judge 模式）")
    else:
        ollama_host = judge_config.get("base_url", "http://localhost:11434")
        judge_model = judge_config.get("model", "qwen3.6-ultra:latest")

        for item in items:
            if item.api_result is None:
                continue

            judge_result = await judge_response(
                question=item.question,
                api_result=item.api_result,
                ollama_host=ollama_host,
                model=judge_model,
                total=len(items),
            )
            item.judge_result = judge_result

            # 简短间隔
            await asyncio.sleep(0.3)

    # ===== 第6步: 生成报告 =====
    logger.info("=" * 40)
    logger.info("第6步: 生成测试报告")
    logger.info("=" * 40)

    report_path = str(test_data_dir / f"sim_report_{timestamp}.json")
    report = generate_report(items, save_path=report_path)

    # 总耗时
    elapsed = time.monotonic() - start_time
    logger.info(f"测试完成 | 总耗时: {elapsed:.1f}s | 通过率: {report.pass_rate:.1f}%")

    return report


def main():
    parser = argparse.ArgumentParser(description="模拟对话测试")
    parser.add_argument("--count", type=int, default=None, help="问题数量 (默认: 50)")
    parser.add_argument("--category", type=str, default=None, help="只测试某分类 (knowledge_base/general_qa/small_talk/task/content_filter/edge_case)")
    parser.add_argument("--verbose", action="store_true", help="详细日志 (DEBUG级别)")
    parser.add_argument("--no-judge", action="store_true", help="跳过LLM评判，仅做规则检查")
    parser.add_argument("--config", type=str, default=str(SCRIPTS_DIR / "chat_sim_config.yaml"), help="配置文件路径")

    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 日志配置
    log_level = "DEBUG" if args.verbose else config.get("logging", {}).get("level", "INFO")
    log_path = config.get("logging", {}).get("save_path", "scripts/test_data/logs/")
    setup_logging(log_level, log_path)

    logger.info("模拟对话测试启动")
    logger.info(f"配置: {args.config}")

    # 运行测试
    asyncio.run(run_test(config, args))


if __name__ == "__main__":
    main()
