/**
 * Chat Hooks 索引文件
 *
 * 从 ChatStage.tsx 提取的性能优化 hooks
 */

export { useFilePreview } from './useFilePreview';
export type { PreviewType, PreviewData, FilePreviewState } from './useFilePreview';

export { useMessageActions } from './useMessageActions';
export type { MessageActionsConfig } from './useMessageActions';

export { usePasteUpload } from './usePasteUpload';
export type { PastedAttachment } from './usePasteUpload';

export { useChatEventListeners, useGlobalEvent } from './useChatEventListeners';
export type { ChatEventListenersConfig } from './useChatEventListeners';

export { useChatStream } from './useChatStream';
export type {
  ExecutionPlanData,
  ExecutionStepData,
  ExecutionResultData,
  BlueprintState,
  ChatStreamConfig,
} from './useChatStream';

// 已有的 hooks
export { useSmartScroll } from './useSmartScroll';
export { useImmediateStream } from './useImmediateStream';