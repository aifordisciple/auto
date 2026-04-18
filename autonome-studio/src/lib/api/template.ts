// ==========================================
// SKILL Templates 模板 API
// ==========================================

import { fetchAPI } from '../api';

export interface SkillTemplate {
  id: number;
  template_id: string;
  name: string;
  description: string | null;
  template_type: 'Logical_Blueprint' | 'Python_env' | 'R_env' | 'Nextflow';
  script_template: string | null;
  parameters_schema: Record<string, any>;
  expert_knowledge: string | null;
  category: string;
  category_name: string;
  subcategory: string | null;
  subcategory_name: string | null;
  tags: string[];
  source_skill_id: string | null;
  is_official: boolean;
  usage_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface InstantiateRequest {
  skill_name?: string;
  customizations?: Record<string, any>;
}

export interface InstantiateResult {
  skill_id: string;
  name: string;
  description: string;
  executor_type: string;
  script_code: string | null;
  nextflow_code?: string | null;
  parameters_schema: Record<string, any>;
  expert_knowledge: string | null;
  dependencies: string[];
}

export const templateApi = {
  /**
   * 获取所有模板
   */
  listTemplates: async (): Promise<SkillTemplate[]> => {
    const response = await fetchAPI('/api/templates/');
    return response;
  },

  /**
   * 获取单个模板详情
   */
  getTemplate: async (templateId: string): Promise<{ status: string; data: SkillTemplate }> => {
    const response = await fetchAPI(`/api/templates/${templateId}`);
    return response;
  },

  /**
   * 从模板实例化技能
   */
  instantiateTemplate: async (templateId: string, request: InstantiateRequest): Promise<InstantiateResult> => {
    const response = await fetchAPI(`/api/templates/${templateId}/instantiate`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
    return response;
  },

  /**
   * 从现有技能提取模板
   */
  extractTemplate: async (skillId: string, templateName: string, templateId?: string, saveToDb: boolean = false): Promise<any> => {
    const params = new URLSearchParams({
      skill_id: skillId,
      template_name: templateName,
      save_to_db: String(saveToDb)
    });
    if (templateId) {
      params.append('template_id', templateId);
    }
    const response = await fetchAPI(`/api/templates/extract?${params.toString()}`, {
      method: 'POST',
    });
    return response;
  },

  /**
   * 获取模板分类统计
   */
  getCategories: async (): Promise<{ status: string; data: any[] }> => {
    const response = await fetchAPI('/api/templates/categories/list');
    return response;
  }
};
