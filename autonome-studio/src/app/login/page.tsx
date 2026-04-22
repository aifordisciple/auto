/**
 * 登录页面 - 双通道认证 + OAuth 第三方登录
 *
 * 设计日期: 2026-03-22
 * 更新日期: 2026-04-22（阶段3：新增 GitHub/微信 OAuth 登录）
 *
 * 功能：
 * - 三 Tab 登录：短信验证码 / 手机号密码 / 邮箱密码
 * - OAuth 第三方登录：GitHub / 微信扫码
 * - 60 秒倒计时发送按钮
 * - Cookie 模式：登录成功后 Cookie 自动设置，无需手动管理 Token
 * - OAuth 回调错误提示（URL query 参数）
 */

"use client";

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { fetchAPI, BASE_URL } from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import { Phone, Mail, Lock, MessageSquare, Send, Loader2, Eye, EyeOff, ArrowRight, Github, QrCode } from 'lucide-react';

// ==========================================
// 类型定义
// ==========================================

type LoginTab = 'sms' | 'password' | 'email';

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    email: string;
    full_name: string | null;
    phone_number: string | null;
    is_superuser: boolean;
    is_email_verified: boolean;
    is_2fa_enabled: boolean;
  };
}

// ==========================================
// 登录页面组件
// ==========================================

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setUser } = useAuthStore();

  // Tab 状态
  const [activeTab, setActiveTab] = useState<LoginTab>('sms');

  // 短信登录表单
  const [smsPhone, setSmsPhone] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [smsSending, setSmsSending] = useState(false);
  const [countdown, setCountdown] = useState(0);

  // 手机号密码登录表单
  const [pwdPhone, setPwdPhone] = useState('');
  const [pwdPassword, setPwdPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // 邮箱登录表单
  const [email, setEmail] = useState('');
  const [emailPassword, setEmailPassword] = useState('');

  // 通用状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // OAuth 回调错误（从 URL 参数读取）
  useEffect(() => {
    const oauthError = searchParams.get('oauth_error');
    if (oauthError) {
      setError(decodeURIComponent(oauthError));
    }
  }, [searchParams]);

  // ==========================================
  // 倒计时逻辑
  // ==========================================

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  // ==========================================
  // 发送验证码
  // ==========================================

  const handleSendSMS = async () => {
    if (!/^1[3-9]\d{9}$/.test(smsPhone)) {
      setError('请输入正确的手机号码');
      return;
    }

    setSmsSending(true);
    setError('');

    try {
      await fetchAPI('/auth/send-sms', {
        method: 'POST',
        body: JSON.stringify({ phone_number: smsPhone }),
      });
      setCountdown(60);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '验证码发送失败');
    } finally {
      setSmsSending(false);
    }
  };

  // ==========================================
  // 短信验证码登录
  // ==========================================

  const handleSMSLogin = async () => {
    if (!/^1[3-9]\d{9}$/.test(smsPhone)) {
      setError('请输入正确的手机号码');
      return;
    }
    if (!/^\d{6}$/.test(otpCode)) {
      setError('请输入 6 位验证码');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const data = await fetchAPI('/auth/login/sms', {
        method: 'POST',
        body: JSON.stringify({ phone_number: smsPhone, otp_code: otpCode }),
      }) as LoginResponse;

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
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  // ==========================================
  // 手机号密码登录
  // ==========================================

  const handlePasswordLogin = async () => {
    if (!/^1[3-9]\d{9}$/.test(pwdPhone)) {
      setError('请输入正确的手机号码');
      return;
    }
    if (pwdPassword.length < 8) {
      setError('密码至少 8 位');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const data = await fetchAPI('/auth/login/password', {
        method: 'POST',
        body: JSON.stringify({ phone_number: pwdPhone, password: pwdPassword }),
      }) as LoginResponse;

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
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  // ==========================================
  // 邮箱密码登录（向后兼容）
  // ==========================================

  const handleEmailLogin = async () => {
    if (!email) {
      setError('请输入邮箱');
      return;
    }
    if (emailPassword.length < 8) {
      setError('密码至少 8 位');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', emailPassword);

      const data = await fetchAPI('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
      }) as { access_token: string; token_type: string };

      const { setToken } = useAuthStore.getState();
      setToken(data.access_token);

      const userInfo = await fetchAPI('/auth/me');
      setUser(userInfo);

      router.push('/');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  // ==========================================
  // GitHub OAuth 登录
  // ==========================================

  const handleGitHubLogin = async () => {
    setError('');
    try {
      // 获取 GitHub 授权 URL，直接跳转
      const data = await fetchAPI('/oauth/github/authorize-url');
      if (data.authorize_url) {
        window.location.href = data.authorize_url;
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'GitHub 登录初始化失败');
    }
  };

  // ==========================================
  // 微信扫码登录（预留）
  // ==========================================

  const handleWeChatLogin = async () => {
    setError('');
    try {
      const data = await fetchAPI('/oauth/wechat/qr-url');
      if (data.qr_url) {
        window.location.href = data.qr_url;
      } else {
        setError('微信登录暂未配置');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '微信登录初始化失败');
    }
  };

  // ==========================================
  // 渲染
  // ==========================================

  const tabs: { key: LoginTab; label: string; icon: React.ReactNode }[] = [
    { key: 'sms', label: '验证码登录', icon: <MessageSquare size={16} /> },
    { key: 'password', label: '密码登录', icon: <Lock size={16} /> },
    { key: 'email', label: '邮箱登录', icon: <Mail size={16} /> },
  ];

  return (
    <div className="min-h-screen bg-neutral-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo / 标题 */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Autonome</h1>
          <p className="text-neutral-400">AI-Native Bioinformatics IDE</p>
        </div>

        {/* Tab 切换 */}
        <div className="flex border-b border-neutral-800 mb-6">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => { setActiveTab(tab.key); setError(''); }}
              className={`flex-1 flex items-center justify-center gap-2 py-3 text-sm font-medium transition-colors border-b-2 ${
                activeTab === tab.key
                  ? 'text-blue-400 border-blue-400'
                  : 'text-neutral-500 border-transparent hover:text-neutral-300'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* 短信验证码登录 */}
        {activeTab === 'sms' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-neutral-300 mb-1.5">手机号码</label>
              <div className="relative">
                <Phone size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                <input
                  type="tel"
                  value={smsPhone}
                  onChange={(e) => setSmsPhone(e.target.value)}
                  placeholder="请输入手机号码"
                  className="w-full pl-10 pr-4 py-2.5 bg-neutral-900 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-neutral-300 mb-1.5">验证码</label>
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <MessageSquare size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                  <input
                    type="text"
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder="6 位验证码"
                    maxLength={6}
                    className="w-full pl-10 pr-4 py-2.5 bg-neutral-900 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                  />
                </div>
                <button
                  onClick={handleSendSMS}
                  disabled={smsSending || countdown > 0 || !smsPhone}
                  className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-neutral-700 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
                >
                  {smsSending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : countdown > 0 ? (
                    `${countdown}s`
                  ) : (
                    <span className="flex items-center gap-1"><Send size={14} /> 发送</span>
                  )}
                </button>
              </div>
            </div>

            <button
              onClick={handleSMSLogin}
              disabled={loading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <ArrowRight size={18} />}
              登录
            </button>
          </div>
        )}

        {/* 手机号密码登录 */}
        {activeTab === 'password' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-neutral-300 mb-1.5">手机号码</label>
              <div className="relative">
                <Phone size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                <input
                  type="tel"
                  value={pwdPhone}
                  onChange={(e) => setPwdPhone(e.target.value)}
                  placeholder="请输入手机号码"
                  className="w-full pl-10 pr-4 py-2.5 bg-neutral-900 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-neutral-300 mb-1.5">密码</label>
              <div className="relative">
                <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={pwdPassword}
                  onChange={(e) => setPwdPassword(e.target.value)}
                  placeholder="请输入密码"
                  className="w-full pl-10 pr-10 py-2.5 bg-neutral-900 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
                <button
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              onClick={handlePasswordLogin}
              disabled={loading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <ArrowRight size={18} />}
              登录
            </button>
          </div>
        )}

        {/* 邮箱密码登录（向后兼容）*/}
        {activeTab === 'email' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-neutral-300 mb-1.5">邮箱</label>
              <div className="relative">
                <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="请输入邮箱"
                  className="w-full pl-10 pr-4 py-2.5 bg-neutral-900 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-neutral-300 mb-1.5">密码</label>
              <div className="relative">
                <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={emailPassword}
                  onChange={(e) => setEmailPassword(e.target.value)}
                  placeholder="请输入密码"
                  onKeyDown={(e) => e.key === 'Enter' && handleEmailLogin()}
                  className="w-full pl-10 pr-10 py-2.5 bg-neutral-900 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
                <button
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              onClick={handleEmailLogin}
              disabled={loading}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <ArrowRight size={18} />}
              登录
            </button>
          </div>
        )}

        {/* ── OAuth 第三方登录 ── */}
        <div className="mt-6 pt-6 border-t border-neutral-800">
          <p className="text-center text-xs text-neutral-500 mb-4 uppercase tracking-wider">第三方登录</p>
          <div className="flex justify-center gap-4">
            {/* GitHub 登录 */}
            <button
              onClick={handleGitHubLogin}
              className="flex items-center gap-2 px-5 py-2.5 bg-neutral-900 border border-neutral-700 rounded-lg text-neutral-300 hover:text-white hover:border-neutral-500 transition-colors text-sm font-medium"
            >
              <Github size={18} />
              GitHub
            </button>

            {/* 微信登录（预留）*/}
            <button
              onClick={handleWeChatLogin}
              className="flex items-center gap-2 px-5 py-2.5 bg-neutral-900 border border-neutral-700 rounded-lg text-neutral-300 hover:text-white hover:border-neutral-500 transition-colors text-sm font-medium"
            >
              <QrCode size={18} />
              微信
            </button>
          </div>
        </div>

        {/* 底部提示 */}
        <p className="mt-6 text-center text-xs text-neutral-600">
          登录即表示同意服务条款和隐私政策
        </p>
      </div>
    </div>
  );
}
