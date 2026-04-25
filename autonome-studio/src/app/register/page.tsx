'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/useAuthStore';
import { fetchAPI } from '@/lib/api';
import { TurnstileWidget } from '@/components/TurnstileWidget';

// ==========================================
// 注册页面 —— 手机号 + 短信验证码 + 设置密码
// ==========================================
// 流程：
//   Step 1: 输入手机号 → 发送验证码 → 输入验证码
//   Step 2: 设置密码 + 确认密码 + 姓名
//   成功后自动登录并跳转首页
// ==========================================

export default function RegisterPage() {
  const router = useRouter();
  const { setToken, setUser } = useAuthStore();

  // ---- 表单状态 ----
  const [step, setStep] = useState<1 | 2>(1);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fullName, setFullName] = useState('');

  // ---- UI 状态 ----
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Turnstile 人机验证 token
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);

  // 隐私协议勾选
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [countdown, setCountdown] = useState(0);

  // ---- 倒计时逻辑 ----
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  // ---- 发送短信验证码 ----
  const handleSendSMS = useCallback(async () => {
    if (!phoneNumber.trim()) {
      setError('请输入手机号');
      return;
    }
    // 简单的中国手机号格式校验
    if (!/^1[3-9]\d{9}$/.test(phoneNumber.trim())) {
      setError('请输入有效的手机号');
      return;
    }

    setError('');
    setLoading(true);
    try {
      await fetchAPI('/auth/send-sms', {
        method: 'POST',
        body: JSON.stringify({ phone_number: phoneNumber.trim(), captcha_token: captchaToken }),
      });
      setCountdown(60);
    } catch (err: any) {
      setError(err.message || '验证码发送失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [phoneNumber]);

  // ---- Step 1 下一步：前端校验手机号与验证码格式 ----
  // 注意：短信验证码的真实校验在 Step 2 提交注册时由后端 /auth/register 完成，
  // 此处仅做前端格式校验，避免使用错误的 /auth/forgot-password/verify 端点。
  const handleStep1Next = useCallback(async () => {
    if (!phoneNumber.trim()) {
      setError('请输入手机号');
      return;
    }
    // 中国手机号格式校验
    if (!/^1[3-9]\d{9}$/.test(phoneNumber.trim())) {
      setError('请输入有效的手机号');
      return;
    }
    if (!smsCode.trim()) {
      setError('请输入验证码');
      return;
    }
    if (smsCode.trim().length !== 6 || !/^\d{6}$/.test(smsCode.trim())) {
      setError('请输入6位数字验证码');
      return;
    }

    // 前端校验通过，进入 Step 2
    setStep(2);
  }, [phoneNumber, smsCode]);

  // ---- Step 2 提交注册 ----
  const handleRegister = useCallback(async () => {
    // 校验
    if (!fullName.trim()) {
      setError('请输入姓名');
      return;
    }
    if (!password) {
      setError('请设置密码');
      return;
    }
    if (password.length < 8) {
      setError('密码至少 8 位');
      return;
    }
    if (password !== confirmPassword) {
      setError('两次密码不一致');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const data = await fetchAPI('/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          phone_number: phoneNumber.trim(),
          sms_code: smsCode.trim(),
          password,
          full_name: fullName.trim(),
        }),
      });

      // 注册成功，自动登录
      if (data.access_token) {
        setToken(data.access_token);
        setUser({
          id: data.user.id,
          email: data.user.email,
          full_name: data.user.full_name,
          is_superuser: data.user.is_superuser,
          phone_number: data.user.phone_number,
          is_email_verified: data.user.is_email_verified,
          is_2fa_enabled: data.user.is_2fa_enabled,
        });
        router.push('/');
      } else {
        // 注册成功但未自动登录，跳转登录页
        router.push('/login');
      }
    } catch (err: any) {
      setError(err.message || '注册失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, [phoneNumber, smsCode, password, confirmPassword, fullName, setToken, setUser, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-950">
      <div className="w-full max-w-md p-8">
        {/* Logo / 标题 */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-white">创建账户</h1>
          <p className="text-sm text-gray-400 mt-2">注册 Autonome Studio 账户</p>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* 步骤指示器 */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <div className={`h-1.5 w-16 rounded-full ${step >= 1 ? 'bg-blue-500' : 'bg-gray-700'}`} />
          <div className={`h-1.5 w-16 rounded-full ${step >= 2 ? 'bg-blue-500' : 'bg-gray-700'}`} />
        </div>

        {step === 1 ? (
          /* ====== Step 1: 手机号 + 验证码 ====== */
          <div className="space-y-4">
            {/* 手机号 */}
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">手机号</label>
              <input
                type="tel"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                placeholder="请输入手机号"
                className="w-full px-4 py-3 rounded-lg bg-neutral-900 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                disabled={loading}
              />
            </div>

            {/* 验证码 */}
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">验证码</label>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={smsCode}
                  onChange={(e) => setSmsCode(e.target.value)}
                  placeholder="请输入验证码"
                  maxLength={6}
                  className="flex-1 px-4 py-3 rounded-lg bg-neutral-900 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                  disabled={loading}
                />
                <button
                  onClick={handleSendSMS}
                  disabled={countdown > 0 || loading}
                  className="px-4 py-3 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                >
                  {countdown > 0 ? `${countdown}s` : '获取验证码'}
                </button>
              </div>
            </div>

            {/* Turnstile 人机验证 */}
            <TurnstileWidget
              onVerify={(token) => setCaptchaToken(token)}
              onError={() => setCaptchaToken(null)}
              onExpire={() => setCaptchaToken(null)}
            />

            {/* 下一步按钮 */}
            <button
              onClick={handleStep1Next}
              disabled={loading}
              className="w-full py-3 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '验证中...' : '下一步'}
            </button>
          </div>
        ) : (
          /* ====== Step 2: 设置密码 + 姓名 ====== */
          <div className="space-y-4">
            {/* 姓名 */}
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">姓名</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="请输入您的姓名"
                className="w-full px-4 py-3 rounded-lg bg-neutral-900 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                disabled={loading}
              />
            </div>

            {/* 密码 */}
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">密码</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 8 位"
                className="w-full px-4 py-3 rounded-lg bg-neutral-900 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                disabled={loading}
              />
            </div>

            {/* 确认密码 */}
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">确认密码</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="再次输入密码"
                className="w-full px-4 py-3 rounded-lg bg-neutral-900 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                disabled={loading}
              />
            </div>

            {/* 隐私协议勾选 */}
            <label className="flex items-start gap-2 text-sm text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={agreedToTerms}
                onChange={(e) => setAgreedToTerms(e.target.checked)}
                className="mt-1 h-4 w-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
              />
              <span>
                我已阅读并同意
                <a href="/terms" className="text-blue-400 hover:text-blue-300" target="_blank">《服务条款》</a>
                和
                <a href="/privacy" className="text-blue-400 hover:text-blue-300" target="_blank">《隐私政策》</a>
              </span>
            </label>

            {/* 注册按钮 */}
            <button
              onClick={handleRegister}
              disabled={loading || !agreedToTerms}
              className="w-full py-3 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '注册中...' : '注册'}
            </button>

            {/* 返回上一步 */}
            <button
              onClick={() => {
                setStep(1);
                setError('');
              }}
              className="w-full py-2 text-sm text-gray-400 hover:text-white"
            >
              返回上一步
            </button>
          </div>
        )}

        {/* 底部链接：已有账户？登录 */}
        <div className="mt-6 text-center text-sm text-gray-400">
          已有账户？{' '}
          <button
            onClick={() => router.push('/login')}
            className="text-blue-400 hover:text-blue-300"
          >
            登录
          </button>
        </div>
      </div>
    </div>
  );
}
