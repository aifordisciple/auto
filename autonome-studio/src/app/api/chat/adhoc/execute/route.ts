/**
 * BFF 代理：即席分析执行端点
 *
 * 接收前端 AdhocAnalysisCard 的执行请求，提取 JWT（优先 Authorization header，
 * 回退到 access_token Cookie），转发到 FastAPI 后端，透传 SSE 流响应。
 *
 * 为什么需要 BFF 代理：
 * - 前端直接跨域调用后端时，httpOnly Cookie 不会被自动发送（需要 credentials:'include'
 *   触发 CORS 预检，容易因 Origin 不匹配被浏览器拦截）
 * - BFF 与前端同源，可直接读取 Cookie，彻底避免 CORS 问题
 */
import { NextRequest } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const authHeader = req.headers.get('authorization');
    const token = authHeader?.replace('Bearer ', '') ||
      req.cookies.get('access_token')?.value || '';

    const backendResponse = await fetch(`${BACKEND_URL}/api/chat/adhoc/execute`, {
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

    // 透传 SSE 流响应
    return new Response(backendResponse.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
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
