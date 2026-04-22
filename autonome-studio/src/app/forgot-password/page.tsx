/**
 * 忘记密码页面
 *
 * 设计日期: 2026-04-22
 *
 * 三步流程：
 * 1. 输入手机号 → 发送验证码
 * 2. 输入验证码 → 获取 reset_token
 * 3. 设置新密码 → 重置成功
 */

"use client";

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { fetchAPI } from '@/lib/api';
import {
  Phone,
  Lock,
  MessageSquare,
  Send,
  Loader2,
  CheckCircle,
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
} from 'lucide-react';

type Step = 1 | 2 | 3;

export default function ForgotPasswordPage() {
  const router = useRouter();

  const [step, setStep] = useState<Step>(1);
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const [countdown, setCountdown] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState('');

  // 倒计时
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (countdown > 0) {
      timer = setTimeout(() => setCountdown(c => c - 1), 1000);
    }
    return () => clearTimeout(timer);
  }, [countdown]);

  // 步骤 1：发送验证码
  const handleSendSMS = async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      setError('请输入合法的手机号');
      return;
    }
    setError('');
    setIsSending(true);

    try {
      await fetchAPI('/auth/forgot-password/send', {
        method: 'POST',
        body: JSON.stringify({ phone }),
      });
      setCountdown(60);
      setStep(2);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '发送失败');
    } finally {
      setIsSending(false);
    }
  };

  // 步骤 2：验证码校验
  const handleVerifyOTP = async () => {
    if (otp.length < 4) {
      setError('请输入验证码');
      return;
    }
    setError('');
    setIsLoading(true);

    try {
      const data = await fetchAPI('/auth/forgot-password/verify', {
        method: 'POST',
        body: JSON.stringify({ phone, otp_code: otp }),
      });
      setResetToken(data.reset_token);
      setStep(3);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '验证失败');
    } finally {
      setIsLoading(false);
    }
  };

  // 步骤 3：重置密码
  const handleResetPassword = async () => {
    if (newPassword.length < 8) {
      setError('密码长度至少 8 位');
      return;
    }
    if (!/[a-zA-Z]/.test(newPassword) || !/\d/.test(newPassword)) {
      setError('密码需包含字母和数字');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }
    setError('');
    setIsLoading(true);

    try {
      await fetchAPI('/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({
          reset_token: resetToken,
          new_password: newPassword,
        }),
      });
      // 重置成功，跳转到登录页
      router.push('/login?reset=success');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '重置失败');
    } finally {
      setIsLoading(false);
    }
  };

  const stepTitles: Record<Step, string> = {
    1: '输入手机号',
    2: '验证身份',
    3: '设置新密码',
  };

  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-4">
      <div className="w-full max-w-[420px]">
        {/* 返回登录 */}
        <button
          onClick={() => router.push('/login')}
          className="flex items-center gap-2 text-neutral-500 hover:text-neutral-300 mb-8 transition-colors"
        >
          <ArrowLeft size={16} />
          <span className="text-sm">返回登录</span>
        </button>

        {/* 标题 */}
        <h1 className="text-2xl font-bold text-white mb-2">忘记密码</h1>
        <p className="text-sm text-neutral-500 mb-8">{stepTitles[step]}</p>

        {/* 进度条 */}
        <div className="flex gap-2 mb-8">
          {[1, 2, 3].map(s => (
            <div
              key={s}
              className={`h-1 flex-1 rounded-full transition-colors ${
                s <= step ? 'bg-blue-500' : 'bg-neutral-800'
              }`}
            />
          ))}
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
            {error}
          </div>
        )}

        {/* 步骤 1：输入手机号 */}
        {step === 1 && (
          <div className="space-y-4">
            <div className="relative">
              <Phone className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
              <input
                type="tel"
                maxLength={11}
                placeholder="请输入注册时使用的手机号"
                className="w-full pl-11 pr-4 py-3 bg-neutral-900 border border-neutral-800 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                value={phone}
                onChange={e => setPhone(e.target.value.replace(/\D/g, ''))}
              />
            </div>
            <button
              onClick={handleSendSMS}
              disabled={phone.length !== 11 || isSending}
              className="w-full py-3.5 bg-blue-600 text-white font-medium rounded-xl hover:bg-blue-700 disabled:opacity-70 disabled:cursor-not-allowed flex justify-center items-center gap-2 transition-all"
            >
              {isSending ? <Loader2 className="w-5 h-5 animate-spin" /> : <ArrowRight size={18} />}
              {isSending ? '发送中...' : '发送验证码'}
            </button>
          </div>
        )}

        {/* 步骤 2：输入验证码 */}
        {step === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-neutral-400">
              验证码已发送至 <span className="text-white">{phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')}</span>
            </p>
            <div className="flex gap-3">
              <input
                type="text"
                maxLength={6}
                placeholder="6位验证码"
                className="flex-1 px-4 py-3 bg-neutral-900 border border-neutral-800 rounded-xl text-white placeholder-neutral-500 text-center tracking-widest font-mono focus:outline-none focus:border-blue-500 transition-colors"
                value={otp}
                onChange={e => setOtp(e.target.value.replace(/\D/g, ''))}
              />
              <button
                type="button"
                disabled={countdown > 0 || isSending}
                onClick={handleSendSMS}
                className="w-[120px] py-3 bg-blue-500/10 text-blue-400 font-medium rounded-xl disabled:opacity-50 disabled:cursor-not-allowed hover:bg-blue-500/20 transition-colors text-sm"
              >
                {countdown > 0 ? `${countdown}s` : '重新发送'}
              </button>
            </div>
            <button
              onClick={handleVerifyOTP}
              disabled={otp.length < 4 || isLoading}
              className="w-full py-3.5 bg-blue-600 text-white font-medium rounded-xl hover:bg-blue-700 disabled:opacity-70 disabled:cursor-not-allowed flex justify-center items-center gap-2 transition-all"
            >
              {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <ArrowRight size={18} />}
              {isLoading ? '验证中...' : '验证'}
            </button>
          </div>
        )}

        {/* 步骤 3：设置新密码 */}
        {step === 3 && (
          <div className="space-y-4">
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="新密码（至少8位，含字母和数字）"
                className="w-full pl-11 pr-12 py-3 bg-neutral-900 border border-neutral-800 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="确认新密码"
                className="w-full pl-11 pr-4 py-3 bg-neutral-900 border border-neutral-800 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
              />
            </div>
            <button
              onClick={handleResetPassword}
              disabled={isLoading || !newPassword || !confirmPassword}
              className="w-full py-3.5 bg-blue-600 text-white font-medium rounded-xl hover:bg-blue-700 disabled:opacity-70 disabled:cursor-not-allowed flex justify-center items-center gap-2 transition-all"
            >
              {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <CheckCircle size={18} />}
              {isLoading ? '重置中...' : '重置密码'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
