import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

import { LEGACY_OSS_TOKEN_COOKIE, OSS_TOKEN_COOKIE } from '@/lib/auth/cookies';

// Paths that don't require authentication.
// '/' (Landing page), '/pricing' (SaaS pricing), '/embed' (widget), and '/widget.js' are public.
const PUBLIC_PATHS = ['/', '/pricing', '/auth', '/handler', '/embed', '/widget.js'];

function isTokenValid(token?: string): boolean {
  if (!token || typeof token !== 'string') return false;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return false;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    const payload = JSON.parse(jsonPayload);
    if (!payload || typeof payload !== 'object') return false;
    if (payload.exp && typeof payload.exp === 'number') {
      if (payload.exp * 1000 <= Date.now()) {
        return false;
      }
    }
    if (!payload.sub && !payload.user_id && !payload.id && !payload.email) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const rawToken =
    request.cookies.get(OSS_TOKEN_COOKIE)?.value ||
    request.cookies.get(LEGACY_OSS_TOKEN_COOKIE)?.value ||
    request.cookies.get('oss_token')?.value;

  const hasValidToken = isTokenValid(rawToken);

  // Strict server-side guard for /admin and /superadmin routes - must have valid token
  if (
    pathname === '/admin' ||
    pathname.startsWith('/admin/') ||
    pathname === '/superadmin' ||
    pathname.startsWith('/superadmin/')
  ) {
    if (!hasValidToken) {
      const loginUrl = new URL('/auth/login', request.url);
      loginUrl.searchParams.set('redirect', pathname);
      const res = NextResponse.redirect(loginUrl);
      if (rawToken) {
        res.cookies.delete(OSS_TOKEN_COOKIE);
        res.cookies.delete(LEGACY_OSS_TOKEN_COOKIE);
        res.cookies.delete('oss_token');
      }
      return res;
    }
  }

  // Allow public paths without auth
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (isPublic) {
    return NextResponse.next();
  }

  // All other routes are private tenant application routes - require valid token
  if (!hasValidToken) {
    const loginUrl = new URL('/auth/login', request.url);
    loginUrl.searchParams.set('redirect', pathname);
    const res = NextResponse.redirect(loginUrl);
    if (rawToken) {
      res.cookies.delete(OSS_TOKEN_COOKIE);
      res.cookies.delete(LEGACY_OSS_TOKEN_COOKIE);
      res.cookies.delete('oss_token');
    }
    return res;
  }

  return NextResponse.next();
}

// Configure which routes the middleware runs on
export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - api routes
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public static assets (anything with a file extension, e.g. /kodewaves-logo.png)
     */
    '/((?!api|_next/static|_next/image|favicon.ico|widget\\.js|.*\\.(?:png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|otf)).*)',
  ],
};
