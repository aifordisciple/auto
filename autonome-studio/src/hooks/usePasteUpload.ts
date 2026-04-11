/**
 * usePasteUpload Hook - 粘贴上传处理
 *
 * 功能：
 * 1. 处理 Ctrl+V 粘贴图片和文件
 * 2. 管理粘贴附件状态
 * 3. 自动上传到服务器 raw_data/.pasted 目录
 *
 * 从 ChatStage.tsx 提取，减少主组件复杂度
 */
import { useCallback } from 'react';
import { useWorkspaceStore } from '@/store/useWorkspaceStore';
import { BASE_URL } from '@/lib/api';

// ==========================================
// 类型定义
// ==========================================

export interface PastedAttachment {
  id: string;
  type: 'image' | 'file';
  localUrl?: string;
  fileName: string;
  fileSize: number;
  serverPath: string;
  isUploading: boolean;
}

// ==========================================
// Hook 实现
// ==========================================

export function usePasteUpload() {
  // Store 状态
  const currentProjectId = useWorkspaceStore(state => state.currentProjectId);
  const pastedAttachments = useWorkspaceStore(state => state.pastedAttachments);
  const addPastedAttachment = useWorkspaceStore(state => state.addPastedAttachment);
  const removePastedAttachment = useWorkspaceStore(state => state.removePastedAttachment);
  const updatePastedAttachment = useWorkspaceStore(state => state.updatePastedAttachment);
  const clearPastedAttachments = useWorkspaceStore(state => state.clearPastedAttachments);

  /**
   * 处理粘贴的文件 - 上传到服务器并添加到状态
   */
  const handlePastedFile = useCallback(async (file: File, type: 'image' | 'file') => {
    if (!currentProjectId) return;

    const attachmentId = `paste_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const localUrl = type === 'image' ? URL.createObjectURL(file) : undefined;

    // 添加到状态（上传中）
    addPastedAttachment({
      id: attachmentId,
      type,
      localUrl,
      fileName: file.name,
      fileSize: file.size,
      serverPath: '',
      isUploading: true
    });

    // 上传到服务器
    try {
      const token = localStorage.getItem('autonome_access_token');
      const formData = new FormData();
      formData.append('file', file);
      formData.append('target_path', 'raw_data/.pasted');

      const response = await fetch(`${BASE_URL}/api/projects/${currentProjectId}/files`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData
      });

      const result = await response.json();
      if (result.status === 'success') {
        // 更新附件状态，保存服务器路径
        updatePastedAttachment(attachmentId, {
          serverPath: result.data.file_path || `raw_data/.pasted/${file.name}`,
          isUploading: false
        });
      } else {
        // 上传失败，移除附件
        if (localUrl) URL.revokeObjectURL(localUrl);
        removePastedAttachment(attachmentId);
        console.error('Paste upload failed:', result);
      }
    } catch (error) {
      // 上传失败，移除附件
      if (localUrl) URL.revokeObjectURL(localUrl);
      removePastedAttachment(attachmentId);
      console.error('Paste upload error:', error);
    }
  }, [currentProjectId, addPastedAttachment, updatePastedAttachment, removePastedAttachment]);

  /**
   * 处理粘贴事件 - 支持图片和文件
   *
   * 工作流程：
   * 1. 检测剪贴板内容类型（图片/文件/文本）
   * 2. 图片类型：创建本地预览 URL，上传到 raw_data/.pasted 目录
   * 3. 文件类型：直接上传到 raw_data/.pasted 目录
   * 4. 文本类型：不处理，走默认行为
   */
  const handlePaste = useCallback(async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items || !currentProjectId) return;

    for (const item of Array.from(items)) {
      // 1. 处理图片类型 (PNG, JPG, GIF, WebP 等)
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) await handlePastedFile(file, 'image');
      }
      // 2. 处理文件类型 (PDF, TXT, Excel, Word 等)
      else if (item.kind === 'file') {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) await handlePastedFile(file, 'file');
      }
      // 3. 文本类型不处理，走默认行为
    }
  }, [currentProjectId, handlePastedFile]);

  /**
   * 清理粘贴附件（包括本地预览 URL）
   */
  const cleanupPastedAttachments = useCallback(() => {
    // 先清理本地预览 URL
    pastedAttachments.forEach(att => {
      if (att.localUrl) URL.revokeObjectURL(att.localUrl);
    });
    clearPastedAttachments();
  }, [pastedAttachments, clearPastedAttachments]);

  /**
   * 获取粘贴的文件路径列表
   */
  const getPastedFilePaths = useCallback(() => {
    return pastedAttachments
      .filter(att => att.type === 'file' && att.serverPath)
      .map(att => att.serverPath);
  }, [pastedAttachments]);

  /**
   * 获取粘贴的图片路径列表
   */
  const getPastedImagePaths = useCallback(() => {
    return pastedAttachments
      .filter(att => att.type === 'image' && att.serverPath)
      .map(att => att.serverPath);
  }, [pastedAttachments]);

  /**
   * 检查是否有正在上传的附件
   */
  const hasUploadingAttachments = useCallback(() => {
    return pastedAttachments.some(att => att.isUploading);
  }, [pastedAttachments]);

  return {
    // 状态
    pastedAttachments,
    // 方法
    handlePaste,
    handlePastedFile,
    cleanupPastedAttachments,
    getPastedFilePaths,
    getPastedImagePaths,
    hasUploadingAttachments,
  };
}

export default usePasteUpload;