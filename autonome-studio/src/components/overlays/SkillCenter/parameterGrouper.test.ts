/**
 * 参数表单智能分组测试
 *
 * User Journey:
 * As a user, I want skill parameters to be organized in logical groups,
 * so that I can quickly find and fill the parameters I need.
 */

import { describe, it, expect } from 'vitest';
import { groupParameters, ParameterGroup, inferParameterGroup } from './parameterGrouper';

// ==========================================
// 测试数据：模拟技能参数 Schema
// ==========================================

const mockSkillSchema = {
  type: 'object',
  properties: {
    // 输入数据
    sample_table: { type: 'string', description: '样本表文件路径' },
    input_dir: { type: 'string', description: '输入文件目录' },
    genome_reference: { type: 'string', description: '基因组参考文件' },
    // 分析参数
    min_genes: { type: 'integer', description: '最小基因数', default: 200 },
    min_cells: { type: 'integer', description: '最小细胞数', default: 3 },
    resolution: { type: 'number', description: '聚类分辨率', default: 0.5 },
    n_pcs: { type: 'integer', description: '主成分数量', default: 30 },
    // 输出设置
    output_dir: { type: 'string', description: '输出目录' },
    output_format: { type: 'string', description: '输出格式', default: 'h5ad' },
    prefix: { type: 'string', description: '输出文件前缀' },
    // 高级选项
    random_seed: { type: 'integer', description: '随机种子' },
    n_jobs: { type: 'integer', description: '并行任务数', default: 4 },
    memory_limit: { type: 'string', description: '内存限制' },
  },
  required: ['sample_table', 'output_dir'],
};

// ==========================================
// Test Suite: 参数分组
// ==========================================

describe('parameterGrouper', () => {
  // ==========================================
  // Test Case 1: 基础分组功能
  // ==========================================

  it('should group parameters into default categories', () => {
    const groups = groupParameters(mockSkillSchema);

    // 应该有4个默认分组
    expect(groups.length).toBe(4);
    expect(groups.map(g => g.name)).toContain('输入数据');
    expect(groups.map(g => g.name)).toContain('分析参数');
    expect(groups.map(g => g.name)).toContain('输出设置');
    expect(groups.map(g => g.name)).toContain('高级选项');
  });

  it('should assign input parameters to correct group', () => {
    const groups = groupParameters(mockSkillSchema);

    const inputGroup = groups.find(g => g.name === '输入数据');
    expect(inputGroup).toBeDefined();
    expect(inputGroup!.parameters.map(p => p.key)).toContain('sample_table');
    expect(inputGroup!.parameters.map(p => p.key)).toContain('input_dir');
    expect(inputGroup!.parameters.map(p => p.key)).toContain('genome_reference');
  });

  it('should assign analysis parameters to correct group', () => {
    const groups = groupParameters(mockSkillSchema);

    const analysisGroup = groups.find(g => g.name === '分析参数');
    expect(analysisGroup).toBeDefined();
    expect(analysisGroup!.parameters.map(p => p.key)).toContain('min_genes');
    expect(analysisGroup!.parameters.map(p => p.key)).toContain('resolution');
  });

  it('should assign output parameters to correct group', () => {
    const groups = groupParameters(mockSkillSchema);

    const outputGroup = groups.find(g => g.name === '输出设置');
    expect(outputGroup).toBeDefined();
    expect(outputGroup!.parameters.map(p => p.key)).toContain('output_dir');
    expect(outputGroup!.parameters.map(p => p.key)).toContain('output_format');
  });

  it('should assign advanced parameters to correct group', () => {
    const groups = groupParameters(mockSkillSchema);

    const advancedGroup = groups.find(g => g.name === '高级选项');
    expect(advancedGroup).toBeDefined();
    expect(advancedGroup!.parameters.map(p => p.key)).toContain('random_seed');
    expect(advancedGroup!.parameters.map(p => p.key)).toContain('n_jobs');
  });

  // ==========================================
  // Test Case 2: 必填参数标记
  // ==========================================

  it('should mark required parameters', () => {
    const groups = groupParameters(mockSkillSchema);

    const inputGroup = groups.find(g => g.name === '输入数据');
    const sampleTableParam = inputGroup?.parameters.find(p => p.key === 'sample_table');

    expect(sampleTableParam?.required).toBe(true);
  });

  it('should mark optional parameters', () => {
    const groups = groupParameters(mockSkillSchema);

    const outputGroup = groups.find(g => g.name === '输出设置');
    const prefixParam = outputGroup?.parameters.find(p => p.key === 'prefix');

    expect(prefixParam?.required).toBe(false);
  });

  // ==========================================
  // Test Case 3: 默认值推断
  // ==========================================

  it('should extract default values', () => {
    const groups = groupParameters(mockSkillSchema);

    const analysisGroup = groups.find(g => g.name === '分析参数');
    const resolutionParam = analysisGroup?.parameters.find(p => p.key === 'resolution');

    expect(resolutionParam?.defaultValue).toBe(0.5);
  });

  it('should handle parameters without default values', () => {
    const groups = groupParameters(mockSkillSchema);

    const inputGroup = groups.find(g => g.name === '输入数据');
    const inputDirParam = inputGroup?.parameters.find(p => p.key === 'input_dir');

    expect(inputDirParam?.defaultValue).toBeUndefined();
  });

  // ==========================================
  // Test Case 4: 参数类型推断
  // ==========================================

  it('should infer parameter types', () => {
    const groups = groupParameters(mockSkillSchema);

    const analysisGroup = groups.find(g => g.name === '分析参数');
    const minGenesParam = analysisGroup?.parameters.find(p => p.key === 'min_genes');

    expect(minGenesParam?.type).toBe('integer');
  });

  it('should infer parameter description', () => {
    const groups = groupParameters(mockSkillSchema);

    const inputGroup = groups.find(g => g.name === '输入数据');
    const sampleTableParam = inputGroup?.parameters.find(p => p.key === 'sample_table');

    expect(sampleTableParam?.description).toBe('样本表文件路径');
  });

  // ==========================================
  // Test Case 5: 分组折叠状态
  // ==========================================

  it('should set default collapsed state for advanced group', () => {
    const groups = groupParameters(mockSkillSchema);

    const advancedGroup = groups.find(g => g.name === '高级选项');
    expect(advancedGroup?.defaultCollapsed).toBe(true);
  });

  it('should set default expanded state for input group', () => {
    const groups = groupParameters(mockSkillSchema);

    const inputGroup = groups.find(g => g.name === '输入数据');
    expect(inputGroup?.defaultCollapsed).toBe(false);
  });

  // ==========================================
  // Test Case 6: 边界情况
  // ==========================================

  it('should handle empty schema', () => {
    const groups = groupParameters({ type: 'object', properties: {} });

    expect(groups).toEqual([]);
  });

  it('should handle schema without required field', () => {
    const schema = {
      type: 'object',
      properties: {
        param1: { type: 'string' },
      },
    };

    const groups = groupParameters(schema);

    // 所有参数应该标记为非必填
    const allParams = groups.flatMap(g => g.parameters);
    expect(allParams.every(p => !p.required)).toBe(true);
  });

  // ==========================================
  // Test Case 7: 智能分组推断
  // ==========================================

  it('should infer group from parameter name', () => {
    const group = inferParameterGroup('sample_table', { type: 'string' });

    expect(group).toBe('输入数据');
  });

  it('should infer input group from path-related names', () => {
    const group1 = inferParameterGroup('input_file', { type: 'string' });
    const group2 = inferParameterGroup('data_path', { type: 'string' });
    const group3 = inferParameterGroup('reference', { type: 'string' });

    expect(group1).toBe('输入数据');
    expect(group2).toBe('输入数据');
    expect(group3).toBe('输入数据');
  });

  it('should infer output group from output-related names', () => {
    const group1 = inferParameterGroup('output_file', { type: 'string' });
    const group2 = inferParameterGroup('result_dir', { type: 'string' });
    const group3 = inferParameterGroup('save_format', { type: 'string' });

    expect(group1).toBe('输出设置');
    expect(group2).toBe('输出设置');
    expect(group3).toBe('输出设置');
  });

  it('should infer advanced group from technical names', () => {
    const group1 = inferParameterGroup('random_seed', { type: 'integer' });
    const group2 = inferParameterGroup('n_jobs', { type: 'integer' });
    const group3 = inferParameterGroup('timeout', { type: 'integer' });

    expect(group1).toBe('高级选项');
    expect(group2).toBe('高级选项');
    expect(group3).toBe('高级选项');
  });
});

// ==========================================
// Test Suite: 参数分组 UI 组件
// ==========================================

describe('ParameterGroupComponent', () => {
  // 这些测试需要 React Testing Library
  // 这里只做类型检查和基本逻辑测试

  it('should export ParameterGroup type', () => {
    const group: ParameterGroup = {
      name: '测试分组',
      parameters: [
        {
          key: 'test_param',
          type: 'string',
          description: '测试参数',
          required: true,
        },
      ],
      defaultCollapsed: false,
    };

    expect(group.name).toBe('测试分组');
    expect(group.parameters.length).toBe(1);
  });
});