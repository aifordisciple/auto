"use client";
import { useState, useEffect } from "react";
import { Settings, Key, Globe, Cpu, Save, CheckCircle2, Server, Cloud } from "lucide-react";
import { fetchAPI } from "../../lib/api";

export function SettingsCenter() {
  const [settings, setSettings] = useState({ openai_api_key: "", openai_base_url: "", default_model: "" });
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

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

  const handleSave = async () => {
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

  // ✨ 核心：一键切换本地私有化部署预设
  const setLocalOllama = () => {
    setSettings({
      openai_api_key: "ollama-local",
      openai_base_url: "http://host.docker.internal:11434/v1",
      default_model: "qwen2.5:7b"
    });
  };

  // ✨ 一键切换公有云预设
  const setCloudOpenAI = () => {
    setSettings({
      openai_api_key: "",
      openai_base_url: "https://api.openai.com/v1",
      default_model: "gpt-4o-mini"
    });
  };

  return (
    <div className="p-8 h-full flex flex-col max-w-4xl mx-auto w-full">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-2 bg-neutral-800 text-neutral-300 rounded-lg"><Settings size={24} /></div>
        <div>
          <h3 className="text-white font-medium text-lg">系统部署设置 (Deployment)</h3>
          <p className="text-neutral-500 text-sm">配置底层 AI 模型引擎，支持公有云与私有化本地集群实时热切。</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pr-4 space-y-8">
        
        {/* ✨ 部署模式快速切换器 */}
        <div className="grid grid-cols-2 gap-4">
          <div onClick={setCloudOpenAI} className={`p-5 rounded-xl border cursor-pointer transition-all ${settings.openai_base_url.includes("api.openai.com") ? 'bg-blue-900/20 border-blue-500 shadow-[0_0_15px_rgba(37,99,235,0.15)]' : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'}`}>
            <div className="flex items-center gap-3 mb-2 text-white font-medium"><Cloud size={20} className="text-blue-400"/> 公有云 SaaS 模式</div>
            <p className="text-xs text-neutral-500">连接 OpenAI 或第三方中转服务，适合非敏感数据的高智商通用计算。</p>
          </div>
          
          <div onClick={setLocalOllama} className={`p-5 rounded-xl border cursor-pointer transition-all ${settings.openai_base_url.includes("host.docker.internal") ? 'bg-emerald-900/20 border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]' : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'}`}>
            <div className="flex items-center gap-3 mb-2 text-white font-medium"><Server size={20} className="text-emerald-400"/> 本地私有化模式 (On-Premise)</div>
            <p className="text-xs text-neutral-500">连接宿主机本地算力 (如 Ollama)。数据绝对隔离，完全不出内网，符合医疗合规要求。</p>
          </div>
        </div>

        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
          <h4 className="text-white font-medium mb-6 flex items-center gap-2 border-b border-neutral-800 pb-3">
            <Cpu size={16} className={settings.openai_base_url.includes("host.docker.internal") ? "text-emerald-500" : "text-blue-500"} /> AI 核心引擎配置参数
          </h4>
          <div className="space-y-5">
            <div>
              <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Globe size={14}/> API Base URL</label>
              <input type="text" value={settings.openai_base_url} onChange={(e) => setSettings({...settings, openai_base_url: e.target.value})} className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-blue-500 focus:ring-1 transition-all font-mono text-sm" />
            </div>
            <div>
              <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Cpu size={14}/> 驱动模型 (Model Name)</label>
              <input type="text" value={settings.default_model} onChange={(e) => setSettings({...settings, default_model: e.target.value})} className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-blue-500 focus:ring-1 transition-all font-mono text-sm" />
              <p className="text-[10px] text-neutral-600 mt-2">提示: 私有化部署推荐拉取 <code className="text-emerald-500">qwen2.5:7b</code> 或 <code className="text-emerald-500">llama3.1</code> 模型，以获得最佳的工具调用能力。</p>
            </div>
            <div>
              <label className="block text-xs text-neutral-400 mb-2 flex items-center gap-2"><Key size={14}/> API Key</label>
              <input type="password" value={settings.openai_api_key} onChange={(e) => setSettings({...settings, openai_api_key: e.target.value})} className="w-full bg-neutral-950 border border-neutral-700 text-white rounded-md p-2.5 outline-none focus:border-blue-500 focus:ring-1 transition-all font-mono text-sm" />
            </div>
          </div>
        </div>
      </div>

      <div className="pt-6 border-t border-neutral-800 flex justify-end shrink-0 mt-4">
        <button onClick={handleSave} disabled={isSaving} className={`flex items-center gap-2 px-6 py-2.5 rounded-md text-sm font-medium transition-all ${saveSuccess ? 'bg-green-600/20 text-green-400 border border-green-500/50' : 'bg-white text-black hover:bg-neutral-200'}`}>
          {saveSuccess ? <><CheckCircle2 size={16} /> 热重载成功</> : isSaving ? "正在应用算力节点..." : <><Save size={16} /> 保存并热重载引擎</>}
        </button>
      </div>
    </div>
  );
}
