#!/usr/bin/env Rscript
################################################################################
## single‑cell gene‑visualisation pipeline – memory‑optimised  (v3.1.0‑lite)
## Author: Chao Cheng <chengchao@biosalt.cc>
## Maintainer of this revision: ChatGPT (2025‑04‑17)
################################################################################

## ────────────────────── 0. 载入依赖 ──────────────────────
suppressPackageStartupMessages({
  library(optparse)      # 命令行参数解析
  library(futile.logger) # 日志记录
  library(dplyr)         # 数据操作
  library(ggplot2)       # 绘图
  library(patchwork)     # 组合 ggplot2 图形
  library(cowplot)       # 主题设置
  library(Seurat)        # 单细胞分析核心包
  library(scCustomize)   # Seurat 可视化自定义
  library(stringr)       # 字符串处理
  library(future.apply)  # 并行计算支持
  library(doParallel)    # 并行计算注册
  library(viridis)       # 调色板
  library(RColorBrewer)  # 另一套调色板
})
options(bitmapType = "cairo")  # 在脚本最开始设置


VERSION <- "3.1.0‑lite"
message("Using Seurat version: ", as.character(packageVersion("Seurat")))


## ────────────────────── 1. 命令行参数 ──────────────────────
option_list <- list(
  make_option(c("-f","--infile"),       type="character",              help="*.rds 文件路径"),
  make_option(c("-n","--ncpus"),        type="integer",  default=4,    help="并行核数"),
  make_option(c("--MaxMemMega"),        type="integer",  default=100000,
              help="future.globals.maxSize (MB)"),
  make_option(c("-l","--listname"),     type="character", default="",
              help="分组名称列表（逗号分割，对应 group metadata）"),
  make_option(c("-g","--genelist"),     type="character", default="",
              help="基因列表（逗号分割）"),
  make_option(c("-m","--genelistfile"), type="character", default="",
              help="基因列表文件 (.tsv)"),
  make_option(c("--genelistcol"),       type="integer",  default=1,
              help="基因列表文件中基因列索引，1‑based"),
  make_option(c("-s","--splitby"),      type="character", default="group",
              help="FeaturePlot/VlnPlot 分组字段"),
  make_option(c("-a","--defaultassay"), type="character", default="RNA",
              help="默认 assay 类型"),
  make_option(c("-t","--plottype"),     type="character", default="all",
              help="绘图类型: all|vlnplot|dotplot"),
  make_option(c("-e","--notitle"),      action="store_true", default=FALSE,
              help="基因列表文件第一行为标题则用 --notitle"),
  make_option("--plan", type="character", default=NULL,
              help="并行方案: multicore|multisession|sequential (默认自动判断)"),
  make_option(c("-v","--version"),      action="store_true", default=FALSE,
              help="显示版本并退出")
)
opt <- parse_args(OptionParser(option_list=option_list))
if (opt$version) { message("Version: ", VERSION); quit(save="no") }

# opt$infile <- "/opt/data1/develop/pancancer_sc/basic/PADC/GSE202051_18notreatment_25neoadjuvant/result/singlecell/2_cells_analysis/cells_analysis.anno.rds"
# opt$listname <- "weak,strong"
# opt$genelist <- "ARHGEF3,CYB561A3,DGKA,ELF1,ESYT2,EXOC1,LRCH4,MTMR1,MYO18A,MYO9B,NUMB,PTK2B,RALGPS2,SCRIB,SLC44A2,SLK,TCF7"


## ────────────────────── 2. 并行设置 ──────────────────────
choose_plan <- function(workers) {
  # 用户可用 --plan multicore/multisession/sequential 手动覆盖
  if (!is.null(opt$plan)) return(tolower(opt$plan))

  os_is_mac <- grepl("darwin", R.version$os, ignore.case = TRUE)
  if (workers <= 1)        return("sequential")
  if (os_is_mac)           return("multisession")  # 避开 fork 崩溃
  if (future::supportsMulticore()) return("multicore")
  "multisession"
}

plan_name <- choose_plan(opt$ncpus)
message(sprintf(">>> future::plan(%s, workers = %d)", plan_name, opt$ncpus))
if (plan_name == "multicore") {
  future::plan(multicore,   workers = opt$ncpus)
} else if (plan_name == "multisession") {
  future::plan(multisession, workers = opt$ncpus)
} else {
  future::plan(sequential)
}
registerDoParallel(cores = ifelse(plan_name == "sequential", 1, opt$ncpus))
options(future.globals.maxSize = opt$MaxMemMega * 1024^2)


## ────────────────────── 3. 读取与精简 Seurat 对象 ──────────────────────
flog.info("[1/4] Loading Seurat object: %s", opt$infile)
sc.full <- readRDS(opt$infile)        # 保留完整对象，供 Heatmap 等高维度展示
DefaultAssay(sc.full) <- opt$defaultassay

flog.info("[2/4] DietSeurat 以减小内存占用…")
sc.slim <- DietSeurat(
  sc.full,
  assays    = opt$defaultassay,
  layers    = c("counts", "data"),
#   layers    = c("counts", "data", "scale.data"),
  dimreducs = c("umap", "tsne"),
  graphs    = FALSE,
  misc      = FALSE
)


## 后续绘图全部对 slim 版操作，以节省内存 / 速度
sc <- sc.slim
rm(sc.slim)  # 防止误用

## ────────────────────── 4. 元数据预处理 ──────────────────────
DefaultAssay(sc) <- opt$defaultassay
Idents(sc)       <- Idents(sc.full)               # 继承身份
sc$celltype.group <- paste(Idents(sc), sc$group, sep = "_")
sc$celltype       <- Idents(sc)

listnames  <- if (nzchar(opt$listname)) strsplit(opt$listname, ",")[[1]] else unique(sc$group)
groupnum   <- length(unique(listnames))
clusternum <- length(unique(Idents(sc)))

## ────────────────────── 5. 获取基因列表 ──────────────────────
genes.to.show <- character()
if (nzchar(opt$genelist)) {
  genes.to.show <- strsplit(opt$genelist, ",")[[1]]
}
if (nzchar(opt$genelistfile)) {
  gn <- read.table(opt$genelistfile,
                   header = !opt$notitle, sep = "\t", quote = "",
                   check.names = FALSE, comment.char = "")
  genes.to.show <- unique(c(genes.to.show, gn[[opt$genelistcol]]))
}
genes.to.show <- unique(toupper(trimws(genes.to.show)))
if (length(genes.to.show) == 0)
  stop("--genelist/--genelistfile 均为空，无法绘图", call. = FALSE)

## ────────────────────── 6. 公共主题 & 工具函数 ──────────────────────
theme_paper <- theme(
  panel.grid.major    = element_line(linewidth = 0.1, linetype = "dashed"),  # ✅ 使用 linewidth
  legend.key          = element_rect(fill = 'white', color = 'white'),
  legend.key.size     = unit(0.5, "cm"),
  legend.position.inside = c(0.2, 0.88),
  legend.title        = element_blank(),
  legend.background   = element_blank(),
  panel.grid.minor    = element_blank(),
  plot.margin         = margin(0.5, 1, 0.5, 1, unit = "cm"),
  legend.text         = element_text(size = 11),
  axis.title          = element_text(size = 12),
  plot.title          = element_text(size = 12, face = "bold"),
  axis.text           = element_text(size = 11, colour = "black")
)
theme_set(theme_paper)

## 快捷导出函数 ----------------------------------------------------------
save_plot <- function(p, filename.base, width.mm, height.mm) {
  ## 自动裁切，限制高度≤2700 mm
  height.mm <- min(height.mm, 2700)
  ## PNG
  png(paste0(filename.base, ".png"),
      width = width.mm, height = height.mm,
      units = "mm", res = 300, pointsize = 2)
  print(p); dev.off()
  ## PDF
  ggsave(paste0(filename.base, ".pdf"), plot = p,
         width = width.mm/25.4, height = height.mm/25.4, units = "in")
}

dir.create("UMAP_byGroup", showWarnings = FALSE, recursive = TRUE)
dir.create("UMAP_global", showWarnings = FALSE, recursive = TRUE)
dir.create("DotPlot_single", showWarnings = FALSE, recursive = TRUE)
dir.create("DotPlot_multi", showWarnings = FALSE, recursive = TRUE)
dir.create("VlnPlot", showWarnings = FALSE, recursive = TRUE)
dir.create("Heatmap", showWarnings = FALSE, recursive = TRUE)


## ────────────────────── 7. 单基因绘图函数 ──────────────────────
plot_one_gene <- function(gene, splitby = opt$splitby) {
  # UMAP 按组
  p.umap.g <- FeaturePlot_scCustom(
    sc, reduction = "umap", features = gene,
    split.by = splitby, raster = FALSE,
    alpha_exp = .75
  )
  save_plot(p.umap.g,
            filename.base = file.path("UMAP_byGroup", paste0("featureplot_bygroup_", gene)),
            width.mm = groupnum * 100, height.mm = 100)

  # UMAP 不分组
  p.umap <- FeaturePlot_scCustom(sc, reduction = "umap",
                                 features = gene, raster = FALSE,
                                 alpha_exp = .75)
  save_plot(p.umap,
            filename.base = file.path("UMAP_global", paste0("featureplot_", gene)),
            width.mm = 125, height.mm = 100)

  # 小提琴图：by cluster / celltype / group
  vln <- function(group.by, prefix, w.factor)
  {
    p <- VlnPlot_scCustom(sc, features = gene,
                          group.by = group.by, split.by = splitby,
                          pt.size = 0) +
         theme(axis.text.x = element_text(angle = 45, hjust = 1))
    group.n <- length(unique(sc[[group.by]][,1]))
    save_plot(p,
              filename.base = file.path("VlnPlot", sprintf("vln_%s_%s", prefix, gene)),
              width.mm = w.factor * group.n + 25,
              height.mm = 100)
  }
  vln("seurat_clusters", "cluster", 25)
  vln("customclassif",  "celltype", 30)
  vln(splitby,          "group",    37.5)
}

## DotPlot（单基因） -----------------------------------------------------
plot_one_gene_dotplot <- function(gene) {
  sc$customclassif_group <- paste(sc$customclassif, sc$group, sep = "-")

  dot <- DotPlot(sc, features = gene,
                 group.by = "customclassif_group",
                 cols = brewer.pal(5, "Reds")) +
         theme(axis.text.x = element_text(angle = 45, hjust = 1))
  save_plot(dot,
            filename.base = file.path("DotPlot_single", paste0("dotplot_", gene)),
            width.mm = 150, height.mm = 200)

  ## 原始数据导出
  write.table(dot$data,
              file = paste0("DotPlot_single/",gene, "_dotplot.data.tsv"),
              sep = "\t", quote = FALSE, row.names = FALSE)
}

## DotPlot（多基因） ------------------------------------------------------
plot_multi_dot <- function(idents.field, prefix, flip = FALSE) {
  Idents(sc) <- idents.field
  p <- DotPlot_scCustom(seurat_object = sc,
                        features = genes.to.show,
                        flip_axes = flip,
                        x_lab_rotate = !flip,
                        colors_use = viridis_plasma_dark_high)
  if (flip) {
    w <- .6 * length(unique(Idents(sc))) + 100/25.4
    h <- .4 * length(genes.to.show) + 100/25.4
  } else {
    w <- .4 * length(genes.to.show) + 100/25.4
    h <- .4 * length(unique(Idents(sc))) + 100/25.4
  }
  ggsave(sprintf("%s.pdf", prefix), p, width = w, height = h)
  ggsave(sprintf("%s.png", prefix), p, width = w, height = h, dpi = 300)
}

## Heatmap --------------------------------------------------------------
plot_heatmap <- function() {
  # step 1: 聚合表达
  avg_exp <- AggregateExpression(sc.full,
                                 group.by = opt$splitby,
                                 assays = opt$defaultassay,
                                 return.seurat = FALSE,
                                 slot = "data")[[1]]

  # step 2: 选择存在的基因
  top.genes <- intersect(genes.to.show, rownames(avg_exp))
  if (length(top.genes) < 2) {
    warning("Heatmap 至少需要 ≥2 个基因，已跳过"); return(invisible(NULL))
  }

  exp.mat <- as.matrix(avg_exp[top.genes, ])

  # step 3: 标准化每行（可选）
  exp.mat.scaled <- t(scale(t(exp.mat)))

  # step 4: 绘图并保存
  library(pheatmap)
  dir.create("Heatmap", showWarnings = FALSE)
  pheatmap::pheatmap(exp.mat.scaled,
                     color = colorRampPalette(rev(brewer.pal(n = 7, name = "RdBu")))(100),
                     cluster_rows = TRUE,
                     cluster_cols = TRUE,
                     border_color = NA,
                     fontsize = 10,
                     filename = "Heatmap/heatmap_scaled_expression.pdf",
                     width = 5, height = max(4, 0.2 * nrow(exp.mat)))
  png("Heatmap/heatmap_scaled_expression.png", width = 1500, height = 1000, res = 300)
  pheatmap::pheatmap(exp.mat.scaled,
                     color = colorRampPalette(rev(brewer.pal(n = 7, name = "RdBu")))(100),
                     cluster_rows = TRUE,
                     cluster_cols = TRUE,
                     border_color = NA,
                     fontsize = 10)
  dev.off()
}


## ────────────────────── 8. 主控函数 ──────────────────────
run_vlnplot <- function() {
  dir.create("VlnPlot", showWarnings = FALSE)
  future_lapply(genes.to.show, plot_one_gene)
}

run_dotplot <- function(onlydotplot = FALSE) {
  dir.create("DotPlot_multi", showWarnings = FALSE)
  plot_multi_dot("seurat_clusters", "DotPlot_multi/cluster")
  plot_multi_dot("customclassif",   "DotPlot_multi/celltype")
  sc$cellclass_group <- paste(sc$customclassif, sc$group, sep = "_")
  plot_multi_dot("cellclass_group", "DotPlot_multi/celltype_group")
  plot_multi_dot("group", "DotPlot_multi/group")
  plot_multi_dot("replicate", "DotPlot_multi/sample")
  plot_multi_dot(opt$splitby, "DotPlot_multi/custome")
  if (!onlydotplot) {
    dir.create("DotPlot_single", showWarnings = FALSE)
    future_lapply(genes.to.show, plot_one_gene_dotplot)
  }
}

## ────────────────────── 9. 调度执行 ──────────────────────
flog.info("[3/4] 开始绘图 (%s)…", opt$plottype)

if (opt$plottype == "vlnplot") {
  run_vlnplot()
} else if (opt$plottype == "dotplot") {
  run_dotplot(onlydotplot = TRUE)
} else {                    # all
  run_vlnplot()
  run_dotplot()
  plot_heatmap()
}

flog.info("[4/4] 所有绘图完成！输出位于 %s", getwd())
################################################################################
