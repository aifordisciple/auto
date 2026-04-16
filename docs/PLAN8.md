# AUTONOME 用户体验与界面升级计划 (PLAN8)

> **评估日期**: 2026-03-31
> **评估维度**: 用户角度（新手 → 专家）× 界面摩擦度
> **核心目标**: 降低界面摩擦度，提升用户价值感知

---

## 一、执行摘要

### 1.1 用户体验评估公式

```
用户价值 = 功能满足度 × 操作效率 / 学习成本
```

**界面摩擦度定义**: 用户从"我想做某事"到"完成这件事"之间的阻力总和

### 1.2 当前体验痛点矩阵

| 用户类型 | 核心痛点 | 界面摩擦度得分 | 优先级 |
|---------|---------|---------------|-------|
| **新手用户** | 不知道从哪开始、功能太多、术语难懂 | 4.5/10 | P0 |
| **中级用户** | 找不到功能、参数填写繁琐、错误恢复难 | 5.5/10 | P1 |
| **专家用户** | 快捷操作少、批量处理效率低、自定义能力弱 | 6.5/10 | P2 |
| **移动端用户** | 三步向导繁琐、触摸目标小、网络敏感 | 3.5/10 | P0 |

### 1.3 升级目标

| 指标 | 当前值 | 目标值 | 提升 |
|------|--------|--------|------|
| 新手完成首次分析时间 | ~10分钟 | <3分钟 | -70% |
| 中级用户参数填写时间 | ~2分钟 | <30秒 | -75% |
| 专家用户操作点击次数 | 4-6次 | 2-3次 | -50% |
| 移动端任务完成率 | 40% | 80% | +100% |

---

## 二、用户角色深度分析

### 2.1 新手用户画像

**典型场景**: 生物信息学研究生，刚接触生信分析，对命令行恐惧

**当前体验问题**:

```
用户旅程: 进入系统 → 看到首页 → ???
         ↓
问题1: 首页展示"What do you want to analyze?"
       - 不知道输入什么
       - 快捷按钮示例过于专业（"单细胞 UMAP 降维"）

问题2: 输入需求后
       - 推荐技能卡片信息量过大
       - 不知道"快速"和"精准"模式的区别

问题3: 点击技能后打开技能中心
       - 三栏布局信息密度高
       - 参数表格复杂，不知道填什么
       - SampleTable 编辑器需要学习

问题4: 执行失败
       - 错误信息技术化
       - 不知道如何修复
```

**摩擦点量化**:
- 决策瘫痪点: 3处（首页输入、模式选择、参数填写）
- 学习曲线陡峭: SampleTable、术语、参数
- 错误恢复成本高: 需要重新配置

### 2.2 中级用户画像

**典型场景**: 生信工程师，熟悉常用工具，追求效率

**当前体验问题**:

```
用户旅程: 进入系统 → 选择技能 → 填参数 → 执行
         ↓
问题1: 技能发现效率低
       - 分类导航层级浅（最多2层）
       - 搜索不支持自然语言
       - 收藏的技能不能直接配置参数

问题2: 参数填写繁琐
       - 相似参数每次都要重新填写
       - 缺少参数模板保存
       - 必填/可选参数混在一起

问题3: 执行等待体验
       - 进度条无具体步骤
       - 无法在等待时做其他事
       - 失败后参数丢失

问题4: 结果查看
       - 需要手动刷新数据中心
       - 图片预览需要点击
       - 无法直接对比多个结果
```

**摩擦点量化**:
- 重复操作: 参数填写、结果查看
- 等待焦虑: 无分步进度、无多任务支持
- 错误代价: 参数丢失需要重新配置

### 2.3 专家用户画像

**典型场景**: 生信团队负责人，管理多人协作，需要定制化

**当前体验问题**:

```
用户旅程: 进入系统 → 批量分析 → 审核结果 → 分享
         ↓
问题1: 缺少批量操作
       - 无法批量提交任务
       - 无法批量下载结果
       - 无法批量配置参数

问题2: 协作能力弱
       - 无法分享执行配置
       - 无法复制他人参数
       - 无团队技能库

问题3: 自定义能力不足
       - 无法自定义参数模板
       - 无法自定义分析流程
       - 无法自定义报告格式

问题4: 高级功能隐藏
       - Tools 菜单发现率低
       - 复杂任务模式入口深
       - 超级执行者功能不直观
```

**摩擦点量化**:
- 效率瓶颈: 无批量操作、无快捷键
- 协作障碍: 无分享机制、无团队功能
- 定制限制: 无模板、无流程自定义

### 2.4 移动端用户画像

**典型场景**: 在地铁上查看结果、紧急修改参数、监控任务进度

**当前体验问题**:

```
用户旅程: 移动端打开 → 查看任务 → ???
         ↓
问题1: 三步向导繁琐
       - 分类 → 技能 → 参数 需要多次点击
       - 每次进入都是新流程，无法快速访问常用技能
       - 底部导航栏功能有限

问题2: 触摸目标过小
       - 分类列表行高不足 44px
       - 参数输入框需要放大
       - 按钮间距不足

问题3: 参数编辑体验差
       - SampleTable 无法在移动端编辑
       - 文件选择器不支持云端文件
       - 长参数列表需要大量滚动

问题4: 网络敏感
       - 无法离线查看历史结果
       - 无断点续传
       - 流式输出网络要求高
```

**摩擦点量化**:
- 操作效率: 步骤数增加 50%
- 触摸问题: 30% 的触摸目标不达标
- 网络依赖: 无离线能力

---

## 三、界面摩擦度深度评估

### 3.1 首页体验分析

**当前设计**:
```tsx
// ChatStage.tsx - 空聊天状态
<h1>What do you want to analyze?</h1>
<QuickExecute /> // 搜索框 + 快捷按钮
<ChatInputBox /> // 输入框
// 快捷按钮示例：单细胞 UMAP 降维、差异基因火山图、数据 QC 质控
```

**问题诊断**:
| 问题 | 影响 | 严重程度 |
|------|------|---------|
| 主标题纯英文，专业术语 | 新用户不知道输入什么 | 🔴 高 |
| 快捷按钮示例过于专业 | 生僻术语增加认知负担 | 🟡 中 |
| QuickExecute 和 ChatInputBox 并存 | 两个输入入口增加困惑 | 🟡 中 |
| 缺少新手引导 | 不知道系统功能边界 | 🔴 高 |
| 缺少最近任务/常用技能 | 老用户无法快速继续工作 | 🟡 中 |

### 3.2 技能中心体验分析

**当前设计**:
```tsx
// SkillExecutePanel.tsx - 桌面端三栏布局
// 左侧：分类导航 180px
// 中间：技能列表 280px
// 右侧：参数配置 flex-1

// 移动端：三步向导
// Step 1: 分类选择
// Step 2: 技能选择
// Step 3: 参数配置
```

**问题诊断**:
| 问题 | 影响 | 严重程度 |
|------|------|---------|
| 三栏布局信息密度高 | 新用户不知所措 | 🔴 高 |
| 分类导航层级浅 | 深层分类不便查找 | 🟡 中 |
| 参数表单无分组 | 填写效率低 | 🔴 高 |
| 缺少参数模板 | 重复填写相同参数 | 🟡 中 |
| 移动端三步向导 | 步骤多、效率低 | 🔴 高 |
| 执行日志冗长 | 无法快速定位关键信息 | 🟢 低 |

### 3.3 聊天交互体验分析

**当前设计**:
```tsx
// ChatInputBox.tsx
// 输入框 + 加号按钮 + Tools按钮 + 发送按钮
// 加号菜单：添加附件、选择技能、导入代码
// Tools菜单：基础分析、复杂任务、超级执行者
```

**问题诊断**:
| 问题 | 影响 | 严重程度 |
|------|------|---------|
| Tools 功能发现率低 | 高级功能被忽略 | 🔴 高 |
| 菜单层级深 | 需要多次点击 | 🟡 中 |
| 缺少快捷键 | 高频操作效率低 | 🟡 中 |
| 附件状态不明显 | 上传中可能误操作 | 🟢 低 |
| 流式输出无停止提示 | 不知道可以中断 | 🟢 低 |

### 3.4 侧边栏体验分析

**当前设计**:
```tsx
// Sidebar.tsx
// Logo + 导航菜单 (6项) + 会话列表 + 用户胶囊
// 导航：控制面板、项目中心、任务中心、数据中心、技能中心、终端
```

**问题诊断**:
| 问题 | 影响 | 严重程度 |
|------|------|---------|
| 导航项过多 | 不知道从哪开始 | 🔴 高 |
| 会话列表与聊天分离 | 需要切换上下文 | 🟡 中 |
| 缺少搜索历史 | 找不到之前的对话 | 🟡 中 |
| 移动端侧边栏隐藏 | 导航不直观 | 🔴 高 |

---

## 四、升级策略规划

### Phase 1: 新手友好化 (P1, 2周)

**目标**: 新用户 3 分钟内完成首次分析

#### P1-1: 首页引导优化

**问题**: 新用户不知道输入什么

**解决方案**:

```tsx
// 新增: OnboardingGuide.tsx - 新手引导组件
// 1. 首次访问显示功能卡片
// 2. 渐进式披露：先展示核心功能，高级功能逐步解锁
// 3. 智能示例：根据项目数据类型推荐输入

interface OnboardingStep {
  title: string;          // 中文标题
  description: string;    // 简短说明
  example: string;        // 可点击的示例
  icon: React.ReactNode;  // 可视化图标
}

// 示例数据
const beginnerSteps: OnboardingStep[] = [
  {
    title: "数据质控",
    description: "检查测序数据质量，发现异常样本",
    example: "分析我的测序数据质量",
    icon: <QualityIcon />
  },
  {
    title: "基因表达分析",
    description: "比较不同组间的基因表达差异",
    example: "找出两组样本的差异基因",
    icon: <GeneIcon />
  },
  {
    title: "可视化绘图",
    description: "生成论文级图表",
    example: "绘制火山图展示差异基因",
    icon: <ChartIcon />
  }
];
```

**实施细节**:

| 文件 | 修改内容 | 预期效果 |
|------|---------|---------|
| `ChatStage.tsx` | 添加 OnboardingGuide 条件渲染 | 首次访问显示引导 |
| `QuickExecute.tsx` | 中文化示例、简化模式选择 | 降低输入门槛 |
| `useUserStore.ts` | 添加 `hasSeenOnboarding` 状态 | 控制引导显示 |

#### P1-2: 输入框智能提示

**问题**: 不知道输入什么格式

**解决方案**:

```tsx
// 新增: SmartInput.tsx - 智能输入组件
// 功能:
// 1. 输入时实时显示推荐提示
// 2. 自动补全常用术语
// 3. 错误输入友好提示

// 示例提示数据
const inputSuggestions = [
  { trigger: "单细胞", suggestions: ["单细胞降维分析", "单细胞聚类分析", "单细胞差异分析"] },
  { trigger: "RNA", suggestions: ["RNA-seq差异表达", "RNA-seq质控", "RNA-seq定量"] },
  { trigger: "质控", suggestions: ["测序数据质控", "样本质量评估", "FastQC分析"] }
];
```

#### P1-3: 技能中心简化

**问题**: 三栏布局过于复杂

**解决方案**:

```tsx
// 新增: SimplifiedSkillPanel.tsx - 简化版技能面板
// 适用场景: 新用户、移动端
// 设计原则: 一屏一任务

// 布局变化
// 新用户: 技能推荐卡片 → 一键执行
// 中级用户: 技能列表 → 参数配置 → 执行
// 专家用户: 保留完整三栏布局

// 参数表单智能分组
const ParameterGroupPanel = ({ schema, paramValues, onParamChange }) => {
  // 自动识别参数类型
  const groups = autoGroupParameters(schema);

  return (
    <div className="space-y-4">
      {groups.map(group => (
        <ParameterGroup
          key={group.id}
          title={group.title}
          description={group.description}
          params={group.params}
          defaultExpanded={group.isRequired}
        />
      ))}
    </div>
  );
};

// 分组策略
const autoGroupParameters = (schema: Schema): ParameterGroup[] => {
  return [
    {
      id: 'input',
      title: '输入数据',
      description: '需要分析的文件或目录',
      params: ['sample_table', 'input_dir', 'genome_reference'],
      isRequired: true
    },
    {
      id: 'analysis',
      title: '分析参数',
      description: '控制分析过程的关键参数',
      params: ['min_genes', 'min_cells', 'resolution'],
      isRequired: true
    },
    {
      id: 'output',
      title: '输出设置',
      description: '结果保存位置和格式',
      params: ['output_dir', 'output_format', 'prefix'],
      isRequired: false
    },
    {
      id: 'advanced',
      title: '高级选项',
      description: '专业人员可调整的参数',
      params: ['random_seed', 'n_jobs', 'memory_limit'],
      isRequired: false,
      defaultCollapsed: true
    }
  ];
};
```

#### P1-4: 移动端体验优化

**问题**: 三步向导繁琐

**解决方案**:

```tsx
// 新增: MobileQuickActions.tsx - 移动端快捷操作面板
// 设计原则: 减少步骤、突出常用功能

// 功能:
// 1. 首页显示最近执行的技能（一键重试）
// 2. 收藏技能直接显示参数配置
// 3. 支持 NFC 标签快捷启动（可选）

// 移动端专属布局
const MobileLayout = () => (
  <div className="flex flex-col h-full">
    {/* 顶部: 最近任务 */}
    <RecentTasksCarousel />

    {/* 中间: 快捷操作 */}
    <QuickActionsGrid actions={commonActions} />

    {/* 底部: 导航 */}
    <MobileNav />
  </div>
);

// 触摸目标优化
const TOUCH_TARGET_SIZE = 44; // 最小触摸目标尺寸 (Apple HIG)
const TOUCH_TARGET_SPACING = 8; // 触摸目标间距

// 触摸目标达标率目标: 100%
```

---

### Phase 2: 效率提升 (P2, 2周)

**目标**: 中级用户参数填写时间减少 75%

#### P2-1: 参数模板系统

**问题**: 每次都要重新填写相同参数

**解决方案**:

```typescript
// 新增: ParameterTemplateService.ts
// 功能:
// 1. 保存常用参数组合为模板
// 2. 一键应用模板
// 3. 模板分享给团队成员

interface ParameterTemplate {
  id: string;
  name: string;
  skill_id: string;
  parameters: Record<string, unknown>;
  created_by: number;
  is_shared: boolean;
  tags: string[];
}

// API 设计
// POST /api/skills/{skill_id}/templates - 保存模板
// GET /api/skills/{skill_id}/templates - 获取模板列表
// POST /api/skills/{skill_id}/templates/{template_id}/apply - 应用模板
```

#### P2-2: 智能默认值

**问题**: 不知道填什么值

**解决方案**:

```typescript
// 新增: DefaultValueInferencer.ts
// 功能:
// 1. 根据项目数据类型推断默认值
// 2. 根据历史执行记录学习偏好
// 3. 根据同组用户行为推荐

interface DefaultValueContext {
  project_id: string;
  skill_id: string;
  user_id: number;
  data_type?: string;  // 项目数据类型
  history?: Execution[]; // 历史执行记录
}

const inferDefaultValue = async (context: DefaultValueContext, param: SkillParameter): Promise<unknown> => {
  // 1. 检查是否有历史偏好
  const historyValue = await getHistoryPreference(context.user_id, context.skill_id, param.name);
  if (historyValue) return historyValue;

  // 2. 检查是否有同组用户偏好
  const teamValue = await getTeamPreference(context.user_id, context.skill_id, param.name);
  if (teamValue) return teamValue;

  // 3. 检查数据类型是否匹配
  const dataBasedValue = await inferFromDataType(context.project_id, param);
  if (dataBasedValue) return dataBasedValue;

  // 4. 使用全局默认值
  return param.default;
};
```

#### P2-3: 快捷键系统

**问题**: 高频操作需要多次点击

**解决方案**:

```typescript
// 新增: KeyboardShortcuts.ts
// 全局快捷键定义

const GLOBAL_SHORTCUTS: ShortcutDefinition[] = [
  { key: '/', description: '聚焦搜索框', action: 'focus-search' },
  { key: 'Cmd+K', description: '快速命令面板', action: 'open-command-palette' },
  { key: 'Cmd+Shift+K', description: '技能中心', action: 'open-skill-center' },
  { key: 'Cmd+Enter', description: '执行当前任务', action: 'execute-task' },
  { key: 'Escape', description: '关闭弹窗/取消操作', action: 'close-modal' },
  { key: 'Cmd+N', description: '新对话', action: 'new-chat' },
  { key: 'Cmd+H', description: '历史记录', action: 'open-history' },
  { key: '?', description: '快捷键帮助', action: 'show-shortcuts-help' }
];

// 技能中心专用快捷键
const SKILL_CENTER_SHORTCUTS: ShortcutDefinition[] = [
  { key: '/', description: '搜索技能', action: 'focus-skill-search' },
  { key: 'Cmd+Enter', description: '执行技能', action: 'execute-skill' },
  { key: 'Cmd+S', description: '保存为模板', action: 'save-template' },
  { key: 'Tab', description: '切换参数组', action: 'next-param-group' }
];
```

#### P2-4: 命令面板

**问题**: 功能发现困难

**解决方案**:

```tsx
// 新增: CommandPalette.tsx - 类似 VS Code 的命令面板
// Cmd+K 唤起
// 功能:
// 1. 快速访问所有功能
// 2. 模糊搜索命令
// 3. 显示最近使用

interface Command {
  id: string;
  label: string;
  category: 'navigation' | 'action' | 'skill' | 'setting';
  shortcut?: string;
  icon?: React.ReactNode;
  action: () => void;
}

const commands: Command[] = [
  { id: 'skill-center', label: '打开技能中心', category: 'navigation', shortcut: 'Cmd+Shift+K' },
  { id: 'execute-fastqc', label: '执行 FastQC 质控', category: 'skill' },
  { id: 'new-chat', label: '新建对话', category: 'action', shortcut: 'Cmd+N' },
  { id: 'toggle-theme', label: '切换主题', category: 'setting' }
];
```

---

### Phase 3: 专家增强 (P3, 2周)

**目标**: 专家用户操作效率提升 50%

#### P3-1: 批量操作支持

**问题**: 无法批量处理

**解决方案**:

```tsx
// 新增: BatchExecutionPanel.tsx
// 功能:
// 1. 批量提交多个技能执行
// 2. 批量下载结果
// 3. 批量配置参数

interface BatchExecution {
  executions: {
    skill_id: string;
    parameters: Record<string, unknown>;
  }[];
  parallelism: number;  // 并行度
  stopOnError: boolean; // 遇错停止
  notification: 'all' | 'errors' | 'none';
}

// UI 设计
// 1. 技能列表支持多选
// 2. 批量参数编辑器
// 3. 执行队列可视化
// 4. 批量结果导出
```

#### P3-2: 工作流编排

**问题**: 无法自定义流程

**解决方案**:

```tsx
// 新增: WorkflowEditor.tsx - 可视化流程编辑器
// 功能:
// 1. 拖拽式流程编排
// 2. 条件分支支持
// 3. 循环执行支持
// 4. 流程模板库

interface WorkflowNode {
  id: string;
  type: 'skill' | 'condition' | 'loop' | 'parallel';
  skill_id?: string;
  parameters?: Record<string, unknown>;
  condition?: string;
  children?: WorkflowNode[];
}

// 流程示例
const rnaSeqWorkflow: WorkflowNode = {
  id: 'rnaseq-pipeline',
  type: 'skill',
  skill_id: 'rnaseq_basic_01',
  children: [
    {
      id: 'quality-check',
      type: 'condition',
      condition: 'fastqc_result.pass',
      children: [
        { id: 'alignment', type: 'skill', skill_id: 'alignment_01' },
        { id: 'quantification', type: 'skill', skill_id: 'quantification_01' },
        { id: 'de-analysis', type: 'skill', skill_id: 'de_analysis_01' }
      ]
    }
  ]
};
```

#### P3-3: 团队协作功能

**问题**: 无法分享配置

**解决方案**:

```typescript
// 新增: TeamSharingService.ts
// 功能:
// 1. 分享参数模板
// 2. 分享工作流
// 3. 团队技能库
// 4. 执行记录分享

interface SharedResource {
  id: string;
  type: 'template' | 'workflow' | 'skill';
  owner_id: number;
  team_id?: number;
  is_public: boolean;
  share_link?: string;
  created_at: number;
}

// API 设计
// POST /api/share/template - 分享模板
// GET /api/share/{share_id} - 获取分享内容
// POST /api/team/{team_id}/templates - 添加到团队库
```

---

### Phase 4: 智能辅助 (P4, 持续)

**目标**: AI 辅助降低学习成本 60%

#### P4-1: 智能输入助手

**功能**: 根据用户输入意图，自动推荐技能和参数

```typescript
// 新增: IntelligentInputAssistant.ts
// 流程:
// 1. 用户输入自然语言需求
// 2. 意图识别
// 3. 技能推荐 + 参数预填
// 4. 一键确认执行

interface InputAnalysis {
  intent: string;           // 用户意图
  confidence: number;       // 置信度
  recommended_skills: {
    skill_id: string;
    match_reason: string;
    pre_filled_params: Record<string, unknown>;
  }[];
  clarification_questions?: string[]; // 需要澄清的问题
}

// 示例
// 用户输入: "我想分析这个单细胞数据，看看有没有什么异常"
// 系统响应:
// - 推荐技能: singlecell_seurat_pipeline_01
// - 预填参数: input_dir = "/data/cell_data", min_genes = 200
// - 澄清问题: "您想进行哪种类型的分析？质控/聚类/差异分析？"
```

#### P4-2: 错误智能诊断

**功能**: 执行失败时，自动分析原因并提供修复建议

```typescript
// 已有: ErrorDiagnosticService.ts
// 增强:
// 1. 错误分类（参数错误/环境错误/数据错误）
// 2. 修复建议排序
// 3. 一键修复支持

interface EnhancedErrorDiagnosis {
  error_type: 'parameter' | 'environment' | 'data' | 'system';
  severity: 'low' | 'medium' | 'high' | 'critical';
  message: string;
  user_friendly_message: string; // 非技术人员可理解
  root_cause: string;
  fix_suggestions: {
    description: string;
    auto_fixable: boolean;
    fix_command?: string;
    manual_steps?: string[];
    estimated_time?: string;
  }[];
  related_help_docs?: string[];
}
```

#### P4-3: 学习助手

**功能**: 根据用户行为，推荐相关学习资源

```typescript
// 新增: LearningAssistant.ts
// 功能:
// 1. 分析用户操作记录
// 2. 推荐相关教程
// 3. 提供最佳实践建议

interface LearningRecommendation {
  trigger_action: string;  // 触发推荐的操作
  recommendations: {
    type: 'tutorial' | 'best_practice' | 'tip' | 'shortcut';
    title: string;
    content: string;
    link?: string;
    relevance_score: number;
  }[];
}

// 示例
// 用户操作: 执行 FastQC 后查看结果
// 推荐内容:
// - 教程: "如何解读 FastQC 报告"
// - 提示: "按住 Shift 点击图表可放大查看"
// - 快捷键: "Cmd+E 快速导出报告"
```

---

## 五、实施优先级

### P0: 立即实施（本周）

| 任务 | 文件 | 工作量 | 收益 |
|------|------|--------|------|
| 首页引导优化 | `ChatStage.tsx`, `OnboardingGuide.tsx` | 2天 | 新用户转化 +30% |
| 参数智能分组 | `ParameterGroupPanel.tsx` | 1天 | 填写效率 +50% |
| 移动端触摸优化 | `MobilePanels.tsx`, `Sidebar.tsx` | 1天 | 移动端可用性 +40% |
| 快捷键系统 | `KeyboardShortcuts.ts` | 1天 | 专家效率 +30% |

### P1: 短期实施（2周内）

| 任务 | 文件 | 工作量 | 收益 |
|------|------|--------|------|
| 参数模板系统 | `ParameterTemplateService.ts` | 3天 | 重复操作 -70% |
| 命令面板 | `CommandPalette.tsx` | 2天 | 功能发现 +50% |
| 智能默认值 | `DefaultValueInferencer.ts` | 2天 | 输入量 -40% |
| 错误诊断增强 | `ErrorDiagnosticService.ts` | 2天 | 错误恢复 +60% |

### P2: 中期实施（1个月内）

| 任务 | 文件 | 工作量 | 收益 |
|------|------|--------|------|
| 批量操作支持 | `BatchExecutionPanel.tsx` | 4天 | 批量效率 +200% |
| 工作流编排 | `WorkflowEditor.tsx` | 5天 | 流程自动化 |
| 团队协作功能 | `TeamSharingService.ts` | 3天 | 协作效率 +100% |
| 智能输入助手 | `IntelligentInputAssistant.ts` | 4天 | 学习成本 -50% |

---

## 六、验收标准

### 6.1 定量指标

| 指标 | 当前值 | P1目标 | P2目标 | P3目标 |
|------|--------|--------|--------|--------|
| 新手首次成功时间 | 10分钟 | 5分钟 | 3分钟 | 2分钟 |
| 参数填写时间 | 2分钟 | 1分钟 | 30秒 | 15秒 |
| 任务完成点击数 | 6次 | 4次 | 3次 | 2次 |
| 移动端完成率 | 40% | 60% | 75% | 85% |
| 错误恢复成功率 | 30% | 50% | 70% | 90% |

### 6.2 定性指标

**新手用户访谈问题**:
- [ ] 首次使用时，能快速知道系统是做什么的
- [ ] 能在3分钟内找到并执行一个分析任务
- [ ] 执行失败时，能理解错误信息并知道如何修复

**中级用户访谈问题**:
- [ ] 能快速找到常用功能
- [ ] 参数填写效率满意
- [ ] 能方便地复用之前的配置

**专家用户访谈问题**:
- [ ] 快捷键能覆盖高频操作
- [ ] 能批量处理多个任务
- [ ] 能自定义分析流程

**移动端用户访谈问题**:
- [ ] 能单手完成主要操作
- [ ] 触摸目标大小合适
- [ ] 网络不佳时仍能使用核心功能

---

## 七、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 新手引导过于繁琐 | 中 | 高 | A/B 测试，收集用户反馈 |
| 快捷键冲突 | 低 | 中 | 遵循系统规范，提供自定义 |
| 移动端性能下降 | 中 | 中 | 懒加载、虚拟滚动、骨架屏 |
| 学习曲线陡峭 | 中 | 高 | 渐进式披露，情境帮助 |
| 功能膨胀 | 高 | 中 | 严格需求评审，功能优先级排序 |

---

## 八、总结

本计划从四个用户角色出发，系统性地评估了当前界面的摩擦点，并制定了四阶段升级策略：

1. **P1 新手友好化**: 降低学习成本，让新用户 3 分钟内完成首次分析
2. **P2 效率提升**: 减少重复操作，让中级用户效率提升 50%
3. **P3 专家增强**: 提供高级功能，让专家用户操作更高效
4. **P4 智能辅助**: AI 辅助决策，降低所有用户的学习成本

**核心设计原则**:
- **渐进式披露**: 新手看简单，专家看详细
- **一致性**: 相同功能在不同位置表现一致
- **容错性**: 错误可恢复，操作可撤销
- **效率优先**: 减少点击、减少输入、减少等待

**预期收益**:
- 新用户转化率提升 30%
- 用户满意度提升 25%
- 任务完成时间减少 50%
- 移动端使用率提升 100%

---

## 九、实施进度追踪

| Phase | 开始日期 | 完成日期 | 状态 |
|-------|----------|----------|------|
| P0 新手友好化 | 2026-03-31 | 2026-04-02 | ✅ 已完成 |
| P1 效率提升 | 2026-04-02 | 2026-04-05 | ✅ 已完成 |
| P2 专家增强 | 2026-04-05 | 2026-04-08 | ✅ 已完成 |
| P3 团队协作 | 2026-04-08 | 2026-04-09 | ✅ 已完成 |

### 已实现功能清单

**P0 新手友好化**:
- `OnboardingGuide.tsx` - 新手引导组件，首次访问显示功能卡片
- `KeyboardShortcuts.ts` - 全局快捷键系统，支持自定义快捷键
- `ShortcutManager.tsx` - 快捷键管理器组件
- `mobile/MobileNav.tsx` - 移动端导航组件
- `mobile/MobileSidebarSheet.tsx` - 移动端侧边栏

**P1 效率提升**:
- `ParameterGroupPanel.tsx` - 参数智能分组面板
- `parameterGrouper.ts` - 参数分组工具函数（含测试）
- `CommandPalette/` - VS Code 风格命令面板（Cmd+K 唤起）
- `SkillFormBuilder` - 4 级参数预填（显式提及 > 实体提取 > 工作区推断 > 默认值）
- `ParamUpdate` - 自然语言参数修改（json_param_update）
- `ErrorDiagnosticService` - 增强错误诊断服务 + 一键修复 API
- `apiCache.ts` - API 缓存（TTL, stale-while-revalidate, 请求去重）
- `contentFilter.ts` - LLM 输出过滤（thinking 标签、参数标签）

**P2 专家增强**:
- `SuperExecutorV4` - 三阶段执行引擎（探查→安装→执行）
- `SandboxPlanner` - PTY + Claude Code 沙箱规划器（门控）
- `ContainerPoolService` - Docker 容器暖池（PYTHON/R/GENERAL 三池）
- `BatchScheduler` - Celery Beat 定时任务（学习周期、索引重建、过期清理）
- `WorkflowOrchestrator` - DAG 工作流编排
- `ExecutionProgress.tsx` - 执行进度组件

**P3 团队协作**:
- `skill_share.py` - 技能分享路由（含权限管理）
- `skill_version.py` - 技能版本管理和回滚
- `SkillDetailDrawer.tsx` - 技能详情抽屉
- `SkillRecommendArea.tsx` - 技能推荐区域
- `RecommendationCard.tsx` - 技能推荐卡片（渲染 json_action_menu）
- `InlineActionMenu/` - 4 阶段内联操作工作流
- `parseActionMenu` - 支持 actions + options 双格式解析

### V2 架构升级（2026-04-09 ~ 2026-04-12）

在 PLAN8 基础上，进行了 V2 Agent 架构升级：

| 里程碑 | 提交 | 内容 |
|--------|------|------|
| M1.1+M1.2+M2.1+M2.2 | `9fe7f8a` | V2 架构升级：单节点图 + 路由节点 + 意图精简 |
| M2.3 | `eb637dc` | 沙箱规划器接入路由流 |
| M2.4 | `0d6f132` | Warm Pool 容器管理集成 |
| M3 | `fbeda52` | 内联交互 UI 重构 |
| M4+M5 | `94b4e4a` | 智能参数系统 + 黑盒消除 |
| V2 启用 | `92c5dac` | 启用 V2 全部新功能 |
| V2 日志 | `722540e` | Router 节点增加 V2 日志输出 |
| V2 测试 | `f65b9a2` | V2 测试套件 + 后端日志增强 |
| V2 修复 | `2c37d26` | V2 功能自动化测试修复 20 个 bug |

---

*文档版本: 2.0.0*
*创建时间: 2026-03-31*
*更新时间: 2026-04-12*
*维护者: Autonome Team*