import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { fetchAPI } from '../lib/api';

interface AuthState {
  token: string | null;
  user: {
    id: number;
    email: string;
    full_name?: string;
    credits_balance: number;
    is_superuser: boolean;
  } | null;
  setToken: (token: string) => void;
  setUser: (user: any) => void;
  updateCredits: (balance: number) => void;
  logout: () => void;
  fetchProfile: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user }),
      updateCredits: (balance) => set((state) => ({ 
        user: state.user ? { ...state.user, credits_balance: balance } : null 
      })),
      logout: () => set({ token: null, user: null }),
      fetchProfile: async () => {
        const { token } = get();
        if (!token) return;
        try {
          const res = await fetchAPI('/api/auth/me');
          if (res && !res.detail) {
            set({ user: res });
          }
        } catch (e) {
          console.error('Failed to fetch profile:', e);
        }
      },
    }),
    { name: 'autonome-auth-storage' }
  )
);
