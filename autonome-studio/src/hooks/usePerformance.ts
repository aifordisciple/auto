/**
 * 性能优化 Hooks
 *
 * 包含：
 * - useDebounce: 防抖 hook
 * - useThrottle: 节流 hook
 * - useDebouncedCallback: 防抖回调
 * - useThrottledCallback: 节流回调
 *
 * @created 2026-04-08
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

/**
 * 防抖 Hook - 延迟更新值
 *
 * @param value 需要防抖的值
 * @param delay 延迟时间（毫秒）
 * @returns 防抖后的值
 *
 * @example
 * const [search, setSearch] = useState('');
 * const debouncedSearch = useDebounce(search, 300);
 *
 * useEffect(() => {
 *   // 只在用户停止输入 300ms 后执行搜索
 *   fetchSearchResults(debouncedSearch);
 * }, [debouncedSearch]);
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debouncedValue;
}

/**
 * 节流 Hook - 限制更新频率
 *
 * @param value 需要节流的值
 * @param interval 间隔时间（毫秒）
 * @returns 节流后的值
 *
 * @example
 * const [scrollY, setScrollY] = useState(0);
 * const throttledScrollY = useThrottle(scrollY, 100);
 */
export function useThrottle<T>(value: T, interval: number): T {
  const [throttledValue, setThrottledValue] = useState<T>(value);
  const lastExecuted = useRef<number>(Date.now());

  useEffect(() => {
    const now = Date.now();
    const timeSinceLastExecution = now - lastExecuted.current;

    if (timeSinceLastExecution >= interval) {
      lastExecuted.current = now;
      setThrottledValue(value);
    } else {
      const timer = setTimeout(() => {
        lastExecuted.current = Date.now();
        setThrottledValue(value);
      }, interval - timeSinceLastExecution);

      return () => clearTimeout(timer);
    }
  }, [value, interval]);

  return throttledValue;
}

/**
 * 防抖回调 Hook
 *
 * @param callback 需要防抖的回调函数
 * @param delay 延迟时间（毫秒）
 * @returns 防抖后的回调函数
 *
 * @example
 * const handleSearch = useDebouncedCallback((query: string) => {
 *   fetchSearchResults(query);
 * }, 300);
 *
 * <input onChange={(e) => handleSearch(e.target.value)} />
 */
export function useDebouncedCallback<T extends (...args: any[]) => any>(
  callback: T,
  delay: number
): (...args: Parameters<T>) => void {
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const callbackRef = useRef(callback);

  // 保持 callback 引用最新
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  const debouncedCallback = useCallback(
    (...args: Parameters<T>) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...args);
      }, delay);
    },
    [delay]
  );

  // 清理
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return debouncedCallback;
}

/**
 * 节流回调 Hook
 *
 * @param callback 需要节流的回调函数
 * @param interval 间隔时间（毫秒）
 * @returns 节流后的回调函数
 *
 * @example
 * const handleScroll = useThrottledCallback(() => {
 *   console.log('滚动位置:', window.scrollY);
 * }, 100);
 *
 * useEffect(() => {
 *   window.addEventListener('scroll', handleScroll);
 *   return () => window.removeEventListener('scroll', handleScroll);
 * }, [handleScroll]);
 */
export function useThrottledCallback<T extends (...args: any[]) => any>(
  callback: T,
  interval: number
): (...args: Parameters<T>) => void {
  const lastExecuted = useRef<number>(0);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const callbackRef = useRef(callback);

  // 保持 callback 引用最新
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  const throttledCallback = useCallback(
    (...args: Parameters<T>) => {
      const now = Date.now();
      const timeSinceLastExecution = now - lastExecuted.current;

      if (timeSinceLastExecution >= interval) {
        lastExecuted.current = now;
        callbackRef.current(...args);
      } else {
        // 清除之前的延迟执行
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
        }

        // 设置延迟执行，确保最后一次调用会被执行
        timeoutRef.current = setTimeout(() => {
          lastExecuted.current = Date.now();
          callbackRef.current(...args);
        }, interval - timeSinceLastExecution);
      }
    },
    [interval]
  );

  // 清理
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return throttledCallback;
}

/**
 * 防抖搜索 Hook - 专门用于搜索场景
 *
 * @param initialQuery 初始搜索词
 * @param delay 延迟时间（毫秒），默认 300ms
 * @param onSearch 搜索回调（可选）
 * @returns { query, debouncedQuery, setQuery, clearQuery }
 *
 * @example
 * const { query, debouncedQuery, setQuery } = useSearch('', 300);
 *
 * useEffect(() => {
 *   if (debouncedQuery) {
 *     searchAPI(debouncedQuery);
 *   }
 * }, [debouncedQuery]);
 */
export function useSearch(
  initialQuery: string = '',
  delay: number = 300,
  onSearch?: (query: string) => void
): {
  query: string;
  debouncedQuery: string;
  setQuery: (query: string) => void;
  clearQuery: () => void;
} {
  const [query, setQuery] = useState(initialQuery);
  const debouncedQuery = useDebounce(query, delay);

  const handleSetQuery = useCallback((newQuery: string) => {
    setQuery(newQuery);
  }, []);

  const clearQuery = useCallback(() => {
    setQuery('');
  }, []);

  // 搜索回调
  useEffect(() => {
    if (onSearch && debouncedQuery) {
      onSearch(debouncedQuery);
    }
  }, [debouncedQuery, onSearch]);

  return {
    query,
    debouncedQuery,
    setQuery: handleSetQuery,
    clearQuery,
  };
}

/**
 * 使用记忆化的值 - 避免不必要的重新计算
 *
 * @param factory 计算函数
 * @param deps 依赖数组
 * @returns 记忆化的值
 */
export function useLazyMemo<T>(factory: () => T, deps: React.DependencyList): T {
  const valueRef = useRef<T | undefined>(undefined);
  const depsRef = useRef(deps);

  if (
    valueRef.current === undefined ||
    deps.length !== depsRef.current.length ||
    deps.some((dep, i) => dep !== depsRef.current[i])
  ) {
    valueRef.current = factory();
    depsRef.current = deps;
  }

  return valueRef.current as T;
}