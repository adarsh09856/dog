"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  AudioLines,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Database,
  ExternalLink,
  Flame,
  Globe,
  Layers,
  LayoutFlow,
  Lock,
  Phone,
  Play,
  Radio,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
  Wrench,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";

export default function HomePage() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Interactive "Fork every box" state
  const [activeS2S, setActiveS2S] = useState<string>("Gemini 3.1 Flash Live");
  const [activeSTT, setActiveSTT] = useState<string>("Deepgram Nova-3");
  const [activeLLM, setActiveLLM] = useState<string>("OpenAI GPT-4o-mini");
  const [activeTTS, setActiveTTS] = useState<string>("Cartesia Sonic 3.5");
  const [activeSIP, setActiveSIP] = useState<string>("Twilio SIP");

  const s2sOptions = [
    "Gemini 3.1 Flash Live",
    "OpenAI Realtime (WebRTC)",
    "MiniMax Speech-to-Speech",
  ];

  const sttOptions = [
    "Deepgram Nova-3",
    "Speaches Whisper (Local CPU)",
    "Navana Bodhi Indic (Hindi/Tamil)",
    "Google Gemini STT",
    "AssemblyAI",
  ];

  const llmOptions = [
    "OpenAI GPT-4o-mini",
    "Ollama Qwen2.5 (Local CPU 0ms)",
    "Gemini 2.5 Flash",
    "Groq Llama-3.3-70B",
    "Claude 3.5 Sonnet",
    "Sarvam 2B Indic",
  ];

  const ttsOptions = [
    "Piper Native Indic (Local CPU)",
    "Google Gemini Voice Studio",
    "Cartesia Sonic 3.5",
    "ElevenLabs Flash v2.5",
    "Navana Bodhi TTS",
    "Sarvam Bulbul (Indic)",
  ];

  const sipOptions = [
    "Twilio SIP",
    "Telnyx Voice",
    "Plivo Inbound/Outbound",
    "Vonage SIP Trunk",
    "FreePBX / Asterisk",
  ];

  useEffect(() => {
    const cookies = document.cookie;
    if (
      cookies.includes("kodewaves_auth_token") ||
      cookies.includes("dograh_auth_token") ||
      cookies.includes("oss_token")
    ) {
      setIsAuthenticated(true);
    }
  }, []);

  const cycleOption = (current: string, options: string[], setter: (v: string) => void) => {
    const currentIndex = options.indexOf(current);
    const nextIndex = (currentIndex + 1) % options.length;
    setter(options[nextIndex]);
  };

  const integrationsLane1 = [
    { name: "OpenAI", logo: "Op" },
    { name: "Gemini", logo: "Ge" },
    { name: "Google", logo: "Go" },
    { name: "Groq", logo: "Gr" },
    { name: "OpenRouter", logo: "OR" },
    { name: "Azure Speech", logo: "Az" },
    { name: "AWS Bedrock", logo: "AW" },
    { name: "Hugging Face", logo: "HF" },
    { name: "MiniMax", logo: "MM" },
    { name: "Sarvam Indic", logo: "Sa" },
    { name: "Gladia", logo: "Gl" },
    { name: "AssemblyAI", logo: "AA" },
    { name: "Speechmatics", logo: "Sp" },
    { name: "Deepgram", logo: "Dg" },
  ];

  const integrationsLane2 = [
    { name: "ElevenLabs", logo: "EL" },
    { name: "Cartesia", logo: "Ca" },
    { name: "Inworld", logo: "In" },
    { name: "Camb.ai", logo: "Cb" },
    { name: "Rime", logo: "Ri" },
    { name: "Speaches (Local)", logo: "Sp" },
    { name: "Smallest AI", logo: "Sm" },
    { name: "xAI Grok", logo: "xA" },
    { name: "Plivo", logo: "Pl" },
    { name: "Telnyx", logo: "Tx" },
    { name: "Twilio", logo: "Tw" },
    { name: "Vonage", logo: "Vo" },
    { name: "Asterisk PBX", logo: "As" },
    { name: "Langfuse", logo: "Lf" },
  ];

  return (
    <div className="min-h-screen bg-[#1c1b1d] text-[#cecbc6] selection:bg-[#e5a84b]/30 selection:text-[#f3f1ed] relative overflow-x-hidden font-sans">
      {/* Film grain noise texture overlay matching Kodewaves brand aesthetic */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-[60] opacity-[0.16] mix-blend-overlay"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeComponentTransfer%3E%3CfeFuncA type='linear' slope='0.55'/%3E%3C/feComponentTransfer%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
          backgroundSize: "320px 320px",
        }}
      />

      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-50 w-full border-b border-[#343336] bg-[#1c1b1d]/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#e5a84b] text-black font-black text-sm shadow-[0_0_16px_rgba(229,168,75,0.4)] transition-transform group-hover:scale-105">
              KW
            </div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-lg tracking-tight text-[#f3f1ed]">
                Kodewaves
              </span>
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border border-[#e5a84b]/40 bg-[#e5a84b]/10 text-[#e5a84b] font-semibold tracking-wider">
                Sovereign
              </span>
            </div>
          </Link>

          <nav className="flex items-center gap-1.5 sm:gap-2">
            <Link
              href="/pricing"
              className="px-3 py-1.5 text-xs sm:text-sm text-[#94918d] hover:text-[#f3f1ed] transition-colors"
            >
              Pricing
            </Link>
            <Link
              href="https://github.com/adarsh09856/dog"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs sm:text-sm text-[#94918d] hover:text-[#f3f1ed] transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
              </svg>
              <span className="hidden sm:inline">GitHub</span>
            </Link>

            {isAuthenticated ? (
              <Link
                href="/workflow"
                className="ml-2 inline-flex items-center gap-1.5 rounded-md bg-[#e5a84b] px-3.5 py-1.5 text-xs sm:text-sm font-semibold text-black transition-all hover:bg-[#d69637] shadow-sm"
              >
                Go to Console
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            ) : (
              <div className="flex items-center gap-2 ml-2">
                <Link
                  href="/auth/login"
                  className="rounded-md border border-[#3b3a3d] bg-[#272629] px-3 py-1.5 text-xs sm:text-sm font-medium text-[#f3f1ed] hover:border-[#4d4b50] transition-colors"
                >
                  Sign In
                </Link>
                <Link
                  href="/auth/signup"
                  className="rounded-md bg-[#e5a84b] px-3.5 py-1.5 text-xs sm:text-sm font-semibold text-black transition-all hover:bg-[#d69637] shadow-sm"
                >
                  Start Building Free
                </Link>
              </div>
            )}
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative pt-16 pb-20 sm:pt-24 sm:pb-28 border-b border-[#302f32]">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 text-center">
          {/* Eyebrow badge */}
          <div className="inline-flex items-center gap-2 rounded-full border border-[#3e3c40] bg-[#252427] px-3.5 py-1.5 text-[11px] font-mono uppercase tracking-[0.2em] text-[#9a9792] mb-8">
            <span className="text-[#9a9792]">THE SELF HOSTABLE VOICE AGENT PLATFORM</span>
            <span className="text-[#595754]">·</span>
            <span className="text-[#e5a84b] font-semibold">OSS ALTERNATIVE TO VAPI & RETELL</span>
          </div>

          {/* Headline with terminal cursor blink */}
          <h1 className="text-4xl sm:text-6xl lg:text-7xl font-semibold tracking-[-0.03em] text-[#f3f1ed] leading-[1.08] mb-6">
            <span className="text-[#5f5d62] font-mono">[</span>
            <span className="text-[#e5a84b] font-bold">Self-Hosted</span>
            <span className="text-[#5f5d62] font-mono">]</span> voice agents
            <span className="cursor-blink ml-1 text-[#e5a84b] font-mono font-normal">_</span>
          </h1>

          {/* Subtitle */}
          <p className="max-w-2xl mx-auto text-lg sm:text-xl font-light text-[#a5a29d] mb-10 leading-relaxed">
            <span className="text-[#f3f1ed] font-medium">Open Source </span>
            <em className="italic text-[#d9a24c]">workflow builder for </em>
            <span className="text-[#f3f1ed] font-medium">Voice Agents</span>. Bring your own models, plug in carrier SIP trunks, or run 100% self-hosted on your CPU VPS with zero cloud API keys.
          </p>

          {/* Action CTAs */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3.5 mb-16">
            <Link
              href={isAuthenticated ? "/workflow" : "/auth/signup"}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-lg bg-[#e5a84b] px-6 py-3.5 text-sm font-semibold text-black transition-all hover:bg-[#d69637] shadow-[0_0_24px_rgba(229,168,75,0.3)]"
            >
              {isAuthenticated ? "Launch Agent Console" : "Start Building Free"}
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/pricing"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-lg border border-[#3b3a3d] bg-[#252427] px-6 py-3.5 text-sm font-medium text-[#f3f1ed] hover:border-[#e5a84b]/40 hover:bg-[#2c2a2e] transition-colors"
            >
              Explore Sovereign Pricing (₹0.60/min)
            </Link>
          </div>

          {/* Recognitions Pill Ticker */}
          <div className="mx-auto max-w-4xl overflow-hidden rounded-full border border-[#353437] bg-[#222124]/90 p-1.5 backdrop-blur-md">
            <div className="flex items-center gap-4 text-xs font-mono uppercase tracking-[0.14em] text-[#9d9a95]">
              <span className="flex items-center gap-1.5 pl-3 text-[#e5a84b] font-semibold shrink-0">
                <Sparkles className="h-3.5 w-3.5" />
                RECOGNITIONS
              </span>
              <div className="h-3 w-px bg-[#3b3a3d] shrink-0" />
              <div className="overflow-hidden flex-1 relative">
                <div className="flex w-max animate-ticker-left gap-8 py-1 items-center">
                  <span className="inline-flex items-center gap-1.5 text-[#cecbc6]">
                    <span className="size-2 rounded-full bg-emerald-500"></span>
                    #1 Product of the Day
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[#cecbc6]">
                    <span className="size-2 rounded-full bg-[#e5a84b]"></span>
                    #1 Product of the Week
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[#cecbc6]">
                    <span className="size-2 rounded-full bg-blue-500"></span>
                    NVIDIA Inception Program
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[#cecbc6]">
                    <span className="size-2 rounded-full bg-purple-500"></span>
                    #3 Repository of the Day
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[#cecbc6]">
                    <span className="size-2 rounded-full bg-amber-500"></span>
                    Developer Tools of the Year
                  </span>

                  {/* Duplicate for infinite loop */}
                  <span className="inline-flex items-center gap-1.5 text-[#cecbc6]">
                    <span className="size-2 rounded-full bg-emerald-500"></span>
                    #1 Product of the Day
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[#cecbc6]">
                    <span className="size-2 rounded-full bg-[#e5a84b]"></span>
                    #1 Product of the Week
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[#cecbc6]">
                    <span className="size-2 rounded-full bg-blue-500"></span>
                    NVIDIA Inception Program
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[#cecbc6]">
                    <span className="size-2 rounded-full bg-purple-500"></span>
                    #3 Repository of the Day
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* § The Stack You Bring: "Fork Every Box" Interactive Visualizer */}
      <section className="py-20 sm:py-28 border-b border-[#302f32] bg-[#1a191b]">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            {/* Left text */}
            <div className="lg:col-span-5 space-y-5">
              <div className="font-mono text-xs uppercase tracking-[0.22em] text-[#e5a84b] font-semibold">
                § the stack you bring
              </div>
              <h2 className="text-4xl sm:text-5xl font-semibold tracking-tight text-[#f3f1ed] leading-[1.08]">
                Fork every <span className="text-[#e5a84b] italic">box</span>.
              </h2>
              <p className="text-[#9e9b95] text-base sm:text-lg leading-relaxed">
                Click any node to see the interchangeable providers you can plug in. Pick your inbound carrier, STT, LLM, TTS, and telephony. Or skip the cascade entirely and switch the whole pipeline to speech-to-speech.
              </p>

              <div className="pt-4 space-y-2 text-xs font-mono text-[#8d8a85]">
                <div className="flex items-center gap-2">
                  <span className="size-1.5 rounded-full bg-emerald-500"></span>
                  Zero vendor lock-in — swap models per workflow in 1 click
                </div>
                <div className="flex items-center gap-2">
                  <span className="size-1.5 rounded-full bg-[#e5a84b]"></span>
                  Local CPU Stack option runs 100% free with zero cloud keys
                </div>
                <div className="flex items-center gap-2">
                  <span className="size-1.5 rounded-full bg-blue-500"></span>
                  Sub-300ms pipeline execution with native streaming WebSockets
                </div>
              </div>
            </div>

            {/* Right interactive node graph */}
            <div className="lg:col-span-7">
              <div className="rounded-2xl border border-[#373539] bg-[#222124]/90 p-6 sm:p-7 backdrop-blur-sm shadow-xl space-y-4">
                <div className="flex items-center justify-between text-[11px] font-mono uppercase tracking-[0.18em] text-[#8e8b86] pb-1">
                  <span className="flex items-center gap-2">
                    <span className="size-2 rounded-full bg-[#e5a84b] animate-ping" />
                    CLICK ANY BOX TO SWAP PROVIDER
                  </span>
                  <span className="text-[#6d6b67]">Interactive Architecture</span>
                </div>

                {/* Node 1: Inbound Call Channel */}
                <div className="p-3.5 rounded-xl border border-dashed border-[#444246] bg-[#27262a] flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="size-8 rounded-full bg-[#e5a84b]/10 text-[#e5a84b] flex items-center justify-center">
                      <Phone className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="text-xs font-mono uppercase tracking-wider text-[#f3f1ed] font-semibold">
                        Inbound Call / WebRTC
                      </div>
                      <div className="text-[10px] text-[#807d79] font-mono">
                        + outbound dialer · floating web widget
                      </div>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold">
                    15ms transport
                  </span>
                </div>

                {/* Connector line */}
                <div className="w-px h-4 bg-[#3d3b3f] mx-7" />

                {/* Speech to Speech Option */}
                <div className="p-4 rounded-xl border border-[#3b3a3d] bg-[#27262a] space-y-2">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-[#82807b]">
                    § speech-to-speech · single model audio in/out
                  </div>
                  <div
                    onClick={() => cycleOption(activeS2S, s2sOptions, setActiveS2S)}
                    className="p-3 rounded-lg border border-[#444246] hover:border-[#e5a84b]/50 bg-[#1d1c1e] cursor-pointer flex items-center justify-between transition-all group"
                  >
                    <div className="flex items-center gap-3">
                      <span className="px-2 py-1 rounded bg-[#e5a84b]/10 text-[#e5a84b] font-mono font-bold text-xs">
                        S2S
                      </span>
                      <div>
                        <div className="text-sm font-semibold text-[#f3f1ed] group-hover:text-[#e5a84b] transition-colors">
                          {activeS2S}
                        </div>
                        <div className="text-[10px] text-[#7d7a76] font-mono">
                          Direct audio-to-audio neural streaming
                        </div>
                      </div>
                    </div>
                    <span className="text-xs text-[#8c8984] group-hover:text-[#f3f1ed]">
                      Click to swap ↻
                    </span>
                  </div>
                </div>

                {/* Divider */}
                <div className="relative flex items-center justify-center my-2">
                  <div className="absolute inset-x-0 h-px bg-[#353437]" />
                  <span className="relative rounded-full border border-[#49474c] bg-[#1d1c1e] px-3 py-0.5 font-mono text-[10px] uppercase font-semibold tracking-wider text-[#e5a84b]">
                    OR MODULAR CASCADE
                  </span>
                </div>

                {/* Modular Cascade Box */}
                <div className="p-4 rounded-xl border border-[#3b3a3d] bg-[#27262a] space-y-3">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-[#82807b]">
                    § modular pipeline · STT → LLM → TTS
                  </div>

                  {/* STT */}
                  <div
                    onClick={() => cycleOption(activeSTT, sttOptions, setActiveSTT)}
                    className="p-2.5 rounded-lg border border-[#444246] hover:border-[#e5a84b]/50 bg-[#1d1c1e] cursor-pointer flex items-center justify-between transition-all group"
                  >
                    <div className="flex items-center gap-3">
                      <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 font-mono font-bold text-xs">
                        STT
                      </span>
                      <span className="text-xs font-semibold text-[#f3f1ed] group-hover:text-[#e5a84b]">
                        {activeSTT}
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-[#8c8984]">
                      Transcriber ↻
                    </span>
                  </div>

                  {/* LLM */}
                  <div
                    onClick={() => cycleOption(activeLLM, llmOptions, setActiveLLM)}
                    className="p-2.5 rounded-lg border border-[#444246] hover:border-[#e5a84b]/50 bg-[#1d1c1e] cursor-pointer flex items-center justify-between transition-all group"
                  >
                    <div className="flex items-center gap-3">
                      <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 font-mono font-bold text-xs">
                        LLM
                      </span>
                      <span className="text-xs font-semibold text-[#f3f1ed] group-hover:text-[#e5a84b]">
                        {activeLLM}
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-[#8c8984]">
                      Brain / Logic ↻
                    </span>
                  </div>

                  {/* TTS */}
                  <div
                    onClick={() => cycleOption(activeTTS, ttsOptions, setActiveTTS)}
                    className="p-2.5 rounded-lg border border-[#444246] hover:border-[#e5a84b]/50 bg-[#1d1c1e] cursor-pointer flex items-center justify-between transition-all group"
                  >
                    <div className="flex items-center gap-3">
                      <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 font-mono font-bold text-xs">
                        TTS
                      </span>
                      <span className="text-xs font-semibold text-[#f3f1ed] group-hover:text-[#e5a84b]">
                        {activeTTS}
                      </span>
                    </div>
                    <span className="text-[10px] font-mono text-[#8c8984]">
                      Voice Synthesizer ↻
                    </span>
                  </div>
                </div>

                {/* Connector line */}
                <div className="w-px h-4 bg-[#3d3b3f] mx-7" />

                {/* Telephony SIP Carrier */}
                <div
                  onClick={() => cycleOption(activeSIP, sipOptions, setActiveSIP)}
                  className="p-3.5 rounded-xl border border-[#3b3a3d] hover:border-[#e5a84b]/50 bg-[#27262a] cursor-pointer flex items-center justify-between transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <span className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 font-mono font-bold text-xs">
                      SIP
                    </span>
                    <div>
                      <div className="text-xs font-semibold text-[#f3f1ed] group-hover:text-[#e5a84b]">
                        {activeSIP}
                      </div>
                      <div className="text-[10px] text-[#7d7a76] font-mono">
                        Global Telephony & WebSocket Audio Gateway
                      </div>
                    </div>
                  </div>
                  <span className="text-xs text-[#8c8984] group-hover:text-[#f3f1ed]">
                    Carrier ↻
                  </span>
                </div>

                {/* Connector line */}
                <div className="w-px h-4 bg-[#3d3b3f] mx-7" />

                {/* Final Production Agent State */}
                <div className="p-3.5 rounded-xl border border-[#e5a84b]/30 bg-[#e5a84b]/5 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="size-8 rounded-full bg-[#e5a84b]/20 text-[#e5a84b] flex items-center justify-center font-bold">
                      ✓
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-[#f3f1ed]">
                        Production Agent Stack
                      </div>
                      <div className="text-[10px] text-[#8e8b86] font-mono">
                        Your custom pipeline, running live
                      </div>
                    </div>
                  </div>
                  <span className="flex items-center gap-1.5 text-[11px] font-mono text-[#e5a84b] font-bold">
                    <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
                    LIVE ON AIR
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* § Integrations Marquee Ticker */}
      <section className="py-20 border-b border-[#302f32] bg-[#1c1b1d] overflow-hidden">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 mb-8 text-center">
          <div className="font-mono text-xs uppercase tracking-[0.22em] text-[#e5a84b] font-semibold mb-2">
            § integrations
          </div>
          <p className="text-sm text-[#8f8c87]">
            Plug into 20+ speech engines, 15+ LLMs, and any carrier SIP trunk seamlessly
          </p>
        </div>

        {/* Lane 1: Scrolling Left */}
        <div className="relative overflow-hidden mb-4">
          <div className="flex w-max animate-ticker-left gap-6 py-2">
            {[...integrationsLane1, ...integrationsLane1].map((item, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2.5 px-4 py-2 rounded-lg border border-[#333235] bg-[#242326] text-xs font-mono uppercase tracking-wider text-[#cecbc6] shrink-0 hover:border-[#e5a84b]/50 transition-colors"
              >
                <span className="flex size-5 items-center justify-center rounded bg-[#333236] text-[10px] font-bold text-[#e5a84b]">
                  {item.logo}
                </span>
                {item.name}
              </div>
            ))}
          </div>
          <div className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-[#1c1b1d] to-transparent z-10" />
          <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-[#1c1b1d] to-transparent z-10" />
        </div>

        {/* Lane 2: Scrolling Right */}
        <div className="relative overflow-hidden">
          <div className="flex w-max animate-ticker-right gap-6 py-2">
            {[...integrationsLane2, ...integrationsLane2].map((item, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2.5 px-4 py-2 rounded-lg border border-[#333235] bg-[#242326] text-xs font-mono uppercase tracking-wider text-[#cecbc6] shrink-0 hover:border-[#e5a84b]/50 transition-colors"
              >
                <span className="flex size-5 items-center justify-center rounded bg-[#333236] text-[10px] font-bold text-emerald-400">
                  {item.logo}
                </span>
                {item.name}
              </div>
            ))}
          </div>
          <div className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-[#1c1b1d] to-transparent z-10" />
          <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-[#1c1b1d] to-transparent z-10" />
        </div>
      </section>

      {/* § Core Platform Highlights */}
      <section className="py-20 sm:py-28 border-b border-[#302f32] bg-[#1a191b]">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16 space-y-3">
            <div className="font-mono text-xs uppercase tracking-[0.22em] text-[#e5a84b] font-semibold">
              § architecture & capabilities
            </div>
            <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight text-[#f3f1ed]">
              Everything Required For Production Voice AI
            </h2>
            <p className="text-[#8f8c87] text-sm sm:text-base">
              Engineered for low latency, telephony reliability, and complete data governance.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div className="p-6 rounded-2xl border border-[#343336] bg-[#222124] hover:border-[#e5a84b]/40 transition-colors space-y-3">
              <div className="size-10 rounded-xl bg-[#e5a84b]/10 text-[#e5a84b] flex items-center justify-center">
                <Workflow className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-[#f3f1ed]">
                Visual Node Flow Canvas
              </h3>
              <p className="text-xs text-[#8f8c87] leading-relaxed">
                Build sophisticated multi-turn conversation state machines with subgraphs, branch conditions, dynamic extraction, and tool triggers on ReactFlow.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-[#343336] bg-[#222124] hover:border-[#e5a84b]/40 transition-colors space-y-3">
              <div className="size-10 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center">
                <Cpu className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-[#f3f1ed]">
                Sovereign Local CPU Stack
              </h3>
              <p className="text-xs text-[#8f8c87] leading-relaxed">
                Run 100% self-hosted Ollama (Qwen2.5) + Faster-Whisper STT + Piper Native Indic ONNX TTS directly on your server CPU. Zero cloud API keys and ₹0 minute costs.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-[#343336] bg-[#222124] hover:border-[#e5a84b]/40 transition-colors space-y-3">
              <div className="size-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
                <Phone className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-[#f3f1ed]">
                Carrier SIP & Inbound / Outbound
              </h3>
              <p className="text-xs text-[#8f8c87] leading-relaxed">
                Direct integration with Twilio, Telnyx, Plivo, Vonage, Exotel, and custom Asterisk PBX trunks. Batch outbound campaigns with CSV mapping.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-[#343336] bg-[#222124] hover:border-[#e5a84b]/40 transition-colors space-y-3">
              <div className="size-10 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center">
                <Globe className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-[#f3f1ed]">
                Indic Speech & Multilingual
              </h3>
              <p className="text-xs text-[#8f8c87] leading-relaxed">
                Native support for Hindi, Tamil, Telugu, Kannada, Bengali, and 10+ Indian languages powered by Navana Bodhi and Sarvam Indic models.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-[#343336] bg-[#222124] hover:border-[#e5a84b]/40 transition-colors space-y-3">
              <div className="size-10 rounded-xl bg-blue-500/10 text-blue-400 flex items-center justify-center">
                <Wrench className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-[#f3f1ed]">
                MCP Tools & Call Transfer
              </h3>
              <p className="text-xs text-[#8f8c87] leading-relaxed">
                Connect your voice agents to external APIs via Model Context Protocol (MCP), trigger dynamic webhooks, or warm-transfer calls to live human agents.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-[#343336] bg-[#222124] hover:border-[#e5a84b]/40 transition-colors space-y-3">
              <div className="size-10 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-[#f3f1ed]">
                Sovereign Multi-Tenant Wallet
              </h3>
              <p className="text-xs text-[#8f8c87] leading-relaxed">
                Built-in organization balance ledger and minute metering stored in local PostgreSQL. Completely independent of any external third-party services.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* § Self-Hosted CPU Box Spotlight */}
      <section className="py-20 border-b border-[#302f32] bg-[#1c1b1d]">
        <div className="mx-auto max-w-5xl px-4 sm:px-6">
          <div className="p-8 sm:p-10 rounded-2xl border border-[#e5a84b]/30 bg-gradient-to-b from-[#252327] to-[#1c1b1d] shadow-2xl relative overflow-hidden">
            <div className="max-w-2xl space-y-4">
              <span className="text-[10px] font-mono uppercase px-2.5 py-1 rounded bg-[#e5a84b]/15 text-[#e5a84b] border border-[#e5a84b]/30 font-semibold tracking-wider">
                LOW-SPEC VPS OPTIMIZATION
              </span>
              <h3 className="text-2xl sm:text-3xl font-bold text-[#f3f1ed] tracking-tight">
                Host The Entire Voice Stack On A 2–4 GB CPU Server
              </h3>
              <p className="text-sm text-[#9f9c96] leading-relaxed">
                No GPUs required. Kodewaves runs lightweight quantised models directly on standard Hostinger, Hetzner, or DigitalOcean CPU droplets using Docker Compose.
              </p>

              <div className="pt-2 grid grid-cols-2 gap-3 text-xs font-mono text-[#cecbc6]">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                  Qwen2.5 0.5B / 1.5B (Ollama)
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                  Faster-Whisper Tiny (Speaches STT)
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                  Piper ONNX Indic (Speaches TTS)
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                  Total RAM consumption &lt; 2.5 GB
                </div>
              </div>

              <div className="pt-4">
                <Link
                  href="/pricing"
                  className="inline-flex items-center gap-2 text-xs font-semibold text-[#e5a84b] hover:underline"
                >
                  View Self-Hosted vs Cloud Pricing comparison →
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Bottom CTA Banner */}
      <section className="py-20 sm:py-24 bg-[#171618] text-center">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 space-y-6">
          <h2 className="text-3xl sm:text-4xl font-bold text-[#f3f1ed] tracking-tight">
            Ready to Build Next-Generation Sovereign Voice Agents?
          </h2>
          <p className="text-[#8e8b86] text-sm sm:text-base max-w-xl mx-auto">
            Get started with complimentary minutes on our managed cloud or spin up a local instance on your own server.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3.5 pt-2">
            <Link
              href={isAuthenticated ? "/workflow" : "/auth/signup"}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-lg bg-[#e5a84b] px-6 py-3.5 text-sm font-semibold text-black transition-all hover:bg-[#d69637]"
            >
              {isAuthenticated ? "Enter Console" : "Start Building Free"}
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/pricing"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-lg border border-[#3b3a3d] bg-[#222124] px-6 py-3.5 text-sm font-medium text-[#f3f1ed] hover:border-[#e5a84b]/40 transition-colors"
            >
              View Pricing
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#302f32] bg-[#141315] py-12 text-xs text-[#706e6b]">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-[#e5a84b] text-black font-bold text-xs">
              KW
            </div>
            <span>Kodewaves Sovereign Voice AI Platform</span>
          </div>

          <div className="flex items-center gap-6">
            <Link href="/pricing" className="hover:text-[#f3f1ed] transition-colors">
              Pricing
            </Link>
            <Link
              href="https://github.com/adarsh09856/dog"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-[#f3f1ed] transition-colors"
            >
              GitHub
            </Link>
            <Link href="/auth/login" className="hover:text-[#f3f1ed] transition-colors">
              Sign In
            </Link>
            <Link href="/admin" className="hover:text-[#f3f1ed] transition-colors">
              Admin
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
