# 意图识别优化：区分编程请求与分析请求

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化意图识别逻辑，区分"编程请求"（用户要代码）和"分析请求"（用户要系统执行分析），避免编程请求错误触发策略卡片。

**Architecture:** 在规则匹配阶段增加"代码生成请求"检测，优先于技能关键词匹配。当检测到编程请求时，直接返回 `LIVE_CODING` 意图类型。

**Tech Stack:** Python 3.10+, FastAPI, 正则表达式匹配

---

## 问题分析

**用户请求示例**：
> "帮我写个程序，输入一个seurat rds文件，绘制两个基因的相关性散点图，标注显著性和R值"

**当前行为**：
- 关键词匹配到 "散点图"、"相关性"、"seurat"
- 触发技能匹配，输出策略卡片

**期望行为**：
- 识别 "写个程序" 为编程请求
- 直接走 live_coding 路径，输出代码
- 不输出策略卡片

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `skill_matcher_config.py` | 添加代码生成请求识别模式 |
| `skill_matcher.py` | 修改 `_rule_match` 方法，优先检查编程请求 |

---

### Task 1: 添加代码生成请求识别模式

**Files:**
- Modify: `autonome-backend/app/services/skill_matcher_config.py:230-235`

- [ ] **Step 1: 在 skill_matcher_config.py 添加代码生成请求识别模式**

在 `NEGATION_WORDS` 定义之后添加以下代码：

```python
# ==========================================
# 代码生成请求识别模式 (CODE_GENERATION_PATTERNS)
# ==========================================
# 当用户请求匹配这些模式时，应该走 live_coding 路径
# 而不是技能匹配路径

CODE_GENERATION_PATTERNS: List[str] = [
    # 中文编程请求模式
    r"写个程序",
    r"写一个程序",
    r"编写程序",
    r"写个脚本",
    r"写一个脚本",
    r"编写脚本",
    r"帮我写代码",
    r"帮我写个",
    r"写一段代码",
    r"实现一个",
    r"开发一个",
    r"写个函数",
    r"写一个函数",
    r"编个程序",
    r"编一个程序",
    r"给我写个",
    r"给我写一个",
    r"能写个",
    r"能写一个",
    r"可以写个",
    r"可以写一个",

    # 英文编程请求模式
    r"write a program",
    r"write a script",
    r"write a function",
    r"write code",
    r"write me a",
    r"can you write",
    r"help me write",
    r"implement a",
    r"develop a",
    r"create a script",
    r"create a program",
]

# 分析请求模式（用户想让系统执行分析）
ANALYSIS_REQUEST_PATTERNS: List[str] = [
    r"帮我分析",
    r"分析一下",
    r"帮我处理",
    r"处理一下",
    r"帮我跑",
    r"跑一下",
    r"运行一下",
    r"执行一下",
    r"帮我做",
    r"分析这些",
    r"处理这些",
    r"run analysis",
    r"analyze",
    r"process this",
]


def is_code_generation_request(query: str) -> bool:
    """
    判断是否为代码生成请求

    代码生成请求的特征：
    1. 用户想要一段代码/脚本
    2. 描述了程序的功能（输入什么、输出什么）
    3. 而不是让系统执行分析

    Args:
        query: 用户查询

    Returns:
        如果是代码生成请求返回 True
    """
    import re
    query_lower = query.lower()

    # 检查是否匹配代码生成模式
    for pattern in CODE_GENERATION_PATTERNS:
        if re.search(pattern, query_lower):
            # 进一步检查：确保不是分析请求
            for analysis_pattern in ANALYSIS_REQUEST_PATTERNS:
                if re.search(analysis_pattern, query_lower):
                    # 如果同时匹配分析模式，优先走分析路径
                    return False
            return True

    return False
```

- [ ] **Step 2: 验证语法正确**

运行: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.services.skill_matcher_config import is_code_generation_request; print(is_code_generation_request('帮我写个程序绘制散点图'))"`
预期输出: `True`

- [ ] **Step 3: 测试分析请求不被误判**

运行: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.services.skill_matcher_config import is_code_generation_request; print(is_code_generation_request('帮我分析这个单细胞数据'))"`
预期输出: `False`

---

### Task 2: 修改规则匹配逻辑

**Files:**
- Modify: `autonome-backend/app/services/skill_matcher.py:217-278`

- [ ] **Step 1: 导入 is_code_generation_request 函数**

在 `skill_matcher.py` 文件顶部的导入部分（约第37-40行），修改导入语句：

```python
from app.services.skill_matcher_config import (
    expand_synonyms, get_keyword_weight, is_negation_context,
    get_context_boost, get_domain_from_keyword, REVERSE_SYNONYM_MAP,
    is_code_generation_request  # 新增导入
)
```

- [ ] **Step 2: 在 _rule_match 方法中添加代码生成请求检查**

在 `_rule_match` 方法中，在检查显式触发词之前，添加代码生成请求检查：

找到以下代码块（约第232-243行）：
```python
async def _rule_match(self, user_query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Phase 1: 规则匹配
    ...
    """
    query_lower = user_query.lower()
    keywords_indexer = self._get_keywords_indexer()

    # 1. 检查显式触发词
    explicit_match = self._check_explicit_trigger(query_lower)
```

修改为：
```python
async def _rule_match(self, user_query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Phase 1: 规则匹配

    基于关键词和同义词进行快速匹配。

    Args:
        user_query: 用户查询
        context: 上下文信息

    Returns:
        匹配结果
    """
    query_lower = user_query.lower()
    keywords_indexer = self._get_keywords_indexer()

    # ✨ 优先级最高：检查是否为代码生成请求
    # 编程请求（用户要代码）应该走 live_coding 路径，而不是技能匹配
    if is_code_generation_request(user_query):
        log.info(f"[SkillMatcher] 检测到代码生成请求，跳过技能匹配: '{user_query[:50]}...'")
        return {
            "intent_type": IntentType.LIVE_CODING,
            "matched_skills": [],
            "confidence": 0.85,
            "parameters_suggestion": {},
            "match_source": "rule",
            "reason": "用户请求代码生成，需要自定义编码实现"
        }

    # 1. 检查显式触发词
    explicit_match = self._check_explicit_trigger(query_lower)
```

- [ ] **Step 3: 验证代码语法**

运行: `cd /opt/data1/public/software/systools/autonome/autonome-backend && python -c "from app.services.skill_matcher import SkillMatcher; print('Import successful')"`
预期输出: `Import successful`

---

### Task 3: 更新 Bot 决策树文档

**Files:**
- Modify: `autonome-backend/app/agent/bot.py:239-264`

- [ ] **Step 1: 更新决策树注释，说明代码生成请求的优先处理**

在 `bot.py` 的决策树部分（约第239行），更新注释：

找到：
```python
<decision_tree>
【智能调度机制 - 关键决策树 (🧠 必须执行)】
在响应用户请求前，请严格按照以下步骤进行意图识别和调度：

▶ 步骤 1：意图识别分析 (必须先输出 intent)
**🚨 优先级顺序：知识型 SKILL > 可执行型 SKILL > Live_Coding**
```

修改为：
```python
<decision_tree>
【智能调度机制 - 关键决策树 (🧠 必须执行)】
在响应用户请求前，请严格按照以下步骤进行意图识别和调度：

▶ 步骤 1：意图识别分析 (必须先输出 intent)
**🚨 优先级顺序：代码生成请求 > 知识型 SKILL > 可执行型 SKILL > Live_Coding**

**特殊处理 - 代码生成请求**（最高优先级）：
- 检测关键词："写个程序"、"写个脚本"、"帮我写代码" 等
- 用户描述程序功能（输入什么、输出什么）
- 匹配成功 → intent_type: "live_coding"，不输出策略卡片，直接生成代码
```

---

### Task 4: 集成测试

- [ ] **Step 1: 启动后端服务**

运行: `cd /opt/data1/public/software/systools/autonome && docker-compose down && docker-compose up -d`
预期: 服务正常启动

- [ ] **Step 2: 测试编程请求**

测试输入: "帮我写个程序，输入一个seurat rds文件，绘制两个基因的相关性散点图"

预期结果:
- `intent_type` 为 `live_coding`
- 不输出策略卡片
- 直接输出代码

- [ ] **Step 3: 测试分析请求**

测试输入: "帮我分析这个单细胞数据，做细胞聚类"

预期结果:
- `intent_type` 为 `implicit_skill` 或 `executable_skill`
- 输出策略卡片

- [ ] **Step 4: 提交代码**

```bash
git add autonome-backend/app/services/skill_matcher_config.py
git add autonome-backend/app/services/skill_matcher.py
git add autonome-backend/app/agent/bot.py
git commit -m "fix: 区分编程请求与分析请求，避免编程请求触发策略卡片

问题：用户请求「写个程序」时，系统错误输出策略卡片

修复：
1. 添加代码生成请求识别模式（write a program, 写个脚本等）
2. 在规则匹配阶段优先检查编程请求
3. 编程请求直接走 live_coding 路径

影响文件：
- skill_matcher_config.py: 新增 CODE_GENERATION_PATTERNS 和 is_code_generation_request
- skill_matcher.py: _rule_match 优先检查编程请求
- bot.py: 更新决策树文档"
```

---

## 测试用例

| 输入 | 期望 intent_type | 期望行为 |
|------|------------------|----------|
| "帮我写个程序，绘制散点图" | `live_coding` | 直接输出代码 |
| "写个脚本处理fastq文件" | `live_coding` | 直接输出代码 |
| "帮我分析这个单细胞数据" | `implicit_skill` | 输出策略卡片 |
| "运行一下RNA-seq质控流程" | `executable_skill` | 输出策略卡片 |
| "写个函数计算基因相关性" | `live_coding` | 直接输出代码 |
| "帮我做差异分析" | `implicit_skill` | 输出策略卡片 |

---

## 成功标准

- [x] 编程请求正确识别为 `live_coding`
- [x] 分析请求正确识别为技能匹配
- [x] 编程请求不输出策略卡片
- [x] 分析请求正常输出策略卡片
- [x] 所有测试用例通过