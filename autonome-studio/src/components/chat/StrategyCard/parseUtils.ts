/**
 * StrategyCard 解析工具函数
 *
 * 从 AI 响应中提取策略卡片数据，支持多种 LLM 模型输出格式。
 *
 * 特点：
 * 1. 多层容错机制
 * 2. 支持不同 LLM 模型的输出特征
 * 3. 更健壮的 JSON 和代码提取
 */
import { preprocessLLMResponse } from '@/lib/contentFilter';
import type { StrategyCardData } from './types';
import type { InteractivePlotData } from '../InteractivePlotCard/types';
import type { ActionMenuData } from '../InlineActionMenu/types';

/**
 * 预处理代码块格式
 * 修复 LLM 流式输出中可能出现的代码块格式问题
 */
export function preprocessCodeBlocks(content: string): string {
  if (!content) return content;

  // 1. 修复开始标签前没有换行的情况：文本紧挨着 ```json_strategy
  content = content.replace(/([^\n])(```[a-zA-Z_]*)/g, '$1\n\n$2');

  // ✨ 修复代码块开始标记后紧跟着非空字符（缺少换行）
  // 例如：```json_strategy{"a":1} -> ```json_strategy\n{"a":1}
  // 使用 (?=[^\s\n]) 防止吞掉实际内容
  // ✨ 添加 json_interactive_plot 和 on_strategy 支持
  // ✨ V2: 添加 json_action_menu 支持
  content = content.replace(
    /```(python|Python|r|R|json_strategy|json_intent|json_blueprint|json_interactive_plot|json_action_menu|on_strategy|on_interactive_plot|json)(?=[^\s\n])/g,
    '```$1\n'
  );

  // 3. 修复代码块开始标记后只有空格（无换行）
  // ✨ 重要：这里用 [ \t]+ 绝不能用 \s+，因为 \s 包含 \n 会误吞换行
  content = content.replace(
    /```(python|Python|r|R|json_strategy|json_intent|json_blueprint|json_interactive_plot|json_action_menu|on_strategy|on_interactive_plot|json)[ \t]+(?=[^\n])/g,
    '```$1\n'
  );

  // 4. 修复结束标签前没有换行的情况：}``` -> }\n```
  content = content.replace(/([^\n])(```)(?:\n|$)/g, '$1\n$2');

  // 5. 修复相邻代码块粘连
  content = content.replace(
    /```\s*```(python|Python|r|R|json_strategy|json_intent|json_blueprint|json_interactive_plot|json_action_menu|on_strategy|on_interactive_plot|json)/g,
    '```\n\n```$1'
  );

  return content;
}

/**
 * 从代码块提取 JSON（支持多种变体）
 *
 * 支持的格式：
 * - 标准格式：```json_strategy\n{...}```
 * - 无换行格式：```json_strategy{...}```
 * - 前置空格格式：``` json_strategy\n{...}```
 */
export function extractJsonFromCodeBlock(content: string): string | null {
  const patterns = [
    // 标准格式
    /```json_strategy\s*([\s\S]*?)```/,
    // 无换行格式（LLM 可能输出 ```json_strategy{...}）
    /```json_strategy\s*([{][\s\S]*?[}])\s*```/,
    // 更宽松的匹配（允许代码块未正确闭合）
    /```json_strategy\s*([\s\S]+)/,
    // ✨ 容错：AI 可能输出 on_strategy 而非 json_strategy
    /```on_strategy\s*([\s\S]*?)```/,
    /```on_strategy\s*([{][\s\S]*?[}])\s*```/,
    /```on_strategy\s*([\s\S]+)/,
  ];

  for (const pattern of patterns) {
    const match = content.match(pattern);
    if (match && match[1]) {
      return match[1].trim();
    }
  }

  return null;
}

/**
 * 从 json_action_menu 代码块提取 JSON
 *
 * V2 架构：支持解析操作菜单格式
 */
export function extractActionMenuFromCodeBlock(content: string): string | null {
  const patterns = [
    // 标准格式
    /```json_action_menu\s*([\s\S]*?)```/,
    // 无换行格式
    /```json_action_menu\s*([{][\s\S]*?[}])\s*```/,
    // 更宽松的匹配
    /```json_action_menu\s*([\s\S]+)/,
  ];

  for (const pattern of patterns) {
    const match = content.match(pattern);
    if (match && match[1]) {
      return match[1].trim();
    }
  }

  return null;
}

/**
 * 从全文提取 JSON（使用大括号深度匹配）
 *
 * 当没有找到规范代码块时，尝试从全文搜索包含 tool_id 的 JSON 对象
 */
export function extractJsonFromFullText(content: string): string | null {
  const toolIdIndex = content.indexOf('"tool_id"');
  if (toolIdIndex === -1) return null;

  // 找到包含 tool_id 的 JSON 对象的起始位置
  const startIndex = content.lastIndexOf('{', toolIdIndex);
  if (startIndex === -1) return null;

  // 使用大括号深度匹配提取完整 JSON
  return extractJSONByDepth(content.substring(startIndex));
}

/**
 * 大括号深度匹配提取 JSON
 *
 * 正确处理字符串内的转义字符和大括号
 */
export function extractJSONByDepth(str: string): string | null {
  const start = str.indexOf('{');
  if (start === -1) return null;

  let depth = 0;
  let inString = false;
  let escapeNext = false;

  for (let i = start; i < str.length; i++) {
    const char = str[i];

    if (escapeNext) {
      escapeNext = false;
      continue;
    }

    if (char === '\\') {
      escapeNext = true;
      continue;
    }

    if (char === '"') {
      inString = !inString;
      continue;
    }

    if (!inString) {
      if (char === '{') depth++;
      else if (char === '}') {
        depth--;
        if (depth === 0) {
          return str.substring(start, i + 1);
        }
      }
    }
  }

  return null;
}

/**
 * 清洗 JSON 字符串
 *
 * 修复常见的 JSON 语法错误：
 * - 零宽空格
 * - 尾随逗号
 */
export function sanitizeJsonString(jsonStr: string): string {
  // 确保 jsonStr 以 { 开头
  const jsonStart = jsonStr.indexOf('{');
  if (jsonStart > 0) {
    jsonStr = jsonStr.substring(jsonStart);
  }

  // 清洗常见错误
  jsonStr = jsonStr
    .replace(/\u00A0/g, ' ')     // 零宽空格
    .replace(/[\u200B-\u200D]/g, '') // 其他零宽字符
    .replace(/,\s*}/g, '}')       // 对象尾随逗号
    .replace(/,\s*]/g, ']');      // 数组尾随逗号

  return jsonStr;
}

/**
 * 尝试修复并解析 JSON
 *
 * 对于解析失败的 JSON，尝试常见修复策略
 */
export function tryRepairAndParseJson(jsonStr: string): unknown | null {
  try {
    return JSON.parse(jsonStr);
  } catch {
    // 尝试修复未闭合的字符串
    if (!jsonStr.endsWith('"') && jsonStr.includes(': "')) {
      try {
        const repaired = jsonStr + '"';
        return JSON.parse(repaired);
      } catch {
        // 继续尝试其他修复
      }
    }

    // 尝试修复未闭合的对象
    if (!jsonStr.endsWith('}')) {
      try {
        const openBraces = (jsonStr.match(/{/g) || []).length;
        const closeBraces = (jsonStr.match(/}/g) || []).length;
        const missing = openBraces - closeBraces;
        const repaired = jsonStr + '}'.repeat(missing);
        return JSON.parse(repaired);
      } catch {
        // 修复失败
      }
    }

    return null;
  }
}

/**
 * 提取代码块（支持多种变体）
 *
 * 支持的格式：
 * - 标准 R 格式：```r\ncode```
 * - 标准 Python 格式：```python\ncode```
 * - 无换行格式：```rcode``` 或 ```pythoncode```
 * - 大小写混合：```Python\n...``` 或 ```R\n...```
 */
export function extractCodeBlock(content: string): string {
  let fixedContent = content;

  // 1. 修复代码块开始标记后缺少换行符
  // 使用正向先行断言，避免吃掉后面的字符，特别是避免误伤 \r
  fixedContent = fixedContent.replace(
    /```(python|Python|r|R)(?=[^\s\n])/g,
    '```$1\n'
  );

  // 2. 修复代码块开始标记后只有空格但无换行
  // ✨ 修复核心 Bug：使用 [ \t]+ 而不是 \s+，因为 \s 包含 \n，会吃掉真实的换行和代码缩进！
  fixedContent = fixedContent.replace(
    /```(python|Python|r|R)[ \t]+(?=[^\n])/g,
    '```$1\n'
  );

  // 3. 修复结束标签前缺少换行符 (确保正则表达式 [\s\S]*? 能安全截断)
  fixedContent = fixedContent.replace(
    /([^\n])(```)(?:\n|$)/g,
    '$1\n$2'
  );

  // 按优先级尝试多种模式
  const patterns = [
    // 标准 Python 格式
    /```(?:python|Python)\s*\n([\s\S]*?)```/,
    // 标准 R 格式
    /```(?:r|R)\s*\n([\s\S]*?)```/,
    // 无换行 Python 格式（如果上面没有成功修复）
    /```(?:python|Python)\s*([\s\S]*?)```/,
    // 无换行 R 格式
    /```(?:r|R)\s*([\s\S]*?)```/,
  ];

  for (const pattern of patterns) {
    const match = fixedContent.match(pattern);
    if (match && match[1] && match[1].trim().length > 10) {
      return match[1].trim();
    }
  }

  return "";
}

/**
 * 解析策略卡片
 *
 * 从 AI 响应中提取策略卡片数据，支持多种 LLM 模型输出格式。
 *
 * 特点：
 * 1. 多层容错机制
 * 2. 支持不同 LLM 模型的输出特征
 * 3. 更健壮的 JSON 和代码提取
 */
export function parseStrategyCard(content: string): StrategyCardData | null {
  if (!content) return null;

  // 🔧 预处理：过滤 thinking 标签
  content = preprocessLLMResponse(content);

  // 🔧 新增：预处理代码块格式
  content = preprocessCodeBlocks(content);

  try {
    let data = null;
    let jsonStr: string | null = "";

    // 🛡️ 方法1: 从规范代码块提取
    jsonStr = extractJsonFromCodeBlock(content);

    // 🛡️ 方法2: 如果方法1失败，从全文搜索
    if (!jsonStr) {
      jsonStr = extractJsonFromFullText(content);
    }

    // 🔧 清洗 JSON 字符串
    if (jsonStr) {
      jsonStr = sanitizeJsonString(jsonStr);

      try {
        data = JSON.parse(jsonStr);
      } catch (e) {
        console.warn("[parseStrategyCard] JSON parse failed, attempting repair:", e);
        // 🛡️ 方法3: 尝试修复常见 JSON 错误
        data = tryRepairAndParseJson(jsonStr);
      }
    }

    if (!data || !data.tool_id || !data.title) {
      // 🔇 降低日志级别：普通消息不包含策略卡片是正常情况，不需要 warn
      // console.warn("[parseStrategyCard] Invalid data:", { hasData: !!data, tool_id: data?.tool_id, title: data?.title });
      return null;
    }

    // 强制统一工具 ID 命名规范
    if (data.tool_id === 'execute_r' || data.tool_id === 'R') {
      data.tool_id = 'execute-r';
    } else if (data.tool_id === 'execute_python' || data.tool_id === 'python') {
      data.tool_id = 'execute-python';
    }

    // ✨ 容错：AI 可能错误地输出 tool_id: "interactive-plot"
    // 自动修正为 execute-python，并从 parameters 中提取配置
    if (data.tool_id === 'interactive-plot') {
      console.warn('[parseStrategyCard] ⚠️ 检测到错误的 tool_id: interactive-plot，自动修正为 execute-python');
      data.tool_id = 'execute-python';
      data.task_mode = 'interactive_visualization';

      // 从 parameters 中提取 visualization_config
      if (data.parameters) {
        const params = data.parameters as Record<string, unknown>;
        data.visualization_config = {
          plot_type: (params.plot_type as string) || 'bar',
          title: data.title || 'Interactive Plot',
          description: data.description || '',
          data_source: 'results.tsv', // 默认数据源
          parameters: {},
          export_formats: ['pdf', 'png_300dpi', 'tsv'],
          aspect_ratio: 1.5,
        };

        // 生成数据处理代码
        const dataFile = params.data_file as string || '';
        const statColumn = params.stat_column as string || '';
        const statMethod = params.stat_method as string || 'count';

        if (dataFile && statColumn) {
          data.code = `import os
import pandas as pd

# 获取输出目录
out_dir = os.environ.get('TASK_OUT_DIR', '/workspace/project_xxx/results/default_task')
os.makedirs(out_dir, exist_ok=True)

# 读取原始数据
df = pd.read_csv('${dataFile}', sep='\\t')

# 统计计算
if '${statMethod}' == 'count':
    result_df = df.groupby('${statColumn}').size().reset_index(name='count')
else:
    result_df = df.groupby('${statColumn}').agg({'value': '${statMethod}'}).reset_index()

# 保存处理结果
result_df.to_csv(f'{out_dir}/results.tsv', sep='\\t', index=False)
print(f'处理完成，结果已保存到 {out_dir}/results.tsv')
print(f'列名: {list(result_df.columns)}')
`;
        }
      }
    }

    // 提取代码块
    data.code = extractCodeBlock(content);

    // ✨ 检查 Live_Coding 模式是否缺少代码
    const isLiveCoding = data.tool_id === 'execute-python' || data.tool_id === 'execute-r';
    if (isLiveCoding && !data.code) {
      console.warn("[parseStrategyCard] ⚠️ Live_Coding 模式但未提取到代码，tool_id:", data.tool_id);
      console.warn("[parseStrategyCard] 原始内容预览:", content.substring(0, 200));
    } else if (isLiveCoding && data.code) {
      console.info("[parseStrategyCard] ✅ 成功提取代码，长度:", data.code.length);
    }

    // ✨ 日志：检查 task_mode 和 visualization_config
    if (data.task_mode === 'interactive_visualization') {
      console.info("[parseStrategyCard] ✅ 检测到交互式可视化模式");
      console.info("[parseStrategyCard] visualization_config:", data.visualization_config);
    }

    return data;
  } catch (e) {
    console.error("❌ 解析卡片失败:", e);
    return null;
  }
}

// ==========================================
// ✨ InteractivePlotCard 解析函数
// ==========================================

/**
 * 从代码块提取 json_interactive_plot（支持多种变体和容错）
 */
export function extractInteractivePlotJson(content: string): string | null {
  // ✨ 尝试各种可能的格式变体
  const patterns = [
    // 标准格式：```json_interactive_plot\n{...}\n```
    /```json_interactive_plot\s*\n?([\s\S]*?)\n?```/,
    // 无换行格式
    /```json_interactive_plot\s*([\s\S]*?)```/,
    // 宽松匹配：可能没有闭合的 ```
    /```json_interactive_plot\s*([\s\S]+)/,
    // ✨ 容错：可能被错误输出为 on_interactive_plot
    /```on_interactive_plot\s*\n?([\s\S]*?)\n?```/,
    /```on_interactive_plot\s*([\s\S]*?)```/,
    // ✨ 容错：可能只有 interactive_plot
    /```interactive_plot\s*\n?([\s\S]*?)\n?```/,
    // ✨ 容错：可能输出为 json 后面跟 interactive_plot
    /```json\s*\n?([\s\S]*?)\n?```(?=[\s\S]*interactive_plot)/,
  ];

  for (const pattern of patterns) {
    const match = content.match(pattern);
    if (match && match[1]) {
      const jsonStr = match[1].trim();
      // 验证是否是有效的 JSON 开头
      if (jsonStr.startsWith('{') || jsonStr.startsWith('[')) {
        console.log('[extractInteractivePlotJson] ✅ 匹配成功，pattern:', pattern.source.slice(0, 30));
        return jsonStr;
      }
    }
  }

  return null;
}

/**
 * 解析交互式图表卡片
 *
 * 从 AI 响应中提取 json_interactive_plot 数据
 * 具有强容错能力，支持多种格式变体
 */
export function parseInteractivePlotCard(content: string): InteractivePlotData | null {
  if (!content) return null;

  console.log('[parseInteractivePlotCard] 🔍 开始解析，内容长度:', content.length);

  // 预处理：过滤 thinking 标签
  content = preprocessLLMResponse(content);

  // 预处理代码块格式
  content = preprocessCodeBlocks(content);

  // ✨ 方法1: 尝试从代码块提取 JSON
  let jsonStr = extractInteractivePlotJson(content);

  // ✨ 方法2/3 仅在内容不包含策略卡片时启用
  // 避免误解析 json_strategy 中的 visualization_config
  const hasStrategyBlock = content.includes('json_strategy') || content.includes('on_strategy');

  // ✨ 方法2: 如果失败，检查是否包含 plot_type 字段（强容错）
  if (!jsonStr && !hasStrategyBlock) {
    const plotTypeMatch = content.match(/"plot_type"\s*:\s*"([^"]+)"/);
    if (plotTypeMatch) {
      console.log('[parseInteractivePlotCard] 🔄 检测到 plot_type，尝试提取完整 JSON');

      // 从第一个 { 开始提取
      const startIdx = content.indexOf('{');
      if (startIdx !== -1) {
        // 使用大括号深度匹配提取完整 JSON
        jsonStr = extractJSONByDepth(content.substring(startIdx));
        if (jsonStr) {
          console.log('[parseInteractivePlotCard] ✅ 通过 plot_type 提取成功');
        }
      }
    }
  }

  // ✨ 方法3: 检查是否包含 data_source 和 parameters（图表配置的特征字段）
  if (!jsonStr && !hasStrategyBlock) {
    const hasDataSource = content.includes('"data_source"');
    const hasParameters = content.includes('"parameters"');
    const hasPlotType = content.includes('"plot_type"');

    if (hasDataSource && hasParameters && hasPlotType) {
      console.log('[parseInteractivePlotCard] 🔄 检测到图表配置特征字段，尝试提取');
      const startIdx = content.indexOf('{');
      if (startIdx !== -1) {
        jsonStr = extractJSONByDepth(content.substring(startIdx));
      }
    }
  }

  // 如果所有方法都失败
  if (!jsonStr) {
    console.log('[parseInteractivePlotCard] ⚠️ 无法提取 JSON 内容');
    return null;
  }

  console.log('[parseInteractivePlotCard] ✅ 成功提取 JSON，长度:', jsonStr.length);

  try {
    // 清洗 JSON
    const sanitized = sanitizeJsonString(jsonStr);

    // 解析 JSON
    let data: InteractivePlotData;
    try {
      data = JSON.parse(sanitized);
    } catch (e) {
      console.warn("[parseInteractivePlotCard] JSON parse failed, attempting repair:", e);
      const repaired = tryRepairAndParseJson(sanitized);
      if (!repaired) {
        return null;
      }
      data = repaired as InteractivePlotData;
    }

    // 验证必要字段
    if (!data.plot_type || !data.title || !data.data_source) {
      console.warn("[parseInteractivePlotCard] Missing required fields:", {
        plot_type: !!data.plot_type,
        title: !!data.title,
        data_source: !!data.data_source,
      });
      return null;
    }

    // 设置默认导出格式
    if (!data.export_formats) {
      data.export_formats = ['pdf', 'png_300dpi', 'tsv'];
    }

    // 设置默认宽高比
    if (!data.aspect_ratio) {
      data.aspect_ratio = 1.5;
    }

    console.info("[parseInteractivePlotCard] ✅ 成功解析交互式图表:", data.plot_type, data.title);
    return data;
  } catch (e) {
    console.error("❌ 解析交互式图表卡片失败:", e);
    return null;
  }
}

// ==========================================
// ✨ V2: ActionMenu 解析函数
// ==========================================

/**
 * 解析操作菜单 (json_action_menu)
 *
 * V2 架构：当后端置信度 < 0.90 时，返回操作菜单供用户选择。
 */
export function parseActionMenu(content: string): ActionMenuData | null {
  if (!content) return null;

  try {
    // 预处理代码块格式
    content = preprocessCodeBlocks(content);

    // 从代码块提取 JSON
    const jsonStr = extractActionMenuFromCodeBlock(content);

    if (!jsonStr) {
      return null;
    }

    // 清洗并解析 JSON
    const cleaned = sanitizeJsonString(jsonStr);
    const data = tryRepairAndParseJson(cleaned);

    if (!data || !Array.isArray(data.options)) {
      console.warn("[parseActionMenu] 无效的 action_menu 数据:", data);
      return null;
    }

    // 确保 options 数组有内容
    if (data.options.length === 0) {
      return null;
    }

    return {
      title: data.title || "请选择操作",
      message: data.message,
      options: data.options.map((opt: { skill_id: string; name?: string; match_score?: number; match_reason?: string }) => ({
        skill_id: opt.skill_id,
        name: opt.name || opt.skill_id,
        match_score: opt.match_score || 0.5,
        match_reason: opt.match_reason,
      })),
    };
  } catch (e) {
    console.error("[parseActionMenu] 解析操作菜单失败:", e);
    return null;
  }
}