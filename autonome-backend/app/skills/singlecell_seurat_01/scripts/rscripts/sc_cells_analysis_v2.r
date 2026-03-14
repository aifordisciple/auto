#!/usr/bin/env Rscript

# =========================================
# Single-cell downstream clustering & viz
# 模式说明（输入 RDS 已完成上游处理）：
#   --defaultassay integrated   : 已做 Seurat Integration（assay=integrated），用 PCA 做邻接/聚类/UMAP/tSNE
#   --defaultassay SCT  : 已做 SCTransform+Harmony（assay=SCT，reduction=harmony），
#                         用 harmony 做邻接/聚类/UMAP/tSNE（缺失时回退到 PCA）
# 作者: CHAO CHENG (biosalt) / 整理: 2025-10-17
# 版本: 2.0.0
# =========================================

suppressPackageStartupMessages({
  library(optparse)
  library(futile.logger)
  library(ggplot2)
  library(dplyr)
  library(SingleCellExperiment)
  library(Seurat)
  library(patchwork)
  library(clustree)
  library(future.apply)
  library(doParallel)
  library(data.table)
})

`%ni%` <- Negate(`%in%`)
options(stringsAsFactors = FALSE)
VERSION <- "3.1.1"

# ---------- CLI ----------
option_list <- list(
  make_option(c("-v","--version"), action="store_true", default=FALSE,
              help="print version and exit"),
  make_option(c("-n","--ncpus"), type="integer", default=6,
              help="number of CPU cores"),
  make_option(c("--MaxMemMega"), type="integer", default=460,
              help="future.globals.maxSize in GB"),
  make_option(c("-i","--infile"), type="character",
              help="input RDS (object already integrated or SCT)"),
  make_option(c("-r","--rdsfile"), type="character", default="",
              help="existing object with clusters (optional; overrides --infile)"),
  make_option(c("-d","--dims"), type="integer", default=25,
              help="number of dims for neighbors/UMAP/tSNE"),
  make_option(c("--resolution"), type="double", default=0.6,
              help="final clustering resolution"),
  make_option(c("-a","--defaultassay"), type="character", default="integrated",
              help="integrated (or SCT)"),
  make_option(c("--skiptsne"), type="character", default="false",
              help="skip tSNE (true/false)"),
  make_option(c("--skipmarker"), type="character", default="false",
              help="skip identify markers (true/false)"),
  make_option(c("--skipanno"), type="character", default="false",
              help="skip ScType annotation (true/false)"),
  make_option(c("--export"), type="character", default="false",
              help="export RNA counts/expr (true/false)"),
  make_option(c("--noparallel"), type="character", default="true",
              help="disable future parallel (true/false)"),
  make_option(c("--sctypedb"), type="character",
              default="/opt/data1/public/database/singlecell/sctype_marker_db.xlsx",
              help="ScType DB xlsx"),
  make_option(c("-t","--tissue"), type="character", default="Immune system",
              help="tissue for ScType DB"),
  make_option(c("--cellanno"), type="character", default="",
              help="(optional) cluster-to-celltype mapping file"),
  make_option(c("--rmcluster"), type="character", default="",
              help="comma list of clusters to remove"),
  make_option(c("--keeps"), type="character", default="",
              help="comma list of clusters to keep"),
  make_option(c("--toolsdir"), type="character", default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/",
              help="optional tools folder for external scripts"),
  make_option(c("--outdir"), type="character", default="./", help="输出目录"),
  make_option(c("--metafile"), type="character", default="meta.xls", help="meta信息"),
  make_option(c("--seed"), type="integer", default=12345,
              help="random seed for reproducibility")
)
opt <- parse_args(OptionParser(option_list = option_list))
if (opt$version) { message("Version: ", VERSION); quit(save="no") }

# ---------- helpers ----------
to_bool <- function(x) tolower(x) %in% c("true","t","1","yes","y")
nzchar_ <- function(x) !is.null(x) && x != ""
dir_create <- function(p) { if (!dir.exists(p)) dir.create(p, recursive = TRUE); normalizePath(p) }

safe_default_assay <- function(obj, wanted) {
  if (wanted %in% names(obj@assays)) {
    DefaultAssay(obj) <- wanted
  } else if ("RNA" %in% names(obj@assays)) {
    DefaultAssay(obj) <- "RNA"
    flog.warn("default assay '%s' not found; fallback to 'RNA'", wanted)
  } else stop("No suitable assay found.")
  obj
}

need_pca <- function(obj) !"pca" %in% names(obj@reductions)
ensure_pca <- function(obj, dims=50, assay_use=NULL) {
  if (need_pca(obj)) {
    flog.info("RunPCA: computing PCA (npcs=%d)...", max(50, dims))
    if (!is.null(assay_use)) DefaultAssay(obj) <- assay_use
    obj <- RunPCA(obj, npcs=max(50, dims), verbose=FALSE)
  }
  obj
}

run_tsne_safe <- function(obj, dims, reduction, nthreads) {
  out <- NULL
  try({
    out <- RunTSNE(obj, dims=1:dims, reduction=reduction,
                   tsne.method="FIt-SNE", nthreads=nthreads, max_iter=2000)
  }, silent=TRUE)
  if (is.null(out)) {
    flog.warn("FIt-SNE unavailable; fallback to Rtsne")
    out <- RunTSNE(obj, dims=1:dims, reduction=reduction)
  }
  out
}

clustree_auto <- function(obj, outfile_prefix="resolution_clustree") {
  p <- NULL
  suppressWarnings({
    p <- clustree(obj)
  })
  if (!is.null(p)) {
    ggsave(paste0(outfile_prefix,".pdf"), plot=p, width=12, height=12)
    ggsave(paste0(outfile_prefix,".png"), plot=p, width=12, height=12, dpi=300)
  } else {
    flog.warn("clustree plot skipped (no *_snn_res.* columns yet).")
  }
}

# ---------- theme ----------
theme_paper <- theme(
  panel.grid.major = element_line(linewidth=0.1, linetype="dashed"),
  legend.key = element_rect(fill='white', color='white'),
  legend.key.size = unit(0.5, "cm"),
  legend.position = c(0.2, 0.88),
  legend.title = element_blank(),
  legend.background = element_blank(),
  panel.grid.minor = element_blank(),
  plot.margin = margin(10, 20, 10, 20),
  legend.text = element_text(size=11),
  axis.title  = element_text(size=12),
  plot.title  = element_text(size=12, face="bold"),
  axis.text   = element_text(size=11, colour="black")
)

# ---------- 绘图 ----------
plot_cluster <- function(o) {
  # UMAP
  p1 <- DimPlot(o, reduction="umap", group.by="replicate", pt.size=0.1)
  p2 <- DimPlot(o, reduction="umap", group.by="group",     pt.size=0.1)
  p3 <- DimPlot(o, reduction="umap", label=TRUE, pt.size=0.1)
  g  <- (p1 + p2 + p3) + theme_paper
  ggsave("umap_cluster.pdf", plot=g, width=18, height=5)
  ggsave("umap_cluster.png", plot=g, width=18, height=5, dpi=300)

  # tSNE（若存在）
  if ("tsne" %in% names(o@reductions)) {
    p1 <- DimPlot(o, reduction="tsne", group.by="replicate", pt.size=0.1)
    p2 <- DimPlot(o, reduction="tsne", group.by="group",     pt.size=0.1)
    p3 <- DimPlot(o, reduction="tsne", label=TRUE, pt.size=0.1)
    g  <- (p1 + p2 + p3) + theme_paper
    ggsave("tsne_cluster.pdf", plot=g, width=18, height=5)
    ggsave("tsne_cluster.png", plot=g, width=18, height=5, dpi=300)
  }

  # 拆分（按 group）
  if (!is.null(o$group)) {
    g_split <- DimPlot(o, reduction="umap", split.by="group", pt.size=0.1, label=TRUE)
    w <- min(4 * length(unique(o$group)), 40)
    ggsave("umap_cluster_bygroup.pdf", plot=g_split, width=w, height=4)
    ggsave("umap_cluster_bygroup.png", plot=g_split, width=w, height=4, dpi=300)
  }
}

# ---------- logging ----------
if (!dir.exists("logs")) dir.create("logs")
cur_date <- format(Sys.Date(), "%Y%m%d")
invisible(flog.logger("error", ERROR, appender.file(file.path("logs", sprintf("ERROR-%s.log", cur_date)))))
invisible(flog.logger("warn",  WARN,  appender.file(file.path("logs", sprintf("WARN-%s.log",  cur_date)))))
invisible(flog.logger("info",  INFO,  appender.file(file.path("logs", sprintf("INFO-%s.log",  cur_date)))))
invisible(flog.appender(appender.console(), name="ROOT"))

logger.info <- function(msg, ...) { flog.info(msg, ..., name="ROOT"); flog.info(msg, ..., name="info") }

# ---------- seed & parallel ----------
set.seed(opt$seed)
registerDoParallel(cores=opt$ncpus)
options(future.globals.maxSize = opt$MaxMemMega * 1024^3)
if (!to_bool(opt$noparallel)) {
  # future::plan("multisession", workers=opt$ncpus)
  # 多线程占内存太多，统一都用单线程
  future::plan(sequential)
  logger.info("parallel enabled with %d workers", opt$ncpus)
} else {
  future::plan(sequential)
  logger.info("parallel disabled")
}

# ---------- read object ----------
if (!nzchar_(opt$rdsfile) && !nzchar_(opt$infile)) stop("Provide --infile (or --rdsfile).")
obj <- if (nzchar_(opt$rdsfile)) readRDS(opt$rdsfile) else readRDS(opt$infile)
flog.info("Done read RDS file: %s", if (nzchar_(opt$rdsfile)) opt$rdsfile else opt$infile)

# RNA 多层尽量合并（导出前也会再试）
if ("RNA" %in% names(obj@assays)) {
  try({ if (length(Layers(obj[["RNA"]])) > 1) obj[["RNA"]] <- JoinLayers(obj[["RNA"]]) }, silent=TRUE)
}

# ---------- optional subset ----------
if (nzchar_(opt$keeps)) obj <- subset(obj, idents = strsplit(opt$keeps,",")[[1]])
if (nzchar_(opt$rmcluster)) {
  rmcs <- strsplit(opt$rmcluster, ",")[[1]]
  keeps <- setdiff(levels(Idents(obj)), rmcs)
  obj <- subset(obj, idents=keeps)
}




# ---------- main workflow (downstream only) ----------
defaultassay <- opt$defaultassay
dims <- opt$dims
res  <- opt$resolution

outdir      <- dir_create(opt$outdir)
sctype_dir <- dir_create(file.path(outdir, "sctype"))
sc_cluster_dir   <- dir_create(file.path(outdir, "sc_cluster"))

has_cellanno <- FALSE


# ---------- 参数记录功能 ----------
save_analysis_parameters <- function(opt, outdir) {
  # 创建参数记录文件
  param_file <- file.path(outdir, "analysis_parameters.txt")
  
  # 打开文件连接
  sink(param_file)
  
  # 写入参数头信息
  cat("单细胞聚类分析参数记录\n")
  cat("==============================\n")
  cat("分析时间:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
  cat("脚本版本:", VERSION, "\n")
  cat("工作目录:", getwd(), "\n")
  cat("R版本:", R.version.string, "\n\n")
  
  # 基本文件参数
  cat("1. 文件参数\n")
  cat("-----------\n")
  cat("输入文件:", ifelse(nzchar_(opt$rdsfile), opt$rdsfile, opt$infile), "\n")
  cat("输出目录:", outdir, "\n")
  cat("元数据文件:", opt$metafile, "\n")
  cat("工具目录:", opt$toolsdir, "\n\n")
  
  # 分析模式参数
  cat("2. 分析模式参数\n")
  cat("---------------\n")
  cat("默认assay:", opt$defaultassay, "\n")
  cat("使用维度数:", opt$dims, "\n")
  cat("聚类分辨率:", opt$resolution, "\n")
  cat("随机种子:", opt$seed, "\n\n")
  
  # 计算资源参数
  cat("3. 计算资源参数\n")
  cat("---------------\n")
  cat("CPU核心数:", opt$ncpus, "\n")
  cat("最大内存(GB):", opt$MaxMemMega, "\n")
  cat("禁用并行:", opt$noparallel, "\n")
  cat("实际并行模式:", ifelse(to_bool(opt$noparallel), "sequential", "multisession"), "\n\n")
  
  # 分析步骤控制
  cat("4. 分析步骤控制\n")
  cat("---------------\n")
  cat("跳过tSNE:", opt$skiptsne, "\n")
  cat("跳过注释:", opt$skipanno, "\n")
  cat("导出表达矩阵:", opt$export, "\n")
  cat("ScType组织类型:", opt$tissue, "\n")
  cat("ScType数据库:", opt$sctypedb, "\n\n")
  
  # 细胞过滤参数
  cat("5. 细胞过滤参数\n")
  cat("---------------\n")
  cat("保留的聚类:", ifelse(nzchar_(opt$keeps), opt$keeps, "全部"), "\n")
  cat("移除的聚类:", ifelse(nzchar_(opt$rmcluster), opt$rmcluster, "无"), "\n")
  cat("细胞注释文件:", ifelse(nzchar_(opt$cellanno), opt$cellanno, "无"), "\n")
  cat("应用细胞注释:", has_cellanno, "\n\n")
  
  # 对象信息统计
  cat("6. 对象信息统计\n")
  cat("---------------\n")
  cat("细胞数量:", ncol(obj), "\n")
  cat("基因数量:", nrow(obj), "\n")
  cat("已有的assay:", paste(names(obj@assays), collapse=", "), "\n")
  cat("已有的降维:", paste(names(obj@reductions), collapse=", "), "\n")
  cat("元数据列:", paste(colnames(obj@meta.data), collapse=", "), "\n")
  
  # 关闭文件连接
  sink()
  
  # 同时在控制台输出信息
  flog.info("分析参数已保存至: %s", param_file)
  
  return(param_file)
}

# ---------- 在环境设置后调用参数记录 ----------
# 在以下代码之后添加调用：
# outdir      <- dir_create(opt$outdir)
# sctype_dir <- dir_create(file.path(outdir, "sctype"))
# sc_cluster_dir   <- dir_create(file.path(outdir, "sc_cluster"))

# 添加参数记录调用（放在目录创建之后，主流程开始之前）
param_file <- save_analysis_parameters(opt, outdir)


# ---- NEW: 如果提供了 --cellanno，基于 seurat_clusters 直接赋值 customclassif ----
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
  plot_cluster(obj)
  setwd(outdir)
  cat('Cell\t',file=opt$metafile)
  write.table(obj@meta.data, file=opt$metafile, quote=FALSE, sep='\t', col.names = TRUE,append=T)
  if (nzchar_(opt$rmcluster)) {
    obj <- RunUMAP(obj, reduction="pca", dims=1:dims, verbose=FALSE)
  }
  saveRDS(obj, file="cells_analysis.reanno.rds")
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
    r_markers1 <- file.path(opt$toolsdir, "tools", "sc_combined_markers.r")
    r_markers2 <- file.path(opt$toolsdir, "tools", "sc_combined_markers_bycelltype.r")
    if (file.exists(r_markers1)) system2("Rscript", c(r_markers1), " -i cells_analysis.reanno.rds") else flog.warn("skip sc_combined_markers.r")
    if (file.exists(r_markers2)) system2("Rscript", c(r_markers2), " -i cells_analysis.reanno.rds") else flog.warn("skip sc_combined_markers_bycelltype.r")
  } else {
    flog.warn("No --toolsdir; skip external stats/marker scripts.")
  }

  writeLines(capture.output(sessionInfo()), "session_info.txt")



  try({ future::plan(sequential) }, silent = TRUE)
  try({ gc() },                    silent = TRUE)
  quit(save = "no", status = 0, runLast = FALSE)
}

# ---- 正常聚类注释 ----

setwd(sc_cluster_dir)

if (defaultassay == "integrated") {
  # 输入已做 Seurat-Integration：以 PCA 为基础
  obj <- safe_default_assay(obj, opt$defaultassay)  # 常见为 'integrated'
  obj <- ensure_pca(obj, dims=dims, assay_use=DefaultAssay(obj))
  obj <- FindNeighbors(obj, reduction="pca", dims=1:dims)
  obj <- FindClusters(obj, resolution=seq(0.1,1.5,by=0.1), verbose=FALSE, random.seed=opt$seed)
  clustree_auto(obj)
  obj <- FindClusters(obj, resolution=res, verbose=FALSE, random.seed=opt$seed)
  obj <- RunUMAP(obj, reduction="pca", dims=1:dims, verbose=FALSE)
  if (!to_bool(opt$skiptsne)) obj <- run_tsne_safe(obj, dims=dims, reduction="pca", nthreads=opt$ncpus)

} else if (defaultassay == "SCT") {
  # 输入已做 SCTransform + Harmony：优先使用 harmony 降维
  if ("SCT" %in% names(obj@assays)) DefaultAssay(obj) <- "SCT"
  reduction_use <- if ("harmony" %in% names(obj@reductions)) "harmony" else "pca"
  if (reduction_use == "pca" && need_pca(obj)) {
    flog.warn("reduction 'harmony' not found; fallback to PCA.")
    obj <- ensure_pca(obj, dims=dims, assay_use=DefaultAssay(obj))
  }
  obj <- FindNeighbors(obj, reduction=reduction_use, dims=1:dims)
  obj <- FindClusters(obj, resolution=seq(0.1,1.5,by=0.1), verbose=FALSE, random.seed=opt$seed)
  clustree_auto(obj)
  obj <- FindClusters(obj, resolution=res, verbose=FALSE, random.seed=opt$seed)
  obj <- RunUMAP(obj, reduction=reduction_use, dims=1:dims, verbose=FALSE)
  if (!to_bool(opt$skiptsne)) obj <- run_tsne_safe(obj, dims=dims, reduction=reduction_use, nthreads=opt$ncpus)

} else {
  stop("Unknown --defaultassay. Use 'integrated' or 'SCT'.")
}

# ---------- 导出 RNA 计数/表达（可选） ----------
if (to_bool(opt$export)) {
  if (!"RNA" %in% names(obj@assays)) {
    flog.warn("No RNA assay found; skip export.")
  } else {
    try({ if (length(Layers(obj[["RNA"]])) > 1) obj[["RNA"]] <- JoinLayers(obj[["RNA"]]) }, silent=TRUE)
    gz1 <- gzfile("Gene_Count_per_Cell.tsv.gz", "w")
    write.table(obj@assays[["RNA"]]@counts, file=gz1, quote=FALSE, sep="\t", col.names=TRUE)
    close(gz1)
    gz2 <- gzfile("Gene_Exp_per_Cell.tsv.gz", "w")
    write.table(obj@assays[["RNA"]]@data, file=gz2, quote=FALSE, sep="\t", col.names=TRUE)
    close(gz2)
  }
}

plot_cluster(obj)

setwd(sctype_dir)

# ---------- ScType 注释（可选；仅可视化标签，不改变流程） ----------
if (!to_bool(opt$skipanno)) {
  sctype_ok <- file.exists(opt$sctypedb)
  gs_prepare <- file.path(opt$toolsdir, "sctype", "gene_sets_prepare.R")
  score_func <- file.path(opt$toolsdir, "sctype", "sctype_score_.R")
  sctype_ok <- sctype_ok && file.exists(gs_prepare) && file.exists(score_func)

  if (!sctype_ok) {
    flog.warn("ScType not available (db/scripts missing). Skip annotation.")
    obj$customclassif <- paste0("C", Idents(obj))
  } else {
    sctype_dir <- dir_create(file.path(outdir, "sctype"))
    lapply(c("HGNChelper"), require, character.only=TRUE)
    source(gs_prepare); source(score_func)
    if ("RNA" %in% names(obj@assays)) {
      DefaultAssay(obj) <- "RNA"
      obj <- FindVariableFeatures(obj, nfeatures=6000)
      obj <- ScaleData(obj, features = VariableFeatures(obj))
      gs_list <- gene_sets_prepare(opt$sctypedb, opt$tissue)
      es.max  <- sctype_score(scRNAseqData = obj[["RNA"]]$scale.data,
                              scaled = TRUE,
                              gs = gs_list$gs_positive,
                              gs2 = gs_list$gs_negative)
      clu_ids <- unique(obj@meta.data$seurat_clusters)
      cL_res <- do.call("rbind", lapply(clu_ids, function(cl){
        cells <- rownames(obj@meta.data)[obj@meta.data$seurat_clusters == cl]
        sc <- sort(rowSums(es.max[, cells, drop=FALSE]), decreasing=TRUE)
        head(data.frame(cluster=cl, type=names(sc), scores=sc,
                        ncells=length(cells)), 10)
      }))
      write.table(cL_res, file="sctype_cluster_scores.tsv",
                  sep="\t", quote=FALSE, row.names=FALSE)
      top1 <- cL_res %>% group_by(cluster) %>% top_n(n=1, wt=scores)
      # top1$type[as.numeric(as.character(top1$scores)) < top1$ncells/4] = "Unknown"
      print(top1[,1:4])
      cat('',file=paste('sctype_scores','.xls',sep=''))
      write.table(top1,file=paste('sctype_scores','.xls',sep=''),
                      append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)
      obj$customclassif <- ""
      for (j in unique(top1$cluster)) {
        lab <- as.character(top1$type[top1$cluster==j][1])
        obj@meta.data$customclassif[obj@meta.data$seurat_clusters==j] <- lab
      }
      g <- DimPlot(obj, reduction="umap", group.by="customclassif",
                   label=TRUE, repel=TRUE, pt.size=0.1) + theme_paper
      ggsave("umap_sctype.pdf", plot=g, width=10, height=6)
      ggsave("umap_sctype.png", plot=g, width=10, height=6, dpi=300)
    } else {
      flog.warn("No RNA assay; skip ScType scoring.")
      obj$customclassif <- paste0("C", Idents(obj))
    }
  }
} else {
  obj$customclassif <- paste0("C", Idents(obj))
}

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

# RNA 单层化 & 保存
try({
  if ("RNA" %in% names(obj@assays) && length(Layers(obj[["RNA"]])) > 1) {
    obj[["RNA"]] <- JoinLayers(obj[["RNA"]])
    message("RNA assay had multiple layers, joined now.")
  }
}, silent=TRUE)

cat('Cell\t',file=opt$metafile)
write.table(obj@meta.data, file=opt$metafile, quote=FALSE, sep='\t', col.names = TRUE,append=T)

saveRDS(obj, file="cells_analysis.rds")
flog.info("Saved: cells_analysis.rds")

# 可选外部脚本
if (nzchar_(opt$toolsdir)) {
  setwd(sc_cluster_dir)
  perl_stat <- file.path(opt$toolsdir, "tools", "sc_stat_cluster.pl")
  if (file.exists(perl_stat)) system2("perl", c(perl_stat), stdout=TRUE, stderr=TRUE)

  setwd(outdir)
  if (!to_bool(opt$skipmarker)) {
    r_markers1 <- file.path(opt$toolsdir, "tools", "sc_combined_markers.r")
    r_markers2 <- file.path(opt$toolsdir, "tools", "sc_combined_markers_bycelltype.r")
    if (file.exists(r_markers1)) system2("Rscript", c(r_markers1)) else flog.warn("skip sc_combined_markers.r")
    if (file.exists(r_markers2)) system2("Rscript", c(r_markers2)) else flog.warn("skip sc_combined_markers_bycelltype.r")
  }
  
} else {
  flog.warn("No --toolsdir; skip external stats/marker scripts.")
}


## ------------------------------------------------------------
## 保存参数设置到文件：run_parameters.tsv
## ------------------------------------------------------------
writeLines(capture.output(sessionInfo()), "session_info.txt")

param_df <- data.frame(
  option = c("VERSION", "run_time", names(opt)),
  value  = c(
    VERSION,
    format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
    vapply(opt, function(x) paste(x, collapse = ","), character(1L))
  ),
  stringsAsFactors = FALSE
)

param_file <- file.path("run_parameters.tsv")
write.table(
  param_df,
  file      = param_file,
  sep       = "\t",
  quote     = FALSE,
  row.names = FALSE
)

message("[INFO] 参数设置已写入: ", param_file)
## ------------------------------------------------------------