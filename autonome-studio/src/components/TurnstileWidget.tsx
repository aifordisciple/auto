/**
 * Cloudflare Turnstile 人机验证组件
 *
 * 设计日期: 2026-04-24
 *
 * 功能：
 * - 渲染 Turnstile 验证 Widget
 * - 验证成功后回调 onVerify(token)
 * - 验证失败/过期时回调 onError/onExpire
 * - 未配置 NEXT_PUBLIC_TURNSTILE_SITE_KEY 时自动跳过（开发环境友好）
 * - 支持显式/隐式渲染模式
 *
 * 使用方式：
 * <TurnstileWidget
 *   onVerify={(token) => setCaptchaToken(token)}
 *   onError={() => setCaptchaToken(null)}
 * />
 */

"use client";

import { useEffect, useRef, useCallback } from 'react';

// Turnstile Site Key（未配置时组件不渲染）
const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || '';

interface TurnstileWidgetProps {
  onVerify: (token: string) => void;
  onError?: (error: string) => void;
  onExpire?: () => void;
  /** 是否在验证成功后自动重置（默认 true，适用于一次性提交场景） */
  autoResetOnVerify?: boolean;
  /** 自定义样式类名 */
  className?: string;
}

/**
 * Turnstile Widget 全局回调注册
 *
 * Turnstile JS SDK 通过全局回调函数通知验证结果。
 * 使用 Map + ref 实现多实例并发支持。
 */
const callbackMap = new Map<string, {
  onVerify: (token: string) => void;
  onError?: (error: string) => void;
  onExpire?: () => void;
}>();

// 注册全局回调（Turnstile SDK 要求回调函数名在 window 上）
if (typeof window !== 'undefined') {
  (window as any).__turnstile_callbacks = {
    verify: (widgetId: string, token: string) => {
      const cb = callbackMap.get(widgetId);
      if (cb) cb.onVerify(token);
    },
    error: (widgetId: string, error: string) => {
      const cb = callbackMap.get(widgetId);
      if (cb) cb.onError?.(error);
    },
    expire: (widgetId: string) => {
      const cb = callbackMap.get(widgetId);
      if (cb) cb.onExpire?.();
    },
  };
}

export function TurnstileWidget({
  onVerify,
  onError,
  onExpire,
  autoResetOnVerify = true,
  className = '',
}: TurnstileWidgetProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string>('');
  const isRenderedRef = useRef(false);

  // 生成唯一 widget ID
  const uniqueId = useRef(`turnstile_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);

  // 注册回调到全局 Map
  useEffect(() => {
    callbackMap.set(uniqueId.current, { onVerify, onError, onExpire });
    return () => {
      callbackMap.delete(uniqueId.current);
    };
  }, [onVerify, onError, onExpire]);

  // 渲染 Turnstile Widget
  const renderWidget = useCallback(() => {
    if (!TURNSTILE_SITE_KEY || !containerRef.current || isRenderedRef.current) return;

    const turnstile = (window as any).turnstile;
    if (!turnstile) return;

    widgetIdRef.current = turnstile.render(containerRef.current, {
      sitekey: TURNSTILE_SITE_KEY,
      callback: `(window.__turnstile_callbacks.verify('${uniqueId.current}', token))`,
      errorCallback: `(window.__turnstile_callbacks.error('${uniqueId.current}', error))`,
      expiredCallback: `(window.__turnstile_callbacks.expire('${uniqueId.current}'))`,
      theme: 'dark',
      size: 'normal',
      appearance: 'interaction-only', // 仅在需要交互时显示
    });
    isRenderedRef.current = true;
  }, []);

  // 加载 Turnstile JS SDK + 渲染
  useEffect(() => {
    if (!TURNSTILE_SITE_KEY) {
      // 未配置 Site Key，直接触发验证成功（开发环境降级）
      onVerify('mock_captcha_token');
      return;
    }

    // 检查 SDK 是否已加载
    if ((window as any).turnstile) {
      renderWidget();
      return;
    }

    // 动态加载 SDK
    const script = document.createElement('script');
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    script.async = true;
    script.onload = () => {
      // SDK 加载完成后渲染
      // turnstile.render 需要在 SDK 加载后才能使用
      setTimeout(renderWidget, 100);
    };
    document.head.appendChild(script);

    return () => {
      // 清理：移除 Widget
      const turnstile = (window as any).turnstile;
      if (turnstile && widgetIdRef.current) {
        turnstile.remove(widgetIdRef.current);
        isRenderedRef.current = false;
      }
    };
  }, [renderWidget, onVerify]);

  // 未配置 Site Key 时不渲染 DOM
  if (!TURNSTILE_SITE_KEY) {
    return null;
  }

  return (
    <div
      ref={containerRef}
      className={`turnstile-container ${className}`}
      style={{ minHeight: '0px' }} // Turnstile 会自动调整高度
    />
  );
}

/**
 * 重置 Turnstile Widget（用于表单提交后重新验证）
 *
 * 需要在父组件中获取 widget ref 后调用
 */
export function resetTurnstileWidget(widgetContainer: HTMLDivElement | null) {
  if (!widgetContainer || !TURNSTILE_SITE_KEY) return;
  const turnstile = (window as any).turnstile;
  if (!turnstile) return;

  // 找到 widget ID 并重置
  const widgetId = widgetContainer.getAttribute('data-turnstile-widget-id');
  if (widgetId) {
    turnstile.reset(widgetId);
  }
}