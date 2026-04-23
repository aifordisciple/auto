/**
 * 邮箱验证落地页
 *
 * 设计日期: 2026-04-23
 *
 * 功能：
 * - 用户点击邮件中的验证链接后跳转到此页面
 * - 从 URL query 参数读取 token
 * - 调用 /api/auth/verify-email 完成验证
 * - 显示验证成功/失败结果
 */

"use client";

import { useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { fetchAPI } from '@/lib/api';
import { CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

export default function VerifyEmailPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');

    if (!token) {
      setStatus('error');
      setMessage('验证链接无效，缺少验证凭证');
      return;
    }

    (async () => {
      try {
        const data = await fetchAPI('/auth/verify-email', {
          method: 'POST',
          body: JSON.stringify({ token }),
        });

        if (data.status === 'success') {
          setStatus('success');
          setMessage('邮箱验证成功！');
        } else {
          setStatus('error');
          setMessage(data.message || '验证失败，请重试');
        }
      } catch (err: unknown) {
        setStatus('error');
        setMessage(err instanceof Error ? err.message : '验证失败，请重试');
      }
    })();
  }, [searchParams]);

  return (
    <div className="min-h-screen bg-neutral-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md text-center">
        <h1 className="text-3xl font-bold text-white mb-8">Autonome</h1>

        {status === 'loading' && (
          <div className="flex flex-col items-center gap-4">
            <Loader2 size={40} className="animate-spin text-blue-400" />
            <p className="text-neutral-400">正在验证邮箱...</p>
          </div>
        )}

        {status === 'success' && (
          <div className="flex flex-col items-center gap-4">
            <div className="w-16 h-16 bg-green-500/10 rounded-full flex items-center justify-center">
              <CheckCircle size={32} className="text-green-400" />
            </div>
            <h2 className="text-xl font-semibold text-white">{message}</h2>
            <p className="text-sm text-neutral-400">您的邮箱已成功绑定，可以安全地使用所有功能。</p>
            <button
              onClick={() => router.push('/')}
              className="mt-4 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
            >
              返回首页
            </button>
          </div>
        )}

        {status === 'error' && (
          <div className="flex flex-col items-center gap-4">
            <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center">
              <AlertCircle size={32} className="text-red-400" />
            </div>
            <h2 className="text-xl font-semibold text-white">验证失败</h2>
            <p className="text-sm text-neutral-400">{message}</p>
            <button
              onClick={() => router.push('/')}
              className="mt-4 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
            >
              返回首页
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
