/**
 * useImmediateStream - 即时渲染流式输出 Hook
 *
 * 核心理念：即时渲染 + 渲染节流
 *
 * 与旧版打字机效果的区别：
 * - 旧版：数据先缓冲，再按固定速率消费（故意减慢显示）
 * - 新版：数据立即累积，使用 requestAnimationFrame 节流渲染
 *
 * 优势：
 * 1. 输出速度跟随 LLM 响应速度，而非固定速率
 * 2. 消除"一开始慢、最后突然全部出现"的问题
 * 3. 流水般的平滑输出体验，向 Gemini 对齐
 *
 * 技术实现：
 * - pendingRef: 累积待渲染内容
 * - requestAnimationFrame: 与浏览器刷新同步（60fps）
 * - 最小更新间隔：防止过于频繁的 setState
 */
import { useRef, useCallback, useEffect } from 'react';

interface ImmediateStreamConfig {
  /** 内容更新回调 */
  onContentUpdate: (content: string) => void;
  /** 最小更新间隔（毫秒），默认 16ms（约 60fps） */
  minUpdateInterval?: number;
}

export function useImmediateStream(config: ImmediateStreamConfig) {
  const {
    onContentUpdate,
    minUpdateInterval = 16,
  } = config;

  // ==========================================
  // 核心状态 Refs
  // ==========================================

  // 已渲染的内容（完整累积）
  const contentRef = useRef<string>('');

  // 待渲染的累积内容（用于节流）
  const pendingRef = useRef<string>('');

  // 是否有待处理的渲染（防止重复 rAF）
  const hasPendingRenderRef = useRef(false);

  // 上次渲染时间戳（用于节流）
  const lastRenderTimeRef = useRef<number>(0);

  // rAF ID（用于清理）
  const rafIdRef = useRef<number | null>(null);

  // ==========================================
  // 渲染更新 - 与浏览器刷新同步
  // ==========================================
  const flushRender = useCallback(() => {
    const now = performance.now();
    const timeSinceLastRender = now - lastRenderTimeRef.current;

    // 节流：确保最小更新间隔
    if (timeSinceLastRender < minUpdateInterval && pendingRef.current.length > 0) {
      // 还没到最小间隔，延迟渲染
      rafIdRef.current = requestAnimationFrame(flushRender);
      return;
    }

    // 有待渲染内容，执行更新
    if (pendingRef.current.length > 0) {
      contentRef.current += pendingRef.current;
      pendingRef.current = '';
      lastRenderTimeRef.current = now;
      onContentUpdate(contentRef.current);
    }

    hasPendingRenderRef.current = false;
  }, [onContentUpdate, minUpdateInterval]);

  // ==========================================
  // 追加内容 - 数据立即累积，渲染使用 rAF 节流
  // ==========================================
  const append = useCallback((chunk: string) => {
    if (!chunk) return;

    // 立即累积到待渲染区域
    pendingRef.current += chunk;

    // 如果还没有待处理的渲染，启动 rAF
    if (!hasPendingRenderRef.current) {
      hasPendingRenderRef.current = true;
      rafIdRef.current = requestAnimationFrame(flushRender);
    }
  }, [flushRender]);

  // ==========================================
  // 重置状态
  // ==========================================
  const reset = useCallback(() => {
    contentRef.current = '';
    pendingRef.current = '';
    hasPendingRenderRef.current = false;
    lastRenderTimeRef.current = 0;

    // 清理 rAF
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  // ==========================================
  // 获取当前内容（已渲染 + 待渲染）
  // ==========================================
  const getCurrentContent = useCallback(() => {
    return contentRef.current + pendingRef.current;
  }, []);

  // ==========================================
  // 组件卸载时清理
  // ==========================================
  useEffect(() => {
    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
      }
    };
  }, []);

  return {
    /** 追加内容（立即累积，rAF 节流渲染） */
    append,
    /** 重置状态 */
    reset,
    /** 获取当前内容（已渲染 + 待渲染） */
    getCurrentContent,
  };
}

export default useImmediateStream;