"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { useAuth } from "@/lib/auth";
import type { ClientFeature } from "@/lib/clientEntitlements";
import { apiFetch } from "@/lib/kodewavesApi";

interface FeatureStatus {
  valid: boolean;
  features: ClientFeature[];
  limits: Record<string, number>;
  message?: string;
}

interface ClientEntitlementsValue {
  isClientEdition: boolean;
  loading: boolean;
  valid: boolean | null;
  features: ClientFeature[];
  message?: string;
  hasFeature: (feature: ClientFeature) => boolean;
  refresh: () => Promise<void>;
}

const IS_CLIENT_EDITION = process.env.NEXT_PUBLIC_KODEWAVES_EDITION === "client";
const ClientEntitlementsContext = createContext<ClientEntitlementsValue>({
  isClientEdition: IS_CLIENT_EDITION,
  loading: IS_CLIENT_EDITION,
  valid: IS_CLIENT_EDITION ? null : true,
  features: [],
  hasFeature: () => !IS_CLIENT_EDITION,
  refresh: async () => {},
});

export function ClientEntitlementsProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [status, setStatus] = useState<FeatureStatus | null>(null);
  const [loading, setLoading] = useState(IS_CLIENT_EDITION);
  const [requestError, setRequestError] = useState("");

  const refresh = useCallback(async () => {
    if (!IS_CLIENT_EDITION) {
      setLoading(false);
      return;
    }
    if (authLoading) return;
    if (!user) {
      setStatus(null);
      setRequestError("");
      setLoading(false);
      return;
    }
    setLoading(true);
    setRequestError("");
    try {
      setStatus(await apiFetch<FeatureStatus>("/installation/features"));
    } catch (cause) {
      setStatus(null);
      setRequestError(
        cause instanceof Error ? cause.message : "Could not load installation features.",
      );
    } finally {
      setLoading(false);
    }
  }, [authLoading, user]);

  useEffect(() => {
    void refresh();
    if (!IS_CLIENT_EDITION || authLoading || !user) return;
    const refreshOnFocus = () => void refresh();
    const timer = window.setInterval(refreshOnFocus, 60_000);
    window.addEventListener("focus", refreshOnFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshOnFocus);
    };
  }, [authLoading, refresh, user]);

  const value = useMemo<ClientEntitlementsValue>(() => {
    const features = status?.valid ? status.features : [];
    return {
      isClientEdition: IS_CLIENT_EDITION,
      loading,
      valid: IS_CLIENT_EDITION ? status?.valid ?? null : true,
      features,
      message: status?.message || requestError || undefined,
      hasFeature: (feature) => !IS_CLIENT_EDITION || features.includes(feature),
      refresh,
    };
  }, [loading, refresh, requestError, status]);

  return (
    <ClientEntitlementsContext.Provider value={value}>
      {children}
    </ClientEntitlementsContext.Provider>
  );
}

export function useClientEntitlements(): ClientEntitlementsValue {
  return useContext(ClientEntitlementsContext);
}
