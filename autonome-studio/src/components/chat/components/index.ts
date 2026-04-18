/**
 * ChatStage 子组件导出模块
 *
 * 包含从 ChatStage.tsx 中拆分出的所有子组件
 */

// 表格预览组件
export { TablePreview } from './TablePreview';

// 附件选择器组件
export { AttachmentPicker } from './AttachmentPicker';

// 消息操作按钮组件
export { MessageActionButtons, copyToClipboard } from './MessageActionButtons';

// 执行结果卡片组件
export {
  ExecutionResultCard,
  AssetTreeCard,
} from './ExecutionResultCard';

// 共享资产树组件（从原 ExecutionResultCard 提取）
export { getFileIcon, getFileTypeIcon, buildAssetTree, buildAssetTreeFromFiles, AssetTreeNode } from '../shared/AssetTree';
export type { AssetNodeType, AssetTreeInputItem, AssetTreeNodeProps } from '../shared/AssetTree';
