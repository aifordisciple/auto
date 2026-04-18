/**
 * 学习中心 API 客户端
 *
 * 提供文献上传、检索、锻造上下文生成等接口
 */

import { fetchAPI } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

export interface Literature {
  id: number;
  literature_id: string;
  title: string;
  authors?: string;
  year?: number;
  journal?: string;
  doi?: string;
  abstract?: string;
  keywords?: string;
  thumbnail_url?: string;
  page_count: number;
  status: 'uploading' | 'parsing' | 'ready' | 'error';
  parse_error?: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface SearchResult {
  chunk_id: string;
  content: string;
  chunk_type: string;
  page_number: number;
  section_title?: string;
  figure_caption?: string;
  source_title?: string;
  source_doi?: string;
  source_literature_id?: string;
  match_type: 'keyword' | 'semantic';
}

// ==========================================
// API 对象
// ==========================================

export const learningApi = {
  /** 列出文献 */
  listLiteratures: async (params: {
    page?: number;
    page_size?: number;
    search?: string;
    tag?: string;
    status?: string;
  } = {}): Promise<Literature[]> => {
    const query = new URLSearchParams();
    if (params.page) query.set('page', String(params.page));
    if (params.page_size) query.set('page_size', String(params.page_size));
    if (params.search) query.set('search', params.search);
    if (params.tag) query.set('tag', params.tag);
    if (params.status) query.set('status', params.status);
    return fetchAPI(`/learning/literatures?${query}`);
  },

  /** 上传 PDF */
  uploadPDF: async (files: File[]): Promise<Literature | Literature[]> => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    return fetchAPI('/learning/literatures', { method: 'POST', body: formData });
  },

  /** 获取文献详情 */
  getLiterature: async (id: number): Promise<Literature> => {
    return fetchAPI(`/learning/literatures/${id}`);
  },

  /** 删除文献 */
  deleteLiterature: async (id: number): Promise<void> => {
    await fetchAPI(`/learning/literatures/${id}`, { method: 'DELETE' });
  },

  /** 获取解析状态 */
  getStatus: async (id: number): Promise<{ status: string; parse_error?: string }> => {
    return fetchAPI(`/learning/literatures/${id}/status`);
  },

  /** 获取知识块 */
  getChunks: async (literatureId: number): Promise<unknown[]> => {
    return fetchAPI(`/learning/literatures/${literatureId}/chunks`);
  },

  /** 搜索知识库 */
  search: async (query: string, topK: number = 10): Promise<{ results: SearchResult[]; total: number }> => {
    return fetchAPI('/learning/search', {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK }),
    });
  },

  /** DOI 导入 */
  ingestDOI: async (doi: string): Promise<{ status: string; literature_id: string }> => {
    return fetchAPI('/learning/ingest/doi', {
      method: 'POST',
      body: JSON.stringify({ doi }),
    });
  },

  /** 生成锻造上下文 */
  forgeContext: async (literatureId: number, chunkIds?: string[]): Promise<{ prompt: string }> => {
    return fetchAPI('/learning/forge-context', {
      method: 'POST',
      body: JSON.stringify({ literature_id: literatureId, chunk_ids: chunkIds }),
    });
  },
};
