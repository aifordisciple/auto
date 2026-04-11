"""
计费核心服务

设计日期: 2026-03-23

核心功能：
1. 预授权冻结机制：任务提交前冻结预估费用
2. 费用结算：任务完成后按实际消费结算（多退少补）
3. 余额检查：实时检查可用余额
4. 交易记录：所有资金变动都有审计日志

设计理念：
- 所有操作为原子事务
- 完整的交易记录和余额快照
- 异常处理和错误码
"""

from typing import Optional, Tuple
from sqlmodel import Session, select
from datetime import datetime, timezone
from loguru import logger

from app.models.billing import (
    Wallet,
    WalletType,
    WalletStatus,
    ComputeRecord,
    TaskType,
    TaskStatus,
    TransactionLedger,
    TransactionType,
    ResourceFlavor,
    BillingError,
    InsufficientBalanceError,
    WalletSuspendedError,
    get_utc_now,
)
from app.models.domain import User


# ==========================================
# 计费配置常量
# ==========================================

# 默认规格定价（CU = Compute Unit）
DEFAULT_PRICING = {
    "chat": {
        "price_per_1k_tokens": 0.01,  # 每千 Token 0.01 CU
        "min_charge": 0.01,
    },
    "sandbox": {
        "price_per_minute": 0.1,  # 每分钟 0.1 CU
        "min_charge_minutes": 1,
    },
    "terminal": {
        "price_per_minute": 0.05,  # 每分钟 0.05 CU
        "min_charge_minutes": 5,  # 最低 5 分钟
    },
    "blueprint": {
        "price_per_minute": 0.2,  # 每分钟 0.2 CU
        "min_charge_minutes": 1,
    },
}

# 默认冻结金额倍数（预估费用 × 倍数）
FREEZE_MULTIPLIER = 1.5


# ==========================================
# BillingService 核心服务类
# ==========================================

class BillingService:
    """
    计费核心服务

    职责：
    1. 预授权冻结/解冻
    2. 费用结算
    3. 余额检查
    4. 交易记录
    """

    def __init__(self, session: Session):
        self.session = session

    def _get_wallet_by_wallet_id(self, wallet_id: str) -> Optional[Wallet]:
        """
        根据 wallet_id 字符串获取钱包

        注意：session.get(Wallet, pk) 使用主键查询，但 wallet_id 是字符串
        所以需要用 select().where() 查询

        Args:
            wallet_id: 钱包 ID（字符串格式：wallet_xxx）

        Returns:
            钱包对象
        """
        return self.session.exec(
            select(Wallet).where(Wallet.wallet_id == wallet_id)
        ).first()

    def get_wallet(self, wallet_id: str) -> Wallet:
        """
        获取钱包（公开方法）

        Args:
            wallet_id: 钱包 ID（字符串格式：wallet_xxx）

        Returns:
            钱包对象

        Raises:
            BillingError: 钱包不存在
        """
        wallet = self._get_wallet_by_wallet_id(wallet_id)
        if not wallet:
            raise BillingError(f"钱包不存在: {wallet_id}")
        return wallet

    # ==========================================
    # 钱包管理
    # ==========================================

    def get_user_wallet(self, user_id: int, create_if_not_exists: bool = True) -> Optional[Wallet]:
        """
        获取用户的个人钱包

        Args:
            user_id: 用户 ID
            create_if_not_exists: 如果钱包不存在是否自动创建

        Returns:
            钱包对象，不存在时返回 None 或创建新钱包
        """
        wallet = self.session.exec(
            select(Wallet).where(
                Wallet.owner_id == user_id,
                Wallet.wallet_type == WalletType.PERSONAL
            )
        ).first()

        if not wallet and create_if_not_exists:
            wallet = self._create_wallet(user_id)
            logger.info(f"[BillingService] 为用户 {user_id} 创建钱包: {wallet.wallet_id}")

        return wallet

    def _create_wallet(self, user_id: int, initial_balance: float = 100.0) -> Wallet:
        """
        创建新钱包

        Args:
            user_id: 用户 ID
            initial_balance: 初始余额

        Returns:
            新创建的钱包对象
        """
        wallet = Wallet(
            owner_id=user_id,
            wallet_type=WalletType.PERSONAL,
            credits_balance=initial_balance,
            status=WalletStatus.ACTIVE
        )
        self.session.add(wallet)
        self.session.commit()
        self.session.refresh(wallet)
        return wallet

    # ==========================================
    # 余额检查
    # ==========================================

    def check_available(self, wallet: Wallet, min_amount: float = 0.0) -> bool:
        """
        检查钱包是否有足够的可用余额

        Args:
            wallet: 钱包对象
            min_amount: 最低需要的金额

        Returns:
            True 如果余额充足，False 如果余额不足
        """
        if wallet.status != WalletStatus.ACTIVE:
            return False

        available = wallet.credits_balance + wallet.credits_overdraft
        return available >= min_amount

    def get_available_balance(self, wallet: Wallet) -> float:
        """
        获取可用余额（余额 + 透支额度）

        Args:
            wallet: 钱包对象

        Returns:
            可用余额
        """
        return wallet.credits_balance + wallet.credits_overdraft

    # ==========================================
    # 费用预估
    # ==========================================

    def estimate_cost(
        self,
        task_type: TaskType,
        estimated_duration_minutes: float = 10.0,
        flavor: ResourceFlavor = None
    ) -> float:
        """
        预估任务费用

        Args:
            task_type: 任务类型
            estimated_duration_minutes: 预估执行时长（分钟）
            flavor: 实例规格（可选）

        Returns:
            预估费用（CU）
        """
        # 如果有规格定义，使用规格定价
        if flavor:
            duration = max(estimated_duration_minutes, flavor.min_charge_minutes)
            base_cost = flavor.price_per_minute * duration
            final_cost = base_cost * (1 - flavor.discount_rate)
            return round(final_cost, 2)

        # 否则使用默认定价
        pricing = DEFAULT_PRICING.get(task_type.value, DEFAULT_PRICING["sandbox"])
        price_per_minute = pricing.get("price_per_minute", 0.1)
        min_minutes = pricing.get("min_charge_minutes", 1)

        duration = max(estimated_duration_minutes, min_minutes)
        cost = price_per_minute * duration

        # 应用冻结倍数
        cost = cost * FREEZE_MULTIPLIER

        return round(cost, 2)

    # ==========================================
    # 预授权冻结
    # ==========================================

    def freeze_credits(
        self,
        wallet_id: str,
        amount: float,
        record_id: str,
        description: str = "预授权冻结"
    ) -> TransactionLedger:
        """
        冻结余额（预授权）

        流程：
        1. 检查钱包状态
        2. 检查可用余额
        3. 扣减可用余额，增加冻结余额
        4. 创建冻结交易记录

        Args:
            wallet_id: 钱包 ID
            amount: 冻结金额
            record_id: 关联的计算记录 ID
            description: 描述

        Returns:
            交易记录

        Raises:
            BillingError: 钱包不存在或状态异常
            InsufficientBalanceError: 余额不足
        """
        wallet = self._get_wallet_by_wallet_id(wallet_id)
        if not wallet:
            raise BillingError(f"钱包不存在: {wallet_id}")

        if wallet.status != WalletStatus.ACTIVE:
            raise WalletSuspendedError(f"钱包状态异常: {wallet.status}")

        available = self.get_available_balance(wallet)
        if available < amount:
            raise InsufficientBalanceError(
                f"余额不足: 可用 {available:.2f} CU, 需要 {amount:.2f} CU",
                available=available,
                required=amount
            )

        # 记录快照
        balance_before = wallet.credits_balance
        frozen_before = wallet.credits_frozen

        # 执行冻结
        if wallet.credits_balance >= amount:
            wallet.credits_balance -= amount
        else:
            # 部分使用透支额度
            overdraft_needed = amount - wallet.credits_balance
            wallet.credits_balance = 0
            wallet.credits_overdraft -= overdraft_needed

        wallet.credits_frozen += amount
        wallet.total_frozen_count += 1
        wallet.updated_at = get_utc_now()

        # 创建交易记录
        transaction = TransactionLedger(
            wallet_id=wallet_id,
            user_id=wallet.owner_id,
            record_id=record_id,
            transaction_type=TransactionType.FREEZE,
            amount=-amount,
            balance_before=balance_before,
            balance_after=wallet.credits_balance,
            frozen_before=frozen_before,
            frozen_after=wallet.credits_frozen,
            description=description
        )

        self.session.add(wallet)
        self.session.add(transaction)
        self.session.commit()
        self.session.refresh(transaction)

        logger.info(f"[BillingService] 冻结成功: wallet={wallet_id}, amount={amount:.2f}, tx={transaction.transaction_id}")

        return transaction

    # ==========================================
    # 结算冻结金额
    # ==========================================

    def settle_frozen_credits(
        self,
        wallet_id: str,
        record_id: str,
        actual_cost: float,
        execution_details: dict = None
    ) -> Tuple[TransactionLedger, ComputeRecord]:
        """
        结算冻结金额

        流程：
        1. 查询冻结的 ComputeRecord
        2. 计算实际消费
        3. 多退少补
        4. 更新 ComputeRecord 状态

        Args:
            wallet_id: 钱包 ID
            record_id: 计算记录 ID
            actual_cost: 实际消费金额
            execution_details: 执行详情

        Returns:
            (结算交易记录, 更新后的计算记录)

        Raises:
            BillingError: 记录不存在或状态异常
        """
        wallet = self.session.get(Wallet, wallet_id)
        record = self.session.exec(
            select(ComputeRecord).where(ComputeRecord.record_id == record_id)
        ).first()

        if not wallet or not record:
            raise BillingError("钱包或记录不存在")

        if record.task_status not in [TaskStatus.FROZEN, TaskStatus.RUNNING]:
            raise BillingError(f"记录状态异常: {record.task_status}")

        frozen_amount = record.frozen_amount
        refund_amount = max(0, frozen_amount - actual_cost)

        # 记录快照
        balance_before = wallet.credits_balance
        frozen_before = wallet.credits_frozen

        # 执行结算
        wallet.credits_frozen -= frozen_amount
        wallet.credits_balance += refund_amount  # 退还多扣部分
        wallet.total_consumed += actual_cost
        wallet.updated_at = get_utc_now()

        # 更新 ComputeRecord
        record.actual_cost = actual_cost
        record.refund_amount = refund_amount
        record.task_status = TaskStatus.COMPLETED
        record.completed_at = get_utc_now()
        if execution_details:
            record.execution_details = execution_details

        # 创建结算交易记录
        settle_tx = TransactionLedger(
            wallet_id=wallet_id,
            user_id=wallet.owner_id,
            record_id=record_id,
            transaction_type=TransactionType.SETTLE,
            amount=-actual_cost,
            balance_before=balance_before,
            balance_after=wallet.credits_balance,
            frozen_before=frozen_before,
            frozen_after=wallet.credits_frozen,
            description=f"任务结算: 实际消费 {actual_cost:.2f} CU, 退款 {refund_amount:.2f} CU"
        )

        # 如果有退款，创建退款交易记录
        if refund_amount > 0:
            refund_tx = TransactionLedger(
                wallet_id=wallet_id,
                user_id=wallet.owner_id,
                record_id=record_id,
                transaction_type=TransactionType.REFUND,
                amount=refund_amount,
                balance_before=wallet.credits_balance - refund_amount,
                balance_after=wallet.credits_balance,
                description=f"预授权退款: {refund_amount:.2f} CU"
            )
            self.session.add(refund_tx)

        self.session.add_all([wallet, record, settle_tx])
        self.session.commit()
        self.session.refresh(settle_tx)
        self.session.refresh(record)

        logger.info(f"[BillingService] 结算成功: wallet={wallet_id}, actual={actual_cost:.2f}, refund={refund_amount:.2f}")

        return settle_tx, record

    # ==========================================
    # 全额退款
    # ==========================================

    def refund_frozen_credits(
        self,
        wallet_id: str,
        record_id: str,
        reason: str = "任务取消"
    ) -> TransactionLedger:
        """
        全额退款（任务取消/失败时）

        Args:
            wallet_id: 钱包 ID
            record_id: 计算记录 ID
            reason: 退款原因

        Returns:
            退款交易记录

        Raises:
            BillingError: 记录不存在或状态异常
        """
        wallet = self.session.get(Wallet, wallet_id)
        record = self.session.exec(
            select(ComputeRecord).where(ComputeRecord.record_id == record_id)
        ).first()

        if not wallet or not record:
            raise BillingError("钱包或记录不存在")

        frozen_amount = record.frozen_amount

        if frozen_amount <= 0:
            logger.warning(f"[BillingService] 无冻结金额可退款: record={record_id}")
            return None

        # 记录快照
        balance_before = wallet.credits_balance
        frozen_before = wallet.credits_frozen

        # 全额退款
        wallet.credits_frozen -= frozen_amount
        wallet.credits_balance += frozen_amount
        wallet.updated_at = get_utc_now()

        # 更新 ComputeRecord
        record.task_status = TaskStatus.CANCELLED
        record.refund_amount = frozen_amount
        record.completed_at = get_utc_now()
        record.execution_details = {"refund_reason": reason}

        # 创建退款交易记录
        transaction = TransactionLedger(
            wallet_id=wallet_id,
            user_id=wallet.owner_id,
            record_id=record_id,
            transaction_type=TransactionType.REFUND,
            amount=frozen_amount,
            balance_before=balance_before,
            balance_after=wallet.credits_balance,
            frozen_before=frozen_before,
            frozen_after=wallet.credits_frozen,
            description=f"全额退款: {reason} ({frozen_amount:.2f} CU)"
        )

        self.session.add_all([wallet, record, transaction])
        self.session.commit()
        self.session.refresh(transaction)

        logger.info(f"[BillingService] 退款成功: wallet={wallet_id}, amount={frozen_amount:.2f}, reason={reason}")

        return transaction

    # ==========================================
    # 直接消费（无冻结）
    # ==========================================

    def deduct_credits(
        self,
        wallet_id: str,
        amount: float,
        transaction_type: TransactionType,
        description: str = "",
        record_id: str = None
    ) -> TransactionLedger:
        """
        直接扣费（不经过冻结流程）

        用于即时消费场景（如对话 Token 消费）

        Args:
            wallet_id: 钱包 ID
            amount: 扣费金额
            transaction_type: 交易类型
            description: 描述
            record_id: 关联的计算记录 ID

        Returns:
            交易记录
        """
        wallet = self._get_wallet_by_wallet_id(wallet_id)
        if not wallet:
            raise BillingError(f"钱包不存在: {wallet_id}")

        if wallet.status != WalletStatus.ACTIVE:
            raise WalletSuspendedError(f"钱包状态异常: {wallet.status}")

        available = self.get_available_balance(wallet)
        if available < amount:
            raise InsufficientBalanceError(
                f"余额不足: 可用 {available:.2f} CU, 需要 {amount:.2f} CU",
                available=available,
                required=amount
            )

        # 记录快照
        balance_before = wallet.credits_balance

        # 执行扣费
        if wallet.credits_balance >= amount:
            wallet.credits_balance -= amount
        else:
            overdraft_needed = amount - wallet.credits_balance
            wallet.credits_balance = 0
            wallet.credits_overdraft -= overdraft_needed

        wallet.total_consumed += amount
        wallet.updated_at = get_utc_now()

        # 创建交易记录
        transaction = TransactionLedger(
            wallet_id=wallet_id,
            user_id=wallet.owner_id,
            record_id=record_id,
            transaction_type=transaction_type,
            amount=-amount,
            balance_before=balance_before,
            balance_after=wallet.credits_balance,
            description=description or f"消费: {transaction_type.value}"
        )

        self.session.add(wallet)
        self.session.add(transaction)
        self.session.commit()
        self.session.refresh(transaction)

        return transaction

    # ==========================================
    # 充值
    # ==========================================

    def recharge(
        self,
        wallet_id: str,
        amount: float,
        transaction_type: TransactionType = TransactionType.RECHARGE_STRIPE,
        description: str = "",
        metadata: dict = None,
        operator_id: int = None
    ) -> TransactionLedger:
        """
        充值

        Args:
            wallet_id: 钱包 ID
            amount: 充值金额
            transaction_type: 交易类型（Stripe/管理员/促销）
            description: 描述
            metadata: 元数据
            operator_id: 操作者 ID（管理员充值时）

        Returns:
            交易记录
        """
        wallet = self._get_wallet_by_wallet_id(wallet_id)
        if not wallet:
            raise BillingError(f"钱包不存在: {wallet_id}")

        # 记录快照
        balance_before = wallet.credits_balance

        # 执行充值
        wallet.credits_balance += amount
        wallet.updated_at = get_utc_now()

        # 如果钱包是挂起状态，检查是否可以恢复
        if wallet.status == WalletStatus.SUSPENDED:
            available = self.get_available_balance(wallet)
            if available > wallet.auto_suspend_threshold:
                wallet.status = WalletStatus.ACTIVE
                wallet.suspended_at = None
                wallet.suspended_reason = None
                logger.info(f"[BillingService] 钱包恢复: {wallet_id}")

        # 创建交易记录
        transaction = TransactionLedger(
            wallet_id=wallet_id,
            user_id=wallet.owner_id,
            transaction_type=transaction_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.credits_balance,
            description=description or f"充值: +{amount:.2f} CU",
            metadata=metadata,
            operator_id=operator_id
        )

        self.session.add(wallet)
        self.session.add(transaction)
        self.session.commit()
        self.session.refresh(transaction)

        logger.info(f"[BillingService] 充值成功: wallet={wallet_id}, amount={amount:.2f}")

        return transaction

    # ==========================================
    # 创建计算记录
    # ==========================================

    def create_compute_record(
        self,
        wallet_id: str,
        user_id: int,
        task_type: TaskType,
        task_name: str,
        project_id: str = None,
        estimated_cost: float = 0.0,
        flavor_id: str = None
    ) -> ComputeRecord:
        """
        创建计算记录

        Args:
            wallet_id: 钱包 ID
            user_id: 用户 ID
            task_type: 任务类型
            task_name: 任务名称
            project_id: 项目 ID
            estimated_cost: 预估费用
            flavor_id: 实例规格 ID

        Returns:
            计算记录
        """
        record = ComputeRecord(
            wallet_id=wallet_id,
            user_id=user_id,
            task_type=task_type,
            task_name=task_name,
            project_id=project_id,
            task_status=TaskStatus.PENDING,
            estimated_cost=estimated_cost,
            flavor_id=flavor_id
        )

        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)

        return record

    def start_compute_record(self, record_id: str) -> ComputeRecord:
        """
        开始计算（更新状态为 RUNNING）

        Args:
            record_id: 计算记录 ID

        Returns:
            更新后的计算记录
        """
        record = self.session.exec(
            select(ComputeRecord).where(ComputeRecord.record_id == record_id)
        ).first()

        if not record:
            raise BillingError(f"计算记录不存在: {record_id}")

        record.task_status = TaskStatus.RUNNING
        record.started_at = get_utc_now()

        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)

        return record

    def fail_compute_record(
        self,
        record_id: str,
        error_message: str = None
    ) -> ComputeRecord:
        """
        标记计算记录为失败

        Args:
            record_id: 计算记录 ID
            error_message: 错误信息

        Returns:
            更新后的计算记录
        """
        record = self.session.exec(
            select(ComputeRecord).where(ComputeRecord.record_id == record_id)
        ).first()

        if not record:
            raise BillingError(f"计算记录不存在: {record_id}")

        record.task_status = TaskStatus.FAILED
        record.completed_at = get_utc_now()
        if error_message:
            record.execution_details = {"error": error_message}

        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)

        return record


# ==========================================
# 便捷函数
# ==========================================

def get_billing_service(session: Session) -> BillingService:
    """获取计费服务实例"""
    return BillingService(session)