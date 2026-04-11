/**
 * Parameter Schema 类型定义
 */

// 支持的参数类型
export type ParameterType =
  | 'string'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'FilePath'
  | 'DirectoryPath'
  | 'enum'
  | 'array';

// 单个参数定义
export interface ParameterDefinition {
  name: string;
  type: ParameterType;
  description: string;
  required: boolean;
  defaultValue?: string | number | boolean | string[];
  enumValues?: string[]; // 仅用于 enum 类型
  min?: number;
  max?: number;
  pattern?: string; // 正则表达式，用于 string 类型
}

// JSON Schema 格式
export interface JsonSchema {
  type: 'object';
  properties: Record<string, {
    type: string;
    description?: string;
    default?: any;
    enum?: string[];
    minimum?: number;
    maximum?: number;
    pattern?: string;
    items?: any;
    format?: string; // 添加 format 字段用于 FilePath/DirectoryPath
  }>;
  required?: string[];
  // 自定义扩展字段：保存参数顺序
  // JSON Schema 的 properties 对象本身不保证顺序，因此需要显式保存参数名列表
  'x-parameter-order'?: string[];
}

// 参数类型配置
export const PARAMETER_TYPES: Array<{
  value: ParameterType;
  label: string;
  description: string;
  icon: string;
}> = [
  { value: 'string', label: '文本', description: '字符串类型', icon: 'Aa' },
  { value: 'number', label: '数字', description: '浮点数类型', icon: '#' },
  { value: 'integer', label: '整数', description: '整数类型', icon: '1' },
  { value: 'boolean', label: '布尔', description: 'true/false', icon: '?' },
  { value: 'FilePath', label: '文件路径', description: '文件路径类型', icon: '📄' },
  { value: 'DirectoryPath', label: '目录路径', description: '目录路径类型', icon: '📁' },
  { value: 'enum', label: '枚举', description: '预定义选项', icon: '📋' },
  { value: 'array', label: '数组', description: '字符串列表', icon: '[]' },
];

/**
 * 将参数定义列表转换为 JSON Schema
 *
 * 重要：使用 x-parameter-order 字段保存参数顺序，确保重新加载时顺序一致
 * JSON Schema 的 properties 对象在现代 JS 引擎中虽然按插入顺序遍历，
 * 但为了跨环境兼容性和明确性，显式保存参数名顺序列表
 */
export function parametersToJsonSchema(params: ParameterDefinition[]): JsonSchema {
  const properties: JsonSchema['properties'] = {};
  const required: string[] = [];
  // 保存参数顺序列表
  const parameterOrder: string[] = [];

  for (const param of params) {
    const prop: any = {
      type: param.type === 'FilePath' || param.type === 'DirectoryPath' ? 'string' : param.type,
      description: param.description,
    };

    // 添加格式标记
    // 统一使用无连字符格式：filepath / directorypath
    // 这样与后端大多数代码保持一致
    if (param.type === 'FilePath') {
      prop.format = 'filepath';
    } else if (param.type === 'DirectoryPath') {
      prop.format = 'directorypath';
    }

    // 默认值
    if (param.defaultValue !== undefined && param.defaultValue !== '') {
      prop.default = param.defaultValue;
    }

    // 枚举值
    if (param.type === 'enum' && param.enumValues && param.enumValues.length > 0) {
      prop.enum = param.enumValues;
    }

    // 数值约束
    if (param.type === 'number' || param.type === 'integer') {
      if (param.min !== undefined) prop.minimum = param.min;
      if (param.max !== undefined) prop.maximum = param.max;
    }

    // 字符串正则
    if (param.type === 'string' && param.pattern) {
      prop.pattern = param.pattern;
    }

    // 数组类型
    if (param.type === 'array') {
      prop.items = { type: 'string' };
    }

    properties[param.name] = prop;
    // 记录参数顺序
    parameterOrder.push(param.name);

    if (param.required) {
      required.push(param.name);
    }
  }

  return {
    type: 'object',
    properties,
    required: required.length > 0 ? required : undefined,
    // 显式保存参数顺序，确保重新加载时顺序一致
    'x-parameter-order': parameterOrder,
  };
}

/**
 * 从 JSON Schema 解析参数定义列表
 *
 * 支持多种 format 写法：
 * - 'file-path' / 'filepath' / 'FilePath' → FilePath 类型
 * - 'directory-path' / 'directorypath' / 'DirectoryPath' → DirectoryPath 类型
 *
 * 参数顺序恢复逻辑：
 * 1. 如果存在 x-parameter-order 字段，按该顺序恢复参数
 * 2. 否则按 Object.entries 遍历顺序（兼容旧数据）
 */
export function jsonSchemaToParameters(schema: JsonSchema): ParameterDefinition[] {
  if (!schema || !schema.properties) return [];

  const params: ParameterDefinition[] = [];
  const requiredSet = new Set(schema.required || []);

  // ==========================================
  // 确定参数顺序：优先使用 x-parameter-order，否则使用 Object.entries 顺序
  // ==========================================
  const parameterOrder = schema['x-parameter-order'];
  let entries: [string, any][];

  if (parameterOrder && Array.isArray(parameterOrder)) {
    // 按 x-parameter-order 定义的顺序遍历
    entries = parameterOrder
      .filter(name => schema.properties[name]) // 过滤掉不存在的参数
      .map(name => [name, schema.properties[name]]);
  } else {
    // 兼容旧数据：使用 Object.entries 顺序
    entries = Object.entries(schema.properties);
  }

  for (const [name, prop] of entries) {
    // ==========================================
    // 根据类型和 format 判断参数类型
    // ==========================================
    let paramType: ParameterType;

    const formatLower = (prop.format || '').toLowerCase().replace(/-/g, '');

    if (formatLower === 'filepath' || formatLower === 'file-path') {
      paramType = 'FilePath';
    } else if (formatLower === 'directorypath' || formatLower === 'directory-path') {
      paramType = 'DirectoryPath';
    } else if (prop.enum && Array.isArray(prop.enum)) {
      paramType = 'enum';
    } else if (prop.type === 'array') {
      paramType = 'array';
    } else if (prop.type === 'boolean') {
      paramType = 'boolean';
    } else if (prop.type === 'number') {
      paramType = 'number';
    } else if (prop.type === 'integer') {
      paramType = 'integer';
    } else {
      paramType = 'string';
    }

    const param: ParameterDefinition = {
      name,
      type: paramType,
      description: prop.description || '',
      required: requiredSet.has(name),
      defaultValue: prop.default,
      min: prop.minimum,
      max: prop.maximum,
      pattern: prop.pattern,
    };

    // 枚举值
    if (paramType === 'enum' && prop.enum && Array.isArray(prop.enum)) {
      param.enumValues = prop.enum;
    }

    params.push(param);
  }

  return params;
}

/**
 * 验证参数名是否有效
 */
export function validateParameterName(name: string): { valid: boolean; error?: string } {
  if (!name) {
    return { valid: false, error: '参数名不能为空' };
  }
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(name)) {
    return { valid: false, error: '只能包含字母、数字、下划线，且不能以数字开头' };
  }
  return { valid: true };
}