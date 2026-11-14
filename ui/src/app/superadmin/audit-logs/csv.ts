import type { AuditLogItem } from "@/lib/kodewavesApi";

const csvCell = (value: unknown) => {
  const text = value == null ? "" : String(value);
  const formulaLike = /^[\u0000-\u0020]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text);
  const safeText = formulaLike ? `'${text}` : text;
  return `"${safeText.replace(/"/g, '""')}"`;
};

export function buildAuditLogsCsv(logs: AuditLogItem[]) {
  const headers = ["Timestamp", "Admin / Actor", "Action", "Target Resource", "Payload Details", "IP Address"];
  const rows = logs.map((log) => {
    const timestamp = log.created_at
      ? (() => {
          const parsed = new Date(log.created_at);
          return Number.isNaN(parsed.getTime()) ? log.created_at : parsed.toISOString();
        })()
      : "";
    return [
      timestamp,
      log.user_email || "System",
      log.action,
      log.target_resource,
      log.details ? JSON.stringify(log.details) : "",
      log.ip_address || "Unavailable",
    ];
  });
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
}
