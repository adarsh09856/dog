// @vitest-environment node
import { beforeEach, expect, it, vi } from 'vitest';

const auth = vi.hoisted(() => ({ user: vi.fn(), token: vi.fn(), count: vi.fn() }));
vi.mock('@/lib/auth/server', () => ({
  getServerAuthProvider: async () => 'local',
  getServerUser: auth.user,
  getServerAccessToken: auth.token,
}));
vi.mock('@/client/sdk.gen', () => ({ getWorkflowCountApiV1WorkflowCountGet: auth.count }));
vi.mock('@/lib/utils', () => ({ getRedirectUrl: vi.fn() }));
vi.mock('@/lib/logger', () => ({ default: { debug: vi.fn(), error: vi.fn() } }));
vi.mock('next/navigation', () => ({ redirect: (path: string) => { throw new Error(`redirect:${path}`); } }));
vi.mock('next/dist/client/components/is-next-router-error', () => ({
  isNextRouterError: (error: Error) => error.message.startsWith('redirect:'),
}));
import { GET as Page } from './route';

beforeEach(() => { vi.clearAllMocks(); auth.user.mockResolvedValue({ id: 1 }); auth.token.mockResolvedValue('test'); });
it('sends absent sessions directly to login without querying workflows', async () => {
  auth.user.mockResolvedValue(null);
  await expect(Page()).rejects.toThrow('redirect:/auth/login');
  expect(auth.count).not.toHaveBeenCalled();
});
it('sends a user with a missing token to login', async () => {
  auth.token.mockResolvedValue(null);
  await expect(Page()).rejects.toThrow('redirect:/auth/login');
  expect(auth.count).not.toHaveBeenCalled();
});
it('keeps authenticated workflow routing', async () => {
  auth.count.mockResolvedValue({ data: { active: 1 } });
  await expect(Page()).rejects.toThrow('redirect:/workflow');
});
