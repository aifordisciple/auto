import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolUseBlock } from '../ToolUseBlock';

describe('ToolUseBlock', () => {
  it('tool_use 事件渲染工具名称', () => {
    render(<ToolUseBlock event={{ type: 'tool_use', tool_name: 'skill_search', tool_input: { q: 'fastqc' } }} />);
    expect(screen.getByText('检索技能')).toBeInTheDocument();
  });

  it('tool_result 成功状态显示结果', () => {
    render(<ToolUseBlock event={{ type: 'tool_result', status: 'success', content: '找到 3 个技能' }} />);
    // "结果" 渲染为 "✓ 结果"，使用包含匹配
    expect(screen.getByText(/结果/)).toBeInTheDocument();
    // 内容默认折叠，点击展开后可见
    fireEvent.click(screen.getByText('展开'));
    expect(screen.getByText('找到 3 个技能')).toBeInTheDocument();
  });

  it('未知工具名使用原始名称作为 fallback', () => {
    render(<ToolUseBlock event={{ type: 'tool_use', tool_name: 'unknown_tool' }} />);
    expect(screen.getByText('unknown_tool')).toBeInTheDocument();
  });
});
