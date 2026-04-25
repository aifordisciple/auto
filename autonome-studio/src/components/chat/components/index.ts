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

// 数据预览卡片
export { DataPreviewCard } from '../DataPreviewCard';

// 技能草稿卡片
export { SkillDraftCard } from '../SkillDraftCard';

// 即席分析策略卡片
export { AdhocAnalysisCard } from './AdhocAnalysisCard';
