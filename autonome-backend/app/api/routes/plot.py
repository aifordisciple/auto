"""
图表 API 路由

NL2Vis 交互式可视化相关的 API 端点：
- POST /api/plot/redraw - 重绘图表
- GET /api/plot/data - 获取图表数据
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import os
from pathlib import Path
import pandas as pd
from loguru import logger

from app.core.config import settings

router = APIRouter(prefix="/api/plot", tags=["plot"])


# ==========================================
# ✨ 请求/响应模型
# ==========================================

class RedrawRequest(BaseModel):
    """重绘请求"""
    plot_type: str
    data_source: str
    parameters: Dict[str, Any]
    project_id: Optional[str] = None


class RedrawResponse(BaseModel):
    """重绘响应"""
    status: str
    config: Optional[Dict[str, Any]] = None
    data: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    error: Optional[str] = None


class PlotDataResponse(BaseModel):
    """图表数据响应"""
    status: str
    data: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    row_count: Optional[int] = None
    error: Optional[str] = None


# ==========================================
# ✨ 辅助函数
# ==========================================

def resolve_data_path(data_source: str, project_id: Optional[str] = None) -> Path:
    """
    解析数据路径

    支持三种格式：
    1. 完整路径：/workspace/project_xxx/data/file.tsv
    2. 相对于项目根目录：data/file.tsv（需要 project_id）
    3. 相对于任务输出目录：results.tsv 或 results/task_name/results.tsv（需要 project_id）
    """
    # 如果是完整路径
    if data_source.startswith("/workspace/"):
        return Path(data_source)

    # 如果没有 project_id，无法解析相对路径
    if not project_id:
        raise ValueError(f"解析相对路径需要 project_id: {data_source}")

    project_dir = Path(settings.UPLOAD_DIR) / f"project_{project_id}"

    # 检查是否是相对于 results 目录的路径
    if data_source.startswith("results/"):
        # 格式: results/task_name/file.tsv
        return project_dir / data_source
    elif "/" not in data_source:
        # 格式: results.tsv（默认在 default_task 目录下）
        return project_dir / "results" / "default_task" / data_source
    else:
        # 格式: data/file.tsv（相对于项目根目录）
        return project_dir / data_source


def read_tabular_data(file_path: Path, limit: int = 500) -> tuple:
    """
    读取表格数据

    返回: (data, columns, row_count)
    """
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 根据扩展名选择分隔符
    suffix = file_path.suffix.lower()
    sep = '\t' if suffix in ['.tsv', '.txt'] else ','

    # 读取数据
    df = pd.read_csv(file_path, sep=sep)

    # 处理 NaN 值
    df = df.fillna('')

    columns = df.columns.tolist()
    total_rows = len(df)
    data = df.head(limit).to_dict('records')

    return data, columns, total_rows


# ==========================================
# ✨ API 端点
# ==========================================

@router.post("/redraw", response_model=RedrawResponse)
async def redraw_plot(request: RedrawRequest):
    """
    重绘图表

    根据参数变更重新生成图表配置，返回真实数据
    """
    try:
        logger.info(f"[PlotAPI] Redraw request: type={request.plot_type}, source={request.data_source}")

        # 解析数据路径
        file_path = resolve_data_path(request.data_source, request.project_id)

        # 读取数据
        data, columns, row_count = read_tabular_data(file_path)

        # 根据参数生成图表配置
        config = generate_plot_config(request.plot_type, columns, request.parameters, data)

        return RedrawResponse(
            status="success",
            config=config,
            data=data[:100],  # 限制返回数据量
            columns=columns
        )

    except FileNotFoundError as e:
        logger.warning(f"[PlotAPI] File not found: {e}")
        return RedrawResponse(
            status="error",
            error=str(e)
        )
    except Exception as e:
        logger.error(f"[PlotAPI] Redraw failed: {e}")
        return RedrawResponse(
            status="error",
            error=str(e)
        )


@router.get("/data", response_model=PlotDataResponse)
async def get_plot_data(
    data_source: str,
    project_id: Optional[str] = None,
    limit: int = 500
):
    """
    获取图表数据

    用于 TSV 导出和数据预览
    """
    try:
        logger.info(f"[PlotAPI] Get data: source={data_source}, project={project_id}")

        # 解析数据路径
        file_path = resolve_data_path(data_source, project_id)

        # 读取数据
        data, columns, row_count = read_tabular_data(file_path, limit)

        return PlotDataResponse(
            status="success",
            data=data,
            columns=columns,
            row_count=row_count
        )

    except FileNotFoundError as e:
        logger.warning(f"[PlotAPI] File not found: {e}")
        return PlotDataResponse(
            status="error",
            error=str(e)
        )
    except Exception as e:
        logger.error(f"[PlotAPI] Get data failed: {e}")
        return PlotDataResponse(
            status="error",
            error=str(e)
        )


# ==========================================
# ✨ 图表配置生成
# ==========================================

def generate_plot_config(
    plot_type: str,
    columns: List[str],
    parameters: Dict[str, Any],
    data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    生成 ECharts 配置

    根据图表类型、列名和参数生成对应的配置对象
    """
    # 提取参数
    x_column = parameters.get('x_column', columns[0] if columns else 'x')
    y_column = parameters.get('y_column', columns[1] if len(columns) > 1 else 'y')
    title = parameters.get('title', '')

    # 基础配置
    base_config = {
        "title": {
            "text": title,
            "left": "center",
            "textStyle": {
                "fontSize": 14,
                "fontWeight": "bold",
                "color": "#e4e4e7",
            }
        },
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "rgba(0, 0, 0, 0.8)",
            "borderColor": "#3f3f46",
            "textStyle": {"color": "#e4e4e7"},
        },
        "legend": {
            "bottom": 10,
            "left": "center",
            "textStyle": {"color": "#a1a1aa"},
        },
        "grid": {
            "left": "5%",
            "right": "5%",
            "bottom": "15%",
            "top": "15%",
            "containLabel": True,
        },
    }

    # 根据图表类型生成系列
    if plot_type in ["scatter", "volcano", "pca"]:
        base_config["xAxis"] = {
            "type": "value",
            "name": x_column,
            "nameTextStyle": {"color": "#a1a1aa"},
            "axisLine": {"lineStyle": {"color": "#3f3f46"}},
            "axisLabel": {"color": "#a1a1aa"},
            "splitLine": {"lineStyle": {"color": "#27272a"}},
        }
        base_config["yAxis"] = {
            "type": "value",
            "name": y_column,
            "nameTextStyle": {"color": "#a1a1aa"},
            "axisLine": {"lineStyle": {"color": "#3f3f46"}},
            "axisLabel": {"color": "#a1a1aa"},
            "splitLine": {"lineStyle": {"color": "#27272a"}},
        }
        # 提取散点数据
        series_data = []
        for row in data[:200]:  # 限制点数
            x_val = row.get(x_column, 0)
            y_val = row.get(y_column, 0)
            try:
                series_data.append([float(x_val), float(y_val)])
            except (ValueError, TypeError):
                continue
        base_config["series"] = [{
            "type": "scatter",
            "symbolSize": parameters.get("point_size", 8),
            "data": series_data,
            "itemStyle": {"color": "#a78bfa"},
        }]

    elif plot_type in ["bar", "line"]:
        base_config["xAxis"] = {
            "type": "category",
            "data": [str(row.get(x_column, '')) for row in data[:50]],
            "axisLine": {"lineStyle": {"color": "#3f3f46"}},
            "axisLabel": {"color": "#a1a1aa", "rotate": 30},
        }
        base_config["yAxis"] = {
            "type": "value",
            "name": y_column,
            "nameTextStyle": {"color": "#a1a1aa"},
            "axisLine": {"lineStyle": {"color": "#3f3f46"}},
            "axisLabel": {"color": "#a1a1aa"},
            "splitLine": {"lineStyle": {"color": "#27272a"}},
        }
        # 提取数值数据
        series_data = []
        for row in data[:50]:
            val = row.get(y_column, 0)
            try:
                series_data.append(float(val))
            except (ValueError, TypeError):
                series_data.append(0)
        base_config["series"] = [{
            "type": plot_type,
            "data": series_data,
            "itemStyle": {"color": "#a78bfa", "borderRadius": [4, 4, 0, 0]} if plot_type == "bar" else None,
            "smooth": parameters.get("smooth", False),
        }]

    elif plot_type == "pie":
        series_data = []
        for row in data[:10]:
            name = str(row.get(x_column, ''))
            value = row.get(y_column, 0)
            try:
                series_data.append({"name": name, "value": float(value)})
            except (ValueError, TypeError):
                continue
        base_config["series"] = [{
            "type": "pie",
            "radius": ["40%", "70%"],
            "data": series_data,
            "itemStyle": {
                "borderRadius": 10,
                "borderColor": "#0a0a0b",
                "borderWidth": 2,
            },
            "label": {
                "show": True,
                "formatter": "{b}: {d}%",
                "color": "#a1a1aa",
            },
        }]
        del base_config["xAxis"]
        del base_config["yAxis"]
        del base_config["grid"]

    elif plot_type == "heatmap":
        # 热图需要特殊处理
        base_config["visualMap"] = {
            "min": 0,
            "max": 10,
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": "0%",
            "textStyle": {"color": "#a1a1aa"},
            "inRange": {
                "color": ["#1e1b4b", "#4c1d95", "#7c3aed", "#a78bfa", "#c4b5fd"],
            },
        }
        base_config["series"] = [{
            "type": "heatmap",
            "data": [],  # 需要根据实际数据格式化
        }]

    return base_config