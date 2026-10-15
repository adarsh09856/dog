"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
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

export default function LocalSttTest({ models }: { models: { id: string; name: string }[] }) {
  const input = useRef<HTMLInputElement>(null);
  const [model, setModel] = useState("");
  const [language, setLanguage] = useState("auto");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Awaited<ReturnType<typeof adminApi.testWhisper>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!models.some(item => item.id === model)) {
      setModel(models.find(item => item.id === "Systran/faster-whisper-small")?.id || models[0]?.id || "");
      setResult(null);
    }
  }, [models, model]);

  const run = async () => {
    if (!file || !model || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await adminApi.testWhisper(language, await audioBase64(file), model);
      setResult(response);
      if (!response.success) setError(response.error || "No speech was recognized");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Speech recognition test failed");
    } finally {
      setBusy(false);
    }
  };

  return <div className="space-y-3 rounded-xl border p-4">
    <h3 className="text-sm font-semibold">Test speech recognition</h3>
    <p className="text-xs text-muted-foreground">Use your own speech: a 16-bit PCM WAV, up to 2 MB and 60 seconds. Automatic detection accepts mixed languages.</p>
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1">
        <Label htmlFor="stt-test-model">Installed model</Label>
        <select id="stt-test-model" className="w-full rounded-md border bg-background p-2 text-sm" disabled={busy} value={model} onChange={event => { setModel(event.target.value); setResult(null); }}>
          {!models.length && <option value="">No installed speech model</option>}
          {models.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="stt-test-language">Recognition language</Label>
        <select id="stt-test-language" className="w-full rounded-md border bg-background p-2 text-sm" disabled={busy} value={language} onChange={event => { setLanguage(event.target.value); setResult(null); }}>
          <option value="auto">Automatic / mixed languages</option>
          <option value="hi">Hindi</option><option value="en">English</option>
          <option value="ta">Tamil</option><option value="te">Telugu</option>
          <option value="mr">Marathi</option><option value="bn">Bengali</option>
          <option value="gu">Gujarati</option><option value="kn">Kannada</option>
          <option value="ml">Malayalam</option><option value="pa">Punjabi</option>
        </select>
      </div>
    </div>
    <input ref={input} aria-label="Speech test WAV" type="file" accept=".wav,audio/wav" hidden disabled={busy} onChange={event => {
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
      <Button disabled={busy || !file || !model} onClick={run}>{busy ? "Transcribing…" : "Run speech test"}</Button>
    </div>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {result?.success && <div role="status" className="space-y-1 text-sm">
      <p>{result.transcript}</p><p className="text-xs text-muted-foreground">Recognition time: {result.latency_ms} ms</p>
    </div>}
  </div>;
}
