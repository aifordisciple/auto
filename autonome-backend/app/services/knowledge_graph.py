"""
知识图谱服务

构建和管理生信领域知识图谱：
1. 节点管理 - 概念、技能、错误、解决方案
2. 边管理 - 关系类型（is_a, part_of, precedes, solves 等）
3. 图遍历 - 查找相关概念、路径搜索
4. 推理能力 - 前置步骤推断、解决方案推荐

设计原则：
- 关系类型明确：8 种核心关系类型
- 权重动态计算：基于证据数量和置信度
- 推理支持：工作流推断、错误解决
- 高效查询：邻接表存储、索引优化
"""

import json
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timezone
from collections import defaultdict
from sqlmodel import Session, select

from app.core.logger import log
from app.models.domain_knowledge import (
    KnowledgeType,
    KnowledgeSource,
    DomainKnowledgeEntry,
    KnowledgeRelation,
    KnowledgeQueryResult,
    DomainKnowledgeRecord,
)


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ==========================================
# 关系类型枚举
# ==========================================

class RelationType:
    """
    知识关系类型

    定义知识节点之间的关系：
    - is_a: 分类关系（RNA-seq is_a 测序技术）
    - part_of: 组成关系（质控 part_of 分析流程）
    - related_to: 相似关系（DESeq2 related_to edgeR）
    - precedes: 顺序关系（质控 precedes 差异表达）
    - follows: 逆序关系
    - solves: 解决关系（检查数据 solves 负值错误）
    - requires: 依赖关系（差异表达 requires 计数矩阵）
    - produces: 产出关系（FastQC produces 质控报告）
    """
    IS_A = "is_a"
    PART_OF = "part_of"
    RELATED_TO = "related_to"
    PRECEDES = "precedes"
    FOLLOWS = "follows"
    SOLVES = "solves"
    REQUIRES = "requires"
    PRODUCES = "produces"

    @classmethod
    def all(cls) -> List[str]:
        """获取所有关系类型"""
        return [
            cls.IS_A,
            cls.PART_OF,
            cls.RELATED_TO,
            cls.PRECEDES,
            cls.FOLLOWS,
            cls.SOLVES,
            cls.REQUIRES,
            cls.PRODUCES,
        ]

    @classmethod
    def is_valid(cls, relation_type: str) -> bool:
        """检查关系类型是否有效"""
        return relation_type in cls.all()


# ==========================================
# 图谱节点和边模型
# ==========================================

class GraphNode:
    """
    图谱节点

    代表一个知识实体（概念、技能、错误等）
    """

    def __init__(
        self,
        knowledge_id: str,
        concept: str,
        knowledge_type: str,
        confidence: float = 1.0,
        synonyms: Optional[List[str]] = None,
        related_skills: Optional[List[str]] = None,
        description: Optional[str] = None,
    ):
        self.knowledge_id = knowledge_id
        self.concept = concept
        self.knowledge_type = knowledge_type
        self.confidence = confidence
        self.synonyms = synonyms or []
        self.related_skills = related_skills or []
        self.description = description

        # 邻接信息
        self.out_edges: List["GraphEdge"] = []  # 出边
        self.in_edges: List["GraphEdge"] = []   # 入边

    def add_out_edge(self, edge: "GraphEdge") -> None:
        """添加出边"""
        self.out_edges.append(edge)

    def add_in_edge(self, edge: "GraphEdge") -> None:
        """添加入边"""
        self.in_edges.append(edge)

    def get_neighbors(
        self,
        relation_type: Optional[str] = None,
        direction: str = "both",  # "in", "out", "both"
    ) -> List["GraphNode"]:
        """
        获取邻居节点

        Args:
            relation_type: 关系类型过滤（可选）
            direction: 方向过滤

        Returns:
            邻居节点列表
        """
        neighbors = []

        if direction in ["out", "both"]:
            for edge in self.out_edges:
                if relation_type is None or edge.relation_type == relation_type:
                    neighbors.append(edge.to_node)

        if direction in ["in", "both"]:
            for edge in self.in_edges:
                if relation_type is None or edge.relation_type == relation_type:
                    neighbors.append(edge.from_node)

        return neighbors

    def matches_query(self, query: str) -> bool:
        """检查是否匹配查询"""
        query_lower = query.lower()

        if self.concept.lower() in query_lower:
            return True

        for synonym in self.synonyms:
            if synonym.lower() in query_lower:
                return True

        return False

    @property
    def importance(self) -> float:
        """
        计算节点重要性

        重要性 = 入边数量 * 平均入边权重
        """
        if not self.in_edges:
            return 0.0

        avg_weight = sum(e.weight for e in self.in_edges) / len(self.in_edges)
        return len(self.in_edges) * avg_weight

    def __repr__(self) -> str:
        return f"GraphNode({self.knowledge_id}, {self.concept})"


class GraphEdge:
    """
    图谱边

    代表两个知识节点之间的关系
    """

    def __init__(
        self,
        from_node: GraphNode,
        to_node: GraphNode,
        relation_type: str,
        weight: float = 1.0,
        evidence: Optional[str] = None,
    ):
        self.from_node = from_node
        self.to_node = to_node
        self.relation_type = relation_type
        self.weight = weight
        self.evidence = evidence

    def __repr__(self) -> str:
        return f"GraphEdge({self.from_node.concept} --{self.relation_type}--> {self.to_node.concept})"


class GraphPath:
    """
    图谱路径

    代表从一个节点到另一个节点的路径
    """

    def __init__(
        self,
        nodes: List[GraphNode],
        edges: List[GraphEdge],
    ):
        self.nodes = nodes
        self.edges = edges
        self.length = len(edges)

    @property
    def confidence(self) -> float:
        """计算路径置信度（各边权重的乘积）"""
        if not self.edges:
            return 0.0

        conf = 1.0
        for edge in self.edges:
            conf *= edge.weight
        return conf

    def __repr__(self) -> str:
        path_str = " -> ".join(n.concept for n in self.nodes)
        return f"GraphPath({path_str}, confidence={self.confidence:.2f})"


# ==========================================
# 知识图谱服务
# ==========================================

class KnowledgeGraphService:
    """
    知识图谱服务

    提供知识图谱的构建、查询和推理功能：
    1. 构建图谱：从知识条目构建节点和边
    2. 查询图谱：按概念、关系类型查询
    3. 路径搜索：查找节点间路径
    4. 推理支持：推断前置步骤、解决方案

    使用方式：
    ```python
    graph = KnowledgeGraphService(session)

    # 构建图谱
    graph.build_from_knowledge_base()

    # 查询相关概念
    related = graph.find_related_concepts("RNA-seq")

    # 查找路径
    path = graph.find_path("FastQC", "差异表达")

    # 推断前置步骤
    prereqs = graph.infer_prerequisites("差异表达分析")
    ```
    """

    def __init__(self, session: Session):
        """
        初始化知识图谱服务

        Args:
            session: 数据库会话
        """
        self.session = session

        # 图谱存储
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []

        # 索引（加速查询）
        self._concept_index: Dict[str, Set[str]] = defaultdict(set)  # concept -> node_ids
        self._synonym_index: Dict[str, Set[str]] = defaultdict(set)  # synonym -> node_ids

        # 状态
        self._is_built = False

    # ==========================================
    # 图谱构建
    # ==========================================

    def build_from_knowledge_base(self) -> int:
        """
        从知识库构建图谱

        Returns:
            构建的节点数量
        """
        log.info("[KnowledgeGraph] 开始构建知识图谱")

        # 清空现有图谱
        self.nodes.clear()
        self.edges.clear()
        self._concept_index.clear()
        self._synonym_index.clear()

        # 加载所有知识条目
        records = self.session.exec(
            select(DomainKnowledgeRecord).order_by(
                DomainKnowledgeRecord.confidence.desc()
            )
        ).all()

        # 构建节点
        for record in records:
            entry = record.to_entry()
            self._add_node(entry)

        # 构建边
        self._build_edges(records)

        self._is_built = True
        log.info(f"[KnowledgeGraph] 图谱构建完成: {len(self.nodes)} 节点, {len(self.edges)} 边")

        return len(self.nodes)

    def _add_node(self, entry: DomainKnowledgeEntry) -> GraphNode:
        """
        添加节点

        Args:
            entry: 知识条目

        Returns:
            创建的节点
        """
        node = GraphNode(
            knowledge_id=entry.knowledge_id,
            concept=entry.concept,
            knowledge_type=entry.knowledge_type.value,
            confidence=entry.effective_confidence,
            synonyms=entry.synonyms,
            related_skills=entry.related_skills,
            description=entry.description,
        )

        self.nodes[entry.knowledge_id] = node

        # 更新索引
        self._concept_index[entry.concept.lower()].add(entry.knowledge_id)
        for synonym in entry.synonyms:
            self._synonym_index[synonym.lower()].add(entry.knowledge_id)

        return node

    def _build_edges(self, records: List[DomainKnowledgeRecord]) -> None:
        """
        构建边（关系）

        关系来源：
        1. 共享技能：两个概念关联同一技能 → related_to
        2. 工作流顺序：基于 category 推断 → precedes
        3. 分类关系：category hierarchy → is_a
        4. 错误解决：error_pattern 与 solution → solves

        Args:
            records: 知识记录列表
        """
        # 按技能分组
        skill_to_knowledge: Dict[str, List[DomainKnowledgeRecord]] = defaultdict(list)
        for record in records:
            entry = record.to_entry()
            for skill_id in entry.related_skills:
                skill_to_knowledge[skill_id].append(record)

        # 共享技能 → related_to 关系
        for skill_id, related_records in skill_to_knowledge.items():
            if len(related_records) >= 2:
                for i, r1 in enumerate(related_records):
                    for r2 in related_records[i+1:]:
                        self._create_related_edge(r1, r2)

        # 按类型分组
        type_to_knowledge: Dict[KnowledgeType, List[DomainKnowledgeRecord]] = defaultdict(list)
        for record in records:
            try:
                kt = KnowledgeType(record.knowledge_type)
                type_to_knowledge[kt].append(record)
            except ValueError:
                continue

        # 错误模式与解决方案 → solves 关系
        error_patterns = type_to_knowledge.get(KnowledgeType.ERROR_PATTERN, [])
        solutions = [r for r in records if r.solution]

        for error in error_patterns:
            for solution_record in solutions:
                if solution_record.knowledge_id != error.knowledge_id:
                    # 检查是否相关（简单匹配）
                    error_entry = error.to_entry()
                    solution_entry = solution_record.to_entry()

                    if self._is_solution_for_error(solution_entry, error_entry):
                        self._create_solves_edge(solution_entry, error_entry)

        # 工作流顺序关系（基于 category）
        self._build_workflow_edges(records)

    def _create_related_edge(
        self,
        record1: DomainKnowledgeRecord,
        record2: DomainKnowledgeRecord,
    ) -> None:
        """创建 related_to 关系边"""
        node1 = self.nodes.get(record1.knowledge_id)
        node2 = self.nodes.get(record2.knowledge_id)

        if not node1 or not node2:
            return

        # 检查是否已存在边
        for edge in node1.out_edges:
            if edge.to_node == node2 and edge.relation_type == RelationType.RELATED_TO:
                return

        # 计算权重（基于共享技能数量）
        entry1 = record1.to_entry()
        entry2 = record2.to_entry()
        shared_skills = set(entry1.related_skills) & set(entry2.related_skills)
        weight = min(1.0, len(shared_skills) / 3.0)

        edge = GraphEdge(
            from_node=node1,
            to_node=node2,
            relation_type=RelationType.RELATED_TO,
            weight=weight,
            evidence=f"共享技能: {', '.join(shared_skills)}",
        )

        self.edges.append(edge)
        node1.add_out_edge(edge)
        node2.add_in_edge(edge)

    def _create_solves_edge(
        self,
        solution_entry: DomainKnowledgeEntry,
        error_entry: DomainKnowledgeEntry,
    ) -> None:
        """创建 solves 关系边"""
        node1 = self.nodes.get(solution_entry.knowledge_id)
        node2 = self.nodes.get(error_entry.knowledge_id)

        if not node1 or not node2:
            return

        edge = GraphEdge(
            from_node=node1,
            to_node=node2,
            relation_type=RelationType.SOLVES,
            weight=0.8,
            evidence="解决方案对应错误模式",
        )

        self.edges.append(edge)
        node1.add_out_edge(edge)
        node2.add_in_edge(edge)

    def _is_solution_for_error(
        self,
        solution: DomainKnowledgeEntry,
        error: DomainKnowledgeEntry,
    ) -> bool:
        """检查解决方案是否对应错误"""
        # 简单匹配：检查概念关键词
        solution_keywords = set(solution.concept.lower().split())
        error_keywords = set(error.concept.lower().split())

        # 有重叠关键词
        overlap = solution_keywords & error_keywords
        return len(overlap) >= 1

    def _build_workflow_edges(self, records: List[DomainKnowledgeRecord]) -> None:
        """
        构建工作流顺序关系

        基于生信分析常见流程建立 precedes 关系
        """
        # 定义常见工作流顺序
        workflow_sequences = [
            # 质量控制 -> 比对 -> 定量 -> 差异表达
            (["quality_control", "qc", "质控"], ["alignment", "比对"]),
            (["alignment", "比对"], ["quantification", "定量"]),
            (["quantification", "定量"], ["differential_expression", "差异表达", "deg"]),

            # 差异表达 -> 功能富集
            (["differential_expression", "差异表达", "deg"], ["enrichment", "富集", "go", "kegg"]),
        ]

        # 查找对应节点
        for prereq_keywords, next_keywords in workflow_sequences:
            prereq_nodes = self._find_nodes_by_keywords(prereq_keywords)
            next_nodes = self._find_nodes_by_keywords(next_keywords)

            for pn in prereq_nodes:
                for nn in next_nodes:
                    self._create_precedes_edge(pn, nn)

    def _find_nodes_by_keywords(self, keywords: List[str]) -> List[GraphNode]:
        """通过关键词查找节点"""
        found = []
        for node in self.nodes.values():
            concept_lower = node.concept.lower()
            if any(kw.lower() in concept_lower for kw in keywords):
                found.append(node)
            else:
                for syn in node.synonyms:
                    if any(kw.lower() in syn.lower() for kw in keywords):
                        found.append(node)
                        break
        return found

    def _create_precedes_edge(self, from_node: GraphNode, to_node: GraphNode) -> None:
        """创建 precedes 关系边"""
        # 检查是否已存在
        for edge in from_node.out_edges:
            if edge.to_node == to_node and edge.relation_type == RelationType.PRECEDES:
                return

        edge = GraphEdge(
            from_node=from_node,
            to_node=to_node,
            relation_type=RelationType.PRECEDES,
            weight=0.7,
            evidence="工作流顺序关系",
        )

        self.edges.append(edge)
        from_node.add_out_edge(edge)
        to_node.add_in_edge(edge)

    # ==========================================
    # 图谱查询
    # ==========================================

    def find_node_by_id(self, knowledge_id: str) -> Optional[GraphNode]:
        """通过 ID 查找节点"""
        return self.nodes.get(knowledge_id)

    def find_nodes_by_concept(self, concept: str) -> List[GraphNode]:
        """通过概念查找节点"""
        concept_lower = concept.lower()
        node_ids = self._concept_index.get(concept_lower, set())

        nodes = [self.nodes[nid] for nid in node_ids if nid in self.nodes]

        # 也搜索同义词
        synonym_ids = self._synonym_index.get(concept_lower, set())
        for nid in synonym_ids:
            if nid in self.nodes and self.nodes[nid] not in nodes:
                nodes.append(self.nodes[nid])

        return nodes

    def find_related_concepts(
        self,
        concept: str,
        max_depth: int = 2,
        relation_types: Optional[List[str]] = None,
    ) -> List[Tuple[GraphNode, float]]:
        """
        查找相关概念

        Args:
            concept: 概念关键词
            max_depth: 最大搜索深度
            relation_types: 关系类型过滤

        Returns:
            (节点, 相关性得分) 列表
        """
        # 找到起始节点
        start_nodes = self.find_nodes_by_concept(concept)
        if not start_nodes:
            return []

        # BFS 遍历
        visited: Set[str] = set()
        results: List[Tuple[GraphNode, float]] = []

        for start_node in start_nodes:
            queue = [(start_node, 0, 1.0)]  # (node, depth, score)

            while queue:
                node, depth, score = queue.pop(0)

                if node.knowledge_id in visited:
                    continue
                visited.add(node.knowledge_id)

                if depth > 0:  # 排除起始节点
                    results.append((node, score))

                if depth < max_depth:
                    for edge in node.out_edges:
                        if relation_types and edge.relation_type not in relation_types:
                            continue
                        new_score = score * edge.weight * 0.8
                        if edge.to_node.knowledge_id not in visited:
                            queue.append((edge.to_node, depth + 1, new_score))

                    for edge in node.in_edges:
                        if relation_types and edge.relation_type not in relation_types:
                            continue
                        new_score = score * edge.weight * 0.8
                        if edge.from_node.knowledge_id not in visited:
                            queue.append((edge.from_node, depth + 1, new_score))

        # 按得分排序
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def find_path(
        self,
        from_concept: str,
        to_concept: str,
        max_length: int = 5,
    ) -> Optional[GraphPath]:
        """
        查找两个概念间的路径

        Args:
            from_concept: 起始概念
            to_concept: 目标概念
            max_length: 最大路径长度

        Returns:
            路径对象（如果找到）
        """
        # 找到起始和目标节点
        start_nodes = self.find_nodes_by_concept(from_concept)
        end_nodes = self.find_nodes_by_concept(to_concept)

        if not start_nodes or not end_nodes:
            return None

        end_ids = {n.knowledge_id for n in end_nodes}

        # BFS 搜索路径
        for start_node in start_nodes:
            visited: Set[str] = set()
            queue: List[Tuple[GraphNode, List[GraphNode], List[GraphEdge]]] = [
                (start_node, [start_node], [])
            ]

            while queue:
                current, path_nodes, path_edges = queue.pop(0)

                if current.knowledge_id in visited:
                    continue
                visited.add(current.knowledge_id)

                if current.knowledge_id in end_ids and len(path_nodes) > 1:
                    return GraphPath(path_nodes, path_edges)

                if len(path_edges) >= max_length:
                    continue

                for edge in current.out_edges:
                    next_node = edge.to_node
                    if next_node.knowledge_id not in visited:
                        queue.append((
                            next_node,
                            path_nodes + [next_node],
                            path_edges + [edge],
                        ))

        return None

    # ==========================================
    # 推理功能
    # ==========================================

    def infer_prerequisites(self, concept: str) -> List[GraphNode]:
        """
        推断前置步骤

        基于 precedes 关系推断执行某分析前需要的步骤

        Args:
            concept: 目标概念

        Returns:
            前置步骤节点列表（按执行顺序）
        """
        nodes = self.find_nodes_by_concept(concept)
        if not nodes:
            return []

        prerequisites: List[GraphNode] = []

        for node in nodes:
            # 查找 precedes 指向该节点的边
            for edge in node.in_edges:
                if edge.relation_type == RelationType.PRECEDES:
                    prereq_node = edge.from_node
                    if prereq_node not in prerequisites:
                        # 递归查找前置的前置
                        earlier_prereqs = self.infer_prerequisites(prereq_node.concept)
                        for ep in earlier_prereqs:
                            if ep not in prerequisites:
                                prerequisites.append(ep)
                        prerequisites.append(prereq_node)

        return prerequisites

    def infer_solutions(self, error_keyword: str) -> List[GraphNode]:
        """
        推断错误解决方案

        基于 solves 关系推荐可能的解决方案

        Args:
            error_keyword: 错误关键词

        Returns:
            解决方案节点列表
        """
        # 查找匹配的错误节点
        error_nodes = []
        for node in self.nodes.values():
            if node.knowledge_type == KnowledgeType.ERROR_PATTERN.value:
                if error_keyword.lower() in node.concept.lower():
                    error_nodes.append(node)

        if not error_nodes:
            return []

        solutions = []
        for error_node in error_nodes:
            for edge in error_node.in_edges:
                if edge.relation_type == RelationType.SOLVES:
                    solution_node = edge.from_node
                    if solution_node not in solutions:
                        solutions.append(solution_node)

        return solutions

    def recommend_related_skills(self, concept: str) -> List[str]:
        """
        推荐相关技能

        Args:
            concept: 概念关键词

        Returns:
            技能 ID 列表
        """
        related = self.find_related_concepts(concept, max_depth=2)

        skill_set: Set[str] = set()
        for node, _ in related:
            skill_set.update(node.related_skills)

        return list(skill_set)

    # ==========================================
    # 统计信息
    # ==========================================

    def get_stats(self) -> Dict[str, Any]:
        """获取图谱统计信息"""
        # 统计各类型节点数量
        type_counts: Dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            type_counts[node.knowledge_type] += 1

        # 统计各类型边数量
        edge_counts: Dict[str, int] = defaultdict(int)
        for edge in self.edges:
            edge_counts[edge.relation_type] += 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": dict(type_counts),
            "edge_types": dict(edge_counts),
            "avg_node_importance": sum(n.importance for n in self.nodes.values()) / len(self.nodes) if self.nodes else 0,
        }

    def is_built(self) -> bool:
        """检查图谱是否已构建"""
        return self._is_built


# ==========================================
# 导出
# ==========================================

__all__ = [
    "RelationType",
    "GraphNode",
    "GraphEdge",
    "GraphPath",
    "KnowledgeGraphService",
]