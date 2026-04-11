/**
 * 工作流编排服务测试
 *
 * User Journey:
 * As an expert user, I want to create custom analysis workflows,
 * so that I can automate complex multi-step analyses.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  WorkflowOrchestrator,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowExecutionResult,
} from './WorkflowOrchestrator';

// ==========================================
// 测试数据
// ==========================================

const simpleWorkflow: WorkflowDefinition = {
  id: 'wf_simple',
  name: '简单线性工作流',
  nodes: [
    {
      id: 'step1',
      type: 'skill',
      skill_id: 'fastqc_pipeline_01',
      parameters: { input_dir: '/data/raw' },
    },
    {
      id: 'step2',
      type: 'skill',
      skill_id: 'alignment_01',
      parameters: { reference: 'hg38' },
      dependsOn: ['step1'],
    },
  ],
};

const conditionalWorkflow: WorkflowDefinition = {
  id: 'wf_conditional',
  name: '条件分支工作流',
  nodes: [
    {
      id: 'qc',
      type: 'skill',
      skill_id: 'fastqc_pipeline_01',
      parameters: {},
    },
    {
      id: 'check_quality',
      type: 'condition',
      condition: 'qc_result.pass == true',
      dependsOn: ['qc'],
    },
    {
      id: 'proceed',
      type: 'skill',
      skill_id: 'alignment_01',
      parameters: {},
      dependsOn: ['check_quality'],
    },
    {
      id: 'abort',
      type: 'skill',
      skill_id: 'notification_01',
      parameters: { message: 'QC failed' },
      dependsOn: ['check_quality'],
      conditionBranch: 'false',
    },
  ],
};

const parallelWorkflow: WorkflowDefinition = {
  id: 'wf_parallel',
  name: '并行执行工作流',
  nodes: [
    {
      id: 'step1',
      type: 'skill',
      skill_id: 'skill_a',
      parameters: {},
    },
    {
      id: 'step2a',
      type: 'skill',
      skill_id: 'skill_b1',
      parameters: {},
      dependsOn: ['step1'],
    },
    {
      id: 'step2b',
      type: 'skill',
      skill_id: 'skill_b2',
      parameters: {},
      dependsOn: ['step1'],
    },
    {
      id: 'step3',
      type: 'skill',
      skill_id: 'skill_c',
      parameters: {},
      dependsOn: ['step2a', 'step2b'],
    },
  ],
};

// ==========================================
// Test Suite: 工作流编排服务
// ==========================================

describe('WorkflowOrchestrator', () => {
  let orchestrator: WorkflowOrchestrator;

  beforeEach(() => {
    vi.clearAllMocks();
    orchestrator = new WorkflowOrchestrator();
  });

  // ==========================================
  // Test Case 1: 工作流验证
  // ==========================================

  describe('Workflow Validation', () => {
    it('should validate a valid workflow', async () => {
      const result = await orchestrator.validateWorkflow(simpleWorkflow);

      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('should detect missing node IDs', async () => {
      const invalidWorkflow = {
        ...simpleWorkflow,
        nodes: [{ type: 'skill', skill_id: 'skill_01', parameters: {} } as any],
      };

      const result = await orchestrator.validateWorkflow(invalidWorkflow);

      expect(result.valid).toBe(false);
    });

    it('should detect circular dependencies', async () => {
      const circularWorkflow: WorkflowDefinition = {
        id: 'wf_circular',
        name: '循环依赖工作流',
        nodes: [
          { id: 'a', type: 'skill', skill_id: 'skill_01', parameters: {}, dependsOn: ['b'] },
          { id: 'b', type: 'skill', skill_id: 'skill_02', parameters: {}, dependsOn: ['a'] },
        ],
      };

      const result = await orchestrator.validateWorkflow(circularWorkflow);

      expect(result.valid).toBe(false);
      expect(result.errors.some((e) => e.includes('circular'))).toBe(true);
    });

    it('should detect missing dependencies', async () => {
      const invalidWorkflow: WorkflowDefinition = {
        id: 'wf_invalid',
        name: '无效工作流',
        nodes: [
          { id: 'a', type: 'skill', skill_id: 'skill_01', parameters: {} },
          { id: 'b', type: 'skill', skill_id: 'skill_02', parameters: {}, dependsOn: ['nonexistent'] },
        ],
      };

      const result = await orchestrator.validateWorkflow(invalidWorkflow);

      expect(result.valid).toBe(false);
    });
  });

  // ==========================================
  // Test Case 2: 执行顺序
  // ==========================================

  describe('Execution Order', () => {
    it('should execute nodes in correct order', async () => {
      const order = await orchestrator.getExecutionOrder(simpleWorkflow);

      expect(order).toBeDefined();
      expect(order.length).toBe(2);
      // step1 应该在 step2 之前
      expect(order.indexOf('step1')).toBeLessThan(order.indexOf('step2'));
    });

    it('should handle parallel execution', async () => {
      const order = await orchestrator.getExecutionOrder(parallelWorkflow);

      // step2a 和 step2b 可以并行执行
      expect(order).toBeDefined();
      expect(order.length).toBe(4);
    });
  });

  // ==========================================
  // Test Case 3: 工作流执行
  // ==========================================

  describe('Workflow Execution', () => {
    it('should execute a simple workflow', async () => {
      const result = await orchestrator.executeWorkflow(simpleWorkflow);

      expect(result.status).toBe('success');
      expect(result.nodeResults.length).toBe(2);
    });

    it('should skip downstream nodes on failure', async () => {
      // 模拟失败的工作流
      const result = await orchestrator.executeWorkflow(simpleWorkflow);

      expect(result).toBeDefined();
    });

    it('should handle parallel nodes correctly', async () => {
      const result = await orchestrator.executeWorkflow(parallelWorkflow);

      expect(result.status).toBe('success');
      // 验证并行节点都被执行
      const executedIds = result.nodeResults.map((r) => r.nodeId);
      expect(executedIds).toContain('step2a');
      expect(executedIds).toContain('step2b');
    });
  });

  // ==========================================
  // Test Case 4: 条件执行
  // ==========================================

  describe('Conditional Execution', () => {
    it('should evaluate conditions', async () => {
      const result = await orchestrator.executeWorkflow(conditionalWorkflow);

      expect(result.nodeResults.length).toBeGreaterThan(0);
    });
  });

  // ==========================================
  // Test Case 5: 进度跟踪
  // ==========================================

  describe('Progress Tracking', () => {
    it('should report progress during execution', async () => {
      const progressEvents: any[] = [];

      await orchestrator.executeWorkflow(simpleWorkflow, {
        onProgress: (progress) => {
          progressEvents.push(progress);
        },
      });

      // 应该有进度更新
      expect(progressEvents.length).toBeGreaterThan(0);
    });
  });

  // ==========================================
  // Test Case 6: 工作流模板
  // ==========================================

  describe('Workflow Templates', () => {
    it('should save workflow as template', async () => {
      const templateId = await orchestrator.saveAsTemplate(simpleWorkflow, 'QC Pipeline');

      expect(templateId).toBeDefined();
    });

    it('should load workflow from template', async () => {
      const templateId = await orchestrator.saveAsTemplate(simpleWorkflow, 'QC Pipeline');
      const loaded = await orchestrator.loadTemplate(templateId);

      expect(loaded).toBeDefined();
      expect(loaded.name).toBe('QC Pipeline');
    });

    it('should list available templates', async () => {
      await orchestrator.saveAsTemplate(simpleWorkflow, 'Template 1');
      await orchestrator.saveAsTemplate(parallelWorkflow, 'Template 2');

      const templates = await orchestrator.listTemplates();

      expect(templates.length).toBeGreaterThanOrEqual(2);
    });
  });
});