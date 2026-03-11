"use client";

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useUIStore } from "@/store/useUIStore";
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { X, Box, Search, Play, Loader2, CheckCircle, XCircle, ChevronRight, ChevronDown, Terminal } from "lucide-react";
import { fetchAPI, BASE_URL } from "@/lib/api";
import { toast } from 'sonner';
import { FilePickerButton } from "@/components/FilePicker";
import { fetchEventSource } from '@microsoft/fetch-event-source';

// ==========================================
// 系统内置分类
// ==========================================
interface Category {
  id: string;
  name: string;
  icon: string;
  subcategories?: Category[];
}

const BUILT_IN_CATEGORIES: Category[] = [
  { id: 'all', name: '全部', icon: '📦' },
  {
    id: 'quality_control',
    name: '质量控制',
    icon: '🔬',
    subcategories: [
      { id: 'fastq_qc', name: 'FastQ质控', icon: '' },
      { id: 'bam_qc', name: 'BAM质控', icon: '' },
      { id: 'vcf_qc', name: 'VCF质控', icon: '' }
    ]
  },
  {
    id: 'alignment',
    name: '序列比对',
    icon: '🧬',
    subcategories: [
      { id: 'dna_align', name: 'DNA比对', icon: '' },
      { id: 'rna_align', name: 'RNA比对', icon: '' }
    ]
  },
  {
    id: 'quantification',
    name: '定量分析',
    icon: '📊'
  },
  {
    id: 'visualization',
    name: '可视化',
    icon: '📈'
  },
  {
    id: 'pipeline',
    name: '流程编排',
    icon: '⚙️'
  }
];

// ==========================================
// 类型定义
// ==========================================
interface SkillParameter {
  type: string;
  format?: string;  // 原始类型信息：directorypath, filepath
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
  category?: string;
  category_name?: string;
  subcategory?: string;
  subcategory_name?: string;
  tags?: string[];
}

// ==========================================
// 主组件：SKILL 兵器库
// ==========================================
export function SkillCenter() {
  const { isSkillCenterOpen, closeAllOverlays, openDataCenter } = useUIStore();
  const { currentProjectId, currentSessionId } = useWorkspaceStore();

  const [skills, setSkills] = useState<Skill[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, unknown>>({});
  const [isExecuting, setIsExecuting] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);

  // 实时日志状态
  const [logs, setLogs] = useState<string[]>([]);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // 分类导航状态
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['quality_control']));

  // 自动滚动日志
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // 日志流式读取
  useEffect(() => {
    if (!taskId) return;

    setLogs([]);
    const controller = new AbortController();

    const connectToLogStream = async () => {
      try {
        await fetchEventSource(`${BASE_URL}/api/tasks/${taskId}/logs/stream`, {
          method: 'GET',
          signal: controller.signal,
          onmessage(event) {
            if (event.event === 'log') {
              const data = JSON.parse(event.data);
              setLogs(prev => [...prev, data.text]);
            } else if (event.event === 'done') {
              controller.abort();
            }
          },
          onerror(err) {
            console.error('Log stream error:', err);
          }
        });
      } catch (e) {
        console.error('Failed to connect to log stream:', e);
      }
    };

    connectToLogStream();
    return () => controller.abort();
  }, [taskId]);

  // 加载 SKILL 目录
  useEffect(() => {
    if (isSkillCenterOpen) {
      fetchSkills();
    }
  }, [isSkillCenterOpen]);

  const fetchSkills = async () => {
    setIsLoading(true);
    try {
      const data = await fetchAPI('/api/skills/catalog');
      if (data.status === 'success') {
        setSkills(data.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch skills:', e);
      toast.error('加载技能列表失败');
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

  // 根据分类过滤 SKILL
  const filteredByCategory = useMemo(() => {
    if (selectedCategory === 'all') return skills;
    return skills.filter(s => {
      if (s.category === selectedCategory) return true;
      if (s.subcategory === selectedCategory) return true;
      return false;
    });
  }, [skills, selectedCategory]);

  // 根据搜索词过滤
  const filteredSkills = useMemo(() => {
    if (!searchQuery) return filteredByCategory;
    const query = searchQuery.toLowerCase();
    return filteredByCategory.filter(s =>
      s.name.toLowerCase().includes(query) ||
      s.skill_id.toLowerCase().includes(query) ||
      (s.tags && s.tags.some(tag => tag.toLowerCase().includes(query)))
    );
  }, [filteredByCategory, searchQuery]);

  // 切换分类展开状态
  const toggleCategoryExpand = (categoryId: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      return next;
    });
  };

  // 执行 SKILL
  const handleExecute = async () => {
    if (!selectedSkill || !currentProjectId) {
      toast.error('请先选择项目');
      return;
    }

    setIsExecuting(true);
    setTaskId(null);
    setTaskStatus(null);

    toast.loading('正在提交任务...', { id: 'skill-exec' });

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
        toast.success('任务已提交，正在后台执行', { id: 'skill-exec' });
        pollTaskStatus(result.task_id);
      } else {
        setTaskStatus('FAILURE');
        setIsExecuting(false);
        toast.error('任务提交失败', { id: 'skill-exec' });
      }
    } catch (e) {
      setTaskStatus('FAILURE');
      setIsExecuting(false);
      toast.error('任务提交失败，请检查网络连接', { id: 'skill-exec' });
    }
  };

  // 轮询任务状态
  const pollTaskStatus = async (id: string) => {
    const poll = async () => {
      try {
        const res = await fetch(`${BASE_URL}/api/tasks/${id}/status`);
        const data = await res.json();
        setTaskStatus(data.status);

        if (data.status === 'SUCCESS') {
          setIsExecuting(false);
          toast.success('SKILL执行完成！', {
            id: 'skill-complete',
            description: '结果已保存到输出目录',
            action: {
              label: '查看结果',
              onClick: () => openDataCenter?.()
            }
          });
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('refresh-chat'));
          }, 500);
        } else if (data.status === 'FAILURE') {
          setIsExecuting(false);
          toast.error('SKILL执行失败', {
            id: 'skill-failed',
            description: '请检查参数或联系技术支持'
          });
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
    const paramType = prop.type?.toLowerCase() || '';
    const paramFormat = prop.format?.toLowerCase() || '';

    // DirectoryPath 类型：使用 FilePicker 选择目录
    if (paramFormat === 'directorypath') {
      return (
        <FilePickerButton
          projectId={currentProjectId || ''}
          value={String(value || '')}
          onChange={(path) => setParamValues({ ...paramValues, [key]: path })}
          type="directory"
          placeholder="选择目录..."
        />
      );
    }

    // FilePath 类型：使用 FilePicker 选择文件
    if (paramFormat === 'filepath') {
      return (
        <FilePickerButton
          projectId={currentProjectId || ''}
          value={String(value || '')}
          onChange={(path) => setParamValues({ ...paramValues, [key]: path })}
          type="file"
          placeholder="选择文件..."
        />
      );
    }

    // Boolean 类型：下拉选择
    if (paramType === 'boolean') {
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

    // Number/Integer 类型：数字输入
    if (paramType === 'number' || paramType === 'integer') {
      return (
        <input
          type="number"
          value={String(value ?? '')}
          onChange={(e) => setParamValues({
            ...paramValues,
            [key]: paramType === 'integer' ? parseInt(e.target.value) || 0 : parseFloat(e.target.value) || 0
          })}
          placeholder={prop.description || key}
          className="w-full px-3 py-2 text-sm bg-neutral-800 border border-neutral-700 rounded-lg text-neutral-200 focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder:text-neutral-500"
        />
      );
    }

    // 默认：文本输入
    return (
      <input
        type="text"
        value={String(value ?? '')}
        onChange={(e) => setParamValues({ ...paramValues, [key]: e.target.value })}
        placeholder={prop.description || key}
        className="w-full px-3 py-2 text-sm bg-neutral-800 border border-neutral-700 rounded-lg text-neutral-200 focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder:text-neutral-500"
      />
    );
  };

  if (!isSkillCenterOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={closeAllOverlays} />

      <div className="relative w-[1200px] h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">

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

        {/* Main Content: 三列布局 */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Panel: 分类导航 (180px) */}
          <div className="w-[180px] border-r border-neutral-800 flex flex-col bg-neutral-900/20">
            <div className="p-3 border-b border-neutral-800">
              <h3 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider">分类导航</h3>
            </div>
            <div className="flex-1 overflow-y-auto p-2 custom-scrollbar">
              {BUILT_IN_CATEGORIES.map((category) => {
                const isExpanded = expandedCategories.has(category.id);
                const isSelected = selectedCategory === category.id;
                const hasSubcategories = category.subcategories && category.subcategories.length > 0;

                return (
                  <div key={category.id}>
                    <button
                      onClick={() => {
                        setSelectedCategory(category.id);
                        if (hasSubcategories) {
                          toggleCategoryExpand(category.id);
                        }
                      }}
                      className={`w-full text-left px-3 py-2 rounded-lg transition-all flex items-center gap-2 ${
                        isSelected
                          ? 'bg-blue-500/10 border border-blue-500/30 text-blue-300'
                          : 'hover:bg-neutral-800/50 text-neutral-400'
                      }`}
                    >
                      <span className="text-sm">{category.icon}</span>
                      <span className="text-xs font-medium flex-1">{category.name}</span>
                      {hasSubcategories && (
                        <span className="text-neutral-500">
                          {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        </span>
                      )}
                    </button>

                    {/* 子分类 */}
                    {hasSubcategories && isExpanded && (
                      <div className="ml-4 mt-1 space-y-0.5">
                        {category.subcategories!.map((sub) => (
                          <button
                            key={sub.id}
                            onClick={() => setSelectedCategory(sub.id)}
                            className={`w-full text-left px-3 py-1.5 rounded-lg transition-all flex items-center gap-2 ${
                              selectedCategory === sub.id
                                ? 'bg-blue-500/10 text-blue-300'
                                : 'hover:bg-neutral-800/50 text-neutral-500'
                            }`}
                          >
                            <span className="text-[10px]">{sub.icon || '•'}</span>
                            <span className="text-xs">{sub.name}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Middle Panel: SKILL 列表 (280px) */}
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
                          <div className="flex items-center gap-2 mt-1">
                            <p className="text-[10px] text-neutral-500 font-mono truncate">{skill.skill_id}</p>
                            {skill.category_name && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400">
                                {skill.category_name}
                              </span>
                            )}
                          </div>
                        </div>
                        <ChevronRight size={14} className="shrink-0 opacity-40" />
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Panel: 参数配置面板 (flex-1) */}
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
                  {selectedSkill.category_name && (
                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-xs text-neutral-400">分类:</span>
                      <span className="text-xs text-neutral-300">{selectedSkill.category_name}</span>
                      {selectedSkill.subcategory_name && (
                        <>
                          <ChevronRight size={10} className="text-neutral-500" />
                          <span className="text-xs text-neutral-300">{selectedSkill.subcategory_name}</span>
                        </>
                      )}
                    </div>
                  )}
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

                {/* 实时日志显示 */}
                {taskId && (
                  <div className="border-t border-neutral-800">
                    <div className="p-3 border-b border-neutral-800 flex items-center gap-2 bg-neutral-900/30">
                      <Terminal size={14} className="text-green-400" />
                      <span className="text-xs font-medium text-neutral-400">执行日志</span>
                      <span className="text-[10px] text-neutral-500 ml-auto font-mono">{logs.length} 行</span>
                    </div>
                    <div className="h-48 overflow-y-auto p-3 bg-neutral-950 font-mono text-xs text-green-400/90 custom-scrollbar">
                      {logs.length === 0 ? (
                        <div className="flex items-center justify-center h-full text-neutral-600 gap-2">
                          <Loader2 size={14} className="animate-spin" />
                          <span>等待日志输出...</span>
                        </div>
                      ) : (
                        <div className="space-y-0.5">
                          {logs.map((log, i) => (
                            <div key={i} className="hover:bg-white/5 px-1 py-0.5 rounded whitespace-pre-wrap">
                              {log}
                            </div>
                          ))}
                          <span className="animate-pulse inline-block w-2 h-3 bg-green-500 ml-1 align-middle"></span>
                          <div ref={terminalEndRef} />
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Execute Button */}
                <div className="p-4 border-t border-neutral-800">
                  <button
                    onClick={handleExecute}
                    disabled={isExecuting || !currentProjectId}
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