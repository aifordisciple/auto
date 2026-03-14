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
# #library(metap)
library(clustree)

library(tidyverse)
library(patchwork)
# library(scCustomize)


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
        default = 180,
        help = "Parallel Max Memory size GB"
    ),
    make_option(
        c("-i", "--infile"),
        action = "store",
        type = "character",
        help = "sc processing rds file"
    ),
    make_option(
        c("-d", "--dims"),
        action = "store",
        type = "integer",
        default = 25,
        help = "PCA dims number"
    ),
    make_option(
        c("--resolution"),
        action = "store",
        type = "double",
        default = 0.6,
        help = "cluster resolution"
    ),
    make_option(
        c("-s","--samplelist"),
        action = "store",
        type = "character",
        default = "",
        help = "samplename1,samplename2,samplename3"
    ),
    make_option(
        c("-l","--listname"),
        action = "store",
        type = "character",
        default = "",
        help = "listname1,listname2,listname3"
    ),
    make_option(
        c("-b","--bdfiles"),
        action = "store",
        type = "character",
        help = "The count matrix file of sample"
    ),
    make_option(
        c("-t","--tissue"),
        action = "store",
        type = "character",
        default = "Immune system",
        help = "Immune system,Pancreas,Liver,Eye,Kidney,Brain,Lung,Embryo,Gastrointestinal tract,Muscle,Skin,Heart,Ovary,Testis,White adipose tissue,Teeth"
    ),
    make_option(
        c("-x","--dirs10x"),
        action = "store",
        type = "character",
        help = "10x UMI count data dir of sample, include 3 files"
    ),
    make_option(
        c("-a","--annofiles"),
        action = "store",
        type = "character",
        help = "The Annotation file of samples"
    ),
    make_option(
        c("--rdsfile"),
        action = "store",
        type = "character",
        default = "",
        help = "The data object rds file containing clusters"
    ),
    make_option(
        c("--rmcluster"),
        action = "store",
        type = "character",
        default = "",
        help = "remove clusters from raw seurat data. eg. 1,3,5"
    ),
    make_option(
        c("-k","--keeps"),
        action = "store",
        type = "character",
        default = "",
        help = "c1,c2,c3"
    ),
    make_option(
        c("--defaultassay"),
        action = "store",
        type = "character",
        default = "SCT",
        help = "default assay"
    ),
    make_option(
        c("--skipanno"),
        action = "store",
        type = "character",
        default = "false",
        help = "skip annotation"
    ),
    make_option(
        c("--sctypedb"),
        action = "store",
        type = "character",
        default = "/public/database/singlecell/sctype_markers/ScTypeDB_full.xlsx",
        help = "sctypedb"
    ),
    make_option(
        c("--skiptsne"),
        action = "store",
        type = "character",
        default = "false",
        help = "skip tsne"
    ),
    make_option(
        c("--noparallel"),
        action = "store",
        type = "character",
        default = "true",
        help = "no parallel"
    ),
    make_option(
        c("--export"),
        action = "store",
        type = "character",
        default = "false",
        help = "export count and exp file, skip when it is false"
    ),
    make_option(
        c("--cellanno"),
        action = "store",
        type = "character",
        default = "",
        help = "The cluster to cell type Annotation file"
    )
)
opt <- parse_args(OptionParser(option_list = option_list))



registerDoParallel(cores=opt$ncpus)

options(future.globals.maxSize = opt$MaxMemMega * 1024^3)

if(opt$noparallel=="false"){
  plan("multisession", workers = opt$ncpus)
}else{
  plan(sequential)
}



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

# opt$dims <- 50
# # opt$infile <- "/mnt/beegfs/basic/single-cell/RX-7710552-N_Treeshrew_immune/basic/scRNA-seq_other_species/mouse/result/singlecell/1_preprocessing/sc_preprocessing.rds"

# opt$rdsfile <- "/mnt/beegfs/basic/single-cell/RX-7710552-N_Treeshrew_immune/basic/scRNA-seq_20220610/result/singlecell/2_cells_analysis_res1.2/cells_analysis.rds"
# opt$samplelist <- "Lymph_1,Lymph_2,Lymph_3,Marrow_1,Marrow_2,Marrow_3,PBMC_1,PBMC_2,PBMC_3,Spleen_1,Spleen_2,Spleen_3,Thymus_1,Thymus_2,Thymus_3,Tonsil_1,Tonsil_2,Tonsil_3,Stomach_1,Nasopharyngeal_1,Lung_1,Liver_1,Kidney_1,Heart_1"
# opt$listname <- "Lymph,Lymph,Lymph,Marrow,Marrow,Marrow,PBMC,PBMC,PBMC,Spleen,Spleen,Spleen,Thymus,Thymus,Thymus,Tonsil,Tonsil,Tonsil,Stomach,Nasopharyngeal,Lung,Liver,Kidney,Heart"
# opt$resolution = 0.8
# opt$keeps = "43,49,50,8,26,36,46,41,9,45,62,6,20,33,52,55"
# opt$sctypedb = "/public/database/singlecell/sctype_markers/ScTypeDB_full.treeshrew.xlsx"
# opt$tissue = "Immune system"

# nohup Rscript /Users/chengchao/biosource/besaltpipe/src//SingleCell/allsample/sc_cells_analysis.r -s Marrow1,Marrow2,Heart1,Heart2,Kidney2,Kidney3,Liver1-1,Liver2,Lung1,Lung2,Peripheral-Blood1,Peripheral-Blood2,Spleen1-1,Spleen1-2,Stomach1,Stomach2,Thymus1,Thymus2,Tonsil_1,Tonsil_2 -l Marrow,Marrow,Heart,Heart,Kidney,Kidney,Liver,Liver,Lung,Lung,PBMC,PBMC,Spleen,Spleen,Stomach,Stomach,Thymus,Thymus,Tonsil,Tonsil -i /mnt/beegfs/basic/single-cell/RX-7710552-N_Treeshrew_immune/basic/scRNA-seq_other_species/mouse/result/singlecell/1_preprocessing/sc_preprocessing.rds -d 30 --sctypedb /public/database/singlecell/sctype_markers/ScTypeDB_full.treeshrew.xlsx -t "Treeshrew" --resolution 1.2 &


# opt$cellanno <- "/data3/basic/single-cell/RX2020-11003-VN_mouse_ovary/basic/SC_pipeline_20210610/cell_anno.txt"

# opt$dims <- 50
# opt$infile <- "/opt/data1/develop/pancancer_sc/basic/3_ccRCC/merge2_basic/result/singlecell/1_preprocessing/sc_preprocessing.rds"

# # opt$rdsfile <- "/opt/data1/develop/pancancer_sc/basic/3_ccRCC/merge2_basic/result/singlecell/1_preprocessing/sc_preprocessing.rds"
# opt$samplelist <- "D1_Tumor_1,D1_Tumor_2,D1_Tumor_3,D1_Tumor_4,D1_Tumor_5,D1_Tumor_6,D1_Tumor_7,D2_BM1-PTumor,D2_BM2-PTumor1,D2_BM2-PTumor2,D2_PR1-PTumor,D2_PR2-PTumor,D2_PR3-PTumor1,D2_PR3-PTumor2,D2_PR3-PTumor3,D2_PR5-PTumor1,D2_PR5-PTumor2,D2_PR5-PTumor3,D2_PR6-PTumor,D2_PR7-PTumor,D2_PR9-PTumor,D2_PR9-PTumor2,D3_p022_Tumoral,D3_p027_Tumoral,D3_p029_Tumoral,D4_RCC1,D4_RCC2,D4_RCC3,D4_RCC4,D4_RCC5,D5_T2_1,D5_T2_2,D5_T3_1,D5_T3_2,D5_T4_2,D5_T5_1,D5_T5_2,D5_T6_1,D5_T6_2,D5_T6_3,D5_T7_1,D5_T7_2,D5_T7_3,D5_T8_1,D5_T8_2,D5_T8_3,D5_T9_1,D5_T9_2,D5_T9_3,D6_T1,D6_T2,D6_T3,D6_T4,D6_T5,D6_T6,D6_T7,D7_RCC1t,D7_RCC2t,D7_RCC4t,D7_RCC5t,D7_RCC6t,D7_RCC7t,D8_RCC100,D8_RCC101,D8_RCC103,D8_RCC104,D8_RCC106,D8_RCC112,D8_RCC113,D8_RCC114,D8_RCC115,D8_RCC116,D8_RCC119,D8_RCC120,D8_RCC81,D8_RCC84,D8_RCC86,D8_RCC87,D8_RCC94,D8_RCC96,D8_RCC99,D1_Benign_1,D1_Benign_2,D1_Benign_3,D1_Benign_4,D1_Benign_5,D1_Benign_6,D2_BM1-Normal,D2_BM2-Normal,D2_PR1-Normal,D2_PR2-Normal,D2_PR3-Normal,D2_PR4-Normal,D2_PR5-Normal,D2_PR6-Normal,D2_PR8-Normal,D2_PR9-Normal,D3_p022_Juxta,D3_p027_Juxta,D3_p029_Juxta,D5_N1_1,D5_N2_1,D5_N2_2,D5_N3_2,D5_N4_2,D5_N5_1,D5_N6_1,D5_N7_1,D5_N8_1,D5_N9_1,D6_N1,D6_N2,D7_RCC1n,D7_RCC2n,D7_RCC3n,D7_RCC4n,D7_RCC5n"
# opt$listname <- "normal,tumor"
# opt$resolution = 0.6
# # opt$keeps = "43,49,50,8,26,36,46,41,9,45,62,6,20,33,52,55"
# opt$sctypedb = "/opt/data1/public/database/singlecell/sctype_marker_db.xlsx"
# opt$tissue = "ccRCC_L1"

# countfiles <- strsplit(opt$bdfiles,",")[[1]]
# annofiles <- strsplit(opt$annofiles,",")[[1]]
samplenames <- strsplit(opt$samplelist,",")[[1]]
listnames <- strsplit(opt$listname,",")[[1]]

groupnum = length(unique(listnames))
samplenum = length(unique(samplenames))

res = opt$resolution
# res = 0.6


#####################################################################################
## preprocessing数据读取，数据对象建立
# We start by reading in the data. The Read10X function reads in the output of the cellranger pipeline from 10X, returning a unique molecular identified (UMI) count matrix. The values in this matrix represent the number of molecules for each feature (i.e. gene; row) that are detected in each cell (column).
#####################################################################################

# Load the sc.combined dataset

if(opt$rdsfile==""){
  sc.combined <- readRDS(file = opt$infile)
}


#####################################################################################
## 基于图的聚类Cluster the cells

# Seurat v3 applies a graph-based clustering approach, building upon initial strategies in (Macosko et al). Importantly, the distance metric which drives the clustering analysis (based on previously identified PCs) remains the same. However, our approach to partioning the cellular distance matrix into clusters has dramatically improved. Our approach was heavily inspired by recent manuscripts which applied graph-based clustering approaches to scRNA-seq data [SNN-Cliq, Xu and Su, Bioinformatics, 2015] and CyTOF data [PhenoGraph, Levine et al., Cell, 2015]. Briefly, these methods embed cells in a graph structure - for example a K-nearest neighbor (KNN) graph, with edges drawn between cells with similar feature expression patterns, and then attempt to partition this graph into highly interconnected 'quasi-cliques' or 'communities'.

# As in PhenoGraph, we first construct a KNN graph based on the euclidean distance in PCA space, and refine the edge weights between any two cells based on the shared overlap in their local neighborhoods (Jaccard similarity). This step is performed using the FindNeighbors function, and takes as input the previously defined dimensionality of the dataset (first 10 PCs).

# To cluster the cells, we next apply modularity optimization techniques such as the Louvain algorithm (default) or SLM [SLM, Blondel et al., Journal of Statistical Mechanics], to iteratively group cells together, with the goal of optimizing the standard modularity function. The FindClusters function implements this procedure, and contains a resolution parameter that sets the 'granularity' of the downstream clustering, with increased values leading to a greater number of clusters. We find that setting this parameter between 0.4-1.2 typically returns good results for single-cell datasets of around 3K cells. Optimal resolution often increases for larger datasets. The clusters can be found using the Idents function.
#####################################################################################

# sc.combined <- FindNeighbors(sc.combined, dims = 1:10)
# sc.combined <- FindClusters(sc.combined, resolution = 0.5)

# Suggestions for large datasets
# The construction of the shared nearest neighbor graph is now fully implemented in C++, significantly improving performance.
# To further increase speed, you can employ an approximate nearest neighbor search via the RANN package by increasing the nn.eps parameter. Setting this at 0 (the default) represents an exact neighbor search.
# By default, we perform 100 random starts for clustering and select the result with highest modularity. You can lower this through the n.start parameter to reduce clustering time.

# sc.combined <- FindNeighbors(sc.combined, reduction = "harmony", dims = 1:opt$dims, nn.eps = 0.5)
workdir = getwd()
# show_genes(showgene,showgenenum,groupnum,clusternum,prefix)

sc_cluster_dir = paste(workdir,"/","sc_cluster", sep="")
if(!file.exists(sc_cluster_dir)){
  dir.create(sc_cluster_dir)
}
setwd(sc_cluster_dir)

if(opt$rdsfile!=""){
  print("读取已有RDS数据")
  sc.combined <- readRDS(file = opt$rdsfile)
  DefaultAssay(sc.combined) <- opt$defaultassay
}else{
  print("###开始进行cluster")
  DefaultAssay(sc.combined) <- opt$defaultassay
  sc.combined <- FindNeighbors(sc.combined, reduction = "harmony", dims = 1:opt$dims)



  # sc.combined <- FindClusters(sc.combined, resolution = 3, n.start = 10)
  # We will use the FindClusters() function to perform the graph-based clustering. The resolution is an important argument that sets the "granularity" of the downstream clustering and will need to be optimized for every individual experiment. For datasets of 3,000 - 5,000 cells, the resolution set between 0.4-1.4 generally yields good clustering. Increased resolution values lead to a greater number of clusters, which is often required for larger datasets.
  
  # Determine the clusters for various resolutions                                
  # sc.combined <- FindClusters(object = sc.combined,
  #                              resolution = c(0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6),seed=TRUE)


  # sc.combined <- FindClusters(sc.combined, resolution = seq(0.3,1.6,by=0.1),seed=TRUE)

  # p1 <- clustree(sc.combined)
  # pdf(file=paste("resolution_clustree",".pdf",sep=""),width = 20,height = 20)
  # print(p1)
  # dev.off()

  # png(file = paste("resolution_clustree",".png",sep=""),width = 500,height = 500,units = "mm",res = 300,pointsize = 1.5)
  # par(mar = c(5, 5, 2, 2), cex.axis = 1.5, cex.lab = 2)
  # print(p1)
  # dev.off()
  
  # head(sc.combined@meta.data)
  # # Assign identity of clusters
  # Idents(object = sc.combined) <- "integrated_snn_res.0.4"
  # print("resolution:0.4")
  # length(unique(factor(Idents(sc.combined))))
  # Idents(object = sc.combined) <- "integrated_snn_res.0.6"
  # print("resolution:0.6")
  # length(unique(factor(Idents(sc.combined))))
  # Idents(object = sc.combined) <- "integrated_snn_res.0.8"
  # print("resolution:0.8")
  # length(unique(factor(Idents(sc.combined))))
  # Idents(object = sc.combined) <- "integrated_snn_res.1"
  # print("resolution:1")
  # length(unique(factor(Idents(sc.combined))))
  # Idents(object = sc.combined) <- "integrated_snn_res.1.2"
  # print("resolution:1.2")
  # length(unique(factor(Idents(sc.combined))))
  # Idents(object = sc.combined) <- "integrated_snn_res.1.4"
  # print("resolution:1.4")
  # length(unique(factor(Idents(sc.combined))))
  # Idents(object = sc.combined) <- "integrated_snn_res.1.6"
  # print("resolution:1.6")
  # length(unique(factor(Idents(sc.combined))))
  
  sc.combined <- FindClusters(sc.combined, resolution = res)

  # sc.combined <- FindClusters(sc.combined, resolution = 1.6)

}

if(opt$rdsfile!="" & opt$rmcluster!=""){
  rmcluster <- strsplit(opt$rmcluster,",")[[1]]
  keeps <- setdiff(unique(factor(Idents(sc.combined))), rmcluster)
  print("keep clusters:")
  print(keeps)
  print("remove clusters:")
  print(rmcluster)

  sc.combined <- subset(sc.combined, idents= keeps)
  DefaultAssay(sc.combined) <- opt$defaultassay
}

if(opt$rdsfile!="" & opt$keeps!=""){
  keeps <- strsplit(opt$keeps,",")[[1]]
  print(keeps)
  sc.combined <- subset(sc.combined, idents= keeps)

  DefaultAssay(sc.combined) <- opt$defaultassay
  opt$rmcluster = "done"
}

if(opt$rdsfile!="" & opt$rmcluster!=""){

  print("###开始进行re-cluster")

  # 降维
  all.genes <- rownames(sc.combined)
  # sc.combined <- ScaleData(sc.combined, features = all.genes, verbose = FALSE, vars.to.regress = "percent.mt")
  sc.combined <- RunPCA(sc.combined, features = VariableFeatures(object = sc.combined), npcs = 100, ndims.print = 1:5, nfeatures.print = 5)

  # Seurat provides several useful ways of visualizing both cells and features that define the PCA, including VizDimReduction, DimPlot, and DimHeatmap
  p1 <- VizDimLoadings(sc.combined, dims = 1:2, reduction = "harmony")
  pdf(file=paste("VizPlot_PCA",".pdf",sep=""),width = 8,height = 5)
  p1
  dev.off()

  png(file = paste("VizPlot_PCA",".png",sep=""),width = 200,height = 125,units = "mm",res = 300,pointsize = 1.5)
  par(mar = c(5, 5, 2, 2), cex.axis = 1.5, cex.lab = 2)
  p1
  dev.off()


  p1 <- DimPlot(sc.combined, reduction = "harmony", group.by = "replicate", split.by = "group",pt.size = 0.01)
  pdf(file=paste("DimPlot_PCA",".pdf",sep=""),width = 4 * groupnum,height = 4)
  p1
  dev.off()

  png(file = paste("DimPlot_PCA",".png",sep=""),width = 100 * groupnum,height = 100,units = "mm",res = 300,pointsize = 2)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  p1
  dev.off()



  # In particular DimHeatmap allows for easy exploration of the primary sources of heterogeneity in a dataset, and can be useful when trying to decide which PCs to include for further downstream analyses. Both cells and features are ordered according to their PCA scores. Setting cells to a number plots the 'extreme' cells on both ends of the spectrum, which dramatically speeds plotting for large datasets. Though clearly a supervised analysis, we find this to be a valuable tool for exploring correlated feature sets.
  # DimHeatmap(sc.combined, dims = 1:2, cells = 500, balanced = TRUE)


  pdf(file=paste("DimHeatmap_PCA",".pdf",sep=""),width = 15,height = 10)
  DimHeatmap(sc.combined, dims = 1:9, cells = 500, balanced = TRUE)
  dev.off()

  png(file = paste("DimHeatmap_PCA",".png",sep=""),width = 450,height = 300,units = "mm",res = 300,pointsize = 15)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  DimHeatmap(sc.combined, dims = 1:9, cells = 500, balanced = TRUE)
  dev.off()


  pdf(file=paste("ElbowPlot",".pdf",sep=""),width = 10,height = 4)
  p1 <- ElbowPlot(sc.combined, ndims = 25)
  p2 <- ElbowPlot(sc.combined, ndims = 100)
  p1+p2
  dev.off()

  png(file = paste("ElbowPlot",".png",sep=""),width = 250,height = 100,units = "mm",res = 300,pointsize = 2)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  p1 <- ElbowPlot(sc.combined, ndims = 25)
  p2 <- ElbowPlot(sc.combined, ndims = 100)
  p1+p2
  dev.off()

  # opt$dims = 15

  sc.combined <- FindNeighbors(sc.combined, reduction = "harmony", dims = 1:opt$dims)
  # sc.combined <- FindClusters(sc.combined, resolution = 3, n.start = 10)
  # We will use the FindClusters() function to perform the graph-based clustering. The resolution is an important argument that sets the "granularity" of the downstream clustering and will need to be optimized for every individual experiment. For datasets of 3,000 - 5,000 cells, the resolution set between 0.4-1.4 generally yields good clustering. Increased resolution values lead to a greater number of clusters, which is often required for larger datasets.
  
  # Determine the clusters for various resolutions                                
  sc.combined <- FindClusters(object = sc.combined,
                               resolution = c(0.3, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6),seed=TRUE)
  # head(sc.combined@meta.data)
  # # Assign identity of clusters
  Idents(object = sc.combined) <- "integrated_snn_res.0.3"
  print("resolution:0.3")
  length(unique(factor(Idents(sc.combined))))
  Idents(object = sc.combined) <- "integrated_snn_res.0.4"
  print("resolution:0.4")
  length(unique(factor(Idents(sc.combined))))
  Idents(object = sc.combined) <- "integrated_snn_res.0.6"
  print("resolution:0.6")
  length(unique(factor(Idents(sc.combined))))
  Idents(object = sc.combined) <- "integrated_snn_res.0.8"
  print("resolution:0.8")
  length(unique(factor(Idents(sc.combined))))
  Idents(object = sc.combined) <- "integrated_snn_res.1"
  print("resolution:1")
  length(unique(factor(Idents(sc.combined))))
  Idents(object = sc.combined) <- "integrated_snn_res.1.2"
  print("resolution:1.2")
  length(unique(factor(Idents(sc.combined))))
  Idents(object = sc.combined) <- "integrated_snn_res.1.4"
  print("resolution:1.4")
  length(unique(factor(Idents(sc.combined))))
  Idents(object = sc.combined) <- "integrated_snn_res.1.6"
  print("resolution:1.6")
  length(unique(factor(Idents(sc.combined))))
  # res = 0.4
  sc.combined <- FindClusters(sc.combined, resolution = res)
  # sc.combined <- FindClusters(sc.combined, resolution = 1.6)
}
if(opt$rdsfile=="" & opt$rmcluster!=""){
  rmcluster <- strsplit(opt$rmcluster,",")[[1]]
  keeps <- setdiff(unique(factor(Idents(sc.combined))), rmcluster)
  print("keep clusters:")
  print(keeps)
  print("remove clusters:")
  print(rmcluster)

  sc.combined <- subset(sc.combined, idents= keeps)

  DefaultAssay(sc.combined) <- opt$defaultassay
}

if(opt$export!="false"){
  # write.table(sc.combined, "sc_count.txt", row.names=F, sep='\t')
  gz1 <- gzfile("Gene_Count_per_Cell.tsv.gz", "w")
  write.table(sc.combined@assays[["RNA"]]@counts, file=gz1, quote=FALSE, sep='\t', col.names = TRUE)
  gz2 <- gzfile("Gene_Exp_per_Cell.tsv.gz", "w")
  write.table(sc.combined@assays[["RNA"]]@data, file=gz2, quote=FALSE, sep='\t', col.names = TRUE)
}
head(Idents(sc.combined), 5)

#####################################################################################
## UMAP/tSNE聚类Run non-linear dimensional reduction (UMAP/tSNE)
# Seurat offers several non-linear dimensional reduction techniques, such as tSNE and UMAP, to visualize and explore these datasets. The goal of these algorithms is to learn the underlying manifold of the data in order to place similar cells together in low-dimensional space. Cells within the graph-based clusters determined above should co-localize on these dimension reduction plots. As input to the UMAP and tSNE, we suggest using the same PCs as input to the clustering analysis.
#####################################################################################

# # If you haven't installed UMAP, you can do so via reticulate::py_install(packages =
# # 'umap-learn')
# sc.combined <- RunUMAP(sc.combined, dims = 1:10)
# 
# # note that you can set `label = TRUE` or use the LabelClusters function to help label individual clusters
# DimPlot(sc.combined, reduction = "umap")
# 
# ## tSNE
# sc.combined <- RunTSNE(sc.combined, dims = 1:10)
# DimPlot(sc.combined, reduction = "tsne")
# 
# 
# sc.combined <- RunTSNE(sc.combined, dims = 1:75, nthreads = 16, max_iter = 2000)
if(opt$rdsfile==""){
  ## large data
  if(opt$skiptsne=="false"){
    sc.combined <- RunTSNE(sc.combined, dims = 1:opt$dims, tsne.method = "FIt-SNE", nthreads = 16, max_iter = 2000, reduction = "harmony")
  }
  
  # sc.combined <- RunUMAP(sc.combined, dims = 1:opt$dims, min.dist = 0.75)
  sc.combined <- RunUMAP(sc.combined, dims = 1:opt$dims, reduction = "harmony")
}

if(opt$rdsfile!="" & opt$rmcluster!=""){
  ## large data
  if(opt$skiptsne=="false"){
    sc.combined <- RunTSNE(sc.combined, dims = 1:opt$dims, tsne.method = "FIt-SNE", nthreads = 16, max_iter = 2000, reduction = "harmony")
  }
  # sc.combined <- RunUMAP(sc.combined, dims = 1:opt$dims, min.dist = 0.75)
  sc.combined <- RunUMAP(sc.combined, dims = 1:opt$dims, reduction = "harmony")
}

#####################################################################################
## 细胞周期分析
#####################################################################################

# s.genes
# g2m.genes
# sc.combined <- CellCycleScoring(sc.combined, s.features = s.genes, g2m.features = g2m.genes, set.ident = FALSE)


#####################################################################################
## 聚类结果可视化
#####################################################################################

plot_cluster <- function(){
  if(opt$skiptsne=="false"){
  ## tsne
  p1 <- DimPlot(sc.combined, reduction = "tsne", group.by = "replicate", pt.size = 0.1)
  p2 <- DimPlot(sc.combined, reduction = "tsne", group.by = "group", pt.size = 0.1)
  p3 <- DimPlot(sc.combined, reduction = "tsne", label = TRUE, pt.size = 0.1)
  # p1 <- AugmentPlot(plot = p1)
  # p2 <- AugmentPlot(plot = p2)

  pdf(file=paste("tsne_cluster","pdf",sep="."),width = 18,height = 5)
  # p1 <- DimPlot(sc.combined, reduction = "tsne", pt.size = 0.1, label = TRUE) + ggtitle(label = "FIt-SNE")
  # p1 <- AugmentPlot(plot = p1)
  print((p1+p2+p3) + theme_paper)
  dev.off()

  png(file = paste("tsne_cluster",".png",sep=""),width = 450,height = 125,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  # p1 <- DimPlot(sc.combined, reduction = "tsne", pt.size = 0.1, label = TRUE) + ggtitle(label = "FIt-SNE")
  # p1 <- AugmentPlot(plot = p1)
  print((p1+p2+p3) + theme_paper)
  dev.off()
  }

  ## umap
  p1 <- DimPlot(sc.combined, reduction = "umap", group.by = "replicate", pt.size = 0.1)
  p2 <- DimPlot(sc.combined, reduction = "umap", group.by = "group", pt.size = 0.1)
  p3 <- DimPlot(sc.combined, reduction = "umap", label = TRUE, pt.size = 0.1)
  # p1 <- AugmentPlot(plot = p1)
  # p2 <- AugmentPlot(plot = p2)

  pdf(file=paste("umap_cluster","pdf",sep="."),width = 18,height = 5)
  print((p1+p2+p3) + theme_paper)
  # p1 <- DimPlot(sc.combined, reduction = "umap", pt.size = 0.1, label = TRUE) + ggtitle(label = "UMAP")
  # p1 <- AugmentPlot(plot = p1)
  # (p1)
  dev.off()

  png(file = paste("umap_cluster",".png",sep=""),width = 450,height = 125,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1+p2+p3)
  # p1 <- DimPlot(sc.combined, reduction = "umap", pt.size = 0.1, label = TRUE) + ggtitle(label = "UMAP")
  # p1 <- AugmentPlot(plot = p1)
  # (p1)
  dev.off()

  if(opt$skiptsne=="false"){
  ## tsne和umap一起展示
  p1 <- DimPlot(sc.combined, reduction = "tsne", pt.size = 0.1, label = TRUE) + ggtitle(label = "FIt-SNE")
  p2 <- DimPlot(sc.combined, reduction = "umap", pt.size = 0.1, label = TRUE) + ggtitle(label = "UMAP")
  # p1 <- AugmentPlot(plot = p1)
  # p2 <- AugmentPlot(plot = p2)

  pdf(file=paste("tsne_umap","pdf",sep="."),width = 12,height = 5)
  print((p1 + p2) + theme_paper)
  dev.off()

  png(file = paste("tsne_umap",".png",sep=""),width = 300,height = 125,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print((p1 + p2) + theme_paper)
  dev.off()
  }

  ## 按照group展示cluster

  p1 <- DimPlot(sc.combined, reduction = "umap", group.by = "replicate", split.by = "group", pt.size = 0.1, label = TRUE)
  # p1 <- AugmentPlot(plot = p1)

  pdf(file=paste("umap_cluster_bygroup","pdf",sep="."),width = 4 * groupnum, height = 4)
  print(p1)
  dev.off()

  png(file = paste("umap_cluster_bygroup",".png",sep=""),width = 100 * groupnum, height = 100,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1)
  dev.off()

  p1 <- DimPlot(sc.combined, reduction = "umap", split.by = "replicate", pt.size = 0.1, label = TRUE)
  # p1 <- AugmentPlot(plot = p1)
if(samplenum<10){
  pdf(file=paste("umap_cluster_byreplicate","pdf",sep="."),width = 4 * samplenum, height = 4)
  print(p1)
  dev.off()

  png(file = paste("umap_cluster_byreplicate",".png",sep=""),width = 100 * samplenum, height = 100,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1)
  dev.off()
}

if(opt$skiptsne=="false"){
  p1 <- DimPlot(sc.combined, reduction = "tsne", group.by = "replicate", split.by = "group", pt.size = 0.1, label = TRUE)
  # p1 <- AugmentPlot(plot = p1)

  pdf(file=paste("tsne_cluster_bygroup_byreplicate","pdf",sep="."),width = 4 * groupnum, height = 4)
  print(p1)
  dev.off()

  png(file = paste("tsne_cluster_bygroup_byreplicate",".png",sep=""),width = 100 * groupnum, height = 100,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1)
  dev.off()
}

  p1 <- DimPlot(sc.combined, reduction = "umap", split.by = "group", pt.size = 0.1, label = TRUE)
  # p1 <- AugmentPlot(plot = p1)

  pdf(file=paste("umap_cluster_bygroup_bycelltype","pdf",sep="."),width = 4 * groupnum, height = 4)
  print(p1)
  dev.off()

  png(file = paste("umap_cluster_bygroup_bycelltype",".png",sep=""),width = 100 * groupnum, height = 100,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1)
  dev.off()

if(opt$skiptsne=="false"){
  p1 <- DimPlot(sc.combined, reduction = "tsne", split.by = "group", pt.size = 0.1, label = TRUE)
  # p1 <- AugmentPlot(plot = p1)

  pdf(file=paste("tsne_cluster_bygroup_bycelltype","pdf",sep="."),width = 4 * groupnum, height = 4)
  print(p1)
  dev.off()

  png(file = paste("tsne_cluster_bygroup_bycelltype",".png",sep=""),width = 100 * groupnum, height = 100,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1)
  dev.off()
}
  # p1 <- DimPlot(sc.combined, reduction = "umap", split.by = "replicate", pt.size = 0.1, label = TRUE)
  # # p1 <- AugmentPlot(plot = p1)

  # pdf(file=paste("umap_cluster_byreplicate_bycelltype","pdf",sep="."),width = 4 * samplenum, height = 4)
  # print(p1)
  # dev.off()

  # png(file = paste("umap_cluster_byreplicate_bycelltype",".png",sep=""),width = 100 * samplenum, height = 100,units = "mm",res = 300,pointsize = 10)
  # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  # print(p1)
  # dev.off()


  # p1 <- DimPlot(sc.combined, reduction = "tsne", split.by = "replicate", pt.size = 0.1, label = TRUE)
  # # p1 <- AugmentPlot(plot = p1)

  # pdf(file=paste("tsne_cluster_byreplicate_bycelltype","pdf",sep="."),width = 4 * samplenum, height = 4)
  # print(p1)
  # dev.off()

  # png(file = paste("tsne_cluster_byreplicate_bycelltype",".png",sep=""),width = 100 * samplenum, height = 100,units = "mm",res = 300,pointsize = 10)
  # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  # print(p1)
  # dev.off()
}

# plot_cluster()

## 回到工作根目录
setwd(workdir)


if(opt$skipanno=="true"){
  sc.combined$customclassif <- paste("C", Idents(sc.combined), sep = "")
}else{
## 注释


# assign cell types
# sc.combined = readRDS(opt$infile); #load example scRNA-seq matrix

sctype_dir = paste("","sctype", sep="")
if(!file.exists(sctype_dir)){
    dir.create(sctype_dir)
}
setwd(sctype_dir)

scRNAseqData = sc.combined

# load libraries and functions
lapply(c("dplyr","Seurat","HGNChelper"), library, character.only = T)
source("/Users/chengchao/biosource/besaltpipe/src/SingleCell/sctype/gene_sets_prepare.R"); 
source("/Users/chengchao/biosource/besaltpipe/src/SingleCell/sctype/sctype_score_.R")

# get cell-type-specific gene sets from our in-built database (DB)
# gs_list = gene_sets_prepare("/Users/chengchao/biosource/besaltpipe/src/SingleCell/sctype/ScTypeDB_short.xlsx", "Immune system") # e.g. Immune system, Liver, Pancreas, Kidney, Eye, Brain
# gs_list = gene_sets_prepare("/Users/chengchao/biosource/besaltpipe/src/SingleCell/sctype/ScTypeDB_full.xlsx", "Immune system") # e.g. Immune system,Pancreas,Liver,Eye,Kidney,Brain,Lung,Embryo,Gastrointestinal tract,Muscle,Skin

# DB file
db_ = opt$sctypedb
tissue = opt$tissue # e.g. Immune system,Pancreas,Liver,Eye,Kidney,Brain,Lung,Embryo,Gastrointestinal tract,Muscle,Skin,Heart,Ovary,Testis,White adipose tissue,Teeth
# tissue = "Immune system" # e.g. Immune system,Pancreas,Liver,Eye,Kidney,Brain,Lung,Embryo,Gastrointestinal tract,Muscle,Skin,Heart,Ovary,Testis,White adipose tissue,Teeth

# prepare gene sets
gs_list = gene_sets_prepare(db_, tissue)



# scRNAseqData <- FindVariableFeatures(scRNAseqData, selection.method = "vst", nfeatures = 2000)

# # scale and run PCA
# scRNAseqData <- ScaleData(scRNAseqData, features = rownames(scRNAseqData))


DefaultAssay(scRNAseqData) <- opt$defaultassay

# scRNAseqData <- FindVariableFeatures(scRNAseqData,nfeatures = 6000)
# scRNAseqData <- ScaleData(scRNAseqData, features = VariableFeatures(scRNAseqData))

scRNAseqData <- ScaleData(scRNAseqData, features = rownames(scRNAseqData), verbose = FALSE)

# # scale and run PCA
# scRNAseqData <- ScaleData(scRNAseqData, features = rownames(scRNAseqData))
# Select the top 6000 features for integration across the models

# Manually set these features as the variable features for the SCT assay
# sc.list <- SplitObject(scRNAseqData, split.by = "replicate")
# variable_features <- SelectIntegrationFeatures(object.list = sc.list, nfeatures = 6000)
# scRNAseqData <- ScaleData(scRNAseqData, features = variable_features)

# es.max = sctype_score(scRNAseqData = scRNAseqData[["RNA"]]@scale.data, scaled = TRUE, gs = gs_list$gs_positive, gs2 = gs_list$gs_negative)

# es.max = sctype_score(scRNAseqData = scRNAseqData[[opt$defaultassay]]@scale.data, scaled = TRUE, gs = gs_list$gs_positive, gs2 = gs_list$gs_negative)


# 获取表达矩阵的所有基因
all_genes <- toupper(rownames(scRNAseqData[[opt$defaultassay]]@scale.data))

# 找出正集/负集 marker 中不在表达矩阵里的基因
drop_pos <- lapply(gs_list$gs_positive, function(x) setdiff(x, all_genes))
drop_neg <- lapply(gs_list$gs_negative, function(x) setdiff(x, all_genes))

# 打印每个细胞类型丢掉的基因
cat("### Dropped positive markers ###\n")
for (ct in names(drop_pos)) {
  if (length(drop_pos[[ct]]) > 0) {
    cat(ct, ":", paste(drop_pos[[ct]], collapse = ", "), "\n")
  }
}
cat("\n### Dropped negative markers ###\n")
for (ct in names(drop_neg)) {
  if (length(drop_neg[[ct]]) > 0) {
    cat(ct, ":", paste(drop_neg[[ct]], collapse = ", "), "\n")
  }
}

# 保留只在矩阵里的 marker
gs_pos <- lapply(gs_list$gs_positive, function(x) intersect(x, all_genes))
gs_neg <- lapply(gs_list$gs_negative, function(x) intersect(x, all_genes))

# 跑 sctype_score
es.max <- sctype_score(
  scRNAseqData = scRNAseqData[[opt$defaultassay]]@scale.data,
  scaled       = TRUE,
  gs           = gs_pos,
  gs2          = gs_neg
)




# View results, cell-type by cell matrix. See the complete example below
# View(es.max)

# saveRDS(es.max, file = "es.max.rds")

# merge by cluster
cL_resutls = do.call("rbind", lapply(unique(scRNAseqData@meta.data$seurat_clusters), function(cl){
    es.max.cl = sort(rowSums(es.max[ ,rownames(scRNAseqData@meta.data[scRNAseqData@meta.data$seurat_clusters==cl, ])]), decreasing = !0)
    head(data.frame(cluster = cl, type = names(es.max.cl), scores = es.max.cl, ncells = sum(scRNAseqData@meta.data$seurat_clusters==cl)), 10)
}))

cL_resutls <- cL_resutls %>%
            dplyr::arrange(cluster, -scores)

cat('',file=paste('cL_resutls','.xls',sep=''))
write.table(cL_resutls,file=paste('cL_resutls','.xls',sep=''),
                append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

sctype_scores = cL_resutls %>% group_by(cluster) %>% top_n(n = 1, wt = scores)  
# set low-confident (low ScType score) clusters to "unknown"

# sctype_scores$type[as.numeric(as.character(sctype_scores$scores)) < sctype_scores$ncells/4] = "Unknown"


print(sctype_scores[,1:4])
cat('',file=paste('sctype_scores','.xls',sep=''))
write.table(sctype_scores,file=paste('sctype_scores','.xls',sep=''),
                append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)
# We can also overlay the identified cell types on UMAP plot:

scRNAseqData@meta.data$customclassif = ""
sc.combined@meta.data$customclassif = ""
for(j in unique(sctype_scores$cluster)){
  cl_type = sctype_scores[sctype_scores$cluster==j,]; 
  scRNAseqData@meta.data$customclassif[scRNAseqData@meta.data$seurat_clusters == j] = as.character(cl_type$type[1])
  sc.combined@meta.data$customclassif[sc.combined@meta.data$seurat_clusters == j] = as.character(cl_type$type[1])
}

# DimPlot(scRNAseqData, reduction = "umap", label = TRUE, repel = TRUE, group.by = 'customclassif') 

DefaultAssay(scRNAseqData) <- opt$defaultassay
plot_cluster_sctype <- function(){
  if(opt$skiptsne=="false"){
  ## tsne
  p1 <- DimPlot(scRNAseqData, reduction = "tsne", group.by = "group", pt.size = 0.1)
  p2 <- DimPlot(scRNAseqData, reduction = "tsne", label = TRUE, pt.size = 0.1)
  p3 <- DimPlot(scRNAseqData, reduction = "tsne", repel = TRUE, group.by = 'customclassif', label = TRUE, pt.size = 0.1)
  # p1 <- AugmentPlot(plot = p1)
  # p2 <- AugmentPlot(plot = p2)

  pdf(file=paste("tsne_cluster_sctype","pdf",sep="."),width = 22,height = 5)
  # p1 <- DimPlot(scRNAseqData, reduction = "tsne", pt.size = 0.1, label = TRUE) + ggtitle(label = "FIt-SNE")
  # p1 <- AugmentPlot(plot = p1)
  print((p1+p2+p3) + theme_paper)
  dev.off()

  png(file = paste("tsne_cluster_sctype",".png",sep=""),width = 550,height = 125,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  # p1 <- DimPlot(scRNAseqData, reduction = "tsne", pt.size = 0.1, label = TRUE) + ggtitle(label = "FIt-SNE")
  # p1 <- AugmentPlot(plot = p1)
  print((p1+p2+p3) + theme_paper)
  dev.off()
  }
  ## umap
  p1 <- DimPlot(scRNAseqData, reduction = "umap", group.by = "group", pt.size = 0.1)
  p2 <- DimPlot(scRNAseqData, reduction = "umap", label = TRUE, pt.size = 0.1)
  p3 <- DimPlot(scRNAseqData, reduction = "umap", repel = TRUE, group.by = 'customclassif', label = TRUE, pt.size = 0.1)
  # p1 <- AugmentPlot(plot = p1)
  # p2 <- AugmentPlot(plot = p2)

  pdf(file=paste("umap_cluster_sctype","pdf",sep="."),width = 22,height = 5)
  print((p1+p2+p3) + theme_paper)
  # p1 <- DimPlot(scRNAseqData, reduction = "umap", pt.size = 0.1, label = TRUE) + ggtitle(label = "UMAP")
  # p1 <- AugmentPlot(plot = p1)
  # (p1)
  dev.off()

  png(file = paste("umap_cluster_sctype",".png",sep=""),width = 550,height = 125,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1+p2+p3)
  # p1 <- DimPlot(scRNAseqData, reduction = "umap", pt.size = 0.1, label = TRUE) + ggtitle(label = "UMAP")
  # p1 <- AugmentPlot(plot = p1)
  # (p1)
  dev.off()
if(opt$skiptsne=="false"){
  ## tsne和umap一起展示
  p1 <- DimPlot(scRNAseqData, reduction = "tsne", repel = TRUE, group.by = 'customclassif', pt.size = 0.1, label = TRUE) + ggtitle(label = "FIt-SNE")
  p2 <- DimPlot(scRNAseqData, reduction = "umap", repel = TRUE, group.by = 'customclassif', pt.size = 0.1, label = TRUE) + ggtitle(label = "UMAP")
  # p1 <- AugmentPlot(plot = p1)
  # p2 <- AugmentPlot(plot = p2)

  pdf(file=paste("tsne_umap_sctype","pdf",sep="."),width = 22,height = 5)
  print((p1 + p2) + theme_paper)
  dev.off()

  png(file = paste("tsne_umap_sctype",".png",sep=""),width = 550,height = 125,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print((p1 + p2) + theme_paper)
  dev.off()
}
}

plot_cluster_sctype()

# sc.combined = scRNAseqData
scRNAseqData<-ls()

}

## 统计cluster
setwd(sc_cluster_dir)

clu = cbind(Idents(sc.combined),sc.combined[["replicate"]],sc.combined[["group"]],sc.combined[["customclassif"]])

cat(c('CellIndex\tClusterID\tsample\tgroup\tcellclass\n'),file=paste('Clusters','.xls',sep=''))
write.table(clu,file=paste('Clusters','.xls',sep=''),
            append=T,quote=F,sep='\t',row.names = TRUE,col.names = FALSE)
system("perl /Users/chengchao/biosource/besaltpipe/src/SingleCell/tools/sc_stat_cluster.pl")

## 回到工作根目录
setwd(workdir)

sc.combined$cellcluster <- paste("C", Idents(sc.combined), sep = "")
sc.combined$cellgroup <- paste("C", Idents(sc.combined), sc.combined$group, sep = "_")

tryCatch(
  {
    if (length(Layers(sc.combined[["RNA"]])) > 1) {
        sc.combined[["RNA"]] <- JoinLayers(sc.combined[["RNA"]])
        message("✅ RNA assay had multiple layers, joined now.")
    } else {
        message("ℹ️ RNA assay already single layer, no need to join.")
    }
    message("✅ RNA assay layers joined successfully.")
  },
  error = function(e) {
    message("⚠️ Skip JoinLayers: ", e$message)
  }
)

tryCatch(
  {
    sc.combined <- PrepSCTFindMarkers(object = sc.combined)
    message("✅ PrepSCTFindMarkers run successfully.")
  },
  error = function(e) {
    message("⚠️ Skip PrepSCTFindMarkers: ", e$message)
  }
)

## 保存
saveRDS(sc.combined, file = "cells_analysis.rds")

system("Rscript /Users/chengchao/biosource/besaltpipe/src/SingleCell/tools/sc_combined_markers.r")
system("Rscript /Users/chengchao/biosource/besaltpipe/src/SingleCell/tools/sc_combined_markers_bycelltype.r")


# library(SeuratData)
# library(SeuratDisk)

# DefaultAssay(sc.combined) <- opt$defaultassay

# SaveH5Seurat(sc.combined, filename = "sc.h5Seurat",overwrite = TRUE)
# Convert("sc.h5Seurat", dest = "h5ad",overwrite = TRUE)

# system("rm -rf sc.h5Seurat")

# # 建议添加sessionInfo记录
writeLines(capture.output(sessionInfo()), "session_info.txt")