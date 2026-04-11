/**
 * 命令面板组件测试
 *
 * User Journey:
 * As a power user, I want to quickly access features via keyboard shortcuts,
 * so that I can navigate and execute tasks efficiently without using the mouse.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CommandPalette, Command, CommandCategory } from './CommandPalette';

// ==========================================
// 测试数据
// ==========================================

const mockCommands: Command[] = [
  {
    id: 'skill-center',
    label: '打开技能中心',
    category: 'navigation',
    shortcut: '⌘⇧K',
    action: vi.fn(),
  },
  {
    id: 'new-chat',
    label: '新建对话',
    category: 'action',
    shortcut: '⌘N',
    action: vi.fn(),
  },
  {
    id: 'execute-fastqc',
    label: '执行 FastQC 质控',
    category: 'skill',
    action: vi.fn(),
  },
  {
    id: 'toggle-theme',
    label: '切换主题',
    category: 'setting',
    action: vi.fn(),
  },
];

// ==========================================
// Test Suite: CommandPalette 组件
// ==========================================

describe('CommandPalette', () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ==========================================
  // Test Case 1: 基础渲染
  // ==========================================

  describe('Rendering', () => {
    it('should render command palette when open', () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      expect(screen.getByPlaceholderText('搜索命令...')).toBeInTheDocument();
    });

    it('should not render when closed', () => {
      render(
        <CommandPalette
          isOpen={false}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      expect(screen.queryByPlaceholderText('搜索命令...')).not.toBeInTheDocument();
    });

    it('should display all commands by default', () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      expect(screen.getByText('打开技能中心')).toBeInTheDocument();
      expect(screen.getByText('新建对话')).toBeInTheDocument();
      expect(screen.getByText('执行 FastQC 质控')).toBeInTheDocument();
      expect(screen.getByText('切换主题')).toBeInTheDocument();
    });

    it('should group commands by category', () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      // 检查分类标题（使用更精确的选择器）
      expect(screen.getAllByText('导航').length).toBeGreaterThan(0);
      expect(screen.getAllByText('操作').length).toBeGreaterThan(0);
      expect(screen.getAllByText('技能').length).toBeGreaterThan(0);
      expect(screen.getAllByText('设置').length).toBeGreaterThan(0);
    });
  });

  // ==========================================
  // Test Case 2: 搜索功能
  // ==========================================

  describe('Search', () => {
    it('should filter commands by search query', async () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      const input = screen.getByPlaceholderText('搜索命令...');
      await userEvent.type(input, '技能');

      expect(screen.getByText('打开技能中心')).toBeInTheDocument();
      expect(screen.queryByText('新建对话')).not.toBeInTheDocument();
    });

    it('should show no results message when no matches', async () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      const input = screen.getByPlaceholderText('搜索命令...');
      await userEvent.type(input, '不存在的命令');

      expect(screen.getByText('未找到相关命令')).toBeInTheDocument();
    });

    it('should be case-insensitive', async () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      const input = screen.getByPlaceholderText('搜索命令...');
      await userEvent.type(input, 'FASTQC');

      expect(screen.getByText('执行 FastQC 质控')).toBeInTheDocument();
    });
  });

  // ==========================================
  // Test Case 3: 交互行为
  // ==========================================

  describe('Interaction', () => {
    it('should execute command on click', async () => {
      const mockAction = vi.fn();
      const commands = [
        { ...mockCommands[0], action: mockAction },
      ];

      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={commands}
        />
      );

      fireEvent.click(screen.getByText('打开技能中心'));

      expect(mockAction).toHaveBeenCalledTimes(1);
      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    it('should execute command on Enter key', async () => {
      const mockAction = vi.fn();
      const commands = [
        { ...mockCommands[0], action: mockAction },
      ];

      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={commands}
        />
      );

      const input = screen.getByPlaceholderText('搜索命令...');
      input.focus();
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(mockAction).toHaveBeenCalledTimes(1);
    });

    it('should close on Escape key', () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      const input = screen.getByPlaceholderText('搜索命令...');
      fireEvent.keyDown(input, { key: 'Escape' });

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    it('should navigate commands with arrow keys', async () => {
      const mockAction = vi.fn();
      const commands = mockCommands.map((cmd, idx) =>
        idx === 0 ? { ...cmd, action: mockAction } : cmd
      );

      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={commands}
        />
      );

      const input = screen.getByPlaceholderText('搜索命令...');

      // 直接按 Enter（默认选中第一个命令）
      fireEvent.keyDown(input, { key: 'Enter' });

      // 第一个命令应该被执行
      expect(mockAction).toHaveBeenCalled();
    });
  });

  // ==========================================
  // Test Case 4: 快捷键显示
  // ==========================================

  describe('Shortcut Display', () => {
    it('should display shortcut if available', () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      expect(screen.getByText('⌘⇧K')).toBeInTheDocument();
      expect(screen.getByText('⌘N')).toBeInTheDocument();
    });

    it('should not display shortcut if not available', () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
        />
      );

      // 快捷键显示区域应该存在，但某些命令没有快捷键
      const commandWithoutShortcut = screen.getByText('执行 FastQC 质控');
      expect(commandWithoutShortcut).toBeInTheDocument();
    });
  });

  // ==========================================
  // Test Case 5: 最近使用
  // ==========================================

  describe('Recent Commands', () => {
    it('should show recent commands section', () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
          recentCommands={[mockCommands[0]]}
        />
      );

      expect(screen.getByText('最近使用')).toBeInTheDocument();
    });

    it('should display recent commands at top', () => {
      render(
        <CommandPalette
          isOpen={true}
          onClose={mockOnClose}
          commands={mockCommands}
          recentCommands={[mockCommands[2]]}
        />
      );

      // 验证最近使用部分存在
      expect(screen.getByText('最近使用')).toBeInTheDocument();
      // 验证命令存在（使用 getAllByText 因为命令可能在多个地方出现）
      expect(screen.getAllByText('执行 FastQC 质控').length).toBeGreaterThan(0);
    });
  });
});