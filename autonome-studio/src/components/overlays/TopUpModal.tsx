"use client";
import { useState } from "react";
import { X, Zap, CreditCard, CheckCircle2, Loader2 } from "lucide-react";
import { fetchAPI, BASE_URL } from "../../lib/api";

interface TopUpModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function TopUpModal({ isOpen, onClose, onSuccess }: TopUpModalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleTopUp = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const data = await fetchAPI('/api/billing/create-checkout-session', {
        method: 'POST'
      });
      
      // 跳转到 Stripe Checkout
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err: any) {
      setError(err.message || "Failed to create checkout session");
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-neutral-900 border border-neutral-800 rounded-2xl p-8 max-w-md w-full mx-4 shadow-2xl">
        {/* Close button */}
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 text-neutral-500 hover:text-white transition-colors"
        >
          <X size={20} />
        </button>
        
        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-amber-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <Zap size={32} className="text-amber-500" />
          </div>
          <h3 className="text-white font-semibold text-xl mb-2">充值算力 Credits</h3>
          <p className="text-neutral-400 text-sm">
            您的算力余额不足，需要充值后才能继续使用 AI 服务
          </p>
        </div>

        {/* Credits Pack Info */}
        <div className="bg-neutral-800/50 rounded-xl p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <CreditCard size={20} className="text-blue-400" />
              <span className="text-white font-medium">算力套餐</span>
            </div>
            <span className="text-amber-400 font-bold text-lg">¥68</span>
          </div>
          <div className="text-sm text-neutral-400 space-y-1">
            <p>• 获得 <span className="text-white font-medium">100 算力点数</span></p>
            <p>• 支持 GPT-4o, Claude, 本地 Ollama 等模型</p>
            <p>• 有效期 12 个月</p>
          </div>
        </div>

        {/* Error message */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-3 bg-neutral-800 text-white rounded-lg font-medium hover:bg-neutral-700 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleTopUp}
            disabled={isLoading}
            className="flex-1 px-4 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                跳转支付...
              </>
            ) : (
              <>
                <CheckCircle2 size={18} />
                立即充值
              </>
            )}
          </button>
        </div>

        {/* Footer note */}
        <p className="text-center text-neutral-500 text-xs mt-4">
          安全支付由 Stripe 提供保障
        </p>
      </div>
    </div>
  );
}
