"use client";
import { useState, useEffect } from "react";
import { FolderGit2, Plus, ArrowRight } from "lucide-react";
import { useWorkspaceStore } from "../../store/useWorkspaceStore";
import { useUIStore } from "../../store/useUIStore";
import { fetchAPI } from "../../lib/api";

export function ProjectCenter() {
  const [projects, setProjects] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { currentProjectId, setCurrentProjectId } = useWorkspaceStore();
  const { closeAllOverlays } = useUIStore();

  // ✨ 新增：弹窗控制状态
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newProjName, setNewProjName] = useState("");
  const [newProjDesc, setNewProjDesc] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    fetchAPI('/api/projects')
      .then(data => { if (data.status === 'success') setProjects(data.data); })
      .finally(() => setIsLoading(false));
  }, []);

  // ✨ 修改：处理表单提交
  const handleCreateSubmit = async () => {
    if (!newProjName.trim()) return;

    setIsCreating(true);
    try {
      const res = await fetchAPI('/api/projects', {
        method: 'POST',
        body: JSON.stringify({
          name: newProjName.trim(),
          description: newProjDesc.trim() || "未提供项目介绍"
        })
      });

      if (res.status === 'success' && res.data) {
        // 创建成功后重新拉取列表
        setIsLoading(true);
        fetchAPI('/api/projects')
          .then(data => { if (data.status === 'success') setProjects(data.data); })
          .finally(() => setIsLoading(false));
        // 自动切换到新创建的项目并关闭弹窗
        setCurrentProjectId(res.data.id);

        // 成功后清空表单并关闭
        setIsModalOpen(false);
        setNewProjName("");
        setNewProjDesc("");
        closeAllOverlays();
      }
    } catch (e) {
      alert("创建失败，请检查网络或登录状态。");
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="p-8 h-full flex flex-col">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-600/20 text-purple-500 rounded-lg"><FolderGit2 size={24} /></div>
          <div>
            <h3 className="text-white font-medium text-lg">项目中心 (Workspaces)</h3>
            <p className="text-neutral-500 text-sm">管理您的生信分析沙箱环境，数据与上下文完全隔离。</p>
          </div>
        </div>
        {/* ✨ 修改：点击打开弹窗 */}
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 bg-white text-black px-4 py-2 rounded-md text-sm font-medium hover:bg-neutral-200 transition-colors"
        >
          <Plus size={16} /> 新建项目
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {isLoading ? (
          <div className="text-neutral-500 animate-pulse">正在加载数据沙箱...</div>
        ) : (
          projects.map((proj) => (
            <div 
              key={proj.id} 
              onClick={() => {
                setCurrentProjectId(proj.id);
                closeAllOverlays(); // 点击瞬间切换项目并关闭大屏
              }}
              className={`group bg-neutral-900 border ${currentProjectId === proj.id ? 'border-blue-500 shadow-lg shadow-blue-900/20' : 'border-neutral-800 hover:border-purple-500/50'} rounded-xl p-5 cursor-pointer transition-all flex flex-col`}
            >
              <div className="flex items-start justify-between mb-3">
                <h4 className="text-white font-medium text-base truncate">{proj.name}</h4>
                {currentProjectId === proj.id && <span className="text-[10px] bg-blue-500/20 text-blue-400 px-2 py-1 rounded border border-blue-500/30">CURRENT</span>}
              </div>
              <p className="text-neutral-500 text-xs flex-1 mb-4 line-clamp-2">{proj.description || "暂无描述"}</p>
              <div className="flex justify-between items-center text-xs text-neutral-600 border-t border-neutral-800 pt-3 group-hover:text-purple-400 transition-colors">
                <span>{new Date(proj.created_at).toLocaleDateString()}</span>
                <ArrowRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity transform group-hover:translate-x-1" />
              </div>
            </div>
          ))
        )}
      </div>

      {/* ✨ 新增：优雅的暗黑风格新建项目弹窗 */}
      {isModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-[#1a1a1c] border border-neutral-800 rounded-2xl w-full max-w-md p-6 shadow-2xl transform transition-all">
            <h3 className="text-lg font-semibold text-white mb-5">🚀 新建生信项目沙箱</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1.5">项目名称 <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
                  placeholder="例如: 肺癌单细胞时空图谱分析"
                  className="w-full bg-[#121212] border border-neutral-800 rounded-lg px-3 py-2 text-sm text-white placeholder-neutral-600 focus:outline-none focus:border-blue-500/50 transition-colors"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1.5">项目介绍</label>
                <textarea
                  value={newProjDesc}
                  onChange={(e) => setNewProjDesc(e.target.value)}
                  placeholder="简要描述该项目的数据来源、物种或研究目的..."
                  className="w-full bg-[#121212] border border-neutral-800 rounded-lg px-3 py-2 text-sm text-white placeholder-neutral-600 focus:outline-none focus:border-blue-500/50 transition-colors resize-none h-24"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-8">
              <button
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2 text-sm font-medium text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreateSubmit}
                disabled={!newProjName.trim() || isCreating}
                className="px-4 py-2 bg-white hover:bg-neutral-200 disabled:bg-neutral-800 disabled:text-neutral-500 text-black text-sm font-medium rounded-lg transition-colors"
              >
                {isCreating ? "创建中..." : "确认创建"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
