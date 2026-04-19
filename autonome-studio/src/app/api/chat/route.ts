/**
 * BFF 代理：主聊天流
 *
 * 接收前端 useChat 的标准 payload，注入 JWT 和上下文，
 * 转发到 FastAPI 后端，透传 Vercel Data Stream 响应。
 */
import { NextRequest } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { messages, data: contextData } = body;

    const authHeader = req.headers.get('authorization');
    const token = authHeader?.replace('Bearer ', '') ||
      req.cookies.get('autonome_access_token')?.value || '';

    const projectId = contextData?.projectId || '';
    const sessionId = contextData?.sessionId || null;
    const contextFiles = contextData?.contextFiles || [];
    const skillId = contextData?.skillId || null;
    const images = contextData?.images || [];

    const lastUserMessage = messages
      ?.filter((m: { role: string }) => m.role === 'user')
      ?.pop()?.content || '';

    const backendResponse = await fetch(`${BACKEND_URL}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        project_id: projectId,
        message: lastUserMessage,
        context_files: contextFiles,
        session_id: sessionId,
        skill_id: skillId,
        images,
      }),
    });

    if (!backendResponse.ok) {
      if (backendResponse.status === 402) {
        const errorText = await backendResponse.text();
        return new Response(`3:${JSON.stringify(errorText)}\n`, {
          status: 200,
          headers: { 'Content-Type': 'text/plain; charset=utf-8' },
        });
      }
      const errorText = await backendResponse.text();
      return new Response(JSON.stringify({ error: errorText }), {
        status: backendResponse.status,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(backendResponse.body, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'no-cache',
      },
    });

  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
