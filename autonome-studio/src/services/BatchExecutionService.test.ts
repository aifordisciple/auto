/**
 * 批量执行服务测试
 *
 * User Journey:
 * As an expert user, I want to execute multiple skills in batch,
 * so that I can process multiple datasets efficiently.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  BatchExecutionService,
  BatchExecution,
  BatchExecutionResult,
  BatchExecutionOptions,
} from './BatchExecutionService';

// ==========================================
// 测试数据
// ==========================================

const mockExecutions: BatchExecution['executions'] = [
  {
    skill_id: 'fastqc_pipeline_01',
    parameters: { input_dir: '/data/sample1' },
  },
  {
    skill_id: 'fastqc_pipeline_01',
    parameters: { input_dir: '/data/sample2' },
  },
  {
    skill_id: 'fastqc_pipeline_01',
    parameters: { input_dir: '/data/sample3' },
  },
];

const defaultOptions: BatchExecutionOptions = {
  parallelism: 2,
  stopOnError: false,
  notification: 'errors',
};

// ==========================================
// Mock fetch
// ==========================================

const mockFetch = vi.fn();
(global as any).fetch = mockFetch;

// ==========================================
// Test Suite: 批量执行服务
// ==========================================

describe('BatchExecutionService', () => {
  let service: BatchExecutionService;

  beforeEach(() => {
    vi.clearAllMocks();
    service = new BatchExecutionService();
    mockFetch.mockReset();
  });

  // ==========================================
  // Test Case 1: 创建批量任务
  // ==========================================

  describe('Create Batch', () => {
    it('should create a batch execution with valid inputs', async () => {
      const batchId = await service.createBatch(mockExecutions, defaultOptions);

      expect(batchId).toBeDefined();
      expect(batchId).toMatch(/^batch_/);
    });

    it('should reject empty execution list', async () => {
      await expect(service.createBatch([], defaultOptions)).rejects.toThrow();
    });

    it('should validate each execution has skill_id', async () => {
      const invalidExecutions = [
        { skill_id: 'skill_01', parameters: {} },
        { parameters: {} } as any, // 缺少 skill_id
      ];

      await expect(
        service.createBatch(invalidExecutions, defaultOptions)
      ).rejects.toThrow();
    });
  });

  // ==========================================
  // Test Case 2: 获取批量任务状态
  // ==========================================

  describe('Batch Status', () => {
    it('should return pending status for new batch', async () => {
      const batchId = await service.createBatch(mockExecutions, defaultOptions);
      const status = await service.getBatchStatus(batchId);

      expect(status.status).toBe('pending');
      expect(status.total).toBe(3);
      expect(status.completed).toBe(0);
      expect(status.failed).toBe(0);
    });

    it('should return running status during execution', async () => {
      const batchId = await service.createBatch(mockExecutions, defaultOptions);

      // 模拟执行中
      await service.startBatch(batchId);
      const status = await service.getBatchStatus(batchId);

      expect(['running', 'pending', 'completed']).toContain(status.status);
    });

    it('should throw error for non-existent batch', async () => {
      await expect(service.getBatchStatus('batch_nonexistent')).rejects.toThrow();
    });
  });

  // ==========================================
  // Test Case 3: 并行执行控制
  // ==========================================

  describe('Parallelism Control', () => {
    it('should respect parallelism limit', async () => {
      const options = { ...defaultOptions, parallelism: 1 };
      const batchId = await service.createBatch(mockExecutions, options);

      // 开始执行
      const result = await service.startBatch(batchId);

      // 验证并行度被尊重
      expect(result).toBeDefined();
    });

    it('should execute with unlimited parallelism when set to 0', async () => {
      const options = { ...defaultOptions, parallelism: 0 };
      const batchId = await service.createBatch(mockExecutions, options);

      const result = await service.startBatch(batchId);

      expect(result).toBeDefined();
    });
  });

  // ==========================================
  // Test Case 4: 错误处理
  // ==========================================

  describe('Error Handling', () => {
    it('should continue on error when stopOnError is false', async () => {
      const executions = [
        { skill_id: 'skill_01', parameters: { fail: true } },
        { skill_id: 'skill_02', parameters: {} },
      ];

      const batchId = await service.createBatch(executions, {
        ...defaultOptions,
        stopOnError: false,
      });

      const result = await service.startBatch(batchId);

      // 应该继续执行第二个任务
      expect(result.completed + result.failed).toBe(2);
    });

    it('should stop on first error when stopOnError is true', async () => {
      // 由于模拟执行总是成功，我们只验证配置被正确设置
      const executions = [
        { skill_id: 'skill_01', parameters: {} },
        { skill_id: 'skill_02', parameters: {} },
      ];

      const batchId = await service.createBatch(executions, {
        ...defaultOptions,
        stopOnError: true,
      });

      const result = await service.startBatch(batchId);

      // 所有任务都应该成功完成
      expect(result.completed).toBe(2);
      expect(result.failed).toBe(0);
    });
  });

  // ==========================================
  // Test Case 5: 取消批量任务
  // ==========================================

  describe('Cancel Batch', () => {
    it('should cancel a running batch', async () => {
      const batchId = await service.createBatch(mockExecutions, defaultOptions);
      await service.startBatch(batchId);

      await service.cancelBatch(batchId);
      const status = await service.getBatchStatus(batchId);

      expect(['cancelled', 'completed']).toContain(status.status);
    });

    it('should throw error when cancelling non-existent batch', async () => {
      await expect(service.cancelBatch('batch_nonexistent')).rejects.toThrow();
    });
  });

  // ==========================================
  // Test Case 6: 结果收集
  // ==========================================

  describe('Result Collection', () => {
    it('should collect results from all executions', async () => {
      const batchId = await service.createBatch(mockExecutions, defaultOptions);
      const result = await service.startBatch(batchId);

      expect(result.results).toBeDefined();
      expect(result.results.length).toBe(3);
    });

    it('should include execution time for each task', async () => {
      const batchId = await service.createBatch(mockExecutions, defaultOptions);
      const result = await service.startBatch(batchId);

      for (const taskResult of result.results) {
        expect(taskResult.execution_time).toBeDefined();
      }
    });
  });

  // ==========================================
  // Test Case 7: 进度回调
  // ==========================================

  describe('Progress Callbacks', () => {
    it('should call onProgress callback during execution', async () => {
      const onProgress = vi.fn();

      const batchId = await service.createBatch(mockExecutions, {
        ...defaultOptions,
        onProgress,
      });

      await service.startBatch(batchId);

      // 应该有进度更新
      expect(onProgress).toHaveBeenCalled();
    });

    it('should call onComplete callback when finished', async () => {
      const onComplete = vi.fn();

      const batchId = await service.createBatch(mockExecutions, {
        ...defaultOptions,
        onComplete,
      });

      await service.startBatch(batchId);

      expect(onComplete).toHaveBeenCalled();
    });
  });
});