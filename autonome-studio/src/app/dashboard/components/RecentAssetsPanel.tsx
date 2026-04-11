"use client";

/**
 * 科研资产与洞察速递面板
 *
 * 替代"存储空间使用量"，展示：
 * - 成果画廊（图表缩略图）
 * - 最新交付物（报告、数据集）
 * - 快速下载入口
 */

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  ChevronRight,
  FileText,
  Image,
  Table,
  Code,
  Download,
  ExternalLink,
  Folder,
  RefreshCw,
} from "lucide-react";
import { fetchAPI, BASE_URL } from "@/lib/api";

// ==========================================
// 类型定义
// ==========================================

interface RecentAsset {
  id: string;
  type: "plot" | "report" | "data" | "code";
  title: string;
  thumbnail_url?: string;
  file_path: string;
  file_size?: number;
  created_at: string;
  related_task_id?: string;
  download_url: string;
}

interface RecentAssetsData {
  assets: RecentAsset[];
  total_count: number;
  plots_count: number;
  reports_count: number;
}

// ==========================================
// 配置
// ==========================================

const ASSET_TYPE_CONFIG = {
  plot: {
    icon: Image,
    color: "text-purple-400",
    bgColor: "bg-purple-500/10",
    label: "图表",
  },
  report: {
    icon: FileText,
    color: "text-emerald-400",
    bgColor: "bg-emerald-500/10",
    label: "报告",
  },
  data: {
    icon: Table,
    color: "text-blue-400",
    bgColor: "bg-blue-500/10",
    label: "数据",
  },
  code: {
    icon: Code,
    color: "text-amber-400",
    bgColor: "bg-amber-500/10",
    label: "代码",
  },
};

// ==========================================
// 组件
// ==========================================

export function RecentAssetsPanel() {
  const [data, setData] = useState<RecentAssetsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeType, setActiveType] = useState<string | null>(null);

  useEffect(() => {
    loadAssets();
  }, [activeType]);

  const loadAssets = async () => {
    try {
      setIsLoading(true);
      const typeParam = activeType ? `&asset_type=${activeType}` : "";
      const result = await fetchAPI(`/dashboard/recent-assets?limit=12${typeParam}`);
      setData(result);
    } catch (error) {
      console.error("加载资产数据失败:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // 格式化文件大小
  const formatFileSize = (bytes?: number) => {
    if (!bytes) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // 格式化时间
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return "刚刚";
    if (diffMins < 60) return `${diffMins} 分钟前`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} 小时前`;
    return `${Math.floor(diffHours / 24)} 天前`;
  };

  // 过滤资产
  const filteredAssets = activeType
    ? data?.assets.filter((a) => a.type === activeType)
    : data?.assets;

  return (
    <div className="bg-neutral-900 rounded-xl border border-neutral-800 p-6">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <ChevronRight className="w-5 h-5 text-emerald-400" />
          科研资产与洞察速递
        </h2>
        {data && (
          <div className="flex items-center gap-3 text-xs text-neutral-400">
            <span className="flex items-center gap-1">
              <Image className="w-3 h-3 text-purple-400" />
              {data.plots_count} 图表
            </span>
            <span className="flex items-center gap-1">
              <FileText className="w-3 h-3 text-emerald-400" />
              {data.reports_count} 报告
            </span>
          </div>
        )}
      </div>

      {/* 类型过滤器 */}
      <div className="flex items-center gap-2 mb-4">
        <button
          onClick={() => setActiveType(null)}
          className={`px-3 py-1 text-xs rounded-lg transition-colors ${
            activeType === null
              ? "bg-emerald-500/20 text-emerald-300"
              : "bg-neutral-800 text-neutral-400 hover:text-white"
          }`}
        >
          全部
        </button>
        {Object.entries(ASSET_TYPE_CONFIG).map(([type, config]) => (
          <button
            key={type}
            onClick={() => setActiveType(type)}
            className={`px-3 py-1 text-xs rounded-lg transition-colors flex items-center gap-1 ${
              activeType === type
                ? `${config.bgColor} ${config.color}`
                : "bg-neutral-800 text-neutral-400 hover:text-white"
            }`}
          >
            <config.icon className="w-3 h-3" />
            {config.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : !data || data.assets.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-neutral-500">
          <Folder className="w-12 h-12 mb-4 opacity-20" />
          <p className="text-sm">暂无科研资产</p>
          <p className="text-xs mt-1">完成任务后资产将自动展示在这里</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {filteredAssets?.slice(0, 12).map((asset, index) => {
            const typeConfig = ASSET_TYPE_CONFIG[asset.type];
            const IconComponent = typeConfig.icon;

            return (
              <motion.div
                key={asset.id}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: index * 0.03 }}
                className="group bg-neutral-800/50 rounded-lg border border-neutral-700/50 overflow-hidden hover:border-neutral-600 transition-all"
              >
                {/* 缩略图区域 */}
                <div className="aspect-[4/3] bg-neutral-800 relative overflow-hidden">
                  {asset.thumbnail_url ? (
                    <img
                      src={`${BASE_URL}${asset.download_url}`}
                      alt={asset.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  ) : (
                    <div className={`w-full h-full flex items-center justify-center ${typeConfig.bgColor}`}>
                      <IconComponent className={`w-8 h-8 ${typeConfig.color} opacity-50`} />
                    </div>
                  )}

                  {/* 悬浮操作 */}
                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                    <button
                      onClick={() => window.open(`${BASE_URL}${asset.download_url}`, "_blank")}
                      className="p-2 bg-white/10 rounded-lg hover:bg-white/20 transition-colors"
                      title="下载"
                    >
                      <Download className="w-4 h-4 text-white" />
                    </button>
                    <button
                      onClick={() => window.open(`${BASE_URL}${asset.download_url}`, "_blank")}
                      className="p-2 bg-white/10 rounded-lg hover:bg-white/20 transition-colors"
                      title="查看"
                    >
                      <ExternalLink className="w-4 h-4 text-white" />
                    </button>
                  </div>
                </div>

                {/* 信息区域 */}
                <div className="p-2">
                  <p className="text-xs text-white truncate font-medium" title={asset.title}>
                    {asset.title}
                  </p>
                  <div className="flex items-center justify-between mt-1">
                    <span className={`text-xs ${typeConfig.color}`}>
                      {typeConfig.label}
                    </span>
                    <span className="text-xs text-neutral-500">
                      {formatFileSize(asset.file_size)}
                    </span>
                  </div>
                  <p className="text-xs text-neutral-500 mt-1">
                    {formatTime(asset.created_at)}
                  </p>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* 底部统计 */}
      {!isLoading && data && data.assets.length > 0 && (
        <div className="mt-4 pt-4 border-t border-neutral-800 flex items-center justify-between text-xs text-neutral-500">
          <span>
            共 {data.total_count} 项资产
          </span>
          <button
            onClick={loadAssets}
            className="flex items-center gap-1 hover:text-neutral-300 transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            刷新
          </button>
        </div>
      )}
    </div>
  );
}