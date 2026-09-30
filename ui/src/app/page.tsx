"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Cpu,
  Globe2,
  PhoneCall,
  ShieldCheck,
  ArrowRight,
  CheckCircle2,
  Workflow,
  Sliders,
  Sparkles,
  Terminal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function LandingPage() {
  const [activePipelineStep, setActivePipelineStep] = useState<number>(2);
  const [hasAuthToken, setHasAuthToken] = useState(false);

  useEffect(() => {
    // Check if user is logged in via cookie
    const cookies = document.cookie;
    if (
      cookies.includes("kodewaves_auth_token") ||
      cookies.includes("dograh_auth_token") ||
      cookies.includes("oss_token")
    ) {
      setHasAuthToken(true);
    }
  }, []);

  const pipelineSteps = [
    {
      step: 1,
      title: "Audio Ingest",
      sub: "WebRTC 48kHz / Telephony 8kHz",
      desc: "Instant bidirectional audio streaming over WebSocket or native SIP trunk (Twilio, Exotel, Plivo).",
      latency: "15ms",
      badge: "Real-time Transport",
      providers: ["WebRTC Browser Client", "Twilio SIP", "Exotel Inbound", "Asterisk"],
    },
    {
      step: 2,
      title: "Speech-to-Text",
      sub: "Ultra-Fast ASR & Turn VAD",
      desc: "Streaming acoustic transcription with smart silence detection and 10+ Indic language acoustic models.",
      latency: "95ms",
      badge: "STT Engine",
      providers: ["Navana Bodhi Indic (Hindi/Tamil/Telugu)", "Deepgram Nova-3", "Faster-Whisper (Local CPU)"],
    },
    {
      step: 3,
      title: "System 1 Guardrail",
      sub: "TypeSafe Jev & Gemini Reflex",
      desc: "Sub-70ms intent classification, slot extraction, sentiment evaluation, and policy guardrails before main LLM.",
      latency: "60ms",
      badge: "Reflex Layer",
      providers: ["TypeSafe Jev AI", "Gemini 2.5 Flash Structured", "Local Rule Engine (0ms)"],
    },
    {
      step: 4,
      title: "Core Intelligence",
      sub: "Multi-Model Reasoning",
      desc: "Deep dialogue management with full tool execution, dynamic variables, CRM lookups, and visual workflow logic.",
      latency: "180ms",
      badge: "LLM Stage",
      providers: ["Gemini 2.5 Flash", "OpenAI GPT-4o", "Claude 3.5 Sonnet", "Qwen 2.5 1.5B (Local CPU)"],
    },
    {
      step: 5,
      title: "Voice Synthesis",
      sub: "Hyper-Realistic Neural Audio",
      desc: "Natural human-like speech streaming with millisecond time-to-first-byte (TTFB) and authentic Indian accents.",
      latency: "85ms",
      badge: "TTS Synthesis",
      providers: ["Cartesia Sonic 3.5", "Navana Bodhi TTS", "ElevenLabs Flash", "Kokoro-82M (Local CPU)"],
    },
  ];

  const providerLogos = [
    { name: "Google Gemini", type: "Multimodal LLM / Live" },
    { name: "Navana.ai", type: "10 Indic Languages" },
    { name: "Deepgram", type: "Streaming STT" },
    { name: "Cartesia", type: "Sub-100ms TTS" },
    { name: "ElevenLabs", type: "Voice Cloning" },
    { name: "OpenAI", type: "GPT-4o & Realtime" },
    { name: "Anthropic", type: "Claude 3.5 Sonnet" },
    { name: "Exotel", type: "Indian Telephony" },
    { name: "Twilio", type: "Global SIP Trunks" },
    { name: "Sarvam.ai", type: "Indic Voices" },
    { name: "Ollama / Speaches", type: "Local CPU Stack" },
  ];

  return (
    <div className="min-h-screen bg-[#0c0d0e] text-stone-100 selection:bg-amber-500/30 selection:text-amber-200">
      {/* Background Ambience */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[1100px] h-[600px] bg-gradient-to-b from-amber-500/12 via-orange-500/5 to-transparent blur-3xl opacity-80" />
        <div className="absolute top-[1200px] -left-40 w-[600px] h-[600px] bg-amber-600/5 blur-3xl rounded-full" />
        <div className="absolute top-[2000px] -right-40 w-[700px] h-[700px] bg-orange-600/5 blur-3xl rounded-full" />
      </div>

      {/* Navigation Header */}
      <header className="sticky top-0 z-50 border-b border-white/5 bg-[#0c0d0e]/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center text-stone-950 font-bold text-lg shadow-lg shadow-amber-500/20">
              K
            </div>
            <span className="font-bold text-lg tracking-tight text-white">
              Kodewaves <span className="text-amber-400 font-mono text-xs uppercase px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20">Sovereign</span>
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-stone-300">
            <a href="#pipeline" className="hover:text-amber-400 transition-colors">Pipeline</a>
            <a href="#features" className="hover:text-amber-400 transition-colors">Features</a>
            <a href="#indic" className="hover:text-amber-400 transition-colors">Indic AI</a>
            <a href="#local-cpu" className="hover:text-amber-400 transition-colors">Local CPU Stack</a>
            <Link href="/pricing" className="hover:text-amber-400 transition-colors">Pricing</Link>
            <a href="https://github.com/dograh-hq/dograh" target="_blank" rel="noreferrer" className="hover:text-amber-400 transition-colors">Docs</a>
          </nav>

          <div className="flex items-center gap-3">
            {hasAuthToken ? (
              <Link href="/workflow">
                <Button size="sm" className="bg-amber-500 hover:bg-amber-400 text-stone-950 font-semibold text-xs shadow-md shadow-amber-500/20">
                  Go to Console <ArrowRight className="h-3.5 w-3.5 ml-1" />
                </Button>
              </Link>
            ) : (
              <>
                <Link href="/auth/login">
                  <Button variant="ghost" size="sm" className="text-stone-300 hover:text-white hover:bg-white/5 text-xs">
                    Sign In
                  </Button>
                </Link>
                <Link href="/auth/signup">
                  <Button size="sm" className="bg-amber-500 hover:bg-amber-400 text-stone-950 font-semibold text-xs shadow-md shadow-amber-500/20">
                    Get Started Free
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 sm:pt-28 pb-20 text-center space-y-8">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/25 text-amber-300 text-xs font-mono shadow-inner shadow-amber-500/5">
          <Sparkles className="h-3.5 w-3.5 text-amber-400 animate-pulse" />
          <span>Sovereign Voice AI Architecture • 100% Self-Hosted & Multi-Cloud</span>
        </div>

        <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-white max-w-5xl mx-auto leading-[1.1]">
          Build Ultra-Fast Voice AI Agents That Sound{" "}
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-300 via-amber-400 to-orange-400">
            Incredibly Human.
          </span>
        </h1>

        <p className="max-w-2xl mx-auto text-base sm:text-lg text-stone-400 leading-relaxed font-normal">
          Deploy conversational telephony and WebRTC voice agents in 10+ Indic languages. Zero vendor lock-in, ultra-low latency (&lt;400ms), and 90% cheaper than traditional cloud platforms.
        </p>

        {/* Action CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
          <Link href="/auth/signup">
            <Button size="lg" className="h-12 px-8 bg-amber-500 hover:bg-amber-400 text-stone-950 font-bold text-sm shadow-xl shadow-amber-500/25 gap-2">
              Launch Agent Builder <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link href="/pricing">
            <Button size="lg" variant="outline" className="h-12 px-8 border-white/15 hover:bg-white/5 text-white font-medium text-sm">
              Explore Sovereign Pricing (₹0.55/m)
            </Button>
          </Link>
        </div>

        {/* Live Metrics Pill Strip */}
        <div className="pt-10 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto text-left">
          <div className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm">
            <div className="text-2xl font-mono font-bold text-amber-400">&lt; 380ms</div>
            <div className="text-xs text-stone-400 mt-1">Glass-to-Glass Latency</div>
          </div>
          <div className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm">
            <div className="text-2xl font-mono font-bold text-emerald-400">₹0.55/min</div>
            <div className="text-xs text-stone-400 mt-1">Starting Turn Cost</div>
          </div>
          <div className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm">
            <div className="text-2xl font-mono font-bold text-white">10+ Indic</div>
            <div className="text-xs text-stone-400 mt-1">Native Indian Dialects</div>
          </div>
          <div className="p-4 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm">
            <div className="text-2xl font-mono font-bold text-indigo-400">Zero GPU</div>
            <div className="text-xs text-stone-400 mt-1">Runs on 2-4GB CPU VPS</div>
          </div>
        </div>
      </section>

      {/* Provider Ecosystem Ticker */}
      <section className="border-y border-white/5 bg-[#090a0b]/60 py-6 overflow-hidden">
        <div className="max-w-7xl mx-auto px-4 flex flex-col md:flex-row items-center gap-6">
          <span className="text-xs font-mono uppercase tracking-widest text-stone-400 shrink-0">
            Integrated Providers:
          </span>
          <div className="flex flex-wrap items-center gap-3 sm:gap-6 justify-center">
            {providerLogos.map((prov, i) => (
              <div
                key={i}
                className="px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/10 text-xs text-stone-300 font-medium flex items-center gap-2"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                <span>{prov.name}</span>
                <span className="text-[10px] text-stone-400 hidden sm:inline">({prov.type})</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Interactive Pipeline Architecture Section */}
      <section id="pipeline" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 space-y-12">
        <div className="text-center max-w-3xl mx-auto space-y-3">
          <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/30 uppercase tracking-widest text-[11px] font-mono py-1 px-3">
            Real-Time Pipeline Architecture
          </Badge>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white">
            Inspect the Millisecond Voice Pipeline
          </h2>
          <p className="text-sm sm:text-base text-stone-400">
            Click any step to inspect how audio, System 1 reflex classification, and audio synthesis achieve sub-second response times.
          </p>
        </div>

        {/* Interactive Step Switcher */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 max-w-4xl mx-auto">
          {pipelineSteps.map((s, idx) => (
            <button
              key={s.step}
              type="button"
              onClick={() => setActivePipelineStep(idx)}
              className={`p-3.5 rounded-xl text-left border transition-all ${
                activePipelineStep === idx
                  ? "bg-amber-500/10 border-amber-500 text-white shadow-lg shadow-amber-500/10"
                  : "bg-white/5 border-white/10 text-stone-400 hover:text-white hover:border-white/20"
              }`}
            >
              <div className="text-[10px] font-mono text-amber-400/80">0{s.step} • {s.latency}</div>
              <div className="text-xs font-bold mt-1 text-white">{s.title}</div>
            </button>
          ))}
        </div>

        {/* Selected Step Display Card */}
        {(() => {
          const step = pipelineSteps[activePipelineStep];
          return (
            <div className="p-8 sm:p-10 rounded-3xl bg-gradient-to-br from-[#131518] to-[#0e0f11] border border-amber-500/30 shadow-2xl max-w-4xl mx-auto relative overflow-hidden">
              <div className="absolute top-0 right-0 w-80 h-80 bg-amber-500/10 blur-3xl rounded-full pointer-events-none" />

              <div className="space-y-6 relative z-10">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <Badge variant="outline" className="border-amber-500/40 text-amber-400 font-mono text-xs mb-2">
                      {step.badge}
                    </Badge>
                    <h3 className="text-2xl font-bold text-white">{step.title}: {step.sub}</h3>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-mono font-extrabold text-amber-400">{step.latency}</div>
                    <div className="text-[11px] text-stone-400">Target Segment Latency</div>
                  </div>
                </div>

                <p className="text-sm text-stone-300 leading-relaxed max-w-2xl">
                  {step.desc}
                </p>

                <div className="pt-4 border-t border-white/10">
                  <div className="text-xs font-mono text-stone-400 uppercase tracking-wider mb-3">
                    Active Drivers & Models Available:
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {step.providers.map((p, pi) => (
                      <span
                        key={pi}
                        className="px-3 py-1 rounded-lg bg-white/10 border border-white/15 text-xs text-stone-200 font-medium"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          );
        })()}
      </section>

      {/* Feature Grid */}
      <section id="features" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 space-y-16">
        <div className="text-center max-w-3xl mx-auto space-y-3">
          <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/30 uppercase tracking-widest text-[11px] font-mono py-1 px-3">
            Platform Capabilities
          </Badge>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white">
            Everything Required For Production Telephony
          </h2>
          <p className="text-sm sm:text-base text-stone-400">
            Engineered from ground up with enterprise multi-tenancy, credit wallet ledger, and sovereign key isolation.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {/* Card 1 */}
          <div className="p-6 rounded-2xl bg-[#111214] border border-white/10 space-y-4 hover:border-amber-500/40 transition-colors">
            <div className="h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Globe2 className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Indic Speech Mastery</h3>
            <p className="text-xs text-stone-400 leading-relaxed">
              Official Navana.ai Bodhi integration providing native 8kHz telephony ASR & TTS in Hindi, Tamil, Telugu, Kannada, Marathi, Gujarati, Bengali, and Malayalam.
            </p>
          </div>

          {/* Card 2 */}
          <div className="p-6 rounded-2xl bg-[#111214] border border-white/10 space-y-4 hover:border-amber-500/40 transition-colors">
            <div className="h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Cpu className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Local CPU AI Engine</h3>
            <p className="text-xs text-stone-400 leading-relaxed">
              Self-host lightweight Qwen 2.5 1.5B, Faster-Whisper, and Kokoro-82M directly on your 2–4GB VPS. Admin opt-in control protects host resources while cutting third-party bills to zero.
            </p>
          </div>

          {/* Card 3 */}
          <div className="p-6 rounded-2xl bg-[#111214] border border-white/10 space-y-4 hover:border-amber-500/40 transition-colors">
            <div className="h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Workflow className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Visual Node Flow Canvas</h3>
            <p className="text-xs text-stone-400 leading-relaxed">
              Drag-and-drop conversational graph builder powered by React Flow. Create branching logic, form collection, API webhooks, and live human transfers visually.
            </p>
          </div>

          {/* Card 4 */}
          <div className="p-6 rounded-2xl bg-[#111214] border border-white/10 space-y-4 hover:border-amber-500/40 transition-colors">
            <div className="h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">System 1 Guardrails (Jev AI)</h3>
            <p className="text-xs text-stone-400 leading-relaxed">
              Instant reflex classification detects user intent, sentiment, and escalation requests in 60ms. Automated PII masking protects confidential numbers before audio leaves.
            </p>
          </div>

          {/* Card 5 */}
          <div className="p-6 rounded-2xl bg-[#111214] border border-white/10 space-y-4 hover:border-amber-500/40 transition-colors">
            <div className="h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <PhoneCall className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Carrier Telephony & SIP</h3>
            <p className="text-xs text-stone-400 leading-relaxed">
              Connect Indian carriers (Exotel) or global providers (Twilio, Plivo, Telnyx). Auto-reconnecting WSS stream handlers guarantee zero dropped calls on edge networks.
            </p>
          </div>

          {/* Card 6 */}
          <div className="p-6 rounded-2xl bg-[#111214] border border-white/10 space-y-4 hover:border-amber-500/40 transition-colors">
            <div className="h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Sliders className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Wallet Ledger & Multi-Tenancy</h3>
            <p className="text-xs text-stone-400 leading-relaxed">
              Every second of speech is metered and deducted in real-time. Superadmins can manage plans, award promotional credits, set concurrency caps, and view live monitoring.
            </p>
          </div>
        </div>
      </section>

      {/* Local CPU Stack Spotlight Section */}
      <section id="local-cpu" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="p-8 sm:p-12 rounded-3xl bg-gradient-to-r from-[#141517] to-[#101214] border border-white/10 shadow-xl grid lg:grid-cols-12 gap-8 items-center">
          <div className="lg:col-span-7 space-y-6">
            <Badge className="bg-indigo-500/10 text-indigo-400 border-indigo-500/30 uppercase tracking-widest text-[11px] font-mono py-1 px-3">
              Low-RAM VPS Optimization
            </Badge>
            <h2 className="text-3xl sm:text-4xl font-bold text-white">
              Host the Entire Voice Stack On A 2–4 GB CPU Server
            </h2>
            <p className="text-sm text-stone-300 leading-relaxed">
              No expensive Nvidia GPU instances required. Kodewaves packages an ultra-lightweight Docker stack that combines Qwen 2.5 1.5B (or Phi-4 Mini), Faster-Whisper, and Kokoro-82M into a 2GB memory footprint.
            </p>
            <div className="grid sm:grid-cols-2 gap-3 text-xs text-stone-300 pt-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Zero external API keys needed</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>100% on-premise privacy (HIPAA/GDPR)</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Strict Docker RAM memory caps</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Admin opt-in toggle per user</span>
              </div>
            </div>
            <div className="pt-2">
              <Link href="/pricing">
                <Button className="bg-white/10 hover:bg-white/20 text-white text-xs">
                  View Sovereign Tiers <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
                </Button>
              </Link>
            </div>
          </div>

          <div className="lg:col-span-5 bg-[#090a0c] p-6 rounded-2xl border border-white/10 font-mono text-xs text-stone-300 space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-white/5 text-[11px] text-stone-400">
              <span className="flex items-center gap-1.5 text-amber-400">
                <Terminal className="h-3.5 w-3.5" /> docker-compose ps
              </span>
              <span className="text-emerald-400">All Healthy</span>
            </div>
            <div className="space-y-1.5 text-[11px] leading-relaxed">
              <div className="text-emerald-400">✔ ollama_cpu (qwen2.5:1.5b) [RAM: ~1.2GB]</div>
              <div className="text-emerald-400">✔ speaches_stt (faster-whisper) [RAM: ~450MB]</div>
              <div className="text-emerald-400">✔ speaches_tts (kokoro-82m) [RAM: ~320MB]</div>
              <div className="text-stone-400 pt-2">Total VPS Footprint: ~2.0 GB RAM</div>
              <div className="text-amber-400">Cost: $0.00 / minute cloud billing</div>
            </div>
          </div>
        </div>
      </section>

      {/* Call to Action Banner */}
      <section className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="p-10 sm:p-14 rounded-3xl bg-gradient-to-b from-[#181a1d] to-[#121316] border border-amber-500/30 text-center space-y-6 relative overflow-hidden shadow-2xl">
          <div className="absolute inset-0 bg-gradient-to-r from-amber-500/5 via-orange-500/10 to-amber-500/5 pointer-events-none" />

          <h2 className="text-3xl sm:text-4xl font-extrabold text-white">
            Ready to Build Next-Generation Sovereign Voice Agents?
          </h2>
          <p className="text-sm sm:text-base text-stone-400 max-w-xl mx-auto">
            Get started with 60 complimentary minutes. Zero credit card required for onboarding.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
            <Link href="/auth/signup">
              <Button size="lg" className="h-12 px-8 bg-amber-500 hover:bg-amber-400 text-stone-950 font-bold text-sm shadow-xl shadow-amber-500/25">
                Start Building Free
              </Button>
            </Link>
            <Link href="/pricing">
              <Button size="lg" variant="outline" className="h-12 px-8 border-white/15 hover:bg-white/5 text-white font-medium text-sm">
                View Pricing Plans
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 bg-[#08090a] py-12 text-stone-400 text-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded bg-amber-500 flex items-center justify-center text-stone-950 font-bold text-xs">
              K
            </div>
            <span className="font-semibold text-white">Kodewaves Sovereign Voice AI</span>
            <span className="text-stone-400">© 2026. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-6">
            <Link href="/pricing" className="hover:text-amber-400 transition-colors">Pricing</Link>
            <Link href="/workflow" className="hover:text-amber-400 transition-colors">Builder</Link>
            <Link href="/auth/login" className="hover:text-amber-400 transition-colors">Sign In</Link>
            <Link href="/auth/signup" className="hover:text-amber-400 transition-colors">Register</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
