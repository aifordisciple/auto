/**
 * BFF 代理：队列操作
 *
 * 统一代理前端对后端消息队列的 CRUD 操作，
 * 根据 action 字段路由到对应的后端端点。
 */
import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { action, sessionId, projectId, ...payload } = body;
    const token = req.cookies.get('autonome_access_token')?.value || '';

    let endpoint = '';
    let method = 'POST';
    let reqBody: unknown = null;

    switch (action) {
      case 'add':
        endpoint = `/api/chat/queue`;
        reqBody = { session_id: sessionId, project_id: projectId, ...payload };
        break;
      case 'status':
        endpoint = `/api/chat/queue/${sessionId}`;
        method = 'GET';
        break;
      case 'update':
        endpoint = `/api/chat/queue/${payload.itemId}`;
        method = 'PATCH';
        reqBody = payload.updates;
        break;
      case 'delete':
        endpoint = `/api/chat/queue/${payload.itemId}`;
        method = 'DELETE';
        break;
      case 'clear':
        endpoint = `/api/chat/queue/session/${sessionId}`;
        method = 'DELETE';
        break;
      case 'reorder':
        endpoint = `/api/chat/queue/reorder`;
        reqBody = { session_id: sessionId, item_ids: payload.itemIds };
        break;
      default:
        return NextResponse.json({ error: 'Unknown action' }, { status: 400 });
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };

    const backendResponse = await fetch(`${BACKEND_URL}${endpoint}`, {
      method,
      headers,
      ...(reqBody ? { body: JSON.stringify(reqBody) } : {}),
    });

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });

  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
