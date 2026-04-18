"use client";

import { useState, useEffect } from 'react';
import {
  Wallet,
  CreditCard,
  History,
  Receipt,
  Plus,
  AlertTriangle,
  ChevronRight,
  Loader2,
  CheckCircle,
  XCircle,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";
import { fetchAPI } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================

interface WalletInfo {
  wallet_id: string;
  wallet_type: string;
  credits_balance: number;
  credits_frozen: number;
  credits_overdraft: number;
  total_consumed: number;
  status: string;
}

interface Transaction {
  transaction_id: string;
  transaction_type: string;
  amount: number;
  balance_before: number;
  balance_after: number;
  description: string;
  created_at: string;
}

interface ComputeRecord {
  record_id: string;
  task_type: string;
  task_name: string;
  status: string;
  estimated_cost: number;
  actual_cost: number;
  duration_seconds: number;
  created_at: string;
}

// 充值套餐
const RECHARGE_PACKAGES = [
  { credits: 100, amount: 68, label: '入门套餐', popular: false },
  { credits: 300, amount: 198, label: '标准套餐', popular: true },
  { credits: 800, amount: 498, label: '专业套餐', popular: false },
  { credits: 1700, amount: 998, label: '企业套餐', popular: false },
];

// 交易类型映射
const TRANSACTION_TYPE_MAP: Record<string, { label: string; color: string }> = {
  recharge_stripe: { label: 'Stripe充值', color: 'text-green-400' },
  recharge_admin: { label: '管理员充值', color: 'text-green-400' },
  consume_chat: { label: '聊天消费', color: 'text-red-400' },
  consume_sandbox: { label: '沙箱消费', color: 'text-red-400' },
  consume_blueprint: { label: '蓝图消费', color: 'text-red-400' },
  consume_terminal: { label: '终端消费', color: 'text-red-400' },
  refund: { label: '退款', color: 'text-blue-400' },
  freeze: { label: '冻结', color: 'text-amber-400' },
  settle: { label: '结算', color: 'text-purple-400' },
};

// ==========================================
// 钱包面板组件
// ==========================================

export function WalletPanel() {
  // 状态
  const [loading, setLoading] = useState(true);
  const [wallet, setWallet] = useState<WalletInfo | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [computeRecords, setComputeRecords] = useState<ComputeRecord[]>([]);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 充值状态
  const [recharging, setRecharging] = useState(false);
  const [selectedPackage, setSelectedPackage] = useState<number | null>(null);

  // 活跃 Tab
  const [activeSection, setActiveSection] = useState<'overview' | 'recharge' | 'history'>('overview');

  // 加载数据
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      // 并行加载钱包和交易记录
      const [walletData, txData, recordsData] = await Promise.all([
        fetchAPI('/billing/wallet').catch(() => null),
        fetchAPI('/billing/transactions?limit=10').catch(() => []),
        fetchAPI('/billing/compute-records?limit=10').catch(() => []),
      ]);

      if (walletData) {
        setWallet(walletData);
      }
      setTransactions(Array.isArray(txData) ? txData : (txData as any)?.items || []);
      setComputeRecords(Array.isArray(recordsData) ? recordsData : (recordsData as any)?.items || []);
    } catch (error) {
      console.error('加载钱包数据失败:', error);
      setMessage({ type: 'error', text: '加载钱包数据失败' });
    } finally {
      setLoading(false);
    }
  };

  // 充值处理
  const handleRecharge = async (pkg: typeof RECHARGE_PACKAGES[0]) => {
    setRecharging(true);
    setSelectedPackage(pkg.credits);

    try {
      const result = await fetchAPI('/billing/recharge/create-session', {
        method: 'POST',
        body: JSON.stringify({
          amount: pkg.amount,
          credits: pkg.credits,
        }),
      });

      if (result.checkout_url) {
        // 跳转到 Stripe 支付页面
        window.open(result.checkout_url, '_blank');
        setMessage({ type: 'success', text: '正在跳转到支付页面...' });
      }
    } catch (error) {
      console.error('创建充值会话失败:', error);
      setMessage({ type: 'error', text: '创建充值会话失败' });
    } finally {
      setRecharging(false);
      setSelectedPackage(null);
    }
  };

  // 格式化时间
  const formatTime = (dateStr: string) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // 格式化时长
  const formatDuration = (seconds: number) => {
    if (!seconds) return '-';
    if (seconds < 60) return `${seconds}秒`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`;
    return `${(seconds / 3600).toFixed(1)}小时`;
  };

  // 获取交易类型显示
  const getTransactionTypeDisplay = (type: string) => {
    return TRANSACTION_TYPE_MAP[type] || { label: type, color: 'text-neutral-400' };
  };

  // 加载中状态
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-6">

        {/* 消息提示 */}
        {message && (
          <div className={`flex items-center gap-2 p-3 rounded-lg ${
            message.type === 'success' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
          }`}>
            {message.type === 'success' ? <CheckCircle size={18} /> : <XCircle size={18} />}
            {message.text}
          </div>
        )}

        {/* 余额概览卡片 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Wallet className="w-5 h-5 text-amber-500" />
              钱包余额
            </h2>
            <span className={`text-xs px-2 py-1 rounded-full ${
              wallet?.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
            }`}>
              {wallet?.status === 'active' ? '正常' : '已挂起'}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-6">
            {/* 可用余额 */}
            <div className="bg-neutral-800/50 rounded-lg p-4">
              <div className="text-neutral-400 text-sm mb-1">可用余额</div>
              <div className="text-2xl font-bold text-white">
                {wallet?.credits_balance?.toFixed(2) || '0.00'}
                <span className="text-sm font-normal text-neutral-400 ml-1">CU</span>
              </div>
            </div>

            {/* 冻结余额 */}
            <div className="bg-neutral-800/50 rounded-lg p-4">
              <div className="text-neutral-400 text-sm mb-1">冻结余额</div>
              <div className="text-2xl font-bold text-amber-400">
                {wallet?.credits_frozen?.toFixed(2) || '0.00'}
                <span className="text-sm font-normal text-neutral-400 ml-1">CU</span>
              </div>
            </div>

            {/* 累计消费 */}
            <div className="bg-neutral-800/50 rounded-lg p-4">
              <div className="text-neutral-400 text-sm mb-1">累计消费</div>
              <div className="text-2xl font-bold text-neutral-300">
                {wallet?.total_consumed?.toFixed(2) || '0.00'}
                <span className="text-sm font-normal text-neutral-400 ml-1">CU</span>
              </div>
            </div>
          </div>

          {/* 透支警告 */}
          {(wallet?.credits_overdraft ?? 0) > 0 && (
            <div className="flex items-center gap-2 p-3 bg-amber-500/20 text-amber-400 rounded-lg mb-4">
              <AlertTriangle size={18} />
              <span className="text-sm">已透支 {(wallet?.credits_overdraft ?? 0).toFixed(2)} CU，请及时充值</span>
            </div>
          )}

          {/* 充值按钮 */}
          <button
            onClick={() => setActiveSection('recharge')}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-colors"
          >
            <Plus size={18} />
            立即充值
          </button>
        </div>

        {/* 充值套餐（展开时显示） */}
        {activeSection === 'recharge' && (
          <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold flex items-center gap-2">
                <CreditCard className="w-5 h-5 text-blue-500" />
                选择充值套餐
              </h3>
              <button
                onClick={() => setActiveSection('overview')}
                className="text-neutral-400 hover:text-white text-sm"
              >
                取消
              </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {RECHARGE_PACKAGES.map((pkg) => (
                <button
                  key={pkg.credits}
                  onClick={() => handleRecharge(pkg)}
                  disabled={recharging}
                  className={`relative p-4 rounded-lg border transition-all ${
                    pkg.popular
                      ? 'border-blue-500 bg-blue-500/10'
                      : 'border-neutral-700 bg-neutral-800/50 hover:border-neutral-600'
                  } ${recharging && selectedPackage === pkg.credits ? 'opacity-50' : ''}`}
                >
                  {pkg.popular && (
                    <span className="absolute -top-2 left-1/2 -translate-x-1/2 bg-blue-500 text-white text-xs px-2 py-0.5 rounded">
                      推荐
                    </span>
                  )}
                  <div className="text-xl font-bold text-white">{pkg.credits} CU</div>
                  <div className="text-neutral-400 text-sm mt-1">¥{pkg.amount}</div>
                  <div className="text-neutral-500 text-xs mt-2">{pkg.label}</div>
                </button>
              ))}
            </div>

            {recharging && (
              <div className="flex items-center justify-center gap-2 mt-4 text-neutral-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                正在创建支付会话...
              </div>
            )}
          </div>
        )}

        {/* 最近交易 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold flex items-center gap-2">
              <History className="w-5 h-5 text-purple-500" />
              最近交易
            </h3>
            <button
              onClick={() => setActiveSection('history')}
              className="text-blue-400 hover:text-blue-300 text-sm flex items-center gap-1"
            >
              查看全部
              <ChevronRight size={14} />
            </button>
          </div>

          {transactions.length === 0 ? (
            <div className="text-center text-neutral-500 py-8">
              暂无交易记录
            </div>
          ) : (
            <div className="space-y-2">
              {transactions.slice(0, 5).map((tx) => {
                const typeDisplay = getTransactionTypeDisplay(tx.transaction_type);
                const isIncome = tx.amount > 0;

                return (
                  <div
                    key={tx.transaction_id}
                    className="flex items-center justify-between p-3 bg-neutral-800/30 rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                        isIncome ? 'bg-green-500/20' : 'bg-red-500/20'
                      }`}>
                        {isIncome ? (
                          <ArrowDownRight className="w-4 h-4 text-green-400" />
                        ) : (
                          <ArrowUpRight className="w-4 h-4 text-red-400" />
                        )}
                      </div>
                      <div>
                        <div className={`text-sm font-medium ${typeDisplay.color}`}>
                          {typeDisplay.label}
                        </div>
                        <div className="text-xs text-neutral-500">{formatTime(tx.created_at)}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-medium ${isIncome ? 'text-green-400' : 'text-red-400'}`}>
                        {isIncome ? '+' : ''}{tx.amount.toFixed(2)} CU
                      </div>
                      <div className="text-xs text-neutral-500">余额: {tx.balance_after.toFixed(2)}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 最近计算记录 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold flex items-center gap-2">
              <Receipt className="w-5 h-5 text-green-500" />
              最近计算
            </h3>
          </div>

          {computeRecords.length === 0 ? (
            <div className="text-center text-neutral-500 py-8">
              暂无计算记录
            </div>
          ) : (
            <div className="space-y-2">
              {computeRecords.slice(0, 5).map((record) => (
                <div
                  key={record.record_id}
                  className="flex items-center justify-between p-3 bg-neutral-800/30 rounded-lg"
                >
                  <div>
                    <div className="text-sm font-medium text-white truncate max-w-[200px]">
                      {record.task_name || record.task_type}
                    </div>
                    <div className="text-xs text-neutral-500">
                      {formatTime(record.created_at)} · {formatDuration(record.duration_seconds)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`font-medium ${
                      record.status === 'COMPLETED' ? 'text-red-400' : 'text-neutral-400'
                    }`}>
                      -{record.actual_cost?.toFixed(2) || record.estimated_cost?.toFixed(2) || '0.00'} CU
                    </div>
                    <div className={`text-xs ${
                      record.status === 'COMPLETED' ? 'text-green-400' :
                      record.status === 'FAILED' ? 'text-red-400' : 'text-amber-400'
                    }`}>
                      {record.status}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}