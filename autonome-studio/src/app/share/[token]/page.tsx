"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BASE_URL } from "../../../lib/api";
import { Bot, User, ShieldCheck, Download } from "lucide-react";
import { MarkdownBlock } from "../../../components/MarkdownBlock";

export default function SharedWorkspacePage() {
  const params = useParams();
  const token = params.token as string;
  
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${BASE_URL}/api/public/shared/${token}`)
      .then(res => {
        if (!res.ok) throw new Error("This shared workspace does not exist or has been revoked.");
        return res.json();
      })
      .then(json => setData(json.data))
      .catch(err => setError(err.message));
  }, [token]);

  if (error) {
    return (
      <div className="min-h-screen bg-neutral-950 flex flex-col items-center justify-center text-center p-4 font-sans">
        <ShieldCheck size={48} className="text-neutral-700 mb-4" />
        <h1 className="text-xl text-white font-medium mb-2">Access Denied</h1>
        <p className="text-neutral-500 text-sm">{error}</p>
      </div>
    );
  }

  if (!data) {
    return <div className="min-h-screen bg-neutral-950 flex items-center justify-center text-blue-500 font-mono animate-pulse">Loading Workspace...</div>;
  }

  return (
    <div className="min-h-screen bg-neutral-950 flex flex-col font-sans relative overflow-hidden">
      {/* 顶部引流 Banner */}
      <div className="h-14 bg-blue-900/20 border-b border-blue-900/50 flex items-center justify-between px-6 z-20 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <span className="text-blue-500 text-lg">🧬</span>
          <span className="text-white font-bold tracking-wider text-sm">AUTONOME <span className="text-neutral-500 font-normal">| Shared Workspace</span></span>
        </div>
        <a href="/login" className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium rounded-full shadow-lg transition-all">
          Sign up to run your own analysis
        </a>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：会话内容 (只读) */}
        <div className="flex-1 overflow-y-auto p-8 relative">
          <div className="max-w-4xl mx-auto space-y-8 pb-20">
            
            <div className="border-b border-neutral-800 pb-6 mb-8">
              <h1 className="text-3xl font-bold text-white mb-2">{data.project_name}</h1>
              <p className="text-neutral-400">{data.project_desc || "No description provided."}</p>
              <div className="mt-4 text-xs text-neutral-600">Created at: {new Date(data.created_at).toLocaleString()}</div>
            </div>

            {data.messages && data.messages.map((msg: any) => (
              <div key={msg.id} className={`flex items-start gap-4 ${msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === 'user' ? 'bg-neutral-800 text-neutral-400' : 'bg-blue-900/40 text-blue-400 border border-blue-500/30'
                }`}>
                  {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
                </div>
                <div className={`flex-1 rounded-xl p-5 border overflow-hidden ${
                  msg.role === 'user' ? 'bg-neutral-800/40 border-neutral-700/50 text-neutral-200' : 'bg-neutral-900/60 border-neutral-800/80 text-neutral-300'
                }`}>
                  {msg.role === 'user' ? <div className="whitespace-pre-wrap text-sm">{msg.content}</div> : <MarkdownBlock content={msg.content} />}
                </div>
              </div>
            ))}
            
            <div className="text-center mt-12 pt-8 border-t border-neutral-800">
              <p className="text-neutral-500 text-sm mb-4">Want to run heavy computational tasks like this?</p>
              <a href="/login" className="inline-block bg-white text-black font-medium px-6 py-2.5 rounded-lg hover:bg-neutral-200 transition-colors">
                Start Your Autonome Studio
              </a>
            </div>
          </div>
        </div>

        {/* 右侧：挂载的文件列表 (防泄露展示) */}
        <div className="w-80 bg-neutral-900 border-l border-neutral-800 p-6 overflow-y-auto hidden md:block">
          <h3 className="text-white font-medium mb-4 flex items-center gap-2">
            <Download size={16} className="text-neutral-500" /> Attached Datasets
          </h3>
          {!data.files || data.files.length === 0 ? (
            <p className="text-neutral-600 text-xs">No files were attached to this session.</p>
          ) : (
            <div className="space-y-3">
              {data.files.map((f: any, idx: number) => (
                <div key={idx} className="bg-neutral-950 border border-neutral-800 p-3 rounded-lg flex flex-col">
                  <span className="text-xs text-blue-300 truncate font-mono mb-1">{f.filename}</span>
                  <span className="text-[10px] text-neutral-600">{(f.file_size / 1024 / 1024).toFixed(2)} MB</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
