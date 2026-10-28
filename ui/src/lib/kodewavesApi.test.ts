import { afterEach, describe, expect, it, vi } from 'vitest';

import { client } from '@/client/client.gen';

import { setupAuthInterceptor } from './apiClient';
import { apiFetch, normalizePublicCreditPackage } from './kodewavesApi';

afterEach(() => vi.unstubAllGlobals());

describe('panel API transport', () => {
  it('preserves configured top-up currency and amount without estimating FX', () => {
    expect(normalizePublicCreditPackage({
      id: 'growth', name: 'Growth', minutes: 500, bonus_minutes: 50,
      price_cents: 199900, currency: 'INR', is_popular: false,
    })).toEqual({
      id: 'growth', name: 'Growth', minutes: 500, bonus_minutes: 50,
      price_cents: 199900, currency: 'INR', is_popular: false, is_active: true,
    });
    expect(normalizePublicCreditPackage({
      id: 'usd', name: 'USD Pack', minutes: 100, bonus_minutes: 0,
      price_cents: 2499, currency: 'USD', is_popular: true,
    })).toMatchObject({ price_cents: 2499, currency: 'USD', is_popular: true });
  });

  it('uses the configured backend and fresh auth token, ignoring stale local storage', async () => {
    client.setConfig({ baseUrl: 'https://api.example.test' });
    localStorage.setItem('kodewaves_auth_token', 'stale-local-token');
    setupAuthInterceptor(client, async () => 'current-stack-token');
    const fetchMock = vi.fn(async (request: Request) => {
      void request;
      return Response.json({ ok: true });
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiFetch('/crm/contacts')).resolves.toEqual({ ok: true });
    const request = fetchMock.mock.calls[0][0] as unknown as Request;
    expect(request.url).toBe('https://api.example.test/api/v1/crm/contacts');
    expect(request.headers.get('Authorization')).toBe('Bearer current-stack-token');
    setupAuthInterceptor(client, async () => 'refreshed-token');
    await apiFetch('/crm/contacts');
    expect((fetchMock.mock.calls[1][0] as unknown as Request).headers.get('Authorization')).toBe('Bearer refreshed-token');
  });

  it('preserves JSON request bodies and accepts empty successful deletes', async () => {
    const fetchMock = vi.fn(async (request: Request) => {
      void request;
      return new Response(null, { status: 204 });
    });
    vi.stubGlobal('fetch', fetchMock);
    await apiFetch('/forms/example', { method: 'DELETE', body: JSON.stringify({ name: 'Example' }) });
    expect(await fetchMock.mock.calls[0][0].text()).toBe('{"name":"Example"}');
  });

  it('turns validation errors into readable failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ detail: [{ msg: 'Invalid phone' }] }, { status: 422 })));
    await expect(apiFetch('/crm/contacts')).rejects.toThrow('Invalid phone');
  });
});
