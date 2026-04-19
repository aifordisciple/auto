/**
 * BFF 代理：队列流
 *
 * 接收前端的队列流请求，注入 JWT，转发到 FastAPI 后端，
 * 透传 SSE 流式响应。
 */
import { NextRequest } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { sessionId, projectId } = body;

    const authHeader = req.headers.get('authorization');
    const token = authHeader?.replace('Bearer ', '') ||
      req.cookies.get('autonome_access_token')?.value || '';

    const backendResponse = await fetch(`${BACKEND_URL}/api/chat/stream/queue`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ session_id: sessionId, project_id: projectId }),
    });

    if (!backendResponse.ok) {
      return new Response(await backendResponse.text(), { status: backendResponse.status });
    }

    return new Response(backendResponse.body, {
      headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-cache' },
    });

  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
