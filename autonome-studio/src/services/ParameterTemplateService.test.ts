/**
 * 参数模板服务测试
 *
 * User Journey:
 * As a user, I want to save and reuse parameter configurations,
 * so that I don't have to re-enter the same parameters every time.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  ParameterTemplateService,
  ParameterTemplate,
  TemplateCreateInput,
} from './ParameterTemplateService';

// ==========================================
// 测试数据
// ==========================================

const mockTemplate: TemplateCreateInput = {
  name: '标准RNA-seq分析',
  skill_id: 'rnaseq_basic_01',
  parameters: {
    min_genes: 200,
    min_cells: 3,
    resolution: 0.5,
    output_format: 'pdf',
  },
  tags: ['RNA-seq', '标准流程'],
};

const mockTemplate2: TemplateCreateInput = {
  name: '高分辨率分析',
  skill_id: 'rnaseq_basic_01',
  parameters: {
    min_genes: 100,
    min_cells: 1,
    resolution: 1.0,
    output_format: 'png',
  },
  tags: ['RNA-seq', '高分辨率'],
};

// ==========================================
// Mock localStorage
// ==========================================

// 创建 localStorage mock
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

// 在全局设置 localStorage mock
const localStorageMock = createLocalStorageMock();
(global as any).localStorage = localStorageMock;

// ==========================================
// Test Suite: 参数模板服务
// ==========================================

describe('ParameterTemplateService', () => {
  let service: ParameterTemplateService;

  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
    service = new ParameterTemplateService();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ==========================================
  // Test Case 1: 创建模板
  // ==========================================

  describe('createTemplate', () => {
    it('should create a new template with generated ID', async () => {
      const template = await service.createTemplate(mockTemplate);

      expect(template.id).toBeDefined();
      expect(template.id).toMatch(/^tpl_/);
      expect(template.name).toBe(mockTemplate.name);
      expect(template.skill_id).toBe(mockTemplate.skill_id);
      expect(template.parameters).toEqual(mockTemplate.parameters);
      expect(template.created_at).toBeDefined();
    });

    it('should save template to localStorage', async () => {
      await service.createTemplate(mockTemplate);

      expect(localStorageMock.setItem).toHaveBeenCalled();
      const savedKey = localStorageMock.setItem.mock.calls[0][0];
      expect(savedKey).toContain('parameter_templates');
    });

    it('should validate required fields', async () => {
      const invalidInput = {
        name: '',
        skill_id: 'skill_01',
        parameters: {},
      };

      await expect(service.createTemplate(invalidInput as any)).rejects.toThrow();
    });
  });

  // ==========================================
  // Test Case 2: 获取模板列表
  // ==========================================

  describe('getTemplates', () => {
    it('should return empty array when no templates exist', async () => {
      const templates = await service.getTemplates('skill_01');

      expect(templates).toEqual([]);
    });

    it('should return templates for specific skill', async () => {
      await service.createTemplate(mockTemplate);
      await service.createTemplate(mockTemplate2);

      const templates = await service.getTemplates('rnaseq_basic_01');

      expect(templates.length).toBe(2);
      expect(templates[0].skill_id).toBe('rnaseq_basic_01');
    });

    it('should not return templates for other skills', async () => {
      await service.createTemplate(mockTemplate);

      const templates = await service.getTemplates('other_skill');

      expect(templates).toEqual([]);
    });
  });

  // ==========================================
  // Test Case 3: 应用模板
  // ==========================================

  describe('applyTemplate', () => {
    it('should return template parameters', async () => {
      const created = await service.createTemplate(mockTemplate);
      const params = await service.applyTemplate(created.id);

      expect(params).toEqual(mockTemplate.parameters);
    });

    it('should throw error for non-existent template', async () => {
      await expect(service.applyTemplate('tpl_nonexistent')).rejects.toThrow();
    });

    it('should update last_used_at timestamp', async () => {
      const created = await service.createTemplate(mockTemplate);
      await service.applyTemplate(created.id);

      const templates = await service.getTemplates('rnaseq_basic_01');
      expect(templates[0].last_used_at).toBeDefined();
    });
  });

  // ==========================================
  // Test Case 4: 删除模板
  // ==========================================

  describe('deleteTemplate', () => {
    it('should remove template from storage', async () => {
      const created = await service.createTemplate(mockTemplate);
      await service.deleteTemplate(created.id);

      const templates = await service.getTemplates('rnaseq_basic_01');
      expect(templates).toEqual([]);
    });

    it('should throw error for non-existent template', async () => {
      await expect(service.deleteTemplate('tpl_nonexistent')).rejects.toThrow();
    });
  });

  // ==========================================
  // Test Case 5: 更新模板
  // ==========================================

  describe('updateTemplate', () => {
    it('should update template name and parameters', async () => {
      const created = await service.createTemplate(mockTemplate);

      const updated = await service.updateTemplate(created.id, {
        name: '更新后的名称',
        parameters: {
          ...mockTemplate.parameters,
          resolution: 0.8,
        },
      });

      expect(updated.name).toBe('更新后的名称');
      expect(updated.parameters.resolution).toBe(0.8);
    });

    it('should preserve created_at timestamp', async () => {
      const created = await service.createTemplate(mockTemplate);

      const updated = await service.updateTemplate(created.id, {
        name: '更新后的名称',
      });

      expect(updated.created_at).toBe(created.created_at);
    });
  });

  // ==========================================
  // Test Case 6: 模板搜索
  // ==========================================

  describe('searchTemplates', () => {
    beforeEach(async () => {
      await service.createTemplate(mockTemplate);
      await service.createTemplate(mockTemplate2);
    });

    it('should search by name', async () => {
      const results = await service.searchTemplates('标准');

      expect(results.length).toBe(1);
      expect(results[0].name).toContain('标准');
    });

    it('should search by tags', async () => {
      const results = await service.searchTemplates('高分辨率');

      expect(results.length).toBe(1);
      expect(results[0].tags).toContain('高分辨率');
    });

    it('should return empty for no matches', async () => {
      const results = await service.searchTemplates('不存在的关键词');

      expect(results).toEqual([]);
    });
  });

  // ==========================================
  // Test Case 7: 最近使用模板
  // ==========================================

  describe('getRecentTemplates', () => {
    it('should return templates sorted by last_used_at', async () => {
      const tpl1 = await service.createTemplate(mockTemplate);
      const tpl2 = await service.createTemplate(mockTemplate2);

      // 使用第二个模板
      await service.applyTemplate(tpl2.id);

      const recent = await service.getRecentTemplates(5);

      // 最近使用的应该在前面
      expect(recent[0].id).toBe(tpl2.id);
    });

    it('should limit results to specified count', async () => {
      const tpl1 = await service.createTemplate(mockTemplate);
      const tpl2 = await service.createTemplate(mockTemplate2);

      // 使用两个模板
      await service.applyTemplate(tpl1.id);
      await service.applyTemplate(tpl2.id);

      const recent = await service.getRecentTemplates(1);

      expect(recent.length).toBe(1);
    });
  });
});