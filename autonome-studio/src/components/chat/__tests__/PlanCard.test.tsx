import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanCard } from '../PlanCard';

const mockPlan = {
  title: 'QC 分析方案',
  steps: [
    { title: '下载数据', description: '从 SRA 获取 FASTQ 文件' },
    { title: '质量检查', description: '运行 FastQC' },
  ],
  codeSnapshot: 'fastqc input.fastq',
  estimatedCost: '5min',
};

describe('PlanCard', () => {
  it('渲染方案标题和步骤', () => {
    render(<PlanCard plan={mockPlan} onConfirm={() => {}} />);
    expect(screen.getByText('QC 分析方案')).toBeInTheDocument();
    expect(screen.getByText('下载数据')).toBeInTheDocument();
    expect(screen.getByText('质量检查')).toBeInTheDocument();
  });

  it('点击确认按钮触发 onConfirm', () => {
    const onConfirm = vi.fn();
    render(<PlanCard plan={mockPlan} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByText('确认执行方案'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('disabled 时按钮不可点击', () => {
    const onConfirm = vi.fn();
    render(<PlanCard plan={mockPlan} onConfirm={onConfirm} disabled={true} />);
    fireEvent.click(screen.getByText('确认执行方案'));
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
