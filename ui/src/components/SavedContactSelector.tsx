"use client";

import { useEffect, useId, useState } from "react";
import { listContactsApiV1CrmContactsGet } from "@/client/sdk.gen";
import type { ContactItem } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function SavedContactSelector({ value, onSelect }: {
  value?: string | null;
  onSelect: (contact: ContactItem | null) => void;
}) {
  const { user, loading: authLoading } = useAuth();
  const inputId = useId();
  const [contacts, setContacts] = useState<ContactItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading || !user) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    listContactsApiV1CrmContactsGet().then(response => {
      if (cancelled) return;
      if (response.error) {
        setError("Saved contacts could not be loaded. You can enter details manually.");
        setContacts([]);
      } else setContacts(response.data ?? []);
    }).catch(() => {
      if (!cancelled) setError("Saved contacts could not be loaded. You can enter details manually.");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [authLoading, user]);

  return <div className="space-y-1">
    <Label htmlFor={inputId}>Use saved contact</Label>
    <Select value={value || "manual"} disabled={loading || authLoading || !user}
      onValueChange={id => onSelect(contacts.find(contact => contact.id === id) ?? null)}>
      <SelectTrigger id={inputId}><SelectValue placeholder={loading ? "Loading contacts…" : "Choose a contact"} /></SelectTrigger>
      <SelectContent>
        <SelectItem value="manual">Enter details manually</SelectItem>
        {contacts.map(contact => <SelectItem key={contact.id} value={contact.id}>
          {[contact.first_name, contact.last_name].filter(Boolean).join(" ") || contact.phone} — {contact.phone}
        </SelectItem>)}
      </SelectContent>
    </Select>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
  </div>;
}
