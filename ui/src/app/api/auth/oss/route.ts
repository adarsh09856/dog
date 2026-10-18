/*
  Provides the OSS session to LocalProviderWrapper once loaded in the browser.
  The cached user cookie is only a display cache: authorization fields must be
  refreshed from the API so a changed role cannot leave stale admin controls.
*/
import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { getAuthProvider } from '@/lib/auth/config';
import {
  LEGACY_OSS_TOKEN_COOKIE,
  LEGACY_OSS_USER_COOKIE,
  OSS_TOKEN_COOKIE,
  OSS_USER_COOKIE,
} from '@/lib/auth/cookies';
import { getServerBackendUrl } from '@/lib/apiClient';

export async function GET() {
  const authProvider = await getAuthProvider();

  if (authProvider !== 'local') {
    return NextResponse.json({ error: 'Not in OSS mode' }, { status: 400 });
  }

  const cookieStore = await cookies();
  const token =
    cookieStore.get(OSS_TOKEN_COOKIE)?.value ||
    cookieStore.get(LEGACY_OSS_TOKEN_COOKIE)?.value;
  const cachedUserValue =
    cookieStore.get(OSS_USER_COOKIE)?.value ||
    cookieStore.get(LEGACY_OSS_USER_COOKIE)?.value;

  if (!token) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  let cachedUser: Record<string, unknown> = {};
  if (cachedUserValue) {
    try {
      const parsed = JSON.parse(cachedUserValue);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        cachedUser = parsed as Record<string, unknown>;
      }
    } catch {
      // The cookie is a convenience cache, never the source of authorization.
    }
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${getServerBackendUrl()}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json(
      { error: 'Unable to verify the current user. Please retry.' },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  if (backendResponse.status === 401 || backendResponse.status === 403) {
    return NextResponse.json(
      { error: 'Not authenticated' },
      { status: 401, headers: { 'Cache-Control': 'no-store' } },
    );
  }
  if (!backendResponse.ok) {
    return NextResponse.json(
      { error: 'Unable to verify the current user. Please retry.' },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  let currentUser: Record<string, unknown>;
  try {
    const payload = await backendResponse.json();
    currentUser = (payload?.user ?? payload) as Record<string, unknown>;
    if (!currentUser || typeof currentUser !== 'object' || Array.isArray(currentUser)) {
      throw new Error('Invalid current-user response');
    }
  } catch {
    return NextResponse.json(
      { error: 'Unable to verify the current user. Please retry.' },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    );
  }

  // Keep non-authoritative display fields from the login cache, while always
  // taking role, identity and organization fields from the authenticated API.
  const user = {
    ...cachedUser,
    ...currentUser,
    is_superuser: currentUser.is_superuser === true,
  };

  return NextResponse.json(
    { token, user },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
