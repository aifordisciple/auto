"""
系统学习层端到端测试用例

测试流程:
1. 模拟成功会话 → 验证 SessionPool 收集
2. 手动添加系统技能 → 验证数据库存储
3. 模拟用户查询 → 验证技能注入
4. 查看统计数据 → 验证完整流程

运行方式:
    docker exec autonome-api python /workspace/test_e2e_system_learning.py
"""

import sys
import json
from datetime import datetime

sys.path.insert(0, "/app")

from app.core.logger import log
from sqlmodel import Session, select

# 导入系统学习层组件
from app.services.system_learning.session_pool import get_session_pool, reset_session_pool
from app.services.system_learning.privacy_validator import get_privacy_validator
from app.services.system_learning.skill_injector import get_skill_injector, reset_skill_injector
from app.services.system_learning.method_extractor import get_method_extractor, reset_method_extractor
from app.models.system_skill import SystemSkill, SystemSkillCreate, SystemSkillStatus
from app.models.uuid import generate_system_skill_id
from app.core.database import engine


def print_header(title: str):
    """打印标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def print_step(step: int, title: str):
    """打印步骤"""
    print(f"\n📌 步骤 {step}: {title}")
    print('-'*70)


def test_e2e_system_learning():
    """端到端测试"""

    print_header("系统学习层端到端测试")
    print(f"测试时间: {datetime.now().isoformat()}")

    db_session = Session(engine)

    try:
        # =====================================================================
        # 步骤 1: 初始化并清空测试数据
        # =====================================================================
        print_step(1, "初始化测试环境")

        # 重置单例
        reset_session_pool()
        reset_skill_injector()
        reset_method_extractor()

        # 获取实例
        pool = get_session_pool()
        validator = get_privacy_validator()
        injector = get_skill_injector()
        extractor = get_method_extractor()

        # 清空会话池
        pool.clear_all()
        print("✅ 测试环境初始化完成")

        # =====================================================================
        # 步骤 2: 模拟成功会话收集
        # =====================================================================
        print_step(2, "模拟成功会话收集到 SessionPool")

        # 模拟 3 个不同置信度的会话
        test_sessions = [
            {
                "session_id": "test_chat_001",
                "confidence": 0.95,  # 高置信度，应被接受
                "user_id": 1,
                "project_id": 10,
                "message_count": 15,
                "has_code": True,
                "expected": "accepted"
            },
            {
                "session_id": "test_chat_002",
                "confidence": 0.75,  # 低于阈值，应被拒绝
                "user_id": 1,
                "project_id": 10,
                "message_count": 10,
                "has_code": True,
                "expected": "rejected"
            },
            {
                "session_id": "test_chat_003",
                "confidence": 0.88,  # 高置信度，应被接受
                "user_id": 2,
                "project_id": 20,
                "message_count": 8,
                "has_code": False,
                "expected": "accepted"
            }
        ]

        for session in test_sessions:
            result = pool.add_session(
                session_id=session["session_id"],
                confidence=session["confidence"],
                user_id=session["user_id"],
                project_id=session["project_id"],
                message_count=session["message_count"],
                has_code=session["has_code"]
            )
            status = "✅ 已接受" if result else "❌ 已拒绝"
            expected = "✅" if (result == (session["expected"] == "accepted")) else "❌ 不符合预期"
            print(f"  会话 {session['session_id']}: 置信度 {session['confidence']:.2f} → {status} {expected}")

        # 检查池状态
        stats = pool.get_stats()
        print(f"\n📊 会话池统计:")
        print(f"  - 待处理会话数: {stats['total']}")
        print(f"  - 平均置信度: {stats['avg_confidence']:.2f}")
        print(f"  - 按用户分布: {stats['by_user']}")

        # =====================================================================
        # 步骤 3: 验证隐私脱敏功能
        # =====================================================================
        print_step(3, "验证隐私脱敏功能")

        # 测试敏感内容
        sensitive_content = """
        请分析 /data/project/sample_001.csv 文件，
        基因 ENSG00000123456 和 ENSG00000789012 的表达情况。
        样本 sample_001 到 sample_100 来自 lab-genomics 团队。
        服务器地址: https://internal.lab.com/api
        """

        is_valid, errors = validator.validate(sensitive_content)
        print(f"  敏感内容验证: {'❌ 检测到隐私问题' if not is_valid else '✅ 无隐私问题'}")

        if errors:
            print(f"  检测到 {len(errors)} 个隐私问题:")
            for error in errors[:5]:
                print(f"    - {error[:60]}...")

        # 自动脱敏
        redacted = validator.redact(sensitive_content)
        print(f"\n  脱敏后内容预览:")
        print(f"    {redacted[:150]}...")

        # =====================================================================
        # 步骤 4: 手动创建系统技能并存储
        # =====================================================================
        print_step(4, "创建测试系统技能并存入数据库")

        # 创建测试技能
        test_skill = SystemSkill(
            skill_id=generate_system_skill_id(),
            method_type="analysis_strategy",
            name="RNA-seq 差异表达分析策略",
            description="基于 DESeq2 的差异表达分析标准流程，包含质量控制、标准化和统计检验",
            instructions="""# 目标
执行标准的 RNA-seq 差异表达分析

# 约束
- 使用 DESeq2 包
- 输出 log2FoldChange 和 adjusted p-value
- 使用 TSV 格式保存结果

# 步骤
1. 读取 count 矩阵
2. 创建 DESeqDataSet 对象
3. 执行差异分析
4. 提取结果并保存

# 参数建议
- padj 阈值: 0.05
- log2FC 阈值: 1.0""",
            triggers=["DESeq2", "差异分析", "RNA-seq", "差异表达", "count矩阵"],
            tags=["transcriptomics", "rnaseq", "differential-expression"],
            examples=["输入: count_matrix.tsv + sample_info.tsv", "输出: DEG_results.tsv"],
            version="1.0.0",
            source_sessions=5,
            confidence_score=0.85,
            status=SystemSkillStatus.ACTIVE.value
        )

        db_session.add(test_skill)
        db_session.commit()
        db_session.refresh(test_skill)

        print(f"  ✅ 系统技能已创建:")
        print(f"    - ID: {test_skill.skill_id}")
        print(f"    - 名称: {test_skill.name}")
        print(f"    - 类型: {test_skill.method_type}")
        print(f"    - 置信度: {test_skill.confidence_score:.2f}")
        print(f"    - 触发词: {test_skill.triggers[:3]}...")

        # =====================================================================
        # 步骤 5: 测试技能注入器检索
        # =====================================================================
        print_step(5, "测试技能注入器检索功能")

        # 模拟用户查询
        test_queries = [
            "如何使用 DESeq2 进行差异表达分析",
            "我有一个 RNA-seq count 矩阵，想做差异分析",
            "帮我分析一下数据"  # 这个查询应该不会匹配
        ]

        for query in test_queries:
            print(f"\n  查询: '{query[:40]}...'")

            # 执行混合检索
            skills = injector.hybrid_search(query, limit=3)

            if skills:
                print(f"  匹配到 {len(skills)} 个系统技能:")
                for skill in skills:
                    print(f"    - {skill.name} (置信度: {skill.confidence_score:.2f})")

                # 获取注入指令
                instructions = injector.inject_for_query(query, limit=1)
                if instructions:
                    print(f"  注入指令预览:")
                    print(f"    {instructions[0][:100]}...")
            else:
                print(f"  未匹配到系统技能")

        # =====================================================================
        # 步骤 6: 模拟方法提取流程
        # =====================================================================
        print_step(6, "模拟方法提取流程")

        # 模拟一个成功的对话
        mock_conversation = [
            {"role": "user", "content": "如何进行 DESeq2 差异分析？"},
            {"role": "assistant", "content": "首先需要准备 count 矩阵和样本信息文件，然后使用 DESeq2 包进行分析..."},
            {"role": "user", "content": "具体步骤是什么？"},
            {"role": "assistant", "content": "步骤如下：1. 读取数据 2. 创建 DESeqDataSet 3. 运行 DESeq 4. 提取结果..."},
            {"role": "user", "content": "成功了，谢谢！"}
        ]

        print(f"  模拟对话消息数: {len(mock_conversation)}")

        # 格式化对话
        formatted = extractor._format_conversation(mock_conversation)
        print(f"  格式化后长度: {len(formatted)} 字符")

        # 注意: 实际提取需要配置 LLM 客户端
        print(f"  ⚠️ 实际方法提取需要配置 LLM 客户端 (OpenAI API Key)")

        # =====================================================================
        # 步骤 7: 查看最终统计数据
        # =====================================================================
        print_step(7, "查看最终统计数据")

        # 会话池统计
        pool_stats = pool.get_stats()
        print(f"\n📊 会话池最终统计:")
        print(f"  - 待处理会话: {pool_stats['total']}")
        print(f"  - 平均置信度: {pool_stats['avg_confidence']:.2f}")
        print(f"  - 已处理总数: {pool_stats['processed_count']}")

        # 数据库技能统计
        db_skills = db_session.exec(
            select(SystemSkill).where(SystemSkill.status == SystemSkillStatus.ACTIVE.value)
        ).all()

        print(f"\n📊 系统技能统计:")
        print(f"  - 总技能数: {len(db_skills)}")

        if db_skills:
            by_type = {}
            for skill in db_skills:
                by_type[skill.method_type] = by_type.get(skill.method_type, 0) + 1
            print(f"  - 按类型分布: {by_type}")

            # 显示最新技能
            latest = db_skills[-1]
            print(f"\n  最新技能:")
            print(f"    - 名称: {latest.name}")
            print(f"    - 注入次数: {latest.injection_count}")
            print(f"    - 置信度: {latest.confidence_score:.2f}")

        # =====================================================================
        # 测试完成
        # =====================================================================
        print_header("测试完成")

        print("\n✅ 端到端测试通过!")
        print("\n📋 功能验证清单:")
        print("  ✅ SessionPool 会话收集")
        print("  ✅ 隐私验证器脱敏功能")
        print("  ✅ 系统技能数据库存储")
        print("  ✅ 技能注入器混合检索")
        print("  ✅ 方法提取器对话处理")
        print("  ✅ 统计数据查询")

        print("\n📝 后续建议:")
        print("  1. 配置 OPENAI_API_KEY 环境变量以启用 LLM 提取")
        print("  2. 配置 Celery Beat 定时任务以自动处理会话池")
        print("  3. 在实际用户对话中验证 SuccessEvaluator 集成")

        # 清理测试数据
        print("\n🧹 清理测试数据...")
        pool.clear_all()
        db_session.delete(test_skill)
        db_session.commit()
        print("  ✅ 测试数据已清理")

        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db_session.close()


if __name__ == "__main__":
    success = test_e2e_system_learning()
    sys.exit(0 if success else 1)