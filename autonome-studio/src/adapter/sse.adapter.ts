/**
 * SSE (Server-Sent Events) 适配器模块
 *
 * 提供统一的 SSE 流式响应接口，自动适配 Web 和桌面端
 */

import { isTauri } from './platform';
import { BASE_URL, getToken } from '@/lib/api';

/**
 * SSE 事件处理器
 */
export type SSEEventHandler<T = unknown> = (event: T) => void;

/**
 * SSE 错误处理器
 */
export type SSEErrorHandler = (error: Error) => void;

/**
 * SSE 选项
 */
export interface SSEOptions {
  /** 请求头 */
  headers?: Record<string, string>;
  /** 请求体 */
  body?: unknown;
  /** HTTP 方法 */
  method?: 'GET' | 'POST';
  /** 超时时间（毫秒） */
  timeout?: number;
  /** 重连次数 */
  maxReconnectAttempts?: number;
  /** 是否自动重连 */
  autoReconnect?: boolean;
}

/**
 * SSE 适配器接口
 */
export interface ISSEAdapter<T = unknown> {
  connect(): Promise<void>;
  close(): void;
  onEvent(handler: SSEEventHandler<T>): void;
  onError(handler: SSEErrorHandler): void;
  onComplete(handler: () => void): void;
}

/**
 * Web 端 SSE 实现（使用 fetch + ReadableStream）
 */
class WebSSEAdapter<T = unknown> implements ISSEAdapter<T> {
  private url: string;
  private options: SSEOptions;
  private eventHandlers: SSEEventHandler<T>[] = [];
  private errorHandlers: SSEErrorHandler[] = [];
  private completeHandlers: (() => void)[] = [];
  private controller: AbortController | null = null;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;

  constructor(url: string, options: SSEOptions = {}) {
    this.url = url;
    this.options = {
      method: 'POST',
      timeout: 300000, // 5 分钟
      ...options,
    };
  }

  async connect(): Promise<void> {
    this.controller = new AbortController();

    const token = getToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...this.options.headers,
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await fetch(this.url, {
        method: this.options.method,
        headers,
        body: this.options.body ? JSON.stringify(this.options.body) : undefined,
        signal: this.controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      this.reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await this.reader.read();

        if (done) {
          this.notifyComplete();
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 事件
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // 保留不完整的行

        for (const line of lines) {
          this.parseSSELine(line);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        // 正常关闭，不报错
        return;
      }
      this.notifyError(error instanceof Error ? error : new Error(String(error)));
    }
  }

  private parseSSELine(line: string): void {
    // SSE 格式: data: {...}
    if (line.startsWith('data: ')) {
      const data = line.slice(6);
      if (data === '[DONE]') {
        this.notifyComplete();
        return;
      }

      try {
        const event = JSON.parse(data) as T;
        this.notifyEvent(event);
      } catch {
        // 非 JSON 数据，直接传递
        this.notifyEvent(data as unknown as T);
      }
    }
    // 事件类型: event: xxx
    else if (line.startsWith('event: ')) {
      // 可以处理不同类型的事件
    }
  }

  close(): void {
    this.controller?.abort();
    this.reader?.cancel();
    this.controller = null;
    this.reader = null;
  }

  onEvent(handler: SSEEventHandler<T>): void {
    this.eventHandlers.push(handler);
  }

  onError(handler: SSEErrorHandler): void {
    this.errorHandlers.push(handler);
  }

  onComplete(handler: () => void): void {
    this.completeHandlers.push(handler);
  }

  private notifyEvent(event: T): void {
    this.eventHandlers.forEach(handler => handler(event));
  }

  private notifyError(error: Error): void {
    this.errorHandlers.forEach(handler => handler(error));
  }

  private notifyComplete(): void {
    this.completeHandlers.forEach(handler => handler());
  }
}

/**
 * 桌面端 SSE 实现（通过 Tauri HTTP 客户端）
 */
class TauriSSEAdapter<T = unknown> implements ISSEAdapter<T> {
  private url: string;
  private options: SSEOptions;
  private eventHandlers: SSEEventHandler<T>[] = [];
  private errorHandlers: SSEErrorHandler[] = [];
  private completeHandlers: (() => void)[] = [];
  private isActive = false;

  constructor(url: string, options: SSEOptions = {}) {
    this.url = url;
    this.options = options;
  }

  async connect(): Promise<void> {
    if (!isTauri()) {
      throw new Error('TauriSSEAdapter can only be used in Tauri environment');
    }

    this.isActive = true;
    const { invoke } = await import('@tauri-apps/api/core');

    try {
      const token = getToken();

      // 调用 Rust 后端的 SSE 流式请求
      await invoke('sse_connect', {
        url: this.url,
        options: {
          method: this.options.method || 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            ...this.options.headers,
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: this.options.body,
          timeout: this.options.timeout,
        },
      });
    } catch (error) {
      this.notifyError(error instanceof Error ? error : new Error(String(error)));
    }
  }

  /**
   * 处理从 Rust 后端推送的事件
   * 通过 Tauri 事件系统调用
   */
  handleEvent(event: T): void {
    if (this.isActive) {
      this.notifyEvent(event);
    }
  }

  close(): void {
    this.isActive = false;
    this.notifyComplete();
  }

  onEvent(handler: SSEEventHandler<T>): void {
    this.eventHandlers.push(handler);
  }

  onError(handler: SSEErrorHandler): void {
    this.errorHandlers.push(handler);
  }

  onComplete(handler: () => void): void {
    this.completeHandlers.push(handler);
  }

  private notifyEvent(event: T): void {
    this.eventHandlers.forEach(handler => handler(event));
  }

  private notifyError(error: Error): void {
    this.errorHandlers.forEach(handler => handler(error));
  }

  private notifyComplete(): void {
    this.completeHandlers.forEach(handler => handler());
  }
}

/**
 * 创建 SSE 适配器
 */
export function createSSEAdapter<T = unknown>(
  url: string,
  options?: SSEOptions
): ISSEAdapter<T> {
  if (isTauri()) {
    return new TauriSSEAdapter<T>(url, options);
  }
  return new WebSSEAdapter<T>(url, options);
}

/**
 * AI 对话流式响应接口
 */
export interface ChatStreamEvent {
  /** 内容片段 */
  content?: string;
  /** 是否结束 */
  done?: boolean;
  /** 错误信息 */
  error?: string;
  /** 消息 ID */
  message_id?: string;
}

/**
 * 连接 AI 对话流
 */
export async function connectChatStream(
  sessionId: string,
  content: string,
  onChunk: (chunk: string) => void,
  onComplete?: (messageId?: string) => void,
  onError?: (error: Error) => void
): Promise<ISSEAdapter<ChatStreamEvent>> {
  const url = `${BASE_URL}/api/chat/stream`;

  const adapter = createSSEAdapter<ChatStreamEvent>(url, {
    method: 'POST',
    body: {
      session_id: sessionId,
      content,
    },
  });

  adapter.onEvent((event) => {
    if (event.error) {
      onError?.(new Error(event.error));
      return;
    }

    if (event.content) {
      onChunk(event.content);
    }

    if (event.done) {
      onComplete?.(event.message_id);
    }
  });

  adapter.onError((error) => {
    onError?.(error);
  });

  // 开始连接（非阻塞）
  adapter.connect().catch((error) => {
    onError?.(error);
  });

  return adapter;
}

/**
 * 任务日志流式响应接口
 */
export interface TaskLogEvent {
  /** 日志内容 */
  log?: string;
  /** 进度 */
  progress?: number;
  /** 状态 */
  status?: string;
  /** 是否结束 */
  done?: boolean;
}

/**
 * 连接任务日志流
 */
export async function connectTaskLogStream(
  taskId: string,
  onLog: (log: string) => void,
  onProgress?: (progress: number) => void,
  onComplete?: () => void
): Promise<ISSEAdapter<TaskLogEvent>> {
  const url = `${BASE_URL}/api/tasks/${taskId}/logs/stream`;

  const adapter = createSSEAdapter<TaskLogEvent>(url, {
    method: 'GET',
  });

  adapter.onEvent((event) => {
    if (event.log) {
      onLog(event.log);
    }

    if (event.progress !== undefined && onProgress) {
      onProgress(event.progress);
    }

    if (event.done) {
      onComplete?.();
    }
  });

  adapter.connect().catch(console.error);

  return adapter;
}