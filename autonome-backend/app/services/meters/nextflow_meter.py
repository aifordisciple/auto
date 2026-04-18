# -*- coding: utf-8 -*-
"""
Nextflow 工作流计量器

用于 Nextflow 工作流执行的计费，支持：
- 解析 trace.txt 获取任务执行详情
- 按 process 匹配 ResourceFlavor 差异化定价
- DAG 任务累计计费
"""

import os
import re
import time
from typing import Any, Dict, List, Optional

from app.core.logger import log

from app.services.meters.base import BaseMeter, MeteringResult


class NextflowMeter(BaseMeter):
    """Nextflow 工作流计量器

    计费策略：
    1. 执行开始时记录开始时间
    2. 执行结束后解析 trace.txt
    3. 按 task 累计费用，支持差异化定价
    4. 未完成的任务不计费

    使用示例：
        meter = NextflowMeter(billing_service, work_dir="/path/to/work")
        meter.start_metering(record_id, {"blueprint_id": "bp_123"})

        # ... 执行 Nextflow 工作流 ...

        result = meter.stop_metering(record_id)
        print(f"总费用: {result.cost_credits} CU")
        print(f"任务数: {result.details['task_count']}")
    """

    def __init__(
        self,
        billing_service: Optional["BillingService"] = None,
        flavor: Optional["ResourceFlavor"] = None,
        work_dir: Optional[str] = None,
    ):
        """初始化 Nextflow 计量器

        Args:
            billing_service: 计费服务实例
            flavor: 资源规格实例
            work_dir: Nextflow 工作目录（包含 trace.txt）
        """
        super().__init__(billing_service, flavor)
        self.work_dir = work_dir
        self.blueprint_id: Optional[str] = None
        self.task_records: List[Dict[str, Any]] = []

    def start_metering(self, record_id: str, context: Dict[str, Any]) -> None:
        """开始计量

        记录工作流开始时间。

        Args:
            record_id: 计算记录 ID
            context: 计量上下文
                - work_dir: 工作目录
                - blueprint_id: 蓝图 ID
                - user_id: 用户 ID
                - project_id: 项目 ID
        """
        self._record_start(record_id, context)

        self.work_dir = context.get("work_dir", self.work_dir)
        self.blueprint_id = context.get("blueprint_id")

        # 清空之前的任务记录
        self.task_records = []

        log.info(
            f"Nextflow 计量开始: record_id={record_id}, blueprint_id={self.blueprint_id}"
        )

    def stop_metering(self, record_id: str) -> MeteringResult:
        """停止计量

        解析 trace.txt，计算总费用。

        Args:
            record_id: 计算记录 ID

        Returns:
            MeteringResult: 计量结果
        """
        duration = self._calculate_duration()

        # 解析 trace.txt
        if self.work_dir:
            trace_path = os.path.join(self.work_dir, "trace.txt")
            if os.path.exists(trace_path):
                self.task_records = self.parse_trace_file(trace_path)
                log.info(
                    f"解析 trace.txt: {len(self.task_records)} 个任务, path={trace_path}"
                )
            else:
                log.warning(f"trace.txt 不存在: {trace_path}")

        # 计算总时长和 CPU 时间
        total_duration = sum(t.get("realtime", 0) for t in self.task_records)
        total_cpu_seconds = sum(
            t.get("realtime", 0) * t.get("cpus", 1) for t in self.task_records
        )

        # 统计成功/失败任务
        success_count = sum(
            1 for t in self.task_records if t.get("status") == "COMPLETED"
        )
        failed_count = len(self.task_records) - success_count

        # 创建结果
        result = MeteringResult(
            duration_seconds=duration,
            cpu_seconds=total_cpu_seconds,
            cost_credits=0.0,  # 先计算费用
            details={
                "blueprint_id": self.blueprint_id,
                "task_count": len(self.task_records),
                "success_count": success_count,
                "failed_count": failed_count,
                "total_task_duration": total_duration,
                "tasks": self.task_records[:10],  # 只保存前 10 个任务详情
            },
        )

        # 计算费用
        result.cost_credits = self.calculate_cost(result)

        log.info(
            f"Nextflow 计量结束: record_id={record_id}, "
            f"tasks={len(self.task_records)}, cost={result.cost_credits} CU"
        )

        return result

    def parse_trace_file(self, trace_path: str) -> List[Dict[str, Any]]:
        """解析 Nextflow trace.txt 文件

        trace.txt 是 TSV 格式，包含每个 task 的执行信息。

        Args:
            trace_path: trace.txt 文件路径

        Returns:
            List[Dict]: 任务记录列表
        """
        try:
            import pandas as pd

            df = pd.read_csv(trace_path, sep="\t")

            tasks = []
            for _, row in df.iterrows():
                task = {
                    "task_id": str(row.get("task_id", "")),
                    "process": str(row.get("process", "")),
                    "realtime": self._parse_duration(str(row.get("realtime", "0s"))),
                    "cpus": self._parse_cpu(str(row.get("cpus", "1"))),
                    "memory": self._parse_memory(str(row.get("memory", "0"))),
                    "status": str(row.get("status", "COMPLETED")),
                    "container": str(row.get("container", "")),
                    "exit": row.get("exit", 0),
                }
                tasks.append(task)

            return tasks

        except ImportError:
            log.warning("pandas 未安装，使用简单解析")
            return self._parse_trace_simple(trace_path)

        except Exception as e:
            log.error(f"解析 trace.txt 失败: {e}")
            return []

    def _parse_trace_simple(self, trace_path: str) -> List[Dict[str, Any]]:
        """简单解析 trace.txt（不依赖 pandas）

        Args:
            trace_path: trace.txt 文件路径

        Returns:
            List[Dict]: 任务记录列表
        """
        tasks = []

        try:
            with open(trace_path, "r") as f:
                lines = f.readlines()

            if not lines:
                return tasks

            # 解析表头
            header = lines[0].strip().split("\t")
            process_idx = header.index("process") if "process" in header else -1
            realtime_idx = header.index("realtime") if "realtime" in header else -1
            status_idx = header.index("status") if "status" in header else -1

            # 解析数据行
            for line in lines[1:]:
                if not line.strip():
                    continue

                values = line.strip().split("\t")
                task = {
                    "process": values[process_idx] if process_idx >= 0 else "",
                    "realtime": self._parse_duration(
                        values[realtime_idx] if realtime_idx >= 0 else "0s"
                    ),
                    "status": values[status_idx] if status_idx >= 0 else "COMPLETED",
                }
                tasks.append(task)

        except Exception as e:
            log.error(f"简单解析 trace.txt 失败: {e}")

        return tasks

    def _parse_duration(self, duration_str: str) -> float:
        """解析时长字符串

        支持格式: "1h30m15s", "45m30s", "120s", "1.5h"

        Args:
            duration_str: 时长字符串

        Returns:
            float: 时长（秒）
        """
        if not duration_str or duration_str == "-":
            return 0.0

        total_seconds = 0.0

        # 匹配 h/m/s
        h_match = re.search(r"(\d+\.?\d*)h", duration_str)
        m_match = re.search(r"(\d+\.?\d*)m", duration_str)
        s_match = re.search(r"(\d+\.?\d*)s", duration_str)

        if h_match:
            total_seconds += float(h_match.group(1)) * 3600
        if m_match:
            total_seconds += float(m_match.group(1)) * 60
        if s_match:
            total_seconds += float(s_match.group(1))

        return total_seconds

    def _parse_cpu(self, cpu_str: str) -> int:
        """解析 CPU 数量

        Args:
            cpu_str: CPU 字符串

        Returns:
            int: CPU 数量
        """
        if not cpu_str or cpu_str == "-":
            return 1

        try:
            return int(float(cpu_str))
        except ValueError:
            return 1

    def _parse_memory(self, memory_str: str) -> float:
        """解析内存大小

        支持格式: "8 GB", "4GB", "1024 MB"

        Args:
            memory_str: 内存字符串

        Returns:
            float: 内存（GB）
        """
        if not memory_str or memory_str == "-":
            return 0.0

        memory_str = memory_str.upper().replace(" ", "")

        if "GB" in memory_str:
            return float(re.search(r"(\d+\.?\d*)", memory_str).group(1))
        elif "MB" in memory_str:
            return float(re.search(r"(\d+\.?\d*)", memory_str).group(1)) / 1024

        return 0.0

    def calculate_cost(self, result: MeteringResult) -> float:
        """计算费用

        按 task 累计计费，支持差异化定价。

        Args:
            result: 计量结果

        Returns:
            float: 费用（CU）
        """
        total_cost = 0.0

        for task in self.task_records:
            # 只计算成功的任务
            if task.get("status") != "COMPLETED":
                continue

            duration_minutes = task.get("realtime", 0) / 60.0
            process_name = task.get("process", "")

            # 查找匹配的 flavor（如果有）
            flavor = self._get_flavor_for_process(process_name)

            if flavor:
                # 使用 flavor 定价
                min_minutes = flavor.min_charge_minutes
                actual_minutes = max(duration_minutes, min_minutes)
                cost = flavor.price_per_minute * actual_minutes
                cost *= 1 - flavor.discount_rate
            else:
                # 使用默认定价
                price_per_minute = self.get_price_per_minute("blueprint")
                min_minutes = self.get_min_charge_minutes("blueprint")
                actual_minutes = max(duration_minutes, min_minutes)
                cost = price_per_minute * actual_minutes

            total_cost += cost

        return round(total_cost, 2)

    def _get_flavor_for_process(
        self, process_name: str
    ) -> Optional["ResourceFlavor"]:
        """根据 process 名称查找匹配的 ResourceFlavor

        可根据实际需求实现 process 到 flavor 的映射逻辑。

        Args:
            process_name: Nextflow process 名称

        Returns:
            ResourceFlavor: 匹配的资源规格，或 None
        """
        # TODO: 实现实际的映射逻辑
        # 可以根据 process 名称中的关键词匹配
        # 例如：包含 "gpu" 的使用 GPU flavor

        if not self.billing_service:
            return None

        # 简单示例：根据名称关键词判断
        process_lower = process_name.lower()

        if "gpu" in process_lower:
            # 查找 GPU flavor
            pass
        elif "highmem" in process_lower:
            # 查找高内存 flavor
            pass

        return None

    def get_task_summary(self) -> Dict[str, Any]:
        """获取任务摘要统计

        Returns:
            Dict: 任务统计信息
        """
        if not self.task_records:
            return {}

        success_tasks = [
            t for t in self.task_records if t.get("status") == "COMPLETED"
        ]
        failed_tasks = [
            t for t in self.task_records if t.get("status") != "COMPLETED"
        ]

        total_duration = sum(t.get("realtime", 0) for t in success_tasks)
        avg_duration = total_duration / len(success_tasks) if success_tasks else 0

        return {
            "total_tasks": len(self.task_records),
            "success_count": len(success_tasks),
            "failed_count": len(failed_tasks),
            "total_duration_seconds": total_duration,
            "avg_duration_seconds": avg_duration,
        }