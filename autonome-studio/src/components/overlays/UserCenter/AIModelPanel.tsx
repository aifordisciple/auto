"use client";

/**
 * AIModelPanel - AI 模型配置面板
 *
 * 用户级 AI 大模型 API 配置：
 * - 主模型配置（对话与推理）
 * - 意图识别模型配置（L1 意图解构，可独立配置或与主模型共用）
 * - 配置源指示器（个人配置 / 系统全局配置）
 * - 快速预设（公有云 SaaS / 本地私有化）
 * - 测试连接 / 恢复默认 / 保存
 */

import { useState, useEffect } from "react";
import {
  Bot, Cloud, Server, Eye, EyeOff, Loader2, CheckCircle2,
  XCircle, RotateCcw, Save, Info, Zap, Brain, Link2, LinkBreak
} from "lucide-react";
import { fetchAPI } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================

interface LLMConfig {
  // 主模型配置
  llm_api_key: string | null;
  llm_base_url: string | null;
  llm_model_name: string | null;
  is_using_user_config: boolean;
  system_base_url: string | null;
  system_model_name: string | null;
  // 意图识别模型配置
  intent_api_key: string | null;
  intent_base_url: string | null;
  intent_model_name: string | null;
  is_using_user_intent_config: boolean;
  system_intent_base_url: string | null;
  system_intent_model_name: string | null;
}

interface TestResult {
  status: "success" | "error";
  message: string;
  latency_ms: number | null;
  model_name: string;
  base_url: string;
}

// ==========================================
// 快速预设
// ==========================================

const PRESETS = {
  saas: {
    label: "公有云 SaaS",
    icon: <Cloud size={16} />,
    description: "OpenAI / Anthropic / DeepSeek 等云服务",
    base_url: "https://api.openai.com/v1",
    model_name: "gpt-4o",
  },
  local: {
    label: "本地私有化",
    icon: <Server size={16} />,
    description: "Ollama / vLLM / LocalAI 等本地部署",
    base_url: "http://host.docker.internal:11434/v1",
    model_name: "qwen2.5:7b",
  },
};

// 意图识别模型快速预设（推荐轻量模型）
const INTENT_PRESETS = {
  saas: {
    label: "公有云轻量模型",
    icon: <Cloud size={16} />,
    description: "gpt-4o-mini / deepseek-chat 等轻量快速模型",
    base_url: "https://api.openai.com/v1",
    model_name: "gpt-4o-mini",
  },
  local: {
    label: "本地轻量模型",
    icon: <Server size={16} />,
    description: "Ollama 小参数模型，延迟低、速度快",
    base_url: "http://host.docker.internal:11434/v1",
    model_name: "qwen2.5:3b",
  },
};

// ==========================================
// 主组件
// ==========================================

export function AIModelPanel() {
  // 主模型表单状态
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelName, setModelName] = useState("");

  // 意图识别模型表单状态
  const [intentApiKey, setIntentApiKey] = useState("");
  const [intentBaseUrl, setIntentBaseUrl] = useState("");
  const [intentModelName, setIntentModelName] = useState("");
  // 是否与主模型共用（默认共用，即不单独配置意图识别模型）
  const [useSharedIntentModel, setUseSharedIntentModel] = useState(true);

  // UI 状态
  const [showApiKey, setShowApiKey] = useState(false);
  const [showIntentApiKey, setShowIntentApiKey] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isTestingIntent, setIsTestingIntent] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [intentTestResult, setIntentTestResult] = useState<TestResult | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  // 配置源状态
  const [isUsingUserConfig, setIsUsingUserConfig] = useState(false);
  const [systemBaseUrl, setSystemBaseUrl] = useState<string | null>(null);
  const [systemModelName, setSystemModelName] = useState<string | null>(null);
  const [isUsingUserIntentConfig, setIsUsingUserIntentConfig] = useState(false);
  const [systemIntentBaseUrl, setSystemIntentBaseUrl] = useState<string | null>(null);
  const [systemIntentModelName, setSystemIntentModelName] = useState<string | null>(null);

  // 📡 加载当前配置
  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const data: LLMConfig = await fetchAPI("/users/me/llm-config");
      // 主模型
      setApiKey(data.llm_api_key || "");
      setBaseUrl(data.llm_base_url || "");
      setModelName(data.llm_model_name || "");
      setIsUsingUserConfig(data.is_using_user_config);
      setSystemBaseUrl(data.system_base_url);
      setSystemModelName(data.system_model_name);
      // 意图识别模型
      setIntentApiKey(data.intent_api_key || "");
      setIntentBaseUrl(data.intent_base_url || "");
      setIntentModelName(data.intent_model_name || "");
      setIsUsingUserIntentConfig(data.is_using_user_intent_config);
      setSystemIntentBaseUrl(data.system_intent_base_url);
      setSystemIntentModelName(data.system_intent_model_name);
      // 如果用户已配置意图识别模型，则关闭"与主模型共用"开关
      setUseSharedIntentModel(!data.is_using_user_intent_config);
    } catch (error) {
      console.error("加载 LLM 配置失败:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // 💾 保存配置
  const handleSave = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    setTestResult(null);
    setIntentTestResult(null);

    try {
      const payload: Record<string, string | null> = {};

      // 主模型 API Key: 如果是脱敏值或空字符串，发 null（清除）
      if (apiKey && !apiKey.startsWith("sk-***")) {
        payload.llm_api_key = apiKey;
      } else if (!apiKey) {
        payload.llm_api_key = null;
      }

      // 主模型 Base URL / Model Name
      payload.llm_base_url = baseUrl || null;
      payload.llm_model_name = modelName || null;

      // 意图识别模型：如果开启"与主模型共用"，则清除所有 intent 字段
      if (useSharedIntentModel) {
        payload.intent_api_key = null;
        payload.intent_base_url = null;
        payload.intent_model_name = null;
      } else {
        // 意图识别 API Key
        if (intentApiKey && !intentApiKey.startsWith("sk-***")) {
          payload.intent_api_key = intentApiKey;
        } else if (!intentApiKey) {
          payload.intent_api_key = null;
        }

        payload.intent_base_url = intentBaseUrl || null;
        payload.intent_model_name = intentModelName || null;
      }

      await fetchAPI("/users/me/llm-config", {
        method: "PUT",
        body: JSON.stringify(payload),
      });

      setSaveMessage("配置已保存");
      await loadConfig();
    } catch (error) {
      setSaveMessage("保存失败，请重试");
      console.error("保存 LLM 配置失败:", error);
    } finally {
      setIsSaving(false);
      setTimeout(() => setSaveMessage(null), 3000);
    }
  };

  // 🧪 测试主模型连接
  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);

    try {
      const payload: Record<string, string | null> = {};

      if (apiKey && !apiKey.startsWith("sk-***")) {
        payload.llm_api_key = apiKey;
      }

      payload.llm_base_url = baseUrl || null;
      payload.llm_model_name = modelName || null;

      const result: TestResult = await fetchAPI("/users/me/llm-config/test", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setTestResult(result);
    } catch (error) {
      setTestResult({
        status: "error",
        message: "请求失败，请检查网络连接",
        latency_ms: null,
        model_name: modelName,
        base_url: baseUrl,
      });
    } finally {
      setIsTesting(false);
    }
  };

  // 🧪 测试意图识别模型连接
  const handleIntentTest = async () => {
    setIsTestingIntent(true);
    setIntentTestResult(null);

    try {
      const payload: Record<string, string | null> = {};

      if (intentApiKey && !intentApiKey.startsWith("sk-***")) {
        payload.intent_api_key = intentApiKey;
      }

      payload.intent_base_url = intentBaseUrl || null;
      payload.intent_model_name = intentModelName || null;

      const result: TestResult = await fetchAPI("/users/me/llm-config/test", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setIntentTestResult(result);
    } catch (error) {
      setIntentTestResult({
        status: "error",
        message: "请求失败，请检查网络连接",
        latency_ms: null,
        model_name: intentModelName,
        base_url: intentBaseUrl,
      });
    } finally {
      setIsTestingIntent(false);
    }
  };

  // 🔄 恢复系统默认
  const handleReset = async () => {
    setIsSaving(true);
    setTestResult(null);
    setIntentTestResult(null);

    try {
      await fetchAPI("/users/me/llm-config", {
        method: "PUT",
        body: JSON.stringify({
          llm_api_key: null,
          llm_base_url: null,
          llm_model_name: null,
          intent_api_key: null,
          intent_base_url: null,
          intent_model_name: null,
        }),
      });

      await loadConfig();
      setSaveMessage("已恢复为系统全局配置");
    } catch (error) {
      setSaveMessage("恢复失败，请重试");
    } finally {
      setIsSaving(false);
      setTimeout(() => setSaveMessage(null), 3000);
    }
  };

  // 🎯 应用快速预设
  const applyPreset = (preset: "saas" | "local") => {
    const p = PRESETS[preset];
    setBaseUrl(p.base_url);
    setModelName(p.model_name);
    setTestResult(null);
  };

  // 🎯 应用意图识别快速预设
  const applyIntentPreset = (preset: "saas" | "local") => {
    const p = INTENT_PRESETS[preset];
    setIntentBaseUrl(p.base_url);
    setIntentModelName(p.model_name);
    setIntentTestResult(null);
  };

  // ==========================================
  // 渲染
  // ==========================================

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-neutral-500" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto w-full p-6 space-y-6">

        {/* ==========================================
            配置源指示器
            ========================================== */}
        <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${
          isUsingUserConfig
            ? "bg-purple-500/5 border-purple-500/20"
            : "bg-blue-500/5 border-blue-500/20"
        }`}>
          <div className={`p-1.5 rounded-md ${
            isUsingUserConfig ? "bg-purple-500/20 text-purple-400" : "bg-blue-500/20 text-blue-400"
          }`}>
            {isUsingUserConfig ? <Zap size={16} /> : <Info size={16} />}
          </div>
          <div>
            <p className={`text-sm font-medium ${
              isUsingUserConfig ? "text-purple-300" : "text-blue-300"
            }`}>
              {isUsingUserConfig ? "使用个人配置" : "使用系统全局配置"}
            </p>
            <p className="text-xs text-neutral-500 mt-0.5">
              {isUsingUserConfig
                ? "当前使用您自定义的 AI 模型配置，优先级高于系统全局配置"
                : "您尚未配置个人模型，当前使用系统全局配置"}
            </p>
          </div>
        </div>

        {/* ==========================================
            快速预设
            ========================================== */}
        <div>
          <h3 className="text-sm font-medium text-neutral-300 mb-3">快速预设</h3>
          <div className="grid grid-cols-2 gap-3">
            {(Object.entries(PRESETS) as [keyof typeof PRESETS, typeof PRESETS.saas][]).map(([key, preset]) => (
              <button
                key={key}
                onClick={() => applyPreset(key)}
                className="flex items-start gap-3 p-3 rounded-lg border border-neutral-800 bg-neutral-900/50 hover:border-neutral-700 hover:bg-neutral-800/50 transition-all text-left"
              >
                <div className={`p-1.5 rounded-md ${
                  key === "saas" ? "bg-blue-500/20 text-blue-400" : "bg-emerald-500/20 text-emerald-400"
                }`}>
                  {preset.icon}
                </div>
                <div>
                  <p className="text-sm font-medium text-neutral-200">{preset.label}</p>
                  <p className="text-xs text-neutral-500 mt-0.5">{preset.description}</p>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* ==========================================
            主模型配置表单
            ========================================== */}
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-neutral-300">主模型配置</h3>

          {/* Base URL */}
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1.5">
              API Base URL
            </label>
            <input
              type="text"
              placeholder="https://api.openai.com/v1"
              className="w-full px-3 py-2.5 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 font-mono"
              value={baseUrl}
              onChange={e => { setBaseUrl(e.target.value); setTestResult(null); }}
            />
            <p className="text-xs text-neutral-600 mt-1">
              OpenAI 兼容的 API 地址，如 https://api.openai.com/v1 或 http://host.docker.internal:11434/v1
            </p>
          </div>

          {/* Model Name */}
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1.5">
              模型名称
            </label>
            <input
              type="text"
              placeholder="gpt-4o"
              className="w-full px-3 py-2.5 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 font-mono"
              value={modelName}
              onChange={e => { setModelName(e.target.value); setTestResult(null); }}
            />
            <p className="text-xs text-neutral-600 mt-1">
              模型标识，如 gpt-4o、claude-3-opus、deepseek-chat、qwen2.5:7b
            </p>
          </div>

          {/* API Key */}
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1.5">
              API Key
            </label>
            <div className="relative">
              <input
                type={showApiKey ? "text" : "password"}
                placeholder="sk-..."
                className="w-full px-3 py-2.5 pr-10 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 font-mono"
                value={apiKey}
                onChange={e => { setApiKey(e.target.value); setTestResult(null); }}
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <p className="text-xs text-neutral-600 mt-1">
              本地模型（Ollama 等）可留空。密钥仅存储在您的账户中，不会泄露给其他用户。
            </p>
          </div>
        </div>

        {/* ==========================================
            意图识别模型配置
            ========================================== */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Brain size={16} className="text-amber-400" />
              <h3 className="text-sm font-medium text-neutral-300">意图识别模型</h3>
            </div>
            {/* 与主模型共用开关 */}
            <button
              onClick={() => {
                setUseSharedIntentModel(!useSharedIntentModel);
                setIntentTestResult(null);
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                useSharedIntentModel
                  ? "bg-purple-500/10 text-purple-300 border border-purple-500/30"
                  : "bg-amber-500/10 text-amber-300 border border-amber-500/30"
              }`}
            >
              {useSharedIntentModel ? <Link2 size={12} /> : <LinkBreak size={12} />}
              {useSharedIntentModel ? "与主模型共用" : "独立配置"}
            </button>
          </div>

          <p className="text-xs text-neutral-500">
            意图识别模型用于解析用户输入的意图类型（L1 解构层），推荐使用轻量快速模型以降低延迟和成本。
            {!useSharedIntentModel && " 未配置的字段将自动从主模型回退。"}
          </p>

          {/* 共用模式下的提示 */}
          {useSharedIntentModel && (
            <div className="p-3 rounded-lg border border-neutral-800 bg-neutral-900/30">
              <div className="flex items-center gap-2">
                <Link2 size={14} className="text-purple-400" />
                <p className="text-xs text-neutral-400">
                  意图识别将使用上方主模型配置。如需使用不同模型（如轻量模型降低延迟），请切换为"独立配置"。
                </p>
              </div>
            </div>
          )}

          {/* 独立配置表单 */}
          {!useSharedIntentModel && (
            <>
              {/* 意图识别快速预设 */}
              <div>
                <h4 className="text-xs font-medium text-neutral-400 mb-2">快速预设</h4>
                <div className="grid grid-cols-2 gap-2">
                  {(Object.entries(INTENT_PRESETS) as [keyof typeof INTENT_PRESETS, typeof INTENT_PRESETS.saas][]).map(([key, preset]) => (
                    <button
                      key={key}
                      onClick={() => applyIntentPreset(key)}
                      className="flex items-start gap-2 p-2.5 rounded-lg border border-neutral-800 bg-neutral-900/50 hover:border-neutral-700 hover:bg-neutral-800/50 transition-all text-left"
                    >
                      <div className={`p-1 rounded-md ${
                        key === "saas" ? "bg-blue-500/20 text-blue-400" : "bg-emerald-500/20 text-emerald-400"
                      }`}>
                        {preset.icon}
                      </div>
                      <div>
                        <p className="text-xs font-medium text-neutral-200">{preset.label}</p>
                        <p className="text-[10px] text-neutral-500 mt-0.5">{preset.description}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Base URL */}
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1.5">
                  API Base URL
                </label>
                <input
                  type="text"
                  placeholder="与主模型共用"
                  className="w-full px-3 py-2.5 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 font-mono"
                  value={intentBaseUrl}
                  onChange={e => { setIntentBaseUrl(e.target.value); setIntentTestResult(null); }}
                />
                <p className="text-xs text-neutral-600 mt-1">
                  留空则使用主模型的 Base URL
                </p>
              </div>

              {/* Model Name */}
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1.5">
                  模型名称
                </label>
                <input
                  type="text"
                  placeholder="gpt-4o-mini"
                  className="w-full px-3 py-2.5 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 font-mono"
                  value={intentModelName}
                  onChange={e => { setIntentModelName(e.target.value); setIntentTestResult(null); }}
                />
                <p className="text-xs text-neutral-600 mt-1">
                  推荐轻量模型，如 gpt-4o-mini、deepseek-chat、qwen2.5:3b
                </p>
              </div>

              {/* API Key */}
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1.5">
                  API Key
                </label>
                <div className="relative">
                  <input
                    type={showIntentApiKey ? "text" : "password"}
                    placeholder="与主模型共用"
                    className="w-full px-3 py-2.5 pr-10 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 font-mono"
                    value={intentApiKey}
                    onChange={e => { setIntentApiKey(e.target.value); setIntentTestResult(null); }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowIntentApiKey(!showIntentApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-neutral-500 hover:text-neutral-300 transition-colors"
                  >
                    {showIntentApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <p className="text-xs text-neutral-600 mt-1">
                  留空则使用主模型的 API Key
                </p>
              </div>

              {/* 意图识别测试结果 */}
              {intentTestResult && (
                <div className={`p-4 rounded-lg border ${
                  intentTestResult.status === "success"
                    ? "bg-emerald-500/5 border-emerald-500/20"
                    : "bg-red-500/5 border-red-500/20"
                }`}>
                  <div className="flex items-center gap-2">
                    {intentTestResult.status === "success" ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    ) : (
                      <XCircle className="w-5 h-5 text-red-400" />
                    )}
                    <div>
                      <p className={`text-sm font-medium ${
                        intentTestResult.status === "success" ? "text-emerald-300" : "text-red-300"
                      }`}>
                        {intentTestResult.message}
                      </p>
                      {intentTestResult.latency_ms !== null && (
                        <p className="text-xs text-neutral-500 mt-0.5">
                         延迟: {intentTestResult.latency_ms}ms | 模型: {intentTestResult.model_name}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* 意图识别测试按钮 */}
              <div className="flex items-center gap-3">
                <button
                  onClick={handleIntentTest}
                  disabled={isTestingIntent || (!intentBaseUrl && !intentModelName)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-800/50 disabled:text-neutral-600 text-neutral-200 text-sm font-medium rounded-md transition-colors"
                >
                  {isTestingIntent ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap size={14} />}
                  测试意图识别连接
                </button>
              </div>
            </>
          )}
        </div>

        {/* ==========================================
            系统回退信息
            ========================================== */}
        {!isUsingUserConfig && (systemBaseUrl || systemModelName) && (
          <div className="p-4 rounded-lg border border-neutral-800 bg-neutral-900/30">
            <h4 className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-3">系统全局配置（回退）</h4>
            <div className="space-y-2 text-sm">
              {systemBaseUrl && (
                <div className="flex items-center gap-2">
                  <span className="text-neutral-500 shrink-0">Base URL:</span>
                  <span className="text-neutral-300 font-mono text-xs truncate">{systemBaseUrl}</span>
                </div>
              )}
              {systemModelName && (
                <div className="flex items-center gap-2">
                  <span className="text-neutral-500 shrink-0">Model:</span>
                  <span className="text-neutral-300 font-mono text-xs">{systemModelName}</span>
                </div>
              )}
              {systemIntentModelName && (
                <div className="flex items-center gap-2">
                  <span className="text-neutral-500 shrink-0">意图识别 Model:</span>
                  <span className="text-neutral-300 font-mono text-xs">{systemIntentModelName}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ==========================================
            主模型测试结果
            ========================================== */}
        {testResult && (
          <div className={`p-4 rounded-lg border ${
            testResult.status === "success"
              ? "bg-emerald-500/5 border-emerald-500/20"
              : "bg-red-500/5 border-red-500/20"
          }`}>
            <div className="flex items-center gap-2">
              {testResult.status === "success" ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              ) : (
                <XCircle className="w-5 h-5 text-red-400" />
              )}
              <div>
                <p className={`text-sm font-medium ${
                  testResult.status === "success" ? "text-emerald-300" : "text-red-300"
                }`}>
                  {testResult.message}
                </p>
                {testResult.latency_ms !== null && (
                  <p className="text-xs text-neutral-500 mt-0.5">
                   延迟: {testResult.latency_ms}ms | 模型: {testResult.model_name}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ==========================================
            操作栏
            ========================================== */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleTest}
            disabled={isTesting || (!baseUrl && !modelName)}
            className="flex items-center gap-2 px-4 py-2.5 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-800/50 disabled:text-neutral-600 text-neutral-200 text-sm font-medium rounded-md transition-colors"
          >
            {isTesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap size={14} />}
            测试主模型
          </button>

          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400 text-white text-sm font-medium rounded-md transition-colors"
          >
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save size={14} />}
            保存配置
          </button>

          {(isUsingUserConfig || isUsingUserIntentConfig) && (
            <button
              onClick={handleReset}
              disabled={isSaving}
              className="flex items-center gap-2 px-4 py-2.5 text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 text-sm rounded-md transition-colors"
            >
              <RotateCcw size={14} />
              恢复系统默认
            </button>
          )}

          {saveMessage && (
            <span className={`text-xs ml-auto ${
              saveMessage.includes("失败") ? "text-red-400" : "text-emerald-400"
            }`}>
              {saveMessage}
            </span>
          )}
        </div>

        {/* ==========================================
            提示信息
            ========================================== */}
        <div className="p-4 rounded-lg border border-neutral-800/50 bg-neutral-900/20">
          <div className="flex items-start gap-2">
            <Bot size={14} className="text-neutral-500 mt-0.5 shrink-0" />
            <div className="text-xs text-neutral-500 space-y-1">
              <p>• 个人配置优先级高于系统全局配置，配置后所有 AI 功能将使用您的模型</p>
              <p>• 意图识别模型推荐使用轻量模型（如 gpt-4o-mini），可降低延迟和成本</p>
              <p>• 清空所有字段并保存，即可回退到系统全局配置</p>
              <p>• 本地模型（Ollama/vLLM）请使用 <code className="text-neutral-400 bg-neutral-800 px-1 rounded">host.docker.internal</code> 代替 localhost</p>
              <p>• API Key 仅存储在您的账户中，不会泄露给其他用户</p>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
