"use client";

import { useUIStore } from "../store/useUIStore";
import { useShortcutStore } from "../store/useShortcutStore";
import { useKeyboardShortcut } from "../hooks/useKeyboardShortcut";

export function ShortcutManager() {
  const { toggleSettings, toggleProjectCenter, toggleDataCenter, toggleTaskCenter } = useUIStore();
  const { shortcuts } = useShortcutStore();

  // 🛡️ 防御性检查：确保 shortcuts 已加载 (防止 Zustand 持久化还没准备好)
  if (!shortcuts || Object.keys(shortcuts).length === 0) return null;

  // 1. 绑定 UI 面板的全局开关
  useKeyboardShortcut(shortcuts.toggle_settings, () => toggleSettings());
  useKeyboardShortcut(shortcuts.toggle_project_center, () => toggleProjectCenter());
  useKeyboardShortcut(shortcuts.toggle_data_center, () => toggleDataCenter());
  useKeyboardShortcut(shortcuts.toggle_task_center, () => toggleTaskCenter());

  // 2. 绑定需要跨组件通信的操作 (抛出全局自定义事件)
  useKeyboardShortcut(shortcuts.new_chat, () => {
    window.dispatchEvent(new CustomEvent('shortcut-new-chat'));
  });

  useKeyboardShortcut(shortcuts.focus_input, (e) => {
    e.preventDefault(); // 阻止把 "/" 或其他键打入正在聚焦的其他地方
    window.dispatchEvent(new CustomEvent('shortcut-focus-input'));
  });

  // 3. 左右侧栏展开收缩快捷键
  useKeyboardShortcut(shortcuts.toggle_left_sidebar, () => {
    window.dispatchEvent(new CustomEvent('shortcut-toggle-left-sidebar'));
  });

  useKeyboardShortcut(shortcuts.toggle_right_sidebar, () => {
    window.dispatchEvent(new CustomEvent('shortcut-toggle-right-sidebar'));
  });

  // 这个组件是"隐形"的引擎，不渲染任何界面
  return null;
}
