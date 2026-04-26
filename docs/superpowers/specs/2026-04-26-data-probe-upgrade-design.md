# 数据探查系统全面升级设计

## 概述

将数据探查（DATA_PROBE）从"终点节点"升级为"跨意图基础设施"，使探针结果可被下游节点（SKILL_FORGE、EXPLICIT_EXEC、ADHOC、WORKFLOW_ORCHESTRATE）结构化消费，并支持条件 DAG 自动分支执行。

## 背景

基于 10 个测试用例的验证结果（4 个失败），以及跨意图对接需求，识别出以下系统性问题：

- **L0 ProbePatternRule 覆盖缺口**：编码检测等场景需要文件上下文，但乱码文件不会是 active_file
- **L1 ADHOC vs DATA_PROBE 边界模糊**：轻量计算（集合运算、NA 检测）被误判为 ADHOC
- **条件 DAG 缺乏执行支持**：图执行层只支持顺序推进，无分支能力
- **探针结果不可消费**：输出为自由文本，下游节点无法解析结构化数据

## 设计原则

1. 全自动条件探针：阈值判断自动执行，无需用户干预
2. 双模输出：探针工具同时返回人类可读文本 + 机器可解析 JSON
3. 向后兼容：现有自由文本流程不受影响
4. 渐进升级：每层独立可测，不破坏现有功能

---

## 第一层：L0 ProbePatternRule 修复

### 问题

`PROBE_KEYWORDS` 中的编码/分隔符检测关键词需要 `has_file_context` 才能匹配。但编码检测场景下，文件是"打不开的/乱码的"，不会成为 active_file，导致查询漏到 L1 被误判为 DIAGNOSTIC_RECOVERY。

### 方案

将编码/分隔符/格式检测关键词从 `PROBE_KEYWORDS`（需要文件上下文）移到 `FILE_EXPLORATION_KEYWORDS`（无需文件上下文）。同时扩展匹配范围覆盖"乱码"、"打不开"等用户表述。

同时，在 `CodeGenPatternRule` 中增加排除模式：当查询同时包含探查动词（扫描/检查/看看/查看）时，不拦截为 SKILL_FORGE。

### 修改文件

- `autonome-backend/app/agent/router/l0_rules.py` — ProbePatternRule + CodeGenPatternRule

### 涉及测试用例

- Test Case 7（编码检测 → DIAGNOSTIC 修复）
- Test Case 10（FASTQ 配对 → SKILL_FORGE 修复）

---

## 第二层：L1 解构器增强

### 问题 1：ADHOC vs DATA_PROBE 边界

L1 prompt 虽有 V2.3 扩展说明"轻量文件内计算属于 DATA_PROBE"，但 LLM 对"算重叠"、"算比例"等词仍倾向路由到 ADHOC。

### 方案

在 L1 prompt 边界 4 中增加**操作动词 → 意图映射表**和具体示例：

```
新增规则：操作动词决定意图归属

"查看/检查/探测/检测/扫描/配对/预览" → DATA_PROBE（只看不算）
"计算重叠/取交集/算比例/统计缺失" → DATA_PROBE（轻量计算，结果用于了解数据）
"画图/可视化/聚类/建模/差异分析" → ADHOC（生成图表或模型）
"写脚本/生成代码/重构" → SKILL_FORGE（代码产出）

示例：
- "算两个文件的基因重叠比例" → DATA_PROBE（集合运算，轻量计算）
- "画基因重叠的 Venn 图" → ADHOC（可视化产出）
- "检查 NA 比例，超过5%就停止" → DATA_PROBE（条件探针，task_1）
```

### 问题 2：条件 DAG 分解

Test Case 8 需要 L1 识别"先检查...如果...就停止...否则..."模式。

### 方案

在 L1 prompt 中增加条件 DAG 生成规则。L1 识别到条件模式时，生成 `is_conditional=true` 的 DAG，task_1.parameters 中包含 `condition` 字段：

```json
{
  "nodes": [
    {
      "task_id": "task_1",
      "intent": "INTENT_DATA_PROBE",
      "raw_instruction": "检查矩阵的 NA 比例",
      "parameters": {
        "probe_action": "detect_na",
        "condition_field": "overall_na_ratio",
        "condition_operator": "gt",
        "condition_value": 0.05,
        "on_true": "stop",
        "on_false": "continue"
      }
    }
  ],
  "is_conditional": true
}
```

### 修改文件

- `autonome-backend/app/agent/router/l1_classifier.py` — L1_DECOMPOSER_PROMPT_TEMPLATE

### 涉及测试用例

- Test Case 6（集合运算 → ADHOC 修复）
- Test Case 8（条件探针 → ADHOC 修复）

---

## 第三层：结构化探查报告

### 问题

11 个探针工具输出都是美化的中文字符串，下游节点无法解析。例如 SKILL_FORGE 不知道 NA 比例是 2% 还是 30%。

### 方案

每个探针工具返回**双模 JSON**：`summary`（人类可读文本，现有输出）+ `structured`（机器可解析字段）。

```python
{
  "summary": "人类可读的格式化报告（现有输出）",
  "structured": {
    # 机器可解析的标准化字段
  }
}
```

各工具的 `structured` 字段定义：

| 工具 | structured 关键字段 |
|------|-------------------|
| `peek_tabular_data` | `n_rows`, `n_cols`, `headers[]`, `delimiter`, `file_size_kb` |
| `detect_na` | `overall_na_ratio`, `columns[]` (name/missing_count/missing_ratio), `total_missing` |
| `compute_summary_stats` | `columns[]` (name/min/max/mean/std/q1/median/q3), `log_transformed_hint` (bool) |
| `compute_set_operations` | `n_set1`, `n_set2`, `n_intersection`, `n_union`, `n_diff1`, `n_diff2`, `overlap_ratio` |
| `detect_file_encoding` | `encoding`, `confidence`, `delimiter`, `has_bom` |
| `match_paired_fastq` | `n_pairs`, `n_r1_only`, `n_r2_only`, `n_unmatched`, `pairs[]`, `r1_only[]`, `r2_only[]` |
| `inspect_bam` | `total_reads`, `mapping_rate`, `avg_insert_size`, `reference_genome` (from @SQ AS), `rg_samples[]` |
| `inspect_vcf` | `n_samples`, `n_variants`, `samples[]`, `variant_types{}` (SNP/INDEL/SV/OTHER counts) |
| `inspect_h5ad` | `n_obs`, `n_vars`, `obs_columns[]`, `var_columns[]`, `obsm_keys[]` |
| `scan_workspace` | `n_files`, `n_dirs`, `extensions{}`, `file_tree` |
| `inspect_fastq` | `n_reads`, `avg_length`, `min_length`, `max_length`, `avg_gc` |

### data_probe_node 写入结构化结果

data_probe_node 从工具调用结果中提取 `structured` 字段，写入 `task_results[task_id].probe_report`：

```python
task_results[task_id] = {
    "status": "success",
    "node": "data_probe_node",
    "result": accumulated_response,          # 人类可读文本（现有）
    "probe_report": {                         # 新增：结构化探查报告
        "tool_name": "detect_na",
        "fields": {
            "overall_na_ratio": 0.02,
            "total_missing": 150,
            "n_rows": 20000,
            "n_cols": 35
        }
    }
}
```

### 向下兼容

- `result` 字段保留（人类可读文本），现有前端展示不受影响
- `probe_report` 为新增字段，下游节点按需读取
- 如果工具返回的 JSON 解析失败，`probe_report` 为 `None`，降级为纯文本模式

### 修改文件

- `autonome-backend/app/tools/probe_tools.py` — 11 个工具的 `return` 格式改为 JSON
- `autonome-backend/app/agent/nodes/data_probe_node.py` — 解析 structured 字段并写入 probe_report

---

## 第四层：条件 DAG 执行引擎

### 问题

图执行层 `task_advance_or_end` 只支持顺序推进。即使 L1 生成了条件 DAG，执行层无法评估条件分支。

### 方案

#### 4.1 新增 DAGCondition 模型（schemas.py）

```python
class DAGCondition(BaseModel):
    """DAG 条件分支定义"""
    field: str              # 探针报告中用于判断的字段路径，如 "overall_na_ratio"
    operator: str           # gt | lt | gte | lte | eq | neq
    value: Any              # 阈值
    on_true: str            # "stop" | "continue" | task_id
    on_false: str           # "stop" | "continue" | task_id
    source_task_id: str     # 条件数据来源的探针任务 ID
```

`TaskNode` 新增字段：

```python
condition: Optional[DAGCondition] = Field(default=None)
```

#### 4.2 条件路由函数（graph.py）

新增 `evaluate_condition_and_route`：

1. 检查当前 task 是否有 condition 定义
2. 从 `task_results[source_task_id].probe_report.fields` 获取实际值
3. 执行比较运算
4. 根据 on_true/on_false 返回路由目标（END / intent_router / 指定 task_id）

#### 4.3 图结构变更

```
data_probe_node → evaluate_condition_and_route
    ├── END (条件触发停止)
    ├── intent_router (推进到下一任务)
    └── task_advance_or_end (无条件时的正常推进)
```

#### 4.4 执行时序（Test Case 8 示例）

```
用户: "先检查 NA 比例，超过5%就停止，否则输出可以继续"
    ↓
L1: 生成条件 DAG
    task_1: DATA_PROBE(detect_na, condition: na_ratio>0.05→stop, ≤0.05→continue)
    task_2: GENERAL_CHAT("输出可以继续的信号", deps: [task_1])
    ↓
data_probe_node(task_1): detect_na → probe_report.fields.overall_na_ratio = 0.02
    ↓
evaluate_condition_and_route: 0.02 ≤ 0.05 → on_false="continue"
    ↓
intent_router → task_2: chat_node → "NA 比例仅 2%，数据质量良好，可以继续"
```

### 修改文件

- `autonome-backend/app/agent/router/schemas.py` — 新增 DAGCondition，TaskNode 加 condition 字段
- `autonome-backend/app/agent/graph.py` — 新增 evaluate_condition_and_route，修改 data_probe_node 出边

### 涉及测试用例

- Test Case 8（条件探针 DAG 执行）

---

## 第五层：跨意图对接 + 探针工具增强

### 5.1 跨意图数据流协议

定义标准消费模式，下游节点通过 `get_upstream_probe_results(state, task)` 获取上游探针的结构化结果。

各下游意图的典型消费模式：

| 下游意图 | 消费的探针字段 | 典型行为 |
|---------|-------------|---------|
| SKILL_FORGE | `overall_na_ratio`, `n_cols`, `headers[]`, `delimiter`, `encoding` | 根据 NA 比例决定是否生成插补代码；根据列名生成正确变量引用；根据编码/分隔符生成正确的 read_csv 参数 |
| EXPLICIT_EXEC | `n_rows`, `file_size`, `log_transformed_hint` | 根据数据规模选择节点规格；根据 Log 转换状态调整参数 |
| ADHOC | `headers[]`, `n_cols`, `n_rows`, 分布统计 | 自动选择可视化策略；根据维度建议图表类型 |
| WORKFLOW_ORCHESTRATE | `n_pairs`, `r1_only[]`, `r2_only[]` | 根据 FASTQ 配对结果决定跳过缺失样本；生成条件流程分支 |

### 5.2 新增探针工具

**`inspect_mtx`** — 轻量级 MTX 矩阵维度探测（不加载全量数据）

- 只读 MTX 文件头 2 行，正则提取行列数和非零元素数
- 对 10GB+ 的 MTX 文件同样秒级返回
- structured 字段：`n_rows`, `n_cols`, `n_nonzero`, `format` (coordinate/array)

**`detect_file_type`** — 基于内容和扩展名综合判断文件类型

- 扩展名检测（第一优先级）
- 文件头 magic bytes 检测
- 内容模式匹配（VCF 的 #CHROM、GTF 的九列格式、FASTA 的 > 开头、FASTQ 的 @+质量行模式等）
- structured 字段：`primary_type`, `confidence`, `alternative_types[]`

### 5.3 data_probe_node prompt 增强

更新 `DATA_PROBE_SYSTEM_PROMPT`，增加跨意图协作指南：

```
## 跨意图协作指南

你的探查结果可能被下游节点消费。请在回答中：
1. 先给出结构化发现（数值、列表、判断）
2. 再给出对下游分析的建议
3. 明确指出潜在风险和注意事项
```

### 修改文件

- `autonome-backend/app/tools/probe_tools.py` — 新增 inspect_mtx, detect_file_type
- `autonome-backend/app/agent/nodes/data_probe_node.py` — prompt 更新, probe_tools_list 更新

---

## 升级范围汇总

| 层 | 文件 | 改动内容 | 解决用例 |
|----|------|---------|---------|
| L0 | `l0_rules.py` | ProbePatternRule: 编码检测移到无文件上下文区；CodeGenPatternRule: 加探查词排除 | TC7, TC10 |
| L1 | `l1_classifier.py` | Prompt: 动词→意图映射表 + 条件DAG生成规则 | TC6, TC8 |
| 结构化 | `probe_tools.py` | 11个工具输出改为双模 JSON（summary + structured） | 跨意图 |
| 结构化 | `data_probe_node.py` | 解析工具 structured 字段，写入 probe_report | 跨意图 |
| 条件DAG | `schemas.py` | 新增 DAGCondition 模型，TaskNode 加 condition 字段 | TC8 |
| 条件DAG | `graph.py` | 新增 evaluate_condition_and_route，修改 data_probe_node 出边 | TC8 |
| 新工具 | `probe_tools.py` | 新增 inspect_mtx, detect_file_type；更新 probe_tools_list | TC1, 通用 |
| Prompt | `data_probe_node.py` | DATA_PROBE_SYSTEM_PROMPT 增加跨意图协作指南 | 全局 |

## 测试验证

升级完成后，针对 10 个测试用例重新验证：

1. 🟢 TC1-TC5, TC9：应保持通过（回归测试）
2. 🟡 TC6：集合运算 → INTENT_DATA_PROBE
3. 🟡 TC7：编码检测 → INTENT_DATA_PROBE
4. 🔴 TC8：条件探针 → DATA_PROBE DAG + 条件分支自动执行
5. 🟡 TC10：FASTQ 配对 → INTENT_DATA_PROBE

### 新增测试用例

11. **跨意图：探针 → SKILL_FORGE**："检查表达矩阵的 NA 比例和列名，然后帮我写个数据清洗脚本"
    - 预期：task_1=DATA_PROBE → task_2=SKILL_FORGE（消费探针结果）

12. **跨意图：探针 → EXPLICIT_EXEC**："先看看这个 BAM 的比对率和参考基因组，确认是 hg38 就运行 featureCounts"
    - 预期：task_1=DATA_PROBE(inspect_bam) → 条件判断(reference_genome=hg38) → task_2=EXPLICIT_EXEC

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 结构化 JSON 输出增加工具返回体积 | structured 字段只包含关键数值，不含原始数据 |
| L1 prompt 增长导致分类延迟增加 | 新增内容约 300 tokens，在可接受范围 |
| 条件 DAG 执行路径增加复杂度 | 条件评估失败时安全降级为 END，不阻塞 |
| 旧版 tool 调用方依赖纯文本输出 | summary 字段保持现有格式完全不变 |
