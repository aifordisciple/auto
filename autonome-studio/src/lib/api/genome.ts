// ==========================================
// 参考基因组管理 API (Genome API)
// ==========================================

import { fetchAPI, BASE_URL } from '../api';
import { cachedFetch, invalidateCache } from '../apiCache';

export interface GenomeAsset {
  id: number;
  genomeid: string;
  species: string;
  version: string;
  species_code: string | null;
  url: string | null;
  date: string | null;
  genome: string;
  chrlen: string | null;
  gff: string | null;
  gffdb: string | null;
  gtf: string | null;
  geneanno: string | null;
  genelen: string | null;
  genome_info: string | null;
  bowtie2_index: string | null;
  bowtie1_index: string | null;
  bwa_index: string | null;
  star_index: string | null;
  hisat2_index: string | null;
  novoalign_index: string | null;
  minimap2_index: string | null;
  minimap2_juncbed: string | null;
  rsem_index: string | null;
  noncode_index: string | null;
  ref10x: string | null;
  sc_star: string | null;
  sc_gtf: string | null;
  godes: string | null;
  kg: string | null;
  known_lncRNA: string | null;
  bsgenome: string | null;
  geneid_or_symbol: string;
  is_active: boolean;
  description: string | null;
  custom_fields: Record<string, any>;
  owner_id: number;
  visibility: string;
  shared_with: number[];
  created_at: string;
  updated_at: string;
}

export const genomeApi = {
  /**
   * 获取基因组列表
   * 使用缓存优化，缓存 10 分钟
   */
  listGenomes: async (species?: string, search?: string, options?: { forceRefresh?: boolean }): Promise<GenomeAsset[]> => {
    const params: Record<string, string> = {};
    if (species) params.species = species;
    if (search) params.search = search;

    return cachedFetch<GenomeAsset[]>(
      'genomes:list',
      () => {
        const query = Object.keys(params).length > 0
          ? `?${new URLSearchParams(params).toString()}`
          : '';
        return fetchAPI(`/api/genomes/${query}`);
      },
      Object.keys(params).length > 0 ? params : undefined,
      options
    );
  },

  /**
   * 使基因组列表缓存失效
   */
  invalidateGenomesCache: () => {
    invalidateCache('genomes:list');
  },

  /**
   * 获取物种列表
   */
  listSpecies: async (): Promise<{ status: string; data: { species: string; count: number }[] }> => {
    return fetchAPI('/api/genomes/species/list');
  },

  /**
   * 获取单个基因组详情
   */
  getGenome: async (genomeid: string): Promise<GenomeAsset> => {
    return fetchAPI(`/api/genomes/${genomeid}`);
  },

  /**
   * 获取基因组配置（besaltpipe 兼容格式）
   */
  getGenomeConfig: async (genomeid: string): Promise<Record<string, any>> => {
    return fetchAPI(`/api/genomes/${genomeid}/config`);
  },

  /**
   * 创建基因组
   */
  createGenome: async (data: Partial<GenomeAsset>): Promise<GenomeAsset> => {
    return fetchAPI('/api/genomes/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * 更新基因组
   */
  updateGenome: async (genomeid: string, data: Partial<GenomeAsset>): Promise<GenomeAsset> => {
    return fetchAPI(`/api/genomes/${genomeid}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /**
   * 删除基因组
   */
  deleteGenome: async (genomeid: string): Promise<{ status: string; message: string }> => {
    return fetchAPI(`/api/genomes/${genomeid}`, {
      method: 'DELETE',
    });
  },

  /**
   * 切换基因组启用/禁用状态
   */
  toggleActive: async (genomeid: string): Promise<{ status: string; is_active: boolean }> => {
    return fetchAPI(`/api/genomes/${genomeid}/toggle-active`, {
      method: 'POST',
    });
  },

  /**
   * 共享基因组
   */
  shareGenome: async (genomeid: string, userIds: number[]): Promise<{ status: string; shared_with: number[] }> => {
    return fetchAPI(`/api/genomes/${genomeid}/share`, {
      method: 'POST',
      body: JSON.stringify({ user_ids: userIds }),
    });
  },

  /**
   * 验证基因组路径
   */
  validatePaths: async (genomeid: string): Promise<{
    status: string;
    total_paths: number;
    existing_paths: number;
    missing_paths: number;
    results: Record<string, any>;
  }> => {
    return fetchAPI(`/api/genomes/${genomeid}/validate`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  /**
   * 导出 TSV
   */
  exportTsv: async (species?: string): Promise<Blob> => {
    const params = species ? `?species=${species}` : '';
    const response = await fetch(`${BASE_URL}/api/genomes/export/tsv${params}`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`,
      },
    });
    return response.blob();
  },

  /**
   * 导入 TSV/CSV 文件
   */
  importTsv: async (formData: FormData): Promise<{
    status: string;
    imported_count: number;
    skipped_count: number;
    error_count: number;
    imported: string[];
    skipped: { genomeid: string; reason: string }[];
    errors: string[];
  }> => {
    const response = await fetch(`${BASE_URL}/api/genomes/import-tsv`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('autonome_access_token')}`,
      },
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || '导入失败');
    }
    return response.json();
  },
};
