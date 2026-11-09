export type ClientFeature =
  | "voice"
  | "telephony"
  | "campaigns"
  | "crm"
  | "appointments"
  | "forms"
  | "widgets"
  | "knowledge_base"
  | "models"
  | "tools"
  | "recordings"
  | "prompt_templates"
  | "reports"
  | "integrations"
  | "billing";

const FEATURED_PATHS: Array<[string, ClientFeature]> = [
  ["/appointments", "appointments"],
  ["/api-keys", "integrations"],
  ["/billing", "billing"],
  ["/billing-sovereign", "billing"],
  ["/campaigns", "campaigns"],
  ["/crm", "crm"],
  ["/files", "knowledge_base"],
  ["/forms", "forms"],
  ["/model-configurations", "models"],
  ["/overview", "voice"],
  ["/prompt-templates", "prompt_templates"],
  ["/recordings", "recordings"],
  ["/reports", "reports"],
  ["/telephony-configurations", "telephony"],
  ["/tools", "tools"],
  ["/usage", "reports"],
  ["/widgets", "widgets"],
  ["/workflow", "voice"],
];

export function requiredFeatureForUiPath(pathname: string): ClientFeature | null {
  return FEATURED_PATHS.find(
    ([prefix]) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )?.[1] ?? null;
}
