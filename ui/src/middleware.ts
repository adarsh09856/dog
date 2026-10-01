import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

import { getServerBackendUrl } from '@/lib/apiClient';
import { LEGACY_OSS_TOKEN_COOKIE, OSS_TOKEN_COOKIE } from '@/lib/auth/cookies';

// Paths that don't require authentication in OSS mode.
// '/' (Landing page), '/pricing' (SaaS pricing), and '/embed' (widget) are public.
const PUBLIC_PATHS = ['/', '/pricing', '/auth/login', '/auth/signup', '/embed'];

let cachedAuthProvider: string | null = null;

async function fetchAuthProvider(): Promise<string> {
  if (cachedAuthProvider) {
    return cachedAuthProvider;
  }

  try {
    const backendUrl = getServerBackendUrl();
    const res = await fetch(`${backendUrl}/api/v1/health`);
    if (res.ok) {
      const data = await res.json();
      cachedAuthProvider = (data.auth_provider as string) || 'local';
      return cachedAuthProvider;
    }
  } catch {
    // Backend not reachable — fall through without caching so we retry next request.
  }

  return 'unknown';
}

export async function middleware(request: NextRequest) {
  const token =
    request.cookies.get(OSS_TOKEN_COOKIE)?.value ||
    request.cookies.get(LEGACY_OSS_TOKEN_COOKIE)?.value ||
    request.cookies.get('oss_token')?.value;

  // Strict server-side guard for /admin routes - must have token regardless of provider
  if (pathname === '/admin' || pathname.startsWith('/admin/')) {
    if (!token) {
      const loginUrl = new URL('/auth/login', request.url);
      loginUrl.searchParams.set('redirect', pathname);
      return NextResponse.redirect(loginUrl);
    }
  }

  // If logged-in user visits root landing page '/', smoothly direct to their dashboard
  if (pathname === '/' && token) {
    return NextResponse.redirect(new URL('/overview', request.url));
  }

  const authProvider = await fetchAuthProvider();

  // Only handle OSS mode for standard user routes
  if (authProvider !== 'local') {
    return NextResponse.next();
  }

  // Allow public paths without auth
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }

  // If no token, redirect to login
  if (!token) {
    const loginUrl = new URL('/auth/login', request.url);
    return NextResponse.redirect(loginUrl);
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
    '/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|otf)).*)',
  ],
};
