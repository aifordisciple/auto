"use client";

import { useState, useEffect } from 'react';

/**
 * useIsMobile Hook - 响应式断点检测
 *
 * 检测当前视口是否为移动端尺寸（< 768px）
 * 用于条件渲染移动端/桌面端组件
 *
 * @returns {boolean} isMobile - 是否为移动端视图
 *
 * @example
 * const isMobile = useIsMobile();
 * return isMobile ? <MobileNav /> : <DesktopNav />;
 */
export function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    // ✨ 初始检测
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };

    // ✨ 首次执行
    checkMobile();

    // ✨ 监听窗口变化
    window.addEventListener('resize', checkMobile);

    // ✨ 清理监听器
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  return isMobile;
}

/**
 * useBreakpoint Hook - 更灵活的断点检测
 *
 * 支持多个断点：
 * - sm: 640px
 * - md: 768px
 * - lg: 1024px
 * - xl: 1280px
 *
 * @returns {object} breakpoints - 各断点状态
 */
export function useBreakpoint() {
  const [breakpoints, setBreakpoints] = useState({
    sm: false,
    md: false,
    lg: false,
    xl: false,
  });

  useEffect(() => {
    const checkBreakpoints = () => {
      setBreakpoints({
        sm: window.innerWidth >= 640,
        md: window.innerWidth >= 768,
        lg: window.innerWidth >= 1024,
        xl: window.innerWidth >= 1280,
      });
    };

    checkBreakpoints();
    window.addEventListener('resize', checkBreakpoints);
    return () => window.removeEventListener('resize', checkBreakpoints);
  }, []);

  return breakpoints;
}