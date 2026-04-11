/**
 * AI 设置面板组件
 *
 * 设计日期: 2026-03-23
 *
 * 功能：
 * - 配置主模型 API（公有云/本地私有化）
 * - 配置视觉模型（可选独立配置）
 * - 支持热重载
 */

"use client";

import { useState, useEffect } from 'react';
import { fetchAPI } from '@/lib/api';
import {
  Cpu,
  Key,
  Globe,
  Monitor,
  Save,
  CheckCircle2,
  Server,
  Cloud,
  Eye,
  Link2,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

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
// AI 设置面板组件
// ==========================================

export function AIPanel() {
  // --- 主模型状态 ---
  const [settings, setSettings] = useState({
    openai_api_key: "",
    openai_base_url: "",
    default_model: ""
  });

  // --- 视觉模型状态 ---
  const [visionSettings, setVisionSettings] = useState<VisionSettings>({
    use_shared_vision_config: true,
    vision_api_key: "",
    vision_base_url: "",
    vision_model: "qwen3.5-plus"
  });
  const [showVisionConfig, setShowVisionConfig] = useState(false);

  // --- 保存状态 ---
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // 加载配置
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await fetchAPI('/system/settings');
      if (data.status === 'success' && data.data) {
        setSettings({
          openai_api_key: data.data.openai_api_key && !data.data.openai_api_key.startsWith("ollama")
            ? "sk-************************"
            : (data.data.openai_api_key || ""),
          openai_base_url: data.data.openai_base_url,
          default_model: data.data.default_model
        });
        setVisionSettings({
          use_shared_vision_config: data.data.use_shared_vision_config ?? true,
          vision_api_key: data.data.vision_api_key && !data.data.vision_api_key.startsWith("ollama")
            ? "sk-************************"
            : (data.data.vision_api_key || ""),
          vision_base_url: data.data.vision_base_url || "",
          vision_model: data.data.vision_model || "qwen3.5-plus"
        });
      }
    } catch (error) {
      console.error('加载 AI 设置失败:', error);
    }
  };

  // 保存配置
  const handleSave = async () => {
    setIsSaving(true);
    try {
      await fetchAPI('/system/settings', {
        method: 'POST',
        body: JSON.stringify({
          ...settings,
          ...visionSettings
        })
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (error) {
      console.error('保存 AI 设置失败:', error);
    } finally {
      setIsSaving(false);
    }
  };

  // 快速预设
  const setCloudOpenAI = () => setSettings({
    openai_api_key: "",
    openai_base_url: "https://api.openai.com/v1",
    default_model: "gpt-4o-mini"
  });

  const setLocalOllama = () => setSettings({
    openai_api_key: "ollama-local",
    openai_base_url: "http://host.docker.internal:11434/v1",
    default_model: "qwen2.5:7b"
  });

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-6">

        {/* 标题区 */}
        <div className="mb-2">
          <h2 className="text-lg font-semibold text-white mb-1 flex items-center gap-2">
            <Cpu size={20} className="text-blue-400" />
            AI 引擎配置
          </h2>
          <p className="text-sm text-neutral-500">配置底层 AI 模型引擎，支持公有云与私有化本地集群实时热切换。</p>
        </div>

        {/* 部署模式选择 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div
            onClick={setCloudOpenAI}
            className={`p-5 rounded-xl border cursor-pointer transition-all ${
              settings.openai_base_url.includes("api.openai.com")
                ? 'bg-blue-900/20 border-blue-500 shadow-[0_0_15px_rgba(37,99,235,0.15)]'
                : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'
            }`}
          >
            <div className="flex items-center gap-3 mb-2 text-white font-medium">
              <Cloud size={20} className="text-blue-400" />
              公有云 SaaS 模式
            </div>
            <p className="text-xs text-neutral-500">连接 OpenAI 或第三方中转服务，适合非敏感数据的高智商通用计算。</p>
          </div>

          <div
            onClick={setLocalOllama}
            className={`p-5 rounded-xl border cursor-pointer transition-all ${
              settings.openai_base_url.includes("host.docker.internal")
                ? 'bg-emerald-900/20 border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]'
                : 'bg-neutral-900 border-neutral-800 hover:border-neutral-600'
            }`}
          >
            <div className="flex items-center gap-3 mb-2 text-white font-medium">
              <Server size={20} className="text-emerald-400" />
              本地私有化模式
            </div>
            <p className="text-xs text-neutral-500">连接宿主机本地算力。数据绝对隔离，完全不出内网，符合医疗合规要求。</p>
          </div>
        </div>

        {/* 主模型配置 */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6 space-y-5">
          <h3 className="text-sm font-medium text-neutral-300 mb-2">主模型配置</h3>

          <div>
            <label className="flex items-center gap-2 text-xs text-neutral-400 mb-2">
              <Globe size={14} />
              API Base URL
            </label>
            <input
              type="text"
              value={settings.openai_base_url}
              onChange={(e) => setSettings({ ...settings, openai_base_url: e.target.value })}
              className="w-full px-4 py-2.5 bg-neutral-950 border border-neutral-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>

          <div>
            <label className="flex items-center gap-2 text-xs text-neutral-400 mb-2">
              <Monitor size={14} />
              驱动模型 (Model Name)
            </label>
            <input
              type="text"
              value={settings.default_model}
              onChange={(e) => setSettings({ ...settings, default_model: e.target.value })}
              className="w-full px-4 py-2.5 bg-neutral-950 border border-neutral-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>

          <div>
            <label className="flex items-center gap-2 text-xs text-neutral-400 mb-2">
              <Key size={14} />
              API Key
            </label>
            <input
              type="password"
              value={settings.openai_api_key}
              onChange={(e) => setSettings({ ...settings, openai_api_key: e.target.value })}
              className="w-full px-4 py-2.5 bg-neutral-950 border border-neutral-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>
        </div>

        {/* 视觉模型配置（可折叠） */}
        <div>
          <button
            onClick={() => setShowVisionConfig(!showVisionConfig)}
            className="w-full flex items-center justify-between p-4 rounded-xl bg-neutral-900/50 border border-neutral-800 hover:border-neutral-700 transition-all"
          >
            <div className="flex items-center gap-3">
              <Eye size={18} className="text-purple-400" />
              <span className="text-white font-medium">图像识别模型</span>
              <span className="text-xs text-neutral-500">（可选独立配置）</span>
            </div>
            <div className="flex items-center gap-2">
              {visionSettings.use_shared_vision_config ? (
                <span className="text-xs text-emerald-400 bg-emerald-900/30 px-2 py-0.5 rounded">使用主模型</span>
              ) : (
                <span className="text-xs text-purple-400 bg-purple-900/30 px-2 py-0.5 rounded">独立配置</span>
              )}
              {showVisionConfig ? (
                <ChevronUp size={16} className="text-neutral-400" />
              ) : (
                <ChevronDown size={16} className="text-neutral-400" />
              )}
            </div>
          </button>

          {showVisionConfig && (
            <div className="mt-2 bg-neutral-900/30 border border-neutral-800 rounded-xl p-6 space-y-5">
              {/* 共用配置开关 */}
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-neutral-200 flex items-center gap-2">
                    <Link2 size={14} className="text-blue-400" />
                    与主模型共用配置
                  </div>
                  <p className="text-xs text-neutral-500 mt-1">
                    启用后，图像识别将使用主模型的 API 配置。如主模型不支持多模态，请关闭此选项。
                  </p>
                </div>
                <button
                  onClick={() => setVisionSettings({
                    ...visionSettings,
                    use_shared_vision_config: !visionSettings.use_shared_vision_config
                  })}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    visionSettings.use_shared_vision_config ? 'bg-blue-600' : 'bg-neutral-700'
                  }`}
                >
                  <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                    visionSettings.use_shared_vision_config ? 'left-1' : 'left-7'
                  }`} />
                </button>
              </div>

              {/* 独立配置输入框 */}
              {!visionSettings.use_shared_vision_config && (
                <div className="space-y-4 pt-4 border-t border-neutral-800">
                  <div>
                    <label className="flex items-center gap-2 text-xs text-neutral-400 mb-2">
                      <Globe size={14} />
                      视觉模型 API Base URL
                    </label>
                    <input
                      type="text"
                      value={visionSettings.vision_base_url}
                      onChange={(e) => setVisionSettings({ ...visionSettings, vision_base_url: e.target.value })}
                      placeholder="https://api.openai.com/v1"
                      className="w-full px-4 py-2.5 bg-neutral-950 border border-neutral-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-purple-500 transition-colors"
                    />
                  </div>

                  <div>
                    <label className="flex items-center gap-2 text-xs text-neutral-400 mb-2">
                      <Monitor size={14} />
                      视觉模型名称
                    </label>
                    <input
                      type="text"
                      value={visionSettings.vision_model}
                      onChange={(e) => setVisionSettings({ ...visionSettings, vision_model: e.target.value })}
                      placeholder="qwen3.5-plus"
                      className="w-full px-4 py-2.5 bg-neutral-950 border border-neutral-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-purple-500 transition-colors"
                    />
                    <p className="text-xs text-neutral-600 mt-1">
                      推荐模型：qwen-vl-plus, gpt-4o, claude-3-5-sonnet, gemini-1.5-pro
                    </p>
                  </div>

                  <div>
                    <label className="flex items-center gap-2 text-xs text-neutral-400 mb-2">
                      <Key size={14} />
                      视觉模型 API Key
                    </label>
                    <input
                      type="password"
                      value={visionSettings.vision_api_key}
                      onChange={(e) => setVisionSettings({ ...visionSettings, vision_api_key: e.target.value })}
                      placeholder="留空则使用主模型 API Key"
                      className="w-full px-4 py-2.5 bg-neutral-950 border border-neutral-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-purple-500 transition-colors"
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

        {/* 保存按钮 */}
        <div className="flex justify-end pt-4">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-medium transition-all ${
              saveSuccess
                ? 'bg-green-600/20 text-green-400 border border-green-500/50'
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            }`}
          >
            {saveSuccess ? (
              <>
                <CheckCircle2 size={16} />
                热重载成功
              </>
            ) : isSaving ? (
              "正在应用..."
            ) : (
              <>
                <Save size={16} />
                保存并热重载引擎
              </>
            )}
          </button>
        </div>

      </div>
    </div>
  );
}