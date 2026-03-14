#!/usr/bin/env Rscript
# """
# Seurat v5 下游聚类与可视化（支持 integrated / IntegrateLayers / Harmony / SCT 工作流）。

# 功能要点
# - 输入：上游已完成预处理/整合的 Seurat RDS（可能包含 layers、integrated assay、integrated.* reduction、harmony reduction、SCT assay）
# - 自动选择用于聚类的降维：优先 integrated.*（Seurat v5 IntegrateLayers 输出），其次 harmony，其次 pca
# - 支持：keep/rm cluster、cellanno 映射生成 customclassif、ScType 注释、导出 counts/data（按需 JoinLayers）
# - 输出：UMAP/tSNE 分组图、clustree、Clusters.xls、meta.xls、session_info 与参数记录、最终 cells_analysis.rds

# 用法示例：
# Rscript sc_downstream_cluster_v5.r \
#   --infile sc_preprocessing.rds \
#   --outdir ./downstream \
#   --default_assay integrated \
#   --dims_use 30 --npcs 50 --cluster_resolution 0.6 \
#   --skip_tsne false --skip_marker false --skip_anno false --export false \
#   --join_layers_before_export true --join_layers_before_save true \
#   --ncpus 8 --max_mem_gb 160
# """

suppressPackageStartupMessages({
  library(optparse)
  library(futile.logger)
  library(Seurat)
  library(ggplot2)
  library(patchwork)
  library(dplyr)
  library(data.table)
  library(clustree)
  library(future)
  library(future.apply)
  library(doParallel)
})

options(stringsAsFactors = FALSE)
VERSION <- "3.2.0"

# -------------------------
# CLI
# -------------------------

option_list <- list(
  make_option(c("--version"), action = "store_true", default = FALSE,
              help = "print version and exit"),

  make_option(c("-n", "--ncpus"), type = "integer", default = 4,
              help = "CPU cores"),
  make_option(c("--max_mem_gb"), type = "double", default = 360,
              help = "future.globals.maxSize (GB)"),

  make_option(c("-i", "--infile"), type = "character", default = NA,
              help = "input RDS (object already preprocessed/integrated)"),
  make_option(c("-r", "--rdsfile"), type = "character", default = "",
              help = "optional: overrides --infile"),

  make_option(c("--outdir"), type = "character", default = "./",
              help = "output directory"),
  make_option(c("--out_prefix"), type = "character", default = "cells_analysis",
              help = "output prefix"),

  make_option(c("-a", "--default_assay"), type = "character", default = "integrated",
              help = "integrated|SCT|RNA"),

  make_option(c("-d", "--dims_use"), type = "integer", default = 25,
              help = "dims for neighbors/UMAP/tSNE"),
  make_option(c("--npcs"), type = "integer", default = 50,
              help = "npcs for PCA if needed"),
  make_option(c("--cluster_resolution"), type = "double", default = 0.6,
              help = "final clustering resolution"),

  make_option(c("--resolution_scan_min"), type = "double", default = 0.1,
              help = "clustree scan min"),
  make_option(c("--resolution_scan_max"), type = "double", default = 1.5,
              help = "clustree scan max"),
  make_option(c("--resolution_scan_step"), type = "double", default = 0.1,
              help = "clustree scan step"),

  make_option(c("--skip_tsne"), type = "character", default = "false",
              help = "true|false"),
  make_option(c("--skip_marker"), type = "character", default = "false",
              help = "true|false"),
  make_option(c("--skip_anno"), type = "character", default = "false",
              help = "true|false"),
  make_option(c("--export"), type = "character", default = "false",
              help = "true|false export RNA counts/data"),
  make_option(c("--noparallel"), type = "character", default = "true",
              help = "true|false"),

  make_option(c("--seed"), type = "integer", default = 12345,
              help = "random seed"),

  make_option(c("--cellanno"), type = "character", default = "",
              help = "cluster-to-celltype mapping (>=2 cols: cluster, celltype)"),
  make_option(c("--rmcluster"), type = "character", default = "",
              help = "comma list of clusters to remove"),
  make_option(c("--keeps"), type = "character", default = "",
              help = "comma list of clusters to keep"),

  make_option(c("--metafile"), type = "character", default = "meta.xls",
              help = "meta data output"),

  make_option(c("--toolsdir"), type = "character",
              default = "/Users/chengchao/biosource/besaltpipe/src/SingleCell/",
              help = "optional tools folder for external scripts"),

  make_option(c("-t", "--tissue"), type = "character", default = "Immune system",
              help = "tissue for ScType DB"),
  make_option(c("--sctypedb"), type = "character",
              default = "/opt/data1/public/database/singlecell/sctype_marker_db.xlsx",
              help = "ScType DB xlsx"),

  make_option(c("--join_layers_before_export"), type = "character", default = "true",
              help = "true|false: JoinLayers(RNA) before export"),
  make_option(c("--join_layers_before_save"), type = "character", default = "true",
              help = "true|false: JoinLayers(RNA) before save")
)

rewrite_argv_aliases <- function(argv) {
  # 旧参数 => 新参数（只保留一个标准长参数名）
  alias_map <- c(
    "--MaxMemMega"    = "--max_mem_gb",
    "--defaultassay"  = "--default_assay",
    "--dims"          = "--dims_use",
    "--resolution"    = "--cluster_resolution",
    "--skiptsne"      = "--skip_tsne",
    "--skipmarker"    = "--skip_marker",
    "--skipanno"      = "--skip_anno"
  )

  for (old in names(alias_map)) {
    new <- unname(alias_map[[old]])

    # 处理 --old=value
    hit_eq <- startsWith(argv, paste0(old, "="))
    argv[hit_eq] <- sub(paste0("^", gsub("([\\-\\[\\]\\^\\$\\.|\\?\\*\\+\\(\\)\\\\])", "\\\\\\1", old), "="),
                        paste0(new, "="),
                        argv[hit_eq])

    # 处理 --old value
    hit_tok <- which(argv == old)
    if (length(hit_tok) > 0) {
      argv[hit_tok] <- new
    }
  }

  argv
}

argv <- rewrite_argv_aliases(commandArgs(trailingOnly = TRUE))
opt <- parse_args(OptionParser(option_list = option_list), args = argv)

# opt <- parse_args(OptionParser(option_list = option_list))
if (opt$version) {
  message("Version: ", VERSION)
  quit(save = "no", status = 0, runLast = FALSE)
}

# -------------------------
# helpers
# -------------------------
to_bool <- function(x) tolower(as.character(x)) %in% c("true", "t", "1", "yes", "y")
nzchar_ <- function(x) !is.null(x) && !is.na(x) && nchar(as.character(x)) > 0
dir_create <- function(p) {
  if (!dir.exists(p)) dir.create(p, recursive = TRUE)
  normalizePath(p)
}

safe_join_layers <- function(obj, assay = "RNA") {
  if (!assay %in% names(obj@assays)) return(obj)
  try({
    if (length(Layers(obj[[assay]])) > 1) {
      obj[[assay]] <- JoinLayers(obj[[assay]])
      flog.info("JoinLayers applied on assay=%s", assay)
    }
  }, silent = TRUE)
  obj
}

safe_default_assay <- function(obj, wanted) {
  if (wanted %in% names(obj@assays)) {
    DefaultAssay(obj) <- wanted
    return(obj)
  }
  if ("RNA" %in% names(obj@assays)) {
    DefaultAssay(obj) <- "RNA"
    flog.warn("default assay '%s' not found; fallback to 'RNA'", wanted)
    return(obj)
  }
  stop("No suitable assay found in object.")
}

pick_integration_reduction <- function(obj) {
  reds <- names(obj@reductions)
  # Seurat v5 IntegrateLayers typically returns integrated.rpca / integrated.cca / integrated.jointpca / integrated.harmony
  if ("harmony" %in% reds) return("harmony")
  integrated_like <- grep("^integrated\\.", reds, value = TRUE)
  if (length(integrated_like) > 0) {
    # prefer rpca > cca > others (经验优先级，实际以存在为准)
    if ("integrated.rpca" %in% integrated_like) return("integrated.rpca")
    if ("integrated.cca" %in% integrated_like) return("integrated.cca")
    return(integrated_like[1])
  }
  if ("pca" %in% reds) return("pca")
  return(NA_character_)
}

ensure_pca <- function(obj, npcs = 50, assay_use = NULL) {
  if (!"pca" %in% names(obj@reductions)) {
    if (!is.null(assay_use)) DefaultAssay(obj) <- assay_use
    flog.info("RunPCA: npcs=%d | assay=%s", npcs, DefaultAssay(obj))
    obj <- RunPCA(obj, npcs = npcs, verbose = FALSE)
  }
  obj
}

run_tsne_safe <- function(obj, dims_use, reduction_use, nthreads) {
  out <- NULL
  try({
    out <- RunTSNE(
      obj, dims = 1:dims_use, reduction = reduction_use,
      tsne.method = "FIt-SNE", nthreads = nthreads, seed.use = opt$seed, max_iter = 2000
    )
  }, silent = TRUE)
  if (is.null(out)) {
    flog.warn("FIt-SNE unavailable; fallback to default RunTSNE()")
    out <- RunTSNE(obj, dims = 1:dims_use, reduction = reduction_use, seed.use = opt$seed)
  }
  out
}

clustree_auto <- function(obj, out_prefix = "resolution_clustree") {
  p <- NULL
  suppressWarnings({
    p <- clustree(obj)
  })
  if (!is.null(p)) {
    ggsave(paste0(out_prefix, ".pdf"), plot = p, width = 12, height = 12)
    ggsave(paste0(out_prefix, ".png"), plot = p, width = 12, height = 12, dpi = 300)
  } else {
    flog.warn("clustree skipped (no *_snn_res.* columns yet).")
  }
}

get_layer_matrix <- function(obj, assay = "RNA", layer = "counts") {
  if (!assay %in% names(obj@assays)) stop("Assay not found: ", assay)
  mat <- NULL
  mat <- tryCatch(
    GetAssayData(obj, assay = assay, layer = layer),
    error = function(e) NULL
  )
  if (is.null(mat)) {
    # 兼容少量旧对象/旧Seurat：slot
    mat <- tryCatch(
      GetAssayData(obj, assay = assay, slot = layer),
      error = function(e) NULL
    )
  }
  if (is.null(mat)) stop("Failed to fetch assay=", assay, " layer/slot=", layer)
  mat
}

# -------------------------
# logging
# -------------------------
outdir <- dir_create(opt$outdir)
logdir <- dir_create(file.path(outdir, "logs"))
cur_date <- format(Sys.Date(), "%Y%m%d")
invisible(flog.logger("error", ERROR, appender.file(file.path(logdir, sprintf("ERROR-%s.log", cur_date)))))
invisible(flog.logger("warn",  WARN,  appender.file(file.path(logdir, sprintf("WARN-%s.log",  cur_date)))))
invisible(flog.logger("info",  INFO,  appender.file(file.path(logdir, sprintf("INFO-%s.log",  cur_date)))))
invisible(flog.appender(appender.console(), name = "ROOT"))

logger.info <- function(msg, ...) {
  flog.info(msg, ..., name = "ROOT")
  flog.info(msg, ..., name = "info")
}

# -------------------------
# theme
# -------------------------
theme_paper <- theme(
  panel.grid.major = element_line(linewidth = 0.1, linetype = "dashed"),
  legend.key = element_rect(fill = "white", color = "white"),
  legend.key.size = unit(0.5, "cm"),
  legend.position = c(0.2, 0.88),
  legend.title = element_blank(),
  legend.background = element_blank(),
  panel.grid.minor = element_blank(),
  plot.margin = margin(10, 20, 10, 20),
  legend.text = element_text(size = 11),
  axis.title  = element_text(size = 12),
  plot.title  = element_text(size = 12, face = "bold"),
  axis.text   = element_text(size = 11, colour = "black")
)

# -------------------------
# seed & parallel
# -------------------------
set.seed(opt$seed)
registerDoParallel(cores = opt$ncpus)
options(future.globals.maxSize = opt$max_mem_gb * 1024^3)

if (!to_bool(opt$noparallel) && opt$ncpus > 1) {
  workers <- min(opt$ncpus, 12L)
  plan(multisession, workers = workers)
  logger.info("future plan: multisession | workers=%d", workers)
} else {
  plan(sequential)
  logger.info("future plan: sequential")
}
# plan(sequential)
# logger.info("future plan: sequential")

# -------------------------
# read object
# -------------------------
if (!nzchar_(opt$rdsfile) && !nzchar_(opt$infile)) {
  stop("Provide --infile (or --rdsfile).")
}
in_path <- if (nzchar_(opt$rdsfile)) opt$rdsfile else opt$infile
obj <- readRDS(in_path)
logger.info("Loaded RDS: %s", in_path)

# -------------------------
# optional subset by clusters
# -------------------------
# 兼容：优先用 Idents(obj)；若没有 clusters 但有 seurat_clusters，则用它
if (is.null(Idents(obj)) && "seurat_clusters" %in% colnames(obj@meta.data)) {
  Idents(obj) <- obj@meta.data$seurat_clusters
}

if (nzchar_(opt$keeps)) {
  keep_ids <- strsplit(opt$keeps, ",")[[1]]
  obj <- subset(obj, idents = keep_ids)
}
if (nzchar_(opt$rmcluster)) {
  rm_ids <- strsplit(opt$rmcluster, ",")[[1]]
  keep_ids <- setdiff(levels(Idents(obj)), rm_ids)
  obj <- subset(obj, idents = keep_ids)
}

# -------------------------
# dirs
# -------------------------
sc_cluster_dir <- dir_create(file.path(outdir, "sc_cluster"))
sctype_dir <- dir_create(file.path(outdir, "sctype"))

# -------------------------
# parameter record
# -------------------------
save_analysis_parameters <- function(opt, outdir, obj) {
  param_file <- file.path(outdir, "analysis_parameters.txt")
  sink(param_file)
  cat("Single-cell downstream clustering parameters\n")
  cat("===========================================\n")
  cat("run_time: ", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
  cat("script_version: ", VERSION, "\n")
  cat("workdir: ", getwd(), "\n")
  cat("R_version: ", R.version.string, "\n\n")

  cat("Input\n")
  cat("-----\n")
  cat("infile: ", if (nzchar_(opt$rdsfile)) opt$rdsfile else opt$infile, "\n")
  cat("outdir: ", outdir, "\n")
  cat("out_prefix: ", opt$out_prefix, "\n\n")

  cat("Compute\n")
  cat("-------\n")
  cat("ncpus: ", opt$ncpus, "\n")
  cat("max_mem_gb: ", opt$max_mem_gb, "\n")
  cat("noparallel: ", opt$noparallel, "\n\n")

  cat("Clustering\n")
  cat("----------\n")
  cat("default_assay: ", opt$default_assay, "\n")
  cat("dims_use: ", opt$dims_use, "\n")
  cat("npcs: ", opt$npcs, "\n")
  cat("cluster_resolution: ", opt$cluster_resolution, "\n")
  cat("resolution_scan: ", opt$resolution_scan_min, " .. ", opt$resolution_scan_max,
      " step ", opt$resolution_scan_step, "\n")
  cat("seed: ", opt$seed, "\n\n")

  cat("Switches\n")
  cat("--------\n")
  cat("skip_tsne: ", opt$skip_tsne, "\n")
  cat("skip_marker: ", opt$skip_marker, "\n")
  cat("skip_anno: ", opt$skip_anno, "\n")
  cat("export: ", opt$export, "\n")
  cat("join_layers_before_export: ", opt$join_layers_before_export, "\n")
  cat("join_layers_before_save: ", opt$join_layers_before_save, "\n\n")

  cat("Object summary\n")
  cat("--------------\n")
  cat("cells: ", ncol(obj), "\n")
  cat("features: ", nrow(obj), "\n")
  cat("assays: ", paste(names(obj@assays), collapse = ", "), "\n")
  cat("reductions: ", paste(names(obj@reductions), collapse = ", "), "\n")
  cat("meta_cols: ", paste(colnames(obj@meta.data), collapse = ", "), "\n")
  sink()
  flog.info("analysis parameters saved: %s", param_file)
}
save_analysis_parameters(opt, outdir, obj)

# -------------------------
# plotting
# -------------------------
plot_cluster <- function(o, outdir, prefix = "") {
  if (!dir.exists(outdir)) dir.create(outdir, recursive = TRUE)

  # UMAP
  if ("umap" %in% names(o@reductions)) {
    p1 <- DimPlot(o, reduction = "umap", group.by = "replicate", pt.size = 0.1)
    p2 <- DimPlot(o, reduction = "umap", group.by = "group", pt.size = 0.1)
    p3 <- DimPlot(o, reduction = "umap", label = TRUE, repel = TRUE, pt.size = 0.1)
    g <- (p1 + p2 + p3) + theme_paper
    ggsave(file.path(outdir, paste0(prefix, "umap_cluster.pdf")), plot = g, width = 18, height = 5)
    ggsave(file.path(outdir, paste0(prefix, "umap_cluster.png")), plot = g, width = 18, height = 5, dpi = 300)

    if (!is.null(o$group)) {
      g_split <- DimPlot(o, reduction = "umap", split.by = "group", pt.size = 0.1, label = TRUE, repel = TRUE)
      w <- min(4 * length(unique(o$group)), 40)
      ggsave(file.path(outdir, paste0(prefix, "umap_cluster_bygroup.pdf")), plot = g_split, width = w, height = 4)
      ggsave(file.path(outdir, paste0(prefix, "umap_cluster_bygroup.png")), plot = g_split, width = w, height = 4, dpi = 300)
    }
  }

  # tSNE
  if ("tsne" %in% names(o@reductions)) {
    p1 <- DimPlot(o, reduction = "tsne", group.by = "replicate", pt.size = 0.1)
    p2 <- DimPlot(o, reduction = "tsne", group.by = "group", pt.size = 0.1)
    p3 <- DimPlot(o, reduction = "tsne", label = TRUE, repel = TRUE, pt.size = 0.1)
    g <- (p1 + p2 + p3) + theme_paper
    ggsave(file.path(outdir, paste0(prefix, "tsne_cluster.pdf")), plot = g, width = 18, height = 5)
    ggsave(file.path(outdir, paste0(prefix, "tsne_cluster.png")), plot = g, width = 18, height = 5, dpi = 300)
  }
}

# -------------------------
# cellanno mapping (optional early exit, but keep all outputs)
# -------------------------


if (nzchar_(opt$cellanno) && file.exists(opt$cellanno)) {
  has_cellanno <- TRUE
  dt <- data.table::fread(opt$cellanno)  # 自动识别分隔符与表头
  if (ncol(dt) < 2) stop("--cellanno 需要至少两列：第1列=cluster，第2列=celltype")
  # 只取前两列并命名
  ann <- as.data.frame(dt)
  colnames(ann)[1:2] <- c("cluster","celltype")

  if (!"seurat_clusters" %in% colnames(obj@meta.data)) {
    stop("对象中找不到 'seurat_clusters'，无法应用 --cellanno 注释。")
  }

  # 映射：按字符匹配，未命中者保留为 C{cluster}
  cl2type <- setNames(as.character(ann$celltype), as.character(ann$cluster))
  clusters_chr <- as.character(obj@meta.data$seurat_clusters)
  custom <- unname(cl2type[clusters_chr])
  na_idx <- is.na(custom)
  if (any(na_idx)) custom[na_idx] <- "Unknown"

  # 使用 AddMetaData 严格按细胞顺序写入（避免 $<-.Seurat 触发 [[<- 分支导致错误）
  custom_df <- data.frame(customclassif = as.character(custom),
                          row.names = rownames(obj@meta.data),
                          check.names = FALSE)
  obj <- AddMetaData(obj, metadata = custom_df)

  flog.info("Applied --cellanno to 'customclassif' from: %s", opt$cellanno)
  setwd(sc_cluster_dir)
  setwd(outdir)
  cat('Cell\t',file=opt$metafile)
  write.table(obj@meta.data, file=opt$metafile, quote=FALSE, sep='\t', col.names = TRUE,append=T)
  if (nzchar_(opt$rmcluster)) {
    obj <- RunUMAP(obj, reduction="pca", dims=1:dims, verbose=FALSE)
  }
  saveRDS(obj, file="cells_analysis.reanno.rds", compress=FALSE)
  flog.info("Saved: cells_analysis.reanno.rds")

  setwd(sc_cluster_dir)

  # ---------- 统计并保存 ----------
  clu_table <- data.frame(
    CellIndex = rownames(obj@meta.data),
    ClusterID = as.character(Idents(obj)),
    sample    = obj$replicate,
    group     = obj$group,
    cellclass = obj$customclassif,
    check.names = FALSE
  )
  write.table(clu_table, file="Clusters.xls", sep="\t", quote=FALSE, row.names=FALSE)

  setwd(outdir)


  # 可选外部脚本
  if (nzchar_(opt$toolsdir)) {
    setwd(sc_cluster_dir)
    perl_stat <- file.path(opt$toolsdir, "tools", "sc_stat_cluster.pl")
    if (file.exists(perl_stat)) system2("perl", c(perl_stat), stdout=TRUE, stderr=TRUE)

    setwd(outdir)
    r_markers1 <- file.path(opt$toolsdir, "tools", "sc_combined_markers_bycelltype.r")
    r_markers2 <- file.path(opt$toolsdir, "tools", "sc_combined_markers_bycelltype.r")
    if (file.exists(r_markers1)) {
      system2("Rscript", c(r_markers1, "-i", "cells_analysis.reanno.rds", "-c", "seurat_clusters", "-b", "cluster"), 
              stdout=TRUE, stderr=TRUE)
    } else {
      flog.warn("skip sc_combined_markers.r")
    }
    
    if (file.exists(r_markers2)) {
      system2("Rscript", c(r_markers2, "-i", "cells_analysis.reanno.rds"), 
              stdout=TRUE, stderr=TRUE)
    } else {
      flog.warn("skip sc_combined_markers_bycelltype.r")
    }
  } else {
    flog.warn("No --toolsdir; skip external stats/marker scripts.")
  }

  writeLines(capture.output(sessionInfo()), "session_info.txt")


  try({ future::plan(sequential) }, silent = TRUE)
  try({ gc() },                    silent = TRUE)
  quit(save = "no", status = 0, runLast = FALSE)
}



# -------------------------
# main clustering workflow (Seurat v5-friendly)
# -------------------------
dims_use <- opt$dims_use
npcs <- max(opt$npcs, dims_use)

# 1) 尽量尊重用户提示的 default_assay，但聚类实际以 reduction 为主（v5 推荐用 integrated.* 或 harmony 这类降维做聚类）
obj <- safe_default_assay(obj, opt$default_assay)

reduction_use <- pick_integration_reduction(obj)

# 2) 若没有任何可用 reduction，则至少保证 pca
if (is.na(reduction_use)) {
  # 尝试：若 integrated assay 存在且用户指定 integrated，则用 integrated；否则用当前 DefaultAssay
  assay_for_pca <- DefaultAssay(obj)
  if ("integrated" %in% names(obj@assays) && opt$default_assay == "integrated") assay_for_pca <- "integrated"
  obj <- safe_default_assay(obj, assay_for_pca)
  obj <- ensure_pca(obj, npcs = npcs, assay_use = DefaultAssay(obj))
  reduction_use <- "pca"
}

flog.info("Clustering will use reduction: %s | dims=1:%d", reduction_use, dims_use)

# 3) neighbors/clusters/UMAP/tSNE
set.seed(opt$seed)
obj <- FindNeighbors(obj, reduction = reduction_use, dims = 1:dims_use, verbose = FALSE)

# scan resolutions for clustree
scan_seq <- seq(opt$resolution_scan_min, opt$resolution_scan_max, by = opt$resolution_scan_step)
obj <- FindClusters(obj, resolution = scan_seq, verbose = FALSE, random.seed = opt$seed)
setwd(sc_cluster_dir)
clustree_auto(obj, out_prefix = file.path(sc_cluster_dir, "resolution_clustree"))

# final clustering
obj <- FindClusters(obj, resolution = opt$cluster_resolution, verbose = FALSE, random.seed = opt$seed)

# UMAP
set.seed(opt$seed)
obj <- RunUMAP(obj, reduction = reduction_use, dims = 1:dims_use, verbose = FALSE, seed.use = opt$seed)

# tSNE
if (!to_bool(opt$skip_tsne)) {
  set.seed(opt$seed)
  obj <- run_tsne_safe(obj, dims_use = dims_use, reduction_use = reduction_use, nthreads = opt$ncpus)
}

# -------------------------
# export RNA matrix (optional)
# -------------------------
if (to_bool(opt$export)) {
  if (!"RNA" %in% names(obj@assays)) {
    flog.warn("No RNA assay found; skip export.")
  } else {
    if (to_bool(opt$join_layers_before_export)) {
      obj <- safe_join_layers(obj, assay = "RNA")
    }
    counts <- get_layer_matrix(obj, assay = "RNA", layer = "counts")
    data <- get_layer_matrix(obj, assay = "RNA", layer = "data")

    gz1 <- gzfile(file.path(outdir, "Gene_Count_per_Cell.tsv.gz"), "w")
    write.table(counts, file = gz1, quote = FALSE, sep = "\t", col.names = TRUE)
    close(gz1)

    gz2 <- gzfile(file.path(outdir, "Gene_Exp_per_Cell.tsv.gz"), "w")
    write.table(data, file = gz2, quote = FALSE, sep = "\t", col.names = TRUE)
    close(gz2)

    flog.info("Exported RNA counts/data to %s", outdir)
  }
}

# -------------------------
# plotting cluster figs
# -------------------------
# plot_cluster(obj, outdir = sc_cluster_dir, prefix = "")

# -------------------------
# ScType annotation (optional)
# -------------------------
if (!to_bool(opt$skip_anno)) {
  sctype_ok <- file.exists(opt$sctypedb)
  gs_prepare <- file.path(opt$toolsdir, "sctype", "gene_sets_prepare.R")
  score_func <- file.path(opt$toolsdir, "sctype", "sctype_score_.R")
  sctype_ok <- sctype_ok && file.exists(gs_prepare) && file.exists(score_func)

  if (!sctype_ok) {
    flog.warn("ScType unavailable (db/scripts missing). Setting customclassif=C{cluster}.")
    obj$customclassif <- paste0("C", as.character(Idents(obj)))
  } else {
    setwd(sctype_dir)
    suppressPackageStartupMessages(library(HGNChelper))
    source(gs_prepare)
    source(score_func)

    if ("RNA" %in% names(obj@assays)) {
      DefaultAssay(obj) <- "RNA"

      # 为 ScType 评分准备 scale.data：只对 HVG，避免全基因 scale 爆内存
      obj <- FindVariableFeatures(obj, nfeatures = 6000, verbose = FALSE)
      obj <- ScaleData(obj, features = VariableFeatures(obj), verbose = FALSE)

      gs_list <- gene_sets_prepare(opt$sctypedb, opt$tissue)

      scale_mat <- NULL
      scale_mat <- tryCatch(
        GetAssayData(obj, assay = "RNA", layer = "scale.data"),
        error = function(e) NULL
      )
      if (is.null(scale_mat)) {
        # 少量旧对象兜底
        scale_mat <- GetAssayData(obj, assay = "RNA", slot = "scale.data")
      }

      print(gs_list$gs_positive)

      print(scale_mat[,1:15])

      es.max <- sctype_score(
        scRNAseqData = scale_mat,
        scaled = TRUE,
        gs = gs_list$gs_positive,
        gs2 = gs_list$gs_negative
      )

      if (!"seurat_clusters" %in% colnames(obj@meta.data)) {
        obj@meta.data$seurat_clusters <- as.character(Idents(obj))
      }

      clu_ids <- sort(unique(obj@meta.data$seurat_clusters))
      cL_res <- do.call("rbind", lapply(clu_ids, function(cl) {
        cells <- rownames(obj@meta.data)[obj@meta.data$seurat_clusters == cl]
        sc <- sort(rowSums(es.max[, cells, drop = FALSE]), decreasing = TRUE)
        head(data.frame(
          cluster = cl,
          type = names(sc),
          scores = as.numeric(sc),
          ncells = length(cells),
          stringsAsFactors = FALSE
        ), 10)
      }))

      write.table(cL_res, file = "sctype_cluster_scores.tsv",
                  sep = "\t", quote = FALSE, row.names = FALSE)

      top1 <- cL_res %>%
        group_by(cluster) %>%
        slice_max(order_by = scores, n = 1, with_ties = FALSE) %>%
        ungroup()

      write.table(top1, file = "sctype_scores.xls",
                  sep = "\t", quote = FALSE, row.names = FALSE, col.names = TRUE)

      obj$customclassif <- "Unknown"
      for (j in unique(top1$cluster)) {
        lab <- as.character(top1$type[top1$cluster == j][1])
        obj@meta.data$customclassif[obj@meta.data$seurat_clusters == j] <- lab
      }

      # # plot
      # if ("umap" %in% names(obj@reductions)) {
      #   g <- DimPlot(obj, reduction = "umap", group.by = "customclassif",
      #                label = TRUE, repel = TRUE, pt.size = 0.1) + theme_paper
      #   ggsave("umap_sctype.pdf", plot = g, width = 10, height = 6)
      #   ggsave("umap_sctype.png", plot = g, width = 10, height = 6, dpi = 300)
      # }
    } else {
      flog.warn("No RNA assay; ScType skipped. Setting customclassif=C{cluster}.")
      obj$customclassif <- paste0("C", as.character(Idents(obj)))
    }
  }
} else {
  obj$customclassif <- if ("customclassif" %in% colnames(obj@meta.data)) {
    obj@meta.data$customclassif
  } else {
    paste0("C", as.character(Idents(obj)))
  }
}

# -------------------------
# export meta & clusters table
# -------------------------
setwd(sc_cluster_dir)
clu_table <- data.frame(
  CellIndex = rownames(obj@meta.data),
  ClusterID = as.character(Idents(obj)),
  sample = if ("replicate" %in% colnames(obj@meta.data)) obj$replicate else NA,
  group = if ("group" %in% colnames(obj@meta.data)) obj$group else NA,
  cellclass = if ("customclassif" %in% colnames(obj@meta.data)) obj$customclassif else NA,
  check.names = FALSE
)
write.table(clu_table, file = "Clusters.xls", sep = "\t", quote = FALSE, row.names = FALSE)

setwd(outdir)
# meta.xls
cat("Cell\t", file = file.path(outdir, opt$metafile))
write.table(obj@meta.data, file = file.path(outdir, opt$metafile),
            quote = FALSE, sep = "\t", col.names = TRUE, append = TRUE)

# -------------------------
# external scripts (optional, keep original behavior)
# -------------------------
if (nzchar_(opt$toolsdir)) {
  perl_stat <- file.path(opt$toolsdir, "tools", "sc_stat_cluster.pl")
  if (file.exists(perl_stat)) {
    setwd(sc_cluster_dir)
    try(system2("perl", args = c(perl_stat), stdout = TRUE, stderr = TRUE), silent = TRUE)
  }

} else {
  flog.warn("No --toolsdir; skip external stats/marker scripts.")
}

# -------------------------
# JoinLayers before save (optional)
# -------------------------
if (to_bool(opt$join_layers_before_save)) {
  obj <- safe_join_layers(obj, assay = "RNA")
}

# -------------------------
# save object + session info + run params
# -------------------------
saveRDS(obj, file = file.path(outdir, paste0(opt$out_prefix, ".rds")), compress = FALSE)
flog.info("Saved: %s", file.path(outdir, paste0(opt$out_prefix, ".rds")))
rm(obj); gc()

# -------------------------
# external scripts (optional, keep original behavior)
# -------------------------
if (nzchar_(opt$toolsdir)) {

  if (!to_bool(opt$skip_marker)) {
    r_markers1 <- file.path(opt$toolsdir, "tools", "sc_combined_markers_bycelltype.r")
    r_markers2 <- file.path(opt$toolsdir, "tools", "sc_combined_markers_bycelltype.r")
    setwd(outdir)
    if (file.exists(r_markers1)) {
      system2("Rscript", c(r_markers1, "-i", "cells_analysis.rds", "-c", "seurat_clusters", "-b", "cluster"), 
              stdout=TRUE, stderr=TRUE)
    } else {
      flog.warn("skip sc_combined_markers.r")
    }
    
    if (file.exists(r_markers2)) {
      system2("Rscript", c(r_markers2, "-i", "cells_analysis.rds"), 
              stdout=TRUE, stderr=TRUE)
    } else {
      flog.warn("skip sc_combined_markers_bycelltype.r")
    }
  }
} else {
  flog.warn("No --toolsdir; skip external stats/marker scripts.")
}


writeLines(capture.output(sessionInfo()), file.path(outdir, "session_info.txt"))

param_df <- data.frame(
  option = c("VERSION", "run_time", names(opt)),
  value = c(
    VERSION,
    format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
    vapply(opt, function(x) paste(x, collapse = ","), character(1L))
  ),
  stringsAsFactors = FALSE
)
write.table(param_df, file = file.path(outdir, "run_parameters.tsv"),
            sep = "\t", quote = FALSE, row.names = FALSE)

flog.info("All done.")
