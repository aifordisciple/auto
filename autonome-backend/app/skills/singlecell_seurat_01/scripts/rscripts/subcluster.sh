#!/usr/bin/env python3
"""
从整合 Seurat RDS 自动生成“某些细胞大类子集重聚类 + 亚型分析”的 Shell Pipeline。

功能要点
- 输入：
  - --project_dir    子聚类分析输出总目录
  - --main_rds       整合后的主 Seurat RDS（通常是 cells_analysis.rds）
  - --subset_tag     子集标签，如 Fibr（会生成 cell_celltype.Fibr.rds）
  - --celltypes      细胞大类列表，逗号分隔，传给 RDS_filter.r 的 -c
  - --contrast       差异分析对比，如 full_21d:half_21d
- 自动在生成的 shell 中完成：
  1) 链接主 RDS
  2) 基于细胞大类提取子集 RDS（cell_celltype.<tag>.rds）
  3) 用 sc_meta_export.r 生成 meta.txt
  4) 从 meta.txt 中抽取 group / replicate（默认使用第 5 列=group，第 6 列=replicate）
     - 得到 meta_groups.tsv：两列 group replicate
  5) 自动构建：
     - SAMPLES：replicate 列，逗号拼接
     - GROUPS：group 列，逗号拼接（与 SAMPLES 一一对应）
     - FMT_LIST：与样本数相同的 sctrds 列表
     - BAM_LIST：project_dir/replicate.rds 列表
  6) 循环调用 RDS_filter.r -s replicate，批量生成每个样本的子集 RDS（带并行批大小）
  7) 调用 sc_preprocessing_v2.r / sc_cells_analysis_v2.r / sc_genes_analysis.r 等下游流程
  8) 利用 meta_groups.tsv 自动确定绘图时的 group 顺序 / sample 顺序（可选自定义）

用法示例
p3 subcluster.py \
  --project_dir /opt/data1/project/NBioS-2025-09003-D_Guhuazheng/figures/fig2/subcluster \
  --main_rds /opt/data1/project/NBioS-2025-09003-D_Guhuazheng/basic/scRNA/result/singlecell/2_cells_analysis/cells_analysis.rds \
  --subset_tag Fibr \
  --celltypes "Chondrocyte/Fibroblast,MSC/Fibroblast,Tendon/Fibroblast" \
  --contrast "full_21d:half_21d" \
  > subcluster_Fibr.sh
"""

import argparse
import os
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description="根据 Seurat RDS 生成子群重聚类 shell 脚本（自动从 meta.txt 抽取 group/replicate）"
    )

    parser.add_argument(
        "--project_dir",
        required=True,
        help="子聚类分析输出总目录，例如 /opt/data1/.../figures/fig2/subcluster"
    )
    parser.add_argument(
        "--main_rds",
        required=True,
        help="整合后的主 Seurat RDS 路径，例如 .../2_cells_analysis/cells_analysis.rds"
    )
    parser.add_argument(
        "--main_rds_name",
        default="cells_analysis.rds",
        help="在子目录中软链接后的 RDS 文件名，默认: cells_analysis.rds"
    )
    parser.add_argument(
        "--subset_tag",
        required=True,
        help="细胞大类子集标签，会用于生成 cell_celltype.<tag>.rds，例如 Fibr"
    )
    parser.add_argument(
        "--celltypes",
        required=True,
        help='细胞大类列表，逗号分隔，传给 RDS_filter.r 的 -c 参数，例如 "Chondrocyte/Fibroblast,MSC/Fibroblast"'
    )
    parser.add_argument(
        "--contrast",
        required=True,
        help='差异分析对比组，格式 "groupA:groupB"，如 "full_21d:half_21d"'
    )

    # meta.txt 中 group / replicate 列索引（1-based）
    parser.add_argument(
        "--group_col_index",
        type=int,
        default=5,
        help="meta.txt 中 group 列的列号（1-based），默认 5"
    )
    parser.add_argument(
        "--replicate_col_index",
        type=int,
        default=6,
        help="meta.txt 中 replicate 列的列号（1-based），默认 6"
    )

    # 并行控制：每批多少个样本同时跑 RDS_filter.r -s
    parser.add_argument(
        "--batch_size",
        type=int,
        default=8,
        help="按样本拆分 RDS 时每批并行任务数，默认 8"
    )

    # 可选：自定义 group / sample 排序（否则自动从 meta_groups.tsv 推）
    parser.add_argument(
        "--group_order",
        default="__AUTO__",
        help='自定义 group 排序，逗号分隔；默认 "__AUTO__" 表示从 meta_groups.tsv 自动推导'
    )
    parser.add_argument(
        "--sample_order",
        default="__AUTO__",
        help='自定义 sample 排序，逗号分隔；默认 "__AUTO__" 表示从 meta_groups.tsv 自动推导'
    )

    # 下面是脚本路径和关键参数（默认按你当前路径来，可以在命令行覆盖）
    parser.add_argument(
        "--rds_filter_script",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/tools/RDS_filter.r",
        help="RDS_filter.r 脚本路径"
    )
    parser.add_argument(
        "--sc_meta_export_script",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/tools/sc_meta_export.r",
        help="sc_meta_export.r 脚本路径"
    )
    parser.add_argument(
        "--sc_preprocessing_script",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/sc_preprocessing_v2.r",
        help="sc_preprocessing_v2.r 脚本路径"
    )
    parser.add_argument(
        "--sc_cells_analysis_script",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/sc_cells_analysis_v2.r",
        help="sc_cells_analysis_v2.r 脚本路径"
    )
    parser.add_argument(
        "--sc_plot_umap_script",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/tools/sc_plot_umap_new.r",
        help="sc_plot_umap_new.r 脚本路径"
    )
    parser.add_argument(
        "--sc_speckle_script",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/tools/sc_speckle.r",
        help="sc_speckle.r 脚本路径"
    )
    parser.add_argument(
        "--stat_markers_sh",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/stat_markers.sh",
        help="stat_markers.sh 路径"
    )
    parser.add_argument(
        "--markers_gokegg_sh",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/markers_gokegg.sh",
        help="markers_gokegg.sh 路径"
    )
    parser.add_argument(
        "--sc_genes_analysis_script",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/sc_genes_analysis.r",
        help="sc_genes_analysis.r 脚本路径"
    )
    parser.add_argument(
        "--stat_deg_sh",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/stat_deg.sh",
        help="stat_deg.sh 路径"
    )
    parser.add_argument(
        "--deg_gokegg_sh",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/deg_gokegg.sh",
        help="deg_gokegg.sh 路径"
    )
    parser.add_argument(
        "--stat_deg_byall_sh",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/stat_deg_byall.sh",
        help="stat_deg_byall.sh 路径"
    )
    parser.add_argument(
        "--deg_gokegg_byall_sh",
        default="/Users/chengchao/biosource/besaltpipe/src/SingleCell/pipeline/deg_gokegg_byall.sh",
        help="deg_gokegg_byall.sh 路径"
    )
    parser.add_argument(
        "--sctype_db_xlsx",
        default="/opt/data1/public/database/singlecell/sctype_marker_db.xlsx",
        help="sctype_marker_db.xlsx 路径，传给 sc_cells_analysis_v2.r"
    )
    parser.add_argument(
        "--sctype_db_txt",
        default="/opt/data1/public/database/singlecell/sctype_marker_db.txt",
        help="sctype_marker_db.txt 路径，用于 key marker UMAP"
    )
    parser.add_argument(
        "--sctype_tag",
        default="HO",
        help="sctype 数据库中当前小类对应的 tag（如 HO），用于提取 key marker"
    )
    parser.add_argument(
        "--go_anno",
        default="/opt/data1/public/genome/human/annotation/gencode_v47/human_godes_final.txt",
        help="GO/KEGG 注释文件路径，传给 *gokegg*.sh"
    )
    parser.add_argument(
        "--kegg_species",
        default="hsa",
        help="KEGG 物种缩写，例如 hsa / mmu 等"
    )

    # QC 及维度参数
    parser.add_argument(
        "--qc_mintotalumi",
        type=int,
        default=50000,
        help="sc_preprocessing_v2.r 的 --MinTotalUMI 参数，默认 50000"
    )
    parser.add_argument(
        "--qc_mingenes",
        type=int,
        default=500,
        help="sc_preprocessing_v2.r 的 --MinGenes 参数，默认 500"
    )
    parser.add_argument(
        "--qc_maxmt",
        type=float,
        default=20.0,
        help="sc_preprocessing_v2.r 的 --MaxMT 参数，默认 20"
    )
    parser.add_argument(
        "--qc_mincellsingene",
        type=int,
        default=1,
        help="sc_preprocessing_v2.r 的 --MinCellsInGene 参数，默认 1"
    )
    parser.add_argument(
        "--sc_method",
        default="sct_harmony",
        help="sc_preprocessing_v2.r 的 -m 方法参数，默认 sct_harmony"
    )
    parser.add_argument(
        "--batch_size_cells",
        type=int,
        default=20,
        help="sc_preprocessing_v2.r 的 --batchSize 参数，默认 20"
    )
    parser.add_argument(
        "--noparallel",
        default="false",
        help="sc_preprocessing_v2.r 的 --noparallel 参数，默认 false"
    )
    parser.add_argument(
        "--dims",
        type=int,
        default=50,
        help="sc_cells_analysis_v2.r 的 -d 维度数，默认 50"
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=0.8,
        help="sc_cells_analysis_v2.r 的 --resolution 参数，默认 0.8"
    )
    parser.add_argument(
        "--deg_dims",
        type=int,
        default=30,
        help="sc_genes_analysis.r 的 -d 参数，默认 30"
    )

    return parser.parse_args()


def main():
    opt = parse_args()

    project_dir = os.path.abspath(opt.project_dir)
    main_rds = os.path.abspath(opt.main_rds)
    main_rds_name = opt.main_rds_name
    subset_tag = opt.subset_tag
    celltypes = opt.celltypes
    contrast = opt.contrast

    subset_rds = f"cell_celltype.{subset_tag}.rds"
    sub_pre_dir = os.path.join(project_dir, "1_preprocessing")
    sub_cells_dir = os.path.join(project_dir, "2_cells_analysis")
    sub_genes_dir = os.path.join(project_dir, "3_genes_analysis")

    # 生成的 shell 内容
    out = []

    out.append("#!/bin/bash")
    out.append("set -euo pipefail")
    out.append("")
    out.append(f"PROJECT_DIR=\"{project_dir}\"")
    out.append(f"cd \"${{PROJECT_DIR}}\"")
    out.append("")
    out.append("# 链接主 RDS")
    out.append(f"ln -sf \"{main_rds}\" \"{main_rds_name}\"")
    out.append("")
    out.append("# 1) 按细胞大类提取子集 RDS")
    out.append(
        f"Rscript \"{opt.rds_filter_script}\" "
        f"-r \"{main_rds_name}\" -c \"{celltypes}\" -n \"{subset_tag}\""
    )
    out.append("")
    out.append("# 2) 导出子集 meta 信息（会生成 meta.txt）")
    out.append(
        f"Rscript \"{opt.sc_meta_export_script}\" -i \"{subset_rds}\""
    )
    out.append("")
    out.append("# 3) 从 meta.txt 中抽取 group / replicate 信息，生成 meta_groups.tsv")
    out.append(f"GROUP_COL_INDEX={opt.group_col_index}")
    out.append(f"REPLICATE_COL_INDEX={opt.replicate_col_index}")
    out.append(
        "awk -v gc=${GROUP_COL_INDEX} -v rc=${REPLICATE_COL_INDEX} "
        "'NR==1{next} {print $gc\"\\t\"$rc}' meta.txt | sort | uniq > meta_groups.tsv"
    )
    out.append("")
    out.append("# meta_groups.tsv: 两列 -> group  replicate")
    out.append("NSAMPLES=$(wc -l < meta_groups.tsv)")
    out.append('SAMPLES=$(cut -f2 meta_groups.tsv | paste -sd, -)')
    out.append('GROUPS=$(cut -f1 meta_groups.tsv | paste -sd, -)')
    out.append('FMT_LIST=$(yes sctrds | head -n "${NSAMPLES}" | paste -sd, -)')
    out.append(
        'BAM_LIST=$(awk -v dir="${PROJECT_DIR}" -v n="${NSAMPLES}" '
        "'{printf \"%s/%s.rds\",dir,$2; if (NR<n) printf \",\"; }' meta_groups.tsv)"
    )
    out.append("")
    out.append("# group / sample 排序（可选自定义，否则自动）")
    out.append(f"GROUP_ORDER=\"{opt.group_order}\"")
    out.append('if [ "${GROUP_ORDER}" = "__AUTO__" ]; then')
    out.append('  GROUP_ORDER=$(cut -f1 meta_groups.tsv | sort | uniq | paste -sd, -)')
    out.append("fi")
    out.append(f"SAMPLE_ORDER=\"{opt.sample_order}\"")
    out.append('if [ "${SAMPLE_ORDER}" = "__AUTO__" ]; then')
    out.append('  SAMPLE_ORDER=$(cut -f2 meta_groups.tsv | paste -sd, -)')
    out.append("fi")
    out.append("")
    out.append("# 4) 各样本单独提取为子集 RDS（按 meta_groups.tsv 读取 replicate 列）")
    out.append("n=0")
    out.append("while read grp rep; do")
    out.append(
        f"  Rscript \"{opt.rds_filter_script}\" -r \"{subset_rds}\" -s \"${{rep}}\" &"
    )
    out.append("  n=$((n+1))")
    out.append(f"  if [ \"$n\" -ge {opt.batch_size} ]; then")
    out.append("    wait")
    out.append("    n=0")
    out.append("  fi")
    out.append("done < meta_groups.tsv")
    out.append("wait")
    out.append("")

    # 1_preprocessing
    out.append("# =============================")
    out.append("# 5. 单样本预处理与整合")
    out.append("# =============================")
    out.append(f"mkdir -p \"{sub_pre_dir}\" && cd \"{sub_pre_dir}\"")
    out.append(
        "Rscript \"{script}\" "
        "-s \"${{SAMPLES}}\" "
        "-l \"${{GROUPS}}\" "
        "-f \"${{FMT_LIST}}\" "
        "-b \"${{BAM_LIST}}\" "
        "--MinTotalUMI {mtu} "
        "--MinGenes {mg} "
        "--MaxMT {mmt} "
        "--MinCellsInGene {mcg} "
        "-m {method} "
        "--batchSize {bs} "
        "--noparallel {np}".format(
            script=opt.sc_preprocessing_script,
            mtu=opt.qc_mintotalumi,
            mg=opt.qc_mingenes,
            mmt=opt.qc_maxmt,
            mcg=opt.qc_mincellsingene,
            method=opt.sc_method,
            bs=opt.batch_size_cells,
            np=str(opt.noparallel).lower()
        )
    )
    out.append("")

    # 2_cells_analysis
    out.append("# =============================")
    out.append("# 6. 细胞聚类与注释")
    out.append("# =============================")
    out.append(f"mkdir -p \"{sub_cells_dir}\" && cd \"{sub_cells_dir}\"")
    out.append(
        "Rscript \"{script}\" -a SCT --skiptsne true "
        "-i \"{pre_rds}\" -d {dims} --resolution {res} "
        "--sctypedb \"{sctype_db}\" -t \"{tag}\"".format(
            script=opt.sc_cells_analysis_script,
            pre_rds=os.path.join(sub_pre_dir, "sc_preprocessing.rds"),
            dims=opt.dims,
            res=opt.resolution,
            sctype_db=opt.sctype_db_xlsx,
            tag=opt.sctype_tag
        )
    )
    out.append("")

    # UMAP
    out.append("# 7. UMAP 绘图")
    out.append(f"mkdir -p \"{sub_cells_dir}\" && cd \"{sub_cells_dir}\"")
    out.append(
        "mkdir -p umap && cd umap && "
        f"Rscript \"{opt.sc_plot_umap_script}\" -i ../cells_analysis.rds &"
    )
    out.append("")

    # key marker UMAP
    out.append("# 8. key marker UMAP 绘制")
    out.append(f"mkdir -p \"{sub_cells_dir}\" && cd \"{sub_cells_dir}\"")
    out.append(
        "mkdir -p keymarker/key && cd keymarker/key && "
        f"cat \"{opt.sctype_db_txt}\" | "
        f"awk -F\"\\t\" '$1== \"{opt.sctype_tag}\"' | "
        "cutme - 5,3 | "
        "grep -v geneSymbolmore1 | "
        "perl -ne 'chomp; @line=split(/\\t/);@tt=split(/,/,$line[1]);"
        "foreach $k (@tt){print $k,\"\\t\",$line[0],\"\\n\";}' "
        "> cell_anno.txt && "
        "cat cell_anno.txt | sort -t$'\\t' -k 2,2 > cell_anno.ed.txt && "
        "Rscript \"/Users/chengchao/biosource/besaltpipe/src/SingleCell/tools/sc_genes_umap_SCT.r\" "
        "-m cell_anno.ed.txt -f ../../cells_analysis.rds --genelistcol 1 &"
    )
    out.append("")

    # markers & GO/KEGG
    out.append("# 9. markers 统计 + GO/KEGG 富集")
    out.append(f"cd \"{sub_cells_dir}\" && sh \"{opt.stat_markers_sh}\"")
    out.append(
        f"cd \"{sub_cells_dir}\" && "
        f"sh \"{opt.markers_gokegg_sh}\" \"{opt.go_anno}\" \"{opt.kegg_species}\""
    )
    out.append("")

    # cellratio_compare（cluster）
    cellratio_dir = os.path.join(sub_cells_dir, "cellratio_compare")
    out.append("# =============================")
    out.append("# 10. 按 cluster 统计细胞比例")
    out.append("# =============================")
    out.append(f"mkdir -p \"{cellratio_dir}\" && cd \"{cellratio_dir}\"")
    out.append("ln -fs ../sc_cluster/stat_cluster_fraction_by_group.xls")
    out.append("ln -fs ../sctype/sctype_scores.xls")
    out.append(
        "cat sctype_scores.xls | cut -f 1,2 | "
        "perl -ne 'chomp;if(/^cluster/){print \"cluster\\tnewgroup\\n\";next;}"
        "@line=split(/\\t/);$n=\"C$line[0]:$line[1]\";"
        "print \"$line[0]\\t$n\\n\";' > sctype.anno.txt"
    )
    out.append(
        "exp_add_anno -exp stat_cluster_fraction_by_group.xls "
        "-anno sctype.anno.txt -t -o stat_cluster_fraction_by_group.ed.xls -column 1"
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_multi.r "
        "-f stat_cluster_fraction_by_group.ed.xls "
        "-n stat_cluster_fraction_by_group "
        "-l \"${GROUP_ORDER}\""
    )
    out.append(
        "cat stat_cluster_fraction_by_group.ed.xls | "
        "perl -ne 'BEGIN{%h=();open IN,\"stat_cluster_fraction_by_group.ed.xls\";"
        "while(<IN>){chomp;next if(/^Group/);@line=split(/\\t/);$h{$line[1]}+=$line[2];}"
        "close IN;}chomp;if(/^Group/){print \"Group\\tClusterID\\tPercentageInCluster\\tnewgroup\\n\";next;}"
        "@line=split(/\\t/);$p=sprintf(\"%.2f\",$line[2]*100/$h{$line[1]});"
        "print \"$line[0]\\t$line[1]\\t$p\\t$line[-1]\\n\";' "
        "> stat_cluster_fraction_by_group.PercentageInCluster.xls"
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_multi_stacked.r "
        "-f stat_cluster_fraction_by_group.PercentageInCluster.xls "
        "-n stat_cluster_fraction_by_group.PercentageInCluster "
        "-l \"${GROUP_ORDER}\""
    )
    out.append(
        "cat stat_cluster_fraction_by_group.ed.xls | "
        "perl -ne 'chomp;next if(/^Group/);@line=split(/\\t/);"
        "$h{$line[1]}{$line[0]}=$line[3];$s{$line[0]}=1;"
        "END{print \"cluster\";foreach $sa (sort keys %s){print \"\\t$sa\";}print \"\\n\";"
        "foreach $k(sort keys %h){print \"C\".$k;foreach $sa(sort keys %s){"
        "$h{$k}{$sa}=0 if not defined($h{$k}{$sa});print \"\\t\",$h{$k}{$sa};}print \"\\n\";}}' "
        "> cluster_percentage_all.txt"
    )
    out.append(
        "cat stat_cluster_fraction_by_group.ed.xls | "
        "perl -ne 'chomp;next if(/^Group/);@line=split(/\\t/);"
        "$h{$line[-1]}{$line[0]}=$line[3];$s{$line[0]}=1;"
        "END{print \"cluster\";foreach $sa (sort keys %s){print \"\\t$sa\";}print \"\\n\";"
        "foreach $k(sort keys %h){print $k;foreach $sa(sort keys %s){"
        "$h{$k}{$sa}=0 if not defined($h{$k}{$sa});print \"\\t\",$h{$k}{$sa};}print \"\\n\";}}' "
        "> cluster_percentage_all2.txt"
    )
    out.append("")
    out.append("ln -fs ../sc_cluster/stat_cluster_fraction_by_sample.xls")
    out.append("ln -fs ../sctype/sctype_scores.xls")
    out.append(
        "cat sctype_scores.xls | cut -f 1,2 | "
        "perl -ne 'chomp;if(/^cluster/){print \"cluster\\tnewgroup\\n\";next;}"
        "@line=split(/\\t/);$n=\"C$line[0]:$line[1]\";"
        "print \"$line[0]\\t$n\\n\";' > sctype.anno.txt"
    )
    out.append(
        "exp_add_anno -exp stat_cluster_fraction_by_sample.xls "
        "-anno sctype.anno.txt -t -o stat_cluster_fraction_by_sample.ed.xls -column 1"
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_multi.r "
        "-f stat_cluster_fraction_by_sample.ed.xls "
        "-n stat_cluster_fraction_by_sample "
        "-w 350 -l \"${SAMPLE_ORDER}\""
    )
    out.append(
        "cat stat_cluster_fraction_by_sample.ed.xls | "
        "perl -ne 'BEGIN{%h=();open IN,\"stat_cluster_fraction_by_sample.ed.xls\";"
        "while(<IN>){chomp;next if(/^Group/);@line=split(/\\t/);$h{$line[1]}+=$line[2];}"
        "close IN;}chomp;if(/^Group/){print \"Group\\tClusterID\\tPercentageInCluster\\tsamplegroup\\tnewgroup\\n\";next;}"
        "@line=split(/\\t/);$p=sprintf(\"%.2f\",$line[2]*100/$h{$line[1]});"
        "print \"$line[0]\\t$line[1]\\t$p\\t$line[-2]\\t$line[-1]\\n\";' "
        "> stat_cluster_fraction_by_sample.PercentageInCluster.xls"
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_multi_stacked.r "
        "-f stat_cluster_fraction_by_sample.PercentageInCluster.xls "
        "-n stat_cluster_fraction_by_sample.PercentageInCluster "
        "-w 350 -l \"${SAMPLE_ORDER}\""
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/box_cellper_multi_dotplot.r "
        "-f stat_cluster_fraction_by_sample.ed.xls "
        "-n stat_cluster_fraction_by_sample.box "
        "-w 450 -l \"${GROUP_ORDER}\""
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_errorbar.r "
        "-f stat_cluster_fraction_by_sample.ed.xls "
        "-n stat_cluster_fraction_by_sample.errorbar "
        "-l \"${GROUP_ORDER}\""
    )
    out.append("")

    # cellratio_compare_bycelltype
    cellratio_ct_dir = os.path.join(sub_cells_dir, "cellratio_compare_bycelltype")
    out.append("# =============================")
    out.append("# 11. 按 celltype 统计细胞比例")
    out.append("# =============================")
    out.append(f"mkdir -p \"{cellratio_ct_dir}\" && cd \"{cellratio_ct_dir}\"")
    out.append("ln -fs ../sc_cluster/stat_celltype_fraction_by_group.xls")
    out.append("ln -fs ../sctype/sctype_scores.xls")
    out.append(
        "cat sctype_scores.xls | cut -f 1,2 | "
        "perl -ne 'chomp;if(/^cluster/){print \"cluster\\tnewgroup\\n\";next;}"
        "@line=split(/\\t/);$n=\"$line[1]\";"
        "print \"$line[1]\\t$n\\n\";' > sctype.anno.txt"
    )
    out.append(
        "exp_add_anno -u -exp stat_celltype_fraction_by_group.xls "
        "-anno sctype.anno.txt -t -o stat_celltype_fraction_by_group.ed.xls -column 1"
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_multi_raw.r "
        "-f stat_celltype_fraction_by_group.ed.xls "
        "-n stat_celltype_fraction_by_group "
        "-l \"${GROUP_ORDER}\""
    )
    out.append(
        "cat stat_celltype_fraction_by_group.ed.xls | "
        "perl -ne 'BEGIN{%h=();open IN,\"stat_celltype_fraction_by_group.ed.xls\";"
        "while(<IN>){chomp;next if(/^Group/);@line=split(/\\t/);$h{$line[1]}+=$line[2];}"
        "close IN;}chomp;if(/^Group/){print \"Group\\tClusterID\\tPercentageInCluster\\tnewgroup\\n\";next;}"
        "@line=split(/\\t/);$p=sprintf(\"%.2f\",$line[2]*100/$h{$line[1]});"
        "print \"$line[0]\\t$line[1]\\t$p\\t$line[-1]\\n\";' "
        "> stat_celltype_fraction_by_group.PercentageInCluster.xls"
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_multi_stacked_raw.r "
        "-f stat_celltype_fraction_by_group.PercentageInCluster.xls "
        "-n stat_celltype_fraction_by_group.PercentageInCluster "
        "-l \"${GROUP_ORDER}\""
    )
    out.append(
        "cat stat_celltype_fraction_by_group.ed.xls | "
        "perl -ne 'chomp;next if(/^Group/);@line=split(/\\t/);"
        "$h{$line[1]}{$line[0]}=$line[3];$s{$line[0]}=1;"
        "END{print \"cluster\";foreach $sa (sort keys %s){print \"\\t$sa\";}print \"\\n\";"
        "foreach $k(sort keys %h){print \"C\".$k;foreach $sa(sort keys %s){"
        "$h{$k}{$sa}=0 if not defined($h{$k}{$sa});print \"\\t\",$h{$k}{$sa};}print \"\\n\";}}' "
        "> celltype_percentage_all.txt"
    )
    out.append(
        "cat stat_celltype_fraction_by_group.ed.xls | "
        "perl -ne 'chomp;next if(/^Group/);@line=split(/\\t/);"
        "$h{$line[-1]}{$line[0]}=$line[3];$s{$line[0]}=1;"
        "END{print \"cluster\";foreach $sa (sort keys %s){print \"\\t$sa\";}print \"\\n\";"
        "foreach $k(sort keys %h){print $k;foreach $sa(sort keys %s){"
        "$h{$k}{$sa}=0 if not defined($h{$k}{$sa});print \"\\t\",$h{$k}{$sa};}print \"\\n\";}}' "
        "> celltype_percentage_all2.txt"
    )
    out.append("")
    out.append("ln -fs ../sc_cluster/stat_celltype_fraction_by_sample.xls")
    out.append("ln -fs ../sctype/sctype_scores.xls")
    out.append(
        "cat sctype_scores.xls | cut -f 1,2 | "
        "perl -ne 'chomp;if(/^cluster/){print \"cluster\\tnewgroup\\n\";next;}"
        "@line=split(/\\t/);$n=\"$line[1]\";"
        "print \"$line[1]\\t$n\\n\";' > sctype.anno.txt"
    )
    out.append(
        "exp_add_anno -u -exp stat_celltype_fraction_by_sample.xls "
        "-anno sctype.anno.txt -t -o stat_celltype_fraction_by_sample.ed.xls -column 1"
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_multi_raw.r "
        "-f stat_celltype_fraction_by_sample.ed.xls "
        "-n stat_celltype_fraction_by_sample "
        "-w 350 -l \"${SAMPLE_ORDER}\""
    )
    out.append(
        "cat stat_celltype_fraction_by_sample.ed.xls | "
        "perl -ne 'BEGIN{%h=();open IN,\"stat_celltype_fraction_by_sample.ed.xls\";"
        "while(<IN>){chomp;next if(/^Group/);@line=split(/\\t/);$h{$line[1]}+=$line[2];}"
        "close IN;}chomp;if(/^Group/){print \"Group\\tClusterID\\tPercentageInCluster\\tsamplegroup\\tnewgroup\\n\";next;}"
        "@line=split(/\\t/);$p=sprintf(\"%.2f\",$line[2]*100/$h{$line[1]});"
        "print \"$line[0]\\t$line[1]\\t$p\\t$line[-2]\\t$line[-1]\\n\";' "
        "> stat_celltype_fraction_by_sample.PercentageInCluster.xls"
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_multi_stacked_raw.r "
        "-f stat_celltype_fraction_by_sample.PercentageInCluster.xls "
        "-n stat_celltype_fraction_by_sample.PercentageInCluster "
        "-w 350 -l \"${SAMPLE_ORDER}\""
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/box_cellper_multi_dotplot.r "
        "-f stat_celltype_fraction_by_sample.ed.xls "
        "-n stat_celltype_fraction_by_sample.box "
        "-w 450 -l \"${GROUP_ORDER}\""
    )
    out.append(
        "Rscript /Users/chengchao/biosource/besaltgraphic/honeycomb/apps/single-cell/bar_basic_errorbar.r "
        "-f stat_celltype_fraction_by_sample.ed.xls "
        "-n stat_celltype_fraction_by_sample.errorbar "
        "-l \"${GROUP_ORDER}\""
    )
    out.append(
        f"Rscript \"{opt.sc_speckle_script}\" "
        f"-r \"{os.path.join(sub_cells_dir, 'cells_analysis.rds')}\""
    )
    out.append("")

    # 3_genes_analysis
    out.append("# =============================")
    out.append("# 12. 基因差异与富集分析")
    out.append("# =============================")
    out.append(f"mkdir -p \"{sub_genes_dir}\" && cd \"{sub_genes_dir}\"")
    out.append(f"CONTRAST=\"{contrast}\"")
    out.append(
        "Rscript \"{script}\" "
        "-s \"${{SAMPLES}}\" "
        "-l \"${{GROUPS}}\" "
        "-i \"{cells_rds}\" "
        "-c \"${{CONTRAST}}\" "
        "-d {dims}".format(
            script=opt.sc_genes_analysis_script,
            cells_rds=os.path.join(sub_cells_dir, "cells_analysis.rds"),
            dims=opt.deg_dims
        )
    )
    out.append("")
    out.append(
        f"cd \"{os.path.join(sub_genes_dir, 'deg_bycluster')}\" && "
        f"sh \"{opt.stat_deg_sh}\""
    )
    out.append(
        "cd \"{deg_dir}\" && "
        "sh \"{deg_gokegg_sh}\" \"{go_anno}\" \"{kegg}\" &".format(
            deg_dir=os.path.join(
                sub_genes_dir,
                "deg_bycluster",
                contrast.replace(":", "_") + "_deg"
            ),
            deg_gokegg_sh=opt.deg_gokegg_sh,
            go_anno=opt.go_anno,
            kegg=opt.kegg_species
        )
    )
    out.append("wait")
    out.append(
        f"cd \"{os.path.join(sub_genes_dir, 'deg_byall')}\" && "
        f"sh \"{opt.stat_deg_byall_sh}\""
    )
    out.append(
        "cd \"{deg_dir}\" && "
        "sh \"{deg_gokegg_byall_sh}\" \"{go_anno}\" \"{kegg}\" &".format(
            deg_dir=os.path.join(
                sub_genes_dir,
                "deg_byall",
                contrast.replace(":", "_") + "_deg"
            ),
            deg_gokegg_byall_sh=opt.deg_gokegg_byall_sh,
            go_anno=opt.go_anno,
            kegg=opt.kegg_species
        )
    )
    out.append("wait")
    out.append("")

    sys.stdout.write("\n".join(out))


if __name__ == "__main__":
    main()
