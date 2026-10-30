export function isOwnerControlPlanePath(pathname: string): boolean {
  return (
    pathname === '/admin' || pathname.startsWith('/admin/') ||
    pathname === '/superadmin' || pathname.startsWith('/superadmin/')
  );
}

export function isHiddenInClientEdition(pathname: string, edition?: string): boolean {
  return edition === 'client' && isOwnerControlPlanePath(pathname);
}
