#!/usr/bin/env Rscript

# 单细胞差异基因分析（稳健版）
# - 长参数统一以下划线命名
# - 模块化：by_cluster / by_class / by_all
# - 线程安全：不使用 <<-；不切换工作目录；无外部 source
# - 兼容 Seurat v4/v5；SCT/RNA 自适配
# 作者: biosalt（重构整理）
# 版本: 2.0.0

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

VERSION <- "2.0.0"
set.seed(1)

# ---------------- CLI ----------------
option_list <- list(
  make_option(c("-i","--infile"),           type="character", help="输入 Seurat RDS 文件"),
  make_option(c("--outdir"),           type="character", default="./", help="输出目录"),
  make_option(c("--group_var"),        type="character", default="group", help="分组列名（meta.data 中）"),
  make_option(c("--ident_var"),        type="character", default="seurat_clusters", help="cluster 列名；为空则使用当前 Idents"),
  make_option(c("--class_var"),        type="character", default="customclassif", help="大类细胞类型列名（可选）"),
  make_option(c("-c","--compare_list"),     type="character", default="", help="组间比较列表，如 A:B,B:C"),
  make_option(c("-a","--default_assay"),    type="character", default="RNA", help="默认 assay [RNA|SCT]"),
  make_option(c("-f","--logfc"),            type="double",   default=0.5, help="log2FC 阈值"),
  make_option(c("--pct"), type="double", default=0.1, help="deg_min_pct_in_higher_group, 表达较高的组最小 pct"),
  make_option(c("--padj"),             type="double",   default=0.05, help="FDR 阈值（p_val_adj）"),
  make_option(c("--min_cells_group"),  type="integer",  default=20, help="每组最少细胞数"),
  make_option(c("--latent_vars"),      type="character", default="", help="潜在协变量，逗号分隔（传给 FindMarkers 的 latent.vars）"),
  make_option(c("--test_use"),         type="character", default="wilcox", help="差异检验方法，见 Seurat::FindMarkers，如果用latent_vars，需要设为MAST"),
  make_option(c("--ncpus"),            type="integer",  default=2,  help="并行核数"),
  make_option(c("--max_mem_mega"),     type="integer",  default=80000, help="future.globals.maxSize (MB)"),
  make_option(c("--topn"),             type="integer",  default=5,  help="标注散点图的 top N 基因"),
  make_option(c("--do_by_cluster"),    type="character", default="FALSE", help="是否按 ident_var 分 cluster 比较"),
  make_option(c("--do_by_class"),      type="character", default="TRUE", help="是否按 class_var 分大类比较"),
  make_option(c("--do_by_all"),        type="character", default="TRUE", help="是否全体细胞比较"),
  make_option(c("--version"),          action="store_true", default=FALSE, help="打印版本")
)
opt <- parse_args(OptionParser(option_list=option_list))
if (opt$version) { cat("Version:", VERSION, "\n"); quit(save="no") }

# ---------------- Utils ----------------
bool <- function(x) tolower(as.character(x)) %in% c("1","true","t","yes","y")

dir_create <- function(p) { if (!dir.exists(p)) dir.create(p, recursive = TRUE); normalizePath(p) }

std_deg_cols <- function(df){
  # 兼容 avg_logFC 与 avg_log2FC
  if ("avg_logFC" %in% colnames(df) && !("avg_log2FC" %in% colnames(df))) {
    df <- dplyr::rename(df, avg_log2FC = avg_logFC)
  }
  df
}

ae_df <- function(obj, group_var){
  # 用 AverageExpression 生成 test/ctrl 两列的 log1p 平均表达
  assay_now <- DefaultAssay(obj)
  Idents(obj) <- group_var
  ae_list <- AverageExpression(obj, assays = assay_now, verbose = FALSE)
  mat <- ae_list[[assay_now]]
  mat <- log1p(mat)
  df  <- as.data.frame(mat)
  df$gene <- rownames(df)
  tibble::as_tibble(df)
}

save_tsv <- function(x, path, rownames_as_col = NULL){
  x <- as.data.frame(x)
  if (!is.null(rownames_as_col)) {
    x[[rownames_as_col]] <- rownames(x); rownames(x) <- NULL
    x <- x[, c(rownames_as_col, setdiff(colnames(x), rownames_as_col)), drop=FALSE]
  }
  readr::write_tsv(x, path)
}

label_genes_scatter <- function(
  df_xy,
  xcol,
  ycol,
  genes_to_label,
  title,
  outfile_prefix,
  label_color   = "red",
  other_color   = "grey50",
  point_size    = 1.2,
  alpha         = 0.6,
  text_size     = 3,
  width_in      = 3.6,
  height_in     = 3.6
){
  # 基础检查
  stopifnot(all(c(xcol, ycol, "gene") %in% colnames(df_xy)))
  if (is.null(genes_to_label)) genes_to_label <- character(0)
  genes_to_label <- unique(genes_to_label[genes_to_label %in% df_xy$gene])

  # 分层数据：先画所有点（other_color），再叠加被标注点（label_color）
  df_lab <- dplyr::filter(df_xy, gene %in% genes_to_label)

  p <- ggplot(df_xy, aes(.data[[xcol]], .data[[ycol]])) +
    geom_point(color = other_color, alpha = alpha, shape = 16, size = point_size) +
    # 高亮被标注的点为红色，并放在上层
    { if (nrow(df_lab) > 0)
        geom_point(data = df_lab, color = label_color, alpha = 1, shape = 16, size = point_size + 0.3)
      else NULL } +
    # 文本标注
    { if (nrow(df_lab) > 0)
        ggrepel::geom_text_repel(
          data = df_lab,
          aes(label = gene),
          max.overlaps = Inf,
          size = text_size
        )
      else NULL } +
    labs(title = title, x = xcol, y = ycol) +
    theme_minimal(base_size = 12)

  # 确保输出目录存在
  dir.create(dirname(outfile_prefix), recursive = TRUE, showWarnings = FALSE)

  ggsave(paste0(outfile_prefix, ".pdf"), plot = p, width = width_in, height = height_in, units = "in")
  ggsave(paste0(outfile_prefix, ".png"), plot = p, width = width_in, height = height_in, units = "in", dpi = 300)

  invisible(p)
}


pick_top <- function(df, n=5, up=TRUE){
  df <- std_deg_cols(df)
  if (up) {
    df %>% arrange(desc(avg_log2FC), p_val) %>% slice_head(n=n)
  } else {
    df %>% arrange(avg_log2FC, p_val) %>% slice_head(n=n)
  }
}

ensure_meta <- function(obj, col){
  if (!nzchar(col)) return(invisible(TRUE))
  if (!(col %in% colnames(obj@meta.data))) {
    stop(sprintf("meta.data 不含列: %s", col))
  }
  invisible(TRUE)
}

# ---------------- 环境与输入 ----------------
plan(multisession, workers = opt$ncpus)
options(future.globals.maxSize = opt$max_mem_mega * 1024^2)

outdir      <- dir_create(opt$outdir)
by_cluster_dir <- dir_create(file.path(outdir, "deg_by_cluster"))
by_class_dir   <- dir_create(file.path(outdir, "deg_by_celltype"))
by_all_dir     <- dir_create(file.path(outdir, "deg_by_all"))

if (is.null(opt$infile)) stop("--infile 必填")
obj <- readRDS(opt$infile)

# 设置 DefaultAssay
if (!(opt$default_assay %in% Assays(obj))) {
  stop(sprintf("对象中未找到 assay: %s", opt$default_assay))
}
DefaultAssay(obj) <- opt$default_assay

# SCT 预处理（若使用 SCT）
if (opt$default_assay == "SCT") {
  try( obj <- PrepSCTFindMarkers(obj, assay = "SCT", verbose = FALSE), silent = TRUE )
}

# 检查分组列
ensure_meta(obj, opt$group_var)

# 若提供 ident_var，则设置 Idents
idents_backup <- Idents(obj)
if (nzchar(opt$ident_var)) {
  ensure_meta(obj, opt$ident_var)
  Idents(obj) <- obj@meta.data[[opt$ident_var]]
}

# 解析比较列表
cmp_vec <- if (nzchar(opt$compare_list)) strsplit(opt$compare_list, ",")[[1]] else character(0)
cmp_pairs <- purrr::map(cmp_vec, ~strsplit(.x, ":", fixed=TRUE)[[1]])
if (length(cmp_pairs) && any(lengths(cmp_pairs) != 2)) stop("--compare_list 格式应为 A:B, C:D ...")

latent_vars <- if (nzchar(opt$latent_vars)) strsplit(opt$latent_vars, ",")[[1]] else NULL

# ---------------- 核心差异分析器 ----------------
run_deg_one_pair <- function(obj_in, ident_name, group_var, test_group, ctrl_group, out_base, topn=5){
  # obj_in: Seurat 对象（Idents 已按 ident_name.group 设置）
  # ident_name: 如 "celltype" 或 "class"
  message(sprintf("[DEG] %s | %s vs %s", ident_name, test_group, ctrl_group))

  # 构造 "ident.group" 作为 Idents
  obj_in[[sprintf("%s.group", ident_name)]] <- paste0(obj_in@meta.data[[ident_name]], "_", obj_in@meta.data[[group_var]])
  obj_in[[ident_name]] <- obj_in@meta.data[[ident_name]]
  Idents(obj_in) <- sprintf("%s.group", ident_name)

  ids_levels <- unique(obj_in@meta.data[[ident_name]])
  # 对每个 ident 水平做差异
  one_ident <- function(level){
    ident1 <- paste0(level, "_", test_group)
    ident2 <- paste0(level, "_", ctrl_group)
    if (sum(Idents(obj_in) == ident1) < opt$min_cells_group ||
        sum(Idents(obj_in) == ident2) < opt$min_cells_group) {
      return(NULL)
    }
    res <- tryCatch(
      FindMarkers(
        obj_in,
        ident.1 = ident1, ident.2 = ident2,
        min.cells.group = opt$min_cells_group,
        logfc.threshold = 0,       # 不先限，统一下游再滤
        only.pos = FALSE,
        test.use = opt$test_use,
        latent.vars = latent_vars
      ) %>% rownames_to_column("gene") %>% cbind(cluster = level, .),
      error = function(e) NULL
    )
    res
  }

  all_deg <- purrr::map(ids_levels, one_ident) %>% bind_rows()
  if (is.null(all_deg) || nrow(all_deg) == 0) {
    warning(sprintf("无可用结果：%s | %s vs %s", ident_name, test_group, ctrl_group))
    return(invisible(NULL))
  }

  all_deg <- std_deg_cols(all_deg) %>% arrange(cluster, p_val)
  save_tsv(all_deg, file.path(out_base, sprintf("%s_vs_%s_all_genes.tsv", test_group, ctrl_group)))

  # 过滤
  up_filt <- all_deg %>% filter(avg_log2FC >=  opt$logfc, p_val_adj <= opt$padj, pct.1 >= opt$pct)
  dn_filt <- all_deg %>% filter(avg_log2FC <= -opt$logfc, p_val_adj <= opt$padj, pct.2 >= opt$pct)
  save_tsv(up_filt, file.path(out_base, sprintf("%s_vs_%s_filter_up.tsv",   test_group, ctrl_group)))
  save_tsv(dn_filt, file.path(out_base, sprintf("%s_vs_%s_filter_down.tsv", test_group, ctrl_group)))

  # 分 cluster 取 topN
  top_up <- all_deg %>%
    group_by(cluster) %>%
    arrange(desc(avg_log2FC), p_val, .by_group=TRUE) %>%
    slice_head(n = topn) %>% ungroup()
  top_dn <- all_deg %>%
    group_by(cluster) %>%
    arrange(avg_log2FC, p_val, .by_group=TRUE) %>%
    slice_head(n = topn) %>% ungroup()
  save_tsv(top_up, file.path(out_base, sprintf("%s_vs_%s_top%d_up.tsv", test_group, ctrl_group, topn)))
  save_tsv(top_dn, file.path(out_base, sprintf("%s_vs_%s_top%d_down.tsv", test_group, ctrl_group, topn)))

  # 表达散点图（每个 ident 做一张）
  # 先限定到 test/ctrl 两组
  sub_idx <- obj_in@meta.data[[group_var]] %in% c(test_group, ctrl_group)
  obj_sub <- subset(obj_in, cells = rownames(obj_in@meta.data)[sub_idx])
  df_ae <- ae_df(obj_sub, group_var = group_var)
  if (!all(c(test_group, ctrl_group) %in% colnames(df_ae))) {
    warning("AverageExpression 未包含预期分组列，跳过散点图")
    return(invisible(list(all=all_deg, up=up_filt, down=dn_filt, top_up=top_up, top_dn=top_dn)))
  }

  expscatter_dir <- dir_create(file.path(out_base, "expscatter"))
  # 为每个 ident 画图
  purrr::walk(unique(top_up$cluster), function(level){
    genes_to_label <- unique(c(
      (top_up  %>% filter(cluster == level) %>% arrange(desc(avg_log2FC), p_val) %>% pull(gene) %>% head(topn)),
      (top_dn  %>% filter(cluster == level) %>% arrange(avg_log2FC, p_val)        %>% pull(gene) %>% head(topn))
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

# ---------------- 参数记录功能 ----------------
save_deg_parameters <- function(opt, outdir) {
  # 创建参数记录文件
  param_file <- file.path(outdir, "deg_analysis_parameters.txt")
  
  # 打开文件连接
  sink(param_file)
  
  # 写入参数头信息
  cat("单细胞差异基因分析参数记录\n")
  cat("==============================\n")
  cat("分析时间:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
  cat("脚本版本:", VERSION, "\n\n")
  
  # 基本文件参数
  cat("1. 文件参数\n")
  cat("-----------\n")
  cat("输入文件:", opt$infile, "\n")
  cat("输出目录:", outdir, "\n\n")
  
  # 分析模式参数
  cat("2. 分析模式\n")
  cat("-----------\n")
  cat("按聚类分析 (do_by_cluster):", opt$do_by_cluster, "\n")
  cat("按大类分析 (do_by_class):", opt$do_by_class, "\n")
  cat("全体细胞分析 (do_by_all):", opt$do_by_all, "\n")
  cat("聚类变量 (ident_var):", opt$ident_var, "\n")
  cat("大类变量 (class_var):", opt$class_var, "\n")
  cat("分组变量 (group_var):", opt$group_var, "\n\n")
  
  # DEG筛选阈值参数
  cat("3. 差异基因筛选阈值\n")
  cat("--------------------\n")
  cat("log2FC阈值:", opt$logfc, "\n")
  cat("最小表达比例 (pct):", opt$pct, "\n")
  cat("FDR调整P值阈值:", opt$padj, "\n")
  cat("每组最小细胞数:", opt$min_cells_group, "\n\n")
  
  # 比较列表参数
  cat("4. 比较组设置\n")
  cat("-------------\n")
  if (length(cmp_pairs) > 0) {
    for (i in seq_along(cmp_pairs)) {
      cat(sprintf("比较组 %d: %s vs %s\n", i, cmp_pairs[[i]][1], cmp_pairs[[i]][2]))
    }
  } else {
    cat("无特定比较组设置\n")
  }
  cat("\n")
  
  # 分析方法参数
  cat("5. 分析方法参数\n")
  cat("---------------\n")
  cat("默认assay:", opt$default_assay, "\n")
  cat("检验方法:", opt$test_use, "\n")
  cat("潜在变量:", ifelse(is.null(latent_vars), "无", paste(latent_vars, collapse = ", ")), "\n")
  cat("并行核数:", opt$ncpus, "\n")
  cat("内存限制(MB):", opt$max_mem_mega, "\n")
  cat("TOP N基因数:", opt$topn, "\n")
  
  # 关闭文件连接
  sink()
  
  # 同时在控制台输出信息
  message("DEG分析参数已保存至: ", param_file)
  
  return(param_file)
}

# ---------------- 在环境设置后调用参数记录 ----------------
# 在以下代码之后添加调用：
# outdir      <- dir_create(opt$outdir)
# ... 其他目录创建代码

# 添加参数记录调用
param_file <- save_deg_parameters(opt, outdir)

# ---------------- three modes ----------------
# 1) by_cluster: ident = Idents(obj) 或指定 ident_var
if (bool(opt$do_by_cluster) && length(cmp_pairs) > 0) {
  ensure_meta(obj, opt$group_var)
  # 建立“celltype”列：来自 Idents
  obj$celltype <- as.character(Idents(obj))
  for (pr in cmp_pairs){
    test_group <- pr[1]; ctrl_group <- pr[2]
    out_base <- dir_create(file.path(by_cluster_dir, sprintf("%s_vs_%s", test_group, ctrl_group)))
    invisible(run_deg_one_pair(
      obj_in = obj, ident_name = "celltype",
      group_var = opt$group_var,
      test_group = test_group, ctrl_group = ctrl_group,
      out_base = out_base, topn = opt$topn
    ))
  }
}

# 2) by_class: ident = class_var（如 customclassif）
if (bool(opt$do_by_class) && nzchar(opt$class_var) && length(cmp_pairs) > 0) {
  ensure_meta(obj, opt$class_var)
  for (pr in cmp_pairs){
    test_group <- pr[1]; ctrl_group <- pr[2]
    out_base <- dir_create(file.path(by_class_dir, sprintf("%s_vs_%s", test_group, ctrl_group)))
    # 将 ident_name 指向 class_var
    obj$class <- obj@meta.data[[opt$class_var]]
    invisible(run_deg_one_pair(
      obj_in = obj, ident_name = "class",
      group_var = opt$group_var,
      test_group = test_group, ctrl_group = ctrl_group,
      out_base = out_base, topn = opt$topn
    ))
  }
}

# 3) by_all: 全体细胞（Idents <- group），一次性比较
if (bool(opt$do_by_all) && length(cmp_pairs) > 0) {
  ensure_meta(obj, opt$group_var)
  Idents(obj) <- obj@meta.data[[opt$group_var]]
  assay_now <- DefaultAssay(obj)

  for (pr in cmp_pairs){
    test_group <- pr[1]; ctrl_group <- pr[2]
    out_base <- dir_create(file.path(by_all_dir, sprintf("%s_vs_%s", test_group, ctrl_group)))
    message(sprintf("[DEG] by_all | %s vs %s", test_group, ctrl_group))

    # FindMarkers（全体）
    if (sum(Idents(obj) == test_group, na.rm = TRUE) >= opt$min_cells_group &&
        sum(Idents(obj) == ctrl_group, na.rm = TRUE) >= opt$min_cells_group) {

      all_deg <- FindMarkers(
        obj, ident.1 = test_group, ident.2 = ctrl_group,
        min.cells.group = opt$min_cells_group,
        logfc.threshold = 0, only.pos = FALSE,
        test.use = opt$test_use, latent.vars = latent_vars
      ) %>% std_deg_cols() %>% arrange(p_val)
      save_tsv(all_deg, file.path(out_base, "all_genes.tsv"), rownames_as_col = "gene")

      up_filt <- all_deg %>% filter(avg_log2FC >=  opt$logfc, p_val_adj <= opt$padj)
      dn_filt <- all_deg %>% filter(avg_log2FC <= -opt$logfc, p_val_adj <= opt$padj)
      save_tsv(up_filt, file.path(out_base, "filter_up.tsv"),   rownames_as_col = "gene")
      save_tsv(dn_filt, file.path(out_base, "filter_down.tsv"), rownames_as_col = "gene")

      # topN（不分 cluster）
      top_up <- pick_top(all_deg, n=opt$topn, up=TRUE)
      top_dn <- pick_top(all_deg, n=opt$topn, up=FALSE)
      save_tsv(top_up, file.path(out_base, sprintf("top%d_up.tsv", opt$topn)),   rownames_as_col = "gene")
      save_tsv(top_dn, file.path(out_base, sprintf("top%d_down.tsv", opt$topn)), rownames_as_col = "gene")

      # 表达散点图（全体）
      df_ae <- ae_df(subset(obj, idents = c(test_group, ctrl_group)), group_var = opt$group_var)
      genes_to_label <- unique(c(rownames(top_up), rownames(top_dn)))
      expscatter_dir <- dir_create(file.path(out_base, "expscatter"))
      if (all(c(test_group, ctrl_group) %in% colnames(df_ae))) {
        label_genes_scatter(
          df_xy = df_ae, xcol = test_group, ycol = ctrl_group,
          genes_to_label = genes_to_label, title = "by_all",
          outfile_prefix = file.path(expscatter_dir, "by_all_top")
        )
      }
    } else {
      warning("by_all: 某组细胞数不足，跳过该比较")
    }
  }
}

# 还原 Idents
Idents(obj) <- idents_backup
message("Done.")


writeLines(capture.output(sessionInfo()), "session_info.txt")
