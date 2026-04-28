'use client'

/**
 * AdhocSkeletonCard — 即席分析策略生成骨架屏。
 *
 * 当后端发送 data-adhoc_status (status=generating_strategy) 事件后，
 * 在 AdhocAnalysisCard 就绪前渲染此脉冲动画骨架卡片，
 * 解决用户提交需求后长时间（10-30s）无反馈的问题。
 */
export function AdhocSkeletonCard() {
  return (
    <div className="my-3 rounded-xl border border-indigo-500/30 bg-white dark:bg-[#1a1a1c] shadow-sm overflow-hidden animate-pulse relative">
      {/* 标题区骨架 */}
      <div className="bg-indigo-50/30 dark:bg-indigo-900/10 p-4 border-b border-indigo-100/50 dark:border-indigo-500/10">
        <div className="h-4 w-48 bg-indigo-200 dark:bg-indigo-700/30 rounded" />
        <div className="h-3 w-64 bg-gray-200 dark:bg-zinc-700/30 rounded mt-3" />
      </div>

      {/* 参数区骨架 */}
      <div className="p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-2">
            <div className="h-3 w-16 bg-gray-200 dark:bg-zinc-700/30 rounded" />
            <div className="h-9 w-full bg-gray-100 dark:bg-zinc-700/20 rounded-md" />
          </div>
          <div className="space-y-2">
            <div className="h-3 w-20 bg-gray-200 dark:bg-zinc-700/30 rounded" />
            <div className="h-9 w-full bg-gray-100 dark:bg-zinc-700/20 rounded-md" />
          </div>
        </div>
      </div>

      {/* 代码区骨架 */}
      <div className="px-4 pb-4">
        <div className="h-3 w-24 bg-gray-200 dark:bg-zinc-700/30 rounded mb-3" />
        <div className="h-24 w-full bg-gray-100 dark:bg-zinc-700/20 rounded-md" />
      </div>

      {/* 操作区骨架 */}
      <div className="p-4 bg-gray-50/50 dark:bg-[#1e1e20] border-t border-gray-200/50 dark:border-zinc-800 flex justify-between">
        <div className="h-9 w-28 bg-gray-200 dark:bg-zinc-700/30 rounded-md" />
        <div className="h-9 w-24 bg-indigo-200 dark:bg-indigo-700/30 rounded-md" />
      </div>

      {/* 生成中提示 */}
      <div className="absolute inset-0 flex items-center justify-center bg-white/60 dark:bg-[#1a1a1c]/60 backdrop-blur-[1px]">
        <div className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-zinc-800 rounded-lg shadow-lg border border-indigo-200 dark:border-indigo-500/30">
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          <span className="text-sm text-gray-700 dark:text-zinc-300 ml-2">
            正在生成分析策略...
          </span>
        </div>
      </div>
    </div>
  )
}
