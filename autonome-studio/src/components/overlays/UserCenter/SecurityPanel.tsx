/**
 * 安全设置面板组件
 *
 * 设计日期: 2026-03-23
 * 更新日期: 2026-04-23（阶段3：2FA/TOTP 完整UI + 修改密码对接 + 修改手机号）
 *
 * 功能：
 * - 修改密码（原密码验证 + 新密码强度验证）
 * - 双因素认证 (2FA) 完整设置/验证/禁用流程
 * - OAuth 第三方账号绑定/解绑（GitHub / 微信）
 * - 显示上次密码修改时间
 */

"use client";

import { useState, useEffect } from 'react';
import QRCode from 'react-qr-code';
import { fetchAPI } from '@/lib/api';
import { useAuthStore } from '@/store/useAuthStore';
import {
  Lock,
  Shield,
  Key,
  Eye,
  EyeOff,
  AlertCircle,
  CheckCircle,
  Loader2,
  Clock,
  Smartphone,
  Github,
  Link2,
  Unlink,
  Mail,
  Send,
  Monitor,
  Trash2,
} from 'lucide-react';

// ==========================================
// 类型定义
// ==========================================

interface PasswordForm {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

interface PasswordStrength {
  score: number; // 0-4
  label: string;
  color: string;
}

// ==========================================
// 密码强度计算函数
// ==========================================

function calculatePasswordStrength(password: string): PasswordStrength {
  let score = 0;

  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) score++;

  const labels = ['极弱', '弱', '一般', '强', '极强'];
  const colors = ['bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-green-500', 'bg-emerald-500'];

  return {
    score: Math.min(score, 4),
    label: labels[Math.min(score, 4)],
    color: colors[Math.min(score, 4)]
  };
}

// ==========================================
// 安全设置面板组件
// ==========================================

export function SecurityPanel() {
  const { user, fetchProfile } = useAuthStore();
  // 密码修改状态
  const [passwordForm, setPasswordForm] = useState<PasswordForm>({
    current_password: '',
    new_password: '',
    confirm_password: ''
  });
  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false
  });
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 2FA 状态
  const [twoFAEnabled, setTwoFAEnabled] = useState(user?.is_2fa_enabled ?? false);
  // 2FA 设置流程状态
  const [twoFASetupStep, setTwoFASetupStep] = useState<'idle' | 'setup' | 'verify' | 'recovery'>('idle');
  const [twoFASecret, setTwoFASecret] = useState('');
  const [twoFAQRUri, setTwoFAQRUri] = useState('');
  const [twoFAVerifyCode, setTwoFAVerifyCode] = useState('');
  const [twoFARecoveryCodes, setTwoFARecoveryCodes] = useState<string[]>([]);
  const [twoFALoading, setTwoFALoading] = useState(false);
  const [twoFAMessage, setTwoFAMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  // 2FA 禁用流程状态
  const [twoFADisableCode, setTwoFADisableCode] = useState('');
  const [twoFADisableLoading, setTwoFADisableLoading] = useState(false);

  // 上次密码修改时间（模拟数据，实际应从后端获取）
  const [lastPasswordChange] = useState<string | null>(null);

  // ── OAuth 账号管理状态 ──
  const [oauthAccounts, setOauthAccounts] = useState<Array<{
    provider: string;
    provider_name: string;
    provider_avatar_url: string;
    created_at: string | null;
  }>>([]);
  const [oauthError, setOauthError] = useState('');
  const [unbindLoading, setUnbindLoading] = useState<string | null>(null);

  // ── 安全邮箱绑定状态 ──
  const [bindEmail, setBindEmail] = useState('');
  const [bindEmailPassword, setBindEmailPassword] = useState('');
  const [bindEmailLoading, setBindEmailLoading] = useState(false);
  const [bindEmailMessage, setBindEmailMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  // 邮箱验证中状态（发送验证邮件后等待用户点击链接）
  const [emailVerifying, setEmailVerifying] = useState(false);

  // ── 设备管理状态 ──
  const [sessions, setSessions] = useState<Array<{
    session_id: number;
    user_agent: string | null;
    ip_address: string | null;
    device_type: string | null;
    created_at: string;
    last_active_at: string;
    is_current: boolean;
  }>>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [revokeLoading, setRevokeLoading] = useState<number | null>(null);

  // 加载 OAuth 账号列表 + 设备会话列表
  useEffect(() => {
    (async () => {
      try {
        const data = await fetchAPI('/oauth/accounts');
        setOauthAccounts(data.accounts || []);
      } catch {
        // 未登录或接口不可用，静默处理
      }
    })();
    loadSessions();
  }, []);

  // 绑定 GitHub OAuth
  const handleBindGithub = async () => {
    setOauthError('');
    try {
      const data = await fetchAPI('/oauth/github/authorize-url');
      if (data.authorize_url) {
        window.location.href = data.authorize_url;
      }
    } catch (err: unknown) {
      setOauthError(err instanceof Error ? err.message : 'GitHub 绑定失败');
    }
  };

  // 绑定微信 OAuth
  const handleBindWechat = async () => {
    setOauthError('');
    try {
      const data = await fetchAPI('/oauth/wechat/qr-url');
      if (data.qr_url) {
        window.location.href = data.qr_url;
      } else {
        setOauthError('微信登录暂未配置');
      }
    } catch (err: unknown) {
      setOauthError(err instanceof Error ? err.message : '微信绑定失败');
    }
  };

  // 解绑 OAuth 账号
  const handleUnbind = async (provider: string) => {
    setOauthError('');
    setUnbindLoading(provider);
    try {
      const data = await fetchAPI('/oauth/unbind', {
        method: 'POST',
        body: JSON.stringify({ provider }),
      });
      if (data.success) {
        // 刷新列表
        const refreshed = await fetchAPI('/oauth/accounts');
        setOauthAccounts(refreshed.accounts || []);
      } else {
        setOauthError(data.message || '解绑失败');
      }
    } catch (err: unknown) {
      setOauthError(err instanceof Error ? err.message : '解绑失败');
    } finally {
      setUnbindLoading(null);
    }
  };

  // 检查是否已绑定某 OAuth
  const isBound = (provider: string) => oauthAccounts.some(a => a.provider === provider);

  // ── 2FA 设置流程 ──
  const handle2FASetup = async () => {
    setTwoFALoading(true);
    setTwoFAMessage(null);
    try {
      const data = await fetchAPI('/auth/2fa/setup', { method: 'POST' });
      setTwoFASecret(data.secret);
      setTwoFAQRUri(data.qr_uri);
      setTwoFASetupStep('setup');
    } catch (err: unknown) {
      setTwoFAMessage({ type: 'error', text: err instanceof Error ? err.message : '2FA 设置失败' });
    } finally {
      setTwoFALoading(false);
    }
  };

  const handle2FAVerify = async () => {
    if (!twoFAVerifyCode || twoFAVerifyCode.length !== 6) {
      setTwoFAMessage({ type: 'error', text: '请输入 6 位验证码' });
      return;
    }
    setTwoFALoading(true);
    setTwoFAMessage(null);
    try {
      const data = await fetchAPI('/auth/2fa/verify', {
        method: 'POST',
        body: JSON.stringify({ secret: twoFASecret, totp_code: twoFAVerifyCode }),
      });
      if (data.recovery_codes) {
        setTwoFARecoveryCodes(data.recovery_codes);
        setTwoFASetupStep('recovery');
        setTwoFAEnabled(true);
        await fetchProfile(); // 刷新用户信息
      }
    } catch (err: unknown) {
      setTwoFAMessage({ type: 'error', text: err instanceof Error ? err.message : '验证码错误' });
    } finally {
      setTwoFALoading(false);
    }
  };

  const handle2FADisable = async () => {
    if (!twoFADisableCode || twoFADisableCode.length !== 6) {
      setTwoFAMessage({ type: 'error', text: '请输入 6 位验证码以确认禁用' });
      return;
    }
    setTwoFADisableLoading(true);
    setTwoFAMessage(null);
    try {
      await fetchAPI('/auth/2fa/disable', {
        method: 'POST',
        body: JSON.stringify({ totp_code: twoFADisableCode }),
      });
      setTwoFAEnabled(false);
      setTwoFADisableCode('');
      setTwoFASetupStep('idle');
      setTwoFAMessage({ type: 'success', text: '2FA 已禁用' });
      await fetchProfile(); // 刷新用户信息
    } catch (err: unknown) {
      setTwoFAMessage({ type: 'error', text: err instanceof Error ? err.message : '验证码错误，无法禁用 2FA' });
    } finally {
      setTwoFADisableLoading(false);
    }
  };

  // ── 安全邮箱绑定 ──
  const handleBindEmail = async () => {
    if (!bindEmail) {
      setBindEmailMessage({ type: 'error', text: '请输入邮箱地址' });
      return;
    }
    // 简单邮箱格式校验
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(bindEmail)) {
      setBindEmailMessage({ type: 'error', text: '请输入合法的邮箱地址' });
      return;
    }
    if (!bindEmailPassword) {
      setBindEmailMessage({ type: 'error', text: '请输入当前密码以验证身份' });
      return;
    }

    setBindEmailLoading(true);
    setBindEmailMessage(null);

    try {
      await fetchAPI('/auth/bind-email', {
        method: 'POST',
        body: JSON.stringify({
          email: bindEmail,
          current_password: bindEmailPassword,
        }),
      });
      setBindEmailMessage({ type: 'success', text: '验证邮件已发送，请查收邮箱并点击验证链接' });
      setEmailVerifying(true);
      setBindEmailPassword('');
    } catch (err: unknown) {
      setBindEmailMessage({ type: 'error', text: err instanceof Error ? err.message : '绑定邮箱失败' });
    } finally {
      setBindEmailLoading(false);
    }
  };

  // ── 设备管理：加载会话列表 ──
  const loadSessions = async () => {
    setSessionsLoading(true);
    try {
      const data = await fetchAPI('/auth/sessions');
      setSessions(Array.isArray(data) ? data : []);
    } catch {
      // 静默失败
    } finally {
      setSessionsLoading(false);
    }
  };

  // ── 设备管理：撤销指定会话 ──
  const handleRevokeSession = async (sessionId: number) => {
    setRevokeLoading(sessionId);
    try {
      await fetchAPI(`/auth/sessions/${sessionId}/revoke`, { method: 'POST' });
      // 从列表中移除已撤销的会话
      setSessions(prev => prev.filter(s => s.session_id !== sessionId));
    } catch {
      // 静默失败
    } finally {
      setRevokeLoading(null);
    }
  };

  // 表单字段变更
  const handlePasswordChange = (field: keyof PasswordForm, value: string) => {
    setPasswordForm(prev => ({ ...prev, [field]: value }));
    setPasswordMessage(null);
  };

  // 切换密码可见性
  const togglePasswordVisibility = (field: 'current' | 'new' | 'confirm') => {
    setShowPasswords(prev => ({ ...prev, [field]: !prev[field] }));
  };

  // 密码强度
  const passwordStrength = calculatePasswordStrength(passwordForm.new_password);

  // 验证表单
  const validateForm = (): string | null => {
    if (!passwordForm.current_password) {
      return '请输入原密码';
    }
    if (!passwordForm.new_password) {
      return '请输入新密码';
    }
    if (passwordForm.new_password.length < 8) {
      return '密码长度至少 8 位';
    }
    if (!/[a-zA-Z]/.test(passwordForm.new_password) || !/\d/.test(passwordForm.new_password)) {
      return '密码需包含字母和数字';
    }
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      return '两次输入的新密码不一致';
    }
    return null;
  };

  // 提交密码修改
  const handleSubmitPassword = async () => {
    const validationError = validateForm();
    if (validationError) {
      setPasswordMessage({ type: 'error', text: validationError });
      return;
    }

    setChangingPassword(true);
    setPasswordMessage(null);

    try {
      await fetchAPI('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({
          old_password: passwordForm.current_password,
          new_password: passwordForm.new_password
        })
      });

      setPasswordMessage({ type: 'success', text: '密码修改成功' });
      // 清空表单
      setPasswordForm({
        current_password: '',
        new_password: '',
        confirm_password: ''
      });
    } catch (err: unknown) {
      setPasswordMessage({ type: 'error', text: err instanceof Error ? err.message : '密码修改失败' });
    } finally {
      setChangingPassword(false);
    }
  };

  // 格式化日期
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* 卡片一：修改密码 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
            <Key size={20} className="text-yellow-400" />
            修改密码
          </h2>

          {/* 上次修改时间 */}
          {lastPasswordChange && (
            <div className="mb-4 flex items-center gap-2 text-sm text-neutral-400">
              <Clock size={14} />
              上次修改时间：{formatDate(lastPasswordChange)}
            </div>
          )}

          <div className="space-y-4">
            {/* 原密码 */}
            <div className="space-y-2">
              <label className="text-sm text-neutral-300">原密码</label>
              <div className="relative">
                <input
                  type={showPasswords.current ? 'text' : 'password'}
                  value={passwordForm.current_password}
                  onChange={(e) => handlePasswordChange('current_password', e.target.value)}
                  placeholder="输入当前密码"
                  className="w-full px-4 py-2.5 pr-10 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => togglePasswordVisibility('current')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-white transition-colors"
                >
                  {showPasswords.current ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* 新密码 */}
            <div className="space-y-2">
              <label className="text-sm text-neutral-300">新密码</label>
              <div className="relative">
                <input
                  type={showPasswords.new ? 'text' : 'password'}
                  value={passwordForm.new_password}
                  onChange={(e) => handlePasswordChange('new_password', e.target.value)}
                  placeholder="输入新密码"
                  className="w-full px-4 py-2.5 pr-10 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => togglePasswordVisibility('new')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-white transition-colors"
                >
                  {showPasswords.new ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>

              {/* 密码强度指示器 */}
              {passwordForm.new_password && (
                <div className="space-y-1">
                  <div className="flex gap-1">
                    {[0, 1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className={`h-1 flex-1 rounded-full transition-colors ${
                          i <= passwordStrength.score ? passwordStrength.color : 'bg-neutral-700'
                        }`}
                      />
                    ))}
                  </div>
                  <p className={`text-xs ${
                    passwordStrength.score >= 3 ? 'text-green-400' : 'text-yellow-400'
                  }`}>
                    密码强度：{passwordStrength.label}
                  </p>
                </div>
              )}

              {/* 密码要求提示 */}
              <div className="text-xs text-neutral-500 space-y-1">
                <p>• 至少 8 个字符</p>
                <p>• 包含字母和数字</p>
                <p>• 建议包含大小写字母和特殊字符</p>
              </div>
            </div>

            {/* 确认新密码 */}
            <div className="space-y-2">
              <label className="text-sm text-neutral-300">确认新密码</label>
              <div className="relative">
                <input
                  type={showPasswords.confirm ? 'text' : 'password'}
                  value={passwordForm.confirm_password}
                  onChange={(e) => handlePasswordChange('confirm_password', e.target.value)}
                  placeholder="再次输入新密码"
                  className="w-full px-4 py-2.5 pr-10 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => togglePasswordVisibility('confirm')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-white transition-colors"
                >
                  {showPasswords.confirm ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {/* 密码匹配提示 */}
              {passwordForm.confirm_password && (
                <p className={`text-xs ${
                  passwordForm.new_password === passwordForm.confirm_password
                    ? 'text-green-400'
                    : 'text-red-400'
                }`}>
                  {passwordForm.new_password === passwordForm.confirm_password
                    ? '✓ 密码一致'
                    : '✗ 密码不一致'}
                </p>
              )}
            </div>
          </div>

          {/* 操作按钮和消息 */}
          <div className="mt-6 flex items-center justify-between">
            {/* 状态消息 */}
            {passwordMessage && (
              <div className={`flex items-center gap-2 text-sm ${
                passwordMessage.type === 'success' ? 'text-green-400' : 'text-red-400'
              }`}>
                {passwordMessage.type === 'success' ? (
                  <CheckCircle size={16} />
                ) : (
                  <AlertCircle size={16} />
                )}
                {passwordMessage.text}
              </div>
            )}
            <div className="flex-1" />
            {/* 提交按钮 */}
            <button
              onClick={handleSubmitPassword}
              disabled={changingPassword}
              className="flex items-center gap-2 px-6 py-2.5 bg-yellow-600 hover:bg-yellow-700 disabled:bg-yellow-600/50 text-white rounded-lg font-medium transition-colors"
            >
              {changingPassword ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  修改中...
                </>
              ) : (
                <>
                  <Lock size={16} />
                  确认修改
                </>
              )}
            </button>
          </div>
        </div>

        {/* 卡片二：双因素认证 (2FA) */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
            <Shield size={20} className="text-purple-400" />
            双因素认证 (2FA)
          </h2>

          {/* 2FA 消息提示 */}
          {twoFAMessage && (
            <div className={`mb-4 p-3 rounded-lg text-sm flex items-center gap-2 ${
              twoFAMessage.type === 'success'
                ? 'bg-green-500/10 border border-green-500/20 text-green-400'
                : 'bg-red-500/10 border border-red-500/20 text-red-400'
            }`}>
              {twoFAMessage.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
              {twoFAMessage.text}
            </div>
          )}

          {/* 2FA 未启用 — idle 状态 */}
          {!twoFAEnabled && twoFASetupStep === 'idle' && (
            <div>
              <div className="flex items-start justify-between gap-6">
                <div className="flex-1">
                  <p className="text-neutral-300 mb-2">
                    为您的账号添加额外的安全保护层
                  </p>
                  <p className="text-sm text-neutral-500">
                    启用后，登录时除了密码外，还需要输入验证器应用生成的 6 位动态码。
                  </p>
                </div>
              </div>
              <button
                onClick={handle2FASetup}
                disabled={twoFALoading}
                className="mt-4 flex items-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white rounded-lg font-medium transition-colors text-sm"
              >
                {twoFALoading ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
                启用 2FA
              </button>
            </div>
          )}

          {/* 2FA 设置步骤1：显示 QR 码 */}
          {twoFASetupStep === 'setup' && (
            <div className="space-y-4">
              <p className="text-sm text-neutral-400">
                请使用验证器应用（如 Google Authenticator、Microsoft Authenticator）扫描下方二维码
              </p>
              {/* QR 码（使用外部 API 渲染） */}
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(twoFAQRUri)}`}
                  alt="2FA QR Code"
                  width={200}
                  height={200}
                />
              </div>
              {/* 手动输入密钥 */}
              <div className="p-3 bg-neutral-800/50 rounded-lg">
                <p className="text-xs text-neutral-500 mb-1">无法扫描？手动输入密钥：</p>
                <p className="text-sm text-neutral-200 font-mono select-all break-all">{twoFASecret}</p>
              </div>
              <button
                onClick={() => setTwoFASetupStep('verify')}
                className="flex items-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors text-sm"
              >
                下一步：验证
              </button>
            </div>
          )}

          {/* 2FA 设置步骤2：验证 TOTP 码 */}
          {twoFASetupStep === 'verify' && (
            <div className="space-y-4">
              <p className="text-sm text-neutral-400">
                请输入验证器应用中显示的 6 位验证码以完成设置
              </p>
              <input
                type="text"
                inputMode="numeric"
                value={twoFAVerifyCode}
                onChange={(e) => setTwoFAVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="6 位验证码"
                maxLength={6}
                className="w-full px-4 py-3 bg-neutral-800 border border-neutral-700 rounded-lg text-white text-center text-2xl tracking-[0.5em] placeholder-neutral-500 focus:outline-none focus:border-purple-500 transition-colors"
              />
              <div className="flex gap-3">
                <button
                  onClick={() => { setTwoFASetupStep('setup'); setTwoFAMessage(null); }}
                  className="flex-1 py-2.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 rounded-lg text-sm font-medium transition-colors"
                >
                  返回
                </button>
                <button
                  onClick={handle2FAVerify}
                  disabled={twoFALoading || twoFAVerifyCode.length !== 6}
                  className="flex-1 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
                >
                  {twoFALoading ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
                  验证并启用
                </button>
              </div>
            </div>
          )}

          {/* 2FA 设置步骤3：显示恢复码 */}
          {twoFASetupStep === 'recovery' && (
            <div className="space-y-4">
              <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg flex items-start gap-2">
                <AlertCircle size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-amber-400">
                  <p className="font-medium">请妥善保存以下恢复码</p>
                  <p className="text-amber-400/80 mt-1">如果丢失验证器，可使用恢复码登录。每个恢复码只能使用一次。</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 p-4 bg-neutral-800/50 rounded-lg">
                {twoFARecoveryCodes.map((code, i) => (
                  <p key={i} className="text-sm font-mono text-neutral-200 select-all">{code}</p>
                ))}
              </div>
              <button
                onClick={() => { setTwoFASetupStep('idle'); setTwoFAMessage(null); }}
                className="w-full py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors text-sm"
              >
                我已保存恢复码，完成设置
              </button>
            </div>
          )}

          {/* 2FA 已启用 — 显示禁用选项 */}
          {twoFAEnabled && twoFASetupStep === 'idle' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <CheckCircle size={16} className="text-green-400" />
                <span className="text-sm text-green-400 font-medium">2FA 已启用</span>
              </div>
              <p className="text-sm text-neutral-400">
                如需禁用 2FA，请输入验证器中的 6 位验证码确认
              </p>
              <div className="flex gap-3">
                <input
                  type="text"
                  inputMode="numeric"
                  value={twoFADisableCode}
                  onChange={(e) => setTwoFADisableCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="6 位验证码"
                  maxLength={6}
                  className="flex-1 px-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-white text-center tracking-[0.3em] placeholder-neutral-500 focus:outline-none focus:border-red-500 transition-colors"
                />
                <button
                  onClick={handle2FADisable}
                  disabled={twoFADisableLoading || twoFADisableCode.length !== 6}
                  className="flex items-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 disabled:bg-red-600/50 text-white rounded-lg font-medium transition-colors text-sm"
                >
                  {twoFADisableLoading ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
                  禁用 2FA
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 卡片三：OAuth 第三方账号绑定 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
            <Link2 size={20} className="text-blue-400" />
            第三方账号绑定
          </h2>

          <p className="text-sm text-neutral-400 mb-4">
            绑定第三方账号可快速登录，且不影响原有登录方式
          </p>

          {oauthError && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              {oauthError}
            </div>
          )}

          <div className="space-y-3">
            {/* GitHub */}
            <div className="flex items-center justify-between p-3 bg-neutral-800/50 rounded-lg">
              <div className="flex items-center gap-3">
                <Github size={20} className="text-white" />
                <div>
                  <p className="text-sm font-medium text-neutral-200">GitHub</p>
                  {isBound('github') && (
                    <p className="text-xs text-neutral-500">
                      已绑定{oauthAccounts.find(a => a.provider === 'github')?.provider_name ? `：${oauthAccounts.find(a => a.provider === 'github')?.provider_name}` : ''}
                    </p>
                  )}
                </div>
              </div>
              {isBound('github') ? (
                <button
                  onClick={() => handleUnbind('github')}
                  disabled={unbindLoading === 'github'}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 border border-red-500/30 rounded-lg transition-colors disabled:opacity-50"
                >
                  {unbindLoading === 'github' ? <Loader2 size={12} className="animate-spin" /> : <Unlink size={12} />}
                  解绑
                </button>
              ) : (
                <button
                  onClick={handleBindGithub}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-blue-400 hover:text-blue-300 border border-blue-500/30 rounded-lg transition-colors"
                >
                  <Link2 size={12} />
                  绑定
                </button>
              )}
            </div>

            {/* 微信 */}
            <div className="flex items-center justify-between p-3 bg-neutral-800/50 rounded-lg">
              <div className="flex items-center gap-3">
                <svg viewBox="0 0 24 24" className="w-5 h-5 text-green-400" fill="currentColor">
                  <path d="M8.691 2.619C4.891 2.619 1.8 5.56 1.8 9.119c0 1.95.98 3.69 2.52 4.83l-.64 2.28 2.64-1.34c.76.24 1.56.37 2.37.37.28 0 .56-.02.83-.05-.17-.56-.26-1.15-.26-1.76 0-3.41 3.09-6.18 6.91-6.18.43 0 .85.04 1.26.11C16.92 4.87 13.08 2.62 8.69 2.62zm-2.52 4.24a.99.99 0 1 1 0 1.98.99.99 0 0 1 0-1.98zm5.04 0a.99.99 0 1 1 0 1.98.99.99 0 0 1 0-1.98zM15.57 8.2c-3.27 0-5.93 2.41-5.93 5.38 0 2.97 2.66 5.38 5.93 5.38.68 0 1.34-.11 1.96-.31l2.08 1.06-.5-1.79c1.22-.97 2-2.41 2-4.04 0-2.97-2.66-5.38-5.93-5.38h-.61zm-2.52 3.04a.84.84 0 1 1 0 1.68.84.84 0 0 1 0-1.68zm4.56 0a.84.84 0 1 1 0 1.68.84.84 0 0 1 0-1.68z"/>
                </svg>
                <div>
                  <p className="text-sm font-medium text-neutral-200">微信</p>
                  {isBound('wechat') && (
                    <p className="text-xs text-neutral-500">
                      已绑定{oauthAccounts.find(a => a.provider === 'wechat')?.provider_name ? `：${oauthAccounts.find(a => a.provider === 'wechat')?.provider_name}` : ''}
                    </p>
                  )}
                </div>
              </div>
              {isBound('wechat') ? (
                <button
                  onClick={() => handleUnbind('wechat')}
                  disabled={unbindLoading === 'wechat'}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 border border-red-500/30 rounded-lg transition-colors disabled:opacity-50"
                >
                  {unbindLoading === 'wechat' ? <Loader2 size={12} className="animate-spin" /> : <Unlink size={12} />}
                  解绑
                </button>
              ) : (
                <button
                  onClick={handleBindWechat}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-blue-400 hover:text-blue-300 border border-blue-500/30 rounded-lg transition-colors"
                >
                  <Link2 size={12} />
                  绑定
                </button>
              )}
            </div>
          </div>
        </div>

        {/* 卡片四：安全邮箱绑定 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
            <Mail size={20} className="text-emerald-400" />
            安全邮箱
          </h2>

          {/* 当前邮箱状态 */}
          {user?.email && (
            <div className="mb-4 flex items-center gap-2 text-sm">
              <span className="text-neutral-400">当前邮箱：</span>
              <span className="text-neutral-200">{user.email}</span>
              {user.is_email_verified ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-500/10 text-green-400 text-xs rounded-full">
                  <CheckCircle size={12} /> 已验证
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-yellow-500/10 text-yellow-400 text-xs rounded-full">
                  <AlertCircle size={12} /> 未验证
                </span>
              )}
            </div>
          )}

          {/* 邮箱验证中提示 */}
          {emailVerifying && (
            <div className="mb-4 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg flex items-center gap-2">
              <Send size={16} className="text-blue-400" />
              <span className="text-sm text-blue-400">验证邮件已发送，请查收邮箱并点击验证链接完成绑定</span>
            </div>
          )}

          {/* 提示消息 */}
          {bindEmailMessage && (
            <div className={`mb-4 p-3 rounded-lg text-sm flex items-center gap-2 ${
              bindEmailMessage.type === 'success'
                ? 'bg-green-500/10 border border-green-500/20 text-green-400'
                : 'bg-red-500/10 border border-red-500/20 text-red-400'
            }`}>
              {bindEmailMessage.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
              {bindEmailMessage.text}
            </div>
          )}

          <p className="text-sm text-neutral-400 mb-4">
            {user?.email
              ? '更换邮箱需要验证当前密码，并通过新邮箱的验证链接确认'
              : '绑定邮箱可用于找回密码和接收安全通知'}
          </p>

          <div className="space-y-3">
            {/* 邮箱输入 */}
            <div className="relative">
              <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-500" />
              <input
                type="email"
                placeholder="请输入邮箱地址"
                className="w-full pl-10 pr-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors text-sm"
                value={bindEmail}
                onChange={e => { setBindEmail(e.target.value); setBindEmailMessage(null); setEmailVerifying(false); }}
              />
            </div>

            {/* 当前密码验证 */}
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-500" />
              <input
                type="password"
                placeholder="输入当前密码以验证身份"
                className="w-full pl-10 pr-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors text-sm"
                value={bindEmailPassword}
                onChange={e => { setBindEmailPassword(e.target.value); setBindEmailMessage(null); }}
              />
            </div>

            <button
              onClick={handleBindEmail}
              disabled={bindEmailLoading || !bindEmail || !bindEmailPassword}
              className="flex items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-600/50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors text-sm"
            >
              {bindEmailLoading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              {user?.email ? '更换邮箱' : '绑定邮箱'}
            </button>
          </div>
        </div>

        {/* 卡片五：设备管理 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Monitor size={20} className="text-cyan-400" />
            在线设备
          </h2>

          <p className="text-sm text-neutral-400 mb-4">
            管理已登录的设备，可撤销可疑设备的登录状态
          </p>

          {sessionsLoading ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 size={20} className="animate-spin text-neutral-500" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-sm text-neutral-500 text-center py-4">
              暂无在线设备
            </div>
          ) : (
            <div className="space-y-2">
              {sessions.map(s => {
                // 解析 user_agent 获取设备信息
                const ua = s.user_agent || '';
                const isMobile = /Mobile|Android|iPhone/i.test(ua);
                const isMac = /Mac/i.test(ua);
                const isWindows = /Windows/i.test(ua);
                const isLinux = /Linux/i.test(ua);
                const browserMatch = ua.match(/(Chrome|Firefox|Safari|Edge)\/[\d.]+/);
                const browser = browserMatch ? browserMatch[1] : '未知浏览器';
                const os = isMobile ? '移动端' : isMac ? 'macOS' : isWindows ? 'Windows' : isLinux ? 'Linux' : '未知系统';

                return (
                  <div key={s.session_id} className="flex items-center justify-between p-3 bg-neutral-800/50 rounded-lg">
                    <div className="flex items-center gap-3 min-w-0">
                      <Monitor size={18} className="text-neutral-400 flex-shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-neutral-200 truncate">
                          {os} · {browser}
                          {s.is_current && (
                            <span className="ml-2 inline-flex items-center px-1.5 py-0.5 bg-blue-500/10 text-blue-400 text-xs rounded-full">
                              当前设备
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-neutral-500">
                          {s.ip_address || '未知IP'} · {formatDate(s.last_active_at)}
                        </p>
                      </div>
                    </div>
                    {s.is_current ? (
                      <span className="text-xs text-neutral-600 flex-shrink-0">当前设备</span>
                    ) : (
                      <button
                        onClick={() => handleRevokeSession(s.session_id)}
                        disabled={revokeLoading === s.session_id}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-red-400 hover:text-red-300 border border-red-500/30 rounded-lg transition-colors disabled:opacity-50 flex-shrink-0"
                      >
                        {revokeLoading === s.session_id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                        下线
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {!sessionsLoading && sessions.length > 0 && (
            <div className="mt-3 text-right">
              <button
                onClick={loadSessions}
                className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                刷新列表
              </button>
            </div>
          )}
        </div>

        {/* 安全提示 */}
        <div className="bg-neutral-900/30 border border-neutral-800 rounded-xl p-4">
          <h3 className="text-sm font-medium text-neutral-300 mb-2 flex items-center gap-2">
            <AlertCircle size={14} className="text-amber-400" />
            安全提示
          </h3>
          <ul className="text-xs text-neutral-500 space-y-1 list-disc list-inside">
            <li>请勿使用与其他网站相同的密码</li>
            <li>建议定期更换密码以保护账号安全</li>
            <li>如发现账号异常，请立即修改密码并联系管理员</li>
          </ul>
        </div>

      </div>
    </div>
  );
}