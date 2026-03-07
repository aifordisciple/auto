"use client";
import { useState, useEffect, useCallback } from "react";
import { Settings, Key, Globe, Cpu, Save, CheckCircle2, Server, Cloud, Keyboard, RotateCcw, Monitor } from "lucide-react";
import { fetchAPI } from "../../lib/api";
import { useShortcutStore, Shortcut } from "../../store/useShortcutStore";

export function SettingsCenter() {
  // --- 基础状态 ---
  const [activeTab, setActiveTab] = useState<'ai' | 'shortcuts'>('ai');

  // --- AI 设置状态 ---
  const [settings, setSettings] = useState({ openai_api_key: "", openai_base_url: "", default_model: "" });
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // --- 快捷键设置状态 ---
  const { shortcuts, updateShortcut, resetToDefault } = useShortcutStore();
  const [recordingId, setRecordingId] = useState<string | null>(null);

  useEffect(() => {
    fetchAPI('/api/system/settings').then(data => {
      if (data.status === 'success' && data.data) {
        setSettings({
          openai_api_key: data.data.openai_api_key && !data.data.openai_api_key.startsWith("ollama") ? "sk-************************" : (data.data.openai_api_key || ""),
          openai_base_url: data.data.openai_base_url,
          default_model: data.data.default_model
        });
      }
    });
  }, []);

  const handleSaveAI = async () => {
    setIsSaving(true);
    try {
      await fetchAPI('/api/system/settings', {
        method: 'POST',
        body: JSON.stringify(settings)
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } finally {
      setIsSaving(false);
    }
  };

  const setLocalOllama = () => setSettings({ openai_api_key: "ollama-local", openai_base_url: "http://host.docker.internal:11434/v1", default_model: "qwen2.5:7b" });
  const setCloudOpenAI = () => setSettings({ openai_api_key: "", openai_base_url: "https://api.openai.com/v1", default_model: "gpt-4o-mini" });

  // ✨ 快捷键录制逻辑
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!recordingId) return;

    e.preventDefault();
    e.stopPropagation();

    // 忽略单纯的修饰键按下
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;

    // 退出录制
    if (e.key === 'Escape') {
      setRecordingId(null);
      return;
    }

    // 保存快捷键
    updateShortcut(recordingId, {
      key: e.key.toLowerCase(),
      ctrl: e.ctrlKey,
      meta: e.metaKey,
      shift: e.shiftKey,
      alt: e.altKey
    });
    setRecordingId(null);
  }, [recordingId, updateShortcut]);

  useEffect(() => {
    if (recordingId) {
      window.addEventListener('keydown', handleKeyDown, { capture: true });
      return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
    }
  }, [recordingId, handleKeyDown]);

  // 格式化展示快捷键
  const formatShortcut = (s: Shortcut) => {
    const keys = [];
    if (s.meta) keys.push('⌘'); // Mac Meta
    if (s.ctrl) keys.push('Ctrl');
    if (s.alt) keys.push('Alt');
    if (s.shift) keys.push('Shift');
    keys.push(s.key.toUpperCase());
    return keys.join(' + ');
  };

  return (
    <div className="flex h-full w-full max-w-5xl mx-auto rounded-2xl overflow-hidden bg-[#121212] border border-neutral-800">

      {/* 👈 左侧导航栏 (Sidebar Tabs) */}
      <div className="w-64 bg-neutral-900/50 border-r border-neutral-800 flex flex-col">
        <div className="p-6">
          <h2 className="text-white font-bold text-lg flex items-center gap-2"><Settings size={20}/> 偏好设置</h2>
        </div>
        <div className="flex-1 px-3 space-y-1">
          <button
            onClick={() => setActiveTab('ai')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all ${activeTab === 'ai' ? 'bg-blue-600/20 text-blue-400' : 'text-neutral-400 hover:bg-neutral-800/50 hover:text-neutral-200'}`}
          >
            <Cpu size={18} /> AI 核心引擎
          </button>
          <button
            onClick={() => setActiveTab('shortcuts')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all ${activeTab === 'shortcuts' ? 'bg-purple-600/20 text-purple-400' : 'text-neutral-400 hover:bg-neutral-800/50 hover:text-neutral-200'}`}
          >
            <Keyboard size={18} /> 快捷键与操作
          </button>
        </div>
      </div>

      {/* 👉 右侧内容区 (Content Area) */}
      <div className="flex-1 flex flex-col bg-[#1a1a1c]">
        {activeTab === 'ai' && (
          <div className="p-8 flex-1 overflow-y-auto animate-in fade-in duration-300">
            <h3 className="text-white font-medium text-lg mb-2">部署设置 (Deployment)</h3>
            <p className="text-neutral-500 text-sm mb-8">配置底层 AI 模型引擎，支持公有云与私有化本地集群实时热切。</p>

            <div className="grid grid-cols-2 gap-4 mb-8">
              <div onClick={setCloudOpenAI} className={`p-5 rounded-xl border cursor-pointer transition-all ${settings.openai_base_url.includes("api.openai.com") ? 'bg-blue-900/20 border-blue-500 shadow-[0_0_15px_rgba(37,99,235,0.15)]' : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'}`}>
                <div className="flex items-center gap-3 mb-2 text-white font-medium"><Cloud size={20} className="text-blue-400"/> 公有云 SaaS 模式</div>
                <p className="text-xs text-neutral-500">连接 OpenAI 或第三方中转服务，适合非敏感数据的高智商通用计算。</p>
              </div>
              <div onClick={setLocalOllama} className={`p-5 rounded-xl border cursor-pointer transition-all ${settings.openai_base_url.includes("host.docker.internal") ? 'bg-emerald-900/20 border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]' : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'}`}>
                <div className="flex items-center gap-3 mb-2 text-white font-medium"><Server size={20} className="text-emerald-400"/> 本地私有化模式</div>
                <p className="text-xs text-neutral-500">连接宿主机本地算力。数据绝对隔离，完全不出内网，符合医疗合规要求。</p>
              </div>
            </div>

            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6 space-y-5">
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Globe size={14}/> API Base URL</label>
                <input type="text" value={settings.openai_base_url} onChange={(e) => setSettings({...settings, openai_base_url: e.target.value})} className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-blue-500 transition-all font-mono text-sm" />
              </div>
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Monitor size={14}/> 驱动模型 (Model Name)</label>
                <input type="text" value={settings.default_model} onChange={(e) => setSettings({...settings, default_model: e.target.value})} className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-blue-500 transition-all font-mono text-sm" />
              </div>
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Key size={14}/> API Key</label>
                <input type="password" value={settings.openai_api_key} onChange={(e) => setSettings({...settings, openai_api_key: e.target.value})} className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-blue-500 transition-all font-mono text-sm" />
              </div>
            </div>

            <div className="flex justify-end mt-8">
              <button onClick={handleSaveAI} disabled={isSaving} className={`flex items-center gap-2 px-6 py-2.5 rounded-md text-sm font-medium transition-all ${saveSuccess ? 'bg-green-600/20 text-green-400 border border-green-500/50' : 'bg-white text-black hover:bg-neutral-200'}`}>
                {saveSuccess ? <><CheckCircle2 size={16} /> 热重载成功</> : isSaving ? "正在应用..." : <><Save size={16} /> 保存并热重载引擎</>}
              </button>
            </div>
          </div>
        )}

        {activeTab === 'shortcuts' && (
          <div className="p-8 flex-1 overflow-y-auto animate-in fade-in duration-300">
            <div className="flex items-start justify-between mb-8">
              <div>
                <h3 className="text-white font-medium text-lg mb-2">快捷键管理 (Keybindings)</h3>
                <p className="text-neutral-500 text-sm">自定义全局快捷键以提升生信平台的操作效率。</p>
              </div>
              <button onClick={resetToDefault} className="flex items-center gap-2 text-xs text-neutral-500 hover:text-white px-3 py-1.5 rounded bg-neutral-900 border border-neutral-800 hover:border-neutral-600 transition-colors">
                <RotateCcw size={14}/> 恢复默认
              </button>
            </div>

            <div className="space-y-3">
              {Object.values(shortcuts).map((sc) => {
                const isRecording = recordingId === sc.id;
                return (
                  <div key={sc.id} className={`flex items-center justify-between p-4 rounded-xl border transition-all ${isRecording ? 'bg-purple-900/10 border-purple-500/50 shadow-[0_0_10px_rgba(168,85,247,0.1)]' : 'bg-neutral-900 border-neutral-800 hover:border-neutral-700'}`}>
                    <div>
                      <div className="text-sm font-medium text-neutral-200">{sc.name}</div>
                      <div className="text-xs text-neutral-500 mt-0.5">{sc.description}</div>
                    </div>
                    <button
                      onClick={() => setRecordingId(isRecording ? null : sc.id)}
                      className={`min-w-[120px] px-3 py-1.5 rounded-md text-xs font-mono font-medium tracking-wide border transition-all ${isRecording ? 'bg-purple-600 text-white border-purple-500 animate-pulse' : 'bg-neutral-950 text-neutral-300 border-neutral-700 hover:border-neutral-500 hover:bg-neutral-800'}`}
                    >
                      {isRecording ? '按下组合键... (Esc 取消)' : formatShortcut(sc)}
                    </button>
                  </div>
                );
              })}
            </div>

            <div className="mt-6 p-4 rounded-lg bg-blue-900/10 border border-blue-900/30">
              <p className="text-xs text-blue-400 leading-relaxed">
                <strong className="font-semibold text-blue-300">💡 录制提示：</strong><br/>
                点击需要修改的快捷键，然后直接在键盘上按下你想要的组合（如 <code>Ctrl + K</code>）。系统会自动过滤掉与浏览器底层的冲突。<br/>
                录制过程中按下 <code>Esc</code> 键可取消修改。
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
