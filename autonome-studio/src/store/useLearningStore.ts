/**
 * useLearningStore - 学习中心状态管理
 *
 * 管理文献列表、知识块、笔记、搜索结果、上传状态等
 *
 * 核心功能：
 * - 文献 CRUD + PDF 上传
 * - 状态轮询：自动轮询 uploading/parsing 状态的文献，直到 ready/error
 * - 知识库搜索（关键词 + 语义）
 * - 一键锻造 → Chat
 */

import { create } from 'zustand';
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

export interface LiteratureChunk {
  id: number;
  chunk_id: string;
  literature_id: number;
  chunk_index: number;
  chunk_type: 'text' | 'figure' | 'table' | 'equation';
  content: string;
  page_number: number;
  section_title?: string;
  figure_caption?: string;
  metadata_?: Record<string, unknown>;
  created_at: string;
}

export interface LiteratureNote {
  id: number;
  note_id: string;
  literature_id: number;
  user_id: number;
  chunk_id?: number;
  content: string;
  color?: string;
  created_at: string;
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

export interface LiteratureTag {
  id: number;
  ltag_id: string;
  name: string;
  color?: string;
  user_id: number;
  created_at: string;
}

// ==========================================
// 轮询配置
// ==========================================

/** 轮询间隔（毫秒） */
const POLL_INTERVAL = 3000;
/** 最大轮询次数（防止无限轮询） */
const POLL_MAX_ATTEMPTS = 200; // 200 * 3s = 10 分钟

// ==========================================
// Store 接口
// ==========================================

interface LearningState {
  // 文献列表
  literatures: Literature[];
  totalCount: number;
  currentPage: number;
  pageSize: number;
  filters: { tags: string[]; search: string; status?: string };

  // 当前选中文献
  selectedLiterature: Literature | null;
  chunks: LiteratureChunk[];
  notes: LiteratureNote[];

  // 知识库搜索
  searchResults: SearchResult[];
  searchQuery: string;
  isSearching: boolean;

  // 标签
  tags: LiteratureTag[];

  // 上传状态
  isUploading: boolean;
  uploadProgress: Record<string, number>;

  // 加载状态
  isLoading: boolean;

  // 📚 状态轮询
  /** 正在轮询的文献 ID 集合 */
  pollingIds: Set<number>;
  /** 轮询定时器引用 */
  _pollTimer: ReturnType<typeof setInterval> | null;

  // Actions
  fetchLiteratures: (page?: number) => Promise<void>;
  uploadPDF: (files: File[]) => Promise<void>;
  deleteLiterature: (id: number) => Promise<void>;
  selectLiterature: (id: number) => Promise<void>;
  clearSelection: () => void;
  searchKnowledge: (query: string) => Promise<void>;
  fetchTags: () => Promise<void>;
  createTag: (name: string, color?: string) => Promise<void>;
  deleteTag: (id: number) => Promise<void>;
  forgeToChat: (literatureId: number, chunkIds?: string[]) => Promise<void>;
  setFilters: (filters: Partial<LearningState['filters']>) => void;
  setPage: (page: number) => void;

  // 📚 状态轮询方法
  startPolling: (literatureId: number) => void;
  stopPolling: (literatureId: number) => void;
  pollPendingStatuses: () => Promise<void>;
  stopAllPolling: () => void;
}

// ==========================================
// Store 实现
// ==========================================

export const useLearningStore = create<LearningState>()((set, get) => ({
  // 初始状态
  literatures: [],
  totalCount: 0,
  currentPage: 1,
  pageSize: 20,
  filters: { tags: [], search: '', status: undefined },

  selectedLiterature: null,
  chunks: [],
  notes: [],

  searchResults: [],
  searchQuery: '',
  isSearching: false,

  tags: [],

  isUploading: false,
  uploadProgress: {},

  isLoading: false,

  // 📚 轮询状态
  pollingIds: new Set<number>(),
  _pollTimer: null,

  // ==========================================
  // 文献列表
  // ==========================================
  fetchLiteratures: async (page?: number) => {
    const state = get();
    const targetPage = page ?? state.currentPage;
    set({ isLoading: true });

    try {
      const params = new URLSearchParams({
        page: String(targetPage),
        page_size: String(state.pageSize),
      });
      if (state.filters.search) params.set('search', state.filters.search);
      if (state.filters.status) params.set('status', state.filters.status);

      const data = await fetchAPI(`/learning/literatures?${params}`);
      const literatures = Array.isArray(data) ? data : [];

      set({
        literatures,
        currentPage: targetPage,
        isLoading: false,
      });

      // 📚 自动启动轮询：检查是否有 uploading/parsing 状态的文献
      const pendingIds = literatures
        .filter((l: Literature) => l.status === 'uploading' || l.status === 'parsing')
        .map((l: Literature) => l.id);

      if (pendingIds.length > 0) {
        const currentPolling = new Set(get().pollingIds);
        let needsTimer = false;
        for (const id of pendingIds) {
          if (!currentPolling.has(id)) {
            currentPolling.add(id);
            needsTimer = true;
          }
        }
        if (needsTimer) {
          set({ pollingIds: currentPolling });
          // 确保轮询定时器在运行
          if (!get()._pollTimer) {
            const timer = setInterval(() => {
              get().pollPendingStatuses();
            }, POLL_INTERVAL);
            set({ _pollTimer: timer });
          }
        }
      }
    } catch (error) {
      console.error('获取文献列表失败:', error);
      set({ isLoading: false });
    }
  },

  // ==========================================
  // 上传 PDF
  // ==========================================
  uploadPDF: async (files: File[]) => {
    set({ isUploading: true });

    try {
      const formData = new FormData();
      files.forEach(file => formData.append('files', file));

      const result = await fetchAPI('/learning/literatures', {
        method: 'POST',
        body: formData,
      });

      // 刷新文献列表
      await get().fetchLiteratures(1);

      // 📚 立即启动轮询：上传后文献状态为 uploading，需要轮询直到 ready/error
      const uploadedIds: number[] = [];
      if (Array.isArray(result)) {
        for (const lit of result) {
          if (lit?.id && (lit.status === 'uploading' || lit.status === 'parsing')) {
            uploadedIds.push(lit.id);
          }
        }
      } else if (result?.id && (result.status === 'uploading' || result.status === 'parsing')) {
        uploadedIds.push(result.id);
      }

      for (const id of uploadedIds) {
        get().startPolling(id);
      }

      set({ isUploading: false });
    } catch (error) {
      console.error('上传 PDF 失败:', error);
      set({ isUploading: false });
    }
  },

  // ==========================================
  // 删除文献
  // ==========================================
  deleteLiterature: async (id: number) => {
    try {
      await fetchAPI(`/learning/literatures/${id}`, { method: 'DELETE' });
      get().stopPolling(id);
      set(state => ({
        literatures: state.literatures.filter(l => l.id !== id),
        selectedLiterature: state.selectedLiterature?.id === id ? null : state.selectedLiterature,
      }));
    } catch (error) {
      console.error('删除文献失败:', error);
    }
  },

  // ==========================================
  // 选择文献
  // ==========================================
  selectLiterature: async (id: number) => {
    try {
      const [literature, chunks, notes] = await Promise.all([
        fetchAPI(`/learning/literatures/${id}`),
        fetchAPI(`/learning/literatures/${id}/chunks`),
        fetchAPI(`/learning/literatures/${id}/notes`),
      ]);
      set({
        selectedLiterature: literature,
        chunks: Array.isArray(chunks) ? chunks : [],
        notes: Array.isArray(notes) ? notes : [],
      });
    } catch (error) {
      console.error('获取文献详情失败:', error);
    }
  },

  clearSelection: () => set({ selectedLiterature: null, chunks: [], notes: [] }),

  // ==========================================
  // 知识库搜索
  // ==========================================
  searchKnowledge: async (query: string) => {
    set({ isSearching: true, searchQuery: query });

    try {
      const data = await fetchAPI('/learning/search', {
        method: 'POST',
        body: JSON.stringify({ query, top_k: 10 }),
      });
      set({
        searchResults: data?.results ?? [],
        isSearching: false,
      });
    } catch (error) {
      console.error('搜索知识库失败:', error);
      set({ isSearching: false });
    }
  },

  // ==========================================
  // 标签管理
  // ==========================================
  fetchTags: async () => {
    try {
      const data = await fetchAPI('/learning/tags');
      set({ tags: Array.isArray(data) ? data : [] });
    } catch (error) {
      console.error('获取标签失败:', error);
    }
  },

  createTag: async (name: string, color?: string) => {
    try {
      await fetchAPI('/learning/tags', {
        method: 'POST',
        body: JSON.stringify({ name, color }),
      });
      await get().fetchTags();
    } catch (error) {
      console.error('创建标签失败:', error);
    }
  },

  deleteTag: async (id: number) => {
    try {
      await fetchAPI(`/learning/tags/${id}`, { method: 'DELETE' });
      set(state => ({ tags: state.tags.filter(t => t.id !== id) }));
    } catch (error) {
      console.error('删除标签失败:', error);
    }
  },

  // ==========================================
  // 一键锻造 → 发送到 Chat
  // ==========================================
  forgeToChat: async (literatureId: number, chunkIds?: string[]) => {
    try {
      const data = await fetchAPI('/learning/forge-context', {
        method: 'POST',
        body: JSON.stringify({ literature_id: literatureId, chunk_ids: chunkIds }),
      });

      if (data?.prompt) {
        // 将 Prompt 注入 Chat 输入框并触发发送
        // 通过自定义事件通知 Chat 组件
        window.dispatchEvent(new CustomEvent('learning:forge-to-chat', {
          detail: { prompt: data.prompt, literatureId },
        }));
      }
    } catch (error) {
      console.error('生成锻造上下文失败:', error);
    }
  },

  // ==========================================
  // 筛选与分页
  // ==========================================
  setFilters: (filters) => {
    set(state => ({ filters: { ...state.filters, ...filters } }));
    get().fetchLiteratures(1);
  },

  setPage: (page: number) => {
    get().fetchLiteratures(page);
  },

  // ==========================================
  // 📚 状态轮询
  // ==========================================

  /** 启动对指定文献的状态轮询 */
  startPolling: (literatureId: number) => {
    const currentPolling = new Set(get().pollingIds);
    currentPolling.add(literatureId);
    set({ pollingIds: currentPolling });

    // 确保轮询定时器在运行
    if (!get()._pollTimer) {
      const timer = setInterval(() => {
        get().pollPendingStatuses();
      }, POLL_INTERVAL);
      set({ _pollTimer: timer });
    }

    // 立即执行一次轮询
    get().pollPendingStatuses();
  },

  /** 停止对指定文献的状态轮询 */
  stopPolling: (literatureId: number) => {
    const currentPolling = new Set(get().pollingIds);
    currentPolling.delete(literatureId);
    set({ pollingIds: currentPolling });

    // 如果没有需要轮询的文献了，清除定时器
    if (currentPolling.size === 0 && get()._pollTimer) {
      clearInterval(get()._pollTimer!);
      set({ _pollTimer: null });
    }
  },

  /** 轮询所有 pending 状态的文献 */
  pollPendingStatuses: async () => {
    const { pollingIds, literatures } = get();
    if (pollingIds.size === 0) return;

    // 对每个正在轮询的文献查询状态
    const updates: { id: number; status: string; parse_error?: string }[] = [];

    for (const id of pollingIds) {
      try {
        const statusData = await fetchAPI(`/learning/literatures/${id}/status`);
        updates.push({
          id,
          status: statusData.status,
          parse_error: statusData.parse_error,
        });
      } catch {
        // 单个请求失败不影响其他轮询
      }
    }

    if (updates.length === 0) return;

    // 更新文献列表中的状态
    const newPollingIds = new Set(pollingIds);
    const updatedLiteratures = literatures.map(lit => {
      const update = updates.find(u => u.id === lit.id);
      if (update) {
        // 如果状态变为终态（ready/error），停止轮询
        if (update.status === 'ready' || update.status === 'error') {
          newPollingIds.delete(lit.id);
        }
        return {
          ...lit,
          status: update.status as Literature['status'],
          parse_error: update.parse_error,
        };
      }
      return lit;
    });

    // 同步更新 selectedLiterature
    const { selectedLiterature } = get();
    let updatedSelected = selectedLiterature;
    if (selectedLiterature) {
      const selUpdate = updates.find(u => u.id === selectedLiterature.id);
      if (selUpdate) {
        updatedSelected = {
          ...selectedLiterature,
          status: selUpdate.status as Literature['status'],
          parse_error: selUpdate.parse_error,
        };
      }
    }

    set({
      literatures: updatedLiteratures,
      selectedLiterature: updatedSelected,
      pollingIds: newPollingIds,
    });

    // 如果没有需要轮询的文献了，清除定时器
    if (newPollingIds.size === 0 && get()._pollTimer) {
      clearInterval(get()._pollTimer!);
      set({ _pollTimer: null });
    }
  },

  /** 停止所有轮询（组件卸载时调用） */
  stopAllPolling: () => {
    const { _pollTimer } = get();
    if (_pollTimer) {
      clearInterval(_pollTimer);
      set({ _pollTimer: null, pollingIds: new Set<number>() });
    }
  },
}));
