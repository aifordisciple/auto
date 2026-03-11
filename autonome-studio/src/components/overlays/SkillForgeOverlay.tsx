"use client";

import React, { useState, useEffect, useRef } from 'react';
import { skillForgeApi, ExecutorType, CraftRequest } from '@/lib/api';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { Play, Hammer, Save, Send, Code, Terminal, FileJson, AlertTriangle, CheckCircle, FolderTree, GitBranch, X, Box, Sparkles, Upload, FileText, Folder, Loader2, FileCode } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useUIStore } from '@/store/useUIStore';
import { FilePickerButton } from '@/components/FilePicker';
import { fetchAPI, BASE_URL } from '@/lib/api';
import { fetchEventSource } from '@microsoft/fetch-event-source';

// 执行器类型配置 (移除了 Python_Package)
const EXECUTOR_TYPES: { value: ExecutorType; label: string; icon: React.ReactNode; description: string }[] = [
  {
    value: 'Python_env',
    label: 'Python 脚本',
    icon: <Code size={16} />,
    description: '单 Python 脚本，使用 argparse 参数化'
  },
  {
    value: 'R_env',
    label: 'R 脚本',
    icon: <Code size={16} />,
    description: '单 R 脚本，使用 commandArgs 参数化'
  },
  {
    value: 'Logical_Blueprint',
    label: 'Nextflow 工作流',
    icon: <GitBranch size={16} />,
    description: 'Nextflow DSL2 并行工作流'
  }
];

// 参数类型接口
interface SkillParameter {
  type: string;
  format?: string;
  description?: string;
  default?: unknown;
}

interface SkillSchema {
  type: string;
  properties: Record<string, SkillParameter>;
  required: string[];
}

// 附件接口
interface Attachment {
  id: string;
  name: string;
  size: number;
  type: string;
  content: string;
}

// 技能列表项接口
interface SkillListItem {
  skill_id: string;
  name: string;
  executor_type: string;
  category_name?: string;
}

// 编辑器 Tab 类型
type EditorTab = 'code' | 'skillmd';

export function SkillForgeOverlay() {
  const { isSkillForgeOpen, closeAllOverlays } = useUIStore();
  const { currentProjectId, currentSessionId } = useWorkspaceStore();

  // 状态管理
  const [rawMaterial, setRawMaterial] = useState('');
  const [isCrafting, setIsCrafting] = useState(false);

  // 执行器类型和文件系统生成选项
  const [executorType, setExecutorType] = useState<ExecutorType>('Python_env');
  const [generateFullBundle, setGenerateFullBundle] = useState(false);
  const [skillNameHint, setSkillNameHint] = useState('');

  const [craftedSkill, setCraftedSkill] = useState<Record<string, any> | null>(null);
  const [scriptCode, setScriptCode] = useState('');
  const [nextflowCode, setNextflowCode] = useState('');
  const [skillName, setSkillName] = useState('');
  const [skillDescription, setSkillDescription] = useState('');
  const [skillMdContent, setSkillMdContent] = useState('');

  // 生成的文件系统信息
  const [bundlePath, setBundlePath] = useState<string | null>(null);
  const [filesCreated, setFilesCreated] = useState<string[]>([]);

  // 锻造日志
  const [craftLogs, setCraftLogs] = useState('');

  // 自动测试状态
  const [isAutoTesting, setIsAutoTesting] = useState(false);
  const [autoTestPassed, setAutoTestPassed] = useState<boolean | null>(null);

  // 手动测试状态
  const [paramValues, setParamValues] = useState<Record<string, unknown>>({});
  const [isManualTesting, setIsManualTesting] = useState(false);
  const [manualTestLogs, setManualTestLogs] = useState<string[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  const [isSaving, setIsSaving] = useState(false);
  const [validationWarning, setValidationWarning] = useState('');

  // 技能列表
  const [skills, setSkills] = useState<SkillListItem[]>([]);
  const [isLoadingSkills, setIsLoadingSkills] = useState(false);

  // 附件上传
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 编辑器 Tab
  const [activeEditorTab, setActiveEditorTab] = useState<EditorTab>('code');

  // 自动滚动日志
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [manualTestLogs]);

  // 日志流式读取
  useEffect(() => {
    if (!taskId) return;

    setManualTestLogs([]);
    const controller = new AbortController();

    const connectToLogStream = async () => {
      try {
        await fetchEventSource(`${BASE_URL}/api/tasks/${taskId}/logs/stream`, {
          method: 'GET',
          signal: controller.signal,
          onmessage(event) {
            if (event.event === 'log') {
              const data = JSON.parse(event.data);
              setManualTestLogs(prev => [...prev, data.text]);
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

  // 加载技能列表
  useEffect(() => {
    if (isSkillForgeOpen) {
      fetchSkills();
    }
  }, [isSkillForgeOpen]);

  const fetchSkills = async () => {
    setIsLoadingSkills(true);
    try {
      const data = await skillForgeApi.getCatalog();
      if (data.status === 'success') {
        setSkills(data.data || []);
      }
    } catch (e) {
      console.error('Failed to fetch skills:', e);
    } finally {
      setIsLoadingSkills(false);
    }
  };

  // 选择技能时初始化参数
  useEffect(() => {
    if (craftedSkill && craftedSkill.parameters_schema?.properties) {
      const defaults: Record<string, unknown> = {};
      Object.entries(craftedSkill.parameters_schema.properties).forEach(([key, prop]) => {
        defaults[key] = prop.default ?? '';
      });
      setParamValues(defaults);
    }
  }, [craftedSkill]);

  // 处理文件上传
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    for (const file of files) {
      // 检查文件大小限制
      const maxSize = file.type.startsWith('image/') ? 5 * 1024 * 1024 : 10 * 1024 * 1024;
      if (file.size > maxSize) {
        alert(`文件 ${file.name} 超过大小限制 (${file.type.startsWith('image/') ? '5MB' : '10MB'})`);
        continue;
      }

      try {
        const content = await readFileContent(file);
        const attachment: Attachment = {
          id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          name: file.name,
          size: file.size,
          type: file.type || 'text/plain',
          content
        };
        setAttachments(prev => [...prev, attachment]);

        // 自动将内容添加到素材区
        setRawMaterial(prev => {
          if (prev) {
            return `${prev}\n\n--- ${file.name} ---\n${content}`;
          }
          return `--- ${file.name} ---\n${content}`;
        });
      } catch (err) {
        console.error('Failed to read file:', err);
        alert(`无法读取文件 ${file.name}`);
      }
    }

    // 清空 input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // 读取文件内容
  const readFileContent = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        resolve(reader.result as string);
      };
      reader.onerror = reject;

      // 根据文件类型选择读取方式
      if (file.type.startsWith('image/')) {
        reader.readAsDataURL(file);
      } else {
        reader.readAsText(file);
      }
    });
  };

  // 移除附件
  const removeAttachment = (id: string) => {
    setAttachments(prev => prev.filter(a => a.id !== id));
  };

  // 格式化文件大小
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // 触发 AI 锻造
  const handleCraft = async () => {
    if (!rawMaterial || rawMaterial.trim().length < 10) {
      alert("请先输入原始素材（至少10个字符）");
      return;
    }

    setIsCrafting(true);
    setCraftLogs("🔨 正在呼叫大模型进行逆向提取与参数推导...\n");
    setValidationWarning('');
    setBundlePath(null);
    setFilesCreated([]);
    setAutoTestPassed(null);
    setActiveEditorTab('code');

    try {
      const request: CraftRequest = {
        raw_material: rawMaterial,
        executor_type: executorType,
        generate_full_bundle: generateFullBundle,
        skill_name_hint: skillNameHint || undefined
      };

      const result = await skillForgeApi.craftFromMaterial(request);
      setCraftedSkill(result.data);
      setScriptCode(result.data.script_code || '');
      setNextflowCode(result.data.nextflow_code || '');
      setSkillName(result.data.name || '');
      setSkillDescription(result.data.description || '');

      // 设置 SKILL.md 内容
      if (result.data.skill_md) {
        setSkillMdContent(result.data.skill_md);
      } else {
        // 生成默认的 SKILL.md
        setSkillMdContent(generateDefaultSkillMd(result.data));
      }

      // 设置文件系统信息
      if (result.bundle_path) {
        setBundlePath(result.bundle_path);
        setFilesCreated(result.files_created || []);
      }

      // 检查校验结果
      if (result.data.validation_warning) {
        setValidationWarning(result.data.validation_warning);
        setCraftLogs(prev => prev + `⚠️ 校验警告: ${result.data.validation_warning}\n`);
      } else if (result.data.validation_passed) {
        setCraftLogs(prev => prev + "✅ 锻造成功！代码已通过铁律校验。\n");
      } else {
        setCraftLogs(prev => prev + "✅ 锻造成功！已生成标准参数面板与规范化代码。\n");
      }

      // 显示生成的文件
      if (result.files_created && result.files_created.length > 0) {
        setCraftLogs(prev => prev + `\n📁 已生成文件系统技能包:\n`);
        result.files_created.forEach((file: string) => {
          setCraftLogs(prev => prev + `  - ${file}\n`);
        });
        setCraftLogs(prev => prev + `\n路径: ${result.bundle_path}\n`);
      }

      // ===== Phase 2: 自动测试整合 =====
      // 仅对单脚本类型自动测试
      if ((executorType === 'Python_env' || executorType === 'R_env') && result.data.script_code) {
        setCraftLogs(prev => prev + "\n🚀 启动自动测试...\n");
        setIsAutoTesting(true);

        try {
          const testResult = await skillForgeApi.testDraftSkill({
            scriptCode: result.data.script_code,
            testInstruction: '',
            parametersSchema: result.data.parameters_schema,
            autoGenerateData: true,
            maxTestRounds: 3
          });

          // 显示测试结果
          if (testResult.logs) {
            setCraftLogs(prev => prev + testResult.logs + '\n');
          }

          if (testResult.test_scenarios && testResult.test_scenarios.length > 0) {
            setCraftLogs(prev => prev + '\n📊 测试场景汇总:\n');
            testResult.test_scenarios.forEach((scenario: any) => {
              const status = scenario.success ? '✅' : '❌';
              setCraftLogs(prev => prev + `  ${status} ${scenario.scenario} (尝试 ${scenario.attempts} 次)\n`);
            });
          }

          if (testResult.status === 'success') {
            setAutoTestPassed(true);
            setCraftLogs(prev => prev + "\n🎉 自动测试通过！\n");
          } else if (testResult.status === 'partial') {
            setAutoTestPassed(false);
            setCraftLogs(prev => prev + "\n⚠️ 部分测试场景通过。\n");
          } else {
            setAutoTestPassed(false);
            setCraftLogs(prev => prev + "\n❌ 自动测试失败。\n");
          }

          // 如果 AI 修复了代码，更新编辑器
          if (testResult.final_code && testResult.final_code !== result.data.script_code) {
            setScriptCode(testResult.final_code);
            setCraftLogs(prev => prev + "\n🤖 Debugger 已自动修复代码。\n");
          }
        } catch (testErr: any) {
          setAutoTestPassed(false);
          setCraftLogs(prev => prev + `\n⚠️ 自动测试失败: ${testErr.message}\n`);
        } finally {
          setIsAutoTesting(false);
        }
      }

    } catch (e: any) {
      setCraftLogs(prev => prev + `❌ 锻造失败: ${e.message}\n`);
    } finally {
      setIsCrafting(false);
    }
  };

  // 生成默认的 SKILL.md 内容
  const generateDefaultSkillMd = (data: Record<string, any>): string => {
    const meta = data || {};
    return `---
skill_id: "${meta.skill_id || 'custom_skill'}"
name: "${meta.name || '未命名技能'}"
version: "1.0.0"
executor_type: "${meta.executor_type || 'Python_env'}"
category: "general"
category_name: "通用"
tags: []
---

## 1. 技能意图与功能边界

${meta.description || '由 SKILL Forge 自动生成的标准化技能包。'}

## 2. 动态参数定义规范

| 参数键名 | 数据类型 | 必填 | 默认值 | 详细描述 |
|---|---|---|---|---|
${Object.entries(meta.parameters_schema?.properties || {}).map(([key, prop]: [string, any]) => {
  const isRequired = meta.parameters_schema?.required?.includes(key);
  return `| \`${key}\` | ${prop.type || 'string'} | ${isRequired ? '是' : '否'} | ${prop.default || ''} | ${prop.description || ''} |`;
}).join('\n')}

## 3. 操作指令与专家级知识库

${meta.expert_knowledge || '- 请根据实际数据情况配置必要的参数。'}
`;
  };

  // 手动测试执行
  const handleManualTest = async () => {
    if (!craftedSkill || !currentProjectId) {
      alert('请先锻造技能并选择项目');
      return;
    }

    setIsManualTesting(true);
    setTaskId(null);
    setTaskStatus(null);
    setManualTestLogs([]);

    try {
      const token = localStorage.getItem('autonome_access_token');
      const payload = {
        tool_id: craftedSkill.skill_id || `draft_${Date.now()}`,
        parameters: {
          ...paramValues,
          session_id: currentSessionId || 1,
          project_id: currentProjectId,
          _draft_script: scriptCode,
          _draft_executor_type: craftedSkill.executor_type || executorType
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
        setIsManualTesting(false);
        alert('任务提交失败');
      }
    } catch (e) {
      setTaskStatus('FAILURE');
      setIsManualTesting(false);
      alert('任务提交失败，请检查网络连接');
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
          setIsManualTesting(false);
        } else if (data.status === 'FAILURE') {
          setIsManualTesting(false);
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

    // DirectoryPath 类型
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

    // FilePath 类型
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
          className="w-full px-3 py-2 text-sm bg-gray-100 dark:bg-neutral-800 border border-gray-300 dark:border-neutral-700 rounded-lg text-gray-700 dark:text-neutral-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
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
          className="w-full px-3 py-2 text-sm bg-gray-100 dark:bg-neutral-800 border border-gray-300 dark:border-neutral-700 rounded-lg text-gray-700 dark:text-neutral-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      );
    }

    // 默认文本输入
    return (
      <input
        type="text"
        value={String(value ?? '')}
        onChange={(e) => setParamValues({ ...paramValues, [key]: e.target.value })}
        placeholder={prop.description || key}
        className="w-full px-3 py-2 text-sm bg-gray-100 dark:bg-neutral-800 border border-gray-300 dark:border-neutral-700 rounded-lg text-gray-700 dark:text-neutral-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
    );
  };

  // 是否显示手动测试（锻造成功后）
  const showManualTest = craftedSkill && (executorType === 'Python_env' || executorType === 'R_env');

  // 固化入库与提审
  const handleSaveAndSubmit = async () => {
    if (!craftedSkill) {
      alert("请先锻造一个技能");
      return;
    }

    setIsSaving(true);

    try {
      const payload = {
        name: skillName || craftedSkill.name || "未命名技能",
        description: skillDescription || craftedSkill.description || "",
        executor_type: craftedSkill.executor_type || "Python_env",
        parameters_schema: craftedSkill.parameters_schema || {},
        expert_knowledge: craftedSkill.expert_knowledge || "",
        script_code: scriptCode,
        dependencies: craftedSkill.dependencies || [],
        skill_md: skillMdContent
      };

      const savedSkill = await skillForgeApi.savePrivateSkill(payload);
      await skillForgeApi.submitForReview(savedSkill.skill_id);

      alert("✅ 技能已成功固化入库，并提交管理员审核！");
      closeAllOverlays();
    } catch (e: any) {
      alert(`保存失败: ${e.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  // 仅保存为私有
  const handleSaveOnly = async () => {
    if (!craftedSkill) {
      alert("请先锻造一个技能");
      return;
    }

    setIsSaving(true);

    try {
      const payload = {
        name: skillName || craftedSkill.name || "未命名技能",
        description: skillDescription || craftedSkill.description || "",
        executor_type: craftedSkill.executor_type || "Python_env",
        parameters_schema: craftedSkill.parameters_schema || {},
        expert_knowledge: craftedSkill.expert_knowledge || "",
        script_code: scriptCode,
        dependencies: craftedSkill.dependencies || [],
        skill_md: skillMdContent
      };

      const savedSkill = await skillForgeApi.savePrivateSkill(payload);
      alert(`✅ 技能已保存为私有！ID: ${savedSkill.skill_id}`);
      fetchSkills();
    } catch (e: any) {
      alert(`保存失败: ${e.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <AnimatePresence>
      {isSkillForgeOpen && (
        <>
          {/* 背景遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeAllOverlays}
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm cursor-pointer"
          />

          {/* 全屏浮层 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            className="fixed inset-0 z-50 bg-white dark:bg-[#131314] flex overflow-hidden font-sans"
          >
            {/* 左侧边栏 - 技能列表 */}
            <div className="w-56 shrink-0 border-r border-gray-200 dark:border-[#2d2d30] bg-gray-50 dark:bg-[#1e1e20] flex flex-col z-20">
              {/* Logo + 关闭按钮 */}
              <div className="h-14 shrink-0 flex items-center justify-between px-4 border-b border-gray-200 dark:border-neutral-800">
                <div className="flex items-center gap-2 text-gray-600 dark:text-white font-bold tracking-wider">
                  <span className="text-blue-500">🧬</span> AUTONOME
                </div>
                <button
                  onClick={closeAllOverlays}
                  className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md transition-colors"
                >
                  <X size={18} />
                </button>
              </div>

              {/* 技能工厂标题 */}
              <div className="px-4 py-3 border-b border-gray-200 dark:border-neutral-800">
                <div className="flex items-center gap-2 text-gray-900 dark:text-white font-semibold">
                  <Hammer size={16} className="text-blue-500" />
                  <span>技能工厂</span>
                </div>
                <p className="text-xs text-gray-500 dark:text-neutral-500 mt-1">锻造标准化分析模块</p>
              </div>

              {/* 技能列表 */}
              <div className="flex-1 overflow-y-auto p-2">
                <div className="text-xs text-gray-500 dark:text-neutral-500 px-2 py-2 font-medium">
                  已有技能 ({skills.length})
                </div>
                {isLoadingSkills ? (
                  <div className="flex items-center justify-center py-4 text-gray-400 dark:text-neutral-500">
                    <Sparkles size={16} className="animate-pulse" />
                  </div>
                ) : skills.length === 0 ? (
                  <div className="text-center py-4 text-xs text-gray-400 dark:text-neutral-600">
                    暂无技能
                  </div>
                ) : (
                  <div className="space-y-1">
                    {skills.map((skill) => (
                      <div
                        key={skill.skill_id}
                        className="flex items-center gap-2 p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-neutral-800/50 cursor-pointer transition-colors"
                      >
                        <Box size={14} className="text-blue-400 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-gray-700 dark:text-neutral-300 truncate">
                            {skill.name}
                          </p>
                          <p className="text-[10px] text-gray-400 dark:text-neutral-600 font-mono truncate">
                            {skill.skill_id}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* 主工作区 */}
            <div className="flex-1 flex flex-col h-screen overflow-hidden">
              {/* 顶部工具栏 */}
              <div className="h-14 bg-gray-100 dark:bg-[#1e1e1f] border-b border-gray-200 dark:border-neutral-800 flex items-center justify-between px-6 shrink-0">
                <div className="flex items-center gap-2">
                  <Hammer className="text-blue-500" size={20} />
                  <h1 className="font-semibold text-gray-900 dark:text-white">SKILL Forge 技能锻造工厂</h1>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={handleSaveOnly}
                    disabled={!craftedSkill || isSaving}
                    className="flex items-center gap-2 px-4 py-1.5 bg-gray-200 dark:bg-neutral-700 hover:bg-gray-300 dark:hover:bg-neutral-600 disabled:opacity-50 text-gray-700 dark:text-white text-sm rounded-lg transition-colors"
                  >
                    <Save size={16} />
                    保存为私有
                  </button>
                  <button
                    onClick={handleSaveAndSubmit}
                    disabled={!craftedSkill || isSaving}
                    className="flex items-center gap-2 px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
                  >
                    <Send size={16} />
                    {isSaving ? "正在提交..." : "保存并提交审核"}
                  </button>
                </div>
              </div>

              {/* 双栏工作区 */}
              <div className="flex-1 flex overflow-hidden">

                {/* 左栏：输入与测试 */}
                <div className="w-1/2 flex flex-col border-r border-gray-200 dark:border-neutral-800 bg-gray-50/50 dark:bg-[#1e1e1f]/50">
                  {/* 素材喂入区 */}
                  <div className="flex-1 p-4 flex flex-col border-b border-gray-200 dark:border-neutral-800 overflow-hidden">
                    <label className="text-xs text-gray-500 dark:text-neutral-500 font-medium mb-2 uppercase tracking-wider flex items-center gap-2 shrink-0">
                      <FileJson size={14} />
                      1. 喂入原始素材 (代码/指令/文献段落)
                    </label>
                    <textarea
                      value={rawMaterial}
                      onChange={e => setRawMaterial(e.target.value)}
                      placeholder="在此粘贴您写死的 R/Python 代码，或者直接输入自然语言指令...

示例：
• '帮我写一个用 scanpy 过滤单细胞矩阵的脚本，需要可调节线粒体比例阈值'
• '写一个 FastQC + MultiQC 质控工作流'
• 粘贴一段需要参数化的代码..."
                      className="flex-1 min-h-[120px] bg-white dark:bg-[#0d0d0e] border border-gray-300 dark:border-neutral-700 rounded-lg p-3 text-sm text-gray-700 dark:text-neutral-300 focus:border-blue-500 focus:outline-none resize-none"
                    />

                    {/* 附件上传区 */}
                    <div className="mt-2 shrink-0">
                      <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        accept=".py,.R,.r,.sh,.js,.ts,.java,.c,.cpp,.go,.md,.txt,.json,.yaml,.yml,.xml,.toml,.zip,.tar,.gz,.tgz"
                        onChange={handleFileUpload}
                        className="hidden"
                      />
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        className="flex items-center gap-2 px-3 py-1.5 bg-gray-200 dark:bg-neutral-700 hover:bg-gray-300 dark:hover:bg-neutral-600 text-gray-700 dark:text-white text-xs rounded-lg transition-colors"
                      >
                        <Upload size={14} />
                        上传附件
                      </button>

                      {/* 附件列表 */}
                      {attachments.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {attachments.map(att => (
                            <div key={att.id} className="flex items-center gap-2 px-2 py-1 bg-gray-100 dark:bg-neutral-800 rounded text-xs">
                              <FileText size={12} className="text-blue-400" />
                              <span className="flex-1 truncate text-gray-700 dark:text-neutral-300">{att.name}</span>
                              <span className="text-gray-400 dark:text-neutral-500">{formatFileSize(att.size)}</span>
                              <button
                                onClick={() => removeAttachment(att.id)}
                                className="text-gray-400 hover:text-red-500 transition-colors"
                              >
                                <X size={12} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* 执行器类型选择器 */}
                    <div className="mt-3 mb-2 shrink-0">
                      <label className="text-xs text-gray-500 dark:text-neutral-500 mb-2 block">执行器类型</label>
                      <div className="grid grid-cols-3 gap-2">
                        {EXECUTOR_TYPES.map(type => (
                          <button
                            key={type.value}
                            onClick={() => setExecutorType(type.value)}
                            className={`flex flex-col items-center justify-center p-2 rounded-lg border text-xs transition-all ${
                              executorType === type.value
                                ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400'
                                : 'border-gray-300 dark:border-neutral-700 bg-white dark:bg-neutral-800/50 text-gray-600 dark:text-neutral-400 hover:border-gray-400 dark:hover:border-neutral-600'
                            }`}
                            title={type.description}
                          >
                            {type.icon}
                            <span className="mt-1">{type.label}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* 选项区域 */}
                    <div className="flex gap-4 mt-2 shrink-0">
                      <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-neutral-500 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={generateFullBundle}
                          onChange={e => setGenerateFullBundle(e.target.checked)}
                          className="rounded border-gray-400 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-blue-500 focus:ring-blue-500"
                        />
                        <FolderTree size={14} />
                        生成完整文件系统目录
                      </label>
                      {generateFullBundle && (
                        <input
                          type="text"
                          value={skillNameHint}
                          onChange={e => setSkillNameHint(e.target.value)}
                          placeholder="技能名称提示（可选）"
                          className="flex-1 bg-white dark:bg-[#0d0d0e] border border-gray-300 dark:border-neutral-700 rounded px-2 py-1 text-xs text-gray-700 dark:text-neutral-300 focus:border-blue-500 focus:outline-none"
                        />
                      )}
                    </div>

                    <button
                      onClick={handleCraft}
                      disabled={isCrafting}
                      className="mt-3 w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg font-medium flex justify-center items-center gap-2 disabled:opacity-50 shrink-0"
                    >
                      {isCrafting ? (
                        <>
                          <Loader2 size={16} className="animate-spin" />
                          AI 架构师正在锻造...
                        </>
                      ) : (
                        <>
                          <Hammer size={16} />
                          一键提炼标准技能包
                        </>
                      )}
                    </button>
                  </div>

                  {/* 锻造日志 */}
                  {craftLogs && (
                    <div className="h-[150px] p-3 flex flex-col shrink-0 border-t border-gray-200 dark:border-neutral-800">
                      <label className="text-xs text-gray-500 dark:text-neutral-500 font-medium mb-1 uppercase tracking-wider flex items-center gap-2">
                        <Terminal size={14} />
                        锻造日志
                        {isAutoTesting && <Loader2 size={12} className="animate-spin text-blue-400" />}
                        {autoTestPassed === true && <CheckCircle size={12} className="text-green-400" />}
                        {autoTestPassed === false && <AlertTriangle size={12} className="text-yellow-400" />}
                      </label>
                      <textarea
                        readOnly
                        value={craftLogs}
                        className="flex-1 bg-black border border-gray-700 dark:border-neutral-800 rounded p-2 text-[10px] text-emerald-400 font-mono focus:outline-none resize-none"
                      />
                    </div>
                  )}

                  {/* 手动测试面板 */}
                  {showManualTest && craftedSkill?.parameters_schema?.properties && (
                    <div className="h-[200px] p-3 flex flex-col shrink-0 border-t border-gray-200 dark:border-neutral-800">
                      <label className="text-xs text-gray-500 dark:text-neutral-500 font-medium mb-2 uppercase tracking-wider flex items-center gap-2">
                        <Play size={14} />
                        手动测试
                      </label>
                      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                        {Object.entries(craftedSkill.parameters_schema.properties).slice(0, 4).map(([key, prop]) => (
                          <div key={key}>
                            <label className="text-[10px] text-gray-500 dark:text-neutral-500 mb-0.5 block">{key}</label>
                            {renderParamInput(key, prop as SkillParameter)}
                          </div>
                        ))}
                      </div>
                      <button
                        onClick={handleManualTest}
                        disabled={isManualTesting || !currentProjectId}
                        className="mt-2 w-full py-1.5 bg-purple-600 hover:bg-purple-500 text-white text-xs rounded-lg font-medium flex justify-center items-center gap-2 disabled:opacity-50"
                      >
                        {isManualTesting ? (
                          <>
                            <Loader2 size={12} className="animate-spin" />
                            执行中...
                          </>
                        ) : (
                          <>
                            <Play size={12} />
                            运行测试
                          </>
                        )}
                      </button>
                    </div>
                  )}

                  {/* 手动测试日志 */}
                  {taskId && (
                    <div className="h-[120px] border-t border-gray-200 dark:border-neutral-800 flex flex-col shrink-0">
                      <div className="px-3 py-2 border-b border-gray-200 dark:border-neutral-800 flex items-center gap-2 bg-gray-100/50 dark:bg-neutral-900/30">
                        <Terminal size={12} className="text-green-400" />
                        <span className="text-[10px] font-medium text-gray-500 dark:text-neutral-400">执行日志</span>
                        {taskStatus && (
                          <span className={`text-[10px] ml-auto ${
                            taskStatus === 'SUCCESS' ? 'text-green-400' :
                            taskStatus === 'FAILURE' ? 'text-red-400' : 'text-blue-400'
                          }`}>
                            {taskStatus}
                          </span>
                        )}
                      </div>
                      <div className="flex-1 overflow-y-auto p-2 bg-black font-mono text-[10px] text-green-400/90">
                        {manualTestLogs.length === 0 ? (
                          <div className="flex items-center justify-center h-full text-gray-600 gap-2">
                            <Loader2 size={12} className="animate-spin" />
                            <span>等待日志...</span>
                          </div>
                        ) : (
                          <div className="space-y-0.5">
                            {manualTestLogs.map((log, i) => (
                              <div key={i} className="whitespace-pre-wrap">{log}</div>
                            ))}
                            <div ref={terminalEndRef} />
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* 右栏：AI 生成的代码编辑器 */}
                <div className="w-1/2 flex flex-col bg-white dark:bg-[#1e1e1f]">
                  {/* 基本信息编辑 */}
                  <div className="p-4 border-b border-gray-200 dark:border-neutral-800 bg-gray-50/50 dark:bg-neutral-900/30">
                    <div className="flex gap-4">
                      <div className="flex-1">
                        <label className="text-xs text-gray-500 dark:text-neutral-500 mb-1 block">技能名称</label>
                        <input
                          type="text"
                          value={skillName}
                          onChange={e => setSkillName(e.target.value)}
                          placeholder="输入技能名称..."
                          className="w-full bg-white dark:bg-[#0d0d0e] border border-gray-300 dark:border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-gray-700 dark:text-neutral-300 focus:border-blue-500 focus:outline-none"
                        />
                      </div>
                      <div className="flex-1">
                        <label className="text-xs text-gray-500 dark:text-neutral-500 mb-1 block">执行器类型</label>
                        <select
                          value={craftedSkill?.executor_type || executorType}
                          onChange={e => setCraftedSkill({ ...craftedSkill, executor_type: e.target.value } as any)}
                          className="w-full bg-white dark:bg-[#0d0d0e] border border-gray-300 dark:border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-gray-700 dark:text-neutral-300 focus:border-blue-500 focus:outline-none"
                        >
                          <option value="Python_env">Python_env</option>
                          <option value="R_env">R_env</option>
                          <option value="Logical_Blueprint">Logical_Blueprint</option>
                        </select>
                      </div>
                    </div>
                    <div className="mt-2">
                      <label className="text-xs text-gray-500 dark:text-neutral-500 mb-1 block">简介描述</label>
                      <input
                        type="text"
                        value={skillDescription}
                        onChange={e => setSkillDescription(e.target.value)}
                        placeholder="一句话描述这个技能的功能..."
                        className="w-full bg-white dark:bg-[#0d0d0e] border border-gray-300 dark:border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-gray-700 dark:text-neutral-300 focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  {/* 生成的文件系统信息 */}
                  {bundlePath && filesCreated.length > 0 && (
                    <div className="px-4 py-2 bg-emerald-50 dark:bg-emerald-900/30 border-b border-emerald-200 dark:border-emerald-800">
                      <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 text-xs">
                        <CheckCircle size={14} />
                        <span className="font-medium">已生成文件系统技能包</span>
                      </div>
                      <div className="mt-1 text-xs text-gray-500 dark:text-neutral-400">
                        路径: <code className="text-emerald-600 dark:text-emerald-300">{bundlePath}</code>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {filesCreated.map((file, idx) => (
                          <span key={idx} className="px-2 py-0.5 bg-white dark:bg-neutral-800 rounded text-xs text-gray-600 dark:text-neutral-300">
                            {file}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 校验警告 */}
                  {validationWarning && (
                    <div className="px-4 py-2 bg-yellow-50 dark:bg-yellow-900/30 border-b border-yellow-200 dark:border-yellow-800 flex items-center gap-2">
                      <AlertTriangle size={16} className="text-yellow-500" />
                      <span className="text-xs text-yellow-700 dark:text-yellow-300">{validationWarning}</span>
                    </div>
                  )}

                  {/* Tab 切换 */}
                  <div className="h-10 bg-gray-100 dark:bg-[#2d2d2d] flex items-center px-4 border-b border-gray-200 dark:border-neutral-800 gap-4">
                    <button
                      onClick={() => setActiveEditorTab('code')}
                      className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-md transition-all ${
                        activeEditorTab === 'code'
                          ? 'bg-blue-500/20 text-blue-600 dark:text-blue-400'
                          : 'text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200'
                      }`}
                    >
                      {executorType === 'Logical_Blueprint' ? <GitBranch size={14} /> : <Code size={14} />}
                      {executorType === 'Logical_Blueprint' ? 'process.nf' : '脚本代码'}
                    </button>
                    <button
                      onClick={() => setActiveEditorTab('skillmd')}
                      className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-md transition-all ${
                        activeEditorTab === 'skillmd'
                          ? 'bg-purple-500/20 text-purple-600 dark:text-purple-400'
                          : 'text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200'
                      }`}
                    >
                      <FileCode size={14} />
                      SKILL.md
                    </button>
                  </div>

                  {/* 编辑器内容 */}
                  {activeEditorTab === 'code' ? (
                    executorType === 'Logical_Blueprint' ? (
                      <textarea
                        value={nextflowCode}
                        onChange={e => setNextflowCode(e.target.value)}
                        placeholder="AI 锻造后的 Nextflow 工作流代码将显示在这里..."
                        className="flex-1 bg-transparent text-gray-700 dark:text-neutral-300 font-mono text-sm p-4 focus:outline-none resize-none leading-relaxed"
                        spellCheck={false}
                      />
                    ) : (
                      <textarea
                        value={scriptCode}
                        onChange={e => setScriptCode(e.target.value)}
                        placeholder="AI 锻造后的标准化代码将显示在这里..."
                        className="flex-1 bg-transparent text-gray-700 dark:text-neutral-300 font-mono text-sm p-4 focus:outline-none resize-none leading-relaxed"
                        spellCheck={false}
                      />
                    )
                  ) : (
                    <textarea
                      value={skillMdContent}
                      onChange={e => setSkillMdContent(e.target.value)}
                      placeholder="SKILL.md 内容将显示在这里..."
                      className="flex-1 bg-transparent text-gray-700 dark:text-neutral-300 font-mono text-sm p-4 focus:outline-none resize-none leading-relaxed"
                      spellCheck={false}
                    />
                  )}

                  {/* 参数 Schema 预览 */}
                  {craftedSkill?.parameters_schema && Object.keys(craftedSkill.parameters_schema.properties || {}).length > 0 && (
                    <div className="border-t border-gray-200 dark:border-neutral-800 p-4 bg-gray-50/50 dark:bg-neutral-900/30 max-h-48 overflow-y-auto">
                      <label className="text-xs text-gray-500 dark:text-neutral-500 font-medium mb-2 block flex items-center gap-2">
                        <FileJson size={14} />
                        参数 Schema (JSON)
                      </label>
                      <pre className="text-xs text-emerald-600 dark:text-emerald-400 font-mono whitespace-pre-wrap">
                        {JSON.stringify(craftedSkill.parameters_schema, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>

              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}