/**
 * useClaudeChat SSE 流接收测试
 *
 * 验证 sendMessage 使用原生 fetch（非 fetchAPI）以保留 Response.body，
 * 并对 SSE 事件进行正确的解析和 store 更新。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Mock useClaudeStore — 捕获 store 函数调用以验证行为
const storeAddMessage = vi.fn();
const storeAppendStreamContent = vi.fn();
const storeSetStreaming = vi.fn();
const storeResetStream = vi.fn();
const storeSetMessages = vi.fn();

vi.mock('@/store/useClaudeStore', () => ({
  useClaudeStore: () => ({
    activeSessionId: 'test-sid',
    activeConversationId: 'test-cid',
    isStreaming: false,
    streamEvents: [],
    addMessage: storeAddMessage,
    appendStreamContent: storeAppendStreamContent,
    setStreaming: storeSetStreaming,
    resetStream: storeResetStream,
    messages: [],
    setMessages: storeSetMessages,
  }),
}));

// Mock BASE_URL and getToken — capture token usage
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual('@/lib/api');
  return {
    ...(actual as object),
    fetchAPI: vi.fn(),
    BASE_URL: 'http://test.local:8000',
    getToken: vi.fn(() => null),
  };
});

function sseChunk(events: Array<{ event?: string; data: unknown }>): Uint8Array {
  const lines = events.flatMap((e) => {
    const result: string[] = [];
    if (e.event) result.push(`event: ${e.event}`);
    result.push(`data: ${typeof e.data === 'string' ? e.data : JSON.stringify(e.data)}`);
    result.push('');
    return result;
  });
  return new TextEncoder().encode(lines.join('\n'));
}

describe('useClaudeChat sendMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uses raw fetch for SSE endpoint to preserve response.body', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    const mockReader = {
      read: vi.fn()
        .mockResolvedValueOnce({ done: false, value: sseChunk([{ data: { type: 'session_info' } }]) })
        .mockResolvedValueOnce({ done: true }),
      cancel: vi.fn(),
    };
    fetchSpy.mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    } as unknown as Response);

    const { useClaudeChat } = await import('@/hooks/useClaudeChat');
    const { result } = renderHook(() => useClaudeChat());
    await act(async () => {
      await result.current.sendMessage('test message');
    });

    expect(fetchSpy).toHaveBeenCalled();
    const callUrl = (fetchSpy.mock.calls[0] as [string])[0];
    expect(callUrl).toContain('/api/claude/sessions/test-sid/conversations/test-cid/messages');
  });

  it('parses SSE events and calls appendStreamContent with correctly parsed data', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    const statusEvent = { type: 'status', status: 'typing', message: 'Claude is thinking', timestamp: 1 };
    const textDelta = { type: 'text_delta', content: 'Hello world', timestamp: 2 };
    const mockReader = {
      read: vi.fn()
        .mockResolvedValueOnce({ done: false, value: sseChunk([
          { data: { type: 'session_info' } },
          { event: 'status', data: statusEvent },
          { event: 'text_delta', data: textDelta },
        ]) })
        .mockResolvedValueOnce({ done: true }),
      cancel: vi.fn(),
    };
    fetchSpy.mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    } as unknown as Response);

    const { useClaudeChat } = await import('@/hooks/useClaudeChat');
    const { result } = renderHook(() => useClaudeChat());
    await act(async () => {
      await result.current.sendMessage('hello');
    });

    // session_info event is NOT passed to appendStreamContent
    // status and text_delta events ARE passed
    expect(storeAppendStreamContent).toHaveBeenCalledWith(statusEvent);
    expect(storeAppendStreamContent).toHaveBeenCalledWith(textDelta);
  });

  it('handles partial chunks split mid-line', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    // Simulate a chunk that ends mid-line — the buffer should wait for next chunk
    const part1 = new TextEncoder().encode('event: status\ndata: {"type":"status","status":"');
    const part2 = new TextEncoder().encode('typing"}\n\n');
    const mockReader = {
      read: vi.fn()
        .mockResolvedValueOnce({ done: false, value: part1 })
        .mockResolvedValueOnce({ done: false, value: part2 })
        .mockResolvedValueOnce({ done: true }),
      cancel: vi.fn(),
    };
    fetchSpy.mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    } as unknown as Response);

    const { useClaudeChat } = await import('@/hooks/useClaudeChat');
    const { result } = renderHook(() => useClaudeChat());
    await act(async () => {
      await result.current.sendMessage('test');
    });

    expect(storeAppendStreamContent).toHaveBeenCalledWith({
      type: 'status',
      status: 'typing',
    });
  });

  it('sets streaming false after stream completes', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch');
    const mockReader = {
      read: vi.fn().mockResolvedValue({ done: true }),
      cancel: vi.fn(),
    };
    fetchSpy.mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    } as unknown as Response);

    const { useClaudeChat } = await import('@/hooks/useClaudeChat');
    const { result } = renderHook(() => useClaudeChat());
    await act(async () => {
      await result.current.sendMessage('test');
    });

    expect(storeSetStreaming).toHaveBeenCalledWith(true);  // starts streaming
    expect(storeSetStreaming).toHaveBeenCalledWith(false); // ends streaming
  });
});
