/**
 * 技能执行面板 - 从 SkillCenter 提取的执行功能
 *
 * P1 错误恢复优化：
 * - 执行失败时自动保存参数状态
 * - 智能错误诊断和修复建议
 * - 支持一键重新执行
 *
 * P2 等待体验优化：
 * - 分段进度条显示
 * - 预估时间提示
 * - 即时反馈
 */

'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useWorkspaceStore } from "@/store/useWorkspaceStore";
import { useChatStore } from "@/store/useChatStore";
import { useUIStore } from "@/store/useUIStore";
import { Search, Play, Loader2, ChevronRight, ChevronDown, Terminal, Box, Info, MessageSquarePlus, ChevronLeft, Filter, RefreshCw, Wrench, AlertTriangle, Pin } from "lucide-react";
import { fetchAPI, BASE_URL, errorDiagnosticApi, executionStateApi, pinnedSkillsApi, type ErrorDiagnosis, type FixSuggestion } from "@/lib/api";
import { toast } from 'sonner';
import { FilePickerButton } from "@/components/FilePicker";
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { SkillDetailDrawer } from './SkillDetailDrawer';
import { SkillSheetInput } from './SampleSheetGenerator/SkillSheetInput';
import { useIsMobile } from "@/hooks/useIsMobile";
import { cn } from "@/lib/utils";

// ✨ P4 用户行为埋点
import { analytics } from '@/lib/analytics';

// ✨ P2 等待体验优化 - 导入执行进度组件
import { ExecutionProgress, estimateExecutionTime } from './ExecutionProgress';

// ✨ 从拆分模块导入
import type { Skill, SkillParameter, Category, SkillExecutePanelProps } from './SkillExecutePanel/types';
import { BUILT_IN_CATEGORIES } from './SkillExecutePanel/categories';
import { MobileCategoryPanel, MobileSkillListPanel, MobileParamConfigPanel } from './SkillExecutePanel/MobilePanels';

// ✨ P4 参数智能分组
import { ParameterGroupPanel } from './ParameterGroupPanel';

// ✨ 重新导出类型，保持向后兼容
export type { Skill, SkillParameter, Category, SkillExecutePanelProps } from './SkillExecutePanel/types';

export function SkillExecutePanel({ onDataCenterOpen, selectedSkillFromMarket, preSelectedSkillId }: SkillExecutePanelProps) {
  const { currentProjectId, currentSessionId, setCurrentSessionId, setPendingChatSkill } = useWorkspaceStore();
  const { setMessages } = useChatStore();
  const { closeAllOverlays, skillFilterMode, setSkillFilterMode } = useUIStore();

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

  // ✨ P2 等待体验优化 - 执行时间追踪
  const [executionStartTime, setExecutionStartTime] = useState<number | null>(null);
  const estimatedDuration = useMemo(() => {
    if (!selectedSkill) return undefined;
    return estimateExecutionTime(selectedSkill.executor_type, selectedSkill.name);
  }, [selectedSkill]);

  // ✨ P1 错误恢复优化状态
  const [errorDiagnosis, setErrorDiagnosis] = useState<ErrorDiagnosis | null>(null);
  const [showErrorPanel, setShowErrorPanel] = useState(false);
  const [lastFailedParams, setLastFailedParams] = useState<Record<string, unknown> | null>(null);

  // 分类导航状态
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['quality_control']));

  // 技能详情抽屉状态
  const [detailSkillId, setDetailSkillId] = useState<string | null>(null);

  // ==========================================
  // 移动端步骤向导状态
  // 移动端采用3步向导流程：分类选择 → 技能选择 → 参数配置
  // 这解决了移动端三栏布局无法并排显示的问题
  // ==========================================
  type MobileViewStep = 'category' | 'skills' | 'params';
  const [mobileViewStep, setMobileViewStep] = useState<MobileViewStep>('category');
  const isMobile = useIsMobile();

  // 从市场选择的技能
  useEffect(() => {
    if (selectedSkillFromMarket) {
      setSelectedSkill(selectedSkillFromMarket);
    }
  }, [selectedSkillFromMarket]);

  // ✨ 预选技能（从推荐卡片打开）
  useEffect(() => {
    if (preSelectedSkillId && skills.length > 0) {
      const skill = skills.find(s => s.skill_id === preSelectedSkillId);
      if (skill) {
        setSelectedSkill(skill);
      }
    }
  }, [preSelectedSkillId, skills]);

  // ==========================================
  // ✨ P1 历史复用功能 - 监听重新执行事件
  // ==========================================
  useEffect(() => {
    const handleReExecute = (event: CustomEvent) => {
      const { skillId, skillName, parameters } = event.detail;

      // 查找技能
      const skill = skills.find(s => s.skill_id === skillId);
      if (skill) {
        setSelectedSkill(skill);
        // 预填充参数
        if (parameters && Object.keys(parameters).length > 0) {
          setParamValues(parameters);
          toast.success('已恢复上次执行参数');
        }
      } else {
        // 技能不在列表中，从后端获取
        fetchAPI(`/api/skills/${skillId}`)
          .then((data) => {
            if (data) {
              const skillData = data.data || data;
              setSelectedSkill(skillData);
              if (parameters && Object.keys(parameters).length > 0) {
                setParamValues(parameters);
                toast.success('已恢复上次执行参数');
              }
            }
          })
          .catch((error) => {
            console.error('[SkillExecutePanel] 获取技能失败:', error);
            toast.error('无法加载技能');
          });
      }
    };

    window.addEventListener('re-execute-skill', handleReExecute as EventListener);
    return () => {
      window.removeEventListener('re-execute-skill', handleReExecute as EventListener);
    };
  }, [skills]);

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
    fetchSkills();
  }, []);

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
      const schema = selectedSkill.parameters_schema;

      // ✨ P4 埋点：技能查看
      analytics.skillView(selectedSkill.skill_id, selectedSkill.name);

      // ==========================================
      // 按照 x-parameter-order 顺序初始化参数默认值
      // ==========================================
      const parameterOrder = schema['x-parameter-order'];
      let entries: [string, SkillParameter][];

      if (parameterOrder && Array.isArray(parameterOrder)) {
        entries = parameterOrder
          .filter(name => schema.properties[name])
          .map(name => [name, schema.properties[name]]);
      } else {
        entries = Object.entries(schema.properties);
      }

      entries.forEach(([key, prop]) => {
        defaults[key] = prop.default ?? '';
      });

      setParamValues(defaults);
    }
  }, [selectedSkill]);

  // 根据分类过滤 SKILL
  const filteredByCategory = useMemo(() => {
    let result = skills;

    // ✨ 基础分析过滤：如果 skillFilterMode 为 'basic'，只显示标记了 is_basic_analysis: true 的技能
    if (skillFilterMode === 'basic') {
      result = result.filter(s => s.is_basic_analysis === true);
    }

    // 分类过滤
    if (selectedCategory !== 'all') {
      result = result.filter(s => {
        if (s.category === selectedCategory) return true;
        if (s.subcategory === selectedCategory) return true;
        return false;
      });
    }

    return result;
  }, [skills, selectedCategory, skillFilterMode]);

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

  // 计算各分类的技能数量
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { all: skills.length };
    skills.forEach(skill => {
      if (skill.category) {
        counts[skill.category] = (counts[skill.category] || 0) + 1;
      }
      if (skill.subcategory) {
        counts[skill.subcategory] = (counts[skill.subcategory] || 0) + 1;
      }
    });
    return counts;
  }, [skills]);

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

    // ✨ P2 等待体验优化 - 记录执行开始时间
    setExecutionStartTime(Date.now());

    setIsExecuting(true);
    setTaskId(null);
    setTaskStatus(null);

    toast.loading('正在提交任务...', { id: 'skill-exec' });

    try {
      // ==========================================
      // ✨ 新对话时自动创建 Session
      // 如果没有 currentSessionId，先创建一个新的 session
      // ==========================================
      let sessionId = currentSessionId;

      if (!sessionId) {
        toast.loading('正在创建新会话...', { id: 'skill-exec' });

        try {
          // 创建新 session - title 作为查询参数
          const sessionTitle = `SKILL: ${selectedSkill.name}`;
          const sessionData = await fetchAPI(
            `/projects/${currentProjectId}/sessions?title=${encodeURIComponent(sessionTitle)}`,
            { method: 'POST' }
          );

          if (sessionData.status === 'success' && sessionData.data?.id) {
            sessionId = String(sessionData.data.id);
            // 更新全局状态
            setCurrentSessionId(sessionId, sessionData.data.title);
            // 清空消息列表（新会话）
            setMessages([]);
            // 通知侧边栏刷新会话列表
            window.dispatchEvent(new Event('refresh-sessions'));
            toast.loading('会话已创建，正在提交任务...', { id: 'skill-exec' });
          } else {
            throw new Error('创建会话失败');
          }
        } catch (sessionError) {
          console.error('Failed to create session:', sessionError);
          toast.error('创建会话失败，请重试', { id: 'skill-exec' });
          setIsExecuting(false);
          return;
        }
      }

      const payload = {
        tool_id: selectedSkill.skill_id,
        parameters: {
          ...paramValues,
          session_id: sessionId || 1,
          project_id: currentProjectId
        },
        project_id: currentProjectId
      };

      const result = await fetchAPI('/tasks/submit', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      // ✨ P4 埋点：技能执行
      analytics.skillExecute(selectedSkill.skill_id, selectedSkill.name, payload.parameters);

      if (result.status === 'submitted') {
        setTaskId(result.task_id);
        toast.success('任务已提交，正在后台执行', { id: 'skill-exec' });
        // ✨ P1 错误恢复：传递执行参数用于失败时诊断
        pollTaskStatus(result.task_id, selectedSkill.skill_id, selectedSkill.name, payload.parameters);
      } else {
        setTaskStatus('FAILURE');
        setIsExecuting(false);
        setExecutionStartTime(null); // ✨ P2: 重置执行时间
        toast.error('任务提交失败', { id: 'skill-exec' });
      }
    } catch (e) {
      setTaskStatus('FAILURE');
      setIsExecuting(false);
      setExecutionStartTime(null); // ✨ P2: 重置执行时间
      toast.error('任务提交失败，请检查网络连接', { id: 'skill-exec' });
    }
  };

  // 轮询任务状态
  const pollTaskStatus = async (id: string, skillId: string, skillName: string, executedParams: Record<string, unknown>) => {
    const poll = async () => {
      try {
        const res = await fetch(`${BASE_URL}/api/tasks/${id}/status`);
        const data = await res.json();
        setTaskStatus(data.status);

        if (data.status === 'SUCCESS') {
          setIsExecuting(false);
          setExecutionStartTime(null); // ✨ P2: 重置执行时间
          // 清除错误状态
          setErrorDiagnosis(null);
          setShowErrorPanel(false);
          setLastFailedParams(null);

          // ✨ P4 埋点：执行成功
          if (selectedSkill) {
            const executionTime = executionStartTime ? (Date.now() - executionStartTime) / 1000 : 0;
            analytics.skillSuccess(selectedSkill.skill_id, selectedSkill.name, executionTime);
          }

          toast.success('SKILL执行完成！', {
            id: 'skill-complete',
            description: '结果已保存到输出目录',
            action: {
              label: '查看结果',
              onClick: () => onDataCenterOpen?.()
            }
          });
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('refresh-chat'));
          }, 500);
        } else if (data.status === 'FAILURE') {
          setIsExecuting(false);
          setExecutionStartTime(null); // ✨ P2: 重置执行时间

          // ✨ P1 错误恢复：保存失败参数
          setLastFailedParams(executedParams);

          // ✨ P4 埋点：执行失败
          analytics.skillFailure(skillId, skillName, logs.slice(-5).join('\n') || 'Unknown error');

          // ✨ P1 错误恢复：获取错误日志并诊断
          const errorLog = logs.join('\n');
          if (errorLog) {
            diagnoseError(skillId, skillName, executedParams, errorLog);
          } else {
            // 尝试从任务详情获取错误信息
            fetchTaskError(id, skillId, skillName, executedParams);
          }

          toast.error('SKILL执行失败', {
            id: 'skill-failed',
            description: '请查看错误诊断和修复建议',
            action: {
              label: '查看诊断',
              onClick: () => setShowErrorPanel(true)
            }
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

  // ✨ P1 错误恢复：诊断错误
  const diagnoseError = async (
    skillId: string,
    skillName: string,
    params: Record<string, unknown>,
    errorLog: string
  ) => {
    try {
      const result = await errorDiagnosticApi.diagnose({
        error_log: errorLog,
        exit_code: 1,
        language: skillId.toLowerCase().includes('r') ? 'r' : 'python',
        context: { skill_id: skillId, params }
      });

      if (result.status === 'success' && result.diagnosis) {
        setErrorDiagnosis(result.diagnosis);
        setShowErrorPanel(true);

        // 保存到本地存储
        executionStateApi.saveParams({
          skillId,
          skillName,
          parameters: params,
          timestamp: Date.now(),
          status: 'failed',
          errorMessage: result.diagnosis.message,
          errorDiagnosis: result.diagnosis
        });
      }
    } catch (e) {
      console.error('Error diagnosis failed:', e);
    }
  };

  // ✨ P1 错误恢复：从任务详情获取错误
  const fetchTaskError = async (
    taskId: string,
    skillId: string,
    skillName: string,
    params: Record<string, unknown>
  ) => {
    try {
      const res = await fetch(`${BASE_URL}/api/tasks/${taskId}`);
      const data = await res.json();

      if (data.error || data.traceback) {
        const errorLog = data.traceback || data.error || 'Unknown error';
        diagnoseError(skillId, skillName, params, errorLog);
      }
    } catch (e) {
      console.error('Failed to fetch task error:', e);
    }
  };

  // ✨ P1 错误恢复：一键修复
  const handleAutoFix = async (suggestion: FixSuggestion) => {
    if (!suggestion.auto_fixable) {
      toast.info('此问题需要手动修复');
      return;
    }

    if (!errorDiagnosis) return;

    toast.loading('正在尝试修复...', { id: 'auto-fix' });

    try {
      const result = await errorDiagnosticApi.fix(
        errorDiagnosis.error_type,
        errorDiagnosis.module_name,
        errorDiagnosis.file_path,
        selectedSkill?.skill_id?.toLowerCase().includes('r') ? 'r' : 'python'
      );

      if (result.success) {
        toast.success(result.message, { id: 'auto-fix' });
        // 显示修复详情
        if (result.details?.install_command) {
          toast.info(`安装命令: ${result.details.install_command}`, { duration: 5000 });
        }
      } else {
        toast.error(result.message, { id: 'auto-fix' });
      }
    } catch (e) {
      toast.error('修复失败', { id: 'auto-fix' });
    }
  };

  // ✨ P1 错误恢复：重新执行
  const handleRetry = async () => {
    if (!lastFailedParams || !selectedSkill) return;

    // 恢复参数
    setParamValues(lastFailedParams);

    // 延迟执行，让参数状态更新
    setTimeout(() => {
      handleExecute();
    }, 100);
  };

  // 渲染参数表单控件
  const renderParamInput = (key: string, prop: SkillParameter) => {
    const value = paramValues[key];
    const paramType = prop.type?.toLowerCase() || '';
    // 统一处理 format：移除连字符并转小写，兼容 'file-path' 和 'filepath' 两种写法
    const paramFormat = (prop.format || '').toLowerCase().replace(/-/g, '');

    // Sample Table 类型 - 新增
    if (paramFormat === 'sampletable') {
      // 根据 skill_id 判断类型
      const skillType = selectedSkill?.skill_id?.toLowerCase().includes('fastqc') ? 'fastqc'
        : selectedSkill?.skill_id?.toLowerCase().includes('singlecell') ? 'singlecell'
        : 'generic';

      return (
        <SkillSheetInput
          projectId={currentProjectId || ''}
          skillId={selectedSkill?.skill_id || ''}
          value={String(value || '')}
          onChange={(path) => setParamValues({ ...paramValues, [key]: path })}
          skillType={skillType}
        />
      );
    }

    // ComparisonTable 类型 - 比较组定义表
    // 使用 FilePicker 让用户选择已保存的比较组文件
    if (paramFormat === 'comparisontable') {
      return (
        <div className="space-y-2">
          <FilePickerButton
            projectId={currentProjectId || ''}
            value={String(value || '')}
            onChange={(path) => setParamValues({ ...paramValues, [key]: path })}
            type="file"
            placeholder="选择比较组文件..."
          />
          <p className="text-xs text-neutral-500">
            可选：比较组定义文件（TSV格式）。若不提供，将自动从 Sample Sheet 推断。
          </p>
        </div>
      );
    }

    // DirectoryPath 类型 - 兼容 'directory-path' 和 'directorypath'
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

    // FilePath 类型 - 兼容 'file-path' 和 'filepath'
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

    // Boolean 类型
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

    // Number/Integer 类型
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

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      {/* ✨ 过滤模式切换按钮 - 仅当 skillFilterMode 为 'basic' 时显示 */}
      {skillFilterMode === 'basic' && (
        <div className="shrink-0 flex items-center justify-between px-4 py-2 bg-blue-500/10 border-b border-blue-500/20">
          <div className="flex items-center gap-2 text-sm text-blue-300">
            <Filter size={14} />
            <span>基础分析模式</span>
          </div>
          <button
            onClick={() => setSkillFilterMode('all')}
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            显示全部技能
          </button>
        </div>
      )}

      {/* 主内容区域 - 响应式布局 */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {isMobile ? (
          // ============================================================
          // 移动端: 步骤向导布局 (3步：分类 → 技能 → 参数)
          // 解决移动端三栏无法并排显示的问题
          // ============================================================
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* 步骤指示器 - 固定顶部 */}
            <div className="shrink-0 px-4 py-3 border-b border-neutral-800 bg-neutral-900/50">
              <div className="flex items-center justify-between">
                {/* 返回按钮 - 仅在非第一步显示 */}
                <button
                  onClick={() => {
                    if (mobileViewStep === 'skills') setMobileViewStep('category');
                    if (mobileViewStep === 'params') setMobileViewStep('skills');
                  }}
                  className={cn(
                    "flex items-center gap-1 text-sm text-neutral-400 min-h-[44px] min-w-[44px]",
                    mobileViewStep === 'category' ? 'invisible' : 'hover:text-neutral-200'
                  )}
                >
                  <ChevronLeft size={18} />
                  返回
                </button>

                {/* 步骤指示点 */}
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "w-2 h-2 rounded-full transition-colors",
                    mobileViewStep === 'category' ? 'bg-blue-500' : 'bg-neutral-600'
                  )} />
                  <span className={cn(
                    "w-2 h-2 rounded-full transition-colors",
                    mobileViewStep === 'skills' ? 'bg-blue-500' : 'bg-neutral-600'
                  )} />
                  <span className={cn(
                    "w-2 h-2 rounded-full transition-colors",
                    mobileViewStep === 'params' ? 'bg-blue-500' : 'bg-neutral-600'
                  )} />
                </div>

                {/* 占位 - 保持布局平衡 */}
                <div className="w-12" />
              </div>

              {/* 步骤标题 */}
              <div className="mt-2 text-center">
                <span className="text-xs text-neutral-500">
                  {mobileViewStep === 'category' && '选择分类'}
                  {mobileViewStep === 'skills' && '选择技能'}
                  {mobileViewStep === 'params' && '参数配置'}
                </span>
              </div>
            </div>

            {/* 步骤内容 - 可滚动 */}
            <div className="flex-1 min-h-0 overflow-hidden">
              {/* Step 1: 分类选择 */}
              {mobileViewStep === 'category' && (
                <MobileCategoryPanel
                  categories={BUILT_IN_CATEGORIES}
                  categoryCounts={categoryCounts}
                  selectedCategory={selectedCategory}
                  expandedCategories={expandedCategories}
                  toggleCategoryExpand={toggleCategoryExpand}
                  onSelect={(categoryId) => {
                    setSelectedCategory(categoryId);
                    setMobileViewStep('skills');
                  }}
                />
              )}

              {/* Step 2: 技能选择 */}
              {mobileViewStep === 'skills' && (
                <MobileSkillListPanel
                  skills={filteredSkills}
                  isLoading={isLoading}
                  searchQuery={searchQuery}
                  setSearchQuery={setSearchQuery}
                  selectedSkill={selectedSkill}
                  onSelect={(skill) => {
                    setSelectedSkill(skill);
                    setMobileViewStep('params');
                  }}
                  onViewDetail={(skillId) => setDetailSkillId(skillId)}
                />
              )}

              {/* Step 3: 参数配置 */}
              {mobileViewStep === 'params' && selectedSkill && (
                <MobileParamConfigPanel
                  skill={selectedSkill}
                  paramValues={paramValues}
                  setParamValues={setParamValues}
                  isExecuting={isExecuting}
                  taskStatus={taskStatus}
                  taskId={taskId}
                  logs={logs}
                  currentProjectId={currentProjectId}
                  onExecute={handleExecute}
                  onViewDetail={() => setDetailSkillId(selectedSkill.skill_id)}
                  onAttachToChat={() => {
                    setPendingChatSkill({
                      skill_id: selectedSkill.skill_id,
                      name: selectedSkill.name,
                      executor_type: selectedSkill.executor_type
                    });
                    closeAllOverlays();
                    toast.success('技能已附加到聊天', {
                      description: '发送消息时 AI 将直接调用此技能'
                    });
                  }}
                  renderParamInput={renderParamInput}
                  terminalEndRef={terminalEndRef}
                />
              )}
            </div>
          </div>
        ) : (
          // ============================================================
          // 桌面端: 保持现有三栏布局
          // ============================================================
          <div className="flex-1 min-h-0 flex overflow-hidden">
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
            const count = categoryCounts[category.id] || 0;

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
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-500">
                    {count}
                  </span>
                  {hasSubcategories && (
                    <span className="text-neutral-500">
                      {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    </span>
                  )}
                </button>

                {/* 子分类 */}
                {hasSubcategories && isExpanded && (
                  <div className="ml-4 mt-1 space-y-0.5">
                    {category.subcategories!.map((sub) => {
                      const subCount = categoryCounts[sub.id] || 0;
                      return (
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
                          <span className="text-xs flex-1">{sub.name}</span>
                          <span className="text-[9px] px-1 py-0.5 rounded bg-neutral-800/50 text-neutral-600">
                            {subCount}
                          </span>
                        </button>
                      );
                    })}
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
                <div
                  key={skill.skill_id}
                  onClick={() => setSelectedSkill(skill)}
                  className={`w-full text-left p-3 rounded-lg transition-all cursor-pointer ${
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
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setDetailSkillId(skill.skill_id);
                      }}
                      className="p-1.5 hover:bg-neutral-700 rounded text-neutral-500 hover:text-neutral-300 transition-colors"
                      title="查看详情"
                    >
                      <Info size={14} />
                    </button>
                    <ChevronRight size={14} className="shrink-0 opacity-40" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right Panel: 参数配置面板 (flex-1) */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {selectedSkill ? (
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            {/* SKILL Info */}
            <div className="shrink-0 p-4 border-b border-neutral-800 bg-neutral-900/20">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-neutral-200">{selectedSkill.name}</h3>
                <div className="flex items-center gap-1">
                  {/* ✨ 收藏到首页按钮 - 支持切换收藏状态 */}
                  <button
                    onClick={() => {
                      const isPinned = pinnedSkillsApi.isPinned(selectedSkill.skill_id);
                      if (isPinned) {
                        pinnedSkillsApi.unpinSkill(selectedSkill.skill_id);
                        toast.success(`「${selectedSkill.name}」已取消收藏`);
                      } else {
                        pinnedSkillsApi.pinSkill({
                          skill_id: selectedSkill.skill_id,
                          name: selectedSkill.name,
                          description: selectedSkill.description,
                          executor_type: selectedSkill.executor_type,
                          pinned_at: Date.now(),
                        });
                        toast.success(`「${selectedSkill.name}」已收藏到首页`);
                      }
                    }}
                    className={cn(
                      "p-1.5 rounded transition-colors",
                      pinnedSkillsApi.isPinned(selectedSkill.skill_id)
                        ? "bg-blue-500/20 text-blue-400 hover:bg-blue-500/30"
                        : "hover:bg-neutral-800 text-neutral-500 hover:text-blue-400"
                    )}
                    title={pinnedSkillsApi.isPinned(selectedSkill.skill_id) ? "取消收藏" : "收藏到首页"}
                  >
                    <Pin size={16} />
                  </button>
                  <button
                    onClick={() => setDetailSkillId(selectedSkill.skill_id)}
                    className="p-1.5 hover:bg-neutral-800 rounded text-neutral-500 hover:text-neutral-300 transition-colors"
                    title="查看详情"
                  >
                    <Info size={16} />
                  </button>
                </div>
              </div>
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

            {/* Parameters Form - 可滚动区域 */}
            <div className="flex-1 min-h-0 max-h-[calc(100vh-380px)] overflow-y-auto overflow-x-hidden p-4 custom-scrollbar">
              <h4 className="text-sm font-medium text-neutral-400 mb-3 sticky top-0 bg-neutral-900/95 pb-2 z-10">参数配置</h4>
              {selectedSkill.parameters_schema?.properties &&
              Object.keys(selectedSkill.parameters_schema.properties).length > 0 ? (
                // ✨ P4 参数智能分组 - 使用 ParameterGroupPanel 组件
                <ParameterGroupPanel
                  schema={selectedSkill.parameters_schema}
                  paramValues={paramValues}
                  onParamChange={(key, value) => setParamValues({ ...paramValues, [key]: value })}
                  renderParamInput={renderParamInput}
                />
              ) : (
                <div className="text-sm text-neutral-500">该 SKILL 无需配置参数</div>
              )}
            </div>

            {/* ✨ P2 等待体验优化 - 使用新的 ExecutionProgress 组件 */}
            <ExecutionProgress
              isExecuting={isExecuting}
              taskStatus={taskStatus}
              taskId={taskId}
              logs={logs}
              startTime={executionStartTime}
              estimatedDuration={estimatedDuration}
              skillName={selectedSkill?.name}
            />

            {/* 实时日志显示 */}
            {taskId && (
              <div className="shrink-0 border-t border-neutral-800">
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

            {/* Execute Buttons */}
            <div className="shrink-0 p-4 border-t border-neutral-800 space-y-2">
              {/* ✨ 附加到聊天按钮 - 新增 */}
              <button
                onClick={() => {
                  if (selectedSkill) {
                    setPendingChatSkill({
                      skill_id: selectedSkill.skill_id,
                      name: selectedSkill.name,
                      executor_type: selectedSkill.executor_type
                    });
                    closeAllOverlays();
                    // 提示用户
                    toast.success('技能已附加到聊天', {
                      description: '发送消息时 AI 将直接调用此技能'
                    });
                  }
                }}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 text-purple-300 font-medium rounded-lg transition-colors"
              >
                <MessageSquarePlus size={16} />
                附加到聊天
              </button>

              {/* 执行按钮 */}
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
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-neutral-600 gap-3">
            <Box size={48} className="opacity-20" />
            <p className="text-sm">选择左侧的 SKILL 开始分析</p>
          </div>
        )}
      </div>
          </div>
        )}
      </div>

      {/* 技能详情抽屉 */}
      {detailSkillId && (
        <SkillDetailDrawer
          skillId={detailSkillId}
          onClose={() => setDetailSkillId(null)}
          onUse={(skillId) => {
            const skill = skills.find(s => s.skill_id === skillId);
            if (skill) {
              setSelectedSkill(skill);
            }
            setDetailSkillId(null);
          }}
        />
      )}

      {/* ✨ P1 错误恢复：错误诊断面板 */}
      {showErrorPanel && errorDiagnosis && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-neutral-900 border border-neutral-700 rounded-xl max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col">
            {/* 标题栏 */}
            <div className="flex items-center justify-between p-4 border-b border-neutral-800">
              <div className="flex items-center gap-2">
                <AlertTriangle className={cn(
                  "w-5 h-5",
                  errorDiagnosis.severity === 'high' || errorDiagnosis.severity === 'critical'
                    ? "text-red-500"
                    : "text-yellow-500"
                )} />
                <h3 className="font-medium text-lg">{errorDiagnosis.title}</h3>
              </div>
              <button
                onClick={() => setShowErrorPanel(false)}
                className="text-neutral-400 hover:text-white transition-colors"
              >
                ✕
              </button>
            </div>

            {/* 内容区 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* 错误描述 */}
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
                <p className="text-red-200">{errorDiagnosis.message}</p>
                {errorDiagnosis.module_name && (
                  <p className="text-sm text-red-300 mt-2">
                    缺失模块: <code className="bg-red-500/20 px-1 rounded">{errorDiagnosis.module_name}</code>
                  </p>
                )}
                {errorDiagnosis.file_path && (
                  <p className="text-sm text-red-300 mt-2">
                    相关路径: <code className="bg-red-500/20 px-1 rounded">{errorDiagnosis.file_path}</code>
                  </p>
                )}
              </div>

              {/* 修复建议 */}
              <div>
                <h4 className="text-sm font-medium text-neutral-400 mb-3">修复建议</h4>
                <div className="space-y-2">
                  {errorDiagnosis.suggestions.map((suggestion, idx) => (
                    <div
                      key={idx}
                      className="bg-neutral-800/50 border border-neutral-700 rounded-lg p-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <p className="text-sm text-neutral-200">{suggestion.description}</p>
                          {suggestion.fix_command && (
                            <code className="block mt-2 text-xs bg-neutral-900 px-2 py-1 rounded text-green-400">
                              {suggestion.fix_command}
                            </code>
                          )}
                          {suggestion.manual_steps.length > 0 && (
                            <ul className="mt-2 text-xs text-neutral-400 space-y-1">
                              {suggestion.manual_steps.map((step, stepIdx) => (
                                <li key={stepIdx}>• {step}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                        {suggestion.auto_fixable && (
                          <button
                            onClick={() => handleAutoFix(suggestion)}
                            className="shrink-0 flex items-center gap-1 px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 text-blue-300 text-sm rounded transition-colors"
                          >
                            <Wrench size={14} />
                            一键修复
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 原始错误（折叠） */}
              <details className="text-xs">
                <summary className="cursor-pointer text-neutral-500 hover:text-neutral-400">
                  查看原始错误日志
                </summary>
                <pre className="mt-2 p-3 bg-neutral-900 rounded text-neutral-400 overflow-x-auto max-h-40">
                  {errorDiagnosis.original_error}
                </pre>
              </details>
            </div>

            {/* 操作按钮 */}
            <div className="p-4 border-t border-neutral-800 flex gap-2">
              <button
                onClick={handleRetry}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg transition-colors"
              >
                <RefreshCw size={16} />
                重新执行
              </button>
              <button
                onClick={() => setShowErrorPanel(false)}
                className="px-4 py-2.5 bg-neutral-700 hover:bg-neutral-600 text-neutral-200 font-medium rounded-lg transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
