#!/usr/bin/env Rscript
# """
# Seurat RDS 差异基因分析（按 Seurat 官方最佳实践重构版）

# 功能要点
# - 支持三种模式：by_cluster / by_class / by_all
# - 支持 compare_list: "A:B,B:C"（test:ctrl）
# - 兼容 Seurat v4/v5；RNA/SCT 自适配
# - SCT 模式自动 PrepSCTFindMarkers
# - FindMarkers 支持 min_pct / min_diff_pct / only_pos / latent_vars（协变量）
# - 并行：可按 cluster 并行跑 FindMarkers（future_lapply）
# - 输出：全基因结果、过滤 up/down、topN、AverageExpression 散点图（pdf/png）
# - 记录参数与 sessionInfo

# 用法示例：
# Rscript deg_seurat.r \
#   --infile cells_analysis.rds \
#   --outdir deg_out \
#   --group_var group \
#   --ident_var seurat_clusters \
#   --class_var customclassif \
#   --compare_list post:pre,pre:Control \
#   --default_assay RNA \
#   --test_use wilcox \
#   --logfc 0.5 \
#   --min_pct 0.1 \
#   --min_diff_pct 0.0 \
#   --padj 0.05 \
#   --min_cells_group 20 \
#   --ncpus 8
# """

suppressPackageStartupMessages({
  library(optparse)
  library(future.apply)
  library(Seurat)
  library(dplyr)
  library(tibble)
  library(readr)
  library(purrr)
  library(ggplot2)
  library(ggrepel)
})

VERSION <- "2.1.0"

# ---------------- CLI ----------------
option_list <- list(
  make_option(c("--version"), action = "store_true", default = FALSE,
              help = "print version and exit"),

  make_option(c("--infile","-i"), type = "character", default = NA,
              help = "input Seurat RDS"),

  make_option(c("--outdir"), type = "character", default = "./",
              help = "output directory"),

  make_option(c("--group_var"), type = "character", default = "group",
              help = "meta.data column used as group (case/control)"),

  make_option(c("--ident_var"), type = "character", default = "seurat_clusters",
              help = "meta.data column used as cluster ident; if empty use Idents(obj)"),

  make_option(c("--class_var"), type = "character", default = "customclassif",
              help = "meta.data column used as broad class (celltype); optional"),

  make_option(c("--compare_list","-c"), type = "character", default = "",
              help = "comparisons: A:B,B:C (test:ctrl)"),

  make_option(c("--default_assay","-a"), type = "character", default = "RNA",
              help = "RNA|SCT (assay used for DE)"),

  make_option(c("--slot_use"), type = "character", default = "data",
              help = "FindMarkers slot/layer preference: data|counts (RNA常用data；部分检验/场景可用counts)"),

  make_option(c("--test_use"), type = "character", default = "wilcox",
              help = "FindMarkers test.use, e.g. wilcox|MAST|LR|DESeq2"),

  make_option(c("--latent_vars"), type = "character", default = "",
              help = "comma separated covariates for latent.vars (e.g. nCount_RNA,percent.mt)"),

  make_option(c("--logfc"), type = "double", default = 0.5,
              help = "abs log2FC threshold for filtering"),

  make_option(c("--padj"), type = "double", default = 0.05,
              help = "adjusted p-value threshold"),

  make_option(c("--p_adjust_method"), type = "character", default = "bonferroni",
              help = "p.adjust method used by Seurat, typically bonferroni (Seurat default)"),

  make_option(c("--min_cells_group"), type = "integer", default = 20,
              help = "minimum cells per group for a comparison"),

  make_option(c("--min_pct"), type = "double", default = 0.1,
              help = "FindMarkers min.pct (speed-up + best practice)"),

  make_option(c("--min_diff_pct"), type = "double", default = 0.0,
              help = "FindMarkers min.diff.pct (optional speed-up)"),

  make_option(c("--only_pos"), type = "character", default = "false",
              help = "true|false output only positive markers"),

  make_option(c("--topn"), type = "integer", default = 5,
              help = "top N genes for labeling"),

  make_option(c("--do_by_cluster"), type = "character", default = "false",
              help = "true|false: run DE within each cluster across groups"),

  make_option(c("--do_by_class"), type = "character", default = "true",
              help = "true|false: run DE within each class across groups"),

  make_option(c("--do_by_all"), type = "character", default = "true",
              help = "true|false: run DE on all cells across groups"),

  make_option(c("--ncpus","-n"), type = "integer", default = 2,
              help = "parallel workers"),

  make_option(c("--max_mem_mega"), type = "integer", default = 80000,
              help = "future.globals.maxSize (MB)"),

  make_option(c("--use_future_parallel"), type = "character", default = "true",
              help = "true|false: parallelize across clusters/classes (recommended)")
)

opt <- parse_args(OptionParser(option_list = option_list))
if (isTRUE(opt$version)) { cat("Version:", VERSION, "\n"); quit(save = "no") }

# ---------------- Utils ----------------
bool <- function(x) tolower(as.character(x)) %in% c("1","true","t","yes","y")

dir_create <- function(p) {
  if (!dir.exists(p)) dir.create(p, recursive = TRUE)
  normalizePath(p)
}

nzchar2 <- function(x) !is.null(x) && is.character(x) && nzchar(x)

ensure_meta <- function(obj, col){
  if (!nzchar2(col)) return(invisible(TRUE))
  if (!(col %in% colnames(obj@meta.data))) stop(sprintf("meta.data 不含列: %s", col))
  invisible(TRUE)
}

std_deg_cols <- function(df){
  if ("avg_logFC" %in% colnames(df) && !("avg_log2FC" %in% colnames(df))) {
    df <- dplyr::rename(df, avg_log2FC = avg_logFC)
  }
  df
}

save_tsv <- function(x, path, rownames_as_col = NULL){
  x <- as.data.frame(x)
  if (!is.null(rownames_as_col)) {
    x[[rownames_as_col]] <- rownames(x)
    rownames(x) <- NULL
    x <- x[, c(rownames_as_col, setdiff(colnames(x), rownames_as_col)), drop = FALSE]
  }
  readr::write_tsv(x, path)
}

label_genes_scatter <- function(
  df_xy, xcol, ycol, genes_to_label,
  title, outfile_prefix,
  point_size = 1.2, alpha = 0.6, text_size = 3,
  width_in = 3.8, height_in = 3.8
){
  stopifnot(all(c(xcol, ycol, "gene") %in% colnames(df_xy)))
  genes_to_label <- unique(genes_to_label[genes_to_label %in% df_xy$gene])
  df_lab <- dplyr::filter(df_xy, gene %in% genes_to_label)

  p <- ggplot(df_xy, aes(.data[[xcol]], .data[[ycol]])) +
    geom_point(alpha = alpha, shape = 16, size = point_size) +
    { if (nrow(df_lab) > 0)
        ggrepel::geom_text_repel(
          data = df_lab, aes(label = gene),
          max.overlaps = Inf, size = text_size
        )
      else NULL } +
    labs(title = title, x = xcol, y = ycol) +
    theme_minimal(base_size = 12)

  dir.create(dirname(outfile_prefix), recursive = TRUE, showWarnings = FALSE)
  ggsave(paste0(outfile_prefix, ".pdf"), plot = p, width = width_in, height = height_in, units = "in")
  ggsave(paste0(outfile_prefix, ".png"), plot = p, width = width_in, height = height_in, units = "in", dpi = 300)
  invisible(p)
}

pick_top <- function(df, n=5, up=TRUE){
  df <- std_deg_cols(df)
  if (up) df %>% arrange(desc(avg_log2FC), p_val) %>% slice_head(n=n)
  else    df %>% arrange(avg_log2FC, p_val) %>% slice_head(n=n)
}

# AverageExpression：避免重复 log
ae_df <- function(obj, group_var, assay_use, slot_use){
  Idents(obj) <- obj@meta.data[[group_var]]
  # v5 有 layer 参数，但 slot 仍可用；这里用 slot_use 兼容
  ae_list <- AverageExpression(obj, assays = assay_use, slot = slot_use, verbose = FALSE)
  mat <- ae_list[[assay_use]]
  df  <- as.data.frame(mat)
  df$gene <- rownames(df)
  tibble::as_tibble(df)
}

# ---------------- 环境与输入 ----------------
if (is.null(opt$infile) || is.na(opt$infile)) stop("--infile 必填")

options(future.globals.maxSize = opt$max_mem_mega * 1024^2)
future::plan(multisession, workers = opt$ncpus)

outdir <- dir_create(opt$outdir)
by_cluster_dir <- dir_create(file.path(outdir, "deg_by_cluster"))
by_class_dir   <- dir_create(file.path(outdir, "deg_by_celltype"))
by_all_dir     <- dir_create(file.path(outdir, "deg_by_all"))

obj <- readRDS(opt$infile)

# 基础检查：group_var 必须存在
ensure_meta(obj, opt$group_var)

# ident_var 可选
idents_backup <- Idents(obj)
if (nzchar2(opt$ident_var)) {
  ensure_meta(obj, opt$ident_var)
  Idents(obj) <- obj@meta.data[[opt$ident_var]]
}

# DefaultAssay
if (!(opt$default_assay %in% Assays(obj))) stop(sprintf("对象中未找到 assay: %s", opt$default_assay))
DefaultAssay(obj) <- opt$default_assay

# SCT: best practice
if (opt$default_assay == "SCT") {
  # 官方建议在 SCT 上跑 FindMarkers 前做 PrepSCTFindMarkers
  try(obj <- PrepSCTFindMarkers(obj, assay = "SCT", verbose = FALSE), silent = TRUE)
}

# compare_list 解析
cmp_vec <- if (nzchar2(opt$compare_list)) strsplit(opt$compare_list, ",")[[1]] else character(0)
cmp_pairs <- purrr::map(cmp_vec, ~strsplit(.x, ":", fixed = TRUE)[[1]])
if (length(cmp_pairs) && any(lengths(cmp_pairs) != 2)) stop("--compare_list 格式应为 A:B,C:D ...")

latent_vars <- if (nzchar2(opt$latent_vars)) strsplit(opt$latent_vars, ",")[[1]] else NULL
if (!is.null(latent_vars)) {
  # 协变量常见需要 MAST/LR；wilcox 通常不做协变量回归
  if (tolower(opt$test_use) == "wilcox") {
    message("[WARN] 指定了 latent_vars 但 test_use=wilcox 可能无法按预期回归协变量；自动切换为 MAST。")
    opt$test_use <- "MAST"
  }
  # 检查 latent_vars 是否存在
  for (lv in latent_vars) ensure_meta(obj, lv)
}

# 过滤参数
only_pos <- bool(opt$only_pos)

# ---------------- 参数记录 ----------------
save_deg_parameters <- function(opt, outdir, cmp_pairs, latent_vars){
  param_file <- file.path(outdir, "deg_analysis_parameters.txt")
  sink(param_file)
  cat("Seurat DEG parameters\n")
  cat("=====================\n")
  cat("time:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
  cat("script_version:", VERSION, "\n")
  cat("input:", opt$infile, "\n")
  cat("outdir:", outdir, "\n\n")

  cat("group_var:", opt$group_var, "\n")
  cat("ident_var:", opt$ident_var, "\n")
  cat("class_var:", opt$class_var, "\n")
  cat("default_assay:", opt$default_assay, "\n")
  cat("slot_use:", opt$slot_use, "\n")
  cat("test_use:", opt$test_use, "\n")
  cat("latent_vars:", ifelse(is.null(latent_vars), "none", paste(latent_vars, collapse=",")), "\n\n")

  cat("thresholds\n")
  cat("logfc:", opt$logfc, "\n")
  cat("padj:", opt$padj, "\n")
  cat("min_cells_group:", opt$min_cells_group, "\n")
  cat("min_pct:", opt$min_pct, "\n")
  cat("min_diff_pct:", opt$min_diff_pct, "\n")
  cat("only_pos:", opt$only_pos, "\n\n")

  cat("comparisons\n")
  if (length(cmp_pairs) > 0) {
    for (i in seq_along(cmp_pairs)) cat(i, ":", cmp_pairs[[i]][1], "vs", cmp_pairs[[i]][2], "\n")
  } else cat("none\n")

  sink()
  message("DEG参数已保存至: ", param_file)
  param_file
}
save_deg_parameters(opt, outdir, cmp_pairs, latent_vars)

# ---------------- 核心：单个 level 的 FindMarkers ----------------
find_markers_safe <- function(obj_use, ident1, ident2, opt, latent_vars){
  tryCatch({
    FindMarkers(
      obj_use,
      ident.1 = ident1,
      ident.2 = ident2,
      min.cells.group = opt$min_cells_group,
      logfc.threshold = 0,           # 不提前截断，统一后滤
      min.pct = opt$min_pct,         # best practice: 预过滤提高速度
      min.diff.pct = opt$min_diff_pct,
      only.pos = only_pos,
      test.use = opt$test_use,
      latent.vars = latent_vars,
      slot = opt$slot_use
    ) %>% std_deg_cols()
  }, error = function(e) NULL)
}

# ---------------- 核心：by ident（cluster 或 class） ----------------
run_deg_by_ident <- function(obj_in, ident_col, group_var, test_group, ctrl_group, out_base, topn, opt, latent_vars){
  message(sprintf("[DEG] %s | %s vs %s", ident_col, test_group, ctrl_group))

  # 只构造一次 composite ident，避免循环反复写 meta
  ident_val <- as.character(obj_in@meta.data[[ident_col]])
  grp_val   <- as.character(obj_in@meta.data[[group_var]])
  composite <- paste0(ident_val, "_", grp_val)

  obj_use <- obj_in
  obj_use[[".deg_ident"]] <- ident_val
  obj_use[[".deg_group"]] <- grp_val
  obj_use[[".deg_comp"]]  <- composite
  Idents(obj_use) <- ".deg_comp"

  levels_ident <- sort(unique(ident_val))
  # 并行跑每个 level
  one_level <- function(level){
    ident1 <- paste0(level, "_", test_group)
    ident2 <- paste0(level, "_", ctrl_group)
    if (sum(Idents(obj_use) == ident1) < opt$min_cells_group) return(NULL)
    if (sum(Idents(obj_use) == ident2) < opt$min_cells_group) return(NULL)

    res <- find_markers_safe(obj_use, ident1, ident2, opt, latent_vars)
    if (is.null(res) || nrow(res) == 0) return(NULL)

    res <- res %>% rownames_to_column("gene")
    res$cluster <- level
    res
  }

  if (bool(opt$use_future_parallel)) {
    deg_list <- future.apply::future_lapply(levels_ident, one_level)
  } else {
    deg_list <- lapply(levels_ident, one_level)
  }

  all_deg <- bind_rows(deg_list)
  if (is.null(all_deg) || nrow(all_deg) == 0) {
    warning(sprintf("无可用结果：%s | %s vs %s", ident_col, test_group, ctrl_group))
    return(invisible(NULL))
  }

  all_deg <- std_deg_cols(all_deg) %>% arrange(cluster, p_val)
  save_tsv(all_deg, file.path(out_base, sprintf("%s_vs_%s_all_genes.tsv", test_group, ctrl_group)))

  # 过滤：up/down（用 pct.1/pct.2 + logfc + padj）
  up_filt <- all_deg %>% filter(avg_log2FC >=  opt$logfc, p_val_adj <= opt$padj, pct.1 >= opt$min_pct)
  dn_filt <- all_deg %>% filter(avg_log2FC <= -opt$logfc, p_val_adj <= opt$padj, pct.2 >= opt$min_pct)
  save_tsv(up_filt, file.path(out_base, sprintf("%s_vs_%s_filter_up.tsv", test_group, ctrl_group)))
  save_tsv(dn_filt, file.path(out_base, sprintf("%s_vs_%s_filter_down.tsv", test_group, ctrl_group)))

  # topN per cluster
  top_up <- all_deg %>%
    group_by(cluster) %>%
    arrange(desc(avg_log2FC), p_val, .by_group = TRUE) %>% slice_head(n = topn) %>% ungroup()
  top_dn <- all_deg %>%
    group_by(cluster) %>%
    arrange(avg_log2FC, p_val, .by_group = TRUE) %>% slice_head(n = topn) %>% ungroup()

  save_tsv(top_up, file.path(out_base, sprintf("%s_vs_%s_top%d_up.tsv", test_group, ctrl_group, topn)))
  save_tsv(top_dn, file.path(out_base, sprintf("%s_vs_%s_top%d_down.tsv", test_group, ctrl_group, topn)))

  # AverageExpression scatter（只看 test/ctrl；按 assay + slot_use）
  sub_idx <- obj_in@meta.data[[group_var]] %in% c(test_group, ctrl_group)
  obj_sub <- subset(obj_in, cells = rownames(obj_in@meta.data)[sub_idx])

  assay_use <- DefaultAssay(obj_sub)
  df_ae <- ae_df(obj_sub, group_var = group_var, assay_use = assay_use, slot_use = opt$slot_use)

  if (!all(c(test_group, ctrl_group) %in% colnames(df_ae))) {
    warning("AverageExpression 未包含预期分组列，跳过散点图")
    return(invisible(list(all=all_deg, up=up_filt, down=dn_filt, top_up=top_up, top_dn=top_dn)))
  }

  expscatter_dir <- dir_create(file.path(out_base, "expscatter"))
  purrr::walk(unique(top_up$cluster), function(level){
    genes_to_label <- unique(c(
      top_up %>% filter(cluster == level) %>% pull(gene) %>% head(topn),
      top_dn %>% filter(cluster == level) %>% pull(gene) %>% head(topn)
    ))
    label_genes_scatter(
      df_xy = df_ae, xcol = test_group, ycol = ctrl_group,
      genes_to_label = genes_to_label,
      title = sprintf("%s | %s vs %s", level, test_group, ctrl_group),
      outfile_prefix = file.path(expscatter_dir, sprintf("%s_%s_vs_%s", level, test_group, ctrl_group))
    )
  })

  invisible(list(all=all_deg, up=up_filt, down=dn_filt, top_up=top_up, top_dn=top_dn))
}

# ---------------- by_all ----------------
run_deg_by_all <- function(obj_in, group_var, test_group, ctrl_group, out_base, topn, opt, latent_vars){
  message(sprintf("[DEG] by_all | %s vs %s", test_group, ctrl_group))
  ensure_meta(obj_in, group_var)

  obj_use <- obj_in
  Idents(obj_use) <- obj_use@meta.data[[group_var]]

  if (sum(Idents(obj_use) == test_group, na.rm = TRUE) < opt$min_cells_group ||
      sum(Idents(obj_use) == ctrl_group, na.rm = TRUE) < opt$min_cells_group) {
    warning("by_all: 某组细胞数不足，跳过该比较")
    return(invisible(NULL))
  }

  all_deg <- find_markers_safe(obj_use, test_group, ctrl_group, opt, latent_vars)
  if (is.null(all_deg) || nrow(all_deg) == 0) return(invisible(NULL))

  all_deg <- all_deg %>% arrange(p_val)
  save_tsv(all_deg, file.path(out_base, "all_genes.tsv"), rownames_as_col = "gene")

  up_filt <- all_deg %>% filter(avg_log2FC >=  opt$logfc, p_val_adj <= opt$padj, pct.1 >= opt$min_pct)
  dn_filt <- all_deg %>% filter(avg_log2FC <= -opt$logfc, p_val_adj <= opt$padj, pct.2 >= opt$min_pct)
  save_tsv(up_filt, file.path(out_base, "filter_up.tsv"), rownames_as_col = "gene")
  save_tsv(dn_filt, file.path(out_base, "filter_down.tsv"), rownames_as_col = "gene")

  top_up <- pick_top(all_deg, n = topn, up = TRUE)
  top_dn <- pick_top(all_deg, n = topn, up = FALSE)
  save_tsv(top_up, file.path(out_base, sprintf("top%d_up.tsv", topn)), rownames_as_col = "gene")
  save_tsv(top_dn, file.path(out_base, sprintf("top%d_down.tsv", topn)), rownames_as_col = "gene")

  # AverageExpression scatter
  obj_sub <- subset(obj_use, idents = c(test_group, ctrl_group))
  assay_use <- DefaultAssay(obj_sub)
  df_ae <- ae_df(obj_sub, group_var = group_var, assay_use = assay_use, slot_use = opt$slot_use)

  if (all(c(test_group, ctrl_group) %in% colnames(df_ae))) {
    expscatter_dir <- dir_create(file.path(out_base, "expscatter"))
    label_genes_scatter(
      df_xy = df_ae, xcol = test_group, ycol = ctrl_group,
      genes_to_label = unique(c(rownames(top_up), rownames(top_dn))),
      title = "by_all",
      outfile_prefix = file.path(expscatter_dir, "by_all_top")
    )
  }
  invisible(list(all=all_deg, up=up_filt, down=dn_filt, top_up=top_up, top_dn=top_dn))
}

# ---------------- main ----------------
if (length(cmp_pairs) == 0) stop("--compare_list 必填，例如 A:B,B:C")

# 1) by_cluster
if (bool(opt$do_by_cluster)) {
  obj$celltype <- as.character(Idents(obj))
  for (pr in cmp_pairs) {
    test_group <- pr[1]; ctrl_group <- pr[2]
    out_base <- dir_create(file.path(by_cluster_dir, sprintf("%s_vs_%s", test_group, ctrl_group)))
    run_deg_by_ident(obj, ident_col = "celltype", group_var = opt$group_var,
                    test_group = test_group, ctrl_group = ctrl_group,
                    out_base = out_base, topn = opt$topn, opt = opt, latent_vars = latent_vars)
  }
}

# 2) by_class
if (bool(opt$do_by_class) && nzchar2(opt$class_var)) {
  ensure_meta(obj, opt$class_var)
  obj$class <- as.character(obj@meta.data[[opt$class_var]])
  for (pr in cmp_pairs) {
    test_group <- pr[1]; ctrl_group <- pr[2]
    out_base <- dir_create(file.path(by_class_dir, sprintf("%s_vs_%s", test_group, ctrl_group)))
    run_deg_by_ident(obj, ident_col = "class", group_var = opt$group_var,
                    test_group = test_group, ctrl_group = ctrl_group,
                    out_base = out_base, topn = opt$topn, opt = opt, latent_vars = latent_vars)
  }
}

# 3) by_all
if (bool(opt$do_by_all)) {
  for (pr in cmp_pairs) {
    test_group <- pr[1]; ctrl_group <- pr[2]
    out_base <- dir_create(file.path(by_all_dir, sprintf("%s_vs_%s", test_group, ctrl_group)))
    run_deg_by_all(obj, group_var = opt$group_var,
                   test_group = test_group, ctrl_group = ctrl_group,
                   out_base = out_base, topn = opt$topn, opt = opt, latent_vars = latent_vars)
  }
}

# restore
Idents(obj) <- idents_backup
writeLines(capture.output(sessionInfo()), file.path(outdir, "session_info.txt"))
message("Done.")
