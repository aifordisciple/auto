"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "../../store/useAuthStore";
import { fetchAPI } from "../../lib/api";
import { Users, Zap, Server, Activity, Shield, CreditCard, AlertTriangle, CheckCircle, XCircle, RefreshCw, ArrowLeft, Cpu, Box, Settings, History, Bot, Database, Sparkles, Save, Globe, Key } from "lucide-react";
import { useKeyboardShortcut } from "../../hooks/useKeyboardShortcut";

type TabType = 'stats' | 'users' | 'cluster' | 'skills' | 'embedding';

// ==========================================
// 技能执行模式相关类型
// ==========================================
interface SkillExecutionMode {
  skill_id: string;
  name: string;
  executor_type: string;
  execution_mode: "docker" | "native";
  status: string;
  owner_id: number;
  is_official: boolean;
  execution_mode_updated_at: string | null;
  execution_mode_updated_by: number | null;
}

// ==========================================
// Claude 权限相关类型
// ==========================================
interface ClaudePermission {
  id: number;
  user_id: number;
  allowed_modes: string[];
  granted_by: number;
  granted_at: string;
  expires_at: string | null;
  notes: string | null;
}

interface UserWithClaudePermission {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  credits_balance: number;
  claude_permission?: ClaudePermission;
}

// ==========================================
// 嵌入模型配置接口
// ==========================================
interface EmbeddingSettings {
  embedding_api_base: string;
  embedding_model: string;
  embedding_api_key: string;
  embedding_dimension: number;
}

export default function AdminDashboard() {
  const router = useRouter();
  const { token, user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<TabType>('stats');
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<UserWithClaudePermission[]>([]);
  const [cluster, setCluster] = useState<any>(null);
  const [skills, setSkills] = useState<SkillExecutionMode[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<SkillExecutionMode | null>(null);
  const [showModeDialog, setShowModeDialog] = useState(false);
  const [pendingMode, setPendingMode] = useState<"docker" | "native">("docker");
  const [modeReason, setModeReason] = useState("");

  // Claude 权限管理状态
  const [showClaudeDialog, setShowClaudeDialog] = useState(false);
  const [selectedUserForClaude, setSelectedUserForClaude] = useState<UserWithClaudePermission | null>(null);
  const [claudeModes, setClaudeModes] = useState<string[]>(["container"]); // 默认只有容器模式
  const [claudeNotes, setClaudeNotes] = useState("");

  // 嵌入模型配置状态
  const [embeddingSettings, setEmbeddingSettings] = useState<EmbeddingSettings>({
    embedding_api_base: "http://host.docker.internal:11434",
    embedding_model: "bge-m3:latest",
    embedding_api_key: "EMPTY",
    embedding_dimension: 1024
  });
  const [embeddingSaving, setEmbeddingSaving] = useState(false);
  const [embeddingSuccess, setEmbeddingSuccess] = useState(false);

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

      // ✨ 加载技能执行模式数据
      const skillsData = await fetchAPI('/api/admin/skills/execution-modes');
      setSkills(skillsData);

      // ✨ 加载嵌入模型配置
      const settingsData = await fetchAPI('/api/system/settings');
      if (settingsData.status === 'success' && settingsData.data) {
        setEmbeddingSettings({
          embedding_api_base: settingsData.data.embedding_api_base || "http://host.docker.internal:11434",
          embedding_model: settingsData.data.embedding_model || "bge-m3:latest",
          embedding_api_key: settingsData.data.embedding_api_key || "EMPTY",
          embedding_dimension: settingsData.data.embedding_dimension || 1024
        });
      }
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

  // ==========================================
  // 技能执行模式管理
  // ==========================================
  const handleOpenModeDialog = (skill: SkillExecutionMode, mode: "docker" | "native") => {
    setSelectedSkill(skill);
    setPendingMode(mode);
    setModeReason("");
    setShowModeDialog(true);
  };

  const handleExecutionModeChange = async () => {
    if (!selectedSkill || !modeReason.trim()) {
      alert("请填写切换原因");
      return;
    }

    try {
      await fetchAPI(`/api/admin/skills/${selectedSkill.skill_id}/execution-mode`, {
        method: 'PATCH',
        body: JSON.stringify({
          execution_mode: pendingMode,
          reason: modeReason
        })
      });
      setShowModeDialog(false);
      loadData();
      alert(`执行模式已更新为 ${pendingMode}`);
    } catch (e: any) {
      alert(e.message || '操作失败');
    }
  };

  // ==========================================
  // Claude 权限管理
  // ==========================================
  const handleOpenClaudeDialog = (targetUser: UserWithClaudePermission) => {
    setSelectedUserForClaude(targetUser);
    // 如果已有权限，加载现有配置
    if (targetUser.claude_permission) {
      setClaudeModes(targetUser.claude_permission.allowed_modes);
      setClaudeNotes(targetUser.claude_permission.notes || "");
    } else {
      // 默认只有容器模式
      setClaudeModes(["container"]);
      setClaudeNotes("");
    }
    setShowClaudeDialog(true);
  };

  const handleGrantClaudePermission = async () => {
    if (!selectedUserForClaude) return;

    try {
      await fetchAPI('/api/claude-executor/permissions/grant', {
        method: 'POST',
        body: JSON.stringify({
          user_id: selectedUserForClaude.id,
          allowed_modes: claudeModes,
          notes: claudeNotes || undefined
        })
      });
      setShowClaudeDialog(false);
      loadData();
      alert('Claude 权限已更新');
    } catch (e: any) {
      alert(e.message || '操作失败');
    }
  };

  const handleRevokeClaudePermission = async (userId: number) => {
    if (!confirm('确定要撤销该用户的 Claude 权限吗？')) return;

    try {
      await fetchAPI(`/api/claude-executor/permissions/${userId}`, {
        method: 'DELETE'
      });
      loadData();
      alert('Claude 权限已撤销');
    } catch (e: any) {
      alert('操作失败');
    }
  };

  // ==========================================
  // 嵌入模型配置保存
  // ==========================================
  const handleSaveEmbeddingSettings = async () => {
    setEmbeddingSaving(true);
    try {
      await fetchAPI('/api/system/settings', {
        method: 'POST',
        body: JSON.stringify(embeddingSettings)
      });
      setEmbeddingSuccess(true);
      setTimeout(() => setEmbeddingSuccess(false), 3000);
    } catch (e: any) {
      alert('保存失败: ' + (e.message || '未知错误'));
    } finally {
      setEmbeddingSaving(false);
    }
  };

  // 设置默认本地嵌入模型
  const setDefaultEmbedding = () => setEmbeddingSettings({
    embedding_api_base: "http://host.docker.internal:11434",
    embedding_model: "bge-m3:latest",
    embedding_api_key: "EMPTY",
    embedding_dimension: 1024
  });

  // 设置 OpenAI 嵌入模型
  const setOpenAIEmbedding = () => setEmbeddingSettings({
    embedding_api_base: "https://api.openai.com/v1",
    embedding_model: "text-embedding-3-small",
    embedding_api_key: "",
    embedding_dimension: 1536
  });

  if (!token) return null;

  return (
    <div className="h-screen bg-neutral-950 text-white font-sans flex flex-col">
      {/* Header */}
      <div className="h-16 bg-neutral-900 border-b border-neutral-800 flex items-center px-6 flex-shrink-0">
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
          { id: 'skills', label: '技能管理', icon: Cpu },
          { id: 'embedding', label: '嵌入模型', icon: Database },
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
      <div className="flex-1 overflow-y-auto p-6">
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
                  <th className="text-left px-6 py-4">Claude权限</th>
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
                      {u.claude_permission ? (
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-1">
                            {u.claude_permission.allowed_modes.includes('host') && (
                              <span className="px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded">宿主机</span>
                            )}
                            {u.claude_permission.allowed_modes.includes('container') && (
                              <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded">容器</span>
                            )}
                          </div>
                          <span className="text-neutral-500 text-xs">
                            {new Date(u.claude_permission.granted_at).toLocaleDateString()}
                          </span>
                        </div>
                      ) : (
                        <span className="text-neutral-600 text-sm">无权限</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex gap-2 flex-wrap">
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
                        <button
                          onClick={() => handleOpenClaudeDialog(u)}
                          className="px-3 py-1.5 bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 rounded text-xs font-medium transition-colors"
                          title="管理 Claude Code 权限"
                        >
                          <Bot size={12} className="inline mr-1" />
                          {u.claude_permission ? '编辑权限' : '授权'}
                        </button>
                        {u.claude_permission && (
                          <button
                            onClick={() => handleRevokeClaudePermission(u.id)}
                            className="px-3 py-1.5 bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded text-xs font-medium transition-colors"
                          >
                            撤销
                          </button>
                        )}
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

        {/* ✨ 技能管理面板 */}
        {!loading && activeTab === 'skills' && (
          <div className="space-y-6">
            {/* 执行模式统计 */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
                <div className="flex items-center gap-3 mb-4">
                  <Box size={20} className="text-blue-500" />
                  <span className="text-neutral-400 text-sm">Docker 模式</span>
                </div>
                <div className="text-3xl font-bold text-white">
                  {skills.filter(s => s.execution_mode === 'docker').length}
                </div>
                <div className="text-sm text-neutral-500 mt-2">容器隔离执行</div>
              </div>

              <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
                <div className="flex items-center gap-3 mb-4">
                  <Cpu size={20} className="text-green-500" />
                  <span className="text-neutral-400 text-sm">Native 模式</span>
                </div>
                <div className="text-3xl font-bold text-white">
                  {skills.filter(s => s.execution_mode === 'native').length}
                </div>
                <div className="text-sm text-neutral-500 mt-2">宿主机直接执行</div>
              </div>

              <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
                <div className="flex items-center gap-3 mb-4">
                  <Shield size={20} className="text-amber-500" />
                  <span className="text-neutral-400 text-sm">官方技能</span>
                </div>
                <div className="text-3xl font-bold text-white">
                  {skills.filter(s => s.is_official).length}
                </div>
                <div className="text-sm text-neutral-500 mt-2">可使用原生模式</div>
              </div>
            </div>

            {/* 技能列表表格 */}
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden">
              <table className="w-full">
                <thead className="bg-neutral-800/50 text-neutral-400 text-sm">
                  <tr>
                    <th className="text-left px-6 py-4">技能名称</th>
                    <th className="text-left px-6 py-4">执行器类型</th>
                    <th className="text-left px-6 py-4">执行模式</th>
                    <th className="text-left px-6 py-4">状态</th>
                    <th className="text-left px-6 py-4">官方</th>
                    <th className="text-left px-6 py-4">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800">
                  {skills.map((skill) => (
                    <tr key={skill.skill_id} className="hover:bg-neutral-800/30">
                      <td className="px-6 py-4">
                        <div className="text-white font-medium">{skill.name}</div>
                        <div className="text-neutral-500 text-xs font-mono mt-1">{skill.skill_id}</div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="px-2 py-1 bg-purple-500/20 text-purple-400 text-xs rounded">
                          {skill.executor_type}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        {skill.execution_mode === 'native' ? (
                          <span className="flex items-center gap-2 text-green-500 text-sm">
                            <Cpu size={14} /> Native
                          </span>
                        ) : (
                          <span className="flex items-center gap-2 text-blue-400 text-sm">
                            <Box size={14} /> Docker
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 text-xs rounded ${
                          skill.status === 'published' ? 'bg-green-500/20 text-green-400' :
                          skill.status === 'pending_review' ? 'bg-yellow-500/20 text-yellow-400' :
                          'bg-neutral-500/20 text-neutral-400'
                        }`}>
                          {skill.status}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        {skill.is_official ? (
                          <span className="flex items-center gap-1 text-amber-500 text-sm">
                            <CheckCircle size={14} /> 是
                          </span>
                        ) : (
                          <span className="text-neutral-500 text-sm">否</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex gap-2">
                          <select
                            value={skill.execution_mode}
                            onChange={(e) => handleOpenModeDialog(skill, e.target.value as "docker" | "native")}
                            disabled={!skill.is_official && skill.execution_mode === 'docker'}
                            className={`px-3 py-1.5 rounded text-xs font-medium bg-neutral-800 border border-neutral-700 text-white ${
                              !skill.is_official && skill.execution_mode === 'docker'
                                ? 'opacity-50 cursor-not-allowed'
                                : 'hover:border-neutral-600'
                            }`}
                            title={!skill.is_official ? '只有官方技能可使用原生执行模式' : ''}
                          >
                            <option value="docker">Docker</option>
                            <option value="native" disabled={!skill.is_official}>Native</option>
                          </select>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 安全提示 */}
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle size={20} className="text-amber-500 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-amber-400 font-medium mb-1">安全提示</h4>
                  <ul className="text-amber-300/80 text-sm space-y-1">
                    <li>• 原生执行模式仅限官方技能使用，非官方技能无法切换</li>
                    <li>• Native 模式在宿主机直接运行，存在安全风险</li>
                    <li>• 所有执行操作都有审计日志记录</li>
                    <li>• 切换执行模式需要填写原因</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ✨ 嵌入模型配置面板 */}
        {!loading && activeTab === 'embedding' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-white">嵌入模型配置</h3>
                <p className="text-neutral-500 text-sm mt-1">配置技能推荐系统的语义向量模型，支持本地 Ollama 或云端嵌入模型。</p>
              </div>
            </div>

            {/* 快速选择卡片 */}
            <div className="grid grid-cols-2 gap-6">
              <div
                onClick={setDefaultEmbedding}
                className={`p-6 rounded-xl border cursor-pointer transition-all ${
                  embeddingSettings.embedding_api_base.includes("host.docker.internal")
                    ? 'bg-emerald-900/20 border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]'
                    : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'
                }`}
              >
                <div className="flex items-center gap-3 mb-3 text-white font-medium">
                  <Server size={22} className="text-emerald-400"/> 本地 Ollama (推荐)
                </div>
                <p className="text-sm text-neutral-400">使用本地 bge-m3 模型，数据不出内网，响应更快。</p>
                <div className="mt-3 text-xs text-emerald-400 font-mono">bge-m3:latest • 1024维</div>
              </div>
              <div
                onClick={setOpenAIEmbedding}
                className={`p-6 rounded-xl border cursor-pointer transition-all ${
                  embeddingSettings.embedding_api_base.includes("api.openai.com")
                    ? 'bg-blue-900/20 border-blue-500 shadow-[0_0_15px_rgba(37,99,235,0.15)]'
                    : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'
                }`}
              >
                <div className="flex items-center gap-3 mb-3 text-white font-medium">
                  <Database size={22} className="text-blue-400"/> OpenAI 云端
                </div>
                <p className="text-sm text-neutral-400">使用 OpenAI text-embedding-3-small，需要 API Key。</p>
                <div className="mt-3 text-xs text-blue-400 font-mono">text-embedding-3-small • 1536维</div>
              </div>
            </div>

            {/* 详细配置表单 */}
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6 space-y-6">
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm text-neutral-400 mb-2 flex items-center gap-2">
                    <Globe size={14}/> API Base URL
                  </label>
                  <input
                    type="text"
                    value={embeddingSettings.embedding_api_base}
                    onChange={(e) => setEmbeddingSettings({...embeddingSettings, embedding_api_base: e.target.value})}
                    placeholder="http://host.docker.internal:11434"
                    className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-lg p-3 outline-none focus:border-emerald-500 transition-all font-mono text-sm"
                  />
                  <p className="text-xs text-neutral-600 mt-2">本地 Ollama 地址或云端 API 端点</p>
                </div>

                <div>
                  <label className="block text-sm text-neutral-400 mb-2 flex items-center gap-2">
                    <Sparkles size={14}/> 嵌入模型名称
                  </label>
                  <input
                    type="text"
                    value={embeddingSettings.embedding_model}
                    onChange={(e) => setEmbeddingSettings({...embeddingSettings, embedding_model: e.target.value})}
                    placeholder="bge-m3:latest"
                    className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-lg p-3 outline-none focus:border-emerald-500 transition-all font-mono text-sm"
                  />
                  <p className="text-xs text-neutral-600 mt-2">
                    本地：bge-m3:latest | OpenAI：text-embedding-3-small
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm text-neutral-400 mb-2 flex items-center gap-2">
                    <Key size={14}/> API Key
                  </label>
                  <input
                    type="text"
                    value={embeddingSettings.embedding_api_key}
                    onChange={(e) => setEmbeddingSettings({...embeddingSettings, embedding_api_key: e.target.value})}
                    placeholder="本地模型填 EMPTY"
                    className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-lg p-3 outline-none focus:border-emerald-500 transition-all font-mono text-sm"
                  />
                  <p className="text-xs text-neutral-600 mt-2">本地模型无需 API Key，云端模型需要填写</p>
                </div>

                <div>
                  <label className="block text-sm text-neutral-400 mb-2 flex items-center gap-2">
                    <Database size={14}/> 向量维度
                  </label>
                  <input
                    type="number"
                    value={embeddingSettings.embedding_dimension}
                    onChange={(e) => setEmbeddingSettings({...embeddingSettings, embedding_dimension: parseInt(e.target.value) || 1024})}
                    className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-lg p-3 outline-none focus:border-emerald-500 transition-all font-mono text-sm"
                  />
                  <p className="text-xs text-neutral-600 mt-2">
                    bge-m3=1024 | text-embedding-3-small=1536 | text-embedding-3-large=3072
                  </p>
                </div>
              </div>
            </div>

            {/* 说明卡片 */}
            <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-5">
              <div className="flex items-start gap-3">
                <Database size={20} className="text-emerald-500 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-emerald-400 font-medium mb-2">使用说明</h4>
                  <ul className="text-emerald-300/80 text-sm space-y-1">
                    <li>• 嵌入模型用于技能推荐系统的语义向量计算</li>
                    <li>• 本地模型（如 bge-m3）响应更快、数据更安全</li>
                    <li>• 云端模型（如 OpenAI）语义理解更强，但需要网络连接和 API Key</li>
                    <li>• <strong className="text-emerald-200">注意：</strong>切换模型后，需要重新计算所有技能的向量索引</li>
                  </ul>
                </div>
              </div>
            </div>

            {/* 保存按钮 */}
            <div className="flex justify-end">
              <button
                onClick={handleSaveEmbeddingSettings}
                disabled={embeddingSaving}
                className={`flex items-center gap-2 px-6 py-3 rounded-lg text-sm font-medium transition-all ${
                  embeddingSuccess
                    ? 'bg-green-600/20 text-green-400 border border-green-500/50'
                    : 'bg-amber-600 hover:bg-amber-500 text-white'
                }`}
              >
                {embeddingSuccess ? (
                  <><CheckCircle size={16} /> 保存成功</>
                ) : embeddingSaving ? (
                  <><RefreshCw size={16} className="animate-spin" /> 保存中...</>
                ) : (
                  <><Save size={16} /> 保存嵌入配置</>
                )}
              </button>
            </div>
          </div>
        )}

        {/* 执行模式切换确认对话框 */}
        {showModeDialog && selectedSkill && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-neutral-900 border border-neutral-700 rounded-xl p-6 w-full max-w-md mx-4">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Settings size={20} className="text-amber-500" />
                切换执行模式
              </h3>

              {pendingMode === 'native' && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4">
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
                    <div className="text-red-400 text-sm">
                      Native 模式将在宿主机直接执行脚本，存在安全风险。请确认该技能为受信任的官方技能。
                    </div>
                  </div>
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <label className="block text-neutral-400 text-sm mb-2">技能名称</label>
                  <div className="text-white">{selectedSkill.name}</div>
                </div>

                <div>
                  <label className="block text-neutral-400 text-sm mb-2">当前模式</label>
                  <div className="text-white">{selectedSkill.execution_mode}</div>
                </div>

                <div>
                  <label className="block text-neutral-400 text-sm mb-2">目标模式</label>
                  <div className={`text-white ${pendingMode === 'native' ? 'text-green-500' : 'text-blue-400'}`}>
                    {pendingMode.toUpperCase()}
                  </div>
                </div>

                <div>
                  <label className="block text-neutral-400 text-sm mb-2">切换原因 <span className="text-red-400">*</span></label>
                  <textarea
                    value={modeReason}
                    onChange={(e) => setModeReason(e.target.value)}
                    placeholder="请输入切换原因..."
                    className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded-lg text-white text-sm focus:outline-none focus:border-amber-500 resize-none"
                    rows={3}
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setShowModeDialog(false)}
                  className="flex-1 px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleExecutionModeChange}
                  disabled={!modeReason.trim()}
                  className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    pendingMode === 'native'
                      ? 'bg-green-600 hover:bg-green-500 text-white'
                      : 'bg-blue-600 hover:bg-blue-500 text-white'
                  } ${!modeReason.trim() ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  确认切换
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Claude 权限管理对话框 */}
        {showClaudeDialog && selectedUserForClaude && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-neutral-900 border border-neutral-700 rounded-xl p-6 w-full max-w-md mx-4">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Bot size={20} className="text-blue-500" />
                Claude Code 权限管理
              </h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-neutral-400 text-sm mb-2">用户</label>
                  <div className="text-white">{selectedUserForClaude.email}</div>
                </div>

                <div>
                  <label className="block text-neutral-400 text-sm mb-2">执行模式权限</label>
                  <div className="space-y-2">
                    {/* 容器模式 - 默认勾选 */}
                    <label className="flex items-center gap-3 p-3 bg-neutral-800 rounded-lg cursor-pointer hover:bg-neutral-700">
                      <input
                        type="checkbox"
                        checked={claudeModes.includes('container')}
                        disabled={true}
                        className="w-4 h-4 rounded border-neutral-600 text-blue-500 focus:ring-blue-500"
                      />
                      <div>
                        <div className="text-white text-sm font-medium">Claude (容器)</div>
                        <div className="text-neutral-500 text-xs">在 Docker 容器内执行，安全隔离</div>
                      </div>
                      <span className="ml-auto text-xs text-neutral-500">默认启用</span>
                    </label>

                    {/* 宿主机模式 - 管理员授权 */}
                    <label className="flex items-center gap-3 p-3 bg-neutral-800 rounded-lg cursor-pointer hover:bg-neutral-700">
                      <input
                        type="checkbox"
                        checked={claudeModes.includes('host')}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setClaudeModes([...claudeModes, 'host']);
                          } else {
                            setClaudeModes(claudeModes.filter(m => m !== 'host'));
                          }
                        }}
                        className="w-4 h-4 rounded border-neutral-600 text-green-500 focus:ring-green-500"
                      />
                      <div>
                        <div className="text-white text-sm font-medium">Claude (宿主机)</div>
                        <div className="text-neutral-500 text-xs">在宿主机直接执行，需要管理员授权</div>
                      </div>
                    </label>
                  </div>
                </div>

                {claudeModes.includes('host') && (
                  <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
                    <div className="flex items-start gap-2">
                      <AlertTriangle size={16} className="text-amber-500 flex-shrink-0 mt-0.5" />
                      <div className="text-amber-400 text-sm">
                        宿主机模式将在服务器直接执行命令，存在安全风险。请确保用户可信。
                      </div>
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-neutral-400 text-sm mb-2">备注</label>
                  <textarea
                    value={claudeNotes}
                    onChange={(e) => setClaudeNotes(e.target.value)}
                    placeholder="授权原因、有效期等备注信息..."
                    className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500 resize-none"
                    rows={2}
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => setShowClaudeDialog(false)}
                  className="flex-1 px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleGrantClaudePermission}
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  确认授权
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
