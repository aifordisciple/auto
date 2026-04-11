/**
 * 参数模板服务
 *
 * P1 效率提升：
 * - 保存常用参数组合为模板
 * - 一键应用模板
 * - 模板搜索和分类
 */

// ==========================================
// 类型定义
// ==========================================

export interface ParameterTemplate {
  id: string;                              // 模板ID (tpl_xxx)
  name: string;                            // 模板名称
  skill_id: string;                        // 关联技能ID
  parameters: Record<string, unknown>;     // 参数配置
  tags: string[];                          // 标签（用于搜索）
  created_at: number;                      // 创建时间戳
  updated_at?: number;                     // 更新时间戳
  last_used_at?: number;                   // 最后使用时间戳
}

export interface TemplateCreateInput {
  name: string;
  skill_id: string;
  parameters: Record<string, unknown>;
  tags?: string[];
}

export interface TemplateUpdateInput {
  name?: string;
  parameters?: Record<string, unknown>;
  tags?: string[];
}

// ==========================================
// 常量
// ==========================================

const STORAGE_KEY = 'autonome_parameter_templates';
const ID_PREFIX = 'tpl_';

// ==========================================
// 服务类
// ==========================================

export class ParameterTemplateService {
  private templates: Map<string, ParameterTemplate> = new Map();

  constructor() {
    this.loadFromStorage();
  }

  // ==========================================
  // 创建模板
  // ==========================================

  async createTemplate(input: TemplateCreateInput): Promise<ParameterTemplate> {
    // 验证必填字段
    if (!input.name || !input.name.trim()) {
      throw new Error('模板名称不能为空');
    }
    if (!input.skill_id) {
      throw new Error('技能ID不能为空');
    }

    // 生成模板
    const template: ParameterTemplate = {
      id: this.generateId(),
      name: input.name.trim(),
      skill_id: input.skill_id,
      parameters: input.parameters || {},
      tags: input.tags || [],
      created_at: Date.now(),
    };

    // 保存到内存和存储
    this.templates.set(template.id, template);
    this.saveToStorage();

    return template;
  }

  // ==========================================
  // 获取模板列表
  // ==========================================

  async getTemplates(skillId: string): Promise<ParameterTemplate[]> {
    const result: ParameterTemplate[] = [];

    for (const template of this.templates.values()) {
      if (template.skill_id === skillId) {
        result.push(template);
      }
    }

    // 按创建时间倒序排列
    return result.sort((a, b) => b.created_at - a.created_at);
  }

  // ==========================================
  // 应用模板
  // ==========================================

  async applyTemplate(templateId: string): Promise<Record<string, unknown>> {
    const template = this.templates.get(templateId);

    if (!template) {
      throw new Error(`模板不存在: ${templateId}`);
    }

    // 更新最后使用时间
    template.last_used_at = Date.now();
    this.saveToStorage();

    return { ...template.parameters };
  }

  // ==========================================
  // 删除模板
  // ==========================================

  async deleteTemplate(templateId: string): Promise<void> {
    if (!this.templates.has(templateId)) {
      throw new Error(`模板不存在: ${templateId}`);
    }

    this.templates.delete(templateId);
    this.saveToStorage();
  }

  // ==========================================
  // 更新模板
  // ==========================================

  async updateTemplate(
    templateId: string,
    input: TemplateUpdateInput
  ): Promise<ParameterTemplate> {
    const template = this.templates.get(templateId);

    if (!template) {
      throw new Error(`模板不存在: ${templateId}`);
    }

    // 更新字段
    if (input.name) {
      template.name = input.name.trim();
    }
    if (input.parameters) {
      template.parameters = { ...input.parameters };
    }
    if (input.tags) {
      template.tags = [...input.tags];
    }

    template.updated_at = Date.now();

    this.saveToStorage();

    return { ...template };
  }

  // ==========================================
  // 搜索模板
  // ==========================================

  async searchTemplates(keyword: string): Promise<ParameterTemplate[]> {
    const lowerKeyword = keyword.toLowerCase();
    const result: ParameterTemplate[] = [];

    for (const template of this.templates.values()) {
      // 搜索名称
      if (template.name.toLowerCase().includes(lowerKeyword)) {
        result.push(template);
        continue;
      }

      // 搜索标签
      for (const tag of template.tags) {
        if (tag.toLowerCase().includes(lowerKeyword)) {
          result.push(template);
          break;
        }
      }
    }

    return result;
  }

  // ==========================================
  // 获取最近使用的模板
  // ==========================================

  async getRecentTemplates(limit: number = 5): Promise<ParameterTemplate[]> {
    const templatesWithUsage = Array.from(this.templates.values())
      .filter(t => t.last_used_at)
      .sort((a, b) => (b.last_used_at || 0) - (a.last_used_at || 0));

    return templatesWithUsage.slice(0, limit);
  }

  // ==========================================
  // 私有方法
  // ==========================================

  private generateId(): string {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 8);
    return `${ID_PREFIX}${timestamp}_${random}`;
  }

  private loadFromStorage(): void {
    try {
      // 使用全局 localStorage（在浏览器环境或 jsdom 测试环境）
      const storage = typeof localStorage !== 'undefined' ? localStorage : null;
      if (!storage) return;

      const stored = storage.getItem(STORAGE_KEY);
      if (stored) {
        const data = JSON.parse(stored) as ParameterTemplate[];
        for (const template of data) {
          this.templates.set(template.id, template);
        }
      }
    } catch (error) {
      console.error('[ParameterTemplateService] 加载模板失败:', error);
    }
  }

  private saveToStorage(): void {
    try {
      // 使用全局 localStorage
      const storage = typeof localStorage !== 'undefined' ? localStorage : null;
      if (!storage) return;

      const data = Array.from(this.templates.values());
      storage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (error) {
      console.error('[ParameterTemplateService] 保存模板失败:', error);
    }
  }
}

// ==========================================
// 单例导出
// ==========================================

let instance: ParameterTemplateService | null = null;

export function getParameterTemplateService(): ParameterTemplateService {
  if (!instance) {
    instance = new ParameterTemplateService();
  }
  return instance;
}

export default ParameterTemplateService;