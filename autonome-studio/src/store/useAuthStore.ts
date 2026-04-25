/**
 * 认证状态管理 Store
 *
 * 设计日期: 2026-03-22
 * 更新日期: 2026-04-21（阶段2：Cookie 模式 + 新用户字段）
 *
 * 功能：
 * - 用户信息管理（id, email, phone_number, 安全字段等）
 * - Token 管理（SSE/第三方场景的手动 Token，Cookie 模式下自动管理）
 * - 登出时调用 /auth/logout 端点撤销会话
 *
 * Cookie 模式说明：
 * - httpOnly Cookie 由浏览器自动携带，前端无需手动管理
 * - store 中的 token 仅用于 SSE/WebSocket 等无法使用 Cookie 的场景
 * - 登出时需调用后端 /auth/logout 撤销会话 + 清除 Cookie
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { fetchAPI } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

interface UserState {
  id: number | null;
  email: string | null;
  full_name: string | null;
  avatar_url: string | null;
  organization: string | null;
  phone_number: string | null;
  bio: string | null;
  is_superuser: boolean;
  is_email_verified: boolean;
  is_2fa_enabled: boolean;
  credits_balance: number;
  last_password_change: string | null;
}

interface AuthState {
  // 用户信息
  user: UserState | null;
  // 手动 Token（仅 SSE/WebSocket 场景使用，Cookie 模式下可为空）
  token: string | null;
  // 是否已认证
  isAuthenticated: boolean;

  // Actions
  setUser: (user: Partial<UserState> & { id: number }) => void;
  setToken: (token: string | null) => void;
  setCreditsBalance: (balance: number) => void;
  fetchProfile: () => Promise<void>;
  logout: () => Promise<void>;
  clearAll: () => void;
  /** 应用启动时校验持久化会话有效性，失效则清除本地状态 */
  initializeAuth: () => Promise<void>;
}

// ==========================================
// 默认用户状态
// ==========================================

const defaultUser: UserState = {
  id: null,
  email: null,
  full_name: null,
  avatar_url: null,
  organization: null,
  phone_number: null,
  bio: null,
  is_superuser: false,
  is_email_verified: false,
  is_2fa_enabled: false,
  credits_balance: 0,
  last_password_change: null,
};

// ==========================================
// Auth Store
// ==========================================

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,

      setUser: (userData) => {
        set({
          user: { ...defaultUser, ...userData },
          isAuthenticated: true,
        });
      },

      setToken: (token) => {
        set({ token });
      },

      // 同步更新 credits_balance，供 SSE billing 事件实时刷新余额
      setCreditsBalance: (balance) => {
        const currentUser = get().user;
        if (currentUser) {
          set({ user: { ...currentUser, credits_balance: balance } });
        }
      },

      fetchProfile: async () => {
        try {
          const data = await fetchAPI('/auth/me');
          set({
            user: {
              id: data.id,
              email: data.email,
              full_name: data.full_name,
              avatar_url: data.avatar_url,
              organization: data.organization,
              phone_number: data.phone_number,
              bio: data.bio,
              is_superuser: data.is_superuser,
              is_email_verified: data.is_email_verified,
              is_2fa_enabled: data.is_2fa_enabled,
              credits_balance: data.credits_balance ?? 0,
              last_password_change: data.last_password_change ?? null,
            },
            isAuthenticated: true,
          });
        } catch {
          // 获取失败，清除认证状态
          get().clearAll();
        }
      },

      logout: async () => {
        try {
          // 调用后端登出端点：撤销会话 + 清除 Cookie
          // skipRefresh: true 防止 logout 401 触发 refresh 死循环
          await fetchAPI('/auth/logout', { method: 'POST', skipRefresh: true });
        } catch {
          // 即使后端登出失败，前端仍需清除本地状态
        }
        get().clearAll();
      },

      clearAll: () => {
        set({
          user: null,
          token: null,
          isAuthenticated: false,
        });
      },

      /**
       * 应用启动时校验持久化会话有效性
       *
       * 场景：用户刷新页面后，localStorage 中 isAuthenticated=true，
       * 但服务端可能已撤销该 session（如用户在其他设备上修改了密码）。
       * 此方法主动调用 /auth/me 验证会话，失败则清除本地状态。
       */
      initializeAuth: async () => {
        const { isAuthenticated } = get();
        if (!isAuthenticated) return; // 未登录，无需校验
        try {
          await get().fetchProfile();
        } catch {
          // 会话已失效（服务端已撤销），清除本地状态
          get().clearAll();
        }
      },
    }),
    {
      name: 'auth-storage',
      // 仅持久化用户基本信息，不持久化 token（Cookie 管理）
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
