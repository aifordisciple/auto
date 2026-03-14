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
    c("-a", "--postname"),
    action = "store",
    type = "character",
    help = "post sample name, post vs pre"
  ),
  make_option(
    c("-b", "--prename"),
    action = "store",
    type = "character",
    help = "pre sample name, post vs pre"
  ),
  make_option(
    c("-s", "--source"),
    action = "store",
    type = "character",
    help = "selected cluster: 1,2,3,4"
  ),
  make_option(
    c("-t", "--target"),
    action = "store",
    type = "character",
    help = "target cluster: 5,6,7,8"
  ),
  make_option(
    c("-o", "--outdir"),
    action = "store",
    type = "character",
    help = "outdir",
    default = "./"
  ),
  make_option("--print",action = "store_true",default = FALSE,
    help = "输出cluster"),
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

postname <- opt$postname
prename <- opt$prename

# postname <- "DN_wk21"
# prename <- "Ctrl"

#####################################################################################

# CellTalk_dir <- paste("/data1/projects/single-cell/ABL2020-08035_Diabetic_Nephropathy/figures/fig4-cellchat/", "", sep = "")
CellTalk_dir <- opt$outdir


if (!file.exists(CellTalk_dir)) {
  dir.create(CellTalk_dir)
}
setwd(CellTalk_dir)




setwd(CellTalk_dir)
cellchat.post <- readRDS(file = paste("sample_",postname,"/cellchat.",postname, ".rds", sep = ""))
cellchat.pre <- readRDS(file = paste("sample_",prename,"/cellchat.",prename, ".rds", sep = ""))




##########################
# 两组样本比较，DN_wk21 vs Ctrl
##########################

setwd(CellTalk_dir)
pos.dataset <- postname
pre.dataset <- prename
cmpdir <- paste0("compare-", pos.dataset, "_vs_", pre.dataset)
if (!file.exists(cmpdir)) {
  dir.create(cmpdir)
}
setwd(cmpdir)
# Load CellChat object of each dataset and then merge together
# 注意顺序，后面的比前面的

# define the cell labels to lift up
a=levels(cellchat.pre@idents)
b=levels(cellchat.post@idents)
group.new = sort(unique(c(a,b)))
group.new

print(length(group.new))

if(opt$print){
  q()
}

cellchat.pre = liftCellChat(cellchat.pre, group.new)
cellchat.post = liftCellChat(cellchat.post, group.new)


object.list <- list(pre = cellchat.pre, post = cellchat.post)
names(object.list) <- c(pre.dataset,pos.dataset)
cellchat <- mergeCellChat(object.list, add.names = c(pre.dataset,pos.dataset))

# start

selected_cluster = c(1:length(group.new))
chat_cluster = c(1:length(group.new))

# source <- strsplit(opt$source,",")[[1]]
# target <- strsplit(opt$target,",")[[1]]
# source = as.numeric(source)
# target = as.numeric(target)

# selected_cluster = source
# chat_cluster = target

# Part I: Predict general principles of cell-cell communication

# Compare the total number of interactions and interaction strength

# 比较交互总数和交互强度
# 为了回答细胞间通讯是否增强的问题，CellChat比较了从不同生物条件下推断的细胞-细胞通讯网络的相互作用总数和相互作用强度。

gg1 <- compareInteractions(cellchat, show.legend = F, group = c(1, 2))
gg2 <- compareInteractions(cellchat, show.legend = F, group = c(1, 2), measure = "weight")
pdf(file = paste("compareInteractions", "pdf", sep = "."), width = 6, height = 3)
print(gg1 + gg2)
dev.off()
png(file = paste("compareInteractions", ".png", sep = ""), width = 150, height = 75, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(gg1 + gg2)
dev.off()

# Compare the number of interactions and interaction strength among different cell populations


# Differential number of interactions or interaction strength among different cell populations
# The differential number of interactions or interaction strength in the cell-cell communication network between two datasets can be visualized using circle plot, where red (or blue) colored edges represent increased (or decreased) signaling in the second dataset compared to the first one.

# 比较不同细胞群之间的相互作用次数和相互作用强度
# 为了确定哪些细胞群之间的相互作用显示出显着的变化，CellChat比较了不同细胞群之间的相互作用数量和相互作用强度。

# 不同细胞群之间的相互作用次数或相互作用强度的差异
# 两个数据集之间小区-小区通信网络中相互作用的差异数或相互作用强度可以使用圆图进行可视化，其中红（或蓝） 彩色边缘表示增加（或减少） 与第一个数据集相比，第二个数据集中的信号。

pdf(file = paste("netVisual_diffInteraction", "pdf", sep = "."), width = 8, height = 6)
netVisual_diffInteraction(cellchat, weight.scale = T)
netVisual_diffInteraction(cellchat, weight.scale = T, measure = "weight")
dev.off()
png(file = paste("netVisual_diffInteraction-1", ".png", sep = ""), width = 200, height = 150, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
netVisual_diffInteraction(cellchat, weight.scale = T)
dev.off()
png(file = paste("netVisual_diffInteraction-2", ".png", sep = ""), width = 200, height = 150, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
netVisual_diffInteraction(cellchat, weight.scale = T, measure = "weight")
dev.off()


# We can also show differential number of interactions or interaction strength in a greater details using a heatmap. The top colored bar plot represents the sum of column of values displayed in the heatmap (incoming signaling). The right colored bar plot represents the sum of row of values (outgoing signaling). In the colorbar, red (or blue) represents increased (or decreased) signaling in the second dataset compared to the first one.

# 我们还可以使用热图在更详细的细节中显示交互次数的差异或交互强度。顶部彩色条形图表示热图（传入信令）中显示的值列的总和。右侧彩色条形图表示值行的总和（传出信号）。在颜色条中，红（或蓝） 表示增加（或减少） 与第一个数据集相比，第二个数据集中的信号。

gg1 <- netVisual_heatmap(cellchat)
gg2 <- netVisual_heatmap(cellchat, measure = "weight")
pdf(file = paste("netVisual_heatmap", "pdf", sep = "."), width = 10, height = 5)
print(gg1 + gg2)
dev.off()
png(file = paste("netVisual_heatmap", ".png", sep = ""), width = 250, height = 125, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(gg1 + gg2)
dev.off()

# The differential network analysis only works for pairwise datasets. If there are more datasets for comparison, we can directly show the number of interactions or interaction strength between any two cell populations in each dataset.

# To better control the node size and edge weights of the inferred networks across different datasets, we compute the maximum number of cells per cell group and the maximum number of interactions (or interaction weights) across all datasets.

# 差分网络分析仅适用于成对数据集。如果有更多数据集可供比较，我们可以直接显示每个数据集中任意两个细胞群之间的相互作用次数或相互作用强度。

# 为了更好地控制不同数据集中推断网络的节点大小和边缘权重，我们计算每个像元组的最大像元数以及所有数据集的最大交互（或交互权重）数。

weight.max <- getMaxWeight(object.list, attribute = c("idents", "count"))

pdf(file = paste("netVisual_circle", "pdf", sep = "."), width = 10, height = 5)
par(mfrow = c(1, 2), xpd = TRUE)
for (i in 1:length(object.list)) {
  netVisual_circle(object.list[[i]]@net$count, weight.scale = T, label.edge = F, edge.weight.max = weight.max[2], edge.width.max = 12, title.name = paste0("Number of interactions - ", names(object.list)[i]))
}
dev.off()
png(file = paste("netVisual_circle", ".png", sep = ""), width = 250, height = 125, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
par(mfrow = c(1, 2), xpd = TRUE)
for (i in 1:length(object.list)) {
  netVisual_circle(object.list[[i]]@net$count, weight.scale = T, label.edge = F, edge.weight.max = weight.max[2], edge.width.max = 12, title.name = paste0("Number of interactions - ", names(object.list)[i]))
}
dev.off()


# 不同细胞类型之间的相互作用次数或相互作用强度的差异 - 未实现


# Differential number of interactions or interaction strength among different cell types
# 比较 2D 空间中的主要来源和目标
# 比较2D空间中传出和传入的相互作用强度，可以预先识别细胞群，并在不同数据集之间发送或接收信号发生重大变化。

num.link <- sapply(object.list, function(x) {
  rowSums(x@net$count) + colSums(x@net$count) - diag(x@net$count)
})
weight.MinMax <- c(min(num.link), max(num.link)) # control the dot size in the different datasets
gg <- list()
for (i in 1:length(object.list)) {
  gg[[i]] <- netAnalysis_signalingRole_scatter(object.list[[i]], title = names(object.list)[i], weight.MinMax = weight.MinMax)
}


pdf(file = paste("netAnalysis_signalingRole_scatter", "pdf", sep = "."), width = 10, height = 5)
patchwork::wrap_plots(plots = gg)
dev.off()
png(file = paste("netAnalysis_signalingRole_scatter", ".png", sep = ""), width = 250, height = 125, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
patchwork::wrap_plots(plots = gg)
dev.off()


# Part II: Identify the conserved and context-specific signaling pathways

# Compare the overall information flow of each signaling pathway
# We can identify the conserved and context-specific signaling pathways by simply comparing the information flow for each signaling pathway, which is defined by the sum of communication probability among all pairs of cell groups in the inferred network (i.e., the total weights in the network).

# This bar graph can be plotted in a stacked mode or not. Significant signaling pathways were ranked based on differences in the overall information flow within the inferred networks between NL and LS skin. The top signaling pathways colored red are enriched in NL skin, and these colored green were enriched in the LS skin.

# 第二部分：确定保守的和特定于上下文的信号通路
# 然后，CellChat可以根据它们在多种生物学条件下的细胞 - 细胞通信网络，识别具有更大（或更少）差异的信号网络，信号传导组以及保守的和特定于上下文的信号通路。

# 识别具有较大（或较小）差异的信令网络以及基于其功能/结构相似性的信令组
# CellChat根据其功能和拓扑相似性对推断的通信网络进行联合流形学习和分类。注意：此类分析适用于两个以上的数据集。

# 功能相似性：高度的功能相似性表明主要发送者和接收者相似，并且可以解释为两个信号通路或两个配体 - 受体对表现出相似和/或冗余的作用。注意：功能相似性分析不适用于具有不同细胞类型组成的多个datset。

# 结构相似性：使用结构相似性来比较其信令网络结构，而不考虑发送方和接收方的相似性。注意：结构相似性分析适用于具有相同细胞类型组成或细胞类型组成截然不同的多个数据集。

# 在这里，我们可以运行基于功能相似性的流形和分类学习分析，因为两个数据集具有相同的单元类型组成。


# 识别和可视化保守的和特定于上下文的信号通路
# 通过比较每个信号通路的信息流/相互作用强度，我们可以识别信号通路，（i）关闭，（ii）减少，（iii）打开或（iv）增加，通过改变它们在一个条件下与另一个条件的信息流。

# 比较每个信号通路的整体信息流
# 我们可以通过简单地比较每个信号通路的信息流来识别保守的和特定于上下文的信号通路，该通路由推断网络中所有细胞群对之间的通信概率总和（即网络中的总权重）定义。

# 此条形图可以在堆叠模式下绘制，也可以不以堆叠模式绘制。根据NL和LS皮肤之间推断网络内整体信息流的差异对显着的信号通路进行排名。红色的顶部信号通路在NL皮肤中富集，这些颜色的绿色在LS皮肤中富集。

gg1 <- rankNet(cellchat, mode = "comparison", stacked = T, do.stat = TRUE)
gg2 <- rankNet(cellchat, mode = "comparison", stacked = F, do.stat = TRUE)
pdf(file = paste("rankNet", "pdf", sep = "."), width = 10, height = 10)
print(gg1 + gg2)
dev.off()
png(file = paste("rankNet", ".png", sep = ""), width = 250, height = 250, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(gg1 + gg2)
dev.off()


# Compare outgoing (or incoming) signaling associated with each cell population
# The above analysis summarize the information from the outgoing and incoming signaling together. We can also compare the outgoing (or incoming) signaling pattern between two datasets, allowing to identify signaling pathways/ligand-receptors that exhibit different signaling patterns.

# We can combine all the identified signaling pathways from different datasets and thus compare them side by side, including outgoing signaling, incoming signaling and overall signaling by aggregating outgoing and incoming signaling together. NB: rankNet also shows the comparison of overall signaling, but it does not show the signaling strength in specific cell populations.

# 比较与每个细胞群相关的传出（或传入）信号传导
# 上述分析总结了来自传出和传入信令的信息。我们还可以比较两个数据集之间的传出（或传入）信号模式，从而识别表现出不同信号模式的信号通路/配体受体。

# 我们可以组合来自不同数据集的所有已识别的信令路径，从而将它们并排比较，包括传出信号，输入信号和整体信号，通过将传出和传入信号聚合在一起。注意：也显示了整体信号传导的比较，但它没有显示特定细胞群的信号传导强度。rankNet

i <- 1
# combining all the identified signaling pathways from different datasets
pathway.union <- union(object.list[[i]]@netP$pathways, object.list[[i + 1]]@netP$pathways)
ht1 <- netAnalysis_signalingRole_heatmap(object.list[[i]], pattern = "outgoing", signaling = pathway.union, title = names(object.list)[i], width = 10, height = 22)
ht2 <- netAnalysis_signalingRole_heatmap(object.list[[i + 1]], pattern = "outgoing", signaling = pathway.union, title = names(object.list)[i + 1], width = 10, height = 22)
pdf(file = paste("netAnalysis_signalingRole_heatmap_outgoing", "pdf", sep = "."), width = 10, height = 10)
draw(ht1 + ht2, ht_gap = unit(0.5, "cm"))
dev.off()
png(file = paste("netAnalysis_signalingRole_heatmap_outgoing", ".png", sep = ""), width = 250, height = 250, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
draw(ht1 + ht2, ht_gap = unit(0.5, "cm"))
dev.off()


ht1 <- netAnalysis_signalingRole_heatmap(object.list[[i]], pattern = "incoming", signaling = pathway.union, title = names(object.list)[i], width = 10, height = 22, color.heatmap = "GnBu")
ht2 <- netAnalysis_signalingRole_heatmap(object.list[[i + 1]], pattern = "incoming", signaling = pathway.union, title = names(object.list)[i + 1], width = 10, height = 22, color.heatmap = "GnBu")
pdf(file = paste("netAnalysis_signalingRole_heatmap_incoming", "pdf", sep = "."), width = 10, height = 10)
draw(ht1 + ht2, ht_gap = unit(0.5, "cm"))
dev.off()
png(file = paste("netAnalysis_signalingRole_heatmap_incoming", ".png", sep = ""), width = 250, height = 250, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
draw(ht1 + ht2, ht_gap = unit(0.5, "cm"))
dev.off()


ht1 <- netAnalysis_signalingRole_heatmap(object.list[[i]], pattern = "all", signaling = pathway.union, title = names(object.list)[i], width = 10, height = 25, color.heatmap = "OrRd")
ht2 <- netAnalysis_signalingRole_heatmap(object.list[[i + 1]], pattern = "all", signaling = pathway.union, title = names(object.list)[i + 1], width = 10, height = 25, color.heatmap = "OrRd")
pdf(file = paste("netAnalysis_signalingRole_heatmap_all", "pdf", sep = "."), width = 10, height = 15)
draw(ht1 + ht2, ht_gap = unit(0.5, "cm"))
dev.off()
png(file = paste("netAnalysis_signalingRole_heatmap_all", ".png", sep = ""), width = 250, height = 375, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
draw(ht1 + ht2, ht_gap = unit(0.5, "cm"))
dev.off()


# Part III: Identify the upgulated and down-regulated signaling ligand-receptor pairs
# Identify dysfunctional signaling by comparing the communication probabities
# We can compare the communication probabilities mediated by ligand-receptor pairs from some cell groups to other cell groups. This can be done by setting comparison in the function netVisual_bubble.

# 第三部分：确定上调和下调的信号传导配体-受体对
# 通过比较通信概率来识别功能失调的信号传导
# 我们可以比较由配体 - 受体对介导的来自某些细胞群与其他细胞组的通信概率。这可以通过在 函数 中设置来完成。comparisonnetVisual_bubble

pdf(file = paste("netVisual_bubble_out_selected_cell", "pdf", sep = "."), width = 15, height = 15)
netVisual_bubble(cellchat, sources.use = selected_cluster, targets.use = chat_cluster, comparison = c(1, 2), angle.x = 45)
dev.off()

pdf(file = paste("netVisual_bubble_in_selected_cell", "pdf", sep = "."), width = 15, height = 15)
netVisual_bubble(cellchat, sources.use = chat_cluster, targets.use = selected_cluster, comparison = c(1, 2), angle.x = 45)
dev.off()


# Moreover, we can identify the upgulated (increased) and down-regulated (decreased) signaling ligand-receptor pairs in one dataset compared to the other dataset. This can be done by specifying max.dataset and min.dataset in the function netVisual_bubble. The increased signaling means these signaling have higher communication probability (strength) in one dataset compared to the other dataset.


gg1 <- netVisual_bubble(cellchat, sources.use = selected_cluster, targets.use = chat_cluster, comparison = c(1, 2), max.dataset = 2, title.name = paste0("Increased signaling in ", names(object.list)[2]), angle.x = 45, remove.isolate = T)
gg2 <- netVisual_bubble(cellchat, sources.use = selected_cluster, targets.use = chat_cluster, comparison = c(1, 2), max.dataset = 1, title.name = paste0("Decreased signaling in ", names(object.list)[2]), angle.x = 45, remove.isolate = T)

pdf(file = paste("netVisual_bubble_updown_out_selected_cell", "pdf", sep = "."), width = 30, height = 15)
print(gg1 + gg2)
dev.off()


cat(c(''),file=paste(postname,'_vs_',prename,'.up.probability.sub.out','.xls',sep=''))
write.table(gg1$data,file=paste(postname,'_vs_',prename,'.up.probability.sub.out','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

cat(c(''),file=paste(postname,'_vs_',prename,'.down.probability.sub.out','.xls',sep=''))
write.table(gg2$data,file=paste(postname,'_vs_',prename,'.down.probability.sub.out','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)


gg1 <- netVisual_bubble(cellchat, sources.use = chat_cluster, targets.use = selected_cluster, comparison = c(1, 2), max.dataset = 2, title.name = paste0("Increased signaling in ", names(object.list)[2]), angle.x = 45, remove.isolate = T)
gg2 <- netVisual_bubble(cellchat, sources.use = chat_cluster, targets.use = selected_cluster, comparison = c(1, 2), max.dataset = 1, title.name = paste0("Decreased signaling in ", names(object.list)[2]), angle.x = 45, remove.isolate = T)

pdf(file = paste("netVisual_bubble_updown_in_selected_cell", "pdf", sep = "."), width = 30, height = 15)
print(gg1 + gg2)
dev.off()


cat(c(''),file=paste(postname,'_vs_',prename,'.up.probability.sub.in','.xls',sep=''))
write.table(gg1$data,file=paste(postname,'_vs_',prename,'.up.probability.sub.in','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

cat(c(''),file=paste(postname,'_vs_',prename,'.down.probability.sub.in','.xls',sep=''))
write.table(gg2$data,file=paste(postname,'_vs_',prename,'.down.probability.sub.in','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

# 使用差异表达分析识别功能失调的信号传导
# 上述识别上调和下调信号传导的方法通过比较每个L-R对和每对细胞群的两个数据集之间的通信概率来实现。或者，我们可以基于差异基因表达分析鉴定上调和下调的信号传导配体 - 受体对。具体而言，我们对每个细胞群进行两种生物条件（即NL和LS）之间的差异表达分析，然后根据发送细胞中配体的折叠变化和受体细胞中的受体获得上调和下调信号传导。这种分析可以按如下方式进行。

# Identify dysfunctional signaling by using differential expression analysis
# perform differential expression analysis
cellchat <- identifyOverExpressedGenes(cellchat, group.dataset = "cell_group", pos.dataset = pos.dataset, features.name = pos.dataset, only.pos = FALSE, thresh.pc = 0.1, thresh.fc = 0.1, thresh.p = 1)
# map the results of differential expression analysis onto the inferred cell-cell communications to easily manage/subset the ligand-receptor pairs of interest
net <- netMappingDEG(cellchat, features.name = pos.dataset)
cat(c(''),file=paste(postname,'_vs_',prename,'_net_deg','.xls',sep=''))
write.table(net,file=paste(postname,'_vs_',prename,'_net_deg','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)
# # extract the ligand-receptor pairs with upregulated ligands in LS
# net.up <- subsetCommunication(cellchat, net = net, datasets = pos.dataset, ligand.logFC = 0.3, receptor.logFC = 0.3)
# # extract the ligand-receptor pairs with upregulated ligands and upregulated recetptors in NL, i.e.,downregulated in LS
# net.down <- subsetCommunication(cellchat, net = net, datasets = pre.dataset, ligand.logFC = 0.3, receptor.logFC = 0.3)
# extract the ligand-receptor pairs with upregulated ligands in LS
net.up <- subsetCommunication(cellchat, net = net, datasets = pos.dataset,ligand.logFC = 0.1, receptor.logFC = 0.1)
cat(c(''),file=paste(postname,'_vs_',prename,'_net.up','.xls',sep=''))
write.table(net.up,file=paste(postname,'_vs_',prename,'_net.up','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)
# extract the ligand-receptor pairs with upregulated ligands and upregulated recetptors in NL, i.e.,downregulated in LS
net.down <- subsetCommunication(cellchat, net = net, datasets = pre.dataset,ligand.logFC = -0.1, receptor.logFC = -0.1)
cat(c(''),file=paste(postname,'_vs_',prename,'_net.down','.xls',sep=''))
write.table(net.down,file=paste(postname,'_vs_',prename,'_net.down','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)
# Since the signaling genes in the net.up and net.down might be complex with multi-subunits, we can do further deconvolution to obtain the individual signaling genes.

gene.up <- extractGeneSubsetFromPair(net.up, cellchat)
gene.down <- extractGeneSubsetFromPair(net.down, cellchat)
# We then visualize the upgulated and down-regulated signaling ligand-receptor pairs using bubble plot or chord diagram.
# 我们使用气泡图或弦图可视化上调和下调的信号配体 - 受体对。


net.up.sub <- subsetCommunication(cellchat, net = net, datasets = pos.dataset,ligand.logFC = 0.1, receptor.logFC = 0.1, sources.use = selected_cluster, targets.use = chat_cluster)
cat(c(''),file=paste(postname,'_vs_',prename,'_net.up.sub.out','.xls',sep=''))
write.table(net.up.sub,file=paste(postname,'_vs_',prename,'_net.up.sub.out','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

pairLR.use.up <- net.up.sub[, "interaction_name", drop = F]
gg1 <- netVisual_bubble(cellchat, pairLR.use = pairLR.use.up, sources.use = selected_cluster, targets.use = chat_cluster, comparison = c(1, 2), angle.x = 90, remove.isolate = T, title.name = paste0("Up-regulated signaling in ", names(object.list)[2]))

net.down.sub <- subsetCommunication(cellchat, net = net, datasets = pre.dataset,ligand.logFC = -0.1, receptor.logFC = -0.1, sources.use = selected_cluster, targets.use = chat_cluster)
cat(c(''),file=paste(postname,'_vs_',prename,'_net.down.sub.out','.xls',sep=''))
write.table(net.down.sub,file=paste(postname,'_vs_',prename,'_net.down.sub.out','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

pairLR.use.down <- net.down.sub[, "interaction_name", drop = F]
gg2 <- netVisual_bubble(cellchat, pairLR.use = pairLR.use.down, sources.use = selected_cluster, targets.use = chat_cluster, comparison = c(1, 2), angle.x = 90, remove.isolate = T, title.name = paste0("Down-regulated signaling in ", names(object.list)[2]))
pdf(file = paste("netVisual_bubble_deg_out_selected_cell", "pdf", sep = "."), width = 20, height = 15)
print(gg1 + gg2)
dev.off()
png(file = paste("netVisual_bubble_deg_out_selected_cell", ".png", sep = ""), width = 500, height = 375, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(gg1 + gg2)
dev.off()

net.up.sub <- subsetCommunication(cellchat, net = net, datasets = pos.dataset,ligand.logFC = 0.1, receptor.logFC = 0.1, sources.use = chat_cluster, targets.use = selected_cluster)
cat(c(''),file=paste(postname,'_vs_',prename,'_net.up.sub.in','.xls',sep=''))
write.table(net.up.sub,file=paste(postname,'_vs_',prename,'_net.up.sub.in','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

pairLR.use.up <- net.up.sub[, "interaction_name", drop = F]
gg1 <- netVisual_bubble(cellchat, pairLR.use = pairLR.use.up, sources.use = chat_cluster, targets.use = selected_cluster, comparison = c(1, 2), angle.x = 90, remove.isolate = T, title.name = paste0("Up-regulated signaling in ", names(object.list)[2]))
net.down.sub <- subsetCommunication(cellchat, net = net, datasets = pre.dataset,ligand.logFC = -0.1, receptor.logFC = -0.1, sources.use = chat_cluster, targets.use = selected_cluster)
cat(c(''),file=paste(postname,'_vs_',prename,'_net.down.sub.in','.xls',sep=''))
write.table(net.down.sub,file=paste(postname,'_vs_',prename,'_net.down.sub.in','.xls',sep=''),append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)

pairLR.use.down <- net.down.sub[, "interaction_name", drop = F]
gg2 <- netVisual_bubble(cellchat, pairLR.use = pairLR.use.down, sources.use = chat_cluster, targets.use = selected_cluster, comparison = c(1, 2), angle.x = 90, remove.isolate = T, title.name = paste0("Down-regulated signaling in ", names(object.list)[2]))
pdf(file = paste("netVisual_bubble_deg_in_selected_cell", "pdf", sep = "."), width = 20, height = 15)
print(gg1 + gg2)
dev.off()
png(file = paste("netVisual_bubble_deg_in_selected_cell", ".png", sep = ""), width = 500, height = 375, units = "mm", res = 300, pointsize = 10)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
print(gg1 + gg2)
dev.off()


# Visualize the upgulated and down-regulated signaling ligand-receptor pairs using Chord diagram

# Chord diagram


# 使用弦图可视化上调和下调信号配体-受体对
net.up.sub <- subsetCommunication(cellchat, net = net, datasets = pos.dataset,ligand.logFC = 0.1, receptor.logFC = 0.1, sources.use = chat_cluster, targets.use = selected_cluster)
net.down.sub <- subsetCommunication(cellchat, net = net, datasets = pre.dataset,ligand.logFC = -0.1, receptor.logFC = -0.1, sources.use = chat_cluster, targets.use = selected_cluster)

pdf(file = paste("netVisual_chord_gene_deg_in_selected_cell", "pdf", sep = "."), width = 10, height = 10)
netVisual_chord_gene(object.list[[2]], sources.use = chat_cluster, targets.use = selected_cluster, slot.name = "net", net = net.up.sub, lab.cex = 0.8, small.gap = 1, title.name = paste0("Up-regulated signaling in ", names(object.list)[2]))
netVisual_chord_gene(object.list[[1]], sources.use = chat_cluster, targets.use = selected_cluster, slot.name = "net", net = net.down.sub, lab.cex = 0.8, small.gap = 1, title.name = paste0("Down-regulated signaling in ", names(object.list)[2]))
dev.off()

net.up.sub <- subsetCommunication(cellchat, net = net, datasets = pos.dataset,ligand.logFC = 0.1, receptor.logFC = 0.1, sources.use = selected_cluster, targets.use = chat_cluster)
net.down.sub <- subsetCommunication(cellchat, net = net, datasets = pre.dataset,ligand.logFC = -0.1, receptor.logFC = -0.1, sources.use = selected_cluster, targets.use = chat_cluster)

pdf(file = paste("netVisual_chord_gene_deg_out_selected_cell", "pdf", sep = "."), width = 10, height = 10)
netVisual_chord_gene(object.list[[2]], sources.use = selected_cluster, targets.use = chat_cluster, slot.name = "net", net = net.up.sub, lab.cex = 0.8, small.gap = 1, title.name = paste0("Up-regulated signaling in ", names(object.list)[2]))
netVisual_chord_gene(object.list[[1]], sources.use = selected_cluster, targets.use = chat_cluster, slot.name = "net", net = net.down.sub, lab.cex = 0.8, small.gap = 1, title.name = paste0("Down-regulated signaling in ", names(object.list)[2]))
dev.off()


# 使用和弦图，CellChat提供了两个功能，用于可视化具有不同目的和不同级别的细胞 - 细胞通信。 用于可视化不同细胞群之间的细胞 - 细胞通讯（其中弦图中的每个扇区都是一个细胞群），并用于可视化由多个配体 - 受体或信号通路（其中弦图中的每个扇区是配体，受体或信号通路）介导的细胞 - 细胞通讯。

pdf(file = paste("netVisual_chord_gene_to_selected_cell_netP", "pdf", sep = "."), width = 20, height = 20)
# par(mfrow = c(1, 2), xpd=TRUE)
for (i in 1:length(object.list)) {
  netVisual_chord_gene(object.list[[i]], sources.use = chat_cluster, targets.use = selected_cluster,slot.name = "netP", lab.cex = 0.8, small.gap = 1, title.name = paste0("signaling received by selected cell - ", names(object.list)[i]))
} 
dev.off()

pdf(file = paste("netVisual_chord_gene_from_selected_cell_netP", "pdf", sep = "."), width = 20, height = 20)
# par(mfrow = c(1, 2), xpd=TRUE)
for (i in 1:length(object.list)) {
  netVisual_chord_gene(object.list[[i]], sources.use = selected_cluster, targets.use = chat_cluster,slot.name = "netP", lab.cex = 0.8, small.gap = 1, title.name = paste0("signaling sending from selected cell - ", names(object.list)[i]))
} 
dev.off()

png(file = paste("netVisual_chord_gene_to_selected_cell_netP", "png", sep = "."), width = 1000, height = 500, units = "mm", res = 300, pointsize = 10)
par(mfrow = c(1, 2), xpd=TRUE)
for (i in 1:length(object.list)) {
  netVisual_chord_gene(object.list[[i]], sources.use = chat_cluster, targets.use = selected_cluster,slot.name = "netP", lab.cex = 0.8, small.gap = 1, title.name = paste0("signaling received by selected cell - ", names(object.list)[i]))
} 
dev.off()

png(file = paste("netVisual_chord_gene_from_selected_cell_netP", "png", sep = "."), width = 1000, height = 500, units = "mm", res = 300, pointsize = 10)
par(mfrow = c(1, 2), xpd=TRUE)
for (i in 1:length(object.list)) {
  netVisual_chord_gene(object.list[[i]], sources.use = selected_cluster, targets.use = chat_cluster,slot.name = "netP", lab.cex = 0.8, small.gap = 1, title.name = paste0("signaling sending from selected cell - ", names(object.list)[i]))
} 
dev.off()



#############


# pdf(file = paste("netVisual_chord_gene_to_selected_cell_net", "pdf", sep = "."), width = 20, height = 20)
# # par(mfrow = c(1, 2), xpd=TRUE)
# for (i in 1:length(object.list)) {
#   netVisual_chord_gene(object.list[[i]], sources.use = chat_cluster, targets.use = selected_cluster,slot.name = "net", lab.cex = 0.8, small.gap = 0, title.name = paste0("signaling received by selected cell - ", names(object.list)[i]))
# } 
# dev.off()

# pdf(file = paste("netVisual_chord_gene_from_selected_cell_net", "pdf", sep = "."), width = 20, height = 20)
# # par(mfrow = c(1, 2), xpd=TRUE)
# for (i in 1:length(object.list)) {
#   netVisual_chord_gene(object.list[[i]], sources.use = selected_cluster, targets.use = chat_cluster,slot.name = "net", lab.cex = 0.8, small.gap = 0, title.name = paste0("signaling sending from selected cell - ", names(object.list)[i]))
# } 
# dev.off()

# png(file = paste("netVisual_chord_gene_to_selected_cell_net", "png", sep = "."), width = 1000, height = 500, units = "mm", res = 300, pointsize = 10)
# par(mfrow = c(1, 2), xpd=TRUE)
# for (i in 1:length(object.list)) {
#   netVisual_chord_gene(object.list[[i]], sources.use = chat_cluster, targets.use = selected_cluster,slot.name = "net", lab.cex = 0.8, small.gap = 0, title.name = paste0("signaling received by selected cell - ", names(object.list)[i]))
# } 
# dev.off()

# png(file = paste("netVisual_chord_gene_from_selected_cell_net", "png", sep = "."), width = 1000, height = 500, units = "mm", res = 300, pointsize = 10)
# par(mfrow = c(1, 2), xpd=TRUE)
# for (i in 1:length(object.list)) {
#   netVisual_chord_gene(object.list[[i]], sources.use = selected_cluster, targets.use = chat_cluster,slot.name = "net", lab.cex = 0.8, small.gap = 0, title.name = paste0("signaling sending from selected cell - ", names(object.list)[i]))
# } 
# dev.off()




# Part IV: Visually compare cell-cell communication using Hierarchy plot, Circle plot or Chord diagram

# 第 IV 部分：使用层次结构图、圆图或和弦图直观地比较小区间通信
# 与单个数据集的CellChat分析类似，我们可以使用层次结构图，圆图或弦图来可视化细胞 - 细胞通信网络。

# 边缘颜色/权重、节点颜色/大小/形状：在所有可视化图中，边缘颜色与作为发送方的源一致，并且边缘权重与交互强度成正比。较粗的边缘线表示信号越强。在层次结构图和圆图中，圆的大小与每个像元组中的像元数成正比。在层次结构图中，实心圆和开放圆分别表示源和目标。在和弦图中，内部较细的条形颜色表示从相应的外条接收信号的目标。内部条形大小与目标接收到的信号强度成正比。这样的内条有助于解释复杂的和弦图。请注意，对于某些单元组，存在一些没有任何和弦的内部条，请将其删除，因为这是circlize包尚未解决的问题。

## 每个信号通路的可视化图
tmpdir2 <- paste("", "all_signaling_pathways", sep = "")
if (!file.exists(tmpdir2)) {
  dir.create(tmpdir2)
}
setwd(tmpdir2)

# Access all the signaling pathways showing significant communications
pathways.show.all <- object.list[[1]]@netP$pathways
pathways.show.all2 <- object.list[[2]]@netP$pathways
# check the order of cell identity to set suitable vertex.receiver
levels(object.list[[1]]@idents)
vertex.receiver <- seq(1, 4)
for (i in 1:length(pathways.show.all)) {
  if (pathways.show.all[i] %ni% pathways.show.all2) {
    next
  }
  # Visualize communication network associated with both signaling pathway and individual L-R pairs
  pdf(file = paste0(pathways.show.all[i], "_circle.pdf"), width = 8, height = 8)
  weight.max <- getMaxWeight(object.list, slot.name = c("netP"), attribute = pathways.show.all[i]) # control the edge weights across different datasets
  par(mfrow = c(1, 2), xpd = TRUE)
  for (j in 1:length(object.list)) {
    netVisual_aggregate(object.list[[j]], signaling = pathways.show.all[i], layout = "circle", edge.weight.max = weight.max[1], edge.width.max = 10, signaling.name = paste(pathways.show.all[i], names(object.list)[j]))
  }
  dev.off()

  pdf(file = paste0(pathways.show.all[i], "_heatmap.pdf"), width = 8, height = 8)
  par(mfrow = c(1, 2), xpd = TRUE)
  ht <- list()
  for (j in 1:length(object.list)) {
    ht[[j]] <- netVisual_heatmap(object.list[[j]], signaling = pathways.show.all[i], color.heatmap = "Reds", title.name = paste(pathways.show.all[i], "signaling ", names(object.list)[j]))
  }
  ComplexHeatmap::draw(ht[[1]] + ht[[2]], ht_gap = unit(0.5, "cm"))
  dev.off()

  cellchat@meta$cell_group <- factor(cellchat@meta$cell_group, levels = c(pre.dataset, pos.dataset)) # set factor level
  gg <- plotGeneExpression(cellchat, signaling = pathways.show.all[i], split.by = "cell_group", colors.ggplot = T)
  ggsave(filename = paste0(pathways.show.all[i], "_GeneExpression.pdf"), plot = gg, width = 500, height = 500, units = "mm", dpi = 300)
}


setwd("../")

# end


# Save the merged CellChat object
saveRDS(cellchat, file = paste0("cellchat_", pos.dataset, "_vs_", pre.dataset, ".rds"))
