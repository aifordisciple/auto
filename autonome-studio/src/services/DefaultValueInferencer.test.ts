/**
 * 智能默认值推断服务测试
 *
 * User Journey:
 * As a user, I want the system to suggest default parameter values,
 * so that I don't have to manually enter common parameters every time.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  DefaultValueInferencer,
  InferContext,
  inferDefaultValue,
} from './DefaultValueInferencer';

// ==========================================
// 测试数据
// ==========================================

const mockContext: InferContext = {
  project_id: 'proj_test_123',
  skill_id: 'rnaseq_basic_01',
  user_id: 1,
};

const mockParameter = {
  name: 'min_genes',
  type: 'integer',
  default: 200,
  description: '最小基因数',
};

const mockParameterOutput = {
  name: 'output_dir',
  type: 'string',
  default: 'results',
  description: '输出目录',
};

// ==========================================
// Mock localStorage
// ==========================================

const createLocalStorageMock = () => {
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
};

const localStorageMock = createLocalStorageMock();
(global as any).localStorage = localStorageMock;

// ==========================================
// Test Suite: 智能默认值推断
// ==========================================

describe('DefaultValueInferencer', () => {
  let inferencer: DefaultValueInferencer;

  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
    inferencer = new DefaultValueInferencer();
  });

  // ==========================================
  // Test Case 1: 基础推断
  // ==========================================

  describe('Basic Inference', () => {
    it('should return default value when no history exists', async () => {
      const value = await inferencer.infer(mockContext, mockParameter);

      expect(value).toBe(200);
    });

    it('should return default string value for output_dir', async () => {
      const value = await inferencer.infer(mockContext, mockParameterOutput);

      expect(value).toBe('results');
    });

    it('should return undefined for parameters without default', async () => {
      const paramWithoutDefault = {
        name: 'custom_param',
        type: 'string',
        description: '自定义参数',
      };

      const value = await inferencer.infer(mockContext, paramWithoutDefault);

      expect(value).toBeUndefined();
    });
  });

  // ==========================================
  // Test Case 2: 历史偏好学习
  // ==========================================

  describe('History Preference Learning', () => {
    it('should remember user preference after recording', async () => {
      // 记录用户选择
      await inferencer.recordPreference(mockContext, 'min_genes', 500);

      // 再次推断应该返回历史值
      const value = await inferencer.infer(mockContext, mockParameter);

      expect(value).toBe(500);
    });

    it('should prioritize recent preference', async () => {
      // 记录多次选择
      await inferencer.recordPreference(mockContext, 'min_genes', 300);
      await inferencer.recordPreference(mockContext, 'min_genes', 500);

      const value = await inferencer.infer(mockContext, mockParameter);

      expect(value).toBe(500);
    });

    it('should track preferences per skill', async () => {
      await inferencer.recordPreference(mockContext, 'min_genes', 500);

      // 不同技能应该使用默认值
      const otherContext = { ...mockContext, skill_id: 'other_skill' };
      const value = await inferencer.infer(otherContext, mockParameter);

      expect(value).toBe(200);
    });

    it('should track preferences per user', async () => {
      await inferencer.recordPreference(mockContext, 'min_genes', 500);

      // 不同用户应该使用默认值
      const otherUserContext = { ...mockContext, user_id: 2 };
      const value = await inferencer.infer(otherUserContext, mockParameter);

      expect(value).toBe(200);
    });
  });

  // ==========================================
  // Test Case 3: 数据类型推断
  // ==========================================

  describe('Data Type Inference', () => {
    it('should infer output_dir from project structure', async () => {
      // 设置项目数据类型
      inferencer.setProjectDataType(mockContext.project_id, 'rna-seq');

      const value = await inferencer.infer(mockContext, mockParameterOutput);

      // 应该推断出合理的输出目录
      expect(value).toBeDefined();
    });

    it('should suggest appropriate value based on data type', async () => {
      inferencer.setProjectDataType(mockContext.project_id, 'single-cell');

      // 单细胞数据通常需要不同的参数
      const scParam = {
        name: 'resolution',
        type: 'number',
        default: 0.5,
        description: '聚类分辨率',
      };

      const value = await inferencer.infer(mockContext, scParam);

      // 单细胞数据类型会推断出不同的默认值
      expect(value).toBe(0.8);
    });
  });

  // ==========================================
  // Test Case 4: 批量推断
  // ==========================================

  describe('Batch Inference', () => {
    it('should infer multiple parameters at once', async () => {
      const params = [
        mockParameter,
        mockParameterOutput,
        { name: 'resolution', type: 'number', default: 0.5, description: '分辨率' },
      ];

      const values = await inferencer.inferBatch(mockContext, params);

      expect(Object.keys(values).length).toBe(3);
      expect(values['min_genes']).toBe(200);
      expect(values['output_dir']).toBe('results');
      expect(values['resolution']).toBe(0.5);
    });

    it('should merge with existing values', async () => {
      await inferencer.recordPreference(mockContext, 'min_genes', 300);

      const params = [mockParameter, mockParameterOutput];
      const values = await inferencer.inferBatch(mockContext, params);

      expect(values['min_genes']).toBe(300);
      expect(values['output_dir']).toBe('results');
    });
  });

  // ==========================================
  // Test Case 5: 便捷函数
  // ==========================================

  describe('Convenience Functions', () => {
    it('should provide standalone infer function', async () => {
      const value = await inferDefaultValue(mockContext, mockParameter);

      expect(value).toBe(200);
    });
  });

  // ==========================================
  // Test Case 6: 边界情况
  // ==========================================

  describe('Edge Cases', () => {
    it('should handle null context gracefully', async () => {
      const value = await inferencer.infer(null as any, mockParameter);

      expect(value).toBe(200);
    });

    it('should handle empty parameter', async () => {
      const value = await inferencer.infer(mockContext, {} as any);

      expect(value).toBeUndefined();
    });

    it('should clear all preferences', async () => {
      await inferencer.recordPreference(mockContext, 'min_genes', 500);
      inferencer.clearAllPreferences();

      const value = await inferencer.infer(mockContext, mockParameter);

      expect(value).toBe(200);
    });
  });
});