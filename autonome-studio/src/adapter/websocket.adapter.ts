/**
 * WebSocket 适配器模块
 *
 * 提供统一的 WebSocket 连接接口，自动适配 Web 和桌面端
 */

import { isTauri } from './platform';

/**
 * WebSocket 连接选项
 */
export interface WebSocketOptions {
  /** 连接超时时间（毫秒） */
  timeout?: number;
  /** 重连次数 */
  maxReconnectAttempts?: number;
  /** 重连间隔（毫秒） */
  reconnectInterval?: number;
  /** 二进制模式 */
  binary?: boolean;
}

/**
 * WebSocket 消息回调
 */
export type WebSocketMessageHandler = (data: string | ArrayBuffer) => void;

/**
 * WebSocket 状态回调
 */
export type WebSocketStateHandler = (state: 'connected' | 'disconnected' | 'error') => void;

/**
 * WebSocket 适配器接口
 */
export interface IWebSocketAdapter {
  connect(): Promise<void>;
  send(data: string | ArrayBuffer): void;
  close(): void;
  onMessage(handler: WebSocketMessageHandler): void;
  onStateChange(handler: WebSocketStateHandler): void;
}

/**
 * Web 端 WebSocket 实现
 */
class WebWebSocketAdapter implements IWebSocketAdapter {
  private ws: WebSocket | null = null;
  private url: string;
  private options: WebSocketOptions;
  private messageHandlers: WebSocketMessageHandler[] = [];
  private stateHandlers: WebSocketStateHandler[] = [];
  private reconnectAttempts = 0;

  constructor(url: string, options: WebSocketOptions = {}) {
    this.url = url;
    this.options = {
      timeout: 10000,
      maxReconnectAttempts: 3,
      reconnectInterval: 1000,
      binary: false,
      ...options,
    };
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);

        if (this.options.binary) {
          this.ws.binaryType = 'arraybuffer';
        }

        const timeout = setTimeout(() => {
          reject(new Error('WebSocket connection timeout'));
          this.ws?.close();
        }, this.options.timeout);

        this.ws.onopen = () => {
          clearTimeout(timeout);
          this.reconnectAttempts = 0;
          this.notifyStateChange('connected');
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.messageHandlers.forEach(handler => handler(event.data));
        };

        this.ws.onclose = () => {
          this.notifyStateChange('disconnected');
          this.attemptReconnect();
        };

        this.ws.onerror = (error) => {
          clearTimeout(timeout);
          this.notifyStateChange('error');
          reject(error);
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  send(data: string | ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    } else {
      throw new Error('WebSocket is not connected');
    }
  }

  close(): void {
    this.reconnectAttempts = this.options.maxReconnectAttempts || 0;
    this.ws?.close();
  }

  onMessage(handler: WebSocketMessageHandler): void {
    this.messageHandlers.push(handler);
  }

  onStateChange(handler: WebSocketStateHandler): void {
    this.stateHandlers.push(handler);
  }

  private notifyStateChange(state: 'connected' | 'disconnected' | 'error'): void {
    this.stateHandlers.forEach(handler => handler(state));
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts < (this.options.maxReconnectAttempts || 0)) {
      this.reconnectAttempts++;
      setTimeout(() => {
        this.connect().catch(console.error);
      }, this.options.reconnectInterval);
    }
  }
}

/**
 * 桌面端 WebSocket 实现（通过 Tauri IPC）
 */
class TauriWebSocketAdapter implements IWebSocketAdapter {
  private url: string;
  private options: WebSocketOptions;
  private messageHandlers: WebSocketMessageHandler[] = [];
  private stateHandlers: WebSocketStateHandler[] = [];
  private sessionId: string | null = null;

  constructor(url: string, options: WebSocketOptions = {}) {
    this.url = url;
    this.options = options;
  }

  async connect(): Promise<void> {
    if (!isTauri()) {
      throw new Error('TauriWebSocketAdapter can only be used in Tauri environment');
    }

    const { invoke } = await import('@tauri-apps/api/core');

    try {
      this.sessionId = await invoke<string>('ws_connect', {
        url: this.url,
        options: this.options,
      });
      this.notifyStateChange('connected');

      // 开始监听消息
      this.startListening();
    } catch (error) {
      this.notifyStateChange('error');
      throw error;
    }
  }

  private async startListening(): Promise<void> {
    if (!this.sessionId) return;

    const { invoke } = await import('@tauri-apps/api/core');

    // 轮询获取消息（简化实现）
    // 实际项目中应使用 Tauri 事件系统
    const poll = async () => {
      while (this.sessionId) {
        try {
          const messages = await invoke<Array<string | number[]>>('ws_poll_messages', {
            sessionId: this.sessionId,
          });
          messages.forEach((msg: string | number[]) => {
            const data = typeof msg === 'string' ? msg : new Uint8Array(msg).buffer;
            this.messageHandlers.forEach(handler => handler(data));
          });
        } catch (error) {
          console.error('Error polling WebSocket messages:', error);
        }
        await new Promise(resolve => setTimeout(resolve, 50));
      }
    };

    poll();
  }

  async send(data: string | ArrayBuffer): Promise<void> {
    if (!this.sessionId) {
      throw new Error('WebSocket is not connected');
    }

    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('ws_send', {
      sessionId: this.sessionId,
      data: typeof data === 'string' ? data : Array.from(new Uint8Array(data)),
    });
  }

  async close(): Promise<void> {
    if (this.sessionId) {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('ws_close', { sessionId: this.sessionId });
      this.sessionId = null;
      this.notifyStateChange('disconnected');
    }
  }

  onMessage(handler: WebSocketMessageHandler): void {
    this.messageHandlers.push(handler);
  }

  onStateChange(handler: WebSocketStateHandler): void {
    this.stateHandlers.push(handler);
  }

  private notifyStateChange(state: 'connected' | 'disconnected' | 'error'): void {
    this.stateHandlers.forEach(handler => handler(state));
  }
}

/**
 * 创建 WebSocket 适配器
 */
export function createWebSocketAdapter(
  url: string,
  options?: WebSocketOptions
): IWebSocketAdapter {
  if (isTauri()) {
    return new TauriWebSocketAdapter(url, options);
  }
  return new WebWebSocketAdapter(url, options);
}

/**
 * 终端 WebSocket 连接
 *
 * 专门用于 Web 终端的 WebSocket 连接
 */
export async function connectTerminalWebSocket(
  projectId: string,
  cols: number,
  rows: number,
  onMessage: (data: ArrayBuffer) => void
): Promise<IWebSocketAdapter | null> {
  const token = localStorage.getItem('autonome_access_token');
  if (!token) {
    console.error('No auth token found');
    return null;
  }

  // 构建终端 WebSocket URL
  const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
  const port = 8000;

  const wsUrl = `${protocol}://${host}:${port}/api/terminal/ws/${projectId}?token=${token}&cols=${cols}&rows=${rows}`;

  const adapter = createWebSocketAdapter(wsUrl, { binary: true });

  adapter.onMessage((data) => {
    if (data instanceof ArrayBuffer) {
      onMessage(data);
    } else {
      onMessage(new TextEncoder().encode(data).buffer);
    }
  });

  try {
    await adapter.connect();
    return adapter;
  } catch (error) {
    console.error('Failed to connect terminal WebSocket:', error);
    return null;
  }
}