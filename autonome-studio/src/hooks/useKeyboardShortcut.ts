"use client";

import { useEffect, useCallback } from "react";

interface ShortcutOptions {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  alt?: boolean;
  /**
   * 跨平台修饰键：Mac 上匹配 metaKey(⌘Cmd)，Windows/Linux 上匹配 ctrlKey(Ctrl)
   * 设置后 meta/ctrl 字段不再单独生效
   */
  metaOrCtrl?: boolean;
  preventDefault?: boolean;
}

/**
 * 检测当前是否为 Mac 平台
 */
function isMacPlatform(): boolean {
  if (typeof window === 'undefined') return false;
  return navigator.platform.toLowerCase().includes('mac');
}

export function useKeyboardShortcut(
  options: ShortcutOptions | string,
  callback: (e: KeyboardEvent) => void
) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const targetKey = typeof options === "string" ? options : options.key;
    const isMetaOrCtrl = typeof options === "string" ? false : !!options.metaOrCtrl;
    // metaOrCtrl 优先：设置后忽略单独的 meta/ctrl
    const requireCtrl = isMetaOrCtrl ? false : (typeof options === "string" ? false : !!options.ctrl);
    const requireMeta = isMetaOrCtrl ? false : (typeof options === "string" ? false : !!options.meta);
    const requireShift = typeof options === "string" ? false : !!options.shift;
    const requireAlt = typeof options === "string" ? false : !!options.alt;
    const preventDef = typeof options === "string" ? true : options.preventDefault !== false;

    // Skip if user is typing in an input field (except for Escape)
    const isInput = ["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName);
    if (isInput && targetKey.toLowerCase() !== "escape") {
      return;
    }

    const isKeyMatch = e.key.toLowerCase() === targetKey.toLowerCase();

    // metaOrCtrl 跨平台匹配：Mac 匹配 metaKey，Windows/Linux 匹配 ctrlKey
    let isModifierMatch: boolean;
    if (isMetaOrCtrl) {
      const isMac = isMacPlatform();
      // Mac 上：metaKey 必须按下，ctrlKey 不能按下（避免与右键菜单冲突）
      // Windows/Linux 上：ctrlKey 必须按下，metaKey 不能按下（Win 键有系统功能）
      isModifierMatch = isMac
        ? (e.metaKey && !e.ctrlKey)
        : (e.ctrlKey && !e.metaKey);
    } else {
      const isCtrlMatch = e.ctrlKey === requireCtrl;
      const isMetaMatch = e.metaKey === requireMeta;
      isModifierMatch = isCtrlMatch && isMetaMatch;
    }

    const isShiftMatch = e.shiftKey === requireShift;
    const isAltMatch = e.altKey === requireAlt;

    if (isKeyMatch && isModifierMatch && isShiftMatch && isAltMatch) {
      if (preventDef) e.preventDefault();
      callback(e);
    }
  }, [options, callback]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}
