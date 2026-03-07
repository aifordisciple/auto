"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "../../store/useAuthStore";
import { fetchAPI } from "../../lib/api";
import { Sidebar } from "../../components/layout/Sidebar";
import { Search, Plus, FileText, ArrowRight, Sparkles } from "lucide-react";
import { useKeyboardShortcut } from "../../hooks/useKeyboardShortcut";

export default function DashboardPage() {
  const { token, user } = useAuthStore();
  const [projects, setProjects] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const localToken = localStorage.getItem('autonome_access_token');
    if (!localToken) {
      window.location.href = '/login';
      return;
    }
    loadProjects();
  }, []);

  // ESC 返回工作区
  useKeyboardShortcut("Escape", () => {
    const currentId = localStorage.getItem('autonome_current_project_id');
    if (currentId) {
      window.location.href = '/';
    }
  });

  const loadProjects = async () => {
    try {
      setLoading(true);
      const res = await fetchAPI('/api/projects');
      if (res.status === 'success') {
        setProjects(res.data);
      }
    } catch (e) {
      console.error("Failed to load projects", e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async () => {
    const name = prompt("请输入新项目/工作区的名称：", "My New Analysis Project");
    if (!name) return;
    
    try {
      const res = await fetchAPI('/api/projects', {
        method: 'POST',
        body: JSON.stringify({ name, description: "Created via Dashboard" })
      });
      if (res.status === 'success') {
        loadProjects();
      }
    } catch (e) {
      alert("创建失败");
    }
  };

  const handleEnterProject = (projectId: string) => {
    localStorage.setItem('autonome_current_project_id', projectId);
    window.location.href = '/';
  };

  const filteredProjects = projects.filter(p => p.name.toLowerCase().includes(searchQuery.toLowerCase()));

  if (!token) return <div className="h-screen bg-black" />;

  return (
    <div className="h-screen w-full bg-[#131314] flex overflow-hidden font-sans text-neutral-300">
      {/* Left Sidebar */}
      <div className="w-64 shrink-0 border-r border-neutral-800/60 bg-[#1e1e1f] hidden md:flex flex-col z-20">
        <Sidebar />
      </div>

      {/* Main Dashboard Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <div className="max-w-6xl mx-auto w-full p-8 lg:p-12">
          
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-10">
            <h1 className="text-3xl font-normal text-white tracking-wide">Projects</h1>
            
            <div className="flex items-center gap-3">
              <button className="flex items-center gap-2 px-4 py-2 text-sm text-neutral-300 hover:text-white hover:bg-neutral-800 rounded-full transition-colors border border-neutral-700">
                <FileText size={16} /> 导入历史项目
              </button>
              <button 
                onClick={handleCreateProject}
                className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded-full transition-colors shadow-lg"
              >
                <Plus size={16} /> 创建新项目
              </button>
            </div>
          </div>

          {/* Search */}
          <div className="relative mb-8 max-w-xl">
            <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-neutral-500" />
            <input 
              type="text" 
              placeholder="Search for a project" 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#1e1e1f] border border-neutral-700/50 text-white rounded-full pl-12 pr-4 py-3 outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all text-sm placeholder:text-neutral-500"
            />
          </div>

          {/* Loading / Empty / List */}
          {loading ? (
            <div className="text-center py-20 text-neutral-500 animate-pulse">Loading projects...</div>
          ) : filteredProjects.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-32 text-center">
              <div className="w-16 h-16 mb-6 text-neutral-700"><Sparkles size={64} strokeWidth={1} /></div>
              <h3 className="text-white text-lg font-medium mb-2">Can't find your projects here?</h3>
              <p className="text-neutral-500 text-sm max-w-md leading-relaxed">
                Only imported or newly created projects appear here. If you don't see your projects, you can create a new one to start your bioinformatics analysis.
              </p>
            </div>
          ) : (
            <div className="w-full overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-sm text-neutral-500 border-b border-neutral-800/60">
                    <th className="pb-4 font-normal pl-4 w-1/2">Project Name</th>
                    <th className="pb-4 font-normal w-1/4">Created Date</th>
                    <th className="pb-4 font-normal w-1/4">Status</th>
                    <th className="pb-4 font-normal text-right pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {filteredProjects.map((p) => (
                    <tr 
                      key={p.id} 
                      onClick={() => handleEnterProject(p.id)}
                      className="border-b border-neutral-800/30 hover:bg-[#1e1e1f] cursor-pointer transition-colors group"
                    >
                      <td className="py-4 pl-4">
                        <div className="text-blue-400 group-hover:text-blue-300 font-medium mb-1">{p.name}</div>
                        <div className="text-xs text-neutral-500 line-clamp-1">{p.description || "No description"}</div>
                      </td>
                      <td className="py-4 text-neutral-400">
                        {new Date(p.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-4 text-neutral-400 flex items-center gap-2">
                         <span className="w-2 h-2 rounded-full bg-emerald-500/50 border border-emerald-500"></span>
                         Active
                      </td>
                      <td className="py-4 pr-4 text-right">
                        <button 
                          onClick={(e) => { e.stopPropagation(); handleEnterProject(p.id); }}
                          className="opacity-0 group-hover:opacity-100 p-2 text-neutral-400 hover:text-white bg-neutral-800/50 hover:bg-blue-600 rounded-md transition-all inline-flex items-center justify-center"
                        >
                          <ArrowRight size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
