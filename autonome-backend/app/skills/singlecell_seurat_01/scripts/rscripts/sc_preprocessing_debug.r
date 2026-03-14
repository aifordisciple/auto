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

library(dplyr)
options(stringsAsFactors = FALSE)
library(grDevices)
library(gplots)
library(Seurat)
library(patchwork)
library(hdf5r)
library(DoubletFinder)
library("stats")
library("ggthemes")
library("reshape2")
library(harmony)
library(glmGamPoi)

library("future.apply")
suppressPackageStartupMessages(library(doParallel))



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
        c("--MinTotalUMI"),
        action = "store",
        type = "integer",
        default = 1000,
        help = "minimal total UMI count"
    ),
    make_option(
        c("--MinGenes"),
        action = "store",
        type = "integer",
        default = 500,
        help = "minimal genes"
    ),
    make_option(
        c("--MaxGenes"),
        action = "store",
        type = "integer",
        default = 8000,
        help = "max genes"
    ),
    make_option(
        c("--MaxMT"),
        action = "store",
        type = "integer",
        default = 15,
        help = "maximal percentage of mitochondria"
    ),
    make_option(
        c("--MinCellsInGene"),
        action = "store",
        type = "integer",
        default = 5,
        help = "minimal cells with UMI>0 in one gene"
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
        c("-f","--format"),
        action = "store",
        type = "character",
        default = "10x",
        help = "The count matrix file format, 10x or BD or h5 or rds"
    ),
    make_option(
        c("-b","--bdfiles"),
        action = "store",
        type = "character",
        help = "The count matrix file of sample"
    ),
    make_option(
        c("-m","--method"),
        action = "store",
        type = "character",
        default = "cca",
        help = "cca or rpca or sct_cca or sct_rpca or harmony or sct_harmony"
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
        help = "The data object rds file"
    )
)
opt <- parse_args(OptionParser(option_list = option_list))

registerDoParallel(cores=opt$ncpus)
plan("multisession", workers = opt$ncpus)
options(future.globals.maxSize = opt$MaxMemMega * 1024^2)


min_total_UMI = opt$MinTotalUMI
max_genes = opt$MaxGenes
min_genes = opt$MinGenes
max_MT = opt$MaxMT
min_cells_in_gene = opt$MinCellsInGene

# min_total_UMI = 1000
# max_genes = 8000
# min_genes = 500
# max_MT = 15
# min_cells_in_gene = 5


# opt$method = "sct_harmony"

# # # 测试参数
# opt$samplelist <- "2_yo,5_yo,8_yo,11_yo,17_yo,Adult_1,Adult_2,Adult_3,Adult_4,Adult_5,iNOA_1,iNOA_2,iNOA_3,AZFa_Del,KS_1,KS_2,KS_3"
# opt$listname <- "2_yo,5_yo,8_yo,11_yo,17_yo,Adult,Adult,Adult,Adult,Adult,iNOA,iNOA,iNOA,AZFa_Del,KS,KS,KS"
# opt$bdfiles <- "/data1/project/sperm/reads/GSE149512_sc/GSM4504189_LZ011matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504187_LZ009matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504184_LZ005matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504186_LZ008matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504194_LZ016matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504182_LZ003matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504185_LZ007matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504191_LZ013matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504192_LZ014matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504193_LZ015matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504195_LZ017matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504196_LZ018matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504197_LZ019matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504181_LZ002matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504183_LZ004matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504188_LZ010matrix.csv,/data1/project/sperm/reads/GSE149512_sc/GSM4504190_LZ012matrix.csv"
# opt$format <- "countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv,countcsv"


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

#####################################################################################
## 数据读取，数据对象建立
# We start by reading in the data. The Read10X function reads in the output of the cellranger pipeline from 10X, returning a unique molecular identified (UMI) count matrix. The values in this matrix represent the number of molecules for each feature (i.e. gene; row) that are detected in each cell (column).
#####################################################################################

# Load the PBMC dataset
# We next use the count matrix to create a Seurat object. The object serves as a container that contains both data (like the count matrix) and analysis (like PCA, or clustering results) for a single-cell dataset. For a technical discussion of the Seurat object structure, check out our GitHub Wiki (https://github.com/satijalab/seurat/wiki). For example, the count matrix is stored in pbmc[["RNA"]]@counts.
# Initialize the Seurat object with the raw (non-normalized data).

countfiles <- strsplit(opt$bdfiles,",")[[1]]
# annofiles <- strsplit(opt$annofiles,",")[[1]]
samplenames <- strsplit(opt$samplelist,",")[[1]]
listnames <- strsplit(opt$listname,",")[[1]]
umiformat <- strsplit(opt$format,",")[[1]]

groupnum = length(unique(listnames))

sc.list <- list()


cell_filter <- function(i){
    testcountfile <- ""
    if(umiformat[i] == "BD"){
        #BD docker流程分析结果tsv，row为cell, col为gene
        testcountfile <- read.table(file = countfiles[i],header = T,com = '',sep = "\t",quote = NULL,check.names = F,row.names = 1)
        testcountfile <- t(testcountfile)
    }
    if(umiformat[i] == "exp"){
        #row为gene, col为cell
        testcountfile <- read.table(file = countfiles[i],header = T,com = '',sep = "\t",quote = NULL,check.names = F,row.names = 1)
        # testcountfile <- t(testcountfile)
    }
    if(umiformat[i] == "expcsv"){
        #row为gene, col为cell
        testcountfile <- read.csv(file = countfiles[i],header = T,check.names = F,row.names = 1)
        # testcountfile <- t(testcountfile)
    }
    if(umiformat[i] == "countcsv"){
        #row为gene, col为cell
        testcountfile <- read.csv(file = countfiles[i],header = T,check.names = F,row.names = 1)
        # testcountfile <- t(testcountfile)
    }
    if(umiformat[i] == "10x"){
        #10x标准输出，三个文件
        testcountfile <- Read10X(data.dir = countfiles[i])
    }
    if(umiformat[i] == "csv"){
        #row为cell， col为gene
        testcountfile <- read.table(file = countfiles[i],header = T,com = '',sep = ",",quote = NULL,check.names = F,row.names = 1)
        testcountfile <- t(testcountfile)
    }
    if(umiformat[i] == "rds"){
        # 直接返回对象
        test <- readRDS(file = countfiles[i])
        DefaultAssay(test) <- "RNA"
        # testcountfile = rdsobj$umicount$exon$all
        return(test)
    }
    if(umiformat[i] == "rdsraw"){
        # 直接返回对象
        rdsobj <- readRDS(file = countfiles[i])
        testcountfile = rdsobj[["RNA"]]$counts
    }
    if(umiformat[i] == "h5"){
        ## TODO：直接读取h5文件的功能待完善，还需要能把注释文件生成出来
        testcountfile= Read10X_h5(countfiles[i])
        testcountfile
        # test <- CreateSeuratObject(counts = testcountfile, project = "test",min.cells = 2, min.features = 100)
        # return(test)
        # gz1 <- gzfile("Gene_Count_per_Cell.tsv.gz", "w")
        # write.table(test@assays[["RNA"]]@counts, file=gz1, quote=FALSE, sep='\t', col.names = TRUE)
    }
    
    # test.metadata <- read.csv(file = annofiles[i], row.names = 1)
    colnames(testcountfile) = paste(samplenames[i],colnames(testcountfile),sep='_')
    # meta <- data.frame(cellid = colnames(testcountfile), replicate=paste("HD2",sep=''), group = "HD")
    # rownames(meta) <- paste(samplenames[i],colnames(testcountfile),sep='')

    # test <- CreateSeuratObject(counts = testcountfile, project = "test",  meta.data = test.metadata)
    test <- CreateSeuratObject(counts = testcountfile, project = "test",min.cells = 1, min.features = 1)
    

    ## 过滤检出基因细胞数过少的基因
    # 提取计数
    counts <- GetAssayData(object = test, slot = "counts")
    # 根据在每个细胞的计数是否大于0为每个基因输出一个逻辑向量
    nonzero <- counts > 0
    # 将所有TRUE值相加，如果每个基因的TRUE值超过10个，则返回TRUE。
    keep_genes <- Matrix::rowSums(nonzero) >= min_cells_in_gene
    test_discard_genes <- Matrix::rowSums(nonzero) < min_cells_in_gene
    # 仅保留那些在10个以上细胞中表达的基因
    filtered_counts <- counts[keep_genes, ]
    # 重新赋值给经过过滤的Seurat对象
    # test <- CreateSeuratObject(filtered_counts, meta.data = test@meta.data)
    test <- CreateSeuratObject(counts = filtered_counts, meta.data = test@meta.data)
    # test <- CreateSeuratObject(counts = filtered_counts, data = filtered_counts, meta.data = test@meta.data)
    test[["group"]] <- listnames[i]
    test[["replicate"]] <- samplenames[i]
    
    # if(umiformat[i] == "expcsv"){
    #     return(test)
    # }


    
    #####################################################################################
    ## cell筛选
    # In the example below, we visualize QC metrics, and use these to filter cells.
    # We filter cells that have unique feature counts over 2,500 or less than 200
    # We filter cells that have >5% mitochondrial counts
    #####################################################################################

    # The [[ operator can add columns to object metadata. This is a great place to stash QC stats
    # ctrl[["percent.mt"]] <- PercentageFeatureSet(ctrl, pattern = "^MT-|^mt-")
    # test[["percent.mt"]] <- PercentageFeatureSet(test, pattern = "^MT-|^mt-")

    # 线粒体基因
    test[["percent.mt"]] <- PercentageFeatureSet(test, pattern = "^ATP6$|^ATP8$|^COX1$|^COX2$|^COX3$|^CYTB$|^mt-Rnr1$|^mt-Rnr2$|^ND1$|^ND2$|^ND3$|^ND4$|^ND4L$|^ND5$|^ND6$|^Trna$|^Trnc$|^Trnd$|^Trne$|^Trnf$|^Trng$|^Trnh$|^Trni$|^Trnk$|^Trnl1$|^Trnl2$|^Trnm$|^Trnn$|^Trnp$|^Trnq$|^Trnr$|^Trns1$|^Trns2$|^Trnt$|^Trnv$|^Trnw$|^Trny$|^MT-|^mt-")
    # Show QC metrics for the first 5 cells
    # head(pbmc@meta.data, 5)

    # 核糖体基因
    test[["percent.ribo"]] <- PercentageFeatureSet(test, "^RP[SL]|^Rp[sl]")

    # 红细胞
    # Percentage hemoglobin genes - includes all genes starting with HB except HBP.
    # And finally, with the same method we will calculate proportion hemoglobin genes, which can give an indication of red blood cell contamination.
    test[["percent.hb"]] <- PercentageFeatureSet(test, "^HB[^(P)]|^Hb[^(p)]")
    test[["percent.plat"]] <- PercentageFeatureSet(test, "^PECAM1$|^PF4$|^Pecam1$|^Pf4$")

    #################################################
    ## Visualize QC metrics as a violin plot, test
    ################################################
    # QC
    p1 <- VlnPlot(test, features = c("nFeature_RNA", "nCount_RNA", "percent.mt", "percent.ribo", "percent.hb"), ncol = 5, pt.size = 0.1)
    # p1 <- VlnPlot(test, features = c("nFeature_RNA", "nCount_RNA"), ncol = 2, pt.size = 0.1)
    pdf(file=paste("QC_all_",samplenames[i],".pdf",sep=""),width = 20,height = 4)
    print(p1)
    dev.off()

    png(file = paste("QC_all_",samplenames[i],".png",sep=""),width = 600,height = 120,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()

    # FeatureScatter is typically used to visualize feature-feature relationships, but can be used
    # for anything calculated by the object, i.e. columns in object metadata, PC scores etc.
    p1 <- FeatureScatter(test, feature1 = "nCount_RNA", feature2 = "percent.mt", pt.size = 0.1)
    p2 <- FeatureScatter(test, feature1 = "nCount_RNA", feature2 = "nFeature_RNA", pt.size = 0.1)
    p3 <- FeatureScatter(test, feature1 = "percent.mt", feature2 = "nFeature_RNA", pt.size = 0.1)
    pdf(file=paste("QC_FeatureScatter_",samplenames[i],".pdf",sep=""),width = 15,height = 4)
    print(p1 + p2 + p3)
    dev.off()

    png(file = paste("QC_FeatureScatter_",samplenames[i],".png",sep=""),width = 375,height = 100,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1 + p2 + p3)
    dev.off()

    ## 最终筛选
    # TODO: 修改参数
    # 筛选掉基因数 over 2,500 or less than 200
    # 筛选掉线粒体比例大于 >5%

    qc.total <- test$nCount_RNA > 0
    # qc.lib <- test$sum < 4e5
    qc.lib <- (test$nCount_RNA < min_total_UMI & test$nCount_RNA > 0)
    # qc.nexprs <- test$detected < 5e3
    qc.nexprs.low <- (test$nFeature_RNA < min_genes & test$nCount_RNA > 0)
    qc.nexprs.high <- (test$nFeature_RNA > max_genes & test$nCount_RNA > 0)
    # qc.spike <- test$altexps_ERCC_percent > 10
    qc.mito <- (test$percent.mt > max_MT & test$nCount_RNA > 0)

    # test <- subset(test, subset = nFeature_RNA > 200 & nFeature_RNA < 2500 & percent.mt < 5)
    test <- subset(test, subset = nFeature_RNA >= min_genes & nFeature_RNA <= max_genes & nCount_RNA >= min_total_UMI & percent.mt <= max_MT)


    qc.keep <- test$nCount_RNA > 0
    dis <- DataFrame(Raw=sum(qc.total), LibSize=sum(qc.lib), NExprsLow=sum(qc.nexprs.low),NExprsHigh=sum(qc.nexprs.high), MitoProp=sum(qc.mito),Total=sum(qc.total)-sum(qc.keep), Keep=sum(qc.keep), ExpressGenes=sum(test_discard_genes), KeepGenes=sum(keep_genes))
    dis
    cat(paste('原始细胞数\t按比对总量过滤','(<',min_total_UMI,')','\t按最低检出基因数过滤','(<',min_genes,')','\t按最高检出基因数过滤','(>',max_genes,')','\t按线粒体比例过滤','(>',max_MT,'%)','\t总过滤细胞数\t最终保留的细胞数\t筛选掉少数细胞表达的基因','(<',min_cells_in_gene,')','\t最终保留的基因数\n',sep=''),file=paste(samplenames[i],'_discard_stat','.xls',sep=''))
    write.table(dis,file=paste(samplenames[i],'_discard_stat','.xls',sep=''),
                append=T,quote=F,sep='\t',row.names = FALSE,col.names = FALSE)


    
    #####################################################################################
    ## 均一化Normalizing the data
    # After removing unwanted cells from the dataset, the next step is to normalize the data. By default, we employ a global-scaling normalization method "LogNormalize" that normalizes the feature expression measurements for each cell by the total expression, multiplies this by a scale factor (10,000 by default), and log-transforms the result. Normalized values are stored in pbmc[["RNA"]]@data.
    #####################################################################################

    if(umiformat[i] != "expcsv"){
        test <-NormalizeData(test, normalization.method = "LogNormalize", scale.factor = 10000)
    }

    #####################################################################################
    ## 高度可变基因选取Identification of highly variable features (feature selection)
    # We next calculate a subset of features that exhibit high cell-to-cell variation in the dataset (i.e, they are highly expressed in some cells, and lowly expressed in others). We and others have found that focusing on these genes in downstream analysis helps to highlight biological signal in single-cell datasets.
    # Our procedure in Seurat3 is described in detail here, and improves on previous versions by directly modeling the mean-variance relationship inherent in single-cell data, and is implemented in the FindVariableFeatures function. By default, we return 2,000 features per dataset. These will be used in downstream analysis, like PCA.
    #####################################################################################

    test <- FindVariableFeatures(test, selection.method = "vst", nfeatures = 2000)
    # pbmc <- FindVariableFeatures(pbmc, selection.method = "vst", nfeatures = 1000)


    ## test
    # Identify the 10 most highly variable genes
    top10 <- head(VariableFeatures(test), 10)

    # plot variable features with and without labels


    pdf(file=paste("QC_highly_variable_features_",samplenames[i],".pdf",sep=""),width = 6,height = 4)
    plot1 <- VariableFeaturePlot(test)
    plot2 <- LabelPoints(plot = plot1, points = top10, repel = TRUE)
    # plot1 + plot2
    print(plot2)
    dev.off()

    png(file = paste("QC_highly_variable_features_",samplenames[i],".png",sep=""),width = 150,height = 100,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    plot1 <- VariableFeaturePlot(test)
    plot2 <- LabelPoints(plot = plot1, points = top10, repel = TRUE)
    # plot1 + plot2
    print(plot2)
    dev.off()

    if(opt$method=="sct_harmony"){
        test <- SCTransform(test, method = "glmGamPoi", vars.to.regress = "percent.mt", verbose = FALSE)
        # test <- SCTransform(test, vars.to.regress = "percent.mt", verbose = FALSE)
    }

    # # 双细胞过滤 
    # # remove doublet using DoubletFinder ; 
    # # https://nbisweden.github.io/workshop-scRNAseq/labs/compiled/seurat/seurat_01_qc.html
    # test = ScaleData(test, vars.to.regress = c("nFeature_RNA", "percent.mt"),verbose = F)
    # test = RunPCA(test, verbose = F, npcs = 20)
    # pc.num=1:15
    # test = RunUMAP(test, dims = pc.num, verbose = F)
    # test <- FindNeighbors(test, dims = pc.num) %>% FindClusters(resolution = 0.3)
    # ## 寻找最优pK值
    # sweep.res.list <- paramSweep_v3(test, PCs = pc.num, sct = T)
    # sweep.stats <- summarizeSweep(sweep.res.list, GT = FALSE)  
    # bcmvn <- find.pK(sweep.stats)
    # pK_bcmvn <- bcmvn$pK[which.max(bcmvn$BCmetric)] %>% as.character() %>% as.numeric()
    # # pK_bcmvn <- 0.2
    # print("pK_bcmvn:")
    # print(pK_bcmvn)

    # ## 排除不能检出的同源doublets，优化期望的doublets数量
    # # qc.total <- test$nCount_RNA > 0

    # DoubletRate = ncol(test)*8*1e-6                     # 5000细胞对应的doublets rate是3.9%
    # homotypic.prop <- modelHomotypic(test$seurat_clusters)   # 最好提供celltype
    # nExp_poi <- round(DoubletRate*ncol(test)) 
    # nExp_poi.adj <- round(nExp_poi*(1-homotypic.prop))

    # ## 使用确定好的参数鉴定doublets
    # test <- doubletFinder_v3(test, PCs = pc.num, pN = 0.25, pK = pK_bcmvn, 
    #                         nExp = nExp_poi.adj, reuse.pANN = F, sct = T)
                            
    # ## 结果展示，分类结果在pbmc@meta.data中
    # DF.name = colnames(test@meta.data)[grepl("DF.classification", colnames(test@meta.data))]
    # p1 <- DimPlot(test, reduction = "umap", group.by = DF.name)
    # pdf(file=paste("DimPlot_doublet_",samplenames[i],".pdf",sep=""),width = 5,height = 4)
    # print(p1)
    # dev.off()

    # png(file = paste("DimPlot_doublet_",samplenames[i],".png",sep=""),width = 125,height = 100,units = "mm",res = 300,pointsize = 2)
    # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    # print(p1)
    # dev.off()

    # p1 <- VlnPlot(test, features = "nFeature_RNA", group.by = DF.name, pt.size = 0.1)
    # pdf(file=paste("VlnPlot_doublet_",samplenames[i],".pdf",sep=""),width = 5,height = 4)
    # print(p1)
    # dev.off()

    # png(file = paste("VlnPlot_doublet_",samplenames[i],".png",sep=""),width = 125,height = 100,units = "mm",res = 300,pointsize = 2)
    # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    # print(p1)
    # dev.off()

    # test.doublet <- test[, test@meta.data[, DF.name] == "Doublet"]
    # qc.doublet <- test.doublet$nCount_RNA > 0
    # test = test[, test@meta.data[, DF.name] == "Singlet"]
    # qc.keep <- test$nCount_RNA > 0



    # dis <- DataFrame(Raw=sum(qc.total), LibSize=sum(qc.lib), NExprs=sum(qc.nexprs),
    #         MitoProp=sum(qc.mito),DoubletProp=sum(qc.doublet), Total=sum(qc.total)-sum(qc.keep), Keep=sum(qc.keep), ExpressGenes=sum(test_discard_genes), KeepGenes=sum(keep_genes))
    # dis
    # cat(paste('原始细胞数\t按比对总量过滤','(<',min_total_UMI,')','\t按检出基因数过滤','(<',min_genes,')','\t按线粒体比例过滤','(>',max_MT,'%)','\t按doublet过滤','\t总过滤细胞数\t最终保留的细胞数\t筛选掉少数细胞表达的基因','(<',min_cells_in_gene,')','\t最终保留的基因数\n',sep=''),file=paste(samplenames[i],'_discard_stat','.xls',sep=''))
    # write.table(dis,file=paste(samplenames[i],'_discard_stat','.xls',sep=''),
    #             append=T,quote=F,sep='\t',row.names = FALSE,col.names = FALSE)

    # # top30基因
    # # Compute the relative expression of each gene per cell
    # coum <- test@assays$RNA@counts
    # coum <- Matrix::t(Matrix::t(coum)/Matrix::colSums(coum)) * 100
    # most_expressed <- order(apply(coum, 1, median), decreasing = T)[30:1]
    # print(most_expressed)
    # gg <- as.data.frame(t(coum[most_expressed, ]))
    # dfs <- melt(gg)
    # print(head(dfs))
    # ggplot(dfs,aes(x=variable,y=value))+geom_boxplot()+coord_flip()+labs(title="Top30 most expressed genes",y="% total count per cell", x = "")+theme_bw() + theme_paper
    # ggsave(
    #     paste("percentage_of_counts_per_gene_",samplenames[i],".pdf",sep=""),
    #     width = 200,
    #     height = 150,
    #     units = "mm"
    # )
    # ggsave(
    #     paste("percentage_of_counts_per_gene_",samplenames[i],".png",sep=""),
    #     width = 200,
    #     height = 150,
    #     units = "mm"
    # )

    return(test)
}

cell_filter(1)

sc.list <- future_lapply(1:length(countfiles), cell_filter)

# sc.list1 <- list()
# sc.list1 <- future_lapply(1:19, cell_filter)
# sc.list2 <- list()
# sc.list2 <- future_lapply(20:37, cell_filter)

# sc.list <- list()
# sc.list <- c(sc.list1,sc.list2)

#####################################################################################
## Perform integration 整合数据， 找到公共anchors
# We then identify anchors using the FindIntegrationAnchors function, which takes a list of Seurat objects as input, and use these anchors to integrate the two datasets together with IntegrateData.
#####################################################################################
## 生成list
# select features that are repeatedly variable across datasets for integration
sc.combined<-""
# 一个样本不需要整合，直接返回
if(length(countfiles)==1){
    sc.combined <- sc.list[[1]]
}else{
    # cca
    if(opt$method=="cca"){
        features <- SelectIntegrationFeatures(object.list = sc.list)
        # sc.list <- lapply(X = sc.list, FUN = function(x) {
        #     x <- ScaleData(x, features = features, verbose = FALSE)
        #     x <- RunPCA(x, features = features, verbose = FALSE)
        # })
        sc.anchors <- FindIntegrationAnchors(object.list = sc.list, anchor.features = features)
        sc.combined <- IntegrateData(anchorset = sc.anchors)

        DefaultAssay(sc.combined) <- "integrated"
    }
    # rpca
    if(opt$method=="rpca"){
        features <- SelectIntegrationFeatures(object.list = sc.list)
        sc.list <- lapply(X = sc.list, FUN = function(x) {
            x <- ScaleData(x, features = features, verbose = FALSE)
            x <- RunPCA(x, features = features, verbose = FALSE)
        })
        anchors <- FindIntegrationAnchors(object.list = sc.list, anchor.features = features, reduction = "rpca", k.anchor = 20)
        sc.combined <- IntegrateData(anchorset = anchors)

        DefaultAssay(sc.combined) <- "integrated"
    }
    # sct_cca
    if(opt$method=="sct_cca"){
        sc.list <- lapply(X = sc.list, FUN = SCTransform)
        features <- SelectIntegrationFeatures(object.list = sc.list, nfeatures = 3000)

        # 使用sctransform
        sc.list <- PrepSCTIntegration(object.list = sc.list, anchor.features = features)

        anchors <- FindIntegrationAnchors(object.list = sc.list, anchor.features = features, normalization.method = "SCT")
        sc.combined <- IntegrateData(anchorset = anchors, normalization.method = "SCT")

        DefaultAssay(sc.combined) <- "integrated"
    }
    # sct_rpca
    if(opt$method=="sct_rpca"){
        sc.list <- lapply(X = sc.list, FUN = SCTransform, method = "glmGamPoi")
        features <- SelectIntegrationFeatures(object.list = sc.list, nfeatures = 3000)

        # 使用sctransform
        sc.list <- PrepSCTIntegration(object.list = sc.list, anchor.features = features)

        sc.list <- lapply(X = sc.list, FUN = function(x) {
            x <- RunPCA(x, features = features, verbose = FALSE)
        })

        anchors <- FindIntegrationAnchors(object.list = sc.list, anchor.features = features, normalization.method = "SCT", reduction = "rpca", k.anchor = 20, dims = 1:50)
        # anchors <- FindIntegrationAnchors(object.list = sc.list, reference = c(1, 2), reduction = "rpca", dims = 1:50)
        sc.combined <- IntegrateData(anchorset = anchors, dims = 1:50, normalization.method = "SCT")

        DefaultAssay(sc.combined) <- "integrated"
    }
    # sct_harmony
    if(opt$method=="sct_harmony"){
        var.features <- SelectIntegrationFeatures(object.list = sc.list, nfeatures = 3000)
        sc.combined <- merge(x = sc.list[[1]], y = sc.list[2:length(sc.list)], merge.data=TRUE)
        VariableFeatures(sc.combined) <- var.features
        sc.combined <- RunPCA(sc.combined, verbose = FALSE)
        sc.combined <- RunHarmony(sc.combined, assay.use="SCT", group.by.vars = "replicate")
        DefaultAssay(sc.combined) <- "SCT"

        sc.combined <- RunUMAP(sc.combined, reduction = "harmony", dims = 1:50)
        sc.combined <- FindNeighbors(sc.combined, reduction = "harmony", dims = 1:50) %>% FindClusters()

        p1 <- DimPlot(sc.combined, reduction = "umap", group.by = "replicate", pt.size = 0.1)
        p2 <- DimPlot(sc.combined, reduction = "umap", group.by = "group", pt.size = 0.1)
        p3 <- DimPlot(sc.combined, reduction = "umap", label = TRUE, pt.size = 0.1)
        # p1 <- AugmentPlot(plot = p1)
        # p2 <- AugmentPlot(plot = p2)

        pdf(file=paste("umap_cluster","pdf",sep="."),width = 18,height = 5)
        print((p1+p2+p3) + theme_paper)
        dev.off()

        png(file = paste("umap_cluster",".png",sep=""),width = 450,height = 125,units = "mm",res = 300,pointsize = 10)
        par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
        print(p1+p2+p3)
        dev.off()

        p1 <- DimPlot(sc.combined, reduction = "umap", group.by = "replicate", split.by = "group", pt.size = 0.1, label = TRUE)
        # p1 <- AugmentPlot(plot = p1)

        pdf(file=paste("umap_cluster_bygroup","pdf",sep="."),width = 4 * groupnum, height = 4)
        print(p1)
        dev.off()

        png(file = paste("umap_cluster_bygroup",".png",sep=""),width = 100 * groupnum, height = 100,units = "mm",res = 300,pointsize = 10)
        par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
        print(p1)
        dev.off()

    }

}


rm(sc.list)




#####################################################################################
## Scaling the data
# Next, we apply a linear transformation ('scaling') that is a standard pre-processing step prior to dimensional reduction techniques like PCA. The ScaleData function:
    # Shifts the expression of each gene, so that the mean expression across cells is 0
    # Scales the expression of each gene, so that the variance across cells is 1
        # This step gives equal weight in downstream analyses, so that highly-expressed genes do not dominate
    # The results of this are stored in pbmc[["RNA"]]@scale.data
#####################################################################################


all.genes <- rownames(sc.combined)
# sc.combined <- ScaleData(sc.combined, features = all.genes)

# You can perform gene scaling on only the HVF, dramatically improving speed and memory use. Since dimensional reduction is run only on HVF, this will not affect downstream results.
# pbmc <- ScaleData(pbmc, features = VariableFeatures(object = pbmc), vars.to.regress = "percent.mt")

if(opt$method=="cca" || opt$method=="rpca"){
    sc.combined <- ScaleData(sc.combined, features = all.genes, verbose = FALSE, vars.to.regress = "percent.mt")
}

#####################################################################################
## 降维Perform linear dimensional reduction
# Next we perform PCA on the scaled data. By default, only the previously determined variable features are used as input, but can be defined using features argument if you wish to choose a different subset.
#####################################################################################


if(opt$method!="sct_harmony"){
    sc.combined <- RunPCA(sc.combined, features = VariableFeatures(object = sc.combined), npcs = 100, ndims.print = 1:5, nfeatures.print = 5)
}

saveRDS(sc.combined, file = "./sc_preprocessing.rds")


# Seurat provides several useful ways of visualizing both cells and features that define the PCA, including VizDimReduction, DimPlot, and DimHeatmap
p1 <- VizDimLoadings(sc.combined, dims = 1:2, reduction = "pca")
pdf(file=paste("VizPlot_PCA",".pdf",sep=""),width = 8,height = 5)
p1
dev.off()

png(file = paste("VizPlot_PCA",".png",sep=""),width = 200,height = 125,units = "mm",res = 300,pointsize = 1.5)
par(mar = c(5, 5, 2, 2), cex.axis = 1.5, cex.lab = 2)
p1
dev.off()


p1 <- DimPlot(sc.combined, reduction = "pca", group.by = "replicate", split.by = "group",pt.size = 0.01)
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

# DimHeatmap(sc.combined, dims = c(1:3, 70:75), cells = 500, balanced = TRUE)


#####################################################################################
## 预测主成分个数Determine the 'dimensionality' of the dataset
# To overcome the extensive technical noise in any single feature for scRNA-seq data, Seurat clusters cells based on their PCA scores, with each PC essentially representing a 'metafeature' that combines information across a correlated feature set. The top principal components therefore represent a robust compression of the dataset. However, how many componenets should we choose to include? 10? 20? 100?
#####################################################################################

# In Macosko et al, we implemented a resampling test inspired by the JackStraw procedure. We randomly permute a subset of the data (1% by default) and rerun PCA, constructing a 'null distribution' of feature scores, and repeat this procedure. We identify 'significant' PCs as those who have a strong enrichment of low p-value features.

# NOTE: This process can take a long time for big datasets, comment out for expediency. More
# approximate techniques such as those implemented in ElbowPlot() can be used to reduce
# computation time

# sc.combined <- JackStraw(sc.combined, num.replicate = 100)
# sc.combined <- ScoreJackStraw(sc.combined, dims = 1:20)
# 
# JackStrawPlot(sc.combined, dims = 1:15)

# An alternative heuristic method generates an 'Elbow plot': a ranking of principle components based on the percentage of variance explained by each one (ElbowPlot function). In this example, we can observe an 'elbow' around PC9-10, suggesting that the majority of true signal is captured in the first 10 PCs.
# ElbowPlot(sc.combined)

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


# sc.combined <- JackStraw(sc.combined, num.replicate = 100)
# sc.combined <- ScoreJackStraw(sc.combined, dims = 1:20)

# pdf(file=paste("JackStrawPlot",".pdf",sep=""),width = 5,height = 4)
# p1 <- JackStrawPlot(sc.combined, dims = 1:20)
# p1
# dev.off()

# png(file = paste("JackStrawPlot",".png",sep=""),width = 125,height = 100,units = "mm",res = 300,pointsize = 2)
# par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
# p1 <- JackStrawPlot(sc.combined, dims = 1:20)
# p1
# dev.off()


# saveRDS(sc.combined, file = "./sc_preprocessing.rds")
