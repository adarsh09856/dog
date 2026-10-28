export type ClientFeature =
  | "voice"
  | "telephony"
  | "campaigns"
  | "crm"
  | "appointments"
  | "forms"
  | "widgets"
  | "knowledge_base"
  | "billing";

const FEATURED_PATHS: Array<[string, ClientFeature]> = [
  ["/appointments", "appointments"],
  ["/api-keys", "voice"],
  ["/billing", "billing"],
  ["/billing-sovereign", "billing"],
  ["/campaigns", "campaigns"],
  ["/crm", "crm"],
  ["/files", "knowledge_base"],
  ["/forms", "forms"],
  ["/model-configurations", "voice"],
  ["/overview", "voice"],
  ["/prompt-templates", "voice"],
  ["/recordings", "voice"],
  ["/reports", "voice"],
  ["/telephony-configurations", "telephony"],
  ["/tools", "voice"],
  ["/usage", "voice"],
  ["/widgets", "widgets"],
  ["/workflow", "voice"],
];

export function requiredFeatureForUiPath(pathname: string): ClientFeature | null {
  return FEATURED_PATHS.find(
    ([prefix]) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )?.[1] ?? null;
}
