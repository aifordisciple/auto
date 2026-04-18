/**
 * 命令面板组件
 *
 * P1 效率提升：
 * - 快速访问所有功能
 * - 模糊搜索命令
 * - 键盘导航支持
 * - 显示最近使用
 */

'use client';

import { useState, useEffect, useRef, useMemo, useCallback, ReactNode, KeyboardEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Command as CommandIcon, Navigation, Settings, Zap, Clock, X } from 'lucide-react';

// 使用相对路径导入以避免测试环境路径别名问题
import { cn } from '../../lib/utils';

// ==========================================
// 类型定义
// ==========================================

export type CommandCategory = 'navigation' | 'action' | 'skill' | 'setting';

export interface Command {
  id: string;
  label: string;
  category: CommandCategory;
  shortcut?: string;
  icon?: ReactNode;
  action: () => void;
}

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  commands: Command[];
  recentCommands?: Command[];
  className?: string;
}

// ==========================================
// 分类配置
// ==========================================

const CATEGORY_CONFIG: Record<CommandCategory, { label: string; icon: ReactNode }> = {
  navigation: { label: '导航', icon: <Navigation className="w-4 h-4" /> },
  action: { label: '操作', icon: <CommandIcon className="w-4 h-4" /> },
  skill: { label: '技能', icon: <Zap className="w-4 h-4" /> },
  setting: { label: '设置', icon: <Settings className="w-4 h-4" /> },
};

// ==========================================
// 主组件
// ==========================================

export function CommandPalette({
  isOpen,
  onClose,
  commands,
  recentCommands = [],
  className,
}: CommandPaletteProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // ==========================================
  // 过滤命令
  // ==========================================

  const filteredCommands = useMemo(() => {
    if (!searchQuery.trim()) {
      return commands;
    }

    const query = searchQuery.toLowerCase();
    return commands.filter((cmd) =>
      cmd.label.toLowerCase().includes(query) ||
      cmd.category.toLowerCase().includes(query)
    );
  }, [commands, searchQuery]);

  // 按分类分组
  const groupedCommands = useMemo(() => {
    const groups: Record<CommandCategory, Command[]> = {
      navigation: [],
      action: [],
      skill: [],
      setting: [],
    };

    for (const cmd of filteredCommands) {
      groups[cmd.category].push(cmd);
    }

    return groups;
  }, [filteredCommands]);

  // 扁平化列表（用于键盘导航）
  const flatCommands = useMemo(() => {
    return filteredCommands;
  }, [filteredCommands]);

  // ==========================================
  // 键盘导航
  // ==========================================

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((prev) => Math.min(prev + 1, flatCommands.length - 1));
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((prev) => Math.max(prev - 1, 0));
          break;
        case 'Enter':
          e.preventDefault();
          if (flatCommands[selectedIndex]) {
            executeCommand(flatCommands[selectedIndex]);
          }
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    },
    [flatCommands, selectedIndex, onClose]
  );

  // ==========================================
  // 执行命令
  // ==========================================

  const executeCommand = useCallback(
    (command: Command) => {
      command.action();
      onClose();
    },
    [onClose]
  );

  // ==========================================
  // 自动聚焦
  // ==========================================

  useEffect(() => {
    if (isOpen) {
      setSearchQuery('');
      setSelectedIndex(0);
      // 延迟聚焦，等待动画完成
      setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
    }
  }, [isOpen]);

  // ==========================================
  // 渲染
  // ==========================================

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh] px-4"
      >
        {/* 背景遮罩 */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        />

        {/* 命令面板 */}
        <motion.div
          initial={{ scale: 0.95, opacity: 0, y: -20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.95, opacity: 0, y: -20 }}
          transition={{ type: 'spring', duration: 0.3 }}
          className={cn(
            'relative w-full max-w-xl bg-white dark:bg-[#1a1a1c] rounded-xl shadow-2xl border border-gray-200 dark:border-neutral-800 overflow-hidden',
            className
          )}
        >
          {/* 搜索框 */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-neutral-800">
            <Search className="w-5 h-5 text-neutral-400" />
            <input
              ref={inputRef}
              type="text"
              placeholder="搜索命令..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setSelectedIndex(0);
              }}
              onKeyDown={handleKeyDown}
              className="flex-1 bg-transparent text-neutral-900 dark:text-white placeholder-neutral-500 outline-none text-sm"
            />
            <button
              onClick={onClose}
              className="p-1 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* 命令列表 */}
          <div className="max-h-[60vh] overflow-y-auto p-2">
            {/* 无结果 */}
            {flatCommands.length === 0 && (
              <div className="py-8 text-center text-neutral-500">
                <p>未找到相关命令</p>
              </div>
            )}

            {/* 最近使用 */}
            {recentCommands.length > 0 && !searchQuery && (
              <CommandGroup
                title="最近使用"
                icon={<Clock className="w-4 h-4" />}
                commands={recentCommands}
                selectedIndex={-1}
                onSelect={executeCommand}
              />
            )}

            {/* 分类命令 */}
            {filteredCommands.length > 0 && (
              <>
                {(Object.entries(groupedCommands) as [CommandCategory, Command[]][]).map(
                  ([category, cmds]) =>
                    cmds.length > 0 && (
                      <CommandGroup
                        key={category}
                        title={CATEGORY_CONFIG[category].label}
                        icon={CATEGORY_CONFIG[category].icon}
                        commands={cmds}
                        globalIndex={flatCommands}
                        selectedIndex={selectedIndex}
                        onSelect={executeCommand}
                      />
                    )
                )}
              </>
            )}
          </div>

          {/* 底部提示 */}
          <div className="flex items-center justify-between px-4 py-2 border-t border-gray-200 dark:border-neutral-800 bg-gray-50 dark:bg-[#1e1e20]">
            <div className="flex items-center gap-4 text-xs text-neutral-500">
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-neutral-200 dark:bg-neutral-700 rounded text-[10px]">↑↓</kbd>
                导航
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-neutral-200 dark:bg-neutral-700 rounded text-[10px]">Enter</kbd>
                选择
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-neutral-200 dark:bg-neutral-700 rounded text-[10px]">Esc</kbd>
                关闭
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// ==========================================
// 命令分组组件
// ==========================================

interface CommandGroupProps {
  title: string;
  icon: ReactNode;
  commands: Command[];
  globalIndex?: Command[];
  selectedIndex: number;
  onSelect: (command: Command) => void;
}

function CommandGroup({
  title,
  icon,
  commands,
  globalIndex,
  selectedIndex,
  onSelect,
}: CommandGroupProps) {
  return (
    <div className="mb-2">
      {/* 分类标题 */}
      <div className="flex items-center gap-2 px-2 py-1.5 text-xs font-medium text-neutral-500">
        {icon}
        <span>{title}</span>
      </div>

      {/* 命令列表 */}
      {commands.map((cmd) => {
        const globalIdx = globalIndex ? globalIndex.indexOf(cmd) : -1;
        const isSelected = globalIdx === selectedIndex;

        return (
          <button
            key={cmd.id}
            onClick={() => onSelect(cmd)}
            className={cn(
              'w-full flex items-center justify-between px-3 py-2 rounded-lg text-left transition-colors',
              isSelected
                ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800'
            )}
          >
            <div className="flex items-center gap-3">
              {cmd.icon && <span className="text-neutral-400">{cmd.icon}</span>}
              <span className="text-sm">{cmd.label}</span>
            </div>
            {cmd.shortcut && (
              <kbd className="px-2 py-0.5 text-xs bg-neutral-100 dark:bg-neutral-800 rounded text-neutral-500">
                {cmd.shortcut}
              </kbd>
            )}
          </button>
        );
      })}
    </div>
  );
}

export default CommandPalette;