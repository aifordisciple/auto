# BesaltPipe 生信流程框架

> **文档版本**: 1.0.0
> **更新日期**: 2026-03-21
> **项目位置**: `biosource/besaltpipe/`

---

## 目录

1. [核心架构](#1-核心架构)
2. [支持的分析流程](#2-支持的分析流程)
3. [RNA-seq 流程示例](#3-rna-seq-流程示例)
4. [Single-cell 10x 单细胞分析流程](#4-single-cell-10x-单细胞分析流程)
5. [模块开发规范](#5-模块开发规范)
6. [配置文件格式](#6-配置文件格式)
7. [输出目录结构](#7-输出目录结构)

---

## 1. 核心架构

BesaltPipe 是一个配置驱动的模块化生物信息学分析流程框架。

```
besaltpipe/
├── Pipeline.py            # 主入口脚本
├── abtools.py             # 命令行工具接口
├── makeconfig.py          # 配置文件生成器
├── pipeline/
│   ├── base.py            # Module 基类（所有分析模块继承）
│   ├── pipeline_main.py   # Config/Genome 类 + 多进程调度
│   └── modules/           # 分析模块实现（40+ 模块）
├── configs/               # 预置流程配置模板
└── src/                   # 生信分析脚本库
```

### 关键设计

- **多进程并行**: 同一 order 的模块并行执行
- **数据流管理**: `source|module_id:output_key` 引用机制
- **基因组数据库**: `Genome` 类管理参考基因组配置
- **断点续跑**: `finished_modules.txt` 记录已完成模块
- **集中日志**: `QueueListener` 汇总多进程日志

---

## 2. 支持的分析流程

| 流程类型 | 配置目录 | 核心模块 |
|----------|----------|----------|
| RNA-seq | `configs/RNA-seq/` | fastqc, mapping_STAR, exp, rnaseq_deg, rnaseq_gokegg |
| Single-cell | `configs/Single-cell/` | 单细胞分析流程 |
| ChIP-seq | `configs/ChIP-seq/` | peak calling, motif analysis |
| ATAC-seq | `configs/ATAC-seq/` | 染色质可及性分析 |
| BS-Seq | `configs/BsSeq/` | 甲基化分析 (bismark) |
| CircRNA-seq | `configs/CircRNA-seq/` | 环状RNA鉴定 |
| Clip-seq | `configs/clip-seq/` | RBP 结合位点分析 |
| miRNA-seq | `configs/miRNA-seq/` | 小RNA分析 |
| ExomeSeq | `configs/ExomeSeq/` | 外显子测序变异检测 |
| Ribo-seq | `configs/Ribo-seq/` | 核糖体 profiling |
| Metagenomic | `configs/Metagenomic/` | 宏基因组分析 |

---

## 3. RNA-seq 流程示例

### 3.1 完整流程步骤

1. **质控**: FastQC → MultiQC
2. **比对**: STAR/HISAT2 → BAM
3. **定量**: featureCounts/StringTie → FPKM/TPM
4. **差异分析**: DESeq2/edgeR → DEG
5. **功能富集**: GO/KEGG 注释
6. **新转录本**: StringTie 组装 → lncRNA 预测
7. **可变剪接**: rMATS/SUVA 分析
8. **报告生成**: 自动生成结题报告

### 3.2 运行方式

```bash
# 方式1: Pipeline 主入口
p3 Pipeline.py -c config_file

# 方式2: abtools 命令行（自动生成配置）
p3 abtools.py <module_name> -samples Sample1,Sample2 -genomeid human_gencode_v38

# 方式3: 生成配置模板
p3 makeconfig.py -t RNA-seq
```

---

## 4. Single-cell 10x 单细胞分析流程

配置文件：`configs/Single-cell/singlecell_10x.config`

### 4.1 流程架构

```
Order 1: 数据拆库与定量
    ├── sc_bd_demultiplex_analysis (BD 平台)
    └── sc_cellranger (10x 平台) ──→ totalumi, listinfo

Order 2: 数据预处理
    └── sc_preprocessing ──→ sc_preprocessing.rds
        ├── 质控过滤 (MIN_TOTAL_UMI, MIN_GENES, MAX_MT_PERCENT)
        ├── 批次整合 (CCA/rPCA/SCT/Harmony)
        └── Doublet 检测

Order 3: 细胞聚类分析
    └── sc_cells_analysis ──→ cells_analysis.rds
        ├── PCA 降维
        ├── UMAP/t-SNE 可视化
        ├── 细胞聚类 (Louvain/Leiden)
        └── 细胞类型注释 (ScType)

Order 4: 多维度分析 (并行执行)
    ├── sc_genes_analysis    # 差异基因分析 + Marker 基因
    ├── sc_advanced_analysis # 高级分析 (拟时序等)
    └── sc_cellchat          # 细胞通讯分析

Order 6: 报告生成
    └── sc_report ──→ 结题报告
```

### 4.2 核心模块详解

#### 4.2.1 sc_cellranger (10x 数据处理)

```bash
cellranger count --id=run_count_{sample} \
    --fasts={fastq_dir} --sample={sample} \
    --transcriptome={ref10x} --localcores=16 --localmem=60
```

**输出**: `filtered_feature_bc_matrix/` (UMI 矩阵)

#### 4.2.2 sc_preprocessing (预处理)

**质控参数**:

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `MIN_TOTAL_UMI` | 最少 UMI 数 | 1000 |
| `MIN_GENES` | 最少基因数 | 500 |
| `MAX_MT_PERCENT` | 线粒体比例上限 | 15 |
| `MIN_CELLS` | 基因最少表达细胞数 | 5 |

**批次整合方法**:

| 方法 | 说明 |
|------|------|
| `cca` | Seurat CCA |
| `rpca` | Seurat rPCA |
| `sct_cca` | SCTransform + CCA |
| `sct_rpca` | SCTransform + rPCA |
| `sct_harmony` | SCTransform + Harmony |

#### 4.2.3 sc_cells_analysis (细胞分析)

核心分析脚本：
- `sc_cells_analysis.r` - 标准流程
- `sc_cells_analysis_harmony.r` - Harmony 整合
- `sc_cells_analysis_SCT.r` - SCTransform 流程

功能：
- PCA 降维 (dims=50)
- UMAP/t-SNE 2D 可视化
- 细胞聚类与注释
- ScType 自动注释 (`ScTypeDB_full.xlsx`)

#### 4.2.4 sc_genes_analysis (差异基因)

- FindAllMarkers (cluster 间差异)
- FindMarkers (指定组间差异)
- GO/KEGG 功能富集

#### 4.2.5 sc_advanced_analysis (高级分析)

- 拟时序分析 (Monocle3/Slingshot)
- 细胞亚群分析
- 轨迹推断

#### 4.2.6 sc_cellchat (细胞通讯)

```r
sc_cellchat_bycelltype_1_sample.r   # 单样本分析
sc_cellchat_bycelltype_2_compare.r  # 样本间比较
```

- 配体-受体互作分析
- 信号流网络可视化

### 4.3 umiconfig 输入文件格式

用于指定多样本单细胞数据的输入路径：

```
# 列格式：样本名<TAB>UMI矩阵路径<TAB>数据类型<TAB>数据集标签
D9_t1_LowerMedial   /path/to/t1_LowerMedial.Gene_Count.tsv   exp   D9
D9_t1_Normal        /path/to/t1_Normal.Gene_Count.tsv        exp   D9
D9_t2_Center        /path/to/t2_Center.Gene_Count.tsv        exp   D9
```

**列说明**:

| 列号 | 字段 | 说明 |
|------|------|------|
| 1 | 样本名 | 唯一标识符，用于后续分析 |
| 2 | UMI矩阵路径 | 表达矩阵文件路径 |
| 3 | 数据类型 | `10x`/`exp`/`BD` 等 |
| 4 | 数据集标签 | 批次整合时的分组标签 |

**支持的数据格式**:

| 格式 | 说明 |
|------|------|
| `10x` | Cell Ranger 输出目录 (filtered_feature_bc_matrix/) |
| `exp` | 表达矩阵 TSV/CSV (gene × cell) |
| `BD` | BD Rhapsody 输出 (*_RSEC_MolsPerCell.csv) |
| `h5` | 10x HDF5 格式 |
| `rds`/`rdsraw` | Seurat RDS 对象 |

### 4.4 典型命令示例

```bash
Rscript sc_preprocessing_v3.r \
  -s D9_t1_LowerMedial,D9_t1_Normal,D9_t2_Center \
  -l tumor,normal,tumor \
  -f exp,exp,exp \
  --dataset D9,D9,D9 \
  -b /path/to/matrix1.tsv,/path/to/matrix2.tsv,/path/to/matrix3.tsv \
  --MinTotalUMI 500 \
  --MinGenes 300 \
  --MaxMT 15 \
  --MinCellsInGene 2 \
  -m sct_harmony \
  --batchSize 10 \
  --doublet_enable true \
  --noparallel false
```

**参数说明**:

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-s` | 样本名列表 (逗号分隔) | 必填 |
| `-l` | 分组标签列表 | 必填 |
| `-f` | 数据格式列表 | 必填 |
| `--dataset` | 数据集标签 | D1 |
| `-b` | UMI矩阵路径列表 | 必填 |
| `--MinTotalUMI` | 最少UMI数阈值 | 1000 |
| `--MinGenes` | 最少基因数阈值 | 500 |
| `--MaxMT` | 线粒体比例上限(%) | 15 |
| `--MinCellsInGene` | 基因最少表达细胞数 | 5 |
| `-m` | 整合方法 | cca |
| `--batchSize` | 批次大小 | 100 |
| `--doublet_enable` | Doublet检测 | true |
| `--noparallel` | 禁用并行 | false |

### 4.5 后处理流程

**cells_analysis 后处理**:

```bash
# 1. Marker 基因统计
sh stat_markers.sh

# 2. GO/KEGG 富集
sh markers_gokegg.sh human_godes_final.txt hsa

# 3. 细胞比例比较分析
Rscript bar_basic_multi.r -f stat_cluster_fraction.xls
Rscript box_cellper_multi_dotplot.r -f stat_celltype_fraction.xls

# 4. Speckle 差异比例分析
Rscript sc_speckle.r -r cells_analysis.rds
```

**genes_analysis 后处理**:

```bash
# 按聚类差异分析
cd deg_by_cluster/tumor_vs_normal_*
sh stat_deg.sh
sh deg_gokegg.sh human_godes_final.txt hsa

# 按细胞类型差异分析
cd deg_by_celltype/tumor_vs_normal_*
sh stat_deg.sh
sh deg_gokegg.sh human_godes_final.txt hsa

# 全局差异分析
cd deg_by_all/
sh stat_deg_byall.sh
sh deg_gokegg_byall.sh human_godes_final.txt hsa
```

---

## 5. 模块开发规范

所有分析模块继承 `Module` 基类：

```python
class Module:
    def __init__(self, config, module_argv):
        self.inputs = {}      # 输入参数
        self.outputs = {}     # 输出结果
        self.cpu = 16         # CPU 核数

    def run(self):
        # 1. 解析输入参数
        # 2. 构建命令行
        # 3. 执行分析
        # 4. 更新输出
        pass
```

---

## 6. 配置文件格式

```ini
[gc]
GenomeID = human_gencode_v38
make-cmd-only = F

[sample]
indir = /path/to/reads
library-type = strand
sample1 = SampleName:end1.fq:end2.fq
list1 = Ctrl1,Ctrl2:Ctrl

[module:mapping_STAR]
order = 1
skip = F
threads = 16
o:uniqbam    # 输出声明

[module:exp]
order = 2
uniqbam = source|mapping:uniqbam  # 引用上游输出
o:exp
```

### Single-cell 配置示例

```ini
[module:sc_preprocessing]
order = 2
skip = F
datatype = 10x
totalumi = source|sc_cellranger:totalumi
MIN_TOTAL_UMI = 1000
MIN_GENES = 500
MAX_MT_PERCENT = 15
MIN_CELLS = 5
method = sct_harmony

[module:sc_cells_analysis]
order = 3
skip = F
tissue = Bladder
sctypedb = /path/to/ScTypeDB_full.xlsx
dims = 50

[module:sc_genes_analysis]
order = 4
skip = F
dims = 50

[module:sc_cellchat]
order = 4
skip = F
```

---

## 7. 输出目录结构

```
result/singlecell/
├── 1_preprocessing/
│   ├── sc_preprocessing.rds          # 整合后 Seurat 对象
│   ├── only_merge/                   # 仅合并无整合版本
│   ├── QC/                           # 质控图表
│   │   ├── {sample}_qc.pdf
│   │   └── {sample}_gene_summary.txt
│   └── discard_stat/                 # 过滤统计
├── 2_cells_analysis/
│   ├── cells_analysis.rds            # 聚类后 Seurat 对象
│   ├── sc_cluster/                   # 聚类结果
│   │   ├── umap_cluster.pdf
│   │   ├── stat_cluster_fraction_by_group.xls
│   │   └── stat_cluster_fraction_by_sample.xls
│   ├── sctype/                       # 细胞类型注释
│   │   └── sctype_scores.xls
│   ├── cellratio_compare/            # 细胞比例比较
│   └── cellratio_compare_bycelltype/
├── 3_genes_analysis/
│   ├── deg_by_cluster/               # 按聚类差异基因
│   ├── deg_by_celltype/              # 按细胞类型差异基因
│   └── deg_by_all/                   # 全局差异基因
├── 4_advanced_analysis/              # 高级分析结果
├── 5_cellchat/                       # 细胞通讯结果
└── report/                           # 结题报告
```

---

## 核心脚本位置

```
src/SingleCell/pipeline/
├── sc_preprocessing.r              # 预处理主脚本
├── sc_cells_analysis.r            # 细胞聚类分析
├── sc_cells_analysis_harmony.r    # Harmony 整合版本
├── sc_genes_analysis.r            # 差异基因分析
├── sc_cellchat_bycelltype_*.r     # 细胞通讯分析
├── sc_trajectory_analysis.r       # 拟时序分析
└── stat_cellranger.sh             # Cell Ranger 统计
```

---

*文档生成时间: 2026-03-21*
*维护者: Autonome Team*