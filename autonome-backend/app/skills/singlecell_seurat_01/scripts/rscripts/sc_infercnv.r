#!/usr/bin/env Rscript

###Set VERSION
VERSION = "1.0.0"

args <- commandArgs(trailingOnly = TRUE)
if(length(args) == 1 && (args[1] == "-v" | args[1] == "--version")){
  message("Version: \n\t", VERSION, "\n")
  quit(status = 0)
}

####################################################################################
### Copyright (C) 2023-2033 by biosalt
####################################################################################
# 名称：infercnv分析
# 描述：单细胞分析流程
# 作者：CHAO CHENG
# 创建时间：2025-1-3
# 联系方式：chengchao@biosalt.cc
####################################################################################
### 修改记录
####################################################################################
# Date           Version       Author            ChangeLog
# 2025-1-3       v1.0          chaocheng         修改测试版本

#####################################################################################
#####################################################################################
#####参考说明
# https://zhuanlan.zhihu.com/p/625589597
# https://github.com/broadinstitute/inferCNV/wiki/instructions-create-genome-position-file
# https://github.com/broadinstitute/inferCNV/wiki/File-Definitions
#####################################################################################

#####################################################################################
#####参数获取
#####################################################################################
# windows系统检查当前程序路径
# script.dir <- dirname(sys.frame(1)$ofile)

setwd("./")

suppressPackageStartupMessages(library(optparse))      ## Options
suppressPackageStartupMessages(library(futile.logger)) ## logger
suppressPackageStartupMessages(library("stats"))
suppressPackageStartupMessages(library(dplyr))
`%ni%` <- Negate(`%in%`)


library("ggplot2")

## old
library(tidyverse)
options(stringsAsFactors = FALSE)
library(Seurat)
library(patchwork)

library("future.apply")
suppressPackageStartupMessages(library(doParallel))

## 参数读取
option_list <- list(
    make_option(
        c("-n","--ncpus"),
        action = "store",
        type = "integer",
        default = 4,
        help = "parallel run number of cores"
    ),
    make_option(
        c("--MaxMemMega"),
        action = "store",
        type = "integer",
        default = 80,
        help = "Parallel Max Memory size megabytes"
    ),
    make_option(
        c("-g", "--genepos"),
        action = "store",
        type = "character",
        default = "/opt/data1//public/genome/human/annotation/gencode_v38/human_gene_pos.txt",
        help = "/opt/data1//public/genome/human/annotation/gencode_v38/human_gene_pos.txt"
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
        c("--refcell"),
        action = "store",
        type = "character",
        default = "T_NK,B",
        help = "reference cell types, separated by commas (e.g., T_NK,B)"
    ),
    ## 新增：指定用作 celltype_col 的 meta 列名
    make_option(
        c("--celltype_col"),
        action = "store",
        type = "character",
        default = "customclassif",
        help = "metadata column name used as major cell type (default: celltype_col)"
    )
)
opt <- parse_args(OptionParser(option_list = option_list))



registerDoParallel(cores=opt$ncpus)
plan("multisession", workers = opt$ncpus)
options(future.globals.maxSize = opt$MaxMemMega * 1024^3)


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


# opt$rdsfile <- "/data1/project/NBioS-2024-08141-D_CC_sc_SF/basic/result/singlecell/2_cells_analysis/cells_analysis.rds"
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

library(Seurat)
library(infercnv)

# 加载Seurat对象
# sc.combined <- readRDS("path_to_your_sc.combinedect.rds")

# 从Seurat对象中提取注释信息（celltype_col 列名可通过参数指定）
annotations <- data.frame(
  Cell     = colnames(sc.combined),
  CellType = sc.combined@meta.data[[opt$celltype_col]]
)


# 确保注释的细胞名称与Seurat对象中的一致
if (!all(annotations$Cell %in% colnames(sc.combined))) {
  stop("Annotation file contains cells not present in the Seurat object.")
}

# 保存表达矩阵和注释文件（infercnv的要求）
# write.table(expr_matrix, "expr_matrix.txt", sep = "\t", quote = FALSE, col.names = NA)
write.table(annotations, "annotations.txt", sep = "\t", quote = FALSE, row.names = FALSE, col.names = FALSE)

# 提取表达矩阵
sc.combined[["RNA"]] = JoinLayers(sc.combined[["RNA"]])
expr_matrix <- as.matrix(GetAssayData(sc.combined, assay = "RNA", layer = "counts"))



# 确定参考细胞类型（通过参数指定）
ref_cell_types <- unlist(strsplit(opt$refcell, ","))
reference_cell_types <- unique(annotations$CellType[annotations$CellType %in% ref_cell_types])
cat(ref_cell_types, "\n")
cat(reference_cell_types, "\n")

options(scipen = 100)

# 创建infercnv对象
infercnv_obj <- CreateInfercnvObject(
  raw_counts_matrix = expr_matrix,
  annotations_file = "annotations.txt",
  delim = "\t",
  gene_order_file = opt$genepos,  # 确保提供了正确的基因顺序文件
  min_max_counts_per_cell = c(100, +Inf),
  ref_group_names = reference_cell_types
)

# 运行infercnv分析
# infercnv_obj <- infercnv::run(
#   infercnv_obj = infercnv_obj,
#   cutoff = 0.1,  # 对低表达基因进行过滤
#   out_dir = "infercnv_results",  # 输出目录
#   cluster_by_groups = FALSE,  # 按组聚类
#   denoise = TRUE,
#   num_threads = 24,
#   write_expr_matrix = TRUE,
#   HMM = FALSE
# )

infercnv_obj <- infercnv::run(
  infercnv_obj       = infercnv_obj,
  cutoff             = 0.1,
  out_dir            = "infercnv_results",
  cluster_by_groups  = TRUE,            # 只按注释分组聚类
  denoise            = TRUE,
  num_threads        = 24,
  HMM                = FALSE,
  write_expr_matrix  = TRUE,
  analysis_mode      = "samples"        # 关闭子聚类模式
)



# saveRDS(infercnv_obj,"infercnv_obj.rds")

# # 生成热图
# heatmap_file <- file.path("infercnv_results", "infercnv.heatmap.pdf")
# if (file.exists(heatmap_file)) {
#   cat("Heatmap generated: ", heatmap_file, "\n")
# } else {
#   cat("Heatmap generation failed. Check the infercnv output.")
# }

# # 输出预测文件
# predicted_malignant_cells <- read.table("infercnv_results/infercnv.predicted.malignant_cells.txt", header = TRUE, sep = "\t")
# write.table(predicted_malignant_cells, "predicted_malignant_cells.txt", sep = "\t", quote = FALSE, row.names = TRUE)

# 绘制箱线图显示 CNV 分布
# library(ggplot2)
# cnv_scores <- read.table("infercnv_results/infercnv.observations.txt", header = TRUE, row.names = 1, sep = "\t")
# cnv_scores$Cell <- rownames(cnv_scores)
# cnv_scores <- merge(cnv_scores, annotations, by = "Cell")

# ggplot(cnv_scores, aes(x = CellType, y = V1, fill = CellType)) +
#   geom_boxplot(outlier.shape = NA) +
#   geom_jitter(shape = 16, position = position_jitter(0.2), alpha = 0.6) +
#   theme_classic() +
#   labs(title = "CNV Scores by Cell Type",
#        x = "Cell Type",
#        y = "CNV Score") +
#   theme(axis.text.x = element_text(angle = 45, hjust = 1)) +
#   ggsave("CNV_Scores_Boxplot.pdf", width = 8, height = 6)

# cat("Analysis completed. Results saved in 'infercnv_results' directory.")
