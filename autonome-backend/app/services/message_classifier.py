"""
消息分类前置服务 - 判断消息是否需要技能推荐

功能:
1. 使用快速规则预筛选纯理论问题（< 1ms）
2. 使用轻量级 LLM 进行深度分类（~500ms）
3. 超时/异常时降级为安全默认值

分类结果:
- needs_skill_recommendation: True/False
- classification_reason: 分类原因
- detected_domains: 检测到的领域
- classification_source: "rule" | "llm" | "fallback"

使用场景:
- 在技能推荐前快速判断是否需要调用推荐流程
- 避免对纯理论问题（如"什么是单细胞测序"）做无意义的技能推荐
"""

import os
import re
import json
import asyncio
from typing import Dict, Any, Optional, List

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from app.core.logger import log
from app.core.database import engine
from sqlmodel import Session, select
from app.models.config import SystemConfig


class MessageClassifier:
    """
    消息分类前置服务 - 判断消息是否需要技能推荐

    使用快速 LLM（如 qwen2.5:7b 或 gpt-4o-mini）判断消息是否涉及:
    - 代码执行需求
    - 技能调用意图
    - 数据处理需求

    对于纯理论问题（如"什么是单细胞测序"），直接跳过技能推荐，
    避免无意义的向量计算和 LLM 精排。
    """

    # 默认配置
    DEFAULT_TIMEOUT = 2.0  # 超时时间（秒），快速响应
    DEFAULT_TEMPERATURE = 0.1  # 低温度，更确定性的输出

    # 快速跳过模式：纯理论问题，不需要技能推荐
    # 这些模式匹配后，如果没有任何执行意图，直接跳过
    QUICK_SKIP_PATTERNS = [
        # 中文纯理论问题
        r'^(什么是|怎么理解|如何理解|解释一下|告诉我|帮我理解)',
        r'^(what is|how to understand|explain|tell me about)',
        r'(有什么区别|有什么不同|为什么|怎样理解)',
        r'(是指|是什么意思|概念|定义|原理)',
        # 简单问候
        r'^(你好|hi|hello|谢谢|感谢|再见|bye)',
        # 纯信息查询（非执行）
        r'^(查看|显示|列出|列举)(?!.*文件|.*数据)',
    ]

    # 快速触发模式：明确需要技能推荐
    QUICK_TRIGGER_PATTERNS = [
        # 执行类动词
        r'(分析|处理|运行|执行|计算|生成|转换|下载|上传)',
        r'(帮我|请帮我|想要|需要|麻烦)',
        r'(帮我分析|帮我处理|帮我运行|帮我计算)',
        # 生物信息数据格式
        r'(fastq|bam|vcf|h5ad|csv|tsv|fasta|gtf|bed)',
        # 生信分析领域
        r'(单细胞|转录组|基因组|质控|差异|比对|定量)',
        r'(pipeline|流程|工作流|流水线)',
        # 明确技能名称
        r'(fastqc|multiqc|seurat|scanpy|cellranger)',
        # 文件操作
        r'(读取|写入|导入|导出|解析)',
    ]

    def __init__(self, session: Session = None):
        """
        初始化消息分类器

        Args:
            session: 数据库会话，用于获取系统配置
        """
        self.session = session
        self._llm_client: Optional[ChatOpenAI] = None
        self._config: Optional[SystemConfig] = None
        self._classifier_config: Optional[Dict[str, str]] = None

    def _get_config(self) -> SystemConfig:
        """获取系统配置"""
        if self._config is None:
            if self.session:
                self._config = self.session.exec(select(SystemConfig)).first()
            else:
                with Session(engine) as temp_session:
                    self._config = temp_session.exec(select(SystemConfig)).first()
        return self._config

    def _get_classifier_config(self) -> Dict[str, str]:
        """
        获取分类器模型配置

        配置优先级:
        1. SystemConfig.classifier_* 专用配置
        2. 环境变量 CLASSIFIER_MODEL, CLASSIFIER_BASE_URL, CLASSIFIER_API_KEY
        3. 使用主模型配置，优先选择快速模型

        Returns:
            Dict: {model, base_url, api_key}
        """
        if self._classifier_config:
            return self._classifier_config

        config = self._get_config()

        # 1. 检查专用分类器配置
        classifier_model = None
        classifier_base_url = None
        classifier_api_key = None

        if config:
            classifier_model = getattr(config, 'classifier_model', None)
            classifier_base_url = getattr(config, 'classifier_base_url', None)
            classifier_api_key = getattr(config, 'classifier_api_key', None)

        # 2. 检查环境变量
        if not classifier_model:
            classifier_model = os.getenv("CLASSIFIER_MODEL")
            classifier_base_url = os.getenv("CLASSIFIER_BASE_URL")
            classifier_api_key = os.getenv("CLASSIFIER_API_KEY")

        # 3. 回退到主模型配置
        if not classifier_model and config:
            base_url = config.openai_base_url or ""
            default_model = config.default_model or ""
            is_local = (
                "host.docker.internal" in base_url or
                "ollama" in base_url.lower() or
                "localhost" in base_url
            )

            # 使用主模型配置
            classifier_base_url = base_url
            classifier_api_key = config.openai_api_key

            if is_local:
                # 本地模型，使用用户配置的模型
                classifier_model = default_model if default_model else "qwen2.5:7b"
            else:
                # 云端模型，使用用户配置的模型
                classifier_model = default_model if default_model else "gpt-4o-mini"

        # 4. 最终回退
        if not classifier_model:
            classifier_model = "gpt-4o-mini"
            classifier_base_url = "https://api.openai.com/v1"
            classifier_api_key = os.getenv("OPENAI_API_KEY", "EMPTY")

        self._classifier_config = {
            "model": classifier_model,
            "base_url": classifier_base_url,
            "api_key": classifier_api_key
        }

        log.debug(f"[MessageClassifier] 分类器配置: model={classifier_model}")
        return self._classifier_config

    def _init_llm_client(self) -> ChatOpenAI:
        """初始化 LLM 客户端"""
        if self._llm_client:
            return self._llm_client

        config = self._get_classifier_config()

        self._llm_client = ChatOpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
            temperature=self.DEFAULT_TEMPERATURE,
            timeout=self.DEFAULT_TIMEOUT
        )

        return self._llm_client

    def _quick_classify(self, user_query: str) -> Optional[bool]:
        """
        快速规则分类（不调用 LLM）

        Returns:
            True: 肯定需要技能推荐
            False: 肯定不需要技能推荐
            None: 需要进一步 LLM 判断
        """
        query_lower = user_query.lower().strip()

        # 空消息或过短消息，跳过推荐
        if len(query_lower) < 3:
            return False

        # 检查快速触发模式（优先）
        for pattern in self.QUICK_TRIGGER_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True  # 明确需要技能推荐

        # 检查快速跳过模式
        for pattern in self.QUICK_SKIP_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return False  # 纯理论问题，跳过推荐

        return None  # 需要进一步判断

    async def classify(self, user_query: str) -> Dict[str, Any]:
        """
        分类消息是否需要技能推荐

        Args:
            user_query: 用户查询

        Returns:
            {
                "needs_skill_recommendation": bool,
                "classification_reason": str,
                "detected_domains": List[str],
                "classification_source": "rule" | "llm" | "fallback"
            }
        """
        # 1. 快速规则分类
        quick_result = self._quick_classify(user_query)

        if quick_result is not None:
            source = "rule"
            reason = "规则匹配: " + (
                "检测到技能/代码执行需求" if quick_result else "纯理论问题或问候"
            )
            log.info(f"[MessageClassifier] 规则分类: needs_recommendation={quick_result}")
            return {
                "needs_skill_recommendation": quick_result,
                "classification_reason": reason,
                "detected_domains": [],
                "classification_source": source
            }

        # 2. LLM 分类
        try:
            llm = self._init_llm_client()

            prompt = f"""判断用户消息是否需要推荐技能或代码执行。

用户消息: {user_query}

技能类别包括:
- 质量控制 (FastQC, MultiQC)
- 单细胞分析 (Seurat, Scanpy)
- 转录组分析 (RNA-seq, 差异表达)
- 流程自动化 (Nextflow)
- 可视化 (绘图, 图表)

需要推荐的情况:
1. 用户需要执行具体的数据分析任务
2. 用户需要处理特定的生物信息数据文件
3. 用户明确要求运行某个流程或工具

不需要推荐的情况:
1. 用户只是在询问概念、定义、原理
2. 用户只是在闲聊或问候
3. 用户没有具体的执行意图

只返回 JSON，不要其他文字:
{{
    "needs_skill_recommendation": true或false,
    "reason": "简短原因（中文）",
    "detected_domains": ["检测到的领域列表"]
}}"""

            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=self.DEFAULT_TIMEOUT
            )

            content = response.content if hasattr(response, 'content') else str(response)
            json_match = re.search(r'\{.*\}', content, re.DOTALL)

            if json_match:
                result = json.loads(json_match.group())
                needs_recommend = result.get("needs_skill_recommendation", True)

                log.info(f"[MessageClassifier] LLM分类: needs_recommendation={needs_recommend}, "
                        f"reason={result.get('reason', '')}")

                return {
                    "needs_skill_recommendation": needs_recommend,
                    "classification_reason": result.get("reason", "LLM 分类"),
                    "detected_domains": result.get("detected_domains", []),
                    "classification_source": "llm"
                }

        except asyncio.TimeoutError:
            log.warning(f"[MessageClassifier] LLM 分类超时 ({self.DEFAULT_TIMEOUT}s)")
        except json.JSONDecodeError as e:
            log.warning(f"[MessageClassifier] JSON 解析失败: {e}")
        except Exception as e:
            log.warning(f"[MessageClassifier] LLM 分类失败: {e}")

        # 3. 降级：默认需要技能推荐（安全策略）
        log.info("[MessageClassifier] 降级默认：启用技能推荐")
        return {
            "needs_skill_recommendation": True,
            "classification_reason": "降级默认：分类服务不可用，保持推荐",
            "detected_domains": [],
            "classification_source": "fallback"
        }


# ==========================================
# 便捷函数
# ==========================================

async def classify_message(
    user_query: str,
    session: Session = None
) -> Dict[str, Any]:
    """
    分类消息是否需要技能推荐（便捷函数）

    Args:
        user_query: 用户查询
        session: 数据库会话（可选）

    Returns:
        分类结果字典
    """
    classifier = MessageClassifier(session)
    return await classifier.classify(user_query)


# ==========================================
# 同步版本（用于非异步上下文）
# ==========================================

def classify_message_sync(user_query: str, session: Session = None) -> Dict[str, Any]:
    """
    分类消息是否需要技能推荐（同步版本）

    注意：此函数会阻塞，仅用于非异步上下文
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环正在运行，创建新的线程执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    classify_message(user_query, session)
                )
                return future.result(timeout=5.0)
        else:
            return loop.run_until_complete(classify_message(user_query, session))
    except RuntimeError:
        # 没有事件循环，直接运行
        return asyncio.run(classify_message(user_query, session))


log.info("✅ 消息分类前置服务已加载")