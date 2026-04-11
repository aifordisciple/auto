"""
参考基因组资产模型

包含参考基因组模型及其创建/更新/公开模型
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB


def get_utc_now() -> datetime:
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    from datetime import timezone
    return datetime.now(timezone.utc)


# ==========================================
# 参考基因组资产模型 (GenomeAsset)
# ==========================================
# 设计理念：
# - 与 besaltpipe genome_db.xls 格式完全兼容
# - 支持多种比对工具索引路径管理
# - 支持自定义字段扩展（custom_fields）
# - 权限控制：公开/团队/私有
# - 共享机制：支持共享给特定用户
# ==========================================

class GenomeAsset(SQLModel, table=True):
    """
    参考基因组资产表 - 与 besaltpipe genome_db.xls 格式兼容

    核心设计理念：
    - 统一管理生信分析所需的参考基因组及其索引文件
    - 字段与 besaltpipe Genome 类完全对应，实现无缝集成
    - 支持自定义字段扩展，适应未来需求
    - 多租户权限控制，支持公开/团队/私有级别

    数据流：
    1. 管理员创建公开基因组（所有用户可见）
    2. 普通用户创建私有基因组（仅自己可见）
    3. 用户可将私有基因组共享给特定用户
    4. SKILL 执行时通过 genomeid 获取基因组配置
    """
    __tablename__ = "genomeasset"

    # ==========================================
    # 基础标识
    # ==========================================
    id: Optional[int] = Field(default=None, primary_key=True)
    genomeid: str = Field(unique=True, index=True, max_length=100, description="基因组唯一标识，如 human_gencode_v38")

    # ==========================================
    # 基本信息
    # ==========================================
    species: str = Field(max_length=100, index=True, description="物种名称，如 human, mouse")
    version: str = Field(max_length=50, description="基因组版本，如 GRCh38, GRCm39")
    species_code: Optional[str] = Field(default=None, max_length=20, description="物种缩写，如 hg38, mm10")
    url: Optional[str] = Field(default=None, max_length=500, description="基因组下载来源 URL")
    date: Optional[str] = Field(default=None, max_length=20, description="创建/更新日期")

    # ==========================================
    # 核心文件路径
    # ==========================================
    genome: str = Field(max_length=500, description="参考基因组 FASTA 文件路径")
    chrlen: Optional[str] = Field(default=None, max_length=500, description="染色体长度文件路径")
    gff: Optional[str] = Field(default=None, max_length=500, description="GFF 注释文件路径")
    gffdb: Optional[str] = Field(default=None, max_length=500, description="GFF 数据库文件路径")
    gtf: Optional[str] = Field(default=None, max_length=500, description="GTF 注释文件路径")
    geneanno: Optional[str] = Field(default=None, max_length=500, description="基因注释文件路径")
    genelen: Optional[str] = Field(default=None, max_length=500, description="基因长度文件路径")
    genome_info: Optional[str] = Field(default=None, max_length=500, description="基因组信息文件路径")

    # ==========================================
    # 比对工具索引
    # ==========================================
    bowtie2_index: Optional[str] = Field(default=None, max_length=500, description="Bowtie2 索引目录路径")
    bowtie1_index: Optional[str] = Field(default=None, max_length=500, description="Bowtie1 索引目录路径")
    bwa_index: Optional[str] = Field(default=None, max_length=500, description="BWA 索引目录路径")
    star_index: Optional[str] = Field(default=None, max_length=500, description="STAR 索引目录路径")
    hisat2_index: Optional[str] = Field(default=None, max_length=500, description="HISAT2 索引目录路径")
    novoalign_index: Optional[str] = Field(default=None, max_length=500, description="Novoalign 索引目录路径")
    minimap2_index: Optional[str] = Field(default=None, max_length=500, description="Minimap2 索引目录路径")
    minimap2_juncbed: Optional[str] = Field(default=None, max_length=500, description="Minimap2 剪接位点 BED 文件路径")
    rsem_index: Optional[str] = Field(default=None, max_length=500, description="RSEM 索引目录路径")
    noncode_index: Optional[str] = Field(default=None, max_length=500, description="非编码 RNA 索引路径")

    # ==========================================
    # 单细胞相关
    # ==========================================
    ref10x: Optional[str] = Field(default=None, max_length=500, description="10x Genomics 参考基因组目录路径")
    sc_star: Optional[str] = Field(default=None, max_length=500, description="单细胞 STAR 索引路径")
    sc_gtf: Optional[str] = Field(default=None, max_length=500, description="单细胞专用 GTF 文件路径")

    # ==========================================
    # 注释相关
    # ==========================================
    godes: Optional[str] = Field(default=None, max_length=500, description="GO 注释文件路径")
    kg: Optional[str] = Field(default=None, max_length=50, description="KEGG 物种代码，如 hsa, mmu")
    known_lncRNA: Optional[str] = Field(default=None, max_length=500, description="已知 lncRNA 注释文件路径")
    bsgenome: Optional[str] = Field(default=None, max_length=100, description="BSgenome R 包名称")
    geneid_or_symbol: str = Field(default="symbol", max_length=20, description="基因 ID 类型: symbol/ensg")

    # ==========================================
    # 元数据与状态
    # ==========================================
    is_active: bool = Field(default=True, description="是否启用")
    description: Optional[str] = Field(default=None, description="基因组描述信息")

    # ==========================================
    # 自定义字段支持
    # ==========================================
    custom_fields: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
        description="自定义扩展字段，存储额外配置"
    )

    # ==========================================
    # 权限与共享
    # ==========================================
    owner_id: int = Field(foreign_key="user.id", index=True, description="所有者用户 ID")
    visibility: str = Field(default="public", max_length=20, description="可见性: public/team/private")
    shared_with: List[int] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="共享给的用户 ID 列表"
    )

    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    def to_besaltpipe_dict(self) -> Dict[str, Any]:
        """
        转换为 besaltpipe Genome.allgenome[genomeid] 兼容格式

        用途：SKILL 执行时获取基因组配置，与 besaltpipe 无缝集成
        返回：与 Genome 类 allgenome 字典格式一致的字典
        """
        return {
            'genomeid': self.genomeid,
            'species': self.species,
            'version': self.version,
            'species_code': self.species_code,
            'url': self.url,
            'date': self.date,
            'genome': self.genome,
            'chrlen': self.chrlen,
            'gff': self.gff,
            'gffdb': self.gffdb,
            'gtf': self.gtf,
            'geneanno': self.geneanno,
            'genelen': self.genelen,
            'genome_info': self.genome_info,
            'bowtie2_index': self.bowtie2_index,
            'bowtie1_index': self.bowtie1_index,
            'bwa_index': self.bwa_index,
            'star_index': self.star_index,
            'hisat2_index': self.hisat2_index,
            'novoalign_index': self.novoalign_index,
            'minimap2_index': self.minimap2_index,
            'minimap2_juncbed': self.minimap2_juncbed,
            'rsem_index': self.rsem_index,
            'noncode_index': self.noncode_index,
            'ref10x': self.ref10x,
            'sc_star': self.sc_star,
            'sc_gtf': self.sc_gtf,
            'godes': self.godes,
            'kg': self.kg,
            'known_lncRNA': self.known_lncRNA,
            'bsgenome': self.bsgenome,
            'geneid_or_symbol': self.geneid_or_symbol,
            **self.custom_fields  # 合并自定义字段
        }


class GenomeAssetCreate(SQLModel):
    """创建基因组资产的请求体"""
    genomeid: str = Field(max_length=100, description="基因组唯一标识")
    species: str = Field(max_length=100, description="物种名称")
    version: str = Field(max_length=50, description="基因组版本")
    species_code: Optional[str] = None
    url: Optional[str] = None
    date: Optional[str] = None
    genome: str = Field(max_length=500, description="参考基因组 FASTA 文件路径")
    chrlen: Optional[str] = None
    gff: Optional[str] = None
    gffdb: Optional[str] = None
    gtf: Optional[str] = None
    geneanno: Optional[str] = None
    genelen: Optional[str] = None
    genome_info: Optional[str] = None
    bowtie2_index: Optional[str] = None
    bowtie1_index: Optional[str] = None
    bwa_index: Optional[str] = None
    star_index: Optional[str] = None
    hisat2_index: Optional[str] = None
    novoalign_index: Optional[str] = None
    minimap2_index: Optional[str] = None
    minimap2_juncbed: Optional[str] = None
    rsem_index: Optional[str] = None
    noncode_index: Optional[str] = None
    ref10x: Optional[str] = None
    sc_star: Optional[str] = None
    sc_gtf: Optional[str] = None
    godes: Optional[str] = None
    kg: Optional[str] = None
    known_lncRNA: Optional[str] = None
    bsgenome: Optional[str] = None
    geneid_or_symbol: str = "symbol"
    is_active: bool = True
    description: Optional[str] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    visibility: str = "private"


class GenomeAssetUpdate(SQLModel):
    """更新基因组资产的请求体"""
    species: Optional[str] = None
    version: Optional[str] = None
    species_code: Optional[str] = None
    url: Optional[str] = None
    date: Optional[str] = None
    genome: Optional[str] = None
    chrlen: Optional[str] = None
    gff: Optional[str] = None
    gffdb: Optional[str] = None
    gtf: Optional[str] = None
    geneanno: Optional[str] = None
    genelen: Optional[str] = None
    genome_info: Optional[str] = None
    bowtie2_index: Optional[str] = None
    bowtie1_index: Optional[str] = None
    bwa_index: Optional[str] = None
    star_index: Optional[str] = None
    hisat2_index: Optional[str] = None
    novoalign_index: Optional[str] = None
    minimap2_index: Optional[str] = None
    minimap2_juncbed: Optional[str] = None
    rsem_index: Optional[str] = None
    noncode_index: Optional[str] = None
    ref10x: Optional[str] = None
    sc_star: Optional[str] = None
    sc_gtf: Optional[str] = None
    godes: Optional[str] = None
    kg: Optional[str] = None
    known_lncRNA: Optional[str] = None
    bsgenome: Optional[str] = None
    geneid_or_symbol: Optional[str] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    visibility: Optional[str] = None
    shared_with: Optional[List[int]] = None


class GenomeAssetPublic(SQLModel):
    """返回给前端的基因组资产公共信息"""
    id: int
    genomeid: str
    species: str
    version: str
    species_code: Optional[str]
    url: Optional[str]
    date: Optional[str]
    genome: str
    chrlen: Optional[str]
    gff: Optional[str]
    gffdb: Optional[str]
    gtf: Optional[str]
    geneanno: Optional[str]
    genelen: Optional[str]
    genome_info: Optional[str]
    bowtie2_index: Optional[str]
    bowtie1_index: Optional[str]
    bwa_index: Optional[str]
    star_index: Optional[str]
    hisat2_index: Optional[str]
    novoalign_index: Optional[str]
    minimap2_index: Optional[str]
    minimap2_juncbed: Optional[str]
    rsem_index: Optional[str]
    noncode_index: Optional[str]
    ref10x: Optional[str]
    sc_star: Optional[str]
    sc_gtf: Optional[str]
    godes: Optional[str]
    kg: Optional[str]
    known_lncRNA: Optional[str]
    bsgenome: Optional[str]
    geneid_or_symbol: str
    is_active: bool
    description: Optional[str]
    custom_fields: Dict[str, Any]
    owner_id: int
    visibility: str
    shared_with: List[int]
    created_at: datetime
    updated_at: datetime