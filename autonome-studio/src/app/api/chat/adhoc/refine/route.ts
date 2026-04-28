/**
 * BFF 代理：即席分析策略包对话式修改端点
 *
 * 接收前端 AdhocAnalysisCard 的策略修改请求，提取 JWT（优先 httpOnly Cookie，
 * 回退到 Authorization header），转发到 FastAPI 后端，返回更新后的策略包 JSON。
 *
 * 与 execute 端点不同，refine 返回 JSON（非 SSE 流），因此直接透传 JSON 响应。
 */
import { NextRequest } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const authHeader = req.headers.get('authorization');
    const token = req.cookies.get('access_token')?.value ||
      authHeader?.replace('Bearer ', '') || '';

    const backendResponse = await fetch(`${BACKEND_URL}/api/chat/adhoc/refine`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      return new Response(errorText, {
        status: backendResponse.status,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const data = await backendResponse.json();
    return new Response(JSON.stringify(data), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
