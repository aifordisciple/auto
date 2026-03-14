#!/usr/bin/env Rscript
# Seurat对象基因平均表达量导出脚本
# 支持从命令行参数指定输入输出文件路径

# Rscript /Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/sc_avg_export.r -i cells_analysis.rds &


# 加载必要的包
suppressPackageStartupMessages({
  library(Seurat)
  library(dplyr)
  library(tidyr)
  library(optparse)
})

# 设置命令行参数
option_list <- list(
  make_option(c("-i", "--input"), type="character", default=NULL,
              help="输入Seurat RDS文件路径 [必需]", metavar="file"),
  make_option(c("-o", "--output_dir"), type="character", default="output_expression_tables",
              help="输出目录 [默认: %default]", metavar="dir"),
  make_option(c("-a", "--assay"), type="character", default="RNA",
              help="使用的assay名称 [默认: %default]", metavar="assay"),
  make_option(c("-s", "--slot"), type="character", default="data",
              help="使用的数据槽 (counts/data/scale.data) [默认: %default]", metavar="slot"),
  make_option(c("--custom_class"), type="character", default="customclassif",
              help="自定义分类列名 [默认: %default]", metavar="column"),
  make_option(c("--group_col"), type="character", default="group",
              help="分组列名 [默认: %default]", metavar="column"),
  make_option(c("--cluster_col"), type="character", default="seurat_clusters",
              help="聚类列名 [默认: %default]", metavar="column"),
  make_option(c("--min_cells"), type="integer", default=1,
              help="每组最少细胞数阈值 [默认: %default]", metavar="number")
)

# 解析参数
opt_parser <- OptionParser(option_list=option_list, 
                          description="从Seurat RDS文件导出基因平均表达量表格",
                          epilogue="示例: Rscript seurat_export.R -i seurat_obj.rds -o results --assay RNA --slot data")
opt <- parse_args(opt_parser)

# 检查必要参数
if (is.null(opt$input)) {
  print_help(opt_parser)
  stop("必须指定输入RDS文件路径!", call.=FALSE)
}

# 创建输出目录
if (!dir.exists(opt$output_dir)) {
  dir.create(opt$output_dir, recursive = TRUE)
  cat("创建输出目录:", opt$output_dir, "\n")
}

# 函数：检查元数据列是否存在
check_metadata_columns <- function(seurat_obj, required_cols) {
  missing_columns <- setdiff(required_cols, colnames(seurat_obj@meta.data))
  if (length(missing_columns) > 0) {
    stop("以下必需的元数据列不存在: ", paste(missing_columns, collapse = ", "), "\n",
         "可用的元数据列有: ", paste(colnames(seurat_obj@meta.data), collapse = ", "))
  }
  
  # 检查是否有有效数据
  for (col in required_cols) {
    if (sum(!is.na(seurat_obj@meta.data[[col]])) == 0) {
      warning("列 '", col, "' 全部为NA或空值，请检查元数据")
    }
  }
}

# 函数：计算平均表达量并保存为TSV
calculate_avg_expression <- function(seurat_obj, group_vars, output_prefix, 
                                    assay = "RNA", slot = "data", min_cells = 10) {
  
  # 创建组合分组列
  group_comb <- apply(seurat_obj@meta.data[, group_vars, drop = FALSE], 1, 
                     function(x) paste(x, collapse = "_"))
  
  # 检查每组细胞数
  group_counts <- table(group_comb)
  small_groups <- names(group_counts)[group_counts < min_cells]
  
  if (length(small_groups) > 0) {
    cat("警告: 以下分组细胞数少于", min_cells, "个:\n")
    for (group in small_groups) {
      cat("  ", group, ": ", group_counts[group], "个细胞\n")
    }
  }
  
  # 将组合分组添加到元数据
  seurat_obj@meta.data$temp_group <- group_comb
  
  # 设置临时分组为细胞标识
  original_idents <- Idents(seurat_obj)
  Idents(seurat_obj) <- seurat_obj@meta.data$temp_group
  
  # 计算平均表达量
  cat("计算", paste(group_vars, collapse = "+"), "分组的平均表达量...\n")
  cat("使用assay:", assay, "slot:", slot, "\n")
  
  tryCatch({
    avg_expression <- AverageExpression(seurat_obj, 
                                        assays = assay,
                                        slot = slot,
                                        return.seurat = FALSE)
    
    # 提取指定assay的平均表达矩阵
    if (assay %in% names(avg_expression)) {
      avg_matrix <- avg_expression[[assay]]
    } else {
      stop("assay '", assay, "' 不在平均表达量结果中。可用的assay有: ", 
           paste(names(avg_expression), collapse = ", "))
    }
    
    avg_df <- as.data.frame(avg_matrix)
    
    # 添加基因名作为列
    avg_df$Gene <- rownames(avg_matrix)
    
    # 重新排列列，将Gene放在第一列
    avg_df <- avg_df[, c("Gene", setdiff(colnames(avg_df), "Gene"))]
    
    # 按基因名排序
    avg_df <- avg_df[order(avg_df$Gene), ]
    
    # 设置输出文件路径
    output_file <- file.path(opt$output_dir, 
                            paste0(output_prefix, "_average_expression.tsv"))
    
    # 保存为TSV文件
    write.table(avg_df, file = output_file, sep = "\t", 
                quote = FALSE, row.names = FALSE, col.names = TRUE)
    
    cat("结果已保存到:", output_file, "\n")
    cat("矩阵维度:", nrow(avg_df), "基因 ×", ncol(avg_df)-1, "个分组\n")
    
    return(avg_df)
    
  }, error = function(e) {
    stop("计算平均表达量时出错: ", e$message)
  }, finally = {
    # 恢复原始细胞标识
    Idents(seurat_obj) <- original_idents
    # 删除临时分组列
    seurat_obj@meta.data$temp_group <- NULL
  })
}

# 主函数
main <- function() {
  cat("=== Seurat基因平均表达量导出脚本 ===\n")
  cat("输入文件:", opt$input, "\n")
  cat("输出目录:", opt$output_dir, "\n")
  cat("参数设置: assay =", opt$assay, "slot =", opt$slot, "\n")
  cat("分组列: custom =", opt$custom_class, "group =", opt$group_col, 
      "cluster =", opt$cluster_col, "\n\n")
  
  # 读取Seurat对象
  cat("1. 读取Seurat对象...\n")
  if (!file.exists(opt$input)) {
    stop("输入文件不存在: ", opt$input)
  }
  
  seurat_obj <- readRDS(opt$input)
  cat("   读取成功! 细胞数:", ncol(seurat_obj), "基因数:", nrow(seurat_obj), "\n")
  
  # 检查assay是否存在
  if (!opt$assay %in% names(seurat_obj@assays)) {
    stop("assay '", opt$assay, "' 不存在。可用的assay有: ", 
         paste(names(seurat_obj@assays), collapse = ", "))
  }
  
  # 检查必需的元数据列
  required_columns <- c(opt$custom_class, opt$group_col, opt$cluster_col)
  check_metadata_columns(seurat_obj, required_columns)
  
  # 计算按照customclassif+group分组的平均表达量
  cat("\n2. 计算", opt$custom_class, "+", opt$group_col, "分组平均表达量\n")
  tryCatch({
    custom_group_avg <- calculate_avg_expression(
      seurat_obj, 
      c(opt$custom_class, opt$group_col), 
      paste0(opt$custom_class, "_", opt$group_col),
      assay = opt$assay,
      slot = opt$slot,
      min_cells = opt$min_cells
    )
  }, error = function(e) {
    cat("   错误:", e$message, "\n")
  })
  
  # 计算按照seurat_clusters+group分组的平均表达量
  cat("\n3. 计算", opt$cluster_col, "+", opt$group_col, "分组平均表达量\n")
  tryCatch({
    cluster_group_avg <- calculate_avg_expression(
      seurat_obj, 
      c(opt$cluster_col, opt$group_col), 
      paste0(opt$cluster_col, "_", opt$group_col),
      assay = opt$assay,
      slot = opt$slot,
      min_cells = opt$min_cells
    )
  }, error = function(e) {
    cat("   错误:", e$message, "\n")
  })
  
  # 生成分组汇总信息
  cat("\n4. 分组汇总信息:\n")
  cat("   customclassif+group 组合:\n")
  custom_combinations <- unique(seurat_obj@meta.data[, c(opt$custom_class, opt$group_col)])
  print(custom_combinations)
  
  cat("   seurat_clusters+group 组合:\n")
  cluster_combinations <- unique(seurat_obj@meta.data[, c(opt$cluster_col, opt$group_col)])
  print(cluster_combinations)
  
  # 保存会话信息
  session_file <- file.path(opt$output_dir, "session_info.txt")
  sink(session_file)
  print(sessionInfo())
  cat("\n运行参数:\n")
  print(opt)
  sink()
  
  cat("\n=== 处理完成 ===\n")
  cat("输出文件保存在目录:", opt$output_dir, "\n")
  cat("会话信息已保存到:", session_file, "\n")
  
  # 显示最终统计信息
  cat("\n最终统计:\n")
  cat("总细胞数:", ncol(seurat_obj), "\n")
  cat("总基因数:", nrow(seurat_obj), "\n")
  cat("分组列概况:\n")
  cat("  ", opt$custom_class, "唯一值:", length(unique(seurat_obj@meta.data[[opt$custom_class]])), "\n")
  cat("  ", opt$group_col, "唯一值:", length(unique(seurat_obj@meta.data[[opt$group_col]])), "\n")
  cat("  ", opt$cluster_col, "唯一值:", length(unique(seurat_obj@meta.data[[opt$cluster_col]])), "\n")
}

# 运行主函数
tryCatch({
  main()
}, error = function(e) {
  cat("脚本执行失败:", e$message, "\n")
  quit(status = 1)
})