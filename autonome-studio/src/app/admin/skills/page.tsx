"use client";

import React, { useEffect, useState } from 'react';
import { adminApi, SkillAsset } from '@/lib/api';
import TopHeader from '@/components/layout/TopHeader';
import Sidebar from '@/components/layout/Sidebar';
import { ShieldCheck, Check, X, FileJson, Code, Clock, User } from 'lucide-react';

export default function AdminSkillReviewPage() {
  const [pendingSkills, setPendingSkills] = useState<SkillAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [rejectReason, setRejectReason] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);

  const fetchPendingSkills = async () => {
    setLoading(true);
    try {
      const data = await adminApi.getPendingSkills();
      setPendingSkills(Array.isArray(data) ? data : []);
    } catch (e: any) {
      console.error("获取待审核列表失败", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPendingSkills();
  }, []);

  const handleReview = async (skillId: string, action: 'APPROVE' | 'REJECT') => {
    if (action === 'REJECT' && !rejectReason.trim()) {
      alert("驳回操作必须填写理由！");
      return;
    }

    if (!confirm(`确定要 ${action === 'APPROVE' ? '批准' : '驳回'} 该技能吗？`)) return;

    try {
      await adminApi.reviewSkill(skillId, action, rejectReason);
      alert(`✅ 操作成功`);
      setRejectReason("");
      setSelectedSkill(null);
      fetchPendingSkills();
    } catch (e: any) {
      alert(`操作失败: ${e.message}`);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString('zh-CN');
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="flex h-screen bg-[#0E1117] text-gray-300 font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        <TopHeader />

        {/* 顶部标题栏 */}
        <div className="h-14 bg-gray-900 border-b border-gray-800 flex items-center px-6 shrink-0">
          <ShieldCheck className="text-emerald-500 mr-2" size={20} />
          <h1 className="font-semibold text-gray-100">技能应用商店审核中心</h1>
          <span className="ml-4 px-2 py-0.5 bg-yellow-900/50 text-yellow-400 text-xs rounded-full">
            {pendingSkills.length} 待审核
          </span>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto p-6 bg-[#0E1117]">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
              <span className="ml-3 text-gray-400">正在加载待审核队列...</span>
            </div>
          ) : pendingSkills.length === 0 ? (
            <div className="text-center py-20 bg-gray-900/50 rounded-lg border border-gray-800">
              <ShieldCheck className="mx-auto text-gray-600 mb-4" size={48} />
              <p className="text-gray-400">目前没有待审核的技能申请，您终于可以喝杯咖啡了。</p>
            </div>
          ) : (
            <div className="space-y-6">
              {pendingSkills.map((skill) => (
                <div key={skill.skill_id} className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden shadow-xl">
                  {/* 卡片头部信息 */}
                  <div className="p-4 border-b border-gray-800 flex justify-between items-start bg-gray-800/30">
                    <div>
                      <h3 className="text-lg font-bold text-gray-100 flex items-center gap-2">
                        {skill.name}
                        <span className="text-xs font-normal px-2 py-0.5 bg-blue-900/50 text-blue-400 rounded-full border border-blue-800">
                          {skill.skill_id}
                        </span>
                      </h3>
                      <p className="text-sm text-gray-400 mt-1">{skill.description || '暂无描述'}</p>
                      <div className="text-xs text-gray-500 mt-2 flex items-center gap-4">
                        <span className="flex items-center gap-1">
                          <User size={12} />
                          创建者 ID: {skill.owner_id}
                        </span>
                        <span className="flex items-center gap-1">
                          <Code size={12} />
                          引擎: {skill.executor_type}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock size={12} />
                          提交时间: {formatDate(skill.updated_at)}
                        </span>
                      </div>
                    </div>
                    <span className={`px-2 py-1 text-xs rounded ${
                      skill.status === 'PENDING_REVIEW' ? 'bg-yellow-900/50 text-yellow-400' :
                      skill.status === 'PUBLISHED' ? 'bg-green-900/50 text-green-400' :
                      'bg-gray-700 text-gray-300'
                    }`}>
                      {skill.status}
                    </span>
                  </div>

                  {/* 核心审查区：Schema 和 代码双栏展示 */}
                  <div className="flex h-[300px] border-b border-gray-800">
                    <div className="w-1/3 p-4 border-r border-gray-800 overflow-y-auto bg-[#12141a]">
                      <h4 className="text-xs font-bold text-gray-500 mb-3 flex items-center gap-1 uppercase tracking-wider">
                        <FileJson size={14} /> 暴露给用户的表单参数 (Schema)
                      </h4>
                      <pre className="text-xs text-emerald-400 font-mono whitespace-pre-wrap">
                        {JSON.stringify(skill.parameters_schema, null, 2)}
                      </pre>
                    </div>
                    <div className="w-2/3 p-4 overflow-y-auto bg-[#1e1e1e]">
                      <h4 className="text-xs font-bold text-gray-400 mb-3 flex items-center gap-1 uppercase tracking-wider">
                        <Code size={14} className="text-yellow-500" /> 物理沙箱执行脚本 (请严格审查有无危险命令！)
                      </h4>
                      <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap">
                        {skill.script_code || '暂无代码'}
                      </pre>
                    </div>
                  </div>

                  {/* 依赖包列表 */}
                  {skill.dependencies && skill.dependencies.length > 0 && (
                    <div className="px-4 py-2 bg-gray-900/50 border-b border-gray-800">
                      <span className="text-xs text-gray-500">依赖包: </span>
                      {skill.dependencies.map((dep, i) => (
                        <span key={i} className="inline-block px-2 py-0.5 bg-gray-700 text-gray-300 text-xs rounded mr-1">
                          {dep}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* 决策操作区 */}
                  <div className="p-4 bg-gray-900 flex items-center justify-between">
                    <div className="flex-1 mr-4">
                      <input
                        type="text"
                        placeholder="如果打算驳回，请在此填写驳回理由 (如: '缺少参数校验' / '散点图未加英文Title')..."
                        value={selectedSkill === skill.skill_id ? rejectReason : ""}
                        onChange={(e) => {
                          setSelectedSkill(skill.skill_id);
                          setRejectReason(e.target.value);
                        }}
                        onFocus={() => setSelectedSkill(skill.skill_id)}
                        className="w-full bg-[#090b10] border border-gray-700 rounded px-3 py-2 text-sm text-gray-300 focus:border-red-500 focus:outline-none"
                      />
                    </div>
                    <div className="flex gap-3 shrink-0">
                      <button
                        onClick={() => handleReview(skill.skill_id, 'REJECT')}
                        className="flex items-center gap-1 px-4 py-2 bg-red-900/50 hover:bg-red-800 text-red-200 border border-red-800 text-sm rounded font-medium transition-colors"
                      >
                        <X size={16} /> 打回修改
                      </button>
                      <button
                        onClick={() => handleReview(skill.skill_id, 'APPROVE')}
                        className="flex items-center gap-1 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded font-medium transition-colors"
                      >
                        <Check size={16} /> 批准全网上架！
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}