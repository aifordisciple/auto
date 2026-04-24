/**
 * OAuth 回调中间页
 *
 * 设计日期: 2026-04-24
 *
 * 功能：
 * - 接收后端 OAuth 重定向，根据 URL 参数分三种场景：
 *   1. ?status=success → 登录成功，刷新用户信息后跳转首页
 *   2. ?oauth_error=... → 登录失败，显示错误信息，提供返回登录页按钮
 *   3. ?requires_binding=true&bind_ref=... → 需绑定手机号，弹出绑定模态框
 *
 * 安全说明：
 * - bind_ref 是一次性引用键（非真实 bind_token），后端从 Redis 取出真实 token
 * - 绑定完成后自动登录并跳转
 */

'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/store/useAuthStore';
import { fetchAPI } from '@/lib/api';
import { BindPhoneModal } from '@/components/overlays/Auth/BindPhoneModal';
import {
  Loader2,
  AlertCircle,
  CheckCircle,
  ArrowLeft,
} from 'lucide-react';

// ==========================================
// 内部组件：使用 useSearchParams（需 Suspense 包裹）
// ==========================================

function OAuthCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { fetchProfile } = useAuthStore();

  // 解析 URL 参数
  const status = searchParams.get('status');
  const oauthError = searchParams.get('oauth_error');
  const requiresBinding = searchParams.get('requires_binding') === 'true';
  const bindRef = searchParams.get('bind_ref') || '';
  const providerName = searchParams.get('provider_name') || '';

  // UI 状态
  const [processing, setProcessing] = useState(true);
  const [errorMessage, setErrorMessage] = useState('');

  // 场景1：登录成功 → 刷新用户信息后跳转首页
  useEffect(() => {
    if (status !== 'success') return;

    (async () => {
      try {
        await fetchProfile();
        router.replace('/');
      } catch {
        setErrorMessage('登录信息获取失败，请重新登录');
        setProcessing(false);
      }
    })();
  }, [status, fetchProfile, router]);

  // 场景2：OAuth 错误 → 直接显示错误
  useEffect(() => {
    if (!oauthError) return;
    setErrorMessage(oauthError);
    setProcessing(false);
  }, [oauthError]);

  // 场景3：需要绑定手机号 → 显示绑定模态框（不需要 processing 状态）
  useEffect(() => {
    if (requiresBinding) {
      setProcessing(false);
    }
  }, [requiresBinding]);

  // 绑定完成回调：刷新用户信息后跳转首页
  const handleBindComplete = async () => {
    try {
      await fetchProfile();
      router.replace('/');
    } catch {
      // 绑定成功但获取信息失败，仍跳转首页
      router.replace('/');
    }
  };

  // ── 渲染：加载中 ──
  if (processing) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a0f]">
        <div className="text-center">
          <Loader2 size={40} className="animate-spin text-blue-500 mx-auto mb-4" />
          <p className="text-gray-400">正在处理 OAuth 登录...</p>
        </div>
      </div>
    );
  }

  // ── 渲染：OAuth 错误 ──
  if (errorMessage) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a0f]">
        <div className="w-full max-w-md p-8 text-center">
          <AlertCircle size={48} className="text-red-400 mx-auto mb-4" />
          <h1 className="text-xl font-bold text-white mb-2">登录失败</h1>
          <p className="text-sm text-gray-400 mb-6">{errorMessage}</p>
          <button
            onClick={() => router.push('/login')}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
          >
            <ArrowLeft size={16} />
            返回登录
          </button>
        </div>
      </div>
    );
  }

  // ── 渲染：需要绑定手机号 ──
  if (requiresBinding && bindRef) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a0f]">
        <div className="w-full max-w-md p-8">
          <div className="text-center mb-6">
            <CheckCircle size={40} className="text-green-400 mx-auto mb-3" />
            <h1 className="text-xl font-bold text-white">绑定手机号</h1>
            <p className="text-sm text-gray-400 mt-2">
              {providerName ? `${providerName} 账号验证成功` : '第三方账号验证成功'}，请绑定手机号以完成注册
            </p>
          </div>
          <BindPhoneModal
            bindRef={bindRef}
            providerName={providerName}
            onComplete={handleBindComplete}
          />
        </div>
      </div>
    );
  }

  // ── 渲染：未知状态（兜底） ──
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0f]">
      <div className="w-full max-w-md p-8 text-center">
        <AlertCircle size={48} className="text-yellow-400 mx-auto mb-4" />
        <h1 className="text-xl font-bold text-white mb-2">未知回调状态</h1>
        <p className="text-sm text-gray-400 mb-6">OAuth 回调参数异常，请重新登录</p>
        <button
          onClick={() => router.push('/login')}
          className="inline-flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
        >
          <ArrowLeft size={16} />
          返回登录
        </button>
      </div>
    </div>
  );
}

// ==========================================
// 页面组件：用 Suspense 包裹 useSearchParams
// ==========================================

export default function OAuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-[#0a0a0f]">
          <Loader2 size={40} className="animate-spin text-blue-500" />
        </div>
      }
    >
      <OAuthCallbackContent />
    </Suspense>
  );
}
