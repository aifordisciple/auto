"""
V2 架构升级测试套件

覆盖所有 V2 里程碑：
- M1.1: 内容过滤（json_intent 泄漏 + 跨块过滤 + 沙箱锚点标记）
- M1.2: 路由器（5 意图类型 + 置信度门控 + sub_intent）
- M2.1: PTY Manager（PTYResult + PTYExtractionError）
- M2.2: 语义搜索（双轨搜索）
- M2.3: 沙箱规划器（重试 + 回退）
- M4.1: 参数预填（4 级策略）
- M5.2: 重试逻辑（指数退避）
"""

import pytest
import json


# ==========================================
# M1.1: 内容过滤 V2 测试
# ==========================================

class TestV2ContentFilter:
    """V2: json_intent 泄漏 + 沙箱锚点标记 + 跨块过滤"""

    def test_filter_json_intent_leak(self):
        """json_intent 绝不应泄漏到前端"""
        from app.core.content_filter import filter_thinking_content
        content = '```json_intent\n{"intent": "VAGUE_ANALYSIS", "confidence": 0.8}\n```\n\n实际回复内容'
        result = filter_thinking_content(content)
        assert "json_intent" not in result
        assert "VAGUE_ANALYSIS" not in result
        assert "实际回复内容" in result

    def test_filter_sandbox_result_tags(self):
        """[AUTONOME_RESULT_START/END] 标记不应泄漏"""
        from app.core.content_filter import filter_thinking_content
        content = '[AUTONOME_RESULT_START]\n{"plan": "test"}\n[AUTONOME_RESULT_END]\n\n实际回复'
        result = filter_thinking_content(content)
        assert "[AUTONOME_RESULT_START]" not in result
        assert "[AUTONOME_RESULT_END]" not in result
        assert "实际回复" in result

    def test_filter_sandbox_start_tag_only(self):
        """单独的 [AUTONOME_RESULT_START] 也应过滤"""
        from app.core.content_filter import filter_thinking_content
        content = '一些内容 [AUTONOME_RESULT_START] 更多内容'
        result = filter_thinking_content(content)
        assert "[AUTONOME_RESULT_START]" not in result

    def test_stream_filter_basic(self):
        """StreamContentFilter 基本过滤"""
        from app.core.content_filter import StreamContentFilter
        sf = StreamContentFilter()
        # 正常内容应通过
        result = sf.filter_chunk("正常内容")
        assert "正常内容" in result

    def test_stream_filter_cross_chunk_leak(self):
        """跨 chunk 边界的 json_intent 应被过滤"""
        from app.core.content_filter import StreamContentFilter
        sf = StreamContentFilter()
        # 将 json_intent 分割到两个 chunk
        chunk1 = "一些内容 ```json_in"
        chunk2 = "tent\n{\"intent\": \"CHAT\"}\n```"
        r1 = sf.filter_chunk(chunk1)
        r2 = sf.filter_chunk(chunk2)
        combined = r1 + r2
        assert "json_intent" not in combined
        assert "CHAT" not in combined

    def test_stream_filter_flush(self):
        """flush 应返回缓冲区剩余内容"""
        from app.core.content_filter import StreamContentFilter
        sf = StreamContentFilter()
        sf.filter_chunk("正常内容")
        remaining = sf.flush()
        # flush 后缓冲区应清空
        assert sf._buffer == ""

    def test_stream_filter_sandbox_tags_cross_chunk(self):
        """跨 chunk 的 [AUTONOME_RESULT_START] 应被过滤"""
        from app.core.content_filter import StreamContentFilter
        sf = StreamContentFilter()
        chunk1 = "内容 [AUTONOME_RESULT_STA"
        chunk2 = "RT]\n{\"plan\": \"test\"}\n[AUTONOME_RESULT_END]"
        r1 = sf.filter_chunk(chunk1)
        r2 = sf.filter_chunk(chunk2)
        combined = r1 + r2
        assert "[AUTONOME_RESULT_START]" not in combined
        assert "[AUTONOME_RESULT_END]" not in combined


# ==========================================
# M1.2: 路由器 V2 测试
# ==========================================

class TestV2Router:
    """V2: 5 意图类型 + 置信度门控 + sub_intent"""

    def test_intent_type_has_5_types(self):
        """IntentType 应只有 5 种类型（typing.Literal）"""
        from app.agent.schemas import IntentType
        # IntentType 是 typing.Literal，不是 Enum
        type_values = set(IntentType.__args__)
        assert len(type_values) == 5
        assert type_values == {"CHAT", "EXPLICIT_SKILL", "VAGUE_ANALYSIS", "TROUBLESHOOT", "SYSTEM_ACTION"}

    def test_intent_classification_has_sub_intent(self):
        """IntentClassification 应有 sub_intent 字段"""
        from app.agent.schemas import IntentClassification
        # 验证 sub_intent 字段存在
        ic = IntentClassification(
            intent="SYSTEM_ACTION",
            confidence=0.9,
            reason="test",
            sub_intent="ui_update"
        )
        assert ic.sub_intent == "ui_update"

    def test_confidence_threshold_default(self):
        """置信度阈值默认 0.6"""
        import os
        # 不设置环境变量时应使用默认值
        from app.agent.nodes.router import CONFIDENCE_THRESHOLD
        assert CONFIDENCE_THRESHOLD == 0.6


# ==========================================
# M2.1: PTY Manager V2 测试
# ==========================================

class TestV2PTYManager:
    """V2: PTYResult + PTYExtractionError"""

    def test_pty_result_success(self):
        """PTYResult 成功状态"""
        from app.services.pty_manager import PTYResult
        result = PTYResult(
            success=True,
            raw_output="test output",
            structured_data={"plan": "test"},
            execution_time_ms=1000
        )
        assert result.success is True
        assert result.structured_data == {"plan": "test"}
        assert result.error is None

    def test_pty_result_failure(self):
        """PTYResult 失败状态"""
        from app.services.pty_manager import PTYResult
        result = PTYResult(
            success=False,
            error="提取失败",
            error_type="marker_not_found",
            execution_time_ms=500
        )
        assert result.success is False
        assert result.error == "提取失败"
        assert result.structured_data is None

    def test_pty_extraction_error_types(self):
        """PTYExtractionError 应有细粒度错误类型"""
        from app.services.pty_manager import PTYExtractionError
        ErrorType = PTYExtractionError.ErrorType
        # 验证所有错误类型
        assert ErrorType.MARKER_NOT_FOUND.value == "marker_not_found"
        assert ErrorType.JSON_INVALID.value == "json_invalid"
        assert ErrorType.JSON_TRUNCATED.value == "json_truncated"
        assert ErrorType.EMPTY_OUTPUT.value == "empty_output"

    def test_extract_structured_result_success(self):
        """extract_structured_result 成功提取"""
        from app.services.pty_manager import PTYManager
        output = '一些内容\n[AUTONOME_RESULT_START]\n{"plan": "分析数据", "steps": []}\n[AUTONOME_RESULT_END]\n更多内容'
        result = PTYManager.extract_structured_result(output)
        assert result is not None
        assert result["plan"] == "分析数据"

    def test_extract_structured_result_no_marker(self):
        """extract_structured_result 无标记应抛出异常"""
        from app.services.pty_manager import PTYManager, PTYExtractionError
        output = "没有标记的普通输出"
        with pytest.raises(PTYExtractionError) as exc_info:
            PTYManager.extract_structured_result(output)
        assert exc_info.value.error_type.value == "marker_not_found"

    def test_extract_structured_result_invalid_json(self):
        """extract_structured_result 空 JSON 内容应抛出异常"""
        from app.services.pty_manager import PTYManager, PTYExtractionError
        # json_repair 非常宽容，大部分无效 JSON 都能修复
        # 但标记之间为空内容时，json.loads("") 会失败
        output = '[AUTONOME_RESULT_START]\n\n[AUTONOME_RESULT_END]'
        with pytest.raises(PTYExtractionError) as exc_info:
            PTYManager.extract_structured_result(output)
        assert exc_info.value.error_type.value == "json_invalid"


# ==========================================
# M2.3: 沙箱规划器 V2 测试
# ==========================================

class TestV2SandboxPlanner:
    """V2: 沙箱规划器门控 + StrategyCard 转换"""

    def test_sandbox_planner_env_gate(self):
        """沙箱规划器应受环境变量门控"""
        import os
        from app.agent.nodes.sandbox_planner import is_sandbox_planner_enabled
        # 当前应启用（已在 docker-compose.yml 中设置）
        assert is_sandbox_planner_enabled() is True

    def test_to_strategy_card(self):
        """_to_strategy_card 应正确转换"""
        from app.agent.nodes.sandbox_planner import SandboxPlanner
        planner = SandboxPlanner()
        plan_result = {
            "title": "RNA-seq 分析",
            "description": "差异表达分析",
            "plan": "使用 DESeq2 分析",
            "skill_id": "deseq2_pipeline",
            "tool_id": "python_executor",
            "parameters": {"pvalue": 0.05},
            "steps": [
                {"task_id": "t1", "name": "加载数据", "instruction": "读取 count matrix"},
                {"task_id": "t2", "name": "差异分析", "instruction": "运行 DESeq2"},
            ],
            "estimated_time": "约 10 分钟"
        }
        card = planner._to_strategy_card(plan_result, "分析 RNA-seq 数据")
        assert card["title"] == "RNA-seq 分析"
        assert card["tool_id"] == "python_executor"
        assert len(card["steps"]) == 2
        assert card["skill_id"] == "deseq2_pipeline"
        assert card["_raw_plan"] == plan_result

    def test_sandbox_planner_node_empty_messages(self):
        """空消息应返回 fallback"""
        from app.agent.nodes.sandbox_planner import sandbox_planner_node
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            sandbox_planner_node({"messages": []})
        )
        assert result.get("fallback") is True


# ==========================================
# M2.4: 容器池集成测试
# ==========================================

class TestV2ContainerPool:
    """V2: 容器池集成"""

    def test_container_pool_service_exists(self):
        """容器池服务应存在"""
        from app.services.container_pool_service import ContainerPoolService
        assert ContainerPoolService is not None

    def test_sandbox_planner_node_container_pool_integration(self):
        """sandbox_planner_node 应支持容器池"""
        from app.agent.nodes.sandbox_planner import sandbox_planner_node
        import inspect
        source = inspect.getsource(sandbox_planner_node)
        assert "AUTONOME_USE_CONTAINER_POOL" in source
        assert "acquire_container" in source
        assert "release_container" in source


# ==========================================
# M4.1: 参数预填 V2 测试
# ==========================================

class TestV2SkillFormBuilder:
    """V2: 4 级参数预填策略"""

    def test_prefill_explicit_mention(self):
        """级别 1: 显式提及（param=value 模式）"""
        from app.agent.nodes.skill_form_builder import _prefill_parameters
        params = [{"name": "resolution", "type": "number", "default": 0.5, "required": True}]
        # 使用 param=value 模式，这是 _extract_explicit_mention 支持的格式
        context = {"user_message": "resolution=0.4 分析数据", "workspace_files": [], "workspace_info": ""}
        result = _prefill_parameters(params, context)
        assert result[0]["source"] == "explicit"
        assert result[0]["value"] == "0.4"
        assert result[0]["confidence"] == 1.0

    def test_prefill_entity_extraction_file(self):
        """级别 2: 实体提取（文件路径）"""
        from app.agent.nodes.skill_form_builder import _prefill_parameters
        params = [{"name": "input_file", "type": "text", "default": None, "required": True}]
        context = {"user_message": "分析 /workspace/data/sample.csv", "workspace_files": [], "workspace_info": ""}
        result = _prefill_parameters(params, context)
        assert result[0]["source"] == "extracted"
        assert "/workspace/data/sample.csv" in str(result[0]["value"])

    def test_prefill_workspace_inference(self):
        """级别 3: 工作区推断"""
        from app.agent.nodes.skill_form_builder import _prefill_parameters
        params = [{"name": "data_file", "type": "text", "default": None, "required": True}]
        context = {
            "user_message": "分析数据",
            "workspace_files": ["sample.csv", "config.yaml"],
            "workspace_info": ""
        }
        result = _prefill_parameters(params, context)
        assert result[0]["source"] == "workspace"
        assert result[0]["value"] == "sample.csv"

    def test_prefill_default_value(self):
        """级别 4: 默认值"""
        from app.agent.nodes.skill_form_builder import _prefill_parameters
        params = [{"name": "threshold", "type": "number", "default": 0.05, "required": False}]
        context = {"user_message": "分析数据", "workspace_files": [], "workspace_info": ""}
        result = _prefill_parameters(params, context)
        assert result[0]["source"] == "default"
        assert result[0]["value"] == 0.05
        assert result[0]["confidence"] == 0.3

    def test_prefill_null_when_no_value(self):
        """无值可填时 source=null"""
        from app.agent.nodes.skill_form_builder import _prefill_parameters
        params = [{"name": "unknown_param", "type": "text", "default": None, "required": False}]
        context = {"user_message": "分析数据", "workspace_files": [], "workspace_info": ""}
        result = _prefill_parameters(params, context)
        assert result[0]["source"] == "null"
        assert result[0]["value"] is None
        assert result[0]["confidence"] == 0.0

    def test_prefill_priority_order(self):
        """显式提及优先于实体提取"""
        from app.agent.nodes.skill_form_builder import _prefill_parameters
        params = [{"name": "input_file", "type": "text", "default": "/default/path.csv", "required": True}]
        context = {
            "user_message": "input_file=/custom/path.csv 分析 /workspace/other.csv",
            "workspace_files": [],
            "workspace_info": ""
        }
        result = _prefill_parameters(params, context)
        # 显式提及应优先
        assert result[0]["source"] == "explicit"
        assert result[0]["value"] == "/custom/path.csv"


# ==========================================
# M5.2: 重试逻辑测试
# ==========================================

class TestV2RetryLogic:
    """V2: 沙箱规划器重试逻辑"""

    def test_sandbox_max_retries_default(self):
        """默认最大重试次数为 2"""
        from app.agent.nodes.sandbox_planner import SANDBOX_MAX_RETRIES
        assert SANDBOX_MAX_RETRIES == 2

    def test_sandbox_timeout_default(self):
        """默认超时为 120 秒"""
        from app.agent.nodes.sandbox_planner import SANDBOX_TIMEOUT
        assert SANDBOX_TIMEOUT == 120

    def test_retry_context_in_prompt(self):
        """重试上下文应注入到 prompt 中"""
        from app.agent.nodes.sandbox_planner import SANDBOX_PLANNER_PROMPT
        assert "{retry_context}" in SANDBOX_PLANNER_PROMPT

    def test_plan_method_has_retry_params(self):
        """plan() 方法应有 max_retries 参数"""
        from app.agent.nodes.sandbox_planner import SandboxPlanner
        import inspect
        sig = inspect.signature(SandboxPlanner.plan)
        assert "max_retries" in sig.parameters
        assert "event_callback" in sig.parameters


# ==========================================
# M2.2: 语义搜索测试
# ==========================================

class TestV2SemanticSearch:
    """V2: 语义搜索引擎"""

    def test_semantic_search_engine_exists(self):
        """SemanticSearchEngine 类应存在"""
        from app.mcp.semantic_search import SemanticSearchEngine
        assert SemanticSearchEngine is not None

    def test_semantic_search_env_gate(self):
        """语义搜索应受环境变量门控"""
        import os
        use_semantic = os.environ.get("AUTONOME_USE_SEMANTIC_SEARCH", "false").lower() == "true"
        # 当前应启用
        assert use_semantic is True

    def test_dual_track_search_weights(self):
        """双轨搜索权重应为 keyword=0.4, semantic=0.6"""
        from app.mcp.autonome_skills_mcp import AutonomeSkillsMCP
        import inspect
        source = inspect.getsource(AutonomeSkillsMCP.search_skills_enhanced)
        assert "KEYWORD_WEIGHT = 0.4" in source
        assert "SEMANTIC_WEIGHT = 0.6" in source


# ==========================================
# 集成测试: SSE 事件类型
# ==========================================

class TestV2SSEEvents:
    """V2: 新 SSE 事件类型"""

    def test_planner_sse_events_in_chat(self):
        """chat.py 应处理 planner_status/planner_log/planner_result 事件"""
        import inspect
        from app.api.routes.chat import chat_stream
        source = inspect.getsource(chat_stream)
        assert "planner_status" in source or "planner_result" in source

    def test_strategy_card_sse_event(self):
        """chat.py 应发送 strategy_card SSE 事件"""
        import inspect
        from app.api.routes.chat import chat_stream
        source = inspect.getsource(chat_stream)
        assert "strategy_card" in source

    def test_sandbox_planner_events(self):
        """sandbox_planner.py 应发出 planner_status/planner_log/planner_result 事件"""
        import inspect
        from app.agent.nodes.sandbox_planner import SandboxPlanner
        source = inspect.getsource(SandboxPlanner.plan)
        assert "planner_status" in source
        assert "planner_log" in source
        assert "planner_result" in source


# ==========================================
# 环境变量门控测试
# ==========================================

class TestV2EnvGates:
    """V2: 所有环境变量门控"""

    def test_sandbox_planner_enabled(self):
        """AUTONOME_USE_SANDBOX_PLANNER=true"""
        import os
        assert os.environ.get("AUTONOME_USE_SANDBOX_PLANNER") == "true"

    def test_container_pool_enabled(self):
        """AUTONOME_USE_CONTAINER_POOL=true"""
        import os
        assert os.environ.get("AUTONOME_USE_CONTAINER_POOL") == "true"

    def test_semantic_search_enabled(self):
        """AUTONOME_USE_SEMANTIC_SEARCH=true"""
        import os
        assert os.environ.get("AUTONOME_USE_SEMANTIC_SEARCH") == "true"

    def test_confidence_threshold(self):
        """AUTONOME_ROUTER_CONFIDENCE_THRESHOLD=0.6"""
        import os
        assert os.environ.get("AUTONOME_ROUTER_CONFIDENCE_THRESHOLD") == "0.6"

    def test_sandbox_max_retries(self):
        """AUTONOME_SANDBOX_MAX_RETRIES=2"""
        import os
        assert os.environ.get("AUTONOME_SANDBOX_MAX_RETRIES") == "2"

    def test_sandbox_timeout(self):
        """AUTONOME_SANDBOX_TIMEOUT=120"""
        import os
        assert os.environ.get("AUTONOME_SANDBOX_TIMEOUT") == "120"
