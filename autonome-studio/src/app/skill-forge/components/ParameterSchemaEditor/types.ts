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
 */
export function parametersToJsonSchema(params: ParameterDefinition[]): JsonSchema {
  const properties: JsonSchema['properties'] = {};
  const required: string[] = [];

  for (const param of params) {
    const prop: any = {
      type: param.type === 'FilePath' || param.type === 'DirectoryPath' ? 'string' : param.type,
      description: param.description,
    };

    // 添加格式标记
    if (param.type === 'FilePath') {
      prop.format = 'file-path';
    } else if (param.type === 'DirectoryPath') {
      prop.format = 'directory-path';
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

    if (param.required) {
      required.push(param.name);
    }
  }

  return {
    type: 'object',
    properties,
    required: required.length > 0 ? required : undefined,
  };
}

/**
 * 从 JSON Schema 解析参数定义列表
 */
export function jsonSchemaToParameters(schema: JsonSchema): ParameterDefinition[] {
  if (!schema || !schema.properties) return [];

  const params: ParameterDefinition[] = [];
  const requiredSet = new Set(schema.required || []);

  for (const [name, prop] of Object.entries(schema.properties)) {
    const param: ParameterDefinition = {
      name,
      type: prop.format === 'file-path' ? 'FilePath' :
            prop.format === 'directory-path' ? 'DirectoryPath' :
            (prop.type as ParameterType) || 'string',
      description: prop.description || '',
      required: requiredSet.has(name),
      defaultValue: prop.default,
      min: prop.minimum,
      max: prop.maximum,
      pattern: prop.pattern,
    };

    // 枚举值
    if (prop.enum && Array.isArray(prop.enum)) {
      param.type = 'enum';
      param.enumValues = prop.enum;
    }

    // 数组类型
    if (prop.type === 'array') {
      param.type = 'array';
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