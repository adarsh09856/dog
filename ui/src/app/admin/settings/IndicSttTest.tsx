"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { INDIAN_TEMPLATE_LANGUAGES } from "@/constants/languages";
import { adminApi } from "@/lib/kodewavesApi";

function audioBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(new Error("Could not read the recording"));
    reader.onabort = () => reject(new Error("Reading the recording was cancelled"));
    reader.readAsDataURL(file);
  });
}

export default function IndicSttTest() {
  const input = useRef<HTMLInputElement>(null);
  const [languages, setLanguages] = useState<string[]>([]);
  const [language, setLanguage] = useState("hi");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Loading installed Indian STT languages…");
  const [result, setResult] = useState<Awaited<ReturnType<typeof adminApi.testIndicStt>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    adminApi.getIndicSttModels().then((response) => {
      if (!active) return;
      const installed = response.languages || [];
      setLanguages(installed);
      setStatus(response.status === "online"
        ? `${installed.length} of 22 IndicConformer languages installed`
        : response.detail || "IndicConformer STT is unavailable");
      setLanguage(current => installed.length && !installed.includes(current) ? installed[0] : current);
    }).catch((reason) => {
      if (!active) return;
      setLanguages([]);
      setStatus(reason instanceof Error ? reason.message : "Could not load IndicConformer inventory");
    });
    return () => { active = false; };
  }, []);

  const run = async () => {
    if (!file || !language || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await adminApi.testIndicStt(language, await audioBase64(file));
      setResult(response);
      if (!response.success) setError(response.error || "No speech was recognized");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "IndicConformer speech test failed");
    } finally {
      setBusy(false);
    }
  };

  return <div className="space-y-3 rounded-xl border p-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-semibold">Test Indian-language recognition</h3>
      <span className="text-xs text-muted-foreground" role="status">{status}</span>
    </div>
    <p className="text-xs text-muted-foreground">
      IndicConformer uses one selected language per test. Use Faster-Whisper above for automatic detection and mixed-language audio.
    </p>
    <div className="space-y-1">
      <Label htmlFor="indic-stt-language">Recognition language</Label>
      <select id="indic-stt-language" className="w-full rounded-md border bg-background p-2 text-sm" disabled={busy || !languages.length} value={language} onChange={event => { setLanguage(event.target.value); setResult(null); }}>
        {!languages.length && <option value="">No installed IndicConformer language</option>}
        {INDIAN_TEMPLATE_LANGUAGES.filter(item => languages.includes(item.code)).map(item => (
          <option key={item.code} value={item.code}>{item.name}</option>
        ))}
      </select>
    </div>
    <input ref={input} aria-label="Indic speech test WAV" type="file" accept=".wav,audio/wav" hidden disabled={busy} onChange={event => {
      const selected = event.target.files?.[0];
      setResult(null); setError(null); setFile(null);
      if (!selected) return;
      if (!selected.name.toLowerCase().endsWith(".wav") || selected.size > 2 * 1024 * 1024 || selected.size === 0) {
        setError("Choose a WAV recording no larger than 2 MB"); event.target.value = ""; return;
      }
      setFile(selected);
    }} />
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="outline" disabled={busy} onClick={() => input.current?.click()}>Choose WAV recording</Button>
      <span className="text-xs">{file?.name || "No recording selected"}</span>
      <Button disabled={busy || !file || !language || !languages.includes(language)} onClick={run}>{busy ? "Transcribing…" : "Run Indian-language test"}</Button>
    </div>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {result?.success && <div role="status" className="space-y-1 text-sm">
      <p>{result.transcript}</p><p className="text-xs text-muted-foreground">Recognition time: {result.latency_ms} ms</p>
    </div>}
  </div>;
}
