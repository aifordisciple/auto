# AUTONOME 技能生态系统全面升级计划

> **文档版本**: v2.0
> **创建日期**: 2026-03-15
> **目标**: 构建从"发现 → 创建 → 使用 → 沉淀 → 新技能"的完整闭环生态

---

## 一、用户角色画像与使用场景

### 1.1 核心用户角色

| 角色 | 技术背景 | 核心诉求 | 典型场景 |
|------|----------|----------|----------|
| **生信工程师** | 熟练 Python/R/Nextflow | 将脚本标准化为可复用技能 | 写了一个分析脚本，想封装成技能分享给团队 |
| **数据分析师** | 会用现成工具，了解参数含义 | 快速找到合适的分析技能 | 手上有 RNA-seq 数据，想找到合适的分析流程 |
| **生物学家/研究员** | 无编程背景 | 一键分析，智能推荐 | 想做差异基因分析，不知道用什么工具 |
| **平台管理员** | 运维、审核 | 技能质量控制、审核发布 | 审核用户提交的技能，管理公共技能库 |

### 1.2 完整用户旅程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          技能生态用户旅程                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  [场景A: 从零开始创建技能]                                               │
│  用户有分析需求 → 与AI对话 → AI推荐技能/生成代码                         │
│      → 测试验证成功 → 一键转化为技能 → 分享给团队                         │
│                                                                          │
│  [场景B: 发现并使用现有技能]                                             │
│  用户有数据 → 打开技能中心 → 搜索/浏览技能                               │
│      → 查看详情和评价 → 配置参数 → 执行 → 查看结果                       │
│                                                                          │
│  [场景C: 从现有代码创建技能]                                             │
│  用户有现成脚本 → 打开技能工厂 → 导入代码                                │
│      → AI推断参数 → 编辑完善 → 测试验证 → 发布                           │
│                                                                          │
│  [场景D: 知识沉淀与复用]                                                 │
│  用户成功完成分析 → 系统提示"转化为技能?" → 一键确认                     │
│      → AI自动生成SKILL规范 → 用户微调 → 保存为私有技能                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、现有系统全面评估

### 2.1 已实现功能评估

#### ✅ 技能规范与解析 (90% 完成度)

| 功能 | 实现状态 | 文件位置 | 评估 |
|------|----------|----------|------|
| SKILL.md 格式定义 | ✅ 完整 | `app/skills/*/SKILL.md` | 格式规范，包含意图、参数、专家知识 |
| YAML 元数据解析 | ✅ 完整 | `app/core/skill_parser.py` | 支持双源解析（文件系统+数据库） |
| 参数 Schema 提取 | ✅ 完整 | `skill_parser.py:146-229` | 支持 JSON Schema 转换 |
| 专家知识提取 | ✅ 完整 | `skill_parser.py:277-293` | 支持 Markdown 解析 |
| 双源解析(文件+数据库) | ✅ 完整 | `get_combined_skills()` | 支持 RBAC 权限控制 |

**存在问题**:
- 参数类型识别不够精确（format 字段识别不完整）
- 缺少 `SampleTable`、`GenomeReference` 等高级参数类型

#### ✅ 技能中心 UI (85% 完成度)

| 功能 | 实现状态 | 文件位置 | 评估 |
|------|----------|----------|------|
| 技能分类导航 | ✅ | `SkillExecutePanel.tsx` | 有分类树，但不够直观 |
| 技能搜索 | ✅ | `SkillExecutePanel.tsx` | 支持名称/ID/标签搜索 |
| 参数表单渲染 | ✅ | `renderParamInput()` | 支持 FilePath/DirectoryPath |
| 执行状态展示 | ✅ | `pollTaskStatus()` | 有轮询和状态展示 |
| 实时日志流 | ✅ | SSE `/api/tasks/{id}/logs/stream` | 有终端风格日志显示 |
| 技能市场 Tab | ✅ | `SkillMarketPanel.tsx` | 已整合到技能中心 |

**存在问题**:
- 分类导航层级较浅，二级分类使用不便
- 缺少技能详情页（参数说明、使用案例）
- 无技能推荐区域（热门/趋势/个性化）
- 从市场选择技能后跳转执行面板体验不连贯

#### ✅ 技能工厂 UI (80% 完成度)

| 功能 | 实现状态 | 文件位置 | 评估 |
|------|----------|----------|------|
| 多入口创建对话框 | ✅ | `CreateEntryDialog.tsx` | 支持4种创建方式 |
| Monaco 代码编辑器 | ✅ | `SkillDraftEditor.tsx` | 支持 Python/R/Nextflow |
| SKILL.md 预览 | ✅ | `SkillDraftEditor.tsx` | 实时预览生成 |
| 参数 Schema 编辑器 | ✅ | `ParameterSchemaEditor/` | 可视化编辑 |
| 专家知识编辑器 | ✅ | `ExpertKnowledgeEditor.tsx` | 支持 Markdown |
| 依赖包管理 | ✅ | `DependenciesEditor.tsx` | 支持 pip/cran/conda |
| 分类标签选择 | ✅ | `CategoryTagsEditor.tsx` | 支持分类选择 |
| AI 参数推断 | ✅ | `/api/skills/infer_parameters` | LLM 自动推断 |
| 沙箱测试 | ✅ | `TestPanel/` | 支持自动修复 |
| AI 对话创建 | ✅ | `ForgeChatStage.tsx` | SSE 流式对话 |

**存在问题**:
- 模板库为空，模板实例化入口不可用
- 缺少技能版本对比功能
- 测试面板结果预览功能较弱

#### ✅ 聊天集成与推荐 (70% 完成度)

| 功能 | 实现状态 | 文件位置 | 评估 |
|------|----------|----------|------|
| 技能目录注入 | ✅ | `bot.py:38-63` | 所有技能加载到 Agent Prompt |
| json_strategy 输出 | ✅ | `StrategyCard.tsx` | 前端解析并展示策略卡 |
| json_intent 意图识别 | ✅ | `bot.py:195-223` | Agent 内置意图识别 |
| 技能推荐 API | ✅ | `skill_recommend.py` | 基于关键词匹配 |
| 推荐结果注入聊天 | ✅ | `chat.py` (刚实现) | 推荐注入到用户消息 |
| 知识转化提示 UI | ✅ | `ChatStage.tsx` (刚实现) | 成功后显示转化提示 |

**存在问题**:
- 意图识别规则较简单，可能误判
- 推荐结果未持久化，无法追踪效果

#### ⚠️ 知识沉淀转化 (50% 完成度)

| 功能 | 实现状态 | 文件位置 | 评估 |
|------|----------|----------|------|
| 经验提取 | ✅ | `knowledge_extractor.py` | 可提取成功经验 |
| 成功评估器 | ✅ | `success_evaluator.py` | 评估会话成功度 |
| transform_from_live API | ✅ | `skills.py` (刚实现) | 从会话转化技能 |
| 蓝图固化 | ✅ | `consolidator.py` | DAG 蓝图转技能 |
| 分析结果转技能 | ⚠️ | | UI 入口不明确 |

### 2.2 功能缺失清单

| 优先级 | 缺失功能 | 用户价值 | 实现难度 | 影响 |
|--------|----------|----------|----------|------|
| **P0** | 模板库初始化 | 快速创建常见分析技能 | 低 | 影响技能工厂入口 |
| **P0** | 技能详情页 | 查看参数说明、使用案例 | 低 | 影响用户理解技能 |
| **P1** | 技能推荐区域 | 热门/趋势/个性化推荐 | 低 | 提升技能发现效率 |
| **P1** | 分类体系优化 | 更直观的分类导航 | 低 | 提升浏览体验 |
| **P1** | 技能版本管理 UI | 查看历史版本、回滚 | 中 | 支持技能迭代 |
| **P2** | 技能测试用例保存 | 回归测试保障 | 中 | 提升技能质量 |
| **P2** | AI 代码审查集成 | 提升代码质量 | 中 | 代码质量保障 |
| **P2** | 技能血缘分析 | 版本升级决策支持 | 高 | 影响分析有限 |

---

## 三、升级计划详细设计

### Phase 1: 技能中心体验优化 (P0)

#### 3.1.1 技能详情页

**需求**: 用户点击技能后，可以查看详细的参数说明、使用案例、评分评论。

**实现方案**:

```typescript
// 新增 SkillDetailDrawer 组件
interface SkillDetailDrawerProps {
  skillId: string;
  onClose: () => void;
  onUse: () => void;  // 跳转到执行面板
}

// 内容包含:
// 1. 基本信息: 名称、版本、作者、分类
// 2. 参数说明: 每个参数的详细说明、默认值、类型
// 3. 使用案例: 示例参数配置
// 4. 评分评论: 用户评价和评分
// 5. 执行历史: 用户的历史执行记录
```

**文件修改**:
- 新增: `autonome-studio/src/components/overlays/SkillCenter/SkillDetailDrawer.tsx`
- 修改: `autonome-studio/src/components/overlays/SkillCenter/SkillExecutePanel.tsx`
- 新增 API: `GET /api/skills/{skill_id}/details` (含评论和评分)

#### 3.1.2 技能推荐区域

**需求**: 在技能中心首页展示热门技能、新上线技能、个性化推荐。

**实现方案**:

```typescript
// 在 SkillCenter 首页添加推荐区域
<div className="p-4 border-b border-neutral-800">
  {/* 热门技能 */}
  <div className="mb-4">
    <h3 className="text-sm font-medium text-neutral-300 mb-2">🔥 热门技能</h3>
    <div className="flex gap-2 overflow-x-auto pb-2">
      {trendingSkills.map(skill => <SkillCard key={skill.skill_id} skill={skill} />)}
    </div>
  </div>

  {/* 新上线 */}
  <div className="mb-4">
    <h3 className="text-sm font-medium text-neutral-300 mb-2">✨ 新上线</h3>
    ...
  </div>

  {/* 个性化推荐 */}
  <div>
    <h3 className="text-sm font-medium text-neutral-300 mb-2">💡 为你推荐</h3>
    ...
  </div>
</div>
```

**API 调用**:
- `GET /api/skill-recommend/trending?limit=5`
- `GET /api/skill-recommend/recent?limit=5`
- `GET /api/skill-recommend/personalized?limit=5`

#### 3.1.3 分类导航优化

**需求**: 优化分类层级，支持更直观的浏览体验。

**实现方案**:

```typescript
// 扩展分类体系
const CATEGORIES = {
  'quality_control': {
    name: '质量控制',
    icon: '🔬',
    subcategories: {
      'fastq_qc': 'FastQ质控',
      'bam_qc': 'BAM质控',
      'vcf_qc': 'VCF质控'
    }
  },
  'single_cell': {
    name: '单细胞分析',
    icon: '🧬',
    subcategories: {
      'scrna_seq': 'scRNA-seq',
      'scatac_seq': 'scATAC-seq',
      'spatial': '空间转录组'
    }
  },
  // ... 更多分类
};
```

### Phase 2: 技能工厂功能完善 (P0)

#### 3.2.1 模板库初始化

**需求**: 提供预置模板，让用户可以快速实例化常见分析技能。

**实现方案**:

```python
# app/core/init_templates.py

SKILL_TEMPLATES = [
    {
        "template_id": "fastqc_qc_template",
        "name": "FastQC 质量控制",
        "description": "对原始测序数据进行质量检测",
        "executor_type": "Python_env",
        "script_template": """
import argparse
import os
import subprocess

def main():
    parser = argparse.ArgumentParser(description='FastQC Quality Control')
    parser.add_argument('--input_dir', type=str, required=True)
    parser.add_argument('--output_dir', type=str, default='./results/fastqc')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()

    # FastQC execution logic
    ...
""",
        "parameters_schema": {
            "type": "object",
            "properties": {
                "input_dir": {"type": "string", "format": "directorypath", "description": "输入FastQ目录"},
                "output_dir": {"type": "string", "format": "directorypath", "default": "./results/fastqc"},
                "threads": {"type": "integer", "default": 4}
            },
            "required": ["input_dir"]
        },
        "category": "quality_control"
    },
    {
        "template_id": "deseq2_deg_template",
        "name": "DESeq2 差异分析",
        "description": "RNA-seq 差异表达基因分析",
        "executor_type": "R_env",
        ...
    },
    {
        "template_id": "scanpy_scrna_template",
        "name": "Scanpy 单细胞分析",
        "description": "单细胞 RNA-seq 标准流程",
        "executor_type": "Python_env",
        ...
    },
    {
        "template_id": "ggplot_vis_template",
        "name": "ggplot2 可视化",
        "description": "数据可视化模板",
        "executor_type": "R_env",
        ...
    }
]

def init_skill_templates():
    """服务启动时初始化模板库"""
    from app.models.domain import SkillTemplate
    from app.core.database import Session

    session = Session()
    try:
        for template_data in SKILL_TEMPLATES:
            existing = session.exec(
                select(SkillTemplate).where(SkillTemplate.template_id == template_data["template_id"])
            ).first()

            if not existing:
                template = SkillTemplate(**template_data)
                session.add(template)

        session.commit()
        log.info(f"✅ 初始化 {len(SKILL_TEMPLATES)} 个技能模板")
    finally:
        session.close()
```

**API 端点**:
- `GET /api/templates` - 获取模板列表
- `POST /api/templates/{template_id}/instantiate` - 实例化模板

#### 3.2.2 技能版本管理 UI

**需求**: 支持查看技能历史版本、对比差异、回滚到指定版本。

**实现方案**:

```typescript
// 新增 VersionHistoryPanel 组件
interface VersionHistoryPanelProps {
  skillId: string;
}

// 功能:
// 1. 版本列表展示（时间线样式）
// 2. 版本对比（diff 视图）
// 3. 回滚操作
// 4. 版本说明编辑
```

**API 端点**:
- `GET /api/skills/{skill_id}/versions` - 获取版本列表
- `POST /api/skills/{skill_id}/versions` - 创建新版本
- `POST /api/skills/{skill_id}/rollback/{version}` - 回滚版本

### Phase 3: 聊天与技能深度集成 (P1)

#### 3.3.1 增强意图识别

**需求**: 更精准地识别用户意图，减少误判。

**实现方案**:

```python
# 在 bot.py 中增强意图识别
INTENT_PATTERNS = {
    "explicit_skill": [
        r"运行\s*(\w+)",
        r"执行\s*(\w+)",
        r"调用\s*(\w+)",
        r"使用\s*(\w+)\s*技能",
    ],
    "implicit_skill": {
        "single_cell": ["单细胞", "scrna", "seurat", "scanpy", "细胞聚类"],
        "rna_seq": ["rna-seq", "转录组", "差异基因", "deseq", "edger"],
        "qc": ["质控", "fastqc", "质量检测"],
        "visualization": ["画图", "可视化", "plot", "热图", "火山图"]
    }
}

async def detect_intent_with_llm(self, user_query: str) -> Dict:
    """使用 LLM 进行精确意图识别"""
    prompt = f"""分析用户需求，判断意图类型:

用户输入: {user_query}

可选意图:
1. explicit_skill: 用户明确提到技能名称
2. implicit_skill: 用户描述的分析需求可被现有技能满足
3. live_coding: 需要自定义代码实现

返回 JSON:
{{"intent_type": "...", "matched_skills": [...], "confidence": 0.0-1.0}}
"""
    response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
    return parse_json_response(response.content)
```

#### 3.3.2 技能推荐追踪

**需求**: 记录推荐结果，分析推荐效果。

**实现方案**:

```python
# 新增数据模型
class SkillRecommendationLog(table=True):
    id: int = Field(primary_key=True)
    user_id: int
    session_id: str
    query: str  # 用户原始查询
    recommended_skills: List[str]  # 推荐的 skill_id 列表
    accepted_skill: Optional[str]  # 用户选择的技能
    created_at: datetime

# 在推荐 API 中记录
@router.post("/recommend")
async def recommend_skills(...):
    # 生成推荐
    recommendations = ...

    # 记录日志
    log = SkillRecommendationLog(
        user_id=current_user.id,
        session_id=request.session_id,
        query=request.user_query,
        recommended_skills=[r.skill_id for r in recommendations]
    )
    session.add(log)
    session.commit()

    return recommendations
```

### Phase 4: 知识沉淀闭环 (P1)

#### 3.4.1 自动转化触发优化

**需求**: 更智能地判断何时触发知识转化提示。

**实现方案**:

```python
# 增强成功评估器
class SuccessEvaluator:
    # 添加代码复杂度评估
    def _evaluate_code_complexity(self, code_blocks: List) -> float:
        """评估代码复杂度，判断是否值得转化为技能"""
        if not code_blocks:
            return 0.0

        total_lines = sum(len(b["code"].split('\n')) for b in code_blocks)
        has_parameters = any('argparse' in b["code"] or 'commandArgs' in b["code"] for b in code_blocks)
        has_output = any('to_csv' in b["code"] or 'write.table' in b["code"] for b in code_blocks)

        score = 0.0
        if total_lines > 20:
            score += 0.3
        if has_parameters:
            score += 0.3
        if has_output:
            score += 0.2
        if total_lines > 50:
            score += 0.2

        return min(score, 1.0)

    def should_prompt_transform(self, session_id: str) -> Dict:
        """
        综合判断是否应该提示用户转化

        Returns:
            {
                "should_prompt": bool,
                "reason": str,
                "confidence": float,
                "suggested_name": str  # AI 生成的建议名称
            }
        """
        result = self.evaluate_session(session_id)
        code_complexity = self._evaluate_code_complexity(extracted_code_blocks)

        should_prompt = (
            result["is_successful"] and
            result["confidence"] > 0.7 and
            code_complexity > 0.5
        )

        return {
            "should_prompt": should_prompt,
            "reason": f"成功完成分析，代码复杂度 {code_complexity:.1%}",
            "confidence": result["confidence"] * code_complexity
        }
```

#### 3.4.2 一键转化流程优化

**需求**: 简化转化流程，自动生成更完整的技能规范。

**实现方案**:

```typescript
// 在 ChatStage.tsx 中优化转化组件
const TransformToSkillPrompt = ({ sessionId, codeBlocks, onClose }) => {
  const [step, setStep] = useState<'preview' | 'edit' | 'saving'>('preview');
  const [draft, setDraft] = useState(null);

  // 自动生成技能草稿
  useEffect(() => {
    generateDraft();
  }, []);

  const generateDraft = async () => {
    const response = await fetch('/api/skills/transform_from_live', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        auto_save: false
      })
    });
    const data = await response.json();
    setDraft(data.draft);
  };

  return (
    <motion.div className="...">
      {step === 'preview' && (
        <DraftPreview
          draft={draft}
          onEdit={() => setStep('edit')}
          onSave={handleSave}
        />
      )}
      {step === 'edit' && (
        <DraftEditor
          draft={draft}
          onChange={setDraft}
          onSave={handleSave}
        />
      )}
    </motion.div>
  );
};
```

---

## 四、系统架构优化

### 4.1 前端组件结构优化

```
autonome-studio/src/
├── components/
│   └── overlays/
│       └── SkillCenter/
│           ├── index.tsx              # 主容器（Tab切换）
│           ├── SkillExecutePanel.tsx  # 执行面板
│           ├── SkillMarketPanel.tsx   # 市场面板
│           ├── SkillDetailDrawer.tsx  # 详情抽屉 ⭐新增
│           ├── SkillRecommendArea.tsx # 推荐区域 ⭐新增
│           └── components/
│               ├── SkillCard.tsx      # 技能卡片
│               ├── CategoryTree.tsx   # 分类树
│               └── ParameterForm.tsx  # 参数表单
├── app/
│   └── skill-forge/
│       ├── page.tsx
│       └── components/
│           ├── CreateEntryDialog.tsx
│           ├── SkillDraftEditor.tsx
│           ├── ParameterSchemaEditor/
│           ├── ExpertKnowledgeEditor.tsx
│           ├── DependenciesEditor.tsx
│           ├── CategoryTagsEditor.tsx
│           ├── VersionHistoryPanel.tsx  ⭐新增
│           └── TestPanel/
```

### 4.2 后端 API 结构优化

```
autonome-backend/app/api/routes/
├── skills.py              # 技能 CRUD
├── skills_forge.py        # 技能工厂
├── skills_market.py       # 技能市场
├── skill_recommend.py     # 技能推荐
└── templates.py           # 模板管理 ⭐新增
```

---

## 五、实施路线图

```
Week 1: Phase 1 技能中心体验优化 (P0)
├── 实现技能详情页组件
├── 添加推荐区域
├── 优化分类导航
└── 测试与验收

Week 2: Phase 2 技能工厂功能完善 (P0)
├── 实现模板库初始化脚本
├── 创建模板 API
├── 实现版本管理 UI
└── 测试模板实例化流程

Week 3: Phase 3 聊天与技能深度集成 (P1)
├── 增强意图识别逻辑
├── 实现推荐追踪
├── 优化推荐提示格式
└── A/B 测试效果评估

Week 4: Phase 4 知识沉淀闭环 (P1)
├── 优化成功评估器
├── 增强转化流程 UI
├── 实现草稿预览编辑
└── 端到端测试
```

---

## 六、验收标准

### 6.1 功能验收

| 功能 | 验收标准 |
|------|----------|
| 技能详情页 | 可查看参数说明、使用案例、评分评论 |
| 技能推荐 | 首页展示热门/新上线/个性化推荐 |
| 模板实例化 | 选择模板 → 实例化 → 编辑保存 |
| 意图识别 | "分析单细胞数据" → 推荐单细胞技能 |
| 知识转化 | 成功分析后 → 显示转化提示 → 一键保存 |

### 6.2 性能验收

| 指标 | 目标值 |
|------|--------|
| 技能列表加载 | < 500ms |
| 技能详情加载 | < 300ms |
| 推荐计算 | < 500ms |
| 转化生成 | < 10s |

### 6.3 用户验收

1. **生信工程师**: 从代码创建技能流程顺畅
2. **数据分析师**: 能快速找到合适的技能
3. **生物学家**: 分析成功后能轻松转化为技能

---

## 七、附录

### A. 关键文件清单

| 优先级 | 文件路径 | 修改内容 |
|--------|----------|----------|
| P0 | `app/core/init_templates.py` | 模板初始化脚本 ⭐新增 |
| P0 | `SkillCenter/SkillDetailDrawer.tsx` | 技能详情页 ⭐新增 |
| P0 | `SkillCenter/SkillRecommendArea.tsx` | 推荐区域 ⭐新增 |
| P1 | `skill-forge/VersionHistoryPanel.tsx` | 版本管理 ⭐新增 |
| P1 | `app/api/routes/templates.py` | 模板 API ⭐新增 |
| P1 | `app/services/success_evaluator.py` | 增强评估逻辑 |

### B. 现有技能清单

| skill_id | 名称 | 执行器类型 | 分类 |
|----------|------|------------|------|
| `fastqc_multiqc_01` | 原始测序数据质量控制 | Logical_Blueprint | quality_control |
| `singlecell_seurat_01` | 单细胞RNA-seq分析 | Python_env | single_cell |
| `meta_nextflow_generator_01` | Nextflow流程生成引擎 | Python_env | pipeline |