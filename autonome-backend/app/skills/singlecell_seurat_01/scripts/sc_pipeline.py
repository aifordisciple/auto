#!/usr/bin/env python3
"""
单细胞RNA测序数据分析流程入口脚本

调用 besaltpipe 框架中的 R 脚本执行 Seurat 分析流程

功能：
1. 解析 SKILL 参数
2. 构建并执行 R 脚本命令
3. 返回分析结果

作者：BioData Team
版本：1.0.0
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加项目路径
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent

# BesaltPipe 路径（容器内）
BESALTPIPE_SRC = "/app/biosource/besaltpipe/src/SingleCell/pipeline"


def parse_arguments() -> Dict[str, Any]:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="单细胞RNA测序数据分析流程",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # 必填参数
    parser.add_argument("--input_format", required=True,
                        choices=["10x", "exp", "BD", "h5", "rds"],
                        help="输入数据格式")
    parser.add_argument("--input_paths", required=True,
                        help="输入数据路径列表（逗号分隔）")
    parser.add_argument("--sample_names", required=True,
                        help="样本名称列表（逗号分隔）")
    parser.add_argument("--group_labels", required=True,
                        help="分组标签列表（逗号分隔）")
    parser.add_argument("--output_dir", required=True,
                        help="输出目录")

    # 可选参数
    parser.add_argument("--min_umi", type=int, default=1000,
                        help="最小UMI数阈值")
    parser.add_argument("--min_genes", type=int, default=500,
                        help="最小基因数阈值")
    parser.add_argument("--max_mt_percent", type=float, default=15,
                        help="线粒体比例上限(%)")
    parser.add_argument("--min_cells", type=int, default=5,
                        help="基因最小表达细胞数")
    parser.add_argument("--integration_method", default="sct_harmony",
                        choices=["cca", "rpca", "sct_cca", "sct_rpca", "sct_harmony", "merge"],
                        help="批次整合方法")
    parser.add_argument("--doublet_detection", type=lambda x: x.lower() == "true",
                        default=True, help="是否启用双细胞检测")
    parser.add_argument("--dims", type=int, default=50,
                        help="PCA主成分数量")
    parser.add_argument("--resolution", type=float, default=0.8,
                        help="聚类分辨率")
    parser.add_argument("--tissue_type", default="",
                        help="组织类型（用于ScType注释）")
    parser.add_argument("--ncpus", type=int, default=16,
                        help="并行CPU核数")
    parser.add_argument("--max_memory", type=int, default=128,
                        help="最大内存(GB)")

    args = parser.parse_args()

    # 转换为字典
    params = vars(args)

    # 解析列表参数
    params["input_paths_list"] = [p.strip() for p in params["input_paths"].split(",")]
    params["sample_names_list"] = [s.strip() for s in params["sample_names"].split(",")]
    params["group_labels_list"] = [g.strip() for g in params["group_labels"].split(",")]

    # 验证列表长度一致
    n_samples = len(params["sample_names_list"])
    if len(params["input_paths_list"]) != n_samples:
        raise ValueError(f"输入路径数量({len(params['input_paths_list'])})与样本数量({n_samples})不匹配")
    if len(params["group_labels_list"]) != n_samples:
        raise ValueError(f"分组标签数量({len(params['group_labels_list'])})与样本数量({n_samples})不匹配")

    return params


def build_preprocessing_command(params: Dict[str, Any]) -> str:
    """构建预处理 R 脚本命令"""

    # 构建数据格式列表
    formats = ",".join([params["input_format"]] * len(params["sample_names_list"]))

    # 构建数据集标签（用于批次整合）
    # 相同分组标签的样本归为同一数据集
    unique_groups = list(dict.fromkeys(params["group_labels_list"]))
    group_to_dataset = {g: f"D{i+1}" for i, g in enumerate(unique_groups)}
    datasets = ",".join([group_to_dataset[g] for g in params["group_labels_list"]])

    cmd = f"""Rscript {BESALTPIPE_SRC}/sc_preprocessing_v3.r \\
  -s {params['sample_names']} \\
  -l {params['group_labels']} \\
  -f {formats} \\
  --dataset {datasets} \\
  -b {params['input_paths']} \\
  --MinTotalUMI {params['min_umi']} \\
  --MinGenes {params['min_genes']} \\
  --MaxMT {params['max_mt_percent']} \\
  --MinCellsInGene {params['min_cells']} \\
  -m {params['integration_method']} \\
  --doublet_enable {str(params['doublet_detection']).lower()} \\
  --noparallel false \\
  --ncpus {params['ncpus']} \\
  --MaxMemMega {params['max_memory']}
"""
    return cmd


def build_cells_analysis_command(params: Dict[str, Any]) -> str:
    """构建细胞聚类分析 R 脚本命令"""

    rds_path = os.path.join(params["output_dir"], "sc_preprocessing.rds")

    cmd = f"""Rscript {BESALTPIPE_SRC}/sc_cells_analysis.r \\
  -r {rds_path} \\
  --dims {params['dims']} \\
  --resolution {params['resolution']}
"""
    return cmd


def run_command(cmd: str, cwd: str) -> int:
    """执行命令并实时输出日志"""
    print(f"\n{'='*60}")
    print(f"执行命令: {cmd}")
    print(f"工作目录: {cwd}")
    print(f"{'='*60}\n")

    process = subprocess.Popen(
        cmd,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in process.stdout:
        print(line, end='')

    process.wait()
    return process.returncode


def run_preprocessing(params: Dict[str, Any]) -> bool:
    """执行预处理步骤"""
    print("\n" + "="*60)
    print("Step 1: 数据预处理 (Preprocessing)")
    print("="*60)

    # 创建输出目录
    os.makedirs(params["output_dir"], exist_ok=True)

    cmd = build_preprocessing_command(params)
    ret = run_command(cmd, params["output_dir"])

    if ret != 0:
        print(f"❌ 预处理失败，返回码: {ret}")
        return False

    print("✅ 预处理完成")
    return True


def run_cells_analysis(params: Dict[str, Any]) -> bool:
    """执行细胞聚类分析"""
    print("\n" + "="*60)
    print("Step 2: 细胞聚类分析 (Cells Analysis)")
    print("="*60)

    cmd = build_cells_analysis_command(params)
    ret = run_command(cmd, params["output_dir"])

    if ret != 0:
        print(f"❌ 聚类分析失败，返回码: {ret}")
        return False

    print("✅ 聚类分析完成")
    return True


def run_sctype_annotation(params: Dict[str, Any]) -> bool:
    """执行细胞类型注释"""
    if not params.get("tissue_type"):
        print("\n⚠️ 未指定组织类型，跳过 ScType 自动注释")
        return True

    print("\n" + "="*60)
    print("Step 3: 细胞类型注释 (ScType Annotation)")
    print("="*60)

    rds_path = os.path.join(params["output_dir"], "cells_analysis.rds")

    cmd = f"""Rscript {BESALTPIPE_SRC}/sc_cells_annotation_sctype.r \\
  -r {rds_path} \\
  --tissue {params['tissue_type']}
"""
    ret = run_command(cmd, params["output_dir"])

    if ret != 0:
        print(f"⚠️ ScType 注释失败，返回码: {ret}")
        return True  # 不阻断流程

    print("✅ 细胞类型注释完成")
    return True


def run_marker_analysis(params: Dict[str, Any]) -> bool:
    """执行 Marker 基因分析"""
    print("\n" + "="*60)
    print("Step 4: Marker 基因分析")
    print("="*60)

    rds_path = os.path.join(params["output_dir"], "cells_analysis.rds")

    cmd = f"""Rscript {BESALTPIPE_SRC}/sc_genes_analysis.r \\
  -r {rds_path} \\
  --dims {params['dims']}
"""
    ret = run_command(cmd, params["output_dir"])

    if ret != 0:
        print(f"⚠️ Marker 分析失败，返回码: {ret}")
        return True  # 不阻断流程

    print("✅ Marker 基因分析完成")
    return True


def generate_output_summary(params: Dict[str, Any]) -> Dict[str, Any]:
    """生成输出摘要"""
    output_dir = params["output_dir"]

    summary = {
        "status": "success",
        "output_dir": output_dir,
        "files": {
            "seurat_object": os.path.join(output_dir, "cells_analysis.rds"),
            "preprocessing_rds": os.path.join(output_dir, "sc_preprocessing.rds"),
        },
        "parameters": {
            "n_samples": len(params["sample_names_list"]),
            "samples": params["sample_names_list"],
            "groups": params["group_labels_list"],
            "integration_method": params["integration_method"],
            "min_umi": params["min_umi"],
            "min_genes": params["min_genes"],
            "dims": params["dims"],
            "resolution": params["resolution"]
        }
    }

    # 检查输出文件
    qc_dir = os.path.join(output_dir, "QC")
    cluster_dir = os.path.join(output_dir, "sc_cluster")
    sctype_dir = os.path.join(output_dir, "sctype")
    markers_dir = os.path.join(output_dir, "markers")

    if os.path.exists(qc_dir):
        summary["files"]["qc_reports"] = qc_dir
    if os.path.exists(cluster_dir):
        summary["files"]["cluster_results"] = cluster_dir
    if os.path.exists(sctype_dir):
        summary["files"]["cell_annotation"] = sctype_dir
    if os.path.exists(markers_dir):
        summary["files"]["markers"] = markers_dir

    return summary


def main():
    """主函数"""
    print("\n" + "="*60)
    print("  单细胞 RNA-seq 分析流程 v1.0.0")
    print("  基于 Seurat v5 + BesaltPipe")
    print("="*60)

    try:
        # 解析参数
        params = parse_arguments()

        print(f"\n📋 分析参数:")
        print(f"  - 样本数: {len(params['sample_names_list'])}")
        print(f"  - 样本名: {params['sample_names']}")
        print(f"  - 分组: {params['group_labels']}")
        print(f"  - 输入格式: {params['input_format']}")
        print(f"  - 整合方法: {params['integration_method']}")
        print(f"  - 输出目录: {params['output_dir']}")

        # 执行分析流程
        steps = [
            ("预处理", run_preprocessing),
            ("聚类分析", run_cells_analysis),
            ("细胞注释", run_sctype_annotation),
            ("Marker分析", run_marker_analysis)
        ]

        for step_name, step_func in steps:
            if not step_func(params):
                print(f"\n❌ 流程在 {step_name} 步骤失败")
                sys.exit(1)

        # 生成输出摘要
        summary = generate_output_summary(params)

        print("\n" + "="*60)
        print("✅ 分析流程全部完成！")
        print("="*60)

        print(f"\n📁 输出文件:")
        for key, path in summary["files"].items():
            if os.path.exists(path):
                print(f"  - {key}: {path}")

        # 写入摘要文件
        summary_path = os.path.join(params["output_dir"], "analysis_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n📄 分析摘要已保存: {summary_path}")

        return 0

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())