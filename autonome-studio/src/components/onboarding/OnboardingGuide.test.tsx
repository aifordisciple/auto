/**
 * 新手引导组件测试
 *
 * User Journey:
 * As a new user, I want to see helpful guidance when I first visit,
 * so that I can quickly understand what the system does and how to get started.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OnboardingGuide } from './OnboardingGuide';

// ==========================================
// Mock 依赖
// ==========================================

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

// ==========================================
// 测试数据：新手引导步骤
// ==========================================

const mockSteps = [
  {
    title: '数据质控',
    description: '检查测序数据质量，发现异常样本',
    example: '分析我的测序数据质量',
    icon: '🔬',
  },
  {
    title: '基因表达分析',
    description: '比较不同组间的基因表达差异',
    example: '找出两组样本的差异基因',
    icon: '🧬',
  },
  {
    title: '可视化绘图',
    description: '生成论文级图表',
    example: '绘制火山图展示差异基因',
    icon: '📊',
  },
];

// ==========================================
// Test Suite: OnboardingGuide 组件
// ==========================================

describe('OnboardingGuide', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  // ==========================================
  // Test Case 1: 基础渲染
  // ==========================================

  it('should render all guide steps', () => {
    render(<OnboardingGuide steps={mockSteps} />);

    // 验证标题渲染
    expect(screen.getByText('数据质控')).toBeInTheDocument();
    expect(screen.getByText('基因表达分析')).toBeInTheDocument();
    expect(screen.getByText('可视化绘图')).toBeInTheDocument();
  });

  it('should render step descriptions', () => {
    render(<OnboardingGuide steps={mockSteps} />);

    expect(screen.getByText('检查测序数据质量，发现异常样本')).toBeInTheDocument();
    expect(screen.getByText('比较不同组间的基因表达差异')).toBeInTheDocument();
    expect(screen.getByText('生成论文级图表')).toBeInTheDocument();
  });

  it('should render example prompts as buttons', () => {
    render(<OnboardingGuide steps={mockSteps} />);

    expect(screen.getByText('分析我的测序数据质量')).toBeInTheDocument();
    expect(screen.getByText('找出两组样本的差异基因')).toBeInTheDocument();
    expect(screen.getByText('绘制火山图展示差异基因')).toBeInTheDocument();
  });

  // ==========================================
  // Test Case 2: 交互行为
  // ==========================================

  it('should call onExampleClick when example button is clicked', () => {
    const handleExampleClick = vi.fn();
    render(<OnboardingGuide steps={mockSteps} onExampleClick={handleExampleClick} />);

    // 点击第一个示例按钮
    fireEvent.click(screen.getByText('分析我的测序数据质量'));

    expect(handleExampleClick).toHaveBeenCalledTimes(1);
    expect(handleExampleClick).toHaveBeenCalledWith('分析我的测序数据质量');
  });

  it('should call onDismiss when dismiss button is clicked', () => {
    const handleDismiss = vi.fn();
    render(<OnboardingGuide steps={mockSteps} onDismiss={handleDismiss} />);

    // 查找关闭按钮（aria-label="关闭引导"）
    const dismissButton = screen.getByRole('button', { name: '关闭引导' });
    fireEvent.click(dismissButton);

    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  // ==========================================
  // Test Case 3: 显示/隐藏逻辑
  // ==========================================

  it('should not render if user has seen onboarding', () => {
    localStorageMock.setItem('autonome_has_seen_onboarding', 'true');

    render(<OnboardingGuide steps={mockSteps} />);

    // 组件应该不渲染任何内容
    expect(screen.queryByText('数据质控')).not.toBeInTheDocument();
  });

  it('should save to localStorage when dismissed', () => {
    render(<OnboardingGuide steps={mockSteps} />);

    // 点击关闭按钮
    const dismissButton = screen.getByRole('button', { name: '关闭引导' });
    fireEvent.click(dismissButton);

    // 验证 localStorage 被设置
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      'autonome_has_seen_onboarding',
      'true'
    );
  });

  // ==========================================
  // Test Case 4: 边界情况
  // ==========================================

  it('should handle empty steps array gracefully', () => {
    render(<OnboardingGuide steps={[]} />);

    // 应该渲染空状态或默认内容
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('should render with default steps if not provided', () => {
    render(<OnboardingGuide />);

    // 应该渲染默认引导内容
    expect(screen.getByRole('heading')).toBeInTheDocument();
  });

  // ==========================================
  // Test Case 5: 可访问性
  // ==========================================

  it('should have accessible heading', () => {
    render(<OnboardingGuide steps={mockSteps} />);

    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading).toBeInTheDocument();
  });

  it('should have accessible buttons', () => {
    render(<OnboardingGuide steps={mockSteps} />);

    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);

    // 所有按钮都应该有可访问的名称
    buttons.forEach((button) => {
      expect(button).toHaveAccessibleName();
    });
  });
});