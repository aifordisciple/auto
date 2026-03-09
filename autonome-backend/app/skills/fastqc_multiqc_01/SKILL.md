---
# ==========================================
# 核心系统元数据 (Core System Metadata)
# ------------------------------------------
# 以下区域为 YAML 格式，供后端系统路由和调度引擎直接读取
# ==========================================

skill_id: "fastqc_multiqc_pipeline_01"
name: "原始测序数据质量控制与 MultiQC 综合评估"
version: "1.0.0"
author: "BioData Core Analysis Team"
executor_type: "Logical_Blueprint"        # 声明为逻辑蓝图，提示系统此节点需交由 Nextflow_Generator 转化为 .nf 脚本
entry_point: "none"                       # 无直接执行脚本，由下游调度引擎接管
timeout_seconds: 7200                     # 预估处理大量样本可能需要较长时间
---

## 1. 技能意图与功能边界 (Intent & Scope)

*面向 AI 的核心描述，帮助其判断在何种场景下应该召唤此工具。*

本技能是一个标准化的原始测序数据质量评估逻辑模块。它旨在读取单个或大批量的原始 FastQ 格式测序文件（兼容单端 Single-end 和双端 Paired-end 数据），对每个样本并行执行 FastQC 质量检测，并在最后一步自动调用 MultiQC 工具，将所有离散的 FastQC 结果报告聚合拼装成一个直观、易于交互的全局 HTML 质控总结报告。
本工具仅执行“只读”性质的质量检测，绝对不包含任何诸如 Cutadapt、Trimmomatic 等数据修剪或过滤（Trimming）操作，专注于呈现数据最原始的真实状态。

## 2. 动态参数定义规范 (Parameters Schema)

*系统底层的解析器将扫描此表格并转换为严格的 JSON Schema，并在前端渲染动态配置卡片。*

| 参数键名 (Key) | 数据类型 (Type) | 必填 (Required) | 默认值 (Default) | 详细描述说明 (Detailed Description) |
|---|---|---|---|---|
| `fastq_dir` | DirectoryPath | 是 (Yes) | | 存放原始测序数据 (fastq 或 fastq.gz) 的目标文件夹路径。系统将自动扫描该目录下的所有有效测序文件。 |
| `is_paired_end` | Boolean | 是 (Yes) | true | 数据类型声明。如果为 true，代表双端测序数据；如果为 false，代表单端测序数据。这将影响下游 Nextflow 通道 (Channel) 的配对解析逻辑。 |
| `file_pattern` | String | 否 (No) | "*_{1,2}.fastq.gz" | 用于精准匹配和配对双端测序文件的正则表达式或通配符。单端数据通常可设为 "*.fastq.gz"。 |
| `threads_per_sample`| Number | 否 (No) | 4 | 分配给每个 FastQC 进程的 CPU 核心数。建议根据集群实际节点的配置进行动态推断和调整。 |
| `output_dir` | DirectoryPath | 否 (No) | "./qc_reports" | 最终存放所有个体 FastQC 结果以及 MultiQC 汇总 HTML 报告的输出根目录。 |

## 3. 操作指令与专家级知识库 (Operational Directives & Expert Knowledge)

*这里包含了系统赋予大模型的“锦囊妙计”，塑造其资深生信架构师的专业表现。*

- **精确触发条件**：当用户提出“检查一下这批数据的测序质量”、“看看有没有接头污染”、“帮我跑个 FastQC 总结一下”等需求时，应优先调用本技能构建蓝图，并明确告知用户将使用 MultiQC 生成汇总报告。
- **智能参数推断逻辑的底线**：在推断 `is_paired_end` 和 `file_pattern` 时，请务必主动扫描用户工作区 `fastq_dir` 目录下的文件命名特征。如果发现存在明显的 `_R1`/`_R2` 或 `_1`/`_2` 后缀，应果断将其设定为双端测序模式，并补全对应的 `file_pattern`。
- **调度引擎协同指令**：在收集齐所有必填参数后，不要尝试自己去编写长串的 Bash 循环脚本。你必须将此 JSON Payload 提交给具有战略意义的 `[Nextflow_Generator]` 接口，请求其将此逻辑蓝图降维转化为支持高度并行的 Nextflow DSL2 脚本。
- **学术级结果深度解读指导**：当最终的 MultiQC HTML 报告生成并在界面上渲染出“树状资产卡片”后，请在解读时主动引导用户关注以下核心质控指标：
  1. **Per base sequence quality**: 序列碱基质量分布，重点观察尾部的 Q20/Q30 下降趋势是否在可接受范围内。
  2. **Adapter Content**: 接头污染情况。如果接头比例过高，请主动向用户提议：“系统检测到显著的接头残留，强烈建议在进入下游比对环节前，先调用数据修剪（Trimming）SKILL 进行清洗。”
  3. **GC Content**: 检查 GC 含量分布是否存在明显的双峰异常，这可能提示潜在的物种污染或建库文库偏差。