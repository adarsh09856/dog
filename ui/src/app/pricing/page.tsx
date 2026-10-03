"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Check,
  Zap,
  ArrowRight,
  Calculator,
  ChevronDown,
  HelpCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { publicApi, SaaSPlan, CreditPackage } from "@/lib/kodewavesApi";

export default function PricingPage() {
  const [billingCycle, setBillingCycle] = useState<"monthly" | "annual">("monthly");
  const [currency, setCurrency] = useState<"INR" | "USD">("INR");
  const [plans, setPlans] = useState<SaaSPlan[]>([]);
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [calculatorMinutes, setCalculatorMinutes] = useState(2500);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [plansData, pkgsData] = await Promise.allSettled([
          publicApi.getPublicPlans(),
          publicApi.getPublicCreditPackages(),
        ]);
        if (plansData.status === "fulfilled" && plansData.value?.length) {
          setPlans(plansData.value);
        }
        if (pkgsData.status === "fulfilled" && pkgsData.value?.length) {
          setPackages(pkgsData.value);
        }
      } catch (err) {
        console.warn("Could not fetch dynamic plans, using sovereign defaults", err);
      }
    }
    loadData();
  }, []);

  // Default plans if API hasn't loaded or is offline
  const defaultPlans: SaaSPlan[] = [
    {
      id: 1,
      name: "Starter",
      code: "starter",
      description: "Ideal for testing voice workflows, prototypes, and low-volume inbound inquiries.",
      monthly_price_inr: 1499,
      monthly_price_usd: 19,
      included_minutes: 100,
      overage_rate_per_minute: 1.2,
      max_concurrent_calls: 2,
      allow_user_byok: true,
      features: [
        "100 Included Voice Minutes",
        "2 Concurrent Channels",
        "All 20+ Model Providers",
        "WebRTC Web Widget",
        "Standard SIP / Telephony",
        "Visual Node Workflow Builder",
        "Basic Call Analytics",
      ],
      is_active: true,
      is_public: true,
    },
    {
      id: 2,
      name: "Professional",
      code: "pro",
      description: "For growing teams running outbound campaigns and customer service automation.",
      monthly_price_inr: 4999,
      monthly_price_usd: 59,
      included_minutes: 500,
      overage_rate_per_minute: 0.95,
      max_concurrent_calls: 8,
      allow_user_byok: true,
      features: [
        "500 Included Voice Minutes",
        "8 Concurrent Channels",
        "Navana Bodhi 10 Indic Languages",
        "Sub-500ms Gemini Live Integration",
        "Twilio & Exotel Native SIP",
        "Outbound CSV Call Campaigns",
        "System 1 Jev Decision Guardrail",
        "Priority Support",
      ],
      is_active: true,
      is_public: true,
    },
    {
      id: 3,
      name: "Scale / Business",
      code: "scale",
      description: "High concurrency voice agents with dedicated infrastructure and enterprise uptime.",
      monthly_price_inr: 14999,
      monthly_price_usd: 179,
      included_minutes: 2000,
      overage_rate_per_minute: 0.75,
      max_concurrent_calls: 25,
      allow_user_byok: true,
      features: [
        "2,000 Included Voice Minutes",
        "25 Concurrent Channels",
        "Lowest ₹0.55/min Internal Route",
        "Custom Voice Cloning Support",
        "Direct CRM & Webhook Sync",
        "Real-Time Human Transfer",
        "Advanced Answering Machine Detection",
        "Dedicated Account Engineer",
      ],
      is_active: true,
      is_public: true,
    },
    {
      id: 4,
      name: "Sovereign Enterprise",
      code: "enterprise",
      description: "Zero third-party cloud bills. 100% On-Premise / Private VPS deployment.",
      monthly_price_inr: 34999,
      monthly_price_usd: 429,
      included_minutes: 10000,
      overage_rate_per_minute: 0.55,
      max_concurrent_calls: 100,
      allow_user_byok: true,
      features: [
        "10,000 Included Voice Minutes",
        "100+ Concurrent Channels",
        "Local CPU AI Engine (Ollama + Whisper)",
        "Zero External Data Transmission (HIPAA/GDPR)",
        "Full White-Label Branding & Domain",
        "Custom Telecom Interconnects",
        "99.99% Guaranteed SLA",
        "24/7 Phone & Slack Support",
      ],
      is_active: true,
      is_public: true,
    },
  ];

  const displayPlans = plans.length > 0 ? plans : defaultPlans;

  const defaultPackages: CreditPackage[] = [
    { id: 1, name: "Starter Pack", minutes: 250, price_inr: 299, price_usd: 4, bonus_minutes: 25, is_popular: false, is_active: true },
    { id: 2, name: "Growth Pack", minutes: 1000, price_inr: 999, price_usd: 12, bonus_minutes: 150, is_popular: true, is_active: true },
    { id: 3, name: "Pro Pack", minutes: 5000, price_inr: 4499, price_usd: 55, bonus_minutes: 1000, is_popular: false, is_active: true },
    { id: 4, name: "High Volume", minutes: 20000, price_inr: 15999, price_usd: 199, bonus_minutes: 5000, is_popular: false, is_active: true },
  ];

  const displayPackages = packages.length > 0 ? packages : defaultPackages;

  // Cost comparison math:
  // Typical Cloud Stack (Twilio $0.015/m + Deepgram $0.007/m + GPT-4o $0.04/m + ElevenLabs $0.08/m) = ~$0.14/m (~₹12.00/min)
  // Kodewaves Sovereign Stack (Exotel SIP ₹0.30 + Navana ₹0.20 + Gemini 2.5 Flash ₹0.15 + Cartesia ₹0.25) = ~₹0.90/min
  const typicalCloudRate = currency === "INR" ? 12.0 : 0.14;
  const kodewavesRate = currency === "INR" ? 0.90 : 0.011;
  const cloudTotalCost = Math.round(calculatorMinutes * typicalCloudRate);
  const kodewavesTotalCost = Math.round(calculatorMinutes * kodewavesRate);
  const savings = cloudTotalCost - kodewavesTotalCost;
  const savingsPercent = Math.round((savings / cloudTotalCost) * 100);

  const faqs = [
    {
      q: "What makes Kodewaves 90% cheaper than Retell or Vapi?",
      a: "Traditional voice platforms charge high markups on top of expensive US cloud providers (Twilio, ElevenLabs, OpenAI). Kodewaves provides native direct integration with ultra-cost-effective sovereign models like Navana Bodhi Indic speech, Gemini 2.5 Flash, Cartesia Sonic, and even ultra-lightweight self-hosted local CPU models (Faster-Whisper + Piper ONNX Hindi), bringing your effective per-minute cost down from ₹12–18/min to just ₹0.55–1.20/min.",
    },
    {
      q: "Can I bring my own API keys (BYOK)?",
      a: "Yes! Kodewaves fully supports Bring-Your-Own-Key for all providers (OpenAI, Gemini, Anthropic, ElevenLabs, Deepgram, Cartesia, Twilio, Exotel). If you use your own keys, you only pay for the platform base subscription without any voice minute markups.",
    },
    {
      q: "How does the Local CPU AI Engine work on a low-RAM VPS?",
      a: "Our self-hosted stack uses lightweight quantized models specifically optimized for CPUs: Qwen 2.5 1.5B (or Phi-4 Mini), Faster-Whisper (STT), and Piper Native Indic ONNX (TTS). It operates within 2–3 GB RAM inside Docker containers, allowing you to run zero-cloud voice agents on budget cloud servers without GPUs.",
    },
    {
      q: "Which Indian languages and accents are supported?",
      a: "Through our official Navana.ai Bodhi integration, we offer state-of-the-art native speech recognition and synthesis across 10 Indic languages: Hindi, English (Indian accent), Tamil, Telugu, Kannada, Marathi, Gujarati, Bengali, Malayalam, and Punjabi, tuned specifically for telephonic 8kHz audio.",
    },
    {
      q: "Do unused voice minutes expire?",
      a: "Prepaid wallet minutes and bonus package minutes never expire as long as your account remains active. Subscription plan included minutes reset on your monthly billing cycle.",
    },
  ];

  return (
    <div className="min-h-screen bg-[#0c0d0e] text-stone-100 selection:bg-amber-500/30 selection:text-amber-200">
      {/* Background Glow */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[500px] bg-gradient-to-b from-amber-500/10 via-orange-500/5 to-transparent blur-3xl opacity-70" />
        <div className="absolute top-[800px] -right-40 w-[600px] h-[600px] bg-amber-600/5 blur-3xl rounded-full" />
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
            <Link href="/" className="hover:text-amber-400 transition-colors">Platform</Link>
            <Link href="/pricing" className="text-amber-400">Pricing</Link>
            <Link href="/workflow" className="hover:text-amber-400 transition-colors">Builder</Link>
            <a href="/docs" target="_blank" rel="noreferrer" className="hover:text-amber-400 transition-colors">Docs</a>
          </nav>

          <div className="flex items-center gap-3">
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
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-28 space-y-24">
        {/* Header Section */}
        <div className="text-center max-w-3xl mx-auto space-y-4">
          <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/30 uppercase tracking-widest text-[11px] font-mono py-1 px-3">
            Transparent Sovereign Economics
          </Badge>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-white">
            High Performance Voice AI. <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-300 via-amber-400 to-orange-400">
              Fraction of the Cloud Cost.
            </span>
          </h1>
          <p className="text-base sm:text-lg text-stone-400 leading-relaxed">
            No punitive markups. Deploy conversational voice agents on your choice of multi-cloud or self-hosted CPU infrastructure.
          </p>

          {/* Toggles */}
          <div className="pt-6 flex flex-wrap items-center justify-center gap-4">
            {/* Monthly / Annual */}
            <div className="inline-flex p-1 rounded-xl bg-white/5 border border-white/10 backdrop-blur-md">
              <button
                type="button"
                onClick={() => setBillingCycle("monthly")}
                className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  billingCycle === "monthly" ? "bg-amber-500 text-stone-950 shadow-sm font-semibold" : "text-stone-400 hover:text-white"
                }`}
              >
                Monthly
              </button>
              <button
                type="button"
                onClick={() => setBillingCycle("annual")}
                className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 ${
                  billingCycle === "annual" ? "bg-amber-500 text-stone-950 shadow-sm font-semibold" : "text-stone-400 hover:text-white"
                }`}
              >
                Annual <span className="text-[10px] px-1 py-0.2 rounded bg-amber-400/20 text-amber-950 font-bold">Save 20%</span>
              </button>
            </div>

            {/* Currency Selector */}
            <div className="inline-flex p-1 rounded-xl bg-white/5 border border-white/10">
              <button
                type="button"
                onClick={() => setCurrency("INR")}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  currency === "INR" ? "bg-white/15 text-white font-semibold" : "text-stone-400 hover:text-white"
                }`}
              >
                INR (₹)
              </button>
              <button
                type="button"
                onClick={() => setCurrency("USD")}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  currency === "USD" ? "bg-white/15 text-white font-semibold" : "text-stone-400 hover:text-white"
                }`}
              >
                USD ($)
              </button>
            </div>
          </div>
        </div>

        {/* Pricing Cards Grid */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {displayPlans.map((plan, idx) => {
            const isPopular = plan.code === "pro" || idx === 1;
            const rawPrice = currency === "INR" ? plan.monthly_price_inr : plan.monthly_price_usd;
            const price = billingCycle === "annual" ? Math.round(rawPrice * 0.8) : rawPrice;
            const sym = currency === "INR" ? "₹" : "$";

            return (
              <Card
                key={plan.id || plan.code}
                className={`relative flex flex-col justify-between transition-all duration-300 ${
                  isPopular
                    ? "bg-[#141517] border-amber-500/50 shadow-2xl shadow-amber-500/10 ring-1 ring-amber-500/30 scale-105 z-10"
                    : "bg-[#111214] border-white/10 hover:border-white/20"
                }`}
              >
                {isPopular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <Badge className="bg-amber-500 text-stone-950 font-bold uppercase tracking-wider text-[10px] px-3 shadow-md shadow-amber-500/30">
                      Most Popular
                    </Badge>
                  </div>
                )}

                <CardHeader className="space-y-2 pb-4">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-xl font-bold text-white">{plan.name}</CardTitle>
                    <Badge variant="outline" className="border-white/10 text-stone-400 text-[10px] font-mono">
                      {plan.max_concurrent_calls} Channels
                    </Badge>
                  </div>
                  <CardDescription className="text-xs text-stone-400 min-h-[36px] line-clamp-2">
                    {plan.description}
                  </CardDescription>

                  <div className="pt-3">
                    <div className="flex items-baseline gap-1">
                      <span className="text-3xl font-extrabold text-white">{sym}{price.toLocaleString()}</span>
                      <span className="text-xs text-stone-400">/month</span>
                    </div>
                    <p className="text-[11px] text-amber-400/90 mt-1 font-mono">
                      Includes {plan.included_minutes.toLocaleString()} mins ({sym}{plan.overage_rate_per_minute}/extra min)
                    </p>
                  </div>
                </CardHeader>

                <CardContent className="space-y-3 py-4 border-t border-white/5 flex-1">
                  <div className="text-[11px] font-mono text-stone-400 uppercase tracking-wider">Features Included</div>
                  <ul className="space-y-2 text-xs text-stone-300">
                    {(plan.features || []).map((feat, fIdx) => (
                      <li key={fIdx} className="flex items-start gap-2">
                        <Check className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>

                <CardFooter className="pt-4 border-t border-white/5">
                  <Link href={`/auth/signup?plan=${plan.code}`} className="w-full">
                    <Button
                      className={`w-full text-xs font-semibold h-10 ${
                        isPopular
                          ? "bg-amber-500 hover:bg-amber-400 text-stone-950 shadow-md shadow-amber-500/20"
                          : "bg-white/10 hover:bg-white/20 text-white"
                      }`}
                    >
                      Choose {plan.name} <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
                    </Button>
                  </Link>
                </CardFooter>
              </Card>
            );
          })}
        </div>

        {/* Top-up Minutes Packages */}
        <div className="space-y-6">
          <div className="text-center max-w-2xl mx-auto space-y-2">
            <h2 className="text-2xl sm:text-3xl font-bold text-white flex items-center justify-center gap-2">
              <Zap className="h-6 w-6 text-amber-400" />
              Prepaid Minute Top-Ups
            </h2>
            <p className="text-xs sm:text-sm text-stone-400">
              Need extra volume without changing tiers? Purchase non-expiring minutes anytime.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {displayPackages.map((pkg) => {
              const price = currency === "INR" ? pkg.price_inr : pkg.price_usd;
              const sym = currency === "INR" ? "₹" : "$";
              const totalMins = pkg.minutes + (pkg.bonus_minutes || 0);

              return (
                <div
                  key={pkg.id}
                  className={`p-5 rounded-2xl border transition-all ${
                    pkg.is_popular
                      ? "bg-amber-500/10 border-amber-500/40 shadow-lg shadow-amber-500/5"
                      : "bg-[#111214] border-white/10 hover:border-white/20"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold text-white">{pkg.name}</span>
                    {pkg.is_popular && (
                      <Badge className="bg-amber-500 text-stone-950 text-[9px] font-bold px-2 py-0">BEST VALUE</Badge>
                    )}
                  </div>
                  <div className="flex items-baseline gap-1 my-3">
                    <span className="text-2xl font-bold text-white">{sym}{price.toLocaleString()}</span>
                  </div>
                  <div className="space-y-1 text-xs text-stone-300 pb-4">
                    <div className="font-semibold text-amber-400">{pkg.minutes.toLocaleString()} standard minutes</div>
                    {pkg.bonus_minutes > 0 && (
                      <div className="text-[11px] text-emerald-400 font-mono">+{pkg.bonus_minutes} bonus minutes included</div>
                    )}
                    <div className="text-[10px] text-stone-400 pt-1">Never expires • Usable on any agent</div>
                  </div>
                  <Link href="/auth/signup">
                    <Button variant="outline" size="sm" className="w-full text-xs border-white/15 hover:bg-white/10 text-white">
                      Add to Wallet
                    </Button>
                  </Link>
                </div>
              );
            })}
          </div>
        </div>

        {/* Interactive Cost Calculator */}
        <div className="p-8 sm:p-12 rounded-3xl bg-gradient-to-b from-[#141619] to-[#0f1012] border border-amber-500/20 shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-amber-500/5 blur-3xl rounded-full pointer-events-none" />

          <div className="grid lg:grid-cols-12 gap-8 items-center">
            <div className="lg:col-span-7 space-y-6">
              <div className="inline-flex items-center gap-2 text-xs font-mono text-amber-400 bg-amber-500/10 border border-amber-500/20 px-3 py-1 rounded-full">
                <Calculator className="h-3.5 w-3.5" />
                Live ROI & Cost Comparison Calculator
              </div>

              <h2 className="text-2xl sm:text-3xl font-extrabold text-white">
                Calculate Your Monthly Voice Savings
              </h2>
              <p className="text-sm text-stone-400 leading-relaxed">
                See what you spend on traditional platforms (Retell / Vapi with OpenAI + ElevenLabs) versus the Kodewaves Sovereign Stack.
              </p>

              <div className="space-y-4 pt-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-stone-300 font-medium">Monthly Call Volume:</span>
                  <span className="font-mono text-lg font-bold text-amber-400">{calculatorMinutes.toLocaleString()} minutes</span>
                </div>
                <input
                  type="range"
                  min={500}
                  max={50000}
                  step={500}
                  value={calculatorMinutes}
                  onChange={(e) => setCalculatorMinutes(parseInt(e.target.value) || 500)}
                  className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
                <div className="flex justify-between text-[11px] font-mono text-stone-400">
                  <span>500 mins</span>
                  <span>10,000 mins</span>
                  <span>50,000 mins</span>
                </div>
              </div>
            </div>

            <div className="lg:col-span-5 bg-[#0a0a0c] p-6 rounded-2xl border border-white/10 space-y-6">
              <div className="space-y-3">
                <div className="flex justify-between text-xs text-stone-400 pb-1 border-b border-white/5">
                  <span>Traditional Cloud Voice</span>
                  <span className="font-mono font-semibold text-stone-300">
                    {currency === "INR" ? `₹${cloudTotalCost.toLocaleString()}` : `$${cloudTotalCost.toLocaleString()}`}
                  </span>
                </div>
                <div className="flex justify-between text-xs text-amber-400/90 font-medium pb-1 border-b border-white/5">
                  <span>Kodewaves Sovereign Platform</span>
                  <span className="font-mono font-bold text-white">
                    {currency === "INR" ? `₹${kodewavesTotalCost.toLocaleString()}` : `$${kodewavesTotalCost.toLocaleString()}`}
                  </span>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-center space-y-1">
                <div className="text-xs uppercase font-mono text-amber-400 font-semibold tracking-wider">Your Monthly Savings</div>
                <div className="text-3xl font-extrabold text-amber-300 font-mono">
                  {currency === "INR" ? `₹${savings.toLocaleString()}` : `$${savings.toLocaleString()}`}
                </div>
                <div className="text-[11px] text-emerald-400 font-medium">({savingsPercent}% reduction in telephony bills)</div>
              </div>

              <Link href="/auth/signup" className="block w-full">
                <Button className="w-full bg-amber-500 hover:bg-amber-400 text-stone-950 font-bold text-xs h-10 shadow-lg shadow-amber-500/20">
                  Start Saving Today <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
                </Button>
              </Link>
            </div>
          </div>
        </div>

        {/* FAQ Accordion */}
        <div className="max-w-3xl mx-auto space-y-8">
          <div className="text-center space-y-2">
            <h2 className="text-2xl sm:text-3xl font-bold text-white flex items-center justify-center gap-2">
              <HelpCircle className="h-6 w-6 text-amber-400" />
              Frequently Asked Questions
            </h2>
            <p className="text-xs sm:text-sm text-stone-400">
              Clear answers regarding sovereign architecture, billing, and telephony setup.
            </p>
          </div>

          <div className="space-y-3">
            {faqs.map((faq, index) => {
              const isOpen = openFaq === index;
              return (
                <div
                  key={index}
                  className="rounded-xl border border-white/10 bg-[#111214] overflow-hidden transition-colors"
                >
                  <button
                    type="button"
                    onClick={() => setOpenFaq(isOpen ? null : index)}
                    className="w-full p-4 sm:p-5 text-left flex items-center justify-between gap-4"
                  >
                    <span className="text-sm font-semibold text-white">{faq.q}</span>
                    <ChevronDown
                      className={`h-4 w-4 text-stone-400 shrink-0 transition-transform duration-200 ${
                        isOpen ? "rotate-180 text-amber-400" : ""
                      }`}
                    />
                  </button>
                  {isOpen && (
                    <div className="px-5 pb-5 text-xs sm:text-sm text-stone-400 leading-relaxed border-t border-white/5 pt-3">
                      {faq.a}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-white/5 bg-[#090a0b] py-12 text-stone-400 text-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded bg-amber-500 flex items-center justify-center text-stone-950 font-bold text-xs">
              K
            </div>
            <span className="font-semibold text-white">Kodewaves Voice AI Platform</span>
            <span className="text-stone-400">© 2026. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-6">
            <Link href="/" className="hover:text-amber-400 transition-colors">Platform</Link>
            <Link href="/pricing" className="hover:text-amber-400 transition-colors">Pricing</Link>
            <Link href="/auth/login" className="hover:text-amber-400 transition-colors">Login</Link>
            <Link href="/auth/signup" className="hover:text-amber-400 transition-colors">Sign Up</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
