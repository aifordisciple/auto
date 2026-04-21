/**
 * 快捷键设置面板组件
 *
 * 设计日期: 2026-03-23
 *
 * 功能：
 * - 自定义全局快捷键
 * - 录制新的快捷键组合
 * - 恢复默认设置
 */

"use client";

import { useState, useEffect, useCallback } from 'react';
import { useShortcutStore, Shortcut } from '@/store/useShortcutStore';
import { Keyboard, RotateCcw } from 'lucide-react';

// ==========================================
// 快捷键设置面板组件
// ==========================================

export function ShortcutsPanel() {
  const { shortcuts, updateShortcut, resetToDefault } = useShortcutStore();
  const [recordingId, setRecordingId] = useState<string | null>(null);

  // 检测当前平台
  const isMac = typeof window !== 'undefined' && navigator.platform.toLowerCase().includes('mac');

  // 格式化展示快捷键（根据平台动态显示修饰键符号）
  const formatShortcut = (s: Shortcut) => {
    const keys = [];
    if (s.metaOrCtrl) {
      keys.push(isMac ? '⌘' : 'Ctrl');
    } else {
      if (s.meta) keys.push(isMac ? '⌘' : 'Win');
      if (s.ctrl) keys.push('Ctrl');
    }
    if (s.alt) keys.push(isMac ? '⌥' : 'Alt');
    if (s.shift) keys.push(isMac ? '⇧' : 'Shift');
    keys.push(s.key.toUpperCase());
    return keys.join(isMac ? '' : ' + ');
  };

  // 快捷键录制逻辑
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!recordingId) return;

    e.preventDefault();
    e.stopPropagation();

    // 忽略单纯的修饰键按下
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;

    // 退出录制
    if (e.key === 'Escape') {
      setRecordingId(null);
      return;
    }

    // 保存快捷键
    // 跨平台录制：Mac 上按 ⌘Cmd 或 Windows 上按 Ctrl 时，统一存为 metaOrCtrl
    const hasMetaOrCtrl = e.metaKey || e.ctrlKey;
    updateShortcut(recordingId, {
      key: e.key.toLowerCase(),
      metaOrCtrl: hasMetaOrCtrl || undefined,
      // metaOrCtrl 优先，清除单独的 meta/ctrl 避免冲突
      meta: hasMetaOrCtrl ? undefined : (e.metaKey || undefined),
      ctrl: hasMetaOrCtrl ? undefined : (e.ctrlKey || undefined),
      shift: e.shiftKey || undefined,
      alt: e.altKey || undefined
    });
    setRecordingId(null);
  }, [recordingId, updateShortcut]);

  useEffect(() => {
    if (recordingId) {
      window.addEventListener('keydown', handleKeyDown, { capture: true });
      return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
    }
  }, [recordingId, handleKeyDown]);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto space-y-6">

        {/* 标题区 */}
        <div className="flex items-start justify-between mb-2">
          <div>
            <h2 className="text-lg font-semibold text-white mb-1 flex items-center gap-2">
              <Keyboard size={20} className="text-purple-400" />
              快捷键管理
            </h2>
            <p className="text-sm text-neutral-500">自定义全局快捷键以提升生信平台的操作效率。</p>
          </div>
          <button
            onClick={resetToDefault}
            className="flex items-center gap-2 text-xs text-neutral-500 hover:text-white px-3 py-1.5 rounded-lg bg-neutral-900 border border-neutral-800 hover:border-neutral-600 transition-colors"
          >
            <RotateCcw size={14} />
            恢复默认
          </button>
        </div>

        {/* 快捷键列表 */}
        <div className="space-y-3">
          {Object.values(shortcuts).map((sc) => {
            const isRecording = recordingId === sc.id;
            return (
              <div
                key={sc.id}
                className={`flex items-center justify-between p-4 rounded-xl border transition-all ${
                  isRecording
                    ? 'bg-purple-900/10 border-purple-500/50 shadow-[0_0_10px_rgba(168,85,247,0.1)]'
                    : 'bg-neutral-900/50 border-neutral-800 hover:border-neutral-700'
                }`}
              >
                <div>
                  <div className="text-sm font-medium text-neutral-200">{sc.name}</div>
                  <div className="text-xs text-neutral-500 mt-0.5">{sc.description}</div>
                </div>
                <button
                  onClick={() => setRecordingId(isRecording ? null : sc.id)}
                  className={`min-w-[140px] px-3 py-1.5 rounded-lg text-xs font-mono font-medium tracking-wide border transition-all ${
                    isRecording
                      ? 'bg-purple-600 text-white border-purple-500 animate-pulse'
                      : 'bg-neutral-950 text-neutral-300 border-neutral-700 hover:border-neutral-500 hover:bg-neutral-800'
                  }`}
                >
                  {isRecording ? '按下组合键... (Esc 取消)' : formatShortcut(sc)}
                </button>
              </div>
            );
          })}
        </div>

        {/* 录制提示 */}
        <div className="p-4 rounded-lg bg-blue-900/10 border border-blue-900/30">
          <p className="text-xs text-blue-400 leading-relaxed">
            <strong className="font-semibold text-blue-300">💡 录制提示：</strong><br />
            点击需要修改的快捷键，然后直接在键盘上按下你想要的组合（如 <code className="px-1 bg-neutral-800 rounded">Ctrl + K</code>）。
            系统会自动过滤掉与浏览器底层的冲突。<br />
            录制过程中按下 <code className="px-1 bg-neutral-800 rounded">Esc</code> 键可取消修改。
          </p>
        </div>

      </div>
    </div>
  );
}