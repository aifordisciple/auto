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

  useEffect(() => {
    setIsLoading(true);
    fetchAPI('/api/projects')
      .then(data => { if (data.status === 'success') setProjects(data.data); })
      .finally(() => setIsLoading(false));
  }, []);

  // ✨ 新增：处理新建项目点击事件
  const handleCreateProject = async () => {
    const name = prompt("请输入新项目/工作区的名称：", "My New Analysis Project");
    if (!name) return;

    try {
      const res = await fetchAPI('/api/projects', {
        method: 'POST',
        body: JSON.stringify({ name, description: "Created via Workspace" })
      });

      if (res.status === 'success' && res.data) {
        // 创建成功后重新拉取列表
        setIsLoading(true);
        fetchAPI('/api/projects')
          .then(data => { if (data.status === 'success') setProjects(data.data); })
          .finally(() => setIsLoading(false));
        // 自动切换到新创建的项目并关闭弹窗
        setCurrentProjectId(res.data.id);
        closeAllOverlays();
      }
    } catch (e) {
      alert("创建失败，请检查网络或登录状态。");
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
        {/* ✨ 绑定 onClick 事件 */}
        <button
          onClick={handleCreateProject}
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
    </div>
  );
}
