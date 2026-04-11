"use client";

import { useEffect, useCallback } from "react";

interface ShortcutOptions {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  alt?: boolean;
  preventDefault?: boolean;
}

export function useKeyboardShortcut(
  options: ShortcutOptions | string,
  callback: (e: KeyboardEvent) => void
) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const targetKey = typeof options === "string" ? options : options.key;
    const requireCtrl = typeof options === "string" ? false : !!options.ctrl;
    const requireMeta = typeof options === "string" ? false : !!options.meta;
    const requireShift = typeof options === "string" ? false : !!options.shift;
    const requireAlt = typeof options === "string" ? false : !!options.alt;
    const preventDef = typeof options === "string" ? true : options.preventDefault !== false;

    // Skip if user is typing in an input field (except for Escape)
    const isInput = ["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName);
    if (isInput && targetKey.toLowerCase() !== "escape") {
      return;
    }

    const isKeyMatch = e.key.toLowerCase() === targetKey.toLowerCase();
    const isCtrlMatch = e.ctrlKey === requireCtrl;
    const isMetaMatch = e.metaKey === requireMeta;
    const isShiftMatch = e.shiftKey === requireShift;
    const isAltMatch = e.altKey === requireAlt;

    if (isKeyMatch && isCtrlMatch && isMetaMatch && isShiftMatch && isAltMatch) {
      if (preventDef) e.preventDefault();
      callback(e);
    }
  }, [options, callback]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}
