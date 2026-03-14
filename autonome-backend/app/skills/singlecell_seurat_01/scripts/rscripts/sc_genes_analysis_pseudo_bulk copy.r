#!/usr/bin/env Rscript

###############################################################################
# 从单细胞 Seurat RDS 生成按样本的 pseudo-bulk 计数矩阵，并用 DESeq2 进行组间差异分析。
#
# 功能要点
# - 输入：Seurat RDS 文件（对象名不限），meta.data 中至少包含：
#   * 分组列（如 group / condition），用于 DESeq2 中的 group 因子
#   * 样本列（如 patient_id / sample），用于 DESeq2 中的 subject 因子（配对设计时）
# - 可选：按指定的细胞类型列 + 细胞类型名称先筛选出某一细胞类型，仅对此 cell type 做 pseudo-bulk
# - pseudo-bulk 生成：
#   * 对每个唯一的 (subject, group) 组合，聚合该组合下所有细胞的 raw counts 之和，得到一个 bulk 样本
#   * 可设置每个 bulk 样本的最小细胞数，低于阈值的 bulk 样本会被丢弃
# - DE 设计：
#   * 非配对：  design = ~ group
#   * 配对：    design = ~ subject + group  （subject 为样本/个体 ID）
# - 对每个指定对比（如 Pembro:Baseline），输出：
#   * 差异分析总表（所有基因）
#   * 显著上调 / 下调基因表（按 log2FC 与 padj 阈值过滤）
#   * 火山图（同时输出 PDF 和 PNG）
# - 额外输出：
#   * pseudo-bulk 计数总表：pseudobulk_counts.tsv（gene × pseudo-bulk 样本）
#   * pseudo-bulk 样本与分组对应表：pseudobulk_sample_group.tsv（sample\tsubject\tgroup）
#
# 显著性筛选逻辑：
# - 如果设置了 --pval_thresh，则使用 pvalue <= pval_thresh + |log2FC| >= lfc_thresh
# - 否则使用 padj <= padj_thresh + |log2FC| >= lfc_thresh
#
# 用法示例：
# Rscript /Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/sc_genes_analysis_pseudo_bulk.r \
#   --rds /opt/data1/project/NBioS-2025-07031-D_Breast_cancer_drug_resistance/basic/result/singlecell/2_cells_analysis/subcell/malignant/3_genes_analysis/Baseline/Baseline.rds \
#   --assay RNA \
#   --group_col response \
#   --sample_col replicate \
#   --celltype_col customclassif \
#   --celltype CD8_T \
#   --contrasts Pembro:Baseline,Pembro_RT:Pembro,Pembro_RT:Baseline \
#   --paired \
#   --outdir deg_pseudobulk_CD8 \
#   --min_cells 20 \
#   --min_samples_group 2 \
#   --lfc_thresh 0.25 \
#   --padj_thresh 0.05
#
#
# Rscript /Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/sc_genes_analysis_pseudo_bulk.r \
#   --rds /opt/data1/project/NBioS-2025-07031-D_Breast_cancer_drug_resistance/basic/result/singlecell/2_cells_analysis/subcell/malignant/3_genes_analysis/Baseline/Baseline.rds \
#   --assay RNA \
#   --group_col response \
#   --sample_col replicate \
#   --contrasts R1:NR,R2:NR,R1:R2 \
#   --outdir deg_pseudobulk \
#   --min_cells 20 \
#   --min_samples_group 2 \
#   --lfc_thresh 1 \
#   --pval_thresh 0.05
###############################################################################

suppressPackageStartupMessages({
  library(optparse)
  library(Seurat)
  library(DESeq2)
  library(Matrix)
  library(dplyr)
  library(tidyr)
  library(readr)
  library(ggplot2)
  library(stringr)
})

VERSION <- "1.1.0"

option_list <- list(
  make_option(
    c("--rds"), type = "character", metavar = "FILE",
    help = "输入 Seurat 对象 RDS 文件路径（必需）"
  ),
  make_option(
    c("--assay"), type = "character", default = "RNA",
    help = "用于 pseudo-bulk 的 Assay 名称，默认 'RNA'"
  ),
  make_option(
    c("--group_col"), type = "character", metavar = "COL",
    help = "meta.data 中表示分组的列名（必需），如 group / condition"
  ),
  make_option(
    c("--sample_col"), type = "character", metavar = "COL",
    help = "meta.data 中表示样本/个体 ID 的列名（必需），如 patient_id / sample"
  ),
  make_option(
    c("--celltype_col"), type = "character", default = NA,
    help = "meta.data 中表示细胞类型的列名（可选）。若指定且同时给出 --celltype，则先按此列筛选细胞"
  ),
  make_option(
    c("--celltype"), type = "character", default = NA,
    help = "需要保留的细胞类型名称（可选）。需与 --celltype_col 搭配使用"
  ),
  make_option(
    c("--contrasts"), type = "character", metavar = "STR",
    help = "组间对比列表，格式如 'Pembro:Baseline,Pembro_RT:Pembro'（必需）"
  ),
  make_option(
    c("--paired"), action = "store_true", default = FALSE,
    help = "是否使用配对设计（design = ~ subject + group）。默认 FALSE（~ group）"
  ),
  make_option(
    c("--min_cells"), type = "integer", default = 10,
    help = "每个 pseudo-bulk 样本至少包含的细胞数，默认 10"
  ),
  make_option(
    c("--min_samples_group"), type = "integer", default = 2,
    help = "每个组至少包含的 pseudo-bulk 样本数阈值，低于此阈值跳过该对比，默认 2"
  ),
  make_option(
    c("--lfc_thresh"), type = "double", default = 0.25,
    help = "显著基因筛选时的 |log2FoldChange| 阈值，默认 0.25"
  ),
  make_option(
    c("--padj_thresh"), type = "double", default = 0.05,
    help = "显著基因筛选时的 adjusted p-value 阈值，默认 0.05"
  ),
  make_option(
    c("--pval_thresh"), type = "double", default = NA,
    help = "显著基因筛选时的 p-value 阈值（可选）。若设置，则按 pvalue <= pval_thresh 进行筛选"
  ),
  make_option(
    c("--outdir"), type = "character", default = "deg_pseudobulk",
    help = "输出目录，默认 'deg_pseudobulk'"
  ),
  make_option(
    c("--version"), action = "store_true", default = FALSE,
    help = "显示版本号后退出"
  )
)

opt_parser <- OptionParser(option_list = option_list)
opt <- parse_args(opt_parser)

if (isTRUE(opt$version)) {
  message("sc_pseudobulk_deseq2.r  Version: ", VERSION)
  quit(status = 0)
}

# 基本参数检查 -------------------------------------------------------------

if (is.null(opt$rds)) {
  stop("必须通过 --rds 指定输入 Seurat RDS 文件。")
}
if (is.null(opt$group_col)) {
  stop("必须通过 --group_col 指定分组列名（meta.data 中）。")
}
if (is.null(opt$sample_col)) {
  stop("必须通过 --sample_col 指定样本/个体列名（meta.data 中）。")
}
if (is.null(opt$contrasts)) {
  stop("必须通过 --contrasts 指定至少一个组间对比，如 'Pembro:Baseline,Pembro_RT:Pembro'。")
}

if (!dir.exists(opt$outdir)) {
  dir.create(opt$outdir, recursive = TRUE, showWarnings = FALSE)
}

message("[INFO] 参数：")
print(opt)

use_pval_filter <- !is.na(opt$pval_thresh)
if (use_pval_filter) {
  message(sprintf(
    "[INFO] 显著基因筛选将使用 pvalue <= %.3g + |log2FC| >= %.3g。",
    opt$pval_thresh, opt$lfc_thresh
  ))
} else {
  message(sprintf(
    "[INFO] 显著基因筛选将使用 padj <= %.3g + |log2FC| >= %.3g。",
    opt$padj_thresh, opt$lfc_thresh
  ))
}

# 辅助函数 -------------------------------------------------------------------

parse_contrasts <- function(contrast_str) {
  x <- str_split(contrast_str, pattern = ",", simplify = FALSE)[[1]]
  x <- trimws(x)
  x <- x[nzchar(x)]
  if (length(x) == 0) {
    stop("contrasts 解析为空，请检查格式。")
  }
  out <- lapply(x, function(s) {
    parts <- str_split(s, pattern = ":", n = 2, simplify = TRUE)
    if (ncol(parts) != 2 || any(parts == "")) {
      stop(sprintf("对比 '%s' 格式错误，应为 'test:ctrl'。", s))
    }
    list(
      name = sprintf("%s_vs_%s", parts[1], parts[2]),
      test = parts[1],
      ctrl = parts[2]
    )
  })
  return(out)
}

reorder_gene_first <- function(df) {
  if (!"gene" %in% colnames(df)) return(df)
  cols <- colnames(df)
  df[, c("gene", setdiff(cols, "gene")), drop = FALSE]
}

plot_volcano <- function(
  res_df,
  lfc_thresh,
  padj_thresh,
  pval_thresh = NA,
  use_pval = FALSE,
  title = NULL,
  outfile_prefix
) {
  df <- res_df %>%
    dplyr::filter(!is.na(log2FoldChange))

  if (use_pval) {
    df <- df %>%
      dplyr::filter(!is.na(pvalue)) %>%
      dplyr::mutate(
        sig = dplyr::case_when(
          pvalue <= pval_thresh & log2FoldChange >= lfc_thresh  ~ "up",
          pvalue <= pval_thresh & log2FoldChange <= -lfc_thresh ~ "down",
          TRUE                                                 ~ "ns"
        ),
        neg_log10 = -log10(pvalue)
      )
    hline_y <- -log10(pval_thresh)
    y_lab   <- "-log10 p-value"
  } else {
    df <- df %>%
      dplyr::filter(!is.na(padj)) %>%
      dplyr::mutate(
        sig = dplyr::case_when(
          padj <= padj_thresh & log2FoldChange >= lfc_thresh  ~ "up",
          padj <= padj_thresh & log2FoldChange <= -lfc_thresh ~ "down",
          TRUE                                               ~ "ns"
        ),
        neg_log10 = -log10(padj)
      )
    hline_y <- -log10(padj_thresh)
    y_lab   <- "-log10 adjusted p-value"
  }

  p <- ggplot(df, aes(x = log2FoldChange, y = neg_log10, colour = sig)) +
    geom_point(alpha = 0.6, size = 1) +
    scale_color_manual(
      values = c(ns = "grey70", up = "red", down = "blue"),
      breaks = c("up", "down", "ns")
    ) +
    geom_vline(xintercept = c(-lfc_thresh, lfc_thresh), linetype = "dashed") +
    geom_hline(yintercept = hline_y, linetype = "dashed") +
    labs(
      x = "log2 fold change",
      y = y_lab,
      colour = "Significance",
      title = title
    ) +
    theme_bw() +
    theme(
      plot.title = element_text(hjust = 0.5),
      legend.position = "right"
    )

  pdf_file <- paste0(outfile_prefix, ".pdf")
  png_file <- paste0(outfile_prefix, ".png")

  ggsave(pdf_file, plot = p, width = 6, height = 5)
  ggsave(png_file, plot = p, width = 6, height = 5, dpi = 300)

  message("[INFO] 火山图已输出：", pdf_file, " 和 ", png_file)
}

# 读取 Seurat 对象 ----------------------------------------------------------

message("[INFO] 读取 Seurat RDS: ", opt$rds)
obj <- readRDS(opt$rds)

if (!opt$assay %in% names(obj@assays)) {
  stop(sprintf("Assay '%s' 在 Seurat 对象中不存在。", opt$assay))
}
DefaultAssay(obj) <- opt$assay

meta <- obj@meta.data
if (!opt$group_col %in% colnames(meta)) {
  stop(sprintf("group_col '%s' 不在 meta.data 列中。", opt$group_col))
}
if (!opt$sample_col %in% colnames(meta)) {
  stop(sprintf("sample_col '%s' 不在 meta.data 列中。", opt$sample_col))
}

# 可选按 celltype 筛选 ------------------------------------------------------

if (!is.na(opt$celltype_col) && !is.na(opt$celltype)) {
  if (!opt$celltype_col %in% colnames(meta)) {
    stop(sprintf("celltype_col '%s' 不在 meta.data 列中。", opt$celltype_col))
  }
  cells_keep <- rownames(meta)[meta[[opt$celltype_col]] == opt$celltype]
  if (length(cells_keep) == 0) {
    stop(sprintf(
      "在列 '%s' 中未找到 celltype = '%s' 的细胞。",
      opt$celltype_col, opt$celltype
    ))
  }
  message(sprintf("[INFO] 仅保留细胞类型 '%s'（列 %s），细胞数 = %d。",
                  opt$celltype, opt$celltype_col, length(cells_keep)))
  obj <- subset(obj, cells = cells_keep)
  meta <- obj@meta.data
} else {
  message("[INFO] 未指定 celltype_col / celltype，使用所有细胞。")
}

# 构建 pseudo-bulk ----------------------------------------------------------

meta$group   <- as.factor(meta[[opt$group_col]])
meta$subject <- as.factor(meta[[opt$sample_col]])

if (any(is.na(meta$group) | is.na(meta$subject))) {
  n_before <- nrow(meta)
  keep_idx <- which(!is.na(meta$group) & !is.na(meta$subject))
  meta <- meta[keep_idx, , drop = FALSE]
  obj  <- subset(obj, cells = rownames(meta))
  message(sprintf(
    "[WARN] 有 NA group / subject 的细胞被移除：%d -> %d 细胞。",
    n_before, nrow(meta)
  ))
}

if (nrow(meta) == 0) {
  stop("所有细胞在 group 或 subject 上均为 NA，无法继续。")
}

# bulk_id = subject__group（一个 bulk 样本对应一个 subject 在某个 group 的聚合）
meta$bulk_id <- paste(meta$subject, meta$group, sep = "__")

# 每个 bulk 样本的细胞数过滤
cell_counts_per_bulk <- table(meta$bulk_id)
valid_bulk_ids <- names(cell_counts_per_bulk)[cell_counts_per_bulk >= opt$min_cells]
if (length(valid_bulk_ids) == 0) {
  stop(sprintf(
    "所有 pseudo-bulk 样本的细胞数都小于 min_cells = %d。",
    opt$min_cells
  ))
}
if (length(valid_bulk_ids) < length(cell_counts_per_bulk)) {
  message(sprintf(
    "[WARN] 有 %d 个 pseudo-bulk 样本细胞数 < %d，被移除。",
    length(cell_counts_per_bulk) - length(valid_bulk_ids), opt$min_cells
  ))
}

keep_cells_idx <- which(meta$bulk_id %in% valid_bulk_ids)
meta <- meta[keep_cells_idx, , drop = FALSE]
obj  <- subset(obj, cells = rownames(meta))

# 获取 raw counts 并用稀疏设计矩阵聚合
counts_mat <- GetAssayData(obj, slot = "counts")  # genes x cells
if (!inherits(counts_mat, "dgCMatrix")) {
  counts_mat <- as(counts_mat, "dgCMatrix")
}

meta_df <- data.frame(
  cell = colnames(counts_mat),
  bulk_id = meta$bulk_id,
  stringsAsFactors = FALSE
)

message("[INFO] 构建设计矩阵并聚合为 pseudo-bulk 计数矩阵...")
design_mat <- sparse.model.matrix(~ 0 + bulk_id, data = meta_df)
# 设计矩阵列名形如 bulk_idA，去掉前缀以获得真实 bulk_id
bulk_ids_from_design <- colnames(design_mat)
bulk_ids_clean <- sub("^bulk_id", "", bulk_ids_from_design)

bulk_counts <- counts_mat %*% design_mat  # genes x bulk_samples
colnames(bulk_counts) <- bulk_ids_clean

# 为 DESeq2 构建 colData（每个 bulk 样本一行）
bulk_meta <- meta %>%
  dplyr::select(bulk_id, group, subject) %>%
  dplyr::distinct() %>%
  dplyr::filter(bulk_id %in% bulk_ids_clean)

# 对齐顺序
bulk_meta <- bulk_meta[match(colnames(bulk_counts), bulk_meta$bulk_id), , drop = FALSE]

rownames(bulk_meta) <- bulk_meta$bulk_id
bulk_meta$group   <- as.factor(bulk_meta$group)
bulk_meta$subject <- as.factor(bulk_meta$subject)

message("[INFO] pseudo-bulk 样本数 = ", ncol(bulk_counts))
message("[INFO] group 水平：")
print(table(bulk_meta$group))

# 输出 pseudo-bulk 计数总表和样本/分组对应表 -------------------------------

counts_out_file <- file.path(opt$outdir, "pseudobulk_counts.tsv")
message("[INFO] 输出 pseudo-bulk counts 总表：", counts_out_file)
bulk_counts_df <- as.matrix(bulk_counts) %>%
  as.data.frame(check.names = FALSE)
bulk_counts_df <- tibble::rownames_to_column(bulk_counts_df, var = "gene")
readr::write_tsv(bulk_counts_df, counts_out_file)

sample_group_file <- file.path(opt$outdir, "pseudobulk_sample_group.tsv")
sample_group_df <- bulk_meta %>%
  dplyr::select(bulk_id, subject, group) %>%
  dplyr::rename(sample = bulk_id)
message("[INFO] 输出 pseudo-bulk 样本与分组对应表：", sample_group_file)
readr::write_tsv(sample_group_df, sample_group_file)

# 构建 DESeq2 对象 ----------------------------------------------------------

if (opt$paired) {
  design_formula <- ~ subject + group
  message("[INFO] 使用配对设计：design = ~ subject + group")
} else {
  design_formula <- ~ group
  message("[INFO] 使用非配对设计：design = ~ group")
}

dds <- DESeqDataSetFromMatrix(
  countData = round(bulk_counts),
  colData   = bulk_meta,
  design    = design_formula
)

# 简单过滤低表达基因（可选）
keep_gene <- rowSums(counts(dds)) >= 10
dds <- dds[keep_gene, ]

message("[INFO] 运行 DESeq() ...")
dds <- DESeq(dds)

# 逐对比输出结果 ------------------------------------------------------------

contrast_list <- parse_contrasts(opt$contrasts)

all_results_for_all_contrasts <- list()

for (cc in contrast_list) {
  test_group <- cc$test
  ctrl_group <- cc$ctrl
  cname      <- cc$name

  message(sprintf("[INFO] 处理对比：%s vs %s", test_group, ctrl_group))

  # 当前对比涉及的样本数统计
  group_table <- table(bulk_meta$group)
  n_test <- group_table[as.character(test_group)]
  n_ctrl <- group_table[as.character(ctrl_group)]

  if (is.na(n_test) || is.na(n_ctrl)) {
    warning(sprintf(
      "[WARN] 对比 %s_vs_%s：某组在 pseudo-bulk 中不存在，跳过。",
      test_group, ctrl_group
    ))
    next
  }

  if (n_test < opt$min_samples_group || n_ctrl < opt$min_samples_group) {
    warning(sprintf(
      "[WARN] 对比 %s_vs_%s：test 组样本数 = %d, ctrl 组样本数 = %d，小于 min_samples_group = %d，跳过。",
      test_group, ctrl_group, n_test, n_ctrl, opt$min_samples_group
    ))
    next
  }

  # 提取 DESeq2 结果
  res <- results(
    dds,
    contrast = c("group", as.character(test_group), as.character(ctrl_group))
  )
  res_df <- as.data.frame(res)
  res_df$gene <- rownames(res_df)
  res_df$comparison <- cname

  # 排序
  res_df <- res_df %>%
    dplyr::arrange(padj, pvalue)

  # 输出目录
  out_dir_contrast <- file.path(opt$outdir, cname)
  if (!dir.exists(out_dir_contrast)) {
    dir.create(out_dir_contrast, recursive = TRUE, showWarnings = FALSE)
  }

  # 差异分析总表（gene 放第一列）
  all_file <- file.path(out_dir_contrast, "deseq2_all_genes.tsv")
  readr::write_tsv(reorder_gene_first(res_df), all_file)
  message("[INFO] 总表输出：", all_file)

  # 显著上下调
  if (use_pval_filter) {
    sig_up <- res_df %>%
      dplyr::filter(
        !is.na(pvalue),
        pvalue <= opt$pval_thresh,
        log2FoldChange >= opt$lfc_thresh
      )

    sig_down <- res_df %>%
      dplyr::filter(
        !is.na(pvalue),
        pvalue <= opt$pval_thresh,
        log2FoldChange <= -opt$lfc_thresh
      )
  } else {
    sig_up <- res_df %>%
      dplyr::filter(
        !is.na(padj),
        padj <= opt$padj_thresh,
        log2FoldChange >= opt$lfc_thresh
      )

    sig_down <- res_df %>%
      dplyr::filter(
        !is.na(padj),
        padj <= opt$padj_thresh,
        log2FoldChange <= -opt$lfc_thresh
      )
  }

  up_file <- file.path(out_dir_contrast, "sig_up.tsv")
  dn_file <- file.path(out_dir_contrast, "sig_down.tsv")
  readr::write_tsv(reorder_gene_first(sig_up), up_file)
  readr::write_tsv(reorder_gene_first(sig_down), dn_file)
  message("[INFO] 显著上调基因表：", up_file)
  message("[INFO] 显著下调基因表：", dn_file)

  # 火山图
  volcano_prefix <- file.path(out_dir_contrast, "volcano")
  plot_title <- sprintf("%s vs %s", test_group, ctrl_group)
  plot_volcano(
    res_df,
    lfc_thresh   = opt$lfc_thresh,
    padj_thresh  = opt$padj_thresh,
    pval_thresh  = opt$pval_thresh,
    use_pval     = use_pval_filter,
    title        = plot_title,
    outfile_prefix = volcano_prefix
  )

  all_results_for_all_contrasts[[cname]] <- res_df
}

# 合并所有对比结果（汇总表，gene 第一列） -----------------------------------

if (length(all_results_for_all_contrasts) > 0) {
  all_combined <- dplyr::bind_rows(all_results_for_all_contrasts)
  combined_file <- file.path(opt$outdir, "all_contrasts_deseq2_results.tsv")
  readr::write_tsv(reorder_gene_first(all_combined), combined_file)
  message("[INFO] 所有对比的结果汇总表：", combined_file)
} else {
  warning("[WARN] 没有任何对比成功完成（可能是样本数不足或组缺失）。")
}

message("[INFO] 任务完成。")
