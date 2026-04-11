/**
 * 增强版错误诊断服务测试
 *
 * User Journey:
 * As a user, I want to understand why my task failed and how to fix it,
 * so that I can recover quickly without needing technical support.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  ErrorDiagnosticService,
  EnhancedErrorDiagnosis,
  diagnoseError,
} from './ErrorDiagnosticService';

// ==========================================
// 测试数据
// ==========================================

const mockParameterError = {
  message: 'ValueError: min_genes must be positive, got -1',
  traceback: ['File "main.py", line 45', 'result = validate_params(params)'],
  context: { skill_id: 'rnaseq_basic_01', execution_id: 'exec_123' },
};

const mockEnvironmentError = {
  message: 'FileNotFoundError: Reference genome not found at /data/genome/hg38',
  traceback: ['File "align.py", line 23', 'ref = load_genome(path)'],
  context: { skill_id: 'alignment_01', execution_id: 'exec_124' },
};

const mockDataError = {
  message: 'DataError: Sample table has 0 valid samples after QC filtering',
  traceback: ['File "qc.py", line 67', 'filtered = apply_qc(samples)'],
  context: { skill_id: 'qc_pipeline_01', execution_id: 'exec_125' },
};

const mockSystemError = {
  message: 'MemoryError: Unable to allocate 64GB for matrix multiplication',
  traceback: ['File "analysis.py", line 120', 'result = np.dot(a, b)'],
  context: { skill_id: 'analysis_01', execution_id: 'exec_126' },
};

// ==========================================
// Test Suite: 错误诊断服务
// ==========================================

describe('ErrorDiagnosticService', () => {
  let service: ErrorDiagnosticService;

  beforeEach(() => {
    vi.clearAllMocks();
    service = new ErrorDiagnosticService();
  });

  // ==========================================
  // Test Case 1: 错误分类
  // ==========================================

  describe('Error Classification', () => {
    it('should classify parameter errors', async () => {
      const diagnosis = await service.diagnose(mockParameterError);

      expect(diagnosis.error_type).toBe('parameter');
      expect(diagnosis.severity).toBe('medium');
    });

    it('should classify environment errors', async () => {
      const diagnosis = await service.diagnose(mockEnvironmentError);

      expect(diagnosis.error_type).toBe('environment');
      expect(diagnosis.severity).toBe('high');
    });

    it('should classify data errors', async () => {
      const diagnosis = await service.diagnose(mockDataError);

      expect(diagnosis.error_type).toBe('data');
      expect(diagnosis.severity).toBe('high');
    });

    it('should classify system errors', async () => {
      const diagnosis = await service.diagnose(mockSystemError);

      expect(diagnosis.error_type).toBe('system');
      expect(diagnosis.severity).toBe('critical');
    });
  });

  // ==========================================
  // Test Case 2: 用户友好消息
  // ==========================================

  describe('User Friendly Messages', () => {
    it('should generate non-technical message for parameter error', async () => {
      const diagnosis = await service.diagnose(mockParameterError);

      expect(diagnosis.user_friendly_message).toBeDefined();
      expect(diagnosis.user_friendly_message).not.toContain('ValueError');
      expect(diagnosis.user_friendly_message.length).toBeLessThan(
        diagnosis.message.length
      );
    });

    it('should generate helpful message for environment error', async () => {
      const diagnosis = await service.diagnose(mockEnvironmentError);

      // 应该生成有用的用户友好消息
      expect(diagnosis.user_friendly_message).toBeDefined();
      expect(diagnosis.user_friendly_message.length).toBeGreaterThan(0);
    });
  });

  // ==========================================
  // Test Case 3: 修复建议
  // ==========================================

  describe('Fix Suggestions', () => {
    it('should provide fix suggestions for parameter error', async () => {
      const diagnosis = await service.diagnose(mockParameterError);

      expect(diagnosis.fix_suggestions.length).toBeGreaterThan(0);
      expect(diagnosis.fix_suggestions[0].description).toBeDefined();
    });

    it('should identify auto-fixable errors', async () => {
      const diagnosis = await service.diagnose(mockParameterError);

      expect(diagnosis.fix_suggestions[0].auto_fixable).toBeDefined();
    });

    it('should provide manual steps when auto-fix not possible', async () => {
      const diagnosis = await service.diagnose(mockEnvironmentError);

      const manualSuggestion = diagnosis.fix_suggestions.find(
        (s) => !s.auto_fixable
      );
      expect(manualSuggestion?.manual_steps).toBeDefined();
    });
  });

  // ==========================================
  // Test Case 4: 根因分析
  // ==========================================

  describe('Root Cause Analysis', () => {
    it('should identify root cause for parameter error', async () => {
      const diagnosis = await service.diagnose(mockParameterError);

      expect(diagnosis.root_cause).toBeDefined();
      expect(diagnosis.root_cause).toContain('min_genes');
    });

    it('should identify root cause for data error', async () => {
      const diagnosis = await service.diagnose(mockDataError);

      expect(diagnosis.root_cause).toBeDefined();
      expect(diagnosis.root_cause.length).toBeGreaterThan(0);
    });
  });

  // ==========================================
  // Test Case 5: 相关文档
  // ==========================================

  describe('Related Documentation', () => {
    it('should provide related help documents', async () => {
      const diagnosis = await service.diagnose(mockParameterError);

      expect(diagnosis.related_help_docs).toBeDefined();
      expect(Array.isArray(diagnosis.related_help_docs)).toBe(true);
    });
  });

  // ==========================================
  // Test Case 6: 便捷函数
  // ==========================================

  describe('Convenience Functions', () => {
    it('should provide standalone diagnose function', async () => {
      const diagnosis = await diagnoseError(mockParameterError);

      expect(diagnosis.error_type).toBe('parameter');
    });
  });

  // ==========================================
  // Test Case 7: 边界情况
  // ==========================================

  describe('Edge Cases', () => {
    it('should handle unknown error types gracefully', async () => {
      const unknownError = {
        message: 'SomeRandomError: Unknown error occurred',
        traceback: [],
        context: {},
      };

      const diagnosis = await service.diagnose(unknownError);

      expect(diagnosis.error_type).toBe('system');
      expect(diagnosis.user_friendly_message).toBeDefined();
    });

    it('should handle empty error message', async () => {
      const emptyError = {
        message: '',
        traceback: [],
        context: {},
      };

      const diagnosis = await service.diagnose(emptyError);

      expect(diagnosis).toBeDefined();
      expect(diagnosis.user_friendly_message).toBeDefined();
    });
  });

  // ==========================================
  // Test Case 8: 预估修复时间
  // ==========================================

  describe('Estimated Fix Time', () => {
    it('should estimate fix time for quick fixes', async () => {
      const diagnosis = await service.diagnose(mockParameterError);

      const quickFix = diagnosis.fix_suggestions.find((s) => s.auto_fixable);
      if (quickFix) {
        expect(quickFix.estimated_time).toBeDefined();
      }
    });

    it('should estimate fix time for manual fixes', async () => {
      const diagnosis = await service.diagnose(mockEnvironmentError);

      const manualFix = diagnosis.fix_suggestions.find((s) => !s.auto_fixable);
      if (manualFix) {
        expect(manualFix.estimated_time).toBeDefined();
      }
    });
  });
});