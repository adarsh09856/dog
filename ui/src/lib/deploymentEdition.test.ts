import { describe, expect, it } from 'vitest';

import { isHiddenInClientEdition } from './deploymentEdition';

describe('client edition route visibility', () => {
  it('hides owner control-plane routes', () => {
    expect(isHiddenInClientEdition('/admin', 'client')).toBe(true);
    expect(isHiddenInClientEdition('/admin/models', 'client')).toBe(true);
    expect(isHiddenInClientEdition('/superadmin/runs', 'client')).toBe(true);
  });

  it('keeps tenant application routes and SaaS owner routes available', () => {
    expect(isHiddenInClientEdition('/workflow', 'client')).toBe(false);
    expect(isHiddenInClientEdition('/settings', 'client')).toBe(false);
    expect(isHiddenInClientEdition('/admin', 'saas')).toBe(false);
  });
});
