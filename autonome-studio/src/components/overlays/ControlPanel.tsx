"use client";
import { useState, useEffect } from "react";
import { Activity, Cpu, HardDrive, MemoryStick, X } from "lucide-react"; // ✨ 新增了 X 图标用于关闭
import { BASE_URL } from "../../lib/api";
import { useUIStore } from "@/store/useUIStore"; // ✨ 引入状态商店

export function ControlPanel() {
  const { isControlPanelOpen, closeAllOverlays } = useUIStore(); // ✨ 获取打开状态和关闭方法
  const [sysStatus, setSysStatus] = useState<any>(null);

  useEffect(() => {
    // ✨ 优化：只有在面板打开时才去轮询后端接口，节省性能
    if (!isControlPanelOpen) return;

    const fetchStatus = () => {
      fetch(`${BASE_URL}/api/system/status`)
        .then(res => res.json())
        .then(data => { if (data.status === 'success') setSysStatus(data.data); })
        .catch(() => {});
    };
    fetchStatus();
    const intervalId = setInterval(fetchStatus, 2000);
    return () => clearInterval(intervalId);
  }, [isControlPanelOpen]);

  // ✨ 核心修复：如果状态是 false，直接不渲染
  if (!isControlPanelOpen) return null;

  return (
    // ✨ 核心修复：加入 fixed inset-0 z-50 悬浮层，保证从右侧滑出
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* 模糊遮罩，点击关闭 */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={closeAllOverlays} />
      
      {/* 侧滑面板实体 */}
      <div className="relative w-[450px] md:w-[600px] h-full bg-[#121212] border-l border-neutral-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">
        
        {/* Header 区域：保持与其它面板 UI 一致 */}
        <div className="h-16 shrink-0 border-b border-neutral-800 px-6 flex items-center justify-between bg-neutral-900/40">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-500/20 border border-emerald-500/30 rounded-lg text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.15)]">
              <Activity size={18} strokeWidth={2.5} />
            </div>
            <div>
              <h2 className="text-sm font-bold text-neutral-200 tracking-wide">集群监控面板 (Control Panel)</h2>
              <p className="text-[10px] text-neutral-500 font-mono mt-0.5">实时监控底层计算节点资源消耗</p>
            </div>
          </div>
          <button onClick={closeAllOverlays} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* 内容区域 */}
        <div className="p-6 overflow-y-auto flex-1">
          <div className="grid grid-cols-1 gap-6">
            {/* CPU */}
            <div className="bg-neutral-900/50 border border-neutral-800 p-6 rounded-xl flex flex-col">
              <div className="flex items-center gap-2 text-neutral-400 mb-4"><Cpu size={18} /> CPU 负载</div>
              <div className="text-4xl font-mono text-white mb-2">{sysStatus ? sysStatus.cpu_percent.toFixed(1) : '--'}%</div>
              <div className="w-full bg-neutral-800 rounded-full h-2 mt-auto overflow-hidden">
                <div className="bg-emerald-500 h-full rounded-full transition-all duration-500" style={{ width: `${sysStatus?.cpu_percent || 0}%` }}></div>
              </div>
            </div>
            
            {/* Memory */}
            <div className="bg-neutral-900/50 border border-neutral-800 p-6 rounded-xl flex flex-col">
              <div className="flex items-center gap-2 text-neutral-400 mb-4"><MemoryStick size={18} /> 物理内存 (RAM)</div>
              <div className="text-4xl font-mono text-white mb-2">{sysStatus ? sysStatus.memory_percent.toFixed(1) : '--'}%</div>
              <p className="text-xs text-neutral-500 mb-2">{sysStatus ? `${sysStatus.memory_used_gb} GB / ${sysStatus.memory_total_gb} GB` : '...'}</p>
              <div className="w-full bg-neutral-800 rounded-full h-2 mt-auto overflow-hidden">
                <div className="bg-blue-500 h-full rounded-full transition-all duration-500" style={{ width: `${sysStatus?.memory_percent || 0}%` }}></div>
              </div>
            </div>
            
            {/* Disk */}
            <div className="bg-neutral-900/50 border border-neutral-800 p-6 rounded-xl flex flex-col">
              <div className="flex items-center gap-2 text-neutral-400 mb-4"><HardDrive size={18} /> 存储空间 (Disk)</div>
              <div className="text-4xl font-mono text-white mb-2">{sysStatus ? sysStatus.disk_percent.toFixed(1) : '--'}%</div>
              <div className="w-full bg-neutral-800 rounded-full h-2 mt-auto overflow-hidden">
                <div className="bg-purple-500 h-full rounded-full transition-all duration-500" style={{ width: `${sysStatus?.disk_percent || 0}%` }}></div>
              </div>
            </div>
          </div>
        </div>
        
      </div>
    </div>
  );
}