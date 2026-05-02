import { renderHook, act } from '@testing-library/react';
import { useClaudeChat } from '@/hooks/useClaudeChat';

// Mock useClaudeStore
jest.mock('@/store/useClaudeStore', () => ({
  useClaudeStore: () => ({
    activeSessionId: 'test-sid',
    activeConversationId: 'test-cid',
    isStreaming: false,
    streamEvents: [],
    addMessage: jest.fn(),
    appendStreamContent: jest.fn(),
    setStreaming: jest.fn(),
    resetStream: jest.fn(),
    messages: [],
    setMessages: jest.fn(),
  }),
}));

/**
 * Create a mock fetch Response that works for BOTH paths:
 * - fetchAPI path: calls response.json(), hook uses the parsed result
 * - native fetch path: hook uses response directly
 *
 * The .json() returns an object with body.getReader() so that
 * the hook code can stream regardless of which path was used.
 */
function createMockResponse(reader: any) {
  const streamResult = {
    ok: true,
    body: { getReader: () => reader },
  };
  return {
    ok: true,
    status: 200,
    body: { getReader: () => reader },
    json: () => Promise.resolve(streamResult),
  };
}

describe('useClaudeChat sendMessage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('uses raw fetch (not fetchAPI) for SSE endpoint to preserve response.body', async () => {
    const mockReader = {
      read: jest.fn()
        .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('event: session_info\ndata: {"type":"session_info"}\n\n') })
        .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('event: status\ndata: {"type":"status","status":"idle"}\n\n') })
        .mockResolvedValueOnce({ done: true }),
      cancel: jest.fn(),
    };

    const mockResponse = createMockResponse(mockReader);
    global.fetch = jest.fn().mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useClaudeChat());
    await act(async () => {
      await result.current.sendMessage('test message');
    });

    // Verify raw fetch was called with SSE endpoint URL
    expect(global.fetch).toHaveBeenCalled();
    const callUrl = (global.fetch as jest.Mock).mock.calls[0][0];
    expect(callUrl).toContain('/api/claude/sessions/test-sid/conversations/test-cid/messages');
  });

  it('does not use fetchAPI (which calls .json()) for SSE', async () => {
    // fetchAPI should NOT be called for the SSE POST during sendMessage
    const fetchAPIModule = await import('@/lib/api');
    const fetchAPISpy = jest.spyOn(fetchAPIModule, 'fetchAPI');

    const mockReader = {
      read: jest.fn().mockResolvedValue({ done: true }),
      cancel: jest.fn(),
    };

    const mockResponse = createMockResponse(mockReader);
    global.fetch = jest.fn().mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useClaudeChat());
    await act(async () => {
      await result.current.sendMessage('hello');
    });

    // fetchAPI should NOT be called for the SSE POST endpoint
    const sseCallArgs = fetchAPISpy.mock.calls.filter(
      args => typeof args[0] === 'string' && args[0].includes('/messages')
    );
    expect(sseCallArgs).toHaveLength(0);
  }, 10000);
});
