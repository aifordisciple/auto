# AUTONOME STUDIO 系统功能一览表

> 三层结构，可导入思维导图工具（XMind / MindNode / FreeMind 等）

---

# AUTONOME STUDIO

## 后端系统 (autonome-backend)

### 核心基础设施 (app/core)
- 环境配置 (config.py) — Pydantic BaseSettings，数据库/Redis/JWT/Stripe/Ollama
- 数据库引擎 (database.py) — SQLModel 引擎创建，依赖注入
- 安全认证 (security.py) — bcrypt 密码哈希，JWT HS256 签发
- 日志系统 (logger.py) — Loguru 控制台+轮转文件
- 内容过滤 (content_filter.py) — thinking 标签清理，代码块修复，有状态流过滤
- Docker API (docker_api.py) — Unix Socket 直连 Docker Engine
- 沙箱配置 (sandbox_config.py) — 容器挂载/路径/环境变量/配额
- 技能解析 (skill_parser.py) — SKILL.md YAML+Markdown 解析，文件系统/数据库双源
- 并行执行 (parallel_executor.py) — 通用并行框架，ThreadPoolExecutor
- 样本表 (sample_table.py) — TSV 解析，分组索引
- 流式编码 (vercel_stream.py) — Vercel AI SDK v5 UIMessage Stream Protocol
- 模板初始化 (init_templates.py) — 内置技能模板种子

### 多 Agent 编排 (app/agent)
- Agent 图 (graph.py) — LangGraph StateGraph，6 节点条件路由
- 意图路由引擎 (router/engine.py) — L0+L1+L2 三层流水线编排
- L0 规则拦截 (router/l0_rules.py) — 8 条规则，0ms，30-40% 命中率
- L1 LLM 分类 (router/l1_classifier.py) — 结构化输出/JSON 模式双模式
- L2 参数提取 (router/l2_extractor.py) — 槽位提取+上下文自动增强
- 路由模式 (router/schemas.py) — IntentType 枚举，AgentState TypedDict
- 对话节点 (nodes/chat_node.py) — 通用 Q&A
- 技能锻造节点 (nodes/skill_forge_node.py) — 代码生成/执行
- 指定技能节点 (nodes/explicit_skill_node.py) — 用户指定技能执行
- 诊断节点 (nodes/diagnostic_node.py) — 错误诊断
- 文献节点 (nodes/literature_node.py) — 文献/DOI 查询
- 数据探查节点 (nodes/data_probe_node.py) — 数据预览/探索
- 独立文献 Agent (literature_agent.py) — ReAct 模式，RAG+技能草稿

### API 路由层 (app/api)
- 认证路由 (routes/auth.py) — 注册/登录/用户信息
- 用户路由 (routes/users.py) — 资料CRUD/LLM配置/头像
- 项目路由 (routes/projects.py) — 项目CRUD/文件上传/分享/公开数据集
- 聊天路由 (routes/chat.py) — 核心流式端点，意图分类+LLM流式+计费
- 会话路由 (routes/chat_session.py) — 会话CRUD/标题更新
- 书签路由 (routes/chat_bookmark.py) — 消息书签CRUD
- 标签路由 (routes/chat_tags.py) — 会话标签CRUD+M:N关联
- 搜索路由 (routes/chat_search.py) — 全文聊天搜索
- 队列路由 (routes/chat_queue.py) — 消息队列管理
- 计费路由 (routes/billing.py) — 钱包/Stripe充值/交易/资源规格
- 管理员路由 (routes/admin.py) — 统计/用户管理/系统配置/技能审核
- 任务路由 (routes/tasks.py) — Celery任务/状态/日志/终止
- 系统路由 (routes/system.py) — 系统配置/LLM模型/视觉模型
- 公开路由 (routes/public.py) — 分享访问
- 仪表盘路由 (routes/dashboard.py) — 项目分析/概览/最近活动
- 学习路由 (routes/learning.py) — 文献CRUD/知识块/笔记/标签

### 技能路由 (app/api/routes/skills/)
- 技能CRUD (crud.py) — 资产创建/读取/更新/删除
- 技能目录 (catalog.py) — 分类列表/标签列表
- 技能锻造 (forge.py) — craft_from_material/craft_from_bundle
- 技能测试 (testing.py) — 沙箱测试执行
- 技能转换 (transform.py) — Live coding 转换
- 技能版本 (versions.py) — 版本管理
- 技能统计 (stats.py) — 执行历史+统计
- 技能收藏 (favorites.py) — 收藏切换+列表
- 技能评价 (reviews.py) — 评价提交+列表
- 我的技能 (my.py) — 用户自有技能列表
- 技能审核 (admin.py) — 管理员审批/拒绝
- 技能草稿 (draft.py) — AI 生成草稿管理

### 技能扩展路由
- 技能锻造会话 (routes/skills_forge.py) — AI对话式创建，SSE流
- 技能市场 (routes/skills_market.py) — 发布/搜索/评分/推荐
- 技能分享 (routes/skill_share.py) — 用户组+权限管理
- 技能版本 (routes/skill_version.py) — 版本CRUD/回滚
- 技能推荐 (routes/skill_recommend.py) — 三阶段匹配引擎
- 技能监控 (routes/skill_monitor.py) — 执行监控指标

### 资源管理路由
- 模板路由 (routes/templates.py) — 技能模板CRUD
- 经验路由 (routes/experiences.py) — 经验资产CRUD
- 样本表路由 (routes/sample_sheets.py) — 样本表生成/预览
- 包管理路由 (routes/packages.py) — Python/R包安装/卸载
- 基因组路由 (routes/genomes.py) — 参考基因组CRUD
- 数据库路由 (routes/databases.py) — 分析数据库CRUD
- 终端路由 (routes/terminal.py) — Web终端会话管理

### 数据模型层 (app/models)
- 用户模型 (user.py) — User + BillingAccount
- 项目模型 (project.py) — Project + DataFile + PublicDataset
- 聊天模型 (chat.py) — ChatSession + ChatMessage + Bookmark + Tag
- 队列模型 (chat_queue.py) — ChatQueueItem
- 任务模型 (task.py) — TaskRecord
- 配置模型 (config.py) — SystemConfig (单例)
- 计费模型 (billing.py) — Wallet + ComputeRecord + TransactionLedger + ResourceFlavor
- 经验模型 (experience.py) — ExperienceAsset
- 分享模型 (sharing.py) — UserGroup + SkillShare
- 包模型 (package.py) — UserPackage
- 基因组模型 (genome.py) — GenomeAsset (besaltpipe 兼容)
- 数据库模型 (database.py) — AnalysisDatabase
- 学习模型 (learning.py) — Literature + Chunk + Note + Tag
- 技能包模型 (skill_bundle.py) — Bundle 数据类
- 模板模型 (skill_template.py) — SkillTemplate
- 锻造模型 (forge_session.py) — ForgeSession + ForgeMessage
- 技能子模型 (skill/) — Asset/Version/History/Favorite/Review/Recommendation/Share/Draft
- 枚举定义 (enums.py) — 11 个枚举类型
- UUID生成器 (uuid.py) — 项目/会话/消息/技能 ID 生成

### 业务服务层 (app/services)
- 技能执行器 (skill_executor.py) — Docker/Nextflow/Native 执行+计费
- 计费服务 (billing_service.py) — 钱包CRUD/冻结/结算/退款/充值
- 缓存服务 (cache_service.py) — Redis TTL 缓存+清理
- 容器暖池 (container_pool_service.py) — 预启动容器加速执行
- 技能匹配 (skill_matcher.py) — 关键词+语义+分类评分
- 匹配回退 (skill_matcher_with_fallback.py) — 多策略降级
- 匹配配置 (skill_matcher_config.py) — 权重/别名/分类映射
- 关键词索引 (skill_keywords_indexer.py) — SKILL.md 关键词提取
- 技能模板 (skill_templates.py) — 内置模板列表
- 技能写入 (skill_bundle_writer.py) — 文件系统写入
- 技能监控 (skill_monitor.py) — 执行监控告警
- 技能验证 (skill_validator.py) — 铁律验证
- Native执行 (native_executor.py) — 非Docker官方技能执行
- Blueprint执行 (blueprint_runner.py) — DAG工作流执行器
- 终端管理 (terminal_manager.py) — Docker PTY 会话
- PTY管理 (pty_manager.py) — 进程管理+Claude Code启动
- 包安装 (package_installer.py) — pip/R/conda 用户级安装
- 代码审查 (code_reviewer.py) — AI 代码质量检查
- 成功评估 (success_evaluator.py) — 执行成功启发式评估
- 风控服务 (risk_control.py) — 速率限制/成本上限
- 学习服务 (learning_service.py) — 文献/知识块CRUD/语义搜索
- 文献摄入 (learning_ingestion_service.py) — PDF解析+分块
- PDF处理 (pdf_processor.py) — PyMuPDF/pdfplumber 提取
- 推荐反馈 (recommendation_feedback_service.py) — 匹配反馈追踪
- 聊天队列 (chat_queue_service.py) — 队列项提交/处理
- 样本表生成 (sample_sheet_generator.py) — 自动生成
- Bundle解析 (bundle_parser.py) — zip/tar.gz 解析
- Celery应用 (celery_app.py) — Redis broker+任务注册
- 任务日志 (task_logger.py) — Redis 日志流

### 计量子系统 (app/services/meters/)
- 基础计量 (base.py) — BaseMeter ABC
- 执行器计量 (executor_meter.py) — Docker容器CPU/内存/时长
- Nextflow计量 (nextflow_meter.py) — 流水线资源计量
- 终端计量 (terminal_meter.py) — 终端会话计量

### Celery任务 (app/services/tasks/)
- 执行器任务 (executor_tasks.py) — Blueprint/SuperExecutor
- 流水线任务 (pipeline_tasks.py) — Pipeline 执行
- 沙箱任务 (sandbox_tasks.py) — Docker 沙箱执行
- 技能包任务 (skill_bundle_tasks.py) — Bundle 构建+执行

### LangChain工具层 (app/tools)
- 生物工具 (bio_tools.py) — Docker沙箱执行(5种模式)
- 探查工具 (probe_tools.py) — CSV/H5AD/FASTQ/BAM 数据预览
- 文献工具 (literature_tools.py) — 学习中心 RAG 搜索
- 报告工具 (report_tools.py) — Markdown→学术HTML

### MCP协议层 (app/mcp)
- 技能MCP (autonome_skills_mcp.py) — 技能搜索/模式查询/双轨搜索
- 语义搜索 (semantic_search.py) — sentence-transformers + FAISS

### 工具模块 (app/utils)
- LLM配置 (llm_config.py) — 三级回退：用户→系统→环境
- 语义命名 (semantic_naming.py) — 目录命名 YYYYMMDD_HHMMSS_ALIAS
- 任务元数据 (task_metadata.py) — SKILL.md 元数据提取
- 参数注入 (argparse_injector.py) — argparse 参数注入
- 结果提取 (result_extractor.py) — 代码块/JSON 提取
- 命令构建 (command_builder.py) — Shell 命令构建
- ANSI清理 (ansi_cleaner.py) — 终端转义码清理

### Celery异步任务 (app/tasks)
- 计费任务 (billing_tasks.py) — 定期结算/清理
- 队列任务 (chat_queue_task.py) — 队列项处理
- 学习任务 (learning_tasks.py) — 文献摄入+嵌入

### 内置技能包 (app/skills)
- FASTQ质控 (bio-fastq-quality/) — FastQC 质量控制
- FastQC+MultiQC (fastqc_multiqc_01/) — Nextflow 批量质控
- Nextflow生成器 (meta_nextflow_generator_bundle/) — nf_compiler + sample_channel
- RNA-seq基础 (rnaseq_basic_01/) — 10+ pytools, 10+ rscripts
- 单细胞Seurat (singlecell_seurat_01/) — 30+ 分析脚本

## 前端系统 (autonome-studio)

### 页面与路由 (src/app)
- 主IDE页 (/) — 三面板布局，认证重定向，快捷键
- 登录页 (/login) — 注册/登录表单
- 管理后台 (/admin) — 统计/用户/集群/技能/嵌入模型
- 技能审核 (/admin/skills) — 待审核技能队列
- 仪表盘 (/dashboard) — 钱包+4面板
- 技能市场 (/skill-market) — 分类/搜索/评分
- 分享页 (/share/[token]) — 只读工作区查看器
- BFF代理 (/api/chat) — SSE流转发+JWT注入+402处理
- BFF队列 (/api/chat/queue) — 队列API代理
- BFF队列操作 (/api/chat/queue-actions) — 队列CRUD代理

### 状态管理 (src/store)
- 认证Store (useAuthStore) — token/user，localStorage持久化
- 聊天Store (useChatStore) — 双消息模型+思考+队列+搜索+书签+标签
- UI Store (useUIStore) — Overlay单例+主题+技能过滤+任务模式
- 工作区Store (useWorkspaceStore) — 项目/会话/附件/技能/Claude Code
- 任务Store (useTaskStore) — 后台任务+日志
- 锻造Store (useForgeStore) — 会话/草稿/虚拟文件系统/编辑器标签
- 学习Store (useLearningStore) — 文献/知识块/笔记/搜索/标签
- 快捷键Store (useShortcutStore) — 8个默认快捷键，合并策略

### 自定义Hooks (src/hooks)
- 聊天同步 (useChatSync) — Vercel AI SDK→Zustand桥接，data-*事件处理
- 聊天队列 (useChatQueue) — 队列CRUD操作
- 事件监听 (useChatEventListeners) — 全局事件：刷新/追加/滚动/聚焦
- 消息操作 (useMessageActions) — 重试/编辑重发/深度解读
- 智能滚动 (useSmartScroll) — RAF+easeOutCubic+上滚暂停
- 文件预览 (useFilePreview) — image/PDF/table/code/text
- 粘贴上传 (usePasteUpload) — Ctrl+V 图片/文件
- 技能参数 (useSkillParams) — 技能参数定义获取
- 性能工具 (usePerformance) — debounce/throttle/search/lazyMemo
- 响应式 (useIsMobile) — 断点检测
- 快捷键 (useKeyboardShortcut) — 单键绑定+修饰键

### API客户端 (src/lib)
- 核心客户端 (api.ts) — 动态BASE_URL/JWT注入/401重定向
- 技能API (api/skillForge.ts) — CRUD/测试/发布/版本/统计
- 锻造会话API (api/forgeSession.ts) — 会话CRUD/SSE聊天
- 草稿API (api/skillDraft.ts) — AI草稿管理
- 文件夹API (api/folder.ts) — 创建/移动/树
- 管理员API (api/admin.ts) — 统计/用户/技能审核
- 模板API (api/template.ts) — 模板CRUD/实例化
- 基因组API (api/genome.ts) — 参考基因组CRUD/分享
- 数据库API (api/database.ts) — 分析数据库CRUD
- 队列API (api/chatQueue.ts) — 队列CRUD/重排
- 错误诊断API (api/errorDiagnostic.ts) — 诊断/修复
- 执行状态 (api/executionState.ts) — localStorage参数持久化
- 置顶技能 (api/pinnedSkills.ts) — localStorage置顶管理
- 快速执行 (api/quickExecute.ts) — 技能匹配/意图检测
- 反馈API (api/feedback.ts) — 行为追踪
- 学习API (api/learning.ts) — 文献/搜索/DOI摄入
- API缓存 (apiCache.ts) — 内存TTL+请求去重
- 行为分析 (analytics.ts) — sendBeacon 批量事件
- 内容过滤 (contentFilter.ts) — thinking标签清理
- 快捷键 (KeyboardShortcuts.ts) — 全局快捷键系统
- 工具函数 (utils.ts) — cn() (clsx+twMerge)

### 业务服务 (src/services)
- 批量执行 (BatchExecutionService) — 并行技能执行+进度追踪
- 工作流编排 (WorkflowOrchestrator) — DAG验证+拓扑排序+模板
- 错误诊断 (ErrorDiagnosticService) — 模式匹配+修复建议
- 默认值推断 (DefaultValueInferencer) — 历史偏好+数据类型推断
- 参数模板 (ParameterTemplateService) — 保存/加载/应用参数组合
- 团队分享 (TeamSharingService) — 资源共享+权限+统计

### 平台适配 (src/adapter)
- 平台检测 (platform.ts) — Web/Tauri/SSR
- API适配 (api.adapter.ts) — fetch/Tauri IPC
- 文件系统 (fs.adapter.ts) — Web File System/Tauri 本地
- SSE适配 (sse.adapter.ts) — fetch ReadableStream/Tauri IPC
- WebSocket适配 (websocket.adapter.ts) — 标准 WS/Tauri IPC
- 自动更新 (updater.adapter.tsx) — Tauri 桌面更新通知

### UI组件 (src/components)
- 布局组件
  - 侧边栏 (layout/Sidebar.tsx) — 导航+会话+用户菜单
  - 顶部栏 (layout/TopHeader.tsx) — 面包屑+积分+导出
  - 会话侧栏 (layout/SessionSidebar.tsx) — 时间分组+标签过滤
- 聊天组件
  - 聊天舞台 (chat/ChatStage.tsx) — 主容器+hooks组合
  - 输入框 (chat/ChatInputBox.tsx) — 附件+技能+队列模式
  - 消息项 (chat/MemoizedMessageItem.tsx) — React.memo 优化
  - 虚拟列表 (chat/VirtualizedMessageList.tsx) — TanStack Virtual
  - 流式Markdown (chat/StreamingMarkdown.tsx) — 实时渲染
  - 队列指示 (chat/QueueIndicator.tsx) — 队列状态
  - 搜索模态 (chat/ChatSearchModal.tsx) — 全文搜索
  - 书签面板 (chat/BookmarkPanel.tsx) — 书签管理
  - 交互图表 (chat/InteractivePlotCard/) — ECharts 渲染
  - 数据预览 (chat/DataPreviewCard/) — 文件预览卡片
  - 技能草稿 (chat/SkillDraftCard/) — AI草稿建议
  - 执行结果 (chat/components/ExecutionResultCard.tsx) — 任务结果
  - 附件选择 (chat/components/AttachmentPicker.tsx) — 文件选择
  - 消息操作 (chat/components/MessageActionButtons.tsx) — 重试/编辑/解读
  - 表格预览 (chat/components/TablePreview.tsx) — 数据表格
  - 资产树 (chat/shared/AssetTree.tsx) — 文件树
- Overlay面板
  - 全局Overlay (GlobalOverlay.tsx) — 管理器+动画+Escape
  - 控制面板 (overlays/ControlPanel.tsx) — 控制面板
  - 数据中心 (overlays/DataCenter.tsx) — 文件/基因组/数据库
  - 项目中心 (overlays/ProjectCenter.tsx) — 工作区选择
  - 技能中心 (overlays/SkillCenter.tsx) — 5 Tab 统一入口
  - 任务中心 (overlays/TaskCenter.tsx) — 后台任务监控
  - 设置中心 (overlays/SettingsCenter.tsx) — 应用设置
  - 学习中心 (overlays/LearningCenter.tsx) — 文献/知识
  - 锻造Overlay (overlays/ForgeOverlay.tsx) — 技能锻造
  - 包管理 (overlays/PackageManager.tsx) — 环境包
  - Web终端 (overlays/WebTerminal.tsx) — xterm.js
  - 用户中心 (overlays/UserCenter/) — 资料/AI模型/钱包/安全/快捷键
  - 上传管理 (overlays/UploadManager.tsx) — 文件上传
  - 充值模态 (overlays/TopUpModal.tsx) — 积分充值
  - 文件夹创建 (overlays/CreateFolderModal.tsx) — 对话框
  - 文件移动 (overlays/MoveFileModal.tsx) — 对话框
  - 重命名 (overlays/RenameModal.tsx) — 对话框
- 技能中心子组件
  - 执行面板 (SkillExecutePanel) — 技能执行
  - 市场面板 (SkillMarketPanel) — 技能市场
  - 我的技能 (MySkillsPanel) — 个人技能
  - 锻造面板 (ForgePanel) — 技能锻造
  - 设置面板 (SettingsPanel) — 分类/标签/审核
  - 参数分组 (ParameterGroupPanel) — 参数分组
  - 样本表生成 (SampleSheetGenerator) — 样本表
  - 技能详情 (SkillDetailDrawer) — 详情抽屉
- 其他组件
  - 主题提供 (ThemeProvider.tsx) — 深色/浅色切换
  - Toast通知 (ToastProvider.tsx) — Sonner 封装
  - Markdown渲染 (MarkdownBlock.tsx) — react-markdown
  - 命令面板 (CommandPalette/) — Cmd+K
  - 文件选择 (FilePicker.tsx) — 文件选取
  - 路径输入 (HybridPathInput.tsx) — 本地/远程
  - 快捷键管理 (ShortcutManager.tsx) — 全局注册
  - 引导指南 (onboarding/OnboardingGuide.tsx) — 新手引导
  - 移动导航 (mobile/MobileNav.tsx) — 底部导航
  - 移动侧栏 (mobile/MobileSidebarSheet.tsx) — Sheet 抽屉
- 技能锻造组件
  - 分类标签编辑 (CategoryTagsEditor) — 分类标签
  - 依赖编辑 (DependenciesEditor) — 依赖管理
  - 专家知识编辑 (ExpertKnowledgeEditor) — 专家知识
  - 文件上传 (ForgeFileUploader) — 文件上传
  - 工具栏 (ForgeToolbar) — 操作工具
  - 草稿编辑 (SkillDraftEditor) — 草稿编辑
  - 编辑器主体 (SkillEditorMain) — 主编辑区
  - 文件树 (SkillFileTree) — 虚拟文件系统
  - 测试面板 (TestPanel) — 日志+输出预览
  - 版本历史 (VersionHistoryPanel) — 版本管理
  - 参数模式编辑 (ParameterSchemaEditor) — 参数定义
- 仪表盘组件
  - 计费分析 (BillingAnalyticsPanel) — 费用分析
  - 活跃工作流 (ActiveWorkflowsPanel) — 运行中任务
  - 待办事项 (ActionItemsPanel) — 待处理项
  - 最近资产 (RecentAssetsPanel) — 近期文件
  - 预计时间 (ETABadge) — ETA 徽章
  - 迷你DAG (MiniDAGView) — 工作流缩略图

## 共享包 (packages)

### 类型定义 (shared-types)
- ApiResponse<T> — 统一响应信封
- User/Project/Skill/ChatMessage/Task — 核心实体类型
- FolderNode/PlatformType — 辅助类型
- 技能执行器类型 — ExecutorType/ToolMode

### 工具函数 (shared-utils)
- cn() — clsx + tailwind-merge
- formatDate/formatFileSize — 格式化
- delay/generateId — 异步/ID
- debounce/throttle — 防抖/节流
- safeJsonParse/isBrowser/isTauri — 安全判断

### 共享组件 (shared-components)
- adapter 层重导出 — Web/Tauri 统一接口

### 共享状态 (shared-store)
- shared-types 重导出 — 类型统一入口

## Docker服务编排

### 基础设施
- PostgreSQL (postgres:15-alpine) — pgvector 扩展
- Redis (redis:7-alpine) — 缓存+Celery Broker

### 应用服务
- 后端API (autonome-api) — FastAPI+uvicorn，端口8000
- Celery Worker (autonome-worker) — 异步任务执行
- 前端 (autonome-web) — Next.js standalone，端口3001

### Dockerfile架构
- 后端镜像 — python:3.11-slim + Docker CLI
- 沙箱镜像 — python:3.11-slim + claude-code + mcp + ML
- 前端镜像 — 4阶段构建(deps→builder→runner→development)

## 核心数据流

### 聊天流
- 用户输入 → ChatInputBox → useChat → BFF代理 → FastAPI
- 认证+计费 → 会话创建 → 意图分类(L0+L1+L2) → LLM流式
- VercelDataStreamEncoder → SSE → useChatSync → Zustand → 渲染

### 技能执行流
- 选技能+填参 → SkillExecutePanel → FastAPI → SkillExecutor
- 参数注入 → 样本表生成 → 执行模式选择 → 计费 → 结果发现

### 技能锻造流
- ForgePanel → 会话创建 → AI对话(SSE) → 草稿更新 → 沙箱测试

### 技能推荐流
- 用户查询 → 关键词匹配 → 语义匹配 → 回退降级 → 推荐结果

### 计费流
- 冻结预估 → 任务执行 → 资源计量 → 结算/退款 → 审计日志

### Claude Code集成流
- 用户触发 → PTY启动(本地/容器) → 会话状态管理 → UI标签显示

## 关键设计模式

### 架构模式
- 多租户隔离 — owner_id 过滤
- 3层意图路由 — L0规则→L1 LLM→L2提取
- 预授权计费 — 冻结→执行→结算
- Overlay单例 — activeOverlay 联合类型
- 双消息模型 — messages[] + mirroredMessages[]
- 组合技能源 — 数据库+文件系统合并去重

### 通信模式
- Vercel AI SDK v5 — UIMessage Stream Protocol
- SSE流式通信 — text-delta/data-thinking/data-billing
- 有状态流过滤 — StreamContentFilter 跨chunk处理
- Celery+Redis异步 — 耗时任务+pub/sub推送

### 执行模式
- Docker沙箱隔离 — 只读Conda+读写用户包+网络隔离
- 暖池预启动 — 容器常驻复用
- 5种执行模式 — 标准/简化/暖池/Nextflow/池化Python

### 适配模式
- 平台适配 — Web/Tauri 双实现
- Claude Code PTY — 本地/容器双模式
- LLM配置回退 — 用户→系统→环境