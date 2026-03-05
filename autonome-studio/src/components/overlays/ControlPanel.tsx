"use client";
import { useState, useEffect } from "react";
import { Activity, Cpu, HardDrive, MemoryStick } from "lucide-react";
import { BASE_URL } from "../../lib/api";

export function ControlPanel() {
  const [sysStatus, setSysStatus] = useState<any>(null);

  useEffect(() => {
    const fetchStatus = () => {
      fetch(`${BASE_URL}/api/system/status`)
        .then(res => res.json())
        .then(data => { if (data.status === 'success') setSysStatus(data.data); })
        .catch(() => {});
    };
    fetchStatus();
    const intervalId = setInterval(fetchStatus, 2000);
    return () => clearInterval(intervalId);
  }, []);

  return (
    <div className="p-8 h-full flex flex-col">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-2 bg-emerald-600/20 text-emerald-500 rounded-lg"><Activity size={24} /></div>
        <div>
          <h3 className="text-white font-medium text-lg">集群监控面板 (Control Panel)</h3>
          <p className="text-neutral-500 text-sm">实时监控底层计算节点资源消耗。</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* CPU */}
        <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-xl flex flex-col">
          <div className="flex items-center gap-2 text-neutral-400 mb-4"><Cpu size={18} /> CPU 负载</div>
          <div className="text-4xl font-mono text-white mb-2">{sysStatus ? sysStatus.cpu_percent.toFixed(1) : '--'}%</div>
          <div className="w-full bg-neutral-800 rounded-full h-2 mt-auto">
            <div className="bg-emerald-500 h-2 rounded-full transition-all duration-500" style={{ width: `${sysStatus?.cpu_percent || 0}%` }}></div>
          </div>
        </div>
        {/* Memory */}
        <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-xl flex flex-col">
          <div className="flex items-center gap-2 text-neutral-400 mb-4"><MemoryStick size={18} /> 物理内存 (RAM)</div>
          <div className="text-4xl font-mono text-white mb-2">{sysStatus ? sysStatus.memory_percent.toFixed(1) : '--'}%</div>
          <p className="text-xs text-neutral-500 mb-2">{sysStatus ? `${sysStatus.memory_used_gb} GB / ${sysStatus.memory_total_gb} GB` : '...'}</p>
          <div className="w-full bg-neutral-800 rounded-full h-2 mt-auto">
            <div className="bg-blue-500 h-2 rounded-full transition-all duration-500" style={{ width: `${sysStatus?.memory_percent || 0}%` }}></div>
          </div>
        </div>
        {/* Disk */}
        <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-xl flex flex-col">
          <div className="flex items-center gap-2 text-neutral-400 mb-4"><HardDrive size={18} /> 存储空间 (Disk)</div>
          <div className="text-4xl font-mono text-white mb-2">{sysStatus ? sysStatus.disk_percent.toFixed(1) : '--'}%</div>
          <div className="w-full bg-neutral-800 rounded-full h-2 mt-auto">
            <div className="bg-purple-500 h-2 rounded-full transition-all duration-500" style={{ width: `${sysStatus?.disk_percent || 0}%` }}></div>
          </div>
        </div>
      </div>
    </div>
  );
}
