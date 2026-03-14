#!/usr/bin/env Rscript

# """
# 从多个样本的 inferCNV 结果生成“细胞 × 基因组区域”的 CNV 热图，
# 图形布局参照 infercnv::plot_cnv：
#
# 功能要点
# - 输入：样本配置表（sample_id, cell_table, obs_txt, ref_txt, gene_order）
#   * cell_table 至少包含：Cell, Cell_Type, Final_Call
#     - Cell_Type: "Observation" / "Reference"
#     - Final_Call: "Malignant" / "NonMalignant" / "Unresolved" 等
#   * obs_txt / ref_txt：inferCNV 矩阵（行=基因，列=细胞，第一列为基因名）
#   * gene_order：基因位置信息（gene, chr, start, end）
# - 先用 Reference 细胞按基因计算参考基线，再对 Observation/Reference
#   做 diff 或 log2ratio 变换。
# - 基因按 gene_order 的 chr + start 排序，构建全基因组连续坐标；
#   染色体在 x 轴上的宽度与基因数成比例。
# - 纵轴：
#   1) 所有 Reference 细胞（跨样本合并），
#   2) 所有 Normal Epithelial 细胞（Observation & Final_Call != Malignant），
#   3) 所有 Observation 恶性细胞（Final_Call == Malignant）。
#   同一大类内部按 sample_id 分块，每块内部对细胞做层次聚类。
# - 右侧：每个样本块标注样本名称；
#   左侧：标注大类名称（Reference / Normal Epithelial / Observation）。
# - 颜色：蓝（缺失）- 白 - 红（扩增），数值可通过 --cap 截断。
# - 选项 --drop_normal_epi 可去掉 Normal Epithelial 分块，只保留 Reference 与恶性细胞。
#
# 用法示例：
# Rscript sc_infercnv_cells_heatmap_grouped.r \
#   --config samples.tsv \
#   --out cnv_cells \
#   --transform log2ratio \
#   --eps 1e-3 \
#   --cap 1.0 \
#   --include_x \
#   --width 12 --height 9
#
# 若只画恶性 Observation 细胞（不包含 Normal Epithelial）：
#   --drop_normal_epi
# """

suppressPackageStartupMessages({
  library(optparse)
  library(data.table)
  library(dplyr)
  library(tidyr)
  library(stringr)
  library(readr)
  library(ggplot2)
  library(forcats)
  library(matrixStats)
})

# ---------------- CLI 参数 ----------------
option_list <- list(
  make_option(c("-c","--config"), type = "character",
              help = "样本配置表 TSV/CSV（含 sample_id, cell_table, obs_txt, ref_txt, gene_order）"),
  make_option(c("-o","--out"), type = "character", default = "cnv_cells",
              help = "输出前缀 [默认: %default]"),
  make_option(c("--transform"), type = "character", default = "log2ratio",
              help = "与 Reference 的变换方式：diff | log2ratio [默认: %default]"),
  make_option(c("--eps"), type = "double", default = 1e-3,
              help = "log2ratio 的伪计数 [默认: %default]"),
  make_option(c("--cap"), type = "double", default = 1.0,
              help = "热图颜色截断到 ±cap [默认: %default]"),
  make_option(c("--include_x"), action = "store_true", default = TRUE,
              help = "是否包含 X 染色体 [默认: TRUE]"),
  make_option(c("--include_y"), action = "store_true", default = FALSE,
              help = "是否包含 Y 染色体 [默认: FALSE]"),
  make_option(c("--width"), type = "double", default = 10,
              help = "图宽（inch）[默认: %default]"),
  make_option(c("--height"), type = "double", default = 8,
              help = "图高（inch）[默认: %default]"),
  make_option(c("--drop_normal_epi"), action = "store_true", default = FALSE,
              help = "是否剔除 Normal Epithelial（Observation & Final_Call != Malignant）[默认: %default]")
)

opt <- parse_args(OptionParser(option_list = option_list))
if (is.null(opt$config)) {
  stop("请用 -c / --config 指定样本配置文件。")
}

# ---------------- 工具函数 ----------------

normalize_chr <- function(x) {
  x <- as.character(x)
  x <- gsub("^chr", "", x, ignore.case = TRUE)
  x <- toupper(x)
  x[x == "23"] <- "X"
  x[x == "24"] <- "Y"
  x
}

read_gene_order <- function(fp) {
  go <- suppressWarnings(fread(fp, header = TRUE))
  if (!all(c("gene","chr","start","end") %in% names(go))) {
    go <- suppressWarnings(fread(fp, header = FALSE,
                                 col.names = c("gene","chr","start","end")))
  } else {
    nm <- tolower(names(go))
    colmap <- list(
      gene  = c("gene","genes","symbol","hgnc_symbol"),
      chr   = c("chr","chromosome","chrom"),
      start = c("start","startbp","start_position","startpos"),
      end   = c("end","endbp","end_position","endpos")
    )
    for (std in names(colmap)) {
      hit <- which(nm %in% colmap[[std]])[1]
      if (!is.na(hit)) names(go)[hit] <- std
    }
    go <- go[, c("gene","chr","start","end"), with = FALSE]
  }
  go %>%
    mutate(chr = normalize_chr(chr)) %>%
    filter(!is.na(gene) & !is.na(chr)) %>%
    arrange(factor(chr, levels = c(as.character(1:22),"X","Y")), start)
}

read_matrix <- function(fp) {
  dt <- suppressWarnings(fread(fp))
  if (ncol(dt) < 2) stop("矩阵文件格式异常: ", fp)
  genes <- dt[[1]]
  mat   <- as.matrix(dt[,-1, with = FALSE])
  rownames(mat) <- genes
  storage.mode(mat) <- "double"
  mat
}

cluster_cells <- function(mat) {
  if (ncol(mat) <= 1) return(colnames(mat))
  m2 <- mat
  m2[is.na(m2)] <- 0
  if (any(apply(m2, 2, sd, na.rm = TRUE) == 0)) {
    m2 <- sweep(m2, 2, apply(m2, 2, mean, na.rm = TRUE), FUN = "-")
  }
  d <- dist(t(m2), method = "euclidean")
  hc <- hclust(d, method = "ward.D2")
  colnames(m2)[hc$order]
}

cap_vals <- function(x, cap) pmin(pmax(x, -cap), cap)

# ---------------- 读配置与基因顺序 ----------------

conf <- suppressWarnings(fread(opt$config))
stopifnot(all(c("sample_id","cell_table","obs_txt","ref_txt","gene_order") %in% colnames(conf)))
conf <- as_tibble(conf)

# 以首个样本为基准的基因顺序
go0 <- read_gene_order(conf$gene_order[1])

keep_chr <- c(as.character(1:22),
              if (isTRUE(opt$include_x)) "X",
              if (isTRUE(opt$include_y)) "Y")

go0 <- go0 %>%
  filter(chr %in% keep_chr) %>%
  arrange(factor(chr, levels = keep_chr), start)

if (nrow(go0) == 0) {
  stop("gene_order 过滤后无任何基因，请检查染色体命名或 --include_x/--include_y 设置。")
}

# x 坐标：每个基因一个单位，宽度与基因数成比例
go0 <- go0 %>%
  mutate(gene = as.character(gene)) %>%
  arrange(factor(chr, levels = keep_chr), start) %>%
  mutate(x = row_number())

chr_pos <- go0 %>%
  group_by(chr) %>%
  summarise(start = min(x),
            end   = max(x),
            mid   = floor((start + end)/2),
            .groups = "drop")

# ---------------- 主循环：汇总所有样本的细胞与数值 ----------------

all_long_list   <- list()
cell_order_list <- list()

sample_order <- unique(conf$sample_id)

for (i in seq_len(nrow(conf))) {
  sid <- conf$sample_id[i]
  message("Processing sample: ", sid)

  # 细胞注释
  tab <- suppressWarnings(fread(conf$cell_table[i])) %>% as_tibble()
  stopifnot(all(c("Cell","Cell_Type","Final_Call") %in% colnames(tab)))

  # 矩阵
  obs_m_raw <- read_matrix(conf$obs_txt[i])
  ref_m_raw <- read_matrix(conf$ref_txt[i])

  # 对齐基因
  common_genes <- intersect(rownames(obs_m_raw), rownames(ref_m_raw))
  obs_m <- obs_m_raw[common_genes, , drop = FALSE]
  ref_m <- ref_m_raw[common_genes, , drop = FALSE]

  # 只保留 gene_order 中的基因，并按 go0 排序
  genes_keep <- intersect(go0$gene, rownames(obs_m))
  if (length(genes_keep) == 0) {
    warning("Sample ", sid, " 与 gene_order 交集基因为 0，跳过该样本。")
    next
  }
  obs_m <- obs_m[genes_keep, , drop = FALSE]
  ref_m <- ref_m[genes_keep, , drop = FALSE]

  # 参考基线：Reference 细胞的行中位数
  ref_cells_all <- tab %>%
    filter(Cell_Type == "Reference") %>%
    pull(Cell)
  ref_cells_all <- intersect(ref_cells_all, colnames(ref_m))
  if (length(ref_cells_all) == 0) {
    warning("Sample ", sid, " 中没有 Reference 细胞，使用全部 ref_m 列做基线。")
    ref_base <- matrixStats::rowMedians(ref_m, na.rm = TRUE)
  } else {
    ref_base <- matrixStats::rowMedians(ref_m[, ref_cells_all, drop = FALSE], na.rm = TRUE)
  }

  # 变换
  if (opt$transform == "diff") {
    obs_rel <- sweep(obs_m, 1, ref_base, FUN = "-")
    ref_rel <- sweep(ref_m, 1, ref_base, FUN = "-")
    legend_title <- "CNA\n(Δ vs ref)"
  } else {
    eps <- opt$eps
    obs_rel <- log2((obs_m + eps) / (ref_base + eps))
    ref_rel <- log2((ref_m + eps) / (ref_base + eps))
    legend_title <- "CNA\n(log2 ratio)"
  }

  # 三类细胞：Reference / Normal Epithelial / Observation(Malignant)
  # Reference
  ref_cells <- tab %>%
    filter(Cell_Type == "Reference") %>%
    pull(Cell)
  ref_cells <- intersect(ref_cells, colnames(ref_rel))

  # Normal Epithelial（Observation 非恶性）
  normal_epi_cells <- tab %>%
    filter(Cell_Type == "Observation", Final_Call != "Malignant") %>%
    pull(Cell)
  normal_epi_cells <- intersect(normal_epi_cells, colnames(obs_rel))

  # Observation 恶性
  obs_malignant_cells <- tab %>%
    filter(Cell_Type == "Observation", Final_Call == "Malignant") %>%
    pull(Cell)
  obs_malignant_cells <- intersect(obs_malignant_cells, colnames(obs_rel))

  # 如果 drop_normal_epi，则直接清空 Normal Epi
  if (isTRUE(opt$drop_normal_epi)) {
    normal_epi_cells <- character(0)
  }

  if (length(ref_cells) == 0 &&
      length(normal_epi_cells) == 0 &&
      length(obs_malignant_cells) == 0) {
    warning("Sample ", sid, " 中无可用细胞，跳过。")
    next
  }

  # 组内聚类排序
  ord_ref <- character(0)
  if (length(ref_cells) > 0) {
    ord_ref <- cluster_cells(ref_rel[, ref_cells, drop = FALSE])
  }

  ord_normal <- character(0)
  if (length(normal_epi_cells) > 0) {
    ord_normal <- cluster_cells(obs_rel[, normal_epi_cells, drop = FALSE])
  }

  ord_obs <- character(0)
  if (length(obs_malignant_cells) > 0) {
    ord_obs <- cluster_cells(obs_rel[, obs_malignant_cells, drop = FALSE])
  }

  # 当前样本的细胞顺序信息
  cell_ids <- c(ord_ref, ord_normal, ord_obs)
  group_vec <- c(rep("Reference", length(ord_ref)),
                 rep("Normal Epithelial", length(ord_normal)),
                 rep("Observation", length(ord_obs)))

  cell_order_sample <- tibble(
    sample_id = sid,
    Cell      = cell_ids,
    group     = group_vec
  ) %>%
    group_by(sample_id, group) %>%
    mutate(order_in_group = row_number()) %>%
    ungroup()

  cell_order_list[[length(cell_order_list) + 1]] <- cell_order_sample

  # 构建长表：基因 × 细胞
  long_list <- list()

  if (length(ord_ref) > 0) {
    mat_ref <- ref_rel[, ord_ref, drop = FALSE]
    df_ref <- as.data.frame(mat_ref)
    df_ref$gene <- rownames(mat_ref)
    long_ref <- df_ref %>%
      pivot_longer(cols = -gene, names_to = "Cell", values_to = "val") %>%
      mutate(sample_id = sid,
             group     = "Reference")
    long_list[[length(long_list) + 1]] <- long_ref
  }

  if (length(ord_normal) > 0) {
    mat_normal <- obs_rel[, ord_normal, drop = FALSE]
    df_normal <- as.data.frame(mat_normal)
    df_normal$gene <- rownames(mat_normal)
    long_normal <- df_normal %>%
      pivot_longer(cols = -gene, names_to = "Cell", values_to = "val") %>%
      mutate(sample_id = sid,
             group     = "Normal Epithelial")
    long_list[[length(long_list) + 1]] <- long_normal
  }

  if (length(ord_obs) > 0) {
    mat_obs <- obs_rel[, ord_obs, drop = FALSE]
    df_obs <- as.data.frame(mat_obs)
    df_obs$gene <- rownames(mat_obs)
    long_obs <- df_obs %>%
      pivot_longer(cols = -gene, names_to = "Cell", values_to = "val") %>%
      mutate(sample_id = sid,
             group     = "Observation")
    long_list[[length(long_list) + 1]] <- long_obs
  }

  all_long_list[[length(all_long_list) + 1]] <- bind_rows(long_list)
}

if (length(all_long_list) == 0) {
  stop("没有有效样本输出，请检查配置和过滤条件。")
}

cnv_long <- bind_rows(all_long_list)
cell_order_df <- bind_rows(cell_order_list)

# ---------------- 整体排序与坐标 ----------------

group_levels <- c("Reference",
                  if (!isTRUE(opt$drop_normal_epi)) "Normal Epithelial",
                  "Observation")

cell_order_df <- cell_order_df %>%
  mutate(
    sample_id = factor(sample_id, levels = sample_order),
    group     = factor(group, levels = group_levels)
  ) %>%
  arrange(group, sample_id, order_in_group) %>%
  mutate(y = row_number())

# 合并 y 坐标与基因坐标
cnv_long <- cnv_long %>%
  inner_join(go0 %>% select(gene, chr, x), by = "gene") %>%
  inner_join(cell_order_df %>% select(sample_id, Cell, group, y),
             by = c("sample_id","Cell","group")) %>%
  mutate(
    val   = cap_vals(val, opt$cap),
    group = factor(group, levels = group_levels)
  )

# 各个样本块（按 group × sample_id）在 y 轴上的范围，用于画横线和标注样本名
block_df <- cell_order_df %>%
  mutate(
    sample_id = as.character(sample_id),
    group     = factor(group, levels = group_levels)
  ) %>%
  group_by(group, sample_id) %>%
  summarise(ymin = min(y), ymax = max(y), .groups = "drop") %>%
  arrange(group, sample_id) %>%
  mutate(ymid = (ymin + ymax) / 2)

# 各个大组（Reference / Normal Epithelial / Observation）的范围，用于左侧大标签和粗横线
group_df <- cell_order_df %>%
  group_by(group) %>%
  summarise(ymin = min(y), ymax = max(y), .groups = "drop") %>%
  mutate(ymid = (ymin + ymax) / 2) %>%
  arrange(group)

# 细横线（样本块之间）
sample_boundaries <- unique(block_df$ymax + 0.5)
sample_boundaries <- sample_boundaries[
  sample_boundaries > min(cell_order_df$y) &
    sample_boundaries < max(cell_order_df$y)
]

# 粗横线（大组之间）
group_boundaries <- unique(group_df$ymax + 0.5)
group_boundaries <- group_boundaries[
  group_boundaries > min(cell_order_df$y) &
    group_boundaries < max(cell_order_df$y)
]

# 染色体竖线
chr_vlines <- chr_pos$end + 0.5

# ---------------- 绘图 ----------------

p <- ggplot(cnv_long,
            aes(x = x, y = y, fill = val)) +
  geom_tile(width = 1, height = 1) +
  scale_fill_gradient2(low = "#0a2091ff",
                       mid = "white",
                       high = "#9f200fff",
                       midpoint = 0,
                       limits = c(-opt$cap, opt$cap),
                       name = legend_title) +
  geom_vline(xintercept = chr_vlines, size = 0.4) +
  scale_x_continuous(
    breaks = chr_pos$mid,
    labels = as.character(chr_pos$chr),
    expand = expansion(mult = c(0.12, 0.20))  # 左右留白，用于大类和样本名
  ) +
  scale_y_reverse(expand = c(0,0)) +
  labs(x = "Genomic Region", y = "Cells") +
  theme_minimal(base_size = 10) +
  theme(
    axis.text.y  = element_blank(),
    axis.ticks.y = element_blank(),
    panel.grid   = element_blank(),
    legend.position = "right",
    plot.margin = margin(5,5,5,5)
  )

# 样本块的细横线
for (b in sample_boundaries) {
  p <- p + annotate("segment",
                    x = -Inf, xend = Inf,
                    y = b, yend = b,
                    size = 0.3)
}

# 大组之间的粗横线
for (b in group_boundaries) {
  p <- p + annotate("segment",
                    x = -Inf, xend = Inf,
                    y = b, yend = b,
                    size = 0.7)
}

# 左侧标注大组名称
p <- p + annotate("text",
                  x = min(go0$x) - 0.05 * max(go0$x),
                  y = group_df$ymid,
                  label = as.character(group_df$group),
                  hjust = 1, size = 3)

# 右侧标注样本名称（每个 group × sample 块一个标签）
p <- p + annotate("text",
                  x = max(go0$x) + 0.08 * max(go0$x),
                  y = block_df$ymid,
                  label = block_df$sample_id,
                  hjust = 0, size = 2.8)

# ---------------- 输出 ----------------

write_tsv(
  cnv_long %>% select(sample_id, Cell, group, gene, chr, x, y, val),
  paste0(opt$out, ".cells_long.tsv")
)

ggsave(paste0(opt$out, ".png"),
       p, width = opt$width, height = opt$height, units = "in", dpi = 300)
ggsave(paste0(opt$out, ".pdf"),
       p, width = opt$width, height = opt$height, units = "in")


message("Done. Figure: ", opt$out, ".pdf / .png ; Long table: ", opt$out, ".cells_long.tsv")
