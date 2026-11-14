import { describe, expect, it } from 'vitest';

import { isHiddenInClientEdition } from './deploymentEdition';

describe('client edition route visibility', () => {
  it('keeps customer admin routes in client installations and hides the owner console', () => {
    expect(isHiddenInClientEdition('/admin', 'client')).toBe(false);
    expect(isHiddenInClientEdition('/admin/settings', 'client')).toBe(false);
    expect(isHiddenInClientEdition('/superadmin', 'client')).toBe(true);
    expect(isHiddenInClientEdition('/superadmin/models', 'client')).toBe(true);
    expect(isHiddenInClientEdition('/superadmin/runs', 'client')).toBe(true);
  });

  it('hides hosted SaaS billing surfaces but keeps a client pricing explanation', () => {
    expect(isHiddenInClientEdition('/pricing', 'client')).toBe(false);
    expect(isHiddenInClientEdition('/billing', 'client')).toBe(true);
    expect(isHiddenInClientEdition('/billing-sovereign', 'client')).toBe(true);
    expect(isHiddenInClientEdition('/billing-sovereign/checkout', 'client')).toBe(true);
  });

  it('keeps tenant application routes and SaaS marketing routes available', () => {
    expect(isHiddenInClientEdition('/workflow', 'client')).toBe(false);
    expect(isHiddenInClientEdition('/settings', 'client')).toBe(false);
    expect(isHiddenInClientEdition('/pricing', 'saas')).toBe(false);
    expect(isHiddenInClientEdition('/admin', 'saas')).toBe(false);
    expect(isHiddenInClientEdition('/superadmin', 'saas')).toBe(false);
  });
});
