import { NextResponse } from "next/server";

import type { HealthResponse } from "@/client/types.gen";
import { getServerBackendUrl } from "@/lib/apiClient";

// Import version from package.json at build time
import packageJson from "../../../../../package.json";

const HEALTHCHECK_TIMEOUT_MS = 8000;

function trimTrailingSlash(url: string) {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function getHealthcheckFailureMessage(error: unknown, backendUrl: string) {
  const errorName =
    error && typeof error === "object" && "name" in error
      ? String((error as { name?: unknown }).name)
      : "";

  if (errorName === "AbortError" || errorName === "TimeoutError") {
    return `Backend health check timed out after ${HEALTHCHECK_TIMEOUT_MS}ms while trying to reach ${backendUrl}.`;
  }

  return `Backend is not reachable at ${backendUrl}.`;
}

export async function GET() {
  const uiVersion = packageJson.version || "dev";
  const primaryBackendUrl = trimTrailingSlash(getServerBackendUrl());
  
  const candidateUrls = Array.from(
    new Set(
      [
        primaryBackendUrl,
        "http://api:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        process.env.NEXT_PUBLIC_BACKEND_URL ? trimTrailingSlash(process.env.NEXT_PUBLIC_BACKEND_URL) : null,
      ].filter((u): u is string => Boolean(u))
    )
  );

  let apiVersion = "unknown";
  let deploymentMode = "oss";
  let authProvider = "local";
  let turnEnabled = false;
  let forceTurnRelay = false;
  let tunnelUrl: string | null = null;
  let backendApiEndpoint: string | null = null;
  let backendStatus: "reachable" | "unreachable" = "unreachable";
  let backendUrl = primaryBackendUrl;
  let healthcheckUrl = `${backendUrl}/api/v1/health`;
  let backendMessage: string | null = `Backend is not reachable at ${backendUrl}.`;

  for (const candidate of candidateUrls) {
    const candidateHealthUrl = `${candidate}/api/v1/health`;
    try {
      const response = await fetch(candidateHealthUrl, {
        cache: "no-store",
        signal: AbortSignal.timeout(HEALTHCHECK_TIMEOUT_MS),
      });

      if (response.ok) {
        const data = (await response.json()) as HealthResponse;
        apiVersion = data.version;
        deploymentMode = data.deployment_mode;
        authProvider = data.auth_provider;
        turnEnabled = Boolean(data.turn_enabled);
        forceTurnRelay = Boolean(data.force_turn_relay);
        tunnelUrl = data.tunnel_url ?? null;
        backendApiEndpoint =
          typeof data.backend_api_endpoint === "string" &&
          data.backend_api_endpoint.length > 0
            ? trimTrailingSlash(data.backend_api_endpoint)
            : null;
        backendStatus = "reachable";
        backendUrl = candidate;
        healthcheckUrl = candidateHealthUrl;
        backendMessage = null;
        break;
      }
    } catch (error) {
      // Continue to next candidate
    }
  }

  if (backendStatus === "unreachable") {
    apiVersion = "unavailable";
    backendMessage = `Backend is not reachable at ${backendUrl}. Ensure backend service is running.`;
  }

  return NextResponse.json({
    ui: uiVersion,
    api: apiVersion,
    deploymentMode,
    authProvider,
    turnEnabled,
    forceTurnRelay,
    tunnelUrl,
    backendApiEndpoint,
    backend: {
      status: backendStatus,
      url: backendUrl,
      healthcheckUrl,
      message: backendMessage,
    },
  });
}
