/**
 * useSmartScroll Hook - 智能滚动管理
 *
 * 核心功能：
 * 1. 检测用户是否手动向上滚动
 * 2. 用户滚动时暂停自动滚动
 * 3. 滚动到底部时恢复自动滚动
 * 4. 使用 requestAnimationFrame 实现平滑滚动（替代 scrollIntoView）
 *
 * 问题背景：
 * 原实现中每次消息变化都触发 scrollIntoView({behavior: "smooth"})，
 * 与 CSS scroll-smooth 冲突，导致滚动跳动。
 *
 * 解决方案：
 * 使用 requestAnimationFrame 实现更平滑的滚动控制，
 * 并在用户主动滚动时暂停自动滚动。
 */
import { useRef, useCallback, useEffect, useState } from 'react';

interface SmartScrollOptions {
  /** 滚动到底部时的阈值（像素），小于此值视为已到底部，默认 100 */
  bottomThreshold?: number;
  /** 是否启用平滑滚动，默认 true */
  smoothScroll?: boolean;
  /** 滚动动画持续时间（毫秒），默认 150 */
  scrollDuration?: number;
}

/**
 * 智能滚动 Hook
 *
 * @param containerRef - 滚动容器的 ref
 * @param options - 滚动选项
 * @returns isAtBottom - 是否在底部
 * @returns isUserScrolling - 用户是否正在滚动
 * @returns scrollToBottom - 滚动到底部
 * @returns pauseAutoScroll - 暂停自动滚动
 * @returns resumeAutoScroll - 恢复自动滚动
 */
export function useSmartScroll(
  containerRef: React.RefObject<HTMLElement | null>,
  options: SmartScrollOptions = {}
) {
  const {
    bottomThreshold = 100,
    smoothScroll = true,
    scrollDuration = 150,
  } = options;

  // 是否在底部附近
  const [isAtBottom, setIsAtBottom] = useState(true);
  const isAtBottomRef = useRef(true);

  // 是否暂停自动滚动（用户主动滚动时）
  // 使用 state 而不是 ref，确保组件能正确重渲染并获取最新状态
  const [isPaused, setIsPaused] = useState(false);
  const isPausedRef = useRef(false);

  // 动画帧 ID
  const animationFrameRef = useRef<number | null>(null);

  // 滚动动画开始时间和位置
  const scrollAnimationRef = useRef<{
    startTime: number;
    startScrollTop: number;
    targetScrollTop: number;
  } | null>(null);

  /**
   * 检测是否在底部附近
   */
  const checkIfAtBottom = useCallback(() => {
    const container = containerRef.current;
    if (!container) return true;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

    return distanceFromBottom <= bottomThreshold;
  }, [containerRef, bottomThreshold]);

  /**
   * 使用 requestAnimationFrame 实现平滑滚动
   * 比原生的 scrollIntoView 更可控，避免跳动
   */
  const smoothScrollToBottom = useCallback(() => {
    const container = containerRef.current;
    if (!container || isPausedRef.current) return;

    // 取消之前的动画
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }

    const { scrollHeight, clientHeight } = container;
    const targetScrollTop = scrollHeight - clientHeight;

    // 如果已经在底部附近，直接返回
    const currentDistanceFromBottom = scrollHeight - container.scrollTop - clientHeight;
    if (currentDistanceFromBottom <= 5) {
      return;
    }

    if (smoothScroll && scrollDuration > 0) {
      // 使用动画滚动
      scrollAnimationRef.current = {
        startTime: performance.now(),
        startScrollTop: container.scrollTop,
        targetScrollTop,
      };

      const animateScroll = (currentTime: number) => {
        if (!scrollAnimationRef.current || !container) return;

        const elapsed = currentTime - scrollAnimationRef.current.startTime;
        const progress = Math.min(elapsed / scrollDuration, 1);

        // 使用 easeOutCubic 缓动函数，更平滑
        const easeProgress = 1 - Math.pow(1 - progress, 3);

        const newScrollTop =
          scrollAnimationRef.current.startScrollTop +
          (scrollAnimationRef.current.targetScrollTop - scrollAnimationRef.current.startScrollTop) * easeProgress;

        container.scrollTop = newScrollTop;

        if (progress < 1 && !isPausedRef.current) {
          animationFrameRef.current = requestAnimationFrame(animateScroll);
        }
      };

      animationFrameRef.current = requestAnimationFrame(animateScroll);
    } else {
      // 直接滚动
      container.scrollTop = targetScrollTop;
    }
  }, [containerRef, smoothScroll, scrollDuration]);

  /**
   * 立即滚动到底部（无动画）
   */
  const immediateScrollToBottom = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    // 取消所有动画
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    scrollAnimationRef.current = null;

    const { scrollHeight, clientHeight } = container;
    container.scrollTop = scrollHeight - clientHeight;
  }, [containerRef]);

  /**
   * 滚动到底部（智能选择动画或立即）
   */
  const scrollToBottom = useCallback((immediate: boolean = false) => {
    if (immediate) {
      immediateScrollToBottom();
    } else {
      smoothScrollToBottom();
    }
  }, [smoothScrollToBottom, immediateScrollToBottom]);

  /**
   * 暂停自动滚动
   */
  const pauseAutoScroll = useCallback(() => {
    isPausedRef.current = true;
    setIsPaused(true);
    // 取消当前动画
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, []);

  /**
   * 恢复自动滚动
   */
  const resumeAutoScroll = useCallback(() => {
    isPausedRef.current = false;
    setIsPaused(false);
    // 滚动到底部
    scrollToBottom();
  }, [scrollToBottom]);

  /**
   * 处理滚动事件
   * 检测用户是否主动滚动
   */
  const handleScroll = useCallback(() => {
    const atBottom = checkIfAtBottom();
    isAtBottomRef.current = atBottom;
    setIsAtBottom(atBottom);

    // 如果用户滚动到底部，恢复自动滚动
    if (atBottom && isPausedRef.current) {
      isPausedRef.current = false;
      setIsPaused(false);
    }
  }, [checkIfAtBottom]);

  /**
   * 处理用户主动开始滚动
   * 通过 wheel 事件检测滚动方向
   *
   * 核心逻辑：
   * - 用户向上滚动（deltaY < 0）：立即暂停自动滚动，允许用户查看历史消息
   * - 用户向下滚动（deltaY > 0）：不做特殊处理，让 scroll 事件处理
   *
   * 这样可以确保：AI 输出时自动滚动 → 用户向上滚动 → 停止自动滚动 → 用户可以浏览历史
   */
  const handleWheel = useCallback((event: WheelEvent) => {
    // 用户向上滚动（deltaY < 0 表示滚轮向上，页面内容向下移动，即用户在查看上方内容）
    if (event.deltaY < 0 && !isPausedRef.current) {
      isPausedRef.current = true;
      setIsPaused(true);
    }
    // 用户向下滚动时不做处理，让 scroll 事件判断是否到底部
  }, []);

  /**
   * 处理触摸开始 - 移动端用户开始触摸滚动
   * 触摸时暂停自动滚动，让用户自由控制
   */
  const handleTouchStart = useCallback(() => {
    if (!isPausedRef.current) {
      isPausedRef.current = true;
      setIsPaused(true);
    }
  }, []);

  /**
   * 处理鼠标按下 - 仅在滚动条区域暂停自动滚动
   * 修复：之前任何点击都会暂停，导致点击消息内的按钮也会停止自动滚动
   */
  const handleMouseDown = useCallback((event: MouseEvent) => {
    const container = containerRef.current;
    if (!container) return;

    // 检查是否点击在滚动条区域（容器右侧，滚动条宽度范围内）
    const rect = container.getBoundingClientRect();
    const scrollbarWidth = container.offsetWidth - container.clientWidth;
    const isScrollbarClick = event.clientX >= rect.right - scrollbarWidth;

    if (isScrollbarClick && !isPausedRef.current) {
      isPausedRef.current = true;
      setIsPaused(true);
    }
  }, [containerRef]);

  // 绑定滚动事件
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.addEventListener('scroll', handleScroll, { passive: true });
    // 使用新的 wheel 处理器，检测滚动方向
    container.addEventListener('wheel', handleWheel, { passive: true });
    container.addEventListener('touchstart', handleTouchStart, { passive: true });
    container.addEventListener('mousedown', handleMouseDown, { passive: true });

    return () => {
      container.removeEventListener('scroll', handleScroll);
      container.removeEventListener('wheel', handleWheel);
      container.removeEventListener('touchstart', handleTouchStart);
      container.removeEventListener('mousedown', handleMouseDown);

      // 清理动画帧
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [containerRef, handleScroll, handleWheel, handleTouchStart, handleMouseDown]);

  return {
    /** 是否在底部附近 */
    isAtBottom,
    /** 是否暂停了自动滚动 */
    isPaused,
    /** 是否在底部附近的 ref（避免闭包过期） */
    isAtBottomRef,
    /** 是否暂停自动滚动的 ref（避免闭包过期） */
    isPausedRef,
    /** 滚动到底部 */
    scrollToBottom,
    /** 暂停自动滚动 */
    pauseAutoScroll,
    /** 恢复自动滚动 */
    resumeAutoScroll,
    /** 立即滚动到底部（无动画） */
    immediateScrollToBottom,
  };
}

export default useSmartScroll;