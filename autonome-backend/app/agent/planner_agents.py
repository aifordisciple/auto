"""
专业规划 Agent 模块 - 4 生信专家委员会成员

包含四个专业规划 Agent:
1. 🕵️‍♂️ DataQCPlanner: 数据与质控架构师
2. 🧮 AlgorithmStatistician: 算法与统计学专家
3. 🧬 SystemsBiologist: 系统生物学与注释专家
4. 🎨 VisualArtist: 出版级可视化设计师

每个 Agent 专注于一个领域，提供精准的规划建议

Author: Autonome AI Team
Created: 2026-03-21
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logger import log
from app.core.content_filter import preprocess_llm_response
from app.tools.probe_tools import peek_tabular_data, scan_workspace


@dataclass
class PlannerAgentConfig:
    """规划 Agent 配置"""
    api_key: str
    base_url: str
    model_name: str
    temperature: float = 0.1


class BasePlannerAgent:
    """
    规划 Agent 基类

    提供通用的 LLM 调用和响应解析功能
    """

    def __init__(
        self,
        llm_config: Dict[str, str],
        agent_name: str,
        agent_role: str,
        temperature: float = 0.1
    ):
        """
        初始化基类

        Args:
            llm_config: LLM 配置
            agent_name: Agent 名称
            agent_role: Agent 角色
            temperature: 温度参数
        """
        self.agent_name = agent_name
        self.agent_role = agent_role

        actual_api_key = llm_config.get("api_key", "") or "ollama-local"

        self.llm = ChatOpenAI(
            api_key=actual_api_key,
            base_url=llm_config.get("base_url", ""),
            model=llm_config.get("model_name", "gpt-4"),
            temperature=temperature,
            max_retries=2
        )

        log.info(f"🤖 [{agent_name}] 初始化完成")

    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        从响应中解析 JSON

        支持多种格式:
        - ```json ... ```
        - 直接 JSON 对象
        - 包含多余文本的混合内容

        Args:
            response: LLM 响应文本

        Returns:
            解析后的字典，失败返回 None
        """
        if not response:
            return None

        # 🔧 预处理：过滤 thinking 标签
        response = preprocess_llm_response(response)

        # 尝试从代码块提取
        json_match = re.search(r'```(?:json)?\s*\n([\s\S]*?)```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试直接解析
        try:
            start = response.find('{')
            if start != -1:
                depth = 0
                for i in range(start, len(response)):
                    if response[i] == '{':
                        depth += 1
                    elif response[i] == '}':
                        depth -= 1
                        if depth == 0:
                            return json.loads(response[start:i+1])
        except json.JSONDecodeError:
            pass

        return None

    async def _invoke_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        调用 LLM 并返回响应

        Args:
            system_prompt: 系统提示
            user_prompt: 用户提示

        Returns:
            LLM 响应文本
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        response = await self.llm.ainvoke(messages)
        return response.content if hasattr(response, 'content') else str(response)


# ============================================================================
# 🕵️‍♂️ Agent A: 数据与质控架构师 (Data & QC Engineer)
# ============================================================================

class DataQCPlanner(BasePlannerAgent):
    """
    🕵️‍♂️ Agent A: 数据与质控架构师

    专属工具: peek_tabular_data, scan_workspace（实际调用探针）

    核心职责:
    1. 实际调用探针预览数据结构（格式、维度、列名）
    2. 确认输入文件格式（10x, h5, exp, BD 等）
    3. 规划预处理和质控策略（UMI 阈值、线粒体比例、Doublet 检测）
    4. 规划样本合并与批次效应消除策略（CCA/rPCA/SCT/Harmony 选择）
    5. 输出数据格式转换方案

    重要设计: 规划前**实际调用探针工具**获取真实数据信息
    """

    def __init__(
        self,
        llm_config: Dict[str, str],
        project_id: int,
        project_context: str
    ):
        """
        初始化数据与质控架构师

        Args:
            llm_config: LLM 配置
            project_id: 项目 ID
            project_context: 项目上下文
        """
        super().__init__(
            llm_config=llm_config,
            agent_name="DataQCPlanner",
            agent_role="数据与质控架构师",
            temperature=0.1
        )
        self.project_id = project_id
        self.project_context = project_context

    async def plan(self, user_request: str) -> Optional[Dict[str, Any]]:
        """
        执行数据与质控规划

        工作流程:
        1. 解析项目上下文，识别输入文件
        2. 实际调用探针工具预览数据
        3. 调用 LLM 生成质控策略
        4. 返回结构化报告

        Args:
            user_request: 用户请求

        Returns:
            数据与质控规划报告
        """
        log.info(f"🕵️‍♂️ [DataQCPlanner] 开始数据与质控规划")

        try:
            # Step 1: 扫描项目目录
            scan_result = await self._scan_project_files()

            # Step 2: 预览数据文件（如果有表格数据）
            preview_result = await self._preview_data_files(scan_result)

            # Step 3: 生成规划报告
            report = await self._generate_report(user_request, scan_result, preview_result)

            log.info(f"✅ [DataQCPlanner] 规划完成")
            return report

        except Exception as e:
            log.error(f"❌ [DataQCPlanner] 规划失败: {e}")
            return None

    async def _scan_project_files(self) -> Dict[str, Any]:
        """扫描项目文件结构"""
        try:
            # 构建项目目录的绝对路径
            # project_id 格式为 "proj_xxx"，目录名为 "project_proj_xxx"
            directory_path = f"/workspace/project_{self.project_id}"

            result = await scan_workspace.ainvoke({
                "directory_path": directory_path
            })
            return {"status": "success", "result": result}
        except Exception as e:
            log.warning(f"⚠️ [DataQCPlanner] 目录扫描失败: {e}")
            return {"status": "error", "error": str(e)}

    async def _preview_data_files(self, scan_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        预览数据文件结构 - 真正实现

        从扫描结果中提取数据文件路径，并预览每个文件的结构
        """
        previews = {}

        # 从扫描结果中提取文件路径
        result_text = scan_result.get("result", "")
        if not result_text:
            return {"status": "skipped", "reason": "扫描结果为空"}

        # 提取数据文件路径（支持多种格式）
        import re
        file_patterns = [
            r'/workspace/[^\s\]\)\}]+\.(tsv|csv|txt|tab|mtx)',
            r'/workspace/[^\s\]\)\}]+\.h5ad',
            r'/workspace/[^\s\]\)\}]+\.(fastq|fq)(?:\.gz)?',
            r'/workspace/[^\s\]\)\}]+\.(bam|sam)',
        ]

        data_files = []
        for pattern in file_patterns:
            matches = re.findall(pattern, result_text, re.IGNORECASE)
            for match in matches:
                # match 可能是元组或字符串
                if isinstance(match, tuple):
                    data_files.append(match[0])
                else:
                    data_files.append(match)

        # 去重
        data_files = list(set(data_files))

        if not data_files:
            return {"status": "skipped", "reason": "未检测到常见数据文件格式"}

        log.info(f"🔍 [DataQCPlanner] 检测到 {len(data_files)} 个数据文件")

        # 预览每个文件（最多 5 个）
        for file_path in data_files[:5]:
            try:
                file_lower = file_path.lower()

                if file_lower.endswith(('.tsv', '.csv', '.txt', '.tab', '.mtx')):
                    # 表格文件
                    preview = await peek_tabular_data.ainvoke({
                        "file_path": file_path,
                        "n_rows": 5
                    })
                    previews[file_path] = {
                        "type": "tabular",
                        "preview": preview[:1000]  # 截断避免过长
                    }

                elif file_lower.endswith('.h5ad'):
                    # 单细胞 h5ad 文件
                    try:
                        from app.tools.probe_tools import inspect_h5ad
                        preview = await inspect_h5ad.ainvoke({"file_path": file_path})
                        previews[file_path] = {
                            "type": "h5ad",
                            "preview": preview[:1000]
                        }
                    except ImportError:
                        previews[file_path] = {
                            "type": "h5ad",
                            "preview": "h5ad 文件（预览工具不可用）"
                        }

                elif file_lower.endswith(('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
                    # FASTQ 文件（只记录存在）
                    previews[file_path] = {
                        "type": "fastq",
                        "preview": "FASTQ 测序数据文件"
                    }

                elif file_lower.endswith(('.bam', '.sam')):
                    # BAM/SAM 文件
                    previews[file_path] = {
                        "type": "bam",
                        "preview": "BAM 比对文件"
                    }

            except Exception as e:
                previews[file_path] = {
                    "type": "error",
                    "error": str(e)
                }
                log.warning(f"⚠️ [DataQCPlanner] 预览失败 {file_path}: {e}")

        return {
            "status": "success",
            "previews": previews,
            "total_files": len(data_files),
            "previewed_files": len(previews)
        }

    async def _generate_report(
        self,
        user_request: str,
        scan_result: Dict[str, Any],
        preview_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成质控规划报告"""

        system_prompt = f"""你是 Autonome 平台的数据与质控架构师（Agent A），专门负责上游数据处理的规划。

【你的职责】
1. 确认输入文件格式（10x, h5, exp, BD, fastq 等）
2. 规划预处理和质控策略
3. 规划批次效应消除策略
4. 输出数据格式转换方案

【当前项目上下文】
{self.project_context}

【数据探查结果】
- 目录扫描: {json.dumps(scan_result, ensure_ascii=False)[:500]}
- 数据预览: {json.dumps(preview_result, ensure_ascii=False)[:500]}

【质控参数知识库】
| 数据类型 | min_umi | min_genes | max_mt_percent |
|---------|---------|-----------|----------------|
| 10x 单细胞 | 1000 | 500 | 15% |
| BD Rhapsody | 500 | 300 | 20% |
| SMART-seq | 10000 | 2000 | 10% |

【批次整合方法选择】
| 方法 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| CCA | 一般批次效应 | 速度快 | 可能过度校正 |
| rPCA | 强批次效应 | 保留生物学变异 | 计算量大 |
| SCT+Harmony | 推荐 | 效果最好 | 需要更多内存 |

【输出格式】
请输出 JSON 格式的规划报告：
```json
{{
  "data_format": "数据格式",
  "sample_info": {{
    "sample_count": 2,
    "samples": ["Sample1", "Sample2"],
    "groups": ["Control", "Treat"]
  }},
  "qc_strategy": {{
    "min_umi": 1000,
    "min_genes": 500,
    "max_mt_percent": 15,
    "doublet_detection": true,
    "min_cells_in_gene": 5
  }},
  "integration_strategy": {{
    "method": "sct_harmony",
    "batch_variable": "sample",
    "reason": "解释选择原因"
  }},
  "upstream_steps": [
    {{
      "step_id": "qc_filtering",
      "name": "质控过滤",
      "description": "基于 UMI 和基因数过滤低质量细胞"
    }},
    {{
      "step_id": "batch_integration",
      "name": "批次整合",
      "description": "使用 SCT+Harmony 消除批次效应"
    }}
  ],
  "notes": "其他建议或注意事项"
}}
```
"""

        user_prompt = f"用户请求: {user_request}\n\n请分析并输出数据与质控规划报告。"

        response = await self._invoke_llm(system_prompt, user_prompt)
        report = self._parse_json_response(response)

        if not report:
            # 返回默认报告
            report = {
                "data_format": "unknown",
                "qc_strategy": {
                    "min_umi": 1000,
                    "min_genes": 500,
                    "max_mt_percent": 15,
                    "doublet_detection": True
                },
                "integration_strategy": {
                    "method": "sct_harmony",
                    "batch_variable": "sample"
                },
                "upstream_steps": [],
                "notes": "使用默认参数（LLM 解析失败）"
            }

        # 添加元数据
        report["_metadata"] = {
            "agent": "DataQCPlanner",
            "scan_status": scan_result.get("status"),
            "preview_status": preview_result.get("status")
        }

        return report


# ============================================================================
# 🧮 Agent B: 算法与统计学专家 (Algorithm & Statistician)
# ============================================================================

class AlgorithmStatistician(BasePlannerAgent):
    """
    🧮 Agent B: 算法与统计学专家

    专属视角: 深刻理解 Autonome 的 SKILL 兵器库

    核心职责:
    1. 决定核心算法（PCA 降维数、聚类 Resolution）
    2. 决定差异分析的统计算法（Wilcoxon/DESeq2/MAST）
    3. 多重检验校正策略（FDR/P-value 阈值）
    4. 填充 SKILL 参数 Schema
    """

    def __init__(
        self,
        llm_config: Dict[str, str],
        available_skills: str = ""
    ):
        """
        初始化算法与统计学专家

        Args:
            llm_config: LLM 配置
            available_skills: 可用 SKILL 列表
        """
        super().__init__(
            llm_config=llm_config,
            agent_name="AlgorithmStatistician",
            agent_role="算法与统计学专家",
            temperature=0.1
        )
        self.available_skills = available_skills

    async def plan(self, user_request: str) -> Optional[Dict[str, Any]]:
        """
        执行算法与统计学规划

        Args:
            user_request: 用户请求

        Returns:
            算法与统计学规划报告
        """
        log.info(f"🧮 [AlgorithmStatistician] 开始算法与统计学规划")

        system_prompt = f"""你是 Autonome 平台的算法与统计学专家（Agent B），专门负责中游核心算法的选择和参数设定。

【你的职责】
1. 决定核心算法（降维、聚类、差异分析）
2. 设定算法参数
3. 选择统计检验方法
4. 填充 SKILL 参数 Schema

【可用 SKILL 库】
{self.available_skills if self.available_skills else "暂无预置 SKILL，使用默认算法配置"}

【算法参数知识库】

### 降维算法
| 算法 | 推荐参数 | 说明 |
|------|----------|------|
| PCA | dims=50 | 主成分分析，保留主要变异 |
| UMAP | n_neighbors=30, min_dist=0.3 | 非线性降维可视化 |
| t-SNE | perplexity=30 | 高维数据可视化 |

### 聚类算法
| 算法 | 参数范围 | 说明 |
|------|----------|------|
| Louvain | resolution=0.4-1.2 | 快速聚类，resolution 越大聚类越多 |
| Leiden | resolution=0.5-1.0 | 改进版 Louvain，更稳定 |

### 差异分析
| 方法 | 适用场景 | 参数 |
|------|----------|------|
| Wilcoxon | 默认推荐 | logfc.threshold=0.25, min.pct=0.1 |
| DESeq2 | 大样本 | padj < 0.05, |log2FC| > 1 |
| MAST | 单细胞特异 | 校正细胞检测率 |

### 多重检验校正
| 方法 | 说明 |
|------|------|
| BH (Benjamini-Hochberg) | 默认推荐，控制 FDR |
| Bonferroni | 保守，控制 FWER |
| q-value | Storey 方法 |

【输出格式】
请输出 JSON 格式的规划报告：
```json
{{
  "core_algorithms": [
    {{
      "algorithm": "PCA",
      "purpose": "降维",
      "parameters": {{"dims": 50}}
    }},
    {{
      "algorithm": "UMAP",
      "purpose": "可视化",
      "parameters": {{"n_neighbors": 30, "min_dist": 0.3}}
    }},
    {{
      "algorithm": "Louvain",
      "purpose": "聚类",
      "parameters": {{"resolution": 0.8}}
    }}
  ],
  "statistical_methods": {{
    "deg_method": "Wilcoxon",
    "multiple_testing": "BH",
    "pvalue_threshold": 0.05,
    "logfc_threshold": 0.25,
    "min_pct": 0.1
  }},
  "skill_parameters": {{
    "dims": 50,
    "resolution": 0.8,
    "deg_test": "wilcox"
  }},
  "recommended_skills": [
    {{
      "skill_id": "singlecell_seurat_pipeline_01",
      "reason": "匹配用户需求"
    }}
  ],
  "notes": "算法选择建议"
}}
```
"""

        user_prompt = f"用户请求: {user_request}\n\n请分析并输出算法与统计学规划报告。"

        try:
            response = await self._invoke_llm(system_prompt, user_prompt)
            report = self._parse_json_response(response)

            if not report:
                # 返回默认报告
                report = {
                    "core_algorithms": [
                        {"algorithm": "PCA", "purpose": "降维", "parameters": {"dims": 50}},
                        {"algorithm": "UMAP", "purpose": "可视化", "parameters": {"n_neighbors": 30}},
                        {"algorithm": "Louvain", "purpose": "聚类", "parameters": {"resolution": 0.8}}
                    ],
                    "statistical_methods": {
                        "deg_method": "Wilcoxon",
                        "multiple_testing": "BH",
                        "pvalue_threshold": 0.05
                    },
                    "skill_parameters": {"dims": 50, "resolution": 0.8},
                    "notes": "使用默认参数（LLM 解析失败）"
                }

            report["_metadata"] = {"agent": "AlgorithmStatistician"}

            log.info(f"✅ [AlgorithmStatistician] 规划完成")
            return report

        except Exception as e:
            log.error(f"❌ [AlgorithmStatistician] 规划失败: {e}")
            return None


# ============================================================================
# 🧬 Agent C: 系统生物学与注释专家 (Systems Biologist)
# ============================================================================

class SystemsBiologist(BasePlannerAgent):
    """
    🧬 Agent C: 系统生物学与注释专家

    专属视角: 拥有各类公共数据库的先验知识

    核心职责:
    1. 规划细胞类型注释策略（ScType/SingleR/Marker 基因）
    2. 决定功能富集的数据库（GO, KEGG, Reactome）
    3. 物种选择和参考基因组路径
    4. Marker 基因提取策略
    """

    def __init__(self, llm_config: Dict[str, str]):
        """
        初始化系统生物学专家

        Args:
            llm_config: LLM 配置
        """
        super().__init__(
            llm_config=llm_config,
            agent_name="SystemsBiologist",
            agent_role="系统生物学与注释专家",
            temperature=0.1
        )

    async def plan(self, user_request: str) -> Optional[Dict[str, Any]]:
        """
        执行系统生物学规划

        Args:
            user_request: 用户请求

        Returns:
            系统生物学规划报告
        """
        log.info(f"🧬 [SystemsBiologist] 开始系统生物学规划")

        system_prompt = f"""你是 Autonome 平台的系统生物学与注释专家（Agent C），专门负责下游生物学意义解释的规划。

【你的职责】
1. 规划细胞类型注释策略
2. 决定功能富集的数据库和参数
3. 推荐物种和参考基因组
4. Marker 基因提取策略

【细胞注释方法知识库】
| 方法 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| ScType | 自动注释 | 快速，支持多种组织 | 依赖数据库完整性 |
| SingleR | 参考数据集注释 | 精确 | 需要高质量参考 |
| Marker 基因 | 手动注释 | 灵活 | 主观性强 |

【功能富集数据库】
| 数据库 | 物种覆盖 | 特点 |
|--------|----------|------|
| GO | 全面 | 基因本体，三层结构 |
| KEGG | 主流物种 | 通路富集 |
| Reactome | 人/小鼠 | 反应通路 |
| WikiPathways | 社区贡献 | 开放性强 |

【常见组织 Marker 基因】
| 组织/细胞类型 | Marker 基因 |
|---------------|-------------|
| T 细胞 | CD3D, CD3E, CD4, CD8A |
| B 细胞 | CD19, MS4A1, CD79A |
| 巨噬细胞 | CD14, CD68, FCGR3A |
| 上皮细胞 | EPCAM, KRT19 |
| 内皮细胞 | PECAM1, VWF |
| 成纤维细胞 | COL1A1, DCN |

【参考基因组路径】
| 物种 | 基因组 ID | 路径 |
|------|-----------|------|
| 人 | human_gencode_v38 | /app/biosource/genomes/human_gencode_v38 |
| 小鼠 | mouse_gencode_vM25 | /app/biosource/genomes/mouse_gencode_vM25 |

【输出格式】
请输出 JSON 格式的规划报告：
```json
{{
  "annotation_strategy": {{
    "method": "ScType",
    "tissue": "组织类型（如 Kidney, Liver 等）",
    "custom_markers": ["基因1", "基因2"],
    "confidence_threshold": 0.7
  }},
  "functional_analysis": {{
    "databases": ["GO", "KEGG"],
    "species": "hsa",
    "background_genes": "all_detected",
    "pvalue_cutoff": 0.05,
    "qvalue_cutoff": 0.2
  }},
  "reference_files": {{
    "sctype_db": "/app/biosource/ScTypeDB_full.xlsx",
    "genome": "human_gencode_v38"
  }},
  "marker_strategy": {{
    "method": "FindAllMarkers",
    "min_pct": 0.25,
    "logfc_threshold": 0.25
  }},
  "notes": "生物学注释建议"
}}
```
"""

        user_prompt = f"用户请求: {user_request}\n\n请分析并输出系统生物学规划报告。"

        try:
            response = await self._invoke_llm(system_prompt, user_prompt)
            report = self._parse_json_response(response)

            if not report:
                # 返回默认报告
                report = {
                    "annotation_strategy": {
                        "method": "ScType",
                        "tissue": "Unknown",
                        "confidence_threshold": 0.7
                    },
                    "functional_analysis": {
                        "databases": ["GO", "KEGG"],
                        "species": "hsa",
                        "pvalue_cutoff": 0.05
                    },
                    "reference_files": {
                        "sctype_db": "/app/biosource/ScTypeDB_full.xlsx"
                    },
                    "notes": "使用默认参数（LLM 解析失败）"
                }

            report["_metadata"] = {"agent": "SystemsBiologist"}

            log.info(f"✅ [SystemsBiologist] 规划完成")
            return report

        except Exception as e:
            log.error(f"❌ [SystemsBiologist] 规划失败: {e}")
            return None


# ============================================================================
# 🎨 Agent D: 出版级可视化设计师 (Visual Artist)
# ============================================================================

class VisualArtist(BasePlannerAgent):
    """
    🎨 Agent D: 出版级可视化设计师

    专属视角: 严格捍卫"发表级图形输出规范"

    核心职责:
    1. 梳理整个流程需要产出的图表
    2. 强制指定图表格式（PDF + PNG）、配色、DPI 和尺寸
    3. 确保图表可编辑性（矢量图优先）
    """

    def __init__(self, llm_config: Dict[str, str]):
        """
        初始化可视化设计师

        Args:
            llm_config: LLM 配置
        """
        super().__init__(
            llm_config=llm_config,
            agent_name="VisualArtist",
            agent_role="出版级可视化设计师",
            temperature=0.1
        )

    async def plan(self, user_request: str) -> Optional[Dict[str, Any]]:
        """
        执行可视化规划

        Args:
            user_request: 用户请求

        Returns:
            可视化规划报告
        """
        log.info(f"🎨 [VisualArtist] 开始可视化规划")

        system_prompt = f"""你是 Autonome 平台的出版级可视化设计师（Agent D），专门负责图表呈现规范的制定。

【你的职责】
1. 梳理整个流程需要产出的图表
2. 强制指定图表格式、配色、DPI 和尺寸
3. 确保图表符合发表级规范

【发表级图形输出规范（强制）】
1. **语言**: 纯英文标签、标题、图例（禁止中文！）
2. **分辨率**:
   - 热图/照片: 300 DPI
   - 线条图: 600 DPI
3. **字体**: Arial/Helvetica
   - 轴标签: 12-14pt
   - 刻度: 10-12pt
   - 图例: 10-12pt
4. **配色**: 色盲友好（viridis, Okabe-Ito, ColorBrewer）
   - 禁止红绿对比
   - 优先使用预设调色板
5. **尺寸**:
   - 单栏: 宽 3.5 英寸
   - 双栏: 宽 7 英寸
   - 高度: 4-6 英寸
6. **格式**: 必须同时输出 PDF（矢量）和 PNG（位图）

【常见图表类型规范】
| 图表类型 | 推荐尺寸 | 配色 |
|----------|----------|------|
| UMAP/t-SNE | 8×6 | 按分组着色 |
| 火山图 | 7×5 | 红-灰-蓝 |
| 热图 | 8×8 | viridis |
| 小提琴图 | 10×6 | 按分组 |
| 箱线图 | 8×5 | 按分组 |
| 条形图 | 7×5 | 配合分组 |

【单细胞分析常用图表】
1. QC 图（小提琴图：nFeature, nCount, percent.mt）
2. UMAP 降维图（按 cluster、sample、cell_type）
3. 火山图（差异基因）
4. 热图（Marker 基因表达）
5. 小提琴图（Marker 基因表达）
6. 点图（基因表达 dot plot）
7. 细胞比例图（堆叠条形图）

【输出格式】
请输出 JSON 格式的规划报告：
```json
{{
  "visualization_plan": [
    {{
      "figure_id": "fig_1",
      "type": "UMAP",
      "title": "UMAP Clustering",
      "group_by": ["cluster", "cell_type", "sample"],
      "format": ["PDF", "PNG"],
      "dpi": 300,
      "size": [8, 6],
      "color_palette": "viridis"
    }},
    {{
      "figure_id": "fig_2",
      "type": "volcano_plot",
      "title": "Differentially Expressed Genes",
      "format": ["PDF", "PNG"],
      "dpi": 300,
      "size": [7, 5],
      "color_palette": "red-gray-blue"
    }}
  ],
  "output_standards": {{
    "dpi": 300,
    "font_family": "Arial",
    "color_palette": "nature_style",
    "language": "English"
  }},
  "export_settings": {{
    "pdf_device": "cairo_pdf",
    "png_type": "cairo-png",
    "vector_friendly": true
  }},
  "notes": "可视化建议"
}}
```
"""

        user_prompt = f"用户请求: {user_request}\n\n请分析并输出可视化规划报告。"

        try:
            response = await self._invoke_llm(system_prompt, user_prompt)
            report = self._parse_json_response(response)

            if not report:
                # 返回默认报告
                report = {
                    "visualization_plan": [
                        {
                            "figure_id": "fig_1",
                            "type": "UMAP",
                            "title": "UMAP Visualization",
                            "format": ["PDF", "PNG"],
                            "dpi": 300,
                            "size": [8, 6]
                        }
                    ],
                    "output_standards": {
                        "dpi": 300,
                        "font_family": "Arial",
                        "language": "English"
                    },
                    "notes": "使用默认参数（LLM 解析失败）"
                }

            report["_metadata"] = {"agent": "VisualArtist"}

            log.info(f"✅ [VisualArtist] 规划完成")
            return report

        except Exception as e:
            log.error(f"❌ [VisualArtist] 规划失败: {e}")
            return None


log.info("🤖 专业规划 Agent 模块已加载（DataQCPlanner, AlgorithmStatistician, SystemsBiologist, VisualArtist）")