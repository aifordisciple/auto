
<autonome_architecture_v2>
  <document_meta>
    <title>Autonome Studio V2: 智能路由与沉浸式工作流架构设计</title>
    <objective>解决全能型Agent导致的响应延迟、上下文超载及交互割裂问题，构建基于“路由-专家”模式的动态自适应生信分析系统。</objective>
    <design_philosophy>
      1. 极速响应（TTFT < 0.5s）：意图拦截层与执行层物理隔离。
      2. 沉浸式交互（Flow State）：内联卡片替代全局弹窗，保持对话文脉连贯。
      3. 数据感知（Data-Aware）：所有推荐与执行均建立在文件与数据格式探查基础之上。
      4. 后台自愈（Self-Healing）：对模型生成的参数和代码提供验证与静默重试机制。
    </design_philosophy>
  </document_meta>

  <core_modules>
    <module id="router_node">
      <name>Supercharged Router (超极速路由节点)</name>
      <description>接收用户输入的第一道网关。使用轻量级模型（暂时用主模型），加载最小化上下文（仅最近2-3轮对话+当前高亮文件名），禁止加载全局文件树或技能库。</description>
      <output_schema>
        <intent_categories>
          <category name="CHAT">纯理论问答、概念解释、打招呼。（直接流式输出文本，无中断）</category>
          <category name="EXPLICIT_SKILL">选择了技能或明确指定调用某工具（如“跑一下 FastQC”）。</category>
          <category name="VAGUE_ANALYSIS">模糊的数据分析需求（如“对这个矩阵做聚类”）。</category>
          <category name="TROUBLESHOOT">报错排查与故障诊断。</category>
          <category name="SYSTEM_ACTION">系统级指令（如“清空临时文件”）。</category>
          <category name="PIPELINE_BUILD">跨越单技能边界的复杂蓝图构建需求。</category>
        </intent_categories>
      </output_schema>
    </module>

    <module id="retrieval_engine">
      <name>Data-Aware RAG (数据感知推荐引擎)</name>
      <description>当路由判定为分析需求时触发。检索不仅仅依赖自然语言向量匹配，必须前置融合“工作区数据状态”。</description>
      <execution_logic>
        <step>Shift-Left Probing (前置探针)：读取当前工作区选中文件的后缀及基础元数据（如 .h5ad, .fastq.gz）。</step>
        <step>Hybrid Match (混合匹配)：计算文本意图与文件类型的联合匹配度。</step>
      </execution_logic>
      <confidence_routing>
        <threshold condition="> 90%">高置信度。直接跳过技能选择菜单，下发具体技能的 Strategy Card 并预填参数。</threshold>
        <threshold condition="< 90%">中低置信度。下发 Inline Action Menu（内联选择卡片），提供 Top 2 技能选项及 Live Coding 兜底选项。</threshold>
      </confidence_routing>
    </module>

    <module id="interaction_ui">
      <name>Immersive Execution UI (沉浸式执行界面)</name>
      <description>前端对后端结构化数据的动态渲染引擎，消除系统级的遮罩弹窗。</description>
      <ui_components>
        <component type="Inline_Action_Menu">
          <trigger>推荐置信度不足时触发。</trigger>
          <behavior>在聊天气泡中渲染选项，用户点击后，卡片原地平滑展开为对应技能的 Strategy Card，不生成新的对话气泡。</behavior>
        </component>
        <component type="Strategy_Card">
          <trigger>用户选定技能或系统高置信度命中时触发。</trigger>
          <features>
            <feature name="Smart_Auto_fill">自动推断并填入依赖文件和默认参数。UI 需使用高亮（如蓝色微光）标识“AI预填项”。</feature>
            <feature name="Self_Validation">必填参数校验。若缺失参考基因组等文件，直接在输入框旁渲染“让AI扫描全盘”或“从公共库下载”的快捷操作按钮。</feature>
            <feature name="Multimodal_Correction">支持用户通过输入自然语言（如“把分辨率改为0.4”）动态刷新卡片内部参数状态，无需重新生成卡片。</feature>
          </features>
        </component>
      </ui_components>
    </module>

    <module id="execution_engine">
      <name>Transparent Executor (透明执行引擎)</name>
      <description>处理 Live Coding 与沙箱执行任务，消除黑盒等待焦虑。</description>
      <mechanisms>
        <mechanism name="Thought_Streaming">
          在执行耗时探查（peek_tabular_data）或编写代码时，前端渲染科技感迷你终端，实时推送日志（如“[Agent] 正在探查前 5 行...发现 20000 个基因”），实现状态外显。
        </mechanism>
        <mechanism name="Silent_Retry">
          沙箱执行 Live Coding 代码时，若遇到数据类型/键值错误，由 Executor Agent 拦截报错并在后台静默重试（上限2次）。彻底失败后才抛出排错卡片。
        </mechanism>
      </mechanisms>
    </module>
  </core_modules>

  <user_journey_specification>
    <scenario>模糊分析需求 + 参数口语微调</scenario>
    <flow>
      <step time="0.0s">用户输入：“我刚传了一个肿瘤矩阵，用最新的算法跑一下聚类，顺便帮我把那些噪音细胞去掉。”</step>
      <step time="0.3s">[Router Node] 判定意图为 VAGUE_ANALYSIS，提取实体 {肿瘤矩阵, 聚类, 去噪}。</step>
      <step time="0.8s">[Retrieval Engine] 探针感知到 tumor_matrix.h5ad。置信度 92% 命中 `Scanpy_Advanced_Clustering` 技能。</step>
      <step time="1.0s">[Interaction UI] 聊天流中顺滑展开 Strategy Card。输入文件自动高亮预填 tumor_matrix.h5ad；过滤参数自动勾选“去除线粒体高表达细胞”。</step>
      <step time="5.0s">用户口语指令：“分辨率调到 0.4”。系统拦截文本，卡片内的 Resolution 滑块自动更新为 0.4。</step>
      <step time="8.0s">用户点击 Run。[Execution Engine] 接管，输出流式状态日志（正在启动 Docker -> 正在降维）。</step>
      <step time="... ">任务完成，卡片折叠为成功状态，原地渲染可交互的 UMAP 图形卡片。</step>
    </flow>
  </user_journey_specification>
</autonome_architecture_v2>



---

### 阶段一：后端重构 - 极速路由节点 (The Supercharged Router)

**目标**：剥离原 `bot.py` 中的“全能型胖 Agent”，引入极速路由层，实现意图与执行的解耦。


```markdown
<task>
重构 LangGraph 工作流的入口节点，实现基于大模型结构化输出的“极速路由（Router）”机制，替代原有的单节点巨型 Prompt 解析。
</task>

<context>
当前 `app/agent/bot.py` 中的 `build_bio_agent` 将所有的工具、技能描述、目录树塞入了一个 System Prompt，导致响应极慢且容易格式错乱。我们需要引入一个轻量级的 Router Node 作为 LangGraph 的第一个节点（START -> router）。
</context>

<files_to_modify>
- `autonome-backend/app/agent/bot.py` (或新建 `autonome-backend/app/agent/nodes/router.py`)
- `autonome-backend/app/agent/schemas.py` (用于定义新的 Pydantic 模型)
</files_to_modify>

<requirements>
1. 在 `schemas.py` 中定义 Pydantic 模型 `IntentClassification`：
   - 字段 `intent`: Enum，包含 `CHAT`, `EXPLICIT_SKILL`, `VAGUE_ANALYSIS`, `TROUBLESHOOT`, `SYSTEM_ACTION`, `PIPELINE_BUILD`。
   - 字段 `entities`: Dict，提取关键实体（如文件名、算法名）。
   - 字段 `reason`: String，简短的判断理由。
2. 实现 `router_node(state: AgentState)` 函数：
   - **严禁**在此节点注入全量技能库和文件树。
   - 仅截取 `state["messages"]` 的最后 3 轮对话。
   - 使用 `llm.with_structured_output(IntentClassification)` 强制模型输出 JSON。
   - 提示词需极简（<200 tokens），例如：“你是一个生信系统的路由网关。请根据用户输入和当前高亮的文件，判断其核心意图。”
3. 在 LangGraph 的 `StateGraph` 中更新边（Edges）：
   - 使用 `add_conditional_edges`，根据 router 输出的 intent 决定下一个节点（如 `CHAT` 走向 `chat_node`，`VAGUE_ANALYSIS` 走向 `retrieval_node`）。
</requirements>

<expected_output>
完成 `router_node` 的代码编写，并成功将其集成到 `StateGraph` 中。要求去除原代码中要求模型输出 ` ```json_intent ` 的正则表达式逻辑，完全改用 Pydantic 结构化输出。
</expected_output>
```

---

### 阶段二：后端升级 - 数据感知推荐引擎 (Data-Aware RAG)

**目标**：让 AI 在推荐技能前，先“看一眼”用户手头的数据格式，并输出带置信度的推荐结果。


```markdown
<task>
升级 `retrieval_node` (技能推荐节点)，引入“前置探针（Shift-Left Probing）”机制和“置信度评分”，实现数据感知的 RAG。
</task>

<context>
系统现有的技能匹配仅依赖自然语言向量检索，容易给单细胞数据推荐 Bulk RNA 流程。我们需要在检索前，结合当前工作区的文件扩展名进行过滤，并根据匹配度决定下发策略卡片还是多选项菜单。
</context>

<files_to_modify>
- `autonome-backend/app/services/skill_matcher.py` (或负责检索的逻辑文件)
- `autonome-backend/app/agent/nodes/knowledge.py` (处理检索结果的节点)
</files_to_modify>

<requirements>
1. 实现数据探针逻辑：
   - 提取 `state["physical_file_info"]` 中的文件扩展名（如 `.h5ad`, `.fastq.gz`）。
2. 改造匹配引擎 (`match_skills`)：
   - 基于提取的文件扩展名，优先过滤或加权那些明确支持该数据类型的 SKILL。
   - 返回结果必须包含 `confidence_score` (0-1.0 浮点数)。
3. 改造路由决策逻辑：
   - 若最高 `confidence_score > 0.90`：直接生成并下发对应技能的 ` ```json_strategy `。
   - 若最高 `confidence_score <= 0.90`：收集 Top 2 的技能，构造并下发一种新的 Markdown 块标记 ` ```json_action_menu `，格式需包含选项列表（附带置信度）和一个 `Live Coding` 的保底选项。
</requirements>

<expected_output>
后端能够稳定地根据输入文件类型调整推荐结果。遇到模棱两可的需求时，能正确输出包含备选项的 `json_action_menu` 字符串块，而不是盲目下发单一的 strategy。
</expected_output>
```

---

### 阶段三：前端重构 - 沉浸式内联交互 UI (Immersive Action Menu)

**目标**：拦截后端的 `json_action_menu`，在聊天气泡中渲染优雅的选项卡，拒绝全局弹窗。


```markdown
<task>
在前端消息解析器中新增对 `json_action_menu` 的拦截渲染，并实现内联的技能选择交互。
</task>

<context>
为了避免弹窗打断用户心流，当后端推荐置信度不足时，会下发一个 `json_action_menu`。前端需要将其渲染为一个列表组件。用户点击其中一个选项后，组件应当**原地平滑切换**为对应的 Strategy Card 或触发 Live Coding 请求。
</context>

<files_to_modify>
- `autonome-studio/src/components/chat/MemoizedMessageItem.tsx` (或消息流拦截器)
- `autonome-studio/src/components/chat/components/InlineActionMenu.tsx` (需新建)
</files_to_modify>

<requirements>
1. 在正则拦截器中添加对 ` ```json_action_menu ` 的解析。
2. 新建 `InlineActionMenu` 组件：
   - 接收解析后的 JSON 数据（包含 title, options 数组）。
   - 渲染为风格类似 Claude Code 的优雅列表（每个选项显示技能名称和匹配度徽章）。
   - 包含一个固定在底部的 `⚡ 实时编写代码 (Live Coding)` 按钮。
3. 交互逻辑：
   - 点击选项后，不要发送可见的新聊天消息。
   - 静默调用后端 API `/api/skills/{skill_id}/generate_strategy`（或向当前会话推送一个隐藏的系统指令），获取该技能的预填参数 Strategy Card。
   - 拿到数据后，将当前 `InlineActionMenu` 组件的局部状态切换为渲染 `StrategyCard` 组件，实现视觉上的“卡片展开”效果。
</requirements>

<expected_output>
在前端测试时，遇到多个备选技能时，聊天框内渲染选项列表。点击后，列表平滑展开为对应技能的参数配置表单（Strategy Card），无页面跳转或遮罩层。
</expected_output>
```

---

### 阶段四：前端/后端联合 - 参数智能预填与动态纠偏 (Smart Auto-fill & Correction)

**目标**：AI 自动填写表单，且允许用户用口语直接修改卡片内的参数。


```markdown
<task>
增强 Strategy Card (策略卡片) 的状态管理与渲染逻辑，实现参数的“AI 置信度视觉提示”与“基于后续聊天的动态更新”。
</task>

<context>
用户面对 Strategy Card 时，输入框已被 AI 预填。我们需要在视觉上区分“AI 填写的”和“用户手动的”。更重要的是，如果用户在卡片下方继续输入文本“把分辨率改成 0.4”，系统应直接更新这张卡片上的滑块，而不是再发一张新卡片。
</context>

<files_to_modify>
- `autonome-studio/src/components/chat/StrategyCard.tsx`
- `autonome-studio/src/store/useChatStore.ts`
- `autonome-backend/app/agent/nodes/chat.py` (处理口语指令纠偏)
</files_to_modify>

<requirements>
1. 视觉更新 (`StrategyCard.tsx`)：
   - 修改表单渲染逻辑，为 `parameters` 增加一个 `is_ai_inferred` 属性标记。若为 true，在输入框边缘加入微弱的蓝色描边或特定的✨图标。
2. 动态纠偏链路 (Zustand + Backend)：
   - 当 UI 上存在一张未执行的 Strategy Card 时，用户发送的新消息，后端需作为 `UI_UPDATE` 意图拦截（基于阶段一的 Router）。
   - 后端解析用户的纠偏意图（如“分辨率 0.4”），不输出新的策略内容，而是输出一个极简格式 ` 
http://googleusercontent.com/immersive_entry_chip/0

---

