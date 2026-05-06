# 技能创建 AI 化全流程设计

## 概述

将技能创建从当前"纯手动编辑"升级为"AI 驱动 + 人工审核"的混合模式。核心思路：**聊天为入口，Forge 为工作区，Skill Agent 为编排引擎**。用户用自然语言描述需求，Agent 自动生成代码和参数，用户在 Forge 中审核微调后发布。

### 设计目标

1. **简单**：自然语言即可启动创建，降低技能开发门槛
2. **强大**：AI 生成的代码经过静态检查和自动测试，质量有保障
3. **用户掌控**：Agent 每个阶段都可中断、修改、跳过，用户始终是决策者
4. **渐进式**：核心先行（代码+参数），文档和元数据按需补全

### 用户偏好清单

基于需求澄清，确定以下交互模式：

| 决策点 | 选择 |
|--------|------|
| AI 介入方式 | 混合模式：对话快速生成 + 手动精细调整 |
| 入口方式 | ABC 融合：聊天触发 + 引导式 + 自由画布，统一汇聚到 Forge |
| 主入口 | 聊天为入口，Forge 为工作区 |
| 生成策略 | 核心先行（代码+参数），文档/元数据按需补全 |
| 迭代方式 | 混合：聊天提意图 → AI 改代码 → 编辑器微调 → 测试 → AI 修复 |
| 验证方式 | 渐进式：静态检查 → 自动测试 → 真实数据验证 |
| 相似发现 | 可选发现：AI 推荐已有技能，但不阻塞创建流程 |

---

## 架构

```
用户聊天输入                    Skill Agent (LangGraph)
    │                              │
    │  "帮我做一个差异分析技能"       ├── 阶段1: 意图解析 + 相似技能检索
    │                              ├── 阶段2: 生成核心（代码+参数）
    │                              ├── 阶段3: 静态检查 + 自动修复
    │                              ├── 阶段4: 自动测试（可选）
    │                              └── 阶段5: 输出到 Forge
    │                                      │
    ▼                                      ▼
 主 Bot Agent ──────────────────────→ ForgeSession + 文件系统
    │                                      │
    │  "已为你生成技能骨架，打开查看"        ▼
    ▼                                  Forge 面板（审核+微调+发布）
 聊天回复 + "打开 Forge" 按钮
```

### 核心原则

- **Skill Agent 独立部署**：不混入主聊天 Agent，通过明确 API 接口通信
- **ForgeSession 是桥梁**：Agent 输出写入 ForgeSession（JSONB），Forge 面板读取展示
- **渐进式输出**：每个阶段完成即推送，用户不用等全流程跑完
- **用户可随时接管**：暂停 Agent，进入 Forge 手动编辑，再继续或放弃

---

## Skill Agent 状态机

Agent 按 6 个阶段流水线执行，每个阶段完成后推送结果并等待确认。

```
阶段1: 意图解析 (~2s)
  ├── 输入：用户自然语言描述
  ├── 处理：LLM 提取技能名、领域、输入输出、执行环境
  └── 输出：结构化意图 { name, domain, inputs, outputs, executor_type }

阶段2: 相似技能发现 (~1s, 可选跳过)
  ├── 输入：结构化意图
  ├── 处理：搜索已有技能（个人/团队/市场），向量相似度匹配
  └── 输出：推荐列表 [{ skill_id, name, similarity, reason }]
       → 用户选择：基于已有修改 / 全新创建

阶段3: 核心生成 (~10s)
  ├── 输入：意图 + 参考技能（如有）
  ├── 处理：LLM 生成 script 代码 + 参数 schema
  └── 输出：{ script_code, parameters_schema }
       → 推送到 ForgeSession，前端即时渲染

阶段4: 静态检查 (~2s)
  ├── 输入：生成的代码
  ├── 处理：安全扫描（硬编码密钥、exec/eval）+ 语法检查 + 参数合理性
  ├── 失败时：自动修复（最多 3 轮），将错误信息喂回 LLM
  └── 输出：{ passed, issues[], fix_attempts }

阶段5: 自动测试 (~30s, 可选跳过)
  ├── 输入：代码 + 参数
  ├── 处理：AI 生成模拟输入 → Docker 沙箱执行 → 检查输出
  └── 输出：{ passed, output, error_log, suggestions[] }

阶段6: 输出到 Forge (~1s)
  ├── 处理：写入 ForgeSession + 文件系统 + DB 索引
  └── 输出：{ forge_url, session_id }
```

### 交互规则

- **可中断**：每个阶段完成后 Agent 等待确认，用户可暂停/跳过/修改后重做
- **补全按需触发**：文档、标签、元数据不在自动流水线中，用户在 Forge 中点击「AI 补全」按钮或在聊天中触发
- **迭代闭环**：修改后测试失败 → 错误自动送入 Agent → 分析建议修复 → 用户确认后应用

---

## Forge 面板重设计

### 布局变化

原 4 个独立 Tab（编辑/配置/元数据/测试）→ **双栏布局**：

```
┌──────────────────────┬──────────────────────────┐
│  AI 助手面板          │  代码/参数编辑器          │
│                      │                          │
│  ┌────────────────┐  │  [main.py] [SKILL.md]    │
│  │ AI: 已生成差异   │  │  [参数]                  │
│  │ 表达分析技能...  │  │                          │
│  │                │  │  def run_de_analysis():  │
│  └────────────────┘  │    ...                   │
│  ┌────────────────┐  │                          │
│  │ 用户: 加一个    │  │                          │
│  │ pvalue 阈值     │  │                          │
│  └────────────────┘  │                          │
│  ┌────────────────┐  │                          │
│  │ AI: 已更新      │  │                          │
│  └────────────────┘  │                          │
│                      ├──────────────────────────┤
│  [输入框] [发送]     │ ✓ 语法  ✓ 安全  [▶ 测试] │
└──────────────────────┴──────────────────────────┘
```

### 关键变化

| 原有 | 新版 |
|------|------|
| 4 个独立 Tab | 双栏：AI 对话 + 代码编辑器 |
| 手动填写表单和编辑器 | AI 预填 + 用户微调 |
| AI 仅「推断参数」按钮 | AI 对话即交互界面 |
| SKILL.md 手动编辑 | 由系统从代码和参数自动生成 |
| 测试 Tab 手动操作 | 测试结果直接显示在底部状态栏 |

---

## 数据流与 API 设计

### SSE 流式推送

Agent 通过 SSE 将每个阶段的输出实时推送到前端：

```
POST /api/forge/agent/generate
  { user_input, chat_context?, base_skill_id? }
  → 创建 ForgeSession → 返回 session_id + SSE 通道

SSE 事件流:
  event: phase
  data: {"phase":"intent_parse","status":"done","result":{...}}

  event: phase
  data: {"phase":"core_generation","status":"streaming","chunk":"..."}

  event: phase
  data: {"phase":"forge_output","status":"done","forge_url":"..."}
```

### 三个核心 API

| API | 用途 | 输入 | 输出 |
|-----|------|------|------|
| `POST /forge/agent/generate` | 首次生成技能 | user_input, base_skill_id?, chat_context? | SSE 流 |
| `POST /forge/agent/iterate` | 迭代修改 | session_id, instruction, scope | SSE 流 |
| `POST /forge/agent/supplement` | 按需补全 | session_id, supplement_type | SSE 流 |

### ForgeSession 扩展字段

```json
{
  "skill_draft": {
    "...existing fields...": "",
    "agent_phase": "core_generation",
    "agent_history": [],
    "static_check_result": {},
    "auto_test_result": {},
    "source_skill_id": null
  }
}
```

---

## 异常处理与边界情况

### 失败恢复策略

| 场景 | 策略 |
|------|------|
| Agent 生成失败 | 自动重试 1 次 → 展示原始输出 + 错误说明 → 用户手动修复或重新描述 |
| 静态检查失败 | Agent 自动修复（最多 3 轮）→ 展示问题列表 → 用户手动修 |
| 自动测试失败 | 展示错误日志 + AI 分析 + 建议方案 → 用户选择修复/忽略/手动修 |
| 用户中断 | 保存当前状态到 ForgeSession → 继续/手动编辑/重新开始（数据不丢失） |
| SSE 连接中断 | 重连后从 ForgeSession 拉取最新状态，未完成阶段重新触发或手动继续 |
| 意图模糊 | Agent 回问关键问题（数据类型？期望输出？工具？），最多追问 3 轮 |
| skill_id 冲突 | Agent 自动追加后缀 + 提示用户可手动改名 |

### 超时策略

| 阶段 | 预计 | 超时 | 超时策略 |
|------|------|------|----------|
| 意图解析 | 2s | 10s | 跳过，进入手动引导 |
| 相似发现 | 1s | 5s | 跳过，直接创建 |
| 核心生成 | 10s | 30s | 重试 1 次，失败交用户 |
| 静态检查 | 2s | 10s | 跳过，标记未检查 |
| 自动测试 | 30s | 120s | 跳过，标记未测试 |

---

## 实施阶段

### Phase 1: Skill Agent 核心 (~2 周)

- 新建 `autonome-backend/app/agent/skill_creator.py` — LangGraph Agent 状态机
- 实现 6 阶段流水线：意图解析 → 相似发现 → 核心生成 → 静态检查 → 自动测试 → 输出
- 复用已有 `code_reviewer.py`、`skill_executor.py`、`skill_bundle_writer.py`
- 新增 SSE 推送机制

### Phase 2: API 层 (~1 周)

- 新增 `autonome-backend/app/api/routes/skills_forge_agent.py`
- 实现 `generate`、`iterate`、`supplement` 三个端点
- 扩展 `ForgeSession` 模型（新增 5 个字段）
- 集成 SSE 流式输出

### Phase 3: Forge UI 升级 (~2 周)

- 重构 `ForgePanel.tsx`：双栏布局取代 Tab 切换
- 新增 `AIAssistantPanel.tsx` — 左侧 AI 对话面板
- 升级 `SkillDraftEditor.tsx` — 支持流式渲染 Agent 输出
- 新增强化成状态栏（静态检查结果 + 测试状态）
- 聊天入口集成：「打开 Forge」按钮

### Phase 4: 迭代与补全 (~1 周)

- 实现 iterate 闭环：测试失败自动回传 → Agent 修复 → 用户确认
- 实现 supplement 功能：按需生成文档、标签、元数据、依赖
- 前端「AI 补全」按钮集成到编辑器和配置区域

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM 生成代码质量不稳定 | 用户信任度下降 | 静态检查 + 自动测试 + 用户最终审核 |
| 不同 LLM 能力差异 | Agent 行为不一致 | 支持模型切换，关键阶段可配置严格度 |
| ForgeSession 数据膨胀 | DB 性能下降 | 超过 30 天的草稿自动清理 |
| 用户过度依赖 AI | 不理解生成代码 | 专家知识面板展示代码解释 |
| Docker 沙箱自动测试不稳定 | 误报/漏报 | 失败不阻塞流程，用户可手动重测 |
