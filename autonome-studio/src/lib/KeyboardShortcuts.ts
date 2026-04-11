/**
 * 全局快捷键系统
 *
 * P2 效率提升：
 * - 快速访问常用功能
 * - 支持修饰键组合
 * - 自动检测操作系统并显示对应快捷键格式
 * - 快捷键帮助面板
 */

'use client';

import { useEffect, useCallback, useState } from 'react';

// ==========================================
// 类型定义
// ==========================================

export interface ShortcutDefinition {
  key: string;                  // 按键
  description: string;          // 描述
  action: string;               // 动作标识
  metaKey?: boolean;            // Cmd (Mac) / Ctrl (Windows)
  ctrlKey?: boolean;            // Ctrl
  shiftKey?: boolean;           // Shift
  altKey?: boolean;             // Alt / Option
  category?: 'navigation' | 'action' | 'general';  // 分类
}

type ShortcutHandlers = Record<string, () => void>;

type Platform = 'mac' | 'windows' | 'linux';

// ==========================================
// 平台检测
// ==========================================

export function detectPlatform(): Platform {
  if (typeof window === 'undefined') return 'mac';

  const platform = navigator.platform.toLowerCase();
  if (platform.includes('mac')) return 'mac';
  if (platform.includes('win')) return 'windows';
  return 'linux';
}

// ==========================================
// Hook: 快捷键监听
// ==========================================

export function useKeyboardShortcuts(
  shortcuts: ShortcutDefinition[],
  handlers: ShortcutHandlers
) {
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      // 如果焦点在输入框中，忽略某些快捷键
      const target = event.target as HTMLElement;
      const isInputFocused =
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable;

      for (const shortcut of shortcuts) {
        // 检查按键是否匹配
        if (event.key.toLowerCase() !== shortcut.key.toLowerCase() &&
            event.key !== shortcut.key) {
          continue;
        }

        // 检查修饰键
        const metaMatch = shortcut.metaKey ? event.metaKey || event.ctrlKey : true;
        const ctrlMatch = shortcut.ctrlKey ? event.ctrlKey : !shortcut.ctrlKey;
        const shiftMatch = shortcut.shiftKey ? event.shiftKey : !shortcut.shiftKey;
        const altMatch = shortcut.altKey ? event.altKey : !shortcut.altKey;

        // 如果需要修饰键但没有按，跳过
        if (shortcut.metaKey && !event.metaKey && !event.ctrlKey) continue;
        if (shortcut.ctrlKey && !event.ctrlKey) continue;
        if (shortcut.shiftKey && !event.shiftKey) continue;
        if (shortcut.altKey && !event.altKey) continue;

        // 如果不需要修饰键但按了，跳过
        if (!shortcut.metaKey && (event.metaKey || event.ctrlKey)) continue;
        if (!shortcut.ctrlKey && event.ctrlKey && !shortcut.metaKey) continue;
        if (!shortcut.shiftKey && event.shiftKey) continue;
        if (!shortcut.altKey && event.altKey) continue;

        // 如果在输入框中，忽略非 Escape 的快捷键
        if (isInputFocused && shortcut.key !== 'Escape') {
          continue;
        }

        // 找到匹配的快捷键，执行对应的 handler
        const handler = handlers[shortcut.action];
        if (handler) {
          event.preventDefault();
          handler();
          return;
        }
      }
    },
    [shortcuts, handlers]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);
}

// ==========================================
// 快捷键格式化
// ==========================================

export const KeyboardShortcuts = {
  /**
   * 格式化快捷键显示
   */
  formatShortcut(shortcut: ShortcutDefinition, platform: Platform): string {
    const parts: string[] = [];

    if (shortcut.metaKey) {
      parts.push(platform === 'mac' ? '⌘' : 'Ctrl');
    }
    if (shortcut.ctrlKey) {
      parts.push(platform === 'mac' ? '⌃' : 'Ctrl');
    }
    if (shortcut.altKey) {
      parts.push(platform === 'mac' ? '⌥' : 'Alt');
    }
    if (shortcut.shiftKey) {
      parts.push(platform === 'mac' ? '⇧' : 'Shift');
    }

    // 格式化按键
    const key = formatKey(shortcut.key, platform);
    parts.push(key);

    return parts.join(platform === 'mac' ? '' : '+');
  },

  /**
   * 获取所有快捷键分类
   */
  getCategories(shortcuts: ShortcutDefinition[]): Record<string, ShortcutDefinition[]> {
    return {
      navigation: shortcuts.filter(s => s.category === 'navigation'),
      action: shortcuts.filter(s => s.category === 'action'),
      general: shortcuts.filter(s => !s.category || s.category === 'general'),
    };
  },
};

/**
 * 格式化单个按键
 */
function formatKey(key: string, platform: Platform): string {
  const keyMap: Record<string, string> = {
    'ArrowUp': '↑',
    'ArrowDown': '↓',
    'ArrowLeft': '←',
    'ArrowRight': '→',
    'Escape': 'Esc',
    'Enter': '↵',
    'Backspace': '⌫',
    'Delete': '⌦',
    'Tab': '⇥',
    ' ': 'Space',
  };

  return keyMap[key] || key.toUpperCase();
}

// ==========================================
// 默认快捷键配置
// ==========================================

export const GLOBAL_SHORTCUTS: ShortcutDefinition[] = [
  { key: '/', description: '聚焦搜索框', action: 'focus-search', category: 'navigation' },
  { key: 'k', description: '快速命令面板', action: 'open-command-palette', metaKey: true, category: 'navigation' },
  { key: 'Shift+K', description: '技能中心', action: 'open-skill-center', metaKey: true, shiftKey: true, category: 'navigation' },
  { key: 'Enter', description: '执行当前任务', action: 'execute-task', metaKey: true, category: 'action' },
  { key: 'Escape', description: '关闭弹窗/取消操作', action: 'close-modal', category: 'general' },
  { key: 'n', description: '新对话', action: 'new-chat', metaKey: true, category: 'action' },
  { key: 'h', description: '历史记录', action: 'open-history', metaKey: true, category: 'navigation' },
  { key: '?', description: '快捷键帮助', action: 'show-shortcuts-help', category: 'general' },
];

// 技能中心专用快捷键
export const SKILL_CENTER_SHORTCUTS: ShortcutDefinition[] = [
  { key: '/', description: '搜索技能', action: 'focus-skill-search', category: 'navigation' },
  { key: 'Enter', description: '执行技能', action: 'execute-skill', metaKey: true, category: 'action' },
  { key: 's', description: '保存为模板', action: 'save-template', metaKey: true, category: 'action' },
  { key: 'Tab', description: '切换参数组', action: 'next-param-group', category: 'navigation' },
];

// ==========================================
// Hook: 快捷键帮助面板状态
// ==========================================

export function useShortcutsHelp() {
  const [isVisible, setIsVisible] = useState(false);

  const show = useCallback(() => setIsVisible(true), []);
  const hide = useCallback(() => setIsVisible(false), []);
  const toggle = useCallback(() => setIsVisible(prev => !prev), []);

  return { isVisible, show, hide, toggle };
}

export default KeyboardShortcuts;