// ==========================================
// API Domain Modules - 统一导出
// ==========================================

// 文件夹管理 API
export {
  createFolder,
  moveFile,
  getFolderTree,
  type CreateFolderRequest,
  type MoveFileRequest,
  type FolderNode,
} from './folder';

// SKILL Forge 技能工厂 API
export {
  skillForgeApi,
  type ExecutorType,
  type CraftRequest,
  type CraftResponse,
  type BundleResponse,
  type SkillAsset,
} from './skillForge';

// 技能草稿 API
export {
  skillDraftApi,
  type PendingSkillDraft,
  type DraftStats,
} from './skillDraft';

// Admin 管理员专区 API
export { adminApi } from './admin';

// SKILL Templates 模板 API
export {
  templateApi,
  type SkillTemplate,
  type InstantiateRequest,
  type InstantiateResult,
} from './template';

// 技能锻造会话 API
export {
  forgeSessionApi,
  type ForgeSessionCreateRequest,
  type ForgeSessionResponse,
  type ForgeSessionDetail,
  type ForgeMessageData,
  type ForgeChatRequest,
  type SkillDraftUpdateRequest,
  type ForgeSessionListItem,
  type SkillDraft,
} from './forgeSession';

// 参考基因组管理 API
export {
  genomeApi,
  type GenomeAsset,
} from './genome';

// 分析数据库管理 API
export {
  databaseApi,
  type AnalysisDatabase,
} from './database';

// 错误诊断 API
export {
  errorDiagnosticApi,
  type DiagnoseRequest,
  type FixSuggestion,
  type ErrorDiagnosis,
  type DiagnoseResponse,
  type FixResponse,
} from './errorDiagnostic';

// 执行参数状态管理（本地存储）
export {
  executionStateApi,
  type ExecutionParams,
} from './executionState';

// 首页收藏技能管理（本地存储）
export {
  pinnedSkillsApi,
  type PinnedSkill,
} from './pinnedSkills';

// 技能快速执行 API
export {
  quickExecuteApi,
  type QuickMatchRequest,
  type QuickMatchResponse,
  type MatchMode,
} from './quickExecute';

// 推荐反馈 API
export {
  feedbackApi,
  type FeedbackEventType,
  type RecordBehaviorRequest,
} from './feedback';
