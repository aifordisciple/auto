"""
规划协调器 (Planning Coordinator) - 4+1 生信专家委员会调度核心

核心职责:
1. 任务复杂度评估与规划模式选择
2. 并行调度多个专业规划 Agent
3. 超时控制与自动降级决策
4. 规划结果汇总与输出

三种规划模式:
- SINGLE_AGENT: 首席研究员直接输出 (<10s)
- DUAL_AGENT: 数据架构师 + 首席研究员 (<15s)
- FULL_PARALLEL: 4 专家并行 + 首席研究员仲裁 (<25s)

Author: Autonome AI Team
Created: 2026-03-21
"""

from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import time
import json

from app.core.logger import log


class PlanningMode(str, Enum):
    """
    规划模式枚举

    SINGLE_AGENT: 简单任务，首席研究员直接输出
    DUAL_AGENT: 中等任务，数据架构师 + 首席研究员
    FULL_PARALLEL: 复杂任务，4 专家并行 + 首席研究员仲裁
    """
    SINGLE_AGENT = "single_agent"
    DUAL_AGENT = "dual_agent"
    FULL_PARALLEL = "full_parallel"


@dataclass
class PlanningContext:
    """
    规划上下文数据结构

    包含规划所需的所有输入信息

    Attributes:
        user_request: 用户原始请求文本
        project_id: 项目 ID
        project_context: 项目上下文信息（目录树、选中文件等）
        available_skills: 可用 SKILL 列表（Markdown 格式）
        llm_config: LLM 配置（api_key, base_url, model_name）
        timeout_seconds: 规划超时时间（秒）
        mode: 规划模式（自动判断或手动指定）
    """
    user_request: str
    project_id: int
    project_context: str
    available_skills: str = ""
    llm_config: Dict[str, str] = field(default_factory=lambda: {
        "api_key": "",
        "base_url": "",
        "model_name": ""
    })
    timeout_seconds: float = 60.0
    mode: Optional[PlanningMode] = None  # None 表示自动判断


@dataclass
class ExpertReports:
    """
    专家报告集合

    汇总四个专业规划 Agent 的输出

    Attributes:
        data_qc_report: Agent A（数据与质控架构师）的报告
        algorithm_report: Agent B（算法与统计学专家）的报告
        annotation_report: Agent C（系统生物学专家）的报告
        visualization_report: Agent D（可视化设计师）的报告
        metadata: 元数据（耗时、成功状态等）
    """
    data_qc_report: Optional[Dict[str, Any]] = None
    algorithm_report: Optional[Dict[str, Any]] = None
    annotation_report: Optional[Dict[str, Any]] = None
    visualization_report: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_successful_reports(self) -> Dict[str, Dict[str, Any]]:
        """获取所有成功生成的报告"""
        reports = {}
        if self.data_qc_report:
            reports["data_qc"] = self.data_qc_report
        if self.algorithm_report:
            reports["algorithm"] = self.algorithm_report
        if self.annotation_report:
            reports["annotation"] = self.annotation_report
        if self.visualization_report:
            reports["visualization"] = self.visualization_report
        return reports

    def get_success_count(self) -> int:
        """获取成功报告数量"""
        return len(self.get_successful_reports())

    def get_failed_agents(self) -> List[str]:
        """获取失败的 Agent 列表"""
        failed = []
        if not self.data_qc_report:
            failed.append("data_qc")
        if not self.algorithm_report:
            failed.append("algorithm")
        if not self.annotation_report:
            failed.append("annotation")
        if not self.visualization_report:
            failed.append("visualization")
        return failed


# 复杂任务关键词列表（用于自动判断规划模式）
COMPLEX_TASK_KEYWORDS = [
    # 流程类
    "全流程", "完整分析", "pipeline", "流程", "端到端", "多组学",
    # 分析类型
    "RNA-Seq", "rna-seq", "rnaseq", "转录组",
    "单细胞", "single-cell", "scRNA", "单细胞RNA",
    "ChIP-Seq", "chip-seq",
    "ATAC-Seq", "atac-seq",
    "甲基化", "methylation", "BS-Seq",
    "全基因组", "WGS", "WES", "外显子",
    "宏基因组", "Metagenomic",
    # 具体流程
    "质控", "比对", "定量", "差异", "注释", "富集",
    "预处理", "标准化", "归一化",
    "降维", "聚类", "细胞类型",
    # 文献相关
    "复刻", "复现", "重现", "文献", "Figure",
    # 高级分析
    "拟时序", "轨迹", "细胞通讯", "CellChat",
]

MEDIUM_TASK_KEYWORDS = [
    "差异分析", "DEG", "DESeq", "edgeR",
    "聚类分析", "分群",
    "功能富集", "GO", "KEGG",
    "可视化", "绘图", "图表",
    "预处理", "质控",
]


class PlanningCoordinator:
    """
    规划协调器 - 4+1 生信专家委员会的调度核心

    核心功能:
    1. determine_planning_mode(): 根据请求复杂度选择规划模式
    2. plan(): 主入口，执行并行规划
    3. _single_agent_plan(): 首席研究员直接输出
    4. _dual_agent_plan(): 数据架构师 + 首席研究员
    5. _full_parallel_plan(): 4 专家并行 + 首席研究员仲裁

    工作流程:
    1. 接收用户请求，判断复杂度
    2. 选择合适的规划模式
    3. 并行调度专业 Agent（如需要）
    4. 收集各专家报告
    5. 调用首席研究员仲裁并生成最终蓝图

    自动降级机制:
    - 当部分专家失败时，自动使用剩余成功报告
    - 当多数专家失败时，自动降级到更简单的模式
    """

    def __init__(self, context: PlanningContext):
        """
        初始化规划协调器

        Args:
            context: 规划上下文，包含所有必要信息
        """
        self.context = context
        self.start_time = time.time()
        self.mode = context.mode or self.determine_planning_mode(context.user_request)

        log.info(f"🎯 [PlanningCoordinator] 初始化完成，模式: {self.mode.value}")

    def determine_planning_mode(self, user_request: str) -> PlanningMode:
        """
        根据用户请求复杂度自动判断规划模式

        判断逻辑:
        1. 统计复杂任务关键词命中数
        2. 检查是否包含流程描述（第一步、第二步等）
        3. 统计中等任务关键词命中数

        判断标准:
        - ≥3 个复杂关键词 或 明确流程描述 → FULL_PARALLEL
        - ≥2 个中等关键词 或 1-2 个复杂关键词 → DUAL_AGENT
        - 其他 → SINGLE_AGENT

        Args:
            user_request: 用户请求文本

        Returns:
            规划模式枚举值
        """
        request_lower = user_request.lower()

        # 统计复杂关键词命中（去重处理，避免 "RNA-Seq" 和 "rna-seq" 重复计数）
        matched_complex = set()
        for kw in COMPLEX_TASK_KEYWORDS:
            if kw.lower() in request_lower:
                # 规范化关键词：统一转小写，处理常见的同义变体
                normalized = kw.lower()
                # 处理已知的同义词变体，确保同一概念只计一次
                # 例如: rna-seq, rnaseq, RNA-Seq 视为同一概念
                if normalized in ['rna-seq', 'rnaseq']:
                    normalized = 'rna-seq'
                elif normalized in ['single-cell', 'scrna', '单细胞rna']:
                    normalized = 'single-cell'
                elif normalized in ['chip-seq', 'chipseq']:
                    normalized = 'chip-seq'
                elif normalized in ['atac-seq', 'atacseq']:
                    normalized = 'atac-seq'
                matched_complex.add(normalized)
        complex_count = len(matched_complex)

        # 检查流程描述
        flow_indicators = ["第一步", "第二步", "第三步", "1.", "2.", "3.", "首先", "然后", "最后"]
        has_flow_description = any(ind in user_request for ind in flow_indicators)

        # 统计中等关键词命中（同样去重处理）
        matched_medium = set()
        for kw in MEDIUM_TASK_KEYWORDS:
            if kw.lower() in request_lower:
                matched_medium.add(kw.lower())
        medium_count = len(matched_medium)

        # 判断模式
        if complex_count >= 3 or has_flow_description:
            return PlanningMode.FULL_PARALLEL
        elif medium_count >= 2 or 1 <= complex_count <= 2:
            return PlanningMode.DUAL_AGENT
        else:
            return PlanningMode.SINGLE_AGENT

    async def plan(self) -> Dict[str, Any]:
        """
        执行规划 - 主入口方法（两阶段架构）

        新架构：数据探测 → 规划生成

        根据规划模式选择对应的规划策略:
        - SINGLE_AGENT: 直接调用首席研究员
        - DUAL_AGENT: 调用数据架构师 + 首席研究员
        - FULL_PARALLEL: 4 专家并行 + 首席研究员仲裁

        Returns:
            规划结果字典，包含:
            - status: 状态（success / degraded / error）
            - blueprint: 生成的蓝图
            - metadata: 元数据（模式、耗时、专家来源等）
            - probe_report: 数据探测报告
        """
        log.info(f"🚀 [PlanningCoordinator] 开始规划，模式: {self.mode.value}")
        self.start_time = time.time()

        # ========== 阶段 1: 数据探测 ==========
        probe_report = None
        try:
            from app.services.data_probe_service import DataProbeService

            probe_service = DataProbeService(max_files_to_preview=10)
            probe_report = await probe_service.probe_project(str(self.context.project_id))

            # 注入探测结果到规划上下文
            if probe_report and probe_report.data_files:
                probe_context = probe_report.to_prompt_context()
                self.context.project_context += f"\n\n{probe_context}"
                log.info(f"🔍 [PlanningCoordinator] 数据探测完成 - {len(probe_report.data_files)} 个文件")
            else:
                log.info(f"🔍 [PlanningCoordinator] 数据探测完成 - 未发现数据文件")

        except Exception as probe_error:
            log.warning(f"⚠️ [PlanningCoordinator] 数据探测失败，继续规划: {probe_error}")
            # 探测失败不阻断规划流程

        # ========== 阶段 2: 规划生成 ==========
        try:
            if self.mode == PlanningMode.SINGLE_AGENT:
                result = await self._single_agent_plan()
            elif self.mode == PlanningMode.DUAL_AGENT:
                result = await self._dual_agent_plan()
            else:  # FULL_PARALLEL
                result = await self._full_parallel_plan()

            # 添加元数据
            elapsed_ms = int((time.time() - self.start_time) * 1000)
            result["metadata"]["planning_time_ms"] = elapsed_ms
            result["metadata"]["planning_mode"] = self.mode.value

            # 添加探测报告
            if probe_report:
                result["probe_report"] = {
                    "total_data_files": probe_report.total_data_files,
                    "probe_time_ms": probe_report.probe_time_ms,
                    "data_files": [
                        {
                            "path": f.file_path,
                            "type": f.file_type,
                            "columns": f.columns[:10] if f.columns else None
                        }
                        for f in probe_report.data_files
                    ]
                }

            log.info(f"✅ [PlanningCoordinator] 规划完成，耗时: {elapsed_ms}ms")
            return result

        except asyncio.TimeoutError:
            log.warning(f"⚠️ [PlanningCoordinator] 规划超时，尝试降级")
            return await self._handle_timeout()

        except Exception as e:
            log.error(f"❌ [PlanningCoordinator] 规划失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "blueprint": None,
                "metadata": {
                    "planning_mode": self.mode.value,
                    "error_type": type(e).__name__
                }
            }

    async def _single_agent_plan(self) -> Dict[str, Any]:
        """
        单 Agent 规划模式

        直接调用首席研究员 Agent 生成蓝图
        适用于简单任务（单步骤、无依赖）

        Returns:
            规划结果字典
        """
        from app.agent.chief_pi_agent import ChiefPIAgent

        log.info(f"🧙‍♂️ [PlanningCoordinator] 单 Agent 模式，调用首席研究员")

        chief_agent = ChiefPIAgent(
            llm_config=self.context.llm_config,
            project_id=self.context.project_id,
            project_context=self.context.project_context,
            available_skills=self.context.available_skills
        )

        blueprint = await chief_agent.generate_blueprint(
            user_request=self.context.user_request,
            expert_reports=None  # 无专家报告
        )

        return {
            "status": "success",
            "blueprint": blueprint,
            "metadata": {
                "expert_sources": [],
                "mode_detail": "single_agent_direct"
            }
        }

    async def _dual_agent_plan(self) -> Dict[str, Any]:
        """
        双 Agent 规划模式

        调用数据架构师 Agent 收集数据和质控策略
        然后调用首席研究员 Agent 汇总生成蓝图
        适用于中等任务（2-3 步骤）

        Returns:
            规划结果字典
        """
        from app.agent.planner_agents import DataQCPlanner
        from app.agent.chief_pi_agent import ChiefPIAgent

        log.info(f"🕵️‍♂️ [PlanningCoordinator] 双 Agent 模式")

        # Step 1: 数据架构师规划
        data_qc_agent = DataQCPlanner(
            llm_config=self.context.llm_config,
            project_id=self.context.project_id,
            project_context=self.context.project_context
        )

        data_qc_report = await data_qc_agent.plan(
            user_request=self.context.user_request
        )

        # 检查是否成功
        if not data_qc_report:
            log.warning(f"⚠️ [PlanningCoordinator] 数据架构师失败，降级到单 Agent")
            return await self._single_agent_plan()

        # Step 2: 首席研究员汇总
        expert_reports = ExpertReports(data_qc_report=data_qc_report)

        chief_agent = ChiefPIAgent(
            llm_config=self.context.llm_config,
            project_id=self.context.project_id,
            project_context=self.context.project_context,
            available_skills=self.context.available_skills
        )

        blueprint = await chief_agent.generate_blueprint(
            user_request=self.context.user_request,
            expert_reports=expert_reports
        )

        return {
            "status": "success",
            "blueprint": blueprint,
            "metadata": {
                "expert_sources": ["data_qc"],
                "mode_detail": "dual_agent"
            }
        }

    async def _full_parallel_plan(self) -> Dict[str, Any]:
        """
        全并行规划模式

        并行调用 4 个专业规划 Agent:
        - Agent A: 数据与质控架构师
        - Agent B: 算法与统计学专家
        - Agent C: 系统生物学专家
        - Agent D: 可视化设计师

        然后调用首席研究员 Agent 仲裁并生成最终蓝图

        Returns:
            规划结果字典
        """
        from app.agent.planner_agents import (
            DataQCPlanner,
            AlgorithmStatistician,
            SystemsBiologist,
            VisualArtist
        )
        from app.agent.chief_pi_agent import ChiefPIAgent

        log.info(f"🚀 [PlanningCoordinator] 全并行模式，启动 4 个专家 Agent")

        # 创建 4 个专家 Agent
        agents = {
            "data_qc": DataQCPlanner(
                llm_config=self.context.llm_config,
                project_id=self.context.project_id,
                project_context=self.context.project_context
            ),
            "algorithm": AlgorithmStatistician(
                llm_config=self.context.llm_config,
                available_skills=self.context.available_skills
            ),
            "annotation": SystemsBiologist(
                llm_config=self.context.llm_config
            ),
            "visualization": VisualArtist(
                llm_config=self.context.llm_config
            )
        }

        # 并行执行（带超时控制）
        # 每个专家 Agent 预留 3 分钟，确保 LLM 有足够响应时间
        # 并行模式下，总超时不应太短，否则容易全部失败
        timeout_per_agent = max(180.0, self.context.timeout_seconds / 2)

        async def run_agent_with_timeout(name: str, agent):
            """带超时的 Agent 执行"""
            try:
                result = await asyncio.wait_for(
                    agent.plan(user_request=self.context.user_request),
                    timeout=timeout_per_agent
                )
                return name, result
            except asyncio.TimeoutError:
                log.warning(f"⚠️ [PlanningCoordinator] Agent {name} 超时")
                return name, None
            except Exception as e:
                log.error(f"❌ [PlanningCoordinator] Agent {name} 失败: {e}")
                return name, None

        # 并行执行所有 Agent
        tasks = [run_agent_with_timeout(name, agent) for name, agent in agents.items()]
        results = await asyncio.gather(*tasks)

        # 收集结果
        reports = ExpertReports()
        for name, result in results:
            if result:
                if name == "data_qc":
                    reports.data_qc_report = result
                elif name == "algorithm":
                    reports.algorithm_report = result
                elif name == "annotation":
                    reports.annotation_report = result
                elif name == "visualization":
                    reports.visualization_report = result

        # 检查成功率
        success_count = reports.get_success_count()
        log.info(f"📊 [PlanningCoordinator] 专家报告完成: {success_count}/4")

        # 自动降级判断
        if success_count < 2:
            log.warning(f"⚠️ [PlanningCoordinator] 成功率过低 ({success_count}/4)，降级到双 Agent")
            return await self._dual_agent_plan()

        # 调用首席研究员仲裁
        chief_agent = ChiefPIAgent(
            llm_config=self.context.llm_config,
            project_id=self.context.project_id,
            project_context=self.context.project_context,
            available_skills=self.context.available_skills
        )

        blueprint = await chief_agent.arbitrate_and_generate(
            user_request=self.context.user_request,
            expert_reports=reports
        )

        # 构建结果
        status = "success" if success_count == 4 else "success_with_degradation"
        result = {
            "status": status,
            "blueprint": blueprint,
            "metadata": {
                "expert_sources": list(reports.get_successful_reports().keys()),
                "failed_agents": reports.get_failed_agents(),
                "mode_detail": "full_parallel"
            }
        }

        if success_count < 4:
            result["metadata"]["degradation_message"] = f"部分专家规划失败，已使用 {success_count} 个成功报告"

        return result

    async def _handle_timeout(self) -> Dict[str, Any]:
        """
        处理超时情况 - 自动降级

        降级链:
        FULL_PARALLEL → DUAL_AGENT → SINGLE_AGENT

        Returns:
            降级后的规划结果
        """
        if self.mode == PlanningMode.FULL_PARALLEL:
            log.info(f"🔄 [PlanningCoordinator] 从 FULL_PARALLEL 降级到 DUAL_AGENT")
            self.mode = PlanningMode.DUAL_AGENT
            return await self._dual_agent_plan()

        elif self.mode == PlanningMode.DUAL_AGENT:
            log.info(f"🔄 [PlanningCoordinator] 从 DUAL_AGENT 降级到 SINGLE_AGENT")
            self.mode = PlanningMode.SINGLE_AGENT
            return await self._single_agent_plan()

        else:
            return {
                "status": "error",
                "error": "规划超时，已尝试所有降级方案",
                "blueprint": None,
                "metadata": {
                    "planning_mode": "timeout_exhausted"
                }
            }


async def execute_planning(
    user_request: str,
    llm_config: Dict[str, str],
    project_id,  # 接受 int 或 str 类型
    project_context: str,
    available_skills: str = "",
    force_mode: Optional[str] = None
) -> Dict[str, Any]:
    """
    执行规划 - 便捷入口函数

    这是外部调用的主要入口，封装了 PlanningCoordinator 的使用

    Args:
        user_request: 用户请求文本
        llm_config: LLM 配置（api_key, base_url, model_name）
        project_id: 项目 ID（支持 int 或 str 类型）
        project_context: 项目上下文
        available_skills: 可用 SKILL 列表
        force_mode: 强制指定规划模式（"single" / "dual" / "full"）

    Returns:
        规划结果字典

    Example:
        result = await execute_planning(
            user_request="对这个单细胞数据做完整分析",
            llm_config={"api_key": "xxx", "base_url": "https://api.xxx.com", "model_name": "gpt-4"},
            project_id=1,
            project_context="项目目录树...",
            available_skills="SKILL 列表..."
        )
    """
    # 确定规划模式
    mode = None
    if force_mode:
        mode_map = {
            "single": PlanningMode.SINGLE_AGENT,
            "dual": PlanningMode.DUAL_AGENT,
            "full": PlanningMode.FULL_PARALLEL
        }
        mode = mode_map.get(force_mode.lower())

    # 创建上下文
    context = PlanningContext(
        user_request=user_request,
        project_id=project_id,
        project_context=project_context,
        available_skills=available_skills,
        llm_config=llm_config,
        mode=mode
    )

    # 创建协调器并执行规划
    coordinator = PlanningCoordinator(context)
    return await coordinator.plan()


log.info("🎯 PlanningCoordinator 模块已加载")