import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThinkingBlock } from '../ThinkingBlock';

describe('ThinkingBlock', () => {
  it('默认折叠状态下显示思考过程标题', () => {
    render(<ThinkingBlock content="正在分析输入数据..." />);
    expect(screen.getByText('思考过程')).toBeInTheDocument();
  });

  it('点击展开后显示思考内容', () => {
    render(<ThinkingBlock content="正在分析输入数据..." />);
    fireEvent.click(screen.getByText('思考过程'));
    expect(screen.getByText('正在分析输入数据...')).toBeInTheDocument();
  });
});
