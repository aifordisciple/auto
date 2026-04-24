/**
 * OAuth 绑定手机号模态框
 *
 * 设计日期: 2026-04-22
 *
 * 功能：
 * - 第三方 OAuth 登录后，若未关联已有用户，弹出此不可关闭的模态框
 * - 用户必须输入手机号 + 验证码完成绑定
 * - 绑定成功后关闭模态框，设置认证状态
 */

"use client";

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { fetchAPI } from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import { TurnstileWidget } from '@/components/TurnstileWidget';
import {
  Smartphone,
  ShieldCheck,
  Loader2,
  AlertCircle,
  CheckCircle,
} from 'lucide-react';

interface BindPhoneModalProps {
  bindRef: string;
  providerName?: string;
  onComplete: () => void;
}

export function BindPhoneModal({ bindRef, providerName, onComplete }: BindPhoneModalProps) {
  const router = useRouter();
  const { setUser, setToken, fetchProfile } = useAuthStore();

  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Turnstile 人机验证 token
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);

  // 倒计时逻辑
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (countdown > 0) {
      timer = setTimeout(() => setCountdown(c => c - 1), 1000);
    }
    return () => clearTimeout(timer);
  }, [countdown]);

  // 发送验证码
  const handleSendSMS = async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      setError('请输入合法的中国大陆手机号');
      return;
    }
    setError('');
    setIsSending(true);

    try {
      await fetchAPI('/auth/send-sms', {
        method: 'POST',
        body: JSON.stringify({ phone_number: phone, captcha_token: captchaToken }),
      });
      setCountdown(60);
      setSuccess('验证码已发送');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '发送失败');
    } finally {
      setIsSending(false);
    }
  };

  // 提交绑定
  const handleBind = async () => {
    if (!phone || !otp) {
      setError('请输入手机号和验证码');
      return;
    }
    setError('');
    setIsLoading(true);

    try {
      const data = await fetchAPI('/auth/bind-phone', {
        method: 'POST',
        body: JSON.stringify({
          phone,
          otp_code: otp,
          bind_ref: bindRef,
        }),
      });

      // 绑定成功，设置认证状态
      if (data.access_token) {
        setToken(data.access_token);
      }
      if (data.user) {
        setUser(data.user);
      }

      // 刷新完整用户资料
      await fetchProfile();

      // 通知父组件绑定完成
      onComplete();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '绑定失败');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[9999]">
      <div className="bg-neutral-900 border border-neutral-800 rounded-2xl w-[420px] p-8 shadow-2xl">
        {/* 标题 */}
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-blue-500/10 rounded-lg">
            <ShieldCheck className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">绑定手机号</h2>
            <p className="text-xs text-neutral-500">
              {providerName ? `${providerName} 账号` : '第三方账号'}需绑定手机号后才能使用
            </p>
          </div>
        </div>

        {/* 说明 */}
        <p className="text-sm text-neutral-400 mb-6">
          根据合规要求，您的第三方账号需绑定手机号后才能进入工作台。
          未注册的手机号将自动创建账号。
        </p>

        {/* 错误/成功提示 */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400 flex items-center gap-2">
            <AlertCircle size={16} />
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-sm text-green-400 flex items-center gap-2">
            <CheckCircle size={16} />
            {success}
          </div>
        )}

        {/* 手机号输入 */}
        <div className="space-y-4">
          <div className="relative">
            <Smartphone className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
            <input
              type="tel"
              maxLength={11}
              placeholder="请输入手机号"
              className="w-full pl-11 pr-4 py-3 bg-neutral-800 border border-neutral-700 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
              value={phone}
              onChange={e => setPhone(e.target.value.replace(/\D/g, ''))}
            />
          </div>

          {/* 验证码输入 + 发送按钮 */}
          <div className="flex gap-3">
            <input
              type="text"
              maxLength={6}
              placeholder="6位验证码"
              className="flex-1 px-4 py-3 bg-neutral-800 border border-neutral-700 rounded-xl text-white placeholder-neutral-500 text-center tracking-widest font-mono focus:outline-none focus:border-blue-500 transition-colors"
              value={otp}
              onChange={e => setOtp(e.target.value.replace(/\D/g, ''))}
            />
            <button
              type="button"
              disabled={countdown > 0 || phone.length !== 11 || isSending}
              onClick={handleSendSMS}
              className="w-[120px] py-3 bg-blue-500/10 text-blue-400 font-medium rounded-xl disabled:opacity-50 disabled:cursor-not-allowed hover:bg-blue-500/20 transition-colors text-sm"
            >
              {isSending ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : null}
              {!isSending && (countdown > 0 ? `${countdown}s` : '获取验证码')}
            </button>
          </div>

          {/* Turnstile 人机验证 */}
          <TurnstileWidget
            onVerify={(token) => setCaptchaToken(token)}
            onError={() => setCaptchaToken(null)}
            onExpire={() => setCaptchaToken(null)}
          />

          {/* 绑定按钮 */}
          <button
            onClick={handleBind}
            disabled={isLoading || !phone || otp.length < 4}
            className="w-full py-3.5 bg-blue-600 text-white font-medium rounded-xl hover:bg-blue-700 disabled:opacity-70 disabled:cursor-not-allowed flex justify-center items-center gap-2 transition-all"
          >
            {isLoading && <Loader2 className="w-5 h-5 animate-spin" />}
            {isLoading ? '绑定中...' : '立即绑定并登录'}
          </button>
        </div>
      </div>
    </div>
  );
}
