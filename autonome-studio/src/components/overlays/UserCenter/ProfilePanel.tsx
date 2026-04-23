/**
 * 个人资料面板组件
 *
 * 设计日期: 2026-03-23
 *
 * 功能：
 * - 展示和编辑用户基础信息（昵称、组织、手机、简介）
 * - 支持头像显示（优先自定义头像，fallback 到 Gravatar）
 * - 显示用户角色和注册时间
 */

"use client";

import { useState, useEffect } from 'react';
import { useAuthStore } from '@/store/useAuthStore';
import { fetchAPI } from '@/lib/api';
import { User, Building2, Phone, FileText, Save, Loader2, CheckCircle, AlertCircle, X, Send } from 'lucide-react';

// ==========================================
// 类型定义
// ==========================================

interface UserProfile {
  id: number;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  organization: string | null;
  phone_number: string | null;
  bio: string | null;
  is_superuser: boolean;
  created_at: string;
  updated_at: string;
  role: string;
  gravatar_url: string;
}

// ==========================================
// 个人资料面板组件
// ==========================================

export function ProfilePanel() {
  const { user } = useAuthStore();

  // 状态管理
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // 修改手机号模态框状态
  const [showChangePhone, setShowChangePhone] = useState(false);
  const [newPhone, setNewPhone] = useState('');
  const [changePhoneOTP, setChangePhoneOTP] = useState('');
  const [changePhonePassword, setChangePhonePassword] = useState('');
  const [changePhoneCountdown, setChangePhoneCountdown] = useState(0);
  const [changePhoneLoading, setChangePhoneLoading] = useState(false);
  const [changePhoneError, setChangePhoneError] = useState('');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // 表单字段
  const [formData, setFormData] = useState({
    full_name: '',
    organization: '',
    phone_number: '',
    bio: ''
  });

  // 加载用户资料
  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const data = await fetchAPI('/users/me');
      setProfile(data);
      setFormData({
        full_name: data.full_name || '',
        organization: data.organization || '',
        phone_number: data.phone_number || '',
        bio: data.bio || ''
      });
    } catch (error) {
      console.error('加载用户资料失败:', error);
      setMessage({ type: 'error', text: '加载用户资料失败' });
    } finally {
      setLoading(false);
    }
  };

  // 表单字段变更
  const handleChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setMessage(null);
  };

  // 保存资料
  const handleSave = async () => {
    setSaving(true);
    setMessage(null);

    try {
      await fetchAPI('/users/me', {
        method: 'PUT',
        body: JSON.stringify(formData)
      });
      setMessage({ type: 'success', text: '资料更新成功' });
      // 刷新本地状态
      if (profile) {
        setProfile({ ...profile, ...formData });
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || '保存失败' });
    } finally {
      setSaving(false);
    }
  };

  // ==========================================
  // 修改手机号流程
  // ==========================================

  /** 发送修改手机号的 SMS 验证码 */
  const handleChangePhoneSendSMS = async () => {
    if (!/^1[3-9]\d{9}$/.test(newPhone)) {
      setChangePhoneError('请输入有效的手机号');
      return;
    }
    try {
      await fetchAPI('/auth/send-sms', {
        method: 'POST',
        body: JSON.stringify({ phone_number: newPhone, purpose: 'change_phone' }),
      });
      setChangePhoneCountdown(60);
      setChangePhoneError('');
    } catch (err: unknown) {
      setChangePhoneError(err instanceof Error ? err.message : '发送验证码失败');
    }
  };

  /** 提交修改手机号 */
  const handleChangePhone = async () => {
    if (!/^1[3-9]\d{9}$/.test(newPhone)) {
      setChangePhoneError('请输入有效的手机号');
      return;
    }
    if (!/^\d{6}$/.test(changePhoneOTP)) {
      setChangePhoneError('请输入 6 位验证码');
      return;
    }
    if (!changePhonePassword) {
      setChangePhoneError('请输入当前密码');
      return;
    }

    setChangePhoneLoading(true);
    setChangePhoneError('');

    try {
      await fetchAPI('/auth/change-phone', {
        method: 'POST',
        body: JSON.stringify({
          new_phone: newPhone,
          otp_code: changePhoneOTP,
          current_password: changePhonePassword,
        }),
      });

      // 更新本地用户信息
      const { setUser } = useAuthStore.getState();
      const currentUser = useAuthStore.getState().user;
      if (currentUser) {
        setUser({ ...currentUser, phone_number: newPhone });
      }
      setFormData(prev => ({ ...prev, phone_number: newPhone }));
      setShowChangePhone(false);
      setNewPhone('');
      setChangePhoneOTP('');
      setChangePhonePassword('');
    } catch (err: unknown) {
      setChangePhoneError(err instanceof Error ? err.message : '修改手机号失败');
    } finally {
      setChangePhoneLoading(false);
    }
  };

  // 修改手机号倒计时
  useEffect(() => {
    if (changePhoneCountdown <= 0) return;
    const timer = setTimeout(() => setChangePhoneCountdown(changePhoneCountdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [changePhoneCountdown]);

  // 格式化日期
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  // 获取头像 URL
  const getAvatarUrl = () => {
    if (profile?.avatar_url) return profile.avatar_url;
    if (profile?.gravatar_url) return profile.gravatar_url;
    return null;
  };

  // 获取角色显示名称
  const getRoleDisplay = () => {
    if (profile?.is_superuser) return { text: '管理员', color: 'text-purple-400 bg-purple-500/10 border-purple-500/30' };
    return { text: '研究员', color: 'text-blue-400 bg-blue-500/10 border-blue-500/30' };
  };

  // Loading 状态
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  const roleDisplay = getRoleDisplay();

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* 卡片一：个人概览 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
            <User size={20} className="text-blue-400" />
            个人概览
          </h2>

          {/* 头像和基础信息 */}
          <div className="flex flex-col md:flex-row gap-6 items-start">
            {/* 头像区域 */}
            <div className="flex-shrink-0">
              <div className="w-24 h-24 rounded-full bg-neutral-800 border-2 border-neutral-700 overflow-hidden flex items-center justify-center">
                {getAvatarUrl() ? (
                  <img
                    src={getAvatarUrl()!}
                    alt="头像"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <User size={40} className="text-neutral-500" />
                )}
              </div>
              {/* 上传按钮预留位 */}
              <button className="mt-3 w-full text-xs text-neutral-400 hover:text-blue-400 transition-colors">
                更换头像
              </button>
            </div>

            {/* 基础信息展示 */}
            <div className="flex-1 space-y-3">
              {/* 邮箱（不可修改） */}
              <div className="flex items-center gap-3">
                <span className="text-neutral-400 text-sm w-16">邮箱</span>
                <span className="text-white font-mono">{profile?.email}</span>
              </div>

              {/* 角色 */}
              <div className="flex items-center gap-3">
                <span className="text-neutral-400 text-sm w-16">角色</span>
                <span className={`px-3 py-1 rounded-full text-xs font-medium border ${roleDisplay.color}`}>
                  {roleDisplay.text}
                </span>
              </div>

              {/* 注册时间 */}
              <div className="flex items-center gap-3">
                <span className="text-neutral-400 text-sm w-16">注册时间</span>
                <span className="text-neutral-300 text-sm">
                  {profile?.created_at && formatDate(profile.created_at)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 卡片二：资料编辑 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
            <FileText size={20} className="text-green-400" />
            资料编辑
          </h2>

          <div className="space-y-5">
            {/* 昵称/全名 */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm text-neutral-300">
                <User size={14} />
                昵称 / 全名
              </label>
              <input
                type="text"
                value={formData.full_name}
                onChange={(e) => handleChange('full_name', e.target.value)}
                placeholder="输入您的昵称或全名"
                className="w-full px-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            {/* 组织/机构 */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm text-neutral-300">
                <Building2 size={14} />
                组织 / 机构
              </label>
              <input
                type="text"
                value={formData.organization}
                onChange={(e) => handleChange('organization', e.target.value)}
                placeholder="如：某某大学 / 某某研究所"
                className="w-full px-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
              />
              <p className="text-xs text-neutral-500">选填。为未来的团队协作功能做准备</p>
            </div>

            {/* 手机号（只读 + 修改按钮，修改需 SMS 验证） */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm text-neutral-300">
                <Phone size={14} />
                手机号码
              </label>
              <div className="flex items-center gap-3">
                <span className="flex-1 px-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-neutral-300">
                  {formData.phone_number || '未绑定'}
                </span>
                <button
                  onClick={() => {
                    setShowChangePhone(true);
                    setNewPhone('');
                    setChangePhoneOTP('');
                    setChangePhonePassword('');
                    setChangePhoneError('');
                  }}
                  className="px-3 py-2.5 text-xs text-blue-400 hover:text-blue-300 border border-blue-500/30 rounded-lg transition-colors whitespace-nowrap"
                >
                  修改
                </button>
              </div>
            </div>

            {/* 个人简介 */}
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm text-neutral-300">
                <FileText size={14} />
                个人简介
              </label>
              <textarea
                value={formData.bio}
                onChange={(e) => handleChange('bio', e.target.value)}
                placeholder="简单介绍一下自己..."
                rows={3}
                className="w-full px-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors resize-none"
              />
              <p className="text-xs text-neutral-500">最多 500 字符</p>
            </div>
          </div>

          {/* 操作按钮和消息 */}
          <div className="mt-6 flex items-center justify-between">
            {/* 状态消息 */}
            {message && (
              <div className={`flex items-center gap-2 text-sm ${
                message.type === 'success' ? 'text-green-400' : 'text-red-400'
              }`}>
                {message.type === 'success' ? (
                  <CheckCircle size={16} />
                ) : (
                  <AlertCircle size={16} />
                )}
                {message.text}
              </div>
            )}
            <div className="flex-1" />
            {/* 保存按钮 */}
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 text-white rounded-lg font-medium transition-colors"
            >
              {saving ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  保存中...
                </>
              ) : (
                <>
                  <Save size={16} />
                  保存修改
                </>
              )}
            </button>
          </div>
        </div>

      </div>

      {/* 修改手机号模态框 */}
      {showChangePhone && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="w-full max-w-sm mx-4 bg-neutral-900 border border-neutral-700 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">修改手机号</h3>
              <button
                onClick={() => setShowChangePhone(false)}
                className="text-neutral-400 hover:text-white transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            {changePhoneError && (
              <div className="mb-4 p-2.5 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm text-center">
                {changePhoneError}
              </div>
            )}

            <div className="space-y-4">
              {/* 新手机号 */}
              <div>
                <label className="block text-sm text-neutral-300 mb-1.5">新手机号</label>
                <div className="flex gap-3">
                  <input
                    type="tel"
                    value={newPhone}
                    onChange={(e) => setNewPhone(e.target.value)}
                    placeholder="请输入新手机号"
                    className="flex-1 px-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                  />
                  <button
                    onClick={handleChangePhoneSendSMS}
                    disabled={changePhoneCountdown > 0 || !/^1[3-9]\d{9}$/.test(newPhone)}
                    className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-neutral-700 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
                  >
                    {changePhoneCountdown > 0 ? `${changePhoneCountdown}s` : <span className="flex items-center gap-1"><Send size={14} /> 发送</span>}
                  </button>
                </div>
              </div>

              {/* 验证码 */}
              <div>
                <label className="block text-sm text-neutral-300 mb-1.5">验证码</label>
                <input
                  type="text"
                  inputMode="numeric"
                  value={changePhoneOTP}
                  onChange={(e) => setChangePhoneOTP(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="6 位验证码"
                  maxLength={6}
                  className="w-full px-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors text-center tracking-[0.3em]"
                />
              </div>

              {/* 当前密码 */}
              <div>
                <label className="block text-sm text-neutral-300 mb-1.5">当前密码（身份验证）</label>
                <input
                  type="password"
                  value={changePhonePassword}
                  onChange={(e) => setChangePhonePassword(e.target.value)}
                  placeholder="输入当前密码以验证身份"
                  className="w-full px-4 py-2.5 bg-neutral-800 border border-neutral-700 rounded-lg text-white placeholder-neutral-500 focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>

              <button
                onClick={handleChangePhone}
                disabled={changePhoneLoading}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-600/50 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
              >
                {changePhoneLoading ? <Loader2 size={16} className="animate-spin" /> : <Phone size={16} />}
                确认修改
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}