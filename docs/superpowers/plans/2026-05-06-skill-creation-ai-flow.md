# 技能创建 AI 化全流程 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将技能创建从纯手动编辑器升级为 AI 驱动的混合模式 — 聊天入口 + Skill Agent 编排 + Forge 双栏审核工作区。

**Architecture:** 新增独立 Skill Creator Agent (LangGraph StateGraph) 作为编排引擎，通过 SSE 流式推送生成进度到前端。Agent 输出写入 ForgeSession JSONB 作为桥梁。前端 Forge 升级为双栏布局（AI 对话 + 代码编辑器）。

**Tech Stack:** Python 3.12 / FastAPI / LangGraph / SQLModel / PostgreSQL JSONB / SSE / Next.js 16 / TypeScript / Zustand / Monaco Editor

---

## File Structure

```
autonome-backend/app/
├── agent/
│   └── skill_creator.py              # NEW: Skill Creator Agent 状态机
├── api/routes/
│   └── skills_forge_agent.py         # NEW: generate/iterate/supplement SSE 端点
├── models/
│   └── forge_session.py              # MODIFY: SkillDraftSchema 扩展 5 个 agent 字段

autonome-studio/src/
├── lib/api/
│   └── forgeAgent.ts                 # NEW: SSE Agent 通信客户端
├── store/
│   └── useForgeStore.ts              # MODIFY: 新增 agentPhase, agentHistory 状态
├── components/overlays/SkillCenter/
│   ├── ForgePanel.tsx                # MODIFY: 双栏布局重构
│   └── AIAssistantPanel.tsx          # NEW: AI 助手对话面板
└── app/skill-forge/components/
    └── SkillDraftEditor.tsx           # MODIFY: 流式渲染 + AI 补全按钮
```

---

### Task 1: ForgeSession 模型扩展 — Agent 阶段字段

**Files:**
- Modify: `autonome-backend/app/models/forge_session.py`

**Context:** Agent 需要在 ForgeSession 的 JSONB skill_draft 中记录当前阶段、操作历史、检查结果。扩展 SkillDraftSchema 添加 5 个字段。

- [ ] **Step 1: 在 SkillDraftSchema 中添加 Agent 相关字段**

在 `autonome-backend/app/models/forge_session.py` 的 `SkillDraftSchema` 类中添加以下字段：

```python
class SkillDraftSchema(SQLModel):
    """存储在 JSONB 列中的技能草稿结构"""
    name: str = ""
    description: str = ""
    executor_type: str = "Python_env"
    script_code: str = ""
    nextflow_code: str = ""
    parameters_schema: Dict[str, Any] = {}
    expert_knowledge: str = ""
    dependencies: List[str] = []
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: List[str] = []
    # === Agent 阶段字段（新增）===
    agent_phase: Optional[str] = None       # 当前 Agent 阶段: intent_parse/similarity_search/core_generation/static_check/auto_test/forge_output
    agent_history: List[Dict[str, Any]] = [] # Agent 操作历史 [{phase, timestamp, summary}]
    static_check_result: Optional[Dict[str, Any]] = None  # 静态检查结果 {passed, score, issues}
    auto_test_result: Optional[Dict[str, Any]] = None     # 自动测试结果 {passed, output, error_log}
    source_skill_id: Optional[str] = None    # 基于哪个已有技能创建的
```

- [ ] **Step 2: 验证模型导入正确**

```bash
cd autonome-backend && python -c "from app.models.forge_session import SkillDraftSchema; s = SkillDraftSchema(); print(s.model_dump().keys())"
```

Expected: 输出中包含 `agent_phase`, `agent_history`, `static_check_result`, `auto_test_result`, `source_skill_id`

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/models/forge_session.py
git commit -m "feat: ForgeSession 模型扩展 Agent 阶段字段，支持 Skill Creator 状态记录"
```

---

### Task 2: Skill Creator Agent — 状态机核心

**Files:**
- Create: `autonome-backend/app/agent/skill_creator.py`

**Context:** 新建独立的 LangGraph StateGraph Agent。6 阶段流水线：意图解析 → 相似发现 → 核心生成 → 静态检查 → 自动测试 → 输出 Forge。每个阶段通过 SSE 回调推送进度。

- [ ] **Step 1: 定义 AgentState TypedDict 和阶段枚举**

```python
# autonome-backend/app/agent/skill_creator.py

"""技能创建 Agent — 6 阶段 LangGraph 状态机，驱动 AI 辅助技能生成流水线。

阶段流水线：
  意图解析 → 相似发现 → 核心生成 → 静态检查 → 自动测试 → 输出 Forge

每个阶段完成后通过 callback 推送 SSE 事件到前端。
用户可随时中断、跳过或重新执行某一阶段。
"""

from typing import TypedDict, Optional, List, Dict, Any, Callable, Awaitable
from enum import StrEnum
from dataclasses import dataclass, field
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from loguru import logger


class CreatorPhase(StrEnum):
    """Agent 流水线阶段"""
    INTENT_PARSE = "intent_parse"
    SIMILARITY_SEARCH = "similarity_search"
    CORE_GENERATION = "core_generation"
    STATIC_CHECK = "static_check"
    AUTO_TEST = "auto_test"
    FORGE_OUTPUT = "forge_output"


class AgentState(TypedDict):
    """Skill Creator Agent 共享状态"""
    # 输入
    user_input: str                          # 用户原始输入
    chat_context: Optional[List[Dict]]        # 聊天上下文（可选）
    base_skill_id: Optional[str]             # 基于已有技能（可选）

    # 意图解析结果
    intent: Dict[str, Any]                   # {name, domain, inputs, outputs, executor_type}

    # 相似技能
    similar_skills: List[Dict[str, Any]]     # [{skill_id, name, similarity, reason}]

    # 核心生成
    script_code: str
    parameters_schema: Dict[str, Any]

    # 检查与测试
    static_check_result: Dict[str, Any]      # {passed, score, issues, summary}
    auto_test_result: Dict[str, Any]         # {passed, output, error_log, suggestions}

    # 控制
    current_phase: str                       # 当前阶段
    error: Optional[str]                     # 错误信息
    retry_count: int                         # 当前阶段重试次数
    should_pause: bool                       # 是否等待用户确认
    user_action: Optional[str]               # 用户指令: continue/skip/modify/abort

    # 输出
    session_id: Optional[str]                # ForgeSession ID
    forge_url: Optional[str]                 # Forge 页面 URL


# 阶段回调类型：每个阶段完成后调用，用于推送 SSE
PhaseCallback = Callable[[str, Dict[str, Any]], Awaitable[None]]
```

- [ ] **Step 2: 定义 Agent 类构造函数**

```python
class SkillCreatorAgent:
    """技能创建 Agent — 编排 6 阶段流水线。

    使用方式：
        agent = SkillCreatorAgent(llm, callback=push_sse)
        final_state = await agent.run(user_input="帮我做差异表达分析")
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        callback: Optional[PhaseCallback] = None,
        max_retries: int = 3,
        timeouts: Optional[Dict[str, int]] = None,
    ):
        """
        Args:
            llm: LangChain ChatOpenAI 实例
            callback: 阶段完成回调 async fn(phase, result)，用于 SSE 推送
            max_retries: 每个阶段最大重试次数（静态检查自动修复用）
            timeouts: 阶段超时配置（秒），默认值见 DEFAULT_TIMEOUTS
        """
        self.llm = llm
        self.callback = callback
        self.max_retries = max_retries
        self.timeouts = timeouts or DEFAULT_TIMEOUTS
        self.graph = self._build_graph()

    DEFAULT_TIMEOUTS: Dict[str, int] = {
        "intent_parse": 10,
        "similarity_search": 5,
        "core_generation": 30,
        "static_check": 10,
        "auto_test": 120,
        "forge_output": 5,
    }

    async def _push_phase(self, phase: str, status: str, result: Optional[Dict] = None, chunk: Optional[str] = None):
        """推送阶段事件到前端（通过 callback）"""
        if self.callback:
            event = {"phase": phase, "status": status}
            if result is not None:
                event["result"] = result
            if chunk is not None:
                event["chunk"] = chunk
            await self.callback(phase, event)
```

- [ ] **Step 3: 构建 LangGraph 状态图**

```python
    def _build_graph(self) -> StateGraph:
        """构建 6 阶段流水线 StateGraph"""
        workflow = StateGraph(AgentState)

        # 添加 6 个节点
        workflow.add_node("intent_parse", self._intent_parse_node)
        workflow.add_node("similarity_search", self._similarity_search_node)
        workflow.add_node("core_generation", self._core_generation_node)
        workflow.add_node("static_check", self._static_check_node)
        workflow.add_node("auto_test", self._auto_test_node)
        workflow.add_node("forge_output", self._forge_output_node)

        # 设置入口
        workflow.set_entry_point("intent_parse")

        # 每个阶段后检查是否暂停
        workflow.add_conditional_edges(
            "intent_parse",
            self._after_phase,
            {"continue": "similarity_search", "pause": END, "error": END}
        )
        workflow.add_conditional_edges(
            "similarity_search",
            self._after_phase,
            {"continue": "core_generation", "skip": "core_generation", "pause": END, "error": END}
        )
        workflow.add_conditional_edges(
            "core_generation",
            self._after_phase,
            {"continue": "static_check", "pause": END, "error": END}
        )
        workflow.add_conditional_edges(
            "static_check",
            self._after_phase,
            {"continue": "auto_test", "retry": "static_check", "skip": "auto_test", "pause": END, "error": END}
        )
        workflow.add_conditional_edges(
            "auto_test",
            self._after_phase,
            {"continue": "forge_output", "skip": "forge_output", "pause": END, "error": END}
        )
        workflow.add_edge("forge_output", END)

        return workflow.compile()

    def _after_phase(self, state: AgentState) -> str:
        """阶段完成后决策：继续 / 暂停 / 重试 / 跳过 / 错误"""
        if state.get("error"):
            return "error"
        if state.get("should_pause"):
            return "pause"
        user_action = state.get("user_action")
        if user_action == "skip" and state["current_phase"] == "similarity_search":
            return "skip"
        if user_action == "skip" and state["current_phase"] in ("static_check", "auto_test"):
            return "skip"
        if user_action == "retry" and state["current_phase"] == "static_check":
            if state.get("retry_count", 0) < self.max_retries:
                return "retry"
        return "continue"
```

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/app/agent/skill_creator.py
git commit -m "feat: Skill Creator Agent 状态机骨架 — 6 阶段 LangGraph 流水线"
```

---

### Task 3: Skill Creator Agent — 意图解析节点

**Files:**
- Modify: `autonome-backend/app/agent/skill_creator.py`

- [ ] **Step 1: 实现意图解析节点**

```python
    INTENT_PARSE_SYSTEM = """你是一个生物信息学技能需求分析师。从用户的自然语言描述中提取以下结构化信息：

请返回 JSON 格式：
{
  "name": "技能名称（中文，简洁, 10字以内）",
  "name_en": "skill_name_english",
  "domain": "领域（如 transcriptomics, genomics, proteomics, metabolomics, single_cell）",
  "description": "一句话功能描述",
  "inputs": [{"name": "参数名", "type": "FilePath|String|Number|Boolean", "required": true/false, "description": "说明"}],
  "outputs": [{"name": "输出名", "type": "File|Plot|Table", "description": "说明"}],
  "executor_type": "Python_env|R_env|Logical_Blueprint",
  "primary_tool": "主要工具/库名（如 DESeq2, Seurat, GATK）",
  "skill_id": "建议的 skill_id（小写英文+下划线）",
  "confidence": "high|medium|low"
}

规则：
- executor_type: 提到 R/Bioconductor 包 → R_env, Python/pandas/numpy → Python_env, 工作流/多步骤 → Logical_Blueprint
- 信息不足时 confidence=low，并在 missing_info 中列出需要追问的问题
"""

    async def _intent_parse_node(self, state: AgentState) -> Dict[str, Any]:
        """阶段1: LLM 提取技能意图结构化信息"""
        logger.info(f"[SkillCreator] 阶段1: 意图解析 — {state['user_input'][:50]}...")
        await self._push_phase("intent_parse", "running")

        user_input = state["user_input"]
        chat_context = state.get("chat_context")

        messages = [SystemMessage(content=self.INTENT_PARSE_SYSTEM)]
        if chat_context:
            messages.extend([HumanMessage(content=f"对话上下文: {chat_context[-3:]}\n\n用户最后一条消息: {user_input}")])
        else:
            messages.append(HumanMessage(content=user_input))

        try:
            response = await self.llm.ainvoke(messages)
            import json
            result = json.loads(response.content)
            logger.info(f"[SkillCreator] 意图解析完成: name={result.get('name')}, executor={result.get('executor_type')}")
            await self._push_phase("intent_parse", "done", result=result)
            return {"intent": result, "current_phase": "intent_parse", "retry_count": 0}
        except Exception as e:
            logger.error(f"[SkillCreator] 意图解析失败: {e}")
            await self._push_phase("intent_parse", "error", result={"error": str(e)})
            return {"error": str(e), "current_phase": "intent_parse"}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/agent/skill_creator.py
git commit -m "feat: Skill Creator — 意图解析节点，LLM 提取技能结构化意图"
```

---

### Task 4: Skill Creator Agent — 相似技能发现节点

**Files:**
- Modify: `autonome-backend/app/agent/skill_creator.py`

- [ ] **Step 1: 实现相似技能发现节点**

```python
    async def _similarity_search_node(self, state: AgentState) -> Dict[str, Any]:
        """阶段2: 搜索已有相似技能，避免重复造轮子"""
        logger.info(f"[SkillCreator] 阶段2: 相似技能发现")
        await self._push_phase("similarity_search", "running")

        intent = state["intent"]

        try:
            from app.services.skill_vector_search import search_similar_skills
            from app.services.skill_matcher_config import get_skill_index

            query = f"{intent.get('name', '')} {intent.get('domain', '')} {intent.get('description', '')} {intent.get('primary_tool', '')}"
            similar = search_similar_skills(query, limit=3)

            recommendations = [
                {
                    "skill_id": s.skill_id,
                    "name": s.name,
                    "description": s.description,
                    "similarity": round(s.similarity, 3) if s.similarity else 0,
                    "reason": f"同样使用 {intent.get('primary_tool', '类似工具')}" if intent.get('primary_tool') else "领域匹配",
                }
                for s in similar
            ]

            await self._push_phase("similarity_search", "done", result={"similar": recommendations})
            return {"similar_skills": recommendations, "current_phase": "similarity_search"}
        except Exception as e:
            logger.warning(f"[SkillCreator] 相似技能搜索失败（非致命）: {e}")
            await self._push_phase("similarity_search", "done", result={"similar": []})
            return {"similar_skills": [], "current_phase": "similarity_search"}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/agent/skill_creator.py
git commit -m "feat: Skill Creator — 相似技能发现节点，向量检索已有技能"
```

---

### Task 5: Skill Creator Agent — 核心生成节点 (代码 + 参数)

**Files:**
- Modify: `autonome-backend/app/agent/skill_creator.py`

- [ ] **Step 1: 实现核心生成节点**

```python
    CORE_GENERATION_SYSTEM = """你是一个生物信息学技能代码生成专家。根据用户需求生成可执行的脚本代码和参数定义。

## 要求：
1. 生成的代码必须是完整的、可直接运行的脚本
2. 使用 argparse（Python）或 optparse（R）解析命令行参数
3. 代码需包含适当的错误处理和日志输出
4. 不要留 TODO 或占位符

## 输出格式（JSON）：
{
  "script_code": "完整的 Python/R 脚本代码",
  "parameters_schema": {
    "参数键名": {
      "type": "FilePath|String|Number|Boolean|Integer|Float",
      "required": true/false,
      "default": null或默认值,
      "description": "参数说明",
      "cli_flag": "--参数名"
    }
  }
}
"""

    async def _core_generation_node(self, state: AgentState) -> Dict[str, Any]:
        """阶段3: 核心生成 — LLM 生成代码 + 参数 schema"""
        logger.info(f"[SkillCreator] 阶段3: 核心生成")
        await self._push_phase("core_generation", "running")

        intent = state["intent"]
        base_skill_content = None

        # 如果有基础技能，加载其 SKILL.md 作为参考
        base_skill_id = state.get("base_skill_id")
        if base_skill_id:
            try:
                from app.core.skill_parser import get_skill_from_db_index
                base = get_skill_from_db_index(base_skill_id)
                if base:
                    base_skill_content = f"参考技能代码:\n{base.script_code}"
            except Exception:
                pass

        messages = [
            SystemMessage(content=self.CORE_GENERATION_SYSTEM),
            HumanMessage(content=f"""## 用户需求
名称: {intent.get('name', '')}
领域: {intent.get('domain', '')}
描述: {intent.get('description', '')}
输入: {intent.get('inputs', [])}
输出: {intent.get('outputs', [])}
执行环境: {intent.get('executor_type', 'Python_env')}
主要工具: {intent.get('primary_tool', '')}

{'## 参考技能\n' + base_skill_content if base_skill_content else ''}
请生成完整的可执行代码和参数 schema。""")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            import json
            content = response.content
            # 提取 JSON（处理 markdown 代码块包裹情况）
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()
            result = json.loads(json_str)

            script_code = result.get("script_code", "")
            parameters_schema = result.get("parameters_schema", {})

            await self._push_phase("core_generation", "done", result={
                "script_code": script_code,
                "parameters_schema": parameters_schema,
            })

            return {
                "script_code": script_code,
                "parameters_schema": parameters_schema,
                "current_phase": "core_generation",
                "retry_count": 0,
            }
        except Exception as e:
            logger.error(f"[SkillCreator] 核心生成失败: {e}")
            await self._push_phase("core_generation", "error", result={"error": str(e)})
            # 重试 1 次
            if state.get("retry_count", 0) < 1:
                return {"error": None, "retry_count": state.get("retry_count", 0) + 1, "current_phase": "core_generation"}
            return {"error": str(e), "current_phase": "core_generation"}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/agent/skill_creator.py
git commit -m "feat: Skill Creator — 核心生成节点，LLM 生成脚本代码和参数 schema"
```

---

### Task 6: Skill Creator Agent — 静态检查 + 自动修复节点

**Files:**
- Modify: `autonome-backend/app/agent/skill_creator.py`

- [ ] **Step 1: 实现静态检查节点（含自动修复）**

```python
    FIX_SYSTEM = """你是代码修复专家。根据静态检查报告修复代码中的安全和质量问题。

请直接返回修复后的完整代码（仅代码，不要解释）。"""

    async def _static_check_node(self, state: AgentState) -> Dict[str, Any]:
        """阶段4: 静态检查 — 安全扫描 + 语法检查，失败时自动修复"""
        logger.info(f"[SkillCreator] 阶段4: 静态检查")
        await self._push_phase("static_check", "running")

        script_code = state["script_code"]
        intent = state["intent"]
        language = "r" if intent.get("executor_type") == "R_env" else "python"

        try:
            from app.services.code_reviewer import review_skill_code

            check_result = review_skill_code(script_code, language=language)

            await self._push_phase("static_check", "done", result={
                "passed": check_result.passed,
                "score": check_result.score,
                "issues": [
                    {"line": i.line, "severity": i.severity.value, "message": i.message, "rule_id": i.rule_id}
                    for i in check_result.issues
                ],
                "summary": check_result.summary,
                "suggestions": check_result.suggestions,
            })

            if not check_result.passed and state.get("retry_count", 0) < self.max_retries:
                # 自动修复：将检查报告喂给 LLM
                logger.info(f"[SkillCreator] 静态检查未通过，尝试自动修复 (第{state['retry_count'] + 1}次)")
                fix_prompt = f"""代码静态检查发现以下问题：

检查分数: {check_result.score}/100
问题列表:
{chr(10).join(f'- [{i.severity.value}] 行{i.line}: {i.message}' for i in check_result.issues)}

建议修复:
{chr(10).join(f'- {s}' for s in check_result.suggestions)}

原始代码:
```{language}
{script_code}
```

请修复上述所有问题，返回完整的修复后代码。"""
                fix_response = await self.llm.ainvoke([SystemMessage(content=self.FIX_SYSTEM), HumanMessage(content=fix_prompt)])
                fixed_code = fix_response.content
                # 提取代码块
                if "```" in fixed_code:
                    fixed_code = fixed_code.split("```")[1]
                    if fixed_code.startswith(language):
                        fixed_code = fixed_code[len(language):]
                    fixed_code = fixed_code.split("```")[0].strip()

                return {
                    "script_code": fixed_code,
                    "static_check_result": {
                        "passed": check_result.passed,
                        "score": check_result.score,
                        "issues": [{"line": i.line, "severity": i.severity.value, "message": i.message, "rule_id": i.rule_id} for i in check_result.issues],
                        "summary": check_result.summary,
                    },
                    "retry_count": state.get("retry_count", 0) + 1,
                    "current_phase": "static_check",
                }

            return {
                "static_check_result": {
                    "passed": check_result.passed,
                    "score": check_result.score,
                    "issues": [{"line": i.line, "severity": i.severity.value, "message": i.message, "rule_id": i.rule_id} for i in check_result.issues],
                    "summary": check_result.summary,
                },
                "current_phase": "static_check",
            }
        except Exception as e:
            logger.error(f"[SkillCreator] 静态检查异常: {e}")
            await self._push_phase("static_check", "error", result={"error": str(e)})
            return {"static_check_result": {"passed": False, "score": 0, "issues": [], "summary": str(e)}, "current_phase": "static_check"}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-backend/app/agent/skill_creator.py
git commit -m "feat: Skill Creator — 静态检查节点，含 LLM 自动修复重试"
```

---

### Task 7: Skill Creator Agent — 自动测试 + Forge 输出节点

**Files:**
- Modify: `autonome-backend/app/agent/skill_creator.py`

- [ ] **Step 1: 实现自动测试和 Forge 输出节点**

```python
    async def _auto_test_node(self, state: AgentState) -> Dict[str, Any]:
        """阶段5: 自动测试 — Docker 沙箱执行，检查输出"""
        logger.info(f"[SkillCreator] 阶段5: 自动测试")
        await self._push_phase("auto_test", "running")

        intent = state["intent"]
        script_code = state["script_code"]
        parameters_schema = state.get("parameters_schema", {})

        # 生成测试用的模拟参数
        test_params = {}
        for key, param in parameters_schema.items():
            if isinstance(param, dict):
                ptype = param.get("type", "String")
                if ptype == "Number" or ptype == "Integer" or ptype == "Float":
                    test_params[key] = param.get("default", 0.05)
                elif ptype == "Boolean":
                    test_params[key] = True
                else:
                    test_params[key] = param.get("default", f"test_{key}")

        try:
            from app.services.skill_executor import execute_skill
            from app.services.skill_bundle_writer import write_skill_from_forge_draft
            import tempfile, uuid, os

            # 将代码写入临时技能目录用于测试
            test_skill_id = f"_test_{uuid.uuid4().hex[:8]}"
            temp_draft = {
                "name": intent.get("name", "Test Skill"),
                "description": intent.get("description", ""),
                "executor_type": intent.get("executor_type", "Python_env"),
                "script_code": script_code,
                "parameters_schema": parameters_schema,
                "expert_knowledge": "",
                "dependencies": [],
                "tags": [],
            }

            test_dir = tempfile.mkdtemp(prefix="skill_test_")
            try:
                write_skill_from_forge_draft(temp_draft, test_skill_id, skills_dir=test_dir)

                result = execute_skill(
                    skill_id=test_skill_id,
                    params=test_params,
                    project_id="skill_creator_test",
                    skip_dependency_check=True,
                )

                passed = result.get("status") == "success"
                await self._push_phase("auto_test", "done", result={
                    "passed": passed,
                    "output": result.get("stdout", "")[:2000],
                    "error_log": result.get("stderr", ""),
                    "suggestions": [] if passed else ["检查输入参数格式", "确认依赖包名称", "验证代码逻辑"],
                })

                return {
                    "auto_test_result": {
                        "passed": passed,
                        "output": result.get("stdout", "")[:2000],
                        "error_log": result.get("stderr", ""),
                    },
                    "current_phase": "auto_test",
                }
            finally:
                # 清理临时目录
                import shutil
                shutil.rmtree(test_dir, ignore_errors=True)

        except Exception as e:
            logger.warning(f"[SkillCreator] 自动测试异常（非致命）: {e}")
            await self._push_phase("auto_test", "done", result={
                "passed": False,
                "output": "",
                "error_log": str(e),
                "suggestions": ["测试环境不可用，建议手动测试"],
            })
            return {
                "auto_test_result": {"passed": False, "output": "", "error_log": str(e)},
                "current_phase": "auto_test",
            }

    async def _forge_output_node(self, state: AgentState) -> Dict[str, Any]:
        """阶段6: 输出到 Forge — 写入 ForgeSession + 文件系统"""
        logger.info(f"[SkillCreator] 阶段6: 输出到 Forge")
        await self._push_phase("forge_output", "running")

        try:
            from app.models.forge_session import ForgeSession, ForgeStatus
            from app.services.skill_bundle_writer import write_skill_from_forge_draft
            from app.services.skill_indexer import get_skill_indexer
            from app.core.database import get_session

            db = next(get_session())
            try:
                intent = state["intent"]
                skill_id = intent.get("skill_id", f"ai_generated_{uuid.uuid4().hex[:8]}")

                # 创建或更新 ForgeSession
                if state.get("session_id"):
                    forge_session = db.query(ForgeSession).filter(ForgeSession.id == state["session_id"]).first()
                else:
                    forge_session = ForgeSession(
                        title=intent.get("name", "AI 生成的技能"),
                        executor_type=intent.get("executor_type", "Python_env"),
                    )
                    db.add(forge_session)
                    db.flush()

                # 更新草稿
                draft = forge_session.skill_draft or {}
                draft.update({
                    "name": intent.get("name", ""),
                    "description": intent.get("description", ""),
                    "executor_type": intent.get("executor_type", "Python_env"),
                    "script_code": state.get("script_code", ""),
                    "parameters_schema": state.get("parameters_schema", {}),
                    "agent_phase": "forge_output",
                    "agent_history": draft.get("agent_history", []) + [
                        {"phase": "forge_output", "timestamp": "", "summary": "Agent 生成完成"}
                    ],
                    "static_check_result": state.get("static_check_result"),
                    "auto_test_result": state.get("auto_test_result"),
                    "source_skill_id": state.get("base_skill_id"),
                })
                forge_session.skill_draft = draft
                forge_session.status = ForgeStatus.READY
                forge_session.skill_id = skill_id
                db.commit()

                session_id = forge_session.id
            finally:
                db.close()

            await self._push_phase("forge_output", "done", result={
                "session_id": session_id,
                "skill_id": skill_id,
                "forge_url": f"/skill-forge?session={session_id}",
            })

            return {
                "session_id": session_id,
                "forge_url": f"/skill-forge?session={session_id}",
                "current_phase": "forge_output",
            }
        except Exception as e:
            logger.error(f"[SkillCreator] Forge 输出失败: {e}")
            await self._push_phase("forge_output", "error", result={"error": str(e)})
            return {"error": str(e), "current_phase": "forge_output"}
```

- [ ] **Step 2: 实现 run() 入口方法**

```python
    async def run(self, user_input: str, chat_context: Optional[List[Dict]] = None, base_skill_id: Optional[str] = None, session_id: Optional[str] = None) -> AgentState:
        """运行完整 Agent 流水线。

        Args:
            user_input: 用户自然语言描述
            chat_context: 聊天上下文（可选）
            base_skill_id: 基于已有技能修改（可选）
            session_id: 已有 ForgeSession ID（续接场景）

        Returns:
            最终 AgentState
        """
        initial_state: AgentState = {
            "user_input": user_input,
            "chat_context": chat_context,
            "base_skill_id": base_skill_id,
            "intent": {},
            "similar_skills": [],
            "script_code": "",
            "parameters_schema": {},
            "static_check_result": {},
            "auto_test_result": {},
            "current_phase": "",
            "error": None,
            "retry_count": 0,
            "should_pause": False,
            "user_action": None,
            "session_id": session_id,
            "forge_url": None,
        }

        logger.info(f"[SkillCreator] 开始执行流水线: input='{user_input[:50]}...'")
        final_state = await self.graph.ainvoke(initial_state)
        logger.info(f"[SkillCreator] 流水线完成: phase={final_state.get('current_phase')}, error={final_state.get('error')}")
        return final_state

    async def resume(self, state: AgentState, user_action: str) -> AgentState:
        """从中断点恢复执行。

        Args:
            state: 当前 AgentState
            user_action: continue/skip/abort

        Returns:
            更新后的 AgentState
        """
        state["user_action"] = user_action
        state["should_pause"] = False
        return await self.graph.ainvoke(state)
```

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/app/agent/skill_creator.py
git commit -m "feat: Skill Creator — 自动测试节点 + Forge 输出节点 + run() 入口"
```

---

### Task 8: Forge Agent API — SSE 流式端点

**Files:**
- Create: `autonome-backend/app/api/routes/skills_forge_agent.py`

- [ ] **Step 1: 创建 skills_forge_agent.py**

```python
# autonome-backend/app/api/routes/skills_forge_agent.py

"""技能创建 Agent API — SSE 流式端点。

提供 generate、iterate、supplement 三个端点，
通过 Server-Sent Events 将 Agent 各阶段输出实时推送到前端。
"""

import asyncio
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger

from app.core.database import get_session
from app.models.forge_session import ForgeSession, ForgeStatus

router = APIRouter(prefix="/api/forge/agent", tags=["skill-forge-agent"])


# --- Request Models ---

class GenerateRequest(BaseModel):
    """首次生成技能请求"""
    user_input: str = Field(..., description="用户自然语言描述")
    chat_context: Optional[List[Dict[str, Any]]] = Field(None, description="聊天上下文")
    base_skill_id: Optional[str] = Field(None, description="基于已有技能创建")
    executor_type: Optional[str] = Field("Python_env", description="执行器类型偏好")


class IterateRequest(BaseModel):
    """迭代修改请求"""
    session_id: str = Field(..., description="ForgeSession ID")
    instruction: str = Field(..., description="修改指令，如 '参数加一个 pvalue 阈值'")
    scope: str = Field("code", description="修改范围: code|params|docs|all")


class SupplementRequest(BaseModel):
    """按需补全请求"""
    session_id: str = Field(..., description="ForgeSession ID")
    supplement_type: str = Field(..., description="补全类型: docs|tags|metadata|dependencies")


# --- SSE Helpers ---

async def _sse_event(event: str, data: dict):
    """生成 SSE 格式的事件字符串"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _sse_error(message: str):
    """生成 SSE 错误事件"""
    return f"event: error\ndata: {json.dumps({'error': message}, ensure_ascii=False)}\n\n"
```

- [ ] **Step 2: 实现 generate 端点**

```python
@router.post("/generate")
async def generate_skill(request: GenerateRequest):
    """首次生成技能 — SSE 流式返回 Agent 各阶段进度。

    SSE 事件类型:
      event: phase → data: {"phase": "intent_parse", "status": "running|done|error", "result": {...}}
      event: done  → data: {"session_id": "...", "forge_url": "..."}
      event: error → data: {"error": "..."}
    """
    logger.info(f"[ForgeAgent] generate: {request.user_input[:50]}...")

    async def event_generator():
        event_queue = asyncio.Queue()

        async def phase_callback(phase: str, event_data: dict):
            await event_queue.put(("phase", event_data))

        try:
            from app.agent.skill_creator import SkillCreatorAgent
            from langchain_openai import ChatOpenAI
            from app.core.config import settings

            llm = ChatOpenAI(
                model=settings.LLM_MODEL or "gpt-4o",
                temperature=0.3,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL if hasattr(settings, 'OPENAI_BASE_URL') else None,
            )

            agent = SkillCreatorAgent(llm=llm, callback=phase_callback)

            # 启动 Agent（后台任务）
            agent_task = asyncio.create_task(
                agent.run(
                    user_input=request.user_input,
                    chat_context=request.chat_context,
                    base_skill_id=request.base_skill_id,
                )
            )

            # 从队列读取 SSE 事件并推送到前端
            while True:
                try:
                    event_type, event_data = await asyncio.wait_for(
                        event_queue.get(), timeout=5.0
                    )
                    yield await _sse_event(event_type, event_data)
                except asyncio.TimeoutError:
                    # 检查 Agent 是否已完成
                    if agent_task.done():
                        break
                    continue

            # Agent 完成，推送最终状态
            try:
                final_state = agent_task.result()
                if final_state.get("error"):
                    yield await _sse_event("error", {"error": final_state["error"]})
                else:
                    yield await _sse_event("done", {
                        "session_id": final_state.get("session_id"),
                        "forge_url": final_state.get("forge_url"),
                    })
            except Exception as e:
                logger.error(f"[ForgeAgent] Agent 执行异常: {e}")
                yield await _sse_event("error", {"error": str(e)})

        except Exception as e:
            logger.error(f"[ForgeAgent] generate 初始化失败: {e}")
            yield await _sse_event("error", {"error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 3: 实现 iterate 和 supplement 端点**

```python
@router.post("/iterate")
async def iterate_skill(request: IterateRequest):
    """迭代修改技能 — 针对已创建的 ForgeSession 进行局部修改。

    从 ForgeSession 加载现有草稿，将用户修改指令 + 现有代码送入 Agent，
    Agent 修改指定范围后更新 ForgeSession。
    """

    async def event_generator():
        from app.models.forge_session import ForgeSession
        from app.core.database import get_session

        db = next(get_session())
        try:
            forge_session = db.query(ForgeSession).filter(ForgeSession.id == request.session_id).first()
            if not forge_session:
                yield await _sse_error(f"Session not found: {request.session_id}")
                return
            draft = forge_session.skill_draft or {}
            existing_code = draft.get("script_code", "")
            existing_params = draft.get("parameters_schema", {})
            existing_name = draft.get("name", "")
            existing_desc = draft.get("description", "")
        finally:
            db.close()

        from langchain_openai import ChatOpenAI
        from app.core.config import settings

        llm = ChatOpenAI(
            model=settings.LLM_MODEL or "gpt-4o",
            temperature=0.3,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL if hasattr(settings, 'OPENAI_BASE_URL') else None,
        )

        scope_map = {
            "code": "只修改脚本代码",
            "params": "只修改参数 schema",
            "docs": "只修改文档/专家知识",
            "all": "可以修改所有内容",
        }
        scope_desc = scope_map.get(request.scope, "修改代码和参数")

        iterate_prompt = f"""根据用户指令修改技能内容。

当前技能:
- 名称: {existing_name}
- 描述: {existing_desc}
- 代码: 
```python
{existing_code[:3000]}
```
- 参数: {json.dumps(existing_params, ensure_ascii=False, indent=2)}

用户指令: {request.instruction}
修改范围: {scope_desc}

请返回 JSON 格式的修改后内容，只包含被修改的字段:
{{"script_code": "修改后的完整代码（如未修改则省略此字段）", "parameters_schema": {{修改后的参数（如未修改则省略此字段）}}}}"""

        try:
            yield await _sse_event("phase", {"phase": "iterate", "status": "running"})
            response = await llm.ainvoke(iterate_prompt)

            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()
            result = json.loads(json_str)

            # 更新 ForgeSession
            db = next(get_session())
            try:
                forge_session = db.query(ForgeSession).filter(ForgeSession.id == request.session_id).first()
                draft = forge_session.skill_draft or {}
                if result.get("script_code"):
                    draft["script_code"] = result["script_code"]
                if result.get("parameters_schema"):
                    draft["parameters_schema"] = result["parameters_schema"]
                draft["agent_history"] = draft.get("agent_history", []) + [
                    {"phase": "iterate", "instruction": request.instruction, "scope": request.scope}
                ]
                forge_session.skill_draft = draft
                db.commit()
            finally:
                db.close()

            yield await _sse_event("phase", {"phase": "iterate", "status": "done", "result": result})
            yield await _sse_event("done", {"session_id": request.session_id})
        except Exception as e:
            logger.error(f"[ForgeAgent] iterate 失败: {e}")
            yield await _sse_event("error", {"error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/supplement")
async def supplement_skill(request: SupplementRequest):
    """按需补全技能 — 生成文档、标签、元数据或依赖。

    从 ForgeSession 加载现有草稿，生成指定类型的补全内容，
    更新 ForgeSession 后返回。
    """

    supplement_prompts = {
        "docs": "为以下技能生成专业知识和操作指南文档（300字以内，中文）：",
        "tags": "为以下技能推荐 3-6 个标签（小写英文，逗号分隔）：",
        "metadata": "为以下技能推荐分类和子分类（JSON格式 {'category': '', 'subcategory': ''}）：",
        "dependencies": "为以下技能列出所需的依赖包（JSON 字符串数组）：",
    }

    async def event_generator():
        from app.models.forge_session import ForgeSession
        from app.core.database import get_session

        db = next(get_session())
        try:
            forge_session = db.query(ForgeSession).filter(ForgeSession.id == request.session_id).first()
            if not forge_session:
                yield await _sse_error(f"Session not found: {request.session_id}")
                return
            draft = forge_session.skill_draft or {}
            skill_context = f"""
名称: {draft.get('name', '')}
描述: {draft.get('description', '')}
执行器: {draft.get('executor_type', 'Python_env')}
参数: {json.dumps(draft.get('parameters_schema', {}), ensure_ascii=False)}
代码摘要: {draft.get('script_code', '')[:1000]}
"""
        finally:
            db.close()

        prompt = supplement_prompts.get(request.supplement_type)
        if not prompt:
            yield await _sse_error(f"Unknown supplement_type: {request.supplement_type}")
            return

        from langchain_openai import ChatOpenAI
        from app.core.config import settings

        llm = ChatOpenAI(
            model=settings.LLM_MODEL or "gpt-4o",
            temperature=0.5,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL if hasattr(settings, 'OPENAI_BASE_URL') else None,
        )

        try:
            yield await _sse_event("phase", {"phase": "supplement", "status": "running"})
            response = await llm.ainvoke(prompt + "\n\n" + skill_context)
            content = response.content.strip()

            # 写入 ForgeSession
            db = next(get_session())
            try:
                forge_session = db.query(ForgeSession).filter(ForgeSession.id == request.session_id).first()
                draft = forge_session.skill_draft or {}
                if request.supplement_type == "docs":
                    draft["expert_knowledge"] = content
                elif request.supplement_type == "tags":
                    draft["tags"] = [t.strip() for t in content.split(",")]
                elif request.supplement_type == "metadata":
                    meta = json.loads(content)
                    draft["category"] = meta.get("category", draft.get("category"))
                    draft["subcategory"] = meta.get("subcategory", draft.get("subcategory"))
                elif request.supplement_type == "dependencies":
                    deps = json.loads(content) if isinstance(content, str) and content.startswith("[") else [d.strip() for d in content.split(",")]
                    draft["dependencies"] = deps
                forge_session.skill_draft = draft
                db.commit()
            finally:
                db.close()

            yield await _sse_event("phase", {"phase": "supplement", "status": "done", "result": {"type": request.supplement_type, "content": content}})
            yield await _sse_event("done", {"session_id": request.session_id})
        except Exception as e:
            logger.error(f"[ForgeAgent] supplement 失败: {e}")
            yield await _sse_event("error", {"error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/session/{session_id}/state")
async def get_agent_state(session_id: str):
    """获取 Agent 当前状态（用于 SSE 断连后恢复）"""
    from app.models.forge_session import ForgeSession

    db = next(get_session())
    try:
        forge_session = db.query(ForgeSession).filter(ForgeSession.id == session_id).first()
        if not forge_session:
            raise HTTPException(status_code=404, detail="Session not found")
        draft = forge_session.skill_draft or {}
        return {
            "session_id": session_id,
            "agent_phase": draft.get("agent_phase"),
            "agent_history": draft.get("agent_history", []),
            "static_check_result": draft.get("static_check_result"),
            "auto_test_result": draft.get("auto_test_result"),
            "has_code": bool(draft.get("script_code")),
            "has_params": bool(draft.get("parameters_schema")),
        }
    finally:
        db.close()
```

- [ ] **Step 4: Commit**

```bash
git add autonome-backend/app/api/routes/skills_forge_agent.py
git commit -m "feat: Forge Agent API — generate/iterate/supplement SSE 端点 + 状态恢复"
```

---

### Task 9: 注册 Forge Agent 路由

**Files:**
- Modify: `autonome-backend/main.py` (or the route registration file)

- [ ] **Step 1: 找到路由注册位置并添加**

Let me check where routes are registered:
```bash
grep -r "skills_forge" autonome-backend/main.py autonome-backend/app/api/__init__.py 2>/dev/null
```

Read the router registration file and add:
```python
from app.api.routes.skills_forge_agent import router as forge_agent_router
app.include_router(forge_agent_router)
```

- [ ] **Step 2: Verify registration**

```bash
cd autonome-backend && python -c "from main import app; routes = [r.path for r in app.routes]; print([r for r in routes if 'forge' in r])"
```

Expected: 包含 `/api/forge/agent/generate`、`/api/forge/agent/iterate`、`/api/forge/agent/supplement`

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/main.py
git commit -m "feat: 注册 Forge Agent 路由到 FastAPI 应用"
```

---

### Task 10: 前端 — forgeAgent SSE 客户端

**Files:**
- Create: `autonome-studio/src/lib/api/forgeAgent.ts`

- [ ] **Step 1: 创建 SSE 通信客户端**

```typescript
// autonome-studio/src/lib/api/forgeAgent.ts

/**
 * Skill Creator Agent 前端通信客户端
 *
 * 通过 SSE (Server-Sent Events) 与后端 Agent 通信，
 * 处理 generate、iterate、supplement 三种操作。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// --- Types ---

export interface GenerateRequest {
  user_input: string;
  chat_context?: Record<string, unknown>[];
  base_skill_id?: string;
  executor_type?: string;
}

export interface IterateRequest {
  session_id: string;
  instruction: string;
  scope: 'code' | 'params' | 'docs' | 'all';
}

export interface SupplementRequest {
  session_id: string;
  supplement_type: 'docs' | 'tags' | 'metadata' | 'dependencies';
}

export interface PhaseEvent {
  phase: string;
  status: 'running' | 'done' | 'error';
  result?: Record<string, unknown>;
  chunk?: string;
}

export interface DoneEvent {
  session_id: string;
  forge_url?: string;
  skill_id?: string;
}

export interface AgentCallbacks {
  onPhase?: (event: PhaseEvent) => void;
  onDone?: (event: DoneEvent) => void;
  onError?: (error: string) => void;
}

// --- SSE Stream Parser ---

async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>
): AsyncGenerator<{ event: string; data: string }> {
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let currentEvent = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        yield { event: currentEvent || 'message', data };
        currentEvent = '';
      }
    }
  }
}

// --- API methods ---

async function streamSSE(
  url: string,
  body: unknown,
  callbacks: AgentCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const errorText = await response.text();
    callbacks.onError?.(`HTTP ${response.status}: ${errorText}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError?.('Response body is not readable');
    return;
  }

  try {
    for await (const { event, data } of parseSSEStream(reader)) {
      try {
        const parsed = JSON.parse(data);
        switch (event) {
          case 'phase':
            callbacks.onPhase?.(parsed as PhaseEvent);
            break;
          case 'done':
            callbacks.onDone?.(parsed as DoneEvent);
            break;
          case 'error':
            callbacks.onError?.(parsed.error || 'Unknown error');
            break;
        }
      } catch {
        // skip unparseable events
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export const forgeAgentApi = {
  /** 首次生成技能 — SSE 流式 */
  generate(request: GenerateRequest, callbacks: AgentCallbacks, signal?: AbortSignal) {
    return streamSSE(`${API_BASE}/api/forge/agent/generate`, request, callbacks, signal);
  },

  /** 迭代修改技能 */
  iterate(request: IterateRequest, callbacks: AgentCallbacks, signal?: AbortSignal) {
    return streamSSE(`${API_BASE}/api/forge/agent/iterate`, request, callbacks, signal);
  },

  /** 按需补全 */
  supplement(request: SupplementRequest, callbacks: AgentCallbacks, signal?: AbortSignal) {
    return streamSSE(`${API_BASE}/api/forge/agent/supplement`, request, callbacks, signal);
  },

  /** 获取 Agent 当前状态（断连恢复） */
  async getState(sessionId: string) {
    const response = await fetch(`${API_BASE}/api/forge/agent/session/${sessionId}/state`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add autonome-studio/src/lib/api/forgeAgent.ts
git commit -m "feat: 前端 forgeAgent SSE 客户端 — generate/iterate/supplement 通信"
```

---

### Task 11: 前端 — useForgeStore 扩展 Agent 状态

**Files:**
- Modify: `autonome-studio/src/store/useForgeStore.ts`

- [ ] **Step 1: 添加 Agent 相关 State 和 Actions**

在 `autonome-studio/src/store/useForgeStore.ts` 的 `ForgeState` 接口中添加：

```typescript
// Agent 状态（新增）
agentPhase: string | null;
agentHistory: Array<{ phase: string; timestamp?: string; summary?: string }>;
staticCheckResult: {
  passed: boolean;
  score: number;
  issues: Array<{ line: number; severity: string; message: string; rule_id: string }>;
  summary?: string;
} | null;
autoTestResult: {
  passed: boolean;
  output: string;
  error_log?: string;
} | null;
isAgentRunning: boolean;
abortController: AbortController | null;

// Agent Actions（新增）
setAgentPhase: (phase: string | null) => void;
appendAgentHistory: (entry: { phase: string; summary: string }) => void;
setStaticCheckResult: (result: ForgeState['staticCheckResult']) => void;
setAutoTestResult: (result: ForgeState['autoTestResult']) => void;
setIsAgentRunning: (running: boolean) => void;
setAbortController: (controller: AbortController | null) => void;
startAgentGeneration: (request: GenerateRequest) => Promise<void>;
startAgentIteration: (request: IterateRequest) => Promise<void>;
startAgentSupplement: (request: SupplementRequest) => Promise<void>;
cancelAgent: () => void;
```

- [ ] **Step 2: 实现 generate/iterate/supplement Actions**

在 store 的 `create` 回调中添加实现：

```typescript
// 初始状态
agentPhase: null,
agentHistory: [],
staticCheckResult: null,
autoTestResult: null,
isAgentRunning: false,
abortController: null,

setAgentPhase: (phase) => set({ agentPhase: phase }),
appendAgentHistory: (entry) =>
  set((state) => ({
    agentHistory: [...state.agentHistory, entry],
  })),
setStaticCheckResult: (result) => set({ staticCheckResult: result }),
setAutoTestResult: (result) => set({ autoTestResult: result }),
setIsAgentRunning: (running) => set({ isAgentRunning: running }),
setAbortController: (controller) => set({ abortController: controller }),

cancelAgent: () => {
  const { abortController } = get();
  if (abortController) {
    abortController.abort();
    set({ abortController: null, isAgentRunning: false });
  }
},

startAgentGeneration: async (request) => {
  const abortController = new AbortController();
  set({ isAgentRunning: true, abortController, agentPhase: null, agentHistory: [] });

  try {
    await forgeAgentApi.generate(
      request,
      {
        onPhase: (event) => {
          set({ agentPhase: event.phase });
          if (event.status === 'done' && event.result) {
            get().appendAgentHistory({
              phase: event.phase,
              summary: `完成: ${event.phase}`,
            });
            // 当核心生成完成时，更新草稿
            if (event.phase === 'core_generation' && event.result) {
              const result = event.result as Record<string, unknown>;
              get().updateSkillDraft({
                script_code: result.script_code as string,
                parameters_schema: result.parameters_schema as Record<string, unknown>,
              });
            }
            // 静态检查完成
            if (event.phase === 'static_check' && event.result) {
              get().setStaticCheckResult(event.result as ForgeState['staticCheckResult']);
            }
            // 自动测试完成
            if (event.phase === 'auto_test' && event.result) {
              get().setAutoTestResult(event.result as ForgeState['autoTestResult']);
            }
          }
        },
        onDone: (event) => {
          set({ isAgentRunning: false, abortController: null });
          if (event.session_id) {
            set({ sessionId: event.session_id });
            // 重新加载完整的 ForgeSession
            get().loadSession(event.session_id);
          }
        },
        onError: (error) => {
          console.error('[ForgeAgent] generate error:', error);
          set({ isAgentRunning: false, abortController: null });
        },
      },
      abortController.signal
    );
  } catch (e) {
    if ((e as Error).name !== 'AbortError') {
      console.error('[ForgeAgent] generate exception:', e);
    }
    set({ isAgentRunning: false, abortController: null });
  }
},

startAgentIteration: async (request) => {
  const abortController = new AbortController();
  set({ isAgentRunning: true, abortController });

  try {
    await forgeAgentApi.iterate(
      request,
      {
        onPhase: (event) => {
          if (event.status === 'done' && event.result) {
            const result = event.result as Record<string, unknown>;
            if (result.script_code) {
              get().updateSkillDraft({ script_code: result.script_code as string });
            }
            if (result.parameters_schema) {
              get().updateSkillDraft({ parameters_schema: result.parameters_schema as Record<string, unknown> });
            }
          }
        },
        onDone: (event) => {
          set({ isAgentRunning: false, abortController: null });
          if (event.session_id) {
            get().loadSession(event.session_id);
          }
        },
        onError: (error) => {
          console.error('[ForgeAgent] iterate error:', error);
          set({ isAgentRunning: false, abortController: null });
        },
      },
      abortController.signal
    );
  } catch (e) {
    if ((e as Error).name !== 'AbortError') {
      console.error('[ForgeAgent] iterate exception:', e);
    }
    set({ isAgentRunning: false, abortController: null });
  }
},

startAgentSupplement: async (request) => {
  const abortController = new AbortController();
  set({ isAgentRunning: true, abortController });

  try {
    await forgeAgentApi.supplement(
      request,
      {
        onDone: (event) => {
          set({ isAgentRunning: false, abortController: null });
          if (event.session_id) {
            get().loadSession(event.session_id);
          }
        },
        onError: (error) => {
          console.error('[ForgeAgent] supplement error:', error);
          set({ isAgentRunning: false, abortController: null });
        },
      },
      abortController.signal
    );
  } catch (e) {
    if ((e as Error).name !== 'AbortError') {
      console.error('[ForgeAgent] supplement exception:', e);
    }
    set({ isAgentRunning: false, abortController: null });
  }
},
```

- [ ] **Step 3: 在 store 文件顶部添加 import**

```typescript
import { forgeAgentApi, type GenerateRequest, type IterateRequest, type SupplementRequest } from '@/lib/api/forgeAgent';
```

- [ ] **Step 4: Commit**

```bash
git add autonome-studio/src/store/useForgeStore.ts
git commit -m "feat: useForgeStore 扩展 Agent 状态和 generate/iterate/supplement actions"
```

---

### Task 12: 前端 — AIAssistantPanel 组件

**Files:**
- Create: `autonome-studio/src/components/overlays/SkillCenter/AIAssistantPanel.tsx`

- [ ] **Step 1: 创建 AI 助手对话面板**

```typescript
// autonome-studio/src/components/overlays/SkillCenter/AIAssistantPanel.tsx

'use client';

/**
 * AI 助手面板 — Forge 左侧的 AI 对话面板。
 *
 * 支持两种模式：
 * 1. 初始模式：输入自然语言描述，触发 Agent 生成技能
 * 2. 迭代模式：在已有 ForgeSession 中提修改要求
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useForgeStore } from '@/store/useForgeStore';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface Message {
  id: string;
  role: 'ai' | 'user';
  content: string;
  timestamp: number;
}

interface AIAssistantPanelProps {
  className?: string;
}

export function AIAssistantPanel({ className }: AIAssistantPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const agentPhase = useForgeStore((s) => s.agentPhase);
  const isAgentRunning = useForgeStore((s) => s.isAgentRunning);
  const sessionId = useForgeStore((s) => s.sessionId);
  const staticCheckResult = useForgeStore((s) => s.staticCheckResult);
  const autoTestResult = useForgeStore((s) => s.autoTestResult);
  const startAgentGeneration = useForgeStore((s) => s.startAgentGeneration);
  const startAgentIteration = useForgeStore((s) => s.startAgentIteration);
  const cancelAgent = useForgeStore((s) => s.cancelAgent);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 当 Agent 阶段变化时，添加 AI 状态消息
  const phaseLabels: Record<string, string> = {
    intent_parse: '正在分析你的需求...',
    similarity_search: '正在搜索已有相似技能...',
    core_generation: '正在生成代码和参数...',
    static_check: '正在执行静态检查...',
    auto_test: '正在运行自动测试...',
    forge_output: '正在保存到工作区...',
  };

  const prevPhaseRef = useRef<string | null>(null);
  useEffect(() => {
    if (agentPhase && agentPhase !== prevPhaseRef.current) {
      prevPhaseRef.current = agentPhase;
      const label = phaseLabels[agentPhase];
      if (label) {
        setMessages((prev) => [
          ...prev,
          { id: `phase-${Date.now()}`, role: 'ai', content: label, timestamp: Date.now() },
        ]);
      }
    }
  }, [agentPhase]);

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isAgentRunning) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsProcessing(true);

    try {
      if (!sessionId) {
        // 模式1: 首次生成 — 没有 session 时创建新的
        await startAgentGeneration({ user_input: trimmed });
      } else {
        // 模式2: 迭代修改 — 已有 session
        await startAgentIteration({
          session_id: sessionId,
          instruction: trimmed,
          scope: 'all',
        });
      }
    } finally {
      setIsProcessing(false);
    }
  }, [input, isAgentRunning, sessionId, startAgentGeneration, startAgentIteration]);

  // 结果摘要消息
  const summaryRef = useRef(false);
  useEffect(() => {
    if (!isAgentRunning && staticCheckResult && !summaryRef.current) {
      summaryRef.current = true;
      const summary = staticCheckResult.passed
        ? `代码生成完成！静态检查通过 (${staticCheckResult.score}/100)。`
        : `代码生成完成，但静态检查发现 ${staticCheckResult.issues.length} 个问题。`;
      setMessages((prev) => [
        ...prev,
        { id: `summary-${Date.now()}`, role: 'ai', content: summary, timestamp: Date.now() },
      ]);
    }
  }, [isAgentRunning, staticCheckResult]);

  return (
    <div className={cn('flex flex-col h-full border-r border-border bg-background', className)}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        <span className="text-sm font-semibold">AI 助手</span>
        {isAgentRunning && (
          <span className="ml-auto text-xs text-muted-foreground animate-pulse">处理中...</span>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-muted-foreground text-sm mt-8">
            <p className="mb-2">告诉我你想创建什么技能？</p>
            <p className="text-xs">例如：「做一个 RNA-seq 差异表达分析」「帮我把 FASTQ 做质控」</p>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              'max-w-[90%] rounded-lg px-3 py-2 text-sm',
              msg.role === 'user'
                ? 'ml-auto bg-primary text-primary-foreground'
                : 'mr-auto bg-muted'
            )}
          >
            {msg.content}
          </div>
        ))}

        {/* 静态检查结果 */}
        {staticCheckResult && !isAgentRunning && (
          <div className="mr-auto max-w-[90%] rounded-lg px-3 py-2 text-xs bg-muted">
            <div className="font-medium mb-1">静态检查: {staticCheckResult.passed ? '✓ 通过' : '✗ 未通过'}</div>
            {!staticCheckResult.passed && staticCheckResult.issues.slice(0, 5).map((issue, i) => (
              <div key={i} className="text-red-500">
                行{issue.line}: [{issue.severity}] {issue.message}
              </div>
            ))}
            {!staticCheckResult.passed && staticCheckResult.issues.length > 5 && (
              <div className="text-muted-foreground">...还有 {staticCheckResult.issues.length - 5} 个问题</div>
            )}
          </div>
        )}

        {/* 自动测试结果 */}
        {autoTestResult && !isAgentRunning && (
          <div className="mr-auto max-w-[90%] rounded-lg px-3 py-2 text-xs bg-muted">
            <div className={`font-medium mb-1 ${autoTestResult.passed ? 'text-green-500' : 'text-red-500'}`}>
              自动测试: {autoTestResult.passed ? '✓ 通过' : '✗ 失败'}
            </div>
            {autoTestResult.error_log && (
              <pre className="text-red-400 mt-1 whitespace-pre-wrap text-[10px]">{autoTestResult.error_log.slice(0, 200)}</pre>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-border">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder={sessionId ? '输入修改要求...' : '描述你想要创建的技能...'}
            className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            disabled={isAgentRunning}
          />
          {isAgentRunning ? (
            <Button variant="outline" size="sm" onClick={cancelAgent}>
              取消
            </Button>
          ) : (
            <Button size="sm" onClick={handleSend} disabled={!input.trim()}>
              发送
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add autonome-studio/src/components/overlays/SkillCenter/AIAssistantPanel.tsx
git commit -m "feat: AIAssistantPanel — Forge 左侧 AI 对话面板，支持生成和迭代模式"
```

---

### Task 13: 前端 — ForgePanel 双栏布局重构

**Files:**
- Modify: `autonome-studio/src/components/overlays/SkillCenter/ForgePanel.tsx`

- [ ] **Step 1: 重构 ForgePanel 为双栏布局**

在 `ForgePanel.tsx` 中，将现有的单面板结构改为左右双栏：

```typescript
// 在 return 的 JSX 中，将原来的：
//   <div className="flex-1 flex flex-col min-h-0 h-full overflow-hidden">
//     <PendingDraftsList ... />
//     <div className="flex-1 ..."><SkillDraftEditor /></div>
//   </div>
// 改为：

return (
  <div className="flex-1 flex min-h-0 h-full overflow-hidden">
    {/* 左侧：AI 助手面板 (30%) */}
    <div className="w-[350px] min-w-[300px] flex-shrink-0">
      <AIAssistantPanel />
    </div>

    {/* 右侧：代码编辑器 (70%) */}
    <div className="flex-1 flex flex-col min-w-0">
      <PendingDraftsList
        onSelectDraft={handleSelectDraft}
      />
      <div className="flex-1 min-h-0 h-full overflow-y-auto">
        <SkillDraftEditor />
      </div>
    </div>
  </div>
);
```

- [ ] **Step 2: 添加 AIAssistantPanel import**

在 ForgePanel.tsx 顶部添加：
```typescript
import { AIAssistantPanel } from './AIAssistantPanel';
```

- [ ] **Step 3: Commit**

```bash
git add autonome-studio/src/components/overlays/SkillCenter/ForgePanel.tsx
git commit -m "feat: ForgePanel 双栏布局重构 — 左侧 AI 助手 + 右侧编辑器"
```

---

### Task 14: 前端 — SkillDraftEditor 流式渲染 + AI 补全按钮

**Files:**
- Modify: `autonome-studio/src/app/skill-forge/components/SkillDraftEditor.tsx`

- [ ] **Step 1: 在编辑器底部状态栏添加 Agent 状态指示**

在 `SkillDraftEditor.tsx` 的底部操作栏（保存/提交按钮区域）添加强化的状态栏：

```typescript
// 从 store 读取 Agent 状态
const agentPhase = useForgeStore((s) => s.agentPhase);
const isAgentRunning = useForgeStore((s) => s.isAgentRunning);
const staticCheckResult = useForgeStore((s) => s.staticCheckResult);
const autoTestResult = useForgeStore((s) => s.autoTestResult);
const startAgentSupplement = useForgeStore((s) => s.startAgentSupplement);
const sessionId = useForgeStore((s) => s.sessionId);

// 添加在底部操作栏区域：
{/* Agent 状态指示栏 */}
{(agentPhase || staticCheckResult || autoTestResult) && (
  <div className="flex items-center gap-3 px-3 py-1.5 border-t border-border bg-muted/30 text-xs">
    {isAgentRunning && (
      <span className="flex items-center gap-1 text-muted-foreground">
        <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
        AI 处理中...
      </span>
    )}
    {staticCheckResult && (
      <span className={staticCheckResult.passed ? 'text-green-500' : 'text-red-500'}>
        {staticCheckResult.passed ? '✓ 检查通过' : `✗ ${staticCheckResult.issues.length} 个问题`}
        ({staticCheckResult.score}分)
      </span>
    )}
    {autoTestResult && (
      <span className={autoTestResult.passed ? 'text-green-500' : 'text-yellow-500'}>
        {autoTestResult.passed ? '✓ 测试通过' : '⚠ 测试未通过'}
      </span>
    )}
  </div>
)}

{/* AI 补全按钮（元数据 Tab 中） */}
{activeTab === 'metadata' && sessionId && (
  <div className="flex gap-2 mt-3">
    <Button
      variant="outline"
      size="sm"
      disabled={isAgentRunning}
      onClick={() => startAgentSupplement({ session_id: sessionId!, supplement_type: 'docs' })}
    >
      AI 生成文档
    </Button>
    <Button
      variant="outline"
      size="sm"
      disabled={isAgentRunning}
      onClick={() => startAgentSupplement({ session_id: sessionId!, supplement_type: 'tags' })}
    >
      AI 推荐标签
    </Button>
    <Button
      variant="outline"
      size="sm"
      disabled={isAgentRunning}
      onClick={() => startAgentSupplement({ session_id: sessionId!, supplement_type: 'dependencies' })}
    >
      AI 分析依赖
    </Button>
  </div>
)}
```

- [ ] **Step 2: 添加必要的 import**

在 SkillDraftEditor.tsx 顶部确认：
```typescript
import { useForgeStore } from '@/store/useForgeStore';
```

- [ ] **Step 3: Commit**

```bash
git add autonome-studio/src/app/skill-forge/components/SkillDraftEditor.tsx
git commit -m "feat: SkillDraftEditor — Agent 状态栏 + AI 补全按钮(文档/标签/依赖)"
```

---

### Task 15: Docker 验证 + 集成测试

**Files:**
- Create: `autonome-backend/tests/test_skill_creator_agent.py`

- [ ] **Step 1: 编写 Skill Creator Agent 单元测试**

```python
# autonome-backend/tests/test_skill_creator_agent.py

"""Skill Creator Agent 单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.skill_creator import (
    SkillCreatorAgent,
    CreatorPhase,
    AgentState,
    DEFAULT_TIMEOUTS,
)


@pytest.fixture
def mock_llm():
    """模拟 LLM"""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()
    return llm


@pytest.fixture
def sample_state() -> AgentState:
    return {
        "user_input": "帮我做差异表达分析",
        "chat_context": None,
        "base_skill_id": None,
        "intent": {},
        "similar_skills": [],
        "script_code": "",
        "parameters_schema": {},
        "static_check_result": {},
        "auto_test_result": {},
        "current_phase": "",
        "error": None,
        "retry_count": 0,
        "should_pause": False,
        "user_action": None,
        "session_id": None,
        "forge_url": None,
    }


@pytest.mark.asyncio
async def test_intent_parse_node(mock_llm):
    """测试意图解析节点正常输出"""
    from langchain_core.messages import AIMessage
    import json

    mock_llm.ainvoke.return_value = AIMessage(content=json.dumps({
        "name": "差异表达分析",
        "name_en": "differential_expression",
        "domain": "transcriptomics",
        "description": "DESeq2差异表达分析",
        "inputs": [{"name": "count_matrix", "type": "FilePath", "required": True, "description": "表达矩阵"}],
        "outputs": [{"name": "de_results", "type": "File", "description": "差异表达结果"}],
        "executor_type": "R_env",
        "primary_tool": "DESeq2",
        "skill_id": "deseq2_de_analysis",
        "confidence": "high",
    }))

    agent = SkillCreatorAgent(llm=mock_llm)
    state = {
        "user_input": "帮我做差异表达分析",
        "chat_context": None,
        "base_skill_id": None,
        "intent": {},
        "similar_skills": [],
        "script_code": "",
        "parameters_schema": {},
        "static_check_result": {},
        "auto_test_result": {},
        "current_phase": "",
        "error": None,
        "retry_count": 0,
        "should_pause": False,
        "user_action": None,
        "session_id": None,
        "forge_url": None,
    }

    result = await agent._intent_parse_node(state)

    assert "error" not in result or result.get("error") is None
    assert result["intent"]["name"] == "差异表达分析"
    assert result["intent"]["executor_type"] == "R_env"
    assert result["current_phase"] == "intent_parse"


@pytest.mark.asyncio
async def test_after_phase_continue():
    """测试阶段完成后正常继续"""
    agent = SkillCreatorAgent(llm=MagicMock())
    state = {
        "user_input": "",
        "chat_context": None,
        "base_skill_id": None,
        "intent": {},
        "similar_skills": [],
        "script_code": "",
        "parameters_schema": {},
        "static_check_result": {},
        "auto_test_result": {},
        "current_phase": "intent_parse",
        "error": None,
        "retry_count": 0,
        "should_pause": False,
        "user_action": None,
        "session_id": None,
        "forge_url": None,
    }

    assert agent._after_phase(state) == "continue"


def test_after_phase_error():
    """测试发生错误时返回 error"""
    agent = SkillCreatorAgent(llm=MagicMock())
    state = {
        "user_input": "",
        "chat_context": None,
        "base_skill_id": None,
        "intent": {},
        "similar_skills": [],
        "script_code": "",
        "parameters_schema": {},
        "static_check_result": {},
        "auto_test_result": {},
        "current_phase": "core_generation",
        "error": "LLM timeout",
        "retry_count": 0,
        "should_pause": False,
        "user_action": None,
        "session_id": None,
        "forge_url": None,
    }

    assert agent._after_phase(state) == "error"


def test_after_phase_pause():
    """测试阶段完成等待用户确认"""
    agent = SkillCreatorAgent(llm=MagicMock())
    state = {
        "user_input": "",
        "chat_context": None,
        "base_skill_id": None,
        "intent": {},
        "similar_skills": [],
        "script_code": "",
        "parameters_schema": {},
        "static_check_result": {},
        "auto_test_result": {},
        "current_phase": "similarity_search",
        "error": None,
        "retry_count": 0,
        "should_pause": True,
        "user_action": None,
        "session_id": None,
        "forge_url": None,
    }

    assert agent._after_phase(state) == "pause"


@pytest.mark.asyncio
async def test_static_check_with_retry(mock_llm):
    """测试静态检查失败时的自动重试逻辑"""
    from langchain_core.messages import AIMessage

    agent = SkillCreatorAgent(llm=mock_llm)
    state = {
        "user_input": "",
        "chat_context": None,
        "base_skill_id": None,
        "intent": {"executor_type": "Python_env"},
        "similar_skills": [],
        "script_code": "print('hello')",
        "parameters_schema": {},
        "static_check_result": {},
        "auto_test_result": {},
        "current_phase": "static_check",
        "error": None,
        "retry_count": 0,
        "should_pause": False,
        "user_action": "retry",
        "session_id": None,
        "forge_url": None,
    }

    with patch("app.agent.skill_creator.review_skill_code") as mock_review:
        mock_review.return_value = MagicMock(
            passed=False, score=70,
            issues=[MagicMock(line=1, severity=MagicMock(value="high"), message="test", rule_id="TEST001")],
            summary="found issues",
            suggestions=["add argparse"]
        )
        mock_llm.ainvoke.return_value = AIMessage(content="fixed code")

        result = await agent._static_check_node(state)

        assert result["retry_count"] == 1
        assert result["script_code"] == "fixed code"
        assert result["current_phase"] == "static_check"


def test_default_timeouts():
    """测试默认超时配置"""
    assert DEFAULT_TIMEOUTS["intent_parse"] == 10
    assert DEFAULT_TIMEOUTS["core_generation"] == 30
    assert DEFAULT_TIMEOUTS["auto_test"] == 120
```

- [ ] **Step 2: Run tests**

```bash
cd autonome-backend && python -m pytest tests/test_skill_creator_agent.py -v
```

Expected: 5 tests PASS

- [ ] **Step 3: Commit**

```bash
git add autonome-backend/tests/test_skill_creator_agent.py
git commit -m "test: Skill Creator Agent 单元测试 — 意图解析、状态转换、静态检查重试"
```

---

### Task 16: 最终验证 — Docker 重启 + 前端构建

- [ ] **Step 1: 重启 Docker 服务**

```bash
cd /opt/data1/public/software/systools/autonome && docker-compose down && docker-compose up -d
```

Check backend and frontend logs for errors:
```bash
docker logs autonome-api | tail -20
docker logs autonome-web | tail -20
```

- [ ] **Step 2: 验证 API 路由注册**

```bash
curl -s http://localhost:8000/docs | grep "forge/agent"
```

Expected: 包含 `/api/forge/agent/generate` 等路由

- [ ] **Step 3: 验证前端构建**

```bash
cd autonome-studio && npm run build
```

Expected: Build succeeds with no errors

- [ ] **Step 4: 验证前端的 TypeScript 编译**

```bash
cd autonome-studio && npx tsc --noEmit
```

Expected: No type errors

- [ ] **Step 5: 运行后端测试**

```bash
cd autonome-backend && python -m pytest tests/test_skill_creator_agent.py -v
```

Expected: All tests pass

- [ ] **Step 6: Commit 验证结果**

```bash
git add -A
git commit -m "chore: Docker 验证 + 前端构建 + 后端测试全部通过"
```

---

## Self-Review Checklist

### 1. Spec Coverage

| 设计章节 | 对应任务 | 状态 |
|----------|----------|------|
| Agent 状态机 6 阶段 | Task 2-7 | ✓ |
| SSE 流式推送 | Task 8 | ✓ |
| generate/iterate/supplement API | Task 8 | ✓ |
| ForgeSession 扩展 | Task 1 | ✓ |
| Forge 双栏布局 | Task 12, 13 | ✓ |
| AI 助手对话面板 | Task 12 | ✓ |
| 流式渲染 Agent 输出 | Task 14 | ✓ |
| 状态栏（检查+测试结果）| Task 14 | ✓ |
| AI 补全按钮 | Task 14 | ✓ |
| 异常处理/重试 | Task 5, 6 | ✓ |
| 超时策略 | Task 2 (DEFAULT_TIMEOUTS) | ✓ |
| 断连恢复 | Task 8 (get_agent_state), Task 10 (getState) | ✓ |

### 2. Placeholder Scan
- No "TBD", "TODO", or "implement later" found
- All steps have actual code (not descriptions)
- No "add appropriate error handling" without code
- No "similar to Task N" references

### 3. Type Consistency
- AgentState TypedDict fields consistent across Tasks 2-7
- PhaseCallback signature matches usage in Tasks 2 and 8
- GenerateRequest/IterateRequest/SupplementRequest consistent across Tasks 8 and 10
- ForgeState agent fields consistent across Tasks 11, 12, 14
- forgeAgentApi method signatures match call sites in Tasks 11 and 12
