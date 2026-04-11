/**
 * useFilePreview Hook - 文件预览状态管理
 *
 * 功能：
 * 1. 管理文件预览状态（类型、内容、加载状态）
 * 2. 支持多种预览类型：图片、PDF、表格、代码、文本
 * 3. 处理文件下载
 *
 * 从 ChatStage.tsx 提取，减少主组件复杂度
 */
import { useState, useCallback } from 'react';
import { BASE_URL } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

export type PreviewType = 'image' | 'text' | 'table' | 'pdf' | 'code' | null;

export interface PreviewData {
  url: string;
  filename: string;
}

export interface FilePreviewState {
  previewData: PreviewData | null;
  previewType: PreviewType;
  previewContent: string | null;
  previewLanguage: string;
  isPreviewLoading: boolean;
}

// ==========================================
// 代码语言映射
// ==========================================

const CODE_LANGUAGE_MAP: Record<string, string> = {
  'py': 'python',
  'r': 'r',
  'js': 'javascript',
  'ts': 'typescript',
  'tsx': 'tsx',
  'jsx': 'jsx',
  'json': 'json',
  'yaml': 'yaml',
  'yml': 'yaml',
  'sh': 'bash',
  'bash': 'bash',
  'zsh': 'bash',
  'sql': 'sql',
  'html': 'html',
  'css': 'css',
  'scss': 'scss',
  'java': 'java',
  'c': 'c',
  'cpp': 'cpp',
  'h': 'c',
  'hpp': 'cpp',
  'go': 'go',
  'rs': 'rust',
  'swift': 'swift',
  'kt': 'kotlin',
  'scala': 'scala',
  'rb': 'ruby',
  'php': 'php',
  'lua': 'lua',
  'pl': 'perl',
  'pm': 'perl',
  'nf': 'groovy',
  'config': 'ini',
  'ini': 'ini',
  'toml': 'toml',
  'xml': 'xml',
  'md': 'markdown',
};

// ==========================================
// Hook 实现
// ==========================================

export function useFilePreview() {
  // 预览状态
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [previewType, setPreviewType] = useState<PreviewType>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [previewLanguage, setPreviewLanguage] = useState<string>('text');
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  /**
   * 下载文件资源
   */
  const handleDownloadAsset = useCallback(async (url: string, filename: string) => {
    try {
      const token = localStorage.getItem('autonome_access_token');
      const fetchUrl = url.startsWith('http') ? url : `${BASE_URL}${url}`;
      const res = await fetch(fetchUrl, { headers: { 'Authorization': `Bearer ${token}` } });
      if (!res.ok) throw new Error("获取文件失败");
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objUrl);
    } catch (e) {
      alert("❌ 下载失败，可能是网络问题或无权限。");
    }
  }, []);

  /**
   * 预览文件资源
   */
  const handlePreviewAsset = useCallback(async (url: string, filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    const isImage = ['png', 'jpg', 'jpeg', 'svg', 'gif'].includes(ext);
    const isTable = ['csv', 'tsv'].includes(ext);
    const isPdf = ext === 'pdf';

    const isCode = ext in CODE_LANGUAGE_MAP;
    const isText = ['txt', 'log'].includes(ext) || (ext in CODE_LANGUAGE_MAP);

    if (!isImage && !isText && !isTable && !isPdf && !isCode) {
      alert("💡 当前格式暂不支持内存预览，请点击右侧【下载】按钮获取。");
      return;
    }

    setPreviewData({ url, filename });
    setIsPreviewLoading(true);
    setPreviewContent(null);
    // 设置代码语言
    setPreviewLanguage(CODE_LANGUAGE_MAP[ext] || 'text');

    try {
      const token = localStorage.getItem('autonome_access_token');
      const fetchUrl = url.startsWith('http') ? url : `${BASE_URL}${url}`;
      const res = await fetch(fetchUrl, { headers: { 'Authorization': `Bearer ${token}` } });
      if (!res.ok) throw new Error("获取失败");

      if (isImage || isPdf) {
        setPreviewContent(URL.createObjectURL(await res.blob()));
        setPreviewType(isImage ? 'image' : 'pdf');
      } else {
        const text = await res.text();
        setPreviewContent(
          text.length > 200000
            ? text.substring(0, 200000) + '\n\n... [⚠️ 数据过大，内存预览已截断]'
            : text
        );
        // 根据文件类型设置预览类型
        if (isTable) {
          setPreviewType('table');
        } else if (isCode && !['txt', 'log'].includes(ext)) {
          setPreviewType('code');
        } else {
          setPreviewType('text');
        }
      }
    } catch (e) {
      alert("❌ 预览加载失败。");
      setPreviewData(null);
    } finally {
      setIsPreviewLoading(false);
    }
  }, []);

  /**
   * 关闭预览
   */
  const closePreview = useCallback(() => {
    // 清理 blob URL 防止内存泄漏
    if ((previewType === 'image' || previewType === 'pdf') && previewContent && previewContent.startsWith('blob:')) {
      URL.revokeObjectURL(previewContent);
    }
    setPreviewData(null);
    setPreviewContent(null);
    setPreviewType(null);
    setPreviewLanguage('text');
  }, [previewType, previewContent]);

  return {
    // 状态
    previewData,
    previewType,
    previewContent,
    previewLanguage,
    isPreviewLoading,
    // 方法
    handlePreviewAsset,
    handleDownloadAsset,
    closePreview,
  };
}

export default useFilePreview;