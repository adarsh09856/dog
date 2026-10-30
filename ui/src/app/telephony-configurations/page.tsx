"use client";
import {
  AlertTriangle,
  ChevronRight,
  Copy,
  Pencil,
  PhoneCall,
  Plus,
  RotateCcw,
  ShieldCheck,
  Star,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
  deleteTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdDelete,
  getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet,
  listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet,
  reactivateTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdReactivatePost,
  setDefaultOutboundApiV1OrganizationsTelephonyConfigsConfigIdSetDefaultOutboundPost,
} from "@/client/sdk.gen";
import type {
  TelephonyConfigurationDetail,
  TelephonyConfigurationListItem,
} from "@/client/types.gen";
import { ConfigFormDialog } from "@/components/telephony/ConfigFormDialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTelephonyConfigWarnings } from "@/context/TelephonyConfigWarningsContext";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";
import { copyTextToClipboard } from "@/lib/clipboard";

import styles from "./TelephonyWorkspace.module.css";

export default function TelephonyConfigurationsPage() {
  const { user, getAccessToken, loading: authLoading } = useAuth();
  const searchParams = useSearchParams();
  const {
    telnyxMissingWebhookPublicKeyCount,
    vonageMissingSignatureSecretCount,
    refresh: refreshWarnings,
  } = useTelephonyConfigWarnings();
  const [items, setItems] = useState<TelephonyConfigurationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<TelephonyConfigurationDetail | null>(
    null,
  );
  const [editOpen, setEditOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] =
    useState<TelephonyConfigurationListItem | null>(null);

  const fetchItems = useCallback(async () => {
    if (authLoading || !user) return;
    setLoading(true);
    try {
      const token = await getAccessToken();
      const res = await listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet(
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (res.error) throw new Error(detailFromError(res.error));
      setItems(res.data?.configurations ?? []);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load configurations");
    } finally {
      setLoading(false);
    }
  }, [authLoading, user, getAccessToken]);

  // After a save (create/update), webhook-verification warning state may have
  // changed — refresh the cached warning state so the page banner and nav badge
  // update without a manual reload.
  const onSaved = useCallback(async () => {
    await fetchItems();
    await refreshWarnings();
  }, [fetchItems, refreshWarnings]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // ?add=1 lands the user straight on the provider form — used by the Phone
  // Call dialog's "Add provider" action so the choice isn't asked twice.
  useEffect(() => {
    if (searchParams.get("add") === "1") setCreateOpen(true);
  }, [searchParams]);

  const onEdit = async (item: TelephonyConfigurationListItem) => {
    try {
      const token = await getAccessToken();
      const res = await getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet(
        {
          headers: { Authorization: `Bearer ${token}` },
          path: { config_id: item.id },
        },
      );
      if (res.error) throw new Error(detailFromError(res.error));
      setEditTarget(res.data ?? null);
      setEditOpen(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load configuration");
    }
  };

  const onSetDefault = async (item: TelephonyConfigurationListItem) => {
    try {
      const token = await getAccessToken();
      const res = await setDefaultOutboundApiV1OrganizationsTelephonyConfigsConfigIdSetDefaultOutboundPost(
        {
          headers: { Authorization: `Bearer ${token}` },
          path: { config_id: item.id },
        },
      );
      if (res.error) throw new Error(detailFromError(res.error));
      toast.success(`${item.name} is now the default outbound configuration`);
      fetchItems();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to set default");
    }
  };

  const onReactivate = async (item: TelephonyConfigurationListItem) => {
    try {
      const token = await getAccessToken();
      const res = await reactivateTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdReactivatePost(
        {
          headers: { Authorization: `Bearer ${token}` },
          path: { config_id: item.id },
        },
      );
      if (res.error) throw new Error(detailFromError(res.error));
      toast.success(`${item.name} reactivated — reconnecting within a minute`);
      fetchItems();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to reactivate configuration",
      );
    }
  };

  const onConfirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      const token = await getAccessToken();
      const res = await deleteTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdDelete(
        {
          headers: { Authorization: `Bearer ${token}` },
          path: { config_id: deleteTarget.id },
        },
      );
      if (res.error) throw new Error(detailFromError(res.error));
      toast.success("Configuration deleted");
      setDeleteTarget(null);
      fetchItems();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete configuration");
    }
  };

  const phoneNumberCount = items.reduce((total, item) => total + (item.phone_number_count ?? 0), 0);
  const readyCount = items.filter((item) => !item.inactive && item.is_ready_for_outbound === true).length;
  const attentionCount = items.filter((item) => item.inactive || item.is_ready_for_outbound === false).length;

  return (
    <div className={styles.page}>
      <div className={styles.inner}>
        <header className={styles.hero}>
          <div className={styles.heroCopy}>
            <span className={styles.eyebrow}>CHANNELS / TELEPHONY</span>
            <h1>Telephony</h1>
            <p>
              Connect carriers, manage phone numbers, and choose the outbound account for your workflows.
            </p>
          </div>
          <Button className={styles.heroAction} onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-2" /> Add configuration
          </Button>
        </header>

        {telnyxMissingWebhookPublicKeyCount > 0 && (
          <div className={styles.warning}>
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
              <div className="space-y-1 text-sm">
                <p className="font-medium">Webhook public key not configured</p>
                <p>
                  {telnyxMissingWebhookPublicKeyCount === 1
                    ? "1 Telnyx configuration is"
                    : `${telnyxMissingWebhookPublicKeyCount} Telnyx configurations are`}{" "}
                  missing a webhook public key. Without it, Telnyx call status
                  updates and inbound calls are being rejected. Copy your
                  public key from{" "}
                  <span className="whitespace-nowrap">
                    Mission Control Portal → Keys &amp; Credentials → Public Key
                  </span>{" "}
                  and paste it into the affected Telnyx configuration below.
                </p>
              </div>
            </div>
          </div>
        )}

        {vonageMissingSignatureSecretCount > 0 && (
          <div className={styles.warning}>
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
              <div className="space-y-1 text-sm">
                <p className="font-medium">Signature secret not configured</p>
                <p>
                  {vonageMissingSignatureSecretCount === 1
                    ? "1 Vonage configuration is"
                    : `${vonageMissingSignatureSecretCount} Vonage configurations are`}{" "}
                  missing a signature secret. Without it, Vonage signed webhooks
                  are rejected, so inbound calls and call status updates will not
                  work. Copy the signature secret from your Vonage account and
                  paste it into the affected Vonage configuration below.
                </p>
              </div>
            </div>
          </div>
        )}

        <section aria-label="Telephony overview" className={styles.stats}>
          {[
            { label: "Provider accounts", value: loading ? "—" : items.length, icon: PhoneCall },
            { label: "Phone numbers", value: loading ? "—" : phoneNumberCount, icon: PhoneCall },
            { label: "Ready for outbound", value: loading ? "—" : readyCount, icon: ShieldCheck },
            { label: "Needs attention", value: loading ? "—" : attentionCount, icon: AlertTriangle },
          ].map(({ label, value, icon: Icon }) => (
            <div key={label} className={styles.stat}>
              <span className={styles.statIcon}><Icon className="size-4" aria-hidden="true" /></span>
              <div className="min-w-0"><p className={styles.statLabel}>{label}</p><p className={styles.statValue}>{value}</p></div>
            </div>
          ))}
        </section>

        {loading ? (
          <div className="grid gap-3" role="status" aria-label="Loading telephony configurations">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : items.length === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}><PhoneCall className="size-5" aria-hidden="true" /></span>
            <h2>No telephony configurations yet</h2>
            <p>Add a carrier account to connect phone numbers, place outbound calls, and receive inbound calls.</p>
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4 mr-2" /> Add configuration
            </Button>
          </div>
        ) : (
          <section aria-labelledby="provider-configurations-heading">
            <div className={styles.sectionHead}>
              <div><h2 id="provider-configurations-heading">Provider accounts</h2><p>Set the default outbound route and maintain inbound numbers for each carrier.</p></div>
              <Badge variant="outline">{items.length} {items.length === 1 ? "account" : "accounts"}</Badge>
            </div>
            <div className={styles.providerList}>
            {items.map((item) => (
              <Card key={item.id} className={styles.provider}>
                <CardContent className={styles.providerContent}>
                  <Link
                    href={`/telephony-configurations/${item.id}`}
                    className={styles.providerIdentity}
                  >
                    <span className={styles.providerMark}><PhoneCall className="size-5" aria-hidden="true" /></span>
                    <div className={styles.providerDetails}>
                      <div className={styles.providerTitle}>
                        <strong>{item.name}</strong>
                        <Badge variant="secondary">{item.provider}</Badge>
                        {item.is_default_outbound && (
                          <span className={styles.defaultMark}>
                            <Star className="h-3 w-3 fill-current" />
                            Default
                          </span>
                        )}
                        {item.inactive && (
                          <Badge variant="destructive">Inactive</Badge>
                        )}
                        {!item.inactive && item.is_ready_for_outbound === false && (
                          <Badge
                            variant="outline"
                            className="gap-1 border-amber-400 text-amber-700 dark:border-amber-700 dark:text-amber-400"
                          >
                            <AlertTriangle className="h-3 w-3" />
                            Setup incomplete
                          </Badge>
                        )}
                      </div>
                      <span className={styles.providerMeta}>
                        {item.phone_number_count} phone{" "}
                        {item.phone_number_count === 1 ? "number" : "numbers"}
                      </span>
                      {item.inactive && (
                        <span className={styles.providerMessage}>
                          Disabled after repeated connection failures
                          {item.inactive_reason ? `: ${item.inactive_reason}` : ""}
                        </span>
                      )}
                      {!item.inactive && item.outbound_blocked_reason && (
                        <span className={styles.providerMessage}>
                          {item.outbound_blocked_reason}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          copyTextToClipboard(String(item.id))
                            .then(() => toast.success("Configuration ID copied"))
                            .catch(() => toast.error("Failed to copy ID"));
                        }}
                        title="Click to copy"
                        className={styles.providerId}
                      >
                        <span className="truncate">Configuration ID: {item.id}</span>
                        <Copy className="h-3 w-3 shrink-0" />
                      </button>
                    </div>
                  </Link>
                  <div className={styles.providerActions}>
                    {item.inactive && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onReactivate(item)}
                        title="Reconnect this configuration now"
                      >
                        <RotateCcw className="h-4 w-4 mr-1" />
                        Reactivate
                      </Button>
                    )}
                    {!item.is_default_outbound && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onSetDefault(item)}
                        title="Set as default outbound"
                      >
                        <Star className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onEdit(item)}
                      title="Edit"
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeleteTarget(item)}
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                    <Button variant="outline" size="sm" asChild>
                      <Link
                        href={`/telephony-configurations/${item.id}`}
                        aria-label={`Manage phone numbers for ${item.name}`}
                      >
                        Manage Phone Numbers
                        <ChevronRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
            </div>
          </section>
        )}
      </div>

      <ConfigFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        existing={null}
        suggestDefaultOutbound={!items.some((item) => item.is_default_outbound)}
        onSaved={onSaved}
      />
      <ConfigFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        existing={editTarget}
        onSaved={onSaved}
      />

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete configuration?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget?.name} and all of its phone numbers will be removed. Any
              campaigns that reference this configuration will block the deletion until
              they are reassigned.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onConfirmDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
