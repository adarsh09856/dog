#!/usr/bin/env node
import { spawn } from "node:child_process";
import { createHash, createPrivateKey, createPublicKey, randomBytes, sign, verify } from "node:crypto";
import { lstat, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = "/app";
const manifestPath = process.env.KODEWAVES_RELEASE_MANIFEST || "/app/client-release-manifest.json";
const publicKeyPath = "/app/client-release-public-key";
const requiredRoots = [".next/server", ".next/static", "public"];
const requiredFiles = ["server.js", "package.json", "verify-client-release.mjs", "client-release-public-key", "client-owner-status-url"];

async function collectFiles(base = root) {
  const files = new Map();
  const normalizedPath = (relative) => relative.split(path.sep).join("/");
  const assertProtectedPath = async (relative, expectedType) => {
    const parts = relative.split(path.sep);
    let absolute = base;
    for (let index = 0; index < parts.length; index += 1) {
      absolute = path.join(absolute, parts[index]);
      const metadata = await lstat(absolute);
      const finalComponent = index === parts.length - 1;
      if (metadata.isSymbolicLink() || (finalComponent && !metadata[expectedType]())) {
        throw new Error(`Client UI integrity check failed: ${normalizedPath(relative)}`);
      }
    }
  };
  const addFile = async (relative) => {
    await assertProtectedPath(relative, "isFile");
    const absolute = path.join(base, relative);
    const content = await readFile(absolute);
    files.set(relative.split(path.sep).join("/"), createHash("sha256").update(content).digest("hex"));
  };
  const walk = async (relative) => {
    const absolute = path.join(base, relative);
    const entries = await readdir(absolute, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const child = path.join(relative, entry.name);
      if (entry.isSymbolicLink()) {
        throw new Error(`Client UI integrity check failed: ${normalizedPath(child)}`);
      }
      if (entry.isDirectory()) await walk(child);
      else if (entry.isFile()) await addFile(child);
    }
  };
  for (const relative of requiredRoots) {
    await assertProtectedPath(relative, "isDirectory");
    await walk(relative);
  }
  for (const relative of requiredFiles) await addFile(relative);
  return Object.fromEntries([...files.entries()].sort(([left], [right]) => left.localeCompare(right)));
}

function canonicalize(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

// Shared with api/services/installation_identity.py. The owner endpoint must
// additionally consume the nonce atomically before accepting a proof.
function ownerCheckMessage({ installation_id, license_token, nonce, issued_at, integrity_ok, integrity_finding }) {
  const finding = integrity_finding == null ? null : {
    reason: integrity_finding.reason,
    component: integrity_finding.component,
    expected_sha256: integrity_finding.expected_sha256 ?? null,
    observed_sha256: integrity_finding.observed_sha256 ?? null,
  };
  const payload = {
    installation_id,
    license_sha256: createHash("sha256").update(license_token, "ascii").digest("hex"),
    nonce,
    issued_at,
    integrity_ok,
    integrity_finding: finding,
  };
  return Buffer.from(`kodewaves-owner-check-v1\n${canonicalize(payload)}`, "utf8");
}

function signOwnerCheck(privateSeed, fields) {
  const seed = Buffer.from(privateSeed);
  if (seed.length !== 32) throw new Error("Invalid installation private key");
  const pkcs8Prefix = Buffer.from("302e020100300506032b657004220420", "hex");
  const key = createPrivateKey({ key: Buffer.concat([pkcs8Prefix, seed]), format: "der", type: "pkcs8" });
  return sign(null, ownerCheckMessage(fields), key).toString("base64url");
}

async function verifyRelease({ base = root, releaseManifestPath = manifestPath, releasePublicKeyPath = publicKeyPath, environment = process.env } = {}) {
  const signed = JSON.parse(await readFile(releaseManifestPath, "utf8"));
  const payload = signed?.payload;
  if (payload?.edition !== "client" || !payload.ui_files || typeof payload.ui_files !== "object") {
    throw new Error("Signed release manifest has no client UI inventory");
  }
  const encodedKey = (await readFile(releasePublicKeyPath, "ascii")).trim();
  const rawKey = Buffer.from(encodedKey.replace(/-/g, "+").replace(/_/g, "/"), "base64");
  if (rawKey.length !== 32) throw new Error("Baked release public key is invalid");
  const spkiPrefix = Buffer.from("302a300506032b6570032100", "hex");
  const publicKey = createPublicKey({ key: Buffer.concat([spkiPrefix, rawKey]), format: "der", type: "spki" });
  const signature = Buffer.from(String(signed.signature || "").replace(/-/g, "+").replace(/_/g, "/"), "base64");
  if (!verify(null, Buffer.from(canonicalize(payload)), publicKey, signature)) {
    throw new Error("Client release manifest signature is invalid");
  }

  const images = payload.images;
  const schema = payload.schema_compatibility;
  if ((images == null) !== (schema == null)) {
    throw new Error("Release image and schema metadata must be signed together");
  }
  if (images != null) {
    if (!images || Object.keys(images).sort().join(",") !== "api,ui") {
      throw new Error("Invalid client release image metadata");
    }
    for (const service of ["api", "ui"]) {
      const image = images[service];
      const pattern = image?.kind === "registry_digest"
        ? /^[^@]+@sha256:[0-9a-f]{64}$/
        : image?.kind === "image_id" ? /^sha256:[0-9a-f]{64}$/ : null;
      if (!pattern || !pattern.test(image.reference)) {
        throw new Error(`Invalid client release image metadata: ${service}`);
      }
      const variable = service === "api" ? "KODEWAVES_API_IMAGE" : "KODEWAVES_UI_IMAGE";
      if (image.kind === "registry_digest" && environment[variable] !== image.reference) {
        throw new Error(`Configured ${service.toUpperCase()} image does not match the signed release`);
      }
    }
    const revision = /^[A-Za-z0-9_]{1,64}$/;
    if (!schema || !revision.test(schema.head || "") || !Array.isArray(schema.upgrade_from)
      || !Array.isArray(schema.rollback_to)
      || !schema.upgrade_from.every((item) => typeof item === "string" && revision.test(item))
      || !schema.rollback_to.every((item) => typeof item === "string" && revision.test(item))
      || new Set(schema.upgrade_from).size !== schema.upgrade_from.length
      || new Set(schema.rollback_to).size !== schema.rollback_to.length
      || !schema.upgrade_from.includes(schema.head)
      || !schema.rollback_to.every((item) => schema.upgrade_from.includes(item))) {
      throw new Error("Invalid client release schema compatibility metadata");
    }
  }

  const observed = await collectFiles(base);
  const expected = payload.ui_files;
  const names = [...new Set([...Object.keys(expected), ...Object.keys(observed)])].sort();
  const mismatch = names.find((name) => expected[name] !== observed[name]);
  if (mismatch) throw new Error(`Client UI integrity check failed: ${mismatch}`);
  return names.length;
}

async function reportFailure(error, {
  ownerStatusUrl,
  licenseToken,
  identityKeyPath,
  installationId,
  fetchImplementation = fetch,
} = {}) {
  try {
    const statusUrl = ownerStatusUrl ?? (await readFile("/app/client-owner-status-url", "utf8")).trim();
    const token = licenseToken ?? process.env.KODEWAVES_LICENSE_TOKEN;
    if (!statusUrl || !token) throw new Error("owner alert credentials are unavailable");
    const message = String(error?.message || "client UI integrity failure");
    const mismatch = message.match(/Client UI integrity check failed: ([A-Za-z0-9_./-]+)/);
    const missing = message.match(/ENOENT[^\n]*['"]([^'"]+)['"]/);
    const finding = {
      reason: mismatch ? "modified_file" : missing ? "missing_file" : "invalid_manifest",
      component: mismatch?.[1] || (missing ? "ui/runtime" : "ui/manifest"),
    };
    const nonce = randomBytes(32).toString("base64url");
    const body = { nonce, integrity_ok: false, integrity_finding: finding };
    const keyPath = identityKeyPath ?? process.env.KODEWAVES_INSTALLATION_KEY_FILE;
    if (keyPath) {
      const id = installationId ?? process.env.KODEWAVES_INSTALLATION_ID;
      if (!id) throw new Error("installation identity is unavailable");
      const issuedAt = Math.floor(Date.now() / 1000);
      const fields = {
        installation_id: id, license_token: token, nonce, issued_at: issuedAt,
        integrity_ok: false, integrity_finding: finding,
      };
      body.proof_issued_at = issuedAt;
      body.proof_signature = signOwnerCheck(await readFile(keyPath), fields);
    }
    const response = await fetchImplementation(statusUrl, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error(`owner returned HTTP ${response.status}`);
  } catch (alertError) {
    process.stderr.write(`Owner UI integrity alert delivery failed: ${alertError instanceof Error ? alertError.message : "unknown error"}\n`);
  }
}

async function main() {
  if (process.argv.includes("--inventory")) {
    process.stdout.write(`${JSON.stringify(await collectFiles())}\n`);
    return;
  }
  const count = await verifyRelease();
  process.stdout.write(`Client UI integrity verified (${count} files)\n`);
  if (!process.argv.includes("--watch")) return;

  const server = spawn("node", ["server.js"], {
    cwd: root,
    env: { ...process.env, PORT: process.env.PORT || "3010" },
    stdio: "inherit",
  });
  let checking = false;
  const timer = setInterval(async () => {
    if (checking) return;
    checking = true;
    try {
      await verifyRelease();
    } catch (error) {
      process.stderr.write(`${error instanceof Error ? error.message : "Client UI integrity check failed"}\n`);
      await reportFailure(error);
      clearInterval(timer);
      server.kill("SIGTERM");
      process.exitCode = 1;
    } finally {
      checking = false;
    }
  }, 60_000);
  const stop = (signal) => { clearInterval(timer); server.kill(signal); };
  process.on("SIGTERM", () => stop("SIGTERM"));
  process.on("SIGINT", () => stop("SIGINT"));
  server.on("exit", (code) => { clearInterval(timer); process.exitCode = code ?? 1; });
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  main().catch(async (error) => {
    process.stderr.write(`${error instanceof Error ? error.message : "Client UI integrity check failed"}\n`);
    await reportFailure(error);
    process.exitCode = 1;
  });
}

export { canonicalize, collectFiles, ownerCheckMessage, reportFailure, signOwnerCheck, verifyRelease };
