#############################################################################
#                    0. 环境准备与包加载
#############################################################################
# 请确保已安装以下R包 (infercnv安装参见官方Github):
# install.packages(c("tidyverse", "ComplexHeatmap", "circlize",
#                    "umap", "cluster", "Rtsne", "ggplot2"))


library(tidyverse)
library(ComplexHeatmap)
library(circlize)
library(ggplot2)
library(umap)
library(cluster)
library(igraph)
library(RANN)



suppressPackageStartupMessages(library(optparse))      ## Options

## 参数读取
option_list <- list(
    make_option(
        c("-s","--signal"),
        action = "store",
        type = "numeric",
        default = 0.7,
        help = "cna_signal_threshold"
    )
)
opt <- parse_args(OptionParser(option_list = option_list))


#############################################################################
#          1. 读取 infercnv 输出: references & observations
#############################################################################
infercnv_dir <- "infercnv_results/"   # 这里需替换为实际路径
ref_file <- file.path(infercnv_dir, "infercnv.references.txt")
obs_file <- file.path(infercnv_dir, "infercnv.observations.txt")

# 如果ref中掺杂的癌细胞较多，cna_signal_threshold要求可以放松一点
# cna_signal_threshold <- 0.99
cna_signal_threshold <- opt$signal

# 1.1 读取矩阵, 行是基因/窗口, 列是细胞
ref_mat <- read.table(ref_file, header=TRUE, row.names=1, sep=" ", check.names=FALSE)
obs_mat <- read.table(obs_file, header=TRUE, row.names=1, sep=" ", check.names=FALSE)

# 1.2 行对齐(基因)
common_genes <- intersect(rownames(ref_mat), rownames(obs_mat))
ref_mat <- ref_mat[common_genes, , drop=FALSE]
obs_mat <- obs_mat[common_genes, , drop=FALSE]

# 合并
cnv_mat <- cbind(ref_mat, obs_mat)
cat("Dim of combined matrix = ", dim(cnv_mat), "\n")

# 1.3 给细胞打标签: 参考 vs. 观察
ref_cells <- colnames(ref_mat)
obs_cells <- colnames(obs_mat)
cell_type <- rep("Reference", ncol(cnv_mat))
names(cell_type) <- colnames(cnv_mat)
cell_type[obs_cells] <- "Observation"

#############################################################################
#        2. 将矩阵转换为 (cna_val = cnv_mat - 1)
#           使得 0 表示无变异, >0 扩增, <0 缺失
#############################################################################
cna_val <- cnv_mat - 1

#############################################################################
#   3. 计算CNA signal (top 2/3) & CNA correlation (top 25%)
#############################################################################

## 3.1 对每个细胞计算 CNA signal
#     方法: 按绝对值对所有基因排序, 仅取 top 2/3, 对它们的 |CNA| 取平均
calc_cna_signal <- function(x, top_frac=2/3){
  # x: 某细胞在全部基因上的 cna_val 向量
  # 按绝对值排序
  n <- length(x)
  rank_idx <- order(abs(x), decreasing = TRUE)
  top_n <- ceiling(n * top_frac)
  top_idx <- rank_idx[seq_len(top_n)]
  mean(abs(x[top_idx]))
}

# 对所有细胞执行:
cna_signal_vec <- apply(cna_val, 2, calc_cna_signal, top_frac=2/3)

## 3.2 选取 "Observation" 细胞中 cna_signal 最高的25% 作为恶性参考
#     先仅针对上皮/观察细胞(若您有更精确上皮标注, 可在此替换)
df_obs <- data.frame(Cell=obs_cells, cna_signal=cna_signal_vec[obs_cells])
thr_25pct <- quantile(df_obs$cna_signal, 0.75)   # 75分位
top_obs <- df_obs$Cell[ df_obs$cna_signal >= thr_25pct ]

# 计算 "恶性参考" 的平均 cna_val 向量
#   文献中并未指定 这里是否也取 top 2/3 基因,
#   一般做法是直接对所有基因(或窗口)做平均, 以保持一致性
mal_ref_profile <- rowMeans(cna_val[, top_obs, drop=FALSE])

## 3.3 对每个细胞计算 CNA correlation
calc_cna_corr <- function(x, ref_profile){
  if (sd(x) == 0 || sd(ref_profile) == 0) {
    return(NA)  # 避免标准差为零导致 Pearson 计算失败
  }
  cor(x, ref_profile, method="pearson", use="complete.obs")
}
cna_corr_vec <- apply(cna_val, 2, calc_cna_corr, ref_profile=mal_ref_profile)

#############################################################################
#   4. 根据文献: 利用参考细胞(基质/非肿瘤)的分布, 确定threshold
#      “cutoffs were set so that <1% of stromal reference cells pass each threshold”
#############################################################################
# 4.1 获取参考细胞(Reference)在 cna_signal, cna_corr 上的分布
df_ref <- data.frame(Cell=ref_cells,
                     cna_signal=cna_signal_vec[ref_cells],
                     cna_corr=cna_corr_vec[ref_cells])

# 过滤掉 NA / NaN
df_ref <- df_ref[!is.na(df_ref$cna_corr) & !is.nan(df_ref$cna_corr), ]

# 让 <1% 的 reference 通过 => 取 reference在 cna_signal/cna_corr 的 99% 分位
# signal_thr <- quantile(df_ref$cna_signal, 0.99, na.rm=TRUE)

# 如果ref中掺杂的癌细胞较多，cna_signal要求可以放松一点
signal_thr <- quantile(df_ref$cna_signal, cna_signal_threshold, na.rm=TRUE)

corr_thr   <- quantile(df_ref$cna_corr, 0.99, na.rm=TRUE)

cat("signal_thr =", signal_thr, "\n")
cat("corr_thr   =", corr_thr, "\n")
# 您也可做更灵活的调试, 确保仅极少数 reference 超过这俩阈值

#############################################################################
#   5. 根据 threshold 判断: 同时高 => malignant; 同时低 => nonmalig; 否则 => unresolved
#############################################################################
# 我们主要对"Observation"细胞做此划分, Reference保留"Reference"
cell_call <- rep("Reference", ncol(cna_val))
names(cell_call) <- colnames(cna_val)

for(obs_cell in obs_cells){
  sigval <- cna_signal_vec[obs_cell]
  corrval<- cna_corr_vec[obs_cell]

  # 检查是否存在缺失值
  if (is.na(sigval) || is.na(corrval)) {
    cell_call[obs_cell] <- "Unresolved"
    next  # 跳过后续判断
  }

  # 同时超过 => malignant
  if(sigval > signal_thr & corrval > corr_thr){
    cell_call[obs_cell] <- "Malignant"
  }
  # 同时没超过 => nonmalig
  else if(sigval < signal_thr & corrval < corr_thr){
    cell_call[obs_cell] <- "NonMalignant"
  }
  # 否则 => unresolved
  else{
    cell_call[obs_cell] <- "Unresolved"
  }
}

table(cell_call)
write.table(table(cell_call), file="cell_malignant_calls_updated.stat.txt",
            sep="\t", row.names=FALSE, quote=FALSE)

df_calls <- data.frame(
  Cell=colnames(cna_val),
  Cell_Type=cell_type,  # Reference vs Observation
  CNA_signal=cna_signal_vec[colnames(cna_val)],
  CNA_corr=cna_corr_vec[colnames(cna_val)],
  Final_Call=cell_call
)
write.table(df_calls, file="cell_malignant_calls_updated.txt",
            sep="\t", row.names=FALSE, quote=FALSE)

#############################################################################
#   6. 画散点图 (cna_corr vs cna_signal), 展示分类
#############################################################################
# 先把 ggplot 对象保存到 p，这样便于同时输出 PDF 和 PNG
p <- ggplot(df_calls, aes(x=CNA_corr, y=CNA_signal, color=Final_Call)) +
  geom_point(size=2, alpha=0.8) +
  theme_bw() +
  theme(panel.grid=element_blank()) +
  labs(x="CNA correlation", y="CNA signal", color="Cell call") +
  scale_color_manual(values=c("Reference"="gray70",
                              "NonMalignant"="green3",
                              "Malignant"="red",
                              "Unresolved"="orange"))

# 输出 PDF
pdf("CNA_signal_vs_corr.pdf", width=5, height=4)
print(p)
dev.off()

# 输出 PNG (300 dpi, 单位为英寸)
png("CNA_signal_vs_corr.png", width=5, height=4, units="in", res=300)
print(p)
dev.off()

#############################################################################
#   7. 示例热图, 按照恶性/非恶性分类对列做分组
#############################################################################
library(ComplexHeatmap)
library(circlize)

#------------------------------
# 1) 转置矩阵，使 row=细胞, col=基因
#------------------------------
mat_t <- t(as.matrix(cna_val))
# 原先 cna_val 行=基因, 列=细胞
# 现在 mat_t 的行=原列(即细胞), 列=原行(基因)

#------------------------------
# 2) 准备分组因子 row_split
#   (行分组, 因为现在行是细胞)
#------------------------------
col_split <- factor(cell_call,
                    levels=c("Reference","NonMalignant","Malignant","Unresolved"))

#------------------------------
# 3) 构建行注释 (rowAnnotation)
#   让每个细胞在行方向有一个颜色标签
#------------------------------
ha_row <- rowAnnotation(
  Cell_Call = col_split,  # 要注释的列名
  col = list(Cell_Call = c(
    "Reference"    = "gray70",
    "NonMalignant" = "green3",
    "Malignant"    = "red",
    "Unresolved"   = "orange"
  ))
)

#------------------------------
# 4) Heatmap 设置:
#   - row_split=col_split 在行方向进行分组
#   - left_annotation=ha_row 将注释放在左侧
#   - 基因顺序在列方向 => cluster_columns=FALSE 表示不聚类基因(保留顺序)
#   - 不对细胞进行聚类 => cluster_rows=FALSE
#   - show_row_names=TRUE/FLASE 控制是否显示细胞名
#   - show_column_names=TRUE/FLASE 控制是否显示基因名
#------------------------------
min_val <- min(mat_t)
max_val <- max(mat_t)
col_fun <- colorRamp2(c(min_val,0,max_val), c("blue","white","red"))

ht_t <- Heatmap(
  mat_t,           # 行=细胞, 列=基因
  name = "CNA",
  col  = col_fun,

  # 行分组 (每个组对应不同细胞类型)
  row_split = col_split,
  # 行注释
  left_annotation = ha_row,
  use_raster=FALSE,

  # 不聚类基因
  cluster_columns = FALSE,
  # 不聚类细胞
  cluster_rows = FALSE,

  # 隐藏行列名
  show_row_names    = FALSE,
  show_column_names = FALSE
)

#------------------------------
# 5) 输出 PDF
#------------------------------
pdf("CNA_heatmap_transposed.pdf", width=8, height=5)
draw(ht_t)
dev.off()

#------------------------------
# 6) 输出 PNG (300 dpi, 单位为英寸)
#------------------------------
png("CNA_heatmap_transposed.png", width=8, height=5, units="in", res=300)
draw(ht_t)
dev.off()

cat("=== 转置热图输出完成 ===\n")

#############################################################################
#   8. 单个样本的亚克隆识别 (参考文献: 过度聚类后合并)
#############################################################################

#  8.1 读取基因-> 染色体 文件
gene2chr_file <- "/opt/data1/public/genome/human/annotation/gencode_v38/human_gene_pos.txt"
gene_chr_map  <- read.table(gene2chr_file, header=FALSE, sep="\t", stringsAsFactors=FALSE)
colnames(gene_chr_map) <- c("Gene","Chr","Start","End")
gene_chr_map$ChrAll <- gene_chr_map$Chr
chr_df <- gene_chr_map[, c("Gene","ChrAll")]
rownames(chr_df) <- chr_df$Gene

# 8.2 过滤基因(绝对值top2/3)
mal_cells <- names(cell_call)[cell_call=="Malignant"]
cat("Malignant cells:", length(mal_cells), "\n")
if(length(mal_cells)<10){
  cat("恶性细胞过少, 无法进行亚克隆识别.\n")
}

# 8.3 过滤基因(绝对值top2/3)
filter_genes_top_fraction <- function(mat, top_frac=2/3) {
  gene_var <- apply(mat, 1, function(x) mean(abs(x)))
  idx <- order(gene_var, decreasing=TRUE)
  keep_n <- ceiling(length(idx)*top_frac)
  keep_idx <- idx[seq_len(keep_n)]
  mat[keep_idx, , drop=FALSE]
}
sub_mat <- cna_val[, mal_cells, drop=FALSE]
sub_mat_filt <- filter_genes_top_fraction(sub_mat, top_frac=2/3)

# 3.2 UMAP + Louvain(k=15) => 过度聚类
run_umap <- function(mat, n_neighbors=15, min_dist=0.3){
  mat_t_ <- t(mat)
  set.seed(2023)
  ures <- umap(mat_t_, n_neighbors=n_neighbors, min_dist=min_dist)
  data.frame(
    UMAP1 = ures$layout[,1],
    UMAP2 = ures$layout[,2],
    Cell  = rownames(ures$layout)
  )
}

louvain_overcluster <- function(umap_df, k=15){
  coords <- umap_df[, c("UMAP1","UMAP2")]
  rownames(coords) <- umap_df$Cell
  nn_res <- nn2(coords, k=k)
  edges <- list()
  for(i in seq_len(nrow(coords))){
    src <- rownames(coords)[i]
    for(j in nn_res$nn.idx[i,]){
      if(j==0 || j==i) next
      tgt <- rownames(coords)[j]
      edges <- append(edges, list(c(src,tgt)))
    }
  }
  edges_vec <- unlist(edges)
  g <- graph(edges_vec, directed=FALSE)
  clust <- cluster_louvain(g)
  membership_vec <- membership(clust)
  data.frame(Cell=names(membership_vec), OverClust_ID=membership_vec)
}

umap_df <- run_umap(sub_mat_filt, n_neighbors=15, min_dist=0.3)
over_df <- louvain_overcluster(umap_df, k=15)

# 3.3 合并小簇 (<10)
merge_small_clusters <- function(umap_df, over_df, min_size=10){
  size_tb <- table(over_df$OverClust_ID)
  small_ids<- names(size_tb)[size_tb<min_size]
  if(length(small_ids)==0) return(over_df)

  df_all <- left_join(over_df, umap_df, by="Cell")
  coords_mat <- as.matrix(df_all[,c("UMAP1","UMAP2")])
  rownames(coords_mat) <- df_all$Cell
  ncell <- nrow(coords_mat)
  k_knn <- max(2, ceiling(log(ncell)))

  df_new <- over_df
  for(cid in small_ids){
    sm_cells <- df_all$Cell[df_all$OverClust_ID==cid]
    for(sc in sm_cells){
      sc_xy <- coords_mat[sc,,drop=FALSE]
      knn_res <- nn2(coords_mat, sc_xy, k=k_knn)
      idx_vec <- knn_res$nn.idx[1,]
      for(idx in idx_vec){
        tgt_cell <- rownames(coords_mat)[idx]
        tgt_clust<- df_all$OverClust_ID[df_all$Cell==tgt_cell]
        if(! tgt_clust %in% small_ids){
          df_new$OverClust_ID[df_new$Cell==sc] <- tgt_clust
          break
        }
      }
    }
  }
  df_new
}

merged_small <- merge_small_clusters(umap_df, over_df, min_size=10)

#############################################################################
# 3.4 计算每聚类在chrAll上的平均CNA (OverClust_ID -> ChrAll -> avgCNA)
#############################################################################
assign_chr_calls <- function(mat_cna, cluster_df, chr_df, del_thr=-0.15, amp_thr=0.15){
  out_list <- list()
  for(cid in unique(cluster_df$OverClust_ID)){
    c_cells <- cluster_df$Cell[cluster_df$OverClust_ID==cid]
    if(length(c_cells)<1) next
    subm <- mat_cna[, c_cells, drop=FALSE]
    gene_means <- rowMeans(subm)
    df_tmp <- data.frame(Gene=names(gene_means), avgCNA=gene_means) %>%
      left_join(chr_df, by="Gene") %>%
      group_by(ChrAll) %>%
      summarise(avgCNA=mean(avgCNA, na.rm=TRUE), .groups="drop") %>%
      mutate(
        OverClust_ID = cid,
        call = case_when(
          avgCNA< del_thr ~ "Del",
          avgCNA> amp_thr ~ "Amp",
          TRUE            ~ "Neutral"
        )
      )
    out_list[[as.character(cid)]] <- df_tmp
  }
  bind_rows(out_list)
}

thr = as.numeric(signal_thr)

chr_calls_df <- assign_chr_calls(sub_mat_filt, merged_small, chr_df,
                                 del_thr=-thr, amp_thr=thr)

#############################################################################
# 3.5 多轮合并(计算new avgCNA)，并实时更新细胞层面的 OverClust_ID
#############################################################################
merge_clusters_by_chr_pattern_iterative <- function(df_chr_calls, cluster_df,
                                                    diff_thr=0.15, max_iter=50){
  # df_chr_calls: (ChrAll, avgCNA, OverClust_ID, ...)
  # cluster_df : (Cell, OverClust_ID) 需与 df_chr_calls 同步更新
  # diff_thr   : 如果2个簇在所有chr的最大差< diff_thr => 合并
  # 多轮迭代: 每次合并后 => 重新计算 new average => 再比较

  df_chr_calls$OverClust_ID <- as.character(df_chr_calls$OverClust_ID)
  cluster_df$OverClust_ID   <- as.character(cluster_df$OverClust_ID)

  recalc_avgCNA <- function(df){
    df %>%
      group_by(OverClust_ID, ChrAll) %>%
      summarise(avgCNA=mean(avgCNA,na.rm=TRUE), .groups="drop")
  }
  build_cluster_vectors <- function(df){
    out <- list()
    for(cid in unique(df$OverClust_ID)){
      sub <- df[df$OverClust_ID==cid, ]
      vec <- tibble::deframe(sub[, c("ChrAll","avgCNA")])
      out[[cid]] <- vec
    }
    out
  }

  # 首次 ensure group
  df_chr_calls <- recalc_avgCNA(df_chr_calls)

  iter <- 0
  changed <- TRUE

  while(changed && iter<max_iter){
    iter <- iter+1
    changed <- FALSE

    cluster_ids <- sort(unique(df_chr_calls$OverClust_ID))
    if(length(cluster_ids)<=1) break
    clust_avgs  <- build_cluster_vectors(df_chr_calls)

    merges_happened <- FALSE
    cluster_map <- setNames(cluster_ids, cluster_ids) # old->new

    for(i in seq_along(cluster_ids)){
      for(j in seq(i+1, length(cluster_ids))){
        cid_i <- cluster_ids[i]
        cid_j <- cluster_ids[j]
        val_i <- cluster_map[cid_i]
        val_j <- cluster_map[cid_j]
        if(is.na(val_i) || is.na(val_j)) next
        if(val_i == val_j) next
        vec_i <- clust_avgs[[cid_i]]
        vec_j <- clust_avgs[[cid_j]]
        if(is.null(vec_i)||is.null(vec_j)) next
        all_chr <- union(names(vec_i), names(vec_j))
        diff_ij <- abs(vec_i[all_chr]-vec_j[all_chr])
        if(all(is.na(diff_ij))) next
        if(max(diff_ij, na.rm=TRUE)< diff_thr){
          merges_happened <- TRUE
          old_i <- cluster_map[cid_i]
          old_j <- cluster_map[cid_j]
          new_id<- as.character(min(as.numeric(old_i), as.numeric(old_j)))

          # map old_i & old_j => new_id
          for(k in names(cluster_map)){
            if(cluster_map[k]==old_i || cluster_map[k]==old_j){
              cluster_map[k]<- new_id
            }
          }
        }
      }
    }

    if(merges_happened){
      changed <- TRUE
      # 更新 df_chr_calls & cluster_df
      for(cid in names(cluster_map)){
        old_id <- cid
        new_id <- cluster_map[[cid]]
        df_chr_calls$OverClust_ID[df_chr_calls$OverClust_ID==old_id] <- new_id
        cluster_df$OverClust_ID[cluster_df$OverClust_ID==old_id]     <- new_id
      }
      # 重新计算 avgCNA
      df_chr_calls <- recalc_avgCNA(df_chr_calls)
    } else {
      changed <- FALSE
    }
  }

  if(iter==max_iter){
    message("Reached max_iter, might not have fully converged.")
  }

  list(df_chr_calls=df_chr_calls, cluster_df=cluster_df)
}

merged_res <- merge_clusters_by_chr_pattern_iterative(chr_calls_df,
                                                      merged_small,
                                                      diff_thr=thr, max_iter=50)

chr_calls_final <- merged_res$df_chr_calls
cluster_df_fin  <- merged_res$cluster_df
# cluster_df_fin: (Cell, OverClust_ID) => 已是最终合并

# 给细胞添加子克隆名称
cluster_df_fin$Subclone <- paste0("C", cluster_df_fin$OverClust_ID)

#############################################################################
# 3.6 输出
#############################################################################
write.table(cluster_df_fin, "subclone_assignments.txt",
            sep="\t", row.names=FALSE, quote=FALSE)

cat("=== Done. Single-sample malignant calling + subclone identification, 
iterative merges with new average. ===\n")


#############################################################################
#   9. 绘制 subclone 热图（加入额外的 cell 注释）
#############################################################################

library(ComplexHeatmap)
library(circlize)
library(tidyverse)

## 9.0 读取用户提供的细胞注释 TSV 文件
# 假设这个文件包含列：Cell、Sample、Group、OtherInfo 等
annotation_file <- "cell_annotation.tsv"
df_cell_anno <- read.table(annotation_file, header = TRUE, sep = "\t", stringsAsFactors = FALSE)

# 确认读入的数据，例如：
# head(df_cell_anno)
#   Cell   Sample Group OtherInfo
# 1 cell1     S1     A      foo
# 2 cell2     S1     A      bar
# 3 cell3     S2     B      baz
# …

## 9.1 构建一个细胞信息表，用于给所有细胞打上最终的分组(subclone 或者其他) + 额外注释
df_subclone_anno <- data.frame(
  Cell = colnames(cna_val),
  Cell_Call = cell_call  # "Reference"/"NonMalignant"/"Malignant"/"Unresolved"
) %>%
  # 原先的 subclone 注释
  left_join(cluster_df_fin, by = "Cell") %>%
  # 额外合并用户提供的注释（可能包含 Sample、Group、OtherInfo 等列）
  left_join(df_cell_anno, by = "Cell")

# 至此，df_subclone_anno 大概包含下列列：
#   Cell, Cell_Call, OverClust_ID, Subclone, Sample, Group, OtherInfo

## 9.2 把 “非恶性/未定” 的 Subclone 置为特殊标记
df_subclone_anno <- df_subclone_anno %>%
  mutate(
    Final_Subclone = Subclone,
    Final_Subclone = case_when(
      Cell_Call == "Reference"    ~ "Reference",
      Cell_Call == "NonMalignant" ~ "NonMalig",
      Cell_Call == "Unresolved"   ~ "Unresolved",
      TRUE                        ~ as.character(Subclone)
    )
  )

## 9.3 将矩阵转置 (行 = 细胞, 列 = 基因)
mat_t_sub <- t(as.matrix(cna_val))  # now row=Cell, column=Gene

## 9.4 自定义行顺序 (先按照 Final_Subclone 排序)
sub_list <- unique(df_subclone_anno$Final_Subclone)
ordered_levels <- c("Reference", "NonMalig", "Unresolved",
                    sort(sub_list[grepl("^C", sub_list)]))
df_subclone_anno$Subclone_factor <- factor(df_subclone_anno$Final_Subclone,
                                           levels = ordered_levels)
df_subclone_anno <- df_subclone_anno %>%
  arrange(Subclone_factor)
ordered_cells <- df_subclone_anno$Cell

## 9.5 重排矩阵的行 (因为 row = Cell)
mat_t_sub <- mat_t_sub[ordered_cells, , drop = FALSE]

## 9.6 准备行注释的颜色映射
# 9.6.1 Subclone 颜色映射（和原来一样）
all_subclones <- levels(df_subclone_anno$Subclone_factor)
subclone_colors <- c("Reference" = "gray70",
                     "NonMalig"  = "green3",
                     "Unresolved"= "orange")
# 对“C1”、“C2”...的自动配色
other_cs <- setdiff(all_subclones, c("Reference", "NonMalig", "Unresolved"))
mycolor_1 <- c("#0072B2","#CC79A7","#009E73","#F0E442","#5d8ac4",
               "#f39659","#936355","#999999","#E69F00","#56B4E9",
               "#D55E00","#FCFBFD","#EFEDF5","#DADAEB","#BCBDDC",
               "#9E9AC8","#807DBA","#6A51A3","#54278F","#3F007D")
col_vec <- mycolor_1[seq_len(length(other_cs))]
names(col_vec) <- other_cs
subclone_colors <- c(subclone_colors, col_vec)

# 9.6.2 Sample 颜色映射（假设 df_subclone_anno$Sample 中有 "S1","S2",...）
sample_levels <- unique(df_subclone_anno$Sample)
# 这里我们再随机选一组颜色，也可以手动指定
sample_colors <- setNames(
  structure(mycolor_1[seq_along(sample_levels)], names = sample_levels),
  sample_levels
)

# 9.6.3 Group 颜色映射（假设 df_subclone_anno$Group 中有 "A","B","C",...）
group_levels <- unique(df_subclone_anno$Group)
# 同样用 mycolor_1 的前几个或自己定制
group_colors <- setNames(
  structure(mycolor_1[seq_along(group_levels)], names = group_levels),
  group_levels
)

## 9.7 构建 rowAnnotation，把所有注释都放进去
ha_row2 <- rowAnnotation(
  Subclone = df_subclone_anno$Subclone_factor,
  Sample   = factor(df_subclone_anno$Sample, levels = sample_levels),
  Group    = factor(df_subclone_anno$Group, levels = group_levels),
  col = list(
    Subclone = subclone_colors,
    Sample   = sample_colors,
    Group    = group_colors
  ),
  annotation_legend_param = list(
    Subclone = list(title = "Subclone"),
    Sample   = list(title = "Sample"),
    Group    = list(title = "Group")
  )
)

## 9.8 定义 CNA 的配色
min_val <- min(cna_val)
max_val <- max(cna_val)
col_fun <- colorRamp2(c(min_val, 0, max_val), c("blue", "white", "red"))

## 9.9 绘制 Heatmap，同时添加行注释
ht_sub <- Heatmap(
  mat_t_sub,
  name           = "CNA",
  col            = col_fun,
  use_raster     = FALSE,
  row_split      = df_subclone_anno$Subclone_factor,
  left_annotation= ha_row2,
  cluster_rows   = FALSE,
  cluster_columns= FALSE,
  show_row_names = FALSE,
  show_column_names = FALSE
)

## 9.10 输出 PDF
pdf("subclone_CNA_heatmap_withAnno.pdf", width = 10, height = 7)
draw(ht_sub, heatmap_legend_side = "right", annotation_legend_side = "right")
dev.off()

## 9.11 输出 PNG (300 dpi)
png("subclone_CNA_heatmap_withAnno.png", width = 10, height = 7, units = "in", res = 300)
draw(ht_sub, heatmap_legend_side = "right", annotation_legend_side = "right")
dev.off()

cat("=== 带额外注释的 subclone_CNA_heatmap 输出完成 ===\n")
