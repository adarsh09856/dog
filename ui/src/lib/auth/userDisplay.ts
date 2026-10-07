import type { AuthUser } from './types';

export function getUserEmail(user: AuthUser | null | undefined): string | null {
  if (!user) return null;
  return 'primaryEmail' in user ? user.primaryEmail : user.email || null;
}
