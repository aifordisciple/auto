"use client";

/**
 * AIModelPanel - AI 模型配置面板
 *
 * 用户级 AI 大模型 API 配置：
 * - 极速模型配置（意图识别、日常对话）
 * - 思考模型配置（深度思考对话）
 * - 配置源指示器（个人配置 / 系统全局配置）
 * - 快速预设（SaaS 旗舰/轻量 / 本地旗舰/轻量）
 * - 测试连接 / 恢复默认 / 保存
 */

import { useState, useEffect } from "react";
import {
  Bot, Cloud, Server, Eye, EyeOff, Loader2, CheckCircle2,
  XCircle, RotateCcw, Save, Info, Zap, Brain, Dna
} from "lucide-react";
import { fetchAPI } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================

interface LLMConfig {
  // 思考模型配置
  thinking_api_key: string | null;
  thinking_base_url: string | null;
  thinking_model_name: string | null;
  is_using_user_thinking_config: boolean;
  system_thinking_base_url: string | null;
  system_thinking_model_name: string | null;
  // 极速模型配置
  fast_api_key: string | null;
  fast_base_url: string | null;
  fast_model_name: string | null;
  is_using_user_fast_config: boolean;
  system_fast_base_url: string | null;
  system_fast_model_name: string | null;
  // 嵌入模型配置
  embedding_api_key: string | null;
  embedding_base_url: string | null;
  embedding_model_name: string | null;
  is_using_user_embedding_config: boolean;
  system_embedding_base_url: string | null;
  system_embedding_model_name: string | null;
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

// 思考模型预设（推荐旗舰模型，深度推理）
const THINKING_PRESETS = {
  saas: {
    label: "SaaS 旗舰模型",
    icon: <Cloud size={16} />,
    description: "gpt-4o / claude-3-opus 等旗舰模型",
    base_url: "https://api.openai.com/v1",
    model_name: "gpt-4o",
  },
  local: {
    label: "本地旗舰模型",
    icon: <Server size={16} />,
    description: "Ollama 大参数模型，深度推理",
    base_url: "http://host.docker.internal:11434/v1",
    model_name: "qwen3:32b",
  },
};

// 极速模型预设（推荐轻量模型，低延迟）
const FAST_PRESETS = {
  saas: {
    label: "SaaS 轻量模型",
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
    model_name: "qwen3:8b",
  },
};

// 嵌入模型预设（向量检索用）
const EMBEDDING_PRESETS = {
  saas: {
    label: "OpenAI 嵌入模型",
    icon: <Cloud size={16} />,
    description: "text-embedding-3-large，3072维",
    base_url: "https://api.openai.com/v1",
    model_name: "text-embedding-3-large",
  },
  local: {
    label: "本地 BGE 模型",
    icon: <Server size={16} />,
    description: "bge-m3，1024维，Ollama 运行",
    base_url: "http://host.docker.internal:11434/v1",
    model_name: "bge-m3",
  },
};

// ==========================================
// 主组件
// ==========================================

export function AIModelPanel() {
  // 思考模型表单状态
  const [thinkingApiKey, setThinkingApiKey] = useState("");
  const [thinkingBaseUrl, setThinkingBaseUrl] = useState("");
  const [thinkingModelName, setThinkingModelName] = useState("");

  // 极速模型表单状态
  const [fastApiKey, setFastApiKey] = useState("");
  const [fastBaseUrl, setFastBaseUrl] = useState("");
  const [fastModelName, setFastModelName] = useState("");

  // 嵌入模型表单状态
  const [embeddingApiKey, setEmbeddingApiKey] = useState("");
  const [embeddingBaseUrl, setEmbeddingBaseUrl] = useState("");
  const [embeddingModelName, setEmbeddingModelName] = useState("");

  // UI 状态
  const [showThinkingApiKey, setShowThinkingApiKey] = useState(false);
  const [showFastApiKey, setShowFastApiKey] = useState(false);
  const [showEmbeddingApiKey, setShowEmbeddingApiKey] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTestingThinking, setIsTestingThinking] = useState(false);
  const [isTestingFast, setIsTestingFast] = useState(false);
  const [thinkingTestResult, setThinkingTestResult] = useState<TestResult | null>(null);
  const [fastTestResult, setFastTestResult] = useState<TestResult | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  // 配置源状态
  const [isUsingUserThinkingConfig, setIsUsingUserThinkingConfig] = useState(false);
  const [systemThinkingBaseUrl, setSystemThinkingBaseUrl] = useState<string | null>(null);
  const [systemThinkingModelName, setSystemThinkingModelName] = useState<string | null>(null);
  const [isUsingUserFastConfig, setIsUsingUserFastConfig] = useState(false);
  const [systemFastBaseUrl, setSystemFastBaseUrl] = useState<string | null>(null);
  const [systemFastModelName, setSystemFastModelName] = useState<string | null>(null);
  const [isUsingUserEmbeddingConfig, setIsUsingUserEmbeddingConfig] = useState(false);
  const [systemEmbeddingBaseUrl, setSystemEmbeddingBaseUrl] = useState<string | null>(null);
  const [systemEmbeddingModelName, setSystemEmbeddingModelName] = useState<string | null>(null);

  // 加载当前配置
  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const data: LLMConfig = await fetchAPI("/users/me/llm-config");
      // 思考模型
      setThinkingApiKey(data.thinking_api_key || "");
      setThinkingBaseUrl(data.thinking_base_url || "");
      setThinkingModelName(data.thinking_model_name || "");
      setIsUsingUserThinkingConfig(data.is_using_user_thinking_config);
      setSystemThinkingBaseUrl(data.system_thinking_base_url);
      setSystemThinkingModelName(data.system_thinking_model_name);
      // 极速模型
      setFastApiKey(data.fast_api_key || "");
      setFastBaseUrl(data.fast_base_url || "");
      setFastModelName(data.fast_model_name || "");
      setIsUsingUserFastConfig(data.is_using_user_fast_config);
      setSystemFastBaseUrl(data.system_fast_base_url);
      setSystemFastModelName(data.system_fast_model_name);
      // 嵌入模型
      setEmbeddingApiKey(data.embedding_api_key || "");
      setEmbeddingBaseUrl(data.embedding_base_url || "");
      setEmbeddingModelName(data.embedding_model_name || "");
      setIsUsingUserEmbeddingConfig(data.is_using_user_embedding_config);
      setSystemEmbeddingBaseUrl(data.system_embedding_base_url);
      setSystemEmbeddingModelName(data.system_embedding_model_name);
    } catch (error) {
      console.error("加载 LLM 配置失败:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // 保存配置
  const handleSave = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    setThinkingTestResult(null);
    setFastTestResult(null);

    try {
      const payload: Record<string, string | null> = {};

      // 思考模型 API Key: 如果是脱敏值或空字符串，发 null（清除）
      if (thinkingApiKey && !thinkingApiKey.startsWith("sk-***")) {
        payload.thinking_api_key = thinkingApiKey;
      } else if (!thinkingApiKey) {
        payload.thinking_api_key = null;
      }

      // 思考模型 Base URL / Model Name
      payload.thinking_base_url = thinkingBaseUrl || null;
      payload.thinking_model_name = thinkingModelName || null;

      // 极速模型 API Key
      if (fastApiKey && !fastApiKey.startsWith("sk-***")) {
        payload.fast_api_key = fastApiKey;
      } else if (!fastApiKey) {
        payload.fast_api_key = null;
      }

      // 极速模型 Base URL / Model Name
      payload.fast_base_url = fastBaseUrl || null;
      payload.fast_model_name = fastModelName || null;

      // 嵌入模型 API Key
      if (embeddingApiKey && !embeddingApiKey.startsWith("sk-***")) {
        payload.embedding_api_key = embeddingApiKey;
      } else if (!embeddingApiKey) {
        payload.embedding_api_key = null;
      }

      // 嵌入模型 Base URL / Model Name
      payload.embedding_base_url = embeddingBaseUrl || null;
      payload.embedding_model_name = embeddingModelName || null;

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

  // 测试思考模型连接
  const handleThinkingTest = async () => {
    setIsTestingThinking(true);
    setThinkingTestResult(null);

    try {
      const payload: Record<string, string | null> = {};

      if (thinkingApiKey && !thinkingApiKey.startsWith("sk-***")) {
        payload.thinking_api_key = thinkingApiKey;
      }

      payload.thinking_base_url = thinkingBaseUrl || null;
      payload.thinking_model_name = thinkingModelName || null;

      const result: TestResult = await fetchAPI("/users/me/llm-config/test", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setThinkingTestResult(result);
    } catch (error) {
      setThinkingTestResult({
        status: "error",
        message: "请求失败，请检查网络连接",
        latency_ms: null,
        model_name: thinkingModelName,
        base_url: thinkingBaseUrl,
      });
    } finally {
      setIsTestingThinking(false);
    }
  };

  // 测试极速模型连接
  const handleFastTest = async () => {
    setIsTestingFast(true);
    setFastTestResult(null);

    try {
      const payload: Record<string, string | null> = {};

      if (fastApiKey && !fastApiKey.startsWith("sk-***")) {
        payload.fast_api_key = fastApiKey;
      }

      payload.fast_base_url = fastBaseUrl || null;
      payload.fast_model_name = fastModelName || null;

      const result: TestResult = await fetchAPI("/users/me/llm-config/test", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setFastTestResult(result);
    } catch (error) {
      setFastTestResult({
        status: "error",
        message: "请求失败，请检查网络连接",
        latency_ms: null,
        model_name: fastModelName,
        base_url: fastBaseUrl,
      });
    } finally {
      setIsTestingFast(false);
    }
  };

  // 恢复系统默认
  const handleReset = async () => {
    setIsSaving(true);
    setThinkingTestResult(null);
    setFastTestResult(null);

    try {
      await fetchAPI("/users/me/llm-config", {
        method: "PUT",
        body: JSON.stringify({
          thinking_api_key: null,
          thinking_base_url: null,
          thinking_model_name: null,
          fast_api_key: null,
          fast_base_url: null,
          fast_model_name: null,
          embedding_api_key: null,
          embedding_base_url: null,
          embedding_model_name: null,
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

  // 应用思考模型快速预设
  const applyThinkingPreset = (preset: "saas" | "local") => {
    const p = THINKING_PRESETS[preset];
    setThinkingBaseUrl(p.base_url);
    setThinkingModelName(p.model_name);
    setThinkingTestResult(null);
  };

  // 应用极速模型快速预设
  const applyFastPreset = (preset: "saas" | "local") => {
    const p = FAST_PRESETS[preset];
    setFastBaseUrl(p.base_url);
    setFastModelName(p.model_name);
    setFastTestResult(null);
  };

  // 应用嵌入模型快速预设
  const applyEmbeddingPreset = (preset: "saas" | "local") => {
    const p = EMBEDDING_PRESETS[preset];
    setEmbeddingBaseUrl(p.base_url);
    setEmbeddingModelName(p.model_name);
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
        <div className="grid grid-cols-3 gap-3">
          {/* 极速模型配置源 */}
          <div className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg border ${
            isUsingUserFastConfig
              ? "bg-amber-500/5 border-amber-500/20"
              : "bg-blue-500/5 border-blue-500/20"
          }`}>
            <div className={`p-1 rounded-md ${
              isUsingUserFastConfig ? "bg-amber-500/20 text-amber-400" : "bg-blue-500/20 text-blue-400"
            }`}>
              <Zap size={14} />
            </div>
            <div>
              <p className={`text-xs font-medium ${
                isUsingUserFastConfig ? "text-amber-300" : "text-blue-300"
              }`}>
                极速: {isUsingUserFastConfig ? "个人配置" : "系统配置"}
              </p>
            </div>
          </div>
          {/* 思考模型配置源 */}
          <div className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg border ${
            isUsingUserThinkingConfig
              ? "bg-purple-500/5 border-purple-500/20"
              : "bg-blue-500/5 border-blue-500/20"
          }`}>
            <div className={`p-1 rounded-md ${
              isUsingUserThinkingConfig ? "bg-purple-500/20 text-purple-400" : "bg-blue-500/20 text-blue-400"
            }`}>
              <Brain size={14} />
            </div>
            <div>
              <p className={`text-xs font-medium ${
                isUsingUserThinkingConfig ? "text-purple-300" : "text-blue-300"
              }`}>
                思考: {isUsingUserThinkingConfig ? "个人配置" : "系统配置"}
              </p>
            </div>
          </div>
          {/* 嵌入模型配置源 */}
          <div className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg border ${
            isUsingUserEmbeddingConfig
              ? "bg-emerald-500/5 border-emerald-500/20"
              : "bg-blue-500/5 border-blue-500/20"
          }`}>
            <div className={`p-1 rounded-md ${
              isUsingUserEmbeddingConfig ? "bg-emerald-500/20 text-emerald-400" : "bg-blue-500/20 text-blue-400"
            }`}>
              <Dna size={14} />
            </div>
            <div>
              <p className={`text-xs font-medium ${
                isUsingUserEmbeddingConfig ? "text-emerald-300" : "text-blue-300"
              }`}>
                嵌入: {isUsingUserEmbeddingConfig ? "个人配置" : "系统配置"}
              </p>
            </div>
          </div>
        </div>

        {/* ==========================================
            极速模型配置
            ========================================== */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-amber-400" />
            <h3 className="text-sm font-medium text-neutral-300">极速模型</h3>
          </div>
          <p className="text-xs text-neutral-500 -mt-2">
            用于：意图识别、日常对话。推荐使用轻量快速模型以降低延迟和成本。
          </p>

          {/* 快速预设 */}
          <div>
            <h4 className="text-xs font-medium text-neutral-400 mb-2">快速预设</h4>
            <div className="grid grid-cols-2 gap-2">
              {(Object.entries(FAST_PRESETS) as [keyof typeof FAST_PRESETS, typeof FAST_PRESETS.saas][]).map(([key, preset]) => (
                <button
                  key={key}
                  onClick={() => applyFastPreset(key)}
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
              placeholder="https://api.openai.com/v1"
              className="w-full px-3 py-2.5 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 font-mono"
              value={fastBaseUrl}
              onChange={e => { setFastBaseUrl(e.target.value); setFastTestResult(null); }}
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
              placeholder="gpt-4o-mini"
              className="w-full px-3 py-2.5 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 font-mono"
              value={fastModelName}
              onChange={e => { setFastModelName(e.target.value); setFastTestResult(null); }}
            />
            <p className="text-xs text-neutral-600 mt-1">
              推荐轻量模型，如 gpt-4o-mini、deepseek-chat、qwen3:8b
            </p>
          </div>

          {/* API Key */}
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1.5">
              API Key
            </label>
            <div className="relative">
              <input
                type={showFastApiKey ? "text" : "password"}
                placeholder="sk-..."
                className="w-full px-3 py-2.5 pr-10 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 font-mono"
                value={fastApiKey}
                onChange={e => { setFastApiKey(e.target.value); setFastTestResult(null); }}
              />
              <button
                type="button"
                onClick={() => setShowFastApiKey(!showFastApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                {showFastApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <p className="text-xs text-neutral-600 mt-1">
              本地模型（Ollama 等）可留空。密钥仅存储在您的账户中，不会泄露给其他用户。
            </p>
          </div>

          {/* 极速模型测试结果 */}
          {fastTestResult && (
            <div className={`p-4 rounded-lg border ${
              fastTestResult.status === "success"
                ? "bg-emerald-500/5 border-emerald-500/20"
                : "bg-red-500/5 border-red-500/20"
            }`}>
              <div className="flex items-center gap-2">
                {fastTestResult.status === "success" ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                ) : (
                  <XCircle className="w-5 h-5 text-red-400" />
                )}
                <div>
                  <p className={`text-sm font-medium ${
                    fastTestResult.status === "success" ? "text-emerald-300" : "text-red-300"
                  }`}>
                    {fastTestResult.message}
                  </p>
                  {fastTestResult.latency_ms !== null && (
                    <p className="text-xs text-neutral-500 mt-0.5">
                     延迟: {fastTestResult.latency_ms}ms | 模型: {fastTestResult.model_name}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 极速模型测试按钮 */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleFastTest}
              disabled={isTestingFast || (!fastBaseUrl && !fastModelName)}
              className="flex items-center gap-2 px-4 py-2.5 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-800/50 disabled:text-neutral-600 text-neutral-200 text-sm font-medium rounded-md transition-colors"
            >
              {isTestingFast ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap size={14} />}
              测试极速模型
            </button>
          </div>
        </div>

        {/* ==========================================
            思考模型配置
            ========================================== */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Brain size={16} className="text-purple-400" />
            <h3 className="text-sm font-medium text-neutral-300">思考模型</h3>
          </div>
          <p className="text-xs text-neutral-500 -mt-2">
            用于：深度思考对话。推荐使用旗舰模型以获得最佳推理能力。
          </p>

          {/* 快速预设 */}
          <div>
            <h4 className="text-xs font-medium text-neutral-400 mb-2">快速预设</h4>
            <div className="grid grid-cols-2 gap-2">
              {(Object.entries(THINKING_PRESETS) as [keyof typeof THINKING_PRESETS, typeof THINKING_PRESETS.saas][]).map(([key, preset]) => (
                <button
                  key={key}
                  onClick={() => applyThinkingPreset(key)}
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
              placeholder="https://api.openai.com/v1"
              className="w-full px-3 py-2.5 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 font-mono"
              value={thinkingBaseUrl}
              onChange={e => { setThinkingBaseUrl(e.target.value); setThinkingTestResult(null); }}
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
              value={thinkingModelName}
              onChange={e => { setThinkingModelName(e.target.value); setThinkingTestResult(null); }}
            />
            <p className="text-xs text-neutral-600 mt-1">
              推荐旗舰模型，如 gpt-4o、claude-3-opus、deepseek-chat、qwen3:32b
            </p>
          </div>

          {/* API Key */}
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1.5">
              API Key
            </label>
            <div className="relative">
              <input
                type={showThinkingApiKey ? "text" : "password"}
                placeholder="sk-..."
                className="w-full px-3 py-2.5 pr-10 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 font-mono"
                value={thinkingApiKey}
                onChange={e => { setThinkingApiKey(e.target.value); setThinkingTestResult(null); }}
              />
              <button
                type="button"
                onClick={() => setShowThinkingApiKey(!showThinkingApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                {showThinkingApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <p className="text-xs text-neutral-600 mt-1">
              本地模型（Ollama 等）可留空。密钥仅存储在您的账户中，不会泄露给其他用户。
            </p>
          </div>

          {/* 思考模型测试结果 */}
          {thinkingTestResult && (
            <div className={`p-4 rounded-lg border ${
              thinkingTestResult.status === "success"
                ? "bg-emerald-500/5 border-emerald-500/20"
                : "bg-red-500/5 border-red-500/20"
            }`}>
              <div className="flex items-center gap-2">
                {thinkingTestResult.status === "success" ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                ) : (
                  <XCircle className="w-5 h-5 text-red-400" />
                )}
                <div>
                  <p className={`text-sm font-medium ${
                    thinkingTestResult.status === "success" ? "text-emerald-300" : "text-red-300"
                  }`}>
                    {thinkingTestResult.message}
                  </p>
                  {thinkingTestResult.latency_ms !== null && (
                    <p className="text-xs text-neutral-500 mt-0.5">
                     延迟: {thinkingTestResult.latency_ms}ms | 模型: {thinkingTestResult.model_name}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 思考模型测试按钮 */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleThinkingTest}
              disabled={isTestingThinking || (!thinkingBaseUrl && !thinkingModelName)}
              className="flex items-center gap-2 px-4 py-2.5 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-800/50 disabled:text-neutral-600 text-neutral-200 text-sm font-medium rounded-md transition-colors"
            >
              {isTestingThinking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain size={14} />}
              测试思考模型
            </button>
          </div>
        </div>

        {/* ==========================================
            嵌入模型配置
            ========================================== */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Dna size={16} className="text-emerald-400" />
            <h3 className="text-sm font-medium text-neutral-300">嵌入模型</h3>
          </div>
          <p className="text-xs text-neutral-500 -mt-2">
            用于：语义检索、经验向量化、技能推荐。推荐使用 text-embedding-3-large 或 bge-m3。
          </p>

          {/* 快速预设 */}
          <div>
            <h4 className="text-xs font-medium text-neutral-400 mb-2">快速预设</h4>
            <div className="grid grid-cols-2 gap-2">
              {(Object.entries(EMBEDDING_PRESETS) as [keyof typeof EMBEDDING_PRESETS, typeof EMBEDDING_PRESETS.saas][]).map(([key, preset]) => (
                <button
                  key={key}
                  onClick={() => applyEmbeddingPreset(key)}
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
              placeholder="https://api.openai.com/v1"
              className="w-full px-3 py-2.5 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 font-mono"
              value={embeddingBaseUrl}
              onChange={e => setEmbeddingBaseUrl(e.target.value)}
            />
            <p className="text-xs text-neutral-600 mt-1">
              OpenAI 兼容的 API 地址，支持本地 Ollama 运行 bge-m3 等嵌入模型
            </p>
          </div>

          {/* Model Name */}
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1.5">
              模型名称
            </label>
            <input
              type="text"
              placeholder="text-embedding-3-large"
              className="w-full px-3 py-2.5 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 font-mono"
              value={embeddingModelName}
              onChange={e => setEmbeddingModelName(e.target.value)}
            />
            <p className="text-xs text-neutral-600 mt-1">
              推荐 text-embedding-3-large（3072维）、text-embedding-3-small（1536维）或 bge-m3（1024维）
            </p>
          </div>

          {/* API Key */}
          <div>
            <label className="block text-xs font-medium text-neutral-400 mb-1.5">
              API Key
            </label>
            <div className="relative">
              <input
                type={showEmbeddingApiKey ? "text" : "password"}
                placeholder="sk-..."
                className="w-full px-3 py-2.5 pr-10 rounded-md border border-neutral-700 bg-neutral-900 text-sm text-neutral-200 placeholder:text-neutral-600 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 font-mono"
                value={embeddingApiKey}
                onChange={e => setEmbeddingApiKey(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowEmbeddingApiKey(!showEmbeddingApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                {showEmbeddingApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <p className="text-xs text-neutral-600 mt-1">
              本地模型（Ollama 等）可留空。嵌入模型用于向量检索，不参与对话生成。
            </p>
          </div>
        </div>

        {/* ==========================================
            系统回退信息
            ========================================== */}
        {(!isUsingUserThinkingConfig || !isUsingUserFastConfig || !isUsingUserEmbeddingConfig) && (
          <div className="p-4 rounded-lg border border-neutral-800 bg-neutral-900/30">
            <h4 className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-3">系统全局配置（回退）</h4>
            <div className="space-y-2 text-sm">
              {/* 极速模型系统回退 */}
              {!isUsingUserFastConfig && (systemFastBaseUrl || systemFastModelName) && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-amber-400/70">极速模型</p>
                  {systemFastBaseUrl && (
                    <div className="flex items-center gap-2">
                      <span className="text-neutral-500 shrink-0">Base URL:</span>
                      <span className="text-neutral-300 font-mono text-xs truncate">{systemFastBaseUrl}</span>
                    </div>
                  )}
                  {systemFastModelName && (
                    <div className="flex items-center gap-2">
                      <span className="text-neutral-500 shrink-0">Model:</span>
                      <span className="text-neutral-300 font-mono text-xs">{systemFastModelName}</span>
                    </div>
                  )}
                </div>
              )}
              {/* 思考模型系统回退 */}
              {!isUsingUserThinkingConfig && (systemThinkingBaseUrl || systemThinkingModelName) && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-purple-400/70">思考模型</p>
                  {systemThinkingBaseUrl && (
                    <div className="flex items-center gap-2">
                      <span className="text-neutral-500 shrink-0">Base URL:</span>
                      <span className="text-neutral-300 font-mono text-xs truncate">{systemThinkingBaseUrl}</span>
                    </div>
                  )}
                  {systemThinkingModelName && (
                    <div className="flex items-center gap-2">
                      <span className="text-neutral-500 shrink-0">Model:</span>
                      <span className="text-neutral-300 font-mono text-xs">{systemThinkingModelName}</span>
                    </div>
                  )}
                </div>
              )}
              {/* 嵌入模型系统回退 */}
              {!isUsingUserEmbeddingConfig && (systemEmbeddingBaseUrl || systemEmbeddingModelName) && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-emerald-400/70">嵌入模型</p>
                  {systemEmbeddingBaseUrl && (
                    <div className="flex items-center gap-2">
                      <span className="text-neutral-500 shrink-0">Base URL:</span>
                      <span className="text-neutral-300 font-mono text-xs truncate">{systemEmbeddingBaseUrl}</span>
                    </div>
                  )}
                  {systemEmbeddingModelName && (
                    <div className="flex items-center gap-2">
                      <span className="text-neutral-500 shrink-0">Model:</span>
                      <span className="text-neutral-300 font-mono text-xs">{systemEmbeddingModelName}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ==========================================
            操作栏
            ========================================== */}
        <div className="flex items-center gap-3 pt-2 flex-wrap">
          <button
            onClick={handleFastTest}
            disabled={isTestingFast || (!fastBaseUrl && !fastModelName)}
            className="flex items-center gap-2 px-4 py-2.5 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-800/50 disabled:text-neutral-600 text-neutral-200 text-sm font-medium rounded-md transition-colors"
          >
            {isTestingFast ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap size={14} />}
            测试极速
          </button>

          <button
            onClick={handleThinkingTest}
            disabled={isTestingThinking || (!thinkingBaseUrl && !thinkingModelName)}
            className="flex items-center gap-2 px-4 py-2.5 bg-neutral-800 hover:bg-neutral-700 disabled:bg-neutral-800/50 disabled:text-neutral-600 text-neutral-200 text-sm font-medium rounded-md transition-colors"
          >
            {isTestingThinking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Brain size={14} />}
            测试思考
          </button>

          <button
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400 text-white text-sm font-medium rounded-md transition-colors"
          >
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save size={14} />}
            保存配置
          </button>

          {(isUsingUserThinkingConfig || isUsingUserFastConfig || isUsingUserEmbeddingConfig) && (
            <button
              onClick={handleReset}
              disabled={isSaving}
              className="flex items-center gap-2 px-4 py-2.5 text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 text-sm rounded-md transition-colors"
            >
              <RotateCcw size={14} />
              恢复默认
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
              <p>• 极速模型推荐使用轻量模型（如 gpt-4o-mini），可降低延迟和成本</p>
              <p>• 思考模型用于深度思考对话，推荐使用旗舰模型（如 gpt-4o）</p>
              <p>• 嵌入模型用于语义检索和经验向量化，推荐 text-embedding-3-large 或 bge-m3</p>
              <p>• 个人配置优先级高于系统全局配置，配置后所有 AI 功能将使用您的模型</p>
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
