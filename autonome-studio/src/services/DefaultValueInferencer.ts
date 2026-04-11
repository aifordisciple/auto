/**
 * 智能默认值推断服务
 *
 * P1 效率提升：
 * - 根据历史偏好推断默认值
 * - 根据项目数据类型推断
 * - 支持批量推断
 */

// ==========================================
// 类型定义
// ==========================================

export interface InferContext {
  project_id: string;
  skill_id: string;
  user_id: number;
  data_type?: string;
}

export interface InferParameter {
  name: string;
  type: string;
  default?: any;
  description?: string;
}

interface PreferenceRecord {
  user_id: number;
  skill_id: string;
  param_name: string;
  value: any;
  timestamp: number;
}

// ==========================================
// 常量
// ==========================================

const PREFERENCE_STORAGE_KEY = 'autonome_param_preferences';
const PROJECT_DATA_TYPE_KEY = 'autonome_project_data_types';

// ==========================================
// 服务类
// ==========================================

export class DefaultValueInferencer {
  private preferences: Map<string, PreferenceRecord> = new Map();
  private projectDataTypes: Map<string, string> = new Map();

  constructor() {
    this.loadFromStorage();
  }

  // ==========================================
  // 推断默认值
  // ==========================================

  async infer(
    context: InferContext | null,
    parameter: InferParameter
  ): Promise<any> {
    // 边界情况处理
    if (!context || !parameter.name) {
      return parameter.default;
    }

    // 1. 检查历史偏好
    const historyValue = this.getHistoryPreference(
      context.user_id,
      context.skill_id,
      parameter.name
    );
    if (historyValue !== undefined) {
      return historyValue;
    }

    // 2. 检查数据类型相关推断
    const dataType = this.projectDataTypes.get(context.project_id);
    if (dataType) {
      const dataBasedValue = this.inferFromDataType(
        dataType,
        parameter,
        context
      );
      if (dataBasedValue !== undefined) {
        return dataBasedValue;
      }
    }

    // 3. 返回默认值
    return parameter.default;
  }

  // ==========================================
  // 批量推断
  // ==========================================

  async inferBatch(
    context: InferContext,
    parameters: InferParameter[]
  ): Promise<Record<string, any>> {
    const result: Record<string, any> = {};

    for (const param of parameters) {
      result[param.name] = await this.infer(context, param);
    }

    return result;
  }

  // ==========================================
  // 记录偏好
  // ==========================================

  async recordPreference(
    context: InferContext,
    paramName: string,
    value: any
  ): Promise<void> {
    const key = this.getPreferenceKey(context.user_id, context.skill_id, paramName);

    const record: PreferenceRecord = {
      user_id: context.user_id,
      skill_id: context.skill_id,
      param_name: paramName,
      value,
      timestamp: Date.now(),
    };

    this.preferences.set(key, record);
    this.saveToStorage();
  }

  // ==========================================
  // 设置项目数据类型
  // ==========================================

  setProjectDataType(projectId: string, dataType: string): void {
    this.projectDataTypes.set(projectId, dataType);
    this.saveProjectDataTypes();
  }

  // ==========================================
  // 清除所有偏好
  // ==========================================

  clearAllPreferences(): void {
    this.preferences.clear();
    this.projectDataTypes.clear();

    try {
      const storage = typeof localStorage !== 'undefined' ? localStorage : null;
      if (storage) {
        storage.removeItem(PREFERENCE_STORAGE_KEY);
        storage.removeItem(PROJECT_DATA_TYPE_KEY);
      }
    } catch (error) {
      console.error('[DefaultValueInferencer] 清除偏好失败:', error);
    }
  }

  // ==========================================
  // 私有方法
  // ==========================================

  private getPreferenceKey(
    userId: number,
    skillId: string,
    paramName: string
  ): string {
    return `${userId}_${skillId}_${paramName}`;
  }

  private getHistoryPreference(
    userId: number,
    skillId: string,
    paramName: string
  ): any | undefined {
    const key = this.getPreferenceKey(userId, skillId, paramName);
    const record = this.preferences.get(key);
    return record?.value;
  }

  private inferFromDataType(
    dataType: string,
    parameter: InferParameter,
    context: InferContext
  ): any | undefined {
    // 根据数据类型推断特定参数
    // 这里可以根据实际业务逻辑扩展

    if (dataType === 'single-cell' && parameter.name === 'resolution') {
      return 0.8; // 单细胞数据通常使用更高的分辨率
    }

    if (dataType === 'rna-seq' && parameter.name === 'output_dir') {
      return 'rna_seq_results';
    }

    if (dataType === 'atac-seq' && parameter.name === 'output_dir') {
      return 'atac_seq_results';
    }

    return undefined;
  }

  private loadFromStorage(): void {
    try {
      const storage = typeof localStorage !== 'undefined' ? localStorage : null;
      if (!storage) return;

      // 加载偏好记录
      const storedPreferences = storage.getItem(PREFERENCE_STORAGE_KEY);
      if (storedPreferences) {
        const data = JSON.parse(storedPreferences) as PreferenceRecord[];
        for (const record of data) {
          const key = this.getPreferenceKey(
            record.user_id,
            record.skill_id,
            record.param_name
          );
          this.preferences.set(key, record);
        }
      }

      // 加载项目数据类型
      const storedDataTypes = storage.getItem(PROJECT_DATA_TYPE_KEY);
      if (storedDataTypes) {
        const data = JSON.parse(storedDataTypes) as Record<string, string>;
        for (const [projectId, dataType] of Object.entries(data)) {
          this.projectDataTypes.set(projectId, dataType);
        }
      }
    } catch (error) {
      console.error('[DefaultValueInferencer] 加载偏好失败:', error);
    }
  }

  private saveToStorage(): void {
    try {
      const storage = typeof localStorage !== 'undefined' ? localStorage : null;
      if (!storage) return;

      const data = Array.from(this.preferences.values());
      storage.setItem(PREFERENCE_STORAGE_KEY, JSON.stringify(data));
    } catch (error) {
      console.error('[DefaultValueInferencer] 保存偏好失败:', error);
    }
  }

  private saveProjectDataTypes(): void {
    try {
      const storage = typeof localStorage !== 'undefined' ? localStorage : null;
      if (!storage) return;

      const data: Record<string, string> = {};
      for (const [projectId, dataType] of this.projectDataTypes) {
        data[projectId] = dataType;
      }
      storage.setItem(PROJECT_DATA_TYPE_KEY, JSON.stringify(data));
    } catch (error) {
      console.error('[DefaultValueInferencer] 保存项目数据类型失败:', error);
    }
  }
}

// ==========================================
// 单例和便捷函数
// ==========================================

let instance: DefaultValueInferencer | null = null;

export function getDefaultValueInferencer(): DefaultValueInferencer {
  if (!instance) {
    instance = new DefaultValueInferencer();
  }
  return instance;
}

export async function inferDefaultValue(
  context: InferContext,
  parameter: InferParameter
): Promise<any> {
  return getDefaultValueInferencer().infer(context, parameter);
}

export default DefaultValueInferencer;