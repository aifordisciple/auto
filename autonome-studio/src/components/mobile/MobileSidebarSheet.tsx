"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useUIStore } from "@/store/useUIStore";
import { Sidebar } from "@/components/layout/Sidebar";

/**
 * MobileSidebarSheet - 移动端侧边栏抽屉
 *
 * 设计原则：
 * - 从左侧滑出（x: '-100%' → x: 0）
 * - 宽度 85vw，最大 320px
 * - 复用现有 Sidebar 组件
 * - 支持点击遮罩关闭
 * - 使用 framer-motion AnimatePresence 实现动画
 *
 * 使用场景：
 * - 移动端点击汉堡菜单触发
 * - 提供完整的项目/会话/设置导航
 */
export function MobileSidebarSheet() {
  const { isMobileMenuOpen, closeMobileMenu } = useUIStore();

  return (
    <AnimatePresence>
      {isMobileMenuOpen && (
        <>
          {/* ✨ 遮罩层 - 点击关闭 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm md:hidden"
            onClick={closeMobileMenu}
          />

          {/* ✨ 侧边栏抽屉 */}
          <motion.div
            initial={{ x: "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: "-100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="fixed top-0 left-0 z-50 h-full w-[85vw] max-w-[320px] md:hidden"
          >
            <div className="h-full bg-neutral-900 border-r border-neutral-800 shadow-2xl flex flex-col overflow-hidden">
              {/* ✨ 关闭按钮 */}
              <button
                onClick={closeMobileMenu}
                className="absolute top-4 right-4 p-2 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors z-10"
                aria-label="关闭菜单"
              >
                <X size={20} />
              </button>

              {/* ✨ 复用 Sidebar 组件 */}
              <div className="h-full overflow-y-auto">
                <Sidebar />
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}