import { isValidEmail } from "./isPersonalEmail";

// The OSS installer uses this address as its placeholder administrator login.
// It is not a real contact identity and should never be submitted implicitly.
const INSTALLER_PLACEHOLDER_EMAIL = "admin@admin.com";

export function getHireExpertEmailPrefill(email: string | null | undefined): string {
  const candidate = email?.trim() ?? "";
  if (!isValidEmail(candidate) || candidate.toLowerCase() === INSTALLER_PLACEHOLDER_EMAIL) {
    return "";
  }
  return candidate;
}
