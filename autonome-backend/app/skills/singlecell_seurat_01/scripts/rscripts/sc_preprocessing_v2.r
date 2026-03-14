#!/usr/bin/env Rscript

# =============================================================================
# Version
# =============================================================================
VERSION = "3.0.0"

args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 1 && (args[1] == "-v" | args[1] == "--version")) {
  message("Version: \n\t", VERSION, "\n")
  quit(status = 0)
}

# =============================================================================
# Copyright
# =============================================================================
# (C) 2019-2022 biosalt
# 名称：single cell pipeline
# 描述：单细胞分析流程
# 作者：CHAO CHENG
# 创建：2020-10-15   联系：chengchao@biosalt.cc
#
# 变更记录：
# Date         Version   Author      ChangeLog
# 2019-12-27   v1.0      chaocheng   修改测试版本
# 2020-10-15   v2.0      chaocheng   整合 seurat
# 2021-03-08   v3.0      chaocheng   流程整合
#
# 参考：
# - https://osca.bioconductor.org/overview.html#quick-start
# - https://satijalab.org/seurat/v3.2/mca.html
# - https://satijalab.org/seurat/pbmc3k_tutorial.html
# - https://github.com/CostaLab/scrna_seurat_pipeline
# =============================================================================


# =============================================================================
# 环境准备 / 参数获取
# =============================================================================

# windows 下检查当前程序路径
# script.dir <- dirname(sys.frame(1)$ofile)

setwd("./")
# setwd("/data1/scRNA_data/DEV2020-10001_seurat/basic/mca")

suppressPackageStartupMessages(library(optparse))       # 参数
suppressPackageStartupMessages(library(futile.logger))  # 日志
suppressPackageStartupMessages(library("stats"))
suppressPackageStartupMessages(library(dplyr))
`%ni%` <- Negate(`%in%`)

# Bioconductor: SingleCellExperiment 等（如需）
# install.packages("BiocManager")
# BiocManager::install(c('SingleCellExperiment','Rtsne','scater','scran','uwot'))

library("ggplot2")
# library("ggthemes")
# library("reshape2")
# library("ggsci")

library(SingleCellExperiment)
# library(scater)

library(dplyr)
options(stringsAsFactors = FALSE)
library(grDevices)
library(gplots)
library(Seurat)
library(patchwork)
library(hdf5r)
# library(DoubletFinder)
library("stats")
library("ggthemes")
library("reshape2")
library(harmony)
library(glmGamPoi)

library("future.apply")
suppressPackageStartupMessages(library(doParallel))
suppressPackageStartupMessages(library(future))         # plan()
suppressPackageStartupMessages(library(DoubletFinder))  # 双细胞筛选

# ---- 命令行参数 ----
option_list <- list(
  make_option(c("-n", "--ncpus"),
              action = "store", type = "integer", default = 24,
              help = "parallel run number of cores"),
  make_option(c("--MaxMemMega"),
              action = "store", type = "integer", default = 160,
              help = "Parallel Max Memory size GB"),
  make_option(c("--MinTotalUMI"),
              action = "store", type = "integer", default = 1000,
              help = "minimal total UMI count"),
  make_option(c("--MinGenes"),
              action = "store", type = "integer", default = 500,
              help = "minimal genes"),
  make_option(c("--MaxGenes"),
              action = "store", type = "integer", default = 8000,
              help = "max genes"),
  make_option(c("--MaxMT"),
              action = "store", type = "integer", default = 15,
              help = "maximal percentage of mitochondria"),
  make_option(c("--MaxHB"),
              action = "store", type = "integer", default = 10,
              help = "maximal percentage of HB"),
  make_option(c("--MinCellsInGene"),
              action = "store", type = "integer", default = 5,
              help = "minimal cells with UMI>0 in one gene"),
  make_option(c("-s", "--samplelist"),
              action = "store", type = "character", default = "",
              help = "samplename1,samplename2,samplename3"),
  make_option(c("-l", "--listname"),
              action = "store", type = "character", default = "",
              help = "listname1,listname2,listname3"),
  make_option(c("--batchSize"),
              action = "store", type = "integer", default = 10,
              help = "分批整合时，每批的样本数目(默认10)"),
  make_option(c("-f", "--format"),
              action = "store", type = "character", default = "10x",
              help = "The count matrix file format, 10x or BD or h5 or rds"),
  make_option(c("-a", "--dataset"),
              action = "store", type = "character", default = "D1",
              help = "dataset label for each sample, e.g. D1,D1,D2"),
  make_option(c("-b", "--bdfiles"),
              action = "store", type = "character",
              help = "The count matrix file of sample"),
  make_option(c("-m", "--method"),
              action = "store", type = "character", default = "cca",
              help = "cca or rpca or sct_cca or sct_rpca or harmony or sct_harmony or none"),
  make_option(c("-t", "--sourcetype"),
              action = "store", type = "character", default = "raw",
              help = "raw or subcell"),
  make_option(c("--noparallel"),
              action = "store", type = "character", default = "false",
              help = "no parallel"),
  make_option(c("--rdsfile"),
              action = "store", type = "character",
              help = "The data object rds file"),
  make_option(c("--doublet_enable"),
              type = "character", default = "true",
              help = "true|false 是否启用 DoubletFinder（默认 false）"),
  make_option(c("--doublet_pc_min"),
              type = "integer", default = 1,
              help = "用于DF的PC起始(含)"),
  make_option(c("--doublet_pc_max"),
              type = "integer", default = 15,
              help = "用于DF的PC结束(含)"),
  make_option(c("--doublet_resolution"),
              type = "double", default = 0.3,
              help = "用于FindClusters的分辨率"),
  make_option(c("--doublet_pn"),
              type = "double", default = 0.25,
              help = "pN 人工双细胞比例（官方常用0.25）"),
  make_option(c("--doublet_rate"),
              type = "double", default = 0.039,
              help = "预期双细胞率（约5000细胞≈0.039，可按平台调整）"),
  make_option(c("--doublet_sct"),
              type = "character", default = "auto",
              help = "auto|true|false 是否按SCT工作流（auto会检测是否存在SCT Assay）"),
  make_option(c("--doublet_force_pk"),
              type = "double", default = NA,
              help = "可选：强制指定pK；缺省则自动选择BCmvn最大值"),
  make_option(c("--doublet_reuse_pann"),
              type = "character", default = "false",
              help = "true|false 是否复用已有pANN列（若存在）"),
  make_option(c("--doublet_keep"),
              type = "character", default = "singlet",
              help = "singlet|all 输出时仅保留Singlet或保留全部并打标")
)

opt <- parse_args(OptionParser(option_list = option_list))

# opt$samplelist = "h42A,h56C,h57C,h63C"
# opt$listname = "Baseline,Pembro_RT,Pembro_RT,Pembro_RT"
# opt$format = "10x,10x,10x,10x"
# opt$bdfiles = "/opt/data1/project/NBioS-2025-07031-D_Breast_cancer_drug_resistance/data/h42A,/opt/data1/project/NBioS-2025-07031-D_Breast_cancer_drug_resistance/data/h56C,/opt/data1/project/NBioS-2025-07031-D_Breast_cancer_drug_resistance/data/h57C,/opt/data1/project/NBioS-2025-07031-D_Breast_cancer_drug_resistance/data/h63C"
# opt$method = "sct_harmony"


registerDoParallel(cores = opt$ncpus)
options(future.globals.maxSize = opt$MaxMemMega * 1024^3)

## ---- [MEM] 限制 worker 数，不超过样本数，也不超过一个合理上限 ----
worker_n <- min(opt$ncpus, length(strsplit(opt$bdfiles, ",")[[1]]), 16L)

if (opt$noparallel == "false" && worker_n > 1L) {
  plan("multisession", workers = worker_n)
} else {
  plan(sequential)
}

# plan("multisession", workers = opt$ncpus)


min_total_UMI     = opt$MinTotalUMI
max_genes         = opt$MaxGenes
min_genes         = opt$MinGenes
max_MT            = opt$MaxMT
max_HB            = opt$MaxHB
min_cells_in_gene = opt$MinCellsInGene

# ---- 测试参数示例（保留注释）----
# opt$method = "sct_harmony"
# opt$samplelist <- "2_yo,5_yo,8_yo,11_yo,17_yo,Adult_1,Adult_2,Adult_3,Adult_4,Adult_5,iNOA_1,iNOA_2,iNOA_3,AZFa_Del,KS_1,KS_2,KS_3"
# opt$listname <- "2_yo,5_yo,8_yo,11_yo,17_yo,Adult,Adult,Adult,Adult,Adult,iNOA,iNOA,iNOA,AZFa_Del,KS,KS,KS"
# opt$bdfiles <- "/data1/.../GSM4504189_LZ011matrix.csv,..."
# opt$format  <- "countcsv,countcsv,..."

# ---- 日志目录与句柄 ----
if (!file.exists("logs")) dir.create("logs")

LOGNAME  = "log-"
cur_date <- as.character(Sys.Date())
errorLog = file.path("logs", sprintf("%sERROR-%s.log", LOGNAME, cur_date))
warnLog  = file.path("logs", sprintf("%sWARN-%s.log",  LOGNAME, cur_date))
infoLog  = file.path("logs", sprintf("%sINFO-%s.log",  LOGNAME, cur_date))
traceLog = file.path("logs", sprintf("%sTRAC-%s.log",  LOGNAME, cur_date))

invisible(flog.logger("error", ERROR, appender.file(errorLog)))
invisible(flog.logger("warn",  WARN,  appender.file(warnLog)))
invisible(flog.logger("info",  INFO,  appender.file(infoLog)))
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

# ---- 主题样式 ----
theme_paper <- theme(
  panel.grid.major  = element_line(linewidth = 0.1, linetype = "dashed"),
  legend.key        = element_rect(fill = "white", color = "white"),
  legend.key.size   = unit(0.5, "cm"),
  legend.position   = c(0.2, 0.88),
  legend.title      = element_blank(),
  legend.background = element_blank(),
  panel.grid.minor  = element_blank(),
  plot.margin       = margin(0.5, 1, 0.5, 1, unit = "cm"),
  legend.text       = element_text(size = 11),
  axis.title        = element_text(size = 12),
  plot.title        = element_text(size = 12, face = "bold"),
  axis.text         = element_text(size = 11, colour = "black")
)


# =============================================================================
# 数据读取/对象创建
# =============================================================================

# 将输入解析为向量
countfiles  <- strsplit(opt$bdfiles,  ",")[[1]]
# annofiles <- strsplit(opt$annofiles, ",")[[1]]
samplenames <- strsplit(opt$samplelist, ",")[[1]]
listnames   <- strsplit(opt$listname,   ",")[[1]]
umiformat   <- strsplit(opt$format,     ",")[[1]]
datasets   <- strsplit(opt$dataset,     ",")[[1]]

groupnum <- length(unique(listnames))
sc.list  <- list()

# ---- 样本读取 + QC/过滤（单样本）----
cell_filter <- function(i) {
  message("Processing sample: ", samplenames[i], " (", i, "/", length(samplenames), ")")
  testcountfile <- ""

  if (umiformat[i] == "BD") {
    # BD 流程 tsv：row=cell, col=gene
    testcountfile <- read.table(file = countfiles[i], header = TRUE, com = "",
                                sep = "\t", quote = NULL, check.names = FALSE,
                                row.names = 1)
    testcountfile <- t(testcountfile)
  }

  if (umiformat[i] == "exp") {
    # row=gene, col=cell
    testcountfile <- read.table(file = countfiles[i], header = TRUE, com = "",
                                sep = "\t", quote = NULL, check.names = FALSE,
                                row.names = 1)
  }

  if (umiformat[i] == "expcsv") {
    # row=gene, col=cell，csv 表达量
    testcountfile <- read.csv(file = countfiles[i], header = TRUE,
                              check.names = FALSE, row.names = 1)
  }

  if (umiformat[i] == "countcsv") {
    # row=gene, col=cell，csv UMI
    testcountfile <- read.csv(file = countfiles[i], header = TRUE,
                              check.names = FALSE, row.names = 1)
  }

  if (umiformat[i] == "10x") {
    # 10x 标准输出（三文件）
    testcountfile <- Read10X(data.dir = countfiles[i])
  }

  if (umiformat[i] == "csv") {
    # row=cell, col=gene
    testcountfile <- read.table(file = countfiles[i], header = TRUE, com = "",
                                sep = ",", quote = NULL, check.names = FALSE,
                                row.names = 1)
    testcountfile <- t(testcountfile)
  }

  if (umiformat[i] == "rds") {
    # 直接返回对象
    test <- readRDS(file = countfiles[i])
    DefaultAssay(test) <- "RNA"
    test <- FindVariableFeatures(test, selection.method = "vst",
                                 nfeatures = 2000)
    return(test)
  }

  if (umiformat[i] == "sctrds") {
    # 直接返回对象 + SCT
    test <- readRDS(file = countfiles[i])
    DefaultAssay(test) <- "RNA"
    test <- FindVariableFeatures(test, selection.method = "vst",
                                 nfeatures = 2000)
    test <- SCTransform(test, method = "glmGamPoi",
                        vars.to.regress = "percent.mt", verbose = FALSE)
    return(test)
  }

  if (umiformat[i] == "rdsraw") {
    # 从 RDS 抽 counts
    rdsobj <- readRDS(file = countfiles[i])
    if (!is.null(rdsobj[["RNA"]]) && length(Layers(rdsobj[["RNA"]])) > 1) {
      rdsobj[["RNA"]] <- JoinLayers(rdsobj[["RNA"]])
      message("Note: JoinLayers applied to ", samplenames[i])
    }
    testcountfile = rdsobj[["RNA"]]$counts
  }

  if (umiformat[i] == "h5") {
    # TODO：完善直接读取 h5 的注释生成功能
    a = Read10X_h5(countfiles[i])
    # testcountfile = a[["Gene Expression"]]
    testcountfile = a
  }

  if (umiformat[i] == "seuratobj") {
    # 直接返回对象
    rdsobj <- countfiles[i]
    testcountfile = rdsobj[["RNA"]]$counts
  }



  # 标准化列名（加样本前缀）
  colnames(testcountfile) = paste(samplenames[i], colnames(testcountfile),
                                  sep = "_")

  ## ---- 读完 count 矩阵后立即转稀疏，避免 dense 矩阵占双份内存 ----
  if (!inherits(testcountfile, "dgCMatrix")) {
    testcountfile <- as(Matrix::as.matrix(testcountfile), "dgCMatrix")
  }


  # 创建对象（最宽松阈值；后续统一 QC）
  test <- CreateSeuratObject(counts = testcountfile, project = "test",
                             min.cells = 1, min.features = 1)

  rm(testcountfile)
  gc()

  # ---- 过滤低检出基因（< min_cells_in_gene 的基因）----
  counts  <- GetAssayData(object = test, layer = "counts")
  nnz     <- Matrix::rowSums(counts > 0)
  keep_genes <- nnz >= min_cells_in_gene
  test_discard_genes <- nnz < min_cells_in_gene

  ## ---- 直接在原对象上按基因子集，不再重建 Seurat 对象 ----
  test <- subset(test, features = rownames(test)[keep_genes])

  rm(counts, nnz)
  gc()


  test[["group"]]     <- listnames[i]
  test[["replicate"]] <- samplenames[i]
  test[["dataset"]] <- datasets[i]

  # ---- QC 指标（线粒体/核糖体/HB/血小板）----
  test[["percent.mt"]] <- PercentageFeatureSet(
    test,
    pattern = "^ATP6$|^ATP8$|^COX1$|^COX2$|^COX3$|^CYTB$|^mt-Rnr1$|^mt-Rnr2$|^ND1$|^ND2$|^ND3$|^ND4$|^ND4L$|^ND5$|^ND6$|^Trna$|^Trnc$|^Trnd$|^Trne$|^Trnf$|^Trng$|^Trnh$|^Trni$|^Trnk$|^Trnl1$|^Trnl2$|^Trnm$|^Trnn$|^Trnp$|^Trnq$|^Trnr$|^Trns1$|^Trns2$|^Trnt$|^Trnv$|^Trnw$|^Trny$|^MT-|^mt-|^ATMG0|cxA01g000760|cxA01g000840|cxA01g008080|cxA01g009770|cxA01g014300|cxA01g015560|cxA01g018480|cxA01g019260|cxA01g019980|cxA01g021880|cxA01g023840|cxA01g025690|cxA01g030590|cxA01g037190|cxA01g038650|cxA01g041980|cxA01g046780|cxA02g004080|cxA02g004140|cxA02g005750|cxA02g007380|cxA02g009060|cxA02g011590|cxA02g011630|cxA02g019030|cxA02g020480|cxA02g020830|cxA02g027150|cxA02g027630|cxA02g030520|cxA02g031020|cxA02g032400|cxA02g033330|cxA02g039030|cxA02g043690|cxA03g000970|cxA03g001170|cxA03g001620|cxA03g001720|cxA03g004090|cxA03g004100|cxA03g004550|cxA03g005790|cxA03g005860|cxA03g009660|cxA03g010230|cxA03g010840|cxA03g011930|cxA03g015200|cxA03g016030|cxA03g017510|cxA03g020050|cxA03g020840|cxA03g021380|cxA03g026350|cxA03g027520|cxA03g032330|cxA03g040920|cxA03g040950|cxA03g050320|cxA03g051400|cxA03g064520|cxA03g066670|cxA04g004440|cxA04g007270|cxA04g008660|cxA04g020420|cxA04g021050|cxA04g023840|cxA04g024020|cxA04g024160|cxA04g024350|cxA04g025220|cxA04g025230|cxA04g025350|cxA04g029180|cxA04g030130|cxA04g034500|cxA04g037760|cxA05g010800|cxA05g014030|cxA05g017080|cxA05g017980|cxA05g019010|cxA05g019500|cxA05g019940|cxA05g023010|cxA05g024850|cxA05g024940|cxA05g025050|cxA05g027010|cxA05g031790|cxA05g032660|cxA05g033660|cxA05g033920|cxA05g034060|cxA05g034520|cxA05g043120|cxA06g006630|cxA06g009910|cxA06g010880|cxA06g014840|cxA06g015300|cxA06g018370|cxA06g019420|cxA06g021550|cxA06g025180|cxA06g025560|cxA06g028340|cxA06g031190|cxA06g036320|cxA06g043760|cxA07g009780|cxA07g011280|cxA07g015320|cxA07g015880|cxA07g018570|cxA07g027760|cxA07g027770|cxA07g033420|cxA07g034500|cxA07g035180|cxA07g039420|cxA07g040580|cxA07g041340|cxA07g041950|cxA08g010220|cxA08g015150|cxA08g017220|cxA08g021720|cxA08g027020|cxA08g027910|cxA08g028000|cxA08g030250|cxA08g030330|cxA08g031960|cxA08g035770|cxA08g036460|cxA09g001250|cxA09g007250|cxA09g011300|cxA09g011790|cxA09g013030|cxA09g017370|cxA09g017430|cxA09g018120|cxA09g021760|cxA09g029780|cxA09g030560|cxA09g031120|cxA09g033670|cxA09g033680|cxA09g035000|cxA09g036040|cxA09g037530|cxA09g037810|cxA09g039630|cxA09g039970|cxA09g040550|cxA09g045270|cxA09g047100|cxA09g047680|cxA09g048620|cxA09g049110|cxA09g049730|cxA09g064460|cxA10g004740|cxA10g010290|cxA10g010590|cxA10g022070|cxA10g022080|cxA10g023600|cxA10g024310|cxA10g024320|cxA10g025450|cxA10g026580|cxA10g028630|cxA10g028890|cxA10g031430|cxSC012000110|cxSC012000160|cxSC012000180|cxSC012000230|cxSC012000320|cxSC012000360|cxSC012000390|cxSC012000400|cxSC012000420|cxSC012000430|cxSC012000460|cxSC012000520|cxSC012000600|cxSC012000620|cxSC012000650|cxSC012000660|cxSC012000680|cxSC012000690|cxSC012000720|cxSC012000750|cxSC012000810|cxSC012000830|cxSC012000910|cxSC012000990|cxSC012001020|cxSC012001130|cxSC012001150|cxSC012001180|cxSC012001230|cxSC012001290|cxSC012001310|cxSC012001400|cxSC012001560|cxSC012001590|cxSC012001640|cxSC023001240|cxA04g025860|cxA02g007270|cxA03g020030|cxA02g011420"
  )
  test[["percent.ribo"]] <- PercentageFeatureSet(test, "^RP[SL]|^Rp[sl]")
  test[["percent.hb"]]   <- PercentageFeatureSet(test, "^HB[^(P)]|^Hb[^(p)]")
  test[["percent.plat"]] <- PercentageFeatureSet(test, "^PECAM1$|^PF4$|^Pecam1$|^Pf4$")

  # ---- QC 可视化 ----
  p1 <- VlnPlot(
    test,
    features = c("nFeature_RNA", "nCount_RNA", "percent.mt",
                 "percent.ribo", "percent.hb"),
    ncol = 5, pt.size = 0.1
  )
  pdf(file = paste("QC_all_", samplenames[i], ".pdf", sep = ""),
      width = 20, height = 4)
  print(p1); dev.off()

  png(file = paste("QC_all_", samplenames[i], ".png", sep = ""),
      width = 600, height = 120, units = "mm", res = 300, pointsize = 2)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1); dev.off()

  p1 <- FeatureScatter(test, feature1 = "nCount_RNA", feature2 = "percent.mt",
                       pt.size = 0.1)
  p2 <- FeatureScatter(test, feature1 = "nCount_RNA", feature2 = "nFeature_RNA",
                       pt.size = 0.1)
  p3 <- FeatureScatter(test, feature1 = "percent.mt", feature2 = "nFeature_RNA",
                       pt.size = 0.1)

  pdf(file = paste("QC_FeatureScatter_", samplenames[i], ".pdf", sep = ""),
      width = 15, height = 4)
  print(p1 + p2 + p3); dev.off()

  png(file = paste("QC_FeatureScatter_", samplenames[i], ".png", sep = ""),
      width = 375, height = 100, units = "mm", res = 300, pointsize = 2)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  print(p1 + p2 + p3); dev.off()

  # ---- QC 过滤 ----
  qc.total       <- test$nCount_RNA > 0
  qc.lib         <- (test$nCount_RNA < min_total_UMI & test$nCount_RNA > 0)
  qc.nexprs.low  <- (test$nFeature_RNA < min_genes  & test$nCount_RNA > 0)
  # qc.nexprs.high <- (test$nFeature_RNA > max_genes & test$nCount_RNA > 0)
  qc.mito        <- (test$percent.mt > max_MT       & test$nCount_RNA > 0)
  qc.hb          <- (test$percent.hb > max_HB       & test$nCount_RNA > 0)

  test <- subset(
    test,
    subset = nFeature_RNA >= min_genes &
             # nFeature_RNA <= max_genes &
             nCount_RNA   >= min_total_UMI &
             percent.mt   <= max_MT &
             percent.hb   <= max_HB
  )
  qc.keep_only <- sum(test$nCount_RNA > 0)

  # ---- 标准化 ----
  if (umiformat[i] != "expcsv") {
    test <- NormalizeData(test, normalization.method = "LogNormalize",
                          scale.factor = 10000)
  }

  # ---- 高变基因 ----
  test <- FindVariableFeatures(test, selection.method = "vst", nfeatures = 2000)

  top10 <- head(VariableFeatures(test), 10)

  pdf(file = paste("QC_highly_variable_features_", samplenames[i], ".pdf",
                   sep = ""),
      width = 6, height = 4)
  plot1 <- VariableFeaturePlot(test)
  plot2 <- LabelPoints(plot = plot1, points = top10, repel = TRUE,
                       xnudge = 0, ynudge = 0)
  print(plot2); dev.off()

  png(file = paste("QC_highly_variable_features_", samplenames[i], ".png",
                   sep = ""),
      width = 150, height = 100, units = "mm", res = 300, pointsize = 2)
  par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  plot1 <- VariableFeaturePlot(test)
  plot2 <- LabelPoints(plot = plot1, points = top10, repel = TRUE,
                       xnudge = 0, ynudge = 0)
  print(plot2); dev.off()

  if (opt$method %in% c("sct_cca", "sct_rpca", "sct_harmony")) {
    test <- SCTransform(test, method = "glmGamPoi",
                        vars.to.regress = "percent.mt", verbose = FALSE)
  }

  # ---- DoubletFinder（每样本独立）----
  if (tolower(opt$doublet_enable) == "true") {
      cat(
      "Run DoubletFinder.\n"
    )
    # 1) 是否使用 SCT
    sct_flag <- if (tolower(opt$doublet_sct) == "auto") {
      "SCT" %in% Assays(test)
    } else tolower(opt$doublet_sct) == "true"

    DefaultAssay(test) <- if (sct_flag) "SCT" else "RNA"

    # 2) 降维与聚类（若缺失则补齐）
    if (DefaultAssay(test) == "RNA") {
      test <- ScaleData(test, vars.to.regress = c("nFeature_RNA", "percent.mt"),
                        verbose = FALSE)
    }
    if (!"pca" %in% names(test@reductions)) {
      test <- RunPCA(test, npcs = max(opt$doublet_pc_max, 20), verbose = FALSE)
    }
    pc.num <- opt$doublet_pc_min:opt$doublet_pc_max

    if (!"umap" %in% names(test@reductions)) {
      test <- RunUMAP(test, dims = pc.num, verbose = FALSE)
    }
    test <- FindNeighbors(test, dims = pc.num)
    test <- FindClusters(test, resolution = opt$doublet_resolution)

    # 3) pK 扫描（兼容新旧 API）
    has_v3 <- "paramSweep_v3" %in% getNamespaceExports("DoubletFinder")
    sweep.res.list <- if (has_v3) {
      DoubletFinder::paramSweep_v3(test, PCs = pc.num, sct = sct_flag)
    } else {
      DoubletFinder::paramSweep(test, PCs = pc.num, sct = sct_flag)
    }
    sweep.stats <- DoubletFinder::summarizeSweep(sweep.res.list, GT = FALSE)
    bcmvn       <- DoubletFinder::find.pK(sweep.stats)

    pK_bcmvn <- if (is.na(opt$doublet_force_pk)) {
      as.numeric(as.character(bcmvn$pK[which.max(bcmvn$BCmetric)]))
    } else {
      opt$doublet_force_pk
    }
    message(sprintf("[DF] sample=%s | pK=%.4f | pN=%.2f",
                    samplenames[i], pK_bcmvn, opt$doublet_pn))

    # 4) 期望双细胞 & 同源修正
    nExp_poi     <- round(opt$doublet_rate * ncol(test))
    homotypic.pr <- DoubletFinder::modelHomotypic(test$seurat_clusters)
    nExp_poi.adj <- round(nExp_poi * (1 - homotypic.pr))

    # 5) 运行 DF（兼容新旧接口）
    reuse_col <- if (tolower(opt$doublet_reuse_pann) == "true") {
      pcols <- grep("^pANN", colnames(test@meta.data), value = TRUE)
      if (length(pcols) > 0) pcols[1] else NULL
    } else NULL

    df_fun <- if (has_v3) DoubletFinder::doubletFinder_v3
              else        DoubletFinder::doubletFinder

    test <- df_fun(test, PCs = pc.num, pN = opt$doublet_pn, pK = pK_bcmvn,
                   nExp = nExp_poi.adj, reuse.pANN = reuse_col, sct = sct_flag)

    # 6) 结果标注与导出
    DF.name <- grep("^DF.classifications", colnames(test@meta.data), value = TRUE)
    if (length(DF.name) >= 1) {
      DF.name <- DF.name[1]

      tab_df <- table(test@meta.data[[DF.name]])
      nD <- if ("Doublet" %in% names(tab_df)) as.integer(tab_df[["Doublet"]]) else 0L
      nS <- if ("Singlet" %in% names(tab_df)) as.integer(tab_df[["Singlet"]])
            else (ncol(test) - nD)

      test@misc$doublet_stats <- list(
        predicted_doublets = nD,
        predicted_singlets = nS,
        pk                 = pK_bcmvn,
        pn                 = opt$doublet_pn,
        nExp_raw           = nExp_poi,
        nExp_adj           = nExp_poi.adj,
        pcs_used           = paste0(min(pc.num), ":", max(pc.num)),
        sct                = sct_flag,
        resolution         = opt$doublet_resolution,
        sample             = samplenames[i]
      )

      p.umap <- DimPlot(test, reduction = "umap", group.by = DF.name,
                        pt.size = 0.1)
      ggsave(paste0("DimPlot_doublet_", samplenames[i], ".pdf"),
             p.umap, width = 5, height = 4)
      ggsave(paste0("DimPlot_doublet_", samplenames[i], ".png"),
             p.umap, width = 5, height = 4, dpi = 300)

      p.vln <- VlnPlot(test, features = "nFeature_RNA", group.by = DF.name,
                       pt.size = 0.1)
      ggsave(paste0("VlnPlot_doublet_", samplenames[i], ".pdf"),
             p.vln, width = 5, height = 4)
      ggsave(paste0("VlnPlot_doublet_", samplenames[i], ".png"),
             p.vln, width = 5, height = 4, dpi = 300)

      write.table(
        table(test[[DF.name]][, 1]),
        file = paste0(samplenames[i], "_doublet_counts.tsv"),
        sep = "\t", quote = FALSE, col.names = FALSE
      )

      if (tolower(opt$doublet_keep) == "singlet") {
        test <- test[, test@meta.data[[DF.name]] == "Singlet"]
      }
    } else {
      warning(sprintf("[DF] %s 未找到 DF.classifications 列，跳过过滤。",
                      samplenames[i]))
    }
  }

  # ---- 过滤统计（含 DF）----
  df_pred <- NA_integer_
  df_sing <- NA_integer_

  if (!is.null(test@misc$doublet_stats)) {
    if (!is.null(test@misc$doublet_stats$predicted_doublets))
      df_pred <- as.integer(test@misc$doublet_stats$predicted_doublets)
    if (!is.null(test@misc$doublet_stats$predicted_singlets))
      df_sing <- as.integer(test@misc$doublet_stats$predicted_singlets)
  }

  if (is.na(df_pred) || is.na(df_sing)) {
    df_col <- grep("^DF.classifications", colnames(test@meta.data), value = TRUE)
    if (length(df_col) >= 1) {
      tmp_tab <- table(test@meta.data[[df_col[1]]])
      df_pred <- if ("Doublet" %in% names(tmp_tab)) as.integer(tmp_tab["Doublet"]) else 0L
      df_sing <- if ("Singlet" %in% names(tmp_tab)) as.integer(tmp_tab["Singlet"])
                 else qc.keep_only
    }
  }

  if (is.na(df_pred)) df_pred <- 0L
  if (is.na(df_sing)) df_sing <- qc.keep_only

  df_rate <- if ((df_pred + df_sing) > 0) df_pred / (df_pred + df_sing) else NA_real_

  keep_final <- max(0L, qc.keep_only - df_pred)
  total_filtered_final <- sum(qc.total) - keep_final

  dis <- DataFrame(
    Raw            = sum(qc.total),
    LibSize        = sum(qc.lib),
    NExprsLow      = sum(qc.nexprs.low),
    # NExprsHigh   = sum(qc.nexprs.high),
    MitoProp       = sum(qc.mito),
    HbProp         = sum(qc.hb),
    DF_PredDoublet = df_pred,     # 预测双细胞数
    DF_PredRate    = df_rate,     # 预测双细胞率
    Total          = total_filtered_final,  # 含 DF 的总过滤数
    Keep           = keep_final,            # 去 DF 后保留数
    ExpressGenes   = sum(test_discard_genes),
    KeepGenes      = sum(keep_genes)
  )

  header_line <- paste(
    "原始细胞数",
    paste0("按比对总量过滤(<", min_total_UMI, ")"),
    paste0("按最低检出基因数过滤(<", min_genes, ")"),
    # paste0("按最高检出基因数过滤(>", max_genes, ")"),
    paste0("按线粒体比例过滤(>", max_MT, "%)"),
    paste0("按红细胞比例过滤(>", max_HB, "%)"),
    "预测双细胞数(DF)",
    "预测双细胞率(DF)",
    "总过滤细胞数(含双细胞)",
    "QC后保留细胞数(去双细胞后)",
    paste0("筛选掉少数细胞表达的基因(<", min_cells_in_gene, ")"),
    "最终保留的基因数",
    sep = "\t"
  )

  out_file <- paste0(samplenames[i], "_discard_stat", ".xls")
  cat(header_line, "\n", file = out_file)
  write.table(dis, file = out_file, append = TRUE, quote = FALSE, sep = "\t",
              row.names = FALSE, col.names = FALSE)

  # ---- Gene-level summary + DotPlot (Top30 by nonzero mean) ----
  DefaultAssay(test) <- "RNA"

  counts_mat <- tryCatch(
    GetAssayData(test, assay = "RNA", layer = "counts"),
    error = function(e) GetAssayData(test, assay = "RNA", slot = "counts")
  )
  data_mat <- tryCatch(
    GetAssayData(test, assay = "RNA", layer = "data"),
    error = function(e) GetAssayData(test, assay = "RNA", slot = "data")
  )

  nnz_cells <- Matrix::rowSums(counts_mat > 0)
  pct_cells <- as.numeric(nnz_cells) / ncol(counts_mat) * 100

  sum_data <- Matrix::rowSums(data_mat)
  mean_all <- as.numeric(sum_data) / ncol(data_mat)
  mean_nz  <- ifelse(nnz_cells > 0, as.numeric(sum_data) / nnz_cells, 0)

  gene_tbl <- data.frame(
    gene              = rownames(data_mat),
    mean_expr_nonzero = mean_nz,
    mean_expr_all     = mean_all,
    pct_cells         = pct_cells,
    n_cells_express   = as.integer(nnz_cells),
    stringsAsFactors  = FALSE
  )
  gene_tbl <- gene_tbl[order(gene_tbl$mean_expr_all, decreasing = TRUE), ]

  out_all <- paste0("gene_summary_avg_nonzero_pct_", samplenames[i], ".tsv")
  write.table(gene_tbl, file = out_all, sep = "\t", quote = FALSE, row.names = FALSE)

  topN      <- min(30L, nrow(gene_tbl))
  top_genes <- gene_tbl$gene[seq_len(topN)]
  top_tbl   <- gene_tbl[seq_len(topN), ]
  write.table(
    top_tbl,
    file = paste0("top", topN, "_gene_summary_", samplenames[i], ".tsv"),
    sep = "\t", quote = FALSE, row.names = FALSE
  )

  df_dot <- transform(top_tbl, sample = samplenames[i])
  df_dot$gene <- factor(df_dot$gene, levels = rev(top_genes))

  p_dot <- ggplot(df_dot, aes(x = sample, y = gene)) +
    geom_point(aes(size = pct_cells, color = mean_expr_all)) +
    scale_size_continuous(name = "% cells", range = c(2, 10), limits = c(0, 100)) +
    scale_color_viridis_c(name = "avg expr\n(nonzero)", option = "C") +
    labs(
      title    = paste0("Top ", topN, " genes per sample (DotPlot)"),
      subtitle = paste0("sample: ", samplenames[i],
                        " | color = mean(log-normalized) among expressing cells"),
      x = NULL, y = NULL
    ) +
    theme_paper +
    theme(
      legend.position = "right",
      axis.text.x     = element_text(angle = 0, vjust = 0.5, hjust = 0.5),
      plot.title      = element_text(face = "bold")
    )

  ggsave(paste0("dotplot_top", topN, "_", samplenames[i], ".pdf"),
         p_dot, width = 120, height = 180, units = "mm")
  ggsave(paste0("dotplot_top", topN, "_", samplenames[i], ".png"),
         p_dot, width = 120, height = 180, units = "mm", dpi = 300)

  ## ---- [MEM] 每个样本完成 QC / Doublet / gene_summary 后做一次“瘦身” ----
  keep_assays <- intersect(c("RNA", "SCT"), Assays(test))

  test <- DietSeurat(
    test,
    assays     = keep_assays,
    counts     = TRUE,
    data       = TRUE,
    scale.data = TRUE,   # 不保留 scale.data
    dimreducs  = NULL,    # 不保留 pca/umap 等
    graphs     = NULL     # 不保留邻接图
  )
  gc()

  return(test)
}


# =============================================================================
# 多样本读取与样本筛选（细胞数 < 30 的样本剔除）
# =============================================================================

## 如果本地已有 sc_list_qc.rds，则直接使用；否则从头计算
if (file.exists("sc_list_qc.rds")) {
  sc.list <- readRDS("sc_list_qc.rds")
  cat("检测到已有 sc_list_qc.rds，直接加载。样本数量：", length(sc.list), "\n")
} else {
  if (opt$sourcetype == "raw") {
    sc.list <- future_lapply(1:length(countfiles), cell_filter)

    keep_indices <- sapply(sc.list, ncol) >= 30
    if (any(!keep_indices)) {
      cat("以下样本因细胞数少于30而被移除：\n")
      print(countfiles[!keep_indices])
    }
    sc.list <- sc.list[keep_indices]

  } else {
    subcells <- readRDS(countfiles[1])
    sc.list  <- SplitObject(subcells, split.by = opt$sourcetype)

    keep_indices <- sapply(sc.list, ncol) >= 30
    if (any(!keep_indices)) {
      cat("以下样本因细胞数少于30而被移除：\n")
      print(names(sc.list)[!keep_indices])
    }
    sc.list <- sc.list[keep_indices]
  }

  cat("过滤后剩余的样本数量：", length(sc.list), "\n")
  # saveRDS(sc.list, file = "sc_list_qc.rds")
  saveRDS(sc.list, file = "sc_list_qc.rds", compress = FALSE)
}


plan(sequential)


# =============================================================================
# 仅 merge（查看批次效应）
# =============================================================================
if (opt$method == "merge") {
  sc.list2 <- lapply(sc.list, function(x) {
    DefaultAssay(x) <- "RNA"
    if (!is.null(x[["RNA"]]) && length(Layers(x[["RNA"]])) > 1) {
      x[["RNA"]] <- JoinLayers(x[["RNA"]])
    }
    x <- DietSeurat(
      x,
      assays     = "RNA",
      counts     = TRUE,
      data       = FALSE,
      scale.data = FALSE,
      dimreducs  = NULL,
      graphs     = NULL
    )
    if ("SCT" %in% Assays(x)) x[["SCT"]] <- NULL
    return(x)
  })

  sc.merge <- sc.list2[[1]]
  # if (length(sc.list2) > 1) {
  #   for (k in 2:length(sc.list2)) {
  #     sc.merge <- merge(sc.merge, y = sc.list2[[k]], merge.data = FALSE)
  #     gc()
  #   }
  # }
  # rm(sc.list2)

  if (length(sc.list2) > 1) {
    # 【核心内存优化】：使用向量化 merge 而不是循环 merge
    # merge(x, y = list(...)) 比循环 merge(x, y) 快且内存占用极低
    sc.merge <- merge(x = sc.list2[[1]], y = sc.list2[-1], merge.data = TRUE)
  } else {
    sc.merge <- sc.list2[[1]]
  }
  rm(sc.list2)

  sc.merge <- NormalizeData(sc.merge, normalization.method = "LogNormalize",
                            scale.factor = 10000, verbose = FALSE)
  sc.merge <- FindVariableFeatures(sc.merge, selection.method = "vst",
                                   nfeatures = 2000, verbose = FALSE)

  logger.warn("Performed simple merge (no batch correction).")

  sc.merge <- FindVariableFeatures(sc.merge, nfeatures = 6000)
  sc.merge <- ScaleData(sc.merge, features = VariableFeatures(sc.merge),
                        verbose = FALSE, vars.to.regress = c("percent.mt", "percent.ribo"))

  DefaultAssay(sc.merge) <- "RNA"
  sc.merge <- RunPCA(sc.merge, npcs = 30, verbose = FALSE)
  sc.merge <- RunUMAP(sc.merge, dims = 1:30)
  sc.merge <- FindNeighbors(sc.merge, dims = 1:30)
  sc.merge <- FindClusters(sc.merge, resolution = 0.5)

  p1 <- DimPlot(sc.merge, reduction = "umap", group.by = "replicate", pt.size = 0.1)
  p2 <- DimPlot(sc.merge, reduction = "umap", group.by = "group",     pt.size = 0.1)
  p3 <- DimPlot(sc.merge, reduction = "umap", label = TRUE, repel = TRUE, pt.size = 0.1)

  pdf("final_umap_plots.onlymerge.pdf", width = 16, height = 4)
  print((p1 + p2 + p3) + theme_paper)
  dev.off()

  png("final_umap_plots.onlymerge.png", width = 400, height = 100, units = "mm", res = 300)
  print((p1 + p2 + p3) + theme_paper)
  dev.off()

  rm(sc.merge)

  cat(
    "Graceful exit: --method merge is disabled in this pipeline.\n",
    "Use --method none (仅合并不整合) 或 rpca/cca/sct_* 以继续。\n",
    file = "EXITED_GRACEFULLY_due_to_merge.txt"
  )
  cat(
    "Graceful exit: --method merge is disabled in this pipeline.\n",
    "Use --method none (仅合并不整合) 或 rpca/cca/sct_* 以继续。\n"
  )

  try({ future::plan(sequential) }, silent = TRUE)
  try({ gc() },                    silent = TRUE)
  quit(save = "no", status = 0, runLast = FALSE)
}


# =============================================================================
# 数据整合
# =============================================================================

# sc.list <- lapply(sc.list, function(x) {
#   DefaultAssay(x) <- "RNA"
#   if (!is.null(x[["RNA"]]) && length(Layers(x[["RNA"]])) > 1) {
#     message("JoinLayers.\n")
#     x[["RNA"]] <- JoinLayers(x[["RNA"]])
#   }
#   return(x)
# })

if (length(countfiles) == 1 && opt$sourcetype == "raw") {
  sc.combined <- sc.list[[1]]

} else if (opt$method == "sct_harmony") {
  var.features <- SelectIntegrationFeatures(object.list = sc.list, nfeatures = 3000)
  sc.combined  <- merge(x = sc.list[[1]], y = sc.list[2:length(sc.list)],
                        merge.data = TRUE)
  DefaultAssay(sc.combined) <- "SCT"
  rm(sc.list)
  VariableFeatures(sc.combined) <- var.features
  sc.combined <- RunPCA(sc.combined, verbose = FALSE)
  sc.combined <- RunHarmony(sc.combined, assay.use = "SCT", group.by.vars = "replicate")

  # sc.combined <- RunUMAP(sc.combined, reduction = "harmony", dims = 1:50)
  # sc.combined <- FindNeighbors(sc.combined, reduction = "harmony", dims = 1:50) %>% FindClusters()

  # p1 <- DimPlot(sc.combined, reduction = "umap", group.by = "replicate", pt.size = 0.1)
  # p2 <- DimPlot(sc.combined, reduction = "umap", group.by = "group",     pt.size = 0.1)
  # p3 <- DimPlot(sc.combined, reduction = "umap", label = TRUE, pt.size = 0.1)

  # pdf(file = paste("umap_cluster", "pdf", sep = "."), width = 18, height = 5)
  # print((p1 + p2 + p3) + theme_paper)
  # dev.off()

  # png(file = paste("umap_cluster", ".png", sep = ""), width = 450, height = 125,
  #     units = "mm", res = 300, pointsize = 10)
  # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  # print(p1 + p2 + p3)
  # dev.off()

  # p1 <- DimPlot(sc.combined, reduction = "umap", group.by = "replicate",
  #               split.by = "group", pt.size = 0.1, label = TRUE)

  # pdf(file = paste("umap_cluster_bygroup", "pdf", sep = "."),
  #     width = 4 * groupnum, height = 4)
  # print(p1)
  # dev.off()

  # png(file = paste("umap_cluster_bygroup", ".png", sep = ""),
  #     width = 100 * groupnum, height = 100, units = "mm", res = 300,
  #     pointsize = 10)
  # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
  # print(p1)
  # dev.off()

} else {
  # ---- 分批整合（子批次）----
  chunk_index <- ceiling(seq_along(sc.list) / opt$batchSize)
  batch_lists <- split(sc.list, chunk_index)
  rm(sc.list)

  message("\n>> 批次数量 ...")
  message(opt$batchSize)
  message("\n")

  message("\n>> 对每个批次进行整合 ...")
  sub_integrated <- future_lapply(seq_along(batch_lists), function(i) {
    sublist <- batch_lists[[i]]
    if (length(sublist) == 1) {
      return(sublist[[1]])
    } else {
      if (opt$method %in% c("cca", "rpca")) {
        features <- SelectIntegrationFeatures(object.list = sublist, nfeatures = 3000)
        if (opt$method == "rpca") {
          sublist <- lapply(sublist, function(x) {
            x <- ScaleData(x, features = features, verbose = FALSE)
            x <- RunPCA(x, features = features, verbose = FALSE)
            return(x)
          })
          anchors  <- FindIntegrationAnchors(object.list = sublist,
                                             anchor.features = features,
                                             reduction = "rpca")
          combined <- IntegrateData(anchorset = anchors)
          DefaultAssay(combined) <- "integrated"
          return(combined)
        } else {
          message("\n>> 开始cca整合 ...")
          anchors  <- FindIntegrationAnchors(object.list = sublist,
                                             anchor.features = features)
          combined <- IntegrateData(anchorset = anchors, k.weight = 100)
          DefaultAssay(combined) <- "integrated"
          message("\n>> cca整合完成 ...")
          return(combined)
        }
      } else if (opt$method %in% c("sct_cca", "sct_rpca")) {
        DefaultAssay(sc.combined) <- "SCT"
        if (opt$sourcetype != "raw") {
          sublist <- lapply(sublist, function(x) {
            x <- SCTransform(x, method = "glmGamPoi",
                             vars.to.regress = "percent.mt", verbose = FALSE)
            return(x)
          })
        }
        features <- SelectIntegrationFeatures(object.list = sublist, nfeatures = 3000)
        sublist  <- PrepSCTIntegration(object.list = sublist, anchor.features = features)

        if (opt$method == "sct_rpca") {
          sublist <- lapply(sublist, function(x) {
            x <- RunPCA(x, features = features, verbose = FALSE)
            return(x)
          })
          anchors  <- FindIntegrationAnchors(
            object.list = sublist,
            anchor.features = features,
            normalization.method = "SCT",
            reduction = "rpca",
            dims = 1:50
          )
          combined <- IntegrateData(anchorset = anchors, normalization.method = "SCT")
          DefaultAssay(combined) <- "SCT"
          return(combined)
        } else {
          anchors  <- FindIntegrationAnchors(
            object.list = sublist,
            anchor.features = features,
            normalization.method = "SCT"
          )
          combined <- IntegrateData(anchorset = anchors, normalization.method = "SCT")
          DefaultAssay(combined) <- "SCT"
          return(combined)
        }
      } else {
        stop("method不在(cca, rpca, sct_cca, sct_rpca, none)范围内: ", opt$method)
      }
    }
  })

  # ---- 最终整合（对子批次结果再整合一次）----
  if (length(sub_integrated) == 1) {
    sc.combined <- sub_integrated[[1]]
  } else {
    message("\n>> 将若干子整合结果，再次 FindIntegrationAnchors + IntegrateData ...")

    final_features <- SelectIntegrationFeatures(object.list = sub_integrated,
                                                nfeatures = 3000)

    if (opt$method == "cca") {
      final_anchors <- FindIntegrationAnchors(
        object.list = sub_integrated,
        anchor.features = final_features
      )
      sc.combined <- IntegrateData(anchorset = final_anchors)
      DefaultAssay(sc.combined) <- "integrated"

    } else if (opt$method == "rpca") {
      sub_integrated <- lapply(sub_integrated, function(x) {
        x <- ScaleData(x, features = final_features, verbose = FALSE)
        x <- RunPCA(x, features = final_features, verbose = FALSE)
        return(x)
      })
      final_anchors <- FindIntegrationAnchors(
        object.list = sub_integrated,
        anchor.features = final_features,
        reduction = "rpca"
      )
      sc.combined <- IntegrateData(anchorset = final_anchors)
      DefaultAssay(sc.combined) <- "integrated"

    } else if (opt$method == "sct_cca") {
      sub_integrated <- lapply(sub_integrated, function(x) {
        DefaultAssay(x) <- "SCT"
        return(x)
      })
      sub_integrated <- PrepSCTIntegration(
        object.list = sub_integrated,
        anchor.features = final_features
      )
      final_anchors <- FindIntegrationAnchors(
        object.list = sub_integrated,
        anchor.features = final_features,
        normalization.method = "SCT"
      )
      sc.combined <- IntegrateData(
        anchorset = final_anchors,
        normalization.method = "SCT"
      )
      DefaultAssay(sc.combined) <- "SCT"

    } else if (opt$method == "sct_rpca") {
      sub_integrated <- lapply(sub_integrated, function(x) {
        DefaultAssay(x) <- "SCT"
        x <- RunPCA(x, features = final_features, verbose = FALSE)
        return(x)
      })
      final_anchors <- FindIntegrationAnchors(
        object.list = sub_integrated,
        anchor.features = final_features,
        normalization.method = "SCT",
        reduction = "rpca",
        dims = 1:50
      )
      sc.combined <- IntegrateData(
        anchorset = final_anchors,
        normalization.method = "SCT"
      )
      DefaultAssay(sc.combined) <- "SCT"

    } else {
      stop("method不在(cca, rpca, sct_cca, sct_rpca)之列:", opt$method)
    }
  }
}



# =============================================================================
# Scale / PCA / 可视化（整合后）
# =============================================================================

all.genes <- rownames(sc.combined)
# sc.combined <- ScaleData(sc.combined, features = all.genes)

# 仅在 cca / rpca 时先对 HVG 做 Scale
if (opt$method == "cca" || opt$method == "rpca") {
  # sc.combined <- ScaleData(sc.combined, features = all.genes,
  #                          verbose = FALSE,
  #                          vars.to.regress = c("percent.mt", "percent.ribo"))
  sc.combined <- FindVariableFeatures(sc.combined, nfeatures = 6000)
  sc.combined <- ScaleData(sc.combined,
                           features = VariableFeatures(sc.combined),
                           verbose  = FALSE,
                           vars.to.regress = c("percent.mt", "percent.ribo"))
}

# ---- PCA ----
if (opt$method != "sct_harmony") {
  sc.combined <- RunPCA(
    sc.combined,
    features      = VariableFeatures(object = sc.combined),
    npcs          = 100,
    ndims.print   = 1:5,
    nfeatures.print = 5
  )
}

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

# saveRDS(sc.combined, file = "./sc_preprocessing.rds")
saveRDS(sc.combined, file = "./sc_preprocessing.rds", compress = FALSE)
cat("\n=== 分批整合完成！结果已输出到 sc_preprocessing.rds ===\n")

sc.combined


# ---- PCA 可视化 ----
p1 <- VizDimLoadings(sc.combined, dims = 1:2, reduction = "pca")
pdf(file = paste("VizPlot_PCA", ".pdf", sep = ""), width = 8, height = 5)
p1; dev.off()

png(file = paste("VizPlot_PCA", ".png", sep = ""),
    width = 200, height = 125, units = "mm", res = 300, pointsize = 1.5)
par(mar = c(5, 5, 2, 2), cex.axis = 1.5, cex.lab = 2)
p1; dev.off()

p1 <- DimPlot(sc.combined, reduction = "pca",
              group.by = "replicate", split.by = "group", pt.size = 0.01)
pdf(file = paste("DimPlot_PCA", ".pdf", sep = ""),
    width = 4 * groupnum, height = 4)
p1; dev.off()

png(file = paste("DimPlot_PCA", ".png", sep = ""),
    width = 100 * groupnum, height = 100, units = "mm", res = 300, pointsize = 2)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
p1; dev.off()

pdf(file = paste("DimHeatmap_PCA", ".pdf", sep = ""),
    width = 15, height = 10)
DimHeatmap(sc.combined, dims = 1:9, cells = 500, balanced = TRUE)
dev.off()

png(file = paste("DimHeatmap_PCA", ".png", sep = ""),
    width = 450, height = 300, units = "mm", res = 300, pointsize = 15)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
DimHeatmap(sc.combined, dims = 1:9, cells = 500, balanced = TRUE)
dev.off()


# =============================================================================
# 选择主成分个数（ElbowPlot）
# =============================================================================

# JackStraw 计算量大，示例保留为注释
# sc.combined <- JackStraw(sc.combined, num.replicate = 100)
# sc.combined <- ScoreJackStraw(sc.combined, dims = 1:20)
# JackStrawPlot(sc.combined, dims = 1:15)

pdf(file = paste("ElbowPlot", ".pdf", sep = ""), width = 10, height = 4)
p1 <- ElbowPlot(sc.combined, ndims = 25)
p2 <- ElbowPlot(sc.combined, ndims = 100)
p1 + p2
dev.off()

png(file = paste("ElbowPlot", ".png", sep = ""),
    width = 250, height = 100, units = "mm", res = 300, pointsize = 2)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
p1 <- ElbowPlot(sc.combined, ndims = 25)
p2 <- ElbowPlot(sc.combined, ndims = 100)
p1 + p2
dev.off()


# =============================================================================
# 常规降维 + 聚类 + UMAP 展示
# =============================================================================

# 默认 Assay 设为 RNA（保持与原脚本一致）
# DefaultAssay(sc.combined) <- "RNA"

# sc.combined <- ScaleData(sc.combined, verbose = FALSE)
# sc.combined <- RunPCA(sc.combined, npcs = 30, verbose = FALSE)
# sc.combined <- RunUMAP(sc.combined, dims = 1:30)
# sc.combined <- FindNeighbors(sc.combined, dims = 1:30)
# sc.combined <- FindClusters(sc.combined, resolution = 0.5)

# p1 <- DimPlot(sc.combined, reduction = "umap", group.by = "replicate", pt.size = 0.1)
# p2 <- DimPlot(sc.combined, reduction = "umap", group.by = "group",     pt.size = 0.1)
# p3 <- DimPlot(sc.combined, reduction = "umap", label = TRUE, repel = TRUE, pt.size = 0.1)

# pdf("final_umap_plots.pdf", width = 16, height = 4)
# print((p1 + p2 + p3) + theme_paper)
# dev.off()

# png("final_umap_plots.png", width = 400, height = 100, units = "mm", res = 300)
# print((p1 + p2 + p3) + theme_paper)
# dev.off()

## 运行示例：
## Rscript split_integration_2level.r \
##   -s Tumor_1,Tumor_2,Normal_3,Normal_4 \
##   -l tumor,tumor,normal,normal \
##   -f expcsv,expcsv,expcsv,expcsv \
##   -b /path/Tumor1.csv,/path/Tumor2.csv,/path/Normal3.csv,/path/Normal4.csv \
##   --batchSize=2 --method=rpca \
##   --MinTotalUMI=500 --MinGenes=500 --MaxGenes=6000 --MaxMT=20 \
##   --ncpus=4
##
## 输出文件：
##  1) QC_violin_*.pdf/png: 每个样本 QC 图
##  2) final_umap_plots.pdf/png: 整合后 UMAP
##  3) cell_cluster_info.tsv: 细胞分组/聚类信息
##  4) final_integrated_obj.rds: 整合后的 Seurat 对象




# =============================================================================
# 参数记录功能
# =============================================================================

# 参数记录主函数
save_pipeline_parameters <- function(opt, outdir = ".", script_version = VERSION) {
  # 创建参数记录文件
  param_file <- file.path(outdir, "pipeline_parameters.txt")
  
  # 打开文件连接
  sink(param_file)
  
  # 写入参数头信息
  cat("单细胞预处理流程参数记录\n")
  cat("==============================\n")
  cat("分析时间:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n")
  cat("脚本版本:", script_version, "\n")
  cat("工作目录:", getwd(), "\n")
  cat("R版本:", R.version.string, "\n\n")
  
  # 基本计算参数
  cat("1. 计算资源参数\n")
  cat("---------------\n")
  cat("CPU核心数:", opt$ncpus, "\n")
  cat("最大内存(GB):", opt$MaxMemMega, "\n")
  cat("禁用并行计算:", opt$noparallel, "\n")
  
  # 输入文件参数
  cat("2. 输入文件参数\n")
  cat("---------------\n")
  cat("输入文件:", ifelse(length(opt$bdfiles) > 0, opt$bdfiles, "未指定"), "\n")
  cat("文件格式:", ifelse(length(opt$format) > 0, opt$format, "未指定"), "\n")
  cat("样本列表:", ifelse(length(opt$samplelist) > 0, opt$samplelist, "未指定"), "\n")
  cat("分组列表:", ifelse(length(opt$listname) > 0, opt$listname, "未指定"), "\n")
  cat("数据源类型:", opt$sourcetype, "\n")
  cat("批次大小:", opt$batchSize, "\n\n")
  
  # QC过滤参数
  cat("3. 质量控制参数\n")
  cat("---------------\n")
  cat("最小UMI数:", opt$MinTotalUMI, "\n")
  cat("最小基因数:", opt$MinGenes, "\n")
  cat("最大基因数:", opt$MaxGenes, "\n")
  cat("最大线粒体比例(%):", opt$MaxMT, "\n")
  cat("最大血红蛋白比例(%):", opt$MaxHB, "\n")
  cat("基因最小表达细胞数:", opt$MinCellsInGene, "\n\n")
  
  # 整合方法参数
  cat("4. 数据整合参数\n")
  cat("---------------\n")
  cat("整合方法:", opt$method, "\n")
  # cat("使用维度数:", ifelse(exists("dims"), dims, "未指定"), "\n")
  cat("批次大小:", opt$batchSize, "\n\n")
  
  # 双细胞检测参数
  cat("5. 双细胞检测参数\n")
  cat("---------------\n")
  cat("启用双细胞检测:", opt$doublet_enable, "\n")
  cat("PC范围:", opt$doublet_pc_min, "-", opt$doublet_pc_max, "\n")
  cat("聚类分辨率:", opt$doublet_resolution, "\n")
  cat("人工双细胞比例(pN):", opt$doublet_pn, "\n")
  cat("预期双细胞率:", opt$doublet_rate, "\n")
  cat("SCT模式:", opt$doublet_sct, "\n")
  cat("强制pK值:", ifelse(is.na(opt$doublet_force_pk), "自动选择", opt$doublet_force_pk), "\n")
  cat("复用pANN:", opt$doublet_reuse_pann, "\n")
  cat("保留策略:", opt$doublet_keep, "\n\n")
  
  # 关闭文件连接
  sink()
  
  # 同时在控制台输出信息
  flog.info("预处理流程参数已保存至: %s", param_file)
  
  return(param_file)
}

# 记录全局参数
global_param_file <- save_pipeline_parameters(opt, outdir = ".", script_version = VERSION)


## ------------------------------------------------------------
## 保存参数设置到文件：run_parameters.tsv
## ------------------------------------------------------------
writeLines(capture.output(sessionInfo()), "session_info.txt")

param_df <- data.frame(
  option = c("VERSION", "run_time", names(opt)),
  value  = c(
    VERSION,
    format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
    vapply(opt, function(x) paste(x, collapse = ","), character(1L))
  ),
  stringsAsFactors = FALSE
)

param_file <- file.path("run_parameters.tsv")
write.table(
  param_df,
  file      = param_file,
  sep       = "\t",
  quote     = FALSE,
  row.names = FALSE
)

message("[INFO] 参数设置已写入: ", param_file)
## ------------------------------------------------------------