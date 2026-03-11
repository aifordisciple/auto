"use client";

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { skillForgeApi, ExecutorType, CraftRequest } from '@/lib/api';
import { TopHeader } from '@/components/layout/TopHeader';
import { Sidebar } from '@/components/layout/Sidebar';
import { Play, Hammer, Save, Send, Code, Terminal, FileJson, AlertTriangle, CheckCircle, FolderTree, Zap, GitBranch, Package } from 'lucide-react';

// 执行器类型配置
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
  },
  {
    value: 'Python_Package',
    label: 'Python 包',
    icon: <Package size={16} />,
    description: '完整 Python 包结构'
  }
];

export default function SkillForgePage() {
  const router = useRouter();

  // 状态管理
  const [rawMaterial, setRawMaterial] = useState('');
  const [isCrafting, setIsCrafting] = useState(false);

  // 新增：执行器类型和文件系统生成选项
  const [executorType, setExecutorType] = useState<ExecutorType>('Python_env');
  const [generateFullBundle, setGenerateFullBundle] = useState(false);
  const [skillNameHint, setSkillNameHint] = useState('');

  const [craftedSkill, setCraftedSkill] = useState<Record<string, any> | null>(null);
  const [scriptCode, setScriptCode] = useState('');
  const [nextflowCode, setNextflowCode] = useState('');
  const [skillName, setSkillName] = useState('');
  const [skillDescription, setSkillDescription] = useState('');

  // 新增：生成的文件系统信息
  const [bundlePath, setBundlePath] = useState<string | null>(null);
  const [filesCreated, setFilesCreated] = useState<string[]>([]);

  const [testInstruction, setTestInstruction] = useState('sys.argv = ["script.py", "--input", "/data/test.tsv"]');
  const [isTesting, setIsTesting] = useState(false);
  const [testLogs, setTestLogs] = useState('');

  const [isSaving, setIsSaving] = useState(false);
  const [validationWarning, setValidationWarning] = useState('');

  // 触发 AI 锻造
  const handleCraft = async () => {
    if (!rawMaterial || rawMaterial.trim().length < 10) {
      alert("请先输入原始素材（至少10个字符）");
      return;
    }

    setIsCrafting(true);
    setTestLogs("🔨 正在呼叫大模型进行逆向提取与参数推导...\n");
    setValidationWarning('');
    setBundlePath(null);
    setFilesCreated([]);

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

      // 设置文件系统信息
      if (result.bundle_path) {
        setBundlePath(result.bundle_path);
        setFilesCreated(result.files_created || []);
      }

      // 检查校验结果
      if (result.data.validation_warning) {
        setValidationWarning(result.data.validation_warning);
        setTestLogs(prev => prev + `⚠️ 校验警告: ${result.data.validation_warning}\n`);
      } else if (result.data.validation_passed) {
        setTestLogs(prev => prev + "✅ 锻造成功！代码已通过铁律校验。\n");
      } else {
        setTestLogs(prev => prev + "✅ 锻造成功！已生成标准参数面板与规范化代码。\n");
      }

      // 显示生成的文件
      if (result.files_created && result.files_created.length > 0) {
        setTestLogs(prev => prev + `\n📁 已生成文件系统技能包:\n`);
        result.files_created.forEach((file: string) => {
          setTestLogs(prev => prev + `  - ${file}\n`);
        });
        setTestLogs(prev => prev + `\n路径: ${result.bundle_path}\n`);
      }
    } catch (e: any) {
      setTestLogs(prev => prev + `❌ 锻造失败: ${e.message}\n`);
    } finally {
      setIsCrafting(false);
    }
  };

  // 触发沙箱测试
  const handleTest = async () => {
    if (!scriptCode) {
      alert("没有代码可测试，请先锻造技能");
      return;
    }

    setIsTesting(true);
    setTestLogs("🚀 正在将代码投入 Docker 沙箱，准备执行自动化试炼...\n");

    try {
      const result = await skillForgeApi.testDraftSkill(scriptCode, testInstruction);
      setTestLogs(prev => prev + `\n--- 沙箱执行日志 ---\n${result.logs}\n`);

      if (result.status === 'success') {
        setTestLogs(prev => prev + "\n🎉 恭喜！代码完美跑通沙箱测试！");
      } else {
        setTestLogs(prev => prev + "\n⚠️ 试炼失败！请检查上方日志或让 AI 再次尝试修复。");
        // 如果 AI 尝试了修复并返回了新代码，更新编辑器
        if (result.final_code && result.final_code !== scriptCode) {
          setScriptCode(result.final_code);
          setTestLogs(prev => prev + "\n🤖 Debugger 已经尝试修改了代码，请查看右侧编辑器。");
        }
      }
    } catch (e: any) {
      setTestLogs(prev => prev + `❌ 测试请求失败: ${e.message}\n`);
    } finally {
      setIsTesting(false);
    }
  };

  // 是否显示沙箱测试（仅单脚本类型）
  const showSandboxTest = executorType === 'Python_env' || executorType === 'R_env';

  // 固化入库与提审
  const handleSaveAndSubmit = async () => {
    if (!craftedSkill) {
      alert("请先锻造一个技能");
      return;
    }

    setIsSaving(true);

    try {
      // 1. 组装入库数据
      const payload = {
        name: skillName || craftedSkill.name || "未命名技能",
        description: skillDescription || craftedSkill.description || "",
        executor_type: craftedSkill.executor_type || "Python_env",
        parameters_schema: craftedSkill.parameters_schema || {},
        expert_knowledge: craftedSkill.expert_knowledge || "",
        script_code: scriptCode,
        dependencies: craftedSkill.dependencies || []
      };

      // 2. 保存为私有
      const savedSkill = await skillForgeApi.savePrivateSkill(payload);

      // 3. 提交审核
      await skillForgeApi.submitForReview(savedSkill.skill_id);

      alert("✅ 技能已成功固化入库，并提交管理员审核！");
      router.push('/');
    } catch (e: any) {
      alert(`保存失败: ${e.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  // 仅保存为私有（不提交审核）
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
        dependencies: craftedSkill.dependencies || []
      };

      const savedSkill = await skillForgeApi.savePrivateSkill(payload);
      alert(`✅ 技能已保存为私有！ID: ${savedSkill.skill_id}`);
    } catch (e: any) {
      alert(`保存失败: ${e.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#0E1117] text-gray-300 font-sans overflow-hidden">
      {/* 左侧边栏 */}
      <div className="w-56 shrink-0 border-r border-gray-800 bg-gray-900 flex flex-col">
        <Sidebar />
      </div>
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        <TopHeader />

        {/* 顶部工具栏 */}
        <div className="h-14 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-2">
            <Hammer className="text-blue-500" size={20} />
            <h1 className="font-semibold text-gray-100">SKILL Forge 技能锻造工厂</h1>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleSaveOnly}
              disabled={!craftedSkill || isSaving}
              className="flex items-center gap-2 px-4 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-sm rounded transition-colors"
            >
              <Save size={16} />
              保存为私有
            </button>
            <button
              onClick={handleSaveAndSubmit}
              disabled={!craftedSkill || isSaving}
              className="flex items-center gap-2 px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm rounded transition-colors"
            >
              <Send size={16} />
              {isSaving ? "正在提交..." : "保存并提交审核"}
            </button>
          </div>
        </div>

        {/* 双栏工作区 */}
        <div className="flex-1 flex overflow-hidden">

          {/* 左栏：输入与测试日志 */}
          <div className="w-1/2 flex flex-col border-r border-gray-800 bg-gray-900/50">
            {/* 素材喂入区 - 主要区域 */}
            <div className="flex-1 p-4 flex flex-col border-b border-gray-800 overflow-hidden">
              <label className="text-xs text-gray-400 font-medium mb-2 uppercase tracking-wider flex items-center gap-2 shrink-0">
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
                className="flex-1 min-h-[120px] bg-[#090b10] border border-gray-700 rounded p-3 text-sm text-gray-300 focus:border-blue-500 focus:outline-none resize-none"
              />

              {/* 执行器类型选择器 */}
              <div className="mt-3 mb-2 shrink-0">
                <label className="text-xs text-gray-400 mb-2 block">执行器类型</label>
                <div className="grid grid-cols-4 gap-2">
                  {EXECUTOR_TYPES.map(type => (
                    <button
                      key={type.value}
                      onClick={() => setExecutorType(type.value)}
                      className={`flex flex-col items-center justify-center p-2 rounded border text-xs transition-all ${
                        executorType === type.value
                          ? 'border-blue-500 bg-blue-500/20 text-blue-400'
                          : 'border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600'
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
                <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={generateFullBundle}
                    onChange={e => setGenerateFullBundle(e.target.checked)}
                    className="rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500"
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
                    className="flex-1 bg-[#090b10] border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:border-blue-500 focus:outline-none"
                  />
                )}
              </div>

              <button
                onClick={handleCraft}
                disabled={isCrafting}
                className="mt-3 w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded font-medium flex justify-center items-center gap-2 disabled:opacity-50 shrink-0"
              >
                <Hammer size={16} />
                {isCrafting ? "AI 架构师正在锻造..." : "一键提炼标准技能包"}
              </button>
            </div>

            {/* 沙箱测试区 - 紧凑模式，仅对单脚本类型显示 */}
            {showSandboxTest && (
              <div className="h-[180px] p-3 flex flex-col shrink-0">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs text-gray-400 font-medium uppercase tracking-wider flex items-center gap-2">
                    <Terminal size={14} />
                    2. 沙箱测试
                  </label>
                  <button
                    onClick={handleTest}
                    disabled={isTesting || !scriptCode}
                    className="px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white text-xs rounded font-medium flex items-center gap-1 disabled:opacity-50"
                  >
                    <Play size={12} />
                    {isTesting ? "运行中..." : "运行"}
                  </button>
                </div>
                {/* 测试参数说明 */}
                <div className="text-[10px] text-gray-500 mb-1">
                  💡 填入测试数据路径，如：<code className="text-gray-400">sys.argv = ["script.py", "--input", "/data/test.tsv"]</code>
                </div>
                <input
                  type="text"
                  value={testInstruction}
                  onChange={e => setTestInstruction(e.target.value)}
                  placeholder="测试参数..."
                  className="bg-[#090b10] border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:border-purple-500 focus:outline-none mb-2"
                />
                <textarea
                  readOnly
                  value={testLogs}
                  placeholder="执行日志将显示在这里..."
                  className="flex-1 bg-black border border-gray-800 rounded p-2 text-[10px] text-emerald-400 font-mono focus:outline-none resize-none"
                />
              </div>
            )}

            {/* 非单脚本类型显示锻造日志 */}
            {!showSandboxTest && testLogs && (
              <div className="h-[120px] p-3 flex flex-col shrink-0 border-t border-gray-800">
                <label className="text-xs text-gray-400 font-medium mb-1 uppercase tracking-wider flex items-center gap-2">
                  <Terminal size={14} />
                  锻造日志
                </label>
                <textarea
                  readOnly
                  value={testLogs}
                  className="flex-1 bg-black border border-gray-800 rounded p-2 text-[10px] text-emerald-400 font-mono focus:outline-none resize-none"
                />
              </div>
            )}
          </div>

          {/* 右栏：AI 生成的代码编辑器 */}
          <div className="w-1/2 flex flex-col bg-[#1e1e1e]">
            {/* 基本信息编辑 */}
            <div className="p-4 border-b border-gray-800 bg-gray-900/30">
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="text-xs text-gray-400 mb-1 block">技能名称</label>
                  <input
                    type="text"
                    value={skillName}
                    onChange={e => setSkillName(e.target.value)}
                    placeholder="输入技能名称..."
                    className="w-full bg-[#090b10] border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-300 focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div className="flex-1">
                  <label className="text-xs text-gray-400 mb-1 block">执行器类型</label>
                  <select
                    value={craftedSkill?.executor_type || executorType}
                    onChange={e => setCraftedSkill({ ...craftedSkill, executor_type: e.target.value } as any)}
                    className="w-full bg-[#090b10] border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-300 focus:border-blue-500 focus:outline-none"
                  >
                    <option value="Python_env">Python_env</option>
                    <option value="R_env">R_env</option>
                    <option value="Logical_Blueprint">Logical_Blueprint</option>
                    <option value="Python_Package">Python_Package</option>
                  </select>
                </div>
              </div>
              <div className="mt-2">
                <label className="text-xs text-gray-400 mb-1 block">简介描述</label>
                <input
                  type="text"
                  value={skillDescription}
                  onChange={e => setSkillDescription(e.target.value)}
                  placeholder="一句话描述这个技能的功能..."
                  className="w-full bg-[#090b10] border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-300 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>

            {/* 生成的文件系统信息 */}
            {bundlePath && filesCreated.length > 0 && (
              <div className="px-4 py-2 bg-emerald-900/30 border-b border-emerald-800">
                <div className="flex items-center gap-2 text-emerald-400 text-xs">
                  <CheckCircle size={14} />
                  <span className="font-medium">已生成文件系统技能包</span>
                </div>
                <div className="mt-1 text-xs text-gray-400">
                  路径: <code className="text-emerald-300">{bundlePath}</code>
                </div>
                <div className="flex flex-wrap gap-1 mt-1">
                  {filesCreated.map((file, idx) => (
                    <span key={idx} className="px-2 py-0.5 bg-gray-800 rounded text-xs text-gray-300">
                      {file}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 校验警告 */}
            {validationWarning && (
              <div className="px-4 py-2 bg-yellow-900/30 border-b border-yellow-800 flex items-center gap-2">
                <AlertTriangle size={16} className="text-yellow-500" />
                <span className="text-xs text-yellow-300">{validationWarning}</span>
              </div>
            )}

            {/* 代码编辑器 - 根据类型显示不同内容 */}
            <div className="h-10 bg-[#2d2d2d] flex items-center px-4 border-b border-gray-800">
              <span className="text-xs text-gray-300 font-mono flex items-center gap-2">
                {executorType === 'Logical_Blueprint' ? (
                  <>
                    <GitBranch size={14} className="text-purple-500" />
                    process.nf (Nextflow DSL2)
                  </>
                ) : (
                  <>
                    <Code size={14} className="text-yellow-500" />
                    main.py / main.R (可手动微调)
                  </>
                )}
              </span>
            </div>

            {executorType === 'Logical_Blueprint' ? (
              <textarea
                value={nextflowCode}
                onChange={e => setNextflowCode(e.target.value)}
                placeholder="AI 锻造后的 Nextflow 工作流代码将显示在这里..."
                className="flex-1 bg-transparent text-gray-300 font-mono text-sm p-4 focus:outline-none resize-none leading-relaxed"
                spellCheck={false}
              />
            ) : (
              <textarea
                value={scriptCode}
                onChange={e => setScriptCode(e.target.value)}
                placeholder="AI 锻造后的标准化代码将显示在这里..."
                className="flex-1 bg-transparent text-gray-300 font-mono text-sm p-4 focus:outline-none resize-none leading-relaxed"
                spellCheck={false}
              />
            )}

            {/* 参数 Schema 预览 */}
            {craftedSkill?.parameters_schema && Object.keys(craftedSkill.parameters_schema.properties || {}).length > 0 && (
              <div className="border-t border-gray-800 p-4 bg-gray-900/30 max-h-48 overflow-y-auto">
                <label className="text-xs text-gray-400 font-medium mb-2 block flex items-center gap-2">
                  <FileJson size={14} />
                  参数 Schema (JSON)
                </label>
                <pre className="text-xs text-emerald-400 font-mono whitespace-pre-wrap">
                  {JSON.stringify(craftedSkill.parameters_schema, null, 2)}
                </pre>
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}