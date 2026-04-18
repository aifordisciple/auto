// ==========================================
// 错误诊断 API
// ==========================================

import { fetchAPI } from '../api';

export interface DiagnoseRequest {
  error_log: string;
  exit_code: number;
  language: string;
  context?: Record<string, unknown>;
}

export interface FixSuggestion {
  action: string;
  description: string;
  auto_fixable: boolean;
  fix_command?: string;
  fix_code?: string;
  manual_steps: string[];
}

export interface ErrorDiagnosis {
  error_type: string;
  severity: string;
  title: string;
  message: string;
  original_error: string;
  line_number?: number;
  module_name?: string;
  file_path?: string;
  suggestions: FixSuggestion[];
  context: Record<string, unknown>;
}

export interface DiagnoseResponse {
  status: string;
  diagnosis: ErrorDiagnosis;
}

export interface FixResponse {
  success: boolean;
  message: string;
  action: string;
  details?: Record<string, unknown>;
}

export const errorDiagnosticApi = {
  /**
   * 诊断执行错误
   */
  diagnose: async (request: DiagnoseRequest): Promise<DiagnoseResponse> => {
    return fetchAPI('/api/error/diagnose', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  /**
   * 一键修复错误
   */
  fix: async (
    errorType: string,
    moduleName?: string,
    filePath?: string,
    language: string = 'python'
  ): Promise<FixResponse> => {
    return fetchAPI('/api/error/fix', {
      method: 'POST',
      body: JSON.stringify({
        error_type: errorType,
        module_name: moduleName,
        file_path: filePath,
        language,
      }),
    });
  },

  /**
   * 获取常见错误列表
   */
  getCommonErrors: async (): Promise<{
    status: string;
    errors: Array<{
      type: string;
      title: string;
      description: string;
      solution: string;
      auto_fixable: boolean;
    }>;
  }> => {
    return fetchAPI('/api/error/common-errors');
  },
};
