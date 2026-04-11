/**
 * 安全设置面板组件
 *
 * 设计日期: 2026-03-23
 *
 * 功能：
 * - 修改密码（原密码验证 + 新密码强度验证）
 * - 双因素认证 (2FA) UI 占位（即将推出）
 * - 显示上次密码修改时间
 */

"use client";

import React, { useState } from 'react';
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
  Smartphone
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