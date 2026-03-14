#!/usr/bin/env Rscript

#############################################################################
# 从多个样本的 inferCNV 结果目录中读取 reference / observation 矩阵，
# 统一按共同基因合并，计算每个细胞的 CNA signal 与 malignant correlation，
# 给所有细胞做 malignant / nonmalignant / unresolved 分类，
# 并输出一个合并的转置 CNA 热图：
# - 行 = 细胞，按样本分块(row_split=Sample)，样本间用实线隔开；
# - 左侧注释 = Cell_Call (Reference / NonMalignant / Malignant / Unresolved)；
# - 右侧注释 = Sample 名称；
# - 列 = 基因窗口，按染色体排序并分块，在底部标注 chr，并画竖线。
#
# 样本配置文件（TSV）示例 (--config）：
# sample_id  infercnv_dir
# S1        /path/to/S1/infercnv_results
# S2        /path/to/S2/infercnv_results
#
# 使用示例：
# Rscript sc_infercnv_merge_cnv_heatmap_multi.r \
#   --config samples.tsv \
#   --signal 0.9 \
#   --signalcorrelation 0.8
#############################################################################

suppressPackageStartupMessages({
  library(tidyverse)
  library(ComplexHeatmap)
  library(circlize)
  library(ggplot2)
  library(umap)
  library(cluster)
  library(igraph)
  library(RANN)
  library(optparse)
  library(grid)
})

#############################################################################
# 参数
#############################################################################

option_list <- list(
  make_option(
    c("-s","--signal"),
    action  = "store",
    type    = "numeric",
    default = 0.9,
    help    = "cna_signal_threshold (reference 细胞通过比例，比如 0.9/0.95/0.99)"
  ),
  make_option(
    c("-c","--signalcorrelation"),
    action  = "store",
    type    = "numeric",
    default = 0.8,
    help    = "signal_correlation_threshold (reference 细胞通过比例，比如 0.8/0.9)"
  ),
  make_option(
    c("-a","--cellanno"),
    action  = "store",
    type    = "character",
    default = "cellanno.txt",
    help    = "细胞注释文件（本版本未使用，仅保留参数占位）"
  ),
  make_option(
    c("-C","--config"),
    action  = "store",
    type    = "character",
    default = "samples.tsv",
    help    = "样本配置表 TSV，必须包含列: sample_id,infercnv_dir"
  ),
  make_option(
    c("-m","--max_heatmap_cells"),
    action  = "store",
    type    = "integer",
    default = 4000,
    help    = "用于 CNA 热图展示的最大细胞数 (>0 时启用随机下采样；设为 0 表示不下采样)"
  ),
  make_option(
    c("-g","--genes_per_bin"),
    action  = "store",
    type    = "integer",
    default = 10,
    help    = "绘制热图时每多少个基因合并为一个 bin（取平均）"
  )
)

opt <- parse_args(OptionParser(option_list = option_list))

cna_signal_threshold <- opt$signal
signal_correlation   <- opt$signalcorrelation
max_heatmap_cells    <- opt$max_heatmap_cells
genes_per_bin        <- opt$genes_per_bin

#############################################################################
# 1. 读取多个样本的 inferCNV 输出
#############################################################################

message("读取样本配置: ", opt$config)
samples_df <- read.table(opt$config, header = TRUE, sep = "\t",
                         stringsAsFactors = FALSE, check.names = FALSE)
if (!all(c("sample_id","infercnv_dir") %in% colnames(samples_df))) {
  stop("config 文件必须至少包含列: sample_id,infercnv_dir")
}

ref_list <- list()
obs_list <- list()
sample_vec_all <- character()  # named vector: names = cell, value = sample_id

for (i in seq_len(nrow(samples_df))) {
  sid  <- samples_df$sample_id[i]
  idir <- samples_df$infercnv_dir[i]

  message("[INFO] 读取样本: ", sid, " 目录: ", idir)

  ref_file <- file.path(idir, "infercnv.references.txt")
  obs_file <- file.path(idir, "infercnv.observations.txt")

  if (!file.exists(ref_file)) stop("ref_file 不存在: ", ref_file)
  if (!file.exists(obs_file)) stop("obs_file 不存在: ", obs_file)

  ref_mat_i <- read.table(ref_file, header = TRUE, row.names = 1,
                          sep = " ", check.names = FALSE)
  obs_mat_i <- read.table(obs_file, header = TRUE, row.names = 1,
                          sep = " ", check.names = FALSE)

  # 先保证本样本内部 ref / obs 行完全对齐
  common_i <- intersect(rownames(ref_mat_i), rownames(obs_mat_i))
  ref_mat_i <- ref_mat_i[common_i, , drop = FALSE]
  obs_mat_i <- obs_mat_i[common_i, , drop = FALSE]

  ref_list[[sid]] <- ref_mat_i
  obs_list[[sid]] <- obs_mat_i

  # 记录每个细胞属于哪个样本
  sample_vec_all <- c(
    sample_vec_all,
    setNames(rep(sid, ncol(ref_mat_i)), colnames(ref_mat_i)),
    setNames(rep(sid, ncol(obs_mat_i)), colnames(obs_mat_i))
  )
}

# 所有样本共同基因（ref + obs 都参与）
all_gene_sets <- c(lapply(ref_list, rownames), lapply(obs_list, rownames))
common_genes  <- Reduce(intersect, all_gene_sets)
message("[INFO] 多样本共同基因数: ", length(common_genes))

# 统一到共同基因
ref_list <- lapply(ref_list, function(m) m[common_genes, , drop = FALSE])
obs_list <- lapply(obs_list, function(m) m[common_genes, , drop = FALSE])

# 合并为大矩阵
ref_mat <- do.call(cbind, ref_list)
obs_mat <- do.call(cbind, obs_list)

cnv_mat <- cbind(ref_mat, obs_mat)
cat("Dim of combined matrix = ", dim(cnv_mat), "\n")

# 细胞类型标签（Reference vs Observation）
ref_cells <- colnames(ref_mat)
obs_cells <- colnames(obs_mat)

cell_type <- rep("Reference", ncol(cnv_mat))
names(cell_type) <- colnames(cnv_mat)
cell_type[obs_cells] <- "Observation"

# 每个细胞的样本来源
sample_of_cell <- sample_vec_all[colnames(cnv_mat)]

#############################################################################
# 2. CNA value = cnv_mat - 1
#############################################################################

cna_val <- cnv_mat - 1

#############################################################################
# 3. 计算 CNA signal & CNA correlation
#############################################################################

# 3.1 CNA signal
calc_cna_signal <- function(x, top_frac = 2/3) {
  n <- length(x)
  rank_idx <- order(abs(x), decreasing = TRUE)
  top_n   <- ceiling(n * top_frac)
  top_idx <- rank_idx[seq_len(top_n)]
  mean(abs(x[top_idx]))
}

cna_signal_vec <- apply(cna_val, 2, calc_cna_signal, top_frac = 2/3)

# 3.2 恶性参考 profile：Observation 中 signal 最高 25%
df_obs <- data.frame(Cell = obs_cells, cna_signal = cna_signal_vec[obs_cells])
thr_25pct <- quantile(df_obs$cna_signal, 0.75)
top_obs   <- df_obs$Cell[df_obs$cna_signal >= thr_25pct]

mal_ref_profile <- rowMeans(cna_val[, top_obs, drop = FALSE])

# 3.3 CNA correlation
calc_cna_corr <- function(x, ref_profile) {
  if (sd(x) == 0 || sd(ref_profile) == 0) return(NA_real_)
  cor(x, ref_profile, method = "pearson", use = "complete.obs")
}
cna_corr_vec <- apply(cna_val, 2, calc_cna_corr, ref_profile = mal_ref_profile)

#############################################################################
# 4. 基于 reference 细胞分布设定 cutoffs
#############################################################################

df_ref <- data.frame(
  Cell       = ref_cells,
  cna_signal = cna_signal_vec[ref_cells],
  cna_corr   = cna_corr_vec[ref_cells]
)
df_ref <- df_ref[!is.na(df_ref$cna_corr) & !is.nan(df_ref$cna_corr), ]

signal_thr <- quantile(df_ref$cna_signal, cna_signal_threshold, na.rm = TRUE)
corr_thr   <- quantile(df_ref$cna_corr,   signal_correlation,  na.rm = TRUE)

cat("signal_thr =", signal_thr, "\n")
cat("corr_thr   =", corr_thr,   "\n")

#############################################################################
# 5. 细胞 malignant / nonmalignant / unresolved 分类
#############################################################################

cell_call <- rep("Reference", ncol(cna_val))
names(cell_call) <- colnames(cna_val)

for (obs_cell in obs_cells) {
  sigval  <- cna_signal_vec[obs_cell]
  corrval <- cna_corr_vec[obs_cell]

  if (is.na(sigval) || is.na(corrval)) {
    cell_call[obs_cell] <- "Unresolved"
    next
  }

  if (sigval > signal_thr & corrval > corr_thr) {
    cell_call[obs_cell] <- "Malignant"
  } else if (sigval < signal_thr & corrval < corr_thr) {
    cell_call[obs_cell] <- "NonMalignant"
  } else {
    cell_call[obs_cell] <- "Unresolved"
  }
}

print(table(cell_call))

write.table(
  table(cell_call),
  file      = "cell_malignant_calls_updated.stat.txt",
  sep       = "\t",
  row.names = FALSE,
  quote     = FALSE
)

df_calls <- data.frame(
  Cell       = colnames(cna_val),
  Sample     = sample_of_cell[colnames(cna_val)],
  Cell_Type  = cell_type,
  CNA_signal = cna_signal_vec[colnames(cna_val)],
  CNA_corr   = cna_corr_vec[colnames(cna_val)],
  Final_Call = cell_call[colnames(cna_val)]
)
write.table(
  df_calls,
  file      = "cell_malignant_calls_updated.txt",
  sep       = "\t",
  row.names = FALSE,
  quote     = FALSE
)

#############################################################################
# 6. CNA_signal vs CNA_corr 散点图
#############################################################################

p_scatter <- ggplot(df_calls, aes(x = CNA_corr, y = CNA_signal,
                                  color = Final_Call)) +
  geom_point(size = 1.5, alpha = 0.8) +
  theme_bw() +
  theme(panel.grid = element_blank()) +
  labs(x = "CNA correlation", y = "CNA signal", color = "Cell call") +
  scale_color_manual(values = c(
    "Reference"    = "gray70",
    "NonMalignant" = "green3",
    "Malignant"    = "red",
    "Unresolved"   = "orange"
  ))

pdf("CNA_signal_vs_corr.pdf", width = 5, height = 4)
print(p_scatter)
dev.off()

png("CNA_signal_vs_corr.png", width = 5, height = 4, units = "in", res = 300)
print(p_scatter)
dev.off()

#------------------------------
# 7.7 画图：左侧 Cell_Call 注释 + 中间主热图 + 右侧 colorbar
#------------------------------
png("CNA_heatmap_transposed.png", width = 10, height = 6, units = "in", res = 300)

## 三列布局：1=左注释条，2=主热图，3=colorbar
layout(matrix(c(1, 2, 3), ncol = 3), widths = c(0.4, 4, 0.4))

nr <- nrow(mat_t)
nc <- ncol(mat_t)

########################################
## 7.7.1 左侧 Cell_Call 注释条
########################################
par(mar = c(5, 1, 2, 2))

cell_call_vals <- as.character(cell_order_df$Cell_Call)
cc_levels <- c("Reference", "NonMalignant", "Malignant", "Unresolved")
cc_colors <- c(
  "Reference"    = "grey70",
  "NonMalignant" = "green3",
  "Malignant"    = "red",
  "Unresolved"   = "orange"
)

cc_idx <- match(cell_call_vals, cc_levels)
z_ann  <- matrix(cc_idx[nr:1], nrow = 1)  # 竖直方向翻转，与主图对齐

image(
  x = 1,
  y = 1:nr,
  z = z_ann,
  col = cc_colors[cc_levels],
  xaxt = "n",
  yaxt = "n",
  xlab = "",
  ylab = "",
  useRaster = TRUE
)

########################################
## 7.7.2 中间主热图（按样本 + 染色体分块）
########################################
par(mar = c(5, 4, 2, 6))

# 主图矩阵，同样竖直方向翻转
z_main <- t(mat_t[nr:1, , drop = FALSE])

image(
  x = 1:nc,
  y = 1:nr,
  z = z_main,
  col = pal,
  xlab = "Genomic bins",
  ylab = "Cells",
  xaxt = "n",
  yaxt = "n",
  useRaster = TRUE
)

## 染色体竖线（bin_chr 来自前面 7.2，长度 = nc）
bin_chr_vec <- bin_chr[1:nc]
chr_boundary <- which(bin_chr_vec[-nc] != bin_chr_vec[-1])
if (length(chr_boundary) > 0) {
  abline(v = chr_boundary + 0.5, col = "black", lwd = 0.5)
}

## 样本之间的粗横线 + 右侧样本名
samp_vec <- as.character(cell_order_df$Sample)

if (nr > 1) {
  samp_boundary <- which(samp_vec[-nr] != samp_vec[-1])
  if (length(samp_boundary) > 0) {
    samp_boundary_y <- nr - samp_boundary + 0.5
    abline(h = samp_boundary_y, col = "black", lwd = 2)  # 粗一点更明显
  }
}

samp_rows <- split(seq_len(nr), samp_vec)
samp_mid  <- vapply(samp_rows, function(v) mean(v), numeric(1))
samp_mid_y <- nr - samp_mid + 1

axis(
  side = 4,
  at   = samp_mid_y,
  labels = names(samp_mid_y),
  las   = 2,
  cex.axis = 0.8
)

## x 轴染色体标签（用每个 chr 的 bin 中点）
chr_mid <- tapply(seq_len(nc), bin_chr_vec, function(v) mean(range(v)))
chr_mid <- chr_mid[!names(chr_mid) %in% "Other"]

if (length(chr_mid) > 0) {
  axis(
    side = 1,
    at   = chr_mid,
    labels = names(chr_mid),
    las   = 2,
    cex.axis = 0.6
  )
}

########################################
## 7.7.3 右侧 colorbar
########################################
par(mar = c(5, 1, 2, 2))

y_leg <- seq(min_val, max_val, length.out = 256)
z_leg <- matrix(y_leg, nrow = 1)

image(
  x = 1,
  y = y_leg,
  z = z_leg,
  col = pal,
  xaxt = "n",
  xlab = "",
  ylab = "CNA",
  useRaster = TRUE
)
axis(4)

dev.off()

cat("=== 多样本 CNA_heatmap_transposed 输出完成（base image + 样本分块 + Reference 标注） ===\n")
