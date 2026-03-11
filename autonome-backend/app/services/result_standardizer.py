"""
Result Standardizer - 结果目录结构标准化服务

提供技能执行结果的标准化整理、摘要生成、可视化报告等功能
"""

import os
import json
import shutil
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from pathlib import Path

from app.core.logger import log


# ==========================================
# 标准输出目录结构定义
# ==========================================
STANDARD_OUTPUT_STRUCTURE = {
    "meta_dir": ".meta",
    "figures_dir": "figures",
    "tables_dir": "tables",
    "reports_dir": "reports",
    "summary_file": "summary.json"
}

META_FILES = {
    "task_info": "task_info.json",
    "parameters": "parameters.json",
    "execution_log": "execution_log.txt"
}


def get_utc_now():
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


class ResultStandardizer:
    """
    结果标准化器

    负责：
    1. 整理技能输出文件到标准目录结构
    2. 生成结果摘要 (summary.json)
    3. 提取主要发现和建议
    """

    def __init__(self, output_dir: str):
        """
        初始化标准化器

        Args:
            output_dir: 技能执行输出目录
        """
        self.output_dir = Path(output_dir)
        self.meta_dir = self.output_dir / STANDARD_OUTPUT_STRUCTURE["meta_dir"]
        self.figures_dir = self.output_dir / STANDARD_OUTPUT_STRUCTURE["figures_dir"]
        self.tables_dir = self.output_dir / STANDARD_OUTPUT_STRUCTURE["tables_dir"]
        self.reports_dir = self.output_dir / STANDARD_OUTPUT_STRUCTURE["reports_dir"]

    def ensure_structure(self) -> None:
        """确保标准目录结构存在"""
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"[ResultStandardizer] 目录结构已创建: {self.output_dir}")

    def organize_outputs(self) -> Dict[str, List[str]]:
        """
        整理输出文件到标准目录

        Returns:
            整理后的文件清单
        """
        self.ensure_structure()

        organized = {
            "figures": [],
            "tables": [],
            "reports": [],
            "meta": []
        }

        # 支持的文件扩展名
        figure_extensions = {'.png', '.jpg', '.jpeg', '.pdf', '.svg', '.tiff', '.tif'}
        table_extensions = {'.tsv', '.csv', '.txt', '.xlsx', '.xls'}
        report_extensions = {'.html', '.htm'}

        # 遍历输出目录（排除已创建的标准子目录）
        exclude_dirs = {STANDARD_OUTPUT_STRUCTURE["meta_dir"],
                       STANDARD_OUTPUT_STRUCTURE["figures_dir"],
                       STANDARD_OUTPUT_STRUCTURE["tables_dir"],
                       STANDARD_OUTPUT_STRUCTURE["reports_dir"]}

        for root, dirs, files in os.walk(self.output_dir):
            # 排除标准子目录
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                if file == STANDARD_OUTPUT_STRUCTURE["summary_file"]:
                    continue

                src_path = Path(root) / file
                ext = Path(file).suffix.lower()

                try:
                    if ext in figure_extensions:
                        dst_path = self.figures_dir / file
                        if src_path != dst_path:
                            shutil.move(str(src_path), str(dst_path))
                        organized["figures"].append(file)

                    elif ext in table_extensions:
                        dst_path = self.tables_dir / file
                        if src_path != dst_path:
                            shutil.move(str(src_path), str(dst_path))
                        organized["tables"].append(file)

                    elif ext in report_extensions:
                        dst_path = self.reports_dir / file
                        if src_path != dst_path:
                            shutil.move(str(src_path), str(dst_path))
                        organized["reports"].append(file)

                except Exception as e:
                    log.warning(f"[ResultStandardizer] 文件移动失败 {file}: {e}")

        log.info(f"[ResultStandardizer] 文件整理完成: 图表 {len(organized['figures'])} 个, "
                f"表格 {len(organized['tables'])} 个, 报告 {len(organized['reports'])} 个")

        return organized

    def generate_summary(
        self,
        task_id: str,
        skill_id: str,
        skill_name: str,
        status: str,
        execution_time: float,
        parameters: Dict[str, Any] = None,
        organized_files: Dict[str, List[str]] = None
    ) -> Dict[str, Any]:
        """
        生成结果摘要

        Args:
            task_id: 任务 ID
            skill_id: 技能 ID
            skill_name: 技能名称
            status: 执行状态
            execution_time: 执行时间（秒）
            parameters: 使用的参数
            organized_files: 整理后的文件清单

        Returns:
            摘要数据
        """
        if organized_files is None:
            organized_files = self.organize_outputs()

        summary = {
            "task_id": task_id,
            "skill_id": skill_id,
            "skill_name": skill_name,
            "status": status,
            "execution_time": round(execution_time, 2),
            "completed_at": get_utc_now().isoformat(),
            "output_summary": {
                "figures_count": len(organized_files.get("figures", [])),
                "tables_count": len(organized_files.get("tables", [])),
                "reports_count": len(organized_files.get("reports", [])),
                "main_findings": [],
                "errors": []
            },
            "files_generated": self._build_file_list(organized_files),
            "recommendations": [],
            "output_directory": str(self.output_dir)
        }

        # 保存任务元数据
        if parameters:
            self._save_meta("parameters", parameters)

        task_info = {
            "task_id": task_id,
            "skill_id": skill_id,
            "skill_name": skill_name,
            "status": status,
            "execution_time": execution_time,
            "completed_at": summary["completed_at"]
        }
        self._save_meta("task_info", task_info)

        # 保存摘要文件
        summary_path = self.output_dir / STANDARD_OUTPUT_STRUCTURE["summary_file"]
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        log.info(f"[ResultStandardizer] 摘要已生成: {summary_path}")
        return summary

    def _build_file_list(self, organized_files: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """构建文件清单"""
        files = []

        for fig in organized_files.get("figures", []):
            files.append({
                "path": f"figures/{fig}",
                "type": "figure",
                "name": fig
            })

        for tbl in organized_files.get("tables", []):
            # 尝试获取行数
            row_count = self._count_table_rows(tbl)
            files.append({
                "path": f"tables/{tbl}",
                "type": "table",
                "name": tbl,
                "rows": row_count
            })

        for rpt in organized_files.get("reports", []):
            files.append({
                "path": f"reports/{rpt}",
                "type": "report",
                "name": rpt
            })

        return files

    def _count_table_rows(self, filename: str) -> Optional[int]:
        """统计表格行数"""
        try:
            table_path = self.tables_dir / filename
            if table_path.exists():
                with open(table_path, 'r', encoding='utf-8') as f:
                    return sum(1 for _ in f) - 1  # 减去表头
        except Exception:
            pass
        return None

    def _save_meta(self, meta_type: str, data: Dict[str, Any]) -> None:
        """保存元数据文件"""
        filename = META_FILES.get(meta_type)
        if not filename:
            return

        meta_path = self.meta_dir / filename
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                if meta_type == "execution_log":
                    f.write(str(data))
                else:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"[ResultStandardizer] 元数据保存失败 {meta_type}: {e}")

    def append_log(self, log_content: str) -> None:
        """追加执行日志"""
        log_path = self.meta_dir / META_FILES["execution_log"]
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(log_content + "\n")
        except Exception as e:
            log.warning(f"[ResultStandardizer] 日志追加失败: {e}")


class ResultVisualizer:
    """
    结果可视化服务

    提供：
    1. HTML 摘要报告生成
    2. 文件预览生成
    3. 可视化卡片数据
    """

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.standardizer = ResultStandardizer(output_dir)

    def generate_summary_report(
        self,
        task_id: str,
        skill_id: str,
        skill_name: str,
        status: str,
        execution_time: float,
        parameters: Dict[str, Any] = None
    ) -> str:
        """
        生成 HTML 摘要报告

        Returns:
            报告文件路径
        """
        # 先整理文件
        organized = self.standardizer.organize_outputs()

        # 生成摘要
        summary = self.standardizer.generate_summary(
            task_id=task_id,
            skill_id=skill_id,
            skill_name=skill_name,
            status=status,
            execution_time=execution_time,
            parameters=parameters,
            organized_files=organized
        )

        # 生成 HTML 报告
        html_content = self._generate_html_report(summary)
        report_path = self.standardizer.reports_dir / f"summary_{task_id}.html"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        log.info(f"[ResultVisualizer] HTML 报告已生成: {report_path}")
        return str(report_path)

    def _generate_html_report(self, summary: Dict[str, Any]) -> str:
        """生成 HTML 报告内容"""
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>分析结果摘要 - {summary['skill_name']}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a1a;
            color: #e0e0e0;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            border-bottom: 1px solid #333;
            padding-bottom: 20px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0;
            color: #3b82f6;
        }}
        .status {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .status.success {{ background: #166534; color: #bbf7d0; }}
        .status.failed {{ background: #991b1b; color: #fecaca; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: #262626;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: bold;
            color: #3b82f6;
        }}
        .stat-label {{
            font-size: 12px;
            color: #888;
            margin-top: 4px;
        }}
        .section {{
            background: #262626;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }}
        .section h2 {{
            margin: 0 0 12px 0;
            font-size: 14px;
            color: #888;
            text-transform: uppercase;
        }}
        .file-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .file-list li {{
            padding: 8px 0;
            border-bottom: 1px solid #333;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .file-list li:last-child {{ border-bottom: none; }}
        .file-icon {{ font-size: 16px; }}
        .meta {{
            font-size: 11px;
            color: #666;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{summary['skill_name']}</h1>
        <p style="margin: 8px 0 0 0; color: #888;">
            <span class="status {'success' if summary['status'] == 'success' else 'failed'}">{summary['status'].upper()}</span>
            <span style="margin-left: 12px;">Task: {summary['task_id']}</span>
        </p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{summary['output_summary']['figures_count']}</div>
            <div class="stat-label">图表</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{summary['output_summary']['tables_count']}</div>
            <div class="stat-label">表格</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{summary['output_summary']['reports_count']}</div>
            <div class="stat-label">报告</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{summary['execution_time']}s</div>
            <div class="stat-label">执行时间</div>
        </div>
    </div>
"""

        # 添加文件列表
        if summary.get('files_generated'):
            html += """
    <div class="section">
        <h2>生成的文件</h2>
        <ul class="file-list">
"""
            for f in summary['files_generated']:
                icon = {'figure': '🖼️', 'table': '📊', 'report': '📄'}.get(f['type'], '📁')
                rows_info = f" ({f['rows']} 行)" if f.get('rows') else ""
                html += f"            <li><span class='file-icon'>{icon}</span>{f['name']}{rows_info}</li>\n"

            html += """        </ul>
    </div>
"""

        # 添加元信息
        html += f"""
    <div class="meta">
        <p>Skill ID: {summary['skill_id']} | Completed: {summary['completed_at']}</p>
        <p>Output: {summary['output_directory']}</p>
    </div>
</body>
</html>"""

        return html

    def generate_result_preview(self, file_path: str) -> Dict[str, Any]:
        """
        生成文件预览数据

        Args:
            file_path: 文件路径

        Returns:
            预览数据
        """
        path = Path(file_path)
        if not path.exists():
            return {"error": "文件不存在"}

        ext = path.suffix.lower()

        if ext in {'.png', '.jpg', '.jpeg', '.gif', '.svg'}:
            return {
                "type": "image",
                "path": str(path),
                "name": path.name
            }

        elif ext in {'.tsv', '.csv', '.txt'}:
            return self._preview_table(path)

        elif ext in {'.html', '.htm'}:
            return {
                "type": "html",
                "path": str(path),
                "name": path.name
            }

        else:
            return {
                "type": "unknown",
                "path": str(path),
                "name": path.name,
                "size": path.stat().st_size
            }

    def _preview_table(self, path: Path, max_rows: int = 20) -> Dict[str, Any]:
        """预览表格数据"""
        try:
            import csv

            delimiter = '\t' if path.suffix == '.tsv' else ','
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=delimiter)
                rows = list(reader)

            headers = rows[0] if rows else []
            data = rows[1:max_rows+1] if len(rows) > 1 else []

            return {
                "type": "table",
                "path": str(path),
                "name": path.name,
                "headers": headers,
                "data": data,
                "total_rows": len(rows) - 1,
                "preview_rows": len(data)
            }

        except Exception as e:
            return {
                "type": "table",
                "path": str(path),
                "error": str(e)
            }


# ==========================================
# 便捷函数
# ==========================================

def standardize_result(
    output_dir: str,
    task_id: str,
    skill_id: str,
    skill_name: str,
    status: str,
    execution_time: float,
    parameters: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    标准化结果并生成摘要

    Args:
        output_dir: 输出目录
        task_id: 任务 ID
        skill_id: 技能 ID
        skill_name: 技能名称
        status: 执行状态
        execution_time: 执行时间
        parameters: 使用的参数

    Returns:
        结果摘要
    """
    visualizer = ResultVisualizer(output_dir)
    report_path = visualizer.generate_summary_report(
        task_id=task_id,
        skill_id=skill_id,
        skill_name=skill_name,
        status=status,
        execution_time=execution_time,
        parameters=parameters
    )

    summary_path = Path(output_dir) / STANDARD_OUTPUT_STRUCTURE["summary_file"]
    with open(summary_path, 'r', encoding='utf-8') as f:
        return json.load(f)