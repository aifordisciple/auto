/**
 * useImmediateStream - 即时渲染流式输出 Hook（带逐字打字机效果）
 *
 * 核心理念：即时累积 + 逐字渲染
 *
 * 问题背景：
 * 某些 LLM 服务（如 MiniMax）返回的 SSE chunk 粒度很粗，
 * 一个 chunk 可能包含整段文字（100+ 字符），导致用户看到
 * "等很久然后突然全部出现"的体验。
 *
 * 解决方案：
 * 1. SSE chunk 到达后立即累积到内部 buffer
 * 2. 新增的字符放入"待显示队列"
 * 3. 用 requestAnimationFrame 逐字消费队列
 * 4. 速率自适应：队列越长每帧输出越多字符（加速追赶）
 * 5. 队列短时每帧只输出 1-2 个字符（打字机效果）
 *
 * 关键设计：
 * - consumeFrame 使用 ref 存储，避免闭包过期和 rAF 循环断裂
 * - onContentUpdate 使用 ref 存储，避免 useCallback 重建导致整条链断裂
 */
import { useRef, useCallback, useEffect } from 'react';

interface ImmediateStreamConfig {
  /** 内容更新回调 */
  onContentUpdate: (content: string) => void;
  /** 最小更新间隔（毫秒），默认 16ms（约 60fps） */
  minUpdateInterval?: number;
  /** 每帧基础输出字符数，默认 2 */
  baseCharsPerFrame?: number;
  /** 队列追赶系数：当队列长度超过阈值时，每帧额外输出 (queueLength / factor) 个字符 */
  catchUpFactor?: number;
}

export function useImmediateStream(config: ImmediateStreamConfig) {
  const {
    onContentUpdate,
    minUpdateInterval = 16,
    baseCharsPerFrame = 2,
    catchUpFactor = 30,
  } = config;

  // ==========================================
  // 核心状态 Refs
  // ==========================================

  /** 已确认显示的完整内容（所有已消费的字符） */
  const confirmedContentRef = useRef<string>('');

  /** 待显示的字符队列（逐字消费） */
  const pendingCharsRef = useRef<string>('');

  /** rAF 是否正在运行 */
  const isAnimatingRef = useRef(false);

  /** rAF ID（用于清理） */
  const rafIdRef = useRef<number | null>(null);

  /** 上次渲染时间戳（用于节流） */
  const lastRenderTimeRef = useRef<number>(0);

  /**
   * 用 ref 存储 onContentUpdate，避免 useCallback 重建导致
   * consumeFrame 闭包过期、rAF 循环断裂
   */
  const onContentUpdateRef = useRef(onContentUpdate);
  onContentUpdateRef.current = onContentUpdate;

  // ==========================================
  // 逐字消费动画 - 每帧从队列中取出若干字符显示
  // 使用 ref 稳定引用，rAF 循环不会因重渲染而断裂
  // ==========================================
  const consumeFrame = useCallback(() => {
    const now = performance.now();
    const timeSinceLastRender = now - lastRenderTimeRef.current;

    // 节流：确保最小更新间隔
    if (timeSinceLastRender < minUpdateInterval) {
      rafIdRef.current = requestAnimationFrame(consumeFrame);
      return;
    }

    const queueLen = pendingCharsRef.current.length;

    if (queueLen > 0) {
      // 自适应速率：
      // - 队列短（<10字符）：每帧输出 baseCharsPerFrame 个字符（打字机效果）
      // - 队列长（>=10字符）：每帧额外输出 queueLen/catchUpFactor 个字符（加速追赶）
      let charsToConsume = baseCharsPerFrame;
      if (queueLen > 10) {
        charsToConsume = baseCharsPerFrame + Math.ceil(queueLen / catchUpFactor);
      }

      // 取出字符
      const actualConsume = Math.min(charsToConsume, queueLen);
      const charsToRender = pendingCharsRef.current.slice(0, actualConsume);
      pendingCharsRef.current = pendingCharsRef.current.slice(actualConsume);

      // 累积到已确认内容
      confirmedContentRef.current += charsToRender;
      lastRenderTimeRef.current = now;

      // 通过 ref 调用最新的 onContentUpdate，避免闭包过期
      onContentUpdateRef.current(confirmedContentRef.current);
    }

    // 如果队列还有字符，继续动画；否则停止
    if (pendingCharsRef.current.length > 0) {
      rafIdRef.current = requestAnimationFrame(consumeFrame);
    } else {
      isAnimatingRef.current = false;
    }
  }, [minUpdateInterval, baseCharsPerFrame, catchUpFactor]);
  // 注意：consumeFrame 不依赖 onContentUpdate，通过 ref 间接访问

  // ==========================================
  // 追加内容 - 数据立即累积到队列，rAF 逐字消费
  // ==========================================
  const append = useCallback((chunk: string) => {
    if (!chunk) return;

    // 立即将新 chunk 的所有字符放入待显示队列
    pendingCharsRef.current += chunk;

    // 如果动画未运行，启动它
    if (!isAnimatingRef.current) {
      isAnimatingRef.current = true;
      rafIdRef.current = requestAnimationFrame(consumeFrame);
    }
  }, [consumeFrame]);

  // ==========================================
  // 重置状态
  // ==========================================
  const reset = useCallback(() => {
    confirmedContentRef.current = '';
    pendingCharsRef.current = '';
    isAnimatingRef.current = false;
    lastRenderTimeRef.current = 0;

    // 清理 rAF
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  // ==========================================
  // 获取当前内容（已确认 + 队列中待显示）
  // 用于流结束时一次性提交所有剩余内容
  // ==========================================
  const getCurrentContent = useCallback(() => {
    return confirmedContentRef.current + pendingCharsRef.current;
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
    /** 追加内容（放入逐字消费队列） */
    append,
    /** 重置状态 */
    reset,
    /** 获取当前内容（已显示 + 队列中待显示） */
    getCurrentContent,
  };
}

export default useImmediateStream;
