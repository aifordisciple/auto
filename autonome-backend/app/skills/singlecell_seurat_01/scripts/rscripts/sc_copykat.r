#!/usr/bin/env Rscript

###Set VERSION
VERSION = "3.0.0"

args <- commandArgs(trailingOnly = TRUE)
if(length(args) == 1 && (args[1] == "-v" | args[1] == "--version")){
  message("Version: \n\t", VERSION, "\n")
  quit(status = 0)
}

####################################################################################
### Copyright (C) 2019-2022 by biosalt
####################################################################################
# 名称：single cell pipeline
# 描述：单细胞分析流程
# 作者：CHAO CHENG
# 创建时间：2020-10-15
# 联系方式：chengchao@biosalt.cc
####################################################################################
### 修改记录
####################################################################################
# Date           Version       Author            ChangeLog
# 2019-12-27      v1.0          chaocheng         修改测试版本
# 2020-10-15      v2.0          chaocheng         整合seurat
# 2021-3-8        v3.0          chaocheng         流程整合
#####################################################################################
#####################################################################################
#####参考说明
# https://osca.bioconductor.org/overview.html#quick-start
# https://satijalab.org/seurat/v3.2/mca.html
# https://satijalab.org/seurat/sc.combined3k_tutorial.html
# https://github.com/CostaLab/scrna_seurat_pipeline
#####################################################################################




#####################################################################################
#####参数获取
#####################################################################################
# windows系统检查当前程序路径
# script.dir <- dirname(sys.frame(1)$ofile)

setwd("./")
# setwd("/data1/scRNA_data/DEV2020-10001_seurat/basic/mca")

suppressPackageStartupMessages(library(optparse))      ## Options
suppressPackageStartupMessages(library(futile.logger)) ## logger
suppressPackageStartupMessages(library("stats"))
suppressPackageStartupMessages(library(dplyr))
`%ni%` <- Negate(`%in%`)

# The Bioconductor package SingleCellExperiment provides the SingleCellExperiment class for usage. While the package is implicitly installed and loaded when using any package that depends on the SingleCellExperiment class, it can be explicitly installed (and loaded) as follows:
# install.packages("BiocManager")
# BiocManager::install(c('SingleCellExperiment','Rtsne','scater', 'scran', 'uwot'))

library("ggplot2")
# # library("factoextra")
# # library("FactoMineR")
# library("stats")
# library("ggthemes")
# library("reshape2")
# library("ggsci")

## old
library(SingleCellExperiment)
#library(scater)

library(tidyverse)
options(stringsAsFactors = FALSE)
library(grDevices)
library(gplots)
library(Seurat)
library(patchwork)
#library(metap)

library("future.apply")
suppressPackageStartupMessages(library(doParallel))

# library(purrr)

## 参数读取
option_list <- list(
    make_option(
        c("-n","--ncpus"),
        action = "store",
        type = "integer",
        default = 16,
        help = "parallel run number of cores"
    ),
    make_option(
        c("--MaxMemMega"),
        action = "store",
        type = "integer",
        default = 80000,
        help = "Parallel Max Memory size megabytes"
    ),
    make_option(
        c("-g", "--genome"),
        action = "store",
        type = "character",
        default = "hg20",
        help = "copyKAT genome, mm10 for mouse, hg20 for human-default"
    ),
    make_option(
        c("-r","--rdsfile"),
        action = "store",
        type = "character",
        default = "",
        help = "The data object rds file containing clusters"
    ),
    make_option(
        c("--keepcluster"),
        action = "store",
        type = "character",
        default = "",
        help = "keep clusters from raw seurat data. eg. 1,3,5"
    ),
    make_option(
        c("-s","--samplename"),
        action = "store",
        type = "character",
        default = "",
        help = "samplename"
    ),
    make_option(
        c("--export"),
        action = "store",
        type = "character",
        default = "false",
        help = "export count and exp file, skip when it is false"
    )
)
opt <- parse_args(OptionParser(option_list = option_list))



registerDoParallel(cores=opt$ncpus)
plan("multisession", workers = opt$ncpus)
options(future.globals.maxSize = opt$MaxMemMega * 1024^2)



## logger记录
if(!file.exists("logs")){
  dir.create("logs")
}

LOGNAME = "log-"
cur_date <- as.character(Sys.Date())
errorLog  =  file.path("logs", sprintf("%sERROR-%s.log", LOGNAME, cur_date))
warnLog   =  file.path("logs", sprintf("%sWARN-%s.log", LOGNAME, cur_date))
infoLog   =  file.path("logs",  sprintf("%sINFO-%s.log", LOGNAME, cur_date))
traceLog   =  file.path("logs",  sprintf("%sTRAC-%s.log", LOGNAME, cur_date))

invisible(flog.logger("error", ERROR, appender.file(errorLog)))
invisible(flog.logger("warn", WARN, appender.file(warnLog)))
invisible(flog.logger("info", INFO, appender.file(infoLog)))
invisible(flog.logger("trace", TRACE, appender.file(traceLog)))
invisible(flog.appender(appender.console(), name = "ROOT"))

logger.info <- function(msg, ...) {
  flog.info(msg, ..., name = "ROOT")
  flog.info(msg, ..., name = "info")
}

logger.warn <- function(msg, ...) {
  flog.warn(msg, ..., name = "ROOT")
  flog.warn(msg, ..., name = "info")
  flog.warn(msg, ..., name = "warn")
}

logger.error <- function(msg, ...) {
  flog.error(msg, ..., name = "ROOT")
  flog.error(msg, ..., name = "info")
  flog.error(msg, ..., name = "warn")
  flog.error(msg, ..., name = "error")
  flog.error(msg, ..., name = "trace")
}

## 主题设置
theme_paper <- theme(
    # panel.border = element_rect(fill = NA,colour = "black"),
    panel.grid.major = element_line(size = 0.1, linetype = "dashed"),
    # panel.grid.minor = element_line(
    #     colour = "grey90",
    #     size = 0.2,
    #     linetype = "dashed"
    # ),
    # axis.text.x= element_text(vjust = 1,hjust = 1, angle = 45, size = 5),
    # legend.position = "top",
    # legend.direction = "horizontal",
    legend.key = element_rect(fill = 'white', color = 'white'),
    legend.key.size = unit(0.5, "cm"),
    legend.position = c(0.2, 0.88),
    # legend.position = "top",
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


# opt$rdsfile <- "/data3/basic/single-cell/RX-7710490_bladder_cancer/basic/scRNAseq_PRJNA662018_GSE135337_20220624/result/singlecell/2_cells_analysis/cells_analysis.rds"
# opt$samplelist <- "normal1,normal2,normal3,BCN,patient1,patient2,patient3,patient4,patient5,patient6,patient7,patient8,BC1,BC2,BC3,BC4,BC5,BC6,BC7"


#####################################################################################
## preprocessing数据读取，数据对象建立
# We start by reading in the data. The Read10X function reads in the output of the cellranger pipeline from 10X, returning a unique molecular identified (UMI) count matrix. The values in this matrix represent the number of molecules for each feature (i.e. gene; row) that are detected in each cell (column).
#####################################################################################

# Load the sc.combined dataset

workdir = getwd()
# show_genes(showgene,showgenenum,groupnum,clusternum,prefix)

if(opt$rdsfile!=""){
  print("读取已有RDS数据")
  sc.combined <- readRDS(file = opt$rdsfile)
  # DefaultAssay(sc.combined) <- "integrated"
}

if(opt$rdsfile!="" & opt$keepcluster!=""){
  keeps <- strsplit(opt$keepcluster,",")[[1]]
  # keeps <- setdiff(unique(factor(Idents(sc.combined))), keepcluster)
  # print("keep clusters:")
  # print(keeps)
  # print("remove clusters:")
  # print(keepcluster)

  sc.combined <- subset(sc.combined, idents= keeps)

}

sc.combined <- subset(sc.combined, replicate==opt$samplename)

library(Seurat)
library(infercnv)

# 加载Seurat对象
# sc.combined <- readRDS("path_to_your_sc.combinedect.rds")

# 从Seurat对象中提取注释信息
annotations <- data.frame(Cell = colnames(sc.combined), 
                          CellType = sc.combined$customclassif)

# 确保注释的细胞名称与Seurat对象中的一致
if (!all(annotations$Cell %in% colnames(sc.combined))) {
  stop("Annotation file contains cells not present in the Seurat object.")
}

# 提取表达矩阵
expr_matrix <- as.matrix(GetAssayData(sc.combined, assay = "RNA", layer = "counts"))

# 保存表达矩阵和注释文件（infercnv的要求）
write.table(expr_matrix, "expr_matrix.txt", sep = "\t", quote = FALSE, col.names = NA)
write.table(annotations, "annotations.txt", sep = "\t", quote = FALSE, row.names = FALSE, col.names = FALSE)

# 确定参考细胞类型（T_NK和B细胞类型）
reference_cell_types <- unique(annotations$CellType[annotations$CellType %in% c("T_NK", "B")])

# 创建infercnv对象
infercnv_obj <- CreateInfercnvObject(
  raw_counts_matrix = "expr_matrix.txt",
  annotations_file = "annotations.txt",
  delim = "\t",
  gene_order_file = "path_to_gene_order_file.txt",  # 确保提供了正确的基因顺序文件
  ref_group_names = reference_cell_types
)

# 运行infercnv分析
infercnv_obj <- infercnv::run(
  infercnv_obj = infercnv_obj,
  cutoff = 0.1,  # 对低表达基因进行过滤
  out_dir = "infercnv_results",  # 输出目录
  cluster_by_groups = TRUE,
  denoise = TRUE,
  HMM = TRUE
)

# 生成热图
heatmap_file <- file.path("infercnv_results", "infercnv.heatmap.pdf")
if (file.exists(heatmap_file)) {
  cat("Heatmap generated: ", heatmap_file, "\n")
} else {
  cat("Heatmap generation failed. Check the infercnv output.")
}

# 输出预测文件
predicted_malignant_cells <- read.table("infercnv_results/infercnv.predicted.malignant_cells.txt", header = TRUE, sep = "\t")
write.table(predicted_malignant_cells, "predicted_malignant_cells.txt", sep = "\t", quote = FALSE, row.names = TRUE)

cat("Analysis completed. Results saved in 'infercnv_results' directory.")
