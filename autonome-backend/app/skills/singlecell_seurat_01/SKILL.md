---
# ==========================================
# 核心系统元数据 (Core System Metadata)
# ------------------------------------------
# 以下区域为 YAML 格式，供后端系统路由和调度引擎直接读取
# ==========================================

skill_id: "singlecell_seurat_pipeline_01"
name: "单细胞RNA测序数据预处理与聚类分析"
version: "1.0.0"
author: "BioData Single-Cell Analysis Team"
executor_type: "Python_env"
entry_point: "scripts/sc_pipeline.py"
timeout_seconds: 86400
# 分类信息
category: "single_cell"
category_name: "单细胞分析"
subcategory: "scRNA_seq"
subcategory_name: "scRNA-seq分析"
tags: ["single-cell", "seurat", "clustering", "UMAP", "cell-annotation"]
---

## 1. 技能意图与功能边界 (Intent & Scope)

*面向 AI 的核心描述，帮助其判断在何种场景下应该召唤此工具。*

本技能是一个标准化的单细胞RNA测序数据分析流程，基于 Seurat v5 框架实现。它旨在处理来自 10x Genomics、BD Rhapsody 等平台的单细胞表达数据，完成从原始 UMI 矩阵到细胞聚类注释的完整分析流程。

**核心功能模块：**

1. **数据预处理 (Preprocessing)**
   - 多格式数据导入（10x、BD、表达矩阵TSV/CSV、Seurat RDS）
   - 细胞质控过滤（UMI数、基因数、线粒体比例、血红蛋白比例）
   - Doublet 双细胞检测与过滤
   - 多样本批次整合（CCA/rPCA/SCTransform/Harmony）

2. **降维聚类 (Clustering)**
   - PCA 主成分分析
   - UMAP/t-SNE 降维可视化
   - Louvain/Leiden 图聚类
   - 细胞类型自动注释（ScType）

3. **差异分析 (Differential Expression)**
   - Cluster 间 Marker 基因鉴定
   - 组间差异基因分析
   - GO/KEGG 功能富集

**适用场景：**
- 用户说"分析这批单细胞数据"
- 用户说"做细胞聚类"
- 用户说"鉴定细胞类型"
- 用户说"找差异基因"

**不适用场景：**
- 空间转录组分析（请使用 spatial_transcriptomics SKILL）
- 单细胞 ATAC-seq（请使用 scATAC SKILL）
- VDJ 免疫组库分析（请使用 vdj_analysis SKILL）

## 2. 动态参数定义规范 (Parameters Schema)

*系统底层的解析器将扫描此表格并转换为严格的 JSON Schema，并在前端渲染动态配置卡片。*

| 参数键名 (Key) | 数据类型 (Type) | 必填 (Required) | 默认值 (Default) | 详细描述说明 (Detailed Description) |
|---|---|---|---|---|
| `input_format` | String | 是 (Yes) | | 输入数据格式。可选值：`10x` (Cell Ranger输出目录)、`exp` (表达矩阵TSV/CSV)、`BD` (BD Rhapsody)、`h5` (10x HDF5)、`rds` (Seurat RDS对象) |
| `input_paths` | String | 是 (Yes) | | 输入数据路径列表，多个路径用逗号分隔。对于10x格式，指向 filtered_feature_bc_matrix 目录；对于exp格式，指向表达矩阵文件。 |
| `sample_names` | String | 是 (Yes) | | 样本名称列表，与输入路径一一对应，用逗号分隔。如：`Sample1,Sample2,Sample3` |
| `group_labels` | String | 是 (Yes) | | 分组标签列表，与样本一一对应，用逗号分隔。如：`Control,Control,Treat,Treat` |
| `min_umi` | Number | 否 (No) | 1000 | 最小 UMI 总数阈值，低于此值的细胞将被过滤。推荐范围：500-2000。 |
| `min_genes` | Number | 否 (No) | 500 | 最小基因数阈值，低于此值的细胞将被过滤。推荐范围：200-1000。 |
| `max_mt_percent` | Number | 否 (No) | 15 | 线粒体基因比例上限(%)，高于此值的细胞将被过滤。推荐范围：10-20。 |
| `min_cells` | Number | 否 (No) | 5 | 基因最小表达细胞数，低于此值的基因将被过滤。 |
| `integration_method` | String | 否 (No) | sct_harmony | 批次整合方法。可选值：`cca`、`rpca`、`sct_cca`、`sct_rpca`、`sct_harmony`、`merge` (仅合并不整合)。多样本强烈推荐使用 `sct_harmony`。 |
| `doublet_detection` | Boolean | 否 (No) | true | 是否启用 DoubletFinder 双细胞检测。 |
| `dims` | Number | 否 (No) | 50 | PCA 降维保留的主成分数量。推荐范围：30-50。 |
| `resolution` | Number | 否 (No) | 0.8 | 聚类分辨率参数，值越大聚类数越多。推荐范围：0.4-1.2。 |
| `tissue_type` | String | 否 (No) | | 组织类型，用于 ScType 细胞类型自动注释。如：`Kidney`、`Liver`、`Blood` 等。不填写则跳过自动注释。 |
| `output_dir` | DirectoryPath | 是 (Yes) | | 分析结果输出目录。将生成 Seurat RDS 对象、质控图表、聚类可视化、Marker 基因列表等。 |

## 3. 操作指令与专家级知识库 (Operational Directives & Expert Knowledge)

*这里包含了系统赋予大模型的"锦囊妙计"，塑造其资深单细胞分析师的专业表现。*

### 精确触发条件

当用户提出以下需求时，应优先调用本技能：
- "分析这批单细胞数据"
- "做一下细胞聚类"
- "鉴定细胞类型"
- "看看细胞群体分布"
- "找出差异基因"

### 智能参数推断逻辑

1. **输入格式判断**：
   - 如果路径指向目录且包含 `barcodes.tsv.gz`、`features.tsv.gz`、`matrix.mtx.gz`，判定为 `10x` 格式
   - 如果文件后缀为 `.h5`，判定为 `h5` 格式
   - 如果文件后缀为 `.tsv` 或 `.csv`，判定为 `exp` 格式
   - 如果文件后缀为 `.rds`，判定为 `rds` 格式
   - 如果文件名包含 `_RSEC_MolsPerCell`，判定为 `BD` 格式

2. **分组标签推断**：
   - 如果样本名包含 `Normal`、`Control`、`Ctrl` 等关键词，可推断为对照组
   - 如果样本名包含 `Treat`、`Drug`、`Tumor` 等关键词，可推断为处理组
   - 主动询问用户确认分组信息

3. **质控阈值建议**：
   - 10x 3' v3 数据：`min_umi=500`，`min_genes=300`
   - 10x 5' 或 VDJ 数据：`min_umi=1000`，`min_genes=500`
   - BD Rhapsody 数据：`min_umi=500`，`min_genes=300`
   - 如果用户提到"数据质量较差"，建议降低阈值

4. **批次整合方法选择**：
   - 单样本：使用 `merge` 即可
   - 2-5 个样本：使用 `sct_cca` 或 `sct_rpca`
   - 6+ 个样本或明显批次效应：强烈推荐 `sct_harmony`

### 执行结果解读指南

当分析完成后，请主动引导用户关注以下核心指标：

1. **质控统计**：
   - 各样本过滤前后细胞数
   - 线粒体比例分布
   - UMI 和基因数分布

2. **聚类质量**：
   - UMAP 图中聚类是否清晰分离
   - 各聚类细胞数量是否合理（避免过小聚类）
   - Marker 基因表达是否具有细胞类型特异性

3. **细胞类型注释**：
   - ScType 注释结果仅供参考，需结合生物学背景验证
   - 推荐用户提供已知 Marker 基因进行人工验证

### 常见问题处理

1. **内存不足**：如果数据量超过 10 万细胞，建议分批处理或使用 `sc_preprocessing_largedata.r` 脚本

2. **聚类不理想**：
   - 调整 `resolution` 参数（增大可得到更多聚类）
   - 调整 `dims` 参数（增加可保留更多变异信息）
   - 检查是否存在批次效应未消除

3. **细胞类型注释失败**：
   - 确认 `tissue_type` 参数是否正确
   - 尝试手动查找 Marker 基因进行注释

### 输出文件说明

```
{output_dir}/
├── sc_preprocessing.rds          # 整合后的 Seurat 对象（可用 R 读取继续分析）
├── cells_analysis.rds            # 聚类后的 Seurat 对象
├── QC/                           # 质控图表
│   ├── {sample}_qc.pdf          # 单样本质控图
│   └── {sample}_gene_summary.txt # 基因统计
├── sc_cluster/                   # 聚类结果
│   ├── umap_cluster.pdf         # UMAP 聚类图
│   └── stat_cluster_fraction.xls # 聚类比例统计
├── sctype/                       # 细胞类型注释
│   └── sctype_scores.xls        # ScType 注释结果
└── markers/                      # Marker 基因
    └── cluster_markers.xls       # 各聚类的 Marker 基因列表
```