---
# ==========================================
# 核心系统元数据 (Core System Metadata)
# ==========================================

skill_id: "meta_nextflow_generator_01"
name: "Nextflow 工业级分布式流水线生成与调度引擎"
version: "2.0.0"
author: "Platform Architecture Team"
executor_type: "Python_env"               # 使用 Python 脚本作为引擎入口，用于生成 .nf 并执行
entry_point: "scripts/nf_compiler.py"     # 负责解析 payload、拼装模板、执行 nextflow run 命令
timeout_seconds: 604800                   # 长时间运行支持 (7天)，Nextflow 负责具体的进程守护
---

## 1. 技能意图与功能边界 (Intent & Scope)

*面向 AI 的核心描述：这是整个平台最高阶的调度引擎。*

本技能是系统内置的终极工作流编排器。当用户的分析请求涉及**多个串行/并行步骤**（例如：FastQC -> Trimming -> Alignment -> MultiQC），或者涉及**超大批量样本的高并发处理**时，绝对不能使用容易崩溃的单线程 Bash/Python 脚本，必须调用本 Meta-SKILL。
它能够接收结构化的流程拓扑图 (Topology)，自动将其降维编译为高度严谨的 Nextflow DSL2 工程代码 (`main.nf`)，并无缝对接底层的异构计算集群（如本地多核、SLURM 调度系统或 K8s），实现具备断点续跑 (Resume)、自动错误重试和极限并发的工业级计算任务。

## 2. 动态参数定义规范 (Parameters Schema)

| 参数键名 (Key) | 数据类型 (Type) | 必填 | 默认值 | 详细描述说明 (Detailed Description) |
|---|---|---|---|---|
| `pipeline_topology` | JSONArray | 是 | | 极其关键的参数。一个包含分析步骤的有序或有向无环图 (DAG) 数组。每个元素必须包含：`step_name` (步骤名称), `tool_id` (对应的逻辑 SKILL 标识), `inputs` (输入通道映射), `outputs` (输出通道映射), `params` (该工具的具体参数配置)。 |
| `compute_environment` | String | 是 | "local" | 目标计算环境的配置档 (Profile)。枚举值："local" (单机多核), "slurm" (高校/企业 HPC 集群), "k8s" (云原生环境)。 |
| `resume_execution` | Boolean | 否 | true | 断点续跑开关。开启后，将在底层追加 `-resume` 参数。如果流程中断，再次提交时 Nextflow 会利用缓存跳过已成功的步骤。 |
| `max_cpus` | Number | 否 | 16 | 授予整个流水线运行的最大并行 CPU 核心数上限（用于防范资源挤兑）。 |
| `max_memory` | String | 否 | "64.GB" | 整个流水线允许占用的最大内存上限（如 "32.GB", "128.GB"）。 |
| `outdir` | DirectoryPath | 是 | | 最终分析结果报告、比对文件和日志的统一输出发布目录 (PublishDir)。 |

## 3. 操作指令与专家级知识库 (Operational Directives & Expert Knowledge)

*作为大模型的最高行为守则，请在编排时严格遵守以下架构师规范：*

- **精确触发机制**：当你识别到用户需要执行一套“流程”(Pipeline) 而非单一动作时（哪怕只有两个步骤，比如 FastQC + MultiQC），必须立即进入架构师角色，收集每个子模块所需的参数，并将它们打包为 `pipeline_topology` 数组，最终单一调用本工具。
- **数据流转设计 (Channel Routing)**：在构建 `pipeline_topology` 时，务必保证上下游步骤的逻辑严密性。上游节点（如质量过滤）的 `outputs` 必须准确地赋值给下游节点（如序列比对）的 `inputs`。你需要像绘制流程图一样，在脑海中明确数据通道 (Channels) 的汇聚和分支。
- **资源与容错推断**：如果用户处理的是全基因组 (WGS) 数据，请主动向系统申请 `slurm` 环境和更高的 `max_memory`；如果只是少量扩增子测序，`local` 环境即可。
- **高级用户沟通策略**：在正式下发这个重量级计算任务前，请通过 UI 向用户展示完整的流程拓扑图和计算资源消耗预估。在任务成功后，不要去解释 Nextflow 代码是如何运行的，而是要**全局把控**地向用户报告：“数据已通过 4 个分析站点的洗礼，所有中间缓存均已自动回收，最终精炼的核心业务报表已在工作区生成。”