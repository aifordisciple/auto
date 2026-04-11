"use client";
import { useState, useEffect, useMemo } from "react";
import { FolderGit2, Plus, ArrowRight, Search, Archive, Trash2, Edit2, ArchiveRestore } from "lucide-react";
import { useWorkspaceStore } from "../../store/useWorkspaceStore";
import { useUIStore } from "../../store/useUIStore";
import { useChatStore } from "../../store/useChatStore";
import { fetchAPI } from "../../lib/api";

const PRESET_ICONS = ["📁", "🧬", "🔬", "📊", "🧠", "🦠", "💊", "🧪", "🧫", "🤖"];

export function ProjectCenter() {
  const [projects, setProjects] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { currentProjectId, setCurrentProjectId, setCurrentSessionId, clearPendingChatAttachments, clearPastedAttachments } = useWorkspaceStore();
  const { clearMessages } = useChatStore();
  const { closeAllOverlays } = useUIStore();

  // ✨ UI 状态管理
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<'active' | 'archived'>('active');

  // ✨ 弹窗状态管理 (支持创建与编辑双模式)
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [editingId, setEditingId] = useState<string | null>(null);

  // 表单状态
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formIcon, setFormIcon] = useState("📁");

  const loadProjects = () => {
    setIsLoading(true);
    fetchAPI('/api/projects')
      .then(data => { if (data.status === 'success') setProjects(data.data); })
      .finally(() => setIsLoading(false));
  };

  useEffect(() => { loadProjects(); }, []);

  // ✨ 本地搜索与状态过滤
  const filteredProjects = useMemo(() => {
    return projects.filter(p => {
      const matchesTab = (activeTab === 'active' ? p.status !== 'archived' : p.status === 'archived');
      const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                            (p.description && p.description.toLowerCase().includes(searchQuery.toLowerCase()));
      return matchesTab && matchesSearch;
    });
  }, [projects, activeTab, searchQuery]);

  // 打开新建弹窗
  const openCreateModal = () => {
    setModalMode('create');
    setFormName("");
    setFormDesc("");
    setFormIcon("📁");
    setEditingId(null);
    setIsModalOpen(true);
  };

  // 打开编辑弹窗
  const openEditModal = (e: React.MouseEvent, proj: any) => {
    e.stopPropagation();
    setModalMode('edit');
    setFormName(proj.name);
    setFormDesc(proj.description || "");
    setFormIcon(proj.icon || "📁");
    setEditingId(proj.id);
    setIsModalOpen(true);
  };

  // 提交表单 (Create & Edit)
  const handleSubmit = async () => {
    if (!formName.trim()) return;
    try {
      if (modalMode === 'create') {
        const res = await fetchAPI('/api/projects', {
          method: 'POST',
          body: JSON.stringify({ name: formName.trim(), description: formDesc.trim(), icon: formIcon })
        });
        if (res.status === 'success' && res.data) {
          // ✨ 创建新项目时，重置聊天和会话状态
          setCurrentProjectId(res.data.id);
          setCurrentSessionId(null);
          clearMessages();
          clearPendingChatAttachments();
          clearPastedAttachments();
          closeAllOverlays();
        }
      } else if (modalMode === 'edit' && editingId) {
        await fetchAPI(`/api/projects/${editingId}`, {
          method: 'PUT',
          body: JSON.stringify({ name: formName.trim(), description: formDesc.trim(), icon: formIcon })
        });
      }
      loadProjects();
      setIsModalOpen(false);
    } catch (e) {
      alert("操作失败，请检查网络或日志。");
    }
  };

  // 软删除 (归档) / 恢复
  const toggleArchive = async (e: React.MouseEvent, id: string, currentStatus: string) => {
    e.stopPropagation();
    const newStatus = currentStatus === 'archived' ? 'active' : 'archived';
    try {
      await fetchAPI(`/api/projects/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ status: newStatus })
      });
      loadProjects();
      if (currentProjectId === id && newStatus === 'archived') {
        // ✨ 归档当前项目时，清空工作区和聊天状态
        setCurrentProjectId(null);
        setCurrentSessionId(null);
        clearMessages();
        clearPendingChatAttachments();
        clearPastedAttachments();
      }
    } catch (e) {
      console.error(e);
    }
  };

  // 硬删除 (彻底销毁)
  const hardDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm("⚠️ 警告：硬删除将彻底抹除该项目的沙箱与所有物理文件，此操作不可逆！\n\n您确定要继续吗？")) return;

    try {
      await fetchAPI(`/api/projects/${id}`, { method: 'DELETE' });
      loadProjects();
      // ✨ 删除当前项目时，清空工作区和聊天状态
      if (currentProjectId === id) {
        setCurrentProjectId(null);
        setCurrentSessionId(null);
        clearMessages();
        clearPendingChatAttachments();
        clearPastedAttachments();
      }
    } catch (e) {
      alert("删除失败，可能存在外键约束错误。");
    }
  };

  return (
    // ✨ 移动端响应式优化：padding 从固定 p-8 改为响应式 p-4 md:p-8
    <div className="p-4 md:p-8 h-full flex flex-col relative overflow-hidden">

      {/* 头部区域 - 移动端垂直堆叠布局 */}
      <div className="flex flex-col gap-4 md:gap-6 mb-6 md:mb-8 shrink-0">
        {/* 标题行：移动端左右分布，桌面端水平居中 */}
        <div className="flex items-center justify-between">
          {/* 左侧标题区 - 移动端紧凑间距 */}
          <div className="flex items-center gap-2 md:gap-3">
            <div className="p-1.5 md:p-2 bg-purple-600/20 text-purple-500 rounded-lg">
              <FolderGit2 size={20} className="md:w-6 md:h-6" />
            </div>
            <div>
              <h3 className="text-white font-medium text-base md:text-lg">项目中心</h3>
              <p className="text-neutral-500 text-xs md:text-sm hidden sm:block">管理您的生信分析沙箱环境</p>
            </div>
          </div>
          {/* 新建按钮：移动端紧凑显示 */}
          <button onClick={openCreateModal} className="md:hidden flex items-center gap-1 bg-white text-black px-3 py-1.5 rounded-md text-sm font-medium hover:bg-neutral-200 transition-colors">
            <Plus size={14} /> 新建
          </button>
          <button onClick={openCreateModal} className="hidden md:flex items-center gap-2 bg-white text-black px-4 py-2 rounded-md text-sm font-medium hover:bg-neutral-200 transition-colors">
            <Plus size={16} /> 新建项目
          </button>
        </div>

        {/* 搜索与 Tabs 控制台 - 移动端垂直堆叠 */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-neutral-900/50 p-2 md:p-1.5 rounded-lg border border-neutral-800">
          {/* Tab 按钮：移动端平分宽度 */}
          <div className="flex gap-1">
            <button onClick={() => setActiveTab('active')} className={`flex-1 sm:flex-none px-3 md:px-4 py-2 md:py-1.5 rounded-md text-sm font-medium transition-all ${activeTab === 'active' ? 'bg-neutral-800 text-white shadow-sm' : 'text-neutral-500 hover:text-neutral-300'}`}>
              活跃项目
            </button>
            <button onClick={() => setActiveTab('archived')} className={`flex-1 sm:flex-none px-3 md:px-4 py-2 md:py-1.5 rounded-md text-sm font-medium transition-all ${activeTab === 'archived' ? 'bg-neutral-800 text-white shadow-sm' : 'text-neutral-500 hover:text-neutral-300'}`}>
              已归档
            </button>
          </div>

          {/* 搜索框：移动端全宽 */}
          <div className="relative w-full sm:w-64">
            <Search size={14} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-neutral-500" />
            <input
              type="text"
              placeholder="搜索项目名称或介绍..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-neutral-950 border border-neutral-800 rounded-md pl-9 pr-3 py-2 md:py-1.5 text-sm text-white placeholder-neutral-600 focus:outline-none focus:border-blue-500/50 transition-colors"
            />
          </div>
        </div>
      </div>

      {/* 项目卡片列表 */}
      <div className="flex-1 overflow-y-auto pr-2 pb-10">
        {isLoading ? (
          <div className="text-neutral-500 animate-pulse text-sm">正在检索数据沙箱...</div>
        ) : filteredProjects.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-neutral-500 text-sm">
            <FolderGit2 size={32} className="mb-3 opacity-20" />
            未找到匹配的项目
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredProjects.map((proj) => (
              <div
                key={proj.id}
                onClick={() => {
                  if (activeTab === 'active') {
                    // ✨ 切换项目时，重置聊天和会话状态，确保新项目开启新对话
                    setCurrentProjectId(proj.id);
                    setCurrentSessionId(null);  // 清空当前会话
                    clearMessages();            // 清空聊天消息（会保留欢迎语）
                    clearPendingChatAttachments(); // 清空待发送的文件附件
                    clearPastedAttachments();   // 清空粘贴的附件
                    closeAllOverlays();
                  }
                }}
                className={`group bg-neutral-900 border ${currentProjectId === proj.id ? 'border-blue-500 shadow-lg shadow-blue-900/20' : 'border-neutral-800 hover:border-neutral-600'} rounded-xl p-5 transition-all flex flex-col relative ${activeTab === 'archived' ? 'opacity-70 grayscale-[30%] cursor-default' : 'cursor-pointer'}`}
              >
                {/* ✨ 操作栏 - 移动端常驻显示，桌面端 hover 显示 */}
                {/* 移动端：opacity-100 始终可见，按钮触摸目标 >= 44px */}
                {/* 桌面端：opacity-0 group-hover:opacity-100 传统 hover 效果 */}
                <div className="absolute top-4 right-4 flex items-center gap-1.5
                  opacity-100 md:opacity-0 md:group-hover:opacity-100
                  transition-opacity bg-neutral-900/90 backdrop-blur-sm p-1 rounded-md border border-neutral-800">
                  <button onClick={(e) => openEditModal(e, proj)} className="p-2 md:p-1 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0" title="编辑信息"><Edit2 size={16} className="md:w-3.5 md:h-3.5" /></button>
                  <button onClick={(e) => toggleArchive(e, proj.id, proj.status)} className="p-2 md:p-1 text-neutral-400 hover:text-amber-400 hover:bg-neutral-800 rounded min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0" title={activeTab === 'active' ? '归档项目' : '恢复项目'}>
                    {activeTab === 'active' ? <Archive size={16} className="md:w-3.5 md:h-3.5" /> : <ArchiveRestore size={16} className="md:w-3.5 md:h-3.5" />}
                  </button>
                  <button onClick={(e) => hardDelete(e, proj.id)} className="p-2 md:p-1 text-neutral-400 hover:text-red-400 hover:bg-neutral-800 rounded min-h-[44px] min-w-[44px] md:min-h-0 md:min-w-0" title="彻底销毁"><Trash2 size={16} className="md:w-3.5 md:h-3.5" /></button>
                </div>

                {/* 卡片内容 - 移动端为操作栏预留更多空间 */}
                <div className="flex items-start gap-3 mb-3 pr-20 md:pr-16">
                  <div className="text-2xl md:text-xl">{proj.icon || "📁"}</div>
                  <div className="flex-1 min-w-0">
                    <h4 className="text-white font-medium text-base truncate leading-tight">{proj.name}</h4>
                    {currentProjectId === proj.id && <span className="inline-block mt-1 text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded border border-blue-500/30">当前</span>}
                  </div>
                </div>

                <p className="text-neutral-500 text-xs flex-1 mb-4 line-clamp-2">{proj.description || "暂无描述"}</p>

                {/* 底部信息 */}
                <div className="flex justify-between items-center text-[11px] text-neutral-600 border-t border-neutral-800 pt-3">
                  <code className="text-[10px] bg-neutral-950 px-1.5 py-0.5 rounded text-neutral-500">{proj.id.split('_')[1]?.substring(0,6) || proj.id}</code>
                  <span>{new Date(proj.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 创建/编辑弹窗 - 移动端全屏适配 */}
      {isModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-[#1a1a1c] border border-neutral-800 rounded-2xl w-full max-w-md max-h-[90vh] overflow-y-auto p-4 md:p-6 shadow-2xl transform transition-all">
            <h3 className="text-lg font-semibold text-white mb-5">
              {modalMode === 'create' ? '🚀 新建生信项目沙箱' : '📝 编辑项目信息'}
            </h3>

            <div className="space-y-4">
              {/* 图标选择器 */}
              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-2">项目封面图标</label>
                <div className="flex gap-2 flex-wrap">
                  {PRESET_ICONS.map(icon => (
                    <button
                      key={icon}
                      onClick={() => setFormIcon(icon)}
                      className={`w-10 h-10 text-xl flex items-center justify-center rounded-lg border transition-all ${formIcon === icon ? 'bg-blue-500/20 border-blue-500' : 'bg-[#121212] border-neutral-800 hover:border-neutral-500'}`}
                    >
                      {icon}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1.5">项目名称 <span className="text-red-500">*</span></label>
                <input
                  type="text" value={formName} onChange={(e) => setFormName(e.target.value)}
                  placeholder="例如: 肺癌单细胞时空图谱分析"
                  className="w-full bg-[#121212] border border-neutral-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50" autoFocus
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-400 mb-1.5">项目介绍</label>
                <textarea
                  value={formDesc} onChange={(e) => setFormDesc(e.target.value)}
                  placeholder="简要描述该项目的数据来源、物种或研究目的..."
                  className="w-full bg-[#121212] border border-neutral-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50 resize-none h-24"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-8">
              <button onClick={() => setIsModalOpen(false)} className="px-4 py-2 text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg">取消</button>
              <button onClick={handleSubmit} disabled={!formName.trim()} className="px-4 py-2 bg-white hover:bg-neutral-200 disabled:bg-neutral-800 disabled:text-neutral-500 text-black text-sm font-medium rounded-lg">
                {modalMode === 'create' ? '确认创建' : '保存修改'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
