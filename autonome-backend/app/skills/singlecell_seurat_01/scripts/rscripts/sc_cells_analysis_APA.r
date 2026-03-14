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
        default = 6,
        help = "parallel run number of cores"
    ),
    make_option(
        c("--MaxMemMega"),
        action = "store",
        type = "integer",
        default = 460,
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
        c("-r","--rdsfile"),
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
        default = "integrated",
        help = "default assay"
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
        c("--skipanno"),
        action = "store",
        type = "character",
        default = "false",
        help = "skip annotation"
    ),
    make_option(
        c("--noparallel"),
        action = "store",
        type = "character",
        default = "false",
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

use_parallel <- tolower(opt$noparallel) != "true"
if (use_parallel) {
  plan("multisession", workers = opt$ncpus)
} else {
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
# opt$infile <- "/users/zhangzd/data/projects/singleCell/result/singlecell/1_preprocessing/sc_preprocessing.rds"

# # opt$rdsfile <- "/users/zhangzd/data/projects/singleCell/result/singlecell/1_preprocessing/sc_preprocessing.rds"
# opt$samplelist <- "MCAO,sham"
# opt$listname <- "MCAO,sham"
# opt$resolution = 0.6
# # opt$keeps = "43,49,50,8,26,36,46,41,9,45,62,6,20,33,52,55"
# opt$sctypedb = "/users/zhangzd/data/projects/singleCell/sctype_marker_db.xlsx"
# opt$tissue = "rat_brain"

# nohup Rscript /Users/chengchao/biosource/besaltpipe/src//SingleCell/allsample/sc_cells_analysis.r -s Marrow1,Marrow2,Heart1,Heart2,Kidney2,Kidney3,Liver1-1,Liver2,Lung1,Lung2,Peripheral-Blood1,Peripheral-Blood2,Spleen1-1,Spleen1-2,Stomach1,Stomach2,Thymus1,Thymus2,Tonsil_1,Tonsil_2 -l Marrow,Marrow,Heart,Heart,Kidney,Kidney,Liver,Liver,Lung,Lung,PBMC,PBMC,Spleen,Spleen,Stomach,Stomach,Thymus,Thymus,Tonsil,Tonsil -i /mnt/beegfs/basic/single-cell/RX-7710552-N_Treeshrew_immune/basic/scRNA-seq_other_species/mouse/result/singlecell/1_preprocessing/sc_preprocessing.rds -d 30 --sctypedb /public/database/singlecell/sctype_markers/ScTypeDB_full.treeshrew.xlsx -t "Treeshrew" --resolution 1.2 &


# opt$cellanno <- "/data3/basic/single-cell/RX2020-11003-VN_mouse_ovary/basic/SC_pipeline_20210610/cell_anno.txt"



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
  sc.combined[["RNA"]] = JoinLayers(sc.combined[["RNA"]])
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

# sc.combined <- FindNeighbors(sc.combined, reduction = "pca", dims = 1:opt$dims, nn.eps = 0.5)
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
  sc.combined <- FindNeighbors(sc.combined, reduction = "pca", dims = 1:opt$dims)
  # sc.combined <- FindClusters(sc.combined, resolution = 3, n.start = 10)
  # We will use the FindClusters() function to perform the graph-based clustering. The resolution is an important argument that sets the "granularity" of the downstream clustering and will need to be optimized for every individual experiment. For datasets of 3,000 - 5,000 cells, the resolution set between 0.4-1.4 generally yields good clustering. Increased resolution values lead to a greater number of clusters, which is often required for larger datasets.
  
  # Determine the clusters for various resolutions                                
  # sc.combined <- FindClusters(object = sc.combined,
  #                              resolution = c(0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6),seed=TRUE)
  sc.combined <- FindClusters(sc.combined, resolution = seq(0.3,1.6,by=0.1),seed=TRUE)

  p1 <- clustree(sc.combined)
  pdf(file=paste("resolution_clustree",".pdf",sep=""),width = 20,height = 20)
  print(p1)
  dev.off()

  png(file = paste("resolution_clustree",".png",sep=""),width = 500,height = 500,units = "mm",res = 300,pointsize = 1.5)
  par(mar = c(5, 5, 2, 2), cex.axis = 1.5, cex.lab = 2)
  print(p1)
  dev.off()
  
  # head(sc.combined@meta.data)
  # # Assign identity of clusters
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

# if(opt$rdsfile!="" & opt$rmcluster!=""){

#   print("###开始进行re-cluster")

#   # 降维
#   all.genes <- rownames(sc.combined)
#   # sc.combined <- ScaleData(sc.combined, features = all.genes, verbose = FALSE, vars.to.regress = "percent.mt")
#   sc.combined <- RunPCA(sc.combined, features = VariableFeatures(object = sc.combined), npcs = 100, ndims.print = 1:5, nfeatures.print = 5)

#   # Seurat provides several useful ways of visualizing both cells and features that define the PCA, including VizDimReduction, DimPlot, and DimHeatmap
#   p1 <- VizDimLoadings(sc.combined, dims = 1:2, reduction = "pca")
#   pdf(file=paste("VizPlot_PCA",".pdf",sep=""),width = 8,height = 5)
#   p1
#   dev.off()

#   png(file = paste("VizPlot_PCA",".png",sep=""),width = 200,height = 125,units = "mm",res = 300,pointsize = 1.5)
#   par(mar = c(5, 5, 2, 2), cex.axis = 1.5, cex.lab = 2)
#   p1
#   dev.off()


#   p1 <- DimPlot(sc.combined, reduction = "pca", group.by = "replicate", split.by = "group",pt.size = 0.01)
#   pdf(file=paste("DimPlot_PCA",".pdf",sep=""),width = 4 * groupnum,height = 4)
#   p1
#   dev.off()

#   png(file = paste("DimPlot_PCA",".png",sep=""),width = 100 * groupnum,height = 100,units = "mm",res = 300,pointsize = 2)
#   par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
#   p1
#   dev.off()



#   # In particular DimHeatmap allows for easy exploration of the primary sources of heterogeneity in a dataset, and can be useful when trying to decide which PCs to include for further downstream analyses. Both cells and features are ordered according to their PCA scores. Setting cells to a number plots the 'extreme' cells on both ends of the spectrum, which dramatically speeds plotting for large datasets. Though clearly a supervised analysis, we find this to be a valuable tool for exploring correlated feature sets.
#   # DimHeatmap(sc.combined, dims = 1:2, cells = 500, balanced = TRUE)


#   pdf(file=paste("DimHeatmap_PCA",".pdf",sep=""),width = 15,height = 10)
#   DimHeatmap(sc.combined, dims = 1:9, cells = 500, balanced = TRUE)
#   dev.off()

#   png(file = paste("DimHeatmap_PCA",".png",sep=""),width = 450,height = 300,units = "mm",res = 300,pointsize = 15)
#   par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
#   DimHeatmap(sc.combined, dims = 1:9, cells = 500, balanced = TRUE)
#   dev.off()


#   pdf(file=paste("ElbowPlot",".pdf",sep=""),width = 10,height = 4)
#   p1 <- ElbowPlot(sc.combined, ndims = 25)
#   p2 <- ElbowPlot(sc.combined, ndims = 100)
#   p1+p2
#   dev.off()

#   png(file = paste("ElbowPlot",".png",sep=""),width = 250,height = 100,units = "mm",res = 300,pointsize = 2)
#   par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
#   p1 <- ElbowPlot(sc.combined, ndims = 25)
#   p2 <- ElbowPlot(sc.combined, ndims = 100)
#   p1+p2
#   dev.off()

#   # opt$dims = 15

#   sc.combined <- FindNeighbors(sc.combined, reduction = "pca", dims = 1:opt$dims)
#   # sc.combined <- FindClusters(sc.combined, resolution = 3, n.start = 10)
#   # We will use the FindClusters() function to perform the graph-based clustering. The resolution is an important argument that sets the "granularity" of the downstream clustering and will need to be optimized for every individual experiment. For datasets of 3,000 - 5,000 cells, the resolution set between 0.4-1.4 generally yields good clustering. Increased resolution values lead to a greater number of clusters, which is often required for larger datasets.
  
#   # Determine the clusters for various resolutions                                
#   sc.combined <- FindClusters(object = sc.combined,
#                                resolution = c(0.3, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6),seed=TRUE)
#   # head(sc.combined@meta.data)
#   # # Assign identity of clusters
#   Idents(object = sc.combined) <- "integrated_snn_res.0.3"
#   print("resolution:0.3")
#   length(unique(factor(Idents(sc.combined))))
#   Idents(object = sc.combined) <- "integrated_snn_res.0.4"
#   print("resolution:0.4")
#   length(unique(factor(Idents(sc.combined))))
#   Idents(object = sc.combined) <- "integrated_snn_res.0.6"
#   print("resolution:0.6")
#   length(unique(factor(Idents(sc.combined))))
#   Idents(object = sc.combined) <- "integrated_snn_res.0.8"
#   print("resolution:0.8")
#   length(unique(factor(Idents(sc.combined))))
#   Idents(object = sc.combined) <- "integrated_snn_res.1"
#   print("resolution:1")
#   length(unique(factor(Idents(sc.combined))))
#   Idents(object = sc.combined) <- "integrated_snn_res.1.2"
#   print("resolution:1.2")
#   length(unique(factor(Idents(sc.combined))))
#   Idents(object = sc.combined) <- "integrated_snn_res.1.4"
#   print("resolution:1.4")
#   length(unique(factor(Idents(sc.combined))))
#   Idents(object = sc.combined) <- "integrated_snn_res.1.6"
#   print("resolution:1.6")
#   length(unique(factor(Idents(sc.combined))))
#   # res = 0.4
#   sc.combined <- FindClusters(sc.combined, resolution = res)
#   # sc.combined <- FindClusters(sc.combined, resolution = 1.6)
# }


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
    sc.combined <- RunTSNE(sc.combined, dims = 1:opt$dims, tsne.method = "FIt-SNE", nthreads = 16, max_iter = 2000)
  }
  
  # sc.combined <- RunUMAP(sc.combined, dims = 1:opt$dims, min.dist = 0.75)
  sc.combined <- RunUMAP(sc.combined, dims = 1:opt$dims)
}

# if(opt$rdsfile!="" & opt$rmcluster!=""){
#   ## large data
#   if(opt$skiptsne=="false"){
#     sc.combined <- RunTSNE(sc.combined, dims = 1:opt$dims, tsne.method = "FIt-SNE", nthreads = 16, max_iter = 2000)
#   }
#   # sc.combined <- RunUMAP(sc.combined, dims = 1:opt$dims, min.dist = 0.75)
#   sc.combined <- RunUMAP(sc.combined, dims = 1:opt$dims)
# }

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

  w = 4 * samplenum
  if(w>40){w=40}

  pdf(file=paste("umap_cluster_byreplicate","pdf",sep="."),width = w, height = 4)
  print(p1)
  dev.off()

  w = 100 * samplenum
  if(w>1000){w=1000}

  png(file = paste("umap_cluster_byreplicate",".png",sep=""),width = w, height = 100,units = "mm",res = 300,pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1)
  dev.off()


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


DefaultAssay(scRNAseqData) <- "RNA"


scRNAseqData <- FindVariableFeatures(scRNAseqData,nfeatures = 6000)
scRNAseqData <- ScaleData(scRNAseqData, features = VariableFeatures(scRNAseqData))
# # scale and run PCA
# scRNAseqData <- ScaleData(scRNAseqData, features = rownames(scRNAseqData))

print(gs_list$gs_positive)

es.max = sctype_score(scRNAseqData = scRNAseqData[["RNA"]]$scale.data, scaled = TRUE, gs = gs_list$gs_positive, gs2 = gs_list$gs_negative)

# es.max = sctype_score(scRNAseqData = scRNAseqData[["RNA"]]@scale.data, scaled = TRUE, gs = gs_list$gs_positive, gs2 = gs_list$gs_negative)

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

DefaultAssay(scRNAseqData) <- "RNA"
plot_cluster_sctype <- function(){
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

# plot_cluster_sctype()
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

## 保存

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

DefaultAssay(sc.combined) <- "RNA"
saveRDS(sc.combined, file = "cells_analysis.rds")


# marker鉴定

system("Rscript /Users/chengchao/biosource/besaltpipe/src/SingleCell/tools/sc_combined_markers.r")



#####################################################################################
## 标志基因Finding differentially expressed features (cluster biomarkers)
# Seurat can help you find markers that define clusters via differential expression. By default, it identifes positive and negative markers of a single cluster (specified in ident.1), compared to all other cells. FindAllMarkers automates this process for all clusters, but you can also test groups of clusters vs. each other, or against all cells.
# The min.pct argument requires a feature to be detected at a minimum percentage in either of the two groups of cells, and the thresh.test argument requires a feature to be differentially expressed (on average) by some amount between the two groups. You can set both of these to 0, but with a dramatic increase in time - since this will test a large number of features that are unlikely to be highly discriminatory. As another option to speed up these computations, max.cells.per.ident can be set. This will downsample each identity class to have no more cells than whatever this is set to. While there is generally going to be a loss in power, the speed increases can be significiant and the most highly differentially expressed features will likely still rise to the top.
#####################################################################################

## cluster number
# maxIdents<- length(unique(factor(Idents(sc.combined))))-1

# ## 导入基因画图模块
# DefaultAssay(sc.combined) <- "RNA"
# source("/Users/chengchao/biosource/besaltpipe/src/SingleCell/allsample/sc_genes_visualizations_function.r")
# sc.idents.bak <- Idents(sc.combined)
# maxIdents<- unique(factor(Idents(sc.combined)))
# sc.combined$celltype.group <- paste(Idents(sc.combined), sc.combined$group, sep = "_")
# sc.combined$celltype <- Idents(sc.combined)
# clusternum <- length(unique(factor(Idents(sc.combined))))

# ####1. FindAllMarkers 找到各组中所有的markers

# # https://hbctraining.github.io/scRNA-seq/lessons/sc_exercises_integ_marker_identification.html

# # find markers for every cluster compared to all remaining cells, report only the positive ones

# combined_markers_dir = paste("","combined_markers", sep="")
# if(!file.exists(combined_markers_dir)){
#   dir.create(combined_markers_dir)
# }
# setwd(combined_markers_dir)


# DefaultAssay(sc.combined) <- "RNA"

# run_parallel_findallmarkers <- function(seurat_obj, ncores = 6, logfc = 0.25) {
#   require(future.apply)
#   # use_parallel <- tolower(opt$noparallel) != "true"
#   # if (use_parallel) {
#   #   plan("multisession", workers = ncores)
#   # } else {
#   #   plan(sequential)
#   # }
#   plan(sequential)
  
#   clusters <- levels(Idents(seurat_obj))
#   markers_list <- future_lapply(clusters, function(cl) {
#     FindMarkers(seurat_obj, ident.1 = cl, only.pos = TRUE, logfc.threshold = logfc)
#   })
  
#   for (i in seq_along(markers_list)) {
#     markers_list[[i]]$cluster <- clusters[i]
#     markers_list[[i]]$gene <- rownames(markers_list[[i]])
#   }
#   df <- do.call(rbind, markers_list)
#   rownames(df) <- NULL
#   return(df)
# }

# combined_markers <- run_parallel_findallmarkers(sc.combined, ncores = opt$ncpus)


# # combined_markers <- FindAllMarkers(object = sc.combined, 
# #                           only.pos = TRUE,
# #                           logfc.threshold = 0.25) 


# # Order the rows by p-adjusted values
# combined_markers <- combined_markers[ , c(6, 7, 2:4, 1, 5)]
# combined_markers <- combined_markers %>%
#         dplyr::arrange(cluster, -avg_log2FC, p_val)




# # 计算每个基因在各cluster的平均表达量（RNA assay的data slot数据）
# avg_exp_cluster <- AverageExpression(
#   sc.combined, 
#   assays = "RNA", 
#   slot = "data", 
#   group.by = "ident",  # 使用cluster分组
#   verbose = FALSE
# )$RNA

# # 计算每个基因在其他所有细胞中的平均表达量（非当前cluster）
# avg_exp_other <- sapply(colnames(avg_exp_cluster), function(cl) {
#   # 标记当前cluster的细胞
#   current_cells <- WhichCells(sc.combined, idents = cl)
#   other_cells <- setdiff(colnames(sc.combined), current_cells)
  
#   # 计算在其他细胞中的平均表达量
#   Matrix::rowMeans(GetAssayData(
#     sc.combined, 
#     assay = "RNA", 
#     slot = "data"
#   )[, other_cells, drop = FALSE])
# })
# colnames(avg_exp_other) <- colnames(avg_exp_cluster)

# # 添加两列到combined_markers
# combined_markers$avgExp_cluster <- apply(
#   combined_markers, 
#   1, 
#   function(row) {
#     cl <- as.character(row["cluster"])
#     gene <- row["gene"]
#     avg_exp_cluster[gene, cl]
#   }
# )

# combined_markers$avgExp_other <- apply(
#   combined_markers, 
#   1, 
#   function(row) {
#     cl <- as.character(row["cluster"])
#     gene <- row["gene"]
#     avg_exp_other[gene, cl]
#   }
# )

# # 调整列顺序（将新列放在avg_log2FC之后）
# combined_markers <- combined_markers %>%
#   dplyr::select(cluster, gene, avg_log2FC, p_val, p_val_adj, pct.1, pct.2, avgExp_cluster, avgExp_other)




# cat(c(''),file=paste('combined_markers_export','.xls',sep=''))
# write.table(combined_markers,file=paste('combined_markers_export','.xls',sep=''),
#             append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# saveRDS(combined_markers, file = "../combined_markers.rds")


# # 提取每个类群排名靠前的3个或10个保守标记物


# top3 <- combined_markers %>% 
#   group_by(cluster) %>% 
#   top_n(n = 3, 
#         wt = avg_log2FC)

# cat(c(''),file=paste('top3_combined_markers_export','.xls',sep=''))
# write.table(top3,file=paste('top3_combined_markers_export','.xls',sep=''),
#             append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# top10 <- combined_markers %>% 
#   group_by(cluster) %>% 
#   top_n(n = 10, 
#         wt = avg_log2FC)
# cat(c(''),file=paste('top10_combined_markers_export','.xls',sep=''))
# write.table(top10,file=paste('top10_combined_markers_export','.xls',sep=''),
#             append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# top50 <- combined_markers %>% 
#   group_by(cluster) %>% 
#   top_n(n = 50, 
#         wt = avg_log2FC)
# cat(c(''),file=paste('top50_combined_markers_export','.xls',sep=''))
# write.table(top50,file=paste('top50_combined_markers_export','.xls',sep=''),
#             append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# top100 <- combined_markers %>% 
#   group_by(cluster) %>% 
#   top_n(n = 100, 
#         wt = avg_log2FC)
# cat(c(''),file=paste('top100_combined_markers_export','.xls',sep=''))
# write.table(top100,file=paste('top100_combined_markers_export','.xls',sep=''),
#             append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# deg <- subset(combined_markers,avg_log2FC>=0.5)
# # deg <- subset(deg,pct.1-pct.2>=0.25)
# deg <- subset(deg,pct.1>=0.5)
# deg <- subset(deg,p_val_adj<=0.05)

# cat(c(''),file=paste('deg_combined_markers_export','.xls',sep=''))
# write.table(deg,file=paste('deg_combined_markers_export','.xls',sep=''),
#             append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)


# ## plot top3 markers heatmap

# # diffgenes=subset(top3,avg_log2FC>=1|avg_log2FC<=-1)
# # diffgenes=subset(diffgenes,pct.1-pct.2>=0.3|pct.1-pct.2<=-0.3)
# # diffgenes=subset(diffgenes,p_val_adj<=0.05)
# diffgenes  = top3
# showgene = unique(diffgenes$gene)
# showgenenum = length(showgene)
# prefix = paste("top3_combined_markers",sep="")

# nowdir = getwd()
# # show_genes(showgene,showgenenum,groupnum,clusternum,prefix,FALSE)
# # system("py3 /users/chengc/work/pipeline/besaltgraphic/honeycomb/apps/single-cell/scanpy_plot.py -s ../sc.h5ad -m ./top3_combined_markers_export.xls -O top3_scanpy")

# setwd(nowdir)

setwd(workdir)

