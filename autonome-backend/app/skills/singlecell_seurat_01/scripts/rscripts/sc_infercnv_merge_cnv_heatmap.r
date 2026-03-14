#!/usr/bin/env Rscript

# Rscript /Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/sc_infercnv_merge_cnv_heatmap.r \
#   -c samples.tsv \
#   -o infercnv_cnvmap \
#   -b 50 \
#   --cap 1.0 \
#   --agg mean \
#   --include_x \
#   --width 12 --height 9
#   # 如需去掉 Normal Epithelial 轨道：
#   # --drop_normal_epi


# sample_id	cell_table	obs_txt	ref_txt	gene_order
# OP10	/path/OP10/final_calls.tsv	/path/OP10/infercnv.observations.txt	/path/OP10/infercnv.references.txt	/opt/data1//public/genome/human/annotation/gencode_v38/human_gene_pos.txt
# OP12	/path/OP12/final_calls.tsv	/path/OP12/infercnv.observations.txt	/path/OP12/infercnv.references.txt	/opt/data1//public/genome/human/annotation/gencode_v38/human_gene_pos.txt

# cell_table：你给的 5 列表（Cell、Cell_Type、CNA_signal、CNA_corr、Final_Call）
# obs_txt/ref_txt：infercnv 的矩阵文件（基因×细胞），第一列为基因名
# gene_order：infercnv 的基因顺序文件（通常 4 列：gene chr start end；有无表头都可）


suppressPackageStartupMessages({
  library(optparse)
  library(data.table)
  library(dplyr)
  library(tidyr)
  library(stringr)
  library(readr)
  library(ggplot2)
  library(forcats)
  library(scales)
  library(matrixStats)
})

# ---------- CLI ----------
option_list <- list(
  make_option(c("-c","--config"), type="character", help="样本配置表 TSV/CSV（含 sample_id, cell_table, obs_txt, ref_txt, gene_order）"),
  make_option(c("-o","--out"),    type="character", default="cnv_multi", help="输出前缀 [默认: %default]"),
  make_option(c("-b","--bins"),   type="integer",   default=40, help="每条染色体的等量分箱数 [默认: %default]"),
  make_option(c("--cap"),         type="double",    default=1.0, help="热图剪裁到 ±cap（与示例色标一致）[默认: %default]"),
  make_option(c("--agg"),         type="character", default="mean", help="聚合函数 mean 或 median [默认: %default]"),
  make_option(c("--include_x"),   action="store_true", default=TRUE, help="是否包含 X 染色体 [默认: TRUE]"),
  make_option(c("--include_y"),   action="store_true", default=FALSE, help="是否包含 Y 染色体 [默认: FALSE]"),
  make_option(c("--width"),       type="double", default=10, help="图宽（inch）[默认: %default]"),
  make_option(c("--height"),      type="double", default=8,  help="图高（inch）[默认: %default]"),
  make_option(c("--transform"),   type="character", default="log2ratio",
              help="与参考的变换: diff | log2ratio [默认: %default]"),
  make_option(c("--eps"),         type="double", default=1e-3,
              help="log2ratio 的伪计数 [默认: %default]"),
  ## 新增：控制是否在热图中去掉 Normal Epithelial 轨道
  make_option(c("--drop_normal_epi"), action="store_true", default=FALSE,
              help="是否在热图中移除 Normal Epithelial 轨道 [默认: %default]")
)
opt <- parse_args(OptionParser(option_list=option_list))
if (is.null(opt$config)) stop("请用 -c 指定配置文件")

# ---------- 小工具 ----------

normalize_chr <- function(x) {
  x <- as.character(x)
  x <- gsub("^chr", "", x, ignore.case = TRUE)  # 去掉前缀 chr
  x <- toupper(x)
  x[x == "23"] <- "X"
  x[x == "24"] <- "Y"
  x
}

read_gene_order <- function(fp) {
  go <- suppressWarnings(data.table::fread(fp, header = TRUE))
  # 如果缺列名，按 4 列读入
  if (!all(c("gene","chr","start","end") %in% names(go))) {
    go <- suppressWarnings(data.table::fread(fp, header = FALSE,
                                             col.names = c("gene","chr","start","end")))
  } else {
    # 容错：常见异名 -> 标准名
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
    dplyr::mutate(chr = normalize_chr(chr)) %>%
    dplyr::filter(!is.na(gene) & !is.na(chr)) %>%
    dplyr::arrange(factor(chr, levels = c(as.character(1:22),"X","Y")), start)
}


read_matrix <- function(fp) {
  # infercnv 矩阵：第一列 gene，后面是细胞列
  dt <- suppressWarnings(fread(fp))
  if (ncol(dt) < 2) stop("矩阵文件格式异常: ", fp)
  genes <- dt[[1]]
  mat   <- as.matrix(dt[,-1,with=FALSE])
  rownames(mat) <- genes
  storage.mode(mat) <- "double"
  mat
}


agg_vec <- function(mat, cells, fun=c("mean","median")) {
  fun <- match.arg(fun)
  if (length(cells) == 0) return(rep(NA_real_, nrow(mat)))
  m <- mat[, intersect(cells, colnames(mat)), drop=FALSE]
  if (ncol(m) == 0) return(rep(NA_real_, nrow(mat)))
  if (fun=="mean") rowMeans(m, na.rm=TRUE) else apply(m, 1, median, na.rm=TRUE)
}

bin_profile_by_chr <- function(profile, gene_order_df, bins_per_chr=40) {
  df <- tibble(gene = names(profile), value = as.numeric(profile)) %>%
    inner_join(gene_order_df, by="gene") %>%
    arrange(factor(chr, levels=unique(gene_order_df$chr)), start)
  if (nrow(df)==0) return(tibble())
  # 对每条 chr 做等量切分
  out <- df %>%
    group_by(chr) %>%
    mutate(bin = as.integer(ceiling(row_number() / (n()/bins_per_chr)))) %>%
    group_by(chr, bin) %>%
    summarise(val = mean(value, na.rm=TRUE), .groups="drop")
  out
}

cap_vals <- function(x, cap) pmin(pmax(x, -cap), cap)

# ---------- 读配置 ----------
conf <- suppressWarnings(fread(opt$config))
stopifnot(all(c("sample_id","cell_table","obs_txt","ref_txt","gene_order") %in% colnames(conf)))
conf <- as_tibble(conf)

# ---------- 基因顺序（以首个样本为主） ----------
go0 <- read_gene_order(conf$gene_order[1])

table(go0$chr) %>% print()   # 应该是 1..22 以及 X(可选)/Y(可选)

keep_chr <- c(as.character(1:22), if (isTRUE(opt$include_x)) "X", if (isTRUE(opt$include_y)) "Y")
go0 <- go0 %>%
  dplyr::filter(chr %in% keep_chr) %>%
  dplyr::arrange(factor(chr, levels = keep_chr), start)

if (nrow(go0) == 0) {
  stop("gene_order 过滤后无任何行。请检查 gene_order 中的染色体命名或 --include_x/--include_y 选项。")
}

# 统计每条 chr 的分箱长度（用于绘图刻度）
chr_levels <- keep_chr
chr_bins_n <- setNames(rep(opt$bins, length(chr_levels)), chr_levels)

# ---------- 主循环：每个样本聚合为 3 条轨道 ----------
all_long <- list()

for (i in seq_len(nrow(conf))) {
  sid <- conf$sample_id[i]
  message("Processing sample: ", sid)

  tab  <- suppressWarnings(fread(conf$cell_table[i])) %>% as_tibble()
  # 必需列检查
  stopifnot(all(c("Cell","Cell_Type","Final_Call") %in% colnames(tab)))

  obs_m <- read_matrix(conf$obs_txt[i])
  ref_m <- read_matrix(conf$ref_txt[i])

  # 和参考细胞做基线；先对齐基因
  common_genes <- intersect(rownames(obs_m), rownames(ref_m))
  obs_m <- obs_m[common_genes, , drop=FALSE]
  ref_m <- ref_m[common_genes, , drop=FALSE]

  # 参考基线（按基因的中位数，更抗噪）
  ref_base <- matrixStats::rowMedians(ref_m, na.rm = TRUE)

  if (opt$transform == "diff") {
    # 差值：表达(或平滑强度) - 参考基线
    obs_rel <- sweep(obs_m, 1, ref_base, FUN = "-")
    ref_rel <- sweep(ref_m, 1, ref_base, FUN = "-")
    legend_title <- "CNA\n(Δ vs ref)"
  } else {
    # log2 比值：log2((obs+eps)/(ref_base+eps))
    eps <- opt$eps
    obs_rel <- log2((obs_m + eps) / (ref_base + eps))
    ref_rel <- log2((ref_m + eps) / (ref_base + eps))
    legend_title <- "CNA\n(log2 ratio)"
  }

  # 后续聚合都基于 *_rel
  obs_m <- obs_rel
  ref_m <- ref_rel

  # —— 定义三类：Cancer / Normal Epi / Fibro-Endo(Reference) ——
  cancer_cells <- tab %>%
    filter(Cell_Type == "Observation", Final_Call == "Malignant") %>%
    pull(Cell)

  normal_epi_cells <- tab %>%
    filter(Cell_Type == "Observation", Final_Call != "Malignant") %>%
    pull(Cell)  # 包含 Unresolved + NonMalignant

  ref_cells <- tab %>%
    filter(Cell_Type == "Reference") %>%
    pull(Cell)

  # —— 聚合向量（按基因） ——
  prof_cancer <- agg_vec(obs_m, cancer_cells, fun = opt$agg)
  prof_normal <- agg_vec(obs_m, normal_epi_cells, fun = opt$agg)
  prof_ref    <- agg_vec(ref_m, ref_cells,    fun = opt$agg)

  names(prof_cancer) <- rownames(obs_m)
  names(prof_normal) <- rownames(obs_m)
  names(prof_ref)    <- rownames(ref_m)

  # —— 按首样本的基因顺序做分箱（确保 x 轴一致） ——
  b1 <- bin_profile_by_chr(prof_cancer, go0, bins_per_chr = opt$bins) %>%
    mutate(category="Cancer")

  b2 <- bin_profile_by_chr(prof_normal, go0, bins_per_chr = opt$bins) %>%
    mutate(category="Normal Epithelial")

  b3 <- bin_profile_by_chr(prof_ref,    go0, bins_per_chr = opt$bins) %>%
    mutate(category="Reference")

  ## 根据 --drop_normal_epi 控制是否保留 Normal Epithelial
  b_list <- list(b1)
  if (!isTRUE(opt$drop_normal_epi)) {
    b_list <- c(b_list, list(b2))
  }
  b_list <- c(b_list, list(b3))

  binded <- bind_rows(b_list) %>%
    mutate(sample_id = sid)

  all_long[[length(all_long)+1]] <- binded
}

cnv_long <- bind_rows(all_long)

# ---------- 生成全局 x 轴（染色体拼接） ----------
chr_bin_df <- expand_grid(chr = factor(chr_levels, levels=chr_levels),
                          bin = seq_len(opt$bins)) %>%
  arrange(chr, bin) %>%
  mutate(x = row_number())

# 合并坐标
cnv_plot_df <- cnv_long %>%
  dplyr::right_join(chr_bin_df, by = c("chr","bin")) %>%
  dplyr::mutate(
    chr = factor(chr, levels = chr_levels),
    val = cap_vals(val, opt$cap)
  )

# 根据是否保留 Normal Epi 设置 category 顺序
cat_levels <- c("Cancer",
                if (!isTRUE(opt$drop_normal_epi)) "Normal Epithelial",
                "Reference")

# y 轴顺序：块内按 sample_id 升序
cnv_plot_df <- cnv_plot_df %>%
  mutate(category = factor(category, levels = cat_levels)) %>%
  group_by(category) %>%
  mutate(y = paste0(sample_id)) %>%
  ungroup() %>%
  mutate(y = fct_inorder(y))

# 计算块分隔线位置（y 轴）
y_levels <- cnv_plot_df %>%
  distinct(category, y) %>%
  arrange(category, y) %>%
  group_by(category) %>%
  summarise(n=n(), .groups="drop")
y_breaks_between <- cumsum(y_levels$n) + 0.5

# 染色体边界与刻度
chr_ends <- chr_bin_df %>%
  group_by(chr) %>%
  summarise(end = max(x), start = min(x),
            mid = floor((min(x)+max(x))/2), .groups="drop")

# ---------- 绘图 ----------
p <- ggplot(cnv_plot_df,
            aes(x=x,
                y=interaction(category, y, sep=" | ", lex.order = TRUE),
                fill=val)) +
  geom_tile(width=1, height=1) +
  scale_fill_gradient2(low="#0a2091ff", mid="white", high="#9f200fff",
                       midpoint=0, limits=c(-opt$cap, opt$cap),
                       name=legend_title) +
  # 染色体边界
  geom_vline(xintercept = chr_ends$end + 0.5, size=0.4) +
  scale_x_continuous(breaks = chr_ends$mid,
                     labels = as.character(chr_ends$chr),
                     expand=c(0,0)) +
  labs(x="Chromosome", y=NULL) +
  theme_minimal(base_size = 11) +
  theme(
    axis.text.y.right = element_text(size=9),
    axis.text.y = element_blank(),
    axis.ticks.y = element_blank(),
    panel.grid = element_blank(),
    legend.position = "right",
    plot.margin = margin(5,5,5,5)
  ) +
  scale_y_discrete(position = "right")

# 分类块的粗横线与左侧大标签
# 计算每个块的 y 范围
ylab_df <- cnv_plot_df %>%
  distinct(category, y) %>%
  arrange(category, y) %>%
  group_by(category) %>%
  summarise(ymin=first(y), ymax=last(y), .groups="drop")

# 转换到数值位置
y_all_levels <- levels(interaction(cnv_plot_df$category,
                                   cnv_plot_df$y,
                                   sep=" | ", lex.order = TRUE))

ylab_df <- ylab_df %>%
  mutate(ymin_id = match(paste0(category," | ", ymin), y_all_levels),
         ymax_id = match(paste0(category," | ", ymax), y_all_levels),
         ymid = (ymin_id + ymax_id)/2)

# 添加分隔线
for (b in y_breaks_between[-length(y_breaks_between)]) {
  p <- p + annotate("segment", x=-Inf, xend=Inf, y=b, yend=b, size=0.6)
}
# 左侧大标签（用注释文本）
p <- p + annotate("text",
                  x=min(chr_bin_df$x)-0.02*max(chr_bin_df$x),
                  y=ylab_df$ymid,
                  label=ylab_df$category,
                  hjust=1, size=4)

# ---------- 输出 ----------
ggsave(paste0(opt$out, ".pdf"), p, width=opt$width, height=opt$height, units="in")
ggsave(paste0(opt$out, ".png"), p, width=opt$width, height=opt$height, units="in", dpi=300)

# 同步保存用于下游的分箱矩阵
write_tsv(cnv_plot_df %>% select(category, sample_id, chr, bin, x, val),
          paste0(opt$out, ".binned.tsv"))

message("Done. Figure: ", opt$out, ".pdf / .png ;  Binned table: ", opt$out, ".binned.tsv")
