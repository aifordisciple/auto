"use client";

import { useState } from "react";
import { fetchAPI, BASE_URL } from "../../lib/api";
import { useAuthStore } from "../../store/useAuthStore";

export default function LoginPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { setToken, setUser } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (isLogin) {
        // FastAPI OAuth2 需要 x-www-form-urlencoded
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);

        const res = await fetch(`${BASE_URL}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: formData.toString()
        });

        if (!res.ok) throw new Error("账号或密码错误");
        const data = await res.json();
        console.log("Login response:", data);
        
        // 1. 存 Token
        console.log("Setting token...");
        setToken(data.access_token);
        // ✨ 这里有个小 trick：存入 localStorage 方便 fetchAPI 读取
        localStorage.setItem('autonome_access_token', data.access_token); 
        
        // 2. 拉取用户信息
        console.log("Fetching user info...");
        const userRes = await fetch(`${BASE_URL}/api/auth/me`, {
          headers: { 'Authorization': `Bearer ${data.access_token}` }
        });
        console.log("User response status:", userRes.status);
        
        if (!userRes.ok) {
          // 即使 /me 请求失败，仍然使用基本信息跳转
          console.warn("/me endpoint failed, using minimal user data");
          setUser({ id: 1, email, credits_balance: 0, is_superuser: false });
        } else {
          const userData = await userRes.json();
          console.log("User data:", userData);
          setUser(userData);
        }
        
        // 3. 跳转 Dashboard
        console.log("Redirecting to /dashboard...");
        window.location.href = "/dashboard";
        console.log("Redirect done");
      } else {
        // 注册流程
        await fetchAPI('/api/auth/register', {
          method: 'POST',
          body: JSON.stringify({ email, password })
        });
        setIsLogin(true); // 注册成功切回登录
        alert("注册成功！送您 100 算力点，请登录。");
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-950 flex items-center justify-center relative overflow-hidden font-sans">
      {/* 背景光效 */}
      <div className="absolute top-[20%] left-[20%] w-[500px] h-[500px] bg-blue-900/20 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[20%] right-[20%] w-[400px] h-[400px] bg-purple-900/20 rounded-full blur-[100px] pointer-events-none"></div>
      <div className="absolute inset-0 bg-grid-pattern pointer-events-none opacity-40"></div>

      <div className="z-10 bg-neutral-900/80 backdrop-blur-xl border border-neutral-800 p-10 rounded-2xl shadow-2xl w-full max-w-md">
        <div className="text-center mb-10">
          <div className="text-3xl mb-2 tracking-widest font-bold text-white"><span className="text-blue-500">🧬</span> AUTONOME</div>
          <p className="text-neutral-500 text-sm">Next-Gen Bioinformatics Agent</p>
        </div>

        <div className="flex gap-4 mb-8">
          <button onClick={() => setIsLogin(true)} className={`flex-1 pb-2 text-sm font-medium transition-colors ${isLogin ? 'text-blue-400 border-b-2 border-blue-500' : 'text-neutral-500 border-b-2 border-transparent hover:text-neutral-300'}`}>Sign In</button>
          <button onClick={() => setIsLogin(false)} className={`flex-1 pb-2 text-sm font-medium transition-colors ${!isLogin ? 'text-blue-400 border-b-2 border-blue-500' : 'text-neutral-500 border-b-2 border-transparent hover:text-neutral-300'}`}>Create Account</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {error && <div className="p-3 bg-red-950/50 border border-red-900/50 text-red-400 text-xs rounded-md text-center">{error}</div>}
          
          <div>
            <label className="block text-xs text-neutral-400 mb-1.5 uppercase tracking-wide">Email Address</label>
            <input type="email" required value={email} onChange={e => setEmail(e.target.value)} className="w-full bg-neutral-950 border border-neutral-800 text-white rounded-lg p-3 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 transition-all text-sm" />
          </div>
          
          <div>
            <label className="block text-xs text-neutral-400 mb-1.5 uppercase tracking-wide">Password</label>
            <input type="password" required value={password} onChange={e => setPassword(e.target.value)} className="w-full bg-neutral-950 border border-neutral-800 text-white rounded-lg p-3 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 transition-all text-sm" />
          </div>

          <button type="submit" disabled={loading} className="w-full mt-4 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white font-medium p-3 rounded-lg text-sm transition-all shadow-[0_0_20px_rgba(37,99,235,0.3)] hover:shadow-[0_0_30px_rgba(37,99,235,0.5)]">
            {loading ? "Processing..." : (isLogin ? "INITIALIZE SESSION" : "DEPLOY WORKSPACE")}
          </button>
        </form>
      </div>
    </div>
  );
}
