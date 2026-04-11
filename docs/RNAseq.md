# RNA-seq 基础分析流程 (rnaseq_basic_01)

## 基本信息

| 属性 | 值 |
|------|-----|
| **skill_id** | `rnaseq_basic_pipeline_01` |
| **名称** | RNA-seq 基础分析流程 |
| **版本** | v2.2.0 |
| **执行器** | Logical_Blueprint (Nextflow DSL2) |
| **入口脚本** | `scripts/pipeline.py` |
| **超时** | 86400秒 (24小时) |
| **分类** | 转录组分析 > RNA-seq基础分析 |
| **标签** | rna-seq, differential-expression, star, deseq2, go-kegg, transcriptomics, lncrna, gsea, alternative-splicing, saturation |

---

## 工作流架构

```
Step 1: 质控 (FASTP + FASTQC + MULTIQC)
    └── 输入: Raw FastQ → 输出: Clean FastQ + QC Reports

Step 2: 比对 (STAR_ALIGN + STAR_POST_PROCESS)
    └── 输入: Clean FastQ → 输出: Sorted BAM + Mapping Stats

Step 3: lncRNA 鉴定 v3.0 (必选)
    ├── STRINGTIE_ASSEMBLY: 转录本组装
    ├── MERGE_TRANSCRIPTS: 合并转录本
    ├── LNCRNA_FILTER_V3: 5工具编码潜力预测 + Pfam金标准
    ├── LNCRNA_QUANT_V3: Salmon 定量（含 mRNA + lncRNA）
    ├── LNCRNA_STAT_V3: 矩阵拆分统计
    ├── LNCRNA_DEG_V3: DESeq2 差异分析（含 mRNA + lncRNA）
    ├── LNCRNA_TARGET_V3: cis/trans 靶基因预测
    └── LNCRNA_CERNA_V3: ceRNA 网络预测

Step 4: 富集分析 (GO_KEGG)
    └── 输入: DEG Results → 输出: GO/KEGG Enrichment

Step 5: GSEA 分析 (可选)
    └── 输入: DEG Results → 输出: GSEA Enrichment Results

Step 6: 饱和度分析 (可选)
    └── 输入: Count Matrix → 输出: Saturation Curves

Step 7: 可变剪接分析 (可选)
    └── 输入: BAM Files → 输出: Splicing Events
```

---

## 各步骤详细说明

### Step 1: 质控 (QC)

| 进程 | 功能 | 输入 | 输出 |
|------|------|------|------|
| **FASTP** | 接头去除、质量控制、序列校正 | Raw FastQ | Clean FastQ + HTML/JSON Report |
| **FASTQC** | 质量评估 | Clean FastQ | FastQC HTML Report |
| **MULTIQC** | 汇总报告 | FastP/FastQC Reports | MultiQC HTML Report |

**关键参数**:
- `fastp_trim_poly_g`: 去除 polyG 尾
- `fastp_length_required`: 最小保留长度 (默认 50)
- `fastp_cut_mean_quality`: 滑动窗口质量阈值 (默认 20)

### Step 2: 比对 (STAR_ALIGN + STAR_POST_PROCESS)

| 进程 | 功能 | 输入 | 输出 |
|------|------|------|------|
| **STAR_ALIGN** | 快速比对到参考基因组 | Clean FastQ + STAR Index | Sorted BAM + Log.final.out + SJ.out.tab |
| **STAR_POST_PROCESS** | 提取唯一比对、统计剪接读数 | Sorted BAM + Log | Unique BAM + map_result.txt + junctions.bed |
| **MAPPING_SUMMARY** | 汇总比对统计 | All map_result.txt | Mapping Summary TSV |

**关键参数** (完整复刻 mapping.py):
- `outFilterMultimapNmax`: 10 (最大多重比对数)
- `alignIntronMax`: 500000 (最大内含子长度)
- `outSAMstrandField`: intronMotif (链特异性标记)
- `twopassMode`: Basic (两轮比对)

### Step 3: lncRNA 鉴定 v3.0 (必选)

这是 v2.2 版本的核心升级，lncRNA 鉴定为必选模块，统一定量和差异分析：

| 进程 | 功能 | 输入 | 输出 |
|------|------|------|------|
| **LNCRNA_FILTER_V3** | 5工具编码潜力预测 (CPC2/CNCI/CPAT/LGC/Pfam) | merged.gtf + reference.gtf + genome.fa | novel_lncRNA.gtf + .fa + .db + Venn Plot |
| **LNCRNA_QUANT_V3** | Salmon 定量 (含 mRNA + lncRNA) | transcript.fa + novel_lncRNA.fa | TPM/Count Matrix + PCA Plot |
| **LNCRNA_STAT_V3** | 矩阵拆分统计 | TPM/Count Matrix | All_lncRNA_Annotation + lncRNA_TPM + mRNA_TPM |
| **LNCRNA_DEG_V3** | DESeq2 差异分析 (含 mRNA + lncRNA) | Count Matrix + Metadata | DEG Results + Volcano Plot |
| **LNCRNA_TARGET_V3** | cis/trans 靶基因预测 | TPM Matrix + DEG + GTF | Cis/Trans Targets + Network |
| **LNCRNA_CERNA_V3** | ceRNA 网络预测 | TPM Matrix + miRNA DB | ceRNA Triplets + Network |

**筛选策略**:
- 五工具交叉验证: CPC2, CNCI, CPAT, LGC, Pfam (金标准)
- class_code 保留: u (intergenic), x (antisense), i (intronic)
- 长度过滤: 单外显子 >= 10000bp, 多外显子 >= 200bp

**注意**: 原有的 Step 4 定量和 Step 5 差异分析已合并到此模块中。

### Step 4: 富集分析 (GO_KEGG)

| 进程 | 功能 | 输入 | 输出 |
|------|------|------|------|
| **GO_KEGG** | 功能富集 | DEG Results | go_enrichment.tsv + kegg_enrichment.tsv |

**关键参数**:
- `organism`: hsa (人) / mmu (小鼠) / rno (大鼠)
- `go_ontology`: ALL / BP / MF / CC
- `enrich_pvalue_cutoff`: 0.05
- `show_category`: 20

---

## 关键脚本功能

### Shell 脚本 (`scripts/`)

| 脚本 | 功能 |
|------|------|
| `run_step1_qc.sh` | FastP 接头去除 + FastQC + MultiQC + QC 统计可视化 |
| `run_step2_alignment.sh` | STAR/HISAT2 比对 + BAM 索引 + 比对统计可视化 |
| `run_step3_lncrna.sh` | StringTie 组装 + 多工具编码潜力预测 + Overlap 筛选 |
| `run_step4_quantification.sh` | featureCounts 定量 + TPM/FPKM 标准化 |
| `run_step5_deg.sh` | DESeq2/edgeR 差异分析 + 可视化 |
| `run_step6_enrichment.sh` | GO/KEGG 富集分析 |
| `run_step10_gsea.sh` | GSEA 基因集富集分析 |
| `run_step8_saturation.sh` | 测序饱和度分析 |
| `run_step9_as_rmats.sh` | rMATS 可变剪接分析 |

### Python 工具 (`scripts/pytools/`)

| 脚本 | 功能 | 版本 |
|------|------|------|
| `lncRNA_filter_pipeline.py` | 5工具编码潜力预测与严格筛选 | v6.1 |
| `lncRNA_quant_pipeline.py` | Salmon 无偏定量与高阶 QC | v5.1 |
| `lncRNA_stat_pipeline.py` | 矩阵拆分与统计切片 | v6.0 |
| `lncRNA_deg_pipeline.py` | DESeq2 差异表达分析 | v6.0 |
| `lncRNA_target_pipeline.py` | cis/trans 靶基因预测 | v6.0 |
| `lncRNA_cerna_pipeline.py` | ceRNA 网络预测 | v6.0 |
| `parse_star_log.py` | 解析 STAR Log.final.out | - |
| `summarize_mapping.py` | 汇总比对统计 | - |
| `get_insert_size.py` | 插入片段大小分析 | - |

### R 脚本 (`scripts/rscripts/`)

| 脚本 | 功能 |
|------|------|
| `rnaseq_qc_statistics.r` | QC 统计可视化 |
| `rnaseq_alignment_stats.r` | 比对统计可视化 |
| `rnaseq_lncrna_identify.r` | lncRNA 鉴定 |
| `rnaseq_lncrna_filter.r` | lncRNA 多工具筛选 |
| `rnaseq_lncrna_visualize.r` | lncRNA 可视化 |
| `rnaseq_quantification.r` | 定量标准化 |
| `rnaseq_deg_analysis.r` | 差异分析 |
| `rnaseq_deg_visualize.r` | 差异分析可视化 |
| `rnaseq_enrichment.r` | 富集分析 |
| `rnaseq_enrichment_visualize.r` | 富集分析可视化 |
| `rnaseq_gsea.r` | GSEA 分析 |
| `rnaseq_saturation.r` | 饱和度分析 |
| `rnaseq_as_rmats.r` | 可变剪接分析 |

---

## 参数配置结构

### 核心输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sample_sheet` | FilePath | 是 | 样本信息表 (TSV格式) |
| `output_dir` | DirectoryPath | 是 | 输出目录 |
| `genome_id` | String | 是 | 基因组标识符 (如 human_gencode_v38) |

### 并行控制参数 (v2.1 新增)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `parallel_samples` | 4 | 同时处理的样本数量上限 |
| `executor` | local | 执行器类型 |
| `cache_mode` | deep | 缓存模式 (断点续跑) |
| `cleanup_workdir` | false | 完成后是否清理工作目录 |

### Sample Sheet 格式

```tsv
sample_name	read1_path	read2_path	group_label
Ctrl_1	/data/Ctrl_1_R1.fq.gz	/data/Ctrl_1_R2.fq.gz	Control
Ctrl_2	/data/Ctrl_2_R1.fq.gz	/data/Ctrl_2_R2.fq.gz	Control
Treat_1	/data/Treat_1_R1.fq.gz	/data/Treat_1_R2.fq.gz	Treatment
Treat_2	/data/Treat_2_R1.fq.gz	/data/Treat_2_R2.fq.gz	Treatment
```

---

## 输出文件结构

```
{output_dir}/
├── 1_qc/                           # 质控结果
│   ├── fastp/                      # FastP 结果
│   ├── fastqc/                     # FastQC 结果
│   └── multiqc/                    # MultiQC 汇总
├── 2_alignment/                    # 比对结果
│   ├── bam/                        # BAM 文件
│   ├── logs/                       # STAR 日志
│   └── stats/                      # 比对统计
├── 3_lncrna/                       # lncRNA 鉴定结果
│   ├── assembly/                   # StringTie 组装
│   ├── merged/                     # 合并转录本
│   ├── coding_potential/           # 编码潜力预测
│   ├── filtered/                   # 筛选结果
│   └── plots/                      # 可视化图表
├── 4_quantification/               # 定量结果
│   ├── counts/                     # 原始计数
│   └── normalized/                 # 标准化结果
├── 5_deg/                          # 差异分析
│   ├── results/                    # DEG 结果
│   └── plots/                      # 可视化图表
├── 6_enrichment/                   # 富集分析
├── 7_report/                       # 综合报告
├── 8_saturation/                   # 饱和度分析
├── 9_as_rmats/                     # 可变剪接分析
├── 10_gsea/                        # GSEA 分析
└── analysis_summary.json           # 分析摘要
```

---

## 基因组配置映射

支持以下基因组:

| genome_id | 物种 | 描述 |
|-----------|------|------|
| `human_gencode_v38` | hsa | 人类 GENCODE v38 (GRCh38) |
| `human_ensembl_108` | hsa | 人类 Ensembl release 108 |
| `mouse_gencode_vM30` | mmu | 小鼠 GENCODE vM30 (GRCm39) |
| `mouse_ensembl_108` | mmu | 小鼠 Ensembl release 108 |
| `rat_ensembl_108` | rno | 大鼠 Ensembl release 108 |

---

## 依赖工具与数据库

### 核心工具

| 工具 | 用途 |
|------|------|
| FastP | 质量控制 |
| FastQC | 质量评估 |
| MultiQC | 报告汇总 |
| STAR | 序列比对 |
| HISAT2 | 序列比对 (可选) |
| StringTie | 转录本组装 |
| featureCounts | 基因定量 |
| Salmon | 转录本定量 |
| CPC2, CNCI, CPAT, LGC | 编码潜力预测 |
| TransDecoder + hmmscan | Pfam 蛋白域预测 |
| rMATS | 可变剪接分析 |

### 数据库

| 数据库 | 路径 |
|--------|------|
| Pfam-A.hmm | `/opt/biodb/pfam/Pfam-A.hmm` |
| CPAT Human Model | `/opt/biodb/cpat/Human_logitModel.RData` |
| tx2gene | `/opt/biodb/annotation/tx2gene.tsv` |
| lncRNA-miRNA DB | `/opt/biodb/miRNA/lncRNA_miRNA.tsv` |
| mRNA-miRNA DB | `/opt/biodb/miRNA/mRNA_miRNA.tsv` |

---

## 断点续跑支持

流程支持从中断位置继续执行:

```bash
# 首次运行
nextflow run process.nf --sample_sheet samples.tsv --output_dir ./results

# 从中断位置继续
nextflow run process.nf --sample_sheet samples.tsv --output_dir ./results -resume
```

使用 `-resume` 参数时，Nextflow 会检查工作目录中的缓存，已成功完成的任务会被跳过。

---

## v2.2 新特性

1. **lncRNA 鉴定必选**: lncRNA 鉴定 v3.0 升级为必选模块，不再需要 enable_lncrna 参数
2. **统一定量**: LNCRNA_QUANT_V3 替代原有的 FEATURECOUNTS，使用 Salmon 进行 mRNA + lncRNA 统一定量
3. **统一差异分析**: LNCRNA_DEG_V3 替代原有的 DESEQ2_ANALYSIS，统一进行 mRNA + lncRNA 差异分析
4. **流程简化**: 减少冗余步骤，流程架构更清晰
5. **断点续跑**: `-resume` 支持，缓存已完成任务
6. **并行控制**: `parallel_samples` 参数限制同时处理样本数
7. **微服务架构**: 各步骤独立 Python 模块，便于维护和扩展