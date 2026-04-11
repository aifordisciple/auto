/**
 * 增强版错误诊断服务
 *
 * P1 效率提升：
 * - 错误分类（参数/环境/数据/系统）
 * - 用户友好消息
 * - 修复建议生成
 * - 根因分析
 */

// ==========================================
// 类型定义
// ==========================================

export type ErrorType = 'parameter' | 'environment' | 'data' | 'system';
export type ErrorSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface FixSuggestion {
  description: string;
  auto_fixable: boolean;
  fix_command?: string;
  manual_steps?: string[];
  estimated_time?: string;
}

export interface EnhancedErrorDiagnosis {
  error_type: ErrorType;
  severity: ErrorSeverity;
  message: string;
  user_friendly_message: string;
  root_cause: string;
  fix_suggestions: FixSuggestion[];
  related_help_docs?: string[];
}

export interface ErrorContext {
  message: string;
  traceback?: string[];
  context?: Record<string, any>;
}

// ==========================================
// 错误模式匹配规则
// ==========================================

interface ErrorPattern {
  pattern: RegExp;
  type: ErrorType;
  severity: ErrorSeverity;
  friendlyMessage: (match: RegExpMatchArray) => string;
  rootCause: (match: RegExpMatchArray) => string;
  suggestions: (match: RegExpMatchArray) => FixSuggestion[];
}

const ERROR_PATTERNS: ErrorPattern[] = [
  // 参数错误
  {
    pattern: /ValueError:\s*(\w+)\s*must be (\w+), got (.+)/i,
    type: 'parameter',
    severity: 'medium',
    friendlyMessage: (match) => `参数 "${match[1]}" 的值无效，需要 ${match[2]} 类型`,
    rootCause: (match) => `参数 ${match[1]} 值为 ${match[3]}，不符合要求`,
    suggestions: (match) => [
      {
        description: `将参数 "${match[1]}" 改为有效的 ${match[2]} 值`,
        auto_fixable: true,
        estimated_time: '< 1分钟',
      },
    ],
  },
  {
    pattern: /TypeError:\s*(\w+)/i,
    type: 'parameter',
    severity: 'medium',
    friendlyMessage: () => '参数类型不正确',
    rootCause: () => '参数类型与预期不符',
    suggestions: () => [
      {
        description: '检查并修正参数类型',
        auto_fixable: false,
        manual_steps: ['查看参数文档', '确认正确的参数类型', '重新输入参数'],
        estimated_time: '1-2分钟',
      },
    ],
  },
  // 环境错误
  {
    pattern: /FileNotFoundError:\s*(.+) not found/i,
    type: 'environment',
    severity: 'high',
    friendlyMessage: (match) => `找不到必需的文件: ${match[1]}`,
    rootCause: () => '缺少必要的参考文件或资源',
    suggestions: (match) => [
      {
        description: '检查文件路径是否正确',
        auto_fixable: false,
        manual_steps: ['确认文件存在', '检查文件路径配置', '上传或创建缺失的文件'],
        estimated_time: '5-10分钟',
      },
    ],
  },
  {
    pattern: /genome|reference/i,
    type: 'environment',
    severity: 'high',
    friendlyMessage: () => '找不到参考基因组文件',
    rootCause: () => '参考基因组文件缺失或路径配置错误',
    suggestions: () => [
      {
        description: '下载或配置参考基因组',
        auto_fixable: false,
        manual_steps: [
          '检查基因组文件是否已下载',
          '确认基因组路径配置正确',
          '支持的基因组: hg38, mm10, etc.',
        ],
        estimated_time: '10-30分钟',
      },
    ],
  },
  // 数据错误
  {
    pattern: /DataError:\s*(.+)/i,
    type: 'data',
    severity: 'high',
    friendlyMessage: (match) => `数据处理错误: ${match[1]}`,
    rootCause: () => '输入数据存在问题',
    suggestions: () => [
      {
        description: '检查输入数据质量',
        auto_fixable: false,
        manual_steps: ['查看数据质控报告', '检查样本表格式', '确认数据完整性'],
        estimated_time: '5-15分钟',
      },
    ],
  },
  {
    pattern: /(\d+)\s*(valid samples?|samples? valid)/i,
    type: 'data',
    severity: 'high',
    friendlyMessage: (match) => `质控后仅剩 ${match[1]} 个有效样本`,
    rootCause: () => '样本质量不合格导致数据丢失',
    suggestions: () => [
      {
        description: '放宽质控参数或检查原始数据',
        auto_fixable: true,
        fix_command: 'adjust_qc_params',
        estimated_time: '2-5分钟',
      },
    ],
  },
  // 系统错误
  {
    pattern: /MemoryError:\s*(.+)/i,
    type: 'system',
    severity: 'critical',
    friendlyMessage: () => '内存不足，无法完成计算',
    rootCause: () => '计算任务超出可用内存',
    suggestions: () => [
      {
        description: '减少数据量或使用增量处理',
        auto_fixable: false,
        manual_steps: [
          '尝试分批处理数据',
          '使用更小的样本子集',
          '联系管理员增加资源',
        ],
        estimated_time: '10-30分钟',
      },
    ],
  },
  {
    pattern: /TimeoutError|timeout/i,
    type: 'system',
    severity: 'high',
    friendlyMessage: () => '任务执行超时',
    rootCause: () => '计算时间超出限制',
    suggestions: () => [
      {
        description: '优化计算流程或增加超时时间',
        auto_fixable: false,
        manual_steps: ['检查任务复杂度', '尝试简化分析流程', '联系管理员调整超时设置'],
        estimated_time: '5-15分钟',
      },
    ],
  },
];

// ==========================================
// 服务类
// ==========================================

export class ErrorDiagnosticService {
  // ==========================================
  // 诊断错误
  // ==========================================

  async diagnose(error: ErrorContext): Promise<EnhancedErrorDiagnosis> {
    const message = error.message || '';

    // 尝试匹配已知错误模式
    for (const pattern of ERROR_PATTERNS) {
      const match = message.match(pattern.pattern);
      if (match) {
        return {
          error_type: pattern.type,
          severity: pattern.severity,
          message,
          user_friendly_message: pattern.friendlyMessage(match),
          root_cause: pattern.rootCause(match),
          fix_suggestions: pattern.suggestions(match),
          related_help_docs: this.getRelatedDocs(pattern.type),
        };
      }
    }

    // 未知错误类型
    return this.createUnknownDiagnosis(message);
  }

  // ==========================================
  // 私有方法
  // ==========================================

  private createUnknownDiagnosis(message: string): EnhancedErrorDiagnosis {
    return {
      error_type: 'system',
      severity: 'medium',
      message,
      user_friendly_message: '执行过程中发生错误，请查看详细信息',
      root_cause: '未知错误',
      fix_suggestions: [
        {
          description: '查看详细错误信息并尝试修复',
          auto_fixable: false,
          manual_steps: ['检查错误日志', '参考文档排查问题', '联系技术支持'],
          estimated_time: '不确定',
        },
      ],
      related_help_docs: ['/docs/troubleshooting'],
    };
  }

  private getRelatedDocs(errorType: ErrorType): string[] {
    const docs: Record<ErrorType, string[]> = {
      parameter: ['/docs/parameters', '/docs/configuration'],
      environment: ['/docs/environment', '/docs/setup'],
      data: ['/docs/data-format', '/docs/quality-control'],
      system: ['/docs/system-requirements', '/docs/troubleshooting'],
    };
    return docs[errorType] || [];
  }
}

// ==========================================
// 单例和便捷函数
// ==========================================

let instance: ErrorDiagnosticService | null = null;

export function getErrorDiagnosticService(): ErrorDiagnosticService {
  if (!instance) {
    instance = new ErrorDiagnosticService();
  }
  return instance;
}

export async function diagnoseError(
  error: ErrorContext
): Promise<EnhancedErrorDiagnosis> {
  return getErrorDiagnosticService().diagnose(error);
}

export default ErrorDiagnosticService;