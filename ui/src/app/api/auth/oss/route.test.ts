// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest';

const cookieStore = { get: vi.fn() };
const fetchMock = vi.fn();
vi.mock('next/headers', () => ({ cookies: vi.fn(async () => cookieStore) }));
vi.mock('@/lib/auth/config', () => ({ getAuthProvider: vi.fn(async () => 'local') }));

import { LEGACY_OSS_TOKEN_COOKIE, LEGACY_OSS_USER_COOKIE, OSS_TOKEN_COOKIE, OSS_USER_COOKIE } from '@/lib/auth/cookies';
import { GET } from './route';

describe('GET /api/auth/oss', () => {
  beforeEach(() => {
    cookieStore.get.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    vi.stubEnv('BACKEND_URL', 'http://api:8000');
  });

  it('requires a session token', async () => {
    cookieStore.get.mockReturnValue(undefined);

    const response = await GET();

    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('uses the authenticated backend role instead of a stale admin cookie', async () => {
    cookieStore.get.mockImplementation((name: string) => {
      if (name === OSS_TOKEN_COOKIE) return { value: 'session-token' };
      if (name === OSS_USER_COOKIE) return { value: JSON.stringify({ id: 'old-user', is_superuser: true, name: 'Cached name' }) };
      return undefined;
    });
    fetchMock.mockResolvedValue(Response.json({ id: 'current-user', is_superuser: false, email: 'user@example.com' }));

    const response = await GET();
    const body = await response.json();

    expect(fetchMock).toHaveBeenCalledWith('http://api:8000/api/v1/auth/me', {
      headers: { Authorization: 'Bearer session-token' },
      cache: 'no-store',
    });
    expect(body.user).toMatchObject({ id: 'current-user', email: 'user@example.com', name: 'Cached name', is_superuser: false });
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('supports the legacy session cookies', async () => {
    cookieStore.get.mockImplementation((name: string) => {
      if (name === LEGACY_OSS_TOKEN_COOKIE) return { value: 'legacy-token' };
      if (name === LEGACY_OSS_USER_COOKIE) return { value: '{broken-json' };
      return undefined;
    });
    fetchMock.mockResolvedValue(Response.json({ id: 'legacy-user', is_superuser: true }));

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.user).toMatchObject({ id: 'legacy-user', is_superuser: true });
  });

  it('rejects an expired or unauthorized token', async () => {
    cookieStore.get.mockImplementation((name: string) => name === OSS_TOKEN_COOKIE ? { value: 'expired' } : undefined);
    fetchMock.mockResolvedValue(new Response(null, { status: 401 }));

    const response = await GET();

    expect(response.status).toBe(401);
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('fails closed when current role verification is unavailable', async () => {
    cookieStore.get.mockImplementation((name: string) => name === OSS_TOKEN_COOKIE
      ? { value: 'session-token' }
      : name === OSS_USER_COOKIE ? { value: JSON.stringify({ is_superuser: true }) } : undefined);
    fetchMock.mockResolvedValue(new Response(null, { status: 500 }));

    const response = await GET();

    expect(response.status).toBe(503);
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('fails closed if the backend cannot be reached', async () => {
    cookieStore.get.mockImplementation((name: string) => name === OSS_TOKEN_COOKIE ? { value: 'session-token' } : undefined);
    fetchMock.mockRejectedValue(new Error('network down'));

    const response = await GET();

    expect(response.status).toBe(503);
  });
});
