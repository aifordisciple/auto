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
# https://satijalab.org/seurat/pbmc3k_tutorial.html
# https://github.com/CostaLab/scrna_seurat_pipeline
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



# library(future)
# plan("multicore", workers = 16)

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
        help = "The cell analysis rds file"
    ),
    make_option(
        c("-d", "--dims"),
        action = "store",
        type = "integer",
        default = 20,
        help = "PCA dims number"
    ),
    make_option(
        c("-f", "--logfc"),
        action = "store",
        type = "double",
        default = 0.5,
        help = "log FC,default is 0.5"
    ),
    make_option(
        c("-a", "--defaultassay"),
        action = "store",
        type = "character",
        default = "RNA",
        help = "default assay"
    )
)
opt <- parse_args(OptionParser(option_list = option_list))


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
library("ggrepel")
library(tidyverse)
options(stringsAsFactors = FALSE)
library(grDevices)
library(gplots)
library(Seurat)
library(patchwork)

library(SeuratData)
library(cowplot)

library("future.apply")
suppressPackageStartupMessages(library(doParallel))



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

# opt$dims <- 25
# opt$infile <- "../2_cells_analysis/cells_analysis.rds"
# opt$samplelist <- "nodule,male_PTC,female_PTC"
# opt$listname <- "nodule,male_PTC,female_PTC"
# opt$comparelist <- "male_PTC:nodule,female_PTC:nodule,male_PTC:female_PTC"

# listnames <- strsplit(opt$listname,",")[[1]]
# groupnum = length(unique(listnames))
#####################################################################################
## preprocessing数据读取，数据对象建立
# We start by reading in the data. The Read10X function reads in the output of the cellranger pipeline from 10X, returning a unique molecular identified (UMI) count matrix. The values in this matrix represent the number of molecules for each feature (i.e. gene; row) that are detected in each cell (column).
#####################################################################################

# Load the PBMC dataset

sc.combined <- readRDS(file = opt$infile)
DefaultAssay(sc.combined) <- opt$defaultassay



if(opt$defaultassay=="SCT"){
	# 重新运行 SCTransform，覆盖现有的 SCT 模型
	# sc.combined <- SCTransform(sc.combined, assay = "RNA", new.assay.name = "SCT", verbose = FALSE)
	# 运行 PrepSCTFindMarkers
	sc.combined <- SCTransform(sc.combined, method = "glmGamPoi", verbose = TRUE)

	sc.combined <- PrepSCTFindMarkers(sc.combined)
}


#####################################################################################
## Identify differential expressed genes across conditions 差异基因分析
# Now that we've aligned the stimulated and control cells, we can start to do comparative analyses and look at the differences induced by stimulation. One way to look broadly at these changes is to plot the average expression of both the stimulated and control cells and look for genes that are visual outliers on a scatter plot. Here, we take the average expression of both the stimulated and control naive T cells and CD14 monocyte populations and generate the scatter plots, highlighting genes that exhibit dramatic responses to interferon stimulation.
#####################################################################################

## 鉴定差异基因
clusternum <- length(unique(factor(Idents(sc.combined))))

sc.idents.bak <- Idents(sc.combined)
# Idents(sc.combined) <- sc.idents.bak
maxIdents<- unique(factor(Idents(sc.combined)))
sc.combined$celltype.group <- paste(Idents(sc.combined), sc.combined$group, sep = "_")
sc.combined$celltype <- Idents(sc.combined)
Idents(sc.combined) <- "celltype.group"

compares <- strsplit(opt$comparelist,",")[[1]]

workdir <- getwd()



source("/Users/chengchao/biosource/besaltpipe/src/SingleCell/allsample/sc_genes_visualizations_function.r")

########################################################################

## 按照ptype做差异分析



## 鉴定差异基因，按照ptype分别做
Idents(sc.combined) <- sc.idents.bak
clusternum <- length(unique(factor(Idents(sc.combined))))
DefaultAssay(sc.combined) <- opt$defaultassay
sc.idents.bak <- Idents(sc.combined)
# Idents(sc.combined) <- sc.idents.bak

setwd(workdir)

deg_dir = paste(workdir,"/","deg_byall", sep="")
if(!file.exists(deg_dir)){
	dir.create(deg_dir)
}
setwd(deg_dir)
sc.idents.bak <- Idents(sc.combined)


get_diff_all <- function(test_group,ctrl_group){
	tryCatch(
			{
				FindMarkers(sc.combined,
											 ident.1 = test_group,
											 ident.2 = ctrl_group,
											 min.cells.group = 30,
											 logfc.threshold = 0.01,
											 only.pos = FALSE)
			},
			error=function(cond) {
				ret_code <<- -1
				data.frame()
			},
			finally={
			})
	
	}

plot_scatter_by_group <- function(test_group,ctrl_group){
		# cluster <- "CD4 Naive T"
		Idents(sc.combined) <- sc.idents.bak
		# Idents(sc.combined) <- "RBP"
		library(ggplot2)
		library(cowplot)
		theme_set(theme_cowplot())

		# sub.cells <- subset(sc.combined, idents = cid)
		# seurat.subset <- subset(x = sub.cells, subset = (group == test_group & group == ctrl_group) & (another_condition == "Ambigious"))
		# sub.cells <- subset(sc.combined,group == c(test_group,ctrl_group))
		sub.cells <- subset(sc.combined,group == c(test_group,ctrl_group))
		# sub.cells <- sub.cells@meta.data
		# table(sub.cells$group)

		degdir = getwd()

		top10 = rbind(top10_up,top10_down)

		expscatter_dir = paste("","expscatter", sep="")
		if(!file.exists(expscatter_dir)){
			dir.create(expscatter_dir)
		}

		setwd(expscatter_dir)

		tryCatch(
			{
				Idents(sub.cells) <- "ptype"
				avg.sub.cells <- log1p(AverageExpression(sub.cells, verbose = FALSE)$RNA)
				avg.sub.cells.data=data.frame(avg.sub.cells)
				avg.sub.cells.data$gene <- rownames(avg.sub.cells.data)
				# diffgenes  = subset(top10, cluster == cid)
				diffgenes  = top10
				genes.to.label = unique(rownames(diffgenes))
				print(genes.to.label)
				p1 <- ggplot(avg.sub.cells.data,aes_string(x=test_group,y=ctrl_group)) + 
						geom_point(
				aes(
					fill = ifelse(gene %in% genes.to.label, "blue", "black")
					),
					shape = 21,
					alpha = 0.6,
				) +

				scale_fill_manual(values = c("black", "red"))+

				ggtitle(paste("top10",sep=""))
				p1 <- LabelPoints(plot = p1, points = genes.to.label, repel = TRUE, max.overlaps=Inf, xnudge=0, ynudge=0)+NoLegend()
				ggsave(file=paste("top10_expscatter",".pdf",sep=""),width = 100,height = 100,units = "mm")
				ggsave(file=paste("top10_expscatter",".png",sep=""),width = 100,height = 100,units = "mm", dpi=300)
			},
			error=function(cond) {
				ret_code <<- -1
			},
			finally={
				print(paste("top10",sep=""))
			})
		

		setwd(degdir)

}

compare_group <- function(gid){
		
		groups <- strsplit(compares[gid],":")[[1]]
		test_group = groups[1]
		ctrl_group = groups[2]

		deg_dir2 = paste(deg_dir,"/",test_group,"_vs_", ctrl_group,"_deg", sep="")

		if(!file.exists(deg_dir2)){
			dir.create(deg_dir2)
		}

		setwd(deg_dir2)

		# https://blog.csdn.net/qq_18055167/article/details/104437236
		# diff_genes <- map_dfr(c(maxIdents,test_group,ctrl_group), get_diff)
		# Idents(sc.combined) <- "celltype.group"
		# diff_genes <- pmap_dfr(list(maxIdents,test_group,ctrl_group), get_diff)
		
		Idents(sc.combined) <- "ptype"
		# Idents(sc.combined) <- "grade"
		# Idents(sc.combined) <- "cnv"
		diff_genes<-""
		diff_genes <- get_diff_all(test_group,ctrl_group)
		# diff_genes <- future_mapply(get_diff,maxIdents,test_group,ctrl_group,future.seed = TRUE)

		# diff_genes <- diff_genes[ , c(1:2,4:6, 3, 7)]
		diff_genes <- diff_genes %>%
						dplyr::arrange(p_val)

		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_all_genes_export','.xls',sep=''))
		write.table(diff_genes,file=paste(test_group,'_vs_',ctrl_group,'_all_genes_export','.xls',sep=''),append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		saveRDS(diff_genes, file = "./diff_genes.rds")
# saveRDS(conserved_markers, file = "./conserved_markers.rds")
# saveRDS(combined_markers, file = "./combined_markers.rds")
		# 提取每个类群排名靠前的3个或10个保守标记物
		#上调

		
		diff_genes <- diff_genes %>%
						dplyr::arrange(-avg_log2FC, p_val)
		deg <- subset(diff_genes,avg_log2FC>=opt$logfc)
		# deg <- subset(deg,pct.1-pct.2>=0.15|pct.1-pct.2<=-0.15)
		deg <- subset(deg,p_val_adj<=0.05)

		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_filter_up_deg','.xls',sep=''))
		write.table(deg,file=paste(test_group,'_vs_',ctrl_group,'_filter_up_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		deg_up <- subset(diff_genes,avg_log2FC>=0)
		top3_up <<- deg_up %>% 
		top_n(n = 3, 
						wt = avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top3_up_deg','.xls',sep=''))
		write.table(top3_up,file=paste(test_group,'_vs_',ctrl_group,'_top3_up_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)
		
		top5_up <<- deg_up %>% 
		top_n(n = 5, 
						wt = avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top5_up_deg','.xls',sep=''))
		write.table(top5_up,file=paste(test_group,'_vs_',ctrl_group,'_top5_up_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		top10_up <<- deg_up %>% 
		top_n(n = 10, 
						wt = avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top10_up_deg','.xls',sep=''))
		write.table(top10_up,file=paste(test_group,'_vs_',ctrl_group,'_top10_up_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		top50_up <<- deg_up %>% 
		top_n(n = 50, 
						wt = avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top50_up_deg','.xls',sep=''))
		write.table(top50_up,file=paste(test_group,'_vs_',ctrl_group,'_top50_up_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		top100_up <<- deg_up %>% 
		top_n(n = 100, 
						wt = avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top100_up_deg','.xls',sep=''))
		write.table(top100_up,file=paste(test_group,'_vs_',ctrl_group,'_top100_up_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)



		diff_genes <- diff_genes %>%
						dplyr::arrange(avg_log2FC, p_val)
		deg <- subset(diff_genes,avg_log2FC<=-opt$logfc)
		# deg <- subset(deg,pct.1-pct.2>=0.15|pct.1-pct.2<=-0.15)
		deg <- subset(deg,p_val_adj<=0.05)

		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_filter_down_deg','.xls',sep=''))
		write.table(deg,file=paste(test_group,'_vs_',ctrl_group,'_filter_down_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		deg_down <- subset(diff_genes,avg_log2FC<0)
		top3_down <<- deg_down %>% 
		top_n(n = 3, 
						wt = -avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top3_down_deg','.xls',sep=''))
		write.table(top3_down,file=paste(test_group,'_vs_',ctrl_group,'_top3_down_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		top5_down <<- deg_down %>% 
		top_n(n = 5, 
						wt = -avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top5_down_deg','.xls',sep=''))
		write.table(top5_down,file=paste(test_group,'_vs_',ctrl_group,'_top5_down_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		top10_down <<- deg_down %>% 
		top_n(n = 10, 
						wt = -avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top10_down_deg','.xls',sep=''))
		write.table(top10_down,file=paste(test_group,'_vs_',ctrl_group,'_top10_down_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		top50_down <<- deg_down %>% 
		top_n(n = 50, 
						wt = -avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top50_down_deg','.xls',sep=''))
		write.table(top50_down,file=paste(test_group,'_vs_',ctrl_group,'_top50_down_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		top100_down <<- deg_down %>% 
		top_n(n = 100, 
						wt = -avg_log2FC)
		cat(c('Gene\t'),file=paste(test_group,'_vs_',ctrl_group,'_top100_down_deg','.xls',sep=''))
		write.table(top100_down,file=paste(test_group,'_vs_',ctrl_group,'_top100_down_deg','.xls',sep=''),
								append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)

		# pmap_dfr(list(maxIdents,test_group,ctrl_group), plot_scatter_by_group)
		expscatter_dir = paste("","expscatter", sep="")
		if(!file.exists(expscatter_dir)){
			dir.create(expscatter_dir)
		}

		showgene_dir = paste("","top5_geneplot", sep="")
		if(!file.exists(showgene_dir)){
			dir.create(showgene_dir)
		}

		plot_scatter_by_group(test_group,ctrl_group)
		# plot_scatter_by_group(0,test_group,ctrl_group)
		setwd("../")
	}


# opt$comparelist = "HighGrade:LowGrade"
compares <- strsplit(opt$comparelist,",")[[1]]
Idents(sc.combined) <- "ptype"

# future_lapply(1:length(compares), compare_group)

for(gid in 1:length(compares)){
	tryCatch(
			{
				compare_group(gid)
			},
			error=function(cond) {
				ret_code <<- -1
			},
			finally={
				print(paste("done compare: ",compares[gid],sep=""))
			})
}
