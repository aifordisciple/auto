#!/usr/bin/env Rscript

# """
# 从单细胞 Seurat RDS 进行 Seurat 官方推荐的 pseudobulk（AggregateExpression）并用 DESeq2 做差异分析，
# 并为每个对比的显著差异基因输出“每个点代表一个样本”的小提琴图。
#
# 功能要点
# - pseudobulk：使用 Seurat::AggregateExpression 按 (group, sample) 聚合 raw counts 求和，得到每个样本一个 pseudo-bulk profile
# - DE：在 pseudo-bulk count 矩阵上用 DESeq2（可选 paired：~ subject + group；否则 ~ group）
# - 输出：
#   * pseudobulk_counts.tsv（gene × pseudobulk_sample）
#   * pseudobulk_sample_group.tsv（sample, subject, group）
#   * 每个对比：deseq2_all_genes.tsv, sig_up.tsv, sig_down.tsv, volcano.pdf/png
#   * 每个对比：violin_sig_genes/ 目录下，每个显著基因一张 violin（每点=一个样本；y=VST）
#
# 用法示例：
# Rscript sc_pseudobulk_deseq2_aggregateexpression.r \
#   --rds input.rds \
#   --assay RNA \
#   --group_col response \
#   --sample_col replicate \
#   --celltype_col customclassif \
#   --celltype CD8_T \
#   --contrasts Pembro:Baseline,Pembro_RT:Pembro \
#   --paired \
#   --min_cells 20 \
#   --min_samples_group 2 \
#   --lfc_thresh 0.25 \
#   --padj_thresh 0.05 \
#   --outdir deg_pseudobulk_CD8 \
#   --threads 8
# """

suppressPackageStartupMessages({
  library(optparse)
  library(Seurat)
  library(DESeq2)
  library(dplyr)
  library(readr)
  library(ggplot2)
  library(stringr)
  library(future)
  library(future.apply)
})

VERSION <- "2.0.0"

option_list <- list(
  make_option(c("--rds"), type="character", metavar="FILE", help="输入 Seurat RDS 文件（必需）"),
  make_option(c("--assay"), type="character", default="RNA", help="用于 pseudobulk 的 assay，默认 RNA"),
  make_option(c("--group_col"), type="character", metavar="COL", help="meta.data 分组列（必需）"),
  make_option(c("--sample_col"), type="character", metavar="COL", help="meta.data 样本/个体列（必需）"),
  make_option(c("--celltype_col"), type="character", default=NA, help="细胞类型列（可选）"),
  make_option(c("--celltype"), type="character", default=NA, help="保留的细胞类型名称（可选，需与 celltype_col 搭配）"),
  make_option(c("--contrasts"), type="character", metavar="STR", help="对比列表，如 A:B,C:D（必需）"),
  make_option(c("--paired"), action="store_true", default=FALSE, help="是否配对设计 ~ subject + group"),
  make_option(c("--min_cells"), type="integer", default=10, help="每个 pseudobulk 样本最少细胞数"),
  make_option(c("--min_samples_group"), type="integer", default=2, help="每个组最少 pseudobulk 样本数"),
  make_option(c("--lfc_thresh"), type="double", default=0.25, help="显著基因 |log2FC| 阈值"),
  make_option(c("--padj_thresh"), type="double", default=0.05, help="显著基因 padj 阈值（BH）"),
  make_option(c("--pval_thresh"), type="double", default=NA, help="可选：用 pvalue 阈值替代 padj"),
  make_option(c("--min_gene_counts"), type="integer", default=10, help="DESeq2 前过滤：总 counts >= 该值"),
  make_option(c("--outdir"), type="character", default="deg_pseudobulk", help="输出目录"),
  make_option(c("--threads"), type="integer", default=4, help="并行线程数（主要用于画大量 violin）"),
  make_option(c("--violin_max_genes"), type="integer", default=0,
              help="每个对比最多画多少个显著基因（0 表示不限制；大量基因时建议设 200/500）"),
  make_option(c("--version"), action="store_true", default=FALSE, help="显示版本号后退出")
)

opt <- parse_args(OptionParser(option_list=option_list))
if (isTRUE(opt$version)) {
  cat("Version: ", VERSION, "\n", sep="")
  quit(status=0)
}

stop_if <- function(cond, ...) if (isTRUE(cond)) stop(sprintf(...), call.=FALSE)
msg <- function(...) cat("[", format(Sys.time(), "%F %T"), "] ", sprintf(...), "\n", sep="")

stop_if(is.null(opt$rds) || !file.exists(opt$rds), "必须提供存在的 --rds")
stop_if(is.null(opt$group_col), "必须提供 --group_col")
stop_if(is.null(opt$sample_col), "必须提供 --sample_col")
stop_if(is.null(opt$contrasts), "必须提供 --contrasts")

dir.create(opt$outdir, recursive=TRUE, showWarnings=FALSE)


plan(future::sequential)

parse_contrasts <- function(contrast_str) {
  x <- str_split(contrast_str, pattern=",", simplify=FALSE)[[1]]
  x <- trimws(x)
  x <- x[nzchar(x)]
  stop_if(length(x) == 0, "contrasts 解析为空，请检查格式")
  lapply(x, function(s) {
    parts <- str_split(s, pattern=":", n=2, simplify=TRUE)
    stop_if(ncol(parts) != 2 || any(parts == ""), "对比 '%s' 格式错误，应为 'test:ctrl'", s)
    list(
      name = sprintf("%s_vs_%s", parts[1], parts[2]),
      test = parts[1],
      ctrl = parts[2]
    )
  })
}

reorder_gene_first <- function(df) {
  if (!"gene" %in% colnames(df)) return(df)
  df[, c("gene", setdiff(colnames(df), "gene")), drop=FALSE]
}

safe_filename <- function(x) {
  x <- gsub("[/\\\\:;\\s\\|\\*\\?\\\"\\<\\>]+", "_", x)
  x <- gsub("_+", "_", x)
  x
}

plot_volcano <- function(res_df, lfc_thresh, padj_thresh, pval_thresh=NA, use_pval=FALSE,
                         title=NULL, outfile_prefix) {
  df <- res_df %>% filter(!is.na(log2FoldChange))
  if (use_pval) {
    df <- df %>%
      filter(!is.na(pvalue)) %>%
      mutate(sig = case_when(
        pvalue <= pval_thresh & log2FoldChange >=  lfc_thresh ~ "up",
        pvalue <= pval_thresh & log2FoldChange <= -lfc_thresh ~ "down",
        TRUE ~ "ns"
      ),
      neg_log10 = -log10(pvalue))
    hline_y <- -log10(pval_thresh)
    y_lab <- "-log10 pvalue"
  } else {
    df <- df %>%
      filter(!is.na(padj)) %>%
      mutate(sig = case_when(
        padj <= padj_thresh & log2FoldChange >=  lfc_thresh ~ "up",
        padj <= padj_thresh & log2FoldChange <= -lfc_thresh ~ "down",
        TRUE ~ "ns"
      ),
      neg_log10 = -log10(padj))
    hline_y <- -log10(padj_thresh)
    y_lab <- "-log10 padj"
  }

  p <- ggplot(df, aes(x=log2FoldChange, y=neg_log10, colour=sig)) +
    geom_point(alpha=0.6, size=1) +
    scale_color_manual(values=c(ns="grey70", up="red", down="blue")) +
    geom_vline(xintercept=c(-lfc_thresh, lfc_thresh), linetype="dashed") +
    geom_hline(yintercept=hline_y, linetype="dashed") +
    labs(x="log2 fold change", y=y_lab, title=title, colour=NULL) +
    theme_bw() +
    theme(plot.title=element_text(hjust=0.5), legend.position="right")

  ggsave(paste0(outfile_prefix, ".pdf"), plot=p, width=6, height=5)
  ggsave(paste0(outfile_prefix, ".png"), plot=p, width=6, height=5, dpi=300)
}

# ----------------------------- Load object -----------------------------------
msg("Loading RDS: %s", opt$rds)
obj <- readRDS(opt$rds)
stop_if(!opt$assay %in% names(obj@assays), "Assay '%s' 不存在", opt$assay)
DefaultAssay(obj) <- opt$assay

meta <- obj@meta.data
stop_if(!opt$group_col %in% colnames(meta), "group_col '%s' 不在 meta.data", opt$group_col)
stop_if(!opt$sample_col %in% colnames(meta), "sample_col '%s' 不在 meta.data", opt$sample_col)

# optional celltype subset
if (!is.na(opt$celltype_col) && !is.na(opt$celltype)) {
  stop_if(!opt$celltype_col %in% colnames(meta), "celltype_col '%s' 不在 meta.data", opt$celltype_col)
  cells_keep <- rownames(meta)[as.character(meta[[opt$celltype_col]]) == opt$celltype]
  stop_if(length(cells_keep) == 0, "未找到 celltype=%s（列 %s）", opt$celltype, opt$celltype_col)
  msg("Subsetting celltype=%s (%s): %d cells", opt$celltype, opt$celltype_col, length(cells_keep))
  obj <- subset(obj, cells=cells_keep)
  meta <- obj@meta.data
}

# clean NA in group/sample
group_vec <- as.character(meta[[opt$group_col]])
sample_vec <- as.character(meta[[opt$sample_col]])
keep <- which(!is.na(group_vec) & !is.na(sample_vec) & nzchar(trimws(group_vec)) & nzchar(trimws(sample_vec)))
if (length(keep) < nrow(meta)) {
  msg("Removing cells with NA/empty group or sample: %d -> %d", nrow(meta), length(keep))
  obj <- subset(obj, cells=rownames(meta)[keep])
  meta <- obj@meta.data
}
stop_if(nrow(meta) == 0, "过滤后无细胞可用")

# ----------------------------- min_cells filter (cell-level) -----------------
group_vec <- as.character(meta[[opt$group_col]])
sample_vec <- as.character(meta[[opt$sample_col]])
bulk_key <- paste0(group_vec, "__", sample_vec)
tab_cells <- table(bulk_key)
keep_keys <- names(tab_cells)[tab_cells >= opt$min_cells]
stop_if(length(keep_keys) == 0, "所有 (group,sample) 组合细胞数都 < min_cells=%d", opt$min_cells)

if (length(keep_keys) < length(tab_cells)) {
  msg("Dropping %d pseudobulk samples with cells < %d", length(tab_cells) - length(keep_keys), opt$min_cells)
}
cells_keep2 <- rownames(meta)[bulk_key %in% keep_keys]
obj <- subset(obj, cells=cells_keep2)
meta <- obj@meta.data

# ----------------------------- Pseudobulk by AggregateExpression --------------
# Seurat vignette style: sum counts for cells from same sample (and condition/group) using AggregateExpression
msg("Running AggregateExpression(group.by=c('%s','%s'))", opt$group_col, opt$sample_col)
pseudo <- AggregateExpression(
  object = obj,
  assays = opt$assay,
  return.seurat = TRUE,
  group.by = c(opt$group_col, opt$sample_col)
)

DefaultAssay(pseudo) <- opt$assay

# Extract pseudobulk counts
bulk_counts <- tryCatch(
  GetAssayData(pseudo, assay=opt$assay, layer="counts"),
  error=function(e) GetAssayData(pseudo, assay=opt$assay, slot="counts")
)

# Build pseudobulk meta
pmeta <- pseudo@meta.data
stop_if(!opt$group_col %in% colnames(pmeta), "pseudobulk meta 缺少列：%s", opt$group_col)
stop_if(!opt$sample_col %in% colnames(pmeta), "pseudobulk meta 缺少列：%s", opt$sample_col)

bulk_meta <- data.frame(
  bulk_id = colnames(bulk_counts),
  group = as.factor(as.character(pmeta[[opt$group_col]])),
  subject = as.factor(as.character(pmeta[[opt$sample_col]])),
  stringsAsFactors = FALSE
)
rownames(bulk_meta) <- bulk_meta$bulk_id

# Align
bulk_meta <- bulk_meta[colnames(bulk_counts), , drop=FALSE]

msg("pseudobulk samples: %d", ncol(bulk_counts))
msg("group table:")
print(table(bulk_meta$group))

# Output pseudobulk tables
readr::write_tsv(
  tibble::rownames_to_column(as.data.frame(as.matrix(bulk_counts)), var="gene"),
  file.path(opt$outdir, "pseudobulk_counts.tsv")
)
readr::write_tsv(
  bulk_meta %>% dplyr::select(bulk_id, subject, group) %>% dplyr::rename(sample=bulk_id),
  file.path(opt$outdir, "pseudobulk_sample_group.tsv")
)

# ----------------------------- DESeq2 ----------------------------------------
design_formula <- if (isTRUE(opt$paired)) ~ subject + group else ~ group
msg("DESeq2 design: %s", format(design_formula))

dds <- DESeqDataSetFromMatrix(
  countData = round(as.matrix(bulk_counts)),
  colData = bulk_meta,
  design = design_formula
)

keep_gene <- rowSums(counts(dds)) >= opt$min_gene_counts
dds <- dds[keep_gene, ]
msg("Keeping genes with total counts >= %d : %d genes", opt$min_gene_counts, sum(keep_gene))

dds <- DESeq(dds)

# 1) DESeq2 normalized counts（与 DE 同口径）
norm_counts <- counts(dds, normalized = TRUE)
norm_counts_df <- as.data.frame(as.matrix(norm_counts), check.names = FALSE)
norm_counts_df <- tibble::rownames_to_column(norm_counts_df, var = "gene")
readr::write_tsv(norm_counts_df, file.path(opt$outdir, "pseudobulk_norm_counts.tsv"))

# 2) VST（更适合可视化/作图）
vst_obj <- vst(dds, blind = TRUE)
vst_mat <- assay(vst_obj)
vst_df <- as.data.frame(as.matrix(vst_mat), check.names = FALSE)
vst_df <- tibble::rownames_to_column(vst_df, var = "gene")
readr::write_tsv(vst_df, file.path(opt$outdir, "pseudobulk_vst.tsv"))

# For violin plots: VST matrix (sample-level)
vst_obj <- vst(dds, blind=TRUE)
vst_mat <- assay(vst_obj)  # gene x sample

# ----------------------------- contrasts loop --------------------------------
plan(multisession, workers=max(1, opt$threads))
contrast_list <- parse_contrasts(opt$contrasts)
use_pval_filter <- !is.na(opt$pval_thresh)

all_results_for_all_contrasts <- list()

for (cc in contrast_list) {
  test_group <- cc$test
  ctrl_group <- cc$ctrl
  cname <- cc$name

  msg("Processing contrast: %s vs %s", test_group, ctrl_group)

  group_table <- table(bulk_meta$group)
  n_test <- group_table[as.character(test_group)]
  n_ctrl <- group_table[as.character(ctrl_group)]

  if (is.na(n_test) || is.na(n_ctrl)) {
    msg("Skip %s: group missing in pseudobulk", cname)
    next
  }
  if (n_test < opt$min_samples_group || n_ctrl < opt$min_samples_group) {
    msg("Skip %s: n_test=%d n_ctrl=%d < min_samples_group=%d",
        cname, as.integer(n_test), as.integer(n_ctrl), opt$min_samples_group)
    next
  }

  res <- results(dds, contrast=c("group", as.character(test_group), as.character(ctrl_group)))
  res_df <- as.data.frame(res)
  res_df$gene <- rownames(res_df)
  res_df$comparison <- cname
  res_df <- res_df %>% arrange(padj, pvalue)

  out_dir_contrast <- file.path(opt$outdir, cname)
  dir.create(out_dir_contrast, recursive=TRUE, showWarnings=FALSE)

  readr::write_tsv(reorder_gene_first(res_df), file.path(out_dir_contrast, "deseq2_all_genes.tsv"))

  # significant genes
  if (use_pval_filter) {
    sig_up <- res_df %>% filter(!is.na(pvalue), pvalue <= opt$pval_thresh,
                                log2FoldChange >= opt$lfc_thresh)
    sig_down <- res_df %>% filter(!is.na(pvalue), pvalue <= opt$pval_thresh,
                                  log2FoldChange <= -opt$lfc_thresh)
  } else {
    sig_up <- res_df %>% filter(!is.na(padj), padj <= opt$padj_thresh,
                                log2FoldChange >= opt$lfc_thresh)
    sig_down <- res_df %>% filter(!is.na(padj), padj <= opt$padj_thresh,
                                  log2FoldChange <= -opt$lfc_thresh)
  }

  readr::write_tsv(reorder_gene_first(sig_up), file.path(out_dir_contrast, "sig_up.tsv"))
  readr::write_tsv(reorder_gene_first(sig_down), file.path(out_dir_contrast, "sig_down.tsv"))

  # volcano
  plot_volcano(
    res_df,
    lfc_thresh=opt$lfc_thresh,
    padj_thresh=opt$padj_thresh,
    pval_thresh=opt$pval_thresh,
    use_pval=use_pval_filter,
    title=sprintf("%s vs %s", test_group, ctrl_group),
    outfile_prefix=file.path(out_dir_contrast, "volcano")
  )

  # --------------------- per-gene violin plots (sample-level) ----------------
  sig_genes <- unique(c(sig_up$gene, sig_down$gene))
  if (length(sig_genes) > 0) {
    vdir <- file.path(out_dir_contrast, "violin_sig_genes")
    dir.create(vdir, recursive=TRUE, showWarnings=FALSE)

    if (opt$violin_max_genes > 0 && length(sig_genes) > opt$violin_max_genes) {
      # keep top by padj/pvalue
      msg("Sig genes=%d > violin_max_genes=%d, will plot top ones", length(sig_genes), opt$violin_max_genes)
      if (use_pval_filter) {
        top_df <- res_df %>% filter(gene %in% sig_genes) %>% arrange(pvalue)
      } else {
        top_df <- res_df %>% filter(gene %in% sig_genes) %>% arrange(padj)
      }
      sig_genes <- head(top_df$gene, opt$violin_max_genes)
    }

    # Only use samples in these two groups for plotting
    plot_samples <- rownames(bulk_meta)[bulk_meta$group %in% c(test_group, ctrl_group)]
    pm <- bulk_meta[plot_samples, , drop=FALSE]
    pm$group <- droplevels(pm$group)
    pm$subject <- droplevels(pm$subject)

    make_one_violin <- function(g) {
      if (!g %in% rownames(vst_mat)) return(NULL)
      df <- data.frame(
        sample = plot_samples,
        group = pm$group,
        subject = pm$subject,
        expr = as.numeric(vst_mat[g, plot_samples]),
        stringsAsFactors = FALSE
      )
      # """
      # paired 小提琴图：点和配对连线严格对应
      # - 不用 jitter（会打乱 x）
      # - 使用 position_dodge，让同一 subject 在各组的点落在同一条轨道
      # - geom_point 与 geom_line 共享同一个 dodge 参数
      # """

      dodge_w <- 0.35
      pd <- position_dodge(width = dodge_w)

      p <- ggplot(df, aes(x = group, y = expr)) +
        geom_violin(trim = FALSE, aes(group = group)) +
        geom_point(
          aes(group = subject),
          position = pd,
          alpha = 0.85,
          size = 1.6
        ) +
        stat_summary(fun = mean, geom = "point", size = 2.2) +
        labs(title = g, x = NULL, y = "VST expression (each point = one sample)") +
        theme_bw() +
        theme(plot.title = element_text(hjust = 0.5))

      if (isTRUE(opt$paired)) {
        p <- p +
          geom_line(
            aes(group = subject),
            position = pd,
            alpha = 0.35,
            linewidth = 0.6
          )
      }

      base <- file.path(vdir, paste0("violin_", safe_filename(g)))
      ggsave(paste0(base, ".pdf"), plot=p, width=5.5, height=4.5)
      ggsave(paste0(base, ".png"), plot=p, width=5.5, height=4.5, dpi=300)
      return(NULL)
    }

    invisible(future_lapply(sig_genes, make_one_violin))
  } else {
    msg("No significant genes for %s", cname)
  }

  all_results_for_all_contrasts[[cname]] <- res_df
}

# Combined table
if (length(all_results_for_all_contrasts) > 0) {
  all_combined <- bind_rows(all_results_for_all_contrasts)
  readr::write_tsv(
    reorder_gene_first(all_combined),
    file.path(opt$outdir, "all_contrasts_deseq2_results.tsv")
  )
} else {
  msg("No contrasts completed (check group/sample counts).")
}

msg("DONE.")
