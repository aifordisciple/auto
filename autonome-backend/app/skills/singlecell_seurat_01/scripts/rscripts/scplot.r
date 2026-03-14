#!/usr/bin/env Rscript
# =============================================================================
# single-cell gene-visualisation – all-in-one (CNS-ready, v5.1)
# - Seurat v4/v5 兼容；Assay5 layer 自动 JoinLayers
# - 预处理阶段显式构建：celltype_group, cluster_group（用于 DotPlot）
# - 分目录输出：featureplots/ violins/ dotplots/ heatmaps/ data_tables/
# - DotPlot 的 group-by 稳健；Feature/Violin/DotPlot/Heatmap 全量导出数据表
# - Heatmap: ComplexHeatmap > pheatmap > ggplot
# =============================================================================

suppressPackageStartupMessages({
  library(optparse); library(dplyr); library(tidyr); library(purrr)
  library(ggplot2); library(patchwork); library(cowplot)
  library(Seurat);  library(scCustomize); library(stringr)
  library(future);  library(future.apply); library(Matrix)
  library(tidyverse)
})

VERSION <- "5.1-CNS"

# ----------------------------- CLI -------------------------------------------
option_list <- list(
  make_option(c("-f","--infile"),        type="character", help="Seurat *.rds"),
  make_option(c("-a","--defaultassay"),  type="character", default="RNA"),
  make_option(c("-c", "--clusterby"),type = "character", default = "customclassif",
              help = "DotPlot 分组字段 [默认: %default]"),
  make_option(c("-s","--splitby"),       type="character", default="group"),
  make_option(c("-g","--genelist"),      type="character", default=""),
  make_option(c("-m","--genelistfile"),  type="character", default=""),
  make_option(c("--genelistcol"),        type="integer",  default=1),
  make_option(c("-l","--listname"),      type="character", default="",
              help="group 顺序，逗号分隔（如 TN,RD,PD）"),
  make_option(c("-t","--plottype"),      type="character", default="all",
              help="all|feature|vlnplot|dotplot|heatmap"),
  make_option(c("--umap_reduction"),     type="character", default="umap"),
  make_option(c("--outdir"),             type="character", default="./"),
  make_option(c("-n","--ncpus"),         type="integer",  default=4),
  make_option(c("--MaxMemMega"),         type="integer",  default=100000),
  make_option(c("--hc_rows"), type="logical",  default=TRUE,
            help="Heatmap 按行聚类 TRUE/FALSE [默认: %default]"),
  make_option(c("--hc_cols"), type="logical",  default=FALSE,
              help="Heatmap 按列聚类 TRUE/FALSE [默认: %default]"),

  # >>> 新增：DotPlot 连续配色 <<<
  make_option(c("--dotcolors"), type="character", default="greyblue",
              help="DotPlot 连续配色：greyred|greyblue|greypurple [默认: %default]"),

  make_option(c("-v","--version"),       action="store_true", default=FALSE)
)

opt <- parse_args(OptionParser(option_list = option_list))
if (opt$version) { cat("Version:", VERSION, "\n"); quit(save="no") }
if (is.null(opt$infile) || !file.exists(opt$infile)) stop("请提供有效的 --infile *.rds")

# ----------------------------- Utils -----------------------------------------
msg  <- function(...) cat("[", format(Sys.time(), "%H:%M:%S"), "] ", sprintf(...), "\n", sep="")
halt <- function(...) stop(sprintf(...))

theme_cns <- function(base=13){
  theme_classic(base_size = base) +
    theme(
      axis.title  = element_text(face="bold"),
      axis.text   = element_text(color="#222"),
      axis.line   = element_line(linewidth = 0.4),
      axis.ticks  = element_line(linewidth = 0.3),
      legend.position = "top",
      legend.title    = element_blank(),
      legend.key      = element_rect(fill="white", colour="white"),
      legend.key.size = unit(0.5, "cm"),
      axis.text.x= element_text(vjust = 1,hjust = 1, angle = 45),
      plot.title      = element_text(face="bold", hjust=0),
      plot.subtitle   = element_text(color="#666"),
      plot.margin     = margin(6, 10, 6, 10)
    )
}
theme_set(theme_cns())

save_plot_both <- function(filename_base, p, w=7, h=5, dpi=300){
  dir.create(dirname(filename_base), recursive = TRUE, showWarnings = FALSE)
  ggplot2::ggsave(paste0(filename_base,".pdf"), p, width=w, height=h, limitsize = FALSE)
  ggplot2::ggsave(paste0(filename_base,".png"), p, width=w, height=h, dpi=dpi, limitsize = FALSE)
}

# ----------------------------- 并行 ------------------------------------------
if (opt$ncpus <= 1) plan(sequential) else plan(multisession, workers = opt$ncpus)
options(future.globals.maxSize = opt$MaxMemMega * 1024^2 * 1.1)

# ----------------------------- 读取/瘦身 --------------------------------------
msg("Loading rds: %s", opt$infile)
obj <- readRDS(opt$infile)
DefaultAssay(obj) <- opt$defaultassay

# v5: 多层合并
if (inherits(obj[[opt$defaultassay]], "Assay5")) {
  try({
    if (length(Layers(obj[[opt$defaultassay]])) > 1) {
      obj[[opt$defaultassay]] <- JoinLayers(obj[[opt$defaultassay]])
      msg("Assay `%s` layers joined.", opt$defaultassay)
    }
  }, silent = TRUE)
}

# 保留必要降维
keep_reds <- intersect(c("umap","tsne"), names(obj@reductions))
obj <- DietSeurat(
  obj,
  assays = opt$defaultassay,
  counts = TRUE, data = TRUE, scale.data = FALSE,
  dimreducs = keep_reds, graphs = FALSE, misc = FALSE
)

idents_backup <- Idents(obj)

# ----------------------------- 基因列表 --------------------------------------
genes <- character(0)
if (nzchar(opt$genelist)) genes <- c(genes, strsplit(opt$genelist, ",")[[1]] |> trimws())
if (nzchar(opt$genelistfile)) {
  glf <- read.table(opt$genelistfile, header = FALSE, sep = "\t", quote = "", comment.char = "",
                    check.names = FALSE, stringsAsFactors = FALSE)
  if (ncol(glf) < opt$genelistcol) halt("`--genelistcol` 超出文件列数")
  genes <- c(genes, as.character(glf[[opt$genelistcol]]))
}
genes <- unique(genes)
valid_genes   <- intersect(genes, rownames(obj))
missing_genes <- setdiff(genes, rownames(obj))
cat(">> 有效基因: ", length(valid_genes), "/", length(genes), "\n", sep = "")
if (length(missing_genes)) cat(">> 缺失基因(≤30): ", paste(head(missing_genes,30), collapse=", "), "\n", sep="")
if (length(valid_genes) == 0) halt("没有可用基因。")

# ----------------------------- 分组层次 & 组合列（关键） ----------------------
# 1) group 列
if (!opt$splitby %in% colnames(obj@meta.data)) {
  halt("meta.data 不含分组列 `%s`，请用 --splitby 指定正确列名。", opt$splitby)
}

# 设置分组列为 Idents 前，先清洗 NA/空值
id_vals <- as.character(obj@meta.data[[opt$splitby]])
# 处理 NA / "NA" / 空字符串
id_vals[is.na(id_vals) | id_vals == "NA" | trimws(id_vals) == ""] <- "unknown"
# 写回 meta 并设置为因子/ident
obj@meta.data[[opt$splitby]] <- id_vals

grp_vec <- obj@meta.data[[opt$splitby]]

if (!is.factor(grp_vec)) grp_vec <- factor(grp_vec)
if (nzchar(opt$listname)) {
  user_lv <- strsplit(opt$listname, ",")[[1]] |> trimws() |> unique()
  if (!"unknown" %in% user_lv) user_lv <- c(user_lv, "unknown")
  grp_vec <- factor(as.character(grp_vec), levels = user_lv)
}
obj$.__grp__ <- grp_vec
group_levels <- levels(obj$.__grp__)
group_n <- length(group_levels)

# 2) 显式构建 celltype_group, cluster_group（用 [[<- 写入 meta.data）
if (opt$clusterby %in% colnames(obj@meta.data)) {
  obj[["celltype_group"]] <- paste0(as.character(obj@meta.data %>% pull(opt$clusterby)), "_", as.character(obj$.__grp__))
  # 只保留实际出现的组合，并按 celltype 内部按 group_levels 排序
  ct_lv <- unique(as.character(obj@meta.data %>% pull(opt$clusterby)))
  present <- unique(obj$celltype_group)
  ordered <- unlist(lapply(ct_lv, function(ct) paste0(ct, "_", group_levels)))
  ordered <- intersect(ordered, present)
  obj$celltype_group <- factor(obj$celltype_group, levels = ordered)
} else {
  msg(paste0("提示：无 `", opt$clusterby,"`，无法构建 celltype_group。"))
}

if ("seurat_clusters" %in% colnames(obj@meta.data) || length(levels(Idents(obj)))>0) {
  # 优先从 meta.data 取 seurat_clusters；否则用 Idents
  clus <- if ("seurat_clusters" %in% colnames(obj@meta.data)) obj$seurat_clusters else as.character(Idents(obj))
  obj[["cluster_group"]] <- paste0(as.character(clus), "_", as.character(obj$.__grp__))
  # 排序：按 cluster(字符序) × group_levels
  cl_lv <- sort(unique(as.character(clus)))
  present <- unique(obj$cluster_group)
  ordered <- unlist(lapply(cl_lv, function(k) paste0(k, "_", group_levels)))
  ordered <- intersect(ordered, present)
  obj$cluster_group <- factor(obj$cluster_group, levels = ordered)
} else {
  msg("提示：未检测到 `seurat_clusters`/Idents，无法构建 cluster_group。")
}

# >>> 新增：DotPlot 连续配色选择器 <<<
get_dot_colors <- function(mode = c("greyred","greyblue","greypurple","viridis")) {
  mode <- match.arg(mode)
  if (mode == "greyred") {
    # 灰 -> 红（三段式更平滑）
    return(c("#E5E5E5", "#FB6A4A"))
  } else if (mode == "greyblue") {
    # 灰 -> 蓝
    return(c("#E5E5E5", "#0f0fdfff"))
  } else if (mode == "greypurple") {
    # 灰 -> 蓝
    return(c("#E5E5E5", "#E5E5E5", "#b2b1b1ff", "#7324e1ff", "#7324e1ff"))
  } else {
    # 兜底（若未来扩展）
    if (exists("viridis_plasma_dark_high")) return(viridis_plasma_dark_high)
    return(c("#E5E5E5", "#0f0fdfff"))
  }
}

# ----------------------------- 目录 ------------------------------------------
OUT <- normalizePath(opt$outdir, mustWork = FALSE)
dirs <- list(
  feature = file.path(OUT, "featureplots"),
  violin  = file.path(OUT, "violins"),
  dot     = file.path(OUT, "dotplots"),
  heatmap = file.path(OUT, "heatmaps"),
  data    = file.path(OUT, "data_tables")
)
invisible(lapply(dirs, function(d) dir.create(d, recursive = TRUE, showWarnings = FALSE)))

# ----------------------------- 工具函数 --------------------------------------
get_expr_mat <- function(obj, genes, assay=opt$defaultassay){
  m <- tryCatch(GetAssayData(obj, assay=assay, layer="data"), error = function(e) NULL)
  if (is.null(m)) m <- GetAssayData(obj, assay=assay, slot="data")
  genes <- intersect(genes, rownames(m))
  m[genes, , drop=FALSE]
}
row_means_by_group <- function(mat, groups){
  groups <- droplevels(as.factor(groups))
  lv <- levels(groups)
  out <- sapply(lv, function(g){
    idx <- which(groups == g)
    if (length(idx) == 0) return(rep(NA_real_, nrow(mat)))
    if (inherits(mat, "dgCMatrix")) Matrix::rowMeans(mat[, idx, drop=FALSE])
    else rowMeans(as.matrix(mat[, idx, drop=FALSE]))
  })
  if (is.vector(out)) out <- matrix(out, ncol=1, dimnames=list(rownames(mat), lv))
  rownames(out) <- rownames(mat); colnames(out) <- lv
  out
}
row_zscore <- function(m){
  z <- t(scale(t(as.matrix(m))))
  z[is.na(z)] <- 0
  z
}

# Heatmap 后端
.has_CH  <- requireNamespace("ComplexHeatmap", quietly = TRUE) &&
            requireNamespace("circlize",       quietly = TRUE)
.has_pHT <- requireNamespace("pheatmap",       quietly = TRUE)

save_heatmap_both <- function(filename_base, draw_fun, width=7.5, height=6.5, dpi=300){
  dir.create(dirname(filename_base), recursive = TRUE, showWarnings = FALSE)
  grDevices::pdf(paste0(filename_base, ".pdf"), width=width, height=height); draw_fun(); grDevices::dev.off()
  grDevices::png(paste0(filename_base, ".png"), width=width, height=height, units="in", res=dpi); draw_fun(); grDevices::dev.off()
}

plot_heatmap_generic <- function(avg_mat, z_mat, title, filename_stub,
                                 col_fun=NULL,
                                 cluster_rows=TRUE, cluster_cols=TRUE){

  # 数据表
  write.table(avg_mat, file=file.path(dirs$data, paste0(filename_stub, ".avg.xls")),
              sep="\t", quote=FALSE, col.names=NA)
  write.table(z_mat,   file=file.path(dirs$data, paste0(filename_stub, ".zscore.xls")),
              sep="\t", quote=FALSE, col.names=NA)
  # 颜色
  if (is.null(col_fun)) {
    blue_red_dark = colorRampPalette(c("#08519c", "#08519c", "#3182bd", "#ffffff", "#e6550d", "#a63603", "#a63603"))(500)

    # if (.has_CH) col_fun <- circlize::colorRamp2(c(-2, 0, 2), c("#2E7EBB","#F7F7F7","#D94C3D"))
    # else         col_fun <- colorRampPalette(c("#2E7EBB","#F7F7F7","#D94C3D"))(100)
    col_fun <- blue_red_dark
  }
  # 自适应尺寸
  W <- max(6.5, 0.28 * ncol(z_mat) + 3)
  H <- max(6.0, 0.24 * nrow(z_mat) + 2.2)

  if (.has_CH) {
    hm <- ComplexHeatmap::Heatmap(
      z_mat, name="row-z", col=col_fun,
      cluster_rows = cluster_rows,
      cluster_columns = cluster_cols,
      show_row_names=TRUE, show_column_names=TRUE,
      row_names_gp=grid::gpar(fontsize=8), column_names_gp=grid::gpar(fontsize=9),
      column_title=title, column_title_gp=grid::gpar(fontface="bold"),
      heatmap_legend_param=list(legend_height=unit(3,"cm"))
    )
    save_heatmap_both(file.path(dirs$heatmap, filename_stub),
                      function(){ ComplexHeatmap::draw(hm, heatmap_legend_side="right") },
                      width=W, height=H)
  } else if (.has_pHT) {
    save_heatmap_both(file.path(dirs$heatmap, filename_stub),
      function(){
        pheatmap::pheatmap(
          z_mat, color=col_fun,
          cluster_rows = cluster_rows,
          cluster_cols = cluster_cols,
          border_color=NA, main=title, show_rownames=TRUE, show_colnames=TRUE,
          fontsize_row=8, fontsize_col=9
        )
      },
      width=W, height=H)

  } else {
    z_plot <- z_mat
    # 手动重排：仅当对应开关为 TRUE 时进行
    if (cluster_rows) {
      rz <- stats::hclust(stats::dist(z_plot, method = "euclidean"), method = "complete")
      z_plot <- z_plot[stats::order.dendrogram(as.dendrogram(rz)), , drop=FALSE]
    }
    if (cluster_cols) {
      cz <- stats::hclust(stats::dist(t(z_plot), method = "euclidean"), method = "complete")
      z_plot <- z_plot[, stats::order.dendrogram(as.dendrogram(cz)), drop=FALSE]
    }

    df <- as.data.frame(z_plot) |>
      tibble::rownames_to_column("gene") |>
      tidyr::pivot_longer(-gene, names_to="group", values_to="z")

    p <- ggplot(df, aes(group, gene, fill=z)) +
      geom_tile() +
      scale_fill_gradient2(low="#2E7EBB", mid="#F7F7F7", high="#D94C3D", midpoint=0, name="row-z") +
      labs(title=title, x=NULL, y=NULL) + theme_cns() +
      theme(axis.text.x = element_text(angle=45, hjust=1, vjust=1),
            axis.text.y = element_text(size=8))

    # 尺寸随重排后矩阵大小自适应
    W <- max(6.5, 0.28 * ncol(z_plot) + 3)
    H <- max(6.0, 0.24 * nrow(z_plot) + 2.2)
    save_plot_both(file.path(dirs$heatmap, filename_stub), p, w = W, h = H)
  }

}

# ===== 新增：通用分组聚合（支持单列或多列组合） =====
get_levels_safe <- function(colname){
  if (!colname %in% colnames(obj@meta.data)) return(NULL)
  x <- obj@meta.data[[colname]]
  if (is.factor(x)) levels(x) else sort(unique(as.character(x)))
}
# 生成“期望顺序”的组合标签（只保留实际出现的组合）
expected_combo_levels <- function(vars, sep="_"){
  lv_list <- lapply(vars, function(v){
    if (v == ".__grp__") return(group_levels)
    get_levels_safe(v)
  })
  if (any(vapply(lv_list, is.null, logical(1)))) return(NULL)
  if (length(vars) == 1) return(lv_list[[1]])
  df <- do.call(expand.grid, c(rev(lv_list), stringsAsFactors = FALSE)) # 反序生成再反拼，避免 expand.grid 的列优先顺序与直觉相反
  lv <- apply(df[, rev(seq_along(vars)), drop=FALSE], 1, function(x) paste(x, collapse=sep))
  unique(as.character(lv))
}
# expr：基因×细胞，vars：meta 中用于分组的列名向量
avg_by_vars <- function(expr, vars, tag, title){
  # 组合向量
  sep <- "_"
  if (!all(vars %in% colnames(obj@meta.data))) {
    msg("Heatmap 跳过 %s：缺少列 %s", tag, paste(setdiff(vars, colnames(obj@meta.data)), collapse=", "))
    return(invisible())
  }
  present_combo <- apply(obj@meta.data[, vars, drop=FALSE], 1, function(x) paste(as.character(x), collapse=sep))
  expected <- expected_combo_levels(vars, sep=sep)
  if (is.null(expected)) {
    msg("Heatmap 跳过 %s：分组水平解析失败", tag); return(invisible())
  }
  # 仅保留确实出现的组合，且按“期望顺序”排列
  present <- unique(present_combo)
  wanted  <- intersect(expected, present)
  if (length(wanted) == 0) { msg("Heatmap 跳过 %s：无有效组合", tag); return(invisible()) }
  grp <- factor(present_combo, levels = wanted)

  avg <- row_means_by_group(expr, grp)
  avg <- avg[valid_genes, , drop=FALSE]
  z   <- row_zscore(avg)
  plot_heatmap_generic(avg, z, title = title,
                     filename_stub = paste0("heatmap_gene_by_", tag),
                     col_fun = NULL,
                     cluster_rows = opt$hc_rows,
                     cluster_cols = opt$hc_cols)

}

# ----------------------------- 绘图函数 --------------------------------------
plot_feature_per_gene <- function(gene, reduction="umap"){
  if (!reduction %in% names(obj@reductions)) return(NULL)

  # 分组小面板
  p_split <- scCustomize::FeaturePlot_scCustom(
    obj,
    reduction = reduction,
    features  = gene,
    split.by  = ".__grp__",
    order     = FALSE,
    alpha_exp=0.75,alpha_na_exp=0.75,
    raster    = FALSE
  ) + patchwork::plot_layout(guides = "collect")
  p_split <- p_split & theme(strip.text = element_text(face="bold", size=12),
                             legend.position = "right") & guides(fill = "none")

  save_plot_both(
    file.path(dirs$feature, sprintf("featureplot_%s_bygroup_%s", reduction, gene)),
    p_split,
    w = max(5, length(levels(obj$.__grp__)) * 3.6), h = 3.8
  )

  # 不分组
  p_one <- scCustomize::FeaturePlot_scCustom(
    obj, reduction = reduction, features = gene,
    order = FALSE, num_columns = 1, raster = FALSE
  ) & guides(fill = "none") & theme(legend.position = "right")

  save_plot_both(
    file.path(dirs$feature, sprintf("featureplot_%s_%s", reduction, gene)),
    p_one, w = 5, h = 4
  )

  # 导出数据
  df <- FetchData(obj, vars = c(gene, ".__grp__", paste0(reduction,"_1"), paste0(reduction,"_2")))
  colnames(df) <- c("expr","group","dim1","dim2")
  write.table(df, file = file.path(dirs$data, sprintf("%s.featureplot_%s.data.xls", gene, reduction)),
              sep = "\t", quote = FALSE, row.names = FALSE)
  invisible(TRUE)
}

plot_vln_per_gene <- function(gene){
  # by cluster
  p_list <- scCustomize::VlnPlot_scCustom(obj, features=gene, split.by=".__grp__", group.by="seurat_clusters", pt.size=0)
  p <- wrap_plots(plots=p_list, ncol=1) + theme_cns()
  save_plot_both(file.path(dirs$violin, sprintf("vln_%s_bycluster", gene)),
                 p, w=max(7, length(levels(Idents(obj)))*1.0), h=4.2)
  # by celltype
  if (opt$clusterby %in% colnames(obj@meta.data)) {
    p_list2 <- scCustomize::VlnPlot_scCustom(obj, features=gene, split.by=".__grp__", group.by=opt$clusterby, pt.size=0)
    p2 <- wrap_plots(plots=p_list2, ncol=1) + theme_cns()
    save_plot_both(file.path(dirs$violin, sprintf("vln_%s_bycelltype", gene)),
                   p2, w=max(7, length(unique(obj@meta.data %>% pull(opt$clusterby)))*1.2), h=4.2)
  }
  # by group
  p_list3 <- scCustomize::VlnPlot_scCustom(obj, features=gene, group.by=".__grp__", pt.size=0)
  p3 <- wrap_plots(plots=p_list3, ncol=1) + theme_cns()
  save_plot_both(file.path(dirs$violin, sprintf("vln_%s_bygroup", gene)),
                 p3, w=max(6.5, length(levels(obj$.__grp__))*1.2), h=4.2)
  # data
  df <- FetchData(obj, vars=c(gene, "seurat_clusters", opt$clusterby, ".__grp__"))
  colnames(df) <- c("expr","cluster","celltype","group")
  write.table(df, file=file.path(dirs$data, sprintf("%s.vln.data.xls", gene)),
              sep="\t", quote=FALSE, row.names=FALSE)
  invisible(TRUE)
}

dotplot_save <- function(idents_col, gene_vec, filename_stub, rotate_x=TRUE, flip_axes=FALSE){
  if (!(idents_col %in% colnames(obj@meta.data)) && idents_col != "seurat_clusters") {
    msg("跳过 %s：meta.data 中不存在该列", idents_col); return(invisible(FALSE))
  }
  if (idents_col == "seurat_clusters") {
    Idents(obj) <- "seurat_clusters"
  } else {
    Idents(obj) <- factor(obj@meta.data[[idents_col]])
  }

  # >>> 新增：根据参数获取颜色向量 <<<
  dot_cols <- tryCatch(get_dot_colors(opt$dotcolors), error = function(e) c("#E5E5E5","#2B8CBE"))

  p <- tryCatch({
      scCustomize::DotPlot_scCustom(
        seurat_object = obj, features = unique(gene_vec),
        flip_axes = flip_axes, x_lab_rotate = rotate_x,
        colors_use = dot_cols
      ) + theme_cns()
    }, error = function(e){
      msg("DotPlot_scCustom 失败，降级 Seurat::DotPlot：%s", e$message)
      Seurat::DotPlot(obj, features = unique(gene_vec), group.by = idents_col) +
        # >>> 覆盖默认渐变 <<< 
        scale_color_gradientn(colors = dot_cols) +
        theme_cns()
    })

  nx <- length(unique(gene_vec)); ny <- nlevels(Idents(obj))
  if (flip_axes) { szw <- max(6.5, 0.35*ny + 4); szh <- max(4.8, 0.25*nx + 4) }
  else           { szw <- max(6.5, 0.35*nx + 4); szh <- max(4.8, 0.25*ny + 4) }
  save_plot_both(file.path(dirs$dot, filename_stub), p, w=szw, h=szh)

  dp <- Seurat::DotPlot(obj, features = unique(gene_vec), group.by = idents_col)$data
  write.table(dp, file=file.path(dirs$data, paste0(filename_stub, ".data.xls")),
              sep="\t", quote=FALSE, row.names=FALSE)
  invisible(TRUE)
}


# ----------------------------- 调度 ------------------------------------------
do_feature <- function(){
  red <- if (opt$umap_reduction %in% names(obj@reductions)) opt$umap_reduction
         else if (length(names(obj@reductions))) names(obj@reductions)[1]
         else NA_character_
  if (is.na(red)) { msg("没有找到降维，跳过 FeaturePlot"); return(invisible()) }
  msg("FeaturePlot 使用降维：%s", red)
  invisible(future_lapply(valid_genes, plot_feature_per_gene, reduction=red))
}
do_vln <- function(){
  Idents(obj) <- idents_backup
  invisible(future_lapply(valid_genes, plot_vln_per_gene))
}
do_dot <- function(){
  # celltype & celltype×group
  if (opt$clusterby %in% colnames(obj@meta.data)) {
    dotplot_save(opt$clusterby,     valid_genes, "Dotplot_bycelltype",            TRUE, FALSE)
    dotplot_save(opt$clusterby,     valid_genes, "Dotplot_bycelltype_flip",       TRUE, TRUE)
    dotplot_save("celltype_group",    valid_genes, "Dotplot_bycelltype_group",      TRUE, FALSE)
    dotplot_save("celltype_group",    valid_genes, "Dotplot_bycelltype_group_flip", TRUE, TRUE)
  } else msg(paste0("提示：无 ", opt$clusterby, "，跳过 celltype 相关 dot 图。"))

  # group
  dotplot_save(".__grp__", valid_genes, "Dotplot_bygroup", TRUE, FALSE)
  dotplot_save(".__grp__", valid_genes, "Dotplot_bygroup_flip", TRUE, TRUE)

  # replicate
  if ("replicate" %in% colnames(obj@meta.data)) {
    dotplot_save("replicate", valid_genes, "Dotplot_byreplicate", TRUE, FALSE)
    dotplot_save("replicate", valid_genes, "Dotplot_byreplicate_flip", TRUE, TRUE)
  } else msg("提示：无 replicate，跳过 replicate 相关 dot 图。")

  # cluster & cluster×group
  dotplot_save("seurat_clusters", valid_genes, "Dotplot_bycluster", TRUE, FALSE)
  dotplot_save("cluster_group",   valid_genes, "Dotplot_bycluster_group", TRUE, FALSE)
  dotplot_save("cluster_group",   valid_genes, "Dotplot_bycluster_group_flip", TRUE, TRUE)
}

# ====== 扩展的 Heatmap（按 celltype / cluster / group / replicate 及其组合）======
do_heatmap <- function(){
  DefaultAssay(obj) <- opt$defaultassay
  expr <- get_expr_mat(obj, valid_genes)
  if (nrow(expr) == 0) { msg("Heatmap: 无有效基因矩阵，跳过"); return(invisible()) }

  # 单一分组
  if (opt$clusterby %in% colnames(obj@meta.data))
    avg_by_vars(expr, c(opt$clusterby), "celltype", "Genes × Celltype (row-z)")
  else msg(paste0("提示：无 ", opt$clusterby, "，跳过 gene×celltype 热图。"))

  if ("seurat_clusters" %in% colnames(obj@meta.data)) {
    avg_by_vars(expr, c("seurat_clusters"), "cluster", "Genes × Cluster (row-z)")
  } else if (length(levels(Idents(obj)))>0) {
    obj$.__cluster__ <- as.character(Idents(obj))
    avg_by_vars(expr, c(".__cluster__"), "cluster", "Genes × Cluster (row-z)")
  } else {
    msg("提示：无 seurat_clusters/Idents，跳过 gene×cluster 热图。")
  }

  avg_by_vars(expr, c(".__grp__"), "group", "Genes × Group (row-z)")

  if ("replicate" %in% colnames(obj@meta.data))
    avg_by_vars(expr, c("replicate"), "replicate", "Genes × Replicate (row-z)")
  else msg("提示：无 replicate，跳过 gene×replicate 热图。")

  # 组合分组（× group）
  if (opt$clusterby %in% colnames(obj@meta.data))
    avg_by_vars(expr, c(opt$clusterby,".__grp__"), "celltype_group", "Genes × (Celltype × Group) (row-z)")
  if ("seurat_clusters" %in% colnames(obj@meta.data))
    avg_by_vars(expr, c("seurat_clusters",".__grp__"), "cluster_group",  "Genes × (Cluster × Group) (row-z)")
  else if (exists(".__cluster__", where=obj@meta.data, inherits=FALSE))
    avg_by_vars(expr, c(".__cluster__",".__grp__"), "cluster_group",  "Genes × (Cluster × Group) (row-z)")

  # 组合分组（× replicate）
  if ("replicate" %in% colnames(obj@meta.data)) {
    if (opt$clusterby %in% colnames(obj@meta.data))
      avg_by_vars(expr, c(opt$clusterby, "replicate"), "celltype_replicate", "Genes × (Celltype × Replicate) (row-z)")
    if ("seurat_clusters" %in% colnames(obj@meta.data))
      avg_by_vars(expr, c("seurat_clusters","replicate"), "cluster_replicate",  "Genes × (Cluster × Replicate) (row-z)")
    else if (exists(".__cluster__", where=obj@meta.data, inherits=FALSE))
      avg_by_vars(expr, c(".__cluster__","replicate"), "cluster_replicate",  "Genes × (Cluster × Replicate) (row-z)")

    # （可选）Group × Replicate
    avg_by_vars(expr, c(".__grp__","replicate"), "group_replicate", "Genes × (Group × Replicate) (row-z)")
  }
}

# ----------------------------- 入口 ------------------------------------------
msg("Assay=%s | splitby=%s | #genes=%d", opt$defaultassay, opt$splitby, length(valid_genes))
msg("Groups: %s", paste(group_levels, collapse=", "))

ptype <- tolower(opt$plottype)
if (ptype %in% c("all","feature"))  do_feature()
if (ptype %in% c("all","vlnplot"))  do_vln()
if (ptype %in% c("all","dotplot"))  do_dot()
if (ptype %in% c("all","heatmap"))  do_heatmap()

# 恢复 Idents & 保存瘦身对象
Idents(obj) <- idents_backup
dir.create(OUT, recursive=TRUE, showWarnings = FALSE)
# saveRDS(obj, file=file.path(OUT,"genes_analysis.slim.rds"))
msg("DONE.")
