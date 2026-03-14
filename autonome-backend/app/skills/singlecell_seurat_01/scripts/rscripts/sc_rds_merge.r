#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(optparse)
  library(Seurat)     # Seurat >=5.0
  library(Matrix)
})

# 1. 参数定义
option_list <- list(
  make_option(c("-a","--input1"), type="character", help="第一个 Seurat RDS 文件路径"),
  make_option(c("-b","--input2"), type="character", help="第二个 Seurat RDS 文件路径"),
  make_option(c("-o", "--output"), type="character", help="合并后 Seurat RDS 输出路径")
)
opt <- parse_args(OptionParser(option_list=option_list))
if (is.null(opt$input1) || is.null(opt$input2) || is.null(opt$output)) {
  stop("请同时指定 --input1, --input2 和 --output", call.=FALSE)
}

# 2. 读取对象
seurat1 <- readRDS(opt$input1)
seurat2 <- readRDS(opt$input2)

# 3. 对齐 layer 的函数
align_layers <- function(obj1, obj2, assay_name) {
  # 读取 raw counts 矩阵
  cnt1 <- GetAssayData(obj1, assay=assay_name, layer="counts")   # layer 参数替代 slot :contentReference[oaicite:0]{index=0}
  cnt2 <- GetAssayData(obj2, assay=assay_name, layer="counts")
  nfeat  <- nrow(cnt1)
  ncell1 <- ncol(cnt1)
  ncell2 <- ncol(cnt2)

  # 列出所有现存 layer
  layers1 <- Layers(obj1[[assay_name]])   # Seurat v5 assays store data in layers :contentReference[oaicite:1]{index=1}
  layers2 <- Layers(obj2[[assay_name]])
  all_layers <- union(layers1, layers2)

  # 构造全零矩阵用于补齐
  zero1 <- Matrix(0, nfeat, ncell1, sparse=TRUE)
  zero2 <- Matrix(0, nfeat, ncell2, sparse=TRUE)

  # 对每个 layer，若缺失则添加
  for (ly in all_layers) {
    if (!(ly %in% layers1)) {
      obj1 <- SetAssayData(obj1, assay=assay_name, new.data=zero1, layer=ly)
    }
    if (!(ly %in% layers2)) {
      obj2 <- SetAssayData(obj2, assay=assay_name, new.data=zero2, layer=ly)
    }
  }

  list(obj1, obj2)
}

# 4. 在所有共有 assay 上对齐 layer
common_assays <- intersect(Assays(seurat1), Assays(seurat2))
for (asn in common_assays) {
  tmp <- align_layers(seurat1, seurat2, asn)
  seurat1 <- tmp[[1]]; seurat2 <- tmp[[2]]
}

# 5. 合并并保存
merged <- merge(
  x = seurat1,
  y = seurat2,
  add.cell.ids = c("S1","S2"),  # 根据实际样本改前缀
  project = "MergedProject",
  merge.data = TRUE
)

merged[["RNA"]] = JoinLayers(merged[["RNA"]])

# 6. 过滤只在少于2个细胞中表达的基因
# 获取counts矩阵
counts_matrix <- GetAssayData(merged, assay = "RNA", layer = "counts")

# 计算每个基因在多少个细胞中表达(>0)
genes_expressed_in <- Matrix::rowSums(counts_matrix > 0)

# 保留在至少2个细胞中表达的基因
genes_to_keep <- names(which(genes_expressed_in >= 2))

# 对Seurat对象进行子集化
merged <- subset(merged, features = genes_to_keep)

saveRDS(merged, file = opt$output)
message("✔ 合并完成，结果已保存到：", opt$output)