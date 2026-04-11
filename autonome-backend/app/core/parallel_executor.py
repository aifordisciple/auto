"""
Parallel Executor Module - 通用并行执行框架

提供样本级和分组级的并行执行能力，支持：
- 样本级并行：每个样本独立执行
- 分组级并行：按分组顺序执行，组内并行
- 线程池管理
- 进度回调和错误处理
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from dataclasses import dataclass, field
from datetime import datetime
import traceback

from app.core.sample_table import SampleInfo, SampleTable


@dataclass
class ExecutionResult:
    """单个样本执行结果"""

    sample_name: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ExecutionReport:
    """执行报告"""

    total_samples: int
    successful: int
    failed: int
    results: List[ExecutionResult]
    total_duration_seconds: float
    start_time: str
    end_time: str


class ParallelTask(ABC):
    """
    并行任务基类

    继承此类实现具体的并行处理逻辑。

    Examples:
        class FastQCTask(ParallelTask):
            def get_sample_params(self, sample: SampleInfo) -> Dict[str, Any]:
                return {"input_file": sample.path, "output_dir": f"/output/{sample.name}"}

            def execute_sample(self, sample: SampleInfo, params: Dict[str, Any]) -> Dict[str, Any]:
                # 执行 FastQC
                result = run_fastqc(params["input_file"], params["output_dir"])
                return {"output_file": result}
    """

    @abstractmethod
    def get_sample_params(self, sample: SampleInfo) -> Dict[str, Any]:
        """
        获取单个样本的执行参数

        Args:
            sample: 样本信息

        Returns:
            传递给 execute_sample 的参数字典
        """
        pass

    @abstractmethod
    def execute_sample(self, sample: SampleInfo, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个样本的处理

        Args:
            sample: 样本信息
            params: 由 get_sample_params 返回的参数

        Returns:
            执行结果字典
        """
        pass

    def on_sample_start(self, sample: SampleInfo) -> None:
        """单个样本开始前的回调（可选重写）"""
        pass

    def on_sample_complete(self, sample: SampleInfo, result: ExecutionResult) -> None:
        """单个样本完成后的回调（可选重写）"""
        pass

    def on_group_start(self, group: str, samples: List[SampleInfo]) -> None:
        """分组开始前的回调（可选重写）"""
        pass

    def on_group_complete(self, group: str, results: List[ExecutionResult]) -> None:
        """分组完成后的回调（可选重写）"""
        pass

    def on_all_complete(self, report: ExecutionReport) -> None:
        """所有样本完成后的回调（可选重写）"""
        pass


class ParallelExecutor:
    """
    通用并行执行器

    支持两种并行模式：
    - sample: 样本级并行，所有样本同时执行
    - group: 分组级并行，分组顺序执行，组内样本并行

    Examples:
        table = SampleTable.parse(tsv_content)
        task = MyParallelTask()
        executor = ParallelExecutor(table, task, max_workers=8)
        report = executor.run()
    """

    def __init__(
        self,
        sample_table: SampleTable,
        task: ParallelTask,
        max_workers: Optional[int] = None,
        parallel_mode: str = "sample",
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ):
        """
        初始化并行执行器

        Args:
            sample_table: 样本表
            task: 并行任务实例
            max_workers: 最大工作线程数，默认为 CPU 核数
            parallel_mode: 并行模式 ("sample" | "group")
            progress_callback: 进度回调函数 (completed, total, message)
        """
        self.sample_table = sample_table
        self.task = task
        self.max_workers = max_workers or multiprocessing.cpu_count()
        self.parallel_mode = parallel_mode
        self.progress_callback = progress_callback

        # 执行状态
        self._completed_count = 0
        self._total_count = len(sample_table.samples)
        self._results: List[ExecutionResult] = []

    def run(self) -> ExecutionReport:
        """
        执行并行任务

        Returns:
            执行报告
        """
        start_time = datetime.now()
        self._results = []
        self._completed_count = 0

        if self.parallel_mode == "group":
            self._run_by_groups()
        else:
            self._run_all_samples()

        end_time = datetime.now()

        # 生成报告
        successful = sum(1 for r in self._results if r.success)
        failed = len(self._results) - successful

        report = ExecutionReport(
            total_samples=self._total_count,
            successful=successful,
            failed=failed,
            results=self._results,
            total_duration_seconds=(end_time - start_time).total_seconds(),
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
        )

        # 完成回调
        self.task.on_all_complete(report)

        return report

    def _run_by_groups(self) -> None:
        """按分组执行：分组顺序执行，组内样本并行"""
        for group_name, sample_names in self.sample_table.groups.items():
            samples = self.sample_table.get_samples_by_group(group_name)

            # 分组开始回调
            self.task.on_group_start(group_name, samples)

            # 并行执行组内样本
            group_results = self._execute_samples(samples)

            # 分组完成回调
            self.task.on_group_complete(group_name, group_results)

            self._results.extend(group_results)

    def _run_all_samples(self) -> None:
        """样本级并行：所有样本同时执行"""
        self._results = self._execute_samples(self.sample_table.samples)

    def _execute_samples(self, samples: List[SampleInfo]) -> List[ExecutionResult]:
        """
        并行执行样本列表

        Args:
            samples: 样本列表

        Returns:
            执行结果列表
        """
        results: List[ExecutionResult] = []

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(samples))) as executor:
            futures = {}

            for sample in samples:
                # 获取样本参数
                params = self.task.get_sample_params(sample)

                # 样本开始回调
                self.task.on_sample_start(sample)

                # 提交任务
                future = executor.submit(self._execute_single, sample, params)
                futures[future] = sample

            # 收集结果
            for future in as_completed(futures):
                sample = futures[future]
                try:
                    result = future.result()
                    results.append(result)

                    # 更新进度
                    self._completed_count += 1
                    if self.progress_callback:
                        self.progress_callback(
                            self._completed_count,
                            self._total_count,
                            f"完成 {sample.name}",
                        )

                    # 样本完成回调
                    self.task.on_sample_complete(sample, result)

                except Exception as e:
                    # 记录异常结果
                    error_result = ExecutionResult(
                        sample_name=sample.name,
                        success=False,
                        error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
                    )
                    results.append(error_result)
                    self._completed_count += 1

        return results

    def _execute_single(
        self, sample: SampleInfo, params: Dict[str, Any]
    ) -> ExecutionResult:
        """
        执行单个样本

        Args:
            sample: 样本信息
            params: 执行参数

        Returns:
            执行结果
        """
        start_time = datetime.now()

        try:
            result_data = self.task.execute_sample(sample, params)
            duration = (datetime.now() - start_time).total_seconds()

            return ExecutionResult(
                sample_name=sample.name,
                success=True,
                result=result_data,
                duration_seconds=duration,
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                sample_name=sample.name,
                success=False,
                error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
                duration_seconds=duration,
            )


class SimpleParallelTask(ParallelTask):
    """
    简单并行任务包装器

    用于快速创建并行任务，无需继承。

    Examples:
        def process(sample, params):
            # 处理逻辑
            return {"output": params["input"]}

        task = SimpleParallelTask(
            param_generator=lambda s: {"input": s.path},
            executor=process
        )
    """

    def __init__(
        self,
        param_generator: Callable[[SampleInfo], Dict[str, Any]],
        executor: Callable[[SampleInfo, Dict[str, Any]], Dict[str, Any]],
    ):
        """
        Args:
            param_generator: 参数生成函数 (sample) -> params
            executor: 执行函数 (sample, params) -> result
        """
        self._param_generator = param_generator
        self._executor = executor

    def get_sample_params(self, sample: SampleInfo) -> Dict[str, Any]:
        return self._param_generator(sample)

    def execute_sample(self, sample: SampleInfo, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._executor(sample, params)


def run_parallel(
    sample_table: SampleTable,
    executor_func: Callable[[SampleInfo, Dict[str, Any]], Dict[str, Any]],
    param_func: Optional[Callable[[SampleInfo], Dict[str, Any]]] = None,
    max_workers: Optional[int] = None,
    parallel_mode: str = "sample",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> ExecutionReport:
    """
    快捷并行执行函数

    Args:
        sample_table: 样本表
        executor_func: 执行函数 (sample, params) -> result
        param_func: 参数生成函数 (sample) -> params，默认返回空字典
        max_workers: 最大工作线程数
        parallel_mode: 并行模式
        progress_callback: 进度回调

    Returns:
        执行报告

    Examples:
        def my_process(sample, params):
            # 处理样本
            return {"status": "done"}

        report = run_parallel(
            sample_table,
            executor_func=my_process,
            param_func=lambda s: {"input": s.path}
        )
    """
    if param_func is None:
        param_func = lambda s: {"path": s.path}

    task = SimpleParallelTask(param_generator=param_func, executor=executor_func)

    executor = ParallelExecutor(
        sample_table=sample_table,
        task=task,
        max_workers=max_workers,
        parallel_mode=parallel_mode,
        progress_callback=progress_callback,
    )

    return executor.run()