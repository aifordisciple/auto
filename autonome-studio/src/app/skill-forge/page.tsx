"use client";

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

/**
 * 技能工厂页面 - 重定向到主页技能中心的工厂Tab
 *
 * 现在技能工厂已整合到技能中心，此页面保留用于向后兼容
 */
export default function SkillForgePage() {
  const router = useRouter();

  useEffect(() => {
    // 重定向到主页并打开技能中心的工厂Tab
    router.push('/?open=skill-center&tab=forge');
  }, [router]);

  return (
    <main className="h-screen w-full bg-[#131314] flex items-center justify-center">
      <div className="flex flex-col items-center gap-4 text-neutral-400">
        <Loader2 size={32} className="animate-spin" />
        <p className="text-sm">正在跳转到技能中心...</p>
      </div>
    </main>
  );
}