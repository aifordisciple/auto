// ==========================================
// 文件夹管理 API
// ==========================================

import { fetchAPI } from '../api';

export interface CreateFolderRequest {
  parent_path: string;
  folder_name: string;
}

export interface MoveFileRequest {
  source_path: string;
  destination_path: string;
  overwrite?: boolean;
}

export interface FolderNode {
  name: string;
  path: string;
  writable: boolean;
  children: FolderNode[];
}

/**
 * 创建新文件夹
 */
export async function createFolder(projectId: string, request: CreateFolderRequest) {
  return fetchAPI(`/api/projects/${projectId}/folders`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * 移动文件或文件夹
 */
export async function moveFile(projectId: string, request: MoveFileRequest) {
  return fetchAPI(`/api/projects/${projectId}/files/move`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * 获取文件夹树（用于目标选择器）
 */
export async function getFolderTree(projectId: string): Promise<{ status: string; data: FolderNode[] }> {
  return fetchAPI(`/api/projects/${projectId}/folders`);
}
