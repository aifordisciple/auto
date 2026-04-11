"""
工业级算力计费系统数据模型

设计日期: 2026-03-23

核心模型：
- Wallet: 双层钱包（个人/团队）
- ComputeRecord: 计算账单流水
- TransactionLedger: 资金变动明细
- ResourceFlavor: 实例规格定义

设计理念：
1. 预授权冻结机制：任务提交前冻结预估费用
2. 双层钱包架构：支持个人账户和团队账户
3. 三段式余额：可用余额 + 冻结余额 + 透支额度
4. 完整审计日志：每笔交易都有流水记录
"""

from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
import uuid


# ==========================================
# 辅助函数
# ==========================================

def get_utc_now():
    """获取带时区的当前 UTC 时间，兼容 Python 3.12+"""
    return datetime.now(timezone.utc)


# ==========================================
# UUID 生成函数
# ==========================================

def generate_wallet_id():
    """生成钱包唯一 ID"""
    return f"wallet_{uuid.uuid4().hex[:12]}"

def generate_record_id():
    """生成计算记录唯一 ID"""
    return f"rec_{uuid.uuid4().hex[:16]}"

def generate_transaction_id():
    """生成交易流水唯一 ID"""
    return f"tx_{uuid.uuid4().hex[:16]}"

def generate_flavor_id():
    """生成规格唯一 ID"""
    return f"flavor_{uuid.uuid4().hex[:8]}"


# ==========================================
# 枚举定义
# ==========================================

class WalletType(str, Enum):
    """钱包类型"""
    PERSONAL = "personal"    # 个人钱包
    TEAM = "team"           # 团队钱包


class WalletStatus(str, Enum):
    """钱包状态"""
    ACTIVE = "active"        # 正常
    SUSPENDED = "suspended"  # 欠费挂起
    FROZEN = "frozen"       # 管理员冻结


class TaskType(str, Enum):
    """任务类型"""
    CHAT = "chat"                     # 普通对话
    SANDBOX_PYTHON = "sandbox_python" # Python 沙箱执行
    SANDBOX_R = "sandbox_r"           # R 沙箱执行
    BLUEPRINT = "blueprint"           # 蓝图 DAG 执行
    SUPER_EXECUTOR = "super_executor" # 超级执行者
    SKILL_PYTHON = "skill_python"     # 技能执行 Python
    SKILL_R = "skill_r"               # 技能执行 R
    SKILL_NEXTFLOW = "skill_nextflow" # Nextflow 流程
    TERMINAL = "terminal"             # Web Terminal


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "PENDING"         # 等待执行
    RUNNING = "RUNNING"         # 执行中
    FROZEN = "FROZEN"          # 预授权冻结
    COMPLETED = "COMPLETED"     # 执行成功
    FAILED = "FAILED"          # 执行失败
    CANCELLED = "CANCELLED"     # 用户取消
    TIMEOUT = "TIMEOUT"        # 执行超时


class TransactionType(str, Enum):
    """交易类型"""
    # 充值相关
    RECHARGE_STRIPE = "recharge_stripe"     # Stripe 充值
    RECHARGE_ADMIN = "recharge_admin"       # 管理员充值
    RECHARGE_PROMO = "recharge_promo"       # 促销赠送

    # 消费相关
    CONSUME_CHAT = "consume_chat"           # 对话消费
    CONSUME_SANDBOX = "consume_sandbox"     # 沙箱消费
    CONSUME_SKILL = "consume_skill"         # 技能消费
    CONSUME_BLUEPRINT = "consume_blueprint" # 蓝图消费
    CONSUME_TERMINAL = "consume_terminal"   # 终端消费

    # 冻结相关
    FREEZE = "freeze"                       # 预授权冻结
    UNFREEZE = "unfreeze"                   # 解冻退款
    SETTLE = "settle"                       # 冻结结算

    # 调整相关
    ADMIN_ADJUST = "admin_adjust"           # 管理员调整
    REFUND = "refund"                       # 退款
    OVERDRAFT = "overdraft"                 # 透支


# ==========================================
# 异常定义
# ==========================================

class BillingError(Exception):
    """计费系统基础异常"""
    pass


class InsufficientBalanceError(BillingError):
    """余额不足异常"""
    def __init__(self, message: str, available: float, required: float):
        self.available = available
        self.required = required
        super().__init__(message)


class WalletSuspendedError(BillingError):
    """钱包已挂起异常"""
    pass


# ==========================================
# 1. 钱包表 (Wallet)
# ==========================================

class Wallet(SQLModel, table=True):
    """
    钱包表 - 支持个人/团队双层钱包架构

    设计理念：
    1. 个人钱包：每个用户一个，注册时自动创建
    2. 团队钱包：团队共享，由团队管理员管理
    3. 预授权机制：任务提交前冻结预估费用
    4. 风控熔断：余额不足时挂起而非直接拒绝

    三段式余额：
    - credits_balance: 可用余额
    - credits_frozen: 冻结余额（预授权）
    - credits_overdraft: 透支额度
    """
    __tablename__ = "wallet"

    # 基础标识
    id: Optional[int] = Field(default=None, primary_key=True)
    wallet_id: str = Field(default_factory=generate_wallet_id, unique=True, index=True, max_length=50)

    # 钱包类型与归属
    wallet_type: WalletType = Field(default=WalletType.PERSONAL, description="钱包类型: personal/team")
    owner_id: int = Field(foreign_key="user.id", index=True, description="所有者 User ID")

    # 三段式余额
    credits_balance: float = Field(default=100.0, ge=0.0, description="可用余额 (CU)")
    credits_frozen: float = Field(default=0.0, ge=0.0, description="冻结余额 (预授权)")
    credits_overdraft: float = Field(default=0.0, ge=0.0, description="透支额度")

    # 消费统计
    total_consumed: float = Field(default=0.0, ge=0.0, description="累计消费")
    total_frozen_count: int = Field(default=0, ge=0, description="累计冻结次数")

    # 风控状态
    status: WalletStatus = Field(default=WalletStatus.ACTIVE, description="钱包状态")
    suspended_at: Optional[datetime] = Field(default=None, description="挂起时间")
    suspended_reason: Optional[str] = Field(default=None, max_length=500, description="挂起原因")

    # 告警阈值
    low_balance_threshold: float = Field(default=10.0, ge=0.0, description="低余额告警阈值")
    auto_suspend_threshold: float = Field(default=0.0, ge=0.0, description="自动挂起阈值")

    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    # 关系
    compute_records: List["ComputeRecord"] = Relationship(
        back_populates="wallet",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    transactions: List["TransactionLedger"] = Relationship(
        back_populates="wallet",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


# ==========================================
# 2. 计算账单流水表 (ComputeRecord)
# ==========================================

class ComputeRecord(SQLModel, table=True):
    """
    计算账单流水表 - 记录每次计算任务的消费详情

    设计理念：
    1. 任务生命周期追踪：从提交到完成/取消
    2. 预授权机制：记录冻结金额和实际消费
    3. 资源计量：CPU/GPU/内存/存储用量
    4. 成本归因：项目、会话、技能多维度
    """
    __tablename__ = "computerecord"

    # 基础标识
    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: str = Field(default_factory=generate_record_id, unique=True, index=True, max_length=50)

    # 关联实体
    wallet_id: str = Field(foreign_key="wallet.wallet_id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    project_id: Optional[str] = Field(default=None, foreign_key="project.id", index=True)

    # 任务信息
    task_type: TaskType = Field(description="任务类型")
    task_name: str = Field(max_length=200, description="任务名称")
    task_status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")

    # 资源规格
    flavor_id: Optional[str] = Field(default=None, foreign_key="resourceflavor.flavor_id", description="实例规格 ID")
    cpu_cores: float = Field(default=1.0, ge=0.0, description="CPU 核数")
    memory_gb: float = Field(default=4.0, ge=0.0, description="内存 GB")
    gpu_count: int = Field(default=0, ge=0, description="GPU 数量")

    # 计费信息
    estimated_cost: float = Field(default=0.0, ge=0.0, description="预估费用")
    frozen_amount: float = Field(default=0.0, ge=0.0, description="冻结金额")
    actual_cost: float = Field(default=0.0, ge=0.0, description="实际消费")
    refund_amount: float = Field(default=0.0, ge=0.0, description="退款金额")

    # 资源用量（实际）
    duration_seconds: int = Field(default=0, ge=0, description="执行时长（秒）")
    cpu_seconds: float = Field(default=0.0, ge=0.0, description="CPU 秒数")
    memory_gb_seconds: float = Field(default=0.0, ge=0.0, description="内存 GB·秒")

    # 执行详情（JSONB）
    execution_details: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB),
        description="执行详情（错误信息、重试次数等）"
    )

    # ✨ 执行模式（新增）
    skill_id: Optional[str] = Field(default=None, max_length=100, description="执行的技能 ID")
    execution_mode: str = Field(default="docker", max_length=20, description="执行模式: docker | native")

    # 时间戳
    submitted_at: datetime = Field(default_factory=get_utc_now, description="提交时间")
    started_at: Optional[datetime] = Field(default=None, description="开始执行时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")

    # 关系
    wallet: Optional[Wallet] = Relationship(back_populates="compute_records")
    flavor: Optional["ResourceFlavor"] = Relationship(back_populates="compute_records")


# ==========================================
# 3. 资金变动明细表 (TransactionLedger)
# ==========================================

class TransactionLedger(SQLModel, table=True):
    """
    资金变动明细表 - 双向记账，可审计

    设计理念：
    1. 每笔交易都有流水号，可追溯
    2. 记录交易前后的余额快照
    3. 支持关联到具体的计算记录
    4. 管理员操作有审计日志
    """
    __tablename__ = "transactionledger"

    # 基础标识
    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: str = Field(default_factory=generate_transaction_id, unique=True, index=True, max_length=50)

    # 关联实体
    wallet_id: str = Field(foreign_key="wallet.wallet_id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    record_id: Optional[str] = Field(default=None, foreign_key="computerecord.record_id", description="关联计算记录")

    # 交易信息
    transaction_type: TransactionType = Field(description="交易类型")
    amount: float = Field(description="交易金额（正数为入账，负数为出账）")

    # 余额快照
    balance_before: float = Field(description="交易前余额")
    balance_after: float = Field(description="交易后余额")
    frozen_before: float = Field(default=0.0, description="冻结前金额")
    frozen_after: float = Field(default=0.0, description="冻结后金额")

    # 描述信息
    description: str = Field(max_length=500, description="交易描述")
    extra_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB),
        description="交易元数据（Stripe ID、管理员 ID 等）"
    )

    # 审计字段
    operator_id: Optional[int] = Field(default=None, foreign_key="user.id", description="操作者 ID")
    ip_address: Optional[str] = Field(default=None, max_length=45, description="操作 IP")

    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now, index=True)

    # 关系
    wallet: Optional[Wallet] = Relationship(back_populates="transactions")


# ==========================================
# 4. 实例规格定义表 (ResourceFlavor)
# ==========================================

class ResourceFlavor(SQLModel, table=True):
    """
    资源规格定义表 - 定义不同规格的计费标准

    设计理念：
    1. 灵活定义各种计算规格
    2. 支持 CPU/GPU 差异化定价
    3. 支持折扣策略
    """
    __tablename__ = "resourceflavor"

    # 基础标识
    id: Optional[int] = Field(default=None, primary_key=True)
    flavor_id: str = Field(default_factory=generate_flavor_id, unique=True, index=True, max_length=50)

    # 规格名称
    name: str = Field(max_length=100, description="规格名称")
    description: Optional[str] = Field(default=None, description="规格描述")

    # 资源配置
    cpu_cores: float = Field(ge=0.0, description="CPU 核数")
    memory_gb: float = Field(ge=0.0, description="内存 GB")
    gpu_type: Optional[str] = Field(default=None, max_length=50, description="GPU 型号")
    gpu_count: int = Field(default=0, ge=0, description="GPU 数量")

    # 计费标准
    price_per_minute: float = Field(ge=0.0, description="每分钟价格 (CU)")
    price_per_hour: float = Field(ge=0.0, description="每小时价格 (CU)")
    min_charge_minutes: int = Field(default=1, ge=1, description="最低收费分钟数")

    # 折扣策略
    discount_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="折扣率")
    discount_reason: Optional[str] = Field(default=None, max_length=200, description="折扣原因")

    # 适用场景
    applicable_tasks: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
        description="适用的任务类型列表"
    )

    # 状态
    is_active: bool = Field(default=True, description="是否启用")
    is_default: bool = Field(default=False, description="是否默认规格")

    # 时间戳
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

    # 关系
    compute_records: List["ComputeRecord"] = Relationship(back_populates="flavor")


# ==========================================
# 请求/响应模型
# ==========================================

class WalletPublic(SQLModel):
    """钱包公开信息"""
    id: int
    wallet_id: str
    wallet_type: WalletType
    credits_balance: float
    credits_frozen: float
    credits_overdraft: float
    total_consumed: float
    status: WalletStatus
    low_balance_threshold: float
    created_at: datetime
    updated_at: datetime


class WalletBalance(SQLModel):
    """钱包余额（轻量接口）"""
    available: float
    frozen: float
    overdraft: float
    total: float


class TransactionPublic(SQLModel):
    """交易记录公开信息"""
    id: int
    transaction_id: str
    transaction_type: TransactionType
    amount: float
    balance_before: float
    balance_after: float
    description: str
    created_at: datetime


class ComputeRecordPublic(SQLModel):
    """计算记录公开信息"""
    id: int
    record_id: str
    task_type: TaskType
    task_name: str
    task_status: TaskStatus
    estimated_cost: float
    frozen_amount: float
    actual_cost: float
    refund_amount: float
    duration_seconds: int
    submitted_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class ResourceFlavorPublic(SQLModel):
    """资源规格公开信息"""
    id: int
    flavor_id: str
    name: str
    description: Optional[str]
    cpu_cores: float
    memory_gb: float
    gpu_count: int
    price_per_minute: float
    price_per_hour: float
    is_default: bool


class FreezeRequest(SQLModel):
    """冻结请求"""
    wallet_id: str
    amount: float = Field(ge=0.0, description="冻结金额")
    record_id: str = Field(description="关联的计算记录 ID")
    description: Optional[str] = Field(default="预授权冻结", description="描述")


class SettleRequest(SQLModel):
    """结算请求"""
    wallet_id: str
    record_id: str
    actual_cost: float = Field(ge=0.0, description="实际消费")
    execution_details: Optional[Dict[str, Any]] = Field(default=None, description="执行详情")


class RefundRequest(SQLModel):
    """退款请求"""
    wallet_id: str
    record_id: str
    reason: str = Field(default="任务取消", max_length=500, description="退款原因")


class RechargeRequest(SQLModel):
    """充值请求"""
    amount: int = Field(ge=10, le=10000, description="充值金额（元）")
    credits: Optional[int] = Field(default=None, ge=10, le=100000, description="充值额度（可选，不传则根据金额计算）")


class AdminAdjustRequest(SQLModel):
    """管理员调整请求"""
    amount: float = Field(description="调整金额（正数增加，负数扣减）")
    reason: str = Field(max_length=500, description="调整原因")


class FreezeRequest(SQLModel):
    """冻结请求"""
    wallet_id: str
    amount: float = Field(ge=0.0, description="冻结金额")
    record_id: str = Field(description="关联的计算记录 ID")
    description: Optional[str] = Field(default="预授权冻结", description="描述")


class SettleRequest(SQLModel):
    """结算请求"""
    wallet_id: str
    record_id: str
    actual_cost: float = Field(ge=0.0, description="实际消费")
    execution_details: Optional[Dict[str, Any]] = Field(default=None, description="执行详情")


class RefundRequest(SQLModel):
    """退款请求"""
    wallet_id: str
    record_id: str
    reason: str = Field(default="任务取消", max_length=500, description="退款原因")