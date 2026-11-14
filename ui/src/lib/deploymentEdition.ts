export function isOwnerControlPlanePath(pathname: string): boolean {
  return pathname === '/superadmin' || pathname.startsWith('/superadmin/');
}

export function isHostedSaasBillingPath(pathname: string): boolean {
  return ['/billing', '/billing-sovereign'].some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
}

export function isHiddenInClientEdition(pathname: string, edition?: string): boolean {
  return edition === 'client' && (
    isOwnerControlPlanePath(pathname) || isHostedSaasBillingPath(pathname)
  );
}
