/**
 * Chat Hooks 索引文件
 *
 * Vercel AI SDK 重构后：
 * - 移除 useImmediateStream、useChatStream（由 useChat 替代）
 * - 新增 useChatSync（桥接 useChat 到 Zustand store）
 * - 新增 useChatQueue（消息队列管理）
 */

export { useFilePreview } from './useFilePreview';
export type { PreviewType, PreviewData, FilePreviewState } from './useFilePreview';

export { useMessageActions } from './useMessageActions';

export { usePasteUpload } from './usePasteUpload';
export type { PastedAttachment } from './usePasteUpload';

export { useChatEventListeners, useGlobalEvent } from './useChatEventListeners';
export type { ChatEventListenersConfig } from './useChatEventListeners';

export { useSmartScroll } from './useSmartScroll';

export { useChatSync } from './useChatSync';

export { useChatQueue } from './useChatQueue';
