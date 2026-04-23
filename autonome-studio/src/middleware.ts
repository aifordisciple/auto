/**
 * Next.js 路由中间件 — 前端路由守卫
 *
 * 设计日期: 2026-04-23
 *
 * 功能：
 * - 检查 authenticated Cookie 判断用户是否已登录
 * - 未登录用户访问受保护路由 → 重定向到 /login
 * - 已登录用户访问登录/注册页 → 重定向到 /
 * - 公开路由直接放行
 *
 * Cookie 说明：
 * - authenticated: 由后端 set_auth_cookies() 设置，非 HttpOnly，Path=/
 * - 登出时由 clear_auth_cookies() 删除
 */

import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/** 不需要登录即可访问的公开路由前缀 */
const PUBLIC_ROUTES = [
  '/login',
  '/register',
  '/forgot-password',
  '/verify-email',
  '/api',       // API 路由由后端鉴权
  '/_next',     // Next.js 内部资源
  '/favicon',
];

/** 已登录用户不应再访问的路由（如登录页） */
const AUTH_ROUTES = [
  '/login',
  '/register',
  '/forgot-password',
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isAuthenticated = request.cookies.get('authenticated')?.value === '1';

  // 公开路由直接放行
  if (PUBLIC_ROUTES.some(route => pathname.startsWith(route))) {
    // 已登录用户访问登录/注册页 → 重定向到首页
    if (isAuthenticated && AUTH_ROUTES.some(route => pathname.startsWith(route))) {
      return NextResponse.redirect(new URL('/', request.url));
    }
    return NextResponse.next();
  }

  // 非公开路由：未登录 → 重定向到登录页
  if (!isAuthenticated) {
    const loginUrl = new URL('/login', request.url);
    // 保存原始路径，登录成功后可跳回
    loginUrl.searchParams.set('redirect', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // 匹配所有路由，排除静态资源
  matcher: [
    '/((?!_next/static|_next/image|.*\\.(?:ico|png|jpg|jpeg|gif|svg|woff|woff2)).*)',
  ],
};
