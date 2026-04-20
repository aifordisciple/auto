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
    const pastedFiles = contextData?.pastedFiles || [];  // ✨ 粘贴上传的文件路径（如PDF）
    // ✨ 深度思考开关：从 transport body 读取并转发给后端
    const enableThink = contextData?.enableThink || false;

    // v5 UIMessage 使用 parts[] 而非 content 字符串
    // 从最后一条用户消息的 parts 中提取文本
    const lastUserMsg = messages?.filter((m: { role: string }) => m.role === 'user')?.pop();
    let lastUserMessage = '';
    if (lastUserMsg) {
      if (lastUserMsg.content) {
        // 兼容 v4 格式
        lastUserMessage = lastUserMsg.content;
      } else if (lastUserMsg.parts) {
        // v5 UIMessage 格式：从 parts 中提取文本
        lastUserMessage = lastUserMsg.parts
          .filter((p: { type: string }) => p.type === 'text')
          .map((p: { type: string; text: string }) => p.text)
          .join('');
      }
    }

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
        pasted_files: pastedFiles,  // ✨ 粘贴上传的文件路径（如PDF）
        enable_think: enableThink,
      }),
    });

    if (!backendResponse.ok) {
      // 402 余额不足：恢复标准 HTTP 语义，让前端 onError 正确捕获
      // 不再将业务错误伪装为 200 SSE 事件，避免监控系统盲区和静默失败
      const errorText = await backendResponse.text();
      return new Response(errorText, {
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
