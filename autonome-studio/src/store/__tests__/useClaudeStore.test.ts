import { describe, it, expect, beforeEach } from 'vitest';
import { useClaudeStore } from '../useClaudeStore';

describe('useClaudeStore', () => {
  beforeEach(() => {
    useClaudeStore.setState({
      sessions: [],
      activeSessionId: null,
      conversations: [],
      activeConversationId: null,
      messages: [],
      isStreaming: false,
      streamEvents: [],
    });
  });

  it('初始状态正确', () => {
    const state = useClaudeStore.getState();
    expect(state.sessions).toEqual([]);
    expect(state.activeSessionId).toBeNull();
    expect(state.isStreaming).toBe(false);
    expect(state.streamEvents).toEqual([]);
  });

  it('addSession 添加会话到列表', () => {
    const session = {
      id: 'sess-1', title: '测试会话', status: 'active' as const,
      createdAt: '2026-01-01', updatedAt: '2026-01-01',
    };
    useClaudeStore.getState().addSession(session);
    expect(useClaudeStore.getState().sessions).toHaveLength(1);
    expect(useClaudeStore.getState().sessions[0].id).toBe('sess-1');
  });

  it('removeSession 从列表中删除会话', () => {
    useClaudeStore.setState({ sessions: [
      { id: 'sess-1', title: 'A', status: 'active', createdAt: '', updatedAt: '' },
      { id: 'sess-2', title: 'B', status: 'active', createdAt: '', updatedAt: '' },
    ]});
    useClaudeStore.getState().removeSession('sess-1');
    expect(useClaudeStore.getState().sessions).toHaveLength(1);
    expect(useClaudeStore.getState().sessions[0].id).toBe('sess-2');
  });

  it('appendStreamContent 逐个追加事件', () => {
    useClaudeStore.getState().appendStreamContent({ type: 'text_delta', content: 'hello', timestamp: 1 });
    useClaudeStore.getState().appendStreamContent({ type: 'text_delta', content: ' world', timestamp: 2 });
    expect(useClaudeStore.getState().streamEvents).toHaveLength(2);
  });

  it('resetStream 清空事件和 isStreaming', () => {
    useClaudeStore.setState({ streamEvents: [{ type: 'text_delta', content: 'x', timestamp: 1 }], isStreaming: true });
    useClaudeStore.getState().resetStream();
    expect(useClaudeStore.getState().streamEvents).toEqual([]);
    expect(useClaudeStore.getState().isStreaming).toBe(false);
  });
});
