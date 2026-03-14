#!/usr/bin/env Rscript
################################################################################
## single‑cell gene‑visualisation pipeline – memory‑optimised  (v3.1.0‑lite)
## Author: Chao Cheng <chengchao@biosalt.cc>
################################################################################
suppressPackageStartupMessages({
  library(optparse); library(futile.logger); library(dplyr)
  library(ggplot2);   library(patchwork);   library(cowplot)
  library(Seurat);    library(scCustomize); library(stringr)
  library(future.apply); library(doParallel)
})

VERSION <- "3.1.0‑lite"

## ─────────────────────── 1. 参数解析 ───────────────────────
option_list <- list(
  make_option(c("-f","--infile"),        type="character", help="*.rds file"),
  make_option(c("-n","--ncpus"),         type="integer",  default=4),
  make_option(c("--MaxMemMega"),         type="integer",  default=100000,
              help="future.globals.maxSize in MB"),
  make_option(c("-l","--listname"),      type="character", default=""),
  make_option(c("-g","--genelist"),      type="character", default=""),
  make_option(c("-m","--genelistfile"),  type="character", default=""),
  make_option(c("--genelistcol"),        type="integer",  default=1),
  make_option(c("-s","--splitby"),       type="character", default="group"),
  make_option(c("-a","--defaultassay"),  type="character", default="RNA"),
  make_option(c("-t","--plottype"),      type="character",
              default="all", help="all|vlnplot|dotplot"),
  make_option(c("-e","--notitle"),       action="store_true", default=FALSE),
  make_option(c("-v","--version"),       action="store_true", default=FALSE)
)
opt <- parse_args(OptionParser(option_list=option_list))

if (opt$version) { message("Version: ", VERSION); quit(save="no") }

## ─────────────────────── 2. 并行设置 ───────────────────────
## 智能选择 future plan – 兼容 Linux / macOS(Apple Silicon) / Windows
supports_mc <- future::supportsMulticore()   # TRUE on macOS & Linux, FALSE on Windows

if (opt$ncpus == 1) {
  future::plan(sequential)
  registerDoParallel(cores = 1)

} else {
  ## Windows 或 RStudio/macOS GUI → 用 multisession，避免 fork 问题
  future::plan(multisession, workers = opt$ncpus)
}

## 自动推算允许的最大对象 (加 10% buffer)
options(future.globals.maxSize = opt$MaxMemMega * 1024^2 * 1.1)

## ─────────────────────── 3. 数据读取 + 精简 ─────────────────
flog.info("Loading Seurat object: %s", opt$infile)
sc.combined <- readRDS(opt$infile)
DefaultAssay(sc.combined) <- opt$defaultassay
## 仅保留需要的 assay 与 umap/tsne，其他全部裁掉
sc.combined <- DietSeurat(
  sc.combined,
  assays       = opt$defaultassay,
  counts       = TRUE,
  data         = TRUE,
  scale.data   = FALSE,
  dimreducs    = c("umap", "tsne"),
  graphs       = FALSE,
  misc         = FALSE
)


## 主题设置
theme_paper <- theme(
    # panel.border = element_rect(fill = NA,colour = "black"),
    panel.grid.major = element_line(linewidth = 0.1, linetype = "dashed"),
    # panel.grid.minor = element_line(
    #     colour = "grey90",
    #     size = 0.2,
    #     linetype = "dashed"
    # ),
    # axis.text.x= element_text(vjust = 1,hjust = 1, angle = 45, size = 5),
    # legend.position.inside = "top",
    # legend.direction = "horizontal",
    legend.key = element_rect(fill = 'white', color = 'white'),
    legend.key.size = unit(0.5, "cm"),
    legend.position.inside = c(0.2, 0.88),
    # legend.position.inside = "top",
    # legend.direction = "horizontal",
    legend.title = element_blank(),
    legend.background = element_blank(),
    panel.grid.minor = element_blank(),
    plot.margin = margin(0.5, 1, 0.5, 1, unit = "cm"),
    legend.text = element_text(size = 11),
    axis.title = element_text(size = 12),
    plot.title = element_text(size = 12, face = "bold"),
    axis.text = element_text(size = 11, colour = "black")
)

## 测试参数
# We start by reading in the data. The Read10X function reads in the output of the cellranger pipeline from 10X, returning a unique molecular identified (UMI) count matrix. The values in this matrix represent the number of molecules for each feature (i.e. gene; row) that are detected in each cell (column).
# opt$listname <- "AML,AML,AML,AML,AML,AML,AML,AML,healthy,healthy,healthy,healthy"
# opt$genelist <- "SDAD1,QRSL1,ZFP36L2,NOSIP,REXO2,POLR2A,TRMT13,NUFIP2,SPAG9,PRDX2"
# opt$infile <- "/mnt/beegfs/basic/single-cell/RX-7710426_AML/basic/SC_pipeline_20211022/result/singlecell/2_cells_analysis/cells_analysis.rds"

#####################################################################################
## preprocessing数据读取，数据对象建立
# We start by reading in the data. The Read10X function reads in the output of the cellranger pipeline from 10X, returning a unique molecular identified (UMI) count matrix. The values in this matrix represent the number of molecules for each feature (i.e. gene; row) that are detected in each cell (column).
#####################################################################################

# Load the PBMC dataset

sc.combined.all <- readRDS(file = opt$infile)
sc.combined <- sc.combined.all

# keeps <- c(1,2,3,4,7,12,13,17,21,23,26,30,32,34)
# keeps <- c(1,3,4,7,12,13,17,21,32)
# sc.combined <- subset(sc.combined.all, idents= keeps)

# sc.combined <- subset(sc.combined, sc.combined$group= c("R13"))
# sc.combined <- subset(sc.combined, group= c("R52"))



clusternum <- length(unique(factor(Idents(sc.combined))))
DefaultAssay(sc.combined) <- opt$defaultassay
sc.idents.bak <- Idents(sc.combined)

sc.combined$celltype.group <- paste(Idents(sc.combined), sc.combined$group, sep = "_")
sc.combined$celltype <- Idents(sc.combined)

listnames <- strsplit(opt$listname,",")[[1]]
groupnum = length(unique(listnames))

theme_set(theme_cowplot())


#####################################################################################
## 单个基因展示
#####################################################################################

genes.to.show <- ""

if(opt$genelist!=""){
    genes.to.show <- strsplit(opt$genelist,",")[[1]]
}

if(opt$genelistfile!=""){
    glf=read.table(opt$genelistfile,header = T,com = '',sep = "\t",quote = NULL,check.names = F)
    if(opt$notitle){
        glf=read.table(opt$genelistfile,header = F,com = '',sep = "\t",quote = NULL,check.names = F)
    }
    genes.to.show <- glf[,opt$genelistcol]
    print(genes.to.show)
}


# genes.to.show = c("Ccn1", "Gfra2")


valid_genes   <- intersect(genes.to.show, rownames(sc.combined))
missing_genes <- setdiff(genes.to.show, rownames(sc.combined))
cat(sprintf(">> 有效基因: %d / %d\n", length(valid_genes), length(genes.to.show)))
if (length(missing_genes)){
  cat(">> 缺失基因 (显示 ≤30):\n",
      paste(head(missing_genes, 30), collapse = ", "), "\n")
}
if (length(valid_genes) == 0) stop("无有效基因！")

valid_genes.num = length(valid_genes)

# source("/Users/chengchao/biosource/besaltpipe/src/SingleCell/allsample/sc_genes_visualizations_function.r")
source("/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/sc_genes_visualizations_function.r")
# source("/root/biosource/besaltpipe/src/SingleCell/pipeline/sc_genes_visualizations_function.r")
# source("/users/chengc/work/pipeline/besaltpipe/src/SingleCell/allsample/sc_genes_umap_function.r")
# source("/users/chengc/work/pipeline/besaltpipe/src/SingleCell/allsample/sc_genes_visualizations_function_dotplot.r")

# sc.combined <- RenameIdents(sc.combined, `1` = "primordial", `3` = "antral/preovulatory", `4` = "preovulatory", `7` = "preovulatory", `12` = "primordial", `13` = "preovulatory", `17` = "preovulatory", `21` = "antral", `32` = "antral/primordial/preovulatory")
# sc.combined$celltype <- Idents(sc.combined)

if(opt$plottype=="vlnplot"){
    show_genes_vlnplot(valid_genes,valid_genes.num,groupnum,clusternum,"./",splitby=opt$splitby,assay=opt$defaultassay)
}

if(opt$plottype=="dotplot"){
    show_genes(valid_genes,valid_genes.num,groupnum,clusternum,"./",splitby=opt$splitby,assay=opt$defaultassay,onlydotplot=TRUE,grouplevel=listnames)
}

if(opt$plottype=="all"){
    show_genes(valid_genes,valid_genes.num,groupnum,clusternum,"./",splitby=opt$splitby,assay=opt$defaultassay,grouplevel=listnames)
}



#####################################################################################
## 两个基因的cell scatter plot方式展示
#####################################################################################
# gene1 = "Ccn1"
# gene2 = "Gfra2"
# show_pair_gene(gene1,gene2)


## 保存RDS

# saveRDS(sc.combined, file = "./genes_analysis.rds")
