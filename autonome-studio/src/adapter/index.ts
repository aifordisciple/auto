/**
 * 适配器模块入口
 *
 * 提供平台检测、API、WebSocket、SSE、文件系统等适配功能
 */

// 平台检测
export {
  Platform,
  isTauri,
  isWeb,
  isSSR,
  getPlatform,
  getTauriInvoke,
  type PlatformType,
  type TauriInvoke,
} from './platform';

// API 适配器
export {
  api,
  fetchAPI,
  getToken,
  setToken,
  removeToken,
  getBaseUrl,
  BASE_URL,
  ApiError,
  type ApiRequestOptions,
} from './api.adapter';

// WebSocket 适配器
export {
  createWebSocketAdapter,
  connectTerminalWebSocket,
  type WebSocketOptions,
  type WebSocketMessageHandler,
  type WebSocketStateHandler,
  type IWebSocketAdapter,
} from './websocket.adapter';

// SSE 适配器
export {
  createSSEAdapter,
  connectChatStream,
  connectTaskLogStream,
  type SSEOptions,
  type SSEEventHandler,
  type SSEErrorHandler,
  type ISSEAdapter,
  type ChatStreamEvent,
  type TaskLogEvent,
} from './sse.adapter';

// 文件系统适配器
export {
  fs,
  FileFilters,
  supportsLocalFs,
  openFilePicker,
  openDirectoryPicker,
  saveFilePicker,
  readFile,
  readTextFile,
  writeFile,
  listDirectory,
  pathExists,
  createDirectory,
  deleteFile,
  deleteDirectory,
  getFileInfo,
  copyFile,
  moveFile,
  type FileFilter,
  type FileInfo,
  type DialogOptions,
} from './fs.adapter';

// 自动更新
export {
  useAutoUpdate,
  UpdateNotification,
  getAppVersion,
  type UpdateInfo,
  type UpdateProgress,
  type UpdateStatus,
} from './updater.adapter';