"use client";

import { Database, Sparkles, ChevronRight } from "lucide-react";

interface Dataset {
  accession: string;
  title: string;
  summary: string;
  status?: string;
}

export function DatasetCards({ datasets }: { datasets: Dataset[] }) {
  // 触发一键分析魔法的函数
  const handleAnalyze = (accession: string) => {
    const magicPrompt = `使用公共数据集 ${accession}，执行单细胞基础分析流程（包括质控、高变基因筛选、PCA和UMAP降维），并保存UMAP图。`;
    
    // 通过自定义事件，将指令发送给外层的 ChatStage
    window.dispatchEvent(new CustomEvent('magic-send-message', { 
      detail: magicPrompt 
    }));
  };

  return (
    <div className="w-full my-4 space-y-4">
      <div className="flex items-center gap-2 text-blue-400 text-sm font-medium mb-3">
        <Database size={16} />
        <span>已从公共多组学数据库检索到以下数据：</span>
      </div>
      
      <div className="grid grid-cols-1 gap-4">
        {datasets.map((ds, idx) => (
          <div 
            key={idx} 
            className="group relative bg-neutral-900/60 border border-neutral-800 hover:border-blue-500/50 rounded-xl p-5 transition-all overflow-hidden"
          >
            {/* 卡片背景光效 */}
            <div className="absolute inset-0 bg-gradient-to-r from-blue-600/0 via-blue-600/0 to-blue-600/5 opacity-0 group-hover:opacity-100 transition-opacity"></div>
            
            <div className="relative z-10 flex flex-col md:flex-row md:items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <span className="px-2 py-0.5 bg-blue-900/30 text-blue-400 text-xs font-mono rounded border border-blue-500/20">
                    {ds.accession}
                  </span>
                  {ds.status && (
                    <span className="text-[10px] text-emerald-500 bg-emerald-900/20 px-2 py-0.5 rounded border border-emerald-500/20">
                      {ds.status}
                    </span>
                  )}
                </div>
                <h4 className="text-white font-medium text-sm leading-relaxed mb-2">
                  {ds.title}
                </h4>
                <p className="text-neutral-500 text-xs line-clamp-2 leading-relaxed">
                  {ds.summary}
                </p>
              </div>

              {/* ⚡️ 魔法按钮 */}
              <div className="shrink-0 flex items-center justify-end">
                <button 
                  onClick={() => handleAnalyze(ds.accession)}
                  className="flex items-center gap-2 bg-blue-600/10 hover:bg-blue-600 text-blue-400 hover:text-white border border-blue-600/30 px-4 py-2 rounded-lg text-sm font-medium transition-all group/btn shadow-[0_0_15px_rgba(37,99,235,0.1)] hover:shadow-[0_0_25px_rgba(37,99,235,0.4)]"
                >
                  <Sparkles size={16} className="group-hover/btn:animate-pulse" />
                  一键导入并分析
                  <ChevronRight size={16} className="opacity-50 group-hover/btn:opacity-100 group-hover/btn:translate-x-1 transition-all" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
