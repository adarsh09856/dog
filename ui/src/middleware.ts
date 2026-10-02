import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

import { LEGACY_OSS_TOKEN_COOKIE, OSS_TOKEN_COOKIE } from '@/lib/auth/cookies';

// Paths that don't require authentication.
// '/' (Landing page), '/pricing' (SaaS pricing), and '/embed' (widget) are public.
const PUBLIC_PATHS = ['/', '/pricing', '/auth', '/handler', '/embed'];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token =
    request.cookies.get(OSS_TOKEN_COOKIE)?.value ||
    request.cookies.get(LEGACY_OSS_TOKEN_COOKIE)?.value ||
    request.cookies.get('oss_token')?.value;

  // Strict server-side guard for /admin and /superadmin routes - must have token
  if (
    pathname === '/admin' ||
    pathname.startsWith('/admin/') ||
    pathname === '/superadmin' ||
    pathname.startsWith('/superadmin/')
  ) {
    if (!token) {
      const loginUrl = new URL('/auth/login', request.url);
      loginUrl.searchParams.set('redirect', pathname);
      return NextResponse.redirect(loginUrl);
    }
  }

  // Allow public paths without auth
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (isPublic) {
    return NextResponse.next();
  }

  // All other routes are private tenant application routes - require token
  if (!token) {
    const loginUrl = new URL('/auth/login', request.url);
    loginUrl.searchParams.set('redirect', pathname);
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
