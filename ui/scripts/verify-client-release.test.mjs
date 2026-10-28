import assert from "node:assert/strict";
import { generateKeyPairSync, sign, verify } from "node:crypto";
import { mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { canonicalize, collectFiles, ownerCheckMessage, reportFailure, verifyRelease } from "./verify-client-release.mjs";

async function createRuntimeFixture(base) {
  for (const directory of [".next/server", ".next/static", "public"]) {
    await mkdir(path.join(base, directory), { recursive: true });
  }
  for (const file of [
    ".next/server/app.js", ".next/static/app.js", "public/favicon.ico",
    "server.js", "package.json", "verify-client-release.mjs",
    "client-release-public-key", "client-owner-status-url",
  ]) {
    await writeFile(path.join(base, file), `approved:${file}`);
  }
}

test("client UI integrity failure sends an authenticated owner alert with a bounded finding", async () => {
  let request;
  await reportFailure(
    new Error("Client UI integrity check failed: .next/server/app.js"),
    {
      ownerStatusUrl: "https://owner.example.test/api/v1/installation/status",
      licenseToken: "license-token",
      fetchImplementation: async (url, options) => {
        request = { url, options };
        return { ok: true };
      },
    },
  );

  assert.equal(request.url, "https://owner.example.test/api/v1/installation/status");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.headers.authorization, "Bearer license-token");
  const body = JSON.parse(request.options.body);
  assert.match(body.nonce, /^[A-Za-z0-9_-]{40,}$/);
  assert.equal(body.integrity_ok, false);
  assert.deepEqual(body.integrity_finding, {
    reason: "modified_file",
    component: ".next/server/app.js",
  });
});

test("client UI signs alerts when its installation key is configured", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "kodewaves-ui-identity-"));
  try {
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const seed = privateKey.export({ type: "pkcs8", format: "der" }).subarray(-32);
    const identityKeyPath = path.join(base, "identity.key");
    await writeFile(identityKeyPath, seed);
    let body;
    await reportFailure(new Error("Client UI integrity check failed: .next/server/app.js"), {
      ownerStatusUrl: "https://owner.example.test/check", licenseToken: "license-token",
      identityKeyPath, installationId: "client-1",
      fetchImplementation: async (_url, options) => {
        body = JSON.parse(options.body);
        return { ok: true };
      },
    });
    const message = ownerCheckMessage({
      installation_id: "client-1", license_token: "license-token", nonce: body.nonce,
      issued_at: body.proof_issued_at, integrity_ok: body.integrity_ok,
      integrity_finding: body.integrity_finding,
    });
    assert.equal(verify(null, message, publicKey, Buffer.from(body.proof_signature, "base64url")), true);
  } finally {
    await rm(base, { recursive: true, force: true });
  }
});

test("client UI never sends a bearer-only alert when the configured key is missing", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "kodewaves-ui-missing-identity-"));
  try {
    let sent = false;
    await reportFailure(new Error("Client UI integrity check failed: .next/server/app.js"), {
      ownerStatusUrl: "https://owner.example.test/check", licenseToken: "license-token",
      identityKeyPath: path.join(base, "missing.key"), installationId: "client-1",
      fetchImplementation: async () => { sent = true; return { ok: true }; },
    });
    assert.equal(sent, false);
  } finally {
    await rm(base, { recursive: true, force: true });
  }
});

test("client UI verifier accepts the signed image inventory and rejects tampering", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "kodewaves-ui-integrity-"));
  try {
    await createRuntimeFixture(base);

    const { publicKey, privateKey } = generateKeyPairSync("ed25519");
    const spki = publicKey.export({ type: "spki", format: "der" });
    const rawPublicKey = spki.subarray(spki.length - 32).toString("base64url");
    const inventory = await collectFiles(base);
    const payload = {
      edition: "client", files: {}, ui_files: inventory,
      images: {
        api: { kind: "registry_digest", reference: `registry.example/api@sha256:${"a".repeat(64)}` },
        ui: { kind: "registry_digest", reference: `registry.example/ui@sha256:${"b".repeat(64)}` },
      },
      schema_compatibility: { head: "rev1", upgrade_from: ["rev1"], rollback_to: [] },
    };
    const signature = sign(null, Buffer.from(canonicalize(payload)), privateKey).toString("base64url");
    const releaseManifestPath = path.join(base, "release-manifest.json");
    const releasePublicKeyPath = path.join(base, "release-public-key.txt");
    await writeFile(releaseManifestPath, JSON.stringify({ payload, signature }));
    await writeFile(releasePublicKeyPath, rawPublicKey);

    const environment = {
      KODEWAVES_API_IMAGE: payload.images.api.reference,
      KODEWAVES_UI_IMAGE: payload.images.ui.reference,
    };
    assert.equal(await verifyRelease({ base, releaseManifestPath, releasePublicKeyPath, environment }), 8);
    await assert.rejects(
      verifyRelease({ base, releaseManifestPath, releasePublicKeyPath, environment: { ...environment, KODEWAVES_UI_IMAGE: "wrong" } }),
      /UI image does not match/,
    );
    await writeFile(path.join(base, ".next/server/injected.js"), "unapproved");
    await assert.rejects(
      verifyRelease({ base, releaseManifestPath, releasePublicKeyPath, environment }),
      /Client UI integrity check failed: \.next\/server\/injected\.js/,
    );
  } finally {
    await rm(base, { recursive: true, force: true });
  }
});

test("client UI inventory rejects a symlinked protected root directory", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "kodewaves-ui-symlink-root-"));
  try {
    await createRuntimeFixture(base);
    const external = path.join(base, "external-server");
    await mkdir(external);
    await writeFile(path.join(external, "injected.js"), "outside protected root");
    await rm(path.join(base, ".next", "server"), { recursive: true });
    await symlink(external, path.join(base, ".next", "server"), process.platform === "win32" ? "junction" : "dir");

    await assert.rejects(
      collectFiles(base),
      /Client UI integrity check failed: \.next\/server/,
    );
  } finally {
    await rm(base, { recursive: true, force: true });
  }
});

test("client UI inventory rejects a symlinked parent of protected roots", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "kodewaves-ui-symlink-parent-"));
  try {
    await createRuntimeFixture(base);
    const external = path.join(base, "external-next");
    await mkdir(external);
    await mkdir(path.join(external, "server"));
    await writeFile(path.join(external, "server", "injected.js"), "outside protected root");
    await rm(path.join(base, ".next"), { recursive: true });
    await symlink(external, path.join(base, ".next"), process.platform === "win32" ? "junction" : "dir");

    await assert.rejects(
      collectFiles(base),
      /Client UI integrity check failed: \.next\/server/,
    );
  } finally {
    await rm(base, { recursive: true, force: true });
  }
});

test("client UI inventory rejects a symlinked required runtime file", async (t) => {
  const base = await mkdtemp(path.join(os.tmpdir(), "kodewaves-ui-symlink-file-"));
  try {
    await createRuntimeFixture(base);
    const external = path.join(base, "external-server.js");
    await writeFile(external, "external runtime");
    await rm(path.join(base, "server.js"));
    try {
      await symlink(external, path.join(base, "server.js"), "file");
    } catch (error) {
      if (process.platform === "win32" && ["EPERM", "EACCES"].includes(error?.code)) {
        t.skip("Windows symlink creation requires Developer Mode or elevated privileges");
        return;
      }
      throw error;
    }

    await assert.rejects(
      collectFiles(base),
      /Client UI integrity check failed: server\.js/,
    );
  } finally {
    await rm(base, { recursive: true, force: true });
  }
});
