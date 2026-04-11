/**
 * Sample Sheet Generator 工具函数
 *
 * 提供 TSV 解析、生成、验证等核心功能
 */

import { ColumnConfig, TableData } from './SampleTableEditor';

/**
 * 解析 TSV 内容为 TableData
 *
 * @param content TSV 格式字符串
 * @param columnConfig 列配置
 * @returns TableData 对象
 */
export function parseTsvToTableData(content: string, columnConfig: ColumnConfig[]): TableData {
  const lines = content
    .split('\n')
    .map(line => line.trim())
    .filter(line => line && !line.startsWith('#'));

  if (lines.length === 0) {
    return { columns: columnConfig, rows: [] };
  }

  // 检测是否有表头
  const firstLine = lines[0].split('\t');
  const hasHeader = firstLine[0].toLowerCase() === 'sample_name' ||
                    firstLine[0].toLowerCase() === 'name' ||
                    firstLine[0].toLowerCase() === 'sample';

  const startIndex = hasHeader ? 1 : 0;
  const rows: Record<string, string>[] = [];

  for (let i = startIndex; i < lines.length; i++) {
    const parts = lines[i].split('\t');
    const row: Record<string, string> = {};

    // 使用列配置的 key 作为列名
    columnConfig.forEach((col, idx) => {
      row[col.key] = parts[idx]?.trim() || '';
    });

    rows.push(row);
  }

  return { columns: columnConfig, rows };
}

/**
 * 将 TableData 转换为 TSV 字符串
 *
 * @param data TableData 对象
 * @returns TSV 格式字符串
 */
export function tableDataToTsv(data: TableData): string {
  const lines: string[] = [];

  // 表头
  const header = data.columns.map(c => c.key).join('\t');
  lines.push(header);

  // 数据行
  data.rows.forEach(row => {
    const rowStr = data.columns.map(col => row[col.key] || '').join('\t');
    lines.push(rowStr);
  });

  return lines.join('\n');
}

/**
 * 验证 TSV 内容的有效性
 *
 * @param content TSV 内容
 * @param skillType SKILL 类型
 * @returns 验证结果
 */
export function validateTsvContent(
  content: string,
  skillType: string
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  const lines = content
    .split('\n')
    .map(line => line.trim())
    .filter(line => line && !line.startsWith('#'));

  if (lines.length === 0) {
    return { valid: false, errors: ['文件内容为空'] };
  }

  // 检测表头
  const firstLine = lines[0].split('\t');
  const hasHeader = firstLine[0].toLowerCase() === 'sample_name' ||
                    firstLine[0].toLowerCase() === 'name' ||
                    firstLine[0].toLowerCase() === 'sample';

  const header = hasHeader ? firstLine : [];
  const dataLines = hasHeader ? lines.slice(1) : lines;

  // 获取必填列索引
  const requiredColumns = getRequiredColumns(skillType);

  // 检查必填列是否存在
  if (hasHeader) {
    requiredColumns.forEach(col => {
      if (!header.includes(col)) {
        errors.push(`缺少必填列: ${col}`);
      }
    });
  }

  // 检查数据行
  const sampleNames: string[] = [];

  dataLines.forEach((line, idx) => {
    const parts = line.split('\t');

    // 检查列数
    const expectedCols = hasHeader ? header.length : 4;
    if (parts.length < expectedCols) {
      errors.push(`第 ${idx + (hasHeader ? 2 : 1)} 行列数不足`);
    }

    // 收集样本名
    if (parts[0]) {
      sampleNames.push(parts[0]);
    }
  });

  // 检查样本名重复
  const duplicates = sampleNames.filter((name, idx) =>
    sampleNames.indexOf(name) !== idx
  );
  if (duplicates.length > 0) {
    errors.push(`样本名重复: ${[...new Set(duplicates)].join(', ')}`);
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * 获取必填列名
 */
function getRequiredColumns(skillType: string): string[] {
  if (skillType === 'fastqc') {
    return ['sample_name', 'read1_path'];
  } else if (skillType === 'singlecell') {
    return ['sample_name', 'input_path', 'input_format'];
  }
  return ['sample_name'];
}

/**
 * 从文件名推断数据格式
 */
export function inferDataFormat(filename: string): string {
  const lower = filename.toLowerCase();

  // 10x 格式通过目录名判断，这里只处理文件
  if (lower.endsWith('.h5')) return 'h5';
  if (lower.includes('_rsec_molspercell')) return 'BD';
  if (lower.endsWith('.rds')) return lower.includes('_raw') ? 'rdsraw' : 'rds';
  if (lower.endsWith('.tsv') || lower.endsWith('.csv')) return 'exp';

  return 'unknown';
}

/**
 * 从样本名推断分组
 */
export function inferGroup(sampleName: string): string {
  const lower = sampleName.toLowerCase();

  const controlKeywords = ['control', 'ctrl', 'normal', 'healthy', 'untreated', 'wildtype', 'wt'];
  const treatmentKeywords = ['treat', 'treatment', 'drug', 'tumor', 'cancer', 'disease', 'mutant', 'ko', 'kd'];

  for (const kw of controlKeywords) {
    if (lower.includes(kw)) return 'Control';
  }

  for (const kw of treatmentKeywords) {
    if (lower.includes(kw)) return 'Treat';
  }

  return '';
}

/**
 * 格式化文件大小
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

/**
 * 生成唯一样本名
 */
export function generateUniqueSampleName(baseName: string, existingNames: string[]): string {
  let name = baseName;
  let counter = 1;

  while (existingNames.includes(name)) {
    name = `${baseName}_${counter}`;
    counter++;
  }

  return name;
}

// ==========================================
// 比较组相关工具函数
// ==========================================

/**
 * 比较组数据结构
 */
export interface ComparisonGroup {
  case_group: string;      // 实验组/处理组
  control_group: string;   // 对照组
  comparison_name: string; // 比较组名称，格式：{case}_vs_{control}
}

/**
 * 比较组表数据
 */
export interface ComparisonTableData {
  comparisons: ComparisonGroup[];
}

/**
 * 对照组识别关键词（用于自动推断时排序）
 */
const CONTROL_GROUP_KEYWORDS = ['control', 'ctrl', 'normal', 'healthy', 'wildtype', 'wt', 'untreated', 'baseline', 'reference', 'ref'];

/**
 * 从分组列表自动推断比较组
 *
 * 推断规则：
 * 1. 将分组排序，control 类分组优先排在前面
 * 2. 生成所有两两组合，格式为 {later_group}_vs_{earlier_group}
 * 3. 这样确保 control 组作为对照组
 *
 * @param groups 分组名称列表
 * @returns 比较组列表
 */
export function inferComparisonGroups(groups: string[]): ComparisonGroup[] {
  if (!groups || groups.length < 2) {
    return [];
  }

  // 过滤空值并去重
  const uniqueGroups = groups
    .filter(g => g && g.trim())
    .filter((g, i, arr) => arr.indexOf(g) === i);

  if (uniqueGroups.length < 2) {
    return [];
  }

  // 将分组排序，control 类分组优先排在前面
  const sortedGroups = uniqueGroups.sort((a, b) => {
    const aIsControl = CONTROL_GROUP_KEYWORDS.some(kw => a.toLowerCase().includes(kw));
    const bIsControl = CONTROL_GROUP_KEYWORDS.some(kw => b.toLowerCase().includes(kw));

    // 包含 control 关键词的分组排前面
    if (aIsControl && !bIsControl) return -1;
    if (!aIsControl && bIsControl) return 1;

    // 同级别按字母顺序排列
    return a.localeCompare(b);
  });

  // 生成所有两两组合
  // 格式：{后组}_vs_{前组}，前组作为对照组
  const comparisons: ComparisonGroup[] = [];

  for (let i = 0; i < sortedGroups.length; i++) {
    for (let j = i + 1; j < sortedGroups.length; j++) {
      comparisons.push({
        case_group: sortedGroups[j],
        control_group: sortedGroups[i],
        comparison_name: `${sortedGroups[j]}_vs_${sortedGroups[i]}`
      });
    }
  }

  return comparisons;
}

/**
 * 验证比较组的有效性
 *
 * @param comparisons 比较组列表
 * @param availableGroups 可用的分组列表
 * @returns 验证结果
 */
export function validateComparisonGroups(
  comparisons: ComparisonGroup[],
  availableGroups: string[]
): { valid: boolean; errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];

  // 过滤空值并去重可用分组
  const validGroups = availableGroups
    .filter(g => g && g.trim())
    .filter((g, i, arr) => arr.indexOf(g) === i);

  // 用于检查重复的组合集合
  const seenCombinations = new Set<string>();

  comparisons.forEach(comp => {
    // 检查分组是否存在
    if (!validGroups.includes(comp.case_group)) {
      errors.push(`实验组 '${comp.case_group}' 不存在于样本分组中`);
    }
    if (!validGroups.includes(comp.control_group)) {
      errors.push(`对照组 '${comp.control_group}' 不存在于样本分组中`);
    }

    // 检查 case 和 control 是否相同
    if (comp.case_group === comp.control_group) {
      errors.push(`比较组 '${comp.comparison_name}' 的实验组和对照组相同`);
    }

    // 检查组合是否重复
    const combinationKey = `${comp.case_group}|${comp.control_group}`;
    if (seenCombinations.has(combinationKey)) {
      errors.push(`比较组组合重复: ${comp.case_group} vs ${comp.control_group}`);
    }
    seenCombinations.add(combinationKey);

    // 检查比较组名称是否规范
    if (!comp.comparison_name || !comp.comparison_name.trim()) {
      warnings.push(`比较组 '${comp.case_group} vs ${comp.control_group}' 缺少名称`);
    }
  });

  return {
    valid: errors.length === 0,
    errors,
    warnings
  };
}

/**
 * 将比较组转换为 TSV 格式
 *
 * @param comparisons 比较组列表
 * @returns TSV 格式字符串
 */
export function comparisonGroupsToTsv(comparisons: ComparisonGroup[]): string {
  const lines: string[] = [];

  // 添加注释表头
  lines.push('# Comparison Table - 比较组定义表');
  lines.push('# case_group\tcontrol_group\tcomparison_name');

  // 数据行
  comparisons.forEach(comp => {
    lines.push(`${comp.case_group}\t${comp.control_group}\t${comp.comparison_name}`);
  });

  return lines.join('\n');
}

/**
 * 解析 TSV 内容为比较组列表
 *
 * @param content TSV 文件内容
 * @returns 比较组列表
 */
export function parseComparisonTsv(content: string): ComparisonGroup[] {
  const comparisons: ComparisonGroup[] = [];
  const lines = content.trim().split('\n');

  lines.forEach(line => {
    // 跳过注释行和空行
    line = line.trim();
    if (!line || line.startsWith('#')) {
      return;
    }

    const parts = line.split('\t');
    if (parts.length >= 2) {
      const case_group = parts[0].trim();
      const control_group = parts[1].trim();
      const comparison_name = parts.length >= 3 ? parts[2].trim() : `${case_group}_vs_${control_group}`;

      if (case_group && control_group) {
        comparisons.push({
          case_group,
          control_group,
          comparison_name
        });
      }
    }
  });

  return comparisons;
}

/**
 * 从 Sample Sheet 数据中提取分组列表
 *
 * 查找 group_label 或 group 列，提取所有唯一的分组值
 *
 * @param tableData Sample Sheet 表格数据
 * @returns 分组名称列表
 */
export function extractGroupsFromTableData(tableData: TableData): string[] {
  const groups: string[] = [];

  // 查找分组列
  const groupColKey = tableData.columns.find(col =>
    col.key.toLowerCase() === 'group_label' ||
    col.key.toLowerCase() === 'group' ||
    col.key.toLowerCase() === 'grouplabel'
  )?.key;

  if (!groupColKey) {
    return groups;
  }

  // 提取所有分组值
  tableData.rows.forEach(row => {
    const groupValue = row[groupColKey]?.trim();
    if (groupValue && !groups.includes(groupValue)) {
      groups.push(groupValue);
    }
  });

  return groups;
}