"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { X, Box, Search, Play, Loader2, CheckCircle, XCircle, Clock, ChevronRight } from "lucide-react";
import { BASE_URL } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================
interface SkillParameter {
  type: string;
  description?: string;
  default?: unknown;
}

interface SkillSchema {
  type: string;
  properties: Record<string, SkillParameter>;
  required: string[];
}

interface Skill {
  skill_id: string;
  name: string;
  version: string;
  author: string;
  executor_type: string;
  timeout_seconds: number;
  parameters_schema: SkillSchema;
  bundle_name: string;
}

// ==========================================
// 主组件：SKILL 中心
// ==========================================
export function SkillCenter() {
  const { isSkillCenterOpen, closeAllOverlays } = useUIStore();
  const { currentProjectId, currentSessionId } = useWorkspaceStore();

  const [skills, setSkills] = useState<Skill[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, unknown>>({});
  const [isExecuting, setIsExecuting] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);

  // 加载 SKILL 目录
  useEffect(() => {
    if (isSkillCenterOpen) {
      fetchSkills();
    }
  }, [isSkillCenterOpen]);

  const fetchSkills = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('autonome_access_token');
      const res = await fetch(`${BASE_URL}/api/skills/catalog`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      const data = await res.json();
      if (data.status === 'success') {
        setSkills(data.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch skills:', e);
    } finally {
      setIsLoading(false);
    }
  };

  // 选择 SKILL 时初始化参数
  useEffect(() => {
    if (selectedSkill && selectedSkill.parameters_schema?.properties) {
      const defaults: Record<string, unknown> = {};
      Object.entries(selectedSkill.parameters_schema.properties).forEach(([key, prop]) => {
        defaults[key] = prop.default ?? '';
      });
      setParamValues(defaults);
    }
  }, [selectedSkill]);

  // 过滤 SKILL 列表
  const filteredSkills = useMemo(() => {
    if (!searchQuery) return skills;
    const query = searchQuery.toLowerCase();
    return skills.filter(s =>
      s.name.toLowerCase().includes(query) ||
      s.skill_id.toLowerCase().includes(query)
    );
  }, [skills, searchQuery]);

  // 执行 SKILL
  const handleExecute = async () => {
    if (!selectedSkill) return;

    setIsExecuting(true);
    setTaskId(null);
    setTaskStatus(null);

    try {
      const token = localStorage.getItem('autonome_access_token');
      const payload = {
        tool_id: selectedSkill.skill_id,
        parameters: {
          ...paramValues,
          session_id: currentSessionId || 1,
          project_id: currentProjectId
        },
        project_id: currentProjectId
      };

      const res = await fetch(`${BASE_URL}/api/tasks/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(payload)
      });

      const result = await res.json();
      if (result.status === 'submitted') {
        setTaskId(result.task_id);
        pollTaskStatus(result.task_id);
      } else {
        setTaskStatus('FAILURE');
        setIsExecuting(false);
      }
    } catch (e) {
      setTaskStatus('FAILURE');
      setIsExecuting(false);
    }
  };

  // 轮询任务状态
  const pollTaskStatus = async (id: string) => {
    const poll = async () => {
      try {
        const res = await fetch(`${BASE_URL}/api/tasks/${id}/status`);
        const data = await res.json();
        setTaskStatus(data.status);

        if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
          setIsExecuting(false);
          if (data.status === 'SUCCESS') {
            setTimeout(() => {
              window.dispatchEvent(new CustomEvent('refresh-chat'));
            }, 500);
          }
        } else {
          setTimeout(poll, 2000);
        }
      } catch (e) {
        setTimeout(poll, 2000);
      }
    };
    poll();
  };

  // 渲染参数表单控件
  const renderParamInput = (key: string, prop: SkillParameter) => {
    const value = paramValues[key];
    const isBool = prop.type === 'boolean';

    if (isBool) {
      return (
        <select
          value={String(value ?? false)}
          onChange={(e) => setParamValues({ ...paramValues, [key]: e.target.value === 'true' })}
          className="w-full px-3 py-2 text-sm bg-neutral-800 border border-neutral-700 rounded-lg text-neutral-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      );
    }

    return (
      <input
        type={prop.type === 'number' || prop.type === 'integer' ? 'number' : 'text'}
        value={String(value ?? '')}
        onChange={(e) => setParamValues({
          ...paramValues,
          [key]: prop.type === 'number' || prop.type === 'integer' ? Number(e.target.value) : e.target.value
        })}
        placeholder={prop.description || key}
        className="w-full px-3 py-2 text-sm bg-neutral-800 border border-neutral-700 rounded-lg text-neutral-200 focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder:text-neutral-500"
      />
    );
  };

  if (!isSkillCenterOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={closeAllOverlays} />

      <div className="relative w-[700px] h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">

        {/* Header */}
        <div className="h-16 shrink-0 border-b border-neutral-800 px-6 flex items-center justify-between bg-neutral-900/40">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/20 border border-blue-500/30 rounded-lg text-blue-400 shadow-[0_0_15px_rgba(59,130,246,0.15)]">
              <Box size={18} strokeWidth={2.5} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-neutral-200 tracking-wide">SKILL 兵器库</h2>
              <p className="text-[10px] text-neutral-500 font-mono mt-0.5">{skills.length} 个标准化分析模块</p>
            </div>
          </div>
          <button onClick={closeAllOverlays} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Panel: SKILL List */}
          <div className="w-[280px] border-r border-neutral-800 flex flex-col">
            {/* Search */}
            <div className="p-3 border-b border-neutral-800">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="搜索 SKILL..."
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-sm text-neutral-300 outline-none focus:border-blue-500/50 transition-all placeholder:text-neutral-600"
                />
              </div>
            </div>

            {/* SKILL List */}
            <div className="flex-1 overflow-y-auto p-2 custom-scrollbar">
              {isLoading ? (
                <div className="flex items-center justify-center h-32 text-neutral-500">
                  <Loader2 size={24} className="animate-spin" />
                </div>
              ) : filteredSkills.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-32 text-neutral-600 gap-2">
                  <Box size={32} className="opacity-20" />
                  <p className="text-sm">暂无匹配的 SKILL</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {filteredSkills.map((skill) => (
                    <button
                      key={skill.skill_id}
                      onClick={() => setSelectedSkill(skill)}
                      className={`w-full text-left p-3 rounded-lg transition-all ${
                        selectedSkill?.skill_id === skill.skill_id
                          ? 'bg-blue-500/10 border border-blue-500/30 text-blue-300'
                          : 'bg-neutral-900/50 border border-transparent hover:bg-neutral-800/50 text-neutral-300'
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        <Box size={16} className="shrink-0 mt-0.5 opacity-60" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{skill.name}</p>
                          <p className="text-[10px] text-neutral-500 font-mono truncate mt-0.5">{skill.skill_id}</p>
                        </div>
                        <ChevronRight size={14} className="shrink-0 opacity-40" />
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Panel: SKILL Detail & Parameters */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {selectedSkill ? (
              <>
                {/* SKILL Info */}
                <div className="p-4 border-b border-neutral-800 bg-neutral-900/20">
                  <h3 className="text-lg font-semibold text-neutral-200">{selectedSkill.name}</h3>
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      {selectedSkill.executor_type}
                    </span>
                    <span className="text-xs text-neutral-500">
                      v{selectedSkill.version}
                    </span>
                    <span className="text-xs text-neutral-500">
                      by {selectedSkill.author}
                    </span>
                  </div>
                </div>

                {/* Parameters Form */}
                <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                  <h4 className="text-sm font-medium text-neutral-400 mb-3">参数配置</h4>
                  {selectedSkill.parameters_schema?.properties &&
                  Object.keys(selectedSkill.parameters_schema.properties).length > 0 ? (
                    <div className="space-y-4">
                      {Object.entries(selectedSkill.parameters_schema.properties).map(([key, prop]) => {
                        const isRequired = selectedSkill.parameters_schema.required?.includes(key);
                        return (
                          <div key={key}>
                            <label className="flex items-center gap-2 text-sm text-neutral-300 mb-1.5">
                              <span className="font-mono">{key}</span>
                              {isRequired && (
                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
                                  必填
                                </span>
                              )}
                            </label>
                            {prop.description && (
                              <p className="text-xs text-neutral-500 mb-1.5">{prop.description}</p>
                            )}
                            {renderParamInput(key, prop)}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-sm text-neutral-500">该 SKILL 无需配置参数</div>
                  )}
                </div>

                {/* Execution Status */}
                {(isExecuting || taskStatus) && (
                  <div className="p-4 border-t border-neutral-800 bg-neutral-900/20">
                    <div className="flex items-center gap-2">
                      {taskStatus === 'SUCCESS' && <CheckCircle size={16} className="text-green-400" />}
                      {taskStatus === 'FAILURE' && <XCircle size={16} className="text-red-400" />}
                      {(taskStatus === 'PENDING' || taskStatus === 'STARTED' || isExecuting) && (
                        <Loader2 size={16} className="text-blue-400 animate-spin" />
                      )}
                      <span className="text-sm text-neutral-300">
                        {taskStatus === 'SUCCESS' && '执行完成'}
                        {taskStatus === 'FAILURE' && '执行失败'}
                        {(taskStatus === 'PENDING' || taskStatus === 'STARTED') && '执行中...'}
                        {!taskStatus && isExecuting && '提交中...'}
                      </span>
                      {taskId && (
                        <span className="text-xs text-neutral-500 font-mono ml-auto">
                          Task: {taskId.slice(0, 8)}
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* Execute Button */}
                <div className="p-4 border-t border-neutral-800">
                  <button
                    onClick={handleExecute}
                    disabled={isExecuting}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
                  >
                    {isExecuting ? (
                      <>
                        <Loader2 size={18} className="animate-spin" />
                        执行中...
                      </>
                    ) : (
                      <>
                        <Play size={18} />
                        执行 SKILL
                      </>
                    )}
                  </button>
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-neutral-600 gap-3">
                <Box size={48} className="opacity-20" />
                <p className="text-sm">选择左侧的 SKILL 开始分析</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}