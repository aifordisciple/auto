"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "../../store/useAuthStore";
import { fetchAPI } from "../../lib/api";
import { Users, Zap, Server, Activity, Shield, CreditCard, AlertTriangle, CheckCircle, XCircle, RefreshCw, ArrowLeft } from "lucide-react";
import { useKeyboardShortcut } from "../../hooks/useKeyboardShortcut";

type TabType = 'stats' | 'users' | 'cluster';

export default function AdminDashboard() {
  const router = useRouter();
  const { token, user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<TabType>('stats');
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [cluster, setCluster] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const localToken = localStorage.getItem('autonome_access_token');
    if (!localToken) {
      router.push('/login');
      return;
    }
    loadData();
  }, []);

  // ESC 返回工作区
  useKeyboardShortcut("Escape", () => {
    window.location.href = '/';
  });

  const loadData = async () => {
    setLoading(true);
    try {
      const statsData = await fetchAPI('/api/admin/stats');
      setStats(statsData.data);
      
      const usersData = await fetchAPI('/api/admin/users');
      setUsers(usersData.data);
      
      const clusterData = await fetchAPI('/api/admin/cluster/status');
      setCluster(clusterData.data);
    } catch (e) {
      console.error('Failed to load admin data:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleUser = async (userId: number) => {
    try {
      await fetchAPI(`/api/admin/users/${userId}/toggle-active`, { method: 'POST' });
      loadData();
    } catch (e) {
      alert('操作失败');
    }
  };

  const handleCreditAdjustment = async (userId: number) => {
    const amount = prompt('请输入算力调整数量（正数增加，负数扣减）:');
    if (!amount) return;
    const reason = prompt('请输入原因:') || '管理员调整';
    try {
      await fetchAPI(`/api/admin/users/${userId}/credits`, {
        method: 'POST',
        body: JSON.stringify({ amount: parseFloat(amount), reason })
      });
      loadData();
      alert('算力调整成功');
    } catch (e) {
      alert('操作失败');
    }
  };

  if (!token) return null;

  return (
    <div className="min-h-screen bg-neutral-950 text-white font-sans">
      {/* Header */}
      <div className="h-16 bg-neutral-900 border-b border-neutral-800 flex items-center px-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => window.location.href = '/'}
            className="p-2 mr-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-all"
            title="返回主页"
          >
            <ArrowLeft size={20} />
          </button>
          <Shield size={24} className="text-amber-500" />
          <h1 className="text-xl font-bold">运营后台 <span className="text-amber-500">Admin Console</span></h1>
        </div>
        <div className="ml-auto flex items-center gap-4">
          <span className="text-neutral-400 text-sm">当前管理员: {user?.email}</span>
          <button onClick={loadData} disabled={loading} className="p-2 hover:bg-neutral-800 rounded-lg">
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-neutral-800">
        {[
          { id: 'stats', label: '数据概览', icon: Activity },
          { id: 'users', label: '用户管理', icon: Users },
          { id: 'cluster', label: '集群监控', icon: Server },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as TabType)}
            className={`flex items-center gap-2 px-6 py-4 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-amber-500 border-b-2 border-amber-500 bg-neutral-900/50'
                : 'text-neutral-400 hover:text-white hover:bg-neutral-900/30'
            }`}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-6">
        {loading && (
          <div className="flex items-center justify-center py-20">
            <RefreshCw size={32} className="animate-spin text-amber-500" />
          </div>
        )}

        {!loading && activeTab === 'stats' && stats && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <Users size={20} className="text-blue-500" />
                <span className="text-neutral-400 text-sm">总用户数</span>
              </div>
              <div className="text-3xl font-bold text-white">{stats.users?.total || 0}</div>
              <div className="text-sm text-green-500 mt-2">活跃: {stats.users?.active || 0}</div>
            </div>

            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <Zap size={20} className="text-amber-500" />
                <span className="text-neutral-400 text-sm"> workspaces</span>
              </div>
              <div className="text-3xl font-bold text-white">{stats.workspaces_created || 0}</div>
            </div>

            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <Activity size={20} className="text-purple-500" />
                <span className="text-neutral-400 text-sm">AI 会话</span>
              </div>
              <div className="text-3xl font-bold text-white">{stats.ai_sessions || 0}</div>
            </div>

            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <CreditCard size={20} className="text-emerald-500" />
                <span className="text-neutral-400 text-sm">流通算力</span>
              </div>
              <div className="text-3xl font-bold text-white">{stats.total_credits_outstanding?.toFixed(0) || 0}</div>
              <div className="text-sm text-neutral-500 mt-2"> Credits</div>
            </div>
          </div>
        )}

        {!loading && activeTab === 'users' && (
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden">
            <table className="w-full">
              <thead className="bg-neutral-800/50 text-neutral-400 text-sm">
                <tr>
                  <th className="text-left px-6 py-4">ID</th>
                  <th className="text-left px-6 py-4">邮箱</th>
                  <th className="text-left px-6 py-4">状态</th>
                  <th className="text-left px-6 py-4">角色</th>
                  <th className="text-left px-6 py-4">算力余额</th>
                  <th className="text-left px-6 py-4">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-neutral-800/30">
                    <td className="px-6 py-4 text-neutral-400">#{u.id}</td>
                    <td className="px-6 py-4 text-white font-mono text-sm">{u.email}</td>
                    <td className="px-6 py-4">
                      {u.is_active ? (
                        <span className="flex items-center gap-2 text-green-500 text-sm">
                          <CheckCircle size={14} /> 正常
                        </span>
                      ) : (
                        <span className="flex items-center gap-2 text-red-500 text-sm">
                          <XCircle size={14} /> 已封禁
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {u.is_superuser ? (
                        <span className="text-amber-500 text-sm font-medium">超级管理员</span>
                      ) : (
                        <span className="text-neutral-500 text-sm">普通用户</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-amber-400 font-mono">{u.credits_balance?.toFixed(0) || 0}</td>
                    <td className="px-6 py-4">
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleToggleUser(u.id)}
                          disabled={u.is_superuser}
                          className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                            u.is_active
                              ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                              : 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                          } ${u.is_superuser ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                          {u.is_active ? '封禁' : '解封'}
                        </button>
                        <button
                          onClick={() => handleCreditAdjustment(u.id)}
                          className="px-3 py-1.5 bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 rounded text-xs font-medium transition-colors"
                        >
                          调账
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && activeTab === 'cluster' && cluster && (
          <div className="space-y-6">
            {/* Docker Containers */}
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Server size={20} className="text-blue-500" />
                运行中的沙箱容器
              </h3>
              {cluster.active_sandboxes?.length > 0 ? (
                <div className="grid gap-4">
                  {cluster.active_sandboxes.map((c: any, i: number) => (
                    <div key={i} className="bg-neutral-950 border border-neutral-800 rounded-lg p-4 flex items-center justify-between">
                      <div>
                        <div className="font-mono text-sm text-blue-400">{c.container_id}</div>
                        <div className="text-neutral-400 text-sm">{c.name}</div>
                        <div className="text-neutral-500 text-xs mt-1">{c.image}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-1 bg-green-500/20 text-green-400 text-xs rounded">Running</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-neutral-500 text-center py-8">
                  <AlertTriangle size={32} className="mx-auto mb-2 opacity-50" />
                  暂无运行中的沙箱容器
                </div>
              )}
            </div>

            {/* Celery Tasks */}
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Activity size={20} className="text-purple-500" />
                Celery 任务队列
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-4">
                  <div className="text-neutral-400 text-sm mb-2">运行中任务</div>
                  <div className="text-2xl font-bold text-white">
                    {Object.values(cluster.active_celery_tasks?.running || {}).flat().length}
                  </div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-4">
                  <div className="text-neutral-400 text-sm mb-2">排队中任务</div>
                  <div className="text-2xl font-bold text-white">
                    {Object.values(cluster.active_celery_tasks?.queued || {}).flat().length}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
