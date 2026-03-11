"use client";

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { skillForgeApi } from '@/lib/api';
import { TopHeader } from '@/components/layout/TopHeader';
import { Sidebar } from '@/components/layout/Sidebar';
import { Play, Hammer, Save, Send, Code, Terminal, FileJson, AlertTriangle, CheckCircle } from 'lucide-react';

export default function SkillForgePage() {
  const router = useRouter();

  // 状态管理
  const [rawMaterial, setRawMaterial] = useState('');
  const [isCrafting, setIsCrafting] = useState(false);

  const [craftedSkill, setCraftedSkill] = useState<Record<string, any> | null>(null);
  const [scriptCode, setScriptCode] = useState('');
  const [skillName, setSkillName] = useState('');
  const [skillDescription, setSkillDescription] = useState('');

  const [testInstruction, setTestInstruction] = useState('# 测试参数模拟\nimport sys\nsys.argv = ["script.py", "--input", "test.tsv"]');
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

    try {
      const result = await skillForgeApi.craftFromMaterial(rawMaterial);
      setCraftedSkill(result);
      setScriptCode(result.script_code || '');
      setSkillName(result.name || '');
      setSkillDescription(result.description || '');

      // 检查校验结果
      if (result.validation_warning) {
        setValidationWarning(result.validation_warning);
        setTestLogs(prev => prev + `⚠️ 校验警告: ${result.validation_warning}\n`);
      } else if (result.validation_passed) {
        setTestLogs(prev => prev + "✅ 锻造成功！代码已通过铁律校验。\n");
      } else {
        setTestLogs(prev => prev + "✅ 锻造成功！已生成标准参数面板与规范化代码。\n");
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
      alert("没有代码可测试");
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
      <Sidebar />
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
            {/* 素材喂入区 */}
            <div className="h-1/2 p-4 flex flex-col border-b border-gray-800">
              <label className="text-xs text-gray-400 font-medium mb-2 uppercase tracking-wider flex items-center gap-2">
                <FileJson size={14} />
                1. 喂入原始素材 (代码/指令/文献段落)
              </label>
              <textarea
                value={rawMaterial}
                onChange={e => setRawMaterial(e.target.value)}
                placeholder="在此粘贴您写死的 R/Python 代码，或者直接输入：'帮我写一个用 scanpy 过滤单细胞矩阵的脚本，需要可调节线粒体比例阈值'..."
                className="flex-1 bg-[#090b10] border border-gray-700 rounded p-3 text-sm text-gray-300 focus:border-blue-500 focus:outline-none resize-none"
              />
              <button
                onClick={handleCraft}
                disabled={isCrafting}
                className="mt-3 w-full py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded font-medium flex justify-center items-center gap-2 disabled:opacity-50"
              >
                <Hammer size={16} />
                {isCrafting ? "AI 架构师正在锻造..." : "一键提炼标准技能包"}
              </button>
            </div>

            {/* 沙箱测试区 */}
            <div className="h-1/2 p-4 flex flex-col">
              <label className="text-xs text-gray-400 font-medium mb-2 uppercase tracking-wider flex items-center gap-2">
                <Terminal size={14} />
                2. 沙箱自动化测试 (Sandbox Console)
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={testInstruction}
                  onChange={e => setTestInstruction(e.target.value)}
                  placeholder="输入测试环境变量或传参模拟代码..."
                  className="flex-1 bg-[#090b10] border border-gray-700 rounded px-3 py-1.5 text-xs text-gray-300 focus:border-blue-500 focus:outline-none"
                />
                <button
                  onClick={handleTest}
                  disabled={isTesting || !scriptCode}
                  className="px-4 py-1.5 bg-purple-600 hover:bg-purple-500 text-white text-xs rounded font-medium flex items-center gap-2 disabled:opacity-50"
                >
                  <Play size={14} />
                  {isTesting ? "试炼中..." : "启动沙箱"}
                </button>
              </div>
              <textarea
                readOnly
                value={testLogs}
                className="flex-1 bg-black border border-gray-800 rounded p-3 text-xs text-emerald-400 font-mono focus:outline-none resize-none"
              />
            </div>
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
                    value={craftedSkill?.executor_type || 'Python_env'}
                    onChange={e => setCraftedSkill({ ...craftedSkill, executor_type: e.target.value } as any)}
                    className="w-full bg-[#090b10] border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-300 focus:border-blue-500 focus:outline-none"
                  >
                    <option value="Python_env">Python_env</option>
                    <option value="R_env">R_env</option>
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

            {/* 校验警告 */}
            {validationWarning && (
              <div className="px-4 py-2 bg-yellow-900/30 border-b border-yellow-800 flex items-center gap-2">
                <AlertTriangle size={16} className="text-yellow-500" />
                <span className="text-xs text-yellow-300">{validationWarning}</span>
              </div>
            )}

            {/* 代码编辑器 */}
            <div className="h-10 bg-[#2d2d2d] flex items-center px-4 border-b border-gray-800">
              <span className="text-xs text-gray-300 font-mono flex items-center gap-2">
                <Code size={14} className="text-yellow-500" />
                main.py / main.R (可手动微调)
              </span>
            </div>
            <textarea
              value={scriptCode}
              onChange={e => setScriptCode(e.target.value)}
              placeholder="AI 锻造后的标准化代码将显示在这里..."
              className="flex-1 bg-transparent text-gray-300 font-mono text-sm p-4 focus:outline-none resize-none leading-relaxed"
              spellCheck={false}
            />

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