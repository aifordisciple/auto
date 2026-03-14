#!/usr/bin/env Rscript

DOC <- "
从多种输入格式构建 Seurat v5 对象，完成单样本 QC/过滤/双细胞检测，
并按 Seurat v5 官方 Layers + IntegrateLayers 工作流完成整合（CCA/RPCA/Harmony，含 SCT 版本）。

功能要点
- 支持 10x 目录/10x h5/BD tsv/表达矩阵 tsv(csv)/count csv/rds/rdsraw 等输入
- 每样本：QC 指标 + QC 图(pdf+png) + 过滤 + 可选 DoubletFinder + gene_summary + dotplot
- 缓存：sc_list_qc.rds（可断点续跑）
- 整合：默认 Seurat v5 IntegrateLayers（v5_layers）；兼容 legacy_anchors 模式
- 输出：整合前对象 sc_preprocessing.rds；聚类结果与 UMAP 图；参数与 sessionInfo 记录

本版修订（仅做必要修复）
- 输入读入强制矩阵化+强制稀疏化+维度/命名检查，避免 as.sparse(numeric)
- future_lapply 增加 future.seed=TRUE，并在每样本 set.seed(seed+i)
- SCTransform vars.to.regress 修正为 percent_mt
- integrate_v5 的 merge/none 分支修复未定义 use_reduction
- GetAssayData(layer=...) 做 v4/v5 兼容封装
- FindNeighbors 默认加速：nn.method=annoy

用法示例：
Rscript seurat5_pipeline.r \
  --bdfiles /path/s1,/path/s2 \
  --samplelist S1,S2 \
  --listname Control,Treat \
  --dataset D1,D1 \
  --format 10x,10x \
  --method sct_harmony \
  --batch_var replicate \
  --ncpus 8 \
  --MaxMemMega 160 \
  --seed 12345
"

suppressPackageStartupMessages(library(optparse))
suppressPackageStartupMessages(library(futile.logger))
suppressPackageStartupMessages(library(Matrix))
suppressPackageStartupMessages(library(Seurat))
suppressPackageStartupMessages(library(ggplot2))
suppressPackageStartupMessages(library(patchwork))
suppressPackageStartupMessages(library(future))
suppressPackageStartupMessages(library(future.apply))
suppressPackageStartupMessages(library(DoubletFinder))

VERSION <- "5.0.0"

option_list <- list(
  # 计算资源
  make_option(c("-n", "--ncpus"),
    action  = "store", type = "integer", default = 24,
    help    = "parallel run number of cores"
  ),
  make_option(c("--MaxMemMega"),
    action  = "store", type = "double", default = 160,
    help    = "Parallel Max Memory size GB (compat: --MaxMemMega)"
  ),
  make_option(c("--noparallel"),
    action  = "store", type = "character", default = "false",
    help    = "no parallel (true|false)"
  ),
  make_option(c("--seed"),
    action  = "store", type = "integer", default = 12345,
    help    = "random seed for parallel-safe runs"
  ),

  # QC 阈值
  make_option(c("--MinTotalUMI"),
    action  = "store", type = "integer", default = 1000,
    help    = "minimal total UMI count (compat: --MinTotalUMI)"
  ),
  make_option(c("--MinGenes"),
    action  = "store", type = "integer", default = 500,
    help    = "minimal genes (compat: --MinGenes)"
  ),
  make_option(c("--MaxGenes"),
    action  = "store", type = "integer", default = 8000,
    help    = "max genes (compat: --MaxGenes)"
  ),
  make_option(c("--MaxMT"),
    action  = "store", type = "double", default = 15,
    help    = "maximal percentage of mitochondria (compat: --MaxMT)"
  ),
  make_option(c("--MaxHB"),
    action  = "store", type = "double", default = 10,
    help    = "maximal percentage of HB (compat: --MaxHB)"
  ),
  make_option(c("--MinCellsInGene"),
    action  = "store", type = "integer", default = 5,
    help    = "minimal cells with UMI>0 in one gene (compat: --MinCellsInGene)"
  ),

  # 样本输入
  make_option(c("-s", "--samplelist"),
    action  = "store", type = "character", default = "",
    help    = "samplename1,samplename2,samplename3"
  ),
  make_option(c("-l", "--listname"),
    action  = "store", type = "character", default = "",
    help    = "listname1,listname2,listname3"
  ),
  make_option(c("-a", "--dataset"),
    action  = "store", type = "character", default = "D1",
    help    = "dataset label for each sample, e.g. D1,D1,D2"
  ),
  make_option(c("-b", "--bdfiles"),
    action  = "store", type = "character",
    help    = "The count matrix file of sample"
  ),
  make_option(c("-f", "--format"),
    action  = "store", type = "character", default = "10x",
    help    = "The count matrix file format, 10x or BD or h5 or rds"
  ),
  make_option(c("-t", "--sourcetype"),
    action  = "store", type = "character", default = "raw",
    help    = "raw or subcell"
  ),

  # 旧版分批整合参数：保留兼容
  make_option(c("--batchSize"),
    action  = "store", type = "integer", default = 10,
    help    = "分批整合时，每批的样本数目(默认10) (legacy_anchors 兼容)"
  ),

  # 整合方法
  make_option(c("-m", "--method"),
    action  = "store", type = "character", default = "cca",
    help    = "cca or rpca or sct_cca or sct_rpca or harmony or sct_harmony or none"
  ),

  # v5 新增：整合引擎与 batch 变量
  make_option(c("--integration_engine"),
    action  = "store", type = "character", default = "v5_layers",
    help    = "v5_layers|legacy_anchors"
  ),
  make_option(c("--integration_feature_num"),
    action  = "store", type = "integer", default = 3000,
    help    = "integration_feature_num, default 3000"
  ),
  make_option(c("--batch_var"),
    action  = "store", type = "character", default = "replicate",
    help    = "用于 split layers / batch correction 的 meta 列名（默认 replicate）"
  ),
  make_option(c("--join_layers_after_integration"),
    action  = "store", type = "character", default = "true",
    help    = "true|false 整合后是否 JoinLayers"
  ),

  # v5 新增：降维与聚类参数
  make_option(c("--dims_use"),
    action  = "store", type = "integer", default = 30,
    help    = "dims used in neighbors/umap, default 30"
  ),
  make_option(c("--npcs"),
    action  = "store", type = "integer", default = 50,
    help    = "PCA npcs, default 50"
  ),
  make_option(c("--cluster_resolution"),
    action  = "store", type = "double", default = 0.5,
    help    = "FindClusters resolution, default 0.5"
  ),

  # v5 新增：输出前缀
  make_option(c("--out_prefix"),
    action  = "store", type = "character", default = "sc_preprocessing",
    help    = "output prefix, default sc_preprocessing"
  ),

  # patterns
  make_option(c("--mt_pattern"),
    action  = "store", type = "character",
    default = "^ATP6$|^ATP8$|^COX1$|^COX2$|^COX3$|^CYTB$|^mt-Rnr1$|^mt-Rnr2$|^ND1$|^ND2$|^ND3$|^ND4$|^ND4L$|^ND5$|^ND6$|^Trna$|^Trnc$|^Trnd$|^Trne$|^Trnf$|^Trng$|^Trnh$|^Trni$|^Trnk$|^Trnl1$|^Trnl2$|^Trnm$|^Trnn$|^Trnp$|^Trnq$|^Trnr$|^Trns1$|^Trns2$|^Trnt$|^Trnv$|^Trnw$|^Trny$|^MT-|^mt-|^ATMG0",
    help    = "pattern for mitochondria genes"
  ),
  make_option(c("--ribo_pattern"),
    action  = "store", type = "character", default = "^RP[SL]|^Rp[sl]",
    help    = "pattern for ribosomal genes"
  ),
  make_option(c("--hb_pattern"),
    action  = "store", type = "character", default = "^HB[^(P)]|^Hb[^(p)]",
    help    = "pattern for hemoglobin genes"
  ),
  make_option(c("--plat_pattern"),
    action  = "store", type = "character", default = "^PECAM1$|^PF4$|^Pecam1$|^Pf4$",
    help    = "pattern for platelet/endo marker genes"
  ),

  # DoubletFinder
  make_option(c("--doublet_enable"),
    action  = "store", type = "character", default = "true",
    help    = "true|false 是否启用 DoubletFinder"
  ),
  make_option(c("--doublet_pc_min"),
    action  = "store", type = "integer", default = 1,
    help    = "用于DF的PC起始(含)"
  ),
  make_option(c("--doublet_pc_max"),
    action  = "store", type = "integer", default = 15,
    help    = "用于DF的PC结束(含)"
  ),
  make_option(c("--doublet_resolution"),
    action  = "store", type = "double", default = 0.3,
    help    = "用于FindClusters的分辨率"
  ),
  make_option(c("--doublet_pn"),
    action  = "store", type = "double", default = 0.25,
    help    = "pN 人工双细胞比例（官方常用0.25）"
  ),
  make_option(c("--doublet_rate"),
    action  = "store", type = "double", default = 0.039,
    help    = "预期双细胞率（约5000细胞≈0.039，可按平台调整）"
  ),
  make_option(c("--doublet_sct"),
    action  = "store", type = "character", default = "auto",
    help    = "auto|true|false 是否按SCT工作流（auto会检测是否存在SCT Assay）"
  ),
  make_option(c("--doublet_force_pk"),
    action  = "store", type = "double", default = NA,
    help    = "可选：强制指定pK；缺省则自动选择BCmvn最大值"
  ),
  make_option(c("--doublet_reuse_pann"),
    action  = "store", type = "character", default = "false",
    help    = "true|false 是否复用已有pANN列（若存在）"
  ),
  make_option(c("--doublet_keep"),
    action  = "store", type = "character", default = "singlet",
    help    = "singlet|all 输出时仅保留Singlet或保留全部并打标"
  )
)

opt <- parse_args(OptionParser(option_list = option_list))

if (length(commandArgs(trailingOnly = TRUE)) == 1 &&
    (commandArgs(trailingOnly = TRUE)[1] %in% c("-v", "--version"))) {
  message("Version:\n\t", VERSION, "\n")
  quit(status = 0)
}

# ---- logs ----
if (!dir.exists("logs")) dir.create("logs", recursive = TRUE)
cur_date <- as.character(Sys.Date())
errorLog <- file.path("logs", paste0("ERROR_", cur_date, ".log"))
warnLog  <- file.path("logs", paste0("WARN_",  cur_date, ".log"))
infoLog  <- file.path("logs", paste0("INFO_",  cur_date, ".log"))
traceLog <- file.path("logs", paste0("TRACE_", cur_date, ".log"))

invisible(flog.logger("error", ERROR, appender.file(errorLog)))
invisible(flog.logger("warn",  WARN,  appender.file(warnLog)))
invisible(flog.logger("info",  INFO,  appender.file(infoLog)))
invisible(flog.logger("trace", TRACE, appender.file(traceLog)))
invisible(flog.appender(appender.console(), name = "ROOT"))

logi <- function(...) { flog.info(..., name = "ROOT"); flog.info(..., name = "info") }
logw <- function(...) { flog.warn(..., name = "ROOT"); flog.warn(..., name = "warn") }
loge <- function(...) { flog.error(..., name = "ROOT"); flog.error(..., name = "error") }

# ---- parallel ----
options(future.globals.maxSize = opt$MaxMemMega * 1024^3)
worker_n <- min(opt$ncpus, 16L)
if (tolower(opt$noparallel) == "false" && worker_n > 1L) {
  plan(multisession, workers = worker_n)
} else {
  plan(sequential)
}

# ---- helpers ----
as_sparse <- function(x, sid = NA_character_, path = NA_character_) {
  # 1) list -> 取第一个
  if (is.list(x) && !inherits(x, "dgCMatrix")) {
    if ("Gene Expression" %in% names(x)) x <- x[["Gene Expression"]]
    else x <- x[[1]]
  }

  # 2) numeric 向量 -> 强制变成 2D 矩阵（否则会触发 as.sparse(numeric)）
  if (is.atomic(x) && is.numeric(x) && is.null(dim(x))) {
    x <- matrix(x, ncol = 1)
  }

  # 3) data.frame -> matrix
  if (is.data.frame(x)) x <- as.matrix(x)

  # 4) 必须是二维
  if (is.null(dim(x)) || length(dim(x)) != 2) {
    stop(sprintf("[as_sparse] input is not 2D. sample=%s file=%s class=%s dim=%s",
                 sid, path, paste(class(x), collapse = ","),
                 paste(dim(x), collapse = "x")))
  }

  # 5) 必须是 numeric（字符会导致 Matrix 失败）
  if (!is.numeric(x) && !inherits(x, "Matrix")) {
    stop(sprintf("[as_sparse] input is not numeric/matrix. sample=%s file=%s class=%s",
                 sid, path, paste(class(x), collapse = ",")))
  }

  # 6) 确保 row/colnames（缺失会导致后面建 Seurat 不稳定）
  if (is.null(rownames(x))) rownames(x) <- paste0("gene_", seq_len(nrow(x)))
  if (is.null(colnames(x))) colnames(x) <- paste0("cell_", seq_len(ncol(x)))

  # 7) 强制稀疏化（用 Matrix::Matrix，比 as()/as.sparse 更稳）
  if (inherits(x, "dgCMatrix")) return(x)
  Matrix::Matrix(x, sparse = TRUE)
}


get_counts <- function(obj, assay = "RNA") {
  tryCatch(
    GetAssayData(obj, assay = assay, layer = "counts"),
    error = function(e) GetAssayData(obj, assay = assay, slot = "counts")
  )
}

get_data <- function(obj, assay = "RNA") {
  tryCatch(
    GetAssayData(obj, assay = assay, layer = "data"),
    error = function(e) GetAssayData(obj, assay = assay, slot = "data")
  )
}

read_counts <- function(path, fmt) {
  if (fmt == "10x") {
    return(Read10X(data.dir = path))
  }
  if (fmt == "h5") {
    a <- Read10X_h5(path)
    return(a)
  }
  if (fmt == "BD") {
    m <- read.table(path, header = TRUE, sep = "\t", quote = "", check.names = FALSE, row.names = 1)
    return(t(m))
  }
  if (fmt == "exp") {
    m <- read.table(path, header = TRUE, sep = "\t", quote = "", check.names = FALSE, row.names = 1)
    return(as.matrix(m))
  }

  if (fmt == "expcsv") {
    m <- read.csv(path, header = TRUE, check.names = FALSE, row.names = 1)
    return(as.matrix(m))
  }
  if (fmt == "countcsv") {
    m <- read.csv(path, header = TRUE, check.names = FALSE, row.names = 1)
    return(as.matrix(m))
  }
  if (fmt == "csv") {
    m <- read.table(path, header = TRUE, sep = ",", quote = "", check.names = FALSE, row.names = 1)
    return(t(m))
  }
  stop("Unsupported format: ", fmt)
}

save_plot <- function(p, pdf_file, png_file, w, h) {
  ggsave(pdf_file, p, width = w, height = h, units = "in", limitsize = FALSE)
  ggsave(png_file, p, width = w, height = h, units = "in", dpi = 300, limitsize = FALSE)
}

add_qc_metrics <- function(obj) {
  obj[["percent_mt"]]   <- PercentageFeatureSet(obj, pattern = opt$mt_pattern)
  obj[["percent_ribo"]] <- PercentageFeatureSet(obj, pattern = opt$ribo_pattern)
  obj[["percent_hb"]]   <- PercentageFeatureSet(obj, pattern = opt$hb_pattern)
  obj[["percent_plat"]] <- PercentageFeatureSet(obj, pattern = opt$plat_pattern)
  obj
}

run_doubletfinder_one <- function(obj, sample_id) {
  if (tolower(opt$doublet_enable) != "true") return(obj)

  sct_flag <- if (tolower(opt$doublet_sct) == "auto") {
    "SCT" %in% Assays(obj)
  } else {
    tolower(opt$doublet_sct) == "true"
  }
  DefaultAssay(obj) <- if (sct_flag) "SCT" else "RNA"

  pc.num <- opt$doublet_pc_min:opt$doublet_pc_max

  if (DefaultAssay(obj) == "RNA") {
    obj <- ScaleData(obj, vars.to.regress = c("nFeature_RNA", "percent_mt"), verbose = FALSE)
  }
  if (!"pca" %in% names(obj@reductions)) {
    obj <- RunPCA(obj, npcs = max(opt$doublet_pc_max, 20), verbose = FALSE)
  }
  if (!"umap" %in% names(obj@reductions)) {
    obj <- RunUMAP(obj, dims = pc.num, verbose = FALSE)
  }
  obj <- FindNeighbors(obj, dims = pc.num, nn.method = "annoy", verbose = FALSE)
  obj <- FindClusters(obj, resolution = opt$doublet_resolution, verbose = FALSE)

  has_v3 <- "paramSweep_v3" %in% getNamespaceExports("DoubletFinder")
  sweep.res.list <- if (has_v3) {
    DoubletFinder::paramSweep_v3(obj, PCs = pc.num, sct = sct_flag)
  } else {
    DoubletFinder::paramSweep(obj, PCs = pc.num, sct = sct_flag)
  }
  sweep.stats <- DoubletFinder::summarizeSweep(sweep.res.list, GT = FALSE)
  bcmvn <- DoubletFinder::find.pK(sweep.stats)

  pK_bcmvn <- if (is.na(opt$doublet_force_pk)) {
    as.numeric(as.character(bcmvn$pK[which.max(bcmvn$BCmetric)]))
  } else {
    opt$doublet_force_pk
  }

  nExp_poi <- round(opt$doublet_rate * ncol(obj))
  homotypic.pr <- DoubletFinder::modelHomotypic(obj$seurat_clusters)
  nExp_poi.adj <- round(nExp_poi * (1 - homotypic.pr))

  reuse_col <- NULL
  if (tolower(opt$doublet_reuse_pann) == "true") {
    pcols <- grep("^pANN", colnames(obj@meta.data), value = TRUE)
    if (length(pcols) > 0) reuse_col <- pcols[1]
  }

  df_fun <- if (has_v3) DoubletFinder::doubletFinder_v3 else DoubletFinder::doubletFinder
  obj <- df_fun(obj, PCs = pc.num, pN = opt$doublet_pn, pK = pK_bcmvn,
                nExp = nExp_poi.adj, reuse.pANN = reuse_col, sct = sct_flag)

  DF.name <- grep("^DF.classifications", colnames(obj@meta.data), value = TRUE)
  if (length(DF.name) >= 1) {
    DF.name <- DF.name[1]
    p.umap <- DimPlot(obj, reduction = "umap", group.by = DF.name, pt.size = 0.1)
    save_plot(p.umap,
              paste0("DimPlot_doublet_", sample_id, ".pdf"),
              paste0("DimPlot_doublet_", sample_id, ".png"),
              5, 4)

    if (tolower(opt$doublet_keep) == "singlet") {
      obj <- obj[, obj@meta.data[[DF.name]] == "Singlet"]
    }
  } else {
    logw("[DF] %s 未找到 DF.classifications 列，跳过过滤。", sample_id)
  }
  obj
}

gene_summary_outputs <- function(obj, sample_id) {
  DefaultAssay(obj) <- "RNA"

  counts_mat <- get_counts(obj, assay = "RNA")
  data_mat   <- get_data(obj, assay = "RNA")

  nnz_cells <- Matrix::rowSums(counts_mat > 0)
  pct_cells <- as.numeric(nnz_cells) / ncol(counts_mat) * 100
  sum_data  <- Matrix::rowSums(data_mat)
  mean_all  <- as.numeric(sum_data) / ncol(data_mat)
  mean_nz   <- ifelse(nnz_cells > 0, as.numeric(sum_data) / nnz_cells, 0)

  gene_tbl <- data.frame(
    gene = rownames(data_mat),
    mean_expr_nonzero = mean_nz,
    mean_expr_all = mean_all,
    pct_cells = pct_cells,
    n_cells_express = as.integer(nnz_cells),
    stringsAsFactors = FALSE
  )
  gene_tbl <- gene_tbl[order(gene_tbl$mean_expr_all, decreasing = TRUE), ]

  write.table(gene_tbl,
              file = paste0("gene_summary_", sample_id, ".tsv"),
              sep = "\t", quote = FALSE, row.names = FALSE)

  topN <- min(30L, nrow(gene_tbl))
  top_tbl <- gene_tbl[seq_len(topN), , drop = FALSE]
  write.table(top_tbl,
              file = paste0("top", topN, "_gene_summary_", sample_id, ".tsv"),
              sep = "\t", quote = FALSE, row.names = FALSE)

  df_dot <- transform(top_tbl, sample = sample_id)
  df_dot$gene <- factor(df_dot$gene, levels = rev(top_tbl$gene))

  p_dot <- ggplot(df_dot, aes(x = sample, y = gene)) +
    geom_point(aes(size = pct_cells, color = mean_expr_all)) +
    labs(title = paste0("Top ", topN, " genes per sample (DotPlot)"),
         subtitle = paste0("sample: ", sample_id),
         x = NULL, y = NULL)

  save_plot(p_dot,
            paste0("dotplot_top", topN, "_", sample_id, ".pdf"),
            paste0("dotplot_top", topN, "_", sample_id, ".png"),
            4.5, 6.5)
}

diet_slim <- function(obj) {
  keep_assays <- intersect(c("RNA", "SCT"), Assays(obj))
  DietSeurat(obj,
             assays = keep_assays,
             counts = TRUE,
             data = TRUE,
             scale.data = FALSE,
             dimreducs = NULL,
             graphs = NULL)
}

write_discard_stat <- function(
  sample_id,
  qc_total,
  qc_lib,
  qc_nexprs_low,
  qc_mito,
  qc_hb,
  qc_keep_only,
  df_pred,
  df_sing,
  df_rate,
  keep_genes_n,
  discard_genes_n,
  min_total_umi,
  min_genes,
  max_mt,
  max_hb,
  min_cells_in_gene
) {
  keep_final <- if (tolower(opt$doublet_keep) == "singlet") {
    max(0L, qc_keep_only - df_pred)
  } else {
    qc_keep_only
  }

  total_filtered_final <- qc_total - keep_final

  dis <- data.frame(
    Raw            = qc_total,
    LibSize        = qc_lib,
    NExprsLow      = qc_nexprs_low,
    MitoProp       = qc_mito,
    HbProp         = qc_hb,
    DF_PredDoublet = df_pred,
    DF_PredRate    = df_rate,
    Total          = total_filtered_final,
    Keep           = keep_final,
    ExpressGenes   = discard_genes_n,
    KeepGenes      = keep_genes_n,
    stringsAsFactors = FALSE
  )

  header_line <- paste(
    "原始细胞数",
    paste0("按比对总量过滤(<", min_total_umi, ")"),
    paste0("按最低检出基因数过滤(<", min_genes, ")"),
    paste0("按线粒体比例过滤(>", max_mt, "%)"),
    paste0("按红细胞比例过滤(>", max_hb, "%)"),
    "预测双细胞数(DF)",
    "预测双细胞率(DF)",
    "总过滤细胞数(含双细胞)",
    "QC后保留细胞数(去双细胞后)",
    paste0("筛选掉少数细胞表达的基因(<", min_cells_in_gene, ")"),
    "最终保留的基因数",
    sep = "\t"
  )

  out_file <- paste0(sample_id, "_discard_stat.xls")
  cat(header_line, "\n", file = out_file)
  write.table(
    dis,
    file = out_file,
    append = TRUE,
    quote = FALSE,
    sep = "\t",
    row.names = FALSE,
    col.names = FALSE
  )
}

# ---- per-sample pipeline ----
cell_filter_one <- function(i, countfiles, samplenames, listnames, formats, datasets) {
  set.seed(opt$seed + as.integer(i))

  sid <- samplenames[i]
  fmt <- formats[i]

  logi("Processing sample: %s (%d/%d) | format=%s", sid, i, length(samplenames), fmt)

  if (fmt %in% c("rds", "sctrds", "rdsraw")) {
    obj <- readRDS(countfiles[i])

    if (fmt == "rdsraw") {
      DefaultAssay(obj) <- "RNA"
      if (!is.null(obj[["RNA"]]) && length(Layers(obj[["RNA"]])) > 1) {
        obj[["RNA"]] <- JoinLayers(obj[["RNA"]])
      }
      counts <- obj[["RNA"]]$counts
      # counts <- as_sparse(counts, sid)
      obj <- CreateSeuratObject(counts = counts, min.cells = 1, min.features = 1)
      rm(counts); gc()
    }
    if (fmt == "rds") {
      DefaultAssay(obj) <- "RNA"
      obj <- FindVariableFeatures(obj, selection.method = "vst", nfeatures = 2000)
      return(obj)
    }

    if (fmt == "sctrds") {
      DefaultAssay(obj) <- "RNA"
      obj <- FindVariableFeatures(obj, selection.method = "vst", nfeatures = 2000)
      obj <- SCTransform(obj, method = "glmGamPoi",
                         vars.to.regress = "percent_mt", verbose = FALSE)
      return(obj)
    }

  } else if (fmt == "seuratobj") {
    obj <- countfiles[i]
    DefaultAssay(obj) <- "RNA"
  } else {
    m <- read_counts(countfiles[i], fmt)
    if (is.list(m)) {
      if ("Gene Expression" %in% names(m)) m <- m[["Gene Expression"]]
      else m <- m[[1]]
    }
    # m <- as_sparse(m, sid = sid, path = countfiles[i])

    colnames(m) <- paste0(sid, "_", colnames(m))
    obj <- CreateSeuratObject(counts = m, project = "sc", min.cells = 1, min.features = 1)
    rm(m); gc()
  }

  obj[["group"]] <- listnames[i]
  obj[["replicate"]] <- sid
  obj[["dataset"]] <- datasets[i]

  obj <- add_qc_metrics(obj)

  # QC plots
  p_vln <- VlnPlot(obj,
                   features = c("nFeature_RNA", "nCount_RNA", "percent_mt", "percent_ribo", "percent_hb"),
                   ncol = 5, pt.size = 0.1)
  save_plot(p_vln,
            paste0("QC_all_", sid, ".pdf"),
            paste0("QC_all_", sid, ".png"),
            16, 4)

  p1 <- FeatureScatter(obj, feature1 = "nCount_RNA", feature2 = "percent_mt", pt.size = 0.1)
  p2 <- FeatureScatter(obj, feature1 = "nCount_RNA", feature2 = "nFeature_RNA", pt.size = 0.1)
  p3 <- FeatureScatter(obj, feature1 = "percent_mt", feature2 = "nFeature_RNA", pt.size = 0.1)
  save_plot(p1 + p2 + p3,
            paste0("QC_FeatureScatter_", sid, ".pdf"),
            paste0("QC_FeatureScatter_", sid, ".png"),
            12, 4)

  # ---- QC flags ----
  qc_total_flag      <- obj$nCount_RNA > 0
  qc_lib_flag        <- (obj$nCount_RNA < opt$MinTotalUMI & obj$nCount_RNA > 0)
  qc_nexprs_low_flag <- (obj$nFeature_RNA < opt$MinGenes  & obj$nCount_RNA > 0)
  qc_mito_flag       <- (obj$percent_mt   > opt$MaxMT      & obj$nCount_RNA > 0)
  qc_hb_flag         <- (obj$percent_hb   > opt$MaxHB      & obj$nCount_RNA > 0)

  # ---- gene filtering stats ----
  counts0 <- get_counts(obj, assay = "RNA")
  nnz0 <- Matrix::rowSums(counts0 > 0)
  keep_genes_vec <- nnz0 >= opt$MinCellsInGene
  discard_genes_vec <- nnz0 < opt$MinCellsInGene
  keep_genes_n <- sum(keep_genes_vec)
  discard_genes_n <- sum(discard_genes_vec)

  obj <- subset(obj, features = rownames(obj)[keep_genes_vec])
  rm(counts0, nnz0); gc()

  # ---- cell QC filter ----
  obj <- subset(
    obj,
    subset =
      nFeature_RNA >= opt$MinGenes &
      nCount_RNA   >= opt$MinTotalUMI &
      nFeature_RNA <= opt$MaxGenes &
      percent_mt   <= opt$MaxMT &
      percent_hb   <= opt$MaxHB
  )

  qc_keep_only <- ncol(obj)

  # normalize + HVG (RNA)
  obj <- NormalizeData(obj, verbose = FALSE)
  obj <- FindVariableFeatures(obj, selection.method = "vst", nfeatures = 2000, verbose = FALSE)

  top10 <- head(VariableFeatures(obj), 10)
  p_hvg <- LabelPoints(plot = VariableFeaturePlot(obj), points = top10, repel = TRUE)
  save_plot(p_hvg,
            paste0("QC_hvg_", sid, ".pdf"),
            paste0("QC_hvg_", sid, ".png"),
            6, 4)

  # SCT (optional, per-sample)
  if (opt$method %in% c("sct_cca", "sct_rpca", "sct_harmony") && fmt != "sctrds") {
    obj <- SCTransform(obj, method = "glmGamPoi", vars.to.regress = "percent_mt", verbose = FALSE)
  }

  # ---- DoubletFinder ----
  obj <- run_doubletfinder_one(obj, sid)

  # ---- DF stats ----
  df_pred <- 0L
  df_sing <- qc_keep_only
  df_rate <- NA_real_

  df_col <- grep("^DF.classifications", colnames(obj@meta.data), value = TRUE)
  if (length(df_col) >= 1) {
    tab_df <- table(obj@meta.data[[df_col[1]]])
    df_pred <- if ("Doublet" %in% names(tab_df)) as.integer(tab_df[["Doublet"]]) else 0L
    df_sing <- if ("Singlet" %in% names(tab_df)) as.integer(tab_df[["Singlet"]]) else as.integer(ncol(obj))
  }

  den <- df_pred + df_sing
  df_rate <- if (den > 0) df_pred / den else NA_real_

  write_discard_stat(
    sample_id = sid,
    qc_total  = sum(qc_total_flag),
    qc_lib    = sum(qc_lib_flag),
    qc_nexprs_low = sum(qc_nexprs_low_flag),
    qc_mito   = sum(qc_mito_flag),
    qc_hb     = sum(qc_hb_flag),
    qc_keep_only = qc_keep_only,
    df_pred   = df_pred,
    df_sing   = df_sing,
    df_rate   = df_rate,
    keep_genes_n = keep_genes_n,
    discard_genes_n = discard_genes_n,
    min_total_umi = opt$MinTotalUMI,
    min_genes = opt$MinGenes,
    max_mt = opt$MaxMT,
    max_hb = opt$MaxHB,
    min_cells_in_gene = opt$MinCellsInGene
  )

  gene_summary_outputs(obj, sid)

  obj <- diet_slim(obj)
  gc()
  obj
}

# ---- parse input ----
countfiles  <- strsplit(opt$bdfiles, ",")[[1]]
samplenames <- strsplit(opt$samplelist, ",")[[1]]
listnames   <- strsplit(opt$listname, ",")[[1]]
formats     <- strsplit(opt$format, ",")[[1]]
datasets    <- strsplit(opt$dataset, ",")[[1]]

groupnum <- length(unique(listnames))

if (length(datasets) == 1 && length(samplenames) > 1) {
  datasets <- rep(datasets, length(samplenames))
}

stopifnot(length(countfiles) == length(samplenames))
stopifnot(length(listnames) == length(samplenames))
stopifnot(length(formats) == length(samplenames))
stopifnot(length(datasets) == length(samplenames))

# ---- build sc.list ----
if (file.exists("sc_list_qc.rds")) {
  sc.list <- readRDS("sc_list_qc.rds")
  logi("Loaded cached sc_list_qc.rds | n=%d", length(sc.list))
} else {
  if (opt$sourcetype == "raw") {
    sc.list <- future_lapply(
      seq_along(countfiles),
      cell_filter_one,
      countfiles = countfiles,
      samplenames = samplenames,
      listnames = listnames,
      formats = formats,
      datasets = datasets,
      future.seed = TRUE
    )
    names(sc.list) <- samplenames
  } else {
    subcells <- readRDS(countfiles[1])
    sc.list <- SplitObject(subcells, split.by = opt$sourcetype)
  }

  keep_idx <- sapply(sc.list, ncol) >= 30
  if (any(!keep_idx)) {
    logw("Removed samples with <30 cells: %s", paste(names(sc.list)[!keep_idx], collapse = ","))
  }
  sc.list <- sc.list[keep_idx]

  saveRDS(sc.list, file = "sc_list_qc.rds", compress = FALSE)
  logi("Saved sc_list_qc.rds | n=%d", length(sc.list))
}

plan(sequential)

# ---- merge into one object ----
merge_all <- function(lst) {
  if (length(lst) == 1) return(lst[[1]])
  merge(x = lst[[1]], y = lst[-1], merge.data = TRUE)
}

sc <- merge_all(sc.list)
rm(sc.list)
gc()

# ---- ensure batch_var exists ----
if (!opt$batch_var %in% colnames(sc@meta.data)) {
  stop("batch_var not found in meta.data: ", opt$batch_var)
}

# ---- layer utils ----
safe_join_layers <- function(obj, assay = "RNA") {
  if (!assay %in% Assays(obj)) return(obj)
  if (length(Layers(obj[[assay]])) > 1) {
    obj[[assay]] <- JoinLayers(obj[[assay]])
  }
  obj
}

safe_split_layers <- function(obj, assay = "RNA", f) {
  obj <- safe_join_layers(obj, assay = assay)
  obj[[assay]] <- split(obj[[assay]], f = f)
  obj
}

join_after <- tolower(opt$join_layers_after_integration) == "true"

# ---- integration (v5) ----
integrate_v5 <- function(obj, method) {
  obj <- safe_split_layers(obj, assay = "RNA", f = obj[[opt$batch_var]][, 1])

  use_sct <- method %in% c("sct_cca", "sct_rpca", "sct_harmony")

  if (use_sct) {
    obj <- SCTransform(obj, method = "glmGamPoi", vars.to.regress = "percent_mt", verbose = FALSE)
    obj <- RunPCA(obj, npcs = opt$npcs, verbose = FALSE)

    if (method == "sct_harmony") {
      obj <- IntegrateLayers(object = obj, method = HarmonyIntegration,
                             orig.reduction = "pca", new.reduction = "harmony",
                             assay = "SCT", verbose = FALSE)
      red <- "harmony"
    } else if (method == "sct_cca") {
      obj <- IntegrateLayers(object = obj, method = CCAIntegration,
                             orig.reduction = "pca", new.reduction = "integrated.cca",
                             assay = "SCT", verbose = FALSE)
      red <- "integrated.cca"
    } else {
      obj <- IntegrateLayers(object = obj, method = RPCAIntegration,
                             orig.reduction = "pca", new.reduction = "integrated.rpca",
                             assay = "SCT", verbose = FALSE)
      red <- "integrated.rpca"
    }
  } else if (method %in% c("cca", "rpca", "harmony", "merge", "none")) {
    obj <- NormalizeData(obj, verbose = FALSE)
    obj <- FindVariableFeatures(obj, verbose = FALSE)
    obj <- ScaleData(obj, verbose = FALSE)
    obj <- RunPCA(obj, npcs = opt$npcs, verbose = FALSE)

    if (method == "harmony") {
      obj <- IntegrateLayers(object = obj, method = HarmonyIntegration,
                             orig.reduction = "pca", new.reduction = "harmony",
                             verbose = FALSE)
      red <- "harmony"
    } else if (method == "cca") {
      obj <- IntegrateLayers(object = obj, method = CCAIntegration,
                             orig.reduction = "pca", new.reduction = "integrated.cca",
                             verbose = FALSE)
      red <- "integrated.cca"
    } else if (method == "rpca") {
      obj <- IntegrateLayers(object = obj, method = RPCAIntegration,
                             orig.reduction = "pca", new.reduction = "integrated.rpca",
                             verbose = FALSE)
      red <- "integrated.rpca"
    } else {
      red <- "pca"
      if (join_after) {
        obj <- safe_join_layers(obj, assay = "RNA")
      }
      dims <- seq_len(opt$dims_use)
      obj <- FindNeighbors(obj, reduction = red, dims = dims, nn.method = "annoy", verbose = FALSE)
      obj <- FindClusters(obj, resolution = opt$cluster_resolution, verbose = FALSE)
      obj <- RunUMAP(obj, reduction = red, dims = dims, verbose = FALSE)

      p_rep <- DimPlot(obj, group.by = "replicate", pt.size = 0.1)
      p_grp <- DimPlot(obj, group.by = "group", pt.size = 0.1)
      p_cls <- DimPlot(obj, label = TRUE, repel = TRUE, pt.size = 0.1)

      save_plot(p_rep + p_grp + p_cls,
                paste0("final_umap_", opt$method, ".pdf"),
                paste0("final_umap_", opt$method, ".png"),
                12, 4)
    }
  } else {
    stop("Unsupported method: ", method)
  }

  if (join_after) {
    obj <- safe_join_layers(obj, assay = "RNA")
  }
  list(obj = obj, reduction = red)
}

# ---- integration (legacy anchors, optional) ----
integrate_legacy <- function(obj, method) {
  lst <- SplitObject(obj, split.by = opt$batch_var)

  if (method %in% c("sct_cca", "sct_rpca")) {
    lst <- lapply(lst, function(x) SCTransform(x, method = "glmGamPoi", vars.to.regress = "percent_mt", verbose = FALSE))
    features <- SelectIntegrationFeatures(object.list = lst, nfeatures = opt$integration_feature_num)
    lst <- PrepSCTIntegration(object.list = lst, anchor.features = features)

    if (method == "sct_rpca") {
      lst <- lapply(lst, function(x) RunPCA(x, features = features, verbose = FALSE))
      anchors <- FindIntegrationAnchors(object.list = lst, normalization.method = "SCT",
                                       anchor.features = features, reduction = "rpca", dims = 1:opt$dims_use)
    } else {
      anchors <- FindIntegrationAnchors(object.list = lst, normalization.method = "SCT",
                                       anchor.features = features)
    }
    obj2 <- IntegrateData(anchorset = anchors, normalization.method = "SCT")
    DefaultAssay(obj2) <- "SCT"
    obj2 <- RunPCA(obj2, npcs = opt$npcs, verbose = FALSE)
    list(obj = obj2, reduction = "pca")
  } else {
    lst <- lapply(lst, function(x) {
      x <- NormalizeData(x, verbose = FALSE)
      x <- FindVariableFeatures(x, verbose = FALSE)
      x
    })
    features <- SelectIntegrationFeatures(object.list = lst, nfeatures = opt$integration_feature_num)

    if (method == "rpca") {
      lst <- lapply(lst, function(x) {
        x <- ScaleData(x, features = features, verbose = FALSE)
        x <- RunPCA(x, features = features, verbose = FALSE)
        x
      })
      anchors <- FindIntegrationAnchors(object.list = lst, anchor.features = features, reduction = "rpca")
    } else {
      anchors <- FindIntegrationAnchors(object.list = lst, anchor.features = features)
    }
    obj2 <- IntegrateData(anchorset = anchors)
    DefaultAssay(obj2) <- "integrated"
    obj2 <- ScaleData(obj2, verbose = FALSE)
    obj2 <- RunPCA(obj2, npcs = opt$npcs, verbose = FALSE)
    list(obj = obj2, reduction = "pca")
  }
}

logi("Integration engine=%s | method=%s | batch_var=%s",
     opt$integration_engine, opt$method, opt$batch_var)

res <- if (opt$integration_engine == "v5_layers") {
  integrate_v5(sc, opt$method)
} else {
  integrate_legacy(sc, opt$method)
}
sc <- res$obj
use_reduction <- res$reduction
rm(res)
gc()

# ---- save ----
saveRDS(sc, file = paste0(opt$out_prefix, ".rds"), compress = FALSE)
writeLines(capture.output(sessionInfo()), "session_info.txt")

file_name <- "sc_list_qc.rds"
if (file.exists(file_name)) {
  file.remove(file_name)
  print(paste(file_name, "has been deleted."))
} else {
  print("File not found.")
}

param_df <- data.frame(
  option = c("VERSION", "run_time", names(opt)),
  value = c(VERSION, format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
            vapply(opt, function(x) paste(x, collapse = ","), character(1L))),
  stringsAsFactors = FALSE
)
write.table(param_df, file = "run_parameters.tsv", sep = "\t", quote = FALSE, row.names = FALSE)

# ---- PCA 可视化 ----
p1 <- VizDimLoadings(sc, dims = 1:2, reduction = "pca")
pdf(file = paste("VizPlot_PCA", ".pdf", sep = ""), width = 8, height = 5)
p1; dev.off()

png(file = paste("VizPlot_PCA", ".png", sep = ""),
    width = 200, height = 125, units = "mm", res = 300, pointsize = 1.5)
par(mar = c(5, 5, 2, 2), cex.axis = 1.5, cex.lab = 2)
p1; dev.off()

p1 <- DimPlot(sc, reduction = "pca",
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
DimHeatmap(sc, dims = 1:9, cells = 500, balanced = TRUE)
dev.off()

png(file = paste("DimHeatmap_PCA", ".png", sep = ""),
    width = 450, height = 300, units = "mm", res = 300, pointsize = 15)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
DimHeatmap(sc, dims = 1:9, cells = 500, balanced = TRUE)
dev.off()

# ---- ElbowPlot ----
pdf(file = paste("ElbowPlot", ".pdf", sep = ""), width = 10, height = 4)
p1 <- ElbowPlot(sc, ndims = 25)
p2 <- ElbowPlot(sc, ndims = 100)
p1 + p2
dev.off()

png(file = paste("ElbowPlot", ".png", sep = ""),
    width = 250, height = 100, units = "mm", res = 300, pointsize = 2)
par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
p1 <- ElbowPlot(sc, ndims = 25)
p2 <- ElbowPlot(sc, ndims = 100)
p1 + p2
dev.off()

logi("Done. Saved: %s.rds | reduction=%s", opt$out_prefix, use_reduction)
