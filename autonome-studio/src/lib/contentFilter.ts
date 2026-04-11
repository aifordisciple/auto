/**
 * LLM 内容过滤模块
 *
 * 处理 LLM 输出中的 thinking 标签和 parameter 标签，确保用户界面干净，解析逻辑正确。
 *
 * 支持的 Thinking 格式：
 * - 심풀...심풀 (DeepSeek R1 韩文格式)
 * - ... (DeepSeek R1 变体)
 * - <thinking>...</thinking> (Claude extended thinking)
 * - |begin_thought|...|end_thought| (其他模型变体)
 *
 * 支持的 Parameter 格式：
 * - <parameter name="...">...</parameter> (模型输出的参数标签)
 */

/**
 * 编译后的正则模式列表（性能优化）
 */
const THINKING_TAG_PATTERNS: RegExp[] = [
  // DeepSeek R1 韩文格式：심풀...심풀
  /심풀[\s\S]*?심풀/g,
  // DeepSeek R1 变体 (ASCII) - 支持中文括号闭合标签
  /<think>[\s\S]*?<\/think>/g,
  /<think>[\s\S]*?好了/g,
  // 中文括号版本
  /\u300a[\s\S]*?\u300b/g,
  // Claude extended thinking
  /<thinking>[\s\S]*?<\/thinking>/gi,
  // 其他模型变体
  /\|begin_thought\|[\s\S]*?\|end_thought\|/g,
  // ✨ o1 系列模型的推理格式：Thought: ...\n\nResponse: ...
  // 匹配从 "Thought:" 到 "Response:" 或第一个空行的内容
  /^Thought:[\s\S]*?(?=^Response:|\n\n[A-Z])/gm,
  // 匹配独立的 Thought: 标签行
  /^Thought:\s*[\s\S]*?(?=^Response:|\n\n)/gm,
  // 匹配 <reasoning> 标签（某些模型的推理格式）
  /<reasoning>[\s\S]*?<\/reasoning>/gi,
  // 匹配 <reflection> 标签
  /<reflection>[\s\S]*?<\/reflection>/gi,
  // 匹配 <search_quality> 标签
  /<search_quality>[\s\S]*?<\/search_quality>/gi,
];

/**
 * Parameter 标签过滤模式
 * 某些 LLM 可能输出 <parameter name="...">...</parameter> 格式的标签
 */
const PARAMETER_TAG_PATTERNS: RegExp[] = [
  /<parameter[^>]*>[\s\S]*?<\/parameter>/gi,
];

/**
 * 过滤 LLM 输出中的 thinking 标签内容
 *
 * @param content - 原始内容字符串
 * @param debug - 是否开启调试模式（保留 thinking 内容，仅标记）
 * @returns 过滤后的内容字符串
 */
export function filterThinkingContent(content: string, debug: boolean = false): string {
  if (!content) {
    return content;
  }

  let result = content;

  if (debug) {
    // 调试模式：标记 thinking 内容而非删除
    THINKING_TAG_PATTERNS.forEach((pattern) => {
      // 重置 lastIndex 确保从头匹配
      pattern.lastIndex = 0;
      result = result.replace(pattern, (match) => {
        return `\n[DEBUG-THINKING]: ${match.slice(0, 50)}...[/DEBUG-THINKING]\n`;
      });
    });
    // Parameter 标签也标记
    PARAMETER_TAG_PATTERNS.forEach((pattern) => {
      pattern.lastIndex = 0;
      result = result.replace(pattern, (match) => {
        return `\n[DEBUG-PARAMETER]: ${match.slice(0, 50)}...[/DEBUG-PARAMETER]\n`;
      });
    });
  } else {
    // 正常模式：删除 thinking 内容
    THINKING_TAG_PATTERNS.forEach((pattern) => {
      // 重置 lastIndex 确保从头匹配
      pattern.lastIndex = 0;
      result = result.replace(pattern, '');
    });
    // 过滤 parameter 标签
    PARAMETER_TAG_PATTERNS.forEach((pattern) => {
      pattern.lastIndex = 0;
      result = result.replace(pattern, '');
    });

    // 处理不完整的 thinking 标签（流式传输中标签被分割的情况）
    // 检测未闭合的 labora 标签，隐藏标签及之后的内容
    const incompleteThinkPattern = /<tool_call>(?![\s\S]*<\/think>)[\s\S]*$/gi;
    const match = result.match(incompleteThinkPattern);
    if (match) {
      // 找到未闭合标签的起始位置，截断内容
      const startIndex = result.search(incompleteThinkPattern);
      if (startIndex > 0) {
        result = result.substring(0, startIndex);
      } else {
        result = '';
      }
    }

    // 处理未闭合的 <thinking> 标签
    const incompleteThinkingPattern = /<thinking>(?![\s\S]*<\/thinking>)[\s\S]*$/gi;
    const thinkingMatch = result.match(incompleteThinkingPattern);
    if (thinkingMatch) {
      const startIndex = result.search(incompleteThinkingPattern);
      if (startIndex > 0) {
        result = result.substring(0, startIndex);
      } else {
        result = '';
      }
    }
  }

  // 清理可能产生的多余空行（连续 3 个以上换行变成 2 个）
  result = result.replace(/\n{3,}/g, '\n\n');

  // 清理开头和结尾的空白
  result = result.trim();

  return result;
}

/**
 * 预处理 LLM 响应内容，用于代码块/JSON 提取前
 *
 * 此函数应在任何解析操作（如提取代码块、JSON、策略卡片）之前调用，
 * 确保 thinking 内容不会干扰解析逻辑。
 *
 * @param content - 原始 LLM 响应内容
 * @returns 预处理后的内容（已过滤 thinking 标签）
 */
export function preprocessLLMResponse(content: string): string {
  return filterThinkingContent(content);
}

/**
 * 检查响应是否仅包含 thinking 内容
 *
 * @param content - 原始内容字符串
 * @returns 如果内容过滤后为空，返回 true
 */
export function isThinkingOnlyResponse(content: string): boolean {
  if (!content || !content.trim()) {
    return true;
  }

  const filtered = filterThinkingContent(content);
  return !filtered || !filtered.trim();
}