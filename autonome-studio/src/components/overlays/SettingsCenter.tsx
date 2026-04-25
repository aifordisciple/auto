"use client";
import { useState, useEffect, useCallback } from "react";
import { Settings, Key, Globe, Cpu, Save, CheckCircle2, Server, Cloud, Keyboard, RotateCcw, Monitor, Eye, Link2, ChevronDown, ChevronUp, Database, Sparkles, Zap } from "lucide-react";
import { fetchAPI } from "../../lib/api";
import { useShortcutStore, Shortcut } from "../../store/useShortcutStore";

// ==========================================
// 视觉模型配置接口
// ==========================================
interface VisionSettings {
  use_shared_vision_config: boolean;
  vision_api_key: string;
  vision_base_url: string;
  vision_model: string;
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

export function SettingsCenter() {
  // --- 基础状态 ---
  const [activeTab, setActiveTab] = useState<'ai' | 'embedding' | 'shortcuts'>('ai');

  // --- 思考模型设置状态（原"主模型"） ---
  const [thinkingSettings, setThinkingSettings] = useState({
    thinking_api_key: "",
    thinking_base_url: "",
    thinking_model: ""
  });

  // --- 极速模型设置状态（原"意图识别模型"） ---
  const [fastSettings, setFastSettings] = useState({
    fast_api_key: "",
    fast_base_url: "",
    fast_model: ""
  });

  // --- 视觉模型设置状态 ---
  const [visionSettings, setVisionSettings] = useState<VisionSettings>({
    use_shared_vision_config: true,
    vision_api_key: "",
    vision_base_url: "",
    vision_model: "qwen3.5-plus"
  });
  const [showVisionConfig, setShowVisionConfig] = useState(false);

  // --- 嵌入模型设置状态 ---
  const [embeddingSettings, setEmbeddingSettings] = useState<EmbeddingSettings>({
    embedding_api_base: "http://host.docker.internal:11434",
    embedding_model: "bge-m3:latest",
    embedding_api_key: "EMPTY",
    embedding_dimension: 1024
  });

  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // --- 快捷键设置状态 ---
  const { shortcuts, updateShortcut, resetToDefault } = useShortcutStore();
  const [recordingId, setRecordingId] = useState<string | null>(null);

  useEffect(() => {
    fetchAPI('/api/system/settings').then(data => {
      if (data.status === 'success' && data.data) {
        setThinkingSettings({
          thinking_api_key: data.data.thinking_api_key && !data.data.thinking_api_key.startsWith("ollama") ? "sk-************************" : (data.data.thinking_api_key || ""),
          thinking_base_url: data.data.thinking_base_url || "",
          thinking_model: data.data.thinking_model || ""
        });
        // 加载极速模型配置
        setFastSettings({
          fast_api_key: data.data.fast_api_key && !data.data.fast_api_key.startsWith("ollama") ? "sk-************************" : (data.data.fast_api_key || ""),
          fast_base_url: data.data.fast_base_url || "",
          fast_model: data.data.fast_model || ""
        });
        // 加载视觉模型配置
        setVisionSettings({
          use_shared_vision_config: data.data.use_shared_vision_config ?? true,
          vision_api_key: data.data.vision_api_key && !data.data.vision_api_key.startsWith("ollama") ? "sk-************************" : (data.data.vision_api_key || ""),
          vision_base_url: data.data.vision_base_url || "",
          vision_model: data.data.vision_model || "qwen3.5-plus"
        });
        // 加载嵌入模型配置
        setEmbeddingSettings({
          embedding_api_base: data.data.embedding_api_base || "http://host.docker.internal:11434",
          embedding_model: data.data.embedding_model || "bge-m3:latest",
          embedding_api_key: data.data.embedding_api_key || "EMPTY",
          embedding_dimension: data.data.embedding_dimension || 1024
        });
      }
    });
  }, []);

  const handleSaveAI = async () => {
    setIsSaving(true);
    try {
      // 合并思考模型、极速模型和视觉模型配置
      const payload = {
        ...thinkingSettings,
        ...fastSettings,
        ...visionSettings
      };
      await fetchAPI('/api/system/settings', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } finally {
      setIsSaving(false);
    }
  };

  // 保存嵌入模型配置
  const handleSaveEmbedding = async () => {
    setIsSaving(true);
    try {
      await fetchAPI('/api/system/settings', {
        method: 'POST',
        body: JSON.stringify(embeddingSettings)
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } finally {
      setIsSaving(false);
    }
  };

  const setLocalOllama = () => setThinkingSettings({ thinking_api_key: "ollama-local", thinking_base_url: "http://host.docker.internal:11434/v1", thinking_model: "qwen2.5:7b" });
  const setCloudOpenAI = () => setThinkingSettings({ thinking_api_key: "", thinking_base_url: "https://api.openai.com/v1", thinking_model: "gpt-4o-mini" });

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
    // 跨平台录制：Mac 上按 ⌘Cmd 或 Windows 上按 Ctrl 时，统一存为 metaOrCtrl
    const hasMetaOrCtrl = e.metaKey || e.ctrlKey;
    updateShortcut(recordingId, {
      key: e.key.toLowerCase(),
      metaOrCtrl: hasMetaOrCtrl || undefined,
      // metaOrCtrl 优先，清除单独的 meta/ctrl 避免冲突
      meta: hasMetaOrCtrl ? undefined : (e.metaKey || undefined),
      ctrl: hasMetaOrCtrl ? undefined : (e.ctrlKey || undefined),
      shift: e.shiftKey || undefined,
      alt: e.altKey || undefined
    });
    setRecordingId(null);
  }, [recordingId, updateShortcut]);

  useEffect(() => {
    if (recordingId) {
      window.addEventListener('keydown', handleKeyDown, { capture: true });
      return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
    }
  }, [recordingId, handleKeyDown]);

  // 格式化展示快捷键（根据平台动态显示修饰键符号）
  const isMac = typeof window !== 'undefined' && navigator.platform.toLowerCase().includes('mac');
  const formatShortcut = (s: Shortcut) => {
    const keys = [];
    if (s.metaOrCtrl) {
      keys.push(isMac ? '⌘' : 'Ctrl');
    } else {
      if (s.meta) keys.push(isMac ? '⌘' : 'Win');
      if (s.ctrl) keys.push('Ctrl');
    }
    if (s.alt) keys.push(isMac ? '⌥' : 'Alt');
    if (s.shift) keys.push(isMac ? '⇧' : 'Shift');
    keys.push(s.key.toUpperCase());
    return keys.join(isMac ? '' : ' + ');
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
            onClick={() => setActiveTab('embedding')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all ${activeTab === 'embedding' ? 'bg-emerald-600/20 text-emerald-400' : 'text-neutral-400 hover:bg-neutral-800/50 hover:text-neutral-200'}`}
          >
            <Database size={18} /> 嵌入模型配置
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
              <div onClick={setCloudOpenAI} className={`p-5 rounded-xl border cursor-pointer transition-all ${thinkingSettings.thinking_base_url.includes("api.openai.com") ? 'bg-blue-900/20 border-blue-500 shadow-[0_0_15px_rgba(37,99,235,0.15)]' : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'}`}>
                <div className="flex items-center gap-3 mb-2 text-white font-medium"><Cloud size={20} className="text-blue-400"/> 公有云 SaaS 模式</div>
                <p className="text-xs text-neutral-500">连接 OpenAI 或第三方中转服务，适合非敏感数据的高智商通用计算。</p>
              </div>
              <div onClick={setLocalOllama} className={`p-5 rounded-xl border cursor-pointer transition-all ${thinkingSettings.thinking_base_url.includes("host.docker.internal") ? 'bg-emerald-900/20 border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]' : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'}`}>
                <div className="flex items-center gap-3 mb-2 text-white font-medium"><Server size={20} className="text-emerald-400"/> 本地私有化模式</div>
                <p className="text-xs text-neutral-500">连接宿主机本地算力。数据绝对隔离，完全不出内网，符合医疗合规要求。</p>
              </div>
            </div>

            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6 space-y-5">
              <h4 className="text-sm font-medium text-white flex items-center gap-2"><Sparkles size={14} className="text-blue-400"/> 思考模型配置</h4>
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Globe size={14}/> API Base URL</label>
                <input type="text" value={thinkingSettings.thinking_base_url} onChange={(e) => setThinkingSettings({...thinkingSettings, thinking_base_url: e.target.value})} className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-blue-500 transition-all font-mono text-sm" />
              </div>
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Monitor size={14}/> 思考模型 (Model Name)</label>
                <input type="text" value={thinkingSettings.thinking_model} onChange={(e) => setThinkingSettings({...thinkingSettings, thinking_model: e.target.value})} className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-blue-500 transition-all font-mono text-sm" />
              </div>
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Key size={14}/> API Key</label>
                <input type="password" value={thinkingSettings.thinking_api_key} onChange={(e) => setThinkingSettings({...thinkingSettings, thinking_api_key: e.target.value})} className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-blue-500 transition-all font-mono text-sm" />
              </div>
            </div>

            {/* ==========================================
                极速模型配置区域（原"意图识别模型"）
                用于意图识别和日常对话，未配置时回退到思考模型
                ========================================== */}
            <div className="mt-6 bg-neutral-900 border border-neutral-800 rounded-xl p-6 space-y-5">
              <h4 className="text-sm font-medium text-white flex items-center gap-2"><Zap size={14} className="text-emerald-400"/> 极速模型配置</h4>
              <p className="text-xs text-neutral-500">用于意图识别和日常对话，未配置时自动回退到思考模型。</p>
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Globe size={14}/> API Base URL</label>
                <input type="text" value={fastSettings.fast_base_url} onChange={(e) => setFastSettings({...fastSettings, fast_base_url: e.target.value})} placeholder="留空则使用思考模型配置" className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-emerald-500 transition-all font-mono text-sm" />
              </div>
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Monitor size={14}/> 极速模型 (Model Name)</label>
                <input type="text" value={fastSettings.fast_model} onChange={(e) => setFastSettings({...fastSettings, fast_model: e.target.value})} placeholder="留空则使用思考模型配置" className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-emerald-500 transition-all font-mono text-sm" />
              </div>
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Key size={14}/> API Key</label>
                <input type="password" value={fastSettings.fast_api_key} onChange={(e) => setFastSettings({...fastSettings, fast_api_key: e.target.value})} placeholder="留空则使用思考模型 API Key" className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-emerald-500 transition-all font-mono text-sm" />
              </div>
            </div>

            {/* ==========================================
                ✨ 视觉模型配置区域
                用于配置独立的图像识别模型
                ========================================== */}
            <div className="mt-8">
              {/* 可折叠的标题栏 */}
              <button
                onClick={() => setShowVisionConfig(!showVisionConfig)}
                className="w-full flex items-center justify-between p-4 rounded-xl bg-neutral-900 border border-neutral-800 hover:border-neutral-700 transition-all"
              >
                <div className="flex items-center gap-3">
                  <Eye size={18} className="text-purple-400"/>
                  <span className="text-white font-medium">图像识别模型</span>
                  <span className="text-xs text-neutral-500">（可选独立配置）</span>
                </div>
                <div className="flex items-center gap-2">
                  {visionSettings.use_shared_vision_config ? (
                    <span className="text-xs text-emerald-400 bg-emerald-900/30 px-2 py-0.5 rounded">使用主模型</span>
                  ) : (
                    <span className="text-xs text-purple-400 bg-purple-900/30 px-2 py-0.5 rounded">独立配置</span>
                  )}
                  {showVisionConfig ? <ChevronUp size={16} className="text-neutral-400"/> : <ChevronDown size={16} className="text-neutral-400"/>}
                </div>
              </button>

              {/* 展开后的配置内容 */}
              {showVisionConfig && (
                <div className="mt-2 bg-neutral-900/50 border border-neutral-800 rounded-xl p-6 space-y-5 animate-in fade-in duration-200">
                  {/* 使用共用配置开关 */}
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm text-neutral-200 flex items-center gap-2">
                        <Link2 size={14} className="text-blue-400"/>
                        与主模型共用配置
                      </div>
                      <p className="text-xs text-neutral-500 mt-1">
                        启用后，图像识别将使用主模型的 API 配置。如主模型不支持多模态，请关闭此选项。
                      </p>
                    </div>
                    <button
                      onClick={() => setVisionSettings({...visionSettings, use_shared_vision_config: !visionSettings.use_shared_vision_config})}
                      className={`relative w-12 h-6 rounded-full transition-colors ${visionSettings.use_shared_vision_config ? 'bg-blue-600' : 'bg-neutral-700'}`}
                    >
                      <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${visionSettings.use_shared_vision_config ? 'left-1' : 'left-7'}`}></div>
                    </button>
                  </div>

                  {/* 独立配置输入框（仅在关闭共用配置时显示） */}
                  {!visionSettings.use_shared_vision_config && (
                    <div className="space-y-4 pt-2 border-t border-neutral-800">
                      <div>
                        <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2">
                          <Globe size={14}/> 视觉模型 API Base URL
                        </label>
                        <input
                          type="text"
                          value={visionSettings.vision_base_url}
                          onChange={(e) => setVisionSettings({...visionSettings, vision_base_url: e.target.value})}
                          placeholder="https://api.openai.com/v1"
                          className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-purple-500 transition-all font-mono text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2">
                          <Monitor size={14}/> 视觉模型名称
                        </label>
                        <input
                          type="text"
                          value={visionSettings.vision_model}
                          onChange={(e) => setVisionSettings({...visionSettings, vision_model: e.target.value})}
                          placeholder="qwen3.5-plus"
                          className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-purple-500 transition-all font-mono text-sm"
                        />
                        <p className="text-xs text-neutral-600 mt-1">
                          推荐模型：qwen-vl-plus, gpt-4o, claude-3-5-sonnet, gemini-1.5-pro
                        </p>
                      </div>
                      <div>
                        <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2">
                          <Key size={14}/> 视觉模型 API Key
                        </label>
                        <input
                          type="password"
                          value={visionSettings.vision_api_key}
                          onChange={(e) => setVisionSettings({...visionSettings, vision_api_key: e.target.value})}
                          placeholder="留空则使用主模型 API Key"
                          className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-purple-500 transition-all font-mono text-sm"
                        />
                      </div>
                    </div>
                  )}

                  {/* 提示信息 */}
                  <div className="p-3 rounded-lg bg-purple-900/10 border border-purple-900/30">
                    <p className="text-xs text-purple-300 leading-relaxed">
                      <strong className="font-semibold">💡 使用场景：</strong>
                      当您的主模型不支持图像识别（如 GLM5、某些本地模型）时，可以配置独立的视觉模型。
                      系统会在检测到用户上传图片时，自动切换到视觉模型进行处理。
                    </p>
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end mt-8">
              <button onClick={handleSaveAI} disabled={isSaving} className={`flex items-center gap-2 px-6 py-2.5 rounded-md text-sm font-medium transition-all ${saveSuccess ? 'bg-green-600/20 text-green-400 border border-green-500/50' : 'bg-white text-black hover:bg-neutral-200'}`}>
                {saveSuccess ? <><CheckCircle2 size={16} /> 热重载成功</> : isSaving ? "正在应用..." : <><Save size={16} /> 保存并热重载引擎</>}
              </button>
            </div>
          </div>
        )}

        {activeTab === 'embedding' && (
          <div className="p-8 flex-1 overflow-y-auto animate-in fade-in duration-300">
            <h3 className="text-white font-medium text-lg mb-2">嵌入模型配置 (Embedding)</h3>
            <p className="text-neutral-500 text-sm mb-8">配置技能推荐系统的语义向量模型，支持本地 Ollama 或云端嵌入模型。</p>

            {/* 快速选择卡片 */}
            <div className="grid grid-cols-2 gap-4 mb-8">
              <div
                onClick={setDefaultEmbedding}
                className={`p-5 rounded-xl border cursor-pointer transition-all ${embeddingSettings.embedding_api_base.includes("host.docker.internal") ? 'bg-emerald-900/20 border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]' : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'}`}
              >
                <div className="flex items-center gap-3 mb-2 text-white font-medium">
                  <Server size={20} className="text-emerald-400"/> 本地 Ollama
                </div>
                <p className="text-xs text-neutral-500">使用本地 bge-m3 模型，数据不出内网，响应更快。</p>
              </div>
              <div
                onClick={setOpenAIEmbedding}
                className={`p-5 rounded-xl border cursor-pointer transition-all ${embeddingSettings.embedding_api_base.includes("api.openai.com") ? 'bg-blue-900/20 border-blue-500 shadow-[0_0_15px_rgba(37,99,235,0.15)]' : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'}`}
              >
                <div className="flex items-center gap-3 mb-2 text-white font-medium">
                  <Cloud size={20} className="text-blue-400"/> OpenAI 云端
                </div>
                <p className="text-xs text-neutral-500">使用 OpenAI text-embedding-3-small，需要 API Key。</p>
              </div>
            </div>

            {/* 详细配置表单 */}
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6 space-y-5">
              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2">
                  <Globe size={14}/> API Base URL
                </label>
                <input
                  type="text"
                  value={embeddingSettings.embedding_api_base}
                  onChange={(e) => setEmbeddingSettings({...embeddingSettings, embedding_api_base: e.target.value})}
                  placeholder="http://host.docker.internal:11434"
                  className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-emerald-500 transition-all font-mono text-sm"
                />
                <p className="text-xs text-neutral-600 mt-1">本地 Ollama 地址或云端 API 端点</p>
              </div>

              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2">
                  <Sparkles size={14}/> 嵌入模型名称
                </label>
                <input
                  type="text"
                  value={embeddingSettings.embedding_model}
                  onChange={(e) => setEmbeddingSettings({...embeddingSettings, embedding_model: e.target.value})}
                  placeholder="bge-m3:latest"
                  className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-emerald-500 transition-all font-mono text-sm"
                />
                <p className="text-xs text-neutral-600 mt-1">
                  本地推荐：bge-m3:latest, nomic-embed-text | OpenAI：text-embedding-3-small
                </p>
              </div>

              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2">
                  <Key size={14}/> API Key
                </label>
                <input
                  type="text"
                  value={embeddingSettings.embedding_api_key}
                  onChange={(e) => setEmbeddingSettings({...embeddingSettings, embedding_api_key: e.target.value})}
                  placeholder="本地模型填 EMPTY"
                  className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-emerald-500 transition-all font-mono text-sm"
                />
                <p className="text-xs text-neutral-600 mt-1">本地模型无需 API Key，云端模型需要填写</p>
              </div>

              <div>
                <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2">
                  <Database size={14}/> 向量维度
                </label>
                <input
                  type="number"
                  value={embeddingSettings.embedding_dimension}
                  onChange={(e) => setEmbeddingSettings({...embeddingSettings, embedding_dimension: parseInt(e.target.value) || 1024})}
                  className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-emerald-500 transition-all font-mono text-sm"
                />
                <p className="text-xs text-neutral-600 mt-1">
                  bge-m3 = 1024 | text-embedding-3-small = 1536 | text-embedding-3-large = 3072
                </p>
              </div>
            </div>

            {/* 说明卡片 */}
            <div className="mt-6 p-4 rounded-lg bg-emerald-900/10 border border-emerald-900/30">
              <p className="text-xs text-emerald-300 leading-relaxed">
                <strong className="font-semibold">💡 使用说明：</strong><br/>
                嵌入模型用于技能推荐系统的语义向量计算。本地模型（如 bge-m3）响应更快、数据更安全；<br/>
                云端模型（如 OpenAI text-embedding-3-small）语义理解更强，但需要网络连接和 API Key。<br/>
                <strong className="text-emerald-200">注意：</strong>切换模型后，需要重新计算所有技能的向量索引。
              </p>
            </div>

            <div className="flex justify-end mt-8">
              <button
                onClick={handleSaveEmbedding}
                disabled={isSaving}
                className={`flex items-center gap-2 px-6 py-2.5 rounded-md text-sm font-medium transition-all ${saveSuccess ? 'bg-green-600/20 text-green-400 border border-green-500/50' : 'bg-white text-black hover:bg-neutral-200'}`}
              >
                {saveSuccess ? <><CheckCircle2 size={16} /> 保存成功</> : isSaving ? "正在保存..." : <><Save size={16} /> 保存嵌入配置</>}
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
