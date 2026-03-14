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
# 描述：单细胞分析流程,拟时序分析
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
# https://satijalab.org/seurat/pbmc3k_tutorial.html
# https://github.com/CostaLab/scrna_seurat_pipeline
# https://www.jianshu.com/p/e79ab1cc0a67
#####################################################################################




#####################################################################################
#####参数获取
#####################################################################################
# windows系统检查当前程序路径
# script.dir <- dirname(sys.frame(1)$ofile)

library(tidyverse)
get_this_file <- function(){
    commandArgs() %>% 
       tibble::enframe(name=NULL) %>%
       tidyr::separate(col=value, into=c("key", "value"), sep="=", fill='right') %>%
       dplyr::filter(key == "--file") %>%
       dplyr::pull(value)
}
script.dir <- get_this_file()

setwd("./")
# setwd("/data1/scRNA_data/DEV2020-10001_seurat/basic/mca")

suppressPackageStartupMessages(library(optparse))      ## Options
suppressPackageStartupMessages(library(futile.logger)) ## logger
suppressPackageStartupMessages(library("stats"))
suppressPackageStartupMessages(library(dplyr))
`%ni%` <- Negate(`%in%`)

# The Bioconductor package SingleCellExperiment provides the SingleCellExperiment classfor usage.While the package is implicitly installed and loaded when using any package that depends on the SingleCellExperiment class, it can be explicitly installed(and loaded) as follows: #install.packages("BiocManager")# BiocManager::install(c('SingleCellExperiment', 'Rtsne', 'scater', 'scran', 'uwot'))

# library("ggplot2")## library("factoextra")## library("FactoMineR")# library("stats")# library("ggthemes")# library("reshape2")# library("ggsci")

## old
library(SingleCellExperiment)
#library(scater)

library("ggplot2")
library(tidyverse)
options(stringsAsFactors = FALSE)
library(grDevices)
library(gplots)
library(Seurat)
library(patchwork)
library(SeuratWrappers)
library(monocle3)

library(SeuratData)
library(cowplot)

library("future.apply")
suppressPackageStartupMessages(library(doParallel))


## 参数读取
option_list <- list(
    make_option(
        c("-n","--ncpus"),
        action = "store",
        type = "integer",
        default = 8,
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
        c("-c","--comparelist"),
        action = "store",
        type = "character",
        default = "",
        help = "group1:group2,group2:group3,group3:group4"
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
        c("-i", "--infile"),
        action = "store",
        type = "character",
        default = "../2_cells_analysis/cells_analysis.rds",
        help = "The cell analysis rds file"
    ),
    make_option(
        c("-r", "--root"),
        action = "store",
        type = "character",
        default = "0",
        help = "root cluster number,default is 0"
    ),
    make_option(
        c("-g", "--rbplist"),
        action = "store",
        type = "character",
        default = "/public/database/RBP/human/RBP_list_human_final.xls",
        help = "rbplist"
    ),
    make_option(
        c("-d", "--defaultassay"),
        action = "store",
        type = "character",
        default = "RNA",
        help = "defaultassay"
    )
)
opt <- parse_args(OptionParser(option_list = option_list))

registerDoParallel(cores=opt$ncpus)
plan("multisession", workers = opt$ncpus)
options(future.globals.maxSize = opt$MaxMemMega * 1024^2)

# opt$samplelist <- "Con,Sham,OB1,OB2"
# opt$listname <- "Con,Sham,OB,OB"
# opt$comparelist <- "OB:Con,Sham:Con,OB:Sham"

# listnames <- strsplit(opt$listname,",")[[1]]
# groupnum = length(unique(listnames))

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

opt$infile <- "/mnt/beegfs/basic/single-cell/RX-7710552-N_Treeshrew_immune/basic/scRNA-seq_20220610/result/bytissue_new/Marrow/cells_analysis.rds"
opt$rbplist <- "/data1/projects/single-cell/RX-7710552-N_Treeshrew_immune/figures/fig2-TF.marrow/pseudotime_monocle3/TF_regulon.txt"

# opt$infile <- "../2_cells_analysis/cells_analysis.rds"
# opt$infile <- "../../B_RBP_basic/RBP_pre_reUMAP.rds"

####################################################################################
### 读取RBP list
####################################################################################
rbps = read.table(
    opt$rbplist,
    header = F,
    com = '',
    sep = "\t",
    quote = NULL,
    check.names = F
)
rbps <- as.vector(t(rbps))



#####################################################################################
## preprocessing数据读取，数据对象建立
# We start by reading in the data. The Read10X function reads in the output of the cellranger pipeline from 10X, returning a unique molecular identified (UMI) count matrix. The values in this matrix represent the number of molecules for each feature (i.e. gene; row) that are detected in each cell (column).
#####################################################################################

# Load the PBMC dataset

#直接通过seurat生成的rds文件的方式进行转换为CellDataSet对象
sc.combined <- readRDS(file = opt$infile)
DefaultAssay(sc.combined) <- opt$defaultassay
# DefaultAssay(sc.combined) <- "RNA"

trajectories_analysis_dir = paste("","trajectories_analysis", sep="")
if(!file.exists(trajectories_analysis_dir)){
  dir.create(trajectories_analysis_dir)
}
setwd(trajectories_analysis_dir)

#Building trajectories with Monocle 3
# https://cole-trapnell-lab.github.io/monocle3/docs/installation/
# We can convert the Seurat object to a CellDataSet object using the as.cell_data_set() function from SeuratWrappers and build the trajectories using Monocle 3. We’ll do this separately for erythroid and lymphoid lineages, but you could explore other strategies building a trajectory for all lineages together.
# 伪时间是衡量单个细胞在细胞分化等过程中所取得进展的指标。在许多生物过程中，细胞的发展并不完全同步。在单细胞表达过程的研究，如细胞分化，捕获的细胞可能广泛分布的进展。也就是说，在同一时间捕获的细胞群中，一些细胞可能已经存活了很长时间，而另一些细胞甚至还没有开始这个过程。当您希望理解细胞从一种状态过渡到另一种状态时发生的调节变化序列时，这种异步性会产生重大问题。在同一时间捕捉到的细胞中跟踪表达可以对一个基因的动力学产生一种非常压缩的感觉，而且该基因表达的明显可变性将非常高。Monocle通过按照已知的轨迹对每个细胞进行排序，缓解了由于异步而产生的问题。Monocle并没有将表情变化作为时间的函数来跟踪，而是将其作为沿着轨迹(我们称之为“伪时间”)进展的函数来跟踪。伪时间是进度的抽象单位:它只是一个细胞和轨迹起点之间的距离，沿着最短路径测量。该轨迹的总长度是根据细胞从起始状态到结束状态所经历的转录变化总量来定义的。

##############
## 使用SeuratWrappers
##############

sc.combined.cds <- as.cell_data_set(sc.combined)

## Calculate size factors using built-in function in monocle3
sc.combined.cds <- estimate_size_factors(sc.combined.cds)
## Add gene names into CDS
sc.combined.cds@rowRanges@elementMetadata@listData[["gene_short_name"]] <- rownames(sc.combined[[opt$defaultassay]])

sc.combined.cds <- cluster_cells(cds = sc.combined.cds, reduction_method = "UMAP")
# sc.combined.cds <- learn_graph(sc.combined.cds, use_partition = TRUE)
sc.combined.cds <- learn_graph(sc.combined.cds)

##############
## 拟时序轨迹图
##############
# a helper function to identify the root principal points:
get_earliest_principal_node <- function(cds, cluster="0"){
  cell_ids <- which(colData(cds)[, "ident"] == cluster)
  
  closest_vertex <-
  cds@principal_graph_aux[["UMAP"]]$pr_graph_cell_proj_closest_vertex
  closest_vertex <- as.matrix(closest_vertex[colnames(cds), ])
  root_pr_nodes <-
  igraph::V(principal_graph(cds)[["UMAP"]])$name[as.numeric(names
  (which.max(table(closest_vertex[cell_ids,]))))]
  
  root_pr_nodes
}
opt$root = "9"
sc.combined.cds <- order_cells(sc.combined.cds, root_pr_nodes=get_earliest_principal_node(sc.combined.cds,opt$root))

# sc.combined.cds <-orderCells(sc.combined.cds)
# plot trajectories colored by pseudotime
p1 <- plot_cells(cds = sc.combined.cds,color_cells_by = "pseudotime",show_trajectory_graph = TRUE,label_cell_groups=FALSE,label_leaves=FALSE,label_branch_points=TRUE,graph_label_size=3)
pdf(file=paste("trajectories_plot","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_plot",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

##############
## UMAP时序图
##############
sc.combined <- AddMetaData(
  object = sc.combined,
  metadata = sc.combined.cds@principal_graph_aux@listData$UMAP$pseudotime,
  col.name = "sc.combined.cds"
)

p1=FeaturePlot(sc.combined, c("sc.combined.cds"), pt.size = 0.1, reduction = "umap") & scale_color_viridis_c()
pdf(file=paste("trajectories_featurePlot_umap","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_featurePlot_umap",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

p1=FeaturePlot(sc.combined, c("sc.combined.cds"), pt.size = 0.1, reduction = "tsne") & scale_color_viridis_c()
pdf(file=paste("trajectories_featurePlot_tsne","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_featurePlot_tsne",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

saveRDS(sc.combined.cds, file = "./sc.combined.cds.rds")




##############
## 拟时序轨迹图
##############
print("拟时序轨迹图")

# plot trajectories colored by pseudotime
p1 <- plot_cells(cds = sc.combined.cds,color_cells_by = "pseudotime",show_trajectory_graph = TRUE,label_cell_groups=FALSE,label_leaves=FALSE,label_branch_points=FALSE,graph_label_size=3)
pdf(file=paste("trajectories_plot_by_pseudotime","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_plot_by_pseudotime",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# plot trajectories colored by cluster
p1 <- plot_cells(cds = sc.combined.cds,color_cells_by = "seurat_clusters",show_trajectory_graph = TRUE,label_cell_groups=FALSE,label_leaves=FALSE,label_branch_points=FALSE,graph_label_size=3)
pdf(file=paste("trajectories_plot_by_cluster","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_plot_by_cluster",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# plot trajectories colored by celltype
p1 <- plot_cells(cds = sc.combined.cds,color_cells_by = "customclassif",show_trajectory_graph = TRUE,label_cell_groups=FALSE,label_leaves=FALSE,label_branch_points=FALSE,graph_label_size=3)
pdf(file=paste("trajectories_plot_by_celltype","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_plot_by_celltype",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# plot trajectories colored by group
p1 <- plot_cells(cds = sc.combined.cds,color_cells_by = "group",show_trajectory_graph = TRUE,label_cell_groups=FALSE,label_leaves=FALSE,label_branch_points=FALSE,graph_label_size=3)
pdf(file=paste("trajectories_plot_by_group","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_plot_by_group",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# plot trajectories colored by cellcluster
p1 <- plot_cells(cds = sc.combined.cds,color_cells_by = "cellcluster",show_trajectory_graph = TRUE,label_cell_groups=FALSE,label_leaves=FALSE,label_branch_points=FALSE,graph_label_size=3)
pdf(file=paste("trajectories_plot_by_cellcluster","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_plot_by_cellcluster",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()



# sc.combined.cds <- order_cells(sc.combined.cds, root_pr_nodes=get_earliest_principal_node(sc.combined.cds), reduction_method = "tSNE")

# # tSNE
# # plot trajectories colored by pseudotime
# cds2 <- reduce_dimension(sc.combined.cds, reduction_method = "tSNE")
# p1 <- plot_cells(cds = cds2,color_cells_by = "pseudotime",show_trajectory_graph = TRUE,label_cell_groups=FALSE,label_leaves=FALSE,label_branch_points=FALSE,graph_label_size=3, reduction_method = "tSNE")
# pdf(file=paste("trajectories_plot_by_pseudotime_tSNE","pdf",sep="."),width = 8,height = 6)
# print(p1)
# dev.off()
# png(file = paste("trajectories_plot_by_pseudotime_tSNE",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
# par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
# print(p1)
# dev.off()

# # plot trajectories colored by cluster
# p1 <- plot_cells(cds = cds2,color_cells_by = "seurat_clusters",show_trajectory_graph = TRUE,label_cell_groups=FALSE,label_leaves=FALSE,label_branch_points=FALSE,graph_label_size=3, reduction_method = "tSNE")
# pdf(file=paste("trajectories_plot_by_cluster_tSNE","pdf",sep="."),width = 8,height = 6)
# print(p1)
# dev.off()
# png(file = paste("trajectories_plot_by_cluster_tSNE",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
# par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
# print(p1)
# dev.off()

# # plot trajectories using seurat umap
# print("UMAP时序图")
# sc.combined.sub <- AddMetaData(
#   object = sc.combined.sub,
#   metadata = sc.combined.cds@principal_graph_aux@listData$UMAP$pseudotime,
#   col.name = "cds"
# )

# p1=FeaturePlot(sc.combined.sub, c("cds"), pt.size = 0.1) & scale_color_viridis_c()
# pdf(file=paste("trajectories_featurePlot","pdf",sep="."),width = 8,height = 6)
# print(p1)
# dev.off()
# png(file = paste("trajectories_featurePlot",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
# par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
# print(p1)
# dev.off()


##############
## 时序相关的基因
##############

# Finding genes that change as a function of pseudotime
# Error: 'rBind' is defunct.
# Here I find a good solution from https://groups.google.com/g/monocle-3-users/c/tBjYuAxwyEo
# trace('calculateLW', edit = T, where = asNamespace("monocle3"))
# change Matrix::rBind to rbind


# cds=readRDS("./sc.combined.cds.rds")

cds = sc.combined.cds

## Calculate size factors using built-in function in monocle3
# cds <- estimate_size_factors(cds)

# cds@rowRanges@elementMetadata@listData[["gene_short_name"]] <- rownames(sc.combined[["RNA"]])


print("时序相关的基因")
ciliated_cds_pr_test_res <- graph_test(cds, neighbor_graph="principal_graph", cores=4)

saveRDS(ciliated_cds_pr_test_res, file = "./pr_test.rds")


pr_deg <- ciliated_cds_pr_test_res %>%
    dplyr::arrange(plyr::desc(morans_test_statistic), plyr::desc(-q_value))
pr_deg <- subset(pr_deg, q_value <= 0.05)
pr_deg_ids <- row.names(pr_deg)

pr_deg_top10 <- pr_deg %>%
    dplyr::arrange(plyr::desc(morans_test_statistic), plyr::desc(-q_value)) %>% head(10)
pr_deg_ids_top10 <- row.names(pr_deg_top10)

pr_deg_top500 <- pr_deg %>%
    dplyr::arrange(plyr::desc(morans_test_statistic), plyr::desc(-q_value)) %>% head(500)
pr_deg_ids_top500 <- row.names(pr_deg_top500)

pr_deg_ids_rbps <- intersect(pr_deg_ids, rbps)
pr_deg_rbps <- subset(pr_deg, row.names(pr_deg) %in% pr_deg_ids_rbps)

pr_deg_rbps_top10 <- pr_deg_rbps %>%
    dplyr::arrange(plyr::desc(morans_test_statistic), plyr::desc(-q_value)) %>% head(10)
pr_deg_rbps_ids_top10 <- row.names(pr_deg_rbps_top10)

pr_deg_rbps_top100 <- pr_deg_rbps %>%
    dplyr::arrange(plyr::desc(morans_test_statistic), plyr::desc(-q_value)) %>% head(100)
pr_deg_rbps_ids_top100 <- row.names(pr_deg_rbps_top100)

pr_deg_rbps_top500 <- pr_deg_rbps %>%
    dplyr::arrange(plyr::desc(morans_test_statistic), plyr::desc(-q_value)) %>% head(500)
pr_deg_rbps_ids_top500 <- row.names(pr_deg_rbps_top500)

cat(c('gene\t'),file=paste('pr_deg','_export','.xls',sep=''))
write.table(pr_deg,file=paste('pr_deg','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c('gene\t'),file=paste('pr_deg_top10','_export','.xls',sep=''))
write.table(pr_deg_top10,file=paste('pr_deg_top10','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c('gene\t'),file=paste('pr_deg_top500','_export','.xls',sep=''))
write.table(pr_deg_top500,file=paste('pr_deg_top500','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c('gene\t'),file=paste('pr_deg_q0.05','_export','.xls',sep=''))
write.table(pr_deg_q0.05,file=paste('pr_deg_q0.05','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c('gene\t'),file=paste('pr_deg_rbps','_export','.xls',sep=''))
write.table(pr_deg_rbps,file=paste('pr_deg_rbps','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c('gene\t'),file=paste('pr_deg_rbps_top10','_export','.xls',sep=''))
write.table(pr_deg_rbps_top10,file=paste('pr_deg_rbps_top10','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c('gene\t'),file=paste('pr_deg_rbps_top100','_export','.xls',sep=''))
write.table(pr_deg_rbps_top100,file=paste('pr_deg_rbps_top100','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c('gene\t'),file=paste('pr_deg_rbps_top500','_export','.xls',sep=''))
write.table(pr_deg_rbps_top500,file=paste('pr_deg_rbps_top500','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

# trajectories_plot_pr_deg_top10
p1<-plot_cells(cds, genes=pr_deg_ids_top10,
           show_trajectory_graph=FALSE,
           label_cell_groups=FALSE,
           label_branch_points=FALSE,
           label_leaves=FALSE)

pdf(file=paste("trajectories_plot_pr_deg_top10","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_plot_pr_deg_top10",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()


cds_subset <- cds[row.names(subset(rowData(cds),
        gene_short_name %in% pr_deg_ids_top10)),]

p2<-plot_genes_violin(cds_subset, group_cells_by="customclassif", ncol=2) +
      theme(axis.text.x=element_text(angle=45, hjust=1))
pdf(file=paste("trajectories_violinplot_pr_deg_top10","pdf",sep="."),width = 8,height = 6)
print(p2)
dev.off()
png(file = paste("trajectories_violinplot_pr_deg_top10",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p2)
dev.off()

# trajectories_violinplot_pr_deg_rbps_top10
p1<-plot_cells(cds, genes=pr_deg_rbps_ids_top10,
           show_trajectory_graph=FALSE,
           label_cell_groups=FALSE,
           label_branch_points=FALSE,
           label_leaves=FALSE)

pdf(file=paste("trajectories_violinplot_pr_deg_rbps_top10","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_violinplot_pr_deg_rbps_top10",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

cds_subset <- cds[row.names(subset(rowData(cds),
        gene_short_name %in% pr_deg_rbps_ids_top10)),]

p2<-plot_genes_violin(cds_subset, group_cells_by="customclassif", ncol=2) +
      theme(axis.text.x=element_text(angle=45, hjust=1))
pdf(file=paste("trajectories_violinplot_pr_deg_rbps_top10","pdf",sep="."),width = 8,height = 6)
print(p2)
dev.off()
png(file = paste("trajectories_violinplot_pr_deg_rbps_top10",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p2)
dev.off()



## module by celltype

gene_module_df <- find_gene_modules(cds[pr_deg_ids_top500,],resolution=1e-2)
cell_group_df <- tibble::tibble(cell=row.names(colData(cds)), 
                                cell_group=colData(cds)$customclassif)
agg_mat <- aggregate_gene_expression(cds, gene_module_df, cell_group_df)
row.names(agg_mat) <- stringr::str_c("Module ", row.names(agg_mat))

cat(c('Module\t'),file=paste('trajectories_deg_module_bycelltype','_export','.xls',sep=''))
write.table(agg_mat,file=paste('trajectories_deg_module_bycelltype','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c(''),file=paste('trajectories_deg_module_bycelltype_detail','_export','.xls',sep=''))
write.table(gene_module_df,file=paste('trajectories_deg_module_bycelltype_detail','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# trajectories_deg_module_bycelltype_heatmap
p1<-pheatmap::pheatmap(agg_mat,
                   scale="column", clustering_method="ward.D2")

pdf(file=paste("trajectories_deg_module_bycelltype_heatmap","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_deg_module_bycelltype_heatmap",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# trajectories_deg_module_bycelltype
p1<-plot_cells(cds,
           genes=gene_module_df,
           label_cell_groups=FALSE,
           show_trajectory_graph=FALSE)
pdf(file=paste("trajectories_deg_module_bycelltype","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_deg_module_bycelltype",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# plot_genes_in_pseudotime
lineage_cds <- cds[rowData(cds)$gene_short_name %in% pr_deg_ids_top10]
p1<-plot_genes_in_pseudotime(lineage_cds,
                         color_cells_by="customclassif",
                         min_expr=0.5)
pdf(file=paste("trajectories_top10genes_bycelltype_in_pseudotime","pdf",sep="."),width = 6,height = 12)
print(p1)
dev.off()
png(file = paste("trajectories_top10genes_bycelltype_in_pseudotime",".png",sep=""),width = 150,height = 300,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

## module by group

gene_module_df <- find_gene_modules(cds[pr_deg_top500,],resolution=1e-2)
cell_group_df <- tibble::tibble(cell=row.names(colData(cds)), 
                                cell_group=colData(cds)$group)
agg_mat <- aggregate_gene_expression(cds, gene_module_df, cell_group_df)
row.names(agg_mat) <- stringr::str_c("Module ", row.names(agg_mat))

cat(c('Module\t'),file=paste('trajectories_deg_module_bygroup','_export','.xls',sep=''))
write.table(agg_mat,file=paste('trajectories_deg_module_bygroup','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c(''),file=paste('trajectories_deg_module_bygroup_detail','_export','.xls',sep=''))
write.table(gene_module_df,file=paste('trajectories_deg_module_bygroup_detail','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# trajectories_deg_module_bygroup_heatmap
p1<-pheatmap::pheatmap(agg_mat,
                   scale="column", clustering_method="ward.D2")

pdf(file=paste("trajectories_deg_module_bygroup_heatmap","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_deg_module_bygroup_heatmap",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# trajectories_deg_module_bygroup
p1<-plot_cells(cds,
           genes=gene_module_df,
           label_cell_groups=FALSE,
           show_trajectory_graph=FALSE)
pdf(file=paste("trajectories_deg_module_bygroup","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_deg_module_bygroup",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# plot_genes_in_pseudotime
lineage_cds <- cds[rowData(cds)$gene_short_name %in% pr_deg_ids_top10]
p1<-plot_genes_in_pseudotime(lineage_cds,
                         color_cells_by="group",
                         min_expr=0.5)
pdf(file=paste("trajectories_top10genes_bygroup_in_pseudotime","pdf",sep="."),width = 6,height = 12)
print(p1)
dev.off()
png(file = paste("trajectories_top10genes_bygroup_in_pseudotime",".png",sep=""),width = 150,height = 300,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()




## module by celltype by RBP

gene_module_df <- find_gene_modules(cds[pr_deg_rbps_ids_top500,],resolution=1e-2)
cell_group_df <- tibble::tibble(cell=row.names(colData(cds)), 
                                cell_group=colData(cds)$customclassif)
agg_mat <- aggregate_gene_expression(cds, gene_module_df, cell_group_df)
row.names(agg_mat) <- stringr::str_c("Module ", row.names(agg_mat))

cat(c('Module\t'),file=paste('trajectories_deg_module_bycelltype_rbp','_export','.xls',sep=''))
write.table(agg_mat,file=paste('trajectories_deg_module_bycelltype_rbp','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c(''),file=paste('trajectories_deg_module_bycelltype_rbp_detail','_export','.xls',sep=''))
write.table(gene_module_df,file=paste('trajectories_deg_module_bycelltype_rbp_detail','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# trajectories_deg_module_bycelltype_rbp_heatmap
p1<-pheatmap::pheatmap(agg_mat,
                   scale="column", clustering_method="ward.D2")

pdf(file=paste("trajectories_deg_module_bycelltype_rbp_heatmap","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_deg_module_bycelltype_rbp_heatmap",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# trajectories_deg_module_bycelltype_rbp
p1<-plot_cells(cds,
           genes=gene_module_df,
           label_cell_groups=FALSE,
           show_trajectory_graph=FALSE)
pdf(file=paste("trajectories_deg_module_bycelltype_rbp","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_deg_module_bycelltype_rbp",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# plot_genes_in_pseudotime
lineage_cds <- cds[rowData(cds)$gene_short_name %in% pr_deg_rbps_ids_top10]
p1<-plot_genes_in_pseudotime(lineage_cds,
                         color_cells_by="customclassif",
                         min_expr=0.5)
pdf(file=paste("trajectories_top10rbps_bycelltype_in_pseudotime","pdf",sep="."),width = 6,height = 12)
print(p1)
dev.off()
png(file = paste("trajectories_top10rbps_bycelltype_in_pseudotime",".png",sep=""),width = 150,height = 300,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

## module by group by RBP

gene_module_df <- find_gene_modules(cds[pr_deg_rbps_ids_top500,],resolution=1e-2)
cell_group_df <- tibble::tibble(cell=row.names(colData(cds)), 
                                cell_group=colData(cds)$group)
agg_mat <- aggregate_gene_expression(cds, gene_module_df, cell_group_df)
row.names(agg_mat) <- stringr::str_c("Module ", row.names(agg_mat))

cat(c('Module\t'),file=paste('trajectories_deg_module_bygroup_rbp','_export','.xls',sep=''))
write.table(agg_mat,file=paste('trajectories_deg_module_bygroup_rbp','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

cat(c(''),file=paste('trajectories_deg_module_bygroup_rbp_detail','_export','.xls',sep=''))
write.table(gene_module_df,file=paste('trajectories_deg_module_bygroup_rbp_detail','_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# trajectories_deg_module_bygroup_rbp_heatmap
p1<-pheatmap::pheatmap(agg_mat,
                   scale="column", clustering_method="ward.D2")

pdf(file=paste("trajectories_deg_module_bygroup_rbp_heatmap","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_deg_module_bygroup_rbp_heatmap",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# trajectories_deg_module_bygroup_rbp
p1<-plot_cells(cds,
           genes=gene_module_df,
           label_cell_groups=FALSE,
           show_trajectory_graph=FALSE)
pdf(file=paste("trajectories_deg_module_bygroup_rbp","pdf",sep="."),width = 8,height = 6)
print(p1)
dev.off()
png(file = paste("trajectories_deg_module_bygroup_rbp",".png",sep=""),width = 200,height = 150,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()

# plot_genes_in_pseudotime
lineage_cds <- cds[rowData(cds)$gene_short_name %in% pr_deg_rbps_ids_top10]
p1<-plot_genes_in_pseudotime(lineage_cds,
                         color_cells_by="group",
                         min_expr=0.5)
pdf(file=paste("trajectories_top10rbps_bygroup_in_pseudotime","pdf",sep="."),width = 6,height = 12)
print(p1)
dev.off()
png(file = paste("trajectories_top10rbps_bygroup_in_pseudotime",".png",sep=""),width = 150,height = 300,units = "mm",res = 300,pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(p1)
dev.off()