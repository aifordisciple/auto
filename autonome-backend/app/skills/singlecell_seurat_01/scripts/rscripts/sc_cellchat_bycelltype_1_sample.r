#!/usr/bin/env Rscript

### Set VERSION
VERSION <- "1.0.0"

args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 1 && (args[1] == "-v" | args[1] == "--version")) {
  message("Version: \n\t", VERSION, "\n")
  quit(status = 0)
}

####################################################################################
### Copyright (C) 2019-2022 by biosalt
####################################################################################
# 名称：single cell pipeline
# 描述：单细胞分析流程,使用cellchat进行细胞通讯分析
# 作者：CHAO CHENG
# 创建时间：2021-8-20
# 联系方式：chengchao@biosalt.cc
####################################################################################
### 修改记录
####################################################################################
# Date           Version       Author            ChangeLog

#####################################################################################
#####################################################################################
##### 参考说明
# https://htmlpreview.github.io/?https://github.com/sqjin/CellChat/blob/master/tutorial/CellChat-vignette.html
# https://htmlpreview.github.io/?https://github.com/sqjin/CellChat/blob/master/tutorial/Comparison_analysis_of_multiple_datasets.html
#####################################################################################




#####################################################################################
##### 参数获取
#####################################################################################
# windows系统检查当前程序路径
# script.dir <- dirname(sys.frame(1)$ofile)

library(tidyverse)
get_this_file <- function() {
  commandArgs() %>%
    tibble::enframe(name = NULL) %>%
    tidyr::separate(col = value, into = c("key", "value"), sep = "=", fill = "right") %>%
    dplyr::filter(key == "--file") %>%
    dplyr::pull(value)
}
script.dir <- get_this_file()

setwd("./")

suppressPackageStartupMessages(library(optparse)) ## Options
suppressPackageStartupMessages(library(futile.logger)) ## logger
suppressPackageStartupMessages(library("stats"))
suppressPackageStartupMessages(library(dplyr))
`%ni%` <- Negate(`%in%`)

# The Bioconductor package SingleCellExperiment provides the SingleCellExperiment classfor usage.While the package is implicitly installed and loaded when using any package that depends on the SingleCellExperiment class, it can be explicitly installed(and loaded) as follows: #install.packages("BiocManager")# BiocManager::install(c('SingleCellExperiment', 'Rtsne', 'scater', 'scran', 'uwot'))
# library(SingleCellExperiment)
# #library(scater)

library("ggplot2")
options(stringsAsFactors = FALSE)
library(grDevices)
library(gplots)
library(pheatmap)
library(Seurat)
library(patchwork)
library(SeuratWrappers)
# library(monocle3)
# library(SeuratData)
library(cowplot)
library("future.apply")
suppressPackageStartupMessages(library(doParallel))
library(dplyr)
# 加载需要的R包
library(CellChat)
library(NMF)
library(ggalluvial)
library(ComplexHeatmap)

## 参数读取
option_list <- list(
  make_option(
    c("-n", "--ncpus"),
    action = "store",
    type = "integer",
    default = 4,
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
    c("-i", "--infile"),
    action = "store",
    type = "character",
    help = "The cell analysis rds file"
  ),
  make_option(
    c("-g", "--groupname"),
    action = "store",
    type = "character",
    help = "The groupname name"
  ),
  make_option(
    c("-s", "--species"),
    action = "store",
    type = "character",
    default = "human",
    help = "human or mouse"
  ),
  make_option(
    c("-k", "--keep"),
    action = "store",
    type = "character",
    default = "",
    help = "ex: 3,5,7 clusters need to keep, default is all. "
  )
)
opt <- parse_args(OptionParser(option_list = option_list))

registerDoParallel(cores = opt$ncpus)
plan("multisession", workers = opt$ncpus)
options(future.globals.maxSize = opt$MaxMemMega * 1024^2)

# opt$samplelist <- "Con,Ctrl,gname,OB2"
# opt$listname <- "Con,Ctrl,OB,OB"
# opt$comparelist <- "OB:Con,Ctrl:Con,OB:Ctrl"

# listnames <- strsplit(opt$listname,",")[[1]]
# groupnum = length(unique(listnames))

## 测试参数
# We start by reading in the data. The Read10X function reads in the output of the cellranger pipeline from 10X, returning a unique molecular identified (UMI) count matrix. The values in this matrix represent the number of molecules for each feature (i.e. gene; row) that are detected in each cell (column).

# opt$dims <- 50

# opt$infile <- "/data1/scRNA_data/DEV2020-10001_seurat/basic/pairsample/result/singlecell/3_cells_annotation/cells_annotation.rds"

# opt$infile <- "/data1/projects/single-cell/RX-7710499_pancreatic_cancer/figures/fig2-RBP/bycell/Macrophage_cell/cellchat/cnv.rds"
# infile2 <- "/data1/projects/single-cell/RX-7710499_pancreatic_cancer/figures/fig2-RBP/bycell/Macrophage_cell/RBP_post_reUMAP.rds"
# infile3 <- "/data1/projects/single-cell/RX-7710499_pancreatic_cancer/figures/fig2-RBP/bycell/Ductal_cell/RBP_post_reUMAP.rds"

gname = opt$groupname
# gname = "Highgroup"

#####################################################################################

# Load the PBMC dataset

# 直接通过seurat生成的rds文件的方式进行转换为CellDataSet对象
sc.combined <- readRDS(file = opt$infile)

sc.combined$cellcluster <- sc.combined$customclassif

# keeps <- c(0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,27)
# sc.combined <- subset(sc.combined, idents= keeps)

CellTalk_dir <- paste("./", "", sep = "")
if (!file.exists(CellTalk_dir)) {
  dir.create(CellTalk_dir)
}
setwd(CellTalk_dir)


# 从文件读取表达量
# countfiles <- "/data1/projects/single-cell/ABL2020-10001-N_Rat_Bladder_fibrosis/basic/BD_pileline_20210727_without_rep/result/singlecell/4_advanced_analysis/CellTalk_cellPhoneDB/sc_counts.txt"
# data <- read.table(file = countfiles,header = T,com = '',sep = "\t",quote = NULL,check.names = F,row.names = 1)
# data <- as.matrix(data)
# saveRDS(data, file = "exp.rds")

# 从seurat对象读取表达量
# data <- as.matrix(sc.combined@assays$RNA@data)
data <- sc.combined[["RNA"]]$data
head(data)

# 替换
original = as.matrix(sc.combined$cellcluster)

meta <- data.frame(cell_type = as.character(original), cell_group = sc.combined@meta.data$group)
rownames(meta) <- rownames(sc.combined@meta.data)
# meta <- meta %>%
#   mutate(newcelltype = paste0("cluster", cell_type))
head(meta)

# write.table(sc.combined.meta, "sc_meta.txt", row.names=F, sep='\t')


# Prepare input data for CelChat analysis

cell.use <- rownames(meta)[meta$cell_group == gname] # extract the cell names from disease data
data.input <- data[, cell.use]
meta.input <- meta[cell.use, ]
unique(meta.input$cell_group) # check the cell labels
unique(meta.input$cell_type) # check the cell labels

cellchat.gname <- createCellChat(object = data.input, meta = meta.input, group.by = "cell_type")
table(cellchat.gname@idents) # number of cells in each cell group

unique(cellchat.gname@idents)

#  1 "cluster0"  "cluster1"  "cluster10" "cluster11" "cluster12" "cluster13"
#  7 "cluster14" "cluster15" "cluster16" "cluster17" "cluster18" "cluster19"
# 13 "cluster2"  "cluster20" "cluster21" "cluster22" "cluster23" "cluster24"
# 19 "cluster25" "cluster26" "cluster3"  "cluster4"  "cluster5"  "cluster6"
# 25 "cluster7"  "cluster8"  "cluster9"

# CellChatDB <- CellChatDB.mouse
# interaction_input <- CellChatDB$interaction
# complex_input <- CellChatDB$complex
# cofactor_input <- CellChatDB$cofactor
# geneInfo <- CellChatDB$geneIfo
# write.csv(interaction_input, file = "interaction_input_CellChatDB.csv")
# write.csv(complex_input, file = "complex_input_CellChat.csv")
# write.csv(cofactor_input, file = "cofactor_input_CellChat.csv")
# write.csv(geneInfo, file = "geneIfo.csv")
# # Second, you need to find the homologous genes in these files.
# # Third, run the following codes to update the database
# interaction_input <- read.csv(file = 'interaction_input_CellChatDB.csv')
# row.names(interaction_input) <- interaction_input[,1]
# complex_input <- read.csv(file = 'complex_input_CellChat.csv', row.names = 1)
# cofactor_input <- read.csv(file = 'cofactor_input_CellChat.csv', row.names = 1)
# # geneInfo <- read.csv(file = 'geneIfo.csv', row.names = 1)
# CellChatDB <- list()
# CellChatDB$interaction <- interaction_input
# CellChatDB$complex <- complex_input
# CellChatDB$cofactor <- cofactor_input
# CellChatDB$geneInfo <- geneInfo
# CellChatDB.rat <- CellChatDB



setwd(CellTalk_dir)
tmpdir <- paste("", "sample_",gname, sep = "")
if (!file.exists(tmpdir)) {
  dir.create(tmpdir)
}
setwd(tmpdir)

#### start

# Set the ligand-receptor interaction database
CellChatDB <- CellChatDB.human # use CellChatDB.mouse if running on mouse data, or CellChatDB.human if running on human data
if(opt$species == "mouse"){
  CellChatDB <- CellChatDB.mouse
}

# CellChatDB <- CellChatDB.mouse # use CellChatDB.mouse if running on mouse data, or CellChatDB.human if running on human data
showDatabaseCategory(CellChatDB)
# Show the structure of the database
dplyr::glimpse(CellChatDB$interaction)
CellChatDB.use <- CellChatDB # simply use the default CellChatDB
cellchat.gname@DB <- CellChatDB.use

# Preprocessing the expression data for cell-cell communication analysis
# subset the expression data of signaling genes for saving computation cost
cellchat.gname <- subsetData(cellchat.gname) # This step is necessary even if using the whole database
future::plan("multicore", workers = 4) # do parallel

cellchat.gname <- identifyOverExpressedGenes(cellchat.gname)
cellchat.gname <- identifyOverExpressedInteractions(cellchat.gname)

if(opt$species == "human"){
  cellchat.gname <- projectData(cellchat.gname, PPI.human)
}
if(opt$species == "mouse"){
  cellchat.gname <- projectData(cellchat.gname, PPI.mouse)
}
# cellchat.gname <- projectData(cellchat.gname, PPI.mouse)

# Part II: Inference of cell-cell communication network

# Compute the communication probability and infer cellular communication network
cellchat.gname <- computeCommunProb(cellchat.gname)
# Filter out the cell-cell communication if there are only few number of cells in certain cell groups
cellchat.gname <- filterCommunication(cellchat.gname, min.cells = 10)
# Extract the inferred cellular communication network as a data frame
# We provide a function subsetCommunication to easily access the inferred cell-cell communications of interest. For example,

# df.net <- subsetCommunication(cellchat) returns a data frame consisting of all the inferred cell-cell communications at the level of ligands/receptors. Set slot.name = "netP" to access the the inferred communications at the level of signaling pathways

# df.net <- subsetCommunication(cellchat, sources.use = c(1,2), targets.use = c(4,5)) gives the inferred cell-cell communications sending from cell groups 1 and 2 to cell groups 4 and 5.

# df.net <- subsetCommunication(cellchat, signaling = c("WNT", "TGFb")) gives the inferred cell-cell communications mediated by signaling WNT and TGFb.

# Infer the cell-cell communication at a signaling pathway level
# CellChat computes the communication probability on signaling pathway level by summarizing the communication probabilities of all ligands-receptors interactions associated with each signaling pathway.

# NB: The inferred intercellular communication network of each ligand-receptor pair and each signaling pathway is stored in the slot ‘net’ and ‘netP’, respectively.

cellchat.gname <- computeCommunProbPathway(cellchat.gname)
# Calculate the aggregated cell-cell communication network
# We can calculate the aggregated cell-cell communication network by counting the number of links or summarizing the communication probability. USER can also calculate the aggregated network among a subset of cell groups by setting sources.use and targets.use.

cellchat.gname <- aggregateNet(cellchat.gname)
# We can also visualize the aggregated cell-cell communication network. For example, showing the number of interactions or the total interaction strength (weights) between any two cell groups using circle plot.
cellchat.gname <- netAnalysis_computeCentrality(cellchat.gname, slot.name = "netP") # the slot 'netP' means the

groupSize <- as.numeric(table(cellchat.gname@idents))


setwd(CellTalk_dir)
saveRDS(cellchat.gname, file = paste0("cellchat.",gname,".rds"))

# Due to the complicated cell-cell communication network, we can examine the signaling sent from each cell group. Here we also control the parameter edge.weight.max so that we can compare edge weights between differet networks.
# 蜂窝网络
pdf(file = paste("cell_cell_commu_network", "pdf", sep = "."), width = 8, height = 6)
netVisual_circle(cellchat.gname@net$count, vertex.weight = groupSize, weight.scale = T, label.edge = F, title.name = "Number of interactions")
netVisual_circle(cellchat.gname@net$weight, vertex.weight = groupSize, weight.scale = T, label.edge = F, title.name = "Interaction weights/strength")
dev.off()

png(file = paste("cell_cell_commu_network-1", ".png", sep = ""), width = 200, height = 150, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
# par(mfrow = c(3,4), xpd=TRUE)
netVisual_circle(cellchat.gname@net$count, vertex.weight = groupSize, weight.scale = T, label.edge = F, title.name = "Number of interactions")
dev.off()
png(file = paste("cell_cell_commu_network-2", ".png", sep = ""), width = 200, height = 150, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
# par(mfrow = c(3,4), xpd=TRUE)
netVisual_circle(cellchat.gname@net$weight, vertex.weight = groupSize, weight.scale = T, label.edge = F, title.name = "Interaction weights/strength")
dev.off()

# 每个单元组发送的信号
mat <- cellchat.gname@net$weight
pdf(file = paste("network_from_each_cluster", "pdf", sep = "."), width = 8, height = 8)
for (i in 1:nrow(mat)) {
  mat2 <- matrix(0, nrow = nrow(mat), ncol = ncol(mat), dimnames = dimnames(mat))
  mat2[i, ] <- mat[i, ]
  netVisual_circle(mat2, vertex.weight = groupSize, weight.scale = T, edge.weight.max = max(mat), title.name = rownames(mat)[i])
}
dev.off()
png(file = paste("network_from_each_cluster", ".png", sep = ""), width = 200, height = 200, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
par(mfrow = c(3, 4), xpd = TRUE)
for (i in 1:nrow(mat)) {
  mat2 <- matrix(0, nrow = nrow(mat), ncol = ncol(mat), dimnames = dimnames(mat))
  mat2[i, ] <- mat[i, ]
  netVisual_circle(mat2, vertex.weight = groupSize, weight.scale = T, edge.weight.max = max(mat), title.name = rownames(mat)[i])
}
dev.off()



## 每个信号通路的可视化图
tmpdir2 <- paste("", "all_signaling_pathways", sep = "")
if (!file.exists(tmpdir2)) {
  dir.create(tmpdir2)
}
setwd(tmpdir2)

# Access all the signaling pathways showing significant communications
pathways.show.all <- cellchat.gname@netP$pathways
# check the order of cell identity to set suitable vertex.receiver
levels(cellchat.gname@idents)
vertex.receiver <- seq(1, 4)
for (i in 1:length(pathways.show.all)) {
  # Visualize communication network associated with both signaling pathway and individual L-R pairs
  netVisual(cellchat.gname, signaling = pathways.show.all[i], vertex.receiver = vertex.receiver, layout = "hierarchy", out.format = c("pdf"))
  netVisual(cellchat.gname, signaling = pathways.show.all[i], vertex.receiver = vertex.receiver, out.format = c("pdf"), layout = "circle")
  # netVisual(cellchat.gname, signaling = pathways.show.all[i], vertex.receiver = vertex.receiver, out.format = c("pdf"), layout = "chord")
  # Compute and visualize the contribution of each ligand-receptor pair to the overall signaling pathway

  pdf(file = paste0(pathways.show.all[i], "_heatmap.pdf"), width = 8, height = 8)
  netVisual_heatmap(cellchat.gname, signaling = pathways.show.all[i], color.heatmap = "Reds")
  dev.off()
  png(file = paste0(pathways.show.all[i], "_heatmap.png"), width = 200, height = 200, units = "mm", res = 300, pointsize = 10)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  netVisual_heatmap(cellchat.gname, signaling = pathways.show.all[i], color.heatmap = "Reds")
  dev.off()

  gg <- netAnalysis_contribution(cellchat.gname, signaling = pathways.show.all[i])
  ggsave(filename = paste0(pathways.show.all[i], "_L-R_contribution.pdf"), plot = gg, width = 500, height = 500, units = "mm", dpi = 300)

  gg <- plotGeneExpression(cellchat.gname, signaling = pathways.show.all[i])
  ggsave(filename = paste0(pathways.show.all[i], "_GeneExpression.pdf"), plot = gg, width = 300, height = 500, units = "mm", dpi = 300)
}
setwd("../")





# Visualize cell-cell communication mediated by multiple ligand-receptors or signaling pathways
# Bubble plot气泡图
# We can also show all the significant interactions (L-R pairs) from some cell groups to other cell groups using netVisual_bubble.

## plot all
gg <- netVisual_bubble(cellchat.gname, remove.isolate = FALSE)
ggsave(filename = paste0("", "netVisual_bubble.pdf"), plot = gg, width = 3000, height = 2000, units = "mm", dpi = 300, limitsize = FALSE)

# show all the significant interactions (L-R pairs) from some cell groups (defined by 'sources.use') to other cell groups (defined by 'targets.use')
# netVisual_bubble(cellchat.gname, sources.use = 10, targets.use = c(1:27), remove.isolate = FALSE)

# show all the significant interactions (L-R pairs) associated with certain signaling pathways
# netVisual_bubble(cellchat, sources.use = 10, targets.use = c(1:27), signaling = c("CCL","CXCL"), remove.isolate = FALSE)

# show all the significant interactions (L-R pairs) based on user's input (defined by `pairLR.use`)
# pairLR.use <- extractEnrichedLR(cellchat, signaling = c("CCL","CXCL","FGF"))
# netVisual_bubble(cellchat, sources.use = c(3,4), targets.use = c(5:8), pairLR.use = pairLR.use, remove.isolate = TRUE)


# show all the significant interactions (L-R pairs) from some cell groups (defined by 'sources.use') to other cell groups (defined by 'targets.use')
# show all the interactions sending from Inflam.FIB
# gg<-netVisual_chord_gene(cellchat, sources.use = 10, targets.use = c(1:27), lab.cex = 0.5,legend.pos.y = 30)
# ggsave(filename=paste0("","netVisual_chord_gene.pdf"), plot=gg, width = 3000, height = 2000, units = 'mm', dpi = 300,limitsize = FALSE)

# show all the interactions received by Inflam.DC
# gg<-netVisual_chord_gene(cellchat, sources.use = c(1,2,3,4), targets.use = 8, legend.pos.x = 15)

# show all the significant interactions (L-R pairs) associated with certain signaling pathways
# gg<-netVisual_chord_gene(cellchat, sources.use = c(1,2,3,4), targets.use = c(1:27), signaling = c("CCL","CXCL"),legend.pos.x = 8)
# ggsave(filename=paste0("","netVisual_chord_gene.pdf"), plot=gg, width = 3000, height = 2000, units = 'mm', dpi = 300,limitsize = FALSE)

# show all the significant signaling pathways from some cell groups (defined by 'sources.use') to other cell groups (defined by 'targets.use')
# gg<-netVisual_chord_gene(cellchat, sources.use = c(1,2,3,4), targets.use = c(1:27), slot.name = "netP", legend.pos.x = 10)
# ggsave(filename=paste0("","netVisual_chord_gene.pdf"), plot=gg, width = 3000, height = 2000, units = 'mm', dpi = 300,limitsize = FALSE)



# Part IV: Systems analysis of cell-cell communication network
# To facilitate the interpretation of the complex intercellular communication networks, CellChat quantitively measures networks through methods abstracted from graph theory, pattern recognition and manifold learning.

# It can determine major signaling sources and targets as well as mediators and influencers within a given signaling network using centrality measures from network analysis

# It can predict key incoming and outgoing signals for specific cell types as well as coordinated responses among different cell types by leveraging pattern recognition approaches.

# It can group signaling pathways by defining similarity measures and performing manifold learning from both functional and topological perspectives.

# It can delineate conserved and context-specific signaling pathways by joint manifold learning of multiple networks.

# Identify signaling roles (e.g., dominant senders, receivers) of cell groups as well as the major contributing signaling
# CellChat allows ready identification of dominant senders, receivers, mediators and influencers in the intercellular communication network by computing several network centrality measures for each cell group. Specifically, we used measures in weighted-directed networks, including out-degree, in-degree, flow betweenesss and information centrality, to respectively identify dominant senders, receivers, mediators and influencers for the intercellular communications. In a weighteddirected network with the weights as the computed communication probabilities, the outdegree, computed as the sum of communication probabilities of the outgoing signaling from a cell group, and the in-degree, computed as the sum of the communication probabilities of the incoming signaling to a cell group, can be used to identify the dominant cell senders and receivers of signaling networks, respectively. For the definition of flow betweenness and information centrality, please check our paper and related reference.

# Compute and visualize the network centrality scores
# Compute the network centrality scores
# cellchat.gname <- netAnalysis_computeCentrality(cellchat.gname, slot.name = "netP") # the slot 'netP' means the inferred intercellular communication network of signaling pathways
# Visualize the computed centrality scores using heatmap, allowing ready identification of major signaling roles of cell groups
# netAnalysis_signalingRole_network(cellchat.gname, signaling = pathways.show, width = 8, height = 2.5, font.size = 10)
# cellchat.gname <- netAnalysis_computeCentrality(cellchat.gname, slot.name = "netP")

pathways.show.all <- cellchat.gname@netP$pathways
# check the order of cell identity to set suitable vertex.receiver
levels(cellchat.gname@idents)
vertex.receiver <- seq(1, 4)
pdf(file = paste0("", "signalingRole.pdf"), width = 10, height = 6)
for (i in 1:length(pathways.show.all)) {
  # Visualize the computed centrality scores using heatmap, allowing ready identification of major signaling roles of cell groups
  netAnalysis_signalingRole_network(cellchat.gname, signaling = pathways.show.all[i], width = 10, height = 2.5, font.size = 10)
}
dev.off()

# Signaling role analysis on the aggregated cell-cell communication network from all signaling pathways
pdf(file = paste0("", "signalingRole_scatter.pdf"), width = 8, height = 8)
netAnalysis_signalingRole_scatter(cellchat.gname)
dev.off()


# Signaling role analysis on the aggregated cell-cell communication network from all signaling pathways
ht1 <- netAnalysis_signalingRole_heatmap(cellchat.gname, pattern = "outgoing", height = 22)
ht2 <- netAnalysis_signalingRole_heatmap(cellchat.gname, pattern = "incoming", height = 22)

pdf(file = paste0("", "netAnalysis_signalingRole_heatmap.pdf"), width = 10, height = 12)
print(ht1 + ht2)
dev.off()


# Signaling role analysis on the cell-cell communication networks of interest
# ht <- netAnalysis_signalingRole_heatmap(cellchat.Ctrl, signaling = c("CXCL", "CCL"))

#   Identify global communication patterns to explore how multiple cell types and signaling pathways coordinate together

pdf(file = paste0("", "outgoing_selectK.pdf"), width = 6, height = 4)
selectK(cellchat.gname, pattern = "outgoing")
dev.off()

# Both Cophenetic and Silhouette values begin to drop suddenly when the number of outgoing patterns is 3.


# heatmap plot
nPatterns <- 3
pdf(file = paste0("", "outgoing_heatmap.pdf"), width = 10, height = 20)
cellchat.gname <- identifyCommunicationPatterns(cellchat.gname, pattern = "outgoing", k = nPatterns, height = 22)
dev.off()

# river plot

pdf(file = paste0("", "outgoing_river.pdf"), width = 10, height = 12)
netAnalysis_river(cellchat.gname, pattern = "outgoing")
dev.off()

# dot plot

pdf(file = paste0("", "outgoing_dot.pdf"), width = 12, height = 12)
netAnalysis_dot(cellchat.gname, pattern = "outgoing")
dev.off()

# Both Cophenetic and Silhouette values begin to drop suddenly when the number of incoming patterns is 3.


pdf(file = paste0("", "incoming_selectK.pdf"), width = 6, height = 4)
selectK(cellchat.gname, pattern = "incoming")
dev.off()


# heatmap plot
nPatterns <- 6
pdf(file = paste0("", "incoming_heatmap.pdf"), width = 10, height = 20)
cellchat.gname <- identifyCommunicationPatterns(cellchat.gname, pattern = "incoming", k = nPatterns, height = 22)
dev.off()

# river plot

pdf(file = paste0("", "incoming_river.pdf"), width = 10, height = 12)
netAnalysis_river(cellchat.gname, pattern = "incoming")
dev.off()

# dot plot

pdf(file = paste0("", "incoming_dot.pdf"), width = 12, height = 12)
netAnalysis_dot(cellchat.gname, pattern = "incoming")
dev.off()

### end


setwd(CellTalk_dir)
saveRDS(cellchat.gname, file = paste0("cellchat.",gname,".rds"))