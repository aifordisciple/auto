/**
 * 安全设置面板组件
 *
 * 设计日期: 2026-03-23
 * 更新日期: 2026-04-22（阶段3：新增 OAuth 账号绑定/解绑管理）
 *
 * 功能：
 * - 修改密码（原密码验证 + 新密码强度验证）
 * - 双因素认证 (2FA) UI 占位（即将推出）
 * - OAuth 第三方账号绑定/解绑（GitHub / 微信）
 * - 显示上次密码修改时间
 */

"use client";

import { useState, useEffect } from 'react';
import { fetchAPI } from '@/lib/api';
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

  // 2FA 状态（MVP 占位）
  const [twoFAEnabled, setTwoFAEnabled] = useState(false);

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

  // 加载 OAuth 账号列表
  useEffect(() => {
    (async () => {
      try {
        const data = await fetchAPI('/oauth/accounts');
        setOauthAccounts(data.accounts || []);
      } catch {
        // 未登录或接口不可用，静默处理
      }
    })();
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
      await fetchAPI('/users/me/password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: passwordForm.current_password,
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
    } catch (error: any) {
      setPasswordMessage({ type: 'error', text: error.message || '密码修改失败' });
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

          <div className="flex items-start justify-between gap-6">
            <div className="flex-1">
              <p className="text-neutral-300 mb-2">
                为您的账号添加额外的安全保护层
              </p>
              <p className="text-sm text-neutral-500">
                启用后，登录时除了密码外，还需要输入手机验证码或验证器应用生成的动态码。
              </p>
            </div>

            {/* 开关占位 */}
            <div className="flex-shrink-0">
              <button
                disabled
                className="relative inline-flex h-7 w-12 items-center rounded-full bg-neutral-700 transition-colors cursor-not-allowed opacity-50"
              >
                <span className="inline-block h-5 w-5 transform rounded-full bg-neutral-400 translate-x-1 transition-transform" />
              </button>
            </div>
          </div>

          {/* 即将推出提示 */}
          <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg flex items-center gap-2">
            <Smartphone size={16} className="text-blue-400" />
            <span className="text-sm text-blue-400">此功能即将推出，敬请期待</span>
          </div>
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