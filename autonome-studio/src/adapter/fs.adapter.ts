/**
 * 文件系统适配器模块
 *
 * 提供统一的文件系统访问接口，自动适配 Web 和桌面端
 * - Web 端：通过后端 API 访问文件
 * - 桌面端：通过 Tauri IPC 直接访问本地文件
 */

import { isTauri } from './platform';

// ============================================
// 类型定义
// ============================================

/** 文件过滤器 */
export interface FileFilter {
  /** 过滤器名称 */
  name: string;
  /** 允许的扩展名（不含点号） */
  extensions: readonly string[];
}

/** 文件信息 */
export interface FileInfo {
  /** 文件/目录名 */
  name: string;
  /** 完整路径 */
  path: string;
  /** 是否是目录 */
  is_dir: boolean;
  /** 文件大小（字节） */
  size: number;
  /** 最后修改时间（Unix 时间戳） */
  modified?: number;
  /** 是否只读 */
  readonly: boolean;
}

/** 对话框选项 */
export interface DialogOptions {
  /** 窗口标题 */
  title?: string;
  /** 文件过滤器 */
  filters?: FileFilter[];
  /** 是否多选 */
  multiple?: boolean;
  /** 默认路径 */
  defaultPath?: string;
}

// ============================================
// 预设过滤器
// ============================================

/** 常用文件过滤器 */
export const FileFilters = {
  /** 数据文件 */
  DATA_FILES: { name: 'Data Files', extensions: ['csv', 'tsv', 'txt', 'xlsx', 'xls'] },
  /** FASTQ 文件 */
  FASTQ: { name: 'FASTQ Files', extensions: ['fastq', 'fq', 'fastq.gz', 'fq.gz'] },
  /** FASTA 文件 */
  FASTA: { name: 'FASTA Files', extensions: ['fasta', 'fa', 'fna', 'fasta.gz'] },
  /** BAM/SAM 文件 */
  BAM: { name: 'BAM/SAM Files', extensions: ['bam', 'sam', 'cram'] },
  /** VCF 文件 */
  VCF: { name: 'VCF Files', extensions: ['vcf', 'vcf.gz', 'bcf'] },
  /** 图片文件 */
  IMAGES: { name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'gif', 'svg', 'pdf'] },
  /** Python 文件 */
  PYTHON: { name: 'Python Files', extensions: ['py', 'ipynb'] },
  /** R 文件 */
  R: { name: 'R Files', extensions: ['r', 'rmd', 'R', 'Rmd'] },
  /** 所有文件 */
  ALL: { name: 'All Files', extensions: ['*'] },
} as const;

// ============================================
// 桌面端实现（Tauri IPC）
// ============================================

async function invokeTauri<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke } = await import('@tauri-apps/api/core');
  return invoke<T>(cmd, args);
}

const desktopFs = {
  async openFile(options?: DialogOptions): Promise<string[]> {
    return invokeTauri<string[]>('open_file_dialog', {
      options: {
        title: options?.title,
        filters: options?.filters || [],
        multiple: options?.multiple ?? false,
        default_path: options?.defaultPath,
      },
    });
  },

  async openDirectory(title?: string, defaultPath?: string): Promise<string | null> {
    return invokeTauri<string | null>('open_directory_dialog', {
      title,
      defaultPath,
    });
  },

  async saveFile(title?: string, defaultName?: string, filters?: FileFilter[]): Promise<string | null> {
    return invokeTauri<string | null>('save_file_dialog', {
      title,
      defaultName,
      filters: filters || [],
    });
  },

  async readFile(path: string, offset?: number, length?: number): Promise<Uint8Array> {
    const data = await invokeTauri<number[]>('read_local_file', {
      path,
      offset,
      length,
    });
    return new Uint8Array(data);
  },

  async readTextFile(path: string): Promise<string> {
    return invokeTauri<string>('read_text_file', { path });
  },

  async writeFile(path: string, content: Uint8Array | string, createDirs = true): Promise<void> {
    const data = typeof content === 'string'
      ? new TextEncoder().encode(content)
      : content;
    return invokeTauri<void>('write_local_file', {
      path,
      content: Array.from(data),
      createDirs,
    });
  },

  async appendFile(path: string, content: Uint8Array | string): Promise<void> {
    const data = typeof content === 'string'
      ? new TextEncoder().encode(content)
      : content;
    return invokeTauri<void>('append_local_file', {
      path,
      content: Array.from(data),
    });
  },

  async listDirectory(path: string, showHidden = false): Promise<FileInfo[]> {
    return invokeTauri<FileInfo[]>('list_directory', { path, showHidden });
  },

  async exists(path: string): Promise<boolean> {
    return invokeTauri<boolean>('path_exists', { path });
  },

  async createDirectory(path: string, recursive = true): Promise<void> {
    return invokeTauri<void>('create_directory', { path, recursive });
  },

  async deleteFile(path: string): Promise<void> {
    return invokeTauri<void>('delete_file', { path });
  },

  async deleteDirectory(path: string, recursive = false): Promise<void> {
    return invokeTauri<void>('delete_directory', { path, recursive });
  },

  async getFileInfo(path: string): Promise<FileInfo> {
    return invokeTauri<FileInfo>('get_file_info', { path });
  },

  async copyFile(source: string, destination: string): Promise<void> {
    return invokeTauri<void>('copy_file', { source, destination });
  },

  async moveFile(source: string, destination: string): Promise<void> {
    return invokeTauri<void>('move_file', { source, destination });
  },
};

// ============================================
// Web 端实现（通过后端 API）
// ============================================

const webFs = {
  async openFile(_options?: DialogOptions): Promise<string[]> {
    // Web 端使用数据中心文件选择
    console.warn('Web 端请使用数据中心选择文件');
    return [];
  },

  async openDirectory(_title?: string): Promise<string | null> {
    console.warn('Web 端不支持直接访问本地目录');
    return null;
  },

  async saveFile(_title?: string, _defaultName?: string): Promise<string | null> {
    console.warn('Web 端不支持本地保存对话框');
    return null;
  },

  async readFile(_path: string): Promise<Uint8Array> {
    throw new Error('Web 端请通过后端 API 访问文件');
  },

  async readTextFile(_path: string): Promise<string> {
    throw new Error('Web 端请通过后端 API 访问文件');
  },

  async writeFile(_path: string, _content: Uint8Array | string): Promise<void> {
    throw new Error('Web 端请通过后端 API 写入文件');
  },

  async appendFile(_path: string, _content: Uint8Array | string): Promise<void> {
    throw new Error('Web 端请通过后端 API 追加文件');
  },

  async listDirectory(_path: string): Promise<FileInfo[]> {
    throw new Error('Web 端请通过后端 API 列出目录');
  },

  async exists(_path: string): Promise<boolean> {
    throw new Error('Web 端请通过后端 API 检查路径');
  },

  async createDirectory(_path: string): Promise<void> {
    throw new Error('Web 端请通过后端 API 创建目录');
  },

  async deleteFile(_path: string): Promise<void> {
    throw new Error('Web 端请通过后端 API 删除文件');
  },

  async deleteDirectory(_path: string): Promise<void> {
    throw new Error('Web 端请通过后端 API 删除目录');
  },

  async getFileInfo(_path: string): Promise<FileInfo> {
    throw new Error('Web 端请通过后端 API 获取文件信息');
  },

  async copyFile(_source: string, _destination: string): Promise<void> {
    throw new Error('Web 端请通过后端 API 复制文件');
  },

  async moveFile(_source: string, _destination: string): Promise<void> {
    throw new Error('Web 端请通过后端 API 移动文件');
  },
};

// ============================================
// 统一导出
// ============================================

/**
 * 文件系统适配器
 *
 * 根据运行环境自动选择实现：
 * - Tauri 桌面端：直接访问本地文件系统
 * - Web 浏览器：通过后端 API 访问
 */
export const fs = isTauri() ? desktopFs : webFs;

/**
 * 检查是否支持本地文件系统
 */
export function supportsLocalFs(): boolean {
  return isTauri();
}

/**
 * 打开文件选择对话框
 *
 * 仅在桌面端可用，Web 端返回空数组
 */
export async function openFilePicker(options?: DialogOptions): Promise<string[]> {
  return fs.openFile(options);
}

/**
 * 打开目录选择对话框
 *
 * 仅在桌面端可用
 */
export async function openDirectoryPicker(title?: string): Promise<string | null> {
  return fs.openDirectory(title);
}

/**
 * 打开保存文件对话框
 *
 * 仅在桌面端可用
 */
export async function saveFilePicker(
  title?: string,
  defaultName?: string,
  filters?: FileFilter[]
): Promise<string | null> {
  return fs.saveFile(title, defaultName, filters);
}

/**
 * 读取文件内容
 *
 * @param path 文件路径
 * @param offset 起始偏移量（可选，用于大文件分块读取）
 * @param length 读取长度（可选）
 */
export async function readFile(path: string, offset?: number, length?: number): Promise<Uint8Array> {
  return fs.readFile(path, offset, length);
}

/**
 * 读取文本文件
 */
export async function readTextFile(path: string): Promise<string> {
  return fs.readTextFile(path);
}

/**
 * 写入文件
 *
 * @param path 文件路径
 * @param content 内容（字符串或字节数组）
 * @param createDirs 是否自动创建父目录
 */
export async function writeFile(
  path: string,
  content: Uint8Array | string,
  createDirs = true
): Promise<void> {
  return fs.writeFile(path, content, createDirs);
}

/**
 * 列出目录内容
 */
export async function listDirectory(path: string, showHidden = false): Promise<FileInfo[]> {
  return fs.listDirectory(path, showHidden);
}

/**
 * 检查路径是否存在
 */
export async function pathExists(path: string): Promise<boolean> {
  return fs.exists(path);
}

/**
 * 创建目录
 */
export async function createDirectory(path: string, recursive = true): Promise<void> {
  return fs.createDirectory(path, recursive);
}

/**
 * 删除文件
 */
export async function deleteFile(path: string): Promise<void> {
  return fs.deleteFile(path);
}

/**
 * 删除目录
 */
export async function deleteDirectory(path: string, recursive = false): Promise<void> {
  return fs.deleteDirectory(path, recursive);
}

/**
 * 获取文件信息
 */
export async function getFileInfo(path: string): Promise<FileInfo> {
  return fs.getFileInfo(path);
}

/**
 * 复制文件
 */
export async function copyFile(source: string, destination: string): Promise<void> {
  return fs.copyFile(source, destination);
}

/**
 * 移动/重命名文件
 */
export async function moveFile(source: string, destination: string): Promise<void> {
  return fs.moveFile(source, destination);
}