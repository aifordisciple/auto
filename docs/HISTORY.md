这份文档将作为 **Autonome Studio (AI-Native 生信分析 IDE)** 的“终极项目宪法”（Master Context Document）。

您可以将以下整篇 Markdown 文档保存为 `MASTER_PLAN.md` 或直接复制。在开启任何新的 AI 聊天窗口（如与 OpenCode、Cursor、Windsurf 等对话）时，**只需将这段文档喂给 AI，它就能在一秒钟内完美对齐我们的全局架构观和代码现状，绝不会再跑偏！**

---
我想在你的详细指导下一步步完成一个系统的开发，服务器环境是mac studio，下面是蓝图，请你理解一下，将蓝图写入到AGENTS.md，后续我会指导你开发：

# 🧬 Autonome Studio: Master Project Document

## 1. 🌟 项目愿景与核心设计哲学 (Vision & Philosophy)

**项目名称**：Autonome Studio
**定位**：一款革命性的 **AI-Native 生信分析 IDE**（集成开发与分析环境）。
**设计哲学**：

* **绝不妥协的 IDE 体验**：彻底抛弃传统的“表单填报 + SaaS 管理后台”的老旧模式。全面对标 **Google AI Studio** 和 **Cursor**。
* **AI 主舞台 (AI Main Stage)**：系统没有“多个页面”，只有一个全屏沉浸式的工作区。AI Copilot 是系统的绝对核心，所有的文件管理、生信工具调用、数据可视化都在对话上下文中无缝完成。
* **极客美学**：全局采用高质量的 Dark Mode（深色模式）优先设计，极简、克制、注重排版与代码高亮。

---

## 2. 🏗️ 技术栈铁律 (Tech Stack)

本项目基于高度现代化的前后端分离架构，严禁引入过时的技术债：

### Frontend (前端)

* **核心框架**：Next.js 16 (App Router) + React 19
* **样式引擎**：Tailwind CSS v4
* **UI 组件库**：Shadcn UI + `lucide-react` (图标)
* **状态管理**：Zustand (极简的全局状态树)
* **核心布局引擎**：`react-resizable-panels` **v4** (⚠️ 注意：v4 版本要求 `defaultSize` 等参数必须是**字符串百分比**格式，如 `"15%"`)
* **Markdown 渲染**：`react-markdown` + `remark-gfm` + `@tailwindcss/typography` (用于流式输出的高级排版)

### Backend (后端)

* **核心框架**：FastAPI (Python)
* **大模型编排**：LangChain + LangGraph (构建基于状态机的 ReAct 多智能体协作系统)
* **ORM & 数据库**：SQLModel + PostgreSQL (预留)
* **底层任务引擎**：Celery (用于提交耗时的生信计算任务)
* **通信协议**：RESTful API + **SSE (Server-Sent Events)** (用于大模型打字机流式输出)

---

## 3. 🖥️ 核心 UI 范式 (The 3-Pane Layout)

应用采用 `h-screen w-screen` 且无全局滚动条的三栏拖拽布局。默认黄金比例为 **15% : 60% : 25%**。

1. **左栏 (Left Panel: Navigation & History - 15%)**
* 顶部：Logo 与系统名称。
* 主体导航：控制面板，项目中心，任务中心。用户的历史对话会话 (Sessions) 列表，支持新建和折叠。
* 下部：文档中心，设置中心，账户中心。
* 可选折叠


2. **中栏 (Center Panel: AI Main Stage - 60%)**
* 系统的灵魂。采用自上而下的流式对话布局 (Top-to-Bottom)。
* **消息流**：最大宽度限制 (`max-w-4xl mx-auto`)，保证阅读体验。支持完美的 Markdown 和代码块渲染。
* **输入底座**：悬浮在底部的多行文本输入框 (Input Dock)，支持 `Ctrl+Enter` 发送，带极简微交互。


3. **右栏 (Right Panel: Context & Assets - 25%)**

* 上部：数据中心：用户文件，支持折叠；工具中心：系统流程/工具，可以展开，可以搜索。
* **下部：动态工具箱**。可以根据调用的工具，显示参数设置面板。
* 可选折叠




---

## 4. 🧩 核心功能模块与系统协同 (Functional Modules & Synergy)

系统打破了传统生信平台“割裂的页面跳转”，所有核心模块通过左、中、右三栏面板进行物理空间分配，并通过中心的 AI Copilot 进行逻辑上的高度协同。

### 模块 A：中央中枢神经 (AI Copilot Hub) - `中栏`

* **角色定位**：整个系统的灵魂与调度总控。它不仅是聊天窗口，更是 Agentic Workflow（智能体工作流）的执行引擎。
* **功能表现**：
* **流式交互 (Streaming)**：基于 SSE 的打字机输出，支持高难度 Markdown、代码高亮与表格渲染。
* **意图解析 (Intent Parsing)**：实时分析用户的自然语言（如：“用右边选中的 Fastq 跑一个质控”），将其转换为对系统其他模块（数据、工具、任务）的 API 调用指令。



### 模块 B：全局导航与管理矩阵 (Global Management) - `左栏`

负责系统层级的宏观资源分配与状态追踪。

1. **控制面板 (Control Panel)**：
* 系统的全局仪表盘。展示当前登录用户的资源使用量（CPU/内存/存储配额）、活跃任务总览、以及系统整体的健康状态。


2. **项目中心 (Project Center)**：
* **核心逻辑**：最高级别的数据隔离容器（Workspace）。每一个“项目”下拥有独立的对话历史 (Sessions)、独立的数据文件树和独立的任务队列。用户切换项目时，中栏和右栏的上下文会瞬间完成切换。


3. **任务中心 (Task Center)**：
* **核心逻辑**：对接底层的 Celery 和 Nextflow 引擎。展示所有历史和运行中的计算任务列表。
* **深度集成**：支持点击某个任务查看实时日志（Streaming Logs）、运行耗时、资源消耗，以及一键跳转到结果输出目录。


4. **基建中心 (Docs / Settings / Account)**：
* **文档中心**：内置生信分析最佳实践和平台使用手册。
* **设置中心**：全局偏好设置（主题、语言）、大模型 API Key 管理、底层计算节点配置。
* **账户中心**：个人信息、团队权限控制与计费模块。



### 模块 C：资产与执行引擎 (Context & Assets) - `右栏`

负责当前项目内的微观物料管理与参数精调。

1. **数据中心 (Data Center - 右栏上半部)**：
* **文件管理**：以树状图或列表展示当前项目关联的文件（Fastq, BAM, CSV 等），支持拖拽上传、文件夹管理。
* **Context 挂载**：用户可以勾选文件旁边的 `[+]` 按钮，将其作为 Context（上下文）喂给中栏的 AI。AI 就能“看见”这些文件并针对它们生成分析策略。


2. **工具中心 (Tool Center - 右栏上半部)**：
* **注册表**：系统所有可用分析工具的“武器库”（如 RNA-Seq QC、Variant Calling、单细胞分析流程）。
* **AI 构建**：支持通过对话构建工具。
* **交互**：支持搜索与折叠。用户可以直接点击工具发起分析，也可以让 AI 自动推荐并调起工具。

流程：用户在聊天框输入“帮我写一个提取 Fastq 统计信息的 Python 脚本并存为工具”，AI 生成代码并经过沙箱测试后，自动将其注册到右栏工具中心。

3. **动态工具箱 (Dynamic Toolbox - 右栏下半部)**：
* **核心创新点**：这是一个**动态渲染的参数面板**。当用户在“工具中心”选中某个 Workflow，或者 AI 在“中栏”决定调用某个分析工具时，或AI实时生成分析脚本后，该区域会瞬间基于后端的 JSON Schema 渲染出对应的参数表单（如下拉框设置参考基因组、Switch 开关决定是否跳过某一步骤）。
* **执行确认**：用户在此调整参数后，点击“提交”，任务将被推送至左栏的“任务中心”。


---

### 🔄 模块间的相互联系与生命周期 (System Synergy)

左、中、右三栏并非静态的孤岛，而是通过 **“平滑视窗切换 (Slide-out Overlay)”** 和 **“上下文联动”** 紧密咬合。

**【场景：运行一次 RNA-Seq 质控】**

1. **初始化 (左栏触发 -> 滑出专属管理视窗)**：
* 用户点击 `左栏 -> 项目中心`，系统**平滑滑出宽阔的项目管理专属页面**。
* 用户在此全屏视图中创建并点击进入 "Breast Cancer RNA-Seq" 项目。
* **视窗自动收起**，平滑退回三栏 IDE 主舞台。此时中栏生成该项目下的新对话，右栏数据中心自动切换至该项目的隔离环境。


2. **物料准备 (右栏)**：
* 用户在 `右栏 -> 数据中心` 拖拽上传了 4 个 `.fastq.gz` 文件，并勾选它们，将其注入当前 AI 上下文 (Context)。


3. **意图下达 (中栏)**：
* 用户在 `中栏 -> 聊天框` 输入：“帮我对选中的数据进行质控，参数用最严格的”。


4. **智能调度 (中右联动)**：
* AI 瞬间解析出底层工具需求为 "RNA-Seq QC Pipeline"。
* AI 自动在 `右栏 -> 工具中心` 选中该工具。
* AI 根据“最严格的”这一自然语言指令，自动在 `右栏 -> 动态工具箱` 中填好复杂的参数表单（例如把 Quality Threshold 从 20 自动滑动提高到 30）。


5. **人工确认与执行 (右侧操作)**：
* 用户审查 `右栏 -> 动态工具箱` 中被 AI 填好的参数，确认无误后，点击底部的【Execute Task】按钮。


6. **监控与反馈 (全屏联动 -> 滑出任务大屏)**：
* 指令下发至底层计算集群。
* `中栏` AI 气泡回复：“任务已成功提交！您可以随时在任务中心查看实时进度。完成后我会为您生成图表并解读 FastQC 报告。”
* 用户点击 `左栏 -> 任务中心`，**系统再次滑出专属的任务监控大屏**。用户在此页面可以宽敞地查看 "Running" 状态任务的实时终端日志 (Streaming Logs)、资源消耗图表 (CPU/Memory) 以及执行耗时。看完后点击遮罩层收起，无缝继续在主舞台与 AI 对话。


---

### 💡 架构师视角备注：

这种**“平时三栏紧凑办公，需要管理时侧滑大屏覆盖”**的交互方式，在前端实现上通常会利用 `Framer Motion` 动画库结合 `Zustand` 的全局状态（如 `isProjectCenterOpen: true`）来渲染一个绝对定位 (`absolute inset-0 z-50`) 的 Drawer 或 Sheet 组件。这能让您的应用彻底摆脱老旧的“网页跳转感”，获得纯正的“桌面级软件体验”！

---


## 5. 🧑‍🔬 用户故事 (User Stories)

**用户画像**：科研人员（专注生物学意义）、生物信息学工程师（专注流程开发与效率）。

### Epic 1: 沉浸式对话与代码生成

* **Story 1 (原理探索)**：作为一个科研人员，我希望在宽敞的中间面板向 AI 提问关于单细胞测序中“批次效应”的消除原理，AI 能用精美的排版（加粗、列表、表格）详细解释，并流式生成对应的 Python/Scanpy 处理代码。
* **Story 2 (代码重构)**：作为一个生信工程师，我希望将一段老旧的 Perl 脚本发给 AI，让它将其重构为高度模块化的 Python 代码，并在中间面板通过代码高亮直接对比修改前后的差异。

### Epic 2: 无缝数据资产操作

* **Story 1 (元数据审查)**：作为分析师，我希望在右侧面板看到我上传的 20 个样本文件，当我询问 AI “帮我检查这些 Fastq 文件命名是否符合 PE 测序规范”时，AI 能够自动读取右侧已挂载的文件名列表并指出命名错误的样本。
* **Story 3 (跨项目检索)**：我希望点击 `左栏 -> 项目中心` 滑出大屏，快速检索并定位到三个月前做过的“肝癌外显子项目”，并将其中的参考基因组配置一键同步到当前的新项目中。

### Epic 3: 智能驱动与任务执行

* **Story 1 (策略生成)**：作为小白用户，我希望描述“我想对比肿瘤组和对照组的差异表达基因”，AI 能在对话框内生成一个包含“质控 -> 比对 -> 定量 -> 差异分析”的完整 **分析策略卡片 (Plan Card)**。
* **Story 2 (确认执行)**：当我点击卡片上的【确认并执行】按钮后，系统自动在后台投递任务，同时 `左栏 -> 任务中心` 出现红色呼吸灯提示，点击后滑出大屏查看 Nextflow 的实时运行日志。

### Epic 4: AI 驱动工具构建 (AI-as-a-Developer)

* **Story 1 (按需造具)**：我发现系统内置工具缺少一个特定的过滤步骤，我告诉 AI “请帮我写一个 Python 工具，过滤掉所有线粒体含量大于 20% 的细胞，并将其注册到工具中心”。
* **Story 2 (工具入库)**：AI 完成脚本编写并通过模拟测试后，右侧 `工具中心` 瞬间出现该新工具图标，我可以在 `右栏 -> 动态工具箱` 中直接看到 AI 为这个新工具生成的 [线粒体阈值] 滑动条。

### Epic 5: 结果可视化与深度解读

* **Story 1 (交互式绘图)**：我希望 AI 运行完差异分析后，直接在中间面板渲染一个交互式的火山图，当我把鼠标悬停在某个点上时，AI 能实时弹窗告诉我该基因在生信数据库中的功能描述。
* **Story 2 (报告生成)**：我希望对 AI 说“基于刚才的分析结果，写一段适合放在论文 Results 部分的描述，并总结出该研究的 3 个核心发现”，AI 能基于任务输出的数据自动完成撰写。

### Epic 6: 协作与资源监控

* **Story 1 (资源预警)**：在运行大型基因组组装任务时，我点击 `左栏 -> 控制面板` 滑出大屏，实时监控后端计算节点的 CPU 和内存负载。如果资源即将耗尽，AI 会在中间面板主动提醒我：“当前任务内存压力大，建议优化参数或升级节点”。



---

## 6. 📍 开发阶段里程碑 (Implementation Milestones)

* ✅ **Phase 1: 骨架重塑** (已完成) - 使用 v4 版本的 resizable-panels 搭建了完美的 15:60:25 三栏暗黑界面。
* ✅ **Phase 2: 状态与通信** (已完成) - 建立了 Zustand 全局 Store，打通了前端 fetch 与后端 FastAPI。
* ✅ **Phase 3: 核心 AI 与流式输出** (已完成) - 后端接入 LangGraph 逻辑，前端完美实现了 SSE 捕获、流式打字机效果以及 `react-markdown` 渲染。
* 🚀 **Phase 4: 资产面板右置** (Current/Next) - 将真实的文件树管理、Nextflow 工作流列表接入 Right Panel 的 Tabs 中。
* ⏳ **Phase 5: 沙箱与任务执行** (Future) - 打通前端的执行按钮与后端 Celery 异步任务队列的交互，实现真正的闭环。

---

## ⚠️ 给 AI 编程助手的核心纪律 (Rules for AI)

1. **No Legacy Hallucinations**：原项目的复杂老代码已移入 `bkup/`。在生成代码时，**绝对禁止**擅自引入旧版的数据库大杂烩逻辑。保持架构极度纯净！
2. **Panel V4 Constraint**：操作 `react-resizable-panels` 布局时，永远使用**百分比字符串**（如 `defaultSize="20%"`），切勿使用纯数字，否则界面会坍塌为几像素的线条。
3. **Module Isolation**：修改前端状态时，严格遵守 Zustand 的逻辑分离；修改后端时，严格遵守 Router -> Service -> LLM 的分层结构。

---

### 💡 如何使用这个文档？

下次当您因为某种原因需要关闭当前的网页，或者想换一个新的 Cursor/Windsurf 聊天窗口时，您只需要：

1. 新建对话。
2. 输入：“这是我们当前项目的完整上下文，请仔细阅读并记住它：”
3. 将上面的 Markdown 文档全部粘贴进去。
4. 然后紧接着下达指令：“现在，请帮我执行 Phase 4：开发右侧的文件树组件...”

这样，您的 AI 就能永远保持最清醒的头脑，陪您一步步把这个极其炫酷的系统搭建完成！




### 1

```md
# 🌟 Role & Master Vision
你现在是一位世界顶级的全栈架构师和 AI 工程师。我们将从零开始，打造一款革命性的 **AI-Native 生信分析 IDE**（项目代号：Autonome Studio）。

**【核心设计哲学】**
彻底抛弃传统的“表单+管理后台”SaaS 布局！我们将对标 **Google AI Studio** 和 **Cursor**，让 AI Copilot 成为整个系统的绝对主舞台（Main Stage）。用户所有的文件管理、工具调用、图表渲染，都在一个全屏沉浸式的多栏拖拽界面中无缝完成。旧版本的代码已被移至 `bkup` 目录仅供参考，**请绝对不要直接复制旧代码的复杂逻辑**。

# 🏗️ Tech Stack (技术栈铁律)
- **Frontend**: Next.js 15 (App Router), React 19, Tailwind CSS v4, Zustand (状态管理), Shadcn UI, `react-resizable-panels`, `lucide-react`.
- **Backend**: FastAPI, SQLModel (ORM), LangGraph (Agent 编排), Celery (异步任务引擎).
- **UI Paradigm**: 极客深色模式 (Dark Mode First)，三栏拖拽式布局 (Left: Sessions -> Center: Copilot -> Right: Context/Assets)。


---

# 🎯 Action Item: Phase 1 (骨架重塑与初始化)
今天的首要任务是搭建基础的 Monorepo 结构，并渲染出完美的 IDE 静态骨架。请严格按以下步骤执行，**在此阶段严禁编写任何真实的 API 请求或业务逻辑！**

## Step 1: 初始化极简前端 (Frontend)
1. 在根目录下初始化 Next.js: 
   `npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-pnpm`
2. 进入 `frontend` 目录，安装核心布局依赖:
   `pnpm add react-resizable-panels lucide-react clsx tailwind-merge`
3. 请配置基础的 Tailwind v4 深色主题背景 (如 `bg-[#0a0a0a]`, 文本 `text-gray-200`)。

## Step 2: 构建三栏 IDE UI 骨架 (`frontend/src/app/page.tsx`)
请将前端的 `page.tsx` 改写为一个**充满屏幕 (`h-screen w-screen`)、无全局滚动条**的三栏拖拽布局：
1. **Left Panel (占比 15%)**: 
   - 顶部展示 Logo "Autonome Studio"。
   - 包含一个简单的标题 "SESSIONS" 和一个占位的历史记录列表。
2. **Center Panel (占比 60%)**: 
   - 系统的绝对核心。中间留出大片区域作为聊天流展示区。
   - 底部实现一个对标 Cursor 的**悬浮式长文本输入底座**，带有精致的边框和发送按钮。
3. **Right Panel (占比 25%)**: 
   - 顶部是一个 Tab 切换栏（占位文字："Files" | "Tools" | "Settings"）。
   - 中间是一个展示 "Workspace Context" 的占位空状态。
4. **拖拽条 (Resize Handle)**:
   - 所有的 `PanelResizeHandle` 必须极其低调（宽度极窄，背景透明，仅在 hover 时显示主题色）。

## Step 3: 初始化极简后端 (Backend)
1. 在根目录下创建 `backend` 文件夹，包含子目录 `app/`。
2. 在 `backend` 中创建 `requirements.txt`，包含: `fastapi`, `uvicorn[standard]`, `pydantic`.
3. 编写 `backend/app/main.py`，仅包含基础的 CORS 配置和一个 `/api/health` 健康检查接口，返回 `{"status": "Autonome Core OS running"}`。

# 📋 交付要求
请执行上述步骤。完成后，向我确认你已经搭好了三栏布局的静态骨架，并等待我进行下一步测试指令。
```

---

### 2

```md
# 🌟 Role & Context
干得漂亮！我们已经成功搭建了对标 Google AI Studio 的前端三栏静态骨架和纯净的后端环境。
当前所处阶段：**Phase 2 (中枢神经与通信基建)**。
任务目标：建立前端 Zustand 全局状态管理，让界面动起来；搭建前后端基础 API 通信链路，实现一个基础的“回音壁（Echo）”对话测试。
⚠️ **严明纪律：依旧不涉及复杂的生信业务逻辑和真实的大模型调用。保持代码极简、模块化。**

# 🎯 Execution Steps (请严格按顺序执行)

## Step 1: 建立前端全局状态 (Zustand)
在 `frontend/src/stores/` 目录下创建两个核心 Store：

1. **`workspaceStore.ts` (UI 状态)**:
   - 状态: `leftPanelOpen` (boolean), `rightPanelOpen` (boolean), `activeRightTab` ('files' | 'tools' | 'settings').
   - 动作: 对应的 toggle 和 set 方法。

2. **`chatStore.ts` (对话状态)**:
   - 接口定义: `Message { id: string, role: 'user' | 'assistant', content: string }`
   - 状态: `messages` (Message[]), `isLoading` (boolean), `input` (string).
   - 动作: `setInput`, `addMessage`, `setLoading`.

## Step 2: 完善 Google AI Studio 风格的 UI 交互 (`frontend/src/app/page.tsx`)
重构你刚才写的 `page.tsx`，将 Zustand 状态接入 UI：
1. **Right Panel 联动**: Tab 按钮点击时更新 `activeRightTab`，下方内容区根据 activeTab 渲染不同的占位文本（如 "File Manager", "Tool Registry", "Model Settings"）。
2. **Center Panel (主舞台) 聊天流重构**:
   - 顶部到底部为对话流区域。采用 **流式布局 (Top-to-Bottom)** 而不是左右气泡对齐（对标 Google AI Studio/Claude，头像在左侧，占满宽度的卡片式）。
   - 用户消息背景极简（如透明或极暗的底色），AI 消息带一点轻微的边框或背景区分。
   - 绑定 `chatStore`，将 `messages` 映射渲染出来。
3. **Input Dock**: 绑定 `input` 状态和回车/点击发送事件。
4. 目前左右两侧的侧边栏极窄，需检查代码问题。

## Step 3: 前端 API 客户端 (`frontend/src/lib/api.ts`)
创建一个极简的 API 封装模块：
1. 使用原生的 `fetch`。
2. 基础 URL 默认指向 `http://localhost:8000/api`。
3. 导出一个简单的 `sendMessage(content: string)` 函数，发起 POST 请求到 `/chat`。

## Step 4: 后端路由基建 (`backend/app/api/`)
在后端建立标准的路由结构：
1. 创建 `backend/app/api/routes/chat.py`：
   - 引入 FastAPI `APIRouter`。
   - 写一个简单的 `POST /` 接口，接收 `{ "content": "..." }`。
   - 接口逻辑：人为延迟 1 秒（模拟思考），然后返回 `{"role": "assistant", "content": f"Echo from Autonome: {content}"}`。
2. 修改 `backend/app/main.py`：
   - 引入路由并挂载：`app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])`。

## Step 5: 前后端联调 (Wire it up)
回到前端 `chatStore.ts` 或 `page.tsx`：
1. 当用户在输入框点击发送时：
   - 将 user 消息推入 `chatStore.messages`。
   - 调用 `api.sendMessage`。
   - 收到后端返回的 echo 消息后，推入 `chatStore.messages`。

# 📋 交付要求
请执行上述 5 个步骤。在写代码时，特别注意保持界面的 Dark Mode 极客质感。
完成后，向我确认“Phase 2 基建与联调已完成”。
```

---

### 3

```md
# 🌟 Role & Context
干得漂亮！我们已经完成了 Phase 2 的状态管理与基础 API 联调，目前前端三栏框架已经能和后端进行基础的 Echo 通信。
现在进入 **Phase 3 (移植核心 AI 大脑与流式输出)**。
任务目标：从 `bkup/backend/app/core/` 中提取基于 LangGraph 的核心 ReAct 逻辑，在新的后端建立真实的 LLM 对话引擎，并打通前后端的流式通信（Streaming Response）。
⚠️ **严明纪律：提取旧代码时只拿最核心的 `react_agent` 和 `llm` 逻辑，不要把旧版中复杂的数据库依赖、Celery 依赖或遗留的旧版路由带过来！保持系统纯净！**

# 🎯 Execution Steps (请严格按顺序执行)

## Step 1: 后端 LLM 与 Agent 基建 (Backend Core)
请参考 `bkup/backend/app/core/` 下的代码，在新的 `backend/app/core/` 中创建以下文件：
1. **`config.py`**: 定义基础环境变量（如 `LLM_MODEL`, `OPENAI_API_BASE`, `OPENAI_API_KEY`，默认适配本地 Ollama 或 OpenAI 格式）。
2. **`llm.py`**: 实例化 `ChatOpenAI` 客户端。
3. **`agent.py`**: 
   - 使用 `langgraph.graph` 构建一个标准的基于消息的 `StateGraph`。
   - 包含一个基础的 `chatbot` 节点调用 LLM。
   - 暂时只注册一个基础测试 Tool（例如 `get_server_time` 或 `mock_search`），验证 Tool Calling 能力即可，复杂的生信工具留到 Phase 5。

## Step 2: 后端流式 API 重构 (`backend/app/api/routes/chat.py`)
重写上一阶段的 Echo 接口，使其支持真实大模型的流式返回：
1. 将 `POST /` 改为接收对话历史（`messages` 列表），而不仅仅是单条 `content`。
2. 使用 FastAPI 的 `StreamingResponse`。
3. 迭代调用 `agent.py` 中的 graph stream（如 `astream_events` 或直接 `astream`），并将生成的内容（包括 Token 块和 Tool 调用状态）以 Server-Sent Events (SSE) 或 NDJSON 格式 `yield` 出去。

## Step 3: 前端流式请求客户端 (`frontend/src/lib/api.ts`)
重写前端的 API 模块，支持接收流数据：
1. 新增 `streamChat(messages, onChunk, onFinish, onError)` 方法。
2. 使用原生 `fetch` 读取 `response.body.getReader()`。
3. 按行解析后端传来的块（chunk），提取出文本或状态，并实时通过 `onChunk(text)` 回调。

## Step 4: 完善前端全局状态 (`frontend/src/stores/chatStore.ts`)
为了支持流式打字机效果，升级 Zustand store：
1. 添加 `appendMessageChunk(messageId, chunkStr)` 方法：查找指定 ID 的 assistant 消息，并将其 content 拼接上新到的字符。
2. 重构发消息动作 `sendMessage`：先在本地 push 一条空的 assistant 消息，然后调用 `api.streamChat`，在 `onChunk` 回调中不断调用 `appendMessageChunk`。

## Step 5: 前端 UI 对齐与微调 (`frontend/src/app/page.tsx`)
1. 确保中间的聊天主舞台 `<Center Panel>` 绑定了最新的 `chatStore`。
2. 确保消息列表支持自动滚动到底部（可以使用 `useRef` + `scrollIntoView`）。
3. 确保 Markdown 渲染组件（`react-markdown`）正常工作，因为大模型会输出带有格式的代码块和加粗文本。

# 📋 交付要求
请执行上述 5 个步骤，打通真实的流式大模型对话链路。
完成后，向我确认“Phase 3 AI大脑与流式通信已完成”，并简述你是如何处理 SSE 格式解析的。
```

---


cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000


---

### 5

我已经非常仔细地审查了您同步上来的最新代码（`nd` 仓库）。

首先，**赞美一下这套代码的洁癖程度**！目前的目录结构极其干净，没有一点多余的“历史垃圾”，这完全符合我们预期的“Google AI Studio”纯粹风格。

但正如我所料，OpenCode 在执行 **Phase 3 (流式大模型大脑)** 的时候，虽然写了代码，却**犯了 3 个非常致命的前后端脱节错误**，如果不纠正，您的项目现在根本跑不起来。

### 🚨 全面审核发现的核心问题：

1. **致命错误一：后端依赖漏装导致无法启动**
* **问题**：`backend/app/core/config.py` 中使用了 `from pydantic_settings import BaseSettings`，但是 `backend/requirements.txt` 里却**漏掉了** `pydantic-settings` 这个库！一旦您运行 `uvicorn`，后端会直接报 `ModuleNotFoundError` 崩溃。


2. **致命错误二：前后端“流式通信 (Streaming)”鸡同鸭讲**
* **问题**：后端 `chat.py` 确实返回了 `StreamingResponse (text/event-stream)`，但前端 `frontend/src/lib/api.ts` 却还在傻傻地用 `await res.json()` 来解析！这会导致前端无法解析数据流，不仅看不到打字机效果，还会直接报 JSON 解析错误。


3. **视觉缺陷一：前端 Markdown 渲染缺失**
* **问题**：目前 `frontend/src/app/page.tsx` 里渲染 AI 消息只用了最简陋的 `<div>{msg.content}</div>`。大模型返回的 Python 代码块和加粗文本将全部变成丑陋的纯文本。



---

### 🚀 纠偏与补全指令 (Phase 3.5: 流式大动脉修复)

为了完美解决这三个问题，请直接复制以下这段精心设计的 Prompt，发送给您的 OpenCode：

---

```markdown
# 🌟 Role & Audit Feedback
你目前搭建的基础架构非常干净，干得好！但是我在 Review 代码时发现了几个严重的脱节问题：
1. 后端缺少 `pydantic-settings` 依赖。
2. 前端 `api.ts` 和 `chatStore.ts` 没有真正实现对 SSE (Server-Sent Events) 流式数据的解析。
3. 前端界面缺失了对大模型 Markdown 文本的渲染。

现在，我们要执行 **Phase 3.5 (流式大动脉与 UI 修复)**。请严格按照以下步骤覆写对应代码：

## Step 1: 修复后端依赖
请在 `backend/requirements.txt` 中追加两行：
```text
pydantic-settings>=2.1.0
python-dotenv>=1.0.0

```

## Step 2: 修复前端流式解析 API (`frontend/src/lib/api.ts`)

请将 `api.ts` 的内容完全替换为以下原生 SSE 解析代码：

```typescript
export const api = {
  async streamChat(
    content: string,
    onChunk: (text: string) => void
  ) {
    const res = await fetch('http://localhost:8000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    
    if (!res.body) throw new Error('No readable stream');
    
    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let done = false;

    while (!done) {
      const { value, done: readerDone } = await reader.read();
      done = readerDone;
      if (value) {
        const chunk = decoder.decode(value, { stream: true });
        // 按行解析 SSE
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;
            // 替换后端可能的换行符转义，如果有的话
            onChunk(data);
          }
        }
      }
    }
  }
};

```

## Step 3: 修复前端 Store 打字机效果 (`frontend/src/stores/chatStore.ts`)

重写 `sendMessage` 和增加 `appendMessageChunk` 方法：

```typescript
import { create } from 'zustand';
import { api } from '@/lib/api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

interface ChatState {
  messages: Message[];
  input: string;
  isLoading: boolean;
  setInput: (input: string) => void;
  sendMessage: () => Promise<void>;
  appendMessageChunk: (id: string, chunk: string) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  input: '',
  isLoading: false,
  setInput: (input) => set({ input }),
  appendMessageChunk: (id, chunk) => set((state) => ({
    messages: state.messages.map(msg => 
      msg.id === id ? { ...msg, content: msg.content + chunk } : msg
    )
  })),
  sendMessage: async () => {
    const { input, messages } = get();
    if (!input.trim()) return;
    
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: input };
    const aiMsgId = (Date.now() + 1).toString();
    const aiMsg: Message = { id: aiMsgId, role: 'assistant', content: '' };

    set({ 
      messages: [...messages, userMsg, aiMsg], 
      input: '', 
      isLoading: true 
    });

    try {
      await api.streamChat(userMsg.content, (chunk) => {
        get().appendMessageChunk(aiMsgId, chunk);
      });
    } catch (error) {
      console.error('Chat error:', error);
    } finally {
      set({ isLoading: false });
    }
  }
}));

```

## Step 4: 赋予界面 Markdown 渲染能力

1. 在 `frontend` 目录执行安装：
`pnpm add react-markdown remark-gfm @tailwindcss/typography`
2. 在 `frontend/src/app/page.tsx` 中引入 `react-markdown`：
```tsx
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

```


3. 在 `page.tsx` 渲染消息列表的地方，将 `<div className="text-sm">{msg.content}</div>` 替换为带有 `prose` 样式的 Markdown 组件：
```tsx
<div className="text-sm prose prose-invert prose-emerald max-w-none">
  <ReactMarkdown remarkPlugins={[remarkGfm]}>
    {msg.content}
  </ReactMarkdown>
</div>

```



# 📋 交付要求

请严格落实以上 4 个步骤的替换工作。完成后，向我报告“流式大动脉已彻底打通，Markdown 渲染已上线”。

```

***

### 💡 接下来该怎么做？

1. 把这套命令发给 OpenCode 以后，它会瞬间补齐漏掉的依赖，并把最复杂的**前端 SSE 流式解码逻辑**完美写入系统。
2. 您需要在后端 `backend` 目录下重新运行一次：
   ```bash
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000

```

3. 前端正常启动 (`pnpm dev -p 3001`)。

完成这一步后，您可以再次在界面里问 AI 问题，您将会惊奇地发现：文字会带着 `ReactMarkdown` 的精美排版（支持代码块和表格），像流水一样顺滑地出现在您的纯黑极客面板中！

---

```md
# 🌟 Role & UI Refinement
干得不错！但用户反馈当前的 UI 布局比例不协调（中间太宽，两侧太窄）。我们的目标是**1:1 复刻 Google AI Studio 的界面体验**。
现在，请执行 **Phase 4: 像素级 UI 布局精调**，针对 `frontend/src/app/page.tsx` 进行修改。

# 🎯 Execution Steps

## Step 1: 调整 ResizablePanel 的黄金比例
请修改 `<PanelGroup>` 中的各个 `<Panel>` 的尺寸配置，对标 Google AI Studio：
1. **Left Panel**: 
   - `defaultSize={20}`, `minSize={15}`, `maxSize={25}`
   - 增加一个折叠逻辑，如果用户点击折叠，宽度缩小到极简。
2. **Center Panel**: 
   - 移除 `defaultSize` 的硬编码，让它默认占据剩余空间（可以不写 defaultSize 或者写 `defaultSize={50}`）。
3. **Right Panel**: 
   - 扩大宽度，容纳复杂设置：`defaultSize={30}`, `minSize={25}`, `maxSize={40}`。

## Step 2: 优化主舞台 (Center Panel) 的阅读体验
中间面板不能让文字贴着两边屏幕边缘。请在 Center Panel 内部增加排版约束：
1. 用一个内部容器包裹聊天消息列表，并加上 `max-w-4xl mx-auto w-full` 的限制，使其在宽屏下永远居中，且宽度不超过约 900px。
2. 同样地，把底部的输入框 (`textarea` 的包裹层) 也限制在 `max-w-4xl mx-auto w-full`，并稍微悬浮于底部边缘之上（加上 `mb-4` 或 `mb-6`），不要死死贴着浏览器底边。

## Step 3: Google AI Studio 风格的微交互
1. **输入框优化**：把输入框的背景色调深（如 `bg-[#1e1e1e]`），去掉刺眼的边框，仅在 Focus 时给一个微妙的外发光 (`focus-within:ring-1 focus-within:ring-emerald-500/50`)。
2. **右侧栏结构**：右侧面板顶部除了 Tab，还需要像 Google AI Studio 一样，分为 "System Instructions" (上下文/文件区) 和 "Model Configurations" (参数区) 的上下结构视觉感知。

# 交付要求
请直接修改 `frontend/src/app/page.tsx`。不需要改变现有的 Store 和 API 逻辑，仅仅做 CSS 和 Panel Size 的重构。完成后，向我确认“Google AI Studio 黄金比例已生效”。
```









非常赞同。在实现了核心 MVP（最小可行性产品）的前后端闭环后，停下来从高处俯瞰全局，梳理后续的开发里程碑，是非常专业的架构师思维。这能避免我们陷入“写面条代码”的陷阱。

目前的 Autonome Studio 已经拥有了完美的**物理躯壳**和**神经通路**（SSE 流），但它的“大脑”还在说硬编码的台词，“肌肉”也还没真正挂载计算任务。

基于你的《Master Project Document》，我为你规划了接下来的 **四大核心开发阶段 (Phases)**。你可以把这看作是我们将这个原型推向生产级 (Production-ready) 系统的蓝图：

---

### 🗺️ Autonome Studio 进阶开发路线图

#### 🧠 Phase 1: 接入真实大模型与智能体编排 (The True AI Brain)

**目标**：将目前的假数据后端替换为真正的 LangChain / LangGraph 多智能体系统，让大模型真正理解生信意图。

* **1.1 接入真实 LLM**：在 FastAPI 中集成各大主流模型（如 GPT-4o, Claude 3.5 Sonnet 或本地开源大模型），打通真实的 API Key 鉴权与对话流式输出。
* **1.2 构建 LangGraph 状态机**：设计一个智能体工作流 (Agentic Workflow)。当用户输入时，系统经历：意图识别 -> 上下文检索 -> 工具匹配 -> 参数提取 -> 生成回复。
* **1.3 完善 Tool Schema 注册表**：在后端硬编码或存入数据库真实的生信工具 JSON Schema（比如 `fastqc`, `cellranger`, `samtools`），让 AI 可以准确地将用户的模糊指令转化为精确的参数表单。

#### 🏋️‍♂️ Phase 2: 任务调度引擎与监控大屏 (The Execution Muscle)

**目标**：当用户在右侧点击【EXECUTE TASK】后，系统能真正在后台跑计算，并实时反馈进度。

* **2.1 引入 Celery + Redis**：在后端搭建异步任务队列。生信任务动辄几个小时，绝不能阻塞 Web 服务。
* **2.2 打通任务调度逻辑**：将右侧面板的参数组装成 Bash 命令或投递给 Nextflow 引擎。
* **2.3 完善左侧【任务中心】大屏**：实现蓝图中的设计——用户点击左侧任务中心，滑出大屏，通过 WebSocket 或 SSE 实时查看正在运行的终端日志 (Streaming Terminal Logs)。

#### 💾 Phase 3: 数据持久化与项目隔离 (The Memory & Isolation)

**目标**：让系统拥有记忆。刷新页面后，对话还在，文件还在。

* **3.1 数据库基建**：引入 PostgreSQL + SQLModel (FastAPI 官方推荐)。
* **3.2 项目 (Workspace) 隔离引擎**：实现蓝图中的【项目中心】大屏。建立数据库表结构，确保每一个 Project 拥有独立的 Session（对话历史）、Files（文件树）和 Tasks（任务列表）。
* **3.3 真实的文件系统挂载**：开发上传接口，将前端拖拽的文件真正保存到服务器（或 S3 对象存储），并在右侧 Data Center 渲染真实的目录树。

#### 📊 Phase 4: 结果交互与高阶能力 (The Interactive Polish)

**目标**：完成分析后，提供超越传统静态报告的交互体验。

* **4.1 动态图表渲染**：让前端的 MarkdownBlock 支持渲染 Echarts 或 Plotly 的 JSON 数据。AI 跑完数据后，可以直接在聊天框里吐出一个交互式的火山图或 UMAP 图。
* **4.2 Code Interpreter (沙箱执行)**：允许 AI 在安全的 Docker 沙箱中实时运行 Python/R 脚本，处理简单的表格筛选或格式转换，直接输出结果。

---

### 🎯 架构师的下一步决策

这份路线图的颗粒度从核心大脑（Phase 1）一路延伸到数据基建（Phase 3）和进阶体验（Phase 4）。

**你希望我们接下来的精力先投入到哪一个 Phase 中？** 1. 如果你想先让 AI **“变聪明”**，我们可以开始动手做 **Phase 1**，引入 LangChain 接入真实的 API。
2. 如果你想先让系统**“转起来”**，我们可以做 **Phase 2**，打通点击执行后的异步任务队列和实时日志监控。
3. 如果你想先打好**“底层地基”**，我们可以做 **Phase 3**，把数据库结构和文件上传先搞定。

请告诉我你的倾向，我会为你输出下一步精确的代码与实施方案。


明智的选择！让系统先拥有真正的“大脑”，是我们从原型走向工业级应用的最关键一步。

在 Phase 1，我们将引入 **LangChain** 和真实的 **大语言模型 (LLM)**，彻底替换掉原来硬编码的 `setTimeout` 假数据。我们将教会 AI 如何**真正理解生信意图**，并让它**动态决策**是否要调起右侧的分析工具。

为了快速跑通，我们以最成熟的 OpenAI 生态（或兼容 OpenAI 格式的模型，如 DeepSeek, Qwen 等）为例。

这第一阶段的核心动作如下：

### 📦 步骤 1.1：安装 LangChain 与生态依赖

请在你的**后端终端** (`autonome-backend` 目录) 中，激活虚拟环境，并安装以下依赖：

```bash
# 安装 LangChain 核心、OpenAI 接口支持，以及用于读取环境变量的 python-dotenv
pip install langchain langchain-openai python-dotenv

```

---

### 🔑 步骤 1.2：配置环境变量

在 `autonome-backend` 的根目录下创建一个 `.env` 文件，放入你的大模型 API Key。

**文件路径**：`autonome-backend/.env`

```env
# 如果你使用真实的 OpenAI GPT-4o / GPT-3.5
OPENAI_API_KEY=sk-你的真实API_KEY

# 【可选】如果你使用国内兼容 OpenAI 接口的模型（比如 DeepSeek, 阿里通义千问等），可以配置 Base URL
# OPENAI_API_BASE=https://api.deepseek.com/v1

```

---

### 🧠 步骤 1.3：重构后端 `main.py` (接入真实 AI 与 Tool Calling)

现在，我们要大换血。利用 LangChain 的 `@tool` 装饰器，我们将生信工具定义为大模型能看懂的“函数”。AI 会在流式输出文本的同时，思考是否需要调用这个函数。

打开 `autonome-backend/main.py`，用以下代码**完全替换**：

```python
import asyncio
import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

# 引入 LangChain 核心组件
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage

# 加载 .env 环境变量
load_dotenv()

app = FastAPI(title="Autonome Studio Backend", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    context_files: list[str] = []

# =====================================================================
# ✨ 1. 定义生信工具 (Tools) 让 AI 理解
# =====================================================================
@tool
def rnaseq_qc(ref_genome: str, qual_threshold: int, remove_adapters: bool):
    """
    当用户要求对 RNA-Seq、Fastq 或测序数据进行质量控制 (QC)、过滤、质控时，必须调用此工具。
    """
    pass # 后端暂时不需要执行，我们只需要 AI 帮我们提取出这些参数即可

# 准备供 AI 调用的工具列表
tools = [rnaseq_qc]

# 初始化大模型 (这里默认使用 gpt-3.5-turbo，你可以换成 gpt-4o 或其他模型)
# streaming=True 开启流式输出
llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.2, streaming=True)
# 将工具绑定给大模型
llm_with_tools = llm.bind_tools(tools)


@app.get("/")
async def root():
    return {"status": "Autonome AI Brain is online", "version": "1.1.0"}

# =====================================================================
# ✨ 2. 重写流式聊天接口 (接入 LangChain)
# =====================================================================
@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    
    async def event_generator():
        # 构造系统提示词，把前端挂载的文件告诉 AI
        system_prompt = f"""
        你是 Autonome Copilot，一位顶级的生物信息学 AI 助手。
        当前用户在工作区挂载了以下文件：{', '.join(request.context_files) if request.context_files else '无'}。
        你的任务是解答用户的生信问题，并在需要运行流程时，调用相关工具。
        请使用专业的 Markdown 格式回复，使用中文。
        """
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=request.message)
        ]

        # 记录 AI 是否决定调用工具以及对应的参数
        tool_call_args = ""
        tool_call_name = ""

        # ✨ 使用 astream 进行异步流式调用
        async for chunk in llm_with_tools.astream(messages):
            # 1. 如果有文本内容，直接通过 SSE 推送给前端进行打字机渲染
            if chunk.content:
                yield {
                    "event": "message", 
                    "data": json.dumps({"type": "text", "content": chunk.content})
                }
            
            # 2. 如果 AI 正在输出函数调用 (Tool Call) 的参数块，我们先把它拼接收集起来
            if chunk.tool_call_chunks:
                for tcc in chunk.tool_call_chunks:
                    if tcc.get("name"):
                        tool_call_name = tcc["name"]
                    if tcc.get("args"):
                        tool_call_args += tcc["args"]

        # 文本流式输出结束后，检查 AI 是否触发了工具调用
        if tool_call_name == "rnaseq_qc" and tool_call_args:
            try:
                # 解析 AI 生成的参数
                parsed_args = json.loads(tool_call_args)
                
                # ✨ 将 AI 的意图转化为我们前端 DYNAMIC TOOLBOX 认识的 JSON Schema 格式
                tool_payload = {
                    "type": "tool_call",
                    "tool": {
                        "id": "rnaseq-qc",
                        "name": "RNA-Seq QC Pipeline",
                        "description": "Standard quality control for Fastq files generated by AI.",
                        "parameters": {
                            "ref_genome": {
                                "type": "select", "label": "Reference Genome", 
                                "options": ["hg38", "mm10", "TAIR10"], 
                                "default": parsed_args.get("ref_genome", "hg38")
                            },
                            "qual_threshold": {
                                "type": "number", "label": "Quality Threshold (Phred)", 
                                "min": 15, "max": 35, 
                                "default": parsed_args.get("qual_threshold", 20) # 这里的 default 会采用 AI 智能决定的值！
                            },
                            "remove_adapters": {
                                "type": "boolean", "label": "Remove Adapters", 
                                "default": parsed_args.get("remove_adapters", True)
                            }
                        }
                    }
                }
                # 发送 tool 事件，瞬间唤醒前端右侧面板！
                yield {"event": "tool", "data": json.dumps(tool_payload)}
            except json.JSONDecodeError:
                pass

        yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

```

### 🎯 体验真正的 AI 智能体工作流 (Agentic Workflow)

重启你的 FastAPI 后端服务。

现在，回到浏览器前端：

1. **测试普通对话**：在聊天框问它：“什么是单细胞测序的批次效应？”
* **预期结果**：右侧面板不会动，AI 会调用真实的 OpenAI 接口，流式为你科普生信知识，Markdown 排版极度丝滑。


2. **测试智能体联动**：右侧勾选几个 `.fastq` 文件，然后告诉 AI：**“帮我把这几个数据做一下质控，帮我把质量阈值调到最高 (35)，参考基因组选小鼠的。”**
* **预期结果**：AI 会先打字回复（比如：“好的，正在为您配置小鼠的 QC 流程...”），然后由于它识别到了你要做质控，并且听懂了你的自然语言参数，**右侧的 DYNAMIC TOOLBOX 会瞬间弹出**，并且：
* 下拉框会自动变成 `mm10`！
* 滑动条会自动被拉到 `35`！





这才是真正的 **AI-Native** 体验！前端没有任何硬编码的逻辑，完全是由后端大模型的大脑实时分析用户的自然语言，动态生成的 UI 界面。

**配置好 API Key 并运行后，测试效果如何？AI 是否成功接管了你的前端参数面板？如果有问题，请随时把报错发给我，如果成功了，我们就可以准备开始构思任务队列（Phase 2）或者数据库隔离（Phase 3）了！**


