/**
 * 参数表单智能分组工具
 *
 * 功能：
 * 1. 将技能参数按逻辑分组（输入数据、分析参数、输出设置、高级选项）
 * 2. 智能推断参数所属分组
 * 3. 标记必填参数
 * 4. 提取默认值
 * 5. 设置分组折叠状态
 */

// ==========================================
// 类型定义
// ==========================================

// 使用宽松的 schema 类型以兼容 SkillSchema
interface LooseJSONSchema {
  type?: string;
  properties?: Record<string, {
    type?: string;
    description?: string;
    default?: unknown;
    enum?: (string | number)[];
    minimum?: number;
    maximum?: number;
    format?: string;
  }>;
  required?: string[];
  'x-parameter-order'?: string[];
}

export interface ParameterInfo {
  key: string;
  type: string;
  format?: string;
  description?: string;
  required: boolean;
  defaultValue?: unknown;
  enum?: (string | number)[];
  minimum?: number;
  maximum?: number;
}

export interface ParameterGroup {
  name: string;
  nameEn?: string;
  parameters: ParameterInfo[];
  defaultCollapsed: boolean;
  icon?: string;
}

// ==========================================
// 参数分组关键词映射
// ==========================================

const GROUP_KEYWORDS: Record<string, string[]> = {
  输入数据: [
    'sample', 'input', 'data', 'file', 'path', 'dir', 'directory',
    'reference', 'genome', 'fastq', 'bam', 'vcf', 'matrix', 'table',
    'upload', 'source', 'read', 'raw',
    // 中文关键词
    '样本', '输入', '数据', '文件', '路径', '目录', '参考',
  ],
  分析参数: [
    'threshold', 'cutoff', 'filter', 'min', 'max', 'resolution',
    'cluster', 'dimension', 'component', 'pc', 'pca', 'tsne', 'umap',
    'normalize', 'scale', 'transform', 'log', 'fold', 'pvalue', 'fdr',
    'method', 'algorithm', 'model', 'kernel', 'distance', 'metric',
    // 中文关键词
    '阈值', '过滤', '聚类', '标准化', '方法', '参数',
  ],
  输出设置: [
    'output', 'result', 'save', 'export', 'write', 'prefix', 'suffix',
    'format', 'filename', 'outdir', 'out_dir', 'output_dir',
    // 中文关键词
    '输出', '结果', '保存', '导出', '格式', '前缀',
  ],
  高级选项: [
    'seed', 'random', 'n_jobs', 'nthread', 'thread', 'parallel', 'cpu',
    'memory', 'mem', 'timeout', 'batch', 'chunk', 'cache', 'gpu',
    'verbose', 'debug', 'log', 'dry_run', 'dry-run', 'test',
    // 中文关键词
    '种子', '并行', '线程', '内存', '超时', '缓存', '调试',
  ],
};

// 默认分组配置
const DEFAULT_GROUPS: Omit<ParameterGroup, 'parameters'>[] = [
  { name: '输入数据', nameEn: 'Input', defaultCollapsed: false, icon: 'database' },
  { name: '分析参数', nameEn: 'Analysis', defaultCollapsed: false, icon: 'sliders' },
  { name: '输出设置', nameEn: 'Output', defaultCollapsed: false, icon: 'download' },
  { name: '高级选项', nameEn: 'Advanced', defaultCollapsed: true, icon: 'settings' },
];

// ==========================================
// 主函数：参数分组
// ==========================================

/**
 * 将 JSON Schema 参数分组
 *
 * @param schema 技能参数 Schema
 * @returns 分组后的参数列表
 */
export function groupParameters(schema: LooseJSONSchema): ParameterGroup[] {
  if (!schema || !schema.properties) {
    return [];
  }

  const properties = schema.properties;
  const required = new Set(schema.required || []);

  // 初始化分组
  const groupMap = new Map<string, ParameterGroup>();
  for (const group of DEFAULT_GROUPS) {
    groupMap.set(group.name, {
      ...group,
      parameters: [],
    });
  }

  // 参数分组
  for (const [key, prop] of Object.entries(properties)) {
    if (typeof prop !== 'object' || prop === null) continue;

    const paramInfo: ParameterInfo = {
      key,
      type: inferType(prop),
      format: prop.format,
      description: prop.description,
      required: required.has(key),
      defaultValue: prop.default,
      enum: prop.enum as (string | number)[] | undefined,
      minimum: prop.minimum,
      maximum: prop.maximum,
    };

    // 推断分组
    const groupName = inferParameterGroup(key, prop);
    const group = groupMap.get(groupName);

    if (group) {
      group.parameters.push(paramInfo);
    } else {
      // 未知分组，放入分析参数
      groupMap.get('分析参数')!.parameters.push(paramInfo);
    }
  }

  // 过滤空分组，保留有参数的分组
  const result = Array.from(groupMap.values()).filter(g => g.parameters.length > 0);

  // 对参数排序：必填参数在前，可选参数在后
  for (const group of result) {
    group.parameters.sort((a, b) => {
      if (a.required && !b.required) return -1;
      if (!a.required && b.required) return 1;
      return a.key.localeCompare(b.key);
    });
  }

  return result;
}

// ==========================================
// 分组推断函数
// ==========================================

/**
 * 推断参数所属分组
 *
 * @param key 参数名
 * @param prop 参数属性
 * @returns 分组名称
 */
export function inferParameterGroup(key: string, prop: Record<string, unknown>): string {
  const keyLower = key.toLowerCase();
  const keyWords = keyLower.split(/[_-]/);

  // 收集所有关键词并按长度降序排列（优先匹配更长的关键词）
  // 这样 "output_dir" 会匹配 "output" 而不是先匹配 "dir"
  const allKeywordsWithGroup: Array<{ keyword: string; groupName: string; priority: number }> = [];
  for (const [groupName, keywords] of Object.entries(GROUP_KEYWORDS)) {
    for (const keyword of keywords) {
      allKeywordsWithGroup.push({
        keyword: keyword.toLowerCase(),
        groupName,
        priority: keyword.length  // 长度越长优先级越高
      });
    }
  }
  // 按关键词长度降序排序
  allKeywordsWithGroup.sort((a, b) => b.priority - a.priority);

  // 检查关键词
  for (const { keyword, groupName } of allKeywordsWithGroup) {
    // 完全匹配
    if (keyLower === keyword) {
      return groupName;
    }

    // 包含匹配（优先匹配长关键词）
    if (keyLower.includes(keyword)) {
      return groupName;
    }

    // 分词匹配
    for (const word of keyWords) {
      if (word === keyword) {
        return groupName;
      }
    }
  }

  // 默认放入分析参数
  return '分析参数';
}

// ==========================================
// 辅助函数
// ==========================================

/**
 * 推断参数类型
 */
function inferType(prop: Record<string, unknown>): string {
  if (prop.type) {
    if (Array.isArray(prop.type)) {
      return prop.type[0] as string;
    }
    return prop.type as string;
  }

  // 根据 format 推断
  if (prop.format === 'date' || prop.format === 'date-time') {
    return 'string';
  }

  // 根据 enum 推断
  if (prop.enum) {
    return 'enum';
  }

  // 默认
  return 'string';
}

/**
 * 获取分组的图标名称
 */
export function getGroupIcon(groupName: string): string {
  const iconMap: Record<string, string> = {
    输入数据: 'database',
    分析参数: 'sliders',
    输出设置: 'download',
    高级选项: 'settings',
  };

  return iconMap[groupName] || 'box';
}

/**
 * 获取分组的描述
 */
export function getGroupDescription(groupName: string): string {
  const descMap: Record<string, string> = {
    输入数据: '配置输入数据文件和路径',
    分析参数: '调整分析算法参数',
    输出设置: '设置输出文件和格式',
    高级选项: '高级配置选项（通常使用默认值）',
  };

  return descMap[groupName] || '';
}

/**
 * 检查分组是否有必填参数
 */
export function hasRequiredParams(group: ParameterGroup): boolean {
  return group.parameters.some(p => p.required);
}

/**
 * 获取分组的必填参数数量
 */
export function countRequiredParams(group: ParameterGroup): number {
  return group.parameters.filter(p => p.required).length;
}