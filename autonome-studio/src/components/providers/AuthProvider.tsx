/**
 * AuthProvider - 应用启动时校验持久化会话有效性
 *
 * 设计日期: 2026-04-24
 *
 * 功能：
 * - 在应用首次挂载时调用 useAuthStore.initializeAuth()
 * - 验证 localStorage 中持久化的会话是否仍然有效
 * - 会话失效时自动清除本地状态
 *
 * 使用：在 layout.tsx 的 <body> 内包裹 <AuthProvider>
 */

"use client";

import { useEffect } from 'react';
import { useAuthStore } from '@/store/useAuthStore';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const initializeAuth = useAuthStore((s) => s.initializeAuth);

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  return <>{children}</>;
}
