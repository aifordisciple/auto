# AUTONOME STUDIO 系统架构文档

> **文档版本**: 2.0.0
> **更新日期**: 2026-04-09
> **项目定位**: AI-Native Bioinformatics IDE — FastAPI/LangGraph 后端 + Next.js 16 前端

---

## 目录

1. [系统概述](#1-系统概述)
2. [后端架构](#2-后端架构)
   - 2.1 [核心 Agent 系统](#21-核心-agent-系统)
   - 2.2 [模块化工具系统](#22-模块化工具系统)
   - 2.3 [技能生态系统](#23-技能生态系统)
   - 2.4 [三阶段技能推荐](#24-三阶段技能推荐)
   - 2.5 [系统学习层](#25-系统学习层)
   - 2.6 [Docker 沙箱执行引擎](#26-docker-沙箱执行引擎)
   - 2.7 [API 路由层](#27-api-路由层)
   - 2.8 [数据模型层](#28-数据模型层)
3. [前端架构](#3-前端架构)
   - 3.1 [页面与路由](#31-页面与路由)
   - 3.2 [状态管理 (Zustand)](#32-状态管理-zustand)
   - 3.3 [核心组件](#33-核心组件)
   - 3.4 [API 客户端](#34-api-客户端)
4. [数据流与交互](#4-数据流与交互)
5. [部署架构](#5-部署架构)

---

## 1. 系统概述

Autonome Studio 是一个面向生物信息学分析的 AI 原生 IDE，采用 **前后端分离 + Docker 沙箱** 的架构设计：

```
┌─────────────────────────────────────────────────────────────────┐
│                     Autonome Studio 架构图                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐     ┌──────────────────┐                  │
│  │   Frontend       │     │   Backend        │                  │
│  │   (Next.js 16)   │────▶│   (FastAPI)     │                  │
│  │   Port: 3001     │     │   Port: 8000    │                  │
│  └──────────────────┘     └────────┬─────────┘                  │
│                                    │                              │
│                           ┌────────▼─────────┐                   │
│                           │  Agent System    │                   │
│                           │  - Bot Agent     │                   │
│                           │  - PI Agents     │                   │
│                           │  - Super Executor│                   │
│                           └────────┬─────────┘                   │
│                                    │                              │
│                           ┌────────▼─────────┐                   │
│                           │  Docker Sandbox  │                   │
│                           │  (代码执行引擎)   │                   │
│                           └──────────────────┘                   │
│                                    │                              │
│  ┌─────────────────────────────────▼──────────────────────────┐  │
│  │                    Data Layer                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │  │
│  │  │ PostgreSQL  │  │   Redis     │  │   FileSystem        │  │  │
│  │  │ + pgvector  │  │   Cache     │  │   (uploads/)       │  │  │
│  │  │ Port: 5433  │  │   Port: 6379│  │                     │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 核心设计理念

1. **Agent 不直接执行代码**：Agent 只负责制定计划和输出代码，实际执行由前端拦截策略卡片后交由沙箱运行
2. **SKILL 优先策略**：优先复用已有的标准化技能包，无法匹配时才进入 Live Coding 模式
3. **环境探针先行**：在处理任何数据前，强制调用探针工具了解数据结构，杜绝盲目猜测
4. **三阶段技能推荐**：规则引擎 + 向量检索 + LLM 精排，平衡速度与准确性
5. **系统学习闭环**：从执行反馈中自动提取方法论，持续优化推荐质量

---

## 2. 后端架构

后端采用 FastAPI + LangGraph 构建，核心模块包括：

### 2.1 核心 Agent 系统

#### 2.1.1 Agent 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      Agent 系统架构                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐│
│  │  Bot Agent  │────▶│ PI Agents   │────▶│ Super Executor V4  ││
│  │  (主规划)   │     │  (复杂任务)  │     │  (三阶段执行)       ││
│  └─────────────┘     └─────────────┘     └─────────────────────┘│
│         │                   │                      │              │
│         ▼                   ▼                      ▼              │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    Tool Registry                            │  │
│  │  - CodeExecutionTool  - DataProbeTool  - FileOperationTool │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │               ExecutionPlan & Orchestrator                    │  │
│  │  - ExecutionPlan    - StepOrchestrator  - ResponseParser    │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.1.2 主 Agent (Bot Agent)

**文件路径**: `autonome-backend/app/agent/bot.py`

**功能描述**: 系统的"大脑"，负责理解用户需求、规划分析流程、输出代码和策略卡片。

**核心算法流程**:

```
用户输入
    │
    ▼
┌─────────────────────────────────────┐
│ 1. Token 预算控制                    │
│   - NORMAL: 普通任务                │
│   - HIGH: 复杂任务 (task_mode=complex)│
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│ 2. 加载上下文                         │
│   - 项目 ID                          │
│   - 文件树 (global_file_tree)        │
│   - 用户选中的文件                    │
│   - 视觉配置 (可选)                  │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│ 3. 加载 SKILL 库                     │
│   - 扫描 /app/skills 目录            │
│   - 解析 SKILL.md 元数据              │
│   - 系统学习技能注入 (SkillInjector) │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│ 4. 构建 LLM Prompt                   │
│   - 上下文信息                        │
│   - 技能目录                          │
│   - 角色定义与交互协议               │
│   - 代码工程规范                      │
│   - 策略卡片确认流程                  │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│ 5. 创建 ReAct Agent                  │
│   - 工具集: 探针工具 + GEO 工具      │
│   - 可选视觉模型                      │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│ 6. 执行 Agent 并流式返回              │
│   - 输出代码块 (```python / ```r)    │
│   - 输出策略卡片 (```json_strategy)  │
│   - 等待前端确认执行                  │
└─────────────────────────────────────┘
```

**工具集**:
- `search_and_vectorize_geo_data`: GEO 数据检索
- `submit_async_geo_analysis_task`: 异步 GEO 分析
- `generate_publishable_report`: 报告生成
- `peek_tabular_data`: 表格数据预览 (探针)
- `scan_workspace`: 目录扫描 (探针)

---

#### 2.1.3 复杂任务处理 (PI Agents)

**文件路径**: `autonome-backend/app/agent/pi_agent.py`, `chief_pi_agent.py`

**功能描述**: 当任务复杂度超过阈值时，触发 PI (Planning & Intelligence) Agents 进行深度规划。

**触发条件**: `is_complex_task()` 函数判断

**流程**:

```
复杂任务检测
    │
    ▼
┌─────────────────────────────────────┐
│ Chief PI Agent                       │
│ - 分解任务为子任务                  │
│ - 确定执行依赖关系                  │
│ - 生成执行蓝图 (Blueprint)          │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│ BlueprintCard 输出                   │
│ - DAG 可视化                        │
│ - 子任务列表                        │
│ - 预期输出                          │
└─────────────────────────────────────┘
```

---

#### 2.1.4 超级执行器 V4 (Super Executor V4)

**文件路径**: `autonome-backend/app/agent/super_executor_v4.py`

**功能描述**: 三阶段执行流程，处理复杂分析任务。

**三阶段状态机**:

```
START → PHASE_1_EXPLORE → PHASE_2_INSTALL_DEPS → PHASE_3_EXECUTE → END
             ↓                    ↓                    ↓
       [探测代码生成]        [conda安装]          [分析执行+重试]
       [沙箱执行]           [启用网络]            [生成战报]
```

**阶段详情**:

| 阶段 | 状态 | 功能 |
|------|------|------|
| Phase 1 | `phase_1_exploring` | 生成并执行探查代码，获取文件详细结构 |
| Phase 2 | `phase_2_installing` | 解析依赖，使用 conda 安装缺失的包 |
| Phase 3 | `phase_3_executing` | 基于探查结果生成并执行最终脚本 |
| 战报 | `battle_report` | 生成执行结果摘要和分析报告 |

**SSE 事件类型**:
- `phase_change`: 阶段切换
- `exploration_progress`: 探查进度
- `install_progress`: 安装进度
- `execution_output`: 执行输出
- `debug_retry`: 调试重试
- `battle_report`: 战报生成

---

#### 2.1.5 执行计划与编排器

**文件路径**: `autonome-backend/app/agent/execution_plan.py`, `orchestrator.py`

**ExecutionPlan 核心类**:

```python
class ExecutionPlan:
    plan_id: str
    project_id: int
    user_id: int
    steps: List[ExecutionStep]
    output_dir: str
    status: ExecutionStatus

class ExecutionStep:
    step_id: str
    tool_id: str
    params: Dict[str, Any]
    dependencies: List[str]  # 依赖的 step_id 列表
    status: ExecutionStatus
    result: Any
```

**StepOrchestrator 编排执行**:

- 拓扑排序执行
- 并行执行无依赖步骤
- 实时 SSE 状态推送
- 智能错误处理和重试

---

#### 2.1.6 技能锻造 Agent (Crafter Agent)

**文件路径**: `autonome-backend/app/agent/crafter.py`

**功能描述**: 将非结构化素材（代码、文献、文本指令）逆向提炼为标准技能包。

**锻造四大铁律**:
1. **参数自动化抽取**: 必须使用 argparse (Python) 或 optparse (R)
2. **强制详细注释**: 详尽的中文块级注释和行级注释
3. **强制 TSV 输出**: 表格数据必须输出为 Tab 分割格式
4. **发表级图形**: 300 DPI、PDF 矢量、色盲友好配色

---

### 2.2 模块化工具系统

**文件路径**: `autonome-backend/app/agent/tools/`

#### 2.2.1 工具注册表 (ToolRegistry)

**文件路径**: `autonome-backend/app/agent/tools/registry.py`

单例模式，管理所有注册的工具：

```python
class ToolRegistry:
    _tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None
    def get(self, tool_id: str) -> BaseTool | None
    def list_tools() -> List[BaseTool]
    def get_tools_by_category(category: ToolCategory) -> List[BaseTool]
```

#### 2.2.2 工具基类 (BaseTool)

**文件路径**: `autonome-backend/app/agent/tools/base.py`

```python
class BaseTool:
    tool_id: str
    name: str
    description: str
    category: ToolCategory
    parameters: List[ToolParameter]

    async def execute(self, params: Dict[str, Any], context: ExecutionContext) -> ToolResult
```

#### 2.2.3 工具类别

| 类别 | 工具 | 功能 |
|------|------|------|
| `CODE_EXECUTION` | `CodeExecutionTool`, `PythonExecutionTool`, `RExecutionTool` | 代码执行 |
| `DATA_PROBE` | `DataProbeTool`, `ScanWorkspaceTool`, `PeekTabularTool`, `InspectH5adTool` | 数据探查 |
| `FILE_OPERATION` | `FileOperationTool` | 文件操作 |

#### 2.2.4 探针工具列表

| 工具名 | 功能 | 使用场景 |
|--------|------|----------|
| `peek_tabular_data` | 预览表格文件（CSV/TSV） | 处理表格数据前，了解表头和维度 |
| `scan_workspace` | 扫描目录结构 | 需要找文件但不确定位置 |
| `inspect_h5ad` | 解析 .h5ad 单细胞数据 | 处理单细胞 AnnData 数据前 |
| `inspect_fastq` | 预览 FASTQ 测序文件 | RNA-Seq、单细胞等测序数据预览 |
| `inspect_bam` | 预览 BAM 比对文件 | 比对结果快速预览 |

---

### 2.3 技能生态系统

#### 2.3.1 技能解析器

**文件路径**: `autonome-backend/app/core/skill_parser.py`

**功能描述**: 解析 SKILL.md 文件，提取元数据、参数 Schema 和专家知识库。

**关键类**:

| 类名 | 描述 | 使用场景 |
|------|------|----------|
| `SkillBundleParser` | 文件系统解析器 | 加载官方预置技能 |
| `DBSkillParser` | 数据库解析器 | 加载用户自定义技能（带权限过滤） |
| `get_combined_skills()` | 统一获取方法 | 返回用户可见的所有技能 |

---

#### 2.3.2 技能执行器

**文件路径**: `autonome-backend/app/services/skill_executor.py`

**功能描述**: 整合样本表预处理和并行执行，支持多种执行器类型。

**执行器类型映射**:

| 执行器类型 | 描述 | 执行方式 |
|------------|------|----------|
| `Python_env` | 单 Python 脚本 | Docker 沙箱 + Python 解释器 |
| `R_env` | 单 R 脚本 | Docker 沙箱 + Rscript |
| `Logical_Blueprint` | Nextflow 工作流 | Nextflow DSL2 编译执行 |
| `Bash_env` | Bash 脚本 | Docker 沙箱 + Shell |

**执行流程**:

```
SkillExecutor(skill_id, params, project_id)
    │
    ├── 1. preprocess()
    │   ├── 处理样本表参数
    │   ├── 注入系统变量 (PROJECT_ID, TASK_OUT_DIR)
    │   └── 验证参数完整性
    │
    ├── 2. 根据执行器类型分发
    │   ├── Logical_Blueprint → _execute_nextflow()
    │   ├── Python_env → _execute_python()
    │   ├── R_env → _execute_r()
    │   └── Bash_env → _execute_bash()
    │
    └── 3. 返回执行结果
```

---

### 2.4 三阶段技能推荐

**文件路径**: `autonome-backend/app/services/skill_matcher.py`

#### 2.4.1 架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     技能推荐系统架构 (混合模式)                           │
├─────────────────────────────────────────────────────────────────────────┤
│  用户查询 ──→ 规则引擎(快速筛选) ──→ 向量检索(语义匹配) ──→ LLM精排     │
│     │              (<50ms)           (~100ms)          (~1-2s)          │
│     │                │                    │                │            │
│     │                ▼                    ▼                ▼            │
│     │           候选技能集 ← ← ← ← ← ← ← ←┘                │            │
│     │                │                                      │            │
│     └───────────────→│← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┘            │
│                      ▼                                                   │
│              推荐结果 + 参数建议                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 2.4.2 匹配模式

| 模式 | 描述 | 响应时间 |
|------|------|----------|
| `FAST` | 仅规则+向量匹配 | <200ms |
| `PRECISE` | 完整三阶段匹配（含LLM精排） | ~1-2s |
| `AUTO` | 系统根据置信度自动决定 | 自适应 |

#### 2.4.3 流程决策逻辑

| 场景 | 规则置信度 | 向量相似度 | 是否触发LLM |
|---------------|-----------|-----------|------------|
| 高置信度 | ≥ 0.85 | - | 否 |
| 中置信度 | 0.5-0.85 | ≥ 0.75 | 否 |
| 低置信度 | < 0.5 | < 0.6 | 是 |
| 候选接近 | - | 多个差距<0.1 | 是 |

#### 2.4.4 核心组件

| 组件 | 文件路径 | 功能 |
|------|----------|------|
| `SkillMatcher` | `skill_matcher.py` | 统一匹配器，整合三阶段 |
| `SkillKeywordsIndexer` | `skill_keywords_indexer.py` | 从 SKILL.md 提取关键词 |
| `SkillEmbeddingService` | `skill_embedding_service.py` | 技能语义向量计算 |
| `SkillVectorSearch` | `skill_vector_search.py` | pgvector 向量检索 |
| `LLMSkillMatcher` | `llm_skill_matcher.py` | LLM 精排、参数推断 |
| `SkillMatcherConfig` | `skill_matcher_config.py` | 同义词映射、关键词权重 |

#### 2.4.5 意图类型

| 类型 | 描述 | 置信度 | 处理方式 |
|------|------|--------|----------|
| `explicit_skill` | 明确提及技能名称 | > 0.9 | 直接调用对应 SKILL |
| `implicit_skill` | 隐式技能需求 | 0.5-0.9 | 推荐并询问确认 |
| `live_coding` | 需要自定义代码 | < 0.5 | 回退到 Live Coding |
| `general_question` | 一般问题 | - | 知识问答 |

---

### 2.5 系统学习层

**文件路径**: `autonome-backend/app/services/system_learning/`

#### 2.5.1 系统学习架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    系统学习层架构                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐                                                │
│  │ 执行反馈    │ ←── 用户确认执行、结果评价                      │
│  └──────┬──────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                 Success Evaluator                           │  │
│  │  - 评估执行结果质量                                        │  │
│  │  - 检测失败模式和成功模式                                  │  │
│  └──────────────────────────┬──────────────────────────────────┘  │
│                             │                                     │
│         ┌───────────────────┼───────────────────┐                │
│         ▼                   ▼                   ▼                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │ 方法提取器  │    │ 技能注入器  │    │ 权重优化器  │          │
│  │MethodExtractor│  │SkillInjector│    │WeightOptimizer│          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│         │                   │                   │                 │
│         └───────────────────┴───────────────────┘                │
│                             │                                     │
│                             ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              反馈到 Agent 上下文                            │  │
│  │  - 注入相关系统技能                                         │  │
│  │  - 调整推荐权重                                             │  │
│  │  - 优化执行策略                                             │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.5.2 核心组件

| 组件 | 文件路径 | 功能 |
|------|----------|------|
| `SuccessEvaluator` | `success_evaluator.py` | 评估执行结果质量 |
| `SkillInjector` | `skill_injector.py` | 隐身注入系统技能到 Agent 上下文 |
| `MethodExtractor` | `method_extractor.py` | 从执行历史中提取方法论 |
| `WeightOptimizer` | `weight_optimizer.py` | 优化推荐权重 |
| `PrivacyValidator` | `privacy_validator.py` | 隐私验证 |
| `SessionPool` | `session_pool.py` | 会话池管理 |
| `BatchScheduler` | `batch_scheduler.py` | 批处理调度 |

#### 2.5.3 技能注入器 (SkillInjector)

**文件路径**: `autonome-backend/app/services/system_learning/skill_injector.py`

**功能**: 在 Agent 处理用户请求时，自动检索并注入相关的系统级技能。

**配置参数**:
- `TOP_K`: 最多注入技能数量 (默认 3)
- `SIMILARITY_THRESHOLD`: 向量相似度阈值 (默认 0.7)
- `VECTOR_WEIGHT`: 向量检索权重 (默认 0.7)
- `KEYWORD_WEIGHT`: 关键词检索权重 (默认 0.3)

---

### 2.6 Docker 沙箱执行引擎

**文件路径**: `autonome-backend/app/tools/bio_tools.py`

**功能描述**: 通过 Docker API 在隔离容器中执行用户代码，提供安全的代码运行环境。

**核心架构**:

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Sandbox 架构                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐      Unix Socket      ┌──────────────┐ │
│  │   FastAPI       │ ──────────────────▶   │ Docker Daemon│ │
│  │   Backend       │   /var/run/docker.sock│              │ │
│  └─────────────────┘                        └──────┬───────┘ │
│                                                     │         │
│                                          ┌─────────▼────────┐│
│                                          │  Container       ││
│                                          │  ┌────────────┐  ││
│                                          │  │ Script.py  │  ││
│                                          │  │ or Script.R│  ││
│                                          │  └────────────┘  ││
│                                          │                   ││
│  Mount Points:                           │  Resources:       ││
│  /workspace ←→ uploads/                │  - 4GB Memory    ││
│  /opt/conda ←→ autonome_conda/           │  - Network: none ││
│                                          │  - CapDrop: ALL  ││
│                                          └───────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**关键函数**:

```python
def run_container(
    image: str,
    command: str | list,
    language: str = "python",
    environment: dict = None,
    timeout: int = 3600,
    cli_mode: bool = False
) -> tuple[str, int]:
    """
    执行流程：
    1. 准备环境变量和挂载目录
    2. 支持 cli_mode
    3. 创建容器（无网络、资源限制）
    4. 启动并等待执行完成
    5. 提取日志并清理容器
    """
```

---

### 2.7 API 路由层

**文件路径**: `autonome-backend/app/api/routes/`

| 路由文件 | 端点前缀 | 功能描述 |
|----------|----------|----------|
| `auth.py` | `/api/auth` | 用户认证、登录、注册、Token 刷新 |
| `chat.py` | `/api/chat` | 聊天会话管理、流式对话、消息历史 |
| `chat_session.py` | `/api/chat/sessions` | 会话 CRUD |
| `chat_bookmark.py` | `/api/chat/bookmarks` | 消息书签 |
| `chat_experience.py` | `/api/chat/experiences` | 经验资产关联 |
| `chat_search.py` | `/api/chat/search` | 聊天搜索 |
| `chat_summary.py` | `/api/chat/summary` | 会话摘要 |
| `chat_tags.py` | `/api/chat/tags` | 会话标签 |
| `chat_interpret.py` | `/api/chat/interpret` | 聊天解读 |
| `tasks.py` | `/api/tasks` | 异步任务管理 |
| `skills/` | `/api/skills` | 技能模块化路由 |
| `skills_forge.py` | `/api/skills/forge` | 技能锻造 |
| `skill_recommend.py` | `/api/skills/recommend` | 技能推荐 |
| `skill_market.py` | `/api/skills/market` | 技能市场 |
| `super_executor.py` | `/api/super-executor` | 超级执行器 |
| `projects.py` | `/api/projects` | 项目管理 |
| `admin.py` | `/api/admin` | 管理员功能 |
| `billing.py` | `/api/billing` | 计费系统 |
| `packages.py` | `/api/packages` | 包管理 |
| `genomes.py` | `/api/genomes` | 参考基因组 |
| `databases.py` | `/api/databases` | 分析数据库 |
| `terminal.py` | `/api/terminal` | Web Terminal |
| `claude_executor.py` | `/api/claude` | Claude 执行器 |
| `blueprint.py` | `/api/blueprint` | 蓝图管理 |
| `system.py` | `/api/system` | 系统配置 |
| `system_learning.py` | `/api/system/learning` | 系统学习配置 |
| `analytics.py` | `/api/analytics` | 分析数据 |
| `preferences.py` | `/api/preferences` | 用户偏好 |
| `knowledge.py` | `/api/knowledge` | 知识库 |
| `weights.py` | `/api/weights` | 权重配置 |
| `learning.py` | `/api/learning` | 学习配置 |
| `sample_sheets.py` | `/api/sample-sheets` | 样本表管理 |
| `plot.py` | `/api/plot` | 绘图服务 |
| `error_diagnostic.py` | `/api/error-diagnostic` | 错误诊断 |
| `dashboard.py` | `/api/dashboard` | 仪表板数据 |
| `experiences.py` | `/api/experiences` | 经验资产 |
| `templates.py` | `/api/templates` | 模板管理 |

**技能模块化路由** (`skills/` 目录):

| 文件 | 功能 |
|------|------|
| `admin.py` | 技能审核管理 |
| `catalog.py` | 技能目录 |
| `favorites.py` | 技能收藏 |
| `forge.py` | 技能锻造 |
| `my.py` | 我的技能 |
| `reviews.py` | 技能评价 |
| `stats.py` | 技能统计 |
| `testing.py` | 技能测试 |
| `transform.py` | 技能转换 |
| `versions.py` | 版本管理 |
| `draft.py` | 草稿管理 |
| `crud.py` | 基础 CRUD |

**认证机制**:
- JWT Token (HS256)
- 7 天有效期
- 自动刷新机制

---

### 2.8 数据模型层

**文件路径**: `autonome-backend/app/models/`

#### 2.8.1 模块化结构

```
models/
├── __init__.py      # 统一入口，向后兼容
├── domain.py        # 向后兼容入口
├── enums.py         # 所有枚举定义
├── uuid.py          # UUID 生成函数
├── user.py          # 用户和计费账户模型
├── project.py       # 项目、数据文件模型
├── chat.py          # 会话、消息、标签模型
├── task.py          # 任务记录模型
├── config.py        # 系统配置模型
├── skill/           # 技能相关模型目录
│   ├── __init__.py
│   ├── asset.py     # SkillAsset 模型
│   ├── version.py   # 版本模型
│   ├── review.py    # 评价模型
│   ├── favorite.py  # 收藏模型
│   ├── history.py   # 执行历史
│   ├── recommendation.py  # 推荐日志
│   ├── share.py     # 分享模型
│   └── draft.py     # 草稿模型
├── experience.py    # 经验资产模型
├── sharing.py       # 用户组和分享模型
├── package.py       # 用户包管理模型
├── genome.py        # 参考基因组模型
├── database.py      # 分析数据库模型
├── billing.py       # 计费模型
├── claude_executor.py  # Claude 执行器模型
├── system_skill.py  # 系统技能模型
├── feedback_weight.py  # 反馈权重模型
├── learning_metrics.py # 学习指标模型
├── user_preference.py  # 用户偏好模型
└── domain_knowledge.py # 领域知识模型
```

#### 2.8.2 核心数据模型

| 模型 | 描述 | 关键字段 |
|------|------|----------|
| `User` | 用户 | id, username, email, role |
| `BillingAccount` | 计费账户 | user_id, balance, tier |
| `Project` | 项目 | id, name, description, owner_id |
| `DataFile` | 数据文件 | project_id, path, type, size |
| `ChatSession` | 聊天会话 | id, title, project_id, user_id |
| `ChatMessage` | 聊天消息 | id, session_id, role, content |
| `SkillAsset` | 技能资产 | skill_id, name, executor_type, status |
| `SkillVersion` | 技能版本 | skill_id, version, change_log |
| `SkillReview` | 技能审核 | skill_id, reviewer_id, rating |
| `TaskRecord` | 异步任务 | id, task_type, status, result |
| `SystemSkill` | 系统技能 | skill_id, embedding, keywords |
| `ExperienceAsset` | 经验资产 | id, user_id, content, type |

#### 2.8.3 技能状态流转

```
DRAFT → PENDING_REVIEW → PUBLISHED
         ↓
       REJECTED → (修改后) → PENDING_REVIEW
```

---

## 3. 前端架构

前端采用 Next.js 16 (App Router) + TypeScript + Zustand 构建。

### 3.1 页面与路由

**文件路径**: `autonome-studio/src/app/`

| 页面路径 | 文件 | 功能描述 |
|----------|------|----------|
| `/` | `page.tsx` | 主 IDE 页面（聊天、文件管理、工作区） |
| `/login` | `login/page.tsx` | 登录页面 |
| `/admin` | `admin/page.tsx` | 管理员面板 |
| `/admin/skills` | `admin/skills/page.tsx` | 技能审核管理 |
| `/skill-forge` | `skill-forge/page.tsx` | 技能锻造工厂 |
| `/skill-market` | `skill-market/page.tsx` | 技能市场 |
| `/dashboard` | `dashboard/page.tsx` | 仪表板 |
| `/share/[token]` | `share/[token]/page.tsx` | 分享页面 |

### 3.2 状态管理 (Zustand)

**文件路径**: `autonome-studio/src/store/`

| Store 文件 | 功能 | 关键状态 |
|------------|------|----------|
| `useAuthStore.ts` | 认证状态 | user, token, isAuthenticated |
| `useChatStore.ts` | 聊天状态 | messages, streamingContent, bookmarks |
| `useWorkspaceStore.ts` | 工作区状态 | currentProject, files, selectedFiles |
| `useTaskStore.ts` | 任务状态 | tasks, activeTask |
| `useUIStore.ts` | UI 状态 | theme, sidebarOpen, modals |
| `useForgeStore.ts` | 技能锻造状态 | draft, session, testResults |
| `useShortcutStore.ts` | 快捷键状态 | shortcuts, commandPaletteOpen |

**流式消息优化 (ChatStore)**:

```typescript
interface ChatState {
  streamingMessageId: string | null;
  streamingContent: string;
  setStreamingMessageId: (id: string | null) => void;
  appendStreamingContent: (chunk: string) => void;
  commitStreamingContent: () => void;
  clearStreamingContent: () => void;
}
```

### 3.3 核心组件

**文件路径**: `autonome-studio/src/components/`

#### 3.3.1 聊天组件 (`chat/`)

| 组件 | 功能描述 |
|------|----------|
| `ChatStage.tsx` | 聊天主舞台，渲染消息列表 |
| `ChatInputBox.tsx` | 聊天输入框 |
| `StrategyCard.tsx` | 策略卡片组件，用户确认执行 |
| `StreamMessageRenderer.tsx` | 流式消息渲染器 |
| `StreamingMarkdown.tsx` | 流式 Markdown 渲染 |
| `MemoizedMessageItem.tsx` | 消息列表项（优化） |
| `VirtualizedMessageList.tsx` | 虚拟化消息列表 |
| `IntentCard.tsx` | 意图识别卡片 |
| `BlueprintCard.tsx` | 蓝图卡片 (PI Agent) |
| `ExecutionPlanCard.tsx` | 执行计划卡片 |
| `BattleReportCard.tsx` | 战报卡片 |
| `BookmarkPanel.tsx` | 书签面板 |
| `DAGCanvas.tsx` | DAG 可视化画布 |
| `QuickExecute.tsx` | 快速执行组件 |
| `InteractivePlotCard/` | 交互式图表卡片 |

#### 3.3.2 布局组件 (`layout/`)

| 组件 | 功能描述 |
|------|----------|
| `Sidebar.tsx` | 侧边栏导航 |
| `SessionSidebar.tsx` | 会话列表侧边栏 |
| `TopHeader.tsx` | 顶部标题栏 |

#### 3.3.3 覆盖层组件 (`overlays/`)

| 组件 | 功能描述 |
|------|----------|
| `SkillCenter.tsx` | 技能中心（统一入口） |
| `SkillCenter/SkillExecutePanel.tsx` | 执行面板 |
| `SkillCenter/MySkillsPanel.tsx` | 我的技能面板 |
| `SkillCenter/SkillMarketPanel.tsx` | 市场面板 |
| `SkillCenter/ForgePanel.tsx` | 工厂面板 |
| `SkillCenter/SettingsPanel.tsx` | 设置面板 |
| `SkillCenter/PendingDraftsList.tsx` | 待提交草稿 |
| `TaskCenter.tsx` | 任务中心 |
| `DataCenter.tsx` | 数据中心 |
| `ProjectCenter.tsx` | 项目中心 |
| `SettingsCenter.tsx` | 设置中心 |
| `UserCenter.tsx` | 用户中心 |
| `ControlPanel.tsx` | 控制面板 |
| `SuperExecutorPanel.tsx` | 超级执行器面板 |
| `WebTerminal.tsx` | Web Terminal |
| `ClaudeTerminal.tsx` | Claude Terminal |
| `ForgeOverlay.tsx` | 锻造覆盖层 |
| `CommandPalette.tsx` | 命令面板 |

#### 3.3.4 技能中心架构

```
SkillCenter.tsx (统一入口)
    │
    ├── SkillExecutePanel.tsx    # 执行 Tab
    ├── MySkillsPanel.tsx        # 我的 Tab
    ├── SkillMarketPanel.tsx     # 市场 Tab
    ├── ForgePanel.tsx           # 工厂 Tab
    └── SettingsPanel.tsx        # 设置 Tab
```

### 3.4 API 客户端

**文件路径**: `autonome-studio/src/lib/api.ts`

**核心功能**:

```typescript
// 动态获取后端 URL
export const BASE_URL = typeof window !== 'undefined'
  ? `http://${window.location.hostname}:8000`
  : 'http://localhost:8000';

// 通用请求方法
export async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  // 自动添加 JWT Token
  // 处理 FormData vs JSON
  // 统一错误处理
  // 401 自动跳转登录
}
```

---

## 4. 数据流与交互

### 4.1 策略卡片执行流程

```
┌──────────────────────────────────────────────────────────────────┐
│                    策略卡片执行流程                                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  用户输入                                                          │
│      │                                                             │
│      ▼                                                             │
│  ┌────────────────┐                                                │
│  │ Bot Agent      │                                                │
│  │                │                                                │
│  │ 1. 分析需求    │                                                │
│  │ 2. 调用探针    │                                                │
│  │ 3. 制定策略    │                                                │
│  └───────┬────────┘                                                │
│          │                                                         │
│          ▼                                                         │
│  输出:                                                              │
│  ```python                                                         │
│  # 完整可执行代码                                                   │
│  ```                                                               │
│                                                                    │
│  ```json_strategy                                                  │
│  {                                                                 │
│    "title": "数据提取",                                             │
│    "tool_id": "execute-python",                                    │
│    "steps": [...]                                                  │
│  }                                                                 │
│  ```                                                               │
│          │                                                         │
│          ▼                                                         │
│  ┌────────────────────┐                                            │
│  │ Frontend           │                                            │
│  │ StrategyCard.tsx   │                                            │
│  │                    │                                            │
│  │ 展示策略卡片        │                                            │
│  │ 等待用户确认        │                                            │
│  └────────┬───────────┘                                            │
│           │                                                        │
│           ▼ 用户点击"确认执行"                                       │
│  ┌────────────────────┐                                            │
│  │ Docker Sandbox     │                                            │
│  │ (bio_tools.py)     │                                            │
│  │                    │                                            │
│  │ 1. 创建容器        │                                            │
│  │ 2. 执行代码        │                                            │
│  │ 3. 返回结果        │                                            │
│  └────────────────────┘                                            │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 超级执行器流程 (Super Executor V4)

```
┌──────────────────────────────────────────────────────────────────┐
│                    Super Executor V4 流程                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  START                                                             │
│      │                                                             │
│      ▼                                                             │
│  ┌────────────────────┐                                            │
│  │ Phase 1: 探查阶段   │                                            │
│  │ phase_1_exploring   │                                            │
│  │                    │                                            │
│  │ 1. 生成探查代码     │                                            │
│  │ 2. 执行探查         │                                            │
│  │ 3. 获取文件结构     │                                            │
│  └────────┬───────────┘                                            │
│           │                                                        │
│           ▼                                                        │
│  ┌────────────────────┐                                            │
│  │ Phase 2: 安装依赖   │                                            │
│  │ phase_2_installing  │                                            │
│  │                    │                                            │
│  │ 1. 解析依赖         │                                            │
│  │ 2. Conda 安装       │                                            │
│  │ 3. 启用网络         │                                            │
│  └────────┬───────────┘                                            │
│           │                                                        │
│           ▼                                                        │
│  ┌────────────────────┐                                            │
│  │ Phase 3: 执行分析   │                                            │
│  │ phase_3_executing   │                                            │
│  │                    │                                            │
│  │ 1. 生成分析代码     │                                            │
│  │ 2. 执行 + 错误重试  │                                            │
│  │ 3. 生成战报         │                                            │
│  └────────┬───────────┘                                            │
│           │                                                        │
│           ▼                                                        │
│      COMPLETED                                                     │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

### 4.3 技能锻造流程

```
原始素材 (代码/文本)
    │
    ▼
┌─────────────────────────────────┐
│ forgeSessionApi.chatStream()    │
│ (流式对话锻造)                   │
└───────────────┬─────────────────┘
                │ SSE Stream
                ▼
┌─────────────────────────────────┐
│ Crafter Agent (crafter.py)      │
│                                 │
│ 1. 分析素材                     │
│ 2. 提取参数 Schema              │
│ 3. 重构代码 (参数化)            │
│ 4. 生成专家知识                 │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ 前端实时更新 Draft              │
│                                 │
│ - name, description             │
│ - parameters_schema             │
│ - script_code                   │
│ - expert_knowledge              │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ testDraftSkillStream()          │
│                                 │
│ 1. 自动生成测试数据             │
│ 2. 执行代码验证                 │
│ 3. 自动修复问题                 │
│ 4. 返回测试结果                 │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ commitSkill() / submitSkill()   │
│                                 │
│ 保存到数据库 / 提交审核         │
└─────────────────────────────────┘
```

### 4.4 三阶段技能推荐流程

```
用户查询
    │
    ├── 阶段1: 规则引擎 (<50ms)
    │   ├── 关键词匹配
    │   ├── 同义词扩展
    │   └── 置信度计算
    │
    ├── 阶段2: 向量检索 (~100ms)
    │   ├── embedding 计算
    │   └── pgvector 相似度搜索
    │
    └── 阶段3: LLM 精排 (~1-2s)
        ├── 候选技能排序
        └── 参数推断

推荐结果
    │
    ├── skill_id
    ├── skill_name
    ├── confidence
    └── suggested_parameters
```

---

## 5. 部署架构

### 5.1 Docker Compose 服务编排

**文件路径**: `docker-compose.yml`

| 服务名 | 容器名 | 端口 | 功能 |
|--------|--------|------|------|
| `backend-api` | `autonome-api` | 8000 | FastAPI 后端 |
| `frontend` | `autonome-web` | 3001 | Next.js 前端 |
| `postgres` | `autonome-postgres` | 5433 | PostgreSQL + pgvector |
| `redis` | `autonome-redis` | 6379 | Redis 缓存 |
| `backend-worker` | `autonome-worker` | - | Celery 异步任务 |

### 5.2 目录挂载

```yaml
volumes:
  # 数据持久化
  - postgres_data:/var/lib/postgresql/data
  - redis_data:/data

  # 用户上传文件
  - ./uploads:/workspace

  # Conda 环境 (持久化)
  - ./autonome_conda:/opt/conda

  # Docker Socket (沙箱执行)
  - /var/run/docker.sock:/var/run/docker.sock
```

### 5.3 启动命令

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker logs autonome-api | tail -30
docker logs autonome-web | tail -30

# 重启服务
docker-compose down && docker-compose up -d

# 进入容器调试
docker-compose exec backend-api bash
docker-compose exec postgres psql -U autonome autonome_db
```

---

## 附录：关键文件索引

### 后端核心文件

| 功能 | 文件路径 |
|------|----------|
| 主 Agent | `autonome-backend/app/agent/bot.py` |
| PI Agent | `autonome-backend/app/agent/pi_agent.py` |
| 首席 PI Agent | `autonome-backend/app/agent/chief_pi_agent.py` |
| 超级执行器 V4 | `autonome-backend/app/agent/super_executor_v4.py` |
| 技能锻造 Agent | `autonome-backend/app/agent/crafter.py` |
| 执行计划 | `autonome-backend/app/agent/execution_plan.py` |
| 步骤编排器 | `autonome-backend/app/agent/orchestrator.py` |
| 工具注册表 | `autonome-backend/app/agent/tools/registry.py` |
| 工具基类 | `autonome-backend/app/agent/tools/base.py` |
| Docker 沙箱 | `autonome-backend/app/tools/bio_tools.py` |
| 探针工具 | `autonome-backend/app/tools/probe_tools.py` |
| 技能解析器 | `autonome-backend/app/core/skill_parser.py` |
| 技能执行器 | `autonome-backend/app/services/skill_executor.py` |
| 技能统一匹配器 | `autonome-backend/app/services/skill_matcher.py` |
| 技能关键词索引 | `autonome-backend/app/services/skill_keywords_indexer.py` |
| 技能向量检索 | `autonome-backend/app/services/skill_vector_search.py` |
| LLM 技能匹配器 | `autonome-backend/app/services/llm_skill_matcher.py` |
| 技能注入器 | `autonome-backend/app/services/system_learning/skill_injector.py` |
| 成功评估器 | `autonome-backend/app/services/success_evaluator.py` |
| 数据模型 | `autonome-backend/app/models/domain.py` |

### 前端核心文件

| 功能 | 文件路径 |
|------|----------|
| 主页面 | `autonome-studio/src/app/page.tsx` |
| 聊天 Store | `autonome-studio/src/store/useChatStore.ts` |
| 技能中心 | `autonome-studio/src/components/overlays/SkillCenter.tsx` |
| 策略卡片 | `autonome-studio/src/components/chat/StrategyCard.tsx` |
| 超级执行器面板 | `autonome-studio/src/components/overlays/SuperExecutorPanel.tsx` |
| API 客户端 | `autonome-studio/src/lib/api.ts` |

---

*文档生成时间: 2026-04-09*
*维护者: Autonome Team*
